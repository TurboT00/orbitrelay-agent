# story: e03s02

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TextIO

from .config import XAI_DEFAULT_BASE_URL, XAI_DEFAULT_MODEL
from .credentials import (
    CredentialNotFoundError,
    CredentialStore,
    ProfileService,
    credential_store_or_default,
)
from .profile_store import ProfileNotFoundError, ProfileRepository
from .profiles import (
    REQUIRED_CAPABILITIES,
    AuthKind,
    ProviderProfile,
)


SUPERGROK_PROFILE_NAME = "supergrok"
XAI_OAUTH_ISSUER = "https://auth.x.ai"
XAI_OAUTH_DEVICE_URL = f"{XAI_OAUTH_ISSUER}/oauth2/device/code"
XAI_OAUTH_TOKEN_URL = f"{XAI_OAUTH_ISSUER}/oauth2/token"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_SCOPE = (
    "openid profile email offline_access grok-cli:access api:access "
    "conversations:read conversations:write"
)
XAI_OAUTH_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
DEFAULT_DEVICE_INTERVAL_SECONDS = 5.0
DEFAULT_DEVICE_MAX_WAIT_SECONDS = 900.0
REFRESH_SKEW_SECONDS = 120.0


class SuperGrokOAuthError(RuntimeError):
    """Base error for SuperGrok OAuth failures."""


class SuperGrokReauthRequired(SuperGrokOAuthError):
    """Refresh failed permanently; user must log in again."""


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]: ...


class UrlLibTransport:
    def __init__(self, opener: Any | None = None) -> None:
        self._opener = opener or urllib.request.build_opener()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, Any]]:
        data = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            request_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                **request_headers,
            }
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                body = response.read()
                status = getattr(response, "status", None) or response.getcode()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            raise SuperGrokOAuthError(f"OAuth request failed: {exc.reason}") from exc
        payload: dict[str, Any]
        if not body:
            payload = {}
        else:
            try:
                decoded = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SuperGrokOAuthError("OAuth response was not valid JSON") from exc
            if not isinstance(decoded, dict):
                raise SuperGrokOAuthError("OAuth response must be a JSON object")
            payload = decoded
        return int(status), payload


@dataclass(frozen=True)
class DeviceCodeChallenge:
    device_code: str
    user_code: str
    verification_uri: str
    interval: float
    expires_in: float


@dataclass(frozen=True)
class SuperGrokTokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: str = ""
    quarantined: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
                "token_type": self.token_type,
                "scope": self.scope,
                "quarantined": self.quarantined,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> SuperGrokTokenBundle:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SuperGrokOAuthError("Stored SuperGrok credential is corrupt") from exc
        if not isinstance(payload, dict):
            raise SuperGrokOAuthError("Stored SuperGrok credential is corrupt")
        try:
            access_token = str(payload["access_token"])
            refresh_token = str(payload["refresh_token"])
            expires_at = float(payload["expires_at"])
            token_type = str(payload.get("token_type", "Bearer"))
            scope = str(payload.get("scope", ""))
            quarantined = bool(payload.get("quarantined", False))
        except (KeyError, TypeError, ValueError) as exc:
            raise SuperGrokOAuthError("Stored SuperGrok credential is corrupt") from exc
        if not access_token or not refresh_token:
            raise SuperGrokOAuthError("Stored SuperGrok credential is corrupt")
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            scope=scope,
            quarantined=quarantined,
        )

    def with_quarantine(self) -> SuperGrokTokenBundle:
        return SuperGrokTokenBundle(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
            token_type=self.token_type,
            scope=self.scope,
            quarantined=True,
        )


@dataclass(frozen=True)
class SuperGrokAuthStatus:
    authenticated: bool
    profile_name: str = SUPERGROK_PROFILE_NAME
    expires_at: float | None = None
    quarantined: bool = False

    def message(self) -> str:
        if not self.authenticated:
            return "SuperGrok OAuth: logged out"
        if self.quarantined:
            return "SuperGrok OAuth: re-authentication required"
        return "SuperGrok OAuth: authenticated"


class SuperGrokOAuthClient:
    def __init__(
        self,
        transport: HttpTransport,
        *,
        device_url: str = XAI_OAUTH_DEVICE_URL,
        token_url: str = XAI_OAUTH_TOKEN_URL,
        client_id: str = XAI_OAUTH_CLIENT_ID,
        scope: str = XAI_OAUTH_SCOPE,
    ) -> None:
        self._transport = transport
        self._device_url = device_url
        self._token_url = token_url
        self._client_id = client_id
        self._scope = scope

    def request_device_code(self) -> DeviceCodeChallenge:
        status, payload = self._transport.request(
            "POST",
            self._device_url,
            form={"client_id": self._client_id, "scope": self._scope},
        )
        if status != 200:
            raise SuperGrokOAuthError(
                f"Device code request failed with HTTP {status}"
            )
        try:
            device_code = str(payload["device_code"])
            user_code = str(payload["user_code"])
            verification_uri = str(
                payload.get("verification_uri")
                or payload.get("verification_uri_complete")
                or ""
            )
            interval = float(payload.get("interval", DEFAULT_DEVICE_INTERVAL_SECONDS))
            expires_in = float(payload["expires_in"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SuperGrokOAuthError("Device code response was incomplete") from exc
        if not device_code or not user_code or not verification_uri:
            raise SuperGrokOAuthError("Device code response was incomplete")
        return DeviceCodeChallenge(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            interval=max(interval, 1.0),
            expires_in=expires_in,
        )

    def exchange_device_code(
        self, device_code: str, *, now: float | None = None
    ) -> SuperGrokTokenBundle | str:
        status, payload = self._transport.request(
            "POST",
            self._token_url,
            form={
                "grant_type": XAI_OAUTH_DEVICE_GRANT_TYPE,
                "device_code": device_code,
                "client_id": self._client_id,
            },
        )
        if status == 200:
            return self._bundle_from_token_payload(
                payload, time.time() if now is None else now
            )
        error = str(payload.get("error", ""))
        if error in {"authorization_pending", "slow_down"}:
            return error
        raise SuperGrokOAuthError(
            f"Device token exchange failed: {error or f'HTTP {status}'}"
        )

    def refresh(self, refresh_token: str, *, now: float | None = None) -> SuperGrokTokenBundle:
        status, payload = self._transport.request(
            "POST",
            self._token_url,
            form={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
            },
        )
        if status != 200:
            error = str(payload.get("error", f"HTTP {status}"))
            if status in {400, 401} or error == "invalid_grant":
                raise SuperGrokReauthRequired(
                    "SuperGrok refresh failed; re-authentication required"
                )
            raise SuperGrokOAuthError(f"Token refresh failed: {error}")
        return self._bundle_from_token_payload(
            payload, time.time() if now is None else now, refresh_token
        )

    def _bundle_from_token_payload(
        self,
        payload: Mapping[str, Any],
        now: float,
        previous_refresh_token: str | None = None,
    ) -> SuperGrokTokenBundle:
        try:
            access_token = str(payload["access_token"])
            refresh_token = str(payload.get("refresh_token") or previous_refresh_token or "")
            expires_in = float(payload.get("expires_in", 3600))
            token_type = str(payload.get("token_type", "Bearer"))
            scope = str(payload.get("scope", self._scope))
        except (KeyError, TypeError, ValueError) as exc:
            raise SuperGrokOAuthError("Token response was incomplete") from exc
        if not access_token or not refresh_token:
            raise SuperGrokOAuthError("Token response was incomplete")
        return SuperGrokTokenBundle(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=now + expires_in,
            token_type=token_type,
            scope=scope,
        )


def supergrok_profile() -> ProviderProfile:
    return ProviderProfile.create(
        name=SUPERGROK_PROFILE_NAME,
        base_url=XAI_DEFAULT_BASE_URL,
        model=XAI_DEFAULT_MODEL,
        auth_kind=AuthKind.SUBSCRIPTION_OAUTH,
        capabilities=REQUIRED_CAPABILITIES,
    )


class SuperGrokAuthService:
    def __init__(
        self,
        repository: ProfileRepository,
        credential_store: CredentialStore | None,
        client: SuperGrokOAuthClient,
        *,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        output: TextIO | None = None,
    ) -> None:
        self._repository = repository
        self._store = credential_store_or_default(credential_store)
        self._service = ProfileService(repository, self._store)
        self._client = client
        self._clock = clock
        self._sleeper = sleeper
        self._output = output

    def _emit(self, message: str) -> None:
        if self._output is not None:
            print(message, file=self._output)

    def _credential_key(self) -> str:
        return self._repository.credential_key(SUPERGROK_PROFILE_NAME)

    def _load_bundle(self) -> SuperGrokTokenBundle | None:
        try:
            secret = self._store.get_secret(self._credential_key())
        except CredentialNotFoundError:
            return None
        return SuperGrokTokenBundle.from_json(secret)

    def _save_bundle(self, bundle: SuperGrokTokenBundle) -> None:
        profile = supergrok_profile()
        secret = bundle.to_json()
        try:
            existing = self._repository.get(SUPERGROK_PROFILE_NAME)
        except ProfileNotFoundError:
            self._service.create(profile, secret=secret)
            return
        if existing.auth_kind is not AuthKind.SUBSCRIPTION_OAUTH:
            raise SuperGrokOAuthError(
                f'Profile "{SUPERGROK_PROFILE_NAME}" exists with auth kind '
                f'"{existing.auth_kind.value}"'
            )
        self._store.set_secret(self._credential_key(), secret)
        if (
            existing.base_url != profile.base_url
            or existing.model != profile.model
            or existing.capabilities != profile.capabilities
        ):
            self._repository.save(profile, replace=True)

    def login(
        self,
        *,
        max_wait_seconds: float = DEFAULT_DEVICE_MAX_WAIT_SECONDS,
    ) -> SuperGrokAuthStatus:
        challenge = self._client.request_device_code()
        self._emit(f"Open {challenge.verification_uri}")
        self._emit(f"Enter code: {challenge.user_code}")
        deadline = self._clock() + min(challenge.expires_in, max_wait_seconds)
        interval = challenge.interval
        while self._clock() < deadline:
            result = self._client.exchange_device_code(
                challenge.device_code, now=self._clock()
            )
            if isinstance(result, SuperGrokTokenBundle):
                self._save_bundle(result)
                self._emit("SuperGrok OAuth login succeeded.")
                return SuperGrokAuthStatus(
                    authenticated=True, expires_at=result.expires_at
                )
            if result == "slow_down":
                interval += 5.0
            self._sleeper(interval)
        raise SuperGrokOAuthError("SuperGrok device authorization timed out")

    def status(self) -> SuperGrokAuthStatus:
        bundle = self._load_bundle()
        if bundle is None:
            return SuperGrokAuthStatus(authenticated=False)
        return SuperGrokAuthStatus(
            authenticated=True,
            expires_at=bundle.expires_at,
            quarantined=bundle.quarantined,
        )

    def logout(self) -> SuperGrokAuthStatus:
        try:
            existing = self._repository.get(SUPERGROK_PROFILE_NAME)
        except ProfileNotFoundError:
            return SuperGrokAuthStatus(authenticated=False)
        if existing.auth_kind is AuthKind.SUBSCRIPTION_OAUTH:
            self._service.delete(SUPERGROK_PROFILE_NAME)
        else:
            raise SuperGrokOAuthError(
                f'Profile "{SUPERGROK_PROFILE_NAME}" is not a SuperGrok OAuth profile'
            )
        self._emit("SuperGrok OAuth logged out.")
        return SuperGrokAuthStatus(authenticated=False)

    def get_valid_access_token(self) -> str:
        bundle = self._load_bundle()
        if bundle is None:
            raise SuperGrokReauthRequired("SuperGrok OAuth login required")
        if bundle.quarantined:
            raise SuperGrokReauthRequired(
                "SuperGrok OAuth re-authentication required"
            )
        now = self._clock()
        if bundle.expires_at - REFRESH_SKEW_SECONDS > now:
            return bundle.access_token
        try:
            refreshed = self._client.refresh(bundle.refresh_token, now=now)
        except SuperGrokReauthRequired:
            self._store.set_secret(
                self._credential_key(), bundle.with_quarantine().to_json()
            )
            raise
        self._save_bundle(refreshed)
        return refreshed.access_token
