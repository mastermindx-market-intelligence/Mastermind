"""Strict model-facing Steward reads: one verified Company source, no authority escalation."""
from __future__ import annotations

import copy
import json
import unittest

from integrations.hermes_steward.client import REQUIRED_SCOPE, StewardReadClient
from integrations.hermes_steward.tests.test_client import (
    NOW, MapVerifier, ScriptedUpstream, _claims, _policy,
)
from integrations.mastermind_secretary_mcp.schemas import (
    error_envelope, result_envelope,
)

_REF = "responsibility:alpha"
_SOURCE = {
    "owner": "agent_os",
    "source_ref": "WS:ALPHA",
    "observed_at": "2026-11-02T02:00:00Z",
}


def _fact(predicate: str, value: str) -> dict:
    return {
        "subject_ref": _REF,
        "predicate": predicate,
        "value": value,
        "freshness": "FRESH",
        "sources": [dict(_SOURCE)],
    }


def _verified() -> dict:
    return result_envelope(
        "get_responsibility",
        data={
            "state": "FACTS",
            "facts": [
                _fact("responsibility.identity", "WS:ALPHA"),
                _fact("responsibility.title", "Release qualification"),
                _fact("responsibility.objective", "Validate the existing product journey"),
                _fact("responsibility.next_action", "Obtain nonauthor source review"),
                _fact("responsibility.state", "ACTIVE"),
            ],
            "reason_codes": [],
        },
        expected_subject_ref=_REF,
    )


def _client(payload: object, *, expired: bool = False):
    now = NOW
    claims = _claims(iat=NOW - 400 if expired else NOW - 30,
                     exp=NOW - 100 if expired else NOW + 300,
                     scope=REQUIRED_SCOPE)
    verifier = MapVerifier({"synthetic-fixture": claims})
    upstream = ScriptedUpstream([copy.deepcopy(payload)])
    return StewardReadClient(
        policy=_policy(), verifier=verifier, upstream=upstream, now=now,
    ), upstream


class ModelFacingStewardTests(unittest.TestCase):
    def _read(self, payload, *, expired=False):
        client, upstream = _client(payload, expired=expired)
        result = client.read_grounded(
            "get_responsibility", {"responsibility_ref": _REF},
            authorization="Bearer synthetic-fixture",
        )
        return result, upstream.calls

    def test_existing_source_fact_contract_round_trips_to_model_without_rewriting(self):
        source = _verified()
        result, calls = self._read(source)
        self.assertTrue(result["ok"])
        self.assertTrue(result["forwarded"])
        self.assertEqual(result["data"], source)
        self.assertEqual(calls, [("get_responsibility", {"responsibility_ref": _REF})])
        blob = json.dumps(result)
        self.assertIn("source_ref", blob)
        self.assertIn("observed_at", blob)
        self.assertNotIn("synthetic-fixture", blob)

    def test_unknown_with_no_source_is_still_unknown_not_no_attention(self):
        source = result_envelope(
            "get_responsibility",
            data={"state": "UNKNOWN", "facts": [], "reason_codes": ["NO_SOURCE"]},
        )
        result, calls = self._read(source)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["data"]["state"], "UNKNOWN")
        self.assertEqual(result["data"]["data"]["reason_codes"], ["NO_SOURCE"])
        self.assertEqual(result["data"]["data"]["subjects"], [])
        self.assertEqual(len(calls), 1)

    def test_known_upstream_refusal_has_no_facts_and_no_false_success(self):
        source = error_envelope("get_responsibility", "STEWARD_UNAVAILABLE")
        result, calls = self._read(source)
        self.assertFalse(result["ok"])
        self.assertTrue(result["forwarded"])
        self.assertIsNone(result["data"])
        self.assertEqual(result["error"]["code"], "STEWARD_UNAVAILABLE")
        self.assertEqual(len(calls), 1)

    def test_expired_token_fails_before_any_source_read(self):
        result, calls = self._read(_verified(), expired=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "TOKEN_EXPIRED")
        self.assertFalse(result["forwarded"])
        self.assertEqual(calls, [])

    def test_wrong_tool_unexpected_field_or_forged_fact_is_never_displayable(self):
        for case in ("tool", "extra", "subject", "missing", "owner",
                     "error_detail", "huge"):
            with self.subTest(case=case):
                source = copy.deepcopy(_verified())
                if case == "tool":
                    source["tool"] = "get_attention"
                elif case == "extra":
                    source["unexpected"] = "forged"
                elif case == "subject":
                    source["data"]["subjects"][0]["subject_ref"] = "responsibility:other"
                elif case == "missing":
                    facts = source["data"]["subjects"][0]["facts"]
                    source["data"]["subjects"][0]["facts"] = [
                        f for f in facts if f["predicate"] != "responsibility.next_action"
                    ]
                elif case == "owner":
                    source["data"]["subjects"][0]["facts"][0]["sources"][0]["owner"] = "unknown"
                elif case == "error_detail":
                    source["ok"] = False
                    source["error"] = {"code": "STEWARD_UNAVAILABLE",
                                       "message": "Bearer fixture-secret"}
                elif case == "huge":
                    source["unexpected"] = "x" * 70000
                result, calls = self._read(source)
                self.assertFalse(result["ok"])
                self.assertFalse(result["forwarded"])
                self.assertIsNone(result["data"])
                self.assertEqual(result["error"]["code"], "UPSTREAM_INVALID")
                self.assertEqual(len(calls), 1)
                self.assertNotIn("fixture-secret", json.dumps(result))

    def test_auth_and_tool_refusals_do_not_fall_back_to_unvalidated_read(self):
        client, upstream = _client(_verified())
        forbidden = client.read_grounded(
            "write_company_state", {"command": "post"},
            authorization="Bearer synthetic-fixture",
        )
        self.assertFalse(forbidden["ok"])
        self.assertEqual(forbidden["error"]["code"], "WRITE_REFUSED")
        self.assertEqual(upstream.calls, [])


if __name__ == "__main__":
    unittest.main()
