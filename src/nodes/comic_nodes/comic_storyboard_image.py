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
        next_available_node=["comic_refine_image"],
    )

    input_schema = ComicStoryboardImageInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"images": ["default_image_1.png"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Storyboard Image generation mock process started."
        )
        panels = inputs.get("comic_storyboard", {}).get("storyboard", [])
        images = [
            f"generated_image_panel_{p.get('panel', i)}.png"
            for i, p in enumerate(panels)
        ]
        node_state.node_summary.info_for_user(
            f"Generated {len(images)} storyboard images."
        )
        return {"images": images}
