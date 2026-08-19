from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from parsers import SourceChunk
from schemas import (
    AnalysisResponse,
    DocumentPreviewSection,
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


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise AgentConfigurationError(f"{name} 必须是 true 或 false。")


def _safe_endpoint_for_log(url: str) -> str:
    """Return an endpoint description without credentials, query, or fragment."""
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return "<已配置的 Agent Run endpoint>"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}{parsed.path}"
    except ValueError:
        return "<已配置的 Agent Run endpoint>"


def _agent_output_log_limit() -> int:
    raw_value = os.getenv("AGENTRUN_LOG_OUTPUT_MAX_CHARS", "30000").strip()
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning(
            "AGENTRUN_LOG_OUTPUT_MAX_CHARS=%r 无效，使用默认值 30000。",
            raw_value,
        )
        return 30_000
    return max(1_000, min(value, 200_000))


def _log_agentrun_output(output: str) -> None:
    if not _environment_flag("AGENTRUN_LOG_OUTPUT", False):
        return
    limit = _agent_output_log_limit()
    if len(output) > limit:
        rendered = output[:limit] + f"\n... [其余 {len(output) - limit} 个字符已截断]"
    else:
        rendered = output
    logger.info(
        "Agent Run 原始输出 BEGIN | 字符=%d | 日志上限=%d\n%s\n"
        "Agent Run 原始输出 END",
        len(output),
        limit,
        rendered,
    )


def _agentrun_request_payload(messages: list[dict[str, str]]) -> dict[str, Any]:
    model_name = os.getenv("AGENTRUN_MODEL_NAME", "").strip()
    if not model_name:
        raise AgentConfigurationError(
            "ANALYSIS_MODE=agentrun 时必须配置 AGENTRUN_MODEL_NAME。"
        )
    return {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "enable_search": _environment_flag("AGENTRUN_ENABLE_SEARCH", True),
    }


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

    try:
        timeout_seconds = float(os.getenv("AGENTRUN_TIMEOUT_SECONDS", "180"))
    except ValueError as exc:
        raise AgentConfigurationError(
            "AGENTRUN_TIMEOUT_SECONDS 必须是有效数字。"
        ) from exc
    endpoint = _chat_url()
    request_payload = _agentrun_request_payload(messages)
    started_at = time.perf_counter()
    logger.info(
        "Agent Run 请求开始 | endpoint=%s | 模型=%s | 消息=%d | 输入字符=%d | "
        "联网搜索=%s | 超时=%.1fs",
        _safe_endpoint_for_log(endpoint),
        request_payload["model"],
        len(messages),
        sum(len(message.get("content", "")) for message in messages),
        request_payload["enable_search"],
        timeout_seconds,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json=request_payload,
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "Agent Run 连接异常 | endpoint=%s | 耗时=%.2fs | 错误=%s",
            _safe_endpoint_for_log(endpoint),
            time.perf_counter() - started_at,
            exc,
        )
        raise AgentTransportError(f"无法连接 Agent Run：{exc}") from exc

    logger.info(
        "Agent Run HTTP 响应 | status=%d | 响应大小=%d bytes | 耗时=%.2fs",
        response.status_code,
        len(response.content),
        time.perf_counter() - started_at,
    )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise AgentTransportError(
            f"Agent Run 返回 HTTP {response.status_code}：{detail}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        _log_agentrun_output(response.text)
        raise ModelOutputError("Agent Run 返回的不是 JSON 响应。") from exc
    try:
        output = _content_from_response(payload)
    except ModelOutputError:
        _log_agentrun_output(json.dumps(payload, ensure_ascii=False, default=str))
        raise
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict):
        logger.info(
            "Agent Run token 用量 | prompt=%s | completion=%s | total=%s",
            usage.get("prompt_tokens", "unknown"),
            usage.get("completion_tokens", "unknown"),
            usage.get("total_tokens", "unknown"),
        )
    logger.info("Agent Run 消息提取完成 | 输出字符=%d", len(output))
    _log_agentrun_output(output)
    return output


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
    mode = _analysis_mode()
    logger.info(
        "分析器启动 | 文件=%r | 模式=%s | 来源块=%d | 文档字符=%d",
        filename,
        mode,
        len(chunks),
        sum(len(chunk.content) for chunk in chunks),
    )
    if mode == "mock":
        logger.info("使用 Mock 模式生成固定测试问题，不会调用 Agent Run。")
        return _mock_draft(chunks)
    if mode != "agentrun":
        raise AgentConfigurationError("ANALYSIS_MODE 只能是 mock 或 agentrun。")

    allowed_for_model = [
        f"{_model_source_id(index)}（{chunk.locator}）"
        for index, chunk in enumerate(chunks, start=1)
    ]
    logger.info(
        "开始组装 Agent Run 输入 | 来源块=%d | 允许的来源 ID=%d",
        len(chunks),
        len(allowed_for_model),
    )
    messages = _runtime_messages(chunks, filename)
    logger.info(
        "Agent Run 输入组装完成 | messages=%d | system字符=%d | user字符=%d",
        len(messages),
        len(messages[0]["content"]),
        len(messages[1]["content"]),
    )

    for attempt in range(2):
        logger.info(
            "Agent Run 生成尝试 %d/2 | 消息=%d",
            attempt + 1,
            len(messages),
        )
        raw_output = await _invoke_agentrun(messages)
        logger.info(
            "开始解析并校验 Agent Run 输出 | 尝试=%d | 输出字符=%d",
            attempt + 1,
            len(raw_output),
        )
        try:
            draft = _draft_from_text(raw_output)
        except ModelOutputError as exc:
            if attempt == 1:
                logger.error("Agent Run 第 2 次输出仍未通过校验 | %s", exc.repair_detail)
                raise
            feedback = exc.repair_detail
            logger.info("将校验反馈发送给 Agent Run 进行一次修复 | %s", feedback)
        else:
            logger.info(
                "Agent Run JSON/Schema 校验通过，开始核对来源引用 | 尝试=%d",
                attempt + 1,
            )
            invalid, repaired = _reconcile_source_ids(draft, chunks)
            if repaired:
                logger.info(
                    "已将 %d 个模型来源位置映射为内部 sourceId。",
                    repaired,
                )
            if not invalid:
                priority_counts = {"high": 0, "medium": 0, "low": 0}
                for question in draft.questions:
                    priority_counts[question.priority] += 1
                logger.info(
                    "Agent Run 输出校验通过 | 尝试=%d | 问题=%d | 高=%d | 中=%d | 低=%d",
                    attempt + 1,
                    len(draft.questions),
                    priority_counts["high"],
                    priority_counts["medium"],
                    priority_counts["low"],
                )
                for index, question in enumerate(draft.questions, start=1):
                    question_text = re.sub(r"\s+", " ", question.question).strip()
                    logger.info(
                        "Agent Run 问题 %02d | %s | %s | %s",
                        index,
                        question.priority,
                        question.category,
                        question_text,
                    )
                return draft
            logger.warning(
                "Agent Run 第 %d 次输出包含无法映射的 sourceId | %s",
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
            logger.info("将来源映射反馈发送给 Agent Run 进行一次修复。")

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
        documentPreview=[
            DocumentPreviewSection(locator=chunk.locator, content=chunk.content)
            for chunk in chunks
        ],
        questions=questions,
    )
