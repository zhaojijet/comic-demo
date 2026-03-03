import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_post_production import ComicPostProductionNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    llm_mock = MagicMock()
    # Mock return value for generate_audio (TTS)
    llm_mock.generate_audio = AsyncMock(
        return_value="http://mock-audio-url.com/tts.mp3"
    )

    return NodeState(
        session_id="test_session",
        artifact_id="test_artifact",
        lang="zh",
        node_summary=summary,
        llm=llm_mock,
        mcp_ctx=MagicMock(),
    )


@pytest.fixture
def mock_server_cfg():
    cfg = MagicMock()
    cfg.developer.developer_mode = True
    cfg.local_mcp_server.server_cache_dir = "test_cache"
    return cfg


@pytest.mark.asyncio
async def test_comic_post_production_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicPostProductionNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_image2video": {
            "videos": [
                "http://mock-video-url.com/clip_1.mp4",
                "http://mock-video-url.com/clip_2.mp4",
            ]
        },
        "comic_script": {
            # Normally this is just the raw text, but let's assume it can be used for TTS
            "script": "旁白：故事开始了..."
        },
    }

    result = await node.process(mock_node_state, inputs)

    assert "edited_video" in result
    assert (
        "final_edited" in result["edited_video"]
        or "composition" in result["edited_video"]
    )

    # Ideally, post-production might do TTS
    assert mock_node_state.llm.generate_audio.call_count >= 1
    call_args_list = mock_node_state.llm.generate_audio.call_args_list
    assert any(
        "故事开始了" in call.kwargs.get("prompt", "") for call in call_args_list
    ), "TTS must include script text"
