"""Provider-independent streaming and non-streaming fallback."""

import asyncio
from contextvars import ContextVar
import logging

from agent_loop import AgentResponseIncompleteError, AgentResponseInterruptedError, AgentLoopResult, ToolCallingNotSupportedError, run_agent_loop
from tools import ToolRegistry
from provider_router import current_request_id, error_details, provider_health, should_failover

logger = logging.getLogger(__name__)
_usage: ContextVar[dict | None] = ContextVar("provider_usage", default=None)


class ProvidersUnavailableError(RuntimeError):
    """All eligible configured providers failed or are cooling down."""

    def __init__(self, message, *, provider=None, status=None, retry_after=None):
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retry_after = retry_after


class EmptyResponseError(RuntimeError):
    """Raised when a provider finishes without usable assistant text."""


class IncompleteResponseError(RuntimeError):
    """A provider stopped for a known non-final reason such as an output limit."""

    def __init__(self, partial: str, finish_reason: str):
        super().__init__(f"Provider ended before completing the response ({finish_reason}).")
        self.partial = partial
        self.finish_reason = finish_reason


class InterruptedResponseError(RuntimeError):
    """A stream failed after yielding text, so its partial answer is retained."""

    def __init__(self, partial: str, cause: Exception):
        super().__init__("The provider stream ended unexpectedly after producing partial text.")
        self.partial = partial
        self.cause = cause


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
    last_provider = None
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
        except IncompleteResponseError:
            # A token limit is a successful provider response, but an incomplete
            # user response. Do not retry another provider and duplicate text.
            provider_health.success(provider, started, _usage.get())
            raise
        except InterruptedResponseError as exc:
            status, retry_after = error_details(exc.cause)
            provider_health.failure(provider, started, exc.cause, status=status, retry_after=retry_after)
            logger.warning("Provider stream interrupted after partial output (request_id=%s provider=%s type=%s)", current_request_id.get() or "unknown", provider, type(exc.cause).__name__)
            raise
        except asyncio.CancelledError as exc:
            provider_health.cancelled(provider, started)
            raise
        except Exception as exc:
            last_error = exc
            last_provider = provider
            status, retry_after = error_details(exc)
            provider_health.failure(provider, started, exc, status=status, retry_after=retry_after)
            logger.warning("Provider attempt failed (request_id=%s provider=%s type=%s status=%s)", current_request_id.get() or "unknown", provider, type(exc).__name__, status or "unknown")
            if not should_failover(exc):
                raise
    if last_error is not None:
        status, retry_after = error_details(last_error)
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.", provider=last_provider, status=status, retry_after=retry_after) from last_error
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
    on_tool_event=None,
    streaming: bool = True,
):
    """Run the native tool loop and retry with the next configured provider."""
    candidates = list(dict.fromkeys(provider_health.available(list(providers))))
    if not candidates:
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.")
    last_error = None
    last_provider = None
    attempted = 0
    for provider in candidates:
        if attempted:
            await on_fallback(provider)
        started = provider_health.begin(provider)
        attempted += 1
        tool_execution_started = False

        async def report_tool_event(event):
            nonlocal tool_execution_started
            if event.get("state") == "started":
                tool_execution_started = True
            if on_tool_event:
                await on_tool_event(event)

        try:
            model = create_model(provider)
            supports_streaming = streaming and callable(getattr(model, "astream", None))
            result: AgentLoopResult = await run_agent_loop(
                model,
                list(messages),
                registry,
                provider=provider,
                model_name=model_name_for(provider),
                permissions=permissions,
                max_steps=max_steps,
                tool_choice=tool_choice,
                on_tool_event=report_tool_event,
                on_token=on_token if streaming else None,
            )
            provider_health.success(provider, started, result.usage)
            if not supports_streaming:
                await on_token(result.text)
            return result.text, provider, result.tool_steps
        except asyncio.CancelledError as exc:
            provider_health.cancelled(provider, started)
            raise
        except ToolCallingNotSupportedError as exc:
            last_error = exc
            last_provider = provider
            provider_health.skipped(provider, started, type(exc).__name__)
            logger.info("Provider skipped for unsupported tool calling (provider=%s)", provider)
            continue
        except AgentResponseIncompleteError as exc:
            provider_health.success(provider, started)
            raise IncompleteResponseError(exc.partial, exc.finish_reason) from exc
        except AgentResponseInterruptedError as exc:
            status, retry_after = error_details(exc.cause)
            provider_health.failure(provider, started, exc.cause, status=status, retry_after=retry_after)
            raise InterruptedResponseError(exc.partial, exc.cause) from exc
        except Exception as exc:
            last_error = exc
            last_provider = provider
            status, retry_after = error_details(exc)
            provider_health.failure(provider, started, exc, status=status, retry_after=retry_after)
            logger.warning(
                "Agent provider attempt failed (request_id=%s provider=%s type=%s status=%s)",
                current_request_id.get() or "unknown",
                provider,
                type(exc).__name__,
                status or "unknown",
            )
            # Retrying the full agent loop after a tool ran could repeat an MCP
            # write or other side effect. Only fail over before tool execution.
            if tool_execution_started:
                raise
            if not should_failover(exc):
                raise
    if last_error is not None:
        status, retry_after = error_details(last_error)
        raise ProvidersUnavailableError("All configured AI providers are unavailable right now. Please try again shortly.", provider=last_provider, status=status, retry_after=retry_after) from last_error
    raise ProvidersUnavailableError("No configured AI provider is available for this request.")


async def generate(model, messages, on_token, streaming: bool = True):
    parts = []
    usage: dict[str, int] = {}
    stream = getattr(model, "astream", None)
    if streaming and callable(stream):
        iterator = stream(messages)
        finish_reason = None
        try:
            try:
                async for chunk in iterator:
                    content = _text_content(getattr(chunk, "content", ""))
                    if content:
                        parts.append(content)
                        await on_token(content)
                    finish_reason = _finish_reason(chunk) or finish_reason
                    _merge_usage(usage, getattr(chunk, "usage_metadata", None))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if parts:
                    raise InterruptedResponseError("".join(parts), exc) from exc
                raise
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
        result = "".join(parts).strip()
        if not result:
            raise EmptyResponseError("Provider stream completed without assistant text.")
        _usage.set(usage or None)
        if _is_length_finish(finish_reason):
            raise IncompleteResponseError("".join(parts), finish_reason)
        return "".join(parts)

    invoke = getattr(model, "ainvoke", None)
    result = await invoke(messages) if callable(invoke) else await asyncio.to_thread(model.invoke, messages)
    content = _text_content(getattr(result, "content", result if isinstance(result, str) else ""))
    finish_reason = _finish_reason(result)
    if content:
        _merge_usage(usage, getattr(result, "usage_metadata", None))
        _usage.set(usage or None)
        await on_token(content)
        if _is_length_finish(finish_reason):
            raise IncompleteResponseError(content, finish_reason)
        return content
    raise EmptyResponseError("Provider returned no assistant text.")


def _merge_usage(target: dict[str, int], value) -> None:
    if not isinstance(value, dict):
        return
    target["input_tokens"] = max(target.get("input_tokens", 0), int(value.get("input_tokens", value.get("prompt_tokens", 0)) or 0))
    target["output_tokens"] = max(target.get("output_tokens", 0), int(value.get("output_tokens", value.get("completion_tokens", 0)) or 0))


def _finish_reason(message) -> str | None:
    """Read normalized finish metadata exposed by LangChain/provider adapters."""
    for source in (
        getattr(message, "response_metadata", None),
        getattr(message, "generation_info", None),
        getattr(message, "additional_kwargs", None),
    ):
        if isinstance(source, dict):
            for key in ("finish_reason", "finishReason", "stop_reason", "stopReason"):
                value = source.get(key)
                if value is not None:
                    return str(value).casefold()
    return None


def _is_length_finish(reason: str | None) -> bool:
    return reason is not None and any(token in reason for token in ("max_tokens", "max token", "length", "token_limit", "token limit"))
