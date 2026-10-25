"""Offline negative tests for the Hermes Steward read client."""

from __future__ import annotations

import copy
import json
import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.business_mcp_auth.contracts import (  # noqa: E402
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.hermes_steward.client import (  # noqa: E402
    ALLOWED_TOOLS,
    REQUIRED_SCOPE,
    StewardReadClient,
)
from integrations.mastermind_secretary_mcp.schemas import (  # noqa: E402
    MAX_REQUEST_BYTES,
    TOOL_SPECS,
)

NOW = 1_800_000_000
ISSUER = "https://identity.example.invalid/"
SUBJECT = "fixture-subject"
SECRET = "fixture-bearer-sentinel-do-not-log"


def _policy():
    digest = subject_digest(issuer=ISSUER, subject=SUBJECT)
    return load_resource_policy(
        {
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "mastermind-steward-v1",
            "resource": "https://mcp.example.invalid/mcp/steward/v1",
            "resource_metadata_url": "https://mcp.example.invalid/.well-known/oauth-protected-resource/mcp/steward/v1",
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": "https://identity.example.invalid/.well-known/jwks.json",
            "required_scopes": [REQUIRED_SCOPE],
            "allowed_subject_digests": [digest],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _claims(*, exp: int, iat: int, scope: str, aud: str | None = None) -> dict:
    return {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": aud or "https://mcp.example.invalid/mcp/steward/v1",
        "iat": iat,
        "exp": exp,
        "scope": scope,
    }


class MapVerifier:
    def __init__(self, claims_by_token: dict[str, dict]) -> None:
        self.claims_by_token = claims_by_token
        self.seen: list[str] = []

    def verify(self, token: str) -> dict:
        self.seen.append(token)
        try:
            return self.claims_by_token[token]
        except KeyError as exc:
            raise AuthError(AuthErrorCode.TOKEN_SIGNATURE_REFUSED) from exc


class ScriptedUpstream:
    def __init__(self, responses: list[object] | None = None, *, boom: BaseException | None = None) -> None:
        self.responses = list(responses or [])
        self.boom = boom
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, dict(arguments)))
        if self.boom is not None:
            raise self.boom
        payload = self.responses.pop(0)
        if not isinstance(payload, dict):
            raise AssertionError("scripted payload must be a dict when returned")
        return payload


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = _policy()
        self.good_claims = _claims(iat=NOW - 30, exp=NOW + 300, scope=REQUIRED_SCOPE)
        self.verifier = MapVerifier({"fixture-good-token": self.good_claims})
        self.upstream = ScriptedUpstream(
            [
                {
                    "schema": "mastermind.secretary_grounding_mcp_result.v2",
                    "tool": "list_responsibilities",
                    "ok": True,
                    "data": {
                        "state": "UNKNOWN",
                        "subjects": [],
                        "reason_codes": ["NO_SOURCE"],
                    },
                    "error": None,
                }
            ]
        )
        self.client = StewardReadClient(
            policy=self.policy,
            verifier=self.verifier,
            upstream=self.upstream,
            now=NOW,
        )

    def _read(self, tool: str = "list_responsibilities", arguments=None, authorization=None, token: str = "fixture-good-token"):
        header = authorization
        if header is None:
            header = f"Bearer {token}"
        return self.client.read(tool, {} if arguments is None else arguments, authorization=header)

    def test_allowlist_is_exactly_the_six_steward_reads(self) -> None:
        self.assertEqual(len(ALLOWED_TOOLS), 6)
        self.assertEqual(ALLOWED_TOOLS, tuple(spec.name for spec in TOOL_SPECS))
        self.assertEqual(
            ALLOWED_TOOLS,
            (
                "list_responsibilities",
                "get_responsibility",
                "get_attention",
                "get_current_runtime",
                "explain_blocker",
                "resolve_surface",
            ),
        )
        self.assertTrue(all(spec.read_only for spec in TOOL_SPECS))

    def test_expired_token_is_refused_and_not_forwarded(self) -> None:
        self.verifier.claims_by_token["fixture-expired-token"] = _claims(
            iat=NOW - 400, exp=NOW - 100, scope=REQUIRED_SCOPE
        )
        result = self._read(token="fixture-expired-token")
        self.assertEqual(result["error"]["code"], "TOKEN_EXPIRED")
        self.assertFalse(result["forwarded"])
        self.assertIsNone(result["data"])
        self.assertEqual(self.upstream.calls, [])

    def test_wrong_token_is_refused_and_not_forwarded(self) -> None:
        result = self._read(token="fixture-wrong-token")
        self.assertEqual(result["error"]["code"], "TOKEN_REJECTED")
        self.assertFalse(result["forwarded"])
        self.assertIsNone(result["data"])
        self.assertEqual(self.upstream.calls, [])
        self.assertNotIn("fixture-wrong-token", json.dumps(result))

    def test_missing_token_is_refused(self) -> None:
        result = self.client.read("list_responsibilities", {}, authorization=None)
        self.assertEqual(result["error"]["code"], "AUTHORIZATION_MISSING")
        self.assertEqual(self.upstream.calls, [])
        self.assertEqual(self.verifier.seen, [])

    def test_wrong_audience_is_refused(self) -> None:
        self.verifier.claims_by_token["fixture-audience-token"] = _claims(
            iat=NOW - 30,
            exp=NOW + 300,
            scope=REQUIRED_SCOPE,
            aud="https://mcp.example.invalid/mcp/other",
        )
        result = self._read(token="fixture-audience-token")
        self.assertEqual(result["error"]["code"], "AUDIENCE_REJECTED")
        self.assertEqual(self.upstream.calls, [])

    def test_wrong_scope_is_refused(self) -> None:
        for scope in (
            "mastermind.executive.read",
            "mastermind.executive.write",
            f"{REQUIRED_SCOPE} mastermind.executive.write",
            "offline_access",
        ):
            with self.subTest(scope=scope):
                token = f"fixture-scope-{scope.split()[0]}"
                self.verifier.claims_by_token[token] = _claims(
                    iat=NOW - 30, exp=NOW + 300, scope=scope
                )
                upstream = ScriptedUpstream([])
                client = StewardReadClient(
                    policy=self.policy,
                    verifier=self.verifier,
                    upstream=upstream,
                    now=NOW,
                )
                result = client.read("list_responsibilities", {}, authorization=f"Bearer {token}")
                self.assertEqual(result["error"]["code"], "SCOPE_REJECTED")
                self.assertEqual(upstream.calls, [])

    def test_offline_access_does_not_become_write_authority(self) -> None:
        token = "fixture-offline-token"
        self.verifier.claims_by_token[token] = _claims(
            iat=NOW - 30,
            exp=NOW + 300,
            scope=f"{REQUIRED_SCOPE} offline_access",
        )
        result = self._read(token=token)
        self.assertTrue(result["forwarded"])
        self.assertEqual(self.upstream.calls[0][0], "list_responsibilities")

    def test_oversized_body_is_refused(self) -> None:
        arguments = {"pad": "x" * (MAX_REQUEST_BYTES + 1)}
        result = self._read(arguments=arguments)
        self.assertEqual(result["error"]["code"], "REQUEST_TOO_LARGE")
        self.assertFalse(result["forwarded"])
        self.assertEqual(self.upstream.calls, [])
        self.assertNotIn("x" * 40, json.dumps(result))

    def test_unknown_tool_is_refused(self) -> None:
        result = self._read(tool="list_widgets")
        self.assertEqual(result["error"]["code"], "UNKNOWN_TOOL")
        self.assertEqual(result["tool"], "unknown")
        self.assertEqual(self.upstream.calls, [])

    def test_write_attempt_is_refused(self) -> None:
        for tool in ("submit_executive_intent", "create_job", "delete_responsibility", "write"):
            with self.subTest(tool=tool):
                upstream = ScriptedUpstream([])
                client = StewardReadClient(
                    policy=self.policy,
                    verifier=self.verifier,
                    upstream=upstream,
                    now=NOW,
                )
                result = client.read(tool, {"responsibility_ref": "responsibility:wp3.steward"}, authorization="Bearer fixture-good-token")
                self.assertEqual(result["error"]["code"], "WRITE_REFUSED")
                self.assertFalse(result["forwarded"])
                self.assertIsNone(result["data"])
                self.assertEqual(upstream.calls, [])

    def test_write_argument_on_a_read_tool_is_refused(self) -> None:
        result = self._read(
            tool="get_responsibility",
            arguments={"responsibility_ref": "responsibility:wp3.steward", "mutation": "apply"},
        )
        self.assertEqual(result["error"]["code"], "WRITE_REFUSED")
        self.assertEqual(self.upstream.calls, [])

    def test_degraded_payload_is_copied_without_synthesis(self) -> None:
        degraded = {
            "schema": "mastermind.secretary_grounding_mcp_result.v2",
            "tool": "get_responsibility",
            "ok": True,
            "data": {
                "state": "DEGRADED",
                "subjects": [
                    {
                        "subject_ref": "responsibility:wp3.steward",
                        "facts": [
                            {
                                "predicate": "responsibility.title",
                                "value": "Steward read bridge",
                                "freshness": "STALE",
                                "sources": [
                                    {
                                        "owner": "agent_os",
                                        "source_ref": "WS:wp3",
                                        "observed_at": None,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "reason_codes": ["NO_SOURCE"],
            },
            "error": None,
        }
        self.upstream.responses = [degraded]
        result = self._read(
            tool="get_responsibility",
            arguments={"responsibility_ref": "responsibility:wp3.steward"},
        )
        self.assertEqual(result["data"], degraded)
        self.assertEqual(result["data"]["data"]["state"], "DEGRADED")
        encoded = json.dumps(result["data"])
        self.assertNotIn("responsibility.objective", encoded)
        self.assertNotIn("requested_action", encoded)
        degraded["data"]["subjects"].append({"injected": True})
        self.assertNotIn("injected", json.dumps(result["data"]))

    def test_unknown_payload_stays_unknown(self) -> None:
        unknown = {
            "schema": "mastermind.secretary_grounding_mcp_result.v2",
            "tool": "get_attention",
            "ok": True,
            "data": {"state": "UNKNOWN", "subjects": [], "reason_codes": ["NO_SOURCE"]},
            "error": None,
        }
        self.upstream.responses = [unknown]
        result = self._read(tool="get_attention")
        self.assertEqual(result["data"]["data"]["state"], "UNKNOWN")
        self.assertEqual(result["data"]["data"]["subjects"], [])
        self.assertNotIn("attention.requested_action", json.dumps(result))
        self.assertNotIn("attention.reason", json.dumps(result))

    def test_incomplete_facts_are_not_completed(self) -> None:
        partial = {
            "ok": True,
            "data": {
                "state": "FACTS",
                "subjects": [
                    {"subject_ref": "responsibility:wp3.steward", "facts": []}
                ],
                "reason_codes": [],
            },
        }
        self.upstream.responses = [partial]
        result = self._read(tool="get_current_runtime", arguments={"responsibility_ref": "responsibility:wp3.steward"})
        self.assertEqual(result["data"]["data"]["state"], "FACTS")
        self.assertEqual(result["data"]["data"]["subjects"][0]["facts"], [])
        encoded = json.dumps(result["data"])
        self.assertNotIn("runtime.attempt_ref", encoded)
        self.assertNotIn("runtime.worker_ref", encoded)
        self.assertNotIn("surface.ref", encoded)

    def test_source_disappearance_is_unavailable_not_invented(self) -> None:
        upstream = ScriptedUpstream(boom=RuntimeError("source disappeared at /tmp/fixture-secret-path"))
        client = StewardReadClient(
            policy=self.policy, verifier=self.verifier, upstream=upstream, now=NOW
        )
        with self.assertLogs("integrations.hermes_steward", level="INFO") as captured:
            result = client.read(
                "explain_blocker",
                {"responsibility_ref": "responsibility:wp3.steward"},
                authorization="Bearer fixture-good-token",
            )
        self.assertEqual(result["error"]["code"], "UPSTREAM_UNAVAILABLE")
        self.assertIsNone(result["data"])
        self.assertNotIn("subjects", json.dumps(result["data"]))
        blob = json.dumps(result) + "\n" + "\n".join(captured.output)
        self.assertNotIn("fixture-secret-path", blob)
        self.assertNotIn("/tmp/", blob)

    def test_later_source_correction_replaces_the_previous_read(self) -> None:
        first = {
            "data": {
                "state": "DEGRADED",
                "subjects": [],
                "reason_codes": ["STALE_SOURCE"],
            }
        }
        corrected = {
            "data": {
                "state": "UNKNOWN",
                "subjects": [],
                "reason_codes": ["NO_SOURCE"],
            }
        }
        upstream = ScriptedUpstream([copy.deepcopy(first), copy.deepcopy(corrected)])
        client = StewardReadClient(
            policy=self.policy, verifier=self.verifier, upstream=upstream, now=NOW
        )
        earlier = client.read("resolve_surface", {"responsibility_ref": "responsibility:wp3.steward"}, authorization="Bearer fixture-good-token")
        later = client.read("resolve_surface", {"responsibility_ref": "responsibility:wp3.steward"}, authorization="Bearer fixture-good-token")
        self.assertEqual(earlier["data"], first)
        self.assertEqual(later["data"], corrected)
        self.assertNotEqual(earlier["data"], later["data"])
        self.assertEqual(len(upstream.calls), 2)
        stored = json.dumps(client.__dict__, default=str)
        self.assertNotIn("STALE_SOURCE", stored)
        self.assertNotIn("NO_SOURCE", stored)

    def test_secrets_are_never_logged(self) -> None:
        self.verifier.claims_by_token[SECRET] = _claims(
            iat=NOW - 400, exp=NOW - 100, scope=REQUIRED_SCOPE
        )
        logger = logging.getLogger("integrations.hermes_steward")
        logger.setLevel(logging.INFO)
        with self.assertLogs("integrations.hermes_steward", level="INFO") as captured:
            result = self.client.read(
                "list_responsibilities",
                {},
                authorization=f"Bearer {SECRET}",
            )
        blob = json.dumps(result) + "\n" + "\n".join(captured.output)
        self.assertEqual(result["error"]["code"], "TOKEN_EXPIRED")
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("Bearer", blob)
        self.assertNotIn("fixture-good-token", blob)

    def test_clock_advances_between_reads(self) -> None:
        # Policy clock skew is 30s, so expiry is now > exp + skew.
        instants = iter((NOW, NOW + 331))
        upstream = ScriptedUpstream(
            [
                {
                    "schema": "mastermind.secretary_grounding_mcp_result.v2",
                    "tool": "list_responsibilities",
                    "ok": True,
                    "data": {"state": "UNKNOWN", "subjects": [], "reason_codes": ["NO_SOURCE"]},
                    "error": None,
                }
            ]
        )
        client = StewardReadClient(
            policy=self.policy,
            verifier=self.verifier,
            upstream=upstream,
            now=NOW,
            clock=lambda: next(instants),
        )
        first = client.read("list_responsibilities", {}, authorization="Bearer fixture-good-token")
        second = client.read("list_responsibilities", {}, authorization="Bearer fixture-good-token")
        self.assertTrue(first["forwarded"])
        self.assertEqual(second["error"]["code"], "TOKEN_EXPIRED")
        self.assertEqual(len(upstream.calls), 1)

    def test_non_ascii_and_oversized_bearers_are_rejected(self) -> None:
        non_ascii = self.client.read(
            "list_responsibilities",
            {},
            authorization="Bearer fixture-good-token\u00e9",
        )
        self.assertEqual(non_ascii["error"]["code"], "TOKEN_REJECTED")
        self.assertEqual(self.upstream.calls, [])
        huge = "a" * ((16 * 1024) + 1)
        oversized = self.client.read("list_responsibilities", {}, authorization=f"Bearer {huge}")
        self.assertEqual(oversized["error"]["code"], "TOKEN_REJECTED")
        self.assertNotIn(huge, json.dumps(oversized))

    def test_client_source_has_no_write_or_network_entry(self) -> None:
        source = (ROOT / "integrations" / "hermes_steward" / "client.py").read_text(encoding="utf-8")
        self.assertNotIn("def write", source)
        self.assertNotIn("def submit", source)
        self.assertNotIn("def create_", source)
        for banned in ("socket", "httpx", "requests", "subprocess", "urllib"):
            self.assertNotIn(f"import {banned}", source)
        self.assertFalse(hasattr(StewardReadClient, "write"))


if __name__ == "__main__":
    unittest.main()
