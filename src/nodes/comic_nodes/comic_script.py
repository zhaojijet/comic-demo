from typing import Any, Dict
from pydantic import BaseModel, Field
from typing import Literal, Annotated

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from utils.register import NODE_REGISTRY


class ComicScriptInput(BaseModel):
    mode: Literal["auto", "skip", "default"] = Field(
        default="auto",
        description="auto: Generate a comic script based on user prompt; skip: Skip generation; default: Use default",
    )
    user_request: Annotated[
        str, Field(default="", description="User requirements for the comic script")
    ]


class ComicScriptOutput(BaseModel):
    script: str = Field(description="The generated comic script")


@NODE_REGISTRY.register()
class ComicScriptNode(BaseNode):
    meta = NodeMeta(
        name="comic_script",
        description="Generate a script for a Manga/Comic Play (漫剧). This is the '确认剧本' phase.",
        node_id="comic_script",
        node_kind="comic_script",
        require_prior_kind=[],  # First node in comic workflow
        default_require_prior_kind=[],
        next_available_node=["comic_style"],
    )

    input_schema = ComicScriptInput

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        return {"script": "Default comic script (Mocked)"}

    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        node_state.node_summary.info_for_user(
            "Comic Script generation mock process started."
        )
        # Mock logic
        user_request = inputs.get("user_request", "A generic comic about a cat")
        script = f"Script generated for: {user_request}"
        node_state.node_summary.info_for_user(f"Generated comic script: {script}")
        return {"script": script}
