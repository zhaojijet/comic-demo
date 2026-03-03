import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_style import ComicStyleNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)
    llm_mock = MagicMock()
    # Return a mocked style description
    llm_mock.chat = AsyncMock(
        return_value={"content": "风格设定：赛博朋克风，高对比度霓虹灯色彩。"}
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
async def test_comic_style_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicStyleNode(server_cfg=mock_server_cfg)

    # Previous node's output comes through inputs key
    inputs = {
        "mode": "auto",
        "user_request": "赛博朋克风，暗黑高对比度",
        "comic_script": {"script": "1. [Scene 1] 在霓虹闪烁的街头，机器猫走过。"},
    }

    result = await node.process(mock_node_state, inputs)

    assert "style_description" in result
    assert "赛博朋克" in result["style_description"]

    # The node must call LLM to generate the style
    mock_node_state.llm.chat.assert_called_once()

    call_args = mock_node_state.llm.chat.call_args[1]
    assert "messages" in call_args
    messages = call_args["messages"]

    user_prompts = [m["content"] for m in messages if m["role"] == "user"]
    assert any(
        "机器猫" in p for p in user_prompts
    ), "The prompt should include the comic script"
    assert any(
        "赛博朋克风" in p for p in user_prompts
    ), "The prompt should include the user style request"
