"""No-provider-call regression tests for exact-model new-request preflight."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from control_plane.fabric_model_readiness import (
    ModelWitness, qualify_model, qualify_grok_native_route,
    parse_grok_models_output, MAX_AGE
)

NOW = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)


def witness(**overrides):
    return replace(ModelWitness(
        provider="grok", host="ubuntu1", observed_at=NOW,
        complete=True, models=("grok-4.6",), source_verified=True,
        lease_id="lease-123"
    ), **overrides)


def decision(model="grok-4.7", proof=None, **kwargs):
    return qualify_model(
        model, witness() if proof is None else proof,
        provider=kwargs.get("provider", "grok"),
        host=kwargs.get("host", "ubuntu1"),
        lease_id=kwargs.get("lease_id", "lease-123"),
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

    def test_credential_scoped_lease_identity_is_not_reusable(self):
        # No catalog observed under another broker lease can qualify a new
        # request, even when host, provider, model and timestamp are identical.
        self.assertEqual(decision("grok-4.6", lease_id="lease-456").code,
                         "MODEL_PREFLIGHT_LEASE_MISMATCH")
        self.assertEqual(decision("grok-4.6", proof=witness(lease_id="lease-old")).code,
                         "MODEL_PREFLIGHT_LEASE_MISMATCH")
        self.assertEqual(decision("grok-4.6", lease_id="").code,
                         "MODEL_PREFLIGHT_LEASE_UNBOUND")
        self.assertEqual(decision("grok-4.6", lease_id="../lease").code,
                         "MODEL_PREFLIGHT_LEASE_UNBOUND")
        self.assertEqual(decision("grok-4.6", proof=witness(lease_id="")).code,
                         "MODEL_PREFLIGHT_LEASE_MISMATCH")

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


class TestNativeGrokRoute(unittest.TestCase):
    def test_incident_route_unavailable_without_model_switch(self):
        route = {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.7",
                 "HOST": "ubuntu3", "KEY": "-", "REASON": "judgment_order_grok"}
        snapshot = witness(host="ubuntu3", models=("grok-4.6",))
        found = qualify_grok_native_route(
            route, snapshot, now=NOW, lease_id="lease-123", original_state="NEW_UNATTEMPTED")
        self.assertEqual(found.code, "MODEL_PREFLIGHT_MODEL_UNAVAILABLE")
        self.assertFalse(found.eligible)
        self.assertFalse(found.retry_authorized)
        self.assertFalse(found.dispatch_authorized)

    def test_exact_selected_model_and_host_only_evidence(self):
        route = {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.6",
                 "HOST": "ubuntu3"}
        found = qualify_grok_native_route(
            route, witness(host="ubuntu3"), now=NOW, lease_id="lease-123", original_state="NEW_UNATTEMPTED")
        self.assertEqual(found.code, "MODEL_ID_LISTED")
        self.assertTrue(found.eligible)
        self.assertFalse(found.dispatch_authorized)

    def test_native_route_cannot_reuse_catalog_under_another_lease(self):
        route = {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.6",
                 "HOST": "ubuntu3"}
        found = qualify_grok_native_route(
            route, witness(host="ubuntu3"), now=NOW, lease_id="lease-456",
            original_state="NEW_UNATTEMPTED")
        self.assertEqual(found.code, "MODEL_PREFLIGHT_LEASE_MISMATCH")
        self.assertFalse(found.eligible)
        self.assertFalse(found.dispatch_authorized)
        self.assertFalse(found.retry_authorized)

    def test_terminal_and_effect_unknown_cannot_reuse_eligibility(self):
        route = {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.6",
                 "HOST": "ubuntu3"}
        for prior in ("TERMINAL", "EFFECT_UNKNOWN", "ACTIVE_OR_WAITING", "",
                      "REQUEST_REFUSED_BEFORE_LAUNCH"):
            with self.subTest(prior=prior):
                found = qualify_grok_native_route(
                    route, witness(host="ubuntu3"), now=NOW, lease_id="lease-123", original_state=prior)
                self.assertEqual(found.code, "MODEL_PREFLIGHT_EXISTING_OPERATION")
                self.assertFalse(found.eligible)
                self.assertFalse(found.retry_authorized)

    def test_unverified_route_and_wrong_pool_refuse(self):
        cases = (None, {}, {"POOL": "grok", "MODE": "grok", "HOST": "ubuntu3"},
                 {"POOL": "glm", "MODE": "grok", "MODEL": "grok-4.6", "HOST": "ubuntu3"},
                 {"POOL": "grok", "MODE": "cursor", "MODEL": "grok-4.6", "HOST": "ubuntu3"},
                 {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.6", "HOST": "../host"},
                 {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.6", "HOST": 3})
        for route in cases:
            with self.subTest(route=route):
                found = qualify_grok_native_route(
                    route, witness(host="ubuntu3"), now=NOW, lease_id="lease-123", original_state="NEW_UNATTEMPTED")
                self.assertFalse(found.eligible)
                self.assertFalse(found.dispatch_authorized)


class TestGrokCliCatalogParser(unittest.TestCase):
    """Vendor-documented display fixtures; no provider command or auth calls."""

    @staticmethod
    def sample(banner="You are logged in with grok.com."):
        return (banner
                + "\n\nDefault model: grok-4.7\n\nAvailable models:\n"
                + "  * grok-4.7 (default)\n  - grok-4.6\n").encode("ascii")

    def test_exact_catalog_and_default(self):
        parsed = parse_grok_models_output(self.sample())
        self.assertEqual(parsed.models, ("grok-4.7", "grok-4.6"))
        self.assertEqual(parsed.default_model, "grok-4.7")
        self.assertEqual(parsed.auth_banner, "LOGIN")
        self.assertFalse(hasattr(parsed, "source_verified"))
        # A parsed string is not a trusted host-owner witness.
        route = {"POOL": "grok", "MODE": "grok", "MODEL": "grok-4.7",
                 "HOST": "ubuntu3"}
        untrusted = qualify_grok_native_route(
            route, None, now=NOW, lease_id="lease-123", original_state="NEW_UNATTEMPTED")
        self.assertEqual(untrusted.code, "MODEL_PREFLIGHT_EVIDENCE_MISSING")

    def test_documented_auth_banner_variants(self):
        banners = (
            ("You are using XAI_API_KEY.", "API_KEY"),
            ("You are authenticated via deployment key.", "DEPLOYMENT_KEY"),
            ("Model 'grok-4.7' is using its own API key.", "MODEL_KEY"),
        )
        for banner, auth in banners:
            with self.subTest(auth=auth):
                self.assertEqual(
                    parse_grok_models_output(self.sample(banner)).auth_banner, auth
                )

    def test_unverified_and_broken_auth_fail_closed(self):
        for banner in (
            "You are not authenticated.",
            "Logged in!",
            "You are logged in with grok.com.\x1b[31m",
            "You are logged in with invalid host.",
        ):
            with self.subTest(banner=banner):
                with self.assertRaises(ValueError):
                    parse_grok_models_output(self.sample(banner))

    def test_incomplete_duplicated_and_contradictory_catalogs_refuse(self):
        base = self.sample()
        invalid = (
            base[:-1],
            base.replace(b"  * grok-4.7 (default)", b"  - grok-4.7"),
            base.replace(b"  * grok-4.7 (default)", b"  * grok-4.6 (default)"),
            base + b" - grok-4.6\n",
            base.replace(b"Default model: grok-4.7", b"Default model: grok-5"),
            base.replace(b"Available models:", b"Model list:"),
            base.replace(b"  * grok-4.7 (default)", b" * grok-4.7 (default)"),
            base.replace(b"  - grok-4.6", b" - grok-4.6"),
            base.replace(b" - grok-4.6", b"  - grok-4.6 trailing text"),
            base + b"\n",
        )
        for raw in invalid:
            with self.subTest(kind=raw[-25:]):
                with self.assertRaises(ValueError):
                    parse_grok_models_output(raw)

    def test_output_bounds_controls_and_untrusted_data(self):
        valid = self.sample()
        invalid = (
            b"",
            "not bytes",
            valid + b"a" * 8193,
            valid.replace(b"grok-4.6", b"grok-\xff"),
            valid.replace(b"grok-4.6", b"grok-4.6\x1b[0m"),
            valid.replace(b"grok-4.6", b"../model"),
        )
        for raw in invalid:
            with self.assertRaises(ValueError):
                parse_grok_models_output(raw)


if __name__ == "__main__":
    unittest.main()
