"""Bounded request planning and execution state for the multi-agent app."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from router import Route, select_route
from tools import expression_from_text


@dataclass(frozen=True)
class TaskPlan:
    route: Route
    prompt: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    max_steps: int = 6
    timeout_seconds: float = 90.0
    max_retries: int = 1


@dataclass
class TaskRun:
    plan: TaskPlan
    status: str = "planned"
    checkpoints: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)

    def checkpoint(self, step: str) -> None:
        if len(self.checkpoints) >= self.plan.max_steps:
            self.status = "failed"
            raise RuntimeError("Task reached its maximum step count.")
        signature = hashlib.sha256(step.encode("utf-8")).hexdigest()
        if signature in self._seen:
            self.status = "failed"
            raise RuntimeError("Repeated task step detected; stopping to avoid a loop.")
        self._seen.add(signature)
        self.checkpoints.append(step)
        self.status = "running"

    async def execute(
        self,
        step: str,
        operation: Callable[[], Awaitable[Any]],
        timeout: float | None = None,
        retries: int = 0,
    ) -> Any:
        if retries < 0 or retries > self.plan.max_retries:
            raise ValueError("Requested retries exceed this task's retry limit.")
        self.checkpoint(step)
        for attempt in range(retries + 1):
            try:
                result = await asyncio.wait_for(operation(), timeout=timeout or self.plan.timeout_seconds)
                self.status = "completed"
                return result
            except asyncio.CancelledError:
                self.status = "cancelled"
                raise
            except Exception:
                if attempt == retries:
                    self.status = "failed"
                    raise


class AgentOrchestrator:
    """Use the local router for one specialist, adding a deterministic tool when safe."""

    def plan(self, message: str, command: str | None = None, default_agent: str = "Auto") -> TaskPlan:
        explicit = {
            "chat": "General",
            "math": "Math",
            "analyze": "Math",
            "write": "Writing",
            "summarize": "Writing",
            "research": "research",
            "code": "General",
        }
        route, prompt = select_route(message, selection=explicit.get(command, default_agent))
        tool_name = None
        tool_input = None
        if route.key == "math":
            expression = expression_from_text(message)
            if expression:
                tool_name = "calculator"
                tool_input = {"expression": expression}
        if command == "summarize":
            prompt = "Summarize the following content. Preserve important facts and structure the summary clearly with bullet points and key takeaways:\n\n" + prompt
        elif command == "research":
            prompt = "Conduct thorough, evidence-based research on the following topic with structured findings, clear citations, and an executive summary:\n\n" + prompt
        elif command == "code":
            prompt = "Help with the code request. Do not claim to execute or test code unless an execution tool was used.\n\n" + prompt
        elif command == "analyze":
            prompt = "Analyze the following calculation or data points with clear step-by-step explanations:\n\n" + prompt
        return TaskPlan(route=route, prompt=prompt, tool_name=tool_name, tool_input=tool_input)
