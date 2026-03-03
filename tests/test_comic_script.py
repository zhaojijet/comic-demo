import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_script import ComicScriptNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)
    llm_mock = MagicMock()
    llm_mock.chat = AsyncMock(
        return_value={"content": "Here is your comic script:\\n1. [Scene 1] ..."}
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
async def test_comic_script_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicScriptNode(server_cfg=mock_server_cfg)

    inputs = {"mode": "auto", "user_request": "A story about a cyberpunk cat"}

    result = await node.process(mock_node_state, inputs)

    assert "script" in result
    assert result["script"] == "Here is your comic script:\\n1. [Scene 1] ..."

    mock_node_state.llm.chat.assert_called_once()

    call_args = mock_node_state.llm.chat.call_args[1]
    assert "messages" in call_args
    messages = call_args["messages"]

    system_prompts = [m["content"] for m in messages if m["role"] == "system"]
    user_prompts = [m["content"] for m in messages if m["role"] == "user"]

    assert any("漫剧" in p or "comic script" in p.lower() for p in system_prompts)
    assert any("cyberpunk cat" in p for p in user_prompts)
