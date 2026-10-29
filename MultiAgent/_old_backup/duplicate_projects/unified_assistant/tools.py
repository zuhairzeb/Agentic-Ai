"""Validated, bounded tools available to the assistant."""

from __future__ import annotations

import ast
import asyncio
from io import BytesIO
import logging
import math
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pypdf import PdfReader

logger = logging.getLogger(__name__)


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=200)


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    content: bytes = Field(max_length=10 * 1024 * 1024)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[dict[str, Any]]]
    permission: str | None = None
    timeout_seconds: float = 3.0
    max_retries: int = 0


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def describe(self) -> list[dict[str, str]]:
        return [{"name": tool.name, "description": tool.description} for tool in self._tools.values()]

    async def execute(self, name: str, payload: dict[str, Any], permissions: set[str] | None = None) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, error="That tool is not registered.")
        if tool.permission and tool.permission not in (permissions or set()):
            return ToolResult(False, error="Permission for this tool was not granted.")
        try:
            arguments = tool.input_model.model_validate(payload)
        except ValidationError:
            return ToolResult(False, error="Tool input did not match its required schema.")

        attempts = tool.max_retries + 1
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(tool.handler(arguments), timeout=tool.timeout_seconds)
                logger.info("Tool completed (tool=%s)", tool.name)
                return ToolResult(True, data=result)
            except asyncio.TimeoutError:
                logger.warning("Tool timed out (tool=%s)", tool.name)
                if attempt + 1 == attempts:
                    return ToolResult(False, error="The tool timed out. Try a simpler request.")
            except (ValueError, ArithmeticError) as exc:
                return ToolResult(False, error=str(exc))
            except Exception as exc:
                logger.error("Tool failed (tool=%s type=%s)", tool.name, type(exc).__name__)
                if attempt + 1 == attempts:
                    return ToolResult(False, error="The tool failed safely. Please revise the input and try again.")
        return ToolResult(False, error="The tool could not complete the request.")


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST, budget: list[int]) -> int | float:
    budget[0] += 1
    if budget[0] > 40:
        raise ValueError("This calculation is too complex.")
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, budget)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        if abs(node.value) > 1e50:
            raise ValueError("The number is outside the supported range.")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, budget))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left, budget)
        right = _evaluate(node.right, budget)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("Exponents are limited to 12 in magnitude.")
        value = _BINARY_OPERATORS[type(node.op)](left, right)
        if not isinstance(value, (int, float)):
            raise ValueError("Complex-number results are not supported.")
        if abs(value) > 1e50 or not math.isfinite(float(value)):
            raise ValueError("The result is outside the supported range.")
        return value
    raise ValueError("Only basic arithmetic with numbers and parentheses is supported.")


def calculate(expression: str) -> dict[str, Any]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Enter a valid arithmetic expression.") from exc
    result = _evaluate(tree, [0])
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    formatted = format(result, ".12g") if isinstance(result, float) else str(result)
    return {"expression": expression, "value": result, "formatted": formatted}


async def _calculate_handler(arguments: BaseModel) -> dict[str, Any]:
    return calculate(arguments.expression)


def _extract_document(name: str, content: bytes) -> dict[str, Any]:
    suffix = Path(name).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Text uploads must use UTF-8 encoding.") from exc
    elif suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            if len(reader.pages) > 200:
                raise ValueError("PDFs are limited to 200 pages.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The PDF could not be parsed.") from exc
    else:
        raise ValueError("Supported uploads are TXT, Markdown, and text-based PDF files.")
    text = text.strip()
    if not text:
        raise ValueError("No readable text was found. Scanned PDFs require OCR, which is not configured.")
    return {"name": Path(name).name, "text": text[:20000], "truncated": len(text) > 20000}


async def _extract_document_handler(arguments: BaseModel) -> dict[str, Any]:
    return await asyncio.to_thread(_extract_document, arguments.name, arguments.content)


def expression_from_text(text: str) -> str | None:
    """Convert common short math phrasing into a safe arithmetic expression."""
    lowered = text.lower().strip()
    percent = re.search(r"(-?\d+(?:\.\d+)?)\s*%\s*of\s*(-?\d+(?:\.\d+)?)", lowered)
    if percent:
        return f"({percent.group(1)}/100)*({percent.group(2)})"
    expression = re.sub(r"^(please\s+)?(calculate|compute|solve|what is|what's)\s+", "", lowered)
    expression = expression.rstrip(" ?.! ")
    expression = re.sub(r"\b(multiplied by|times)\b", "*", expression)
    expression = re.sub(r"\b(divided by|over)\b", "/", expression)
    expression = re.sub(r"\bplus\b", "+", expression)
    expression = re.sub(r"\bminus\b", "-", expression)
    expression = expression.replace("^", "**")
    if not re.fullmatch(r"[0-9\s.+*/()%\-]+(?:\*\*)?", expression):
        return None
    return expression.strip() or None


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="calculator",
        description="Evaluate bounded basic arithmetic without executing Python or shell code.",
        input_model=CalculatorInput,
        handler=_calculate_handler,
        permission="math",
        timeout_seconds=1.0,
    ))
    registry.register(ToolDefinition(
        name="extract_document",
        description="Extract bounded text from an uploaded TXT, Markdown, or text-based PDF document.",
        input_model=DocumentInput,
        handler=_extract_document_handler,
        permission="file_read",
        timeout_seconds=8.0,
    ))
    return registry


tools = build_tool_registry()
