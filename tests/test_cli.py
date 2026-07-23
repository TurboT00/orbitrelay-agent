# story: e01s01

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from orbitrelay import cli
from orbitrelay.credentials import CredentialNotFoundError
from orbitrelay.config import DEFAULT_BASE_URL, DEFAULT_MODEL
from orbitrelay.profile_store import ProfileNotFoundError, ProfileRepository
from orbitrelay.profiles import (
    AuthKind,
    ProviderCapability,
    ProviderProfile,
)


CAPABILITIES = {
    ProviderCapability.TOOL_CALLING,
    ProviderCapability.ASSISTANT_MESSAGE_PASSTHROUGH,
}


def profile(name, base_url, auth_kind=AuthKind.API_KEY):
    return ProviderProfile.create(
        name=name,
        base_url=base_url,
        model=f"{name}-model",
        auth_kind=auth_kind,
        capabilities=CAPABILITIES,
    )


class FakeCredentialStore:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def set_secret(self, profile_name, secret):
        self.values[profile_name] = secret

    def get_secret(self, profile_name):
        try:
            return self.values[profile_name]
        except KeyError as exc:
            raise CredentialNotFoundError(profile_name) from exc

    def delete_secret(self, profile_name):
        self.values.pop(profile_name, None)


class CliTests(unittest.TestCase):
    def test_import_has_no_cli_or_network_side_effects(self):
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-c", "import orbitrelay; import orbitrelay.cli"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_main_wires_environment_cli_and_agent_without_network(self):
        fake_client = Mock(name="client")
        output = StringIO()

        with tempfile.TemporaryDirectory() as workspace:
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}) as dotenv_values,
                patch("orbitrelay.cli.OpenAI", return_value=fake_client) as openai,
                patch(
                    "orbitrelay.cli.run_agent", return_value="final answer"
                ) as run_agent,
                redirect_stdout(output),
            ):
                exit_code = cli.main(
                    [
                        "inspect the calculator",
                        "--workspace",
                        workspace,
                        "--verbose",
                    ],
                    profile_repository=ProfileRepository(
                        Path(workspace) / "profiles.json"
                    ),
                )

        dotenv_values.assert_called_once_with(interpolate=False)
        openai.assert_called_once_with(
            api_key="secret", base_url=DEFAULT_BASE_URL
        )
        run_agent.assert_called_once_with(
            fake_client,
            "inspect the calculator",
            DEFAULT_MODEL,
            working_directory=str(Path(workspace).resolve()),
            verbose=True,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "final answer\n")

    def test_main_rejects_missing_key_before_client_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI") as openai,
            ):
                with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
                    cli.main(
                        ["inspect"],
                        profile_repository=ProfileRepository(
                            Path(directory) / "profiles.json"
                        ),
                    )

        openai.assert_not_called()

    def test_workspace_defaults_to_current_directory(self):
        self.assertEqual(cli.resolve_workspace(None), str(Path.cwd().resolve()))

    def test_invalid_workspace_is_rejected_before_client_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing"
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI") as openai,
            ):
                with self.assertRaisesRegex(ValueError, "Workspace is not a directory"):
                    cli.main(["inspect", "--workspace", str(missing)])

        openai.assert_not_called()

    def test_explicit_profile_overrides_selection_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(profile("selected", "https://selected.test/v1"))
            repository.save(profile("explicit", "https://explicit.test/v1"))
            repository.select("selected")
            credentials = FakeCredentialStore(
                {
                    repository.credential_key("selected"): "selected-secret",
                    repository.credential_key("explicit"): "explicit-secret",
                }
            )
            fake_client = Mock(name="client")

            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "env-secret",
                        "OPENAI_BASE_URL": "https://environment.test/v1",
                        "OPENAI_MODEL": "environment-model",
                    },
                    clear=True,
                ),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI", return_value=fake_client) as openai,
                patch("orbitrelay.cli.run_agent", return_value="done"),
                redirect_stdout(StringIO()),
            ):
                cli.main(
                    ["inspect", "--profile", "explicit"],
                    profile_repository=repository,
                    credential_store=credentials,
                )

        openai.assert_called_once_with(
            api_key="explicit-secret", base_url="https://explicit.test/v1"
        )

    def test_saved_selection_overrides_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(profile("selected", "https://selected.test/v1"))
            repository.select("selected")
            fake_client = Mock(name="client")

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "env-secret"}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value={}),
                patch("orbitrelay.cli.OpenAI", return_value=fake_client) as openai,
                patch("orbitrelay.cli.run_agent", return_value="done"),
                redirect_stdout(StringIO()),
            ):
                cli.main(
                    ["inspect"],
                    profile_repository=repository,
                    credential_store=FakeCredentialStore(
                        {repository.credential_key("selected"): "selected-secret"}
                    ),
                )

        openai.assert_called_once_with(
            api_key="selected-secret", base_url="https://selected.test/v1"
        )

    def test_rejects_deferred_auth_kind_before_client_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(
                profile(
                    "ollama",
                    "http://127.0.0.1:11434/v1",
                    auth_kind=AuthKind.LOCAL_NONE,
                )
            )
            with patch("orbitrelay.cli.OpenAI") as openai:
                with self.assertRaisesRegex(ValueError, "not executable in P1"):
                    cli.main(
                        ["inspect", "--profile", "ollama"],
                        profile_repository=repository,
                        credential_store=FakeCredentialStore(),
                    )

        openai.assert_not_called()

    def test_rejects_missing_profile_credential_before_client_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(profile("work", "https://example.test/v1"))
            with patch("orbitrelay.cli.OpenAI") as openai:
                with self.assertRaises(CredentialNotFoundError):
                    cli.main(
                        ["inspect", "--profile", "work"],
                        profile_repository=repository,
                        credential_store=FakeCredentialStore(),
                    )

        openai.assert_not_called()

    def test_empty_explicit_profile_does_not_fall_back_to_saved_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(profile("selected", "https://selected.test/v1"))
            repository.select("selected")
            with patch("orbitrelay.cli.OpenAI") as openai:
                with self.assertRaises(ProfileNotFoundError):
                    cli.main(
                        ["inspect", "--profile", ""],
                        profile_repository=repository,
                        credential_store=FakeCredentialStore(
                            {repository.credential_key("selected"): "selected-secret"}
                        ),
                    )

        openai.assert_not_called()

    def test_dotenv_cannot_redirect_profile_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            trusted_home = Path(directory) / "trusted"
            untrusted_home = Path(directory) / "untrusted"
            ProfileRepository(trusted_home / "profiles.json").save(
                profile("trusted", "https://trusted.test/v1")
            )
            ProfileRepository(untrusted_home / "profiles.json").save(
                profile("untrusted", "https://untrusted.test/v1")
            )
            output = StringIO()

            with (
                patch.dict(
                    os.environ,
                    {"ORBITRELAY_HOME": str(trusted_home)},
                    clear=True,
                ),
                patch(
                    "orbitrelay.cli.dotenv_values",
                    return_value={"ORBITRELAY_HOME": str(untrusted_home)},
                ),
                redirect_stdout(output),
            ):
                cli.main(["profile", "list"])

        self.assertIn("trusted", output.getvalue())
        self.assertNotIn("untrusted", output.getvalue())

    def test_dotenv_does_not_mix_endpoint_with_process_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            fake_client = Mock(name="client")

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "process-key"}, clear=True),
                patch(
                    "orbitrelay.cli.dotenv_values",
                    return_value={
                        "OPENAI_BASE_URL": "https://project-controlled.test/v1",
                        "OPENAI_MODEL": "project-model",
                    },
                ),
                patch("orbitrelay.cli.OpenAI", return_value=fake_client) as openai,
                patch("orbitrelay.cli.run_agent", return_value="done"),
                redirect_stdout(StringIO()),
            ):
                cli.main(["inspect"], profile_repository=repository)

        openai.assert_called_once_with(
            api_key="process-key", base_url=DEFAULT_BASE_URL
        )

    def test_dotenv_transport_variables_never_mutate_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            repository.save(profile("work", "https://profile.test/v1"))
            credentials = FakeCredentialStore(
                {repository.credential_key("work"): "profile-secret"}
            )
            dotenv = {
                "OPENAI_API_KEY": "dotenv-key",
                "HTTPS_PROXY": "https://project-proxy.test",
                "ALL_PROXY": "https://project-proxy.test",
                "SSL_CERT_FILE": "/project/controlled-ca.pem",
            }

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("orbitrelay.cli.dotenv_values", return_value=dotenv),
                patch("orbitrelay.cli.OpenAI") as openai,
                patch("orbitrelay.cli.run_agent", return_value="done"),
                redirect_stdout(StringIO()),
            ):
                cli.main(
                    ["inspect", "--profile", "work"],
                    profile_repository=repository,
                    credential_store=credentials,
                )
                self.assertNotIn("HTTPS_PROXY", os.environ)
                self.assertNotIn("ALL_PROXY", os.environ)
                self.assertNotIn("SSL_CERT_FILE", os.environ)

            openai.assert_called_once_with(
                api_key="profile-secret", base_url="https://profile.test/v1"
            )

    def test_uses_dotenv_when_process_has_no_openai_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "orbitrelay.cli.dotenv_values",
                    return_value={"OPENAI_API_KEY": "dotenv-key"},
                ),
                patch("orbitrelay.cli.OpenAI") as openai,
                patch("orbitrelay.cli.run_agent", return_value="done"),
                redirect_stdout(StringIO()),
            ):
                cli.main(["inspect"], profile_repository=repository)

        openai.assert_called_once_with(
            api_key="dotenv-key", base_url=DEFAULT_BASE_URL
        )

    def test_partial_process_source_does_not_merge_dotenv_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProfileRepository(Path(directory) / "profiles.json")
            with (
                patch.dict(os.environ, {"OPENAI_MODEL": "process-model"}, clear=True),
                patch(
                    "orbitrelay.cli.dotenv_values",
                    return_value={"OPENAI_API_KEY": "dotenv-key"},
                ),
                patch("orbitrelay.cli.OpenAI") as openai,
            ):
                with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
                    cli.main(["inspect"], profile_repository=repository)

        openai.assert_not_called()

    def test_dotenv_cannot_interpolate_inherited_secrets(self):
        for field in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
            with self.subTest(field=field):
                dotenv = {
                    "OPENAI_API_KEY": "dotenv-key",
                    "OPENAI_BASE_URL": DEFAULT_BASE_URL,
                    "OPENAI_MODEL": DEFAULT_MODEL,
                    field: "${AWS_SECRET_ACCESS_KEY}",
                }
                with (
                    patch.dict(
                        os.environ,
                        {"AWS_SECRET_ACCESS_KEY": "must-not-expand"},
                        clear=True,
                    ),
                    patch("orbitrelay.cli.dotenv_values", return_value=dotenv),
                    patch("orbitrelay.cli.OpenAI") as openai,
                ):
                    with self.assertRaisesRegex(ValueError, "interpolation"):
                        cli.main(["inspect"])

                openai.assert_not_called()


if __name__ == "__main__":
    unittest.main()
