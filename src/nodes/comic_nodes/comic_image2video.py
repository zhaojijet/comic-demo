from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicImage2VideoInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Convert images to video; skip: Skip video gen; default: default",
    )


class ComicImage2VideoOutput(BaseModel):
    videos: List[str] = Field(description="List of paths/URLs to generated video clips")


@NODE_REGISTRY.register()
class ComicImage2VideoNode(BaseNode):
    meta = NodeMeta(
        name="comic_image2video",
        description="Convert highres images to video clips. This is the '图生视频' phase.",
        node_id="comic_image2video",
        node_kind="comic_image2video",
        require_prior_kind=["comic_highres_image"],
        default_require_prior_kind=["comic_highres_image"],
        next_available_node=["comic_post_production"],  # Bridge to Post-Production
    )

    input_schema = ComicImage2VideoInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"videos": ["default_video_1.mp4"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user("Comic Image2Video mock process started.")
        images = inputs.get("comic_highres_image", {}).get("highres_images", [])
        videos = [
            img.replace(".png", ".mp4").replace("highres", "video") for img in images
        ]
        node_state.node_summary.info_for_user(f"Generated {len(videos)} video clips.")
        return {"videos": videos}
