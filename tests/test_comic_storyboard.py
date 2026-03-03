import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.comic_nodes.comic_storyboard import ComicStoryboardNode
from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary


@pytest.fixture
def mock_node_state():
    summary = MagicMock(spec=NodeSummary)
    llm_mock = MagicMock()
    # Mocking JSON array returned by the LLM
    mock_json = """
    [
        {"panel": 1, "desc": "镜头推向远景，霓虹闪烁的赛博城市，黑猫警长站在高楼边缘俯视。", "characters": ["黑猫警长"]},
        {"panel": 2, "desc": "近景特写黑猫警长的脸，他按下通讯器。", "characters": ["黑猫警长"]}
    ]
    """
    llm_mock.chat = AsyncMock(return_value={"content": mock_json})

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
async def test_comic_storyboard_node_auto_mode(mock_node_state, mock_server_cfg):
    node = ComicStoryboardNode(server_cfg=mock_server_cfg)

    inputs = {
        "mode": "auto",
        "comic_script": {"script": "1. [Scene 1] 主角黑猫警长抓小偷。"},
        "comic_style": {"style_description": "赛博朋克风"},
        "comic_character": {"characters": ["黑猫警长：黑发蓝眼，穿着赛博朋克风皮夹克"]},
    }

    result = await node.process(mock_node_state, inputs)

    assert "storyboard" in result
    panels = result["storyboard"]
    assert isinstance(panels, list)
    assert len(panels) == 2
    assert "panel" in panels[0]
    assert "desc" in panels[0]

    mock_node_state.llm.chat.assert_called_once()

    call_args = mock_node_state.llm.chat.call_args[1]
    assert "messages" in call_args
    messages = call_args["messages"]

    user_prompts = [m["content"] for m in messages if m["role"] == "user"]
    assert any(
        "主角黑猫警长" in p for p in user_prompts
    ), "Prompt must include the script"
    assert any("赛博朋克风" in p for p in user_prompts), "Prompt must include the style"
    assert any(
        "黑猫警长：黑发蓝眼" in p for p in user_prompts
    ), "Prompt must include the character info"
