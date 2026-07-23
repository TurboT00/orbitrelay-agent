import unittest

from orbitrelay.profiles import (
    AuthKind,
    ProviderCapability,
    ProviderProfile,
    ProfileValidationError,
)


CAPABILITIES = frozenset(
    {
        ProviderCapability.TOOL_CALLING,
        ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
    }
)


class ProviderProfileTests(unittest.TestCase):
    def test_accepts_each_declared_auth_kind_without_a_secret_value(self):
        for auth_kind in AuthKind:
            with self.subTest(auth_kind=auth_kind):
                profile = ProviderProfile.create(
                    name=f"profile-{auth_kind.value.replace('_', '-')}",
                    base_url=(
                        "http://127.0.0.1:11434/v1"
                        if auth_kind is AuthKind.LOCAL_NONE
                        else "https://example.test/v1"
                    ),
                    model="test-model",
                    auth_kind=auth_kind,
                    capabilities=CAPABILITIES,
                )

                self.assertEqual(profile.auth_kind, auth_kind)
                self.assertNotIn("secret", profile.to_dict())
                self.assertNotIn("api_key", profile.to_dict())

    def test_rejects_unsafe_profile_names(self):
        for name in ("", "../escape", "has spaces", "a/b", ".hidden"):
            with self.subTest(name=name):
                with self.assertRaises(ProfileValidationError):
                    ProviderProfile.create(
                        name=name,
                        base_url="https://example.test/v1",
                        model="test-model",
                        auth_kind=AuthKind.API_KEY,
                        capabilities=CAPABILITIES,
                    )

    def test_rejects_unauthenticated_non_loopback_endpoint(self):
        with self.assertRaisesRegex(ProfileValidationError, "loopback"):
            ProviderProfile.create(
                name="unsafe-local",
                base_url="http://192.168.1.20:11434/v1",
                model="test-model",
                auth_kind=AuthKind.LOCAL_NONE,
                capabilities=CAPABILITIES,
            )

    def test_rejects_missing_required_capability(self):
        with self.assertRaisesRegex(ProfileValidationError, "tool_calling"):
            ProviderProfile.create(
                name="missing-tools",
                base_url="https://example.test/v1",
                model="test-model",
                auth_kind=AuthKind.API_KEY,
                capabilities={ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH},
            )

    def test_round_trips_secret_free_metadata(self):
        profile = ProviderProfile.create(
            name="deepseek-work",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            auth_kind=AuthKind.API_KEY,
            capabilities=CAPABILITIES,
        )

        self.assertEqual(ProviderProfile.from_dict(profile.to_dict()), profile)

    def test_rejects_unknown_serialized_fields(self):
        with self.assertRaisesRegex(ProfileValidationError, "unknown fields"):
            ProviderProfile.from_dict(
                {
                    "name": "unsafe",
                    "base_url": "https://example.test/v1",
                    "model": "test-model",
                    "auth_kind": "api_key",
                    "capabilities": ["tool_calling"],
                    "api_key": "must-not-load",
                }
            )


if __name__ == "__main__":
    unittest.main()
