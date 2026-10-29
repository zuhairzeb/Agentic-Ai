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


@dataclass(frozen=True)
class Config:
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY") or None
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-3.8-flash")
    groq_fast_model: str = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
    groq_smart_model: str = os.getenv("GROQ_SMART_MODEL", "openai/gpt-oss-120b")
    database_path: Path = PROJECT_DIR / os.getenv("APP_DATABASE", "data/assistant.sqlite3")

    def missing_key_message(self, agent: str) -> str | None:
        if agent in {"math", "writing", "research"} and not self.google_api_key:
            return "The Google Gemini key is missing. Add GOOGLE_API_KEY to this project's .env file."
        if agent in {"general", "agent1", "agent2"} and not self.groq_api_key:
            return "The Groq key is missing. Add GROQ_API_KEY to this project's .env file."
        return None


@dataclass(frozen=True)
class Branding:
    """Single source for the app-controlled UI identity."""

    name: str = os.getenv("APP_NAME") or os.getenv("APP_GREETING_NAME") or "AI Assistant"
    greeting_name: str | None = os.getenv("APP_GREETING_NAME") or None
    tagline: str = os.getenv("APP_TAGLINE", "A clear place to think, write, and build.")
    logo: str | None = os.getenv("APP_LOGO") or None
    favicon: str | None = os.getenv("APP_FAVICON") or None
    description: str = os.getenv(
        "APP_DESCRIPTION", "A private, multi-agent assistant for writing, math, research, and general questions."
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
