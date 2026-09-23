import asyncio
import json
from datetime import datetime, timezone

import pytest

from integrations.mosyle_mdm.client import (
    DEVICE_COLUMNS,
    DEVICES_URL,
    HttpResult,
    MosyleCredential,
    MosyleInventoryClient,
    MosyleTelemetryError,
)


class Credentials:
    def __init__(self, credential=None, error=None):
        self.credential = credential or MosyleCredential("a" * 32)
        self.error = error
        self.calls = 0

    async def resolve(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.credential


class Poster:
    def __init__(self, pages):
        self.pages = list(pages)
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
        value = self.pages.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(devices, *, rows=None, page=1, page_size=None, status="OK"):
    payload = {
        "devices": devices,
        "rows": len(devices) if rows is None else rows,
        "page": page,
        "page_size": len(devices) if page_size is None else page_size,
    }
    return HttpResult(
        200,
        json.dumps({"status": status, "response": [payload]}).encode(),
    )


def device(serial="SERIAL1", name="mini-01", **extra):
    return {"serial_number": serial, "device_name": name, **extra}


def run(awaitable):
    return asyncio.run(awaitable)


def test_list_projects_only_allowlisted_fields_and_fixed_request():
    raw = device(
        HostName="mini-01.local",
        osversion="26.0",
        ManagementStatus="Managed",
        tags="worker, mini",
        username="must-not-leak",
        ethernet_mac="must-not-leak",
        ip="must-not-leak",
    )
    credentials = Credentials(MosyleCredential("a" * 32, "b" * 32))
    poster = Poster([response([raw])])
    client = MosyleInventoryClient(
        credentials,
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

    call = poster.calls[0]
    assert call["url"] == DEVICES_URL
    assert call["headers"]["accessToken"] == "a" * 32
    assert call["headers"]["Authorization"] == "Bearer " + "b" * 32
    assert call["body"] == {
        "operation": "list",
        "options": {
            "os": "macos",
            "page": 1,
            "specific_columns": list(DEVICE_COLUMNS),
        },
    }


def test_pagination_is_bounded_and_sorted():
    poster = Poster(
        [
            response([device("S2", "Zulu")], rows=2, page=1, page_size=1),
            response([device("S1", "alpha")], rows=2, page=2, page_size=1),
        ]
    )
    client = MosyleInventoryClient(Credentials(), poster=poster)

    result = run(client.list_macos_devices())

    assert result["page_count"] == 2
    assert [d["serial_number"] for d in result["devices"]] == ["S1", "S2"]


@pytest.mark.parametrize("status,code", [(401, "credential_refused"), (403, "credential_refused"), (500, "provider_unavailable")])
def test_http_failure_is_telemetry_failure_not_host_status(status, code):
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


def test_no_mutating_operation_or_sensitive_field_is_in_source():
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "integrations/mosyle_mdm/client.py"
    ).read_text()
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
