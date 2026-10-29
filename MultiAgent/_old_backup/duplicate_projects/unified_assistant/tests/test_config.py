import unittest

from agents import AgentFactory
from config import Config
from router import AGENTS


class ConfigTests(unittest.TestCase):
    def test_key_errors_are_provider_specific(self):
        config = Config(google_api_key=None, groq_api_key=None)
        self.assertIn("GOOGLE_API_KEY", config.missing_key_message("math"))
        self.assertIn("GROQ_API_KEY", config.missing_key_message("general"))

    def test_factory_checks_keys_before_provider_setup(self):
        factory = AgentFactory(Config(google_api_key=None, groq_api_key=None))
        with self.assertRaisesRegex(RuntimeError, "GOOGLE_API_KEY"):
            factory.create(AGENTS["math"])


if __name__ == "__main__":
    unittest.main()
