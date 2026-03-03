from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicRefineImageInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Refine storyboard images (PS+MJ); skip: Skip refine; default: default",
    )


class ComicRefineImageOutput(BaseModel):
    refined_images: List[str] = Field(
        description="List of paths/URLs to refined images"
    )


@NODE_REGISTRY.register()
class ComicRefineImageNode(BaseNode):
    meta = NodeMeta(
        name="comic_refine_image",
        description="Refine storyboard images (e.g. using PS + MJ). This is the '修分镜图 (PS+MJ)' phase.",
        node_id="comic_refine_image",
        node_kind="comic_refine_image",
        require_prior_kind=["comic_storyboard_image"],
        default_require_prior_kind=["comic_storyboard_image"],
        next_available_node=["comic_highres_image"],
    )

    input_schema = ComicRefineImageInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"refined_images": ["default_refined_1.png"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在为您优化与精细化分镜底图...")
        images = inputs.get("comic_storyboard_image", {}).get("images", [])

        if not images:
            return {"refined_images": []}

        import asyncio
        import os
        from mcp_custom.sampling_requester import LLMClient

        from pathlib import Path

        save_dir = Path("outputs/comic_refine_image")
        save_dir.mkdir(parents=True, exist_ok=True)

        async def refine_single_image(image_path: str, idx: int) -> str:
            prompt = f"请对该底图进行精细化处理、提取清晰的线稿并优化画面结构与光影细节: {image_path}"
            try:
                # generate_image returns a list of URLs
                urls = await node_state.llm.generate_image(prompt)
                url = urls[0] if urls else ""
                if url:
                    filename = f"{node_state.session_id}_{node_state.artifact_id}_refined_{idx}.png"
                    save_path = str(save_dir / filename)
                    await LLMClient.download_media(url, save_path)
                    return str(save_path)
                return ""
            except Exception as e:
                node_state.node_summary.warning_for_user(
                    f"图片精细化失败 ({image_path}): {e}"
                )
                return ""

        # Run refinement concurrently for all images
        tasks = [refine_single_image(img, i) for i, img in enumerate(images)]
        refined_images = await asyncio.gather(*tasks)

        node_state.node_summary.info_for_user(
            f"成功精细化了 {len([img for img in refined_images if img])} 张底图。"
        )
        return {"refined_images": refined_images}
