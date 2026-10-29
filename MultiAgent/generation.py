"""Provider-independent streaming and non-streaming fallback."""

import asyncio
import logging

from agent_loop import AgentLoopResult, ToolCallingNotSupportedError, run_agent_loop
from tools import ToolRegistry

logger = logging.getLogger(__name__)


class EmptyResponseError(RuntimeError):
    """Raised when a provider finishes without usable assistant text."""


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


async def generate_with_fallback(providers, create_model, messages, on_token, on_fallback, streaming=True):
    """Try configured providers in order and notify the caller before a retry."""
    last_error = None
    for index, provider in enumerate(providers):
        if index:
            await on_fallback(provider)
        try:
            model = create_model(provider)
            response = await generate(model, messages, on_token, streaming=streaming)
            return response, provider
        except Exception as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning("Provider attempt failed (provider=%s type=%s status=%s)", provider, type(exc).__name__, status or "unknown")
    if last_error is not None:
        raise last_error
    raise RuntimeError("No provider was configured for this request.")


async def generate_agent_with_fallback(
    providers,
    create_model,
    model_name_for,
    messages,
    on_token,
    on_fallback,
    registry: ToolRegistry,
    *,
    permissions: set[str] | None = None,
    max_steps: int = 8,
):
    """Run the native tool loop and retry with the next configured provider."""
    last_error = None
    for index, provider in enumerate(providers):
        if index:
            await on_fallback(provider)
        try:
            result: AgentLoopResult = await run_agent_loop(
                create_model(provider),
                list(messages),
                registry,
                provider=provider,
                model_name=model_name_for(provider),
                permissions=permissions,
                max_steps=max_steps,
            )
            await on_token(result.text)
            return result.text, provider, result.tool_steps
        except ToolCallingNotSupportedError:
            raise
        except Exception as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "Agent provider attempt failed (provider=%s type=%s status=%s)",
                provider,
                type(exc).__name__,
                status or "unknown",
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError("No provider was configured for this request.")


async def generate(model, messages, on_token, streaming: bool = True):
    parts = []
    stream = getattr(model, "astream", None)
    if streaming and callable(stream):
        iterator = stream(messages)
        try:
            async for chunk in iterator:
                content = _text_content(getattr(chunk, "content", ""))
                if content:
                    parts.append(content)
                    await on_token(content)
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
        result = "".join(parts).strip()
        if not result:
            raise EmptyResponseError("Provider stream completed without assistant text.")
        return "".join(parts)

    invoke = getattr(model, "ainvoke", None)
    result = await invoke(messages) if callable(invoke) else await asyncio.to_thread(model.invoke, messages)
    content = _text_content(getattr(result, "content", result if isinstance(result, str) else ""))
    if content:
        await on_token(content)
        return content
    raise EmptyResponseError("Provider returned no assistant text.")
