import unittest

from config import Config
from provider_router import configured_providers, provider_health


class ProviderRouterTests(unittest.TestCase):
    def tearDown(self):
        provider_health.reset()

    def test_free_only_filters_paid_models_and_requires_free_plan_confirmation(self):
        config = Config(
            free_only=True,
            google_api_key="g", groq_api_key="r",
            cloudflare_account_id="a", cloudflare_api_token="t",
            openrouter_api_key="o", ollama_base_url="http://localhost:11434/v1",
            gemini_free_tier_confirmed=True, groq_free_tier_confirmed=False,
            cloudflare_free_plan_confirmed=True,
        )
        self.assertEqual(configured_providers(config), ["google", "cloudflare", "openrouter", "ollama"])

    def test_free_only_blocks_unverified_models_and_openrouter_paid_ids(self):
        base = dict(free_only=True, google_api_key="g", gemini_free_tier_confirmed=True,
                    openrouter_api_key="o", ollama_base_url="http://localhost:11434/v1")
        self.assertEqual(configured_providers(Config(**base, google_model="gemini-4-argon")), ["openrouter", "ollama"])
        self.assertEqual(configured_providers(Config(**base, openrouter_model="provider/model")), ["google", "ollama"])

    def test_nonlocal_ollama_is_excluded_in_free_only_mode(self):
        config = Config(free_only=True, ollama_base_url="https://ollama.example.com/v1")
        self.assertNotIn("ollama", configured_providers(config))

    def test_priority_and_preferred_provider_fallback_order_are_configurable(self):
        config = Config(
            google_api_key="g", groq_api_key="r", openrouter_api_key="o",
            provider_priority=("openrouter", "gemini", "groq"),
            enabled_providers=("openrouter", "gemini", "groq"),
        )
        self.assertEqual(configured_providers(config), ["openrouter", "google", "groq"])
        self.assertEqual(configured_providers(config, "Groq"), ["groq", "openrouter", "google"])


if __name__ == "__main__":
    unittest.main()
