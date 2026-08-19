from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import main
from review_agent import AgentTimeoutError
from schemas import EvidenceDraft, RegulatoryBasis, ReviewDraft, ReviewQuestionDraft


client = TestClient(main.app)


def fake_draft() -> ReviewDraft:
    questions = []
    for index in range(8):
        questions.append(
            ReviewQuestionDraft(
                question=f"请解释问题 {index + 1}。",
                category="非 GAAP 指标",
                priority="high" if index < 2 else "medium",
                evidence=[
                    EvidenceDraft(
                        source_id="csv-rows-1-2",
                        references=["A2", "B2"],
                        observation="文件展示了 Adjusted EBITDA。",
                    )
                ],
                regulatory_basis=[
                    RegulatoryBasis(
                        authority="C&DI 102.10",
                        relevance="最可比指标必须同等或更突出。",
                    )
                ],
                answer_directions=["准备 GAAP 指标与版式对照。"],
            )
        )
    return ReviewDraft(questions=questions)


def test_health_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "super-secret")
    monkeypatch.setenv("AGENTRUN_MODEL_NAME", "qwen3.7-plus")
    monkeypatch.setenv("AGENTRUN_LOG_OUTPUT", "true")
    monkeypatch.setenv("AGENTRUN_TIMEOUT_SECONDS", "600")
    response = client.get("/health")
    assert response.status_code == 200
    assert "super-secret" not in response.text
    assert response.json()["agentRunModelName"] == "qwen3.7-plus"
    assert response.json()["agentRunTimeoutSeconds"] == 600
    assert response.json()["agentRunOutputLogging"] is True
    assert response.json()["sourceIdProtocol"] == "short-v1"


def test_backend_does_not_expose_agent_chat_protocol():
    response = client.post("/openai/v1/chat/completions", json={"messages": []})
    assert response.status_code == 404


def test_analyze_requires_proxy_token(monkeypatch):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "test-token")
    response = client.post(
        "/analyze",
        data={"reviewType": "SEC"},
        files={"file": ("report.csv", b"item,value\nrevenue,100\n", "text/csv")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_hkex_is_an_explicit_placeholder(monkeypatch):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "test-token")
    response = client.post(
        "/analyze",
        data={"reviewType": "HKEX"},
        files={"file": ("report.csv", b"item,value\nrevenue,100\n", "text/csv")},
        headers={"X-App-Token": "test-token"},
    )
    assert response.status_code == 422
    assert "筹备中" in response.json()["error"]["message"]


def test_success_response_matches_frontend_contract(monkeypatch, caplog):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "test-token")
    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")
    caplog.set_level(logging.INFO, logger="inquiry-analysis")

    async def fake_analyze_document(chunks, filename):
        assert filename == "report.csv"
        assert chunks[0].source_id == "csv-rows-1-2"
        return fake_draft()

    monkeypatch.setattr(main, "analyze_document", fake_analyze_document)
    response = client.post(
        "/analyze",
        data={"reviewType": "SEC"},
        files={"file": ("report.csv", "项目,金额\n收入,100\n".encode(), "text/csv")},
        headers={"X-App-Token": "test-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["fileName"] == "report.csv"
    assert payload["reviewType"] == "SEC"
    assert payload["documentPreview"] == [
        {
            "locator": "CSV 行 1–2",
            "content": (
                "第 1 行（列标题） | A列标题（A1）=项目 | B列标题（B1）=金额\n"
                "第 2 行 | 项目（A2）=收入 | 金额（B2）=100"
            ),
        }
    ]
    assert len(payload["questions"]) == 8
    assert payload["questions"][0]["evidence"][0]["source"] == "CSV 行 1–2"
    assert payload["questions"][0]["evidence"][0]["references"] == ["A2", "B2"]
    assert "sourceId" not in response.text
    assert "阶段 1/8：收到分析请求" in caplog.text
    assert "阶段 2/8：文件读取完成" in caplog.text
    assert "阶段 3/8：文档解析成功" in caplog.text
    assert "解析器已选择" in caplog.text
    assert "文档内容提取完成" in caplog.text
    assert "阶段 4/8：文档解析结果已准备，开始 Agent Run" in caplog.text
    assert "阶段 5/8：Agent Run 处理完成" in caplog.text
    assert "阶段 6/8：开始构造前端响应" in caplog.text
    assert "阶段 7/8：响应数据构造完成" in caplog.text
    assert "阶段 8/8：分析结束" in caplog.text


def test_agent_timeout_returns_distinct_gateway_timeout(monkeypatch):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "test-token")
    monkeypatch.setenv("ANALYSIS_MODE", "agentrun")

    async def fake_analyze_document(chunks, filename):
        raise AgentTimeoutError("Agent Run 在 600 秒内未完成分析。")

    monkeypatch.setattr(main, "analyze_document", fake_analyze_document)
    response = client.post(
        "/analyze",
        data={"reviewType": "SEC"},
        files={"file": ("report.csv", "项目,金额\n收入,100\n".encode(), "text/csv")},
        headers={"X-App-Token": "test-token"},
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "AGENTRUN_TIMEOUT"
