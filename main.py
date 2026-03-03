import os
import sys
import json
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any

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


class SessionManager:
    """Manages active WebSocket sessions, inspired by openclaw's session model."""

    def __init__(self):
        self.active_sessions: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_sessions[session_id] = websocket
        logger.info(f"[Gateway] Session connected: {session_id}")

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
            "ComicRefineImageNode",
            "ComicHighresImageNode",
            "ComicImage2VideoNode",
            "ComicPostProductionNode",
            "ComicSuperResolutionNode",
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

            elif msg_type == "test_llm":
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "Testing Text LLM (DeepSeek)..."},
                )
                try:
                    from llm_client import LLMClient

                    client = LLMClient(settings.llm)
                    resp = await client.chat(
                        [{"role": "user", "content": "你好，请用一句话自我介绍"}]
                    )
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "complete",
                            "content": "LLM 测试完成",
                            "result": f"大模型回复: {resp.get('content')}",
                        },
                    )
                except Exception as e:
                    await session_manager.send_event(
                        session_id, {"type": "error", "content": f"LLM Test Error: {e}"}
                    )

            elif msg_type == "test_image_llm":
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "Testing Image LLM (Seedream)..."},
                )
                try:
                    from llm_client import LLMClient

                    client = LLMClient(settings.image_llm)
                    urls = await client.generate_image(
                        "一个赛博朋克机械师角色设定图，半身像"
                    )
                    result = (
                        f"生图成功！图片链接:\n" + "\n".join(urls)
                        if urls
                        else "生图失败，返回为空"
                    )
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "complete",
                            "content": "Image LLM 测试完成",
                            "result": result,
                        },
                    )
                except Exception as e:
                    await session_manager.send_event(
                        session_id,
                        {"type": "error", "content": f"Image LLM Test Error: {e}"},
                    )

            elif msg_type == "test_video_llm":
                await session_manager.send_event(
                    session_id,
                    {"type": "system", "content": "Testing Video LLM (Seedance)..."},
                )
                try:
                    from llm_client import LLMClient

                    client = LLMClient(settings.video_llm)
                    url = await client.generate_video(
                        "赛博朋克城市里的飞行汽车呼啸而过 --duration 5"
                    )
                    await session_manager.send_event(
                        session_id,
                        {
                            "type": "complete",
                            "content": "Video LLM 测试完成",
                            "result": f"视频生成成功！链接:\n{url}",
                        },
                    )
                except Exception as e:
                    await session_manager.send_event(
                        session_id,
                        {"type": "error", "content": f"Video LLM Test Error: {e}"},
                    )

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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
