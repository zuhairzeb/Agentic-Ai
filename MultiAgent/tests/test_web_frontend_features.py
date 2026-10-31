import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from router import AGENTS
from web_app import LibraryDocument, MemoryUpdate, _messages, add_library_document, add_saved_memory, app, edit_saved_memory


class WebFrontendFeatureTests(unittest.TestCase):
    def test_composer_menu_only_exposes_supported_tools_and_settings(self):
        source = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('label: "Upload or add files"', source)
        self.assertIn('label: "Web search"', source)
        self.assertIn('label: "Agent"', source)
        self.assertIn('label: "Model quality"', source)
        self.assertIn('item.toggle ? "menuitemcheckbox" : "menuitem"', source)
        self.assertIn("aria-activedescendant", source)
        self.assertIn("No matching commands", source)
        self.assertNotIn('label: "Take a screenshot"', source)

    def test_voice_capture_uses_recorded_audio_not_browser_speech_recognition(self):
        web_root = Path(__file__).resolve().parents[1] / "web"
        source = (web_root / "app.js").read_text(encoding="utf-8")
        markup = (web_root / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/transcribe"', source)
        self.assertNotIn("SpeechRecognition", source)
        for element_id in ("voiceInput", "voiceRetry", "settingVoiceLanguage"):
            self.assertIn(f'id="{element_id}"', markup)
        for element_id in ("voiceStop", "voiceCancel", "voiceClear", "voiceLanguage", "voiceControls"):
            self.assertNotIn(f'id="{element_id}"', markup)
        self.assertIn('response.status === 404', source)

    def test_voice_transcription_route_is_registered(self):
        routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
        self.assertIn(("POST", "/api/transcribe"), routes)

    def test_composer_submit_guard_and_keyboard_behavior(self):
        source = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (event.key === "Enter" && !event.shiftKey)', source)
        self.assertIn("state.sending || state.submitting", source)
        self.assertIn('button.disabled = !state.sending && (state.submitting || (!input.value.trim() && !state.uploaded))', source)
        self.assertIn('if (state.sending) { const requestId = state.activeRequestId;', source)
        self.assertIn('/api/chat/${encodeURIComponent(requestId)}/cancel', source)
        self.assertIn('state.abortController?.abort(); return;', source)
        self.assertIn('state.messages.push({ role: "assistant", content: "", prompt: content, status: "thinking"', source)
        self.assertIn('message.content += typeof value === "string" ? value : ""', source)

    def test_response_completion_requires_terminal_event_and_preserves_recovery_actions(self):
        source = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (!terminalState) {', source)
        self.assertIn('finishRequest("interrupted", "Connection interrupted.', source)
        self.assertIn('event.type === "completed" || event.type === "done"', source)
        self.assertIn('data-response-action="retry"', source)
        self.assertIn('data-response-action="continue"', source)
        self.assertIn('data-response-action="regenerate"', source)

    def test_composer_uses_compact_inline_voice_and_shared_stream_button(self):
        web_root = Path(__file__).resolve().parents[1] / "web"
        markup = (web_root / "index.html").read_text(encoding="utf-8")
        styles = (web_root / "style.css").read_text(encoding="utf-8")
        self.assertIn('data-gramm="false" data-gramm_editor="false" data-enable-grammarly="false"', markup)
        self.assertIn('id="recordingTimer"', markup)
        self.assertNotIn('id="stopGeneration"', markup)
        self.assertNotIn('id="voiceMeter"', markup)
        self.assertIn('[hidden]{display:none!important}', styles)
        self.assertIn('.composer:focus-within', styles)
        self.assertIn('@media(prefers-reduced-motion:reduce){.recording-dot{animation:none!important}}', styles)

    def test_web_memory_api_accepts_safe_preferences(self):
        with patch("web_app.store.add_memory", return_value=42) as add_memory:
            result = asyncio.run(add_saved_memory(MemoryUpdate(content="I prefer concise replies")))
        self.assertEqual(result, {"id": 42})
        add_memory.assert_called_once_with("local", "I prefer concise replies")

    def test_web_memory_api_rejects_credentials(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(add_saved_memory(MemoryUpdate(content="api_key=do-not-store")))
        self.assertEqual(raised.exception.status_code, 400)

    def test_web_memory_edit_uses_existing_profile_scoped_storage(self):
        with patch("web_app.store.edit_memory", return_value=True) as edit_memory:
            result = asyncio.run(edit_saved_memory(7, MemoryUpdate(content="Use Roman Urdu")))
        self.assertEqual(result, {"updated": True})
        edit_memory.assert_called_once_with("local", 7, "Use Roman Urdu")

    def test_web_library_api_saves_uploads_for_future_retrieval(self):
        with patch("web_app.store.save_library_document", return_value=9) as save_document:
            result = asyncio.run(add_library_document(LibraryDocument(name="notes.md", content="project notes")))
        self.assertEqual(result, {"id": 9})
        save_document.assert_called_once_with("local", "notes.md", "project notes")

    def test_relevant_private_library_content_is_added_to_web_chat_context(self):
        document = {"id": 3, "name": "notes.md", "content": "Project uses a nightly backup."}
        with patch("web_app.knowledge_base.retrieve", return_value=[]), patch("web_app.store.search_library_documents", return_value=[document]):
            messages = _messages(AGENTS["general"], "When does the project back up?", [], {}, False)
        self.assertTrue(any("Library document notes.md" in item.content and "nightly backup" in item.content for item in messages))

    def test_disabled_training_examples_are_not_added_to_chat_context(self):
        with patch("web_app.knowledge_base.retrieve", return_value=[]), \
             patch("web_app.store.search_library_documents", return_value=[]), \
             patch("web_app.store.list_platform_items", return_value=[]) as list_items:
            _messages(AGENTS["general"], "How do I write Python?", [], {}, False)
        self.assertIn(unittest.mock.call("local", "training_example", include_disabled=False), list_items.call_args_list)


if __name__ == "__main__":
    unittest.main()
