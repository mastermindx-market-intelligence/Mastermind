"""Adversarial tests for the private owner-side release token codec.

Every expected MAC is recomputed here from the stdlib only; no codec internal
is used to derive a vector. Fixtures use fake keys/identity and are test-only.
"""

import ast
import base64
import copy
import hashlib
import hmac
import json
import os
import unittest

from control_plane.executive_release_contract import ReleaseRecord
from control_plane import executive_release_token as t
from tests.test_executive_release_contract import fixtures, prepared_fixture

KEY = bytes(range(32))
KEY_ID = "key-v1"
TRUST = 1
OWNER = "11111111-1111-4111-8111-111111111111"
BOOT = "22222222-2222-4222-8222-222222222222"
APPROVAL_DOMAIN = b"MMX_EXECUTIVE_RELEASE_APPROVAL_V1\x00"
PREPARED_DOMAIN = b"MMX_EXECUTIVE_RELEASE_PREPARED_V1\x00"
ALLOWED_CODES = frozenset(
    {
        "KEY_LENGTH", "KEY_ID", "TRUST_GENERATION", "OWNER_ID",
        "APPROVAL_STRUCTURE", "PREPARED_STRUCTURE",
        "OWNER_MISMATCH", "KEY_MISMATCH", "TRUST_MISMATCH", "MAC_MISMATCH",
        "TOKEN_TYPE", "TOKEN_SIZE", "TOKEN_FORMAT", "TOKEN_B64",
        "PAYLOAD_SIZE", "MAC_SIZE", "CLOCK", "BOOT_MISMATCH", "LIFETIME",
    }
)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _load(name):
    # Reuse the protected positive vectors rather than a capsule-only file.
    if name == "POSITIVE_APPROVAL.json":
        return fixtures()[3]
    if name == "POSITIVE_PREPARED.json":
        return prepared_fixture()
    raise AssertionError("unknown test vector")


def b64u(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def approval_payload(approval):
    return {k: v for k, v in approval.items() if k != "owner_seal"}


def expected_approval_mac(approval, key=KEY):
    raw = canonical(approval_payload(approval))
    return b64u(hmac.new(key, APPROVAL_DOMAIN + raw, hashlib.sha256).digest())


def prepared_token(raw, key=KEY, domain=PREPARED_DOMAIN):
    mac = hmac.new(key, domain + raw, hashlib.sha256).digest()
    return b64u(raw) + "." + b64u(mac)


def codec(**overrides):
    params = dict(key=KEY, key_id=KEY_ID, trust_generation=TRUST, owner_installation_id=OWNER)
    params.update(overrides)
    return t._OwnerReleaseCodec(**params)


class TokenCodecTest(unittest.TestCase):
    def setUp(self):
        self.codec = codec()
        self.approval = _load("POSITIVE_APPROVAL.json")
        self.prepared = _load("POSITIVE_PREPARED.json")

    # ---- construction -------------------------------------------------
    def test_constructor_rejects_bad_inputs(self):
        cases = [
            dict(key=b"short"), dict(key=bytearray(32)), dict(key="x" * 32),
            dict(key=bytes(31)), dict(key=bytes(33)), dict(key_id=""),
            dict(key_id="bad id"), dict(key_id="a" * 161),
            dict(key_id="\u00e9"), dict(trust_generation=True),
            dict(trust_generation=0), dict(trust_generation=1 << 63),
            dict(trust_generation="1"), dict(owner_installation_id="nope"),
            dict(owner_installation_id="00000000-0000-0000-0000-000000000000"),
            dict(owner_installation_id="abcdefab-1234-4abc-8def-abcdefabcdef".upper()),
        ]
        for case in cases:
            with self.assertRaises(t.ReleaseTokenError):
                codec(**case)

    def test_repr_hides_key(self):
        text = repr(self.codec)
        self.assertNotIn(repr(KEY), text)
        self.assertNotIn("key=", text)
        self.assertIn(KEY_ID, text)

    # ---- seal / verify approval --------------------------------------
    def test_seal_matches_independent_mac(self):
        sealed = self.codec.seal_approval(self.approval)
        self.assertEqual(sealed["owner_seal"]["mac"], expected_approval_mac(self.approval))
        self.assertNotEqual(sealed["owner_seal"]["mac"], self.approval["owner_seal"]["mac"])
        self.assertEqual(sealed["owner_seal"]["key_id"], KEY_ID)
        self.assertEqual(sealed["owner_seal"]["trust_generation"], TRUST)

    def test_seal_excludes_owner_seal_from_mac(self):
        first = self.codec.seal_approval(self.approval)
        other = copy.deepcopy(self.approval)
        other["owner_seal"]["mac"] = b64u(bytes([7]) * 32)
        second = self.codec.seal_approval(other)
        self.assertEqual(first["owner_seal"]["mac"], second["owner_seal"]["mac"])

    def test_seal_is_deterministic_and_detached(self):
        before = copy.deepcopy(self.approval)
        first = self.codec.seal_approval(self.approval)
        second = self.codec.seal_approval(self.approval)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(self.approval, before)
        self.assertIsNot(first, self.approval)

    def test_seal_returns_immutable_record(self):
        sealed = self.codec.seal_approval(self.approval)
        self.assertIsInstance(sealed, ReleaseRecord)
        with self.assertRaises(TypeError):
            sealed["operation_key"] = "x"

    def test_verify_roundtrip_and_mac_tamper(self):
        sealed = self.codec.seal_approval(self.approval)
        self.assertEqual(
            self.codec.verify_approval(sealed)["owner_seal"]["mac"],
            sealed["owner_seal"]["mac"],
        )
        bad_mac = copy.deepcopy(sealed.to_dict())
        mac = bad_mac["owner_seal"]["mac"]
        bad_mac["owner_seal"]["mac"] = _ALPHABET[(_ALPHABET.index(mac[0]) + 1) % 64] + mac[1:]
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.verify_approval(bad_mac)
        self.assertEqual(ctx.exception.code, "MAC_MISMATCH")

    def test_verify_rejects_payload_tamper(self):
        sealed = self.codec.seal_approval(self.approval).to_dict()
        sealed["created_at_ms"] = 1500
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.verify_approval(sealed)
        self.assertEqual(ctx.exception.code, "MAC_MISMATCH")

    def test_verify_identity_mismatches(self):
        sealed = self.codec.seal_approval(self.approval)
        for params, expected in (
            (dict(owner_installation_id="33333333-3333-4333-8333-333333333333"), "OWNER_MISMATCH"),
            (dict(key_id="key-v9"), "KEY_MISMATCH"),
            (dict(key=bytes(range(1, 33))), "MAC_MISMATCH"),
            (dict(trust_generation=2), "TRUST_MISMATCH"),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                codec(**params).verify_approval(sealed)
            self.assertEqual(ctx.exception.code, expected)

    def test_seal_rejects_broken_structure(self):
        broken = copy.deepcopy(self.approval)
        broken.pop("transition_digest")
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.seal_approval(broken)
        self.assertEqual(ctx.exception.code, "APPROVAL_STRUCTURE")

    # ---- encode / decode prepared ------------------------------------
    def test_encode_matches_independent_mac_and_roundtrips(self):
        token = self.codec.encode_prepared(self.prepared)
        payload_seg, mac_seg = token.split(".")
        raw = base64.urlsafe_b64decode(payload_seg + "==")
        self.assertEqual(raw, canonical(self.prepared))
        self.assertEqual(
            mac_seg,
            b64u(hmac.new(KEY, PREPARED_DOMAIN + raw, hashlib.sha256).digest()),
        )
        record = self.codec.decode_prepared(
            token, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
        )
        self.assertEqual(record.to_dict(), self.prepared)
        self.assertTrue(token.isascii())

    def test_encode_is_deterministic_and_detached(self):
        before = copy.deepcopy(self.prepared)
        self.assertEqual(
            self.codec.encode_prepared(self.prepared),
            self.codec.encode_prepared(self.prepared),
        )
        self.assertEqual(self.prepared, before)

    def test_encode_identity_mismatches(self):
        for params, expected in (
            (dict(owner_installation_id="33333333-3333-4333-8333-333333333333"), "OWNER_MISMATCH"),
            (dict(key_id="key-v9"), "KEY_MISMATCH"),
            (dict(trust_generation=2), "TRUST_MISMATCH"),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                codec(**params).encode_prepared(self.prepared)
            self.assertEqual(ctx.exception.code, expected)

    def test_encode_rejects_broken_structure(self):
        broken = copy.deepcopy(self.prepared)
        broken.pop("request_fingerprint")
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.encode_prepared(broken)
        self.assertEqual(ctx.exception.code, "PREPARED_STRUCTURE")

    # ---- decode window / boot ----------------------------------------
    def _token(self):
        return self.codec.encode_prepared(self.prepared)

    def test_decode_accepts_exact_issuance_boundary(self):
        self.codec.decode_prepared(
            self._token(), now_ms=1000, monotonic_ns=1_000_000_000, boot_id=BOOT
        )

    def test_decode_rejects_before_issuance_and_at_expiry(self):
        for now_ms, mono in (
            (999, 1_000_000_000),
            (301000, 1_000_000_000),
            (2000, 999_999_999),
            (2000, 301_000_000_000),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                self.codec.decode_prepared(
                    self._token(), now_ms=now_ms, monotonic_ns=mono, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, "LIFETIME")

    def test_decode_accepts_last_millisecond(self):
        self.codec.decode_prepared(
            self._token(), now_ms=300999, monotonic_ns=300_999_999_999, boot_id=BOOT
        )

    def test_decode_boot_mismatch(self):
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                self._token(), now_ms=2000, monotonic_ns=2_000_000_000,
                boot_id="33333333-3333-4333-8333-333333333333",
            )
        self.assertEqual(ctx.exception.code, "BOOT_MISMATCH")
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                self._token(), now_ms=2000, monotonic_ns=2_000_000_000, boot_id="not-a-uuid"
            )
        self.assertEqual(ctx.exception.code, "BOOT_MISMATCH")

    def test_decode_identity_mismatches(self):
        token = self._token()
        for params, expected in (
            (dict(owner_installation_id="33333333-3333-4333-8333-333333333333"), "OWNER_MISMATCH"),
            (dict(key_id="key-v9"), "KEY_MISMATCH"),
            (dict(trust_generation=2), "TRUST_MISMATCH"),
            (dict(key=bytes(range(1, 33))), "MAC_MISMATCH"),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                codec(**params).decode_prepared(
                    token, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, expected)

    # ---- decode wire integrity ---------------------------------------
    def test_decode_corrupt_mac(self):
        payload_seg, mac_seg = self._token().split(".")
        flipped = (_ALPHABET.index(mac_seg[0]) + 1) % 64
        bad = payload_seg + "." + _ALPHABET[flipped] + mac_seg[1:]
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                bad, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
            )
        self.assertEqual(ctx.exception.code, "MAC_MISMATCH")

    def test_decode_cross_domain_mac(self):
        raw = canonical(self.prepared)
        token = prepared_token(raw, domain=APPROVAL_DOMAIN)
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                token, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
            )
        self.assertEqual(ctx.exception.code, "MAC_MISMATCH")

    def test_decode_noncanonical_pad_bits_refused(self):
        payload_seg, mac_seg = self._token().split(".")
        index = _ALPHABET.index(mac_seg[-1])
        alt = _ALPHABET[(index & 0b111100) | ((index + 1) & 0b11)]
        self.assertNotEqual(alt, mac_seg[-1])
        bad = payload_seg + "." + mac_seg[:-1] + alt
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                bad, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
            )
        self.assertEqual(ctx.exception.code, "TOKEN_B64")

    def test_decode_token_type_and_ascii(self):
        for bad in (b"abc.def", 123, None, [".", "."]):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                self.codec.decode_prepared(
                    bad, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, "TOKEN_TYPE")
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                "abc.def\u00e9", now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
            )
        self.assertEqual(ctx.exception.code, "TOKEN_FORMAT")

    def test_decode_wire_size_and_segments(self):
        small = self._token()
        payload_seg, mac_seg = small.split(".")
        oversize = "A" * 33100 + "." + mac_seg
        for bad, expected in (
            (oversize, "TOKEN_SIZE"),
            (payload_seg + mac_seg, "TOKEN_FORMAT"),
            ("a.b.c", "TOKEN_FORMAT"),
            ("." + mac_seg, "TOKEN_FORMAT"),
            (payload_seg + ".", "TOKEN_FORMAT"),
            (payload_seg + "=." + mac_seg, "TOKEN_FORMAT"),
            (payload_seg + ".A!A", "TOKEN_FORMAT"),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                self.codec.decode_prepared(
                    bad, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, expected)

    def test_decode_payload_and_mac_size(self):
        big = prepared_token(b"x" * 20000)
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                big, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
            )
        self.assertEqual(ctx.exception.code, "PAYLOAD_SIZE")
        payload_seg, _ = self._token().split(".")
        with self.assertRaises(t.ReleaseTokenError) as ctx:
            self.codec.decode_prepared(
                payload_seg + "." + b64u(b"\x00" * 31),
                now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT,
            )
        self.assertEqual(ctx.exception.code, "MAC_SIZE")

    # ---- decode signed payload structure -----------------------------
    def test_decode_signed_payload_refusals(self):
        spaced = json.dumps(
            self.prepared, sort_keys=True, separators=(", ", ": "), ensure_ascii=False
        ).encode("utf-8")
        extra = copy.deepcopy(self.prepared)
        extra["unexpected_field"] = "x"
        cases = [
            spaced,
            b'{"a":1,"a":2}',
            b'{"a":1.5}',
            b'["x", NaN]',
            b"[" * 9 + b"9" + b"]" * 9,
            canonical(extra),
        ]
        for raw in cases:
            token = prepared_token(raw)
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                self.codec.decode_prepared(
                    token, now_ms=2000, monotonic_ns=2_000_000_000, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, "PREPARED_STRUCTURE")

    def test_decode_malformed_clocks(self):
        token = self._token()
        for now_ms, mono in (
            (True, 2_000_000_000),
            (-1, 2_000_000_000),
            (1.5, 2_000_000_000),
            ("1000", 2_000_000_000),
            (2000, True),
            (2000, -5),
            (2000, None),
        ):
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                self.codec.decode_prepared(
                    token, now_ms=now_ms, monotonic_ns=mono, boot_id=BOOT
                )
            self.assertEqual(ctx.exception.code, "CLOCK")

    # ---- surface / hygiene -------------------------------------------
    def test_only_four_public_methods_exposed(self):
        public = {
            name
            for name in dir(self.codec)
            if not name.startswith("_") and callable(getattr(self.codec, name))
        }
        self.assertEqual(
            public,
            {"seal_approval", "verify_approval", "encode_prepared", "decode_prepared"},
        )

    def test_domains_contain_real_nul(self):
        self.assertIn(b"\x00", t._APPROVAL_DOMAIN)
        self.assertIn(b"\x00", t._PREPARED_DOMAIN)
        self.assertNotIn(b"\\0", t._APPROVAL_DOMAIN)
        self.assertNotIn(b"\\0", t._PREPARED_DOMAIN)

    def test_module_has_no_io_auth_or_dispatch_imports(self):
        with open(t.__file__, "r", encoding="utf-8") as handle:
            source = handle.read()
        forbidden = {
            "os", "io", "socket", "subprocess", "time", "secrets", "ssl",
            "pathlib", "shutil", "random", "tempfile", "requests", "urllib",
            "http", "ctypes", "multiprocessing", "threading", "asyncio",
            "sqlite3", "logging", "sys",
        }
        found = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertFalse(found & forbidden, found & forbidden)

    def test_refusal_diagnostics_are_bounded(self):
        token = self._token()
        failures = [
            (lambda: codec(key=b""), token),
            (lambda: self.codec.encode_prepared({"bad": "shape"}), token),
            (lambda: self.codec.verify_approval({"bad": "shape"}), token),
            (lambda: self.codec.decode_prepared(123, now_ms=2000, monotonic_ns=2, boot_id=BOOT), token),
            (lambda: prepared_token(b"x" * 20000) and self.codec.decode_prepared(
                prepared_token(b"x" * 20000), now_ms=2000, monotonic_ns=2, boot_id=BOOT), token),
            (lambda: self.codec.decode_prepared(token, now_ms=True, monotonic_ns=2, boot_id=BOOT), token),
        ]
        for call, secret in failures:
            with self.assertRaises(t.ReleaseTokenError) as ctx:
                call()
            error = ctx.exception
            self.assertIn(error.code, ALLOWED_CODES)
            self.assertLessEqual(len(error.code), 32)
            text = str(error)
            self.assertNotIn(secret, text)
            self.assertNotIn(KEY_ID, text)
            self.assertNotIn(OWNER, text)


if __name__ == "__main__":
    unittest.main()
