from __future__ import annotations

import unittest

from orbitrelay.providers import (
    AuthMethod,
    ExecutionRoute,
    ProviderId,
    provider_definition,
    provider_for_legacy_endpoint,
    supported_providers,
)


class ProviderCatalogTests(unittest.TestCase):
    def test_required_provider_ids_are_present_once(self) -> None:
        providers = supported_providers()

        self.assertEqual(
            {provider.identifier for provider in providers},
            {
                ProviderId.OPENAI,
                ProviderId.CODEX,
                ProviderId.GEMINI,
                ProviderId.GROK,
                ProviderId.DEEPSEEK,
            },
        )
        self.assertEqual(len(providers), len({provider.identifier for provider in providers}))

    def test_openai_compatible_providers_have_https_defaults(self) -> None:
        for provider in supported_providers():
            if provider.route is ExecutionRoute.OPENAI_COMPATIBLE:
                self.assertTrue(provider.base_url and provider.base_url.startswith("https://"))
                self.assertTrue(provider.default_model)
                self.assertTrue(provider.capabilities)

    def test_grok_and_deepseek_do_not_advertise_subscription(self) -> None:
        for identifier in (ProviderId.GROK, ProviderId.DEEPSEEK):
            subscription = provider_definition(identifier).auth(AuthMethod.SUBSCRIPTION)
            self.assertFalse(subscription.available)
            self.assertTrue(subscription.reason)

    def test_codex_uses_the_external_cli_subscription_route(self) -> None:
        codex = provider_definition(ProviderId.CODEX)

        self.assertIs(codex.route, ExecutionRoute.CODEX_CLI)
        self.assertTrue(codex.auth(AuthMethod.SUBSCRIPTION).available)
        self.assertFalse(codex.auth(AuthMethod.API_KEY).available)

    def test_known_legacy_endpoints_map_to_their_provider(self) -> None:
        self.assertIs(
            provider_for_legacy_endpoint("https://api.x.ai/v1/"),
            provider_definition(ProviderId.GROK),
        )
        self.assertIsNone(provider_for_legacy_endpoint("https://example.test/v1"))


if __name__ == "__main__":
    unittest.main()
