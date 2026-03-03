from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicStoryboardInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Create storyboard from script; skip: Skip storyboard; default: Use default storyboard",
    )


class ComicStoryboardOutput(BaseModel):
    storyboard: List[Dict[str, Any]] = Field(description="List of storyboard panels")


@NODE_REGISTRY.register()
class ComicStoryboardNode(BaseNode):
    meta = NodeMeta(
        name="comic_storyboard",
        description="Create storyboard based on script and characters. This is the '制作分镜表' phase.",
        node_id="comic_storyboard",
        node_kind="comic_storyboard",
        require_prior_kind=["comic_script", "comic_character"],
        default_require_prior_kind=["comic_script", "comic_character"],
        next_available_node=["comic_storyboard_image"],
    )

    input_schema = ComicStoryboardInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"storyboard": [{"panel": 1, "desc": "Default panel 1"}]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "正在根据剧本、角色与风格为您拆解漫剧分镜表..."
        )

        prev_script = inputs.get("comic_script", {}).get("script", "")
        prev_style = inputs.get("comic_style", {}).get("style_description", "")
        prev_chars = inputs.get("comic_character", {}).get("characters", [])

        system_prompt = (
            "你是一个专业的漫剧（Comic Play）分镜师。\n"
            "请根据提供的剧本、整体美术风格、以及已有角色设定，将故事拆分为连续的画面分镜（Storyboard）。\n"
            "【极度重要限制】：为了控制最终成片时长在10秒内，每个剧本**最多只能拆解为 1 到 2 个分镜（镜头）**，绝不可超过 2 个！\n"
            "你需要输出一个合法的 JSON 对象数组 (List of objects)，每个对象代表一个分镜。\n"
            "对象必须包含以下键：\n"
            '- "panel" (int): 分镜序号，如 1, 2\n'
            '- "desc" (str): 对画面的详细描述，供AI生图使用，应结合美术风格进行具象化描述\n'
            '- "characters" (List[str]): 画面中出现的角色对象名称，如果没有角色请留空数组\n\n'
            "务必且只能输出纯JSON数组形式，例如：\n"
            '[{"panel": 1, "desc": "镜头推向远景，霓虹闪烁的赛博城市效果...", "characters": ["主角小明"]}]'
        )

        prompt_content = f"【原剧本】\n{prev_script}\n\n【美术风格】\n{prev_style}\n\n"
        if prev_chars:
            prompt_content += f"【已有角色设定】\n{prev_chars}\n\n"

        prompt_content += "请输出分镜表（JSON数组）："

        response = await node_state.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_content},
            ],
            response_format={"type": "json_object"},
        )

        content = response.get("content", "[]")

        import json

        try:
            panels = json.loads(content)
            if not isinstance(panels, list):
                panels = [{"panel": 1, "desc": str(content), "characters": []}]
        except json.JSONDecodeError:
            panels = [{"panel": 1, "desc": content, "characters": []}]

        from pathlib import Path
        import json

        out_dir = Path("outputs/comic_storyboard")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(
            out_dir
            / f"{node_state.session_id}_{node_state.artifact_id}_storyboard.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"storyboard": panels}, f, ensure_ascii=False, indent=2)

        node_state.node_summary.info_for_user(f"成功拆解为 {len(panels)} 个分镜。")
        return {"storyboard": panels}
