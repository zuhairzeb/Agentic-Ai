"""Free-aware provider eligibility, health circuits, and privacy-safe telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ipaddress
import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

from config import Config

logger = logging.getLogger(__name__)

ALIASES = {"gemini": "google", "google": "google", "google gemini": "google", "groq": "groq",
           "cloudflare": "cloudflare", "cloudflare workers ai": "cloudflare",
           "openrouter": "openrouter", "openrouter free": "openrouter", "ollama": "ollama"}
PROVIDER_NAMES = {"google": "Google Gemini", "groq": "Groq", "cloudflare": "Cloudflare Workers AI", "openrouter": "OpenRouter", "ollama": "Ollama"}
FREE_MODELS = {
    "google": {"gemini-3.8-flash", "gemini-3.6-flash"},
    "groq": {"openai/gpt-oss-20b", "openai/gpt-oss-120b"},
    "cloudflare": {"@cf/zai-org/glm-4.7-flash", "@cf/google/gemma-4-26b-a4b-it", "@cf/nvidia/nemotron-3-120b"},
}


def canonical_provider(value: str) -> str | None:
    return ALIASES.get(value.strip().casefold())


def _local_ollama(url: str | None) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").casefold()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def configured_providers(config: Config, requested: str = "Auto") -> list[str]:
    """Return enabled providers in priority order, enforcing free-only eligibility."""
    explicit = canonical_provider(requested) if requested.casefold() not in {"auto", "automatic"} else None
    configured = {
        "google": bool(getattr(config, "google_api_key", None)),
        "groq": bool(getattr(config, "groq_api_key", None)),
        "cloudflare": bool(getattr(config, "cloudflare_account_id", None) and getattr(config, "cloudflare_api_token", None)),
        "openrouter": bool(getattr(config, "openrouter_api_key", None)),
        "ollama": bool(getattr(config, "ollama_base_url", None)),
    }
    model_for = {"google": getattr(config, "google_model", "gemini-3.8-flash"), "groq": getattr(config, "groq_smart_model", "openai/gpt-oss-120b"),
                 "cloudflare": getattr(config, "cloudflare_model", "@cf/zai-org/glm-4.7-flash"), "openrouter": getattr(config, "openrouter_model", "openrouter/free"),
                 "ollama": getattr(config, "ollama_model", "llama3.2")}
    confirmed = {"google": getattr(config, "gemini_free_tier_confirmed", False), "groq": getattr(config, "groq_free_tier_confirmed", False),
                 "cloudflare": getattr(config, "cloudflare_free_plan_confirmed", False), "openrouter": True, "ollama": True}
    raw_order = [canonical_provider(p) for p in getattr(config, "provider_priority", ("gemini", "groq", "cloudflare", "openrouter", "ollama"))]
    order = list(dict.fromkeys(p for p in raw_order if p))
    enabled = {canonical_provider(p) for p in getattr(config, "enabled_providers", ("gemini", "groq", "cloudflare", "openrouter", "ollama"))}
    eligible = []
    for provider in order:
        if provider not in enabled or not configured.get(provider):
            continue
        if getattr(config, "free_only", False):
            if not confirmed.get(provider, False):
                continue
            model = model_for[provider]
            if provider in FREE_MODELS and model not in FREE_MODELS[provider]:
                continue
            if provider == "openrouter" and model != "openrouter/free":
                continue
            if provider == "ollama" and not _local_ollama(getattr(config, "ollama_base_url", None)):
                continue
        eligible.append(provider)
    if explicit:
        return ([explicit] if explicit in eligible else []) + [provider for provider in eligible if provider != explicit]
    return eligible


def default_model(provider: str, config: Config, *, model_tier: str | None = "Fast", route_key: str = "general") -> str:
    if provider == "google":
        return config.google_model
    if provider == "groq":
        smart = model_tier == "Smart" or (model_tier is None and route_key in {"agent2", "math", "research", "code"})
        return config.groq_smart_model if smart else config.groq_fast_model
    if provider == "cloudflare":
        return config.cloudflare_model
    if provider == "openrouter":
        return "openrouter/free" if config.free_only else config.openrouter_model
    if provider == "ollama":
        return config.ollama_model
    raise ValueError("Unknown provider")


@dataclass
class ProviderHealth:
    state: str = "ready"
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    quota_errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_latency_ms: float | None = None
    last_status_code: int | None = None
    last_error_type: str | None = None
    cooldown_until: float = 0.0
    failure_streak: int = 0
    last_served_at: float | None = None


class ProviderHealthRegistry:
    """In-process circuit breaker and aggregate metrics; never stores prompts or keys."""

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._health: dict[str, ProviderHealth] = {}
        self._last_served_provider: str | None = None

    def available(self, providers: list[str]) -> list[str]:
        now = self._clock()
        with self._lock:
            return [p for p in providers if self._health.get(p, ProviderHealth()).cooldown_until <= now]

    def begin(self, provider: str) -> float:
        with self._lock:
            row = self._health.setdefault(provider, ProviderHealth())
            row.attempts += 1
            row.state = "running"
        return self._clock()

    def success(self, provider: str, started: float, usage: dict[str, Any] | None = None) -> None:
        with self._lock:
            row = self._health.setdefault(provider, ProviderHealth())
            row.successes += 1
            row.failure_streak = 0
            row.cooldown_until = 0
            row.state = "ready"
            row.last_error_type = None
            row.last_latency_ms = round((self._clock() - started) * 1000, 1)
            row.last_served_at = time.time()
            self._last_served_provider = provider
            if usage:
                row.input_tokens += int(usage.get("input_tokens", usage.get("input", 0)) or 0)
                row.output_tokens += int(usage.get("output_tokens", usage.get("output", 0)) or 0)

    def skipped(self, provider: str, started: float, reason: str) -> None:
        with self._lock:
            row = self._health.setdefault(provider, ProviderHealth())
            row.state = "ready"
            row.last_latency_ms = round((self._clock() - started) * 1000, 1)
            row.last_error_type = reason

    def failure(self, provider: str, started: float, exc: Exception, *, status: int | None, retry_after: float | None = None) -> None:
        with self._lock:
            row = self._health.setdefault(provider, ProviderHealth())
            row.failures += 1
            row.failure_streak += 1
            row.last_latency_ms = round((self._clock() - started) * 1000, 1)
            row.last_status_code = status
            row.last_error_type = type(exc).__name__
            if status == 429:
                row.quota_errors += 1
            auth_error = status in {401, 403}
            if auth_error:
                cooldown = 900.0
                row.state = "credentials" if status == 401 else "unavailable"
            else:
                exponential = min(120.0, 5.0 * (2 ** min(row.failure_streak - 1, 5)))
                cooldown = max(exponential, retry_after or 0.0)
                row.state = "cooldown"
            row.cooldown_until = self._clock() + cooldown

    def snapshot(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            result = {}
            for provider, row in self._health.items():
                state = row.state
                if row.cooldown_until and row.cooldown_until <= now:
                    state = "ready"
                result[PROVIDER_NAMES.get(provider, provider)] = {
                    "state": state,
                    "attempts": row.attempts,
                    "successes": row.successes,
                    "failures": row.failures,
                    "quota_errors": row.quota_errors,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "last_latency_ms": row.last_latency_ms,
                    "last_status_code": row.last_status_code,
                    "last_error_type": row.last_error_type,
                    "cooldown_seconds": max(0, round(row.cooldown_until - now)),
                    "last_served_at": row.last_served_at,
                }
            return result

    def last_served_provider(self) -> str | None:
        with self._lock:
            return PROVIDER_NAMES.get(self._last_served_provider, self._last_served_provider)

    def reset(self) -> None:
        with self._lock:
            self._health.clear()
            self._last_served_provider = None


provider_health = ProviderHealthRegistry()


def error_details(exc: Exception) -> tuple[int | None, float | None]:
    response = getattr(exc, "response", None)
    status = (getattr(exc, "status_code", None) or getattr(response, "status_code", None)
              or getattr(exc, "http_status", None))
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    headers = getattr(exc, "headers", None) or getattr(response, "headers", None) or {}
    retry = None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value is not None:
            try:
                retry = float(value)
            except (TypeError, ValueError):
                moment = parsedate_to_datetime(str(value))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                retry = (moment - datetime.now(timezone.utc)).total_seconds()
                retry = max(0.0, min(86400.0, retry))
    except (TypeError, ValueError):
        pass
    return status, retry


def should_failover(exc: Exception) -> bool:
    status, _ = error_details(exc)
    if status is not None:
        return status in {401, 402, 403, 404, 408, 425, 429, 500, 502, 503, 504}
    # Safety refusals are successful text responses. A non-HTTP exception is
    # treated as a connection/provider failure and is safe to fail over.
    return True
