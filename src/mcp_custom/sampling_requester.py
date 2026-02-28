from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import SamplingMessage, TextContent, ModelHint, ModelPreferences

from utils.emoji import EmojiManager


class BaseLLMSampling(Protocol):
    # Low-level protocol: Sampling shared across multiple tools
    async def sampling(
        self,
        *,
        system_prompt: str | None,
        messages: list[SamplingMessage],
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        model_preferences: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        ...

@runtime_checkable
class LLMClient(Protocol):
    # High-level protocol: Tools are distinguished only by multimodal capability requirement
    async def complete(
        self,
        *,
        system_prompt: str | None,
        user_prompt: str,
        media: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        model_preferences: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        ...

class MCPSampler(BaseLLMSampling):
    def __init__(self, mcp_ctx: Context[ServerSession, object]):
        self._mcp_ctx = mcp_ctx

    def _to_mcp_model_preferences(
        self,
        model_preferences: dict[str, Any] | None,
    ) -> Optional[ModelPreferences]:
        if not model_preferences:
            return None

        raw_hints = model_preferences.get("hints")
        hints: list[ModelHint] | None = None
        if isinstance(raw_hints, list):
            hints = []
            for h in raw_hints:
                if isinstance(h, ModelHint):
                    hints.append(h)
                elif isinstance(h, dict):
                    hints.append(ModelHint(**h))
                elif isinstance(h, str):
                    hints.append(ModelHint(name=h))

        return ModelPreferences(
            hints=hints,
            costPriority=model_preferences.get("costPriority"),
            speedPriority=model_preferences.get("speedPriority"),
            intelligencePriority=model_preferences.get("intelligencePriority"),
        )
    
    def _extract_text(self, content: Any) -> str:
        emoji_manager = EmojiManager()

        # MCP returns content as either a single block or array; here we only extract text blocks
        if isinstance(content, list):
            texts: list[str] = []
            for block in content:
                if getattr(block, "type", None) == "text":
                    texts.append(block.text)
            return emoji_manager.remove_emoji("\n".join(texts).strip())

        if getattr(content, "type", None) == "text":
            return emoji_manager.remove_emoji(content.text.strip())

        
        return emoji_manager.remove_emoji(str(content))
    
    async def sampling(self,
        *, 
        system_prompt: str | None, 
        messages: list[SamplingMessage], 
        temperature: float = 0.3, 
        top_p: float = 0.9, 
        max_tokens: int = 4096, 
        model_preferences: dict[str, Any] | None = None, 
        metadata: dict[str, Any] | None = None, 
        stop_sequences: list[str] | None = None
    ) -> str:
        merged_metadata = dict(metadata or {})
        merged_metadata["top_p"] = top_p
        
        result = await self._mcp_ctx.session.create_message(
            messages=messages,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=temperature,
            # stop_sequences=stop_sequences,
            metadata=merged_metadata,
            # model_preferences=self._to_mcp_model_preferences(model_preferences),
        )
        return self._extract_text(result.content)
    
class SamplingLLMClient(LLMClient):
    """
    Only differentiate based on presence of media input.
    Server passes media paths and timestamps to Client, Client handles base64 conversion.
    """

    def __init__(self, sampler: BaseLLMSampling):
        self._sampler = sampler

    async def complete(self,
        *,
        system_prompt: str | None,
        user_prompt: str,
        media: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        model_preferences: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        stop_sequences: list[str] | None = None
    )-> str:
        messages = [
            SamplingMessage(
                role="user",
                content=TextContent(type="text", text=user_prompt),
            )
        ]

        merged_metadata = dict(metadata or {})
        merged_metadata["modality"] = "multimodal" if media else "text"
        if media:
            merged_metadata["media"] = media # Critical: Pass media paths and timestamps through transparently

        return await self._sampler.sampling(
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_preferences=model_preferences,
            metadata=merged_metadata,
            stop_sequences=stop_sequences,
        )

def make_llm(mcp_ctx: Context[ServerSession, object]) -> LLMClient:
    # Tools can directly call llm.complete() via llm = make_llm(ctx)
    return SamplingLLMClient(MCPSampler(mcp_ctx))
    
