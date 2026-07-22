import unittest

from orbitrelay.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_api_config


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
        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
            load_api_config({})

    def test_explicit_empty_base_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_BASE_URL cannot be empty"):
            load_api_config(
                {"OPENAI_API_KEY": "secret", "OPENAI_BASE_URL": "  "}
            )

    def test_explicit_empty_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_MODEL cannot be empty"):
            load_api_config({"OPENAI_API_KEY": "secret", "OPENAI_MODEL": ""})


if __name__ == "__main__":
    unittest.main()
