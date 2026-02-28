from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicPostProductionInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Edit and assemble clips; skip: Skip editing; default: default",
    )


class ComicPostProductionOutput(BaseModel):
    edited_video: str = Field(description="Path to the assembled and edited video")


@NODE_REGISTRY.register()
class ComicPostProductionNode(BaseNode):
    meta = NodeMeta(
        name="comic_post_production",
        description="Assemble video clips, add audio, text, and effects. This is the '剪辑&后期' phase.",
        node_id="comic_post_production",
        node_kind="comic_post_production",
        require_prior_kind=["comic_image2video", "comic_script"],
        default_require_prior_kind=["comic_image2video", "comic_script"],
        next_available_node=["comic_super_resolution"],
    )

    input_schema = ComicPostProductionInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"edited_video": "default_edited_video.mp4"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Post Production mock process started."
        )
        videos = inputs.get("comic_image2video", {}).get("videos", [])
        edited_video = "final_edited_comic_timeline.mp4"
        node_state.node_summary.info_for_user(
            f"Assembled {len(videos)} clips into {edited_video}."
        )
        return {"edited_video": edited_video}
