import os
import sys
import json
import asyncio
import base64
import mimetypes
import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

# Ensure we can import from local src
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
COMICDEMO_SRC = os.path.join(ROOT_DIR, "src")
if COMICDEMO_SRC not in sys.path:
    sys.path.insert(0, COMICDEMO_SRC)

from agent import build_agent, ClientContext
from config import load_settings
from llm_client import LLMRegistry, LLMClient
from storage.agent_memory import ArtifactStore
from utils.logging import get_logger

logger = get_logger(__name__)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Comic Demo - AI 漫剧创作代理")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize settings and store
CONFIG_PATH = os.path.join(ROOT_DIR, "config.toml")
settings = load_settings(CONFIG_PATH)

# ── Initialize LLM Registry from settings ─────────────────────────────────────
llm_registry = LLMRegistry.from_settings(settings)
logger.info(
    f"[Registry] Initialized with providers: "
    f"llm={list(llm_registry._providers.get('llm', {}).keys())}, "
    f"image_llm={list(llm_registry._providers.get('image_llm', {}).keys())}, "
    f"video_llm={list(llm_registry._providers.get('video_llm', {}).keys())}"
)


# ── WebSocket Gateway (inspired by openclaw) ──────────────────────────────────


class HistoryStore:
    """Handles persistence of session history to a JSON file."""

    def __init__(self, data_dir: str):
        self.data_path = os.path.join(data_dir, "history.json")
        os.makedirs(data_dir, exist_ok=True)
        self.history = self.load()

    def load(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[HistoryStore] Error loading history: {e}")
        return []

    def save(self):
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[HistoryStore] Error saving history: {e}")

    def add_session(self, session):
        self.history.append(session)
        self.save()

    def get_all(self):
        return self.history


history_store = HistoryStore(os.path.join(ROOT_DIR, "data"))


class SessionManager:
    """Manages active WebSocket sessions, inspired by openclaw's session model."""

    def __init__(self):
        self.active_sessions: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_sessions[session_id] = websocket
        logger.info(f"[Gateway] Session connected: {session_id}")
        # Send history on connection
        await self.send_event(
            session_id, {"type": "history", "content": history_store.get_all()}
        )

    def disconnect(self, session_id: str):
        self.active_sessions.pop(session_id, None)
        logger.info(f"[Gateway] Session disconnected: {session_id}")

    async def send_event(self, session_id: str, event: dict):
        ws = self.active_sessions.get(session_id)
        if ws:
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.error(f"[Gateway] Failed to send event to {session_id}: {e}")


session_manager = SessionManager()


async def stream_comic_creation(session_id: str, user_prompt: str):
    """Execute comic creation pipeline and stream progress events via WebSocket."""
    try:
        # ── Phase 1: Initialization ──
        await session_manager.send_event(
            session_id,
            {
                "type": "system",
                "content": "🚀 正在初始化漫剧创作代理...",
            },
        )

        artifact_store = ArtifactStore(
            os.path.join(ROOT_DIR, ".comic_demo", "artifacts"),
            session_id=session_id,
        )

        # ── Phase 2: Build Agent ──
        await session_manager.send_event(
            session_id,
            {
                "type": "node_start",
                "node": "AgentBuilder",
                "content": "正在构建 AI 代理和工具链...",
            },
        )

        agent, node_manager = await build_agent(
            cfg=settings, session_id=session_id, store=artifact_store
        )

        await session_manager.send_event(
            session_id,
            {
                "type": "node_complete",
                "node": "AgentBuilder",
                "content": "AI 代理构建完成，开始漫剧创作流水线。",
            },
        )

        # ── Phase 3: Pipeline Execution ──
        # Stream the available nodes as progress context
        node_names = [
            "ComicScriptNode",
            "ComicStyleNode",
            "ComicCharacterNode",
            "ComicStoryboardNode",
            "ComicStoryboardImageNode",
            "ComicImage2VideoNode",
        ]

        await session_manager.send_event(
            session_id,
            {
                "type": "pipeline_info",
                "nodes": node_names,
                "content": f"漫剧流水线已就绪，共 {len(node_names)} 个工作节点。",
            },
        )

        try:
            # Execute the agent
            result = await agent.ainvoke(
                {
                    "input": f"Help me create a comic based on: {user_prompt}",
                    "chat_history": [],
                }
            )
        finally:
            # Teardown the MCP connection
            if hasattr(agent, "_exit_stack"):
                await agent._exit_stack.aclose()

        # ── Phase 4: Completion ──
        await session_manager.send_event(
            session_id,
            {
                "type": "complete",
                "content": "✅ 漫剧创作完成！",
                "result": (
                    str(result.get("output", result))
                    if isinstance(result, dict)
                    else str(result)
                ),
            },
        )

    except Exception as e:
        logger.error(f"[Gateway] Pipeline error for {session_id}: {e}")
        await session_manager.send_event(
            session_id,
            {
                "type": "error",
                "content": f"❌ 创作过程中发生错误: {str(e)}",
            },
        )


async def execute_single_node(session_id: str, node_key: str):
    """单独执行一个工作流节点并返回结果到前端。"""
    from agent import build_agent

    node_mapping = {
        "script": "ComicScriptNode",
        "style": "ComicStyleNode",
        "character": "ComicCharacterNode",
        "storyboard": "ComicStoryboardNode",
        "storyboard_image": "ComicStoryboardImageNode",
        "image2video": "ComicImage2VideoNode",
    }

    tool_name = node_mapping.get(node_key)
    if not tool_name:
        await session_manager.send_event(
            session_id, {"type": "error", "content": f"未知节点类型: {node_key}"}
        )
        return

    await session_manager.send_event(
        session_id,
        {
            "type": "node_start",
            "node": tool_name,
            "content": f"开始单节点运行: {tool_name}...",
        },
    )

    try:
        # 正确传参给 build_agent(cfg, session_id, store)
        from storage.agent_memory import ArtifactStore

        store = ArtifactStore(
            session_id=session_id, artifacts_dir=settings.project.outputs_dir
        )

        agent, _ = await build_agent(settings, session_id, store)

        tool = None
        for t in agent.tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool or not tool.callable:
            raise ValueError(f"Agent tool {tool_name} 未正确注册或缺少可调用对象。")

        # 运行节点
        result = (
            await tool.caller()
        )  # AgentLoop's ToolDef uses caller for encapsulated call

        # 处理结果中的媒体路径以便前端访问
        if isinstance(result, str) and result.startswith("outputs/"):
            result_display = (
                f"IMAGE_PATH:{result}"
                if result.endswith((".png", ".jpg", ".jpeg"))
                else f"VIDEO_PATH:{result}"
            )
        else:
            result_display = str(result)

        await session_manager.send_event(
            session_id,
            {
                "type": "node_complete",
                "node": tool_name,
                "content": f"节点 {tool_name} 运行完毕。",
            },
        )
        await session_manager.send_event(
            session_id,
            {
                "type": "complete",
                "content": f"✅ {tool_name} 执行成功！结果如下:",
                "result": result_display,
            },
        )
    except Exception as e:
        logger.error(f"[Gateway] Node Execution Error for {tool_name}: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await session_manager.send_event(
            session_id, {"type": "error", "content": f"❌ 执行异常: {str(e)}"}
        )
    finally:
        if "agent" in locals() and hasattr(agent, "_exit_stack"):
            await agent._exit_stack.aclose()


def _resolve_provider(category: str, provider_id: Optional[str]) -> tuple:
    """
    Resolve a provider from the registry.
    Returns (client, config, model_name) tuple.
    """
    if provider_id:
        try:
            entry = llm_registry.get_provider(category, provider_id)
        except KeyError:
            # Fallback to default if invalid provider_id
            logger.warning(
                f"[Registry] Provider '{provider_id}' not found in '{category}', "
                f"using default"
            )
            entry = llm_registry.get_default(category)
    else:
        entry = llm_registry.get_default(category)

    return entry["client"], entry["config"], entry["model"]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket Gateway endpoint — inspired by openclaw's WS control plane."""
    session_id = None
    try:
        # Accept connection with a temporary ID
        import uuid

        session_id = str(uuid.uuid4())[:8]
        await session_manager.connect(session_id, websocket)

        # Send welcome event
        await session_manager.send_event(
            session_id,
            {
                "type": "connected",
                "session_id": session_id,
                "content": "已连接到 Comic Demo Gateway。请发送您的漫剧构思。",
            },
        )

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                message = {"type": "chat", "content": data}

            msg_type = message.get("type", "chat")

            if msg_type == "ping":
                await session_manager.send_event(session_id, {"type": "pong"})

            elif msg_type == "chat":
                user_prompt = message.get("content", "")
                if not user_prompt.strip():
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "error",
                            "content": "请输入漫剧构思内容。",
                        },
                    )
                    continue

                # Echo user message back for chat history
                await session_manager.send_event(
                    session_id,
                    {
                        "type": "user_message",
                        "content": user_prompt,
                    },
                )

                # Run the comic creation pipeline in the background
                asyncio.create_task(stream_comic_creation(session_id, user_prompt))

            # ── LLM Test Messages (pluggable via registry) ────────────────
            if msg_type in ("test_llm", "test_image_llm", "test_video_llm"):
                # Parse JSON string from frontend
                content_obj = message.get("content", "")
                user_content = ""
                frontend_provider_id = None

                if isinstance(content_obj, str) and content_obj.startswith("{"):
                    try:
                        content_dict = json.loads(content_obj)
                        user_content = content_dict.get("text", "").strip()
                        frontend_provider_id = content_dict.get("provider_id", "")
                    except Exception:
                        user_content = content_obj.strip()
                else:
                    user_content = str(content_obj).strip()

            if msg_type == "test_llm":
                user_content = user_content or "你好，请用一句话自我介绍"
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "正在调用文本大模型..."},
                )
                try:
                    client, cfg, model_name = _resolve_provider(
                        "llm", frontend_provider_id
                    )
                    llm_client = LLMClient(cfg)

                    resp = await llm_client.chat(
                        [{"role": "user", "content": user_content}],
                    )
                    params = {"model": model_name}
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "complete",
                            "input": user_content,
                            "content": "文本 LLM 回复",
                            "result": resp.get("content", str(resp)),
                            "params": params,
                        },
                    )
                    history_store.add_session(
                        {
                            "id": f"srv_{int(asyncio.get_event_loop().time() * 1000)}",
                            "timestamp": datetime.now().isoformat(),
                            "mode": "llm",
                            "input": user_content,
                            "output": resp.get("content", str(resp)),
                            "params": params,
                        }
                    )
                except Exception as e:
                    await session_manager.send_event(
                        session_id, {"type": "error", "content": f"LLM 调用失败: {e}"}
                    )

            elif msg_type == "test_image_llm":
                user_content = user_content or "一个赛博朋克机械师角色设定图，半身像"
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "正在调用图片生成模型..."},
                )
                try:
                    client, cfg, model_name = _resolve_provider(
                        "image_llm", frontend_provider_id
                    )
                    llm_client = LLMClient(cfg)

                    urls = await llm_client.generate_image(user_content)
                    if urls:
                        local_urls = []
                        for idx, img_url in enumerate(urls):
                            filename = f"gen_img_{int(asyncio.get_event_loop().time() * 1000)}_{idx}.png"
                            save_path = os.path.join(
                                settings.project.outputs_dir, filename
                            )
                            await llm_client.download_media(img_url, save_path)
                            local_urls.append(f"/outputs/{filename}")

                        params = {"model": model_name}
                        event = {
                            "type": "complete",
                            "input": user_content,
                            "content": "图片生成完成",
                            "result": "生图成功！",
                            "media_type": "image",
                            "media_urls": local_urls,
                            "params": params,
                        }
                        await session_manager.send_event(session_id, event)
                        history_store.add_session(
                            {
                                "id": f"srv_{int(asyncio.get_event_loop().time() * 1000)}",
                                "timestamp": datetime.now().isoformat(),
                                "mode": "image-llm",
                                "input": user_content,
                                "output": "图片生成完成",
                                "mediaType": "image",
                                "mediaUrl": local_urls[0] if local_urls else None,
                                "params": params,
                            }
                        )
                    else:
                        await session_manager.send_event(
                            session_id,
                            {
                                "type": "complete",
                                "content": "图片生成完成",
                                "result": "生图失败，返回为空",
                            },
                        )
                except Exception as e:
                    await session_manager.send_event(
                        session_id,
                        {"type": "error", "content": f"图片生成失败: {e}"},
                    )

            elif msg_type == "test_video_llm":
                user_content = user_content or "赛博朋克城市里的飞行汽车呼啸而过"

                # ── Parse video generation parameters from frontend ──
                video_ratio = "16:9"
                video_resolution = "720p"
                video_duration = 5
                video_seed = -1
                video_camera_fixed = False
                video_watermark = True
                first_frame_image = None
                last_frame_image_url = None
                ref_style_image = None
                sample_video_url = None

                if isinstance(content_obj, str) and content_obj.startswith("{"):
                    try:
                        vp = json.loads(content_obj)
                        video_ratio = vp.get("ratio", "16:9")
                        video_resolution = vp.get("resolution", "720p")
                        video_duration = int(vp.get("duration", 5))
                        video_seed = int(vp.get("seed", -1))
                        video_camera_fixed = bool(vp.get("camera_fixed", False))
                        video_watermark = bool(vp.get("watermark", True))
                        first_frame_image = vp.get("first_frame_image") or None
                        last_frame_image_url = vp.get("last_frame_image") or None
                        # Support multi-image ref_style_images array
                        raw_ref_images = vp.get("ref_style_images") or []
                        ref_style_image = vp.get("ref_style_image") or None
                        sample_video_url = vp.get("sample_video") or None
                    except Exception:
                        pass

                # ── Convert local paths to base64 data URIs for API ──
                def _local_path_to_data_uri(rel_path: str) -> str | None:
                    """Convert a local relative path like /outputs/uploads/xx.png
                    to a base64 data URI that the Volcengine API accepts."""
                    if not rel_path:
                        return None
                    # If it's already a full URL or data URI, pass through
                    if rel_path.startswith(("http://", "https://", "data:")):
                        return rel_path
                    # Resolve local file path
                    abs_path = os.path.join(ROOT_DIR, rel_path.lstrip("/"))
                    if not os.path.isfile(abs_path):
                        logger.warning(f"[VideoGen] File not found: {abs_path}")
                        return None
                    mime, _ = mimetypes.guess_type(abs_path)
                    if not mime:
                        mime = "image/png"
                    with open(abs_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    return f"data:{mime};base64,{b64}"

                first_frame_image = (
                    _local_path_to_data_uri(first_frame_image)
                    if first_frame_image
                    else None
                )
                last_frame_image_url = (
                    _local_path_to_data_uri(last_frame_image_url)
                    if last_frame_image_url
                    else None
                )
                ref_style_image = (
                    _local_path_to_data_uri(ref_style_image)
                    if ref_style_image
                    else None
                )
                # Convert multi-image reference list
                ref_style_images_converted = []
                if raw_ref_images:
                    for ri in raw_ref_images:
                        url = ri.get("url", "") if isinstance(ri, dict) else ri
                        desc = ri.get("description", "") if isinstance(ri, dict) else ""
                        converted = _local_path_to_data_uri(url)
                        if converted:
                            ref_style_images_converted.append(
                                {"url": converted, "description": desc}
                            )
                elif ref_style_image:
                    # Backward compat: single image
                    ref_style_images_converted.append(
                        {"url": ref_style_image, "description": ""}
                    )
                # sample_video stays as-is (API may require URL for video)

                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "正在调用视频生成模型..."},
                )
                try:
                    client, cfg, model_name = _resolve_provider(
                        "video_llm", frontend_provider_id
                    )
                    llm_client = LLMClient(cfg)

                    # ── Progress callback for polling status ──
                    _last_status = {"value": None}

                    async def _video_progress(status: str):
                        if status != _last_status["value"]:
                            _last_status["value"] = status
                            status_map = {
                                "queued": "⏳ 排队中...",
                                "running": "🎬 视频生成中...",
                            }
                            display = status_map.get(status, status)
                            await session_manager.send_event(
                                session_id,
                                {
                                    "type": "video_progress",
                                    "content": display,
                                    "status": status,
                                },
                            )

                    url = await llm_client.generate_video(
                        user_content,
                        reference_image=first_frame_image,
                        last_frame_image=last_frame_image_url,
                        reference_style_images=ref_style_images_converted or None,
                        sample_video=sample_video_url,
                        resolution=video_resolution,
                        ratio=video_ratio,
                        duration=video_duration,
                        seed=video_seed,
                        camera_fixed=video_camera_fixed,
                        watermark=video_watermark,
                        on_progress=_video_progress,
                    )
                    local_url = None
                    if url:
                        logger.info(
                            f"[VideoGen] Video ready, remote URL: {url[:120]}..."
                        )
                        filename = f"gen_video_{int(asyncio.get_event_loop().time() * 1000)}.mp4"
                        save_path = os.path.join(settings.project.outputs_dir, filename)
                        try:
                            await llm_client.download_media(url, save_path)
                            local_url = f"/outputs/{filename}"
                        except Exception as dl_err:
                            logger.warning(
                                f"[VideoGen] Download failed ({dl_err}), skipping remote URL (would expire)"
                            )
                            local_url = None

                    params = {
                        "model": model_name,
                        "ratio": video_ratio,
                        "resolution": video_resolution,
                        "duration": f"{video_duration}s",
                        "seed": video_seed,
                        "camera_fixed": "开" if video_camera_fixed else "关",
                    }
                    event = {
                        "type": "complete",
                        "input": user_content,
                        "content": "视频生成完成",
                        "result": "视频生成成功！",
                        "media_type": "video",
                        "media_urls": [local_url] if local_url else [],
                        "params": params,
                    }
                    await session_manager.send_event(session_id, event)
                    history_store.add_session(
                        {
                            "id": f"srv_{int(asyncio.get_event_loop().time() * 1000)}",
                            "timestamp": datetime.now().isoformat(),
                            "mode": "video-llm",
                            "input": user_content,
                            "output": "视频生成完成",
                            "mediaType": "video",
                            "mediaUrl": local_url,
                            "params": params,
                        }
                    )
                except Exception as e:
                    await session_manager.send_event(
                        session_id,
                        {"type": "error", "content": f"视频生成失败: {e}"},
                    )

            elif msg_type.startswith("run_node_"):
                logger.info(f"[Gateway] Incoming test command: {msg_type}")
                node_key = msg_type.replace("run_node_", "")
                asyncio.create_task(execute_single_node(session_id, node_key))

    except WebSocketDisconnect:
        logger.info(f"[Gateway] Client disconnected: {session_id}")
    except Exception as e:
        logger.error(f"[Gateway] WebSocket error: {e}")
    finally:
        if session_id:
            session_manager.disconnect(session_id)


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/providers")
async def get_providers():
    """Return available LLM providers for all categories (used by frontend dropdowns)."""
    return llm_registry.get_all_providers_info()

@app.post("/api/upload_frame")
async def upload_frame(file: UploadFile = File(...)):
    """Upload a frame image or sample video for video generation."""
    import time

    ext = os.path.splitext(file.filename or "")[1] or ".png"
    safe_name = f"upload_{int(time.time() * 1000)}{ext}"
    save_dir = os.path.join(ROOT_DIR, "outputs", "uploads")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, safe_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    local_url = f"/outputs/uploads/{safe_name}"
    logger.info(f"[Upload] Saved {file.filename} -> {save_path}")
    return {"url": local_url, "filename": safe_name}

# ── Static Files ──────────────────────────────────────────────────────────────
# NOTE: /outputs MUST be mounted BEFORE / because the catch-all "/" mount
# would otherwise swallow all /outputs/* requests and return 404.

outputs_path = os.path.join(ROOT_DIR, "outputs")
if os.path.exists(outputs_path):
    app.mount("/outputs", StaticFiles(directory=outputs_path), name="outputs")

frontend_path = os.path.join(ROOT_DIR, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)
