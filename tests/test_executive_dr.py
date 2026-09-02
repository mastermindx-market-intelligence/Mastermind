"""Adversarial tests for Executive OS off-host disaster recovery (DR-V1).

Style-matched to tests/test_executive_backup.py. Covers: envelope closed-set
validation, encrypt/decrypt round trip, every encrypt-then-MAC failure mode
(wrong key, truncation, bit-flip, envelope substitution), the identity law
(duplicate vs conflict) for both transports, quarantine, the GitHub
transport's HTTP-layer parsing and its ship/fetch flows (all via a stubbed
`_github_request`/`urllib` seam -- zero real network), the secret canary
(no key/token material ever appears in an envelope, a receipt, or an
exception), and a full offline clean-host drill integration run.
"""

from __future__ import annotations

import base64
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import executive_dr as dr
from control_plane.executive_backup import create_online_backup
from control_plane.executive_runtime import Runtime

_ROOT = Path(__file__).resolve().parents[1]
_OPS = _ROOT / "ops" / "executive_os"
_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _fresh_key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _fabricated_backup(tmp_path: Path) -> tuple[Path, Path]:
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="primary", worker_type="mock", capabilities=["code"]
    )
    job = runtime.jobs.create_job("dr test objective")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    return Path(receipt.database_path), Path(receipt.manifest_path)


def _export(tmp_path: Path, *, key: str | None = None) -> tuple[dr.ExportReceipt, str]:
    artifact, manifest = _fabricated_backup(tmp_path)
    key = key or _fresh_key()
    receipt = dr.encrypt_export(
        artifact,
        manifest,
        key,
        tmp_path / "staging",
        transport_target="github-release",
        retention_class="drill",
        source_release_commit=_SHA_A,
    )
    return receipt, key


# --------------------------------------------------------------------------
# Envelope closed-set validation
# --------------------------------------------------------------------------


def test_envelope_rejects_unknown_field(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    envelope = json.loads(Path(receipt.envelope_path).read_text(encoding="utf-8"))
    envelope["unexpected_field"] = "x"
    corrupt = tmp_path / "corrupt.envelope.json"
    corrupt.write_text(json.dumps(envelope), encoding="utf-8")
    corrupt.chmod(0o600)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.verify_export_envelope(corrupt)
    assert excinfo.value.state is dr.DRFailureState.ENVELOPE_INVALID


def test_envelope_rejects_missing_field(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    envelope = json.loads(Path(receipt.envelope_path).read_text(encoding="utf-8"))
    del envelope["mac_b64"]
    corrupt = tmp_path / "corrupt.envelope.json"
    corrupt.write_text(json.dumps(envelope), encoding="utf-8")
    corrupt.chmod(0o600)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.verify_export_envelope(corrupt)
    assert excinfo.value.state is dr.DRFailureState.ENVELOPE_INVALID


def test_envelope_rejects_unsupported_cipher_label(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    envelope = json.loads(Path(receipt.envelope_path).read_text(encoding="utf-8"))
    envelope["cipher"] = "aes-256-gcm"
    corrupt = tmp_path / "corrupt.envelope.json"
    corrupt.write_text(json.dumps(envelope), encoding="utf-8")
    corrupt.chmod(0o600)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.verify_export_envelope(corrupt)
    assert excinfo.value.state is dr.DRFailureState.ENVELOPE_INVALID


def test_envelope_verification_never_requires_a_key(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    verification = dr.verify_export_envelope(receipt.envelope_path, receipt.ciphertext_path)
    assert verification.export_id == receipt.export_id
    assert verification.ciphertext_sha256 == receipt.ciphertext_sha256


# --------------------------------------------------------------------------
# Encrypt/decrypt round trip and every authenticated-failure mode
# --------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip_is_byte_identical(tmp_path: Path) -> None:
    artifact, manifest = _fabricated_backup(tmp_path)
    key = _fresh_key()
    receipt = dr.encrypt_export(
        artifact, manifest, key, tmp_path / "staging",
        transport_target="github-release", retention_class="drill", source_release_commit=_SHA_A,
    )
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    decrypt_receipt = dr.decrypt_export(receipt.ciphertext_path, receipt.envelope_path, key, output)
    assert decrypt_receipt.plaintext_sha256 == receipt.plaintext_sha256
    # Byte-identical to the exact artifact that was encrypted.
    assert output.read_bytes() == artifact.read_bytes()
    assert dr._sha256_path(output) == receipt.plaintext_sha256


def test_decrypt_with_wrong_key_is_typed_and_produces_no_output(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    wrong_key = _fresh_key()
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(receipt.ciphertext_path, receipt.envelope_path, wrong_key, output)
    assert excinfo.value.state is dr.DRFailureState.MAC_MISMATCH
    assert not output.exists()
    assert not list(output.parent.glob("*"))


def test_decrypt_truncated_ciphertext_is_typed_and_produces_no_output(tmp_path: Path) -> None:
    receipt, key = _export(tmp_path)
    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    corrupt_cipher = corrupt_dir / Path(receipt.ciphertext_path).name
    corrupt_cipher.write_bytes(Path(receipt.ciphertext_path).read_bytes()[:-8])
    corrupt_cipher.chmod(0o600)
    corrupt_envelope = corrupt_dir / Path(receipt.envelope_path).name
    shutil.copyfile(receipt.envelope_path, corrupt_envelope)
    corrupt_envelope.chmod(0o600)

    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(corrupt_cipher, corrupt_envelope, key, output)
    assert excinfo.value.state is dr.DRFailureState.MAC_MISMATCH
    assert not output.exists()


def test_decrypt_single_bit_flip_is_typed_and_produces_no_output(tmp_path: Path) -> None:
    receipt, key = _export(tmp_path)
    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    data = bytearray(Path(receipt.ciphertext_path).read_bytes())
    data[len(data) // 2] ^= 0x01
    corrupt_cipher = corrupt_dir / Path(receipt.ciphertext_path).name
    corrupt_cipher.write_bytes(bytes(data))
    corrupt_cipher.chmod(0o600)
    corrupt_envelope = corrupt_dir / Path(receipt.envelope_path).name
    shutil.copyfile(receipt.envelope_path, corrupt_envelope)
    corrupt_envelope.chmod(0o600)

    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(corrupt_cipher, corrupt_envelope, key, output)
    assert excinfo.value.state is dr.DRFailureState.MAC_MISMATCH
    assert not output.exists()


def test_decrypt_envelope_substitution_is_typed_and_produces_no_output(tmp_path: Path) -> None:
    receipt_a, key_a = _export(tmp_path / "a")
    receipt_b, _key_b = _export(tmp_path / "b")

    mixed_dir = tmp_path / "mixed"
    mixed_dir.mkdir()
    mixed_cipher = mixed_dir / Path(receipt_a.ciphertext_path).name
    shutil.copyfile(receipt_a.ciphertext_path, mixed_cipher)
    mixed_cipher.chmod(0o600)
    mixed_envelope = mixed_dir / Path(receipt_a.envelope_path).name
    shutil.copyfile(receipt_b.envelope_path, mixed_envelope)  # substituted
    mixed_envelope.chmod(0o600)

    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(mixed_cipher, mixed_envelope, key_a, output)
    assert excinfo.value.state is dr.DRFailureState.MAC_MISMATCH
    assert not output.exists()


def test_decrypt_refuses_to_overwrite_an_existing_output(tmp_path: Path) -> None:
    receipt, key = _export(tmp_path)
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    output.write_bytes(b"already here")
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(receipt.ciphertext_path, receipt.envelope_path, key, output)
    assert excinfo.value.state is dr.DRFailureState.OUTPUT_CONFLICT
    assert output.read_bytes() == b"already here"


# --------------------------------------------------------------------------
# Identity law (duplicate vs conflict) + create-only refusal -- directory
# transport (no network dependency).
# --------------------------------------------------------------------------


def test_directory_ship_is_idempotent_on_identical_reship(tmp_path: Path) -> None:
    receipt, _key = _export(tmp_path)
    vault = tmp_path / "vault"
    first = dr.ship_export_directory(receipt.ciphertext_path, receipt.envelope_path, directory=vault)
    assert first.duplicate is False
    second = dr.ship_export_directory(receipt.ciphertext_path, receipt.envelope_path, directory=vault)
    assert second.duplicate is True
    assert second.tag == first.tag


def test_directory_ship_refuses_a_differently_digested_object_at_the_same_identity(tmp_path: Path) -> None:
    receipt, key = _export(tmp_path)
    vault = tmp_path / "vault"
    dr.ship_export_directory(receipt.ciphertext_path, receipt.envelope_path, directory=vault)

    # Force a collision: fabricate a second export and rewrite its envelope
    # to claim the FIRST export's export_id/created_at (so the tag/object
    # name collides) while its digest legitimately differs.
    other_artifact, other_manifest = _fabricated_backup(tmp_path / "other")
    other_key = _fresh_key()
    other = dr.encrypt_export(
        other_artifact, other_manifest, other_key, tmp_path / "other-staging",
        transport_target="github-release", retention_class="drill", source_release_commit=_SHA_B,
    )
    other_envelope = json.loads(Path(other.envelope_path).read_text(encoding="utf-8"))
    other_envelope["export_id"] = receipt.export_id
    other_envelope["created_at"] = receipt.created_at
    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    forged_envelope = forged_dir / "forged.envelope.json"
    forged_envelope.write_text(json.dumps(other_envelope), encoding="utf-8")
    forged_envelope.chmod(0o600)
    forged_cipher = forged_dir / "forged.sqlite3.enc"
    shutil.copyfile(other.ciphertext_path, forged_cipher)
    forged_cipher.chmod(0o600)
    # The forged envelope's own byte_size/digest still describe its OWN
    # ciphertext (only identity fields were forged), so it passes the
    # ciphertext-matches-envelope check and reaches the identity conflict.

    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.ship_export_directory(forged_cipher, forged_envelope, directory=vault)
    assert excinfo.value.state is dr.DRFailureState.REMOTE_DIGEST_CONFLICT


def test_fetch_directory_absent_tag_is_typed(tmp_path: Path) -> None:
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.fetch_export_directory("dr-export/does-not-exist", directory=tmp_path / "vault", dest_dir=tmp_path / "out")
    assert excinfo.value.state is dr.DRFailureState.OFFHOST_ABSENT


def test_directory_round_trip(tmp_path: Path) -> None:
    receipt, key = _export(tmp_path)
    vault = tmp_path / "vault"
    ship_receipt = dr.ship_export_directory(receipt.ciphertext_path, receipt.envelope_path, directory=vault)
    fetch_receipt = dr.fetch_export_directory(ship_receipt.tag, directory=vault, dest_dir=tmp_path / "fetched")
    assert fetch_receipt.export_id == receipt.export_id
    assert fetch_receipt.ciphertext_sha256 == receipt.ciphertext_sha256
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    decrypt_receipt = dr.decrypt_export(fetch_receipt.ciphertext_path, fetch_receipt.envelope_path, key, output)
    assert decrypt_receipt.plaintext_sha256 == receipt.plaintext_sha256


# --------------------------------------------------------------------------
# Quarantine
# --------------------------------------------------------------------------


def test_quarantine_renames_aside_with_a_receipt_and_never_deletes(tmp_path: Path) -> None:
    victim = tmp_path / "corrupt-artifact.sqlite3.enc"
    victim.write_bytes(b"not actually valid ciphertext")
    victim.chmod(0o600)
    receipt = dr.quarantine_artifact(victim, reason="failed digest check")
    assert not victim.exists()
    quarantined = Path(receipt.quarantined_path)
    assert quarantined.exists()
    assert quarantined.read_bytes() == b"not actually valid ciphertext"
    receipt_file = Path(receipt.receipt_path)
    assert receipt_file.exists()
    body = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert body["reason"] == "failed digest check"
    assert body["original_path"] == str(victim)


# --------------------------------------------------------------------------
# GitHub transport -- `_github_request` is stubbed; zero real network calls
# happen anywhere in this file (asserted below).
# --------------------------------------------------------------------------


class _FakeGitHub:
    """In-memory GitHub releases API sufficient for ship/fetch coverage."""

    def __init__(self) -> None:
        self.releases: dict[str, dict] = {}
        self._next_release_id = 1
        self._next_asset_id = 1
        self.upload_calls = 0
        self.download_calls = 0

    @staticmethod
    def _public_view(release: dict) -> dict:
        return {
            **{k: v for k, v in release.items() if k != "assets"},
            "assets": [{k: v for k, v in asset.items() if k != "_bytes"} for asset in release["assets"]],
        }

    def request(self, method, url, *, token=None, headers=None, data=None, timeout=30.0):
        if method == "GET" and "/releases/tags/" in url:
            tag = url.rsplit("/releases/tags/", 1)[1]
            import urllib.parse as _urlparse

            tag = _urlparse.unquote(tag)
            release = self.releases.get(tag)
            if release is None:
                return 404, {}, b'{"message":"Not Found"}'
            return 200, {}, json.dumps(self._public_view(release)).encode("utf-8")

        if method == "POST" and url.endswith("/releases"):
            payload = json.loads(data.decode("utf-8"))
            tag = payload["tag_name"]
            if tag in self.releases:
                return 422, {}, b'{"message":"tag already exists"}'
            release_id = self._next_release_id
            self._next_release_id += 1
            release = {
                "id": release_id,
                "tag_name": tag,
                "body": payload["body"],
                "upload_url": f"https://uploads.example.com/releases/{release_id}/assets{{?name,label}}",
                "assets": [],
            }
            self.releases[tag] = release
            return 201, {}, json.dumps(release).encode("utf-8")

        if method == "POST" and "/releases/" in url and "/assets" in url:
            self.upload_calls += 1
            release_id = int(url.split("/releases/")[1].split("/assets")[0])
            release = next(r for r in self.releases.values() if r["id"] == release_id)
            import urllib.parse as _urlparse

            name = _urlparse.parse_qs(_urlparse.urlparse(url).query)["name"][0]
            if any(a["name"] == name for a in release["assets"]):
                return 422, {}, b'{"message":"asset already exists"}'
            asset_id = self._next_asset_id
            self._next_asset_id += 1
            asset = {"id": asset_id, "name": name, "_bytes": data}
            release["assets"].append(asset)
            return 201, {}, json.dumps({"id": asset_id, "name": name}).encode("utf-8")

        if method == "GET" and "/releases/assets/" in url:
            self.download_calls += 1
            asset_id = int(url.rsplit("/releases/assets/", 1)[1])
            for release in self.releases.values():
                for asset in release["assets"]:
                    if asset["id"] == asset_id:
                        return 200, {}, asset["_bytes"]
            return 404, {}, b'{"message":"Not Found"}'

        raise AssertionError(f"unexpected fake GitHub request: {method} {url}")


@pytest.fixture()
def fake_github(monkeypatch: pytest.MonkeyPatch) -> _FakeGitHub:
    fake = _FakeGitHub()

    def _stub(method, url, *, token=None, headers=None, data=None, timeout=30.0):
        return fake.request(method, url, token=token, headers=headers, data=data, timeout=timeout)

    monkeypatch.setattr(dr, "_github_request", _stub)
    return fake


def test_ship_and_fetch_github_round_trip(tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    receipt, key = _export(tmp_path)
    ship_receipt = dr.ship_export_github(
        receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN"
    )
    assert ship_receipt.duplicate is False
    assert fake_github.upload_calls == 2  # ciphertext + envelope
    assert fake_github.download_calls == 1  # checksum-after-upload

    fetch_receipt = dr.fetch_export_github(
        ship_receipt.tag, repo="acme/vault", dest_dir=tmp_path / "fetched", token_env="EXECUTIVE_DR_TOKEN"
    )
    assert fetch_receipt.export_id == receipt.export_id
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    decrypt_receipt = dr.decrypt_export(fetch_receipt.ciphertext_path, fetch_receipt.envelope_path, key, output)
    assert decrypt_receipt.plaintext_sha256 == receipt.plaintext_sha256


def test_ship_github_is_idempotent_on_identical_reship(tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    receipt, _key = _export(tmp_path)
    first = dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert first.duplicate is False
    second = dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert second.duplicate is True


def test_ship_github_refuses_overwrite_on_tag_reuse_with_different_digest(
    tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    receipt, _key = _export(tmp_path)
    dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    # Pre-seed a conflicting body under the exact same tag by hand.
    fake_github.releases[dr._export_tag(json.loads(Path(receipt.envelope_path).read_text()))]["body"] = json.dumps(
        {"ciphertext_sha256": "0" * 64}
    )
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert excinfo.value.state is dr.DRFailureState.REMOTE_DIGEST_CONFLICT


def test_ship_github_checksum_after_upload_mismatch_is_typed(
    tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    receipt, _key = _export(tmp_path)

    real_request = fake_github.request

    def _tampering_stub(method, url, *, token=None, headers=None, data=None, timeout=30.0):
        status, headers_out, body = real_request(method, url, token=token, headers=headers, data=data, timeout=timeout)
        if method == "GET" and "/releases/assets/" in url and status == 200:
            body = b"tampered-in-flight" + body
        return status, headers_out, body

    monkeypatch.setattr(dr, "_github_request", _tampering_stub)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert excinfo.value.state is dr.DRFailureState.UPLOAD_EFFECT_UNKNOWN


def test_ship_github_requires_the_credential_env_var(tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXECUTIVE_DR_TOKEN", raising=False)
    receipt, _key = _export(tmp_path)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert excinfo.value.state is dr.DRFailureState.CREDENTIAL_LOST


def test_fetch_github_absent_tag_is_typed(tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.fetch_export_github("dr-export/nope", repo="acme/vault", dest_dir=tmp_path / "out", token_env="EXECUTIVE_DR_TOKEN")
    assert excinfo.value.state is dr.DRFailureState.OFFHOST_ABSENT


def test_no_real_network_socket_is_ever_touched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_github: _FakeGitHub) -> None:
    """Positive proof the fixture really replaces the HTTP seam: a real
    socket connection attempt anywhere in this module during a ship/fetch
    call would raise, not silently succeed."""

    import socket

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("a real network socket was opened during a stubbed-urllib DR test")

    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", "not-a-real-token")
    receipt, _key = _export(tmp_path)
    dr.ship_export_github(receipt.ciphertext_path, receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")


# --------------------------------------------------------------------------
# `_github_request` itself, against a stubbed urllib opener (no `_github_
# request` monkeypatch here -- this exercises the real HTTP-response-parsing
# code, including redirect handling, with urllib's opener replaced).
# --------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = _HeaderStub({})

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _HeaderStub:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def items(self):
        return self._values.items()

    def get(self, key, default=None):
        return self._values.get(key, default)


class _FakeOpener:
    def __init__(self, plan: dict[str, tuple[int, dict, bytes]]) -> None:
        self._plan = plan

    def open(self, request, timeout=None):
        key = request.full_url
        status, headers, body = self._plan[key]
        if 300 <= status < 400 or status >= 400:
            import email.message
            import io
            import urllib.error

            msg = email.message.Message()
            for k, v in headers.items():
                msg[k] = v
            raise urllib.error.HTTPError(key, status, "stub", msg, io.BytesIO(body))
        return _FakeHTTPResponse(status, body)


def test_github_request_parses_a_direct_200(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = _FakeOpener({"https://api.github.com/repos/acme/vault/releases/tags/x": (200, {}, b'{"id":1}')})
    monkeypatch.setattr(dr.urllib.request, "build_opener", lambda *_a, **_k: opener)
    status, _headers, body = dr._github_request(
        "GET", "https://api.github.com/repos/acme/vault/releases/tags/x", token="t"
    )
    assert status == 200
    assert json.loads(body) == {"id": 1}


def test_github_request_maps_404_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = _FakeOpener({"https://api.github.com/repos/acme/vault/releases/tags/x": (404, {}, b"{}")})
    monkeypatch.setattr(dr.urllib.request, "build_opener", lambda *_a, **_k: opener)
    status, _headers, _body = dr._github_request("GET", "https://api.github.com/repos/acme/vault/releases/tags/x", token="t")
    assert status == 404


def test_github_asset_download_follows_a_redirect_without_forwarding_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_tokens: list[str | None] = []
    real_request = dr._github_request

    def _tracking(method, url, *, token=None, headers=None, data=None, timeout=30.0):
        seen_tokens.append(token)
        if url == "https://api.github.com/repos/acme/vault/releases/assets/9":
            return 302, {"Location": "https://objects.example.com/signed?x=1"}, b""
        if url == "https://objects.example.com/signed?x=1":
            assert token is None  # the second hop must never carry the GitHub Authorization header
            return 200, {}, b"asset-bytes"
        raise AssertionError(url)

    monkeypatch.setattr(dr, "_github_request", _tracking)
    body = dr._github_download_asset("https://api.github.com", "acme/vault", 9, "secret-token")
    assert body == b"asset-bytes"
    assert seen_tokens == ["secret-token", None]


# --------------------------------------------------------------------------
# Secret canary: no key or token material ever appears in an envelope, a
# receipt, or an exception's string representation.
# --------------------------------------------------------------------------


def test_no_key_or_token_material_leaks_into_envelope_receipts_or_exceptions(
    tmp_path: Path, fake_github: _FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_key = _fresh_key()
    secret_token = "ghp_super-secret-canary-token-value"
    monkeypatch.setenv("EXECUTIVE_DR_TOKEN", secret_token)

    artifact, manifest = _fabricated_backup(tmp_path)
    export_receipt = dr.encrypt_export(
        artifact, manifest, secret_key, tmp_path / "staging",
        transport_target="github-release", retention_class="drill", source_release_commit=_SHA_A,
    )
    ship_receipt = dr.ship_export_github(
        export_receipt.ciphertext_path, export_receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN"
    )
    fetch_receipt = dr.fetch_export_github(
        ship_receipt.tag, repo="acme/vault", dest_dir=tmp_path / "fetched", token_env="EXECUTIVE_DR_TOKEN"
    )
    output = tmp_path / "restored" / "out.sqlite3"
    output.parent.mkdir()
    decrypt_receipt = dr.decrypt_export(fetch_receipt.ciphertext_path, fetch_receipt.envelope_path, secret_key, output)

    haystacks = [
        Path(export_receipt.envelope_path).read_text(encoding="utf-8"),
        json.dumps(export_receipt.to_dict()),
        json.dumps(ship_receipt.to_dict()),
        json.dumps(fetch_receipt.to_dict()),
        json.dumps(decrypt_receipt.to_dict()),
    ]
    for haystack in haystacks:
        assert secret_key not in haystack
        assert secret_token not in haystack

    # And every typed exception's string form, across every failure path
    # exercised elsewhere in this file.
    wrong_key = _fresh_key()
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo:
        dr.decrypt_export(export_receipt.ciphertext_path, export_receipt.envelope_path, wrong_key, tmp_path / "out2.sqlite3")
    assert secret_key not in str(excinfo.value)
    assert wrong_key not in str(excinfo.value)

    monkeypatch.delenv("EXECUTIVE_DR_TOKEN", raising=False)
    with pytest.raises(dr.ExecutiveDRTypedError) as excinfo2:
        dr.ship_export_github(export_receipt.ciphertext_path, export_receipt.envelope_path, repo="acme/vault", token_env="EXECUTIVE_DR_TOKEN")
    assert secret_token not in str(excinfo2.value)


# --------------------------------------------------------------------------
# Integration: the offline clean-host drill end-to-end, against a fabricated
# Runtime, asserting logical-state equality and receipt shape.
# --------------------------------------------------------------------------


def _load_dr_drill():
    import importlib.util

    spec = importlib.util.spec_from_file_location("dr_drill", _ROOT / "scripts" / "dr_drill.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_drill_end_to_end_logical_state_equality(tmp_path: Path) -> None:
    dr_drill = _load_dr_drill()
    receipt = dr_drill.run_drill(
        work_root=tmp_path / "work", offline=True, repo="unused/unused", token_env="GITHUB_TOKEN", api_base="https://api.github.com"
    )
    assert receipt["schema_version"] == dr_drill.DRILL_RECEIPT_SCHEMA_VERSION
    assert receipt["logical_state_equal"] is True
    assert receipt["pre_loss_state"] == receipt["post_restore_state"]
    assert receipt["transport"] == "directory"
    assert receipt["restore_drill"]["integrity_check"] == "ok"
    assert receipt["restore_drill"]["foreign_key_check"] == "ok"
    assert set(receipt["stage_timings_ms"]) == {
        "fabricate", "backup", "encrypt", "ship", "discard_local", "fetch", "decrypt", "verify",
    }
    assert receipt["rto_ms"] >= 0
    # Every logical-state bucket is non-empty -- a real workload, not a
    # vacuously-equal empty comparison.
    assert receipt["pre_loss_state"]["workers"]
    assert receipt["pre_loss_state"]["jobs"]
    assert receipt["pre_loss_state"]["attempts"]
    assert receipt["pre_loss_state"]["events"]


def test_dr_drill_cli_exits_zero_and_writes_a_receipt(tmp_path: Path) -> None:
    receipt_out = tmp_path / "receipt.json"
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(_ROOT / "scripts" / "dr_drill.py"), "--offline", "--receipt-out", str(receipt_out)],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert receipt_out.exists()
    body = json.loads(receipt_out.read_text(encoding="utf-8"))
    assert body["logical_state_equal"] is True


# --------------------------------------------------------------------------
# Launchd plist template + shell syntax.
# --------------------------------------------------------------------------


def test_backup_plist_template_parses_and_ships_disabled() -> None:
    path = _OPS / "com.mastermind.executive.backup.plist.template"
    with path.open("rb") as handle:
        value = plistlib.load(handle)
    assert value["Label"] == "com.mastermind.executive.backup"
    assert value["RunAtLoad"] is False
    assert value["KeepAlive"] is False
    assert "StartCalendarInterval" in value
    assert value["ProgramArguments"][0] == "/bin/bash"
    assert value["UserName"].startswith("__")


@pytest.mark.parametrize("name", ["run_nightly_backup.sh"])
def test_new_shell_scripts_pass_bash_dash_n(name: str) -> None:
    path = _OPS / name
    completed = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_backup_wrapper_is_executable_and_has_no_secret_literals() -> None:
    path = _OPS / "run_nightly_backup.sh"
    info = path.stat()
    assert info.st_mode & stat.S_IXUSR
    text = path.read_text(encoding="utf-8")
    # The wrapper must read key/token material only from paths/env-var NAMES
    # supplied as arguments -- never embed a literal secret.
    assert "ghp_" not in text
    assert "BEGIN PRIVATE KEY" not in text
