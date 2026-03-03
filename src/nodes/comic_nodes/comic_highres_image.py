from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicHighresImageInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Create high-res images (Magnific+MJ); skip: Skip hi-res; default: default",
    )


class ComicHighresImageOutput(BaseModel):
    highres_images: List[str] = Field(
        description="List of paths/URLs to high-resolution images"
    )


@NODE_REGISTRY.register()
class ComicHighresImageNode(BaseNode):
    meta = NodeMeta(
        name="comic_highres_image",
        description="Generate high-resolution storyboard images (Magnific+MJ). This is the '精修分镜图 (Magnific+MJ)' phase.",
        node_id="comic_highres_image",
        node_kind="comic_highres_image",
        require_prior_kind=["comic_refine_image"],
        default_require_prior_kind=["comic_refine_image"],
        next_available_node=["comic_image2video"],
    )

    input_schema = ComicHighresImageInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"highres_images": ["default_highres_1.png"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("正在为您进行高清上色与高分辨率重绘...")
        images = inputs.get("comic_refine_image", {}).get("refined_images", [])

        if not images:
            return {"highres_images": []}

        import asyncio
        import os
        from mcp_custom.sampling_requester import LLMClient

        from pathlib import Path

        save_dir = Path("outputs/comic_highres_image")
        save_dir.mkdir(parents=True, exist_ok=True)

        async def highres_single_image(image_path: str, idx: int) -> str:
            prompt = f"请对该底图进行高清上色与高分辨率重绘（Hi-Res Fix），增加环境光影细节材质表现: {image_path}"
            try:
                urls = await node_state.llm.generate_image(prompt)
                url = urls[0] if urls else ""
                if url:
                    filename = f"{node_state.session_id}_{node_state.artifact_id}_highres_{idx}.png"
                    save_path = str(save_dir / filename)
                    await LLMClient.download_media(url, save_path)
                    return str(save_path)
                return ""
            except Exception as e:
                node_state.node_summary.warning_for_user(
                    f"图片高清处理失败 ({image_path}): {e}"
                )
                return ""

        # Run highres concurrently for all images
        tasks = [highres_single_image(img, i) for i, img in enumerate(images)]
        highres_images = await asyncio.gather(*tasks)

        node_state.node_summary.info_for_user(
            f"成功生成了 {len([img for img in highres_images if img])} 张高清成品图。"
        )
        return {"highres_images": highres_images}
