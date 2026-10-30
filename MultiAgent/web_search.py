"""Server-side web search providers and a guarded public-page reader."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import gzip
from html.parser import HTMLParser
import ipaddress
import json
import logging
import os
import re
import socket
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 4
MAX_PAGE_BYTES = 1_000_000
MAX_PAGE_CHARS = 8_000
MAX_RESULTS = 10
MAX_SEARCHES_PER_TASK = 5
CACHE_TTL_SECONDS = 300
_search_cache: dict[tuple[str, str], tuple[float, list[dict[str, str]]]] = {}
_page_cache: dict[str, tuple[float, str]] = {}

_PRIVATE_QUERY = re.compile(
    r"\b(my|me|mine|our|ours|internal|private|personal|"
    r"applicant|recruitment|previous decision|what did i|what do i prefer|my history|"
    r"current office holders|logistics lead|undocumented|confidential)\b", re.I,
)
_SENSITIVE_QUERY = re.compile(r"\b(api key|password|passphrase|access token|secret|credential|my email|my phone|my address|account number|social security)\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)
_SOCIAPI_INTERNAL = re.compile(
    r"(?:\bsociapi(?: society)?\b.{0,120}\b(founder|founded|members?|team|decision|preference|history|role|recruit|internal)\b|\b(founder|founded|members?|team|decision|preference|history|role|recruit|internal)\b.{0,120}\bsociapi\b)",
    re.I,
)
_CURRENT = re.compile(r"\b(latest|newest|current|currently|today|now|right now|this week|this month|recent|versions?|prices?|weather|news|score|schedule|date|dates|as of)\b", re.I)
_RESEARCH = re.compile(r"\b(search|google|look up|verify|fact.check|source|research|compare|citation|cite)\b", re.I)
_GREETINGS = re.compile(r"^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you|bye)[!.? ]*$", re.I)
_MATH = re.compile(r"^(?:what is |calculate |compute )?\s*-?\d+(?:\.\d+)?\s*(?:[+*/%]|\btimes\b|\bminus\b|\bplus\b|\bdivided by\b)\s*-?\d+(?:\.\d+)?\s*[?!. ]*$", re.I)
_CODE_ONLY = re.compile(r"\b(create|make|build|generate|debug|write|fix|explain|review|refactor)\b.*\b(code|python|javascript|typescript|function|class|script|regex|algorithm|program|website|web\s*app|web\s*page|html|application|app|calculator)\b", re.I)


@dataclass
class _TaskState:
    searches: int = 0
    query_cache: dict[tuple[str, str], list[dict[str, str]]] = field(default_factory=dict)
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    last_provider: str | None = None
    last_error: str | None = None
    last_query: str | None = None
    result_urls: set[str] = field(default_factory=set)


from contextvars import ContextVar
_task_state: ContextVar[_TaskState | None] = ContextVar("web_search_task", default=None)
_selected_provider: ContextVar[str | None] = ContextVar("web_search_provider", default=None)
_progress_callback: ContextVar[Any | None] = ContextVar("web_search_progress", default=None)
_current_user_query: ContextVar[str | None] = ContextVar("web_search_current_query", default=None)


def reset_search_task() -> None:
    """Start fresh search accounting for the current async request."""
    _task_state.set(_TaskState())
    _current_user_query.set(None)


def get_task_sources() -> list[dict[str, str]]:
    return list(_state().sources.values())


def is_time_sensitive_query(query: str) -> bool:
    return bool(_CURRENT.search(query))


def last_search_status() -> tuple[str | None, str | None, str | None]:
    state = _state()
    return state.last_provider, state.last_error, state.last_query


_SOURCE_DATE = re.compile(
    r"\b(?:release date|published(?: on)?|last updated|date)\s*[:\-]?\s*((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[.,]?\s+\d{1,2},?\s+20\d{2}|20\d{2}-\d{2}-\d{2})",
    re.I,
)


def _source_date(text: str) -> str:
    match = _SOURCE_DATE.search(text[:MAX_PAGE_CHARS])
    if match:
        return match.group(1).strip()
    release_date = re.search(
        r"\b(?:Python\s+)?\d+\.\d+\.\d+\s+((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[.,]?\s+\d{1,2},?\s+20\d{2})",
        text[:MAX_PAGE_CHARS], re.I,
    )
    return release_date.group(1).strip() if release_date else ""


def _record_page_source(url: str, content: str = "") -> None:
    parsed = urlparse(url)
    state = _state()
    metadata = next((item for results in state.query_cache.values() for item in results if item.get("url") == url), None)
    source = dict(metadata or {"title": parsed.hostname or "Web page", "url": url, "snippet": "", "date": "", "domain": parsed.hostname or ""})
    if content and not source.get("date"):
        source["date"] = _source_date(content)
    state.sources.setdefault(url, source)


def set_search_provider(provider: str | None) -> None:
    """Bind the saved UI provider choice to this request and its tool calls."""
    _selected_provider.set(provider)


def set_search_user_query(query: str) -> None:
    """Limit tool-generated search refinements to the current user message."""
    _current_user_query.set(query[:500])


def set_search_progress(callback) -> None:
    _progress_callback.set(callback)


async def _report_progress(message: str) -> None:
    callback = _progress_callback.get()
    if callback:
        await callback(message)


def _state() -> _TaskState:
    state = _task_state.get()
    if state is None:
        state = _TaskState()
        _task_state.set(state)
    return state


def should_search(query: str, excerpts: list[dict[str, Any]], mode: str = "Auto") -> bool:
    """Decide whether a public query is appropriate using only the current message."""
    if not query.strip() or mode.casefold() == "off" or _PRIVATE_QUERY.search(query) or _SENSITIVE_QUERY.search(query) or _SOCIAPI_INTERNAL.search(query):
        return False
    if mode.casefold() == "always":
        return bool(query.strip())
    if _GREETINGS.fullmatch(query.strip()) or _MATH.fullmatch(query.strip()) or _CODE_ONLY.search(query):
        return False
    if _CURRENT.search(query) or _RESEARCH.search(query):
        return True
    if not excerpts:
        return True
    if any(re.search(r"\b(uncertain|historical|may have changed|unconfirmed|draft|not established)\b", str(item.get("text", "")), re.I) for item in excerpts):
        return True
    return max((float(item.get("score", 0) or 0) for item in excerpts), default=0) < 1.0


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Accept": "application/json", **headers}, method="POST")
    with build_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read(1_000_000))


def _serper_search_sync(query: str, number_results: int, api_key: str) -> list[dict[str, str]]:
    data = _http_json("https://google.serper.dev/search", {"q": query[:500], "num": number_results}, {"X-API-KEY": api_key})
    items = data.get("organic", [])
    return [_normalize(item.get("title"), item.get("link"), item.get("snippet"), item.get("date")) for item in items]


def _tavily_search_sync(query: str, number_results: int, api_key: str) -> list[dict[str, str]]:
    data = _http_json("https://api.tavily.com/search", {"api_key": api_key, "query": query[:500], "max_results": number_results, "search_depth": "basic", "include_answer": False}, {})
    items = data.get("results", [])
    return [_normalize(item.get("title"), item.get("url"), item.get("content"), item.get("published_date")) for item in items]


def _ddg_search_sync(query: str, number_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS
    with DDGS(timeout=TIMEOUT_SECONDS) as ddgs:
        items = list(ddgs.text(query[:500], max_results=number_results))
    return [_normalize(item.get("title"), item.get("href") or item.get("url"), item.get("body") or item.get("snippet"), item.get("date")) for item in items]


def _normalize(title: Any, url: Any, snippet: Any, date: Any = None) -> dict[str, str]:
    link = str(url or "").strip()
    parsed = urlparse(link)
    if parsed.scheme != "https" or not parsed.hostname:
        return {}
    return {"title": str(title or "")[:300], "url": link[:2000], "snippet": str(snippet or "")[:1200], "date": str(date or "")[:100], "domain": parsed.hostname}


def _clean_results(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    result = []
    seen = set()
    for item in items:
        if not item or item["url"] in seen:
            continue
        seen.add(item["url"])
        result.append(item)
        if len(result) >= limit:
            break
    def authority(item: dict[str, str]) -> tuple[int, int]:
        host = item.get("domain", "").casefold()
        title = item.get("title", "").casefold()
        if host.endswith((".gov", ".gov.uk", ".gov.pk", ".edu", ".edu.pk")):
            return 0, 0
        if host == "python.org" or host.endswith(".python.org"):
            return 0, 0 if "release" in title else 1
        if host.startswith(("docs.", "developers.", "support.")):
            return 1, 0
        return 2, 0
    return sorted(result, key=authority)


async def _provider_search(provider: str, query: str, count: int) -> list[dict[str, str]]:
    if provider == "Serper":
        key = os.getenv("SERPER_API_KEY", "").strip()
        if not key:
            _state().last_error = "provider not configured"
            logger.warning("Web search provider failed provider=%s query=%r results=0 error=not_configured", provider, query)
            return []
        call = _serper_search_sync
        args = (query, count, key)
    elif provider == "Tavily":
        key = os.getenv("TAVILY_API_KEY", "").strip()
        if not key:
            _state().last_error = "provider not configured"
            logger.warning("Web search provider failed provider=%s query=%r results=0 error=not_configured", provider, query)
            return []
        call = _tavily_search_sync
        args = (query, count, key)
    else:
        call = _ddg_search_sync
        args = (query, count)
    try:
        results = await asyncio.wait_for(asyncio.to_thread(call, *args), timeout=TIMEOUT_SECONDS + 1)
        _state().last_error = None if results else "no results"
        logger.info("Web search provider finished provider=%s query=%r results=%d error=%s", provider, query, len(results), "none" if results else "no_results")
        return results
    except Exception as exc:
        _state().last_error = type(exc).__name__
        logger.warning("Web search provider failed provider=%s query=%r results=0 error=%s", provider, query, type(exc).__name__)
        return []


def _provider_order(preference: str | None) -> list[str]:
    selected = (preference or os.getenv("WEB_SEARCH_PROVIDER", "DuckDuckGo")).strip().casefold()
    if selected in {"duckduckgo", "duck duck go", "ddg"}:
        return ["DuckDuckGo"]
    if selected == "tavily":
        return ["Tavily", "DuckDuckGo"]
    if selected == "serper":
        return ["Serper", "DuckDuckGo"]
    return ["DuckDuckGo"]


async def web_search(query: str, number_results: int = 5, provider: str | None = None) -> list[dict[str, str]]:
    """Search public web pages; only the explicit query is sent to a provider."""
    query = query.strip()[:500]
    original_query = _current_user_query.get()
    if original_query is not None and query.casefold() != original_query.casefold():
        if _PRIVATE_QUERY.search(query) or _SENSITIVE_QUERY.search(query) or _SOCIAPI_INTERNAL.search(query):
            return []
        original_terms = {term.casefold() for term in re.findall(r"[\w.-]{2,}", original_query)}
        allowed_refinements = {"search", "web", "official", "docs", "documentation", "source", "sources", "latest", "current", "version", "compare", "review", "reviews", "research", "news", "2026"}
        terms = [term for term in re.findall(r"[\w.-]{2,}", query) if term.casefold() in original_terms | allowed_refinements]
        query = " ".join(terms)[:500] if len(terms) >= 2 else original_query
    if not query or _PRIVATE_QUERY.search(query) or _SENSITIVE_QUERY.search(query) or _SOCIAPI_INTERNAL.search(query):
        return []
    await _report_progress("Searching the web")
    count = max(1, min(int(number_results), MAX_RESULTS))
    state = _state()
    state.last_query = query
    state.last_provider = None
    state.last_error = None
    logger.info("Tool call started tool=web_search query=%r number_results=%d", query, count)
    volatile = is_time_sensitive_query(query)
    # Volatile facts always bypass caches so current results cannot silently age out.
    provider = provider or _selected_provider.get()
    for preferred in _provider_order(provider):
        cache_key = (preferred, query.casefold())
        if not volatile and cache_key in state.query_cache:
            state.last_provider = preferred
            cached_results = state.query_cache[cache_key][:count]
            state.result_urls.update(item["url"] for item in cached_results)
            logger.info("Tool call completed tool=web_search query=%r provider=%s results=%d error=none source=task_cache", query, preferred, len(cached_results))
            return cached_results
        cached = _search_cache.get(cache_key)
        if not volatile and cached and asyncio.get_running_loop().time() - cached[0] < CACHE_TTL_SECONDS:
            state.query_cache[cache_key] = cached[1]
            state.last_provider = preferred
            cached_results = cached[1][:count]
            state.result_urls.update(item["url"] for item in cached_results)
            logger.info("Tool call completed tool=web_search query=%r provider=%s results=%d error=none source=cache", query, preferred, len(cached_results))
            return cached_results
    if state.searches >= MAX_SEARCHES_PER_TASK:
        state.last_error = "search limit reached"
        logger.warning("Tool call completed tool=web_search query=%r provider=none results=0 error=search_limit", query)
        return []
    state.searches += 1
    for chosen in _provider_order(provider):
        results = _clean_results(await _provider_search(chosen, query, count), count)
        if results:
            state.last_provider = chosen
            key = (chosen, query.casefold())
            state.query_cache[key] = results
            state.result_urls.update(item["url"] for item in results)
            if not volatile:
                _search_cache[key] = (asyncio.get_running_loop().time(), results)
            logger.info("Tool call completed tool=web_search query=%r provider=%s results=%d error=none", query, chosen, len(results))
            return results
        # A missing/failing main API automatically falls back to DuckDuckGo.
    logger.warning("Tool call completed tool=web_search query=%r provider=none results=0 error=%s", query, state.last_error or "unavailable")
    return []


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Please provide a public HTTPS page URL.")
    if parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS pages on the standard port can be opened.")
    if any(re.search(r"(key|token|auth|password|secret|credential)", name, re.I) for name, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("URLs containing credentials or access tokens cannot be opened.")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and private addresses cannot be opened.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise ValueError("That public page address could not be verified.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Local and private addresses cannot be opened.")
    return url


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "header", "iframe", "form"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "header", "iframe", "form"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def _read_page_sync(url: str) -> str:
    url = _validate_public_url(url)
    request = Request(url, headers={"User-Agent": "SociapiAssistant/1.0", "Accept": "text/html,text/plain,application/xhtml+xml"})
    with build_opener(_SafeRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        _validate_public_url(final_url)
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise ValueError("That page is not readable HTML or text.")
        payload = response.read(MAX_PAGE_BYTES + 1)
        content_encoding = (response.headers.get("Content-Encoding") or "").casefold()
    if len(payload) > MAX_PAGE_BYTES:
        payload = payload[:MAX_PAGE_BYTES]
    try:
        if content_encoding == "gzip":
            with gzip.GzipFile(fileobj=BytesIO(payload)) as compressed:
                payload = compressed.read(MAX_PAGE_BYTES + 1)
        elif content_encoding == "deflate":
            payload = zlib.decompressobj().decompress(payload, MAX_PAGE_BYTES + 1)
        elif content_encoding not in {"", "identity"}:
            raise ValueError("The page uses an unsupported compression format.")
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("The page content could not be decoded safely.") from exc
    if len(payload) > MAX_PAGE_BYTES:
        payload = payload[:MAX_PAGE_BYTES]
    if content_type == "text/plain":
        return " ".join(payload.decode("utf-8", errors="replace").split())[:MAX_PAGE_CHARS]
    parser = _PageText()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return " ".join(parser.parts)[:MAX_PAGE_CHARS]


async def read_page(url: str) -> str:
    """Extract bounded, readable text from a public HTTPS page."""
    await _report_progress("Reading a web page")
    state = _state()
    if _current_user_query.get() is not None and url not in state.result_urls:
        raise ValueError("Only URLs returned by web search can be opened for this request.")
    try:
        url = await asyncio.wait_for(asyncio.to_thread(_validate_public_url, url), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        logger.warning("Tool call failed tool=read_page error=address_verification_timeout")
        raise ValueError("The page address took too long to verify.") from exc
    except ValueError as exc:
        logger.warning("Tool call failed tool=read_page error=%s", type(exc).__name__)
        raise
    cached = _page_cache.get(url)
    now = asyncio.get_running_loop().time()
    volatile = is_time_sensitive_query(_current_user_query.get() or "")
    if not volatile and cached and now - cached[0] < CACHE_TTL_SECONDS:
        if cached[1]:
            _record_page_source(url, cached[1])
        logger.info("Tool call completed tool=read_page url=%s characters=%d source=cache error=none", url, len(cached[1]))
        return cached[1]
    try:
        content = await asyncio.wait_for(asyncio.to_thread(_read_page_sync, url), timeout=TIMEOUT_SECONDS + 2)
    except asyncio.TimeoutError as exc:
        logger.warning("Tool call failed tool=read_page url=%s error=timeout", url)
        raise ValueError("The page took too long to respond. Try another source.") from exc
    except ValueError as exc:
        logger.warning("Tool call failed tool=read_page url=%s error=%s", url, type(exc).__name__)
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.info("Page read failed (type=%s)", type(exc).__name__)
        logger.warning("Tool call failed tool=read_page url=%s error=%s", url, type(exc).__name__)
        raise ValueError("That page could not be opened. Try another source.") from exc
    if not volatile:
        _page_cache[url] = (now, content)
    if content:
        _record_page_source(url, content)
    logger.info("Tool call completed tool=read_page url=%s characters=%d source=live error=none", url, len(content))
    return content


async def google_search(query: str, *, api_key: str | None = None, engine_id: str | None = None) -> list[dict[str, str]]:
    """Legacy name kept for compatibility; the configured provider is used."""
    return await web_search(query)


async def search_if_needed(query: str, excerpts: list[dict[str, Any]], mode: str = "Auto", provider: str | None = None, progress=None) -> list[dict[str, str]]:
    """Apply local-first policy, then search and open up to three public results."""
    if not should_search(query, excerpts, mode):
        reason = "mode_off" if mode.casefold() == "off" else "private_or_sensitive" if _PRIVATE_QUERY.search(query) or _SENSITIVE_QUERY.search(query) or _SOCIAPI_INTERNAL.search(query) else "not_needed"
        logger.info("Web search skipped mode=%s reason=%s", mode, reason)
        return []
    if progress:
        set_search_progress(progress)
    results = await web_search(query, 5, provider)
    if not results:
        logger.warning("Web research completed query=%r provider=%s verified_pages=0 error=search_unavailable", query, _state().last_provider or "none")
        return []
    best = results[:3]
    if progress:
        await progress(f"Reading {len(best)} pages")
    state = _state()
    state.result_urls.update(item["url"] for item in best)
    opened = await asyncio.gather(*(read_page(item["url"]) for item in best), return_exceptions=True)
    verified = []
    for item, content in zip(best, opened):
        if isinstance(content, str) and content:
            verified.append({**item, "content": content})
    if not verified and _provider_order(provider)[0] != "DuckDuckGo":
        logger.warning("Search pages were unreadable; retrying fallback provider query=%r provider=DuckDuckGo", query)
        fallback_results = await web_search(query, 5, "DuckDuckGo")
        state.result_urls.update(item["url"] for item in fallback_results)
        fallback_opened = await asyncio.gather(*(read_page(item["url"]) for item in fallback_results[:3]), return_exceptions=True)
        verified = [
            {**item, "content": content}
            for item, content in zip(fallback_results[:3], fallback_opened)
            if isinstance(content, str) and content
        ]
    logger.info(
        "Web research completed query=%r provider=%s verified_pages=%d error=%s",
        query,
        _state().last_provider or "none",
        len(verified),
        "none" if verified else "pages_unavailable",
    )
    return verified


def format_search_context(results: list[dict[str, str]]) -> str:
    blocks = []
    for item in results:
        body = item.get("content") or item.get("snippet", "")
        if body:
            source_date = f"\nDate: {item['date']}" if item.get("date") else ""
            blocks.append(f"Title: {item.get('title', '')}{source_date}\nURL: {item.get('url', '')}\nUntrusted page text: {body}")
    return "\n\n---\n\n".join(blocks)
