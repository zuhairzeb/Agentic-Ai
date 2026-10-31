"""Branding and provider configuration loaded from this project's .env."""

import os
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().casefold() in {"1", "true", "yes", "on"}


def _provider_list(name: str, default: str) -> tuple[str, ...]:
    values = os.getenv(name, default)
    return tuple(item.strip().casefold() for item in values.split(",") if item.strip())


def _max_output_tokens() -> int:
    try:
        value = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "8192"))
    except ValueError:
        value = 8192
    return max(256, min(value, 32768))


@dataclass(frozen=True)
class Config:
    google_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    google_model: str = os.getenv("GEMINI_MODEL") or os.getenv("GOOGLE_MODEL", "gemini-3.8-flash")
    groq_fast_model: str = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
    groq_smart_model: str = os.getenv("GROQ_SMART_MODEL", "openai/gpt-oss-120b")
    cloudflare_account_id: str | None = os.getenv("CLOUDFLARE_ACCOUNT_ID") or None
    cloudflare_api_token: str | None = os.getenv("CLOUDFLARE_API_TOKEN") or None
    cloudflare_model: str = os.getenv("CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY") or None
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    ollama_base_url: str | None = os.getenv("OLLAMA_BASE_URL") or None
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    max_output_tokens: int = _max_output_tokens()
    free_only: bool = _env_bool("FREE_ONLY", False)
    gemini_free_tier_confirmed: bool = _env_bool("GEMINI_FREE_TIER_CONFIRMED")
    groq_free_tier_confirmed: bool = _env_bool("GROQ_FREE_TIER_CONFIRMED")
    cloudflare_free_plan_confirmed: bool = _env_bool("CLOUDFLARE_FREE_PLAN_CONFIRMED")
    enabled_providers: tuple[str, ...] = _provider_list(
        "LLM_ENABLED_PROVIDERS", "gemini,groq,cloudflare,openrouter,ollama"
    )
    provider_priority: tuple[str, ...] = _provider_list(
        "LLM_PROVIDER_PRIORITY", "gemini,groq,cloudflare,openrouter,ollama"
    )
    database_path: Path = PROJECT_DIR / os.getenv("APP_DATABASE", "data/assistant.sqlite3")

    def missing_key_message(self, agent: str) -> str | None:
        if agent in {"math", "writing", "research"} and not self.google_api_key:
            return "The Google Gemini key is missing. Add GEMINI_API_KEY (or legacy GOOGLE_API_KEY) to this project's .env file."
        if agent in {"general", "agent1", "agent2"} and not self.groq_api_key:
            return "The Groq key is missing. Add GROQ_API_KEY to this project's .env file."
        return None


@dataclass(frozen=True)
class Branding:
    """Single source for the app-controlled UI identity."""

    name: str = os.getenv("APP_NAME") or os.getenv("APP_GREETING_NAME") or "Morrow"
    greeting_name: str | None = os.getenv("APP_GREETING_NAME") or None
    tagline: str = os.getenv("APP_TAGLINE", "What are we working on?")
    logo: str | None = os.getenv("APP_LOGO") or None
    favicon: str | None = os.getenv("APP_FAVICON") or None
    description: str = os.getenv(
        "APP_DESCRIPTION", "A local workspace for questions, research, writing, and interactive builds."
    )


BRANDING = Branding()


def apply_branding() -> None:
    """Apply centralized branding to Chainlit before it serves the frontend."""
    from chainlit.config import config as chainlit_config

    chainlit_config.ui.name = BRANDING.name
    chainlit_config.ui.description = BRANDING.description
    chainlit_config.ui.custom_css = "/public/style.css"
    chainlit_config.ui.login_page_image = "/public/login.svg"

    public_dir = PROJECT_DIR / "public"
    public_dir.mkdir(exist_ok=True)
    if BRANDING.logo:
        source = Path(BRANDING.logo).expanduser()
        if source.is_file() and source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            for destination in (public_dir / "logo_dark.png", public_dir / "logo_light.png"):
                if source.resolve() != destination.resolve():
                    shutil.copyfile(source, destination)
        else:
            logger.warning("APP_LOGO must point to an existing PNG, JPG, or WEBP file")
    if BRANDING.favicon:
        source = Path(BRANDING.favicon).expanduser()
        if source.is_file() and source.suffix.lower() in {".svg", ".png", ".ico"}:
            fallback = public_dir / "favicon.svg"
            destination = public_dir / f"favicon{source.suffix.lower()}"
            same_source = source.resolve() == destination.resolve()
            if fallback.exists() and not same_source:
                fallback.unlink()
            if not same_source:
                shutil.copyfile(source, destination)
        else:
            logger.warning("APP_FAVICON must point to an existing SVG, PNG, or ICO file")
