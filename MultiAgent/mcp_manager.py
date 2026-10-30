"""Local MCP client support for explicitly configured Streamable HTTP servers."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tools import ToolResult

ROOT = Path(__file__).resolve().parent
SECRET_KEY_PATH = ROOT / "data" / "platform-secret.key"
MAX_TOOL_COUNT = 40
MAX_TOOL_RESULT_CHARS = 12000


def _cipher() -> Fernet:
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        key = SECRET_KEY_PATH.read_bytes()
    except FileNotFoundError:
        key = Fernet.generate_key()
        try:
            with SECRET_KEY_PATH.open("xb") as key_file:
                key_file.write(key)
        except FileExistsError:
            key = SECRET_KEY_PATH.read_bytes()
        try:
            SECRET_KEY_PATH.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("The saved MCP credential could not be decrypted. Enter it again.") from exc


def validate_endpoint(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Enter an MCP endpoint without embedded username or password.")
    host = parsed.hostname.rstrip(".").casefold()
    is_loopback_name = host == "localhost" or host.endswith(".localhost")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and not ip.is_global and not ip.is_loopback:
        raise ValueError("Private network addresses are blocked for MCP connections.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback_name):
        raise ValueError("MCP endpoints must use HTTPS. HTTP is allowed only for localhost.")
    if ip and ip.is_loopback and parsed.scheme != "http":
        raise ValueError("Use HTTP for a loopback MCP endpoint.")
    if ip is None:
        if not is_loopback_name:
            try:
                addresses = {ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
            except OSError as lookup_error:
                raise ValueError("The MCP endpoint host could not be verified.") from lookup_error
            if not addresses or any(not address.is_global for address in addresses):
                raise ValueError("MCP hostnames that resolve to private networks are blocked.")
    if parsed.query and re.search(r"(?:token|key|secret|password|auth)=", parsed.query, re.I):
        raise ValueError("Put MCP credentials in the credential field, not in the endpoint URL.")
    return url.strip()


async def _open_session(server: dict[str, Any], secret: str, stack: AsyncExitStack):
    endpoint = validate_endpoint(str(server.get("url", "")))
    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    read_stream, write_stream, _session_id = await stack.enter_async_context(
        streamablehttp_client(endpoint, headers=headers, timeout=10, sse_read_timeout=30)
    )
    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await asyncio.wait_for(session.initialize(), timeout=12)
    return session


async def discover_tools(server: dict[str, Any], secret: str) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        session = await _open_session(server, secret, stack)
        result = await asyncio.wait_for(session.list_tools(), timeout=15)
        tools = []
        for item in result.tools[:MAX_TOOL_COUNT]:
            schema = getattr(item, "inputSchema", None) or getattr(item, "input_schema", None) or {"type": "object", "properties": {}}
            if not isinstance(schema, dict) or schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            tools.append({"name": str(item.name)[:128], "description": str(getattr(item, "description", "") or "External MCP tool")[:1000], "input_schema": schema})
        return tools


async def call_tool(server: dict[str, Any], secret: str, name: str, arguments: dict[str, Any]) -> ToolResult:
    try:
        async with AsyncExitStack() as stack:
            session = await _open_session(server, secret, stack)
            result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=30)
        if getattr(result, "isError", False):
            return ToolResult(False, error="The connected MCP tool reported an error.")
        structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
        if structured is not None:
            text = json.dumps(structured, ensure_ascii=False, default=str)
        else:
            text = "\n".join(str(getattr(part, "text", "")) for part in (getattr(result, "content", None) or []) if getattr(part, "text", None))
        return ToolResult(True, data={"result": text[:MAX_TOOL_RESULT_CHARS]})
    except asyncio.TimeoutError:
        return ToolResult(False, error="The MCP tool timed out.")
    except Exception as exc:
        return ToolResult(False, error=f"The MCP connection failed ({type(exc).__name__}).")


class ConnectedToolRegistry:
    """Combine the built-in tools with tools explicitly enabled from MCP servers."""

    def __init__(self, builtins, servers: list[dict[str, Any]], credentials: dict[str, str], discovered: list[tuple[str, dict[str, Any]]]):
        self.builtins = builtins
        self.servers = {server["id"]: server for server in servers}
        self.credentials = credentials
        self.external: dict[str, tuple[str, dict[str, Any]]] = {}
        self.schemas = []
        for server_id, tool in discovered:
            model_name = f"mcp_{server_id[:8]}_{tool['name']}"[:64]
            suffix = 2
            base = model_name
            while model_name in self.external or model_name in {row["name"] for row in builtins.model_tools()}:
                model_name = f"{base[:59]}_{suffix}"
                suffix += 1
            self.external[model_name] = (server_id, tool)
            self.schemas.append({"name": model_name, "description": f"MCP server {self.servers[server_id].get('name','Server')}: {tool['description']}", "parameters": tool["input_schema"]})

    def model_tools(self, permissions=None):
        return self.builtins.model_tools(permissions) + (self.schemas if "mcp" in (permissions or set()) else [])

    def allowed_names(self, permissions=None):
        names = self.builtins.allowed_names(permissions)
        if "mcp" in (permissions or set()):
            names.update(self.external)
        return names

    async def execute(self, name: str, payload: dict[str, Any], permissions=None):
        if name not in self.external:
            return await self.builtins.execute(name, payload, permissions=permissions)
        if "mcp" not in (permissions or set()):
            return ToolResult(False, error="MCP tool permission was not granted.")
        server_id, tool = self.external[name]
        server = self.servers.get(server_id)
        if not server or not server.get("enabled"):
            return ToolResult(False, error="This MCP server is not enabled.")
        return await call_tool(server, self.credentials.get(server_id, ""), tool["name"], payload)
