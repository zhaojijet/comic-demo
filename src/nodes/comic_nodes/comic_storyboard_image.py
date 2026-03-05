from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicStoryboardImageInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Create storyboard images; skip: Skip; default: default",
    )


class ComicStoryboardImageOutput(BaseModel):
    images: List[str] = Field(
        description="List of paths/URLs to generated storyboard images"
    )


@NODE_REGISTRY.register()
class ComicStoryboardImageNode(BaseNode):
    meta = NodeMeta(
        name="comic_storyboard_image",
        description="Generate images for the storyboard. This is the '制作分镜图' phase.",
        node_id="comic_storyboard_image",
        node_kind="comic_storyboard_image",
        require_prior_kind=["comic_storyboard", "comic_style"],
        default_require_prior_kind=["comic_storyboard", "comic_style"],
        next_available_node=["comic_image2video"],
    )

    input_schema = ComicStoryboardImageInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"images": ["default_image_1.png"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在为您生成漫剧分镜底图...")
        panels = inputs.get("comic_storyboard", {}).get("storyboard", [])
        style = inputs.get("comic_style", {}).get("style_description", "")

        if not panels:
            return {"images": []}

        import asyncio
        import os
        from mcp_custom.sampling_requester import LLMClient

        from pathlib import Path

        save_dir = Path("outputs/comic_storyboard_image")
        save_dir.mkdir(parents=True, exist_ok=True)

        async def generate_single_image(panel: dict, idx: int) -> str:
            desc = panel.get("desc", "")
            chars = panel.get("characters", [])

            prompt = f"画面描述: {desc}\n"
            if chars:
                prompt += f"角色设定: {', '.join(chars)}\n"
            prompt += f"美术风格: {style}"

            try:
                # generate_image returns a list of URLs
                urls = await node_state.llm.generate_image(prompt)
                url = urls[0] if urls else ""
                if url:
                    filename = f"{node_state.session_id}_{node_state.artifact_id}_storyboard_{idx}.png"
                    save_path = str(save_dir / filename)
                    # node_state.llm is likely LLMClient wrapper or similar, which might not have download_media static method.
                    # But LLMClient has it. Let's use it.
                    await LLMClient.download_media(url, save_path)
                    return str(save_path)
                return ""
            except Exception as e:
                node_state.node_summary.warning_for_user(
                    f"分镜 {panel.get('panel')} 生图失败: {e}"
                )
                return ""

        # Run image generation concurrently for all panels
        tasks = [generate_single_image(p, i) for i, p in enumerate(panels)]
        images = await asyncio.gather(*tasks)

        node_state.node_summary.info_for_user(
            f"成功生成了 {len([img for img in images if img])} 张分镜底图。"
        )
        return {"images": images}
