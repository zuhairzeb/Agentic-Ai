import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from router import AGENTS
from web_app import LibraryDocument, MemoryUpdate, _messages, add_library_document, add_saved_memory, edit_saved_memory


class WebFrontendFeatureTests(unittest.TestCase):
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
