import unittest

from agents import AgentFactory
from config import Config
from langchain_openai import ChatOpenAI
from router import AGENTS


class ProviderAdapterTests(unittest.TestCase):
    def test_cloudflare_openrouter_and_ollama_adapt_to_openai_chat_interface(self):
        config = Config(
            free_only=True,
            cloudflare_account_id="account-test", cloudflare_api_token="token-test",
            cloudflare_model="@cf/zai-org/glm-4.7-flash", cloudflare_free_plan_confirmed=True,
            openrouter_api_key="openrouter-test", openrouter_model="provider/paid-model",
            ollama_base_url="http://localhost:11434", ollama_model="llama3.2",
        )
        factory = AgentFactory(config)
        cloudflare = factory.create(AGENTS["general"], provider="cloudflare")
        openrouter = factory.create(AGENTS["general"], provider="openrouter")
        ollama = factory.create(AGENTS["general"], provider="ollama")
        self.assertIsInstance(cloudflare, ChatOpenAI)
        self.assertEqual(cloudflare.model_name, "@cf/zai-org/glm-4.7-flash")
        self.assertIn(config.cloudflare_account_id, cloudflare.openai_api_base)
        self.assertEqual(openrouter.model_name, "openrouter/free")
        self.assertEqual(openrouter.openai_api_base, "https://openrouter.ai/api/v1")
        self.assertEqual(ollama.openai_api_base, "http://localhost:11434/v1")

    def test_free_only_cloudflare_rejects_model_outside_verified_free_allowlist(self):
        config = Config(
            free_only=True,
            cloudflare_account_id="account-test", cloudflare_api_token="token-test",
            cloudflare_model="@cf/moonshotai/kimi-k2.6", cloudflare_free_plan_confirmed=True,
        )
        with self.assertRaisesRegex(RuntimeError, "not enabled for FREE_ONLY"):
            AgentFactory(config).create(AGENTS["general"], provider="cloudflare")


if __name__ == "__main__":
    unittest.main()
