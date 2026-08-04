"""D-01 workspace path privacy classification and discovery policy."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pathspec import PathSpec

from .path_safety import resolve_path_within

PRIVACY_DENIED_MESSAGE = "Error: protected path denied"
PRIVACY_DENIED_REASON = "privacy_denied"
OMITTED_ENTRIES_LINE = "protected entries omitted"
ORBITRELAY_IGNORE_NAME = ".orbitrelayignore"
GITIGNORE_NAME = ".gitignore"


class PathSensitivity(StrEnum):
    ORDINARY = "ordinary"
    SENSITIVE = "sensitive"
    ABSOLUTE_DENY = "absolute_deny"


@dataclass(frozen=True, slots=True)
class PathClassification:
    sensitivity: PathSensitivity
    rule_id: str | None = None
    authorized: bool = False

    @property
    def allowed(self) -> bool:
        if self.sensitivity is PathSensitivity.ABSOLUTE_DENY:
            return False
        if self.sensitivity is PathSensitivity.ORDINARY:
            return True
        return self.authorized

    @property
    def discoverable(self) -> bool:
        return self.allowed

    @property
    def deny_message(self) -> str:
        if self.allowed:
            raise RuntimeError("ordinary paths are not denied")
        if self.rule_id is None:
            return PRIVACY_DENIED_MESSAGE
        return f"{PRIVACY_DENIED_MESSAGE} [{self.rule_id}]"


@dataclass(frozen=True, slots=True)
class PrivacyAuthorization:
    """Process-scoped exact-file and subtree exceptions (e06s02/e06s03)."""

    exact_files: frozenset[str] = field(default_factory=frozenset)
    subtrees: frozenset[str] = field(default_factory=frozenset)

    def authorizes(self, relative_path: str) -> bool:
        path = _normalize_relative(relative_path)
        folded = path.casefold()
        if folded in self.exact_files:
            return True
        for subtree in self.subtrees:
            if folded == subtree or folded.startswith(f"{subtree}/"):
                return True
        return False


_AUTHORIZATION = PrivacyAuthorization()


def get_privacy_authorization() -> PrivacyAuthorization:
    return _AUTHORIZATION


def set_privacy_authorization(authorization: PrivacyAuthorization) -> None:
    global _AUTHORIZATION
    _AUTHORIZATION = authorization
    clear_workspace_policy_cache()


def clear_privacy_authorization() -> None:
    set_privacy_authorization(PrivacyAuthorization())


def authorize_exact_path(relative_path: str) -> None:
    path = _normalize_relative(relative_path).casefold()
    current = get_privacy_authorization()
    set_privacy_authorization(
        PrivacyAuthorization(
            exact_files=frozenset({*current.exact_files, path}),
            subtrees=current.subtrees,
        )
    )


def authorize_subtree(relative_path: str) -> None:
    path = _normalize_relative(relative_path).casefold().rstrip("/")
    current = get_privacy_authorization()
    set_privacy_authorization(
        PrivacyAuthorization(
            exact_files=current.exact_files,
            subtrees=frozenset({*current.subtrees, path}),
        )
    )


def declare_run_exception(
    workspace: str,
    relative_path: str,
    *,
    scope: str,
) -> str:
    """Validate and install one process-scoped sensitive-read exception.

    Returns the normalized workspace-relative path that was authorized.
    Absolute-deny paths, escapes, and missing targets fail closed.
    """
    if scope not in {"file", "subtree"}:
        raise ValueError('sensitive exception scope must be "file" or "subtree"')
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("sensitive exception path cannot be empty")
    working_real, target_real, valid = resolve_path_within(workspace, relative_path)
    if not valid:
        raise ValueError(
            f'sensitive exception path escapes the workspace: "{relative_path}"'
        )
    # Reject symlink targets that resolved outside already handled; also reject
    # declaring through a symlink leaf when the leaf itself is a symlink escape.
    rel = os.path.relpath(target_real, working_real).replace(os.sep, "/")
    if rel == os.curdir:
        raise ValueError("sensitive exception cannot target the workspace root")
    classification = classify_relative_path(rel, workspace_root=working_real)
    if classification.sensitivity is PathSensitivity.ABSOLUTE_DENY:
        raise ValueError(
            "sensitive exception cannot authorize absolute-deny credential material"
        )
    if scope == "file":
        if not os.path.isfile(target_real):
            raise ValueError(
                f'sensitive exception exact path must be an existing file: "{relative_path}"'
            )
        authorize_exact_path(rel)
    else:
        if not os.path.isdir(target_real):
            raise ValueError(
                f'sensitive exception subtree must be an existing directory: "{relative_path}"'
            )
        authorize_subtree(rel)
    return rel

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


@dataclass(frozen=True, slots=True)
class WorkspacePrivacyPolicy:
    workspace_root: str
    git_spec: PathSpec | None
    orbit_spec: PathSpec | None
    orbit_error: str | None

    def classify(self, relative_path: str) -> PathClassification:
        parts = _casefolded_parts(relative_path)
        if not parts:
            return PathClassification(PathSensitivity.ORDINARY)
        absolute = _absolute_deny(parts)
        if absolute is not None:
            return PathClassification(PathSensitivity.ABSOLUTE_DENY, absolute)
        sensitive = _sensitive_builtin(parts)
        if sensitive is None:
            sensitive = self._ignore_sensitive(relative_path)
        if sensitive is None:
            return PathClassification(PathSensitivity.ORDINARY)
        authorized = get_privacy_authorization().authorizes(relative_path)
        return PathClassification(
            PathSensitivity.SENSITIVE,
            sensitive,
            authorized=authorized,
        )

    def _ignore_sensitive(self, relative_path: str) -> str | None:
        if self.orbit_error is not None:
            return None
        path = _normalize_relative(relative_path)
        if self.orbit_spec is not None and self.orbit_spec.match_file(path):
            return "SP-08"
        if self.git_spec is not None and self.git_spec.match_file(path):
            return "SP-08"
        return None

    def policy_error_message(self) -> str | None:
        if self.orbit_error is None:
            return None
        return f"Error: invalid {ORBITRELAY_IGNORE_NAME}: {self.orbit_error}"


def load_workspace_privacy_policy(workspace_root: str) -> WorkspacePrivacyPolicy:
    root = Path(os.path.realpath(workspace_root))
    git_spec = _load_git_ignore_spec(root)
    orbit_spec, orbit_error = _load_orbitrelay_ignore(root)
    return WorkspacePrivacyPolicy(
        workspace_root=str(root),
        git_spec=git_spec,
        orbit_spec=orbit_spec,
        orbit_error=orbit_error,
    )


@lru_cache(maxsize=32)
def _cached_policy(workspace_root: str) -> WorkspacePrivacyPolicy:
    return load_workspace_privacy_policy(workspace_root)


def clear_workspace_policy_cache() -> None:
    _cached_policy.cache_clear()


def workspace_privacy_policy(workspace_root: str) -> WorkspacePrivacyPolicy:
    return _cached_policy(os.path.realpath(workspace_root))


def classify_relative_path(
    relative_path: str,
    *,
    workspace_root: str | None = None,
) -> PathClassification:
    """Classify a workspace-relative path using the D-01 catalog."""
    if workspace_root is None:
        parts = _casefolded_parts(relative_path)
        if not parts:
            return PathClassification(PathSensitivity.ORDINARY)
        absolute = _absolute_deny(parts)
        if absolute is not None:
            return PathClassification(PathSensitivity.ABSOLUTE_DENY, absolute)
        sensitive = _sensitive_builtin(parts)
        if sensitive is None:
            return PathClassification(PathSensitivity.ORDINARY)
        authorized = get_privacy_authorization().authorizes(relative_path)
        return PathClassification(
            PathSensitivity.SENSITIVE, sensitive, authorized=authorized
        )
    return workspace_privacy_policy(workspace_root).classify(relative_path)


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
            (
                f'Error: Cannot read "{relative_path}" as it is outside the '
                "permitted working directory"
            ),
        )
    rel = os.path.relpath(target_real, working_real)
    if rel == os.curdir:
        return PathClassification(PathSensitivity.ORDINARY), None
    relative = rel.replace(os.sep, "/")
    return classify_relative_path(relative, workspace_root=working_real), None


def deny_protected_read(
    working_directory: str, relative_path: str
) -> str | None:
    """Return a secret-free denial message when a read must fail closed."""
    policy = workspace_privacy_policy(working_directory)
    if policy.policy_error_message() is not None:
        return policy.policy_error_message()
    classification, confinement_error = classify_workspace_target(
        working_directory, relative_path
    )
    if confinement_error is not None:
        return confinement_error
    if classification.allowed:
        return None
    return classification.deny_message


def deny_protected_listing(
    working_directory: str, relative_directory: str
) -> str | None:
    """Deny listing a protected directory target (not the workspace root)."""
    policy = workspace_privacy_policy(working_directory)
    if policy.policy_error_message() is not None:
        return policy.policy_error_message()
    if not isinstance(relative_directory, str) or relative_directory in {"", "."}:
        return None
    classification, confinement_error = classify_workspace_target(
        working_directory, relative_directory
    )
    if confinement_error is not None:
        return confinement_error.replace("Cannot read", "Cannot list", 1)
    if classification.allowed:
        return None
    return classification.deny_message


def filter_listing_names(
    working_directory: str,
    directory: str,
    names: list[str],
) -> tuple[list[str], int]:
    """Return discoverable entry names and the omitted protected count."""
    base = _normalize_relative(directory)
    visible: list[str] = []
    omitted = 0
    for name in names:
        relative = name if base in {"", "."} else f"{base}/{name}"
        classification = classify_relative_path(
            relative, workspace_root=os.path.realpath(working_directory)
        )
        if classification.discoverable:
            visible.append(name)
        else:
            omitted += 1
    return visible, omitted


def _load_git_ignore_spec(root: Path) -> PathSpec | None:
    lines: list[str] = []
    ignore_path = root / GITIGNORE_NAME
    if ignore_path.is_file() and not ignore_path.is_symlink():
        try:
            lines.extend(ignore_path.read_text(encoding="utf-8").splitlines())
        except OSError:
            return None
    # Nested .gitignore files: prefix patterns with their directory.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Do not descend into VCS internals for rule loading.
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", ".hg", ".svn"}
            and not Path(dirpath, name).is_symlink()
        ]
        if dirpath == str(root):
            continue
        if GITIGNORE_NAME not in filenames:
            continue
        nested = Path(dirpath) / GITIGNORE_NAME
        if nested.is_symlink():
            continue
        rel_dir = Path(dirpath).resolve().relative_to(root).as_posix()
        try:
            nested_lines = nested.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in nested_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            negation = stripped.startswith("!")
            body = stripped[1:] if negation else stripped
            if body.startswith("/"):
                body = body[1:]
            prefixed = f"{rel_dir}/{body}"
            lines.append(f"!{prefixed}" if negation else prefixed)
    if not lines:
        return None
    return PathSpec.from_lines("gitignore", lines)


def _load_orbitrelay_ignore(
    root: Path,
) -> tuple[PathSpec | None, str | None]:
    path = root / ORBITRELAY_IGNORE_NAME
    if not path.is_file() or path.is_symlink():
        return None, None
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return None, f"unreadable ({exc})"
    patterns: list[str] = []
    for line_number, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            return None, f"negation is not allowed on line {line_number}"
        patterns.append(stripped)
    if not patterns:
        return None, None
    return PathSpec.from_lines("gitignore", patterns), None


def _normalize_relative(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized or normalized == ".":
        return "."
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) if parts else "."


def _casefolded_parts(relative_path: str) -> tuple[str, ...]:
    normalized = _normalize_relative(relative_path)
    if normalized == ".":
        return ()
    return tuple(part.casefold() for part in normalized.split("/"))


def _absolute_deny(parts: tuple[str, ...]) -> str | None:
    basename = parts[-1]
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


def _sensitive_builtin(parts: tuple[str, ...]) -> str | None:
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
