import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from artifacts import load_project
from tools import ToolDefinition, ToolRegistry, calculate, expression_from_text, reset_artifact_conversation, set_artifact_conversation, tools


class SlowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=10)


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def test_safe_calculator_and_natural_math_parsing(self):
        self.assertEqual(calculate("2 + 3 * 4")["value"], 14)
        self.assertEqual(calculate(expression_from_text("calculate 15% of 200"))["value"], 30)
        self.assertEqual(calculate(expression_from_text("what is 17 times 19"))["value"], 323)

    def test_calculator_rejects_code_and_unsafe_exponents(self):
        with self.assertRaises(ValueError):
            calculate("__import__('os').system('whoami')")
        with self.assertRaises(ValueError):
            calculate("2**99")
        self.assertIsNone(expression_from_text("open a file and read it"))

    async def test_registry_validates_schema_and_permissions(self):
        denied = await tools.execute("calculator", {"expression": "2+2"})
        self.assertFalse(denied.ok)
        self.assertIn("Permission", denied.error)
        extra = await tools.execute("calculator", {"expression": "2+2", "command": "whoami"}, {"math"})
        self.assertFalse(extra.ok)
        result = await tools.execute("calculator", {"expression": "2+2"}, {"math"})
        self.assertTrue(result.ok)
        self.assertEqual(result.data["value"], 4)

    async def test_web_tools_are_registered_but_require_web_search_permission(self):
        self.assertTrue({"web_search", "read_page"}.issubset(tools.allowed_names({"web_search"})))
        self.assertFalse({"web_search", "read_page"} & tools.allowed_names(set()))
        denied = await tools.execute("web_search", {"query": "latest Python version"})
        self.assertFalse(denied.ok)
        self.assertIn("Permission", denied.error)

    async def test_registry_enforces_timeout_and_reports_failure(self):
        async def slow(arguments):
            await asyncio.sleep(0.1)
            return {"value": arguments.value}
        registry = ToolRegistry()
        registry.register(ToolDefinition("slow", "slow test tool", SlowInput, slow, timeout_seconds=0.01))
        result = await registry.execute("slow", {"value": "test"})
        self.assertFalse(result.ok)
        self.assertIn("timed out", result.error)

    async def test_code_agent_artifact_tool_saves_web_project_and_checks_html(self):
        files = {"index.html": "<!doctype html><html><head><title>Demo</title></head><body><main>Ready</main></body></html>"}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}):
            token = set_artifact_conversation("code-tool-test")
            try:
                result = await tools.execute("create_artifact", {"title": "Demo page", "type": "web", "files": [{"path": name, "content": content} for name, content in files.items()]}, {"code"})
            finally:
                reset_artifact_conversation(token)
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.data["entry"], "index.html")
            self.assertEqual(load_project("code-tool-test")["files"], files)

    async def test_web_artifact_tool_rejects_incomplete_html(self):
        token = set_artifact_conversation("invalid-code-tool-test")
        try:
            result = await tools.execute("create_artifact", {"title": "Broken", "type": "web", "files": [{"path": "index.html", "content": "<main>Missing document root"}]}, {"code"})
        finally:
            reset_artifact_conversation(token)
        self.assertFalse(result.ok)
        self.assertIn("basic HTML document structure", result.error)

    async def test_web_artifact_tool_rejects_banned_defaults_and_remote_images(self):
        cases = (
            ("<html><body style=\"font-family: Arial\"></body></html>", "banned default"),
            ("<html><body><img src=\"https://images.example.invalid/photo.png\"></body></html>", "external image"),
        )
        token = set_artifact_conversation("design-check-test")
        try:
            for html, expected in cases:
                result = await tools.execute("create_artifact", {"title": "Design check", "type": "web", "files": [{"path": "index.html", "content": html}]}, {"code"})
                self.assertFalse(result.ok)
                self.assertIn(expected, result.error)
        finally:
            reset_artifact_conversation(token)


if __name__ == "__main__":
    unittest.main()
