# story: e03s01

import unittest

from orbitrelay.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    XAI_DEFAULT_BASE_URL,
    XAI_DEFAULT_MODEL,
    load_api_config,
)


class ApiConfigTests(unittest.TestCase):
    def test_uses_deepseek_defaults(self):
        config = load_api_config({"OPENAI_API_KEY": "secret"})

        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertEqual(config.model, DEFAULT_MODEL)

    def test_all_settings_can_be_overridden(self):
        config = load_api_config(
            {
                "OPENAI_API_KEY": "custom-key",
                "OPENAI_BASE_URL": "https://example.test/v1",
                "OPENAI_MODEL": "custom-model",
            }
        )

        self.assertEqual(config.api_key, "custom-key")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.model, "custom-model")

    def test_api_key_is_required(self):
        with self.assertRaisesRegex(
            ValueError, "OPENAI_API_KEY or XAI_API_KEY is required"
        ):
            load_api_config({})

    def test_explicit_empty_base_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_BASE_URL cannot be empty"):
            load_api_config(
                {"OPENAI_API_KEY": "secret", "OPENAI_BASE_URL": "  "}
            )

    def test_explicit_empty_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_MODEL cannot be empty"):
            load_api_config({"OPENAI_API_KEY": "secret", "OPENAI_MODEL": ""})

    def test_xai_api_key_uses_xai_defaults(self):
        config = load_api_config({"XAI_API_KEY": "xai-secret"})

        self.assertEqual(config.api_key, "xai-secret")
        self.assertEqual(config.base_url, XAI_DEFAULT_BASE_URL)
        self.assertEqual(config.model, XAI_DEFAULT_MODEL)
        self.assertEqual(config.base_url, "https://api.x.ai/v1")
        self.assertEqual(config.model, "grok-4.5")

    def test_xai_base_url_and_model_can_be_overridden(self):
        config = load_api_config(
            {
                "XAI_API_KEY": "xai-secret",
                "XAI_BASE_URL": "https://xai.example.test/v1",
                "XAI_MODEL": "grok-custom",
            }
        )

        self.assertEqual(config.api_key, "xai-secret")
        self.assertEqual(config.base_url, "https://xai.example.test/v1")
        self.assertEqual(config.model, "grok-custom")

    def test_openai_api_key_takes_precedence_over_xai_api_key(self):
        config = load_api_config(
            {
                "OPENAI_API_KEY": "openai-secret",
                "XAI_API_KEY": "xai-secret",
            }
        )

        self.assertEqual(config.api_key, "openai-secret")
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertEqual(config.model, DEFAULT_MODEL)

    def test_explicit_empty_xai_base_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "XAI_BASE_URL cannot be empty"):
            load_api_config({"XAI_API_KEY": "xai-secret", "XAI_BASE_URL": " "})

    def test_explicit_empty_xai_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "XAI_MODEL cannot be empty"):
            load_api_config({"XAI_API_KEY": "xai-secret", "XAI_MODEL": ""})


if __name__ == "__main__":
    unittest.main()
