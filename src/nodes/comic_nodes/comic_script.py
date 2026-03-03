from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicScriptInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Generate a comic script based on user prompt; skip: Skip generation; default: Use default",
    )
    user_request: Annotated[
        str, Field(default="", description="User requirements for the comic script")
    ]


class ComicScriptOutput(BaseModel):
    script: str = Field(description="The generated comic script")


@NODE_REGISTRY.register()
class ComicScriptNode(BaseNode):
    meta = NodeMeta(
        name="comic_script",
        description="Generate a script for a Manga/Comic Play (漫剧). This is the '确认剧本' phase.",
        node_id="comic_script",
        node_kind="comic_script",
        require_prior_kind=[],  # First node in comic workflow
        default_require_prior_kind=[],
        next_available_node=["comic_style"],
    )

    input_schema = ComicScriptInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"script": "Default comic script (Mocked)"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在根据您的构思生成漫剧剧本...")

        user_request = inputs.get("user_request", "一个关于猫的故事")

        system_prompt = (
            "你是一个专业的漫剧（Comic Play）编剧。"
            "请根据用户的构思，将其扩展为一个结构完整的漫剧剧本分镜表。\n"
            "【极度重要限制】：为了保证最终生成的视频总时长绝对不超过10秒，请严格限制剧本内容，**最多只能包含 1 到 2 个分镜（镜头）**。所有的台词和动作必须极其精简，保证在10秒内能演完！\n"
            "每个分镜应包含：\n"
            "1. 画面描述（场景环境、角色动作和表情）\n"
            "2. 旁白/台词"
        )

        response = await node_state.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"用户构思: {user_request}"},
            ]
        )

        script = response.get("content", "")

        from pathlib import Path
        import json

        out_dir = Path("outputs/comic_script")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(
            out_dir / f"{node_state.session_id}_{node_state.artifact_id}_script.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"script": script}, f, ensure_ascii=False, indent=2)

        node_state.node_summary.info_for_user("剧本生成完成。")

        return {"script": script}
