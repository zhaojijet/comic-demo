import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_image2video import ComicImage2VideoNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    llm_mock = MagicMock()
    # Mock return value for generate_video
    llm_mock.generate_video = AsyncMock(
        return_value="http://mock-video-url.com/generated_video.mp4"
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
async def test_comic_image2video_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicImage2VideoNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_highres_image": {
            "highres_images": [
                "http://mock-image-url.com/highres_1.png",
                "http://mock-image-url.com/highres_2.png",
            ]
        },
    }

    result = await node.process(mock_node_state, inputs)

    assert "videos" in result
    videos = result["videos"]
    assert isinstance(videos, list)
    assert len(videos) == 2
    assert videos[0] == "http://mock-video-url.com/generated_video.mp4"
    assert videos[1] == "http://mock-video-url.com/generated_video.mp4"

    # generate_video should be called twice (once for each image)
    assert mock_node_state.llm.generate_video.call_count == 2

    # Verify prompt content
    call_args_list = mock_node_state.llm.generate_video.call_args_list
    assert any(
        "http://mock-image-url.com/highres_1.png" in call.kwargs.get("image_url", "")
        for call in call_args_list
    ), "Prompt must include the image path/url"
