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
            "Comic Storyboard creation mock process started."
        )
        panels = [
            {"panel": 1, "desc": "Establish shot", "characters": ["Protagonist"]},
            {"panel": 2, "desc": "Action shot", "characters": ["Antagonist"]},
        ]
        node_state.node_summary.info_for_user(
            f"Generated storyboard with {len(panels)} panels."
        )
        return {"storyboard": panels}
