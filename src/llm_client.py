"""
llm_client.py — Lightweight OpenAI-compatible LLM client.
Replaces LangChain's ChatOpenAI with direct openai SDK calls.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI


@dataclass
class LLMConfig:
    """Configuration for an LLM endpoint."""

    model: str
    base_url: str
    api_key: str
    timeout: float = 30.0
    temperature: float = 0.1
    max_retries: int = 2


class LLMClient:
    """
    Async OpenAI-compatible chat client.
    Supports text chat, tool calling, and vision (multimodal) inputs.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url.rstrip("/") if config.base_url else None,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Override default temperature.
            max_tokens: Maximum tokens in response.
            stream: Whether to stream the response.

        Returns:
            The assistant's message dict: {"role": "assistant", "content": "..."}
        """
        params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self.config.temperature
            ),
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        params.update(kwargs)

        if stream:
            return await self._stream_chat(params)

        response = await self.client.chat.completions.create(**params)
        choice = response.choices[0]
        msg = choice.message

        result = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return result

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict:
        """
        Chat with function/tool definitions available.

        Args:
            messages: Conversation history.
            tools: OpenAI tool definitions [{type: "function", function: {...}}].

        Returns:
            Assistant message dict, potentially with tool_calls.
        """
        return await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools if tools else None,
            **kwargs,
        )

    async def chat_with_vision(
        self,
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        top_p: float = 0.9,
    ) -> str:
        """
        Chat with multimodal (vision) content.
        Messages can contain image_url blocks in content.

        Returns:
            The text content of the assistant's response.
        """
        result = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )
        return result.get("content", "")

    async def _stream_chat(self, params: dict) -> dict:
        """Stream a chat response and collect the full result."""
        stream = await self.client.chat.completions.create(**params, stream=True)
        content_parts = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                content_parts.append(delta.content)
        return {"role": "assistant", "content": "".join(content_parts)}


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create an LLMClient."""
    return LLMClient(config)
