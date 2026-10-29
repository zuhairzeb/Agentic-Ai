"""Local, rule-based routing that does not make an extra model call."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Route:
    key: str
    label: str
    prompt: str


AGENTS = {
    "math": Route(
        "math",
        "Math & Data Specialist",
        "Solve mathematical questions, statistics, arithmetic, and data analysis accurately. Show concise, clear steps when useful.",
    ),
    "writing": Route(
        "writing",
        "Writing & Editing Specialist",
        "Help with drafting, editing, rewriting, summarizing, and creating written content. Match the requested tone and format.",
    ),
    "research": Route(
        "research",
        "Research Specialist",
        "Conduct thorough, evidence-based research, synthesize findings, cite source material accurately, and structure the analysis with clear executive summaries and insights.",
    ),
    "general": Route(
        "general",
        "General Assistant",
        "You are a helpful general assistant. Answer conversational, explanatory, coding, and general knowledge questions clearly.",
    ),
    "agent1": Route(
        "agent1",
        "Agent 1 (Quick Assistant)",
        "You are a quick, friendly assistant. Keep answers concise, clear, and direct.",
    ),
    "agent2": Route(
        "agent2",
        "Agent 2 (Detailed Thinker)",
        "You are a careful assistant. Give considered, detailed explanations with structured reasoning.",
    ),
}


def select_route(message: str, selection: str = "Auto") -> tuple[Route, str]:
    """Choose an agent from a manual selection, command prefix, or message cues."""
    text = message.strip()
    if selection and selection.lower() not in {"auto", "automatic"}:
        normalized = selection.lower()
        key = {
            "writer": "writing",
            "writing": "writing",
            "write": "writing",
            "writing agent": "writing",
            "writing & editing specialist": "writing",
            "math": "math",
            "math agent": "math",
            "analyze": "math",
            "analyze data": "math",
            "math & data specialist": "math",
            "research": "research",
            "research specialist": "research",
            "general": "general",
            "general agent": "general",
            "general assistant": "general",
            "code": "general",
            "agent 1": "agent1",
            "agent1": "agent1",
            "agent 2": "agent2",
            "agent2": "agent2",
        }.get(normalized, normalized)
        if key not in AGENTS:
            raise ValueError(f"Unknown agent selection: {selection}")
        return AGENTS[key], text

    match = re.match(r"^(math|analyze|writer|writing|research|agent1|agent2)\b\s*[:,]?\s*", text, re.I)
    if match:
        command = match.group(1).lower()
        key = {
            "writer": "writing",
            "writing": "writing",
            "analyze": "math",
            "research": "research",
        }.get(command, command)
        return AGENTS[key], text[match.end():].strip()

    lowered = text.lower()
    math_patterns = (
        r"\b(calculate|compute|solve|equation|integral|derivative|percentage|percent|arithmetic|math|average|sum|variance|formula|dataset|statistics)\b",
        r"\d\s*[+*/^=]\s*\d",
        r"\b(?:times|multiplied by|divided by|plus|minus|percent of)\b",
    )
    research_patterns = (
        r"\b(research|investigate|in-depth analysis|literature review|market study|pros and cons of|case study|evidence on)\b",
    )
    writing_patterns = (
        r"\b(write|writer|draft|compose|rewrite|summari[sz]e|email|essay|story|poem|blog post|haiku|resume|curriculum vitae|cv|report|proposal|document|cover letter)\b",
    )

    if any(re.search(pattern, lowered) for pattern in math_patterns):
        return AGENTS["math"], text
    if any(re.search(pattern, lowered) for pattern in research_patterns):
        return AGENTS["research"], text
    if any(re.search(pattern, lowered) for pattern in writing_patterns):
        return AGENTS["writing"], text

    return AGENTS["general"], text
