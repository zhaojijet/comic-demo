import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_super_resolution import ComicSuperResolutionNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    llm_mock = MagicMock()
    # Mock return value for generate_video as an upscaler operation
    llm_mock.generate_video = AsyncMock(
        return_value="http://mock-video-url.com/upscaled_video.mp4"
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
async def test_comic_super_resolution_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicSuperResolutionNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_post_production": {
            "edited_video": "http://mock-video-url.com/edited_video.mp4"
        },
    }

    result = await node.process(mock_node_state, inputs)

    assert "final_video" in result
    assert result["final_video"] == "http://mock-video-url.com/upscaled_video.mp4"

    # generate_video should be called once to upscale the final composed video
    mock_node_state.llm.generate_video.assert_called_once()

    call_args = mock_node_state.llm.generate_video.call_args
    prompt = call_args.kwargs.get("prompt", "")
    assert "超分" in prompt or "画质提升" in prompt
    assert (
        call_args.kwargs.get("video_url")
        == "http://mock-video-url.com/edited_video.mp4"
    )
