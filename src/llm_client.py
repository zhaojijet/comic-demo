"""
llm_client.py — Lightweight OpenAI-compatible LLM client.
Replaces LangChain's ChatOpenAI with direct openai SDK calls.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI

try:
    from volcenginesdkarkruntime import AsyncArk
except ImportError:
    AsyncArk = None


@dataclass
class LLMConfig:
    """Configuration for an LLM endpoint."""

    model: str
    base_url: str
    api_key: str
    timeout: float = 30.0
    temperature: float = 0.1
    max_retries: int = 2


@dataclass
class ImageVideoLLMConfig:
    """Configuration for Image and Video LLM endpoints."""

    model: str
    base_url: str = ""
    api_key: str = ""
    timeout: float = 60.0
    max_retries: int = 2


class LLMClient:
    """
    Async OpenAI-compatible chat client.
    Supports text chat, tool calling, and vision (multimodal) inputs.
    """

    def __init__(self, config: Any, image_config: Any = None, video_config: Any = None):
        self.config = config
        self.image_config = image_config or config
        self.video_config = video_config or config

        self.is_ark = bool(config.base_url and "volces.com" in config.base_url)
        self.client = self._create_client(config)
        self.image_client = self._create_client(self.image_config)
        self.video_client = self._create_client(self.video_config)

    def _create_client(self, cfg: Any):
        is_ark = bool(cfg.base_url and "volces.com" in cfg.base_url)
        if is_ark and AsyncArk is not None:
            return AsyncArk(
                api_key=cfg.api_key,
                base_url=cfg.base_url.rstrip("/") if cfg.base_url else None,
                timeout=getattr(cfg, "timeout", 60.0),
                max_retries=getattr(cfg, "max_retries", 2),
            )
        else:
            return AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url.rstrip("/") if cfg.base_url else None,
                timeout=getattr(cfg, "timeout", 60.0),
                max_retries=getattr(cfg, "max_retries", 2),
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
            "model": kwargs.pop("model_override", self.config.model),
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

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_images: Optional[list[str]] = None,
        is_batch: bool = False,
        batch_size: int = 4,
        size: str = "2K",
        watermark: bool = True,
        stream: bool = False,
        model_override: Optional[str] = None,
    ) -> list[str] | Any:
        """
        Generate images via Volcengine Ark SDK (or standard OpenAI).
        Returns list of urls if stream=False, or AsyncStream if stream=True.
        """
        img_arg = None
        if reference_images:
            img_arg = (
                reference_images[0] if len(reference_images) == 1 else reference_images
            )

        is_ark = bool(
            self.image_config.base_url and "volces.com" in self.image_config.base_url
        )
        if is_ark and AsyncArk is not None:
            from volcenginesdkarkruntime.types.images.images import (
                SequentialImageGenerationOptions,
            )

            resp = await self.image_client.images.generate(
                model=model_override or self.image_config.model,
                prompt=prompt,
                image=img_arg,
                sequential_image_generation="auto" if is_batch else "disabled",
                sequential_image_generation_options=(
                    SequentialImageGenerationOptions(max_images=batch_size)
                    if is_batch
                    else None
                ),
                response_format="url",
                size=size,
                watermark=watermark,
                stream=stream,
            )

            if stream:
                return resp
            return [img.url for img in resp.data if img.url]

        else:
            # Fallback to standard OpenAI or extra_body method
            extra_body = {}
            if img_arg:
                extra_body["image"] = img_arg
            extra_body["sequential_image_generation"] = (
                "auto" if is_batch else "disabled"
            )

            resp = await self.image_client.images.generate(
                model=model_override or self.image_config.model,
                prompt=prompt,
                size=size,
                extra_body=extra_body,
            )
            return [img.url for img in resp.data if img.url]

    async def _stream_chat(self, params: dict) -> dict:
        """Stream a chat response and collect the full result."""
        stream = await self.client.chat.completions.create(**params, stream=True)
        content_parts = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                content_parts.append(delta.content)
        return {"role": "assistant", "content": "".join(content_parts)}

    @staticmethod
    async def download_media(url: str, save_path: str) -> str:
        """Download media from a URL to a local file asynchronously."""
        import httpx
        import aiofiles
        import os
        import asyncio

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    response = await client.get(url, timeout=60.0)
                    response.raise_for_status()
                    async with aiofiles.open(save_path, "wb") as f:
                        await f.write(response.content)
                    return save_path
                except httpx.RequestError as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(2)
        return save_path

    # Alias for backwards compatibility with tests
    download_image = download_media

    async def generate_video(
        self,
        prompt: str,
        *,
        reference_image: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> str:
        """
        Generate video via Volcengine Ark SDK (or others if supported).
        Returns the URL of the generated video.
        """
        is_ark = bool(
            self.video_config.base_url and "volces.com" in self.video_config.base_url
        )
        if is_ark and AsyncArk is not None:
            content = []

            # Text prompt with optional flags
            text_part = {"type": "text", "text": prompt}
            content.append(text_part)

            # Optional image reference
            if reference_image:
                content.append(
                    {"type": "image_url", "image_url": {"url": reference_image}}
                )

            resp = await self.video_client.content_generation.tasks.create(
                model=model_override or self.video_config.model, content=content
            )

            task_id = resp.id
            import asyncio

            while True:
                task_status = await self.video_client.content_generation.tasks.get(
                    task_id=task_id
                )
                if task_status.status == "succeeded":
                    return task_status.content.video_url
                elif task_status.status == "failed":
                    error_msg = (
                        task_status.error.message
                        if task_status.error
                        else "Unknown Error"
                    )
                    raise Exception(f"Video generation failed: {error_msg}")
                else:
                    await asyncio.sleep(3)
        else:
            raise NotImplementedError(
                "Video generation is currently only implemented for Volcengine Ark SDK."
            )


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create an LLMClient."""
    return LLMClient(config)
