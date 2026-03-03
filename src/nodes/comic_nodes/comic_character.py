from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicCharacterInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Identify characters; skip: Skip character identification; default: default characters",
    )
    user_request: Annotated[
        str, Field(default="", description="User requirements for character design")
    ]


class ComicCharacterOutput(BaseModel):
    characters: List[str] = Field(
        description="List of designed characters (Three views + Expressions + Poses)"
    )


@NODE_REGISTRY.register()
class ComicCharacterNode(BaseNode):
    meta = NodeMeta(
        name="comic_character",
        description="Confirm and design characters (Three views, Expressions, Poses). This is the '确认角色' phase.",
        node_id="comic_character",
        node_kind="comic_character",
        require_prior_kind=["comic_script", "comic_style"],
        default_require_prior_kind=["comic_script", "comic_style"],
        next_available_node=["comic_storyboard"],
    )

    input_schema = ComicCharacterInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"characters": ["Default Character A", "Default Character B"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在根据剧本和设定生成漫剧角色设定...")

        prev_script = inputs.get("comic_script", {}).get("script", "")
        prev_style = inputs.get("comic_style", {}).get("style_description", "")
        user_request = inputs.get("user_request", "")

        system_prompt = (
            "你是一个专业的漫剧（Comic Play）角色设计师。\n"
            "请根据以下漫剧剧本内容、美术风格设定以及用户的特殊要求，提取并设计主要角色。\n"
            "对于每个角色，请提供一段详细描述（含外貌特征、服装、发型、关键配色），用于指导后续的Image LLM生图，通常包括三视图、表情图等概念的设计。\n"
            "请务必且只能以合法的 JSON 字符串数组格式输出（List of strings），格式如：\n"
            '["主角小明：短发，红夹克，赛博风三视图设定", "反派BOSS：光头电子义眼外观"]'
        )

        prompt_content = f"【原剧本】\n{prev_script}\n\n【美术风格】\n{prev_style}\n\n"
        if user_request:
            prompt_content += f"【用户角色要求】\n{user_request}\n\n"

        response = await node_state.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_content},
            ],
            response_format={
                "type": "json_object"
            },  # optional hint if LLM supports it, we just parse
        )

        content = response.get("content", "[]")

        import json

        try:
            characters = json.loads(content)
            if not isinstance(characters, list):
                characters = [str(characters)]
        except json.JSONDecodeError:
            # Fallback if LLM didn't return pure JSON array
            characters = [content]

        from pathlib import Path
        import json

        out_dir = Path("outputs/comic_character")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(
            out_dir
            / f"{node_state.session_id}_{node_state.artifact_id}_characters.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"characters": characters}, f, ensure_ascii=False, indent=2)

        node_state.node_summary.info_for_user(f"确立了 {len(characters)} 个角色设定。")
        return {"characters": characters}
