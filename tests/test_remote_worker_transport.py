from __future__ import annotations

import hashlib
import json
import ssl
import subprocess
from pathlib import Path

import pytest

from control_plane.remote_worker_transport import (
    BrokerTransportBinding,
    TransportEffect,
    TransportError,
    TransportValidationError,
    build_request,
    decode_frame,
    encode_frame,
    request_sha256,
    validate_request,
    validate_response,
)


HOST_REF = "a" * 64
IDENTITY = {
    "host_ref": HOST_REF,
    "job_id": "JOB-001",
    "attempt_id": "ATT-001",
    "worker_id": "WORKER-001",
    "operation_id": "OP-001",
}


def _request(**overrides: object) -> dict:
    request = build_request(IDENTITY, "status", {"run_id": "RUN-001"})
    request.update(overrides)
    return request


def test_builds_and_validates_closed_request() -> None:
    request = _request()
    validate_request(
        request,
        expected_host_ref=HOST_REF,
        allowed_worker_ids={"WORKER-001"},
        allowed_operations={"status"},
    )
    digest = hashlib.sha256(
        json.dumps(
            {key: value for key, value in request.items() if key != "request_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert request["request_sha256"] == digest
    assert request_sha256(request) == digest


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "other/v1"},
        {"schema_version": "unexpected"},
        {"host_ref": "b" * 64},
        {"job_id": "../JOB-002"},
        {"attempt_id": "ATT-002"},
        {"worker_id": "WORKER-002"},
        {"operation_id": "OP-002"},
        {"broker_operation": "start"},
        {"broker_request": {"run_id": float("nan")}},
        {"request_sha256": "0" * 64},
        {"extra": "refused"},
    ],
)
def test_request_refusals_are_closed_and_sanitized(mutation: dict) -> None:
    request = json.loads(json.dumps({**_request(), **mutation}, allow_nan=True))
    with pytest.raises(TransportValidationError) as raised:
        validate_request(
            request,
            expected_host_ref=HOST_REF,
            allowed_worker_ids={"WORKER-001"},
            allowed_operations={"status"},
        )
    assert "endpoint" not in str(raised.value)
    assert "sock" not in str(raised.value).lower()


def test_oversize_request_and_frame_refuse() -> None:
    request = _request(broker_request={"value": "x" * (1024 * 1024)})
    with pytest.raises(TransportValidationError, match="request exceeds"):
        validate_request(
            request,
            expected_host_ref=HOST_REF,
            allowed_worker_ids={"WORKER-001"},
            allowed_operations={"status"},
        )
    with pytest.raises(TransportValidationError, match="frame exceeds"):
        encode_frame(b"x" * (1024 * 1024 + 1))


def test_response_identity_drift_refuses_before_payload() -> None:
    request = _request()
    response = {
        "schema": "mastermind.remote_worker_broker_response/v1",
        "host_ref": HOST_REF,
        "job_id": "JOB-001",
        "attempt_id": "ATT-001",
        "worker_id": "WORKER-001",
        "operation_id": "OP-001",
        "broker_operation": "status",
        "request_sha256": request["request_sha256"],
        "outcome": "ok",
        "broker_response": {"secret": "not-visible"},
        "observed_at_ms": 1,
    }
    validate_response(response, request)
    response["worker_id"] = "WORKER-002"
    with pytest.raises(TransportValidationError, match="identity"):
        validate_response(response, request)


def test_length_frame_is_exact_and_closed() -> None:
    payload = b'{"closed":true}'
    frame = encode_frame(payload)
    assert frame[:4] == len(payload).to_bytes(4, "big")
    assert b"\n" not in frame
    assert decode_frame(frame) == payload
    with pytest.raises(TransportValidationError, match="trailing"):
        decode_frame(frame + b"x")


def test_effect_classification_is_explicit() -> None:
    assert TransportEffect.NO_EFFECT.value == "no_effect"
    assert TransportEffect.EFFECT_UNKNOWN.value == "effect_unknown"
    error = TransportError("unavailable", TransportEffect.NO_EFFECT)
    assert error.classification is TransportEffect.NO_EFFECT
    assert str(error) == "remote worker transport unavailable"


def test_binding_configuration_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(TransportValidationError, match="binding"):
        BrokerTransportBinding(
            endpoint=("localhost", -1),
            ca_path=tmp_path / "missing-ca.pem",
            client_cert_path=tmp_path / "missing-cert.pem",
            client_key_path=tmp_path / "missing-key.pem",
            expected_server_fingerprint="z" * 64,
        )


def _openssl_available() -> bool:
    try:
        return subprocess.run(
            ["openssl", "version"], check=False, capture_output=True
        ).returncode == 0
    except OSError:
        return False


def _certificate_fixture(
    tmp_path: Path,
    *,
    name: str,
    common_name: str,
    san: str,
    ca: bool = False,
    issuer_key: Path | None = None,
    issuer_cert: Path | None = None,
) -> tuple[Path, Path, Path]:
    key = tmp_path / f"{name}.key"
    cert = tmp_path / f"{name}.pem"
    config = tmp_path / f"{name}.cnf"
    if ca:
        config.write_text(
            "[v3]\nbasicConstraints=critical,CA:TRUE\n"
            "keyUsage=critical,keyCertSign,cRLSign\n"
            f"subjectAltName={san}\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                f"/CN={common_name}",
                "-extensions",
                "v3",
                "-config",
                str(config),
            ],
            check=True,
            capture_output=True,
        )
        return key, cert, config

    if issuer_key is None or issuer_cert is None:
        raise ValueError("leaf certificate fixture requires issuer")
    csr = tmp_path / f"{name}.csr"
    config.write_text(
        "[v3]\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth,clientAuth\n"
        f"subjectAltName={san}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(csr),
            "-subj",
            f"/CN={common_name}",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(issuer_cert),
            "-CAkey",
            str(issuer_key),
            "-CAcreateserial",
            "-out",
            str(cert),
            "-days",
            "1",
            "-extensions",
            "v3",
            "-extfile",
            str(config),
        ],
        check=True,
        capture_output=True,
    )
    return key, cert, config


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
def test_tls_contexts_require_tls_1_3_and_fingerprint(tmp_path: Path) -> None:
    from control_plane.remote_worker_transport import build_client_ssl_context

    ca_key, ca_cert, _ = _certificate_fixture(
        tmp_path, name="ca", common_name="Test CA", san="DNS:ca.invalid", ca=True
    )
    key, cert, _ = _certificate_fixture(
        tmp_path,
        name="client",
        common_name="control",
        san="DNS:control.invalid",
        issuer_key=ca_key,
        issuer_cert=ca_cert,
    )
    fingerprint = hashlib.sha256(cert.read_bytes()).hexdigest()
    binding = BrokerTransportBinding(
        endpoint=("localhost", 8443),
        ca_path=ca_cert,
        client_cert_path=cert,
        client_key_path=key,
        expected_server_fingerprint=fingerprint,
    )
    context = build_client_ssl_context(binding)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_versioned_broker_operation_round_trips_through_transport() -> None:
    request = build_request(
        IDENTITY,
        "capacity-observe/v1",
        {"schema_version": "mastermind.executive_worker_capacity_observe_request/v1"},
    )
    validate_request(
        request,
        expected_host_ref=HOST_REF,
        allowed_worker_ids={"WORKER-001"},
        allowed_operations={"capacity-observe/v1"},
    )
    assert request["broker_operation"] == "capacity-observe/v1"


@pytest.mark.parametrize(
    "operation",
    [
        "capacity-observe/v0",
        "capacity-observe/v01",
        "capacity//v1",
        "capacity-observe/v1/extra",
        "../v1",
    ],
)
def test_transport_rejects_arbitrary_path_like_operation_names(operation: str) -> None:
    with pytest.raises(TransportValidationError):
        build_request(IDENTITY, operation, {})
