"""Local, file-backed Markdown retrieval for the personal assistant."""
from __future__ import annotations

import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_DIR = PROJECT_DIR.parent / "sociapi_agent_knowledge_base"
TOKEN_RE = re.compile(r"[\w+#.-]+", re.UNICODE)
STOP_WORDS = set("a an and are as at be by can do does for from had has have how i in into is it its me my of on or our the their them then there these they this to was we were what when where which who why with you your draft write writing compose prepare create send reply respond polish email e-mail please professional concise short polite".split())
SOCIAPI_BRAND_TERMS = {"brand", "color", "colors", "colour", "colours", "palette", "font", "fonts", "logo", "design", "visual"}
SOCIAPI_RECRUITMENT_TERMS = {"recruit", "recruits", "recruitment", "applicant", "applicants", "shortlisted", "offer", "onboarding", "joining", "interview", "hr"}
SOCIAPI_ACTIVITY_TERMS = {"event", "events", "webinar", "workshop", "bootcamp", "boot", "camp", "operations", "sponsor", "sponsors"}
SOCIAPI_REFERENCE_TERMS = {"source", "sources", "reference", "references", "verify", "verification", "link", "links", "official", "cite", "citation"}
SOCIAPI_GOVERNANCE_TERMS = {
    "own", "owns", "owner", "owners", "ownership", "owned", "member-owned", "memberowned",
    "found", "founded", "founder", "founders", "cofounder", "co-founder", "advisor", "advisors",
    "start", "started", "starting", "creator", "created", "create", "idea", "initiative", "original",
    "establish", "established", "establishment", "behind",
    "lead", "leads", "leader", "leaders", "leadership", "manage", "manages", "manager", "management",
    "govern", "governs", "governed", "governance", "elected", "elect", "election", "elections",
    "role", "roles", "director", "president", "legal", "registered", "registration", "structure",
}


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text) if len(token) > 1 and token.casefold() not in STOP_WORDS]


@dataclass(frozen=True)
class Chunk:
    source: str
    heading: str
    text: str
    terms: Counter[str]
    sensitivity: str = "normal"


class MarkdownKnowledgeBase:
    """A small BM25 index that rereads changed Markdown files without model training."""

    def __init__(self, folder: str | Path | None = None):
        configured = folder or os.getenv("SOCIAPI_KNOWLEDGE_DIR")
        self.folder = Path(configured).expanduser().resolve() if configured else DEFAULT_KNOWLEDGE_DIR.resolve()
        self._lock = threading.RLock()
        self._stamp: tuple[tuple[str, int, int], ...] | None = None
        self._chunks: list[Chunk] = []
        self._errors: list[str] = []
        self._files: list[str] = []

    def _current_stamp(self) -> tuple[tuple[str, int, int], ...]:
        if not self.folder.is_dir():
            return ()
        rows = []
        for path in sorted(self.folder.rglob("*.md")):
            try:
                stat = path.stat()
                rows.append((str(path.relative_to(self.folder)), stat.st_mtime_ns, stat.st_size))
            except OSError:
                continue
        return tuple(rows)

    @staticmethod
    def _split_file(source: str, content: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        heading = "Document"
        parent_heading = heading
        body: list[str] = []
        max_words = 850

        def flush() -> None:
            nonlocal body
            text = "\n".join(body).strip()
            body = []
            if not text:
                return
            words = text.split()
            for start in range(0, len(words), max_words):
                part = " ".join(words[start:start + max_words])
                sensitivity = "internal" if re.search(r"\b(internal|private|financial|applicant|member data|account incident)\b", heading + " " + part, re.I) else "normal"
                chunks.append(Chunk(source, heading, part, Counter(_tokens(heading + " " + part)), sensitivity))

        for line in content.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if match:
                flush()
                heading = match.group(2).strip()
                parent_heading = heading
            elif (source.endswith("08_fact_register_and_uncertainty.md")
                  and parent_heading == "Conflicting or time-sensitive details"
                  and (detail := re.match(r"^\d+\.\s+\*\*(.+?):\*\*\s*(.*)$", line))):
                flush()
                heading = f"Conflicting or time-sensitive details: {detail.group(1).strip()}"
                body.append(detail.group(2))
            else:
                body.append(line)
        flush()
        return chunks

    def reload(self, force: bool = True) -> dict[str, Any]:
        with self._lock:
            stamp = self._current_stamp()
            if not force and stamp == self._stamp:
                return self.status()
            chunks: list[Chunk] = []
            errors: list[str] = []
            files: list[str] = []
            if not self.folder.is_dir():
                errors.append(f"Knowledge folder not found: {self.folder}")
            else:
                for rel, _, _ in stamp:
                    path = self.folder / rel
                    try:
                        content = path.read_text(encoding="utf-8-sig")
                        if not content.strip():
                            errors.append(f"Empty Markdown file: {rel}")
                            continue
                        parsed = self._split_file(rel, content)
                        if not parsed:
                            errors.append(f"No readable sections in Markdown file: {rel}")
                            continue
                        chunks.extend(parsed)
                        files.append(rel)
                    except (OSError, UnicodeError) as exc:
                        errors.append(f"Could not read {rel}: {type(exc).__name__}: {exc}")
            self._stamp, self._chunks, self._errors, self._files = stamp, chunks, errors, files
            return self.status()

    def _ensure_current(self) -> None:
        self.reload(force=False)

    def status(self) -> dict[str, Any]:
        return {"folder": str(self.folder), "document_count": len(self._files), "chunk_count": len(self._chunks), "sources": list(self._files), "errors": list(self._errors)}

    @staticmethod
    def _sociapi_scope(query_terms: set[str]) -> tuple[tuple[str, ...], set[str] | None] | None:
        """Route Society questions to the topical source and sections that support them."""
        if not ({"sociapi", "sociapisociety"} & query_terms):
            role_terms = {"founder", "founders", "cofounder", "co-founder", "advisor", "advisors", "teacher", "creator", "created", "initiative"}
            if query_terms & role_terms:
                return (("02_sociapi_society.md",), {"Identity", "Leadership and roles"})
            return None
        legal_terms = {"legal", "registered", "registration", "secp", "corporate", "incorporated"}
        if query_terms & legal_terms:
            headings = {"Identity", "Leadership and roles", "Registration status"}
            if query_terms & SOCIAPI_REFERENCE_TERMS:
                headings.add("Official links and contact")
            return (("02_sociapi_society.md",), headings)
        if query_terms & SOCIAPI_REFERENCE_TERMS:
            return (("02_sociapi_society.md",), {"Identity", "Mission and positioning", "Official links and contact"})
        if query_terms & SOCIAPI_GOVERNANCE_TERMS:
            headings = {"Identity", "Leadership and roles"}
            if query_terms & SOCIAPI_REFERENCE_TERMS:
                headings.add("Official links and contact")
            return (("02_sociapi_society.md",), headings)
        if query_terms & SOCIAPI_BRAND_TERMS:
            return (("04_brand_and_communication_rules.md",), None)
        if query_terms & SOCIAPI_RECRUITMENT_TERMS:
            if query_terms & SOCIAPI_ACTIVITY_TERMS:
                return (("02_sociapi_society.md", "03_events_projects_operations.md"), None)
            return (("02_sociapi_society.md",), {"Identity", "Leadership and roles", "Recruitment"})
        if query_terms & SOCIAPI_ACTIVITY_TERMS:
            return (("02_sociapi_society.md", "03_events_projects_operations.md"), None)
        if query_terms & {"founder", "cofounder", "co-founder", "advisor", "leadership", "role", "roles"}:
            return (("02_sociapi_society.md",), {"Identity", "Leadership and roles"})
        if query_terms & {"chapter", "chapters", "members", "member", "reach", "participants", "size", "count"}:
            return (("02_sociapi_society.md",), {"Size and reach"})
        if query_terms & {"product", "products", "tool", "tools", "nexus", "pos", "certificate", "outreach"}:
            return (("02_sociapi_society.md",), {"Society products and tools"})
        # Broad identity and activity questions use the Society's own identity
        # and mission sections, never the user's CV or unrelated brand guidance.
        return (("02_sociapi_society.md",), {"Identity", "Mission and positioning"})

    def retrieve(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        self._ensure_current()
        query_terms = _tokens(query)
        if not query_terms:
            return []
        qf = Counter(query_terms)
        sociapi_scope = self._sociapi_scope(set(qf))
        with self._lock:
            chunks = list(self._chunks)
        if not chunks:
            return []
        n = len(chunks)
        avgdl = sum(sum(chunk.terms.values()) for chunk in chunks) / n
        doc_freq = Counter(term for chunk in chunks for term in chunk.terms)
        ranked: list[tuple[float, Chunk]] = []
        for chunk in chunks:
            if sociapi_scope:
                sources, headings = sociapi_scope
                if not chunk.source.endswith(sources) or (headings and chunk.heading not in headings):
                    continue
            dl = sum(chunk.terms.values())
            score = 0.0
            for term, qcount in qf.items():
                tf = chunk.terms.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * dl / max(avgdl, 1))) * min(qcount, 2)
            if score or (sociapi_scope and sociapi_scope[1] and chunk.heading in sociapi_scope[1]):
                score = score or 0.01
                # Core identity and mission sections are the best starting point for
                # broad "What is Sociapi?" questions; topic specific matches still win.
                if sociapi_scope and chunk.source.endswith("02_sociapi_society.md") and chunk.heading in {"Identity", "Mission and positioning"}:
                    score += 1.0
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))
        results = []
        result_limit = max(limit, 7) if sociapi_scope and set(query_terms) & SOCIAPI_GOVERNANCE_TERMS else limit
        for score, chunk in ranked[:max(1, min(result_limit, 8))]:
            results.append({"source": chunk.source, "heading": chunk.heading, "text": chunk.text, "score": round(score, 4), "sensitivity": chunk.sensitivity})
        return results


knowledge_base = MarkdownKnowledgeBase()

