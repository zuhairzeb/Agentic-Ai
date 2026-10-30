"""Safe local services for skills, knowledge imports, and MCP metadata."""

from __future__ import annotations

import asyncio
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse
import uuid

import httpx

MAX_SKILL_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_SKILL_FILES = 60
MAX_SKILL_CONTENT_BYTES = 1_000_000


def _skill_metadata(text: str) -> tuple[str, str]:
    name_match = re.search(r"(?m)^name:\s*(.+?)\s*$", text[:4000])
    description_match = re.search(r"(?m)^description:\s*(.+?)\s*$", text[:4000])
    heading_match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    name = (name_match.group(1).strip(" '\"") if name_match else heading_match.group(1).strip() if heading_match else "Imported skill")[:100]
    description = (description_match.group(1).strip(" '\"") if description_match else "Custom instructions for relevant requests.")[:500]
    return name, description


def build_skill(files: dict[str, str], source: str) -> dict[str, Any]:
    if not files or "SKILL.md" not in files:
        raise ValueError("The skill package must contain a SKILL.md file at its root or in one folder.")
    instructions = files["SKILL.md"]
    if not instructions.strip() or len(instructions) > 100_000:
        raise ValueError("SKILL.md must contain up to 100 KB of instructions.")
    name, description = _skill_metadata(instructions)
    clean_files = {name: body[:100_000] for name, body in files.items() if name != "SKILL.md" and isinstance(body, str)}
    return {"name": name, "description": description, "instructions": instructions, "resources": clean_files, "source": source[:500]}


def read_skill_archive(raw: bytes, source: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_SKILL_ARCHIVE_BYTES:
        raise ValueError("Skill ZIP files must be between 1 byte and 8 MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("That file is not a readable ZIP archive.") from exc
    candidates: dict[str, bytes] = {}
    total = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if info.is_dir() or info.filename.endswith("/"):
            continue
        if path.is_absolute() or (path.parts and path.parts[0].endswith(":")) or ".." in path.parts or "\\" in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("The ZIP contains an unsafe path or symbolic link.")
        if len(candidates) >= MAX_SKILL_FILES:
            raise ValueError("Skill ZIP files may contain up to 60 files.")
        total += info.file_size
        if total > MAX_SKILL_CONTENT_BYTES:
            raise ValueError("Skill text resources may total up to 1 MB.")
        if info.file_size > 200_000:
            continue
        if path.suffix.casefold() in {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".js"}:
            try:
                candidates[info.filename] = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
    skill_files = [name for name in candidates if PurePosixPath(name).name == "SKILL.md"]
    if not skill_files:
        raise ValueError("The ZIP must include a SKILL.md file.")
    chosen = min(skill_files, key=lambda name: (len(PurePosixPath(name).parts), name))
    root = str(PurePosixPath(chosen).parent)
    prefix = "" if root == "." else root + "/"
    files = {PurePosixPath(name).relative_to(PurePosixPath(root)).as_posix(): body for name, body in candidates.items() if name == chosen or name.startswith(prefix)}
    files["SKILL.md"] = files.pop(PurePosixPath(chosen).relative_to(PurePosixPath(root)).as_posix())
    return build_skill(files, source)


async def import_github_skill(url: str) -> dict[str, Any]:
    parsed = urlparse(url.strip())
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/tree/[A-Za-z0-9_.-]+(?:/(.*))?)?/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not match or parsed.query or parsed.fragment:
        raise ValueError("Use a GitHub repository URL such as https://github.com/owner/repo.")
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"Accept": "application/vnd.github+json", "User-Agent": "Morrow-Skill-Importer"}) as client:
        async with client.stream("GET", endpoint) as response:
            if response.status_code != 200:
                raise ValueError("GitHub could not provide that repository archive. Check the URL and repository visibility.")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_SKILL_ARCHIVE_BYTES:
                    raise ValueError("GitHub skill archives are limited to 8 MB.")
    skill = await asyncio.to_thread(read_skill_archive, bytes(data), url)
    skill["repository"] = f"{owner}/{repo}"
    return skill


def relevant_skills(skills: list[dict[str, Any]], query: str, selected_ids: list[str] | None = None, limit: int = 2) -> list[dict[str, Any]]:
    selected = set(selected_ids or [])
    terms = {term.casefold() for term in re.findall(r"[\w+#.-]{2,}", query)}
    scored = []
    for skill in skills:
        if not skill.get("enabled"):
            continue
        haystack = f"{skill.get('name','')} {skill.get('description','')} {skill.get('instructions','')}".casefold()
        skill_terms = {term.casefold() for term in re.findall(r"[\w+#.-]{2,}", haystack[:12000])}
        score = len(terms & skill_terms) / max(1, len(terms))
        if skill["id"] in selected:
            score += 1.0
        if score:
            scored.append((score, skill))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [skill for _score, skill in scored[:limit]]


def new_item_id() -> str:
    return uuid.uuid4().hex
