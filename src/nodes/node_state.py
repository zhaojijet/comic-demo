from dataclasses import dataclass

from mcp_custom.sampling_requester import SamplingLLMClient
from nodes.node_summary import NodeSummary

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession


@dataclass
class NodeState:
    """Node execution state"""

    session_id: str
    artifact_id: str
    lang: str
    node_summary: NodeSummary
    llm: SamplingLLMClient
    mcp_ctx: Context[ServerSession, object]
