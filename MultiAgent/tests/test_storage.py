import tempfile
import unittest
from pathlib import Path

from storage import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.temp.name) / "assistant.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_are_persistent_and_profile_scoped(self):
        self.store.save_settings("alice", {"agent": "Math", "streaming": False})
        reopened = SQLiteStore(self.store.path)
        self.assertEqual(reopened.get_settings("alice"), {"agent": "Math", "streaming": False})
        self.assertEqual(reopened.get_settings("bob"), {})

    def test_memories_are_crud_and_profile_scoped(self):
        memory_id = self.store.add_memory("alice", "Prefers concise answers")
        self.assertEqual(self.store.list_memories("bob"), [])
        self.assertTrue(self.store.edit_memory("alice", memory_id, "Prefers Urdu answers"))
        self.assertEqual(self.store.list_memories("alice")[0]["content"], "Prefers Urdu answers")
        self.assertTrue(self.store.delete_memory("alice", memory_id))
        self.assertEqual(self.store.list_memories("alice"), [])

    def test_clear_only_removes_the_selected_profiles_memories(self):
        self.store.add_memory("alice", "Short answers")
        self.store.add_memory("alice", "Urdu")
        self.store.add_memory("bob", "English")
        self.assertEqual(self.store.clear_memories("alice"), 2)
        self.assertEqual([m["content"] for m in self.store.list_memories("bob")], ["English"])

    def test_old_local_login_profile_is_migrated_without_losing_memories(self):
        self.store.save_settings("local@example.com", {"agent": "Writing"})
        self.store.add_memory("local@example.com", "Prefers concise replies")
        reopened = SQLiteStore(self.store.path)
        self.assertEqual(reopened.get_settings("local"), {"agent": "Writing"})
        self.assertEqual(reopened.list_memories("local")[0]["content"], "Prefers concise replies")

    def test_conversation_messages_search_and_flags_survive_reopen_without_duplicates(self):
        self.assertTrue(self.store.save_conversation_message("thread-a", "alice", "user", "Explain SQLite transactions", "user-1"))
        self.assertFalse(self.store.save_conversation_message("thread-a", "alice", "user", "duplicate", "user-1"))
        self.store.save_conversation_message("thread-a", "alice", "assistant", "A transaction groups database changes.", "assistant-1", status="incomplete")
        reopened = SQLiteStore(self.store.path)
        self.assertEqual([row["role"] for row in reopened.get_conversation_messages("thread-a", "alice")], ["user", "assistant"])
        self.assertEqual(reopened.get_conversation_messages("thread-a", "alice")[1]["status"], "incomplete")
        self.assertEqual(reopened.search_conversations("alice", "transactions")[0]["id"], "thread-a")
        self.assertEqual(reopened.search_conversations("bob", "transactions"), [])
        self.assertTrue(reopened.rename_conversation("thread-a", "alice", "Transaction notes"))
        self.assertEqual(reopened.get_conversation("thread-a", "alice")["title"], "Transaction notes")
        self.assertTrue(reopened.set_conversation_flag("thread-a", "alice", "pinned", True))
        self.assertTrue(reopened.list_conversations("alice")[0]["pinned"])
        self.assertTrue(reopened.set_conversation_flag("thread-a", "alice", "archived", True))
        self.assertEqual(reopened.list_conversations("alice"), [])
        self.assertEqual(reopened.list_conversations("alice", archived=True)[0]["id"], "thread-a")

    def test_existing_message_table_is_migrated_with_completed_default(self):
        import sqlite3
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        conn = sqlite3.connect(legacy)
        with conn:
            conn.executescript("""
                CREATE TABLE conversations (id TEXT PRIMARY KEY,user_identifier TEXT NOT NULL,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,pinned INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,temporary INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE conversation_messages (id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT NOT NULL,message_key TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(conversation_id,message_key));
                INSERT INTO conversations VALUES ('legacy','alice','Old chat','now','now',0,0,0);
                INSERT INTO conversation_messages(conversation_id,message_key,role,content,created_at) VALUES ('legacy','a1','assistant','Old answer','now');
            """)
        conn.close()
        reopened = SQLiteStore(legacy)
        rows = reopened.get_conversation_messages("legacy", "alice")
        self.assertEqual(rows[0]["status"], "completed")

    def test_temporary_conversations_do_not_persist_new_turns(self):
        self.store.save_conversation_message("thread-temp", "alice", "user", "earlier turn", "u1")
        self.store.set_conversation_temporary("thread-temp", "alice", True)
        self.assertFalse(self.store.save_conversation_message("thread-temp", "alice", "user", "private turn", "u2"))
        self.assertEqual(len(self.store.get_conversation_messages("thread-temp", "alice")), 1)

    def test_delete_conversation_removes_its_messages_only(self):
        self.store.save_conversation_message("alice-thread", "alice", "user", "private title", "a1")
        self.store.save_conversation_message("bob-thread", "bob", "user", "another title", "b1")
        self.assertTrue(self.store.delete_conversation("alice-thread", "alice"))
        self.assertEqual(self.store.get_conversation_messages("alice-thread", "alice"), [])
        self.assertEqual(len(self.store.get_conversation_messages("bob-thread", "bob")), 1)

    def test_memories_are_deduplicated_and_retrieved_only_on_overlap(self):
        first = self.store.add_memory("alice", "Prefers answers in Urdu")
        duplicate = self.store.add_memory("alice", "  prefers answers in urdu  ")
        self.assertEqual(first, duplicate)
        self.store.add_memory("alice", "Uses Python for data analysis")
        self.assertEqual([row["content"] for row in self.store.search_memories("alice", "Python data analysis")], ["Uses Python for data analysis"])
        self.assertEqual(self.store.search_memories("alice", "weather forecast"), [])

    def test_library_documents_persist_retrieve_and_remain_profile_scoped(self):
        doc_id = self.store.save_library_document("alice", "notes.md", "The deployment uses PostgreSQL and a nightly backup.")
        reopened = SQLiteStore(self.store.path)
        self.assertEqual(reopened.list_library_documents("alice")[0]["id"], doc_id)
        found = reopened.search_library_documents("alice", "nightly backup")
        self.assertEqual(found[0]["name"], "notes.md")
        self.assertEqual(reopened.search_library_documents("bob", "nightly backup"), [])
        self.assertTrue(reopened.delete_library_document("alice", doc_id))
        self.assertEqual(reopened.search_library_documents("alice", "nightly backup"), [])


if __name__ == "__main__":
    unittest.main()
