import unittest
from unittest.mock import patch

from agents import AgentFactory
from config import Config, _max_output_tokens
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

    def test_output_token_budget_is_configurable_and_bounded(self):
        with patch.dict("os.environ", {"LLM_MAX_OUTPUT_TOKENS": "12000"}):
            self.assertEqual(_max_output_tokens(), 12000)
        with patch.dict("os.environ", {"LLM_MAX_OUTPUT_TOKENS": "90000"}):
            self.assertEqual(_max_output_tokens(), 32768)
        with patch.dict("os.environ", {"LLM_MAX_OUTPUT_TOKENS": "invalid"}):
            self.assertEqual(_max_output_tokens(), 8192)


if __name__ == "__main__":
    unittest.main()
