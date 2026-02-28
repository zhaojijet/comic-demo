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
        node_state.node_summary.info_for_user(
            "Comic Hi-Res Image mock process started."
        )
        images = inputs.get("comic_refine_image", {}).get("refined_images", [])
        highres_images = [img.replace("refined", "highres") for img in images]
        node_state.node_summary.info_for_user(
            f"Generated {len(highres_images)} Hi-Res images."
        )
        return {"highres_images": highres_images}
