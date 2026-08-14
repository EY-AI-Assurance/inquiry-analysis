from __future__ import annotations

import logging
import os
import secrets
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse

from parsers import DocumentError, parse_document
from review_agent import (
    AgentConfigurationError,
    AgentTransportError,
    ModelOutputError,
    analyze_document,
    build_analysis_response,
)


MAX_FILE_BYTES = 50 * 1024 * 1024
logger = logging.getLogger("inquiry-analysis")
app = FastAPI(title="Financial Disclosure Inquiry Analysis API", version="0.2.0")


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def token_is_valid(received: str | None) -> bool:
    configured = os.getenv("BACKEND_APP_TOKEN", "")
    return bool(configured and received and secrets.compare_digest(configured, received))


@app.get("/health")
def health():
    mode = os.getenv("ANALYSIS_MODE", "mock").strip().lower()
    return {
        "status": "ok",
        "analysisMode": mode,
        "agentRunConfigured": bool(
            os.getenv("AGENTRUN_CHAT_COMPLETIONS_URL", "").strip()
            or os.getenv("AGENTRUN_BASE_URL", "").strip()
        ),
        "appTokenConfigured": bool(os.getenv("BACKEND_APP_TOKEN", "")),
        "supportedMarkets": ["SEC"],
        "sourceIdProtocol": "short-v1",
    }


@app.post("/analyze")
async def analyze(
    file: Annotated[UploadFile, File(...)],
    review_type: Annotated[str, Form(alias="reviewType")],
    x_app_token: Annotated[str | None, Header(alias="X-App-Token")] = None,
):
    if not os.getenv("BACKEND_APP_TOKEN", ""):
        return error_response(503, "APP_TOKEN_NOT_CONFIGURED", "后端尚未配置应用令牌。")
    if not token_is_valid(x_app_token):
        return error_response(401, "UNAUTHORIZED", "应用令牌无效。")
    if review_type.upper() != "SEC":
        return error_response(422, "UNSUPPORTED_REVIEW_TYPE", "联交所审查正在筹备中。")

    filename = file.filename or "uploaded-document"
    try:
        data = await file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return error_response(413, "FILE_TOO_LARGE", "单个文件不能超过 50 MB。")
        if not data:
            return error_response(422, "EMPTY_FILE", "文件内容为空，请重新选择。")

        try:
            max_chars = int(os.getenv("MAX_DOCUMENT_CHARS", "120000"))
        except ValueError:
            max_chars = 120_000
        parsed = parse_document(filename, data, max_chars=max_chars)
        draft = await analyze_document(parsed.chunks, filename)
        warnings = list(parsed.warnings)
        if os.getenv("ANALYSIS_MODE", "mock").strip().lower() == "mock":
            warnings.insert(
                0,
                "当前使用本地 Mock 模式：文件解析和页面流程是真实的，问题内容仅用于界面测试。",
            )
        response = build_analysis_response(
            draft=draft,
            chunks=parsed.chunks,
            filename=filename,
            warnings=warnings,
        )
        return JSONResponse(
            content=response.model_dump(mode="json", by_alias=True),
            headers={"Cache-Control": "no-store"},
        )
    except DocumentError as exc:
        return error_response(422, exc.code, str(exc))
    except AgentConfigurationError as exc:
        return error_response(503, "AGENTRUN_NOT_CONFIGURED", str(exc))
    except AgentTransportError as exc:
        logger.warning("Agent Run request failed: %s", exc)
        return error_response(502, "AGENTRUN_UNREACHABLE", str(exc))
    except ModelOutputError as exc:
        return error_response(502, "INVALID_MODEL_OUTPUT", str(exc))
    except Exception:
        logger.exception("Document analysis failed")
        return error_response(502, "ANALYSIS_FAILED", "分析服务暂时不可用，请稍后重试。")
    finally:
        await file.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("BACKEND_PORT", "8001")))
