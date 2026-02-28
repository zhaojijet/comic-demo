"""
agent_loop.py — Custom tool-calling agent loop.
Replaces LangChain's create_agent with a direct OpenAI function-calling loop.
Inspired by openclaw's framework-free approach.
"""

import json
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from llm_client import LLMClient
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolDef:
    """A tool definition — replaces LangChain's StructuredTool."""

    name: str
    description: str
    parameters: dict  # JSON Schema
    callable: Optional[Callable] = None  # async callable
    metadata: Optional[dict] = None


@dataclass
class ToolCallResult:
    """Result from executing a tool call."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    additional_data: dict = field(default_factory=dict)


class AgentLoop:
    """
    Custom agent loop that replaces LangChain's create_agent.

    Flow:
    1. Send messages + tool definitions to LLM
    2. If response has tool_calls → execute tools → append results → goto 1
    3. If response has no tool_calls → return final text
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: list[ToolDef],
        *,
        max_iterations: int = 30,
        system_prompt: str = "",
        on_tool_start: Optional[Callable] = None,
        on_tool_end: Optional[Callable] = None,
        on_tool_error: Optional[Callable] = None,
    ):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.on_tool_error = on_tool_error

    def _build_tool_schemas(self) -> list[dict]:
        """Convert ToolDefs to OpenAI function-calling format."""
        schemas = []
        for tool in self.tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    async def ainvoke(self, input_data: dict) -> dict:
        """
        Run the agent loop.

        Args:
            input_data: {"input": "user message", "chat_history": [...]}

        Returns:
            {"output": "final assistant response", "messages": [...]}
        """
        user_input = input_data.get("input", "")
        chat_history = input_data.get("chat_history", [])

        # Build initial messages
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for msg in chat_history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_input})

        tool_schemas = self._build_tool_schemas()
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"[AgentLoop] Iteration {iteration}/{self.max_iterations}")

            # Call LLM
            if tool_schemas:
                response = await self.llm.chat_with_tools(
                    messages, tool_schemas, max_tokens=4096
                )
            else:
                response = await self.llm.chat(messages, max_tokens=4096)

            # Check for tool calls
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # No tool calls — agent is done
                final_text = response.get("content", "")
                logger.info(f"[AgentLoop] Complete after {iteration} iterations")
                return {"output": final_text, "messages": messages}

            # Append assistant message with tool calls
            messages.append(response)

            # Execute each tool call
            for tc in tool_calls:
                tc_id = tc["id"]
                func = tc["function"]
                tool_name = func["name"]
                try:
                    args = json.loads(func["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Callback: tool start
                if self.on_tool_start:
                    try:
                        await self.on_tool_start(tool_name, args, tc_id)
                    except Exception:
                        pass

                # Execute the tool
                tool_result = await self._execute_tool(tool_name, args, tc_id)

                # Callback: tool end
                if tool_result.is_error and self.on_tool_error:
                    try:
                        await self.on_tool_error(tool_name, tool_result.content, tc_id)
                    except Exception:
                        pass
                elif self.on_tool_end:
                    try:
                        await self.on_tool_end(tool_name, tool_result.content, tc_id)
                    except Exception:
                        pass

                # Append tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": tool_name,
                        "content": tool_result.content,
                    }
                )

        logger.warning(f"[AgentLoop] Hit max iterations ({self.max_iterations})")
        return {"output": "Agent reached maximum iterations.", "messages": messages}

    async def _execute_tool(self, name: str, args: dict, tc_id: str) -> ToolCallResult:
        """Execute a single tool call."""
        tool = self.tools.get(name)
        if not tool:
            return ToolCallResult(
                tool_call_id=tc_id,
                name=name,
                content=f"Error: Unknown tool '{name}'",
                is_error=True,
            )

        if not tool.callable:
            return ToolCallResult(
                tool_call_id=tc_id,
                name=name,
                content=f"Error: Tool '{name}' has no callable",
                is_error=True,
            )

        try:
            result = await tool.callable(**args) if args else await tool.callable()
            content = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False)
            )
            return ToolCallResult(
                tool_call_id=tc_id,
                name=name,
                content=content,
            )
        except Exception as e:
            logger.error(
                f"[AgentLoop] Tool '{name}' error: {e}\n{traceback.format_exc()}"
            )
            return ToolCallResult(
                tool_call_id=tc_id,
                name=name,
                content=(
                    f"Tool call failed\n"
                    f"Tool name: {name}\n"
                    f"Error: {type(e).__name__}: {e}\n"
                    f"If it is a parameter issue, please correct and retry. "
                    f"If a preceding dependency is missing, call the preceding node first."
                ),
                is_error=True,
            )
