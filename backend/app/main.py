from __future__ import annotations

import logging
import os
import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse
from dotenv import load_dotenv


# Load the backend's local configuration before importing modules that read
# environment variables. The local .env is authoritative when it exists, which
# prevents values exported by an older development session from selecting a
# stale Agent Run endpoint. Deployed environments do not include this file and
# continue to use variables injected by the hosting platform.
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=True)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("inquiry-analysis").setLevel(level)
    # The application emits a sanitized Agent Run endpoint and timing itself.
    # Suppress httpx/httpcore INFO lines because they can duplicate the request
    # and may include query parameters from the configured endpoint.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


configure_logging()

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
        "agentRunModelName": os.getenv("AGENTRUN_MODEL_NAME", "").strip() or None,
        "agentRunOutputLogging": os.getenv("AGENTRUN_LOG_OUTPUT", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
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
    request_id = secrets.token_hex(4)
    started_at = time.perf_counter()
    mode = os.getenv("ANALYSIS_MODE", "mock").strip().lower()
    logger.info(
        "[%s] 阶段 1/8：收到分析请求 | 文件=%r | 审查市场=%s | 模式=%s | Content-Type=%s",
        request_id,
        filename,
        review_type.upper(),
        mode,
        file.content_type or "unknown",
    )
    try:
        logger.info("[%s] 阶段 2/8：开始读取上传文件", request_id)
        data = await file.read(MAX_FILE_BYTES + 1)
        logger.info(
            "[%s] 阶段 2/8：文件读取完成 | 大小=%d bytes (%.1f KiB)",
            request_id,
            len(data),
            len(data) / 1024,
        )
        if len(data) > MAX_FILE_BYTES:
            logger.warning("[%s] 文件超过 50 MB 限制", request_id)
            return error_response(413, "FILE_TOO_LARGE", "单个文件不能超过 50 MB。")
        if not data:
            logger.warning("[%s] 文件内容为空", request_id)
            return error_response(422, "EMPTY_FILE", "文件内容为空，请重新选择。")

        try:
            max_chars = int(os.getenv("MAX_DOCUMENT_CHARS", "120000"))
        except ValueError:
            max_chars = 120_000
        parse_started_at = time.perf_counter()
        logger.info(
            "[%s] 阶段 3/8：开始解析文档 | 字符上限=%d",
            request_id,
            max_chars,
        )
        parsed = parse_document(filename, data, max_chars=max_chars)
        logger.info(
            "[%s] 阶段 3/8：文档解析成功 | 来源块=%d | 文本字符=%d | 警告=%d | 耗时=%.2fs",
            request_id,
            len(parsed.chunks),
            sum(len(chunk.content) for chunk in parsed.chunks),
            len(parsed.warnings),
            time.perf_counter() - parse_started_at,
        )
        logger.debug(
            "[%s] 来源定位 | %s",
            request_id,
            " | ".join(chunk.locator for chunk in parsed.chunks),
        )

        agent_started_at = time.perf_counter()
        if mode == "agentrun":
            logger.info(
                "[%s] 阶段 4/8：文档解析结果已准备，开始 Agent Run",
                request_id,
            )
        else:
            logger.info(
                "[%s] 阶段 4/8：开始 Mock 分析（不会调用 Agent Run）",
                request_id,
            )
        draft = await analyze_document(parsed.chunks, filename)
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        for question in draft.questions:
            priority_counts[question.priority] += 1
        logger.info(
            "[%s] 阶段 5/8：%s 处理完成 | 问题=%d | 高=%d | 中=%d | 低=%d | 耗时=%.2fs",
            request_id,
            "Agent Run" if mode == "agentrun" else "Mock",
            len(draft.questions),
            priority_counts["high"],
            priority_counts["medium"],
            priority_counts["low"],
            time.perf_counter() - agent_started_at,
        )
        warnings = list(parsed.warnings)
        if mode == "mock":
            warnings.insert(
                0,
                "当前使用本地 Mock 模式：文件解析和页面流程是真实的，问题内容仅用于界面测试。",
            )
        logger.info("[%s] 阶段 6/8：开始构造前端响应", request_id)
        response = build_analysis_response(
            draft=draft,
            chunks=parsed.chunks,
            filename=filename,
            warnings=warnings,
        )
        logger.info(
            "[%s] 阶段 7/8：响应数据构造完成 | 文档块=%d | 问题=%d",
            request_id,
            len(response.document_preview),
            len(response.questions),
        )
        logger.info(
            "[%s] 阶段 8/8：分析结束，正在返回结果 | 总耗时=%.2fs",
            request_id,
            time.perf_counter() - started_at,
        )
        return JSONResponse(
            content=response.model_dump(mode="json", by_alias=True),
            headers={"Cache-Control": "no-store"},
        )
    except DocumentError as exc:
        logger.warning(
            "[%s] 文件解析失败 | code=%s | 错误=%s | 总耗时=%.2fs",
            request_id,
            exc.code,
            exc,
            time.perf_counter() - started_at,
        )
        return error_response(422, exc.code, str(exc))
    except AgentConfigurationError as exc:
        logger.error(
            "[%s] Agent Run 配置错误 | %s | 总耗时=%.2fs",
            request_id,
            exc,
            time.perf_counter() - started_at,
        )
        return error_response(503, "AGENTRUN_NOT_CONFIGURED", str(exc))
    except AgentTransportError as exc:
        logger.warning(
            "[%s] Agent Run 请求失败 | %s | 总耗时=%.2fs",
            request_id,
            exc,
            time.perf_counter() - started_at,
        )
        return error_response(502, "AGENTRUN_UNREACHABLE", str(exc))
    except ModelOutputError as exc:
        logger.warning(
            "[%s] Agent Run 输出无效 | %s | 总耗时=%.2fs",
            request_id,
            exc,
            time.perf_counter() - started_at,
        )
        return error_response(502, "INVALID_MODEL_OUTPUT", str(exc))
    except Exception:
        logger.exception(
            "[%s] 未预期的分析错误 | 总耗时=%.2fs",
            request_id,
            time.perf_counter() - started_at,
        )
        return error_response(502, "ANALYSIS_FAILED", "分析服务暂时不可用，请稍后重试。")
    finally:
        await file.close()


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "后端启动 | 地址=http://127.0.0.1:%s | 模式=%s | 模型=%s | "
        "完整 Agent 输出日志=%s",
        os.getenv("BACKEND_PORT", "8001"),
        os.getenv("ANALYSIS_MODE", "mock").strip().lower(),
        os.getenv("AGENTRUN_MODEL_NAME", "").strip() or "未配置",
        os.getenv("AGENTRUN_LOG_OUTPUT", "false").strip().lower(),
    )
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("BACKEND_PORT", "8001")))
