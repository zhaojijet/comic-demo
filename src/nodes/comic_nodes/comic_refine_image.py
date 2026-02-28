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
        node_state.node_summary.info_for_user(
            "Comic Refine Image mock process started."
        )
        images = inputs.get("comic_storyboard_image", {}).get("images", [])
        refined_images = [img.replace("generated", "refined") for img in images]
        node_state.node_summary.info_for_user(f"Refined {len(refined_images)} images.")
        return {"refined_images": refined_images}
