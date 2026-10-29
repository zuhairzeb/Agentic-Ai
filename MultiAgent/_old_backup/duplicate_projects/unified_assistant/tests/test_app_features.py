import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from app import _command, _conversation_id_argument, _make_messages, _parse_uploads, _provider_error_message, _provider_order, _route_for_turn, _settings_widgets, _visible_commands, _welcome_content
from config import Config
from router import AGENTS


class AppFeatureTests(unittest.TestCase):
    def test_explicit_commands_route_to_real_specialists(self):
        self.assertEqual(_route_for_turn("math", "what is 3+4", "Auto")[0].key, "math")
        self.assertEqual(_route_for_turn("analyze", "calculate 15% of 200", "Auto")[0].key, "math")
        self.assertEqual(_route_for_turn("write", "draft a note", "Auto")[0].key, "writing")
        self.assertEqual(_route_for_turn("research", "quantum computing developments", "Auto")[0].key, "research")
        self.assertEqual(_route_for_turn("chat", "calculate 3+4", "Auto")[0].key, "general")
        self.assertEqual(_route_for_turn("summarize", "some notes", "Auto")[0].key, "writing")
        self.assertTrue(_route_for_turn("summarize", "some notes", "Auto")[1].startswith("Summarize the following content"))
        self.assertEqual(_route_for_turn("code", "write a Python function", "Auto")[0].key, "general")

    def test_slash_command_is_parsed_for_native_command_and_text_forms(self):
        self.assertEqual(_command(SimpleNamespace(command="math", content="/math 2+2")), ("math", "2+2"))
        self.assertEqual(_command(SimpleNamespace(command="analyze", content="/analyze 2+2")), ("analyze", "2+2"))
        self.assertEqual(_command(SimpleNamespace(command="research", content="/research AI trends")), ("research", "AI trends"))
        self.assertEqual(_command(SimpleNamespace(command=None, content="/write hello")), ("write", "hello"))
        self.assertEqual(_command(SimpleNamespace(command=None, content="/resume\t<abc-123>")), ("resume", "<abc-123>"))
        self.assertEqual(_command(SimpleNamespace(command=None, content="/search project notes")), ("search", "project notes"))

    def test_starters_only_offer_backed_agent_actions(self):
        from app import set_starters
        starters = asyncio.run(set_starters())
        self.assertEqual({starter.command for starter in starters}, {"write", "research", "code", "analyze", "summarize"})

    def test_resume_argument_normalizes_displayed_id(self):
        self.assertEqual(_conversation_id_argument("  `<abc-123>`  "), "abc-123")
        self.assertEqual(_conversation_id_argument("abc-123 extra text"), "abc-123")
        self.assertEqual(_conversation_id_argument("  "), "")

    def test_welcome_uses_only_configured_app_name(self):
        content = _welcome_content()
        self.assertTrue(content.startswith("# Hello"))
        self.assertNotIn("AI Assistant", content)
        self.assertNotIn("configured", content)

    def test_explicit_provider_selection_does_not_fallback(self):
        config = Config(google_api_key="google-test", groq_api_key="groq-test")
        self.assertEqual(_provider_order("math", "Gemini", config), ["google"])
        self.assertEqual(_provider_order("math", "Groq", config), ["groq"])
        self.assertEqual(_provider_order("math", "Auto", config), ["google", "groq"])

    def test_settings_offer_provider_and_real_provider_check(self):
        ids = {widget.id for widget in _settings_widgets({})}
        self.assertIn("provider", ids)
        self.assertIn("model_tier", ids)
        self.assertIn("test_providers", ids)
        self.assertIn("manage_memory", ids)

    def test_primary_command_picker_hides_management_and_debug_commands(self):
        ids = {item["id"] for item in _visible_commands()}
        self.assertEqual(ids, {"write", "research", "code", "analyze", "summarize"})
        self.assertTrue({"pin", "unpin", "archive", "unarchive", "temporary", "export", "clear-context", "memory", "regenerate", "help", "test-provider"}.isdisjoint(ids))

    def test_provider_errors_are_specific_and_never_include_exception_text(self):
        class ResourceExhausted(Exception):
            pass
        error = ResourceExhausted("secret token must not be surfaced")
        message = _provider_error_message(error, attempts=1)
        self.assertIn("rate-limited", message)
        self.assertIn("selected provider", message)
        self.assertNotIn("secret token", message)

    def test_empty_provider_response_has_a_clear_retry_message(self):
        from generation import EmptyResponseError
        message = _provider_error_message(EmptyResponseError("private details"), attempts=1)
        self.assertIn("without returning readable text", message)
        self.assertIn("Retry", message)
        self.assertNotIn("private details", message)

    @patch("app.store.search_memories")
    def test_disabling_memory_skips_long_term_retrieval(self, search_memories):
        _make_messages(AGENTS["general"], "Explain async", [], {"memory_enabled": False})
        search_memories.assert_not_called()

    def test_professional_style_avoids_casual_instruction(self):
        messages = _make_messages(AGENTS["general"], "Draft a notice", [], {"response_style": "Professional"})
        self.assertIn("polished professional English", messages[0].content)
        self.assertNotIn("occasional light", messages[0].content)

    def test_web_artifact_requests_get_file_and_preview_instructions(self):
        messages = _make_messages(AGENTS["writing"], "Create an event registration form with validation", [], {})
        self.assertIn("complete working implementation", messages[0].content)
        self.assertIn("filename=index.html", messages[0].content)
        self.assertIn("No network dependencies", messages[0].content)

    def test_casual_style_is_light_and_preserves_technical_clarity(self):
        messages = _make_messages(AGENTS["general"], "Explain async", [], {"response_style": "Casual / Gen Z"})
        self.assertIn("occasional light", messages[0].content)
        self.assertIn("technical, serious", messages[0].content)

    def test_login_is_not_enabled(self):
        from chainlit.config import config
        from chainlit.auth import require_login
        self.assertIsNone(config.code.password_auth_callback)
        self.assertFalse(require_login())

    def test_uploads_extract_supported_text_and_reject_unknown_types(self):
        with tempfile.TemporaryDirectory() as directory:
            text_file = Path(directory) / "notes.txt"
            text_file.write_text("meeting moved to Tuesday", encoding="utf-8")
            message = SimpleNamespace(elements=[SimpleNamespace(name="notes.txt", path=str(text_file))])
            self.assertEqual(asyncio.run(_parse_uploads(message)), ("[Attached document: notes.txt]\nmeeting moved to Tuesday", None))
            markdown_file = Path(directory) / "notes.markdown"
            markdown_file.write_text("## Notes", encoding="utf-8")
            markdown_message = SimpleNamespace(elements=[SimpleNamespace(name="notes.markdown", path=str(markdown_file))])
            self.assertEqual(asyncio.run(_parse_uploads(markdown_message)), ("[Attached document: notes.markdown]\n## Notes", None))
            binary_file = Path(directory) / "payload.exe"
            binary_file.write_bytes(b"not executed")
            rejected = SimpleNamespace(elements=[SimpleNamespace(name="payload.exe", path=str(binary_file))])
            content, error = asyncio.run(_parse_uploads(rejected))
            self.assertEqual(content, "")
            self.assertIn("Supported uploads", error)


if __name__ == "__main__":
    unittest.main()
