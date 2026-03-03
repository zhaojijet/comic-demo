import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath("src"))

from nodes.node_state import NodeState
from nodes.node_summary import NodeSummary
from agent import AgentLoop


@pytest.mark.asyncio
async def test_comic_pipeline_integration():
    """
    Integration test to ensure that the entire pipeline from comic_script to comic_super_resolution
    can execute without errors in the AgentLoop.
    """
    # 1. Setup Mock configurations and LLM
    mock_llm = MagicMock()
    # Mock text generation
    mock_llm.chat = AsyncMock(return_value={"content": "Mocked Text Response"})
    # Mock image generation
    mock_llm.generate_image = AsyncMock(return_value=["http://mock.com/image.png"])
    # Mock video generation
    mock_llm.generate_video = AsyncMock(return_value="http://mock.com/video.mp4")
    # Mock audio generation
    mock_llm.generate_audio = AsyncMock(return_value="http://mock.com/audio.mp3")

    # 2. Setup the nodes
    from nodes.comic_nodes.comic_script import ComicScriptNode
    from nodes.comic_nodes.comic_style import ComicStyleNode
    from nodes.comic_nodes.comic_character import ComicCharacterNode
    from nodes.comic_nodes.comic_storyboard import ComicStoryboardNode
    from nodes.comic_nodes.comic_storyboard_image import ComicStoryboardImageNode
    from nodes.comic_nodes.comic_refine_image import ComicRefineImageNode
    from nodes.comic_nodes.comic_highres_image import ComicHighresImageNode
    from nodes.comic_nodes.comic_image2video import ComicImage2VideoNode
    from nodes.comic_nodes.comic_post_production import ComicPostProductionNode
    from nodes.comic_nodes.comic_super_resolution import ComicSuperResolutionNode

    cfg = MagicMock()
    nodes = {
        "comic_script": ComicScriptNode(server_cfg=cfg),
        "comic_style": ComicStyleNode(server_cfg=cfg),
        "comic_character": ComicCharacterNode(server_cfg=cfg),
        "comic_storyboard": ComicStoryboardNode(server_cfg=cfg),
        "comic_storyboard_image": ComicStoryboardImageNode(server_cfg=cfg),
        "comic_refine_image": ComicRefineImageNode(server_cfg=cfg),
        "comic_highres_image": ComicHighresImageNode(server_cfg=cfg),
        "comic_image2video": ComicImage2VideoNode(server_cfg=cfg),
        "comic_post_production": ComicPostProductionNode(server_cfg=cfg),
        "comic_super_resolution": ComicSuperResolutionNode(server_cfg=cfg),
    }

    from agent_loop import ToolDef
    import json

    tool_defs = []

    mock_node_state = NodeState(
        session_id="test_pipeline_session",
        artifact_id="test_artifact_123",
        lang="zh",
        node_summary=MagicMock(),
        llm=mock_llm,
        mcp_ctx=MagicMock(),
    )

    def make_caller(name, node):
        async def caller(**kwargs):
            res = await node.process(mock_node_state, kwargs)
            return json.dumps(res, ensure_ascii=False)

        return caller

    for name, node in nodes.items():
        tool_defs.append(
            ToolDef(
                name=name,
                description=node.meta.description,
                parameters=node.input_schema.model_json_schema(),
                callable=make_caller(name, node),
            )
        )

    agent_loop = AgentLoop(
        tools=tool_defs,
        llm=mock_llm,
    )

    # 3. Simulate the user request execution
    mock_responses = []
    ordered_nodes = [
        ("comic_script", {"mode": "auto", "user_request": "一个关于太空猫的故事"}),
        (
            "comic_style",
            {
                "mode": "auto",
                "user_request": "赛博朋克风",
                "comic_script": {"script": "1. [Scene 1] 太空猫"},
            },
        ),
        (
            "comic_character",
            {
                "mode": "auto",
                "user_request": "",
                "comic_script": {"script": "1. [Scene 1] 太空猫"},
                "comic_style": {"style_description": "赛博朋克风"},
            },
        ),
        (
            "comic_storyboard",
            {
                "mode": "auto",
                "comic_script": {"script": "1. [Scene 1] 太空猫"},
                "comic_style": {"style_description": "赛博朋克风"},
                "comic_character": {"characters": ["太空猫"]},
            },
        ),
        (
            "comic_storyboard_image",
            {
                "mode": "auto",
                "comic_storyboard": {
                    "storyboard": [
                        {"panel": 1, "desc": "太空舱内", "characters": ["太空猫"]}
                    ]
                },
                "comic_style": {"style_description": "赛博朋克风"},
            },
        ),
        (
            "comic_refine_image",
            {
                "mode": "auto",
                "comic_storyboard_image": {"images": ["http://mock.com/image.png"]},
            },
        ),
        (
            "comic_highres_image",
            {
                "mode": "auto",
                "comic_refine_image": {
                    "refined_images": ["http://mock.com/refined.png"]
                },
            },
        ),
        (
            "comic_image2video",
            {
                "mode": "auto",
                "comic_highres_image": {
                    "highres_images": ["http://mock.com/highres.png"]
                },
            },
        ),
        (
            "comic_post_production",
            {
                "mode": "auto",
                "comic_image2video": {"videos": ["http://mock.com/video.mp4"]},
                "comic_script": {"script": "1. [Scene 1] 太空猫"},
            },
        ),
        (
            "comic_super_resolution",
            {
                "mode": "auto",
                "comic_post_production": {"edited_video": "http://mock.com/edited.mp4"},
            },
        ),
    ]

    for tool_name, args in ordered_nodes:
        mock_responses.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{tool_name}",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(args)},
                    }
                ],
            }
        )

    mock_responses.append({"role": "assistant", "content": "漫剧创作已全部完成！"})

    mock_llm.chat_with_tools = AsyncMock(side_effect=mock_responses)
    mock_llm.chat = AsyncMock(return_value={"content": "漫剧创作已全部完成！"})

    executed_tools = []

    async def on_tool_end(tool_name, tool_result, tc_id):
        executed_tools.append(tool_name)

    agent_loop.on_tool_end = on_tool_end

    # 4. Run the pipeline
    inputs = {"input": "请帮我制作一个太空猫的漫剧", "chat_history": []}
    result = await agent_loop.ainvoke(inputs)

    # 5. Assertions
    expected_nodes = [
        "comic_script",
        "comic_style",
        "comic_character",
        "comic_storyboard",
        "comic_storyboard_image",
        "comic_refine_image",
        "comic_highres_image",
        "comic_image2video",
        "comic_post_production",
        "comic_super_resolution",
    ]

    for enode in expected_nodes:
        assert (
            enode in executed_tools
        ), f"Node {enode} did not execute successfully in pipeline."

    assert "漫剧创作已全部完成" in result["output"]
    assert mock_llm.chat_with_tools.call_count == 11

    # Check that LLM inner methods were called appropriately by the nodes' logic
    assert mock_llm.generate_image.call_count >= 1
    assert mock_llm.generate_video.call_count >= 1
