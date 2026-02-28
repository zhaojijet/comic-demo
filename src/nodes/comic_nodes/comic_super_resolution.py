from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicSuperResolutionInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Upscale video; skip: Skip upscale; default: default",
    )


class ComicSuperResolutionOutput(BaseModel):
    final_video: str = Field(description="Path to the final super-resolution video")


@NODE_REGISTRY.register()
class ComicSuperResolutionNode(BaseNode):
    meta = NodeMeta(
        name="comic_super_resolution",
        description="Upscale the final video for better quality. This is the '视频超分' phase.",
        node_id="comic_super_resolution",
        node_kind="comic_super_resolution",
        require_prior_kind=["comic_post_production"],
        default_require_prior_kind=["comic_post_production"],
        next_available_node=[],  # Final node in the pipeline
    )

    input_schema = ComicSuperResolutionInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"final_video": "default_final_4k_video.mp4"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Super Resolution mock process started."
        )
        edited = inputs.get("comic_post_production", {}).get(
            "edited_video", "video.mp4"
        )
        final_video = edited.replace(".mp4", "_4k_super_res.mp4")
        node_state.node_summary.info_for_user(f"Upscaled video to {final_video}.")
        return {"final_video": final_video}
