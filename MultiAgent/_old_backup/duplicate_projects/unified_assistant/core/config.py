"""Environment-backed application configuration."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY") or None
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    groq_fast_model: str = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
    groq_smart_model: str = os.getenv("GROQ_SMART_MODEL", "openai/gpt-oss-120b")

    def missing_key_message(self, agent: str) -> str | None:
        if agent in {"math", "writing"} and not self.google_api_key:
            return "The Google Gemini key is missing. Add GOOGLE_API_KEY to your .env file."
        if agent in {"general", "agent1", "agent2"} and not self.groq_api_key:
            return "The Groq key is missing. Add GROQ_API_KEY to your .env file."
        return None
