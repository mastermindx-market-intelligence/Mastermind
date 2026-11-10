"""Credential custody: 0600 files or env names, and a grep that secrets stay out of logs."""

from __future__ import annotations

import io
import json
import logging
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.cli import main  # noqa: E402
from integrations.hermes_models.client import UrllibTransport  # noqa: E402
from integrations.hermes_models.contract import PROVIDERS  # noqa: E402
from integrations.hermes_models.credentials import CredentialUnavailable, load_credential  # noqa: E402
from integrations.hermes_models.tests.support import (  # noqa: E402
    CANARY,
    client,
    ok_body,
    request,
    ScriptedTransport,
)


class SecretTests(unittest.TestCase):
    def test_env_and_0600_file_load_and_loose_file_is_refused(self):
        spec = PROVIDERS["zai.glm-5.3"]
        self.assertEqual(load_credential(spec, {spec.credential_env: CANARY}), CANARY)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "zai.key"
            path.write_text(CANARY + "\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(CredentialUnavailable) as loose:
                load_credential(spec, {spec.credential_file_env: str(path)})
            self.assertNotIn(CANARY, str(loose.exception))
            path.chmod(0o600)
            self.assertEqual(load_credential(spec, {spec.credential_file_env: str(path)}), CANARY)
            json_path = Path(raw) / "zai.json"
            json_path.write_text(json.dumps({"api_key": CANARY}), encoding="utf-8")
            json_path.chmod(0o600)
            self.assertEqual(
                load_credential(spec, {spec.credential_file_env: str(json_path)}),
                CANARY,
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_empty_or_relative_file_pointer_never_falls_back_to_inline_key(self):
        spec = PROVIDERS["zai.glm-5.3"]
        for pointer in ("", "relative.key"):
            with self.subTest(pointer=pointer):
                with self.assertRaises(CredentialUnavailable):
                    load_credential(spec, {
                        spec.credential_file_env: pointer,
                        spec.credential_env: CANARY,
                    })

    def test_file_pointer_must_be_owned_by_runtime_user(self):
        spec = PROVIDERS["zai.glm-5.3"]
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "not-ours.key"
            path.write_text(CANARY + "\n", encoding="utf-8")
            path.chmod(0o600)
            wrong_uid = os.geteuid() + 1
            with mock.patch(
                "integrations.hermes_models.credentials.os.geteuid",
                return_value=wrong_uid,
            ):
                with self.assertRaises(CredentialUnavailable):
                    load_credential(spec, {spec.credential_file_env: str(path)})

    def test_secrets_are_never_logged(self):
        spec = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        logger = logging.getLogger("integrations.hermes_models")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                transport = ScriptedTransport([ok_body(spec.served_model, content="noted")])
                model = client(root, transport, {spec.credential_env: CANARY})
                result = model.complete(
                    request(
                        "secretary",
                        spec.provider_id,
                        effect="read_only",
                        turn="secret-1",
                        messages=({"role": "user", "content": CANARY},),
                    )
                )
                stderr = io.StringIO()
                with mock.patch("sys.stderr", stderr):
                    code = main([f"--api-key={CANARY}"])
                self.assertEqual(code, 2)
                (root / "client.log").write_text(stream.getvalue(), encoding="utf-8")
                (root / "cli.stderr").write_text(stderr.getvalue(), encoding="utf-8")
                (root / "result.txt").write_text(str(result), encoding="utf-8")
                loose = root / "loose-error.txt"
                key = root / "loose.key"
                key.write_text(CANARY, encoding="utf-8")
                key.chmod(0o644)
                try:
                    load_credential(spec, {spec.credential_file_env: str(key)})
                except CredentialUnavailable as exc:
                    loose.write_text(str(exc), encoding="utf-8")
                key.unlink()
                completed = subprocess.run(
                    ["grep", "-R", "-n", CANARY, str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout)
                self.assertNotIn(CANARY, completed.stdout)
                self.assertNotIn(CANARY, completed.stderr)
                self.assertTrue(result.ok)
                self.assertIn(CANARY, transport.calls[0]["headers"]["Authorization"])
                self.assertNotIn(CANARY, transport.calls[0]["url"])
                meter = (root / "usage.jsonl").read_text(encoding="utf-8")
                self.assertNotIn("Authorization", meter)
                self.assertNotIn("Bearer", meter)
                self.assertNotIn("messages", meter)
        finally:
            logger.removeHandler(handler)

    def test_urllib_transport_is_opt_in_and_mockable(self):
        spec = PROVIDERS["zai.glm-5.3"]
        payload = json.dumps(
            {
                "model": spec.served_model,
                "choices": [{"message": {"role": "assistant", "content": "noted"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }
        ).encode("ascii")

        class Response:
            status = 200
            headers = {}

            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        calls = []

        def urlopen(request, timeout=None):
            calls.append(request)
            if len(calls) > 1:
                raise AssertionError("replayed")
            return Response()

        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "urllib.request.urlopen", urlopen
        ):
            model = client(Path(raw), UrllibTransport(), {spec.credential_env: CANARY})
            result = model.complete(
                request("meta-ceo", spec.provider_id, effect="read_only", turn="urllib-1")
            )
        self.assertTrue(result.ok)
        self.assertEqual(len(calls), 1)
        self.assertNotIn(CANARY, calls[0].full_url)
        self.assertIn(spec.served_model, calls[0].data.decode("ascii"))
        self.assertNotIn(CANARY, calls[0].data.decode("ascii"))

    def test_urllib_429_is_a_single_http_error(self):
        spec = PROVIDERS["minimax.attended"]
        calls = []

        def urlopen(request, timeout=None):
            calls.append(request)
            raise HTTPError(
                request.full_url,
                429,
                "rate",
                {"Retry-After": "5"},
                io.BytesIO(b"{}"),
            )

        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "urllib.request.urlopen", urlopen
        ):
            model = client(Path(raw), UrllibTransport(), {spec.credential_env: CANARY})
            result = model.complete(
                request("vision", spec.provider_id, effect="read_only", turn="urllib-429")
            )
        self.assertEqual(result.outcome, "rate_limited")
        self.assertEqual(result.backoff_seconds, 5.0)
        self.assertEqual(len(calls), 1)
        self.assertNotIn(CANARY, calls[0].full_url)

    def test_symlink_hardlink_loose_mode_and_bad_json_do_not_leak(self):
        spec = PROVIDERS["zai.glm-5.3"]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "zai.key"
            target.write_text(CANARY + "\n", encoding="utf-8")
            target.chmod(0o600)
            link = root / "zai.link"
            link.symlink_to(target)
            with self.assertRaises(CredentialUnavailable) as linked:
                load_credential(spec, {spec.credential_file_env: str(link), spec.credential_env: CANARY})
            self.assertNotIn(CANARY, str(linked.exception))
            hard = root / "zai.hard"
            os.link(target, hard)
            with self.assertRaises(CredentialUnavailable) as hard_link:
                load_credential(spec, {spec.credential_file_env: str(hard)})
            self.assertNotIn(CANARY, str(hard_link.exception))
            loose = root / "zai.loose"
            loose.write_text(CANARY + "\n", encoding="utf-8")
            loose.chmod(0o700)
            with self.assertRaises(CredentialUnavailable):
                load_credential(spec, {spec.credential_file_env: str(loose)})
            broken = root / "zai.json"
            broken.write_text("{not-json " + CANARY, encoding="utf-8")
            broken.chmod(0o600)
            with self.assertRaises(CredentialUnavailable) as bad_json:
                load_credential(spec, {spec.credential_file_env: str(broken)})
            self.assertIsNone(bad_json.exception.__cause__)
            self.assertNotIn(CANARY, str(bad_json.exception))
            self.assertNotIn(CANARY, repr(bad_json.exception))


if __name__ == "__main__":
    unittest.main()
