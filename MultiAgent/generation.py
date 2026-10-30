"""Provider-independent streaming and non-streaming fallback."""

import asyncio
from contextvars import ContextVar
import logging

from agent_loop import AgentLoopResult, ToolCallingNotSupportedError, run_agent_loop
from tools import ToolRegistry
from provider_router import error_details, provider_health, should_failover

logger = logging.getLogger(__name__)
_usage: ContextVar[dict | None] = ContextVar("provider_usage", default=None)


class ProvidersUnavailableError(RuntimeError):
    """All eligible configured providers failed or are cooling down."""


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
    """Try eligible providers in priority order; never retries one provider per turn."""
    candidates = list(dict.fromkeys(provider_health.available(list(providers))))
    if not candidates:
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.")
    _usage.set(None)
    last_error = None
    attempted = 0
    for provider in candidates:
        if attempted:
            await on_fallback(provider)
        started = provider_health.begin(provider)
        attempted += 1
        try:
            model = create_model(provider)
            response = await generate(model, messages, on_token, streaming=streaming)
            provider_health.success(provider, started, _usage.get())
            return response, provider
        except asyncio.CancelledError as exc:
            provider_health.failure(provider, started, exc, status=None)
            raise
        except Exception as exc:
            last_error = exc
            status, retry_after = error_details(exc)
            provider_health.failure(provider, started, exc, status=status, retry_after=retry_after)
            logger.warning("Provider attempt failed (provider=%s type=%s status=%s)", provider, type(exc).__name__, status or "unknown")
            if not should_failover(exc):
                raise
    if last_error is not None:
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.") from last_error
    raise ProvidersUnavailableError("No configured AI provider is available for this request.")


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
    tool_choice: str = "auto",
):
    """Run the native tool loop and retry with the next configured provider."""
    candidates = list(dict.fromkeys(provider_health.available(list(providers))))
    if not candidates:
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.")
    last_error = None
    attempted = 0
    for provider in candidates:
        if attempted:
            await on_fallback(provider)
        started = provider_health.begin(provider)
        attempted += 1
        try:
            result: AgentLoopResult = await run_agent_loop(
                create_model(provider),
                list(messages),
                registry,
                provider=provider,
                model_name=model_name_for(provider),
                permissions=permissions,
                max_steps=max_steps,
                tool_choice=tool_choice,
            )
            provider_health.success(provider, started, result.usage)
            await on_token(result.text)
            return result.text, provider, result.tool_steps
        except asyncio.CancelledError as exc:
            provider_health.failure(provider, started, exc, status=None)
            raise
        except ToolCallingNotSupportedError as exc:
            last_error = exc
            provider_health.skipped(provider, started, type(exc).__name__)
            logger.info("Provider skipped for unsupported tool calling (provider=%s)", provider)
            continue
        except Exception as exc:
            last_error = exc
            status, retry_after = error_details(exc)
            provider_health.failure(provider, started, exc, status=status, retry_after=retry_after)
            logger.warning(
                "Agent provider attempt failed (provider=%s type=%s status=%s)",
                provider,
                type(exc).__name__,
                status or "unknown",
            )
            if not should_failover(exc):
                raise
    if last_error is not None:
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.") from last_error
    raise ProvidersUnavailableError("No configured AI provider is available for this request.")


async def generate(model, messages, on_token, streaming: bool = True):
    parts = []
    usage: dict[str, int] = {}
    stream = getattr(model, "astream", None)
    if streaming and callable(stream):
        iterator = stream(messages)
        try:
            async for chunk in iterator:
                content = _text_content(getattr(chunk, "content", ""))
                if content:
                    parts.append(content)
                    await on_token(content)
                _merge_usage(usage, getattr(chunk, "usage_metadata", None))
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
        result = "".join(parts).strip()
        if not result:
            raise EmptyResponseError("Provider stream completed without assistant text.")
        _usage.set(usage or None)
        return "".join(parts)

    invoke = getattr(model, "ainvoke", None)
    result = await invoke(messages) if callable(invoke) else await asyncio.to_thread(model.invoke, messages)
    content = _text_content(getattr(result, "content", result if isinstance(result, str) else ""))
    if content:
        _merge_usage(usage, getattr(result, "usage_metadata", None))
        _usage.set(usage or None)
        await on_token(content)
        return content
    raise EmptyResponseError("Provider returned no assistant text.")


def _merge_usage(target: dict[str, int], value) -> None:
    if not isinstance(value, dict):
        return
    target["input_tokens"] = max(target.get("input_tokens", 0), int(value.get("input_tokens", value.get("prompt_tokens", 0)) or 0))
    target["output_tokens"] = max(target.get("output_tokens", 0), int(value.get("output_tokens", value.get("completion_tokens", 0)) or 0))
