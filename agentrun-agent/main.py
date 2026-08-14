from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# A manually built ZIP vendors Linux dependencies into ./python.
vendor_dir = Path(__file__).with_name("python")
if vendor_dir.is_dir():
    sys.path.insert(0, str(vendor_dir))

from agentrun.integration.langchain import AgentRunConverter, model
from agentrun.server import AgentRequest, AgentRunServer
from langchain.agents import create_agent

from system_prompt import BOOTSTRAP_SYSTEM_PROMPT


def configured_model():
    service_name = os.getenv("MODEL_SERVICE_NAME", "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip()
    if not service_name:
        raise RuntimeError("缺少 MODEL_SERVICE_NAME，请先配置 Agent Run 模型服务名称。")
    if model_name:
        return model(service_name, model=model_name)
    return model(service_name)


agent = create_agent(
    model=configured_model(),
    tools=[],
    system_prompt=BOOTSTRAP_SYSTEM_PROMPT,
)


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
        "modelServiceConfigured": bool(os.getenv("MODEL_SERVICE_NAME", "").strip()),
        "businessPromptsBundled": False,
    }


if __name__ == "__main__":
    server.start(port=int(os.getenv("AGENT_PORT", "9000")))
