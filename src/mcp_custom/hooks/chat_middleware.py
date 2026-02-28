"""
chat_middleware.py — Agent middleware hooks.
No LangChain dependency — uses plain functions instead of decorators.
"""

import contextvars
import uuid
from typing import Callable, Optional, Any

from utils.logging import get_logger

logger = get_logger(__name__)

_SENSITIVE_KEYS = {
    "api_key",
    "access_token",
    "authorization",
    "token",
    "password",
    "secret",
    "x-api-key",
    "apikey",
}

# GUI log output channel
_MCP_LOG_SINK = contextvars.ContextVar("mcp_log_sink", default=None)
_MCP_ACTIVE_TOOL_CALL_ID = contextvars.ContextVar(
    "mcp_active_tool_call_id", default=None
)


def set_mcp_log_sink(sink: Optional[Callable[[dict], None]]):
    return _MCP_LOG_SINK.set(sink)


def reset_mcp_log_sink(token):
    _MCP_LOG_SINK.reset(token)


def _mask_secrets(obj: Any) -> Any:
    """Recursive desensitization of keys/tokens."""
    try:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if str(k).lower() in _SENSITIVE_KEYS:
                    out[k] = "***"
                else:
                    out[k] = _mask_secrets(v)
            return out
        if isinstance(obj, list):
            return [_mask_secrets(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(_mask_secrets(x) for x in obj)
        return obj
    except Exception:
        return "***"


def make_tool_start_hook():
    """Create a tool start callback for AgentLoop."""

    async def on_tool_start(tool_name: str, args: dict, tool_call_id: str):
        sink = _MCP_LOG_SINK.get()
        safe_args = _mask_secrets(args)
        _MCP_ACTIVE_TOOL_CALL_ID.set(tool_call_id)

        if sink:
            sink(
                {
                    "type": "tool_start",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "args": safe_args,
                }
            )
        logger.info(f"[Agent tool start] {tool_name} args={safe_args}")

    return on_tool_start


def make_tool_end_hook():
    """Create a tool end callback for AgentLoop."""

    async def on_tool_end(tool_name: str, content: str, tool_call_id: str):
        sink = _MCP_LOG_SINK.get()
        summary = content[:200] if isinstance(content, str) else str(content)[:200]

        if sink:
            sink(
                {
                    "type": "tool_end",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "is_error": False,
                    "summary": _mask_secrets(summary),
                }
            )
        logger.info(f"[Agent tool finished] {tool_name}: {summary}")

    return on_tool_end


def make_tool_error_hook():
    """Create a tool error callback for AgentLoop."""

    async def on_tool_error(tool_name: str, content: str, tool_call_id: str):
        sink = _MCP_LOG_SINK.get()

        if sink:
            sink(
                {
                    "type": "tool_end",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "is_error": True,
                    "summary": _mask_secrets(content),
                }
            )
        logger.error(f"[Agent tool error] {tool_name}: {content}")

    return on_tool_error


async def on_progress(
    progress: float, total: float | None, message: str | None, context: Any
):
    """Progress callback for MCP tool execution."""
    sink = _MCP_LOG_SINK.get()
    if sink:
        sink(
            {
                "type": "tool_progress",
                "tool_call_id": _MCP_ACTIVE_TOOL_CALL_ID.get(),
                "name": getattr(context, "tool_name", ""),
                "progress": progress,
                "total": total,
                "message": message,
            }
        )
