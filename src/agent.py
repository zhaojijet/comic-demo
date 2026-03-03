"""
agent.py — Agent builder.
Uses direct OpenAI SDK (via LLMClient) and custom AgentLoop.
No LangChain dependency.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Any

from llm_client import LLMClient, LLMConfig
from agent_loop import AgentLoop, ToolDef
from config import Settings
from storage.agent_memory import ArtifactStore
from nodes.node_manager import NodeManager
from mcp_custom.sampling_handler import make_sampling_callback
from mcp_custom.hooks.chat_middleware import (
    make_tool_start_hook,
    make_tool_end_hook,
    make_tool_error_hook,
)
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ClientContext:
    cfg: Settings
    session_id: str
    media_dir: str
    bgm_dir: str
    outputs_dir: str
    node_manager: NodeManager
    chat_model_key: str
    pexels_api_key: Optional[str] = None
    tts_config: Optional[dict] = None
    llm_client: Optional[LLMClient] = None
    lang: str = "zh"


async def build_agent(
    cfg: Settings,
    session_id: str,
    store: ArtifactStore,
    *,
    llm_override: Optional[dict] = None,
):
    def _get(override: Optional[dict], key: str, default: Any) -> Any:
        return (
            override.get(key)
            if isinstance(override, dict) and key in override
            else default
        )

    def _norm_url(u: str) -> str:
        u = (u or "").strip()
        return u.rstrip("/") if u else u

    # 1) Build LLM client (replaces ChatOpenAI)
    llm_config = LLMConfig(
        model=_get(llm_override, "model", cfg.llm.model),
        base_url=_norm_url(_get(llm_override, "base_url", cfg.llm.base_url)),
        api_key=_get(llm_override, "api_key", cfg.llm.api_key),
        timeout=_get(llm_override, "timeout", cfg.llm.timeout),
        temperature=_get(llm_override, "temperature", cfg.llm.temperature),
        max_retries=_get(llm_override, "max_retries", cfg.llm.max_retries),
    )

    from llm_client import ImageVideoLLMConfig

    image_config = ImageVideoLLMConfig(
        model=cfg.image_llm.model,
        base_url=(
            _norm_url(cfg.image_llm.base_url)
            if cfg.image_llm.base_url
            else llm_config.base_url
        ),
        api_key=cfg.image_llm.api_key if cfg.image_llm.api_key else llm_config.api_key,
        timeout=cfg.image_llm.timeout,
        max_retries=cfg.image_llm.max_retries,
    )
    video_config = ImageVideoLLMConfig(
        model=cfg.video_llm.model,
        base_url=(
            _norm_url(cfg.video_llm.base_url)
            if cfg.video_llm.base_url
            else llm_config.base_url
        ),
        api_key=cfg.video_llm.api_key if cfg.video_llm.api_key else llm_config.api_key,
        timeout=cfg.video_llm.timeout,
        max_retries=cfg.video_llm.max_retries,
    )

    llm = LLMClient(llm_config, image_config=image_config, video_config=video_config)

    # 3) Connect to MCP server and get tools
    sampling_callback = make_sampling_callback(llm)

    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    server_url = cfg.local_mcp_server.url
    logger.info(f"[Agent] Connecting to MCP server at {server_url}")

    import contextlib

    exit_stack = contextlib.AsyncExitStack()

    http_ctx = streamablehttp_client(
        url=server_url,
        headers={"X-ComicDemo-Session-Id": session_id},
    )
    read_stream, write_stream, _ = await exit_stack.enter_async_context(http_ctx)

    mcp_session = ClientSession(
        read_stream,
        write_stream,
        sampling_callback=sampling_callback,
    )
    await exit_stack.enter_async_context(mcp_session)
    await mcp_session.initialize()

    # List available tools from MCP server
    tools_result = await mcp_session.list_tools()
    mcp_tools = tools_result.tools

    # Convert MCP tools to ToolDef
    tool_defs = []
    for t in mcp_tools:

        async def _make_caller(tool_name):
            async def caller(**kwargs):
                result = await mcp_session.call_tool(tool_name, kwargs)
                if result.isError:
                    raise Exception(f"MCP tool error: {result.content}")
                # Extract text content
                texts = []
                for block in result.content or []:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                return "\n".join(texts) if texts else ""

            return caller

        tool_defs.append(
            ToolDef(
                name=t.name,
                description=t.description or "",
                parameters=t.inputSchema or {"type": "object", "properties": {}},
                callable=await _make_caller(t.name),
                metadata=getattr(t, "metadata", None) or {},
            )
        )

    node_manager = NodeManager(tool_defs)

    # 4) Build AgentLoop (replaces create_agent)
    agent = AgentLoop(
        llm=llm,
        tools=tool_defs,
        max_iterations=30,
        on_tool_start=make_tool_start_hook(),
        on_tool_end=make_tool_end_hook(),
        on_tool_error=make_tool_error_hook(),
    )

    agent._exit_stack = exit_stack

    return agent, node_manager
