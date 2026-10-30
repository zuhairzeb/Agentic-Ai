import unittest

from router import AGENTS, requires_artifact, select_route


class RouterTests(unittest.TestCase):
    def test_automatic_routing(self):
        cases = {
            "Calculate 15% of 200": "math",
            "Write a professional email": "writing",
            "Tell me a short story about Mars": "writing",
            "Explain Python decorators": "general",
            "What is the capital of France?": "general",
            "Conduct in-depth analysis of AI hardware": "research",
        }
        for prompt, key in cases.items():
            with self.subTest(prompt=prompt):
                route, unchanged = select_route(prompt)
                self.assertEqual(route.key, key)
                self.assertEqual(unchanged, prompt)

    def test_commands_and_manual_selection(self):
        cases = (
            ("math: 2 + 2", "math", "2 + 2"),
            ("analyze: calculate 15% of 200", "math", "calculate 15% of 200"),
            ("writer: draft a note", "writing", "draft a note"),
            ("research: recent breakthroughs in medicine", "research", "recent breakthroughs in medicine"),
            ("agent1: hello", "agent1", "hello"),
            ("agent2 hello", "agent2", "hello"),
        )
        for text, key, prompt in cases:
            with self.subTest(text=text):
                route, actual_prompt = select_route(text)
                self.assertEqual((route.key, actual_prompt), (key, prompt))
        self.assertEqual(select_route("calculate 2+2", selection="writer")[0].key, "writing")
        self.assertEqual(select_route("quantum physics", selection="research")[0].key, "research")

    def test_topic_changes_route_each_turn(self):
        self.assertEqual(select_route("calculate 3*5")[0].key, "math")
        self.assertEqual(select_route("now write an email")[0].key, "writing")
        self.assertEqual(select_route("Create a resume for me")[0].key, "writing")
        self.assertEqual(select_route("investigate market trends")[0].key, "research")
        self.assertIn("general", AGENTS)
        self.assertIn("research", AGENTS)

    def test_build_requests_require_artifact_tool(self):
        prompts = (
            "Create an interactive web app for a social media profile",
            "Make a login page",
            "Build a simple calculator",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(select_route(prompt)[0].key, "code")
                self.assertTrue(requires_artifact(prompt))


if __name__ == "__main__":
    unittest.main()
