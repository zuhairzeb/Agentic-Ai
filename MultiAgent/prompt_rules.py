"""Reusable guardrails for evidence-based email drafting."""
from __future__ import annotations

import re

SOCIAPI_GOVERNANCE_GUIDANCE = (
    " For ordinary Sociapi questions asking who owns, started, created, initiated, or is behind the Society, answer about its founding: Muhammad Zuhair Zeb is the Founder and original creator; the original idea and initiative came from him, and he established the society. "
    "Identify Muhammad Mudassir as Co-Founder and Dr. Naveed Abbas as Teacher Advisor when relevant. Adapt the wording to the question instead of repeating a fixed paragraph. "
    "Treat a casual question like 'who owns Sociapi?' as asking who founded and created the student society. Answer with the Founder and, when useful, the Co-Founder and Teacher Advisor. Do not add a caveat or sentence about legal or corporate ownership unless the user explicitly asks about legal ownership. Do not describe the Society as member-owned or say its leadership is elected unless a source confirms that. "
    "Do not introduce legal registration, corporate ownership, or legal status unless the user asks about it. When asked whether it is legally registered, answer directly: 'Sociapi Society was not formally registered at its last confirmed status. Its current status should be checked.' Do not say that newer information is unavailable or refer to sources/records; avoid SECP details unless the user asks for them. "
    "For a direct legal-ownership question whose answer is not established, state the limitation briefly and naturally without guessing. "
    "Use retrieved section headings and metadata only internally. When you rely on a local knowledge fact, cite its Markdown filename briefly (for example, 'Source: 02_sociapi_society.md'); never reveal local paths, retrieval scores, or debug details. Cite public web facts with clickable source links."
)


EMAIL_WRITING_GUIDANCE = (
    " For email drafts, use a professional, concise, natural tone. Include factual details only when explicitly supplied by the user or supported by retrieved source excerpts. "
    "Keep verified details separate from assumptions or suggested wording; never present an assumption as a verified fact. Keep local file paths out of the draft; a brief filename citation may appear after the draft when local facts were used, and web facts need clickable source links. "
    "Never promise a future email, meeting, offer letter, or onboarding step unless a retrieved source explicitly confirms it. "
    "If responsibilities, reporting structure, or joining date are not established by the user or sources, omit them entirely; do not promise to provide them later and do not add placeholders. "
    "Omit other unavailable details rather than inventing them. Do not ask for optional missing HR details when a concise neutral draft can be written."
)


def is_email_writing_request(message: str, route_key: str) -> bool:
    """Apply email rules to email composition handled by the writing agent."""
    return route_key == "writing" and bool(re.search(r"\b(?:e-?mail)\b", message, re.IGNORECASE))
