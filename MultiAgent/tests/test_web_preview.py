import unittest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import web_app
from web_app import _conversation_title, _preview_document, open_preview


class WebPreviewTests(unittest.TestCase):
    def test_preview_inlines_local_assets_and_blocks_network(self):
        html = '''<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body>
        <img src="https://example.invalid/photo.png"><script src="app.js"></script></body></html>'''
        document = _preview_document({"index.html": html, "styles.css": "body { color: teal; }", "app.js": "document.title = 'Local';"})
        self.assertIn("<style>body { color: teal; }</style>", document)
        self.assertIn("<script>document.title = 'Local';</script>", document)
        self.assertIn("img-src data: blob:", document)
        self.assertIn("connect-src 'none'", document)

    def test_preview_frame_only_allows_scripts(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('sandbox="allow-scripts"', html)
        self.assertNotIn('sandbox="allow-scripts allow-same-origin"', html)

    def test_open_preview_response_sets_sandbox_csp(self):
        project = {"title": "Demo", "files": {"index.html": "<html><body>Demo</body></html>"}}
        web_app.TEMP_CHATS["preview-check"] = []
        try:
            with patch("web_app.load_project", return_value=project):
                response = asyncio.run(open_preview("preview-check"))
        finally:
            web_app.TEMP_CHATS.pop("preview-check", None)
        policy = response.headers["content-security-policy"]
        self.assertIn("sandbox allow-scripts", policy)
        self.assertNotIn("allow-forms", policy)
        self.assertNotIn("allow-same-origin", policy)


class ChatTitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_chat_title_uses_fast_model_and_sentence_case(self):
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="Interactive Profile Builder")))
        config = SimpleNamespace(groq_api_key="configured", google_api_key=None, groq_fast_model="openai/gpt-oss-20b", google_model="gemini-3.8-flash")
        with patch("web_app.Config", return_value=config), patch("web_app.factory.create", return_value=model):
            title = await _conversation_title("Create an interactive web app for a profile")
        self.assertEqual(title, "Interactive profile builder")
        model.ainvoke.assert_awaited_once()

    async def test_short_title_fallback_has_three_words(self):
        config = SimpleNamespace(groq_api_key=None, google_api_key=None)
        with patch("web_app.Config", return_value=config):
            title = await _conversation_title("Hi")
        self.assertEqual(title, "Hi conversation chat")


if __name__ == "__main__":
    unittest.main()
