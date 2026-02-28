from typing import Any, Dict, List
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicCharacterInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Identify characters; skip: Skip character identification; default: default characters",
    )
    user_request: Annotated[
        str, Field(default="", description="User requirements for character design")
    ]


class ComicCharacterOutput(BaseModel):
    characters: List[str] = Field(
        description="List of designed characters (Three views + Expressions + Poses)"
    )


@NODE_REGISTRY.register()
class ComicCharacterNode(BaseNode):
    meta = NodeMeta(
        name="comic_character",
        description="Confirm and design characters (Three views, Expressions, Poses). This is the '确认角色' phase.",
        node_id="comic_character",
        node_kind="comic_character",
        require_prior_kind=["comic_script", "comic_style"],
        default_require_prior_kind=["comic_script", "comic_style"],
        next_available_node=["comic_storyboard"],
    )

    input_schema = ComicCharacterInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"characters": ["Default Character A", "Default Character B"]}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Character design mock process started."
        )
        characters = ["Protagonist", "Antagonist", "Sidekick"]
        node_state.node_summary.info_for_user(f"Confirmed characters: {characters}")
        return {"characters": characters}
