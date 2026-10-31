"""Lazy construction of normalized chat models for configured providers."""

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
        provider = (provider or ("google" if route.key in {"math", "writing", "research"} else "groq")).casefold()
        if provider == "gemini":
            provider = "google"
        missing = (
            "The Google Gemini key is missing. Add GEMINI_API_KEY (or legacy GOOGLE_API_KEY) to this project's .env file."
            if provider == "google" and not self.config.google_api_key else
            "The Groq key is missing. Add GROQ_API_KEY to this project's .env file."
            if provider == "groq" and not self.config.groq_api_key else
            "Cloudflare Workers AI needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN."
            if provider == "cloudflare" and not (self.config.cloudflare_account_id and self.config.cloudflare_api_token) else
            "OpenRouter needs OPENROUTER_API_KEY."
            if provider == "openrouter" and not self.config.openrouter_api_key else
            "Set OLLAMA_BASE_URL to a reachable Ollama OpenAI-compatible endpoint."
            if provider == "ollama" and not self.config.ollama_base_url else None
        )
        if missing:
            raise RuntimeError(missing)
        if self.config.free_only:
            selected_model = model_name
            if provider == "google":
                selected_model = selected_model or self.config.google_model
            elif provider == "groq":
                use_smart = model_tier == "Smart" or (model_tier is None and route.key in {"agent2", "math", "research", "code"})
                selected_model = selected_model or (self.config.groq_smart_model if use_smart else self.config.groq_fast_model)
            if provider in {"google", "groq"}:
                from provider_router import FREE_MODELS
                if selected_model not in FREE_MODELS[provider]:
                    raise RuntimeError("The selected model is not eligible for FREE_ONLY mode.")
        try:
            if provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=model_name or self.config.google_model,
                    google_api_key=self.config.google_api_key,
                    temperature=temperature if temperature is not None else (0.2 if route.key == "math" else 0.7),
                    timeout=15,
                    max_output_tokens=self.config.max_output_tokens,
                    max_retries=0,
                )

            if provider == "groq":
                from langchain_groq import ChatGroq
                use_smart = model_tier == "Smart" or (model_tier is None and route.key in {"agent2", "math", "research"})
                model = model_name or (self.config.groq_smart_model if use_smart else self.config.groq_fast_model)
                return ChatGroq(model=model, api_key=self.config.groq_api_key, temperature=temperature if temperature is not None else 0.4, timeout=30, max_tokens=self.config.max_output_tokens, max_retries=0)

            from langchain_openai import ChatOpenAI
            use_smart = model_tier == "Smart" or (model_tier is None and route.key in {"agent2", "math", "research"})
            if provider == "cloudflare":
                model = model_name or self.config.cloudflare_model
                if self.config.free_only and model not in {
                    "@cf/zai-org/glm-4.7-flash", "@cf/google/gemma-4-26b-a4b-it", "@cf/nvidia/nemotron-3-120b"
                }:
                    raise RuntimeError("That Cloudflare model is not enabled for FREE_ONLY mode.")
                return ChatOpenAI(
                    model=model, api_key=self.config.cloudflare_api_token,
                    base_url=f"https://api.cloudflare.com/client/v4/accounts/{self.config.cloudflare_account_id}/ai/v1",
                    temperature=temperature if temperature is not None else 0.4, timeout=30, max_tokens=self.config.max_output_tokens, max_retries=0,
                )
            if provider == "openrouter":
                model = "openrouter/free" if self.config.free_only else (model_name or self.config.openrouter_model)
                if self.config.free_only and model != "openrouter/free":
                    raise RuntimeError("FREE_ONLY mode only permits the openrouter/free model router.")
                return ChatOpenAI(
                    model=model, api_key=self.config.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_headers={"HTTP-Referer": "https://sociapis.vercel.app", "X-Title": "Sociapi Assistant"},
                    temperature=temperature if temperature is not None else 0.4, timeout=30, max_tokens=self.config.max_output_tokens, max_retries=0,
                )
            if provider == "ollama":
                base_url = self.config.ollama_base_url.rstrip("/")
                if not base_url.endswith("/v1"):
                    base_url += "/v1"
                return ChatOpenAI(
                    model=model_name or self.config.ollama_model, api_key="ollama", base_url=base_url,
                    temperature=temperature if temperature is not None else 0.4, timeout=45, max_tokens=self.config.max_output_tokens, max_retries=0,
                )
            raise ValueError(f"Unknown LLM provider: {provider}")
        except ImportError as exc:
            package = "langchain-google-genai" if provider == "google" else "langchain-groq" if provider == "groq" else "langchain-openai"
            raise RuntimeError(f"Missing provider integration. Install {package} from requirements.txt.") from exc
