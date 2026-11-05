"""Tests for the pure principal owner-namespace helper.

The OS Executive transport derives one documented, stable, opaque owner
namespace from a verified principal's closed identity fields.  The recipe
used to live inline in ``integrations.mastermind_executive_app.os_transport``,
behind that module's top-level Starlette imports, so the pinned, root-owned
runtime (``python3.12 -I -S -B``: no site, no third-party packages, no
bytecode) could not evaluate it.  The recipe now lives in
``integrations.mastermind_executive_app.principal_namespace``, a
stdlib-only module, and the transport's public ``principal_scope`` delegates
to it unchanged.

These tests pin four facts:

1. The helper reproduces the ORIGINAL recipe byte for byte.  Golden digests
   below were derived independently of this repository (Python ``hashlib``
   over the exact material bytes, cross-checked with ``openssl dgst
   -sha256``) and are hard-coded here, so a recipe drift fails loudly.
2. The recipe is discriminating: the literal resource rides as literal
   UTF-8 (never its digest), the fields are joined with exactly NUL bytes
   (no other joiner, no length framing), Unicode ``client_ref``/``resource``
   ride as UTF-8, and ``issuer_digest``/``subject_digest`` stay ASCII-strict.
3. The transport's public ``principal_scope`` delegates byte for byte on a
   real ``VerifiedPrincipal``.  These tests skip honestly where the
   transport's edge dependencies (Starlette) are genuinely absent — no shim
   stands in for it.
4. The helper imports and computes under the actual pinned flags
   (``-I -S -B``), via package import and via direct file load, with the
   package ``__init__`` staying inert.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.mastermind_executive_app.principal_namespace import (
    NAMESPACE_SCOPE,
    principal_scope_from_identity,
)

# Honest dependency detection for the transport delegation tests.  Under the
# pinned runtime the transport's Starlette import fails; that absence skips
# the delegation class below, it never fakes the transport.
try:
    from integrations.business_mcp_auth.contracts import VerifiedPrincipal
    from integrations.mastermind_executive_app import os_transport
    _TRANSPORT_IMPORTABLE = True
    _TRANSPORT_IMPORT_ERROR: Exception | None = None
except ImportError as _exc:  # pragma: no cover - depends on host
    _TRANSPORT_IMPORTABLE = False
    _TRANSPORT_IMPORT_ERROR = _exc

#: The documented recipe prefix, restated literally so the module constant
#: cannot drift without this file noticing.
_NAMESPACE = b"mastermind.os.executive.principal_scope.v1"

#: (issuer_digest, subject_digest, client_ref, resource, expected hex digest)
#: Every expected value was computed from the exact material bytes by an
#: independent SHA-256 implementation (openssl) outside this repository.
GOLDEN_VECTORS = (
    (
        "a3f1c2d4e5b60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
        "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "exec-web-7f3a",
        "owner_context",
        "2450199c84db17543129de2970a466a0e93208d79d88a2172ff32ac2518bb7c1",
    ),
    (
        "b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3",
        "7a8b9c0d1e2f3a4b5c6d7e8f90a1b2c37a8b9c0d1e2f3a4b5c6d7e8f90a1b2c3",
        "确保-éø-7f3a",
        "board-packets/2026-Q3–策略",
        "4a82dd7598b5c97fc310a5dacc6a790004f162561ad8485cf694cc5620b67b89",
    ),
    (
        "",
        "",
        "",
        "",
        "988108edb0eca5b3ff23eecbe4830e12bdb8e6ef9bee4ce4451be0ac3bd30090",
    ),
    (
        "Issuer.Example+9=",
        "Subject-42",
        "ref/with/slashes",
        "背景 file.txt",
        "dc046e4e4c3d587a31d8f8037c50c80205831947acea40f044c24f5e2537d9f6",
    ),
)

_HEX_DIGITS = set("0123456789abcdef")


def _scope(issuer: str, subject: str, client_ref: str, resource: str) -> str:
    """The documented recipe, restated independently of the helper module."""

    material = b"\0".join((
        _NAMESPACE,
        issuer.encode("ascii"),
        subject.encode("ascii"),
        client_ref.encode("utf-8"),
        resource.encode("utf-8"),
    ))
    return hashlib.sha256(material).hexdigest()


class GoldenVectorTests(unittest.TestCase):
    """The helper reproduces the original algorithm byte for byte."""

    def test_golden_vectors_match_independent_recipe(self) -> None:
        for issuer, subject, client_ref, resource, expected in GOLDEN_VECTORS:
            with self.subTest(resource=resource, client_ref=client_ref):
                self.assertEqual(
                    principal_scope_from_identity(
                        issuer_digest=issuer,
                        subject_digest=subject,
                        client_ref=client_ref,
                        resource=resource,
                    ),
                    expected,
                )
                # The restated recipe in this file agrees with the hard-coded
                # golden digest, so vector and helper cannot drift together.
                self.assertEqual(_scope(issuer, subject, client_ref, resource),
                                 expected)

    def test_scope_is_lowercase_hex64(self) -> None:
        for issuer, subject, client_ref, resource, expected in GOLDEN_VECTORS:
            with self.subTest(resource=resource):
                scope = principal_scope_from_identity(
                    issuer_digest=issuer,
                    subject_digest=subject,
                    client_ref=client_ref,
                    resource=resource,
                )
                self.assertEqual(len(scope), 64)
                self.assertTrue(set(scope) <= _HEX_DIGITS)
                self.assertEqual(scope, scope.lower())

    def test_namespace_scope_constant_is_the_documented_prefix(self) -> None:
        self.assertEqual(NAMESPACE_SCOPE, _NAMESPACE)


class RecipeShapeTests(unittest.TestCase):
    """Discriminating properties of the one fixed recipe."""

    _ISSUER = GOLDEN_VECTORS[0][0]
    _SUBJECT = GOLDEN_VECTORS[0][1]
    _CLIENT_REF = GOLDEN_VECTORS[0][2]
    _RESOURCE = GOLDEN_VECTORS[0][3]

    def _scope(self, *, issuer_digest: str, subject_digest: str,
               client_ref: str, resource: str) -> str:
        return principal_scope_from_identity(
            issuer_digest=issuer_digest,
            subject_digest=subject_digest,
            client_ref=client_ref,
            resource=resource,
        )

    def test_resource_is_literal_utf8_never_its_digest(self) -> None:
        resource_hex = hashlib.sha256(self._RESOURCE.encode("utf-8")).hexdigest()
        self.assertNotEqual(self._RESOURCE, resource_hex)
        literal = self._scope(
            issuer_digest=self._ISSUER,
            subject_digest=self._SUBJECT,
            client_ref=self._CLIENT_REF,
            resource=self._RESOURCE,
        )
        hashed = self._scope(
            issuer_digest=self._ISSUER,
            subject_digest=self._SUBJECT,
            client_ref=self._CLIENT_REF,
            resource=resource_hex,
        )
        self.assertNotEqual(literal, hashed)
        self.assertEqual(literal, GOLDEN_VECTORS[0][4])

    def test_joining_is_exactly_nul_no_other_joiner_or_framing(self) -> None:
        material = (
            _NAMESPACE,
            self._ISSUER.encode("ascii"),
            self._SUBJECT.encode("ascii"),
            self._CLIENT_REF.encode("utf-8"),
            self._RESOURCE.encode("utf-8"),
        )
        expected = GOLDEN_VECTORS[0][4]
        self.assertEqual(hashlib.sha256(b"\0".join(material)).hexdigest(),
                         expected)
        # Any other joiner, or length framing, would produce a different
        # namespace; the recipe admits none of them.
        self.assertNotEqual(
            hashlib.sha256(b"".join(material)).hexdigest(), expected)
        self.assertNotEqual(
            hashlib.sha256(b"\n".join(material)).hexdigest(), expected)
        self.assertNotEqual(
            hashlib.sha256(
                b"".join(bytes((len(part),)) + part for part in material)
            ).hexdigest(),
            expected,
        )

    def test_embedded_nuls_join_exactly_as_current_semantics(self) -> None:
        # The current recipe joins raw field bytes with NUL and frames
        # nothing, so embedded NULs are not escaped.  This pins that exact
        # behavior: the helper preserves it rather than silently adding
        # unescaping or length prefixes.
        first = self._scope(issuer_digest="a", subject_digest="b\0c",
                            client_ref="x", resource="y")
        second = self._scope(issuer_digest="a\0b", subject_digest="c",
                             client_ref="x", resource="y")
        self.assertEqual(first, second)
        self.assertEqual(first, _scope("a", "b\0c", "x", "y"))

    def test_unicode_client_ref_and_resource_ride_as_utf8(self) -> None:
        issuer, subject, client_ref, resource, expected = GOLDEN_VECTORS[1]
        self.assertEqual(
            self._scope(issuer_digest=issuer, subject_digest=subject,
                        client_ref=client_ref, resource=resource),
            expected,
        )
        # Encoding the Unicode fields to their literal UTF-8 bytes before the
        # digest is what the golden digest pins; any surrogateescape or
        # ASCII fallback would diverge.
        self.assertEqual(
            hashlib.sha256(b"\0".join((
                _NAMESPACE,
                issuer.encode("ascii"),
                subject.encode("ascii"),
                client_ref.encode("utf-8"),
                resource.encode("utf-8"),
            ))).hexdigest(),
            expected,
        )

    def test_issuer_and_subject_remain_ascii_strict(self) -> None:
        for field in ("issuer_digest", "subject_digest"):
            with self.subTest(field=field):
                kwargs = {
                    "issuer_digest": self._ISSUER,
                    "subject_digest": self._SUBJECT,
                    "client_ref": self._CLIENT_REF,
                    "resource": self._RESOURCE,
                }
                kwargs[field] = "é-Ø-策略"
                with self.assertRaises(UnicodeEncodeError):
                    self._scope(**kwargs)

    def test_non_ascii_client_ref_and_resource_are_accepted(self) -> None:
        # Unicode is admitted in client_ref and resource (UTF-8), only the
        # two digest fields are ASCII-strict.  Golden vector 2 asserts the
        # exact bytes; this asserts acceptance itself.
        scope = self._scope(issuer_digest=self._ISSUER,
                            subject_digest=self._SUBJECT,
                            client_ref="确保-éø", resource="背景/文件.txt")
        self.assertEqual(len(scope), 64)

    def test_fields_are_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            principal_scope_from_identity(  # type: ignore[misc]
                self._ISSUER, self._SUBJECT, self._CLIENT_REF,
                self._RESOURCE,
            )

    def test_helper_module_is_stdlib_only_with_no_relative_imports(self
                                                                    ) -> None:
        source = (REPO_ROOT
                  / "integrations/mastermind_executive_app"
                  / "principal_namespace.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name, {"hashlib"})
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module or "", {"__future__", "hashlib"})
                self.assertEqual(node.level, 0)


@unittest.skipUnless(
    _TRANSPORT_IMPORTABLE,
    f"transport edge dependencies unavailable: {_TRANSPORT_IMPORT_ERROR}",
)
class TransportDelegationTests(unittest.TestCase):
    """The public transport function delegates byte for byte.

    Skipped where the transport's edge dependencies are genuinely missing —
    never stubbed.
    """

    def _principal(self, **overrides: object) -> "VerifiedPrincipal":
        values: dict[str, object] = {
            "policy_id": "os-executive-v3",
            "issuer": "https://auth.mastermind-x.com/",
            "issuer_digest": GOLDEN_VECTORS[0][0],
            "resource": "owner_context",
            "subject_digest": GOLDEN_VECTORS[0][1],
            "client_ref": GOLDEN_VECTORS[0][2],
            "scopes": ("os.owner_context.read",),
            "issued_at": 1_800_000_000,
            "expires_at": 1_800_000_300,
            "jti_digest": None,
        }
        values.update(overrides)
        return VerifiedPrincipal(**values)

    def test_public_principal_scope_matches_helper_on_real_principal(
        self,
    ) -> None:
        principal = self._principal()
        self.assertEqual(
            os_transport.principal_scope(principal),
            principal_scope_from_identity(
                issuer_digest=principal.issuer_digest,
                subject_digest=principal.subject_digest,
                client_ref=principal.client_ref,
                resource=principal.resource,
            ),
        )

    def test_public_principal_scope_matches_golden_digest(self) -> None:
        principal = self._principal()
        self.assertEqual(os_transport.principal_scope(principal),
                         GOLDEN_VECTORS[0][4])

    def test_delegation_preserves_unicode_and_error_semantics(self) -> None:
        issuer, subject, client_ref, resource, expected = GOLDEN_VECTORS[1]
        principal = self._principal(
            issuer_digest=issuer,
            subject_digest=subject,
            client_ref=client_ref,
            resource=resource,
        )
        self.assertEqual(os_transport.principal_scope(principal), expected)
        with self.assertRaises(UnicodeEncodeError):
            os_transport.principal_scope(self._principal(issuer_digest="é"))


_TRANSPORT_PROBE = r'''
import importlib.util
import sys
from pathlib import Path

assert sys.flags.isolated == 1, sys.flags
assert sys.flags.no_site == 1, sys.flags
assert sys.flags.dont_write_bytecode == 1, sys.flags
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))

# Package import under the pinned runtime: no site, no ambient path.
from integrations.mastermind_executive_app import principal_namespace
assert principal_namespace.NAMESPACE_SCOPE == \
    b"mastermind.os.executive.principal_scope.v1"

vectors = eval(sys.argv[2])  # Delivered by the test below, never user input.
for issuer, subject, client_ref, resource, expected in vectors:
    got = principal_namespace.principal_scope_from_identity(
        issuer_digest=issuer, subject_digest=subject,
        client_ref=client_ref, resource=resource)
    assert got == expected, (got, expected)

# Direct file load: the module must not need its package context either.
spec = importlib.util.spec_from_file_location(
    "principal_namespace_direct",
    repo / "integrations/mastermind_executive_app/principal_namespace.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.principal_scope_from_identity(
    issuer_digest=vectors[0][0], subject_digest=vectors[0][1],
    client_ref=vectors[0][2], resource=vectors[0][3]) == vectors[0][4]

# The package __init__ stays inert: importing the package must not pull in
# the Starlette-backed transport.
import integrations.mastermind_executive_app as package
assert "integrations.mastermind_executive_app.os_transport" \
    not in sys.modules
print("PINNED_NAMESPACE_HELPER_OK", len(vectors))
'''


class PinnedRuntimeImportTests(unittest.TestCase):
    """The helper imports and computes under the actual pinned flags."""

    def test_helper_imports_and_computes_under_pinned_isolated_runtime(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", _TRANSPORT_PROBE,
             str(REPO_ROOT), repr(GOLDEN_VECTORS)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertEqual(result.stdout.split()[-2:], ["PINNED_NAMESPACE_HELPER_OK", "4"])

    def test_edge_transport_stays_out_of_the_pinned_runtime(self) -> None:
        # Documents the structural fact this extraction answers: the
        # transport module itself cannot be imported under -I -S -B, so the
        # pure helper is the pinned runtime's only route to this recipe.  If
        # this ever starts importing, the premise changed and must be
        # reviewed, not silently absorbed.
        probe = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "try:\n"
            "    import integrations.mastermind_executive_app.os_transport\n"
            "except ModuleNotFoundError as exc:\n"
            "    print('TRANSPORT_NOT_PINNED_IMPORTABLE', exc.name)\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit('transport imported under pinned runtime')\n"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", probe, str(REPO_ROOT)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("TRANSPORT_NOT_PINNED_IMPORTABLE", result.stdout)


class PackageInertnessTests(unittest.TestCase):
    """The package ``__init__`` files stay inert under the pinned runtime."""

    def test_mastermind_executive_app_init_imports_nothing(self) -> None:
        source = (REPO_ROOT / "integrations/mastermind_executive_app"
                  / "__init__.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                self.fail(f"package __init__ grew an import: {node}")
            if isinstance(node, ast.ImportFrom):
                self.assertEqual(node.module, "__future__")


if __name__ == "__main__":
    unittest.main()
