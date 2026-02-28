"""
node_manager.py — Manages tool/node registrations and dependency checking.
No LangChain dependency — uses ToolDef from agent_loop instead of StructuredTool.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from storage.agent_memory import ArtifactStore


class NodeManager:
    """Manages comic pipeline nodes and their dependencies."""

    def __init__(self, tools: list = None):
        self.kind_to_node_ids: Dict[str, List[str]] = defaultdict(list)
        self.id_to_tool: Dict[str, Any] = {}  # node_id -> ToolDef
        self.id_to_next: Dict[str, List[str]] = {}
        self.id_to_priority: Dict[str, int] = {}
        self.id_to_kind: Dict[str, str] = {}

        # Prerequisite dependencies
        self.id_to_require_prior_kind: Dict[str, List[str]] = {}
        self.id_to_default_require_prior_kind: Dict[str, List[str]] = {}

        # Reverse index
        self.kind_to_dependent_nodes: Dict[str, Set[str]] = defaultdict(set)
        self.kind_to_default_dependent_nodes: Dict[str, Set[str]] = defaultdict(set)

        if tools:
            self._build(tools)

    def _build(self, tools: list):
        for tool in tools:
            metadata = getattr(tool, "metadata", None)
            if metadata:
                meta = metadata.get("_meta", {}) if isinstance(metadata, dict) else {}
                node_id = meta.get("node_id")
                if node_id:
                    self.add_node(tool)

    def add_node(self, tool) -> bool:
        metadata = getattr(tool, "metadata", None)
        if not metadata:
            return False

        meta = metadata.get("_meta", {}) if isinstance(metadata, dict) else {}
        node_id = meta.get("node_id")

        if not node_id:
            return False

        if node_id in self.id_to_tool:
            self.remove_node(node_id)

        node_kind = meta.get("node_kind", node_id)
        priority = meta.get("priority", 0)
        next_nodes = meta.get("next_available_node", [])
        require_prior_kind = meta.get("require_prior_kind", [])
        default_require_prior_kind = meta.get("default_require_prior_kind", [])

        self.id_to_tool[node_id] = tool
        self.id_to_priority[node_id] = priority
        self.id_to_next[node_id] = next_nodes
        self.id_to_kind[node_id] = node_kind
        self.id_to_require_prior_kind[node_id] = require_prior_kind
        self.id_to_default_require_prior_kind[node_id] = default_require_prior_kind

        self.kind_to_node_ids[node_kind].append(node_id)
        self._sort_kind(node_kind)

        for kind in require_prior_kind:
            self.kind_to_dependent_nodes[kind].add(node_id)

        for kind in default_require_prior_kind:
            self.kind_to_default_dependent_nodes[kind].add(node_id)

        return True

    def remove_node(self, node_id: str, clean_references: bool = True) -> bool:
        if node_id not in self.id_to_tool:
            return False

        node_kind = self.id_to_kind[node_id]

        if node_id in self.id_to_require_prior_kind:
            for kind in self.id_to_require_prior_kind[node_id]:
                self.kind_to_dependent_nodes[kind].discard(node_id)
                if not self.kind_to_dependent_nodes[kind]:
                    del self.kind_to_dependent_nodes[kind]

        if node_id in self.id_to_default_require_prior_kind:
            for kind in self.id_to_default_require_prior_kind[node_id]:
                self.kind_to_default_dependent_nodes[kind].discard(node_id)
                if not self.kind_to_default_dependent_nodes[kind]:
                    del self.kind_to_default_dependent_nodes[kind]

        del self.id_to_tool[node_id]
        del self.id_to_priority[node_id]
        del self.id_to_next[node_id]
        del self.id_to_kind[node_id]

        if node_id in self.id_to_require_prior_kind:
            del self.id_to_require_prior_kind[node_id]
        if node_id in self.id_to_default_require_prior_kind:
            del self.id_to_default_require_prior_kind[node_id]

        if node_id in self.kind_to_node_ids[node_kind]:
            self.kind_to_node_ids[node_kind].remove(node_id)

        if not self.kind_to_node_ids[node_kind]:
            del self.kind_to_node_ids[node_kind]

        if clean_references:
            for nid in list(self.id_to_next.keys()):
                if node_id in self.id_to_next[nid]:
                    self.id_to_next[nid].remove(node_id)

        return True

    def _sort_kind(self, kind: str):
        if kind in self.kind_to_node_ids:
            self.kind_to_node_ids[kind].sort(
                key=lambda nid: self.id_to_priority[nid], reverse=True
            )

    def get_tool(self, node_id: str) -> Optional[Any]:
        return self.id_to_tool.get(node_id)

    def check_excutable(
        self, session_id: str, store: ArtifactStore, all_require_kind: List[str]
    ) -> Dict[str, Any]:
        collected_output = {}
        for req_kind in all_require_kind:
            req_ids_queue = self.kind_to_node_ids[req_kind]
            valid_outputs = []
            for node_id in req_ids_queue:
                output = store.get_latest_meta(node_id=node_id, session_id=session_id)
                if output is not None:
                    valid_outputs.append(output)

            if valid_outputs:
                latest_output = max(valid_outputs, key=lambda output: output.created_at)
                collected_output[req_kind] = latest_output

        return {
            "excutable": len(collected_output.keys()) == len(all_require_kind),
            "collected_node": collected_output,
            "missing_kind": list(set(all_require_kind) - set(collected_output.keys())),
        }
