"""
node_interceptors.py — Tool call interceptors for MCP node execution.
No LangChain dependency — uses plain dicts and standard exceptions.
"""

from collections import defaultdict
from typing import List, Any, Dict
import os
from pathlib import Path
import json
import traceback

from nodes.node_manager import NodeManager
from storage.file import FileCompressor
from utils.logging import get_logger

logger = get_logger(__name__)


def compress_payload_to_base64(payload: Dict[str, List[Any]]):
    if not isinstance(payload, dict):
        return payload
    for key, value in payload.items():
        if isinstance(value, list) and all([isinstance(item, dict) for item in value]):
            for item in value:
                if "path" in item.keys():
                    path = item["path"]
                    compress_data = FileCompressor.compress_and_encode(path)
                    item.update(
                        {
                            "path": path,
                            "base64": compress_data.base64,
                            "md5": compress_data.md5,
                        }
                    )
        elif isinstance(value, dict):
            compress_payload_to_base64(value)


class ToolInterceptor:
    """
    Interceptors for MCP tool calls.
    These are invoked by the AgentLoop before/after tool execution.
    No LangChain dependency — uses plain dicts and standard Python exceptions.
    """

    @staticmethod
    async def inject_media_content_before(
        tool_name: str,
        args: dict,
        context: Any,
        store: Any,
    ) -> dict:
        """
        Pre-process tool arguments: inject prior node outputs and media content.
        Returns modified args dict.
        """
        try:
            session_id = context.session_id
            node_id = tool_name
            lang = context.lang
            artifact_id = store.generate_artifact_id(node_id)
            meta_collector: NodeManager = context.node_manager
            input_data = defaultdict(list)

            def load_collected_data(collected_node, input_data, store):
                for collect_kind, artifact_meta in collected_node.items():
                    _, prior_node_output = store.load_result(artifact_meta.artifact_id)
                    compress_payload_to_base64(prior_node_output["payload"])
                    input_data[collect_kind] = prior_node_output["payload"]

            if node_id == "load_media":
                input_data["inputs"] = []
                media_dir = Path(context.media_dir)
                for file_name in os.listdir(media_dir):
                    path = media_dir / file_name
                    if path.is_dir():
                        continue
                    compress_data = FileCompressor.compress_and_encode(path)
                    input_data["inputs"].append(
                        {
                            "path": str(path.relative_to(os.getcwd())),
                            "base64": compress_data.base64,
                            "md5": compress_data.md5,
                        }
                    )
            elif node_id in list(meta_collector.id_to_tool.keys()):
                tool_call_type = args.get("tool_call_type", "auto")
                is_skip_mode = args.get("mode", "auto") != "auto"
                require_kind = (
                    meta_collector.id_to_default_require_prior_kind[node_id]
                    if is_skip_mode
                    else meta_collector.id_to_require_prior_kind[node_id]
                )

                collect_result = meta_collector.check_excutable(
                    session_id, store, require_kind
                )
                load_collected_data(collect_result["collected_node"], input_data, store)

                if not collect_result["excutable"]:
                    missing_kinds = collect_result["missing_kind"]
                    logger.info(f"`{node_id}` require kind missing `{missing_kinds}`")
                    # Note: In the new architecture, the AgentLoop handles
                    # dependency resolution through its tool-calling iterations.
                    # The LLM will be informed of missing dependencies via error messages.
                    raise Exception(
                        f"Node '{node_id}' is missing prerequisites: {missing_kinds}. "
                        f"Please execute the prerequisite nodes first."
                    )
            else:
                input_data["artifacts_dir"] = store.artifacts_dir

            new_args = {
                "artifact_id": artifact_id,
                "lang": lang,
            }
            new_args.update(args)
            new_args.update(input_data)
            return new_args

        except Exception as e:
            logger.error("[ToolInterceptor] " + "".join(traceback.format_exception(e)))
            raise

    @staticmethod
    async def save_media_content_after(
        tool_name: str,
        result: str,
        context: Any,
        store: Any,
    ) -> dict:
        """
        Post-process tool results: save artifacts.
        Returns processed result dict.
        """
        try:
            tool_result = json.loads(result) if isinstance(result, str) else result
            node_id = tool_name
            artifact_id = tool_result.get("artifact_id", "")
            session_id = context.session_id

            if not tool_result.get("isError", False):
                store.save_result(session_id, node_id, tool_result)

            return {
                "summary": tool_result.get("summary", ""),
                "isError": tool_result.get("isError", False),
            }

        except Exception as e:
            logger.error("[ToolInterceptor] " + "".join(traceback.format_exception(e)))
            raise
