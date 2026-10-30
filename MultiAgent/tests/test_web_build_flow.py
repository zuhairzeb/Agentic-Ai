import asyncio
import json
import os
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

import web_app


class FakeCodeModel:
    def __init__(self, title, filename, label):
        self.title = title
        self.filename = filename
        self.label = label
        self.required = False

    def bind_tools(self, schemas, tool_choice="auto"):
        self.required = tool_choice == "required"
        self.asserted_tools = {item["name"] for item in schemas}
        return self

    async def ainvoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content=f"Built the {self.label}.\n\nOne improvement: add a settings panel.")
        return AIMessage(content="", tool_calls=[{
            "name": "create_artifact",
            "args": {
                "title": self.title,
                "type": "web",
                "files": [{"path": self.filename, "content": f"<!doctype html><html><head><title>{self.title}</title></head><body><main>{self.label}</main></body></html>"}],
            },
            "id": "create-project",
        }])


class WebBuildFlowTests(unittest.TestCase):
    def test_three_build_prompts_call_tool_and_return_preview_artifact(self):
        prompts = (
            ("Create an interactive web app for a social media profile", "Profile", "profile.html", "social profile"),
            ("Make a login page", "Login", "login.html", "login form"),
            ("Build a simple calculator", "Calculator", "calculator.html", "calculator"),
        )
        config = SimpleNamespace(
            groq_api_key="configured", google_api_key=None,
            groq_fast_model="openai/gpt-oss-20b", groq_smart_model="openai/gpt-oss-120b",
            google_model="gemini-3.8-flash",
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_ARTIFACT_DIR": directory}), patch("web_app.Config", return_value=config):
            for prompt, title, filename, label in prompts:
                with self.subTest(prompt=prompt):
                    thread_id = uuid.uuid4().hex
                    web_app.TEMP_CHATS[thread_id] = []
                    model = FakeCodeModel(title, filename, label)

                    async def choose_code(message, selection):
                        return web_app.orchestrator.plan(message, default_agent="Code")

                    async def execute():
                        with patch("web_app._plan_request", side_effect=choose_code), patch("web_app.factory.create", return_value=model) as create_model, patch("web_app._settings", return_value={"agent": "Auto", "provider": "Auto", "model_tier": "Fast", "memory_enabled": False}):
                            response = await web_app.chat(web_app.ChatRequest(
                                thread_id=thread_id,
                                message=prompt,
                                settings={"agent": "Auto", "provider": "Groq", "model": "Auto", "model_tier": "Fast", "memory_enabled": False},
                            ))
                            chunks = []
                            async for chunk in response.body_iterator:
                                chunks.append(chunk)
                            self.assertEqual(create_model.call_args.kwargs["model_tier"], "Smart")
                            return "".join(chunks)

                    try:
                        stream = asyncio.run(execute())
                        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
                        done = next(event["value"] for event in events if event["type"] == "done")
                        self.assertTrue(model.required)
                        self.assertIn("create_artifact", model.asserted_tools)
                        self.assertEqual(done["agent_key"], "code")
                        self.assertEqual(done["artifact"]["title"], title)
                        project = web_app.load_project(thread_id)
                        self.assertIn(filename, project["files"])
                        preview = asyncio.run(web_app.open_preview(thread_id))
                        self.assertIn("sandbox allow-scripts", preview.headers["content-security-policy"])
                    finally:
                        web_app.TEMP_CHATS.pop(thread_id, None)


if __name__ == "__main__":
    unittest.main()
