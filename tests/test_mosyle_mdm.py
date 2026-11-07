import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from integrations.mosyle_mdm.client import (
    AUTH_MODE_JWT,
    AUTH_MODE_SESSION_LOGIN,
    DEVICE_COLUMNS,
    DEVICES_URL,
    LOGIN_URL,
    HttpResult,
    MosyleCredential,
    MosyleInventoryClient,
    MosyleTelemetryError,
)


class Credentials:
    def __init__(self, credential=None, error=None):
        self.credential = credential or MosyleCredential(
            AUTH_MODE_JWT, "a" * 32
        )
        self.error = error
        self.calls = 0

    async def resolve(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.credential


class Poster:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def post_json(
        self, *, url, headers, body, timeout_seconds, max_response_bytes
    ):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout_seconds,
                "max": max_response_bytes,
            }
        )
        value = self.results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(
    devices, *, rows=None, page=1, page_size=None, status="OK", direct=False
):
    payload = {
        "devices": devices,
        "rows": len(devices) if rows is None else rows,
        "page": page,
        "page_size": len(devices) if page_size is None else page_size,
    }
    response_value = payload if direct else [payload]
    return HttpResult(
        200,
        json.dumps({"status": status, "response": response_value}).encode(),
    )


def login_response(*, status=200, body=b"", authorization="Bearer " + "b" * 32):
    if not isinstance(body, bytes):
        body = json.dumps(body).encode()
    return HttpResult(status, body, authorization)


def device(serial="SERIAL1", name="mini-01", **extra):
    return {"serial_number": serial, "device_name": name, **extra}


def run(awaitable):
    return asyncio.run(awaitable)


def session_credential():
    return MosyleCredential(
        AUTH_MODE_SESSION_LOGIN,
        "a" * 32,
        "api-user@example.com",
        "secret123",
    )


def test_session_login_then_list_projects_only_allowlisted_fields():
    raw = device(
        HostName="mini-01.local",
        osversion="26.0",
        ManagementStatus="Managed",
        tags="worker, mini",
        username="must-not-leak",
        ethernet_mac="must-not-leak",
        ip="must-not-leak",
    )
    poster = Poster([login_response(), response([raw])])
    client = MosyleInventoryClient(
        Credentials(session_credential()),
        poster=poster,
        clock=lambda: datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc),
    )

    result = run(client.list_macos_devices())

    assert result["schema"] == "mastermind.mosyle_fleet_snapshot.v1"
    assert result["device_count"] == 1
    projected = result["devices"][0]
    assert projected["serial_number"] == "SERIAL1"
    assert projected["device_name"] == "mini-01"
    assert projected["tags"] == ["worker", "mini"]
    assert "username" not in projected
    assert "ethernet_mac" not in projected
    assert "ip" not in projected

    login, listing = poster.calls
    assert login["url"] == LOGIN_URL
    assert login["headers"]["accessToken"] == "a" * 32
    assert "Authorization" not in login["headers"]
    assert login["body"] == {
        "email": "api-user@example.com",
        "password": "secret123",
    }

    assert listing["url"] == DEVICES_URL
    assert listing["headers"]["accessToken"] == "a" * 32
    assert listing["headers"]["Authorization"] == "Bearer " + "b" * 32
    assert listing["body"] == {
        "operation": "list",
        "options": {
            "os": "macos",
            "page": 1,
            "specific_columns": list(DEVICE_COLUMNS),
        },
    }
    encoded = json.dumps(result)
    assert "api-user@example.com" not in encoded
    assert "secret123" not in encoded
    assert "b" * 32 not in encoded


def test_login_response_body_is_not_an_identity_oracle():
    poster = Poster(
        [
            login_response(body=b""),
            response([device()]),
        ]
    )
    result = run(
        MosyleInventoryClient(
            Credentials(session_credential()), poster=poster
        ).list_macos_devices()
    )
    assert result["device_count"] == 1


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer ", "Bearer Bearer " + "b" * 32],
)
def test_session_login_requires_one_valid_bearer_header(authorization):
    client = MosyleInventoryClient(
        Credentials(session_credential()),
        poster=Poster([login_response(authorization=authorization)]),
    )
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == "invalid_response"


@pytest.mark.parametrize(
    "status,code",
    [(401, "credential_refused"), (403, "credential_refused"), (500, "provider_unavailable")],
)
def test_session_login_http_failures_are_typed(status, code):
    client = MosyleInventoryClient(
        Credentials(session_credential()),
        poster=Poster([login_response(status=status)]),
    )
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == code
    assert "offline" not in caught.value.message.lower()


def test_jwt_mode_omits_login_and_authorization_header():
    poster = Poster([response([device()])])
    client = MosyleInventoryClient(
        Credentials(MosyleCredential(AUTH_MODE_JWT, "a" * 32)),
        poster=poster,
    )
    result = run(client.list_macos_devices())
    assert result["device_count"] == 1
    assert len(poster.calls) == 1
    assert poster.calls[0]["url"] == DEVICES_URL
    headers = poster.calls[0]["headers"]
    assert headers["accessToken"] == "a" * 32
    assert "Authorization" not in headers


@pytest.mark.parametrize(
    "args",
    [
        ("unknown", "a" * 32, None, None),
        (AUTH_MODE_JWT, "a" * 32, "api@example.com", None),
        (AUTH_MODE_JWT, "a" * 32, None, "password"),
        (AUTH_MODE_SESSION_LOGIN, "a" * 32, None, "password"),
        (AUTH_MODE_SESSION_LOGIN, "a" * 32, "api@example.com", None),
    ],
)
def test_auth_mode_is_closed_and_mode_specific(args):
    with pytest.raises(ValueError):
        MosyleCredential(*args)


def test_credential_repr_redacts_all_secret_and_identity_fields():
    credential = session_credential()
    shown = repr(credential)
    assert "a" * 8 not in shown
    assert "api-user@example.com" not in shown
    assert "secret123" not in shown
    assert "session_login" in shown


def test_direct_response_object_shape_is_accepted():
    poster = Poster([response([device()], direct=True)])
    result = run(MosyleInventoryClient(Credentials(), poster=poster).list_macos_devices())
    assert result["device_count"] == 1
    assert result["devices"][0]["serial_number"] == "SERIAL1"


def test_pagination_is_bounded_and_sorted():
    poster = Poster(
        [
            response([device("S2", "Zulu")], rows=2, page=1, page_size=1),
            response([device("S1", "alpha")], rows=2, page=2, page_size=1),
        ]
    )
    result = run(MosyleInventoryClient(Credentials(), poster=poster).list_macos_devices())
    assert result["page_count"] == 2
    assert [d["serial_number"] for d in result["devices"]] == ["S1", "S2"]


@pytest.mark.parametrize(
    "status,code",
    [(401, "credential_refused"), (403, "credential_refused"), (500, "provider_unavailable")],
)
def test_device_http_failure_is_telemetry_failure_not_host_status(status, code):
    client = MosyleInventoryClient(
        Credentials(), poster=Poster([HttpResult(status, b"{}")])
    )
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == code
    assert "offline" not in caught.value.message.lower()


def test_credential_failure_is_typed_and_secret_free():
    client = MosyleInventoryClient(
        Credentials(error=RuntimeError("secret provider detail")),
        poster=Poster([]),
    )
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == "credential_unavailable"
    assert "secret provider detail" not in caught.value.message


@pytest.mark.parametrize(
    "payload",
    [
        HttpResult(200, b"not-json"),
        HttpResult(200, json.dumps({"status": "ERROR", "response": []}).encode()),
        HttpResult(200, json.dumps({"status": "OK", "response": []}).encode()),
    ],
)
def test_malformed_provider_response_refuses(payload):
    client = MosyleInventoryClient(Credentials(), poster=Poster([payload]))
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == "invalid_response"


def test_device_selection_by_serial_and_hostname():
    raw = device("S1", "friendly", HostName="mini-01.local", LocalHostName="mini-01")
    client = MosyleInventoryClient(Credentials(), poster=Poster([response([raw])]))
    by_serial = run(client.device(serial_number="S1"))
    assert by_serial["device"]["device_name"] == "friendly"

    client = MosyleInventoryClient(Credentials(), poster=Poster([response([raw])]))
    by_host = run(client.device(hostname="MINI-01"))
    assert by_host["device"]["serial_number"] == "S1"


def test_device_selector_requires_exactly_one_selector():
    client = MosyleInventoryClient(Credentials(), poster=Poster([]))
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.device())
    assert caught.value.code == "invalid_input"
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.device(serial_number="S1", hostname="mini"))
    assert caught.value.code == "invalid_input"


def test_declared_inventory_over_budget_refuses_before_second_page():
    poster = Poster([response([device()], rows=501, page=1, page_size=1)])
    client = MosyleInventoryClient(Credentials(), poster=poster)
    with pytest.raises(MosyleTelemetryError) as caught:
        run(client.list_macos_devices())
    assert caught.value.code == "output_too_large"
    assert len(poster.calls) == 1


def test_only_read_endpoints_and_operations_are_present():
    source = (
        Path(__file__).parents[1] / "integrations/mosyle_mdm/client.py"
    ).read_text()
    assert 'LOGIN_URL = ORIGIN + "/v1/login"' in source
    assert 'DEVICES_URL = ORIGIN + "/v1/devices"' in source
    assert '"operation": "list"' in source
    for forbidden in (
        '"wipe"',
        '"restart"',
        '"shutdown"',
        '"lock"',
        '"assign"',
        '"install"',
        "activation_lock_bypass",
        "ethernet_mac",
        "wifi_mac",
        "username",
    ):
        assert forbidden not in source
