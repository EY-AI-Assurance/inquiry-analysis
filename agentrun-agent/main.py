from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# A manually built ZIP vendors Linux dependencies into ./python.
vendor_dir = Path(__file__).with_name("python")
if vendor_dir.is_dir():
    sys.path.insert(0, str(vendor_dir))

from dotenv import load_dotenv
from agentrun.integration.langchain import AgentRunConverter, model
from agentrun.server import AgentRequest, AgentRunServer
from langchain.agents import create_agent

from system_prompt import BOOTSTRAP_SYSTEM_PROMPT

logger = logging.getLogger("inquiry-analysis.agentrun-agent")


def load_local_environment() -> Path | None:
    """Load local settings when present; cloud settings come from Runtime env."""
    candidates = (
        Path(__file__).with_name(".env"),
        Path(__file__).resolve().parent.parent / "agentrun-agent.env",
        Path.cwd() / "agentrun-agent.env",
    )
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


LOCAL_ENV_FILE = load_local_environment()
MODEL_SERVICE_NAME = os.getenv("MODEL_SERVICE_NAME", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "").strip()


def environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} 必须是 true 或 false。")


MODEL_ENABLE_SEARCH = environment_flag("MODEL_ENABLE_SEARCH", True)


def configured_model():
    if not MODEL_SERVICE_NAME:
        raise RuntimeError("缺少 MODEL_SERVICE_NAME，请先配置 Agent Run 模型服务名称。")
    if not MODEL_NAME:
        raise RuntimeError(
            "缺少 MODEL_NAME。为避免静默使用模型服务的默认模型，必须显式配置具体模型名称。"
        )
    logger.info(
        "Initializing Agent Run model service=%s model=%s local_env_loaded=%s",
        MODEL_SERVICE_NAME,
        MODEL_NAME,
        bool(LOCAL_ENV_FILE),
    )
    return model(MODEL_SERVICE_NAME, model=MODEL_NAME)


base_model = configured_model()


def create_runtime_agent(*, enable_search: bool):
    selected_model = base_model
    if enable_search:
        selected_model = base_model.model_copy(
            update={"extra_body": {"enable_search": True}}
        )
    return create_agent(
        model=selected_model,
        tools=[],
        system_prompt=BOOTSTRAP_SYSTEM_PROMPT,
    )


agents = {
    False: create_runtime_agent(enable_search=False),
    True: create_runtime_agent(enable_search=True),
}


def _input_from_request(request: AgentRequest) -> dict[str, Any]:
    return {
        "messages": [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
    }


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _final_content(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    if not messages:
        return ""
    last_message = messages[-1]
    if isinstance(last_message, dict):
        content = last_message.get("content")
    else:
        content = getattr(last_message, "content", None)
    return _content_as_text(content)


async def invoke_agent(request: AgentRequest):
    body = await request.raw_request.json() if request.raw_request else {}
    requested_model = str(body.get("model", "")).strip()
    if not requested_model:
        raise RuntimeError("请求体必须显式提供 model。")
    if requested_model != MODEL_NAME:
        raise RuntimeError(
            f"请求模型 {requested_model!r} 与 Runtime 配置的模型 {MODEL_NAME!r} 不一致。"
        )
    enable_search = body.get("enable_search", MODEL_ENABLE_SEARCH)
    if not isinstance(enable_search, bool):
        raise RuntimeError("enable_search 必须是 JSON 布尔值 true 或 false。")

    agent = agents[enable_search]
    agent_input = _input_from_request(request)
    if request.stream:
        converter = AgentRunConverter()

        async def stream_generator():
            async for event in agent.astream(agent_input, stream_mode="updates"):
                for item in converter.convert(event):
                    yield item

        return stream_generator()

    result = await agent.ainvoke(agent_input)
    content = _final_content(result)
    if not content:
        raise RuntimeError("模型调用完成，但没有返回可用的文本内容。")
    return content


server = AgentRunServer(invoke_agent=invoke_agent)
app = server.app


@app.get("/health")
def health():
    return {
        "status": "ok",
        "modelServiceConfigured": bool(MODEL_SERVICE_NAME),
        "modelServiceName": MODEL_SERVICE_NAME,
        "modelName": MODEL_NAME,
        "modelSelectionMode": "explicit",
        "enableSearchDefault": MODEL_ENABLE_SEARCH,
        "localEnvLoaded": bool(LOCAL_ENV_FILE),
        "businessPromptsBundled": False,
    }


if __name__ == "__main__":
    server.start(port=int(os.getenv("AGENT_PORT", "9000")))
