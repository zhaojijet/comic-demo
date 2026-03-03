import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_storyboard_image import ComicStoryboardImageNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    # We will reuse the single LLMClient mock for both chat and image generation in this test setup
    llm_mock = MagicMock()
    # Mock return value for generate_image (returns a list of URLs)
    llm_mock.generate_image = AsyncMock(
        return_value=["http://mock-image-url.com/image.png"]
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
async def test_comic_storyboard_image_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicStoryboardImageNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_storyboard": {
            "storyboard": [
                {"panel": 1, "desc": "镜头推向远景...", "characters": ["主角小明"]},
                {"panel": 2, "desc": "近景特写...", "characters": ["主角小明"]},
            ]
        },
        "comic_style": {"style_description": "赛博朋克风"},
    }

    result = await node.process(mock_node_state, inputs)

    assert "images" in result
    images = result["images"]
    assert isinstance(images, list)
    assert len(images) == 2
    assert images[0] == "http://mock-image-url.com/image.png"
    assert images[1] == "http://mock-image-url.com/image.png"

    # generate_image should be called twice (once for each panel)
    assert mock_node_state.llm.generate_image.call_count == 2

    # Verify prompt content
    call_args_list = mock_node_state.llm.generate_image.call_args_list
    assert any(
        "赛博朋克风" in call[0][0] for call in call_args_list
    ), "Image prompt must include the style"
    assert any(
        "镜头推向远景" in call[0][0] for call in call_args_list
    ), "Image prompt must include panel desc"
