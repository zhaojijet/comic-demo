import os
import sys
import json
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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


class ComicRequest(BaseModel):
    session_id: str
    user_prompt: str


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
    from core.config import settings

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

            if msg_type in ("test_llm", "test_image_llm", "test_video_llm"):
                # Parse JSON string from frontend if possible
                content_obj = message.get("content", "")
                user_content = ""
                frontend_model = None

                if isinstance(content_obj, str) and content_obj.startswith("{"):
                    try:
                        content_dict = json.loads(content_obj)
                        user_content = content_dict.get("text", "").strip()
                        frontend_model = content_dict.get("model", "")
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
                    from llm_client import LLMClient

                    client = LLMClient(settings.llm)

                    model_override = None
                    if frontend_model and "deepseek" in frontend_model.lower():
                        model_override = "deepseek-chat"

                    resp = await client.chat(
                        [{"role": "user", "content": user_content}],
                        model_override=model_override,
                    )
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "complete",
                            "input": user_content,
                            "content": "文本 LLM 回复",
                            "result": resp.get("content", str(resp)),
                        },
                    )
                    history_store.add_session(
                        {
                            "id": f"srv_{int(asyncio.get_event_loop().time() * 1000)}",
                            "timestamp": datetime.now().isoformat(),
                            "mode": "llm",
                            "input": user_content,
                            "output": resp.get("content", str(resp)),
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
                    from llm_client import LLMClient

                    client = LLMClient(settings.image_llm)

                    model_override = None
                    if frontend_model and "seedream" in frontend_model.lower():
                        model_override = "doubao-seedream-5-0-260128"

                    urls = await client.generate_image(
                        user_content, model_override=model_override
                    )
                    if urls:
                        event = {
                            "type": "complete",
                            "input": user_content,
                            "content": "图片生成完成",
                            "result": "生图成功！",
                            "media_type": "image",
                            "media_urls": urls,
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
                                "mediaUrl": urls[0] if urls else None,
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
                user_content = (
                    user_content or "赛博朋克城市里的飞行汽车呼啸而过 --duration 5"
                )
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "正在调用视频生成模型..."},
                )
                try:
                    from llm_client import LLMClient

                    client = LLMClient(settings.video_llm)

                    model_override = None
                    if frontend_model:
                        if (
                            "1.0-pro-fast" in frontend_model
                            or "1.0profast" in frontend_model.lower()
                        ):
                            model_override = "doubao-seedance-1-0-pro-fast-251015"
                        elif (
                            "1.5-pro" in frontend_model
                            or "1.5pro" in frontend_model.lower()
                        ):
                            model_override = "doubao-seedance-1-5-pro-251215"

                    url = await client.generate_video(
                        user_content, model_override=model_override
                    )
                    event = {
                        "type": "complete",
                        "input": user_content,
                        "content": "视频生成完成",
                        "result": "视频生成成功！",
                        "media_type": "video",
                        "media_urls": [url] if url else [],
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
                            "mediaUrl": url,
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


# ── REST Endpoints (backward compatible) ──────────────────────────────────────


@app.get("/")
async def root():
    return {"message": "Welcome to Comic Demo - AI 漫剧创作代理"}


@app.post("/create_comic")
async def create_comic(request: ComicRequest):
    try:
        artifact_store = ArtifactStore(
            os.path.join(ROOT_DIR, ".comic_demo", "artifacts"),
            session_id=request.session_id,
        )

        agent, node_manager = await build_agent(
            cfg=settings, session_id=request.session_id, store=artifact_store
        )

        result = await agent.ainvoke(
            {
                "input": f"Help me create a comic based on: {request.user_prompt}",
                "chat_history": [],
            }
        )

        return {"session_id": request.session_id, "result": result}
    except Exception as e:
        logger.error(f"Error creating comic: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Static Files ──────────────────────────────────────────────────────────────

frontend_path = os.path.join(ROOT_DIR, "frontend")
if os.path.exists(frontend_path):
    app.mount("/web", StaticFiles(directory=frontend_path, html=True), name="frontend")

outputs_path = os.path.join(ROOT_DIR, "outputs")
if os.path.exists(outputs_path):
    app.mount("/outputs", StaticFiles(directory=outputs_path), name="outputs")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
