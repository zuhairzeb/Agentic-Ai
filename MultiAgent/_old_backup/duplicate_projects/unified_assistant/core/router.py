"""Rule-based routing and lazy model construction."""

from dataclasses import dataclass
import re

from core.config import Config


@dataclass(frozen=True)
class Route:
    key: str
    label: str
    prompt: str


AGENTS = {
    "math": Route("math", "Math Agent (Gemini)", "Solve mathematical questions accurately. Show concise, clear steps when useful."),
    "writing": Route("writing", "Writing Agent (Gemini)", "Help with writing, editing, rewriting, summarizing, and creating content. Match the requested tone and format."),
    "general": Route("general", "General Agent (Groq)", "You are a helpful general assistant. Answer conversational, explanatory, coding, and general knowledge questions clearly."),
    "agent1": Route("agent1", "Agent 1 (Groq quick)", "You are a quick, friendly assistant. Keep answers concise and clear."),
    "agent2": Route("agent2", "Agent 2 (Groq detailed)", "You are a careful assistant. Give considered, detailed explanations in simple language."),
}


def select_route(message: str, selection: str = "Auto") -> tuple[Route, str]:
    """Return a route and message with an optional leading command removed."""
    text = message.strip()
    if selection and selection.lower() not in {"auto", "automatic"}:
        key = selection.lower()
        key = {"writer": "writing"}.get(key, key)
        if key not in AGENTS:
            raise ValueError("Unknown agent selection.")
        return AGENTS[key], text

    match = re.match(r"^(math|writer|writing|agent1|agent2)\b\s*[:,]?\s*", text, re.I)
    if match:
        command = match.group(1).lower()
        key = {"writer": "writing", "writing": "writing"}.get(command, command)
        return AGENTS[key], text[match.end():].strip()

    lowered = text.lower()
    math_patterns = (
        r"\b(calculate|compute|solve|equation|integral|derivative|percentage|percent|arithmetic|math)\b",
        r"\d\s*[+*/^=]\s*\d",
    )
    writing_patterns = r"\b(write|writer|draft|compose|rewrite|summari[sz]e|email|essay|story|poem|blog post|haiku)\b"
    if any(re.search(pattern, lowered) for pattern in math_patterns):
        return AGENTS["math"], text
    if re.search(writing_patterns, lowered):
        return AGENTS["writing"], text
    return AGENTS["general"], text


class AgentFactory:
    """Create provider chat models only when the chosen route needs one."""

    def __init__(self, config: Config = Config()):
        self.config = config

    def create(self, route: Route):
        missing = self.config.missing_key_message(route.key)
        if missing:
            raise RuntimeError(missing)
        try:
            if route.key in {"math", "writing"}:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=self.config.google_model,
                    google_api_key=self.config.google_api_key,
                    temperature=0.2 if route.key == "math" else 0.7,
                )
            from langchain_groq import ChatGroq
            model = self.config.groq_smart_model if route.key == "agent2" else self.config.groq_fast_model
            return ChatGroq(model=model, api_key=self.config.groq_api_key, temperature=0.4)
        except ImportError as exc:
            provider = "langchain-google-genai" if route.key in {"math", "writing"} else "langchain-groq"
            raise RuntimeError(f"Missing provider integration. Install {provider} from requirements.txt.") from exc
