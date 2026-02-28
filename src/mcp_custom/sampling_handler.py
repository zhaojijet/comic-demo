"""
sampling_handler.py — MCP sampling callback.
Uses direct openai SDK (via LLMClient) instead of LangChain messages.
"""

import asyncio
import os
import math
import base64
from io import BytesIO
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from PIL import Image
from moviepy.video.io.VideoFileClip import VideoFileClip

from mcp.types import CreateMessageRequestParams, CreateMessageResult, TextContent


# -----------------------------
# Configurable parameters
# -----------------------------
DEFAULT_RESIZE_EDGE = 600
DEFAULT_JPEG_QUALITY = 80
DEFAULT_MIN_FRAMES = 2
DEFAULT_MAX_FRAMES = 6
DEFAULT_FRAMES_PER_SEC = 3.0
GLOBAL_MAX_IMAGE_BLOCKS = 48

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def _is_data_url(u: str) -> bool:
    return isinstance(u, str) and u.startswith("data:")


def _is_http_url(u: str) -> bool:
    return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))


def _strip_file_scheme(u: str) -> str:
    if not isinstance(u, str):
        return str(u)
    if u.startswith("file://"):
        parsed = urlparse(u)
        return parsed.path
    return u


def _guess_ext(path_or_url: str) -> str:
    try:
        p = urlparse(path_or_url).path if _is_http_url(path_or_url) else path_or_url
        return os.path.splitext(p)[1].lower()
    except Exception:
        return ""


def _resize_long_edge(img: Image.Image, long_edge: int) -> Image.Image:
    if long_edge <= 0:
        return img
    w, h = img.size
    le = max(w, h)
    if le <= long_edge:
        return img
    scale = long_edge / float(le)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return img.resize((nw, nh), Image.LANCZOS)


def _pil_to_data_url(img: Image.Image, resize_edge: int, jpeg_quality: int) -> str:
    img = img.convert("RGB")
    img = _resize_long_edge(img, resize_edge)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _image_path_to_data_url(path: str, resize_edge: int, jpeg_quality: int) -> str:
    img = Image.open(path)
    return _pil_to_data_url(img, resize_edge, jpeg_quality)


def _choose_num_frames(
    duration_sec: float, min_frames: int, max_frames: int, frames_per_sec: float
) -> int:
    duration_sec = max(0.0, float(duration_sec))
    n = int(math.ceil(duration_sec * frames_per_sec))
    n = max(min_frames, n)
    n = min(max_frames, n)
    return n


def _sample_video_segment_to_data_urls(
    video_path: str,
    in_sec: float,
    out_sec: float,
    resize_edge: int,
    jpeg_quality: int,
    min_frames: int,
    max_frames: int,
    frames_per_sec: float,
) -> List[Tuple[float, str]]:
    in_sec = float(in_sec)
    out_sec = float(out_sec)

    clip = VideoFileClip(video_path, audio=False)
    try:
        vdur = float(clip.duration or 0.0)

        if vdur <= 0:
            t = max(0.0, in_sec)
            frame = clip.get_frame(t)
            img = Image.fromarray(frame)
            return [(0.0, _pil_to_data_url(img, resize_edge, jpeg_quality))]

        in_sec = max(0.0, min(in_sec, vdur))
        out_sec = max(0.0, min(out_sec, vdur))

        if out_sec <= in_sec:
            frame = clip.get_frame(in_sec)
            img = Image.fromarray(frame)
            return [(0.0, _pil_to_data_url(img, resize_edge, jpeg_quality))]

        seg_dur = out_sec - in_sec
        n = _choose_num_frames(seg_dur, min_frames, max_frames, frames_per_sec)

        times = [((i + 0.5) / n) * seg_dur for i in range(n)]

        out: List[Tuple[float, str]] = []
        for rel_t in times:
            abs_t = in_sec + rel_t
            frame = clip.get_frame(abs_t)
            img = Image.fromarray(frame)
            out.append((rel_t, _pil_to_data_url(img, resize_edge, jpeg_quality)))
        return out
    finally:
        clip.close()


def _extract_text_from_mcp_content(content: Any) -> str:
    if content is None:
        return ""
    blocks = content if isinstance(content, list) else [content]
    texts: List[str] = []
    for b in blocks:
        if getattr(b, "type", None) == "text":
            texts.append(getattr(b, "text", "") or "")
    return "\n".join([t for t in (x.strip() for x in texts) if t])


def _normalize_media_items(media_inputs: List[Any]) -> List[Dict[str, Any]]:
    out = []
    for item in media_inputs or []:
        if isinstance(item, str):
            out.append({"url": item})
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 1:
            d = {"url": item[0]}
            if len(item) >= 2:
                d["in_sec"] = item[1]
            if len(item) >= 3:
                d["out_sec"] = item[2]
            out.append(d)
            continue
        if isinstance(item, dict):
            url = item.get("url") or item.get("path") or item.get("media")
            if not url:
                continue
            d = {"url": url}
            if "in_sec" in item:
                d["in_sec"] = item.get("in_sec")
            if "out_sec" in item:
                d["out_sec"] = item.get("out_sec")
            out.append(d)
            continue
    return out


def _build_media_blocks(
    media_inputs: List[Any],
    resize_edge: int,
    jpeg_quality: int,
    min_frames: int,
    max_frames: int,
    frames_per_sec: float,
    global_max_images: int,
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    img_count = 0
    items = _normalize_media_items(media_inputs)

    for idx, mi in enumerate(items):
        if img_count >= global_max_images:
            break

        raw_url = _strip_file_scheme(str(mi.get("url")))
        ext = _guess_ext(raw_url)
        in_sec = mi.get("in_sec")
        out_sec = mi.get("out_sec")
        has_segment = in_sec is not None and out_sec is not None

        if _is_data_url(raw_url):
            blocks.append({"type": "text", "text": f"Media {idx+1}: (data url image)"})
            blocks.append({"type": "image_url", "image_url": {"url": raw_url}})
            img_count += 1
            continue

        if _is_http_url(raw_url):
            if ext in VIDEO_EXTS:
                seg_info = f" segment [{in_sec},{out_sec}]s" if has_segment else ""
                blocks.append(
                    {
                        "type": "text",
                        "text": f"Media {idx+1}: remote video url{seg_info} (cannot sample frames locally): {raw_url}",
                    }
                )
                continue
            blocks.append({"type": "text", "text": f"Media {idx+1}: {raw_url}"})
            blocks.append({"type": "image_url", "image_url": {"url": raw_url}})
            img_count += 1
            continue

        path = raw_url
        if not os.path.exists(path):
            blocks.append(
                {"type": "text", "text": f"Media {idx+1}: (missing file) {path}"}
            )
            continue

        if ext in IMAGE_EXTS:
            data_url = _image_path_to_data_url(path, resize_edge, jpeg_quality)
            blocks.append(
                {
                    "type": "text",
                    "text": f"Media {idx+1}: image file {os.path.basename(path)}",
                }
            )
            blocks.append({"type": "image_url", "image_url": {"url": data_url}})
            img_count += 1
            continue

        if ext in VIDEO_EXTS:
            if has_segment:
                in_s = float(in_sec)
                out_s = float(out_sec)
            else:
                in_s = 0.0
                out_s = 1e12

            frames = _sample_video_segment_to_data_urls(
                video_path=path,
                in_sec=in_s,
                out_sec=out_s,
                resize_edge=resize_edge,
                jpeg_quality=jpeg_quality,
                min_frames=min_frames,
                max_frames=max_frames,
                frames_per_sec=frames_per_sec,
            )

            if has_segment:
                blocks.append(
                    {
                        "type": "text",
                        "text": f"Media {idx+1}: video segment {os.path.basename(path)} [{in_s:.2f}s, {out_s:.2f}s]",
                    }
                )
            else:
                blocks.append(
                    {
                        "type": "text",
                        "text": f"Media {idx+1}: video file {os.path.basename(path)}",
                    }
                )

            for fi, (rel_t, data_url) in enumerate(frames):
                if img_count >= global_max_images:
                    break
                blocks.append(
                    {
                        "type": "text",
                        "text": f"Frame {fi+1}/{len(frames)} (t≈{rel_t:.2f}s)",
                    }
                )
                blocks.append({"type": "image_url", "image_url": {"url": data_url}})
                img_count += 1
            continue

        blocks.append(
            {"type": "text", "text": f"Media {idx+1}: unsupported file type: {path}"}
        )

    return blocks


def make_sampling_callback(
    llm,  # LLMClient
    vlm,  # LLMClient
    *,
    resize_edge: int = DEFAULT_RESIZE_EDGE,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    min_frames: int = DEFAULT_MIN_FRAMES,
    max_frames: int = DEFAULT_MAX_FRAMES,
    frames_per_sec: float = DEFAULT_FRAMES_PER_SEC,
    global_max_images: int = GLOBAL_MAX_IMAGE_BLOCKS,
):
    """
    Callback for MCP server sampling requests.
    Uses direct OpenAI SDK (LLMClient) instead of LangChain messages.
    """

    async def sampling_callback(
        context, params: CreateMessageRequestParams
    ) -> CreateMessageResult:
        model_name = "unknown"
        try:
            # 1. System prompt
            system_prompt = getattr(params, "systemPrompt", None) or ""

            # 2. MCP messages → OpenAI format dicts
            mcp_messages = getattr(params, "messages", []) or []
            messages: List[Dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # 3. Metadata
            metadata = getattr(params, "metadata", None) or {}
            media_inputs = list(metadata.get("media", []) or [])
            top_p: float = float(metadata.get("top_p", 0.9))
            temperature: float = float(getattr(params, "temperature", None) or 0.6)
            max_tokens: int = int(getattr(params, "maxTokens", 4096) or 4096)

            # 4. Route to appropriate model
            use_multimodal = bool(media_inputs)
            model = vlm if use_multimodal else llm
            if model is None:
                model = vlm or llm
            model_name = model.config.model

            # 5. Build media blocks
            media_blocks: List[Dict[str, Any]] = []
            if use_multimodal:
                media_blocks = await asyncio.to_thread(
                    _build_media_blocks,
                    media_inputs,
                    resize_edge,
                    jpeg_quality,
                    min_frames,
                    max_frames,
                    frames_per_sec,
                    global_max_images,
                )

            # 6. Convert MCP messages to OpenAI format
            user_indices = [
                i
                for i, m in enumerate(mcp_messages)
                if getattr(m, "role", "") == "user"
            ]
            last_user_idx = user_indices[-1] if user_indices else None

            if not mcp_messages:
                content = (
                    [{"type": "text", "text": ""}] + media_blocks
                    if media_blocks
                    else ""
                )
                messages.append({"role": "user", "content": content})
            else:
                for i, m in enumerate(mcp_messages):
                    role = getattr(m, "role", "") or "user"
                    text = _extract_text_from_mcp_content(getattr(m, "content", None))

                    if role == "assistant":
                        messages.append({"role": "assistant", "content": text})
                        continue

                    if role == "user":
                        if (
                            last_user_idx is not None
                            and i == last_user_idx
                            and media_blocks
                        ):
                            content = [{"type": "text", "text": text}] + media_blocks
                            messages.append({"role": "user", "content": content})
                        else:
                            messages.append({"role": "user", "content": text})
                        continue

                    messages.append({"role": "user", "content": text})

            # 7. Call model via LLMClient
            if use_multimodal:
                text_out = await model.chat_with_vision(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
            else:
                result = await model.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                text_out = result.get("content", "")

            return CreateMessageResult(
                content=TextContent(type="text", text=text_out),
                model=str(model_name),
                role="assistant",
                stopReason="endTurn",
            )
        except Exception as e:
            return CreateMessageResult(
                content=TextContent(type="text", text=f"{type(e)}: {e}"),
                model=str(model_name),
                role="assistant",
                stopReason="error",
            )

    return sampling_callback
