import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from app import _command, _conversation_id_argument, _features_content, _filter_unverified_links, _make_messages, _parse_uploads, _provider_error_message, _provider_order, _route_for_turn, _settings_widgets, _time_sensitive_fallback, _visible_commands, _welcome_content
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
        self.assertEqual(_route_for_turn("code", "write a Python function", "Auto")[0].key, "code")

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

    def test_explicit_provider_selection_is_first_and_can_fail_over(self):
        config = Config(
            google_api_key="google-test", groq_api_key="groq-test",
            enabled_providers=("gemini", "groq"), provider_priority=("gemini", "groq"),
            free_only=False,
        )
        self.assertEqual(_provider_order("math", "Gemini", config), ["google", "groq"])
        self.assertEqual(_provider_order("math", "Groq", config), ["groq", "google"])
        self.assertEqual(_provider_order("math", "Auto", config), ["google", "groq"])

    def test_settings_offer_provider_and_real_provider_check(self):
        ids = {widget.id for widget in _settings_widgets({})}
        self.assertIn("provider", ids)
        self.assertIn("model_tier", ids)
        self.assertIn("test_providers", ids)
        self.assertIn("manage_memory", ids)
        self.assertIn("web_search_mode", ids)
        self.assertIn("web_search_provider", ids)

    def test_primary_command_picker_hides_management_and_debug_commands(self):
        ids = {item["id"] for item in _visible_commands()}
        self.assertEqual(ids, {"write", "research", "code", "analyze", "summarize", "upload", "features"})
        self.assertTrue({"pin", "unpin", "archive", "unarchive", "temporary", "export", "clear-context", "memory", "regenerate", "help", "test-provider"}.isdisjoint(ids))

    def test_features_menu_includes_slash_discovery_and_supported_uploads(self):
        text = _features_content()
        for entry in ("/features", "/upload", "paperclip button", "TXT", "Markdown", "PDF", "/research", "/code", "Web search", "Settings", "/memory"):
            self.assertIn(entry, text)

    def test_upload_slash_command_accepts_file_picker_results(self):
        from app import _command
        self.assertEqual(_command(SimpleNamespace(command="upload", content="/upload")), ("upload", ""))

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

    def test_time_sensitive_answer_context_excludes_local_memory_and_chat_history(self):
        result = {"title": "Python releases", "url": "https://www.python.org/downloads/", "date": "2026-10-26", "content": "Latest Python 3.15.2"}
        messages = _make_messages(AGENTS["general"], "What is the latest version of Python?", [("user", "My old team decision")], {"memory_enabled": True}, [result], True, True)
        combined = "\n".join(message.content for message in messages)
        self.assertIn("Latest Python 3.15.2", combined)
        self.assertNotIn("old team decision", combined)
        self.assertNotIn("02_sociapi_society.md", combined)
        self.assertNotIn("my old", combined.lower())

    def test_time_sensitive_answer_removes_links_not_in_search_results(self):
        answer = "Python 3.15.2 [official](https://www.python.org/downloads/) and [fake](https://example.invalid/python). https://bad.example"
        safe = _filter_unverified_links(answer, {"https://www.python.org/downloads/"})
        self.assertIn("[official](https://www.python.org/downloads/)", safe)
        self.assertIn("fake", safe)
        self.assertNotIn("https://example.invalid", safe)
        self.assertNotIn("https://bad.example", safe)

    def test_time_sensitive_answers_fail_closed_when_search_is_off_or_unavailable(self):
        self.assertIn("I could not verify this online", _time_sensitive_fallback(True, "Off", []))
        self.assertIn("I could not verify this online", _time_sensitive_fallback(True, "Auto", []))
        self.assertIsNone(_time_sensitive_fallback(True, "Auto", [{"url": "https://www.python.org/"}]))
        self.assertIsNone(_time_sensitive_fallback(False, "Auto", []))

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
            picker_result = [SimpleNamespace(name="notes.txt", path=str(text_file))]
            self.assertEqual(asyncio.run(_parse_uploads(picker_result)), ("[Attached document: notes.txt]\nmeeting moved to Tuesday", None))
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
