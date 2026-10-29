import unittest

from memory import SessionMemory, is_sensitive_memory


class MemoryTests(unittest.TestCase):
    def test_history_is_shared_by_agent_and_isolated_by_session(self):
        memory = SessionMemory()
        memory.add_turn("session-a", "My name is Ada", "Hello Ada")
        self.assertEqual(memory.get("session-a"), [("user", "My name is Ada"), ("assistant", "Hello Ada")])
        self.assertEqual(memory.get("session-b"), [])

    def test_bounded_and_clearable(self):
        memory = SessionMemory(max_turns=1)
        memory.add_turn("a", "first", "reply")
        memory.add_turn("a", "second", "reply")
        self.assertEqual(memory.get("a"), [("user", "second"), ("assistant", "reply")])
        memory.clear("a")
        self.assertEqual(memory.get("a"), [])

    def test_sensitive_content_is_rejected_for_saved_memory(self):
        self.assertTrue(is_sensitive_memory("My email is person@example.com"))
        self.assertTrue(is_sensitive_memory("api_key=secret-value"))
        self.assertFalse(is_sensitive_memory("I prefer concise answers in Urdu"))


if __name__ == "__main__":
    unittest.main()
