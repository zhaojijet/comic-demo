import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_character import ComicCharacterNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)
    llm_mock = MagicMock()
    # Mocking JSON array returned by the LLM
    llm_mock.chat = AsyncMock(
        return_value={
            "content": '["主角：黑发蓝眼，穿着赛博朋克风皮夹克", "反派：戴着电子义眼的光头胖子"]'
        }
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
async def test_comic_character_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicCharacterNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "user_request": "",
        "comic_script": {"script": "1. [Scene 1] 主角黑猫警长抓小偷。"},
        "comic_style": {"style_description": "2D 扁平化动画风格"},
    }

    result = await node.process(mock_node_state, inputs)

    assert "characters" in result
    assert isinstance(result["characters"], list)
    assert len(result["characters"]) == 2
    assert "主角" in result["characters"][0]

    mock_node_state.llm.chat.assert_called_once()
