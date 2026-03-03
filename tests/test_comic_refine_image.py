import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_refine_image import ComicRefineImageNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    llm_mock = MagicMock()
    # Mock return value for generate_image (we simulate refine as image2image or an image LLM pass)
    llm_mock.generate_image = AsyncMock(
        return_value=["http://mock-image-url.com/refined_image.png"]
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
async def test_comic_refine_image_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicRefineImageNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_storyboard_image": {
            "images": [
                "http://mock-image-url.com/initial_1.png",
                "http://mock-image-url.com/initial_2.png",
            ]
        },
    }

    result = await node.process(mock_node_state, inputs)

    assert "refined_images" in result
    refined_images = result["refined_images"]
    assert isinstance(refined_images, list)
    assert len(refined_images) == 2
    assert refined_images[0] == "http://mock-image-url.com/refined_image.png"
    assert refined_images[1] == "http://mock-image-url.com/refined_image.png"

    # generate_image should be called twice (once for each image)
    assert mock_node_state.llm.generate_image.call_count == 2

    # Verify prompt content
    call_args_list = mock_node_state.llm.generate_image.call_args_list
    assert any(
        "http://mock-image-url.com/initial_1.png" in call[0][0]
        for call in call_args_list
    ), "Prompt must include the original image path/url"
    assert any(
        "线稿" in call[0][0] or "精细化" in call[0][0] for call in call_args_list
    ), "Prompt must include refine instructions"
