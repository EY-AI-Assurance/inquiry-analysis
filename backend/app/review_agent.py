from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from parsers import SourceChunk
from schemas import (
    AnalysisResponse,
    EvidenceDraft,
    EvidenceResponse,
    RegulatoryBasis,
    ReviewDraft,
    ReviewQuestionDraft,
    ReviewQuestionResponse,
)


class AgentConfigurationError(RuntimeError):
    pass


class AgentTransportError(RuntimeError):
    pass


class ModelOutputError(RuntimeError):
    def __init__(self, message: str, *, repair_detail: str | None = None):
        super().__init__(message)
        self.repair_detail = repair_detail or message


PROJECT_DIR = Path(__file__).resolve().parents[1]
logger = logging.getLogger("inquiry-analysis.review-agent")


@lru_cache(maxsize=8)
def _read_text(relative_path: str) -> str:
    return (PROJECT_DIR / relative_path).read_text(encoding="utf-8").strip()


def _analysis_mode() -> str:
    return os.getenv("ANALYSIS_MODE", "mock").strip().lower()


def _model_source_id(index: int) -> str:
    return f"S{index:03d}"


def _sources(chunks: list[SourceChunk]) -> list[dict[str, str]]:
    return [
        {
            "sourceId": _model_source_id(index),
            "location": chunk.locator,
            "content": chunk.content,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def _runtime_messages(chunks: list[SourceChunk], filename: str) -> list[dict[str, str]]:
    system_prompt = _read_text("prompts/system.md")
    skill = _read_text("skills/sec-review.md")
    task_prompt = _read_text("prompts/generate-questions.md")
    schema = ReviewDraft.model_json_schema(by_alias=True)

    trusted_runtime_prompt = "\n\n".join(
        [
            system_prompt,
            "<review_policy>\n" + skill + "\n</review_policy>",
            "<task_prompt>\n" + task_prompt + "\n</task_prompt>",
            "<output_schema>\n"
            + json.dumps(schema, ensure_ascii=False)
            + "\n</output_schema>",
        ]
    )
    document_payload = {
        "fileName": filename,
        "market": "SEC",
        "sources": _sources(chunks),
    }
    return [
        {"role": "system", "content": trusted_runtime_prompt},
        {
            "role": "user",
            "content": "<document>\n"
            + json.dumps(document_payload, ensure_ascii=False)
            + "\n</document>",
        },
    ]


def _chat_url() -> str:
    explicit = os.getenv("AGENTRUN_CHAT_COMPLETIONS_URL", "").strip()
    if explicit:
        return explicit
    base_url = os.getenv("AGENTRUN_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise AgentConfigurationError(
            "ANALYSIS_MODE=agentrun 时必须配置 AGENTRUN_CHAT_COMPLETIONS_URL。"
        )
    return f"{base_url}/openai/v1/chat/completions"


def _content_from_response(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelOutputError("Agent Run 没有返回 OpenAI 兼容的消息内容。") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts)
    raise ModelOutputError("Agent Run 返回了无法识别的消息内容。")


async def _invoke_agentrun(messages: list[dict[str, str]]) -> str:
    headers = {"content-type": "application/json"}
    api_key = os.getenv("AGENTRUN_API_KEY", "").strip()
    if api_key:
        auth_header = os.getenv("AGENTRUN_AUTH_HEADER", "X-API-Key").strip()
        auth_scheme = os.getenv("AGENTRUN_AUTH_SCHEME", "").strip()
        if not auth_header:
            raise AgentConfigurationError("AGENTRUN_AUTH_HEADER 不能为空。")
        headers[auth_header] = (
            f"{auth_scheme} {api_key}" if auth_scheme else api_key
        )

    timeout_seconds = float(os.getenv("AGENTRUN_TIMEOUT_SECONDS", "180"))
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                _chat_url(),
                headers=headers,
                json={"messages": messages, "stream": False},
            )
    except httpx.HTTPError as exc:
        raise AgentTransportError(f"无法连接 Agent Run：{exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        raise AgentTransportError(
            f"Agent Run 返回 HTTP {response.status_code}：{detail}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelOutputError("Agent Run 返回的不是 JSON 响应。") from exc
    return _content_from_response(payload)


def _json_value(text: str) -> Any:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for index, character in enumerate(candidate):
            if character not in "[{":
                continue
            try:
                payload, _ = decoder.raw_decode(candidate[index:])
                return payload
            except json.JSONDecodeError:
                continue
        raise ModelOutputError(
            "模型没有返回可解析的 JSON。",
            repair_detail=(
                f"JSON 语法错误位于第 {original_error.lineno} 行、"
                f"第 {original_error.colno} 列：{original_error.msg}"
            ),
        ) from original_error


def _as_list(value: Any) -> Any:
    if isinstance(value, list) or value is None:
        return value
    return [value]


def _normalize_draft_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {"questions": payload}
    if not isinstance(payload, dict):
        raise ModelOutputError(
            "模型返回的 JSON 顶层必须是对象。",
            repair_detail="JSON 顶层必须是包含 questions 数组的对象。",
        )

    if not isinstance(payload.get("questions"), list):
        for key in ("data", "result", "output"):
            nested = payload.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("questions"), list):
                payload = nested
                break

    normalized = dict(payload)
    questions = normalized.get("questions")
    if not isinstance(questions, list):
        return normalized

    priority_map = {
        "HIGH": "high",
        "高": "high",
        "高优先级": "high",
        "MEDIUM": "medium",
        "MODERATE": "medium",
        "中": "medium",
        "中优先级": "medium",
        "LOW": "low",
        "低": "low",
        "低优先级": "low",
    }
    normalized_questions: list[Any] = []
    for item in questions[:12]:
        if not isinstance(item, dict):
            normalized_questions.append(item)
            continue
        question = dict(item)
        priority = question.get("priority")
        if isinstance(priority, str):
            question["priority"] = priority_map.get(priority.strip(), priority.strip().lower())
        for key, maximum in (
            ("evidence", 5),
            ("regulatoryBasis", 5),
            ("regulatory_basis", 5),
            ("answerDirections", 6),
            ("answer_directions", 6),
        ):
            if key not in question:
                continue
            values = _as_list(question[key])
            question[key] = values[:maximum] if isinstance(values, list) else values
        normalized_questions.append(question)
    normalized["questions"] = normalized_questions
    return normalized


def _validation_detail(exc: ValidationError) -> str:
    issues: list[str] = []
    for error in exc.errors(include_url=False, include_input=False)[:12]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "root"
        issues.append(f"{location}: {error.get('msg', '校验失败')}")
    return "; ".join(issues)


def _json_object(text: str) -> dict[str, Any]:
    return _normalize_draft_payload(_json_value(text))
    return payload


def _draft_from_text(text: str) -> ReviewDraft:
    try:
        return ReviewDraft.model_validate(_json_object(text))
    except ModelOutputError:
        raise
    except ValidationError as exc:
        detail = _validation_detail(exc)
        logger.warning("Agent Run output schema validation failed: %s", detail)
        raise ModelOutputError(
            "模型返回的结果不符合问题数据结构。",
            repair_detail=detail,
        ) from exc


def _canonical_source_reference(value: str) -> str:
    """Normalize formatting without discarding meaningful words or numbers."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _source_aliases(chunk: SourceChunk) -> set[str]:
    aliases = {chunk.source_id, chunk.locator}

    if match := re.fullmatch(r"pdf-page-(\d+)", chunk.source_id):
        page = match.group(1)
        aliases.update(
            {
                f"page {page}",
                f"PDF page {page}",
                f"第 {page} 页",
                f"PDF 第 {page} 页",
            }
        )
    elif match := re.fullmatch(r"csv-rows-(\d+)-(\d+)", chunk.source_id):
        start, end = match.groups()
        aliases.update(
            {
                f"CSV rows {start}-{end}",
                f"CSV 行 {start}-{end}",
                f"行 {start}-{end}",
            }
        )
    elif match := re.fullmatch(
        r"sheet-(\d+)-rows-(\d+)-(\d+)", chunk.source_id
    ):
        sheet, start, end = match.groups()
        aliases.update(
            {
                f"sheet {sheet} rows {start}-{end}",
                f"工作表 {sheet} 行 {start}-{end}",
                f"行 {start}-{end}",
            }
        )
    elif match := re.fullmatch(
        r"word-paragraphs-(\d+)-(\d+)", chunk.source_id
    ):
        start, end = match.groups()
        aliases.update(
            {
                f"Word paragraphs {start}-{end}",
                f"Word 段落 {start}-{end}",
                f"段落 {start}-{end}",
            }
        )
    elif match := re.fullmatch(r"word-table-(\d+)", chunk.source_id):
        table = match.group(1)
        aliases.update(
            {
                f"Word table {table}",
                f"Word 表格 {table}",
                f"表格 {table}",
            }
        )

    return {
        canonical
        for alias in aliases
        if (canonical := _canonical_source_reference(alias))
    }


def _reconcile_source_ids(
    draft: ReviewDraft, chunks: list[SourceChunk]
) -> tuple[set[str], int]:
    """Map model-friendly location labels only when they identify one source."""
    allowed = {chunk.source_id for chunk in chunks}
    alias_index: dict[str, set[str]] = {}
    for index, chunk in enumerate(chunks, start=1):
        ordinal_aliases = {
            _model_source_id(index),
            f"source {index}",
            f"source-{index}",
            f"来源 {index}",
            f"来源-{index}",
        }
        for alias in _source_aliases(chunk):
            alias_index.setdefault(alias, set()).add(chunk.source_id)
        for alias in ordinal_aliases:
            canonical = _canonical_source_reference(alias)
            alias_index.setdefault(canonical, set()).add(chunk.source_id)

    invalid: set[str] = set()
    repaired = 0
    for question in draft.questions:
        for evidence in question.evidence:
            if evidence.source_id in allowed:
                continue
            canonical = _canonical_source_reference(evidence.source_id)
            candidates = alias_index.get(canonical, set())
            if not candidates:
                embedded_candidates: set[str] = set()
                for alias, source_ids in alias_index.items():
                    if len(alias) >= 4 and alias in canonical:
                        embedded_candidates.update(source_ids)
                candidates = embedded_candidates
            if len(candidates) == 1:
                evidence.source_id = next(iter(candidates))
                repaired += 1
            else:
                invalid.add(evidence.source_id)
    return invalid, repaired


def _source_ids_for_log(values: set[str]) -> list[str]:
    return [re.sub(r"[\r\n\t]+", " ", value)[:160] for value in sorted(values)]


def _mock_draft(chunks: list[SourceChunk]) -> ReviewDraft:
    source_id = chunks[0].source_id
    templates = [
        ("法定指标突出程度", "请说明法定 GAAP/IFRS 指标与非 GAAP 指标在本披露中的展示顺序和突出程度。", "high"),
        ("指标定义", "请完整定义披露中的非 GAAP 指标，并说明各调整项目是否在所有期间保持一致。", "high"),
        ("正常经营成本", "请说明被剔除项目为何不属于正常、重复发生的现金经营成本。", "high"),
        ("确认与计量", "请解释相关调整是否改变了 GAAP/IFRS 的确认时点或计量基础。", "high"),
        ("调整项筛选", "请分别量化各调整项，并说明纳入或排除项目所依据的客观标准。", "medium"),
        ("对称性", "请说明同类收益和损失是否采用一致、对称的调整政策。", "medium"),
        ("期间可比性", "请说明本期指标口径与比较期间是否一致，并量化所有口径变化。", "medium"),
        ("分部指标", "请说明分部指标是否与主要经营决策者实际使用的管理口径一致。", "medium"),
        ("调节表完整性", "请提供最可比法定指标到非 GAAP 指标的完整逐项调节。", "medium"),
        ("披露目的", "请说明管理层使用该指标的具体目的，以及该指标对投资者不应被单独依赖的原因。", "low"),
    ]
    questions = []
    for question, (category, text, priority) in enumerate(templates, start=1):
        questions.append(
            ReviewQuestionDraft(
                question=text,
                category=category,
                priority=priority,
                evidence=[
                    EvidenceDraft(
                        sourceId=source_id,
                        observation=f"本地 Mock 结果：已读取上传文件的第一个可用来源，用于验证问题 {question} 的展示流程。",
                    )
                ],
                regulatoryBasis=[
                    RegulatoryBasis(
                        authority="SEC Non-GAAP Financial Measures guidance",
                        relevance="Mock 模式只验证系统流程；正式规则关联由 Agent Run 模式生成。",
                    )
                ],
                answerDirections=[
                    "核对原始披露、会计记录与管理层口径。",
                    "准备逐项量化数据和期间一致性说明。",
                ],
            )
        )
    return ReviewDraft(questions=questions)


async def analyze_document(chunks: list[SourceChunk], filename: str) -> ReviewDraft:
    if _analysis_mode() == "mock":
        return _mock_draft(chunks)
    if _analysis_mode() != "agentrun":
        raise AgentConfigurationError("ANALYSIS_MODE 只能是 mock 或 agentrun。")

    allowed_for_model = [
        f"{_model_source_id(index)}（{chunk.locator}）"
        for index, chunk in enumerate(chunks, start=1)
    ]
    messages = _runtime_messages(chunks, filename)

    for attempt in range(2):
        raw_output = await _invoke_agentrun(messages)
        try:
            draft = _draft_from_text(raw_output)
        except ModelOutputError as exc:
            if attempt == 1:
                raise
            feedback = exc.repair_detail
        else:
            invalid, repaired = _reconcile_source_ids(draft, chunks)
            if repaired:
                logger.info(
                    "Mapped %d model evidence location label(s) to sourceId.",
                    repaired,
                )
            if not invalid:
                return draft
            logger.warning(
                "Agent Run returned unmapped sourceId values on attempt %d: %s",
                attempt + 1,
                _source_ids_for_log(invalid),
            )
            if attempt == 1:
                raise ModelOutputError("模型两次返回了无法映射到原文件的依据。")
            feedback = (
                "以下 sourceId 不存在："
                + "、".join(sorted(invalid))
                + "。允许的 sourceId 只有："
                + "、".join(allowed_for_model)
            )

        messages.extend(
            [
                {"role": "assistant", "content": raw_output},
                {
                    "role": "user",
                    "content": (
                        "上一次输出未通过服务端校验。校验问题："
                        + feedback
                        + "。请重新输出完整 JSON 对象，不要解释或使用 Markdown。"
                        "必须包含 8–12 个 questions；每个问题必须包含 question、"
                        "category、priority、evidence、regulatoryBasis 和 "
                        "answerDirections；priority 只能是 high、medium、low；"
                        "sourceId 只能逐字使用文档提供的值。"
                    ),
                },
            ]
        )

    raise ModelOutputError("模型输出修复失败。")


def build_analysis_response(
    *,
    draft: ReviewDraft,
    chunks: list[SourceChunk],
    filename: str,
    warnings: list[str],
) -> AnalysisResponse:
    locations = {chunk.source_id: chunk.locator for chunk in chunks}
    questions = []
    for index, question in enumerate(draft.questions, start=1):
        questions.append(
            ReviewQuestionResponse(
                id=f"q-{index:02d}",
                question=question.question,
                category=question.category,
                priority=question.priority,
                evidence=[
                    EvidenceResponse(
                        source=locations[evidence.source_id],
                        observation=evidence.observation,
                    )
                    for evidence in question.evidence
                ],
                regulatoryBasis=question.regulatory_basis,
                answerDirections=question.answer_directions,
            )
        )
    return AnalysisResponse(
        fileName=filename,
        warnings=warnings,
        questions=questions,
    )
