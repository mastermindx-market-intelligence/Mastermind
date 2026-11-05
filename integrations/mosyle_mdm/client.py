"""Bounded read-only Mosyle Business inventory adapter."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

import httpx

ORIGIN = "https://businessapi.mosyle.com"
DEVICES_URL = ORIGIN + "/v1/devices"
LOGIN_URL = ORIGIN + "/v1/login"
FLEET_SCHEMA = "mastermind.mosyle_fleet_snapshot.v1"
DEVICE_SCHEMA = "mastermind.mosyle_device.v1"
MAX_DEVICES = 500
MAX_PAGES = 10
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_LOGIN_BYTES = 64 * 1024
TIMEOUT_SECONDS = 15.0
AUTH_MODE_JWT = "jwt"
AUTH_MODE_SESSION_LOGIN = "session_login"
AUTH_MODES = frozenset({AUTH_MODE_JWT, AUTH_MODE_SESSION_LOGIN})
DEVICE_COLUMNS = (
    "serial_number", "device_name", "device_model", "model_name", "device_type",
    "os", "osversion", "BuildVersion", "date_last_beat", "date_checkin",
    "status", "ManagementStatus", "is_supervised", "enrollment_type",
    "total_disk", "available_disk", "battery", "needosupdate", "OSUpdateStatus",
    "AvailableOSUpdates", "SystemIntegrityProtectionEnabled", "LocalHostName",
    "HostName", "asset_tag", "tags",
)


class MosyleTelemetryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class MosyleCredential:
    auth_mode: str
    access_token: str = field(repr=False)
    email: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.auth_mode) is not str or self.auth_mode not in AUTH_MODES:
            raise ValueError("Mosyle authentication mode is unavailable")
        if not _secret(self.access_token):
            raise ValueError("Mosyle access token is unavailable")
        if self.auth_mode == AUTH_MODE_JWT:
            if self.email is not None or self.password is not None:
                raise ValueError("Mosyle JWT mode refuses user credentials")
            return
        if not _email(self.email) or not _password(self.password):
            raise ValueError("Mosyle session login credential is unavailable")


class CredentialSource(Protocol):
    async def resolve(self) -> MosyleCredential: ...


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    body: bytes
    authorization: str | None = None


class JsonPoster(Protocol):
    async def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any],
        timeout_seconds: float, max_response_bytes: int,
    ) -> HttpResult: ...


class HttpxJsonPoster:
    async def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any],
        timeout_seconds: float, max_response_bytes: int,
    ) -> HttpResult:
        if url not in {DEVICES_URL, LOGIN_URL}:
            raise MosyleTelemetryError("invalid_request", "Mosyle endpoint is not admitted")
        chunks, total = [], 0
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(
                "POST", url, headers=dict(headers), json=dict(body)
            ) as response:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_response_bytes:
                        raise MosyleTelemetryError(
                            "output_too_large", "Mosyle response exceeds the page budget"
                        )
                    chunks.append(chunk)
        authorization = response.headers.get("authorization")
        if authorization is not None and (
            len(authorization.encode("utf-8")) > 16384
            or "\r" in authorization
            or "\n" in authorization
        ):
            raise MosyleTelemetryError(
                "invalid_response", "Mosyle authorization response header is invalid"
            )
        return HttpResult(response.status_code, b"".join(chunks), authorization)


class MosyleInventoryClient:
    def __init__(
        self, credentials: CredentialSource, *, poster: JsonPoster | None = None, clock=None
    ) -> None:
        self._credentials = credentials
        self._poster = poster or HttpxJsonPoster()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def list_macos_devices(self) -> dict[str, Any]:
        credential = await self._credential()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "accessToken": credential.access_token,
        }
        if credential.auth_mode == AUTH_MODE_SESSION_LOGIN:
            headers["Authorization"] = "Bearer " + await self._login(credential)
        devices: list[dict[str, Any]] = []
        declared_rows: int | None = None
        pages = 0
        for page_number in range(1, MAX_PAGES + 1):
            page = await self._page(headers, page_number)
            pages += 1
            if declared_rows is None:
                declared_rows = page["rows"]
                if declared_rows > MAX_DEVICES:
                    raise MosyleTelemetryError(
                        "output_too_large", "Mosyle inventory exceeds device budget"
                    )
            elif page["rows"] != declared_rows:
                raise MosyleTelemetryError(
                    "invalid_response", "Mosyle row count changed during pagination"
                )
            if page["page"] != page_number:
                raise MosyleTelemetryError(
                    "invalid_response", "Mosyle page identity is inconsistent"
                )
            devices.extend(_device(row) for row in page["devices"])
            if len(devices) > MAX_DEVICES:
                raise MosyleTelemetryError(
                    "output_too_large", "Mosyle inventory exceeds device budget"
                )
            if len(devices) >= declared_rows:
                if len(devices) != declared_rows:
                    raise MosyleTelemetryError(
                        "invalid_response", "Mosyle row count is inconsistent"
                    )
                break
            if not page["devices"] or page["page_size"] <= 0:
                raise MosyleTelemetryError(
                    "invalid_response", "Mosyle pagination ended early"
                )
        else:
            raise MosyleTelemetryError(
                "output_too_large", "Mosyle inventory exceeds page budget"
            )
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise MosyleTelemetryError("clock_unavailable", "telemetry clock is unavailable")
        devices.sort(key=lambda item: (item["device_name"].casefold(), item["serial_number"]))
        return {
            "schema": FLEET_SCHEMA,
            "source": "mosyle_business",
            "generated_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "coverage": "macos",
            "complete": True,
            "device_count": len(devices),
            "page_count": pages,
            "devices": devices,
        }

    async def device(
        self, *, serial_number: str | None = None, hostname: str | None = None
    ) -> dict[str, Any]:
        if (serial_number is None) == (hostname is None):
            raise MosyleTelemetryError(
                "invalid_input", "exactly one device selector is required"
            )
        needle = _selector(serial_number if serial_number is not None else hostname)
        fleet = await self.list_macos_devices()
        if serial_number is not None:
            matches = [d for d in fleet["devices"] if d["serial_number"] == needle]
        else:
            folded = needle.casefold()
            matches = [
                d for d in fleet["devices"]
                if folded in {
                    d["device_name"].casefold(),
                    str(d.get("HostName") or "").casefold(),
                    str(d.get("LocalHostName") or "").casefold(),
                }
            ]
        if len(matches) != 1:
            raise MosyleTelemetryError(
                "not_found" if not matches else "ambiguous_device",
                "Mosyle device selector did not resolve to exactly one Mac",
            )
        return {
            "schema": DEVICE_SCHEMA,
            "source": fleet["source"],
            "generated_at": fleet["generated_at"],
            "coverage": "macos",
            "device": matches[0],
        }

    async def _credential(self) -> MosyleCredential:
        try:
            value = await self._credentials.resolve()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise MosyleTelemetryError(
                "credential_unavailable", "Mosyle credential is unavailable"
            ) from exc
        if not isinstance(value, MosyleCredential):
            raise MosyleTelemetryError(
                "credential_unavailable", "Mosyle credential is unavailable"
            )
        return value

    async def _login(self, credential: MosyleCredential) -> str:
        """Obtain one ephemeral bearer for this inventory read; never cache it."""
        request = {"email": credential.email, "password": credential.password}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "accessToken": credential.access_token,
        }
        try:
            result = await self._poster.post_json(
                url=LOGIN_URL,
                headers=headers,
                body=request,
                timeout_seconds=TIMEOUT_SECONDS,
                max_response_bytes=MAX_LOGIN_BYTES,
            )
        except asyncio.CancelledError:
            raise
        except MosyleTelemetryError:
            raise
        except Exception as exc:
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle session login is unavailable"
            ) from exc
        if not isinstance(result, HttpResult):
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle login transport result is invalid"
            )
        if result.status_code in {401, 403}:
            raise MosyleTelemetryError(
                "credential_refused", "Mosyle refused the session login credential"
            )
        if result.status_code != 200:
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle session login failed"
            )
        # Mosyle's session credential is carried by the response header.
        # Do not invent or depend on undocumented response-body identity fields.
        authorization = result.authorization
        if (
            not isinstance(authorization, str)
            or not authorization.startswith("Bearer ")
        ):
            raise MosyleTelemetryError(
                "invalid_response", "Mosyle login response is missing its bearer"
            )
        token = authorization[len("Bearer "):]
        if not _secret(token) or token.startswith("Bearer "):
            raise MosyleTelemetryError(
                "invalid_response", "Mosyle login bearer is invalid"
            )
        return token

    async def _page(self, headers: Mapping[str, str], number: int) -> dict[str, Any]:
        request = {
            "operation": "list",
            "options": {
                "os": "macos",
                "page": number,
                "specific_columns": list(DEVICE_COLUMNS),
            },
        }
        try:
            result = await self._poster.post_json(
                url=DEVICES_URL,
                headers=headers,
                body=request,
                timeout_seconds=TIMEOUT_SECONDS,
                max_response_bytes=MAX_PAGE_BYTES,
            )
        except asyncio.CancelledError:
            raise
        except MosyleTelemetryError:
            raise
        except Exception as exc:
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle telemetry is unavailable"
            ) from exc
        if not isinstance(result, HttpResult):
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle transport result is invalid"
            )
        if result.status_code in {401, 403}:
            raise MosyleTelemetryError(
                "credential_refused", "Mosyle refused the telemetry credential"
            )
        if result.status_code != 200:
            raise MosyleTelemetryError(
                "provider_unavailable", "Mosyle telemetry request failed"
            )
        try:
            raw = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise MosyleTelemetryError(
                "invalid_response", "Mosyle response is not JSON"
            ) from exc
        return _page_shape(raw)


def _page_shape(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or raw.get("status") != "OK":
        raise MosyleTelemetryError("invalid_response", "Mosyle response status is invalid")
    response = raw.get("response")
    if isinstance(response, Mapping):
        page = response
    elif (
        isinstance(response, list)
        and len(response) == 1
        and isinstance(response[0], Mapping)
    ):
        page = response[0]
    else:
        raise MosyleTelemetryError("invalid_response", "Mosyle response envelope is invalid")
    devices = page.get("devices")
    rows, size, number = page.get("rows"), page.get("page_size"), page.get("page")
    if (
        not isinstance(devices, list)
        or any(not isinstance(x, Mapping) for x in devices)
        or isinstance(rows, bool) or not isinstance(rows, int) or rows < 0
        or isinstance(size, bool) or not isinstance(size, int) or size < 0
        or isinstance(number, bool) or not isinstance(number, int) or number < 1
    ):
        raise MosyleTelemetryError("invalid_response", "Mosyle device page is invalid")
    return {"devices": devices, "rows": rows, "page_size": size, "page": number}


def _device(raw: Mapping[str, Any]) -> dict[str, Any]:
    out = {
        "serial_number": _text(raw.get("serial_number"), "serial_number", 128),
        "device_name": _text(raw.get("device_name"), "device_name", 256),
    }
    for field in DEVICE_COLUMNS:
        if field not in out:
            out[field] = _value(raw.get(field), field)
    return out


def _value(value: Any, field: str) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if field == "tags":
        if isinstance(value, str):
            return [x.strip()[:128] for x in value.split(",") if x.strip()][:64]
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return [x[:128] for x in value[:64]]
    if isinstance(value, str) and len(value) <= 4096:
        return value
    if isinstance(value, (list, dict)):
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if len(encoded.encode("utf-8")) <= 4096:
            return value
    raise MosyleTelemetryError("invalid_response", f"Mosyle {field} field is invalid")


def _text(value: Any, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum
    ):
        raise MosyleTelemetryError("invalid_response", f"Mosyle {field} is invalid")
    return value


def _selector(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > 256
    ):
        raise MosyleTelemetryError("invalid_input", "device selector is invalid")
    return value


def _email(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.strip() == value
        and 3 <= len(value) <= 320
        and "@" in value
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
    )


def _password(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 16384
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
    )


def _secret(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.strip() == value
        and 8 <= len(value) <= 16384
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
    )
