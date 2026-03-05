"""
llm_client.py — Pluggable LLM client with Registry pattern.
Supports text chat, image generation, and video generation via
registered providers (OpenAI-compatible or Volcengine Ark SDK).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional

from openai import AsyncOpenAI

try:
    from volcenginesdkarkruntime import AsyncArk
except ImportError:
    AsyncArk = None


# ── Legacy Config Dataclasses (kept for backward compatibility) ────────────────


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


# ── LLM Registry ──────────────────────────────────────────────────────────────


class LLMRegistry:
    """
    Central registry for LLM providers across all categories.

    Categories: 'llm', 'image_llm', 'video_llm'
    Each category can have multiple named providers.
    """

    def __init__(self):
        # { category: { provider_id: { "config": ..., "client": ..., "meta": ... } } }
        self._providers: Dict[str, Dict[str, dict]] = {
            "llm": {},
            "image_llm": {},
            "video_llm": {},
        }
        self._defaults: Dict[str, str] = {}

    @staticmethod
    def _create_client(cfg: Any):
        """Create AsyncArk or AsyncOpenAI client based on base_url."""
        base_url = getattr(cfg, "base_url", "") or ""
        api_key = getattr(cfg, "api_key", "") or ""
        timeout = getattr(cfg, "timeout", 60.0)
        max_retries = getattr(cfg, "max_retries", 2)

        is_ark = bool(base_url and "volces.com" in base_url)
        if is_ark and AsyncArk is not None:
            return AsyncArk(
                api_key=api_key,
                base_url=base_url.rstrip("/") if base_url else None,
                timeout=timeout,
                max_retries=max_retries,
            )
        else:
            return AsyncOpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/") if base_url else None,
                timeout=timeout,
                max_retries=max_retries,
            )

    def register(
        self,
        category: str,
        provider_id: str,
        config: Any,
        *,
        display_name: str = "",
        description: str = "",
    ):
        """Register a provider under a category."""
        if category not in self._providers:
            self._providers[category] = {}

        client = self._create_client(config)
        self._providers[category][provider_id] = {
            "config": config,
            "client": client,
            "display_name": display_name
            or getattr(config, "display_name", provider_id),
            "description": description or getattr(config, "description", ""),
            "model": getattr(config, "model", ""),
        }

    def unregister(self, category: str, provider_id: str):
        """Remove a provider from the registry."""
        if category in self._providers:
            self._providers[category].pop(provider_id, None)
            # Clear default if it was the removed provider
            if self._defaults.get(category) == provider_id:
                del self._defaults[category]

    def set_default(self, category: str, provider_id: str):
        """Set the default provider for a category."""
        if category in self._providers and provider_id in self._providers[category]:
            self._defaults[category] = provider_id
        else:
            raise KeyError(
                f"Provider '{provider_id}' not found in category '{category}'"
            )

    def get_provider(self, category: str, provider_id: str) -> dict:
        """Get a specific provider entry (config + client + meta)."""
        if category not in self._providers:
            raise KeyError(f"Unknown category '{category}'")
        if provider_id not in self._providers[category]:
            raise KeyError(
                f"Provider '{provider_id}' not found in '{category}'. "
                f"Available: {list(self._providers[category].keys())}"
            )
        return self._providers[category][provider_id]

    def get_client(self, category: str, provider_id: str):
        """Get the API client for a specific provider."""
        return self.get_provider(category, provider_id)["client"]

    def get_config(self, category: str, provider_id: str):
        """Get the config for a specific provider."""
        return self.get_provider(category, provider_id)["config"]

    def get_default(self, category: str) -> dict:
        """Get the default provider entry for a category."""
        default_id = self._defaults.get(category)
        if default_id and default_id in self._providers.get(category, {}):
            return self._providers[category][default_id]
        # Fallback: first registered provider
        providers = self._providers.get(category, {})
        if providers:
            return next(iter(providers.values()))
        raise KeyError(f"No providers registered for category '{category}'")

    def get_default_id(self, category: str) -> str:
        """Get the default provider ID for a category."""
        default_id = self._defaults.get(category)
        if default_id and default_id in self._providers.get(category, {}):
            return default_id
        providers = self._providers.get(category, {})
        if providers:
            return next(iter(providers.keys()))
        raise KeyError(f"No providers registered for category '{category}'")

    def list_providers(self, category: str) -> list[dict]:
        """Return a serializable list of providers for a category."""
        providers = self._providers.get(category, {})
        return [
            {
                "id": pid,
                "display_name": entry["display_name"],
                "description": entry["description"],
                "model": entry["model"],
            }
            for pid, entry in providers.items()
        ]

    def get_all_providers_info(self) -> dict:
        """Return provider info for all categories (used by /api/providers)."""
        result = {}
        for category in ("llm", "image_llm", "video_llm"):
            try:
                default_id = self.get_default_id(category)
            except KeyError:
                default_id = ""
            result[category] = {
                "default": default_id,
                "providers": self.list_providers(category),
            }
        return result

    @classmethod
    def from_settings(cls, settings) -> "LLMRegistry":
        """
        Build a registry from a Settings object (config.py).
        Expects settings.llm, settings.image_llm, settings.video_llm
        to be LLMCategoryConfig instances.
        """
        registry = cls()

        for category_name in ("llm", "image_llm", "video_llm"):
            category_cfg = getattr(settings, category_name, None)
            if category_cfg is None:
                continue

            # LLMCategoryConfig has .providers dict and .default str
            providers = getattr(category_cfg, "providers", {})
            default_id = getattr(category_cfg, "default", "")

            for pid, pcfg in providers.items():
                registry.register(
                    category_name,
                    pid,
                    pcfg,
                    display_name=getattr(pcfg, "display_name", pid),
                    description=getattr(pcfg, "description", ""),
                )

            if default_id and default_id in providers:
                registry.set_default(category_name, default_id)

        return registry


# ── LLM Client ────────────────────────────────────────────────────────────────


class LLMClient:
    """
    Async LLM client that works with the LLMRegistry.

    Can be initialized in two ways:
    1. With a registry + provider IDs (new pluggable pattern)
    2. With raw config objects (legacy compatibility)
    """

    def __init__(
        self,
        config: Any = None,
        image_config: Any = None,
        video_config: Any = None,
        *,
        registry: Optional[LLMRegistry] = None,
        llm_provider_id: Optional[str] = None,
        image_provider_id: Optional[str] = None,
        video_provider_id: Optional[str] = None,
    ):
        self.registry = registry

        if registry is not None:
            # New registry-based initialization
            self._init_from_registry(
                registry, llm_provider_id, image_provider_id, video_provider_id
            )
        else:
            # Legacy: direct config initialization
            self.config = config
            self.image_config = image_config or config
            self.video_config = video_config or config

            self.client = self._create_client(config)
            self.image_client = self._create_client(self.image_config)
            self.video_client = self._create_client(self.video_config)

    def _init_from_registry(
        self,
        registry: LLMRegistry,
        llm_id: Optional[str],
        image_id: Optional[str],
        video_id: Optional[str],
    ):
        """Initialize clients from registry providers."""
        # Text LLM
        if llm_id:
            entry = registry.get_provider("llm", llm_id)
        else:
            entry = registry.get_default("llm")
        self.config = entry["config"]
        self.client = entry["client"]

        # Image LLM
        try:
            if image_id:
                img_entry = registry.get_provider("image_llm", image_id)
            else:
                img_entry = registry.get_default("image_llm")
            self.image_config = img_entry["config"]
            self.image_client = img_entry["client"]
        except KeyError:
            self.image_config = self.config
            self.image_client = self.client

        # Video LLM
        try:
            if video_id:
                vid_entry = registry.get_provider("video_llm", video_id)
            else:
                vid_entry = registry.get_default("video_llm")
            self.video_config = vid_entry["config"]
            self.video_client = vid_entry["client"]
        except KeyError:
            self.video_config = self.config
            self.video_client = self.client

    @staticmethod
    def _create_client(cfg: Any):
        base_url = getattr(cfg, "base_url", "") or ""
        api_key = getattr(cfg, "api_key", "") or ""
        is_ark = bool(base_url and "volces.com" in base_url)
        if is_ark and AsyncArk is not None:
            return AsyncArk(
                api_key=api_key,
                base_url=base_url.rstrip("/") if base_url else None,
                timeout=getattr(cfg, "timeout", 60.0),
                max_retries=getattr(cfg, "max_retries", 2),
            )
        else:
            return AsyncOpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/") if base_url else None,
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
            "model": kwargs.pop("model_override", None)
            or getattr(self.config, "model", ""),
            "messages": messages,
            "temperature": (
                temperature
                if temperature is not None
                else getattr(self.config, "temperature", 0.1)
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

        base_url = getattr(self.image_config, "base_url", "") or ""
        is_ark = bool(base_url and "volces.com" in base_url)
        if is_ark and AsyncArk is not None:
            from volcenginesdkarkruntime.types.images.images import (
                SequentialImageGenerationOptions,
            )

            resp = await self.image_client.images.generate(
                model=model_override or getattr(self.image_config, "model", ""),
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
                model=model_override or getattr(self.image_config, "model", ""),
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
        base_url = getattr(self.video_config, "base_url", "") or ""
        is_ark = bool(base_url and "volces.com" in base_url)
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
                model=model_override or getattr(self.video_config, "model", ""),
                content=content,
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
    """Factory function to create an LLMClient (legacy)."""
    return LLMClient(config)


def create_llm_client_from_registry(
    registry: LLMRegistry,
    *,
    llm_provider_id: Optional[str] = None,
    image_provider_id: Optional[str] = None,
    video_provider_id: Optional[str] = None,
) -> LLMClient:
    """Factory function to create an LLMClient from a registry."""
    return LLMClient(
        registry=registry,
        llm_provider_id=llm_provider_id,
        image_provider_id=image_provider_id,
        video_provider_id=video_provider_id,
    )
