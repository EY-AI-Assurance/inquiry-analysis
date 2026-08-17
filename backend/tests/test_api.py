from __future__ import annotations

from fastapi.testclient import TestClient

import main
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
    response = client.get("/health")
    assert response.status_code == 200
    assert "super-secret" not in response.text
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


def test_success_response_matches_frontend_contract(monkeypatch):
    monkeypatch.setenv("BACKEND_APP_TOKEN", "test-token")

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
                "第 1 行（列标题） | A列标题=项目 | B列标题=金额\n"
                "第 2 行 | 项目（A2）=收入 | 金额（B2）=100"
            ),
        }
    ]
    assert len(payload["questions"]) == 8
    assert payload["questions"][0]["evidence"][0]["source"] == "CSV 行 1–2"
    assert "sourceId" not in response.text
