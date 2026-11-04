"""No-provider-call regression tests for exact-model new-request preflight."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from control_plane.fabric_model_readiness import (
    ModelWitness, qualify_model, MAX_AGE
)

NOW = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)


def witness(**overrides):
    return replace(ModelWitness(
        provider="grok", host="ubuntu1", observed_at=NOW,
        complete=True, models=("grok-4.6",), source_verified=True
    ), **overrides)


def decision(model="grok-4.7", proof=None, **kwargs):
    return qualify_model(
        model, witness() if proof is None else proof,
        provider=kwargs.get("provider", "grok"),
        host=kwargs.get("host", "ubuntu1"),
        now=kwargs.get("now", NOW)
    )


class TestModelReadiness(unittest.TestCase):
    def test_unknown_reported_model_fails_before_dispatch(self):
        result = decision()
        self.assertEqual(result.code, "MODEL_PREFLIGHT_MODEL_UNAVAILABLE")
        self.assertFalse(result.eligible)
        self.assertFalse(result.dispatch_authorized)
        self.assertFalse(result.retry_authorized)

    def test_exact_listed_id_is_only_evidence_not_dispatch_permission(self):
        result = decision("grok-4.6")
        self.assertTrue(result.eligible)
        self.assertEqual(result.code, "MODEL_ID_LISTED")
        self.assertFalse(result.dispatch_authorized)
        self.assertFalse(result.retry_authorized)

    def test_no_catalog_claim_is_not_validated(self):
        self.assertEqual(decision(proof="not a witness").code, "MODEL_PREFLIGHT_EVIDENCE_MISSING")
        self.assertEqual(decision(proof=witness(source_verified=False)).code,
                         "MODEL_PREFLIGHT_UNQUALIFIED")
        self.assertEqual(decision(proof=witness(complete=False)).code,
                         "MODEL_PREFLIGHT_UNQUALIFIED")

    def test_wrong_provider_or_host_refused(self):
        self.assertEqual(decision(proof=witness(host="ubuntu2")).code,
                         "MODEL_PREFLIGHT_ORIGIN_MISMATCH")
        self.assertEqual(decision(provider="glm").code,
                         "MODEL_PREFLIGHT_ORIGIN_MISMATCH")

    def test_time_window_does_not_permit_stale_or_future_proof(self):
        self.assertEqual(decision(proof=witness(observed_at=NOW-MAX_AGE)).code,
                         "MODEL_PREFLIGHT_MODEL_UNAVAILABLE")
        self.assertEqual(decision(proof=witness(observed_at=NOW-MAX_AGE-timedelta(microseconds=1))).code,
                         "MODEL_PREFLIGHT_STALE")
        self.assertEqual(decision(proof=witness(observed_at=NOW+timedelta(seconds=1))).code,
                         "MODEL_PREFLIGHT_STALE")
        self.assertEqual(decision(proof=witness(observed_at=NOW.replace(tzinfo=None))).code,
                         "MODEL_PREFLIGHT_CLOCK_INVALID")

    def test_catalog_must_be_bounded_unique_exact_case(self):
        for models in ((), tuple(["grok-4.7"] * 257), ("grok-4.6", "grok-4.6"),
                       ("grok-4.7", ""), ("grok-4.7", "grok 4.6")):
            with self.subTest(models=models[:3]):
                self.assertEqual(decision(proof=witness(models=models)).code,
                                 "MODEL_PREFLIGHT_CATALOG_INVALID")
        self.assertEqual(decision(proof=witness(models=("GROK-4.7",))).code,
                         "MODEL_PREFLIGHT_MODEL_UNAVAILABLE")

    def test_invalid_requested_model_and_scope_never_accepted(self):
        for model in ("", "grok 4.7", "../grok", "grok-4.7\n", "x" * 97):
            self.assertEqual(decision(model).code, "MODEL_PREFLIGHT_REQUEST_INVALID")
        self.assertEqual(decision(host="bad host").code, "MODEL_PREFLIGHT_SCOPE_INVALID")
        self.assertEqual(decision(now=NOW.replace(tzinfo=None)).code,
                         "MODEL_PREFLIGHT_CLOCK_INVALID")


if __name__ == "__main__":
    unittest.main()
