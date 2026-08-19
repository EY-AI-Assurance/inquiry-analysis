from __future__ import annotations

import asyncio
import json
import logging

from parsers import SourceChunk
import review_agent


def valid_payload(source_id: str = "csv-rows-1-2") -> dict:
    return {
        "questions": [
            {
                "question": f"请解释问题 {index + 1}。",
                "category": "非 GAAP 指标",
                "priority": "high" if index < 2 else "medium",
                "evidence": [
                    {
                        "sourceId": source_id,
                        "observation": "文件展示了 Adjusted EBITDA。",
                    }
                ],
                "regulatoryBasis": [
                    {
                        "authority": "C&DI 102.10",
                        "relevance": "需要检查法定指标的突出程度。",
                    }
                ],
                "answerDirections": ["准备版式和指标对照。"],
            }
            for index in range(8)
        ]
    }


def test_draft_accepts_json_fence_with_surrounding_text():
    text = "输出如下：\n```json\n" + json.dumps(valid_payload()) + "\n```\n完成。"
    draft = review_agent._draft_from_text(text)
    assert len(draft.questions) == 8


def test_draft_normalizes_common_model_variations():
    payload = valid_payload()
    first = payload["questions"][0]
    first["priority"] = "HIGH"
    first["evidence"] = first["evidence"][0]
    first["regulatoryBasis"] = first["regulatoryBasis"][0]
    first["answerDirections"] = first["answerDirections"][0]

    draft = review_agent._draft_from_text(json.dumps(payload))
    assert draft.questions[0].priority == "high"
    assert len(draft.questions[0].evidence) == 1
    assert draft.questions[0].answer_directions == ["准备版式和指标对照。"]


def test_runtime_uses_short_source_ids_for_model():
    chunks = [
        SourceChunk(
            source_id="sheet-1-rows-1-30",
            locator="工作表“利润表”行 1–30",
            content="Revenue",
            order=1,
        ),
        SourceChunk(
            source_id="sheet-1-rows-31-60",
            locator="工作表“利润表”行 31–60",
            content="Operating income",
            order=2,
        ),
    ]

    messages = review_agent._runtime_messages(chunks, "report.xlsx")
    document = json.loads(
        messages[1]["content"].removeprefix("<document>\n").removesuffix(
            "\n</document>"
        )
    )

    assert [source["sourceId"] for source in document["sources"]] == [
        "S001",
        "S002",
    ]


def test_agentrun_payload_sends_explicit_model_and_search(monkeypatch):
    monkeypatch.setenv("AGENTRUN_MODEL_NAME", "qwen3.7-plus")
    monkeypatch.setenv("AGENTRUN_ENABLE_SEARCH", "true")

    payload = review_agent._agentrun_request_payload(
        [{"role": "user", "content": "test"}]
    )

    assert payload == {
        "model": "qwen3.7-plus",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
        "enable_search": True,
    }


def test_agentrun_payload_requires_model(monkeypatch):
    monkeypatch.delenv("AGENTRUN_MODEL_NAME", raising=False)

    try:
        review_agent._agentrun_request_payload([])
    except review_agent.AgentConfigurationError as exc:
        assert "AGENTRUN_MODEL_NAME" in str(exc)
    else:
        raise AssertionError("missing AGENTRUN_MODEL_NAME must fail")


def test_safe_endpoint_log_removes_credentials_and_query():
    safe = review_agent._safe_endpoint_for_log(
        "https://user:secret@example.com:8443/invoke/chat?token=hidden#fragment"
    )

    assert safe == "https://example.com:8443/invoke/chat"
    assert "secret" not in safe
    assert "hidden" not in safe


def test_agent_output_logging_can_be_enabled(monkeypatch, caplog):
    monkeypatch.setenv("AGENTRUN_LOG_OUTPUT", "true")
    monkeypatch.setenv("AGENTRUN_LOG_OUTPUT_MAX_CHARS", "1000")
    caplog.set_level(logging.INFO, logger="inquiry-analysis.review-agent")

    review_agent._log_agentrun_output('{"questions":[{"question":"测试输出"}]}')

    assert "Agent Run 原始输出 BEGIN" in caplog.text
    assert "测试输出" in caplog.text
    assert "Agent Run 原始输出 END" in caplog.text


def test_analyze_retries_after_schema_validation_error(monkeypatch, caplog):
    responses = [
        json.dumps({"questions": []}),
        json.dumps(valid_payload()),
    ]
    received_messages: list[list[dict[str, str]]] = []

    async def fake_invoke(messages):
        received_messages.append([dict(message) for message in messages])
        return responses.pop(0)

    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")
    monkeypatch.setattr(review_agent, "_invoke_agentrun", fake_invoke)
    caplog.set_level(logging.INFO, logger="inquiry-analysis.review-agent")
    chunks = [
        SourceChunk(
            source_id="csv-rows-1-2",
            locator="CSV 行 1–2",
            content="item,value\nAdjusted EBITDA,100",
            order=1,
        )
    ]

    draft = asyncio.run(review_agent.analyze_document(chunks, "report.csv"))

    assert len(draft.questions) == 8
    assert len(received_messages) == 2
    assert received_messages[1][-2]["role"] == "assistant"
    assert "未通过服务端校验" in received_messages[1][-1]["content"]
    assert "Agent Run 生成尝试 1/2" in caplog.text
    assert "开始组装 Agent Run 输入" in caplog.text
    assert "Agent Run 输入组装完成" in caplog.text
    assert "开始解析并校验 Agent Run 输出" in caplog.text
    assert "Agent Run JSON/Schema 校验通过" in caplog.text
    assert "将校验反馈发送给 Agent Run" in caplog.text
    assert "Agent Run 输出校验通过" in caplog.text
    assert "Agent Run 问题 01" in caplog.text


def test_analyze_retries_invalid_source_id(monkeypatch):
    invalid = valid_payload(source_id="made-up-source")
    responses = [json.dumps(invalid), json.dumps(valid_payload())]

    async def fake_invoke(messages):
        return responses.pop(0)

    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")
    monkeypatch.setattr(review_agent, "_invoke_agentrun", fake_invoke)
    chunks = [
        SourceChunk(
            source_id="csv-rows-1-2",
            locator="CSV 行 1–2",
            content="item,value\nAdjusted EBITDA,100",
            order=1,
        )
    ]

    draft = asyncio.run(review_agent.analyze_document(chunks, "report.csv"))
    assert draft.questions[0].evidence[0].source_id == "csv-rows-1-2"


def test_analyze_maps_pdf_location_label_without_retry(monkeypatch):
    responses = [json.dumps(valid_payload(source_id="PDF 第 3 页"))]
    calls = 0

    async def fake_invoke(messages):
        nonlocal calls
        calls += 1
        return responses.pop(0)

    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")
    monkeypatch.setattr(review_agent, "_invoke_agentrun", fake_invoke)
    chunks = [
        SourceChunk(
            source_id="pdf-page-3",
            locator="PDF 第 3 页",
            content="Adjusted EBITDA reconciliation",
            order=3,
        )
    ]

    draft = asyncio.run(review_agent.analyze_document(chunks, "report.pdf"))

    assert calls == 1
    assert draft.questions[0].evidence[0].source_id == "pdf-page-3"


def test_analyze_maps_short_source_label_without_retry(monkeypatch):
    responses = [json.dumps(valid_payload(source_id="来源 S001（PDF 第 3 页）"))]

    async def fake_invoke(messages):
        return responses.pop(0)

    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")
    monkeypatch.setattr(review_agent, "_invoke_agentrun", fake_invoke)
    chunks = [
        SourceChunk(
            source_id="pdf-page-3",
            locator="PDF 第 3 页",
            content="Adjusted EBITDA reconciliation",
            order=3,
        )
    ]

    draft = asyncio.run(review_agent.analyze_document(chunks, "report.pdf"))

    assert draft.questions[0].evidence[0].source_id == "pdf-page-3"


def test_source_mapping_rejects_ambiguous_row_label():
    draft = review_agent._draft_from_text(
        json.dumps(valid_payload(source_id="行 1-30"))
    )
    chunks = [
        SourceChunk(
            source_id="sheet-1-rows-1-30",
            locator="工作表“利润表”行 1–30",
            content="Revenue",
            order=1,
        ),
        SourceChunk(
            source_id="sheet-2-rows-1-30",
            locator="工作表“分部”行 1–30",
            content="Segment revenue",
            order=2,
        ),
    ]

    invalid, repaired = review_agent._reconcile_source_ids(draft, chunks)

    assert invalid == {"行 1-30"}
    assert repaired == 0


def test_analysis_response_includes_original_document_preview():
    chunks = [
        SourceChunk(
            source_id="csv-rows-1-2",
            locator="CSV 行 1–2",
            content="项目 | 金额\n收入 | 100",
            order=1,
        )
    ]

    response = review_agent.build_analysis_response(
        draft=review_agent._draft_from_text(json.dumps(valid_payload())),
        chunks=chunks,
        filename="report.csv",
        warnings=[],
    )

    assert response.document_preview[0].locator == "CSV 行 1–2"
    assert response.document_preview[0].content == "项目 | 金额\n收入 | 100"
