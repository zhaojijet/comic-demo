import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_highres_image import ComicHighresImageNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)

    llm_mock = MagicMock()
    # Mock return value for generate_image (we simulate highres as an image LLM pass)
    llm_mock.generate_image = AsyncMock(
        return_value=["http://mock-image-url.com/highres_image.png"]
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
async def test_comic_highres_image_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicHighresImageNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_refine_image": {
            "refined_images": [
                "http://mock-image-url.com/refined_1.png",
                "http://mock-image-url.com/refined_2.png",
            ]
        },
    }

    result = await node.process(mock_node_state, inputs)

    assert "highres_images" in result
    highres_images = result["highres_images"]
    assert isinstance(highres_images, list)
    assert len(highres_images) == 2
    assert highres_images[0] == "http://mock-image-url.com/highres_image.png"
    assert highres_images[1] == "http://mock-image-url.com/highres_image.png"

    # generate_image should be called twice (once for each image)
    assert mock_node_state.llm.generate_image.call_count == 2

    # Verify prompt content
    call_args_list = mock_node_state.llm.generate_image.call_args_list
    assert any(
        "http://mock-image-url.com/refined_1.png" in call[0][0]
        for call in call_args_list
    ), "Prompt must include the refined image path/url"
    assert any(
        "上色" in call[0][0] or "高分辨率重绘" in call[0][0] for call in call_args_list
    ), "Prompt must include hi-res or colorization instructions"
