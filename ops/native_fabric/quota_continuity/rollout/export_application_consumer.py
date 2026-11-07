"""Read-only consumer projection of the incumbent completed APPLICATION owner.

This helper issues no grant, credential, capacity claim or installation record.
Its output is finite eligibility evidence for the original install/configuration
publisher. Actual admission and recovery remain the original Broker/gateway.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

_DIRECTORY = Path(__file__).resolve().parent
if str(_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_DIRECTORY))
import native_install as owner

SCHEMA = "mastermind.application_consumer_observation.v1"
_SCOPE_FIELDS = (
    "service_profile", "principal_id", "caller_host", "native_host", "workload",
    "credential_ref", "capability_lane", "workload_profile",
)
_MAX_ROUTES = 256


class _ObservationClock:
    """Only the clock consumed by the incumbent pure grant matcher."""
    def __init__(self, timestamp):
        self.timestamp = timestamp

    def now(self):
        return self.timestamp


def _current_grants(startup, scope, document, observed_at):
    """Reuse the original matcher; never construct a Broker or open its DB."""
    pools = tuple(scope["route_scope"]["pools"]) if "route_scope" in scope else ("go",)
    candidates = sorted({
        (grant["pool"], model, grant.get("recipe_digest"))
        for grant in document["application_grants"]
        if grant["principal_id"] == scope["principal_id"]
        and grant["pool"] in pools
        and scope["caller_host"] in grant["caller_hosts"]
        and scope["workload"] in grant["workloads"]
        for model in grant["models"]
    }, key=lambda row: (row[0], row[1], row[2] or ""))
    if len(candidates) > _MAX_ROUTES:
        raise ValueError("application consumer route projection too large")
    clock = _ObservationClock(observed_at)
    matcher = startup.broker_module.Broker._application_grant_from_document
    rows = []
    for pool, model, recipe in candidates:
        try:
            _, grant, digest = matcher(
                clock, document, scope["principal_id"], scope["caller_host"],
                scope["workload"], pool, model, scope["credential_ref"], recipe)
        except startup.broker_module.ApplicationAdmissionError as error:
            # Expired/disabled routes are absent, never silently requalified.
            # Ambiguity, wrong credentials and invalid recipes refuse the view.
            if str(error) == "grant_unavailable":
                continue
            raise
        rows.append({
            "pool": pool, "model": model, "grant_id": grant["grant_id"],
            "grant_sha256": digest, "expires_at": grant["expires_at"],
            "qualification_ref": grant["qualification_ref"],
            "application_permission_ref": grant["application_permission_ref"],
        })
    if not rows:
        raise ValueError("application consumer has no current grant")
    return rows


def observe_application_consumer(go_ingress_bundle, service_profile):
    """Observe the actual original v9 owner and its current parsed account policy.

    No caller-authored qualification dictionary is accepted. Private binding and
    account paths, credentials and credential-derived private commitments never
    enter the returned projection. A changed original owner invalidates the read.
    """
    with owner._service_source(go_ingress_bundle) as (plan, selected, metadata, entry, startup):
        if (type(service_profile) is not str
                or service_profile not in entry.SERVICE_ROLE_PROFILES):
            raise ValueError("application consumer role unavailable")
        paths = entry.application_enrollment_paths(startup, service_profile)
        completed = entry.load_completed_application_startup(startup, service_profile)
        if len(completed[0]) != 1:
            raise ValueError("application consumer enrollment unavailable")
        snapshots = {
            name: owner._service_snapshot(entry, path, mode=0o600)
            for name, path in paths.items()
        }
        receipt = entry._service_json(snapshots["receipt"][0])
        if receipt["schema"] != entry.SERVICE_ROLE_RECEIPT_SCHEMA:
            raise ValueError("application consumer requires completed role enrollment")
        scope = receipt["scope"]
        if entry.validate_application_role_scope(scope) != service_profile:
            raise ValueError("application consumer role differs")
        if "admin_pool_view" in scope:
            raise ValueError("application consumer metadata permission unavailable")
        accounts = startup.paths["accounts_path"]
        policy_before, policy_identity = owner._service_snapshot(entry, accounts)
        document = startup.broker_module._read_application_accounts(accounts)
        observed_at = time.time()
        rows = _current_grants(startup, scope, document, observed_at)
        qualified_until = min(row["expires_at"] for row in rows)
        result = {
            "schema": SCHEMA,
            "enrollment": {
                "owner": "native_go_service_enrollment",
                "schema": receipt["schema"],
                **{key: receipt[key] for key in (
                    "operation_id", "plan_digest", "source_generation", "ingress_digest")},
            },
            "selected_source": {
                "generation": plan["target_generation"],
                "ingress_sha256": metadata["files"][owner.generation.GO_ENTRY],
                "selection": selected,
            },
            "scope": {key: scope[key] for key in _SCOPE_FIELDS},
            "selection": (
                {"kind": "auto", "route_scope": json.loads(json.dumps(scope["route_scope"]))}
                if "route_scope" in scope else {"kind": "fixed", "pool": "go"}),
            "eligibility": {
                "observed_at": observed_at, "qualified_until": qualified_until,
                "routes": rows,
            },
            "authority": {
                "grant_issued": False, "credential_included": False,
                "capacity_reserved": False, "provider_readiness_proven": False,
                "admission_required": True,
            },
        }
        # These are original-owner read fences, not a new lock or policy store.
        if any(entry.application_file_identity(paths[name]) != identity
               for name, (_, identity) in snapshots.items()):
            raise ValueError("application consumer enrollment changed during observation")
        after, identity = owner._service_snapshot(entry, accounts)
        if after != policy_before or identity != policy_identity:
            raise ValueError("application consumer policy changed during observation")
        if entry.load_completed_application_startup(startup, service_profile) != completed:
            raise ValueError("application consumer enrollment changed during observation")
        if owner._completed_go_for_service(go_ingress_bundle)[1] != selected:
            raise ValueError("application consumer source selection changed")
        if qualified_until <= time.time():
            raise ValueError("application consumer qualification expired")
        raw = owner.generation.canonical(result)
        if len(raw) > 262144:
            raise ValueError("application consumer projection too large")
        # A public digest identifies this observation; it is not a signature,
        # transport authentication, installation authority or admission receipt.
        return {**result, "observation_sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-ingress-bundle", required=True, type=Path)
    parser.add_argument("--service-profile", required=True)
    args = parser.parse_args()
    try:
        result = observe_application_consumer(args.go_ingress_bundle, args.service_profile)
    except Exception:
        print("application consumer observation unavailable", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
