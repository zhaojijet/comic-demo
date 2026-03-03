from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicStyleInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Confirm graphic style based on script; skip: Skip style; default: Use default style",
    )
    user_request: Annotated[
        str,
        Field(default="", description="User requirements for the comic visual style"),
    ]


class ComicStyleOutput(BaseModel):
    style_description: str = Field(description="The confirmed visual style description")


@NODE_REGISTRY.register()
class ComicStyleNode(BaseNode):
    meta = NodeMeta(
        name="comic_style",
        description="Confirm the visual style for the comic. This is the '确认风格' phase.",
        node_id="comic_style",
        node_kind="comic_style",
        require_prior_kind=["comic_script"],
        default_require_prior_kind=["comic_script"],
        next_available_node=["comic_character"],
    )

    input_schema = ComicStyleInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"style_description": "Default comic style (Mocked)"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "正在根据剧本和您的要求生成漫剧美术风格设定..."
        )

        prev_script = inputs.get("comic_script", {}).get("script", "")
        user_request = inputs.get("user_request", "")

        system_prompt = (
            "你是一个专业的漫剧（Comic Play）美术指导。\n"
            "请根据以下给定的漫剧剧本内容以及用户的视觉风格要求，生成一段详细的画面风格设定描述。\n"
            "这段描述将用于指导后续的AI绘画模型（Image LLM）进行图像生成，"
            "因此请务必包含：画面质感、色彩基调、光影风格、线条特征等提示词方向的内容。"
        )

        prompt_content = f"【原剧本】\n{prev_script}\n\n"
        if user_request:
            prompt_content += f"【用户风格要求】\n{user_request}\n\n"
        prompt_content += "请输出最终的美术风格设定描写："

        response = await node_state.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_content},
            ]
        )

        style = response.get("content", "")

        from pathlib import Path
        import json

        out_dir = Path("outputs/comic_style")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(
            out_dir / f"{node_state.session_id}_{node_state.artifact_id}_style.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"style_description": style}, f, ensure_ascii=False, indent=2)

        node_state.node_summary.info_for_user("风格设定完成。")
        return {"style_description": style}
