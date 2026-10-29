"""Bounded native function-calling loop shared by the specialist agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage

from tools import ToolRegistry


VERIFIED_TOOL_MODELS = {
    "google": {"gemini-3.8-flash"},
    "groq": {"openai/gpt-oss-20b", "openai/gpt-oss-120b"},
}


class ToolCallingNotSupportedError(RuntimeError):
    """The selected model has not been verified for native tool calling."""


@dataclass(frozen=True)
class AgentLoopResult:
    text: str
    tool_steps: tuple[str, ...]


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
    return ""


def _tool_call_parts(call: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    name = str(call.get("name") or "")
    arguments = call.get("args", call.get("arguments", {}))
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    call_id = str(call.get("id") or "")
    if not name or not call_id:
        raise ValueError("The model returned an incomplete tool call.")
    return name, arguments, call_id


async def run_agent_loop(
    model: Any,
    messages: list[Any],
    registry: ToolRegistry,
    *,
    provider: str,
    model_name: str,
    permissions: set[str] | None = None,
    max_steps: int = 8,
) -> AgentLoopResult:
    """Call the model, run requested registered tools, and return its final answer."""
    schemas = registry.model_tools(permissions)
    if not schemas:
        raise ValueError("No tools are available to this task.")
    if model_name not in VERIFIED_TOOL_MODELS.get(provider, set()):
        raise ToolCallingNotSupportedError(
            f"Native tool calling has not been verified for {provider} model '{model_name}'. "
            "Choose Gemini gemini-3.8-flash or Groq openai/gpt-oss-20b / openai/gpt-oss-120b, "
            "or set a verified model in .env."
        )
    bind_tools = getattr(model, "bind_tools", None)
    if not callable(bind_tools):
        raise ToolCallingNotSupportedError(
            f"The {provider} integration for '{model_name}' does not expose native tool calling. "
            "Choose Gemini gemini-3.8-flash or a Groq GPT-OSS model."
        )
    try:
        tool_model = bind_tools(schemas, tool_choice="auto")
    except (NotImplementedError, TypeError, ValueError) as exc:
        raise ToolCallingNotSupportedError(
            f"Native tool calling could not be enabled for {provider} model '{model_name}'. "
            "Choose Gemini gemini-3.8-flash or a Groq GPT-OSS model."
        ) from exc

    working_messages = list(messages)
    allowed_names = registry.allowed_names(permissions)
    used_steps: list[str] = []
    seen_calls: set[str] = set()

    for _ in range(max_steps):
        response = await tool_model.ainvoke(working_messages)
        calls = list(getattr(response, "tool_calls", None) or [])
        if not calls:
            text = _message_text(response)
            if not text:
                raise RuntimeError("The model returned no final answer after the tool loop.")
            return AgentLoopResult(text=text, tool_steps=tuple(used_steps))

        working_messages.append(response)
        remaining_steps = max_steps - len(used_steps)
        allowed_calls = calls[:remaining_steps]
        for call in allowed_calls:
            name, arguments, call_id = _tool_call_parts(call)
            if name not in allowed_names:
                result = {"ok": False, "error": "That tool is not available for this task."}
            else:
                signature = json.dumps([name, arguments], sort_keys=True, default=str)
                if signature in seen_calls:
                    result = {"ok": False, "error": "That exact tool call was already attempted."}
                else:
                    seen_calls.add(signature)
                    execution = await registry.execute(name, arguments, permissions=permissions)
                    result = {"ok": execution.ok}
                    if execution.ok:
                        result["data"] = execution.data
                    else:
                        result["error"] = execution.error
            used_steps.append(name)
            working_messages.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False, default=str),
                tool_call_id=call_id,
                name=name,
            ))
        if len(allowed_calls) < len(calls):
            for call in calls[len(allowed_calls):]:
                name, _, call_id = _tool_call_parts(call)
                working_messages.append(ToolMessage(
                    content=json.dumps({"ok": False, "error": "The task reached its tool step limit."}),
                    tool_call_id=call_id,
                    name=name,
                ))
            break

    # Give the model one final chance to summarize the last tool results, with no
    # tools bound, so reaching the tool limit still produces a clean user answer.
    final = await model.ainvoke(working_messages)
    text = _message_text(final)
    if not text:
        raise RuntimeError("The model reached the tool step limit without a readable final answer.")
    return AgentLoopResult(text=text, tool_steps=tuple(used_steps))
