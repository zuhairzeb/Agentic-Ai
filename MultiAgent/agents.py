"""Lazy construction of Google Gemini and Groq chat models."""

from config import Config
from router import Route


class AgentFactory:
    def __init__(self, config: Config = Config()):
        self.config = config

    def create(
        self,
        route: Route,
        provider: str | None = None,
        model_tier: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ):
        provider = provider or ("google" if route.key in {"math", "writing", "research"} else "groq")
        missing = (
            "The Google Gemini key is missing. Add GOOGLE_API_KEY to this project's .env file."
            if provider == "google" and not self.config.google_api_key else
            "The Groq key is missing. Add GROQ_API_KEY to this project's .env file."
            if provider == "groq" and not self.config.groq_api_key else None
        )
        if missing:
            raise RuntimeError(missing)
        try:
            if provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=model_name or self.config.google_model,
                    google_api_key=self.config.google_api_key,
                    temperature=temperature if temperature is not None else (0.2 if route.key == "math" else 0.7),
                    timeout=15,
                    max_retries=1,
                )

            from langchain_groq import ChatGroq
            use_smart = model_tier == "Smart" or (model_tier is None and route.key in {"agent2", "math", "research"})
            model = model_name or (self.config.groq_smart_model if use_smart else self.config.groq_fast_model)
            return ChatGroq(model=model, api_key=self.config.groq_api_key, temperature=temperature if temperature is not None else 0.4, timeout=30, max_retries=1)
        except ImportError as exc:
            package = "langchain-google-genai" if route.key in {"math", "writing", "research"} else "langchain-groq"
            raise RuntimeError(f"Missing provider integration. Install {package} from requirements.txt.") from exc
