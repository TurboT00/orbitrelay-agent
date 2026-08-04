"""D-01 workspace path privacy classification.

Classify confined workspace paths before protected bytes are loaded.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum

from .path_safety import resolve_path_within

PRIVACY_DENIED_MESSAGE = "Error: protected path denied"
PRIVACY_DENIED_REASON = "privacy_denied"


class PathSensitivity(StrEnum):
    ORDINARY = "ordinary"
    SENSITIVE = "sensitive"
    ABSOLUTE_DENY = "absolute_deny"


@dataclass(frozen=True, slots=True)
class PathClassification:
    sensitivity: PathSensitivity
    rule_id: str | None = None

    @property
    def allowed(self) -> bool:
        return self.sensitivity is PathSensitivity.ORDINARY

    @property
    def deny_message(self) -> str:
        if self.allowed:
            raise RuntimeError("ordinary paths are not denied")
        if self.rule_id is None:
            return PRIVACY_DENIED_MESSAGE
        return f"{PRIVACY_DENIED_MESSAGE} [{self.rule_id}]"


_AP01 = re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)([._-].+)?$")
_AP02_SUFFIXES = (
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
    ".keychain",
    ".keychain-db",
)
_AP03_NAMES = frozenset({".git-credentials", ".netrc", ".npmrc", ".pypirc"})
_AP04_SUFFIXES = (
    (".aws", "credentials"),
    (".docker", "config.json"),
    (".kube", "config"),
    (".config", "gcloud", "application_default_credentials.json"),
)
_AP05 = re.compile(r"^(.*[._-])?service[._-]?account([._-].*)?\.json$")
_AP06_SEQUENCE = (".gnupg", "private-keys-v1.d")

_SP02 = re.compile(
    r"(^|[._-])(secret|secrets|token|tokens|password|passwd|credential|"
    r"credentials|apikey|api_key)($|[._-])"
)
_SP04_COMPONENTS = frozenset(
    {".git", ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".terraform"}
)


def classify_relative_path(relative_path: str) -> PathClassification:
    """Classify a workspace-relative path using the D-01 catalog."""
    parts = _casefolded_parts(relative_path)
    if not parts:
        return PathClassification(PathSensitivity.ORDINARY)
    absolute = _absolute_deny(parts)
    if absolute is not None:
        return PathClassification(PathSensitivity.ABSOLUTE_DENY, absolute)
    sensitive = _sensitive(parts)
    if sensitive is not None:
        return PathClassification(PathSensitivity.SENSITIVE, sensitive)
    return PathClassification(PathSensitivity.ORDINARY)


def classify_workspace_target(
    working_directory: str, relative_path: str
) -> tuple[PathClassification, str | None]:
    """Confine then classify. Returns (classification, confinement_error)."""
    if not isinstance(relative_path, str) or not relative_path:
        return PathClassification(PathSensitivity.ORDINARY), None
    working_real, target_real, valid = resolve_path_within(
        working_directory, relative_path
    )
    if not valid:
        return (
            PathClassification(PathSensitivity.ORDINARY),
            f'Error: Cannot read "{relative_path}" as it is outside the permitted working directory',
        )
    rel = os.path.relpath(target_real, working_real)
    if rel == os.curdir:
        return PathClassification(PathSensitivity.ORDINARY), None
    return classify_relative_path(rel.replace(os.sep, "/")), None


def deny_protected_read(
    working_directory: str, relative_path: str
) -> str | None:
    """Return a secret-free denial message when a read must fail closed."""
    classification, confinement_error = classify_workspace_target(
        working_directory, relative_path
    )
    if confinement_error is not None:
        return confinement_error
    if classification.allowed:
        return None
    return classification.deny_message


def _casefolded_parts(relative_path: str) -> tuple[str, ...]:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized or normalized == ".":
        return ()
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part.casefold())
    return tuple(parts)


def _absolute_deny(parts: tuple[str, ...]) -> str | None:
    basename = parts[-1]
    # Path-component rules first so nested private-key stores keep their rule id.
    if _contains_sequence(parts, _AP06_SEQUENCE):
        return "AP-06"
    for sequence in _AP04_SUFFIXES:
        if len(parts) >= len(sequence) and parts[-len(sequence) :] == sequence:
            return "AP-04"
    if _AP01.fullmatch(basename):
        return "AP-01"
    if any(basename.endswith(suffix) for suffix in _AP02_SUFFIXES):
        return "AP-02"
    if basename in _AP03_NAMES:
        return "AP-03"
    if _AP05.fullmatch(basename):
        return "AP-05"
    return None


def _sensitive(parts: tuple[str, ...]) -> str | None:
    basename = parts[-1]
    if basename == ".env" or basename.startswith(".env."):
        return "SP-01"
    if _SP02.search(basename):
        return "SP-02"
    if basename.endswith(".pem"):
        return "SP-03"
    if any(part in _SP04_COMPONENTS for part in parts):
        return "SP-04"
    if _contains_sequence(parts, (".config", "gcloud")):
        return "SP-05"
    if (
        basename == "terraform.tfstate"
        or basename.startswith("terraform.tfstate.")
        or basename.endswith(".tfstate")
        or ".tfstate." in basename
    ):
        return "SP-06"
    if (
        basename in {"terraform.tfvars", "terraform.tfvars.json"}
        or basename.endswith(".auto.tfvars")
        or basename.endswith(".auto.tfvars.json")
    ):
        return "SP-07"
    return None


def _contains_sequence(parts: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    size = len(sequence)
    if size == 0 or size > len(parts):
        return False
    return any(
        parts[index : index + size] == sequence
        for index in range(0, len(parts) - size + 1)
    )
