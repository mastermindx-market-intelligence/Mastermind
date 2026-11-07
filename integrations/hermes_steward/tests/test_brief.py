"""Pure company-brief consumption from existing authenticated Steward reads."""
from __future__ import annotations

import json
import unittest

from integrations.hermes_steward.brief import responsibility_brief
from integrations.hermes_steward.tests.test_client import (
    NOW, MapVerifier, ScriptedUpstream, _claims, _policy,
)
from integrations.hermes_steward.tests.test_client_grounded import _REF, _verified
from integrations.hermes_steward.client import REQUIRED_SCOPE, StewardReadClient
from integrations.mastermind_secretary_mcp.schemas import result_envelope


def _unknown(tool: str, reason: str) -> dict:
    return result_envelope(
        tool,
        data={"state": "UNKNOWN", "facts": [], "reason_codes": [reason]},
    )


def _make(responses, *, exp=NOW + 300, clock=None):
    upstream = ScriptedUpstream(responses)
    verifier = MapVerifier({
        "brief-fixture-token": _claims(iat=NOW - 30, exp=exp, scope=REQUIRED_SCOPE),
    })
    reader = StewardReadClient(
        policy=_policy(), verifier=verifier, upstream=upstream, now=NOW,
        clock=clock,
    )
    return reader, upstream, verifier


class CompanyResponsibilityBriefTests(unittest.TestCase):
    def test_one_exact_responsibility_preserves_provenance_and_unknown_sections(self):
        reader, upstream, verifier = _make([
            _verified(),
            _unknown("get_current_runtime", "RUNTIME_UNKNOWN"),
            _unknown("explain_blocker", "NO_SOURCE"),
        ])
        value = responsibility_brief(
            reader, responsibility_ref=_REF,
            authorization="Bearer brief-fixture-token",
        )
        self.assertEqual(value["schema"], "mastermind.hermes_steward_brief.v1")
        self.assertEqual(value["status"], "PARTIAL")
        self.assertEqual([s["tool"] for s in value["sections"]], [
            "get_responsibility", "get_current_runtime", "explain_blocker",
        ])
        self.assertEqual(value["sections"][1]["state"], "UNKNOWN")
        self.assertEqual(value["sections"][1]["reason_codes"], ["RUNTIME_UNKNOWN"])
        self.assertEqual(value["sections"][2]["reason_codes"], ["NO_SOURCE"])
        self.assertEqual(value["sections"][1]["facts"], [])
        facts = value["sections"][0]["facts"]
        self.assertTrue(facts)
        self.assertTrue(all(f["sources"][0]["owner"] == "agent_os" for f in facts))
        self.assertTrue(all(f["sources"][0]["source_ref"] == "WS:ALPHA" for f in facts))
        self.assertEqual(value["effect"], "NONE")
        self.assertFalse(value["company_completion_proven"])
        self.assertEqual([tool for tool, _ in upstream.calls], [
            "get_responsibility", "get_current_runtime", "explain_blocker",
        ])
        self.assertEqual(len(verifier.seen), 3)
        self.assertNotIn("brief-fixture-token", json.dumps(value))

    def test_all_unknown_never_claims_completion_or_no_blocker(self):
        reader, upstream, _ = _make([
            _unknown("get_responsibility", "NO_SOURCE"),
            _unknown("get_current_runtime", "RUNTIME_UNKNOWN"),
            _unknown("explain_blocker", "NO_SOURCE"),
        ])
        result = responsibility_brief(reader, responsibility_ref=_REF,
                                      authorization="Bearer brief-fixture-token")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(len(result["sections"]), 3)
        self.assertTrue(all(not s["facts"] for s in result["sections"]))
        self.assertFalse(result["company_completion_proven"])
        self.assertEqual(len(upstream.calls), 3)

    def test_revoked_credential_mid_sequence_discards_valid_previous_facts(self):
        times = iter([NOW, NOW + 500])
        reader, upstream, _ = _make([
            _verified(),
            _unknown("get_current_runtime", "RUNTIME_UNKNOWN"),
        ], clock=lambda: next(times))
        result = responsibility_brief(reader, responsibility_ref=_REF,
                                      authorization="Bearer brief-fixture-token")
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["sections"], [])
        self.assertEqual(result["reason"], "READ_NOT_AUTHORIZED_OR_VERIFIED")
        self.assertEqual(len(upstream.calls), 1)
        self.assertNotIn("WS:ALPHA", json.dumps(result))

    def test_bad_upstream_after_first_source_discards_prior_facts(self):
        reader, upstream, _ = _make([
            _verified(),
            {"ok": True, "tool": "get_current_runtime", "data": {
                "state": "FACTS", "subjects": [{"subject_ref": "responsibility:wrong"}],
                "reason_codes": [],
            }},
        ])
        result = responsibility_brief(reader, responsibility_ref=_REF,
                                      authorization="Bearer brief-fixture-token")
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["sections"], [])
        self.assertEqual(len(upstream.calls), 2)

    def test_invalid_or_unbound_read_port_cannot_claim_company_context(self):
        reader, upstream, _ = _make([])
        invalid = responsibility_brief(reader, responsibility_ref="WS:ALPHA",
                                       authorization="Bearer brief-fixture-token")
        self.assertEqual(invalid["status"], "REFUSED")
        self.assertEqual(invalid["reason"], "INVALID_RESPONSIBILITY_REF")
        self.assertEqual(upstream.calls, [])
        wrong = responsibility_brief(object(), responsibility_ref=_REF,
                                     authorization="Bearer brief-fixture-token")
        self.assertEqual(wrong["status"], "REFUSED")
        self.assertEqual(wrong["reason"], "READ_PORT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
