from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicStyleInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Confirm graphic style based on script; skip: Skip style; default: Use default style",
    )
    user_request: Annotated[
        str,
        Field(default="", description="User requirements for the comic visual style"),
    ]


class ComicStyleOutput(BaseModel):
    style_description: str = Field(description="The confirmed visual style description")


@NODE_REGISTRY.register()
class ComicStyleNode(BaseNode):
    meta = NodeMeta(
        name="comic_style",
        description="Confirm the visual style for the comic. This is the '确认风格' phase.",
        node_id="comic_style",
        node_kind="comic_style",
        require_prior_kind=["comic_script"],
        default_require_prior_kind=["comic_script"],
        next_available_node=["comic_character"],
    )

    input_schema = ComicStyleInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"style_description": "Default comic style (Mocked)"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Style confirmation mock process started."
        )
        # Ensure we have the outputs of previous nodes before processing
        prev_script = inputs.get("comic_script", {}).get("script", "Unknown Script")
        style = f"Style aligned with script: {prev_script}"
        node_state.node_summary.info_for_user(f"Confirmed comic style: {style}")
        return {"style_description": style}
