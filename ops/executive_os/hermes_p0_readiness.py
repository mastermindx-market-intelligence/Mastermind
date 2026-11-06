"""Pure, source-only H24-11 reduction of original-owner evidence.

Nothing here reads a path, clock, process, socket, credential or service. Callers
inject retained bytes, independent source expectations, time and their existing
owner's authentication result. This is an evidence checker, never admission or
an installer. In particular a raw C26 INCOMPLETE report is never rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Callable, Mapping

from common.hermes_role_status_contract import validate_gateway_listener


MISSING = "MISSING"
INCOMPLETE = "INCOMPLETE"
REFUSED = "REFUSED"
READY = "READY_FOR_AUTHORIZED_NEXT_STEP"
STATES = (READY, MISSING, INCOMPLETE, REFUSED)
BASE_SHA = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"
UPSTREAM_SHA = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
REPORT_SCHEMA = "mastermind.hermes_role_isolation_qualification.v2"
MANIFEST_SCHEMA = "mastermind.executive_release_manifest/v1"
ROLES = ("mmsecretary", "mmmeta")
RUNS = {"A1": "mmsecretary", "B1": "mmmeta", "A2": "mmsecretary"}
PORTS = {"mmsecretary": ("127.0.0.2", 8765, 8766, 18651),
         "mmmeta": ("127.0.0.3", 8865, 8866, 18652)}
GUARDS = ("assert_root_service_cgroup", "assert_role_network_profile",
          "assert_role_credential_isolation", "enforce_role_tcp_ports")
PROBE_SOURCE_KEYS = frozenset("integrations.hermes_runtime." + name for name in (
    "isolation_probe", "system_service", "role_isolation", "tcp_sandbox", "profile",
    "system_service.assert_root_service_cgroup:loaded_code",
    "system_service.assert_role_network_profile:loaded_code",
    "role_isolation.assert_role_credential_isolation:loaded_code",
    "tcp_sandbox.enforce_role_tcp_ports:loaded_code", "profile.load_profile:loaded_code",
    "isolation_probe._run_probe:loaded_code"))
CASES = frozenset({"profile.fixed_ports", "bind.own_alias.gateway_port",
    "bind.own_alias.backend_port", "bind.own_alias.ephemeral_port",
    "tcp.own_alias.gateway_port", "tcp.own_alias.backend_port",
    "tcp.own_alias.denied_port", "tcp.sibling_alias.gateway_port",
    "tcp.shared_loopback.gateway_port", "exec.own_alias.denied_port",
    "exec.own_alias.gateway_port", "file.own.read", "file.peer.read"})
EXTERNAL = frozenset({"tcp.sibling_alias.gateway_port",
                      "tcp.shared_loopback.gateway_port", "file.peer.read"})
DENIED = EXTERNAL | {"bind.own_alias.ephemeral_port", "tcp.own_alias.denied_port",
                     "exec.own_alias.denied_port"}
MARKER = b"mastermind-hermes-role-isolation-qualification-synthetic-v1\n"
MARKER_SHA256 = hashlib.sha256(MARKER).hexdigest()
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_AGE_SECONDS = 900

# Local input slots, not newly minted canonical receipt schemas or state owners.
OWNERS = {"source": "release-owner", "release": "github-release-owner",
    "c25": "control-installation-owner", "manifest": "release-owner",
    "installation": "control-installation-owner", "incumbents": "control-installation-owner",
    "units": "role-host-owner", "qualification": "role-host-owner",
    "A1": "role-host-owner", "B1": "role-host-owner", "A2": "role-host-owner",
    "cleanup": "role-host-owner", "effects": "original-operation-owner",
    "enrollment": "enrollment-owner", "edge": "edge-owner",
    "serving": "role-host-owner", "useful_turn": "native-session-owner",
    "cutover": "cutover-owner"}
DEPENDENCIES = {
    "source_prepared": (), "source_released": ("source_prepared",),
    "effects_reconciled": (),
    "c25_checkout": ("source_released", "effects_reconciled"),
    "staged_inert": ("c25_checkout",),
    "actual_unit_qualified": ("staged_inert",),
    "enrolled": ("actual_unit_qualified",),
    "serving": ("enrolled",),
    "authenticated_useful_turn": ("serving",),
    "cutover": ("authenticated_useful_turn",),
}
GATE_RECEIPTS = {
    "source_prepared": ("source",), "source_released": ("release",),
    "effects_reconciled": ("effects",), "c25_checkout": ("c25",),
    "staged_inert": ("manifest", "installation", "incumbents", "units"),
    "actual_unit_qualified": ("qualification", "A1", "B1", "A2", "cleanup"),
    "enrolled": ("enrollment",), "serving": ("edge", "serving"),
    "authenticated_useful_turn": ("useful_turn",), "cutover": ("cutover",),
}


@dataclass(frozen=True)
class ExpectedSource:
    """Independent current expectations, never learned from the candidate bundle."""
    implementation_sha: str
    protected_law_sha: str
    original_pr_head: str
    issuer_sha256: str
    upstream_sha: str = UPSTREAM_SHA
    original_pr: int = 2120


@dataclass(frozen=True)
class ReceiptVerification:
    """Result from the incumbent verifier, not flags decoded from receipt JSON.

    NOT_APPLICABLE permits original unsigned, root-custody evidence. It is not
    an invented signature. INVALID always refuses. source_ref must identify the
    exact original retained object (a human description alone is insufficient).
    """
    owner: str
    source_ref: str
    raw_sha256: str
    signature: str
    custody_verified: bool


Verifier = Callable[[str, bytes], ReceiptVerification | None]


class _Invalid(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def _integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= 2**53 - 1


def _dict(value: object) -> dict:
    if type(value) is not dict:
        raise _Invalid("OBJECT_REQUIRED")
    return value


def _list(value: object) -> list:
    if type(value) is not list:
        raise _Invalid("ARRAY_REQUIRED")
    return value


def _decode(raw: bytes, limit: int) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise _Invalid("RECEIPT_SIZE_OR_TYPE")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _Invalid("DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_):
        raise _Invalid("NONFINITE_NUMBER")

    def bounded(value, depth=0):
        if depth > 32:
            raise _Invalid("RECEIPT_DEPTH")
        if type(value) is float and not math.isfinite(value):
            raise _Invalid("NONFINITE_NUMBER")
        if type(value) in {list, dict}:
            if len(value) > 16384:
                raise _Invalid("RECEIPT_COLLECTION_SIZE")
            for child in (value.values() if type(value) is dict else value):
                bounded(child, depth + 1)

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=constant)
        bounded(result)
        return _dict(result)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _Invalid(str(exc) if isinstance(exc, _Invalid) else "INVALID_JSON") from None


def _time(value: object) -> int:
    if type(value) is not str:
        raise _Invalid("INVALID_TIMESTAMP")
    try:
        return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp())
    except ValueError:
        raise _Invalid("INVALID_TIMESTAMP") from None


def _state(issues: list[dict]) -> str:
    return max((i["state"] for i in issues), key=STATES.index, default=READY)


class _Check:
    def __init__(self, receipts, expected, verify, now):
        self.expected, self.now = expected, now
        self.raw, self.docs, self.auth, self.issues = {}, {}, {}, []
        self.gate, self.slot = "input", "bundle"
        if not isinstance(expected, ExpectedSource) or not callable(verify):
            raise _Invalid("TRUST_BOUNDARY_REQUIRED")
        if (not all(_hex(v, 40) for v in (expected.implementation_sha,
                expected.protected_law_sha, expected.original_pr_head, expected.upstream_sha))
                or not _hex(expected.issuer_sha256) or expected.original_pr != 2120
                or type(expected.original_pr) is not int or not _integer(now, 1)):
            raise _Invalid("INVALID_INDEPENDENT_EXPECTATION")
        if (type(receipts) is not dict or set(receipts) - set(OWNERS)
                or any(type(v) is not bytes for v in receipts.values())
                or sum(len(v) for v in receipts.values()) > MAX_BUNDLE_BYTES):
            raise _Invalid("INVALID_BUNDLE")
        # Retain immutable byte references before invoking an injected verifier.
        # A caller changing its input mapping cannot replace already checked data.
        self.raw = dict(receipts)
        for slot, raw in self.raw.items():
            self.slot = slot
            try:
                doc = _decode(raw, MAX_REPORT_BYTES if slot in RUNS else MAX_RECEIPT_BYTES)
                # The injected verifier must use already acquired original-owner
                # evidence; the reducer supplies bytes, never a filesystem path.
                proof = verify(slot, raw)
                if proof is None:
                    self.add(INCOMPLETE, "AUTHENTICATION_RECEIPT_MISSING")
                    continue
                if not isinstance(proof, ReceiptVerification):
                    raise _Invalid("VERIFIER_RESULT_INVALID")
                if (proof.owner != OWNERS[slot] or proof.raw_sha256 != _digest(raw)
                        or proof.signature not in {"VERIFIED", "NOT_APPLICABLE"}
                        or proof.custody_verified is not True
                        or type(proof.source_ref) is not str or not proof.source_ref.strip()):
                    raise _Invalid("SIGNATURE_CUSTODY_OR_ORIGIN_INVALID")
                self.docs[slot], self.auth[slot] = doc, proof
            except _Invalid as exc:
                self.add(REFUSED, str(exc))
            except Exception:
                # Never echo verifier exceptions: they could contain private data.
                self.add(REFUSED, "OWNER_VERIFICATION_FAILED")

    def add(self, state, code, field=""):
        item = {"gate": self.gate, "receipt": self.slot, "state": state,
                "code": code, "field": field}
        if item not in self.issues:
            self.issues.append(item)

    def need(self, condition, code, field="", state=INCOMPLETE):
        if not condition:
            self.add(state, code, field)
        return condition

    def same(self, actual, expected, field):
        return self.need(type(actual) is type(expected) and actual == expected,
                         "IDENTITY_OR_SOURCE_DRIFT", field, REFUSED)

    def receipt(self, slot):
        self.slot = slot
        if slot not in self.raw:
            self.add(MISSING, "RECEIPT_MISSING")
        elif slot not in self.docs:
            self.add(INCOMPLETE, "RECEIPT_NOT_AUTHENTICATED")
        return self.docs.get(slot, {})

    def fresh(self, value, field):
        t = _time(value)
        self.need(0 <= self.now - t <= MAX_AGE_SECONDS, "STALE_OR_FUTURE_RECEIPT", field, REFUSED)
        return t

    def bound(self, doc):
        self.same(doc.get("implementation_sha"), self.expected.implementation_sha, "implementation_sha")

    def role_pin(self, role):
        return _dict(_dict(self.docs.get("source", {}).get("roles", {})).get(role, {}))

    def source_prepared(self):
        d = self.receipt("source")
        if not d:
            return
        self.bound(d)
        self.same(d.get("protected_law_sha"), self.expected.protected_law_sha, "protected_law_sha")
        self.same(d.get("upstream_sha"), self.expected.upstream_sha, "upstream_sha")
        self.same(d.get("issuer_sha256"), self.expected.issuer_sha256, "issuer_sha256")
        for key in ("immutable", "protected_pin_verified", "source_prepared"):
            self.need(d.get(key) is True, "SOURCE_PROOF_MISSING", key)
        self.need(_hex(d.get("tree_sha"), 40), "SOURCE_TREE_MISSING", "tree_sha")
        for field in ("manifest_sha256", "installed_inventory_sha256"):
            self.need(_hex(d.get(field)), "EXPECTED_HASH_MISSING", field)
        sources = _dict(d.get("probe_sources"))
        self.need(set(sources) == PROBE_SOURCE_KEYS and all(_hex(v) for v in sources.values()),
                  "PROBE_SOURCE_PINS_MISSING")
        self.same(set(_dict(d.get("roles"))), set(ROLES), "roles")
        for role in ROLES:
            p = self.role_pin(role)
            for field in ("uid", "gid"):
                self.need(_integer(p.get(field), 1), "ROLE_IDENTITY_MISSING", role + "." + field)
            for field in ("profile_sha256", "fragment_sha256", "exec_start_sha256", "image_sha256"):
                self.need(_hex(p.get(field)), "EXPECTED_HASH_MISSING", role + "." + field)
            self.need(type(p.get("state_dir")) is str and p["state_dir"].startswith("/")
                      and ".." not in p["state_dir"].split("/"), "ROLE_PATH_MISSING", role)
        for field in ("uid", "gid", "state_dir"):
            self.need(self.role_pin(ROLES[0]).get(field) != self.role_pin(ROLES[1]).get(field),
                      "SHARED_ROLE_IDENTITY", field, REFUSED)

    def source_released(self):
        d = self.receipt("release")
        if not d:
            return
        pr = _dict(d.get("pr"))
        self.same(pr.get("number"), self.expected.original_pr, "pr.number")
        self.same(pr.get("head_sha"), self.expected.original_pr_head, "pr.head_sha")
        self.need(pr.get("merged") is True and pr.get("state") == "closed",
                  "ORIGINAL_PR_NOT_RELEASED", "pr")
        self.need(_hex(pr.get("merge_commit_sha"), 40), "MERGE_RECEIPT_MISSING")
        self.same(d.get("selected_commit"), self.expected.implementation_sha, "selected_commit")
        self.need(d.get("protected_release_accepted") is True, "PROTECTED_RELEASE_NOT_ACCEPTED")
        if pr.get("merge_commit_sha") != self.expected.implementation_sha:
            self.need(d.get("frozen_ancestor_accepted") is True,
                      "EXACT_RELEASE_ANCESTRY_NOT_ACCEPTED")

    def effects_reconciled(self):
        d = self.receipt("effects")
        if not d:
            return
        for name in ("origin", "workers", "c25", "c26"):
            row = _dict(d.get(name))
            self.need(type(row.get("operation_id")) is str and bool(row["operation_id"]),
                      "ORIGINAL_OPERATION_ID_MISSING", name)
            self.need(row.get("state") in {"NO_EFFECT", "RECONCILED", "TERMINAL"},
                      "ORIGINAL_EFFECT_UNRESOLVED", name, REFUSED)
            self.need(row.get("denied") is False and row.get("active_writer") is False,
                      "DENIED_OR_LIVE_WRITER", name, REFUSED)
        self.need(d.get("new_authority_granted") is False, "READINESS_IS_NOT_AUTHORITY", state=REFUSED)

    def c25_checkout(self):
        d = self.receipt("c25")
        if not d:
            return
        self.bound(d)
        e = self.docs.get("effects", {}).get("c25", {})
        self.same(d.get("operation_id"), e.get("operation_id"), "operation_id")
        self.need(d.get("original_effect") in {"NO_EFFECT", "RECONCILED", "TERMINAL"},
                  "C25_ORIGINAL_EFFECT_UNKNOWN", state=REFUSED)
        self.need(d.get("diagnostic") == "UNRELATED_REF_BAD_TREE"
                  and d.get("repair_accepted") is True, "C25_DIAGNOSTIC_OR_REPAIR_MISSING")
        stage = _dict(d.get("stage", {}))
        self.need(stage.get("staged_admin_checkout") is True, "C25_CHECKOUT_MISSING")
        if stage:
            self.same(stage.get("commit_sha"), self.expected.implementation_sha, "stage.commit_sha")
            for key in ("selection_changed", "services_changed", "configs_changed",
                        "receipt_changed", "transaction_changed"):
                self.same(stage.get(key), False, "stage." + key)
        norm = _dict(d.get("normalization", {}))
        self.need(norm.get("schema") == "mastermind.executive_admin_checkout_normalization.v1",
                  "C25_NORMALIZATION_MISSING")
        if norm:
            self.same(norm.get("commit"), self.expected.implementation_sha, "normalization.commit")
            self.need(_integer(norm.get("reachable_object_count"), 1)
                      and _integer(norm.get("normalized_promisor_markers")), "C25_CLOSURE_UNPROVEN")

    def staged_inert(self):
        manifest, install = self.receipt("manifest"), self.receipt("installation")
        source = self.docs.get("source", {})
        if manifest:
            self.slot = "manifest"
            self.same(manifest.get("schema_version"), MANIFEST_SCHEMA, "schema_version")
            self.same(manifest.get("commit_sha"), self.expected.implementation_sha, "commit_sha")
            self.same(manifest.get("tree_sha"), source.get("tree_sha"), "tree_sha")
            self.same(_digest(self.raw["manifest"]), source.get("manifest_sha256"), "manifest_sha256")
            self.need(bool(_list(manifest.get("entries"))), "SEALED_MANIFEST_ENTRIES_MISSING")
            runtime = _dict(manifest.get("hermes_runtime", {}))
            self.need(runtime.get("schema") == "mastermind.hermes_runtime_installation/v1",
                      "FROZEN_ROLE_INSTALLATION_MISSING")
            if runtime:
                rows = _list(runtime.get("roles"))
                self.same([r.get("role") for r in rows], ["mmmeta", "mmsecretary"], "hermes_runtime.roles")
                for row in rows:
                    p = self.role_pin(row.get("role"))
                    for key in ("uid", "gid", "state_dir"):
                        self.same(row.get(key), p.get(key), "hermes_runtime." + key)
        if install:
            self.slot = "installation"
            self.bound(install)
            for name, expected in (("manifest", source.get("manifest_sha256")),
                                   ("inventory", source.get("installed_inventory_sha256"))):
                pair = _dict(install.get(name))
                self.same(pair.get("expected_sha256"), expected, name + ".expected_sha256")
                self.same(pair.get("observed_sha256"), expected, name + ".observed_sha256")
            self.need(install.get("sealed") is True and install.get("staged_inert") is True,
                      "INERT_INSTALLATION_NOT_PROVEN")
        incumbents = self.receipt("incumbents")
        if incumbents:
            self.fresh(incumbents.get("observed_at_utc"), "observed_at_utc")
            for role in ("Control", "Worker"):
                pair = _dict(incumbents.get(role))
                before, after = _dict(pair.get("before")), _dict(pair.get("after"))
                self.same(after, before, role + ".identity")
                for field in ("pid", "start_ticks"):
                    self.need(_integer(before.get(field), 1), "INCUMBENT_IDENTITY_MISSING", role + "." + field)
                self.need(_hex(before.get("implementation_sha"), 40)
                          and _hex(before.get("config_sha256"))
                          and bool(before.get("boot_id")) and bool(before.get("invocation_id"))
                          and before.get("running") is True,
                          "INCUMBENT_IDENTITY_MISSING", role)
        units = self.receipt("units")
        if units:
            self.bound(units)
            self.fresh(units.get("observed_at_utc"), "observed_at_utc")
            self.same(set(_dict(units.get("roles"))), set(ROLES), "roles")
            for role, row in units["roles"].items():
                self.unit(row, role, inert=True)

    def unit(self, row, role, *, inert):
        row, p = _dict(row), self.role_pin(role)
        unit = "hermes-runtime-" + role + ".service"
        for key, expected in (("unit", unit), ("User", role), ("Group", role),
                ("FragmentPath", "/etc/systemd/system/" + unit), ("LoadState", "loaded"),
                ("NeedDaemonReload", "no"), ("Transient", "no"), ("DropInPaths", [])):
            self.same(row.get(key), expected, key)
        for key in ("fragment_sha256", "exec_start_sha256"):
            self.same(row.get(key), p.get(key), key)
        self.need(row.get("root_custody_verified") is True, "ROOT_FRAGMENT_CUSTODY_MISSING")
        if inert:
            self.same(row.get("UnitFileState"), "disabled", "UnitFileState")
            self.need(row.get("MainPID") == 0 and type(row.get("MainPID")) is int
                      and row.get("ControlPID") == 0 and type(row.get("ControlPID")) is int
                      and row.get("job_pending") is False
                      and row.get("ActiveState") in {"inactive", "failed"},
                      "UNEXPECTED_LIVE_ROLE", role, REFUSED)

    def actual_unit_qualified(self):
        q = self.receipt("qualification")
        reports = {run: self.receipt(run) for run in RUNS}
        cleanup = self.receipt("cleanup")
        if not q:
            return
        self.slot = "qualification"
        self.bound(q)
        self.fresh(q.get("observed_at_utc"), "observed_at_utc")
        effects = self.docs.get("effects", {}).get("c26", {})
        self.same(q.get("operation_id"), effects.get("operation_id"), "operation_id")
        self.same(q.get("sources"), self.docs.get("source", {}).get("probe_sources"), "sources")
        self.need(type(q.get("qualification_id")) is str and re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", q["qualification_id"]) is not None, "QUALIFICATION_ID_MISSING")
        host = _dict(q.get("host"))
        self.need(_hex(host.get("machine_id"), 32) and type(host.get("boot_id")) is str
                  and re.fullmatch(r"[0-9a-f-]{36}", host["boot_id"]) is not None,
                  "HOST_BOOT_IDENTITY_MISSING")
        units = self.docs.get("units", {})
        self.same(host.get("boot_id"), units.get("boot_id"), "boot_id")
        self.same(host.get("machine_id"), units.get("machine_id"), "machine_id")
        run_facts = _dict(q.get("runs"))
        self.same(set(run_facts), set(RUNS), "runs")
        previous_finish, invocation_ids = None, set()
        for run, role in RUNS.items():
            if run not in run_facts or not reports[run]:
                continue
            self.slot = run
            facts = _dict(run_facts[run])
            self.same(facts.get("role"), role, "role")
            self.same(facts.get("report_sha256"), _digest(self.raw[run]), "report_sha256")
            self.same(facts.get("unit_fragment_sha256"), self.role_pin(role).get("fragment_sha256"), "unit_fragment_sha256")
            self.need(_hex(facts.get("invocation_id"), 32)
                      and facts["invocation_id"] not in invocation_ids, "INVOCATION_ID_REUSED_OR_MISSING", state=REFUSED)
            invocation_ids.add(facts.get("invocation_id"))
            self.need(_integer(facts.get("pid"), 1) and _integer(facts.get("start_ticks"), 1),
                      "ACTUAL_ROLE_PROCESS_MISSING")
            # The v2 probe itself carries no PID1 invocation ID. Join the
            # authenticated original operator's start/terminal observations,
            # rather than assuming a plausible invocation string is sufficient.
            for key in ("unit_start", "unit_terminal"):
                observed = _dict(facts.get(key, {}))
                if not self.need(bool(observed), "ACTUAL_UNIT_INVOCATION_RECEIPT_MISSING", key):
                    continue
                for field, value in (("unit", "hermes-runtime-" + role + ".service"),
                        ("boot_id", host.get("boot_id")), ("InvocationID", facts.get("invocation_id")),
                        ("ExecMainPID", facts.get("pid")), ("start_ticks", facts.get("start_ticks")),
                        ("fragment_sha256", self.role_pin(role).get("fragment_sha256")),
                        ("uid", self.role_pin(role).get("uid")), ("gid", self.role_pin(role).get("gid"))):
                    self.same(observed.get(field), value, key + "." + field)
                self.same(observed.get("MainPID"), facts.get("pid") if key == "unit_start" else 0, key + ".MainPID")
                if key == "unit_terminal":
                    self.same(observed.get("ExecMainStatus"), 78, key + ".ExecMainStatus")
            started, finished = _time(facts.get("started_at_utc")), _time(facts.get("finished_at_utc"))
            self.need(started <= finished <= self.now and self.now - started <= MAX_AGE_SECONDS
                      and (previous_finish is None or previous_finish < started),
                      "STALE_OR_OVERLAPPING_ABA_SEQUENCE", state=REFUSED)
            previous_finish = finished
            self.report(reports[run], facts, q, run, role, started, finished)
        self.slot = "qualification"
        self.need(q.get("external_acceptance") == "ACCEPTED_FOR_QUALIFICATION_ONLY",
                  "ORIGINAL_HOST_QUALIFICATION_ACCEPTANCE_MISSING")
        if cleanup:
            self.slot = "cleanup"
            self.same(cleanup.get("operation_id"), q.get("operation_id"), "operation_id")
            self.same(cleanup.get("boot_id"), host.get("boot_id"), "boot_id")
            hashes = _dict(cleanup.get("report_sha256"))
            self.same(set(hashes), set(RUNS), "report_sha256.keys")
            for k in RUNS:
                if k in self.raw:
                    self.same(hashes.get(k), _digest(self.raw[k]), "report_sha256." + k)
            for field in ("terminal_processes", "no_residual_children", "external_sockets_closed",
                          "exact_overrides_removed", "original_properties_restored", "credentials_untouched"):
                self.need(cleanup.get(field) is True, "CLEANUP_PROOF_MISSING", field)
            self.same(cleanup.get("serving_started"), False, "serving_started")

    def report(self, r, facts, q, run, role, started, finished):
        self.same(r.get("schema"), REPORT_SCHEMA, "schema")
        self.same(r.get("role"), role, "role")
        peer = next(x for x in ROLES if x != role)
        self.same(r.get("peer_role"), peer, "peer_role")
        self.same(r.get("qualification_id"), q.get("qualification_id"), "qualification_id")
        generated = _time(r.get("generated_at_utc"))
        self.need(started <= generated <= finished, "REPORT_OUTSIDE_INVOCATION", state=REFUSED)
        context = _dict(r.get("context"))
        selected = _list(r.get("selected_matrix"))
        self.need(len(selected) == len(CASES) and set(selected) == CASES
                  and r.get("full_matrix_selected") is True, "THIRTEEN_CASE_MATRIX_INCOMPLETE")
        self.same(r.get("context_fingerprint"), _digest(_canonical({"context": context, "selected": sorted(selected)})), "context_fingerprint")
        p = self.role_pin(role)
        provenance = _dict(context.get("provenance"))
        for key, expected in (("qualification_id", q.get("qualification_id")),
                ("host", q.get("host")), ("sources", q.get("sources")), ("profile_sha256", p.get("profile_sha256"))):
            self.same(provenance.get(key), expected, "provenance." + key)
        alias, gateway, backend, proxy = PORTS[role]
        cgroup = "/system.slice/hermes-runtime-" + role + ".service"
        for key, value in (("role", role), ("peer_role", peer), ("service_name", "hermes-runtime-" + role),
                ("expected_cgroup", cgroup), ("gateway_host", alias), ("gateway_port", gateway),
                ("backend_port", backend), ("proxy_host", alias), ("proxy_port", proxy),
                ("state_dir", p.get("state_dir")), ("landlock_bind_ports", sorted([gateway, backend])),
                ("landlock_connect_ports", sorted([gateway, backend, proxy]))):
            self.same(context.get(key), value, "context." + key)
        identity = _dict(context.get("identity"))
        for key, value in (("role", role), ("nss_user", role), ("nss_uid", p.get("uid")),
                ("nss_primary_gid", p.get("gid")), ("nss_gid", p.get("gid")),
                ("process_uid", p.get("uid")), ("process_euid", p.get("uid")),
                ("process_gid", p.get("gid")), ("process_egid", p.get("gid")),
                ("uid_is_nss_uid", True), ("gid_is_nss_gid", True),
                ("no_extra_supplementary_groups", True), ("effective_cgroup_expected", cgroup)):
            self.same(identity.get(key), value, "identity." + key)
        observed_cgroup = identity.get("effective_cgroup_observed")
        self.need(type(observed_cgroup) is str and (observed_cgroup == cgroup or observed_cgroup.startswith(cgroup + "/")),
                  "NOT_ACTUAL_ROLE_CGROUP", state=REFUSED)
        groups = _list(identity.get("process_groups"))
        self.need(all(type(g) is int and g == p.get("gid") for g in groups), "EXTRA_ROLE_GROUP", state=REFUSED)
        guards = _list(r.get("guards"))
        self.need([g.get("name") for g in guards] == list(GUARDS)
                  and all(g.get("status") == "PASS" and g.get("code") is None for g in guards), "PRODUCTION_GUARDS_INCOMPLETE")
        recheck = _dict(r.get("observational_recheck"))
        self.need(r.get("context_rechecked") is True and r.get("cleanup_complete") is True
                  and all(recheck.get(k) is True for k in ("identity_matched", "guards_matched", "provenance_matched")),
                  "CONTEXT_OR_CLEANUP_INCOMPLETE")
        self.same(recheck.get("observed_identity"), identity, "observational_recheck.identity")
        self.same(recheck.get("guards"), guards[:3], "observational_recheck.guards")
        self.need(_dict(r.get("witnesses")).get("cleanup_complete") is True, "CHILD_CLEANUP_INCOMPLETE")
        matrix = _list(r.get("matrix"))
        self.need(len(matrix) == 13 and {m.get("case_id") for m in matrix} == CASES,
                  "MISSING_OR_DUPLICATE_CASE", state=REFUSED)
        counts = {"pass": 0, "fail": 0, "unavailable": 0, "not_run": 0}
        for row in matrix:
            status = row.get("status")
            self.need(status in {"PASS", "FAIL", "UNAVAILABLE", "NOT_RUN"}, "INVALID_CASE_STATUS", state=REFUSED)
            counts[status.lower() if status in {"PASS", "FAIL", "UNAVAILABLE"} else "not_run"] += 1
            self.case(row, facts, q, run, role, context)
        self.same(r.get("counts"), counts, "counts")
        expected_status = "FAIL" if counts["fail"] else ("INCOMPLETE" if counts["unavailable"] or counts["not_run"] else "PASS")
        self.same(r.get("status"), expected_status, "status")
        self.same(r.get("qualified"), expected_status == "PASS", "qualified")
        self.need(expected_status != "FAIL", "OBSERVED_ISOLATION_FAILURE", state=REFUSED)
        own_rows = [row for row in matrix if row.get("case_id") == "file.own.read"]
        if len(own_rows) == 1:
            own_witness = _dict(own_rows[0].get("witness"))
            self.same(r.get("own_file"), {"path": own_witness.get("path"),
                "sha256": own_witness.get("sha256"), "facts": own_witness.get("facts"),
                "status": own_rows[0].get("status")}, "own_file")

    def listener(self, w, host, port, field):
        w = _dict(w)
        self.need(w.get("sufficient") is True and all(_integer(w.get(k), 1) for k in
            ("pid", "start_ticks", "socket_inode")) and _integer(w.get("socket_fd")),
            "SAME_SOCKET_FD_INODE_WITNESS_MISSING", field)
        self.same(w.get("host"), host, field + ".host")
        self.same(w.get("port"), port, field + ".port")

    def case(self, row, facts, q, run, role, context):
        case = row.get("case_id")
        if case not in CASES:
            return
        self.need(row.get("selected") is True, "CASE_NOT_SELECTED", case)
        expected = "REFUSED" if case in DENIED else "ALLOWED"
        self.same(row.get("expected"), expected, case + ".expected")
        if row.get("status") == "FAIL" or (case in DENIED and row.get("observed") == "ALLOWED"):
            self.add(REFUSED, "OBSERVED_ISOLATION_FAILURE", case)
            return
        if case in EXTERNAL:
            self.need(row.get("status") == "UNAVAILABLE" and _dict(row.get("witness")).get("sufficient") is False,
                      "RAW_EXTERNAL_CASE_RELABELLED", case, REFUSED)
            if run == "A1" and case == "file.peer.read":
                # Bootstrap provides only earlier own-file evidence. Final Secretary
                # peer denial belongs to A2, never inherited from Meta's B1.
                self.need(row.get("observed") == "UNAVAILABLE", "A1_BOOTSTRAP_PEER_EVIDENCE_INVALID", case)
                return
            self.need(row.get("observed") == "REFUSED", "EXTERNAL_NEGATIVE_NOT_OBSERVED", case)
            self.external(row, facts, q, run, role)
            return
        if not self.need(row.get("status") == "PASS" and row.get("observed") == expected,
                         "LOCAL_CASE_INCOMPLETE", case):
            return
        w = _dict(row.get("witness"))
        self.need(w.get("sufficient") is True, "LOCAL_WITNESS_INCOMPLETE", case)
        alias, gateway, backend, _ = PORTS[role]
        port = backend if "backend" in case else gateway
        if "denied_port" in case:
            port = context.get("denied_port")
            self.need(_integer(port, 1024) and port <= 65535 and port not in
                      {p for v in PORTS.values() for p in v[1:]}, "INVALID_DENIED_PORT", case, REFUSED)
        if case.startswith(("tcp.", "exec.")):
            self.same(row.get("target"), {"host": alias, "port": port}, case + ".target")
            before, after = _dict(w.get("before", {})), _dict(w.get("after", {}))
            self.listener(before, alias, port, case + ".before")
            self.listener(after, alias, port, case + ".after")
            self.same(after, before, case + ".listener_identity")
            if case in DENIED:
                self.need(type(row.get("errno")) is int and row["errno"] in {1, 13}
                          and row.get("symptom") == "refused_immediately", "PORT_DENIAL_NOT_PROVEN", case)
                positive = w.get("pre_landlock_reached") is True if case.startswith("tcp.") else w.get("pre_landlock_exec") == ["connected", None]
                self.need(positive, "SAME_TARGET_POSITIVE_MISSING", case)
        elif case.startswith("bind.") and "ephemeral" not in case:
            self.listener(w, alias, port, case)
        elif case == "bind.own_alias.ephemeral_port":
            self.need(type(row.get("errno")) is int and row["errno"] in {1, 13}
                      and row.get("symptom") == "refused_immediately"
                      and _dict(w.get("baseline", {})).get("bound") is True,
                      "EPHEMERAL_BIND_DENIAL_NOT_PROVEN", case)
        elif case == "file.own.read":
            self.fixture(w, role, case)

    def fixture(self, value, role, field):
        value, pin = _dict(value), self.role_pin(role)
        self.same(value.get("path"), str(pin.get("state_dir")) + "/qualification/synthetic.txt", field + ".path")
        self.same(value.get("sha256"), MARKER_SHA256, field + ".sha256")
        facts = _dict(value.get("facts", {}))
        for key, expected in (("uid", pin.get("uid")), ("gid", pin.get("gid")),
                              ("mode", "0o600"), ("nlink", 1), ("size", len(MARKER))):
            self.same(facts.get(key), expected, field + "." + key)
        self.need(_integer(facts.get("device")) and _integer(facts.get("inode"), 1)
                  and _integer(facts.get("mtime_ns")) and _integer(facts.get("ctime_ns")),
                  "FIXTURE_IDENTITY_MISSING", field)

    def external(self, row, facts, q, run, role):
        case = row["case_id"]
        ext = _dict(facts.get("external", {})).get(case)
        if not self.need(type(ext) is dict, "EXTERNAL_BRACKET_MISSING", case):
            return
        self.same(ext.get("report_sha256"), facts.get("report_sha256"), case + ".report_sha256")
        self.same(ext.get("invocation_id"), facts.get("invocation_id"), case + ".invocation_id")
        self.same(ext.get("boot_id"), q["host"]["boot_id"], case + ".boot_id")
        start, finish = _time(facts["started_at_utc"]), _time(facts["finished_at_utc"])
        before_t, attempt, after_t = (_time(ext.get(k)) for k in ("before_at_utc", "attempt_at_utc", "after_at_utc"))
        self.need(before_t <= start <= attempt <= finish <= after_t <= self.now
                  and after_t - before_t <= MAX_AGE_SECONDS, "EXTERNAL_BRACKET_TIME_MISMATCH", case, REFUSED)
        before, after = _dict(ext.get("before")), _dict(ext.get("after"))
        self.same(after, before, case + ".bracket_identity")
        peer = next(x for x in ROLES if x != role)
        if case == "file.peer.read":
            self.need(type(row.get("errno")) is int and row["errno"] in {1, 13}, "PEER_DENIAL_NOT_PROVEN", case)
            self.same(row.get("target"), {"path": self.role_pin(peer).get("state_dir", "") + "/qualification/synthetic.txt"}, case + ".target")
            self.same(set(before), set(ROLES), case + ".both_fixtures")
            for r in ROLES:
                self.fixture(before.get(r, {}), r, case + "." + r)
            predecessor = {"B1": "A1", "A2": "B1"}[run]
            if not self.need(predecessor in self.raw, "EARLIER_PEER_REPORT_MISSING", case):
                return
            peer_digest = _digest(self.raw[predecessor])
            self.same(ext.get("peer_report_sha256_before"), peer_digest, case + ".peer_report_before")
            self.same(ext.get("peer_report_sha256_after"), peer_digest, case + ".peer_report_after")
            self.same(_dict(row.get("witness")).get("peer_report_sha256"), peer_digest, case + ".peer_report_sha256")
            witness = _dict(row.get("witness"))
            for field, value in (("peer_role", peer), ("peer_file_path", before[peer].get("path")),
                    ("peer_file_sha256", before[peer].get("sha256")), ("peer_file_facts", before[peer].get("facts"))):
                self.same(witness.get(field), value, case + "." + field)
            peer_report = self.docs.get(predecessor, {})
            self.same(peer_report.get("own_file"), {**before[peer], "status": "PASS"}, case + ".earlier_own_file")
            self.need(witness.get("artifact_qualified") is True,
                      "PEER_REPORT_CUSTODY_MISSING", case)
        else:
            host = PORTS[peer][0] if "sibling" in case else "127.0.0.1"
            port = PORTS[role][1]
            self.same(row.get("target"), {"host": host, "port": port}, case + ".target")
            self.listener(before, host, port, case + ".external_listener")
            self.need(before.get("outside_role_cgroup") is True and before.get("connected") is True,
                      "OUTSIDE_CGROUP_POSITIVE_MISSING", case)
            cgroup = before.get("cgroup")
            self.need(before.get("uid") == 0 and type(before.get("uid")) is int
                      and type(cgroup) is str and cgroup.startswith("/")
                      and all(cgroup != "/system.slice/hermes-runtime-" + r + ".service"
                              and not cgroup.startswith("/system.slice/hermes-runtime-" + r + ".service/")
                              for r in ROLES), "OUTSIDE_CGROUP_OWNER_UNQUALIFIED", case)
            code, symptom = row.get("errno"), row.get("symptom")
            self.need(type(code) is int and ((code == 1 and symptom == "refused_immediately")
                or (code in {11, 110} and symptom == "timed_out")), "ADDRESS_DENIAL_NOT_PROVEN", case)

    def enrolled(self):
        d = self.receipt("enrollment")
        if not d:
            return
        self.bound(d)
        self.same(d.get("upstream_sha"), self.expected.upstream_sha, "upstream_sha")
        self.same(d.get("issuer_sha256"), self.expected.issuer_sha256, "issuer_sha256")
        for name in ("C29", "C30", "C31"):
            receipt = _dict(d.get(name, {}))
            self.need(receipt.get("accepted") is True, name + "_NOT_ACCEPTED")
            self.same(receipt.get("implementation_sha"), self.expected.implementation_sha, name + ".implementation_sha")
        self.need(d.get("principal_enrolled") is True and bool(d.get("principal_id"))
                  and d.get("issuer_entitlement") == "ACCEPTED", "ENROLLED_PRINCIPAL_OR_ENTITLEMENT_MISSING")
        self.same(set(_dict(d.get("roles"))), set(ROLES), "roles")
        for role, row in d["roles"].items():
            p = self.role_pin(role)
            self.same(row.get("uid"), p.get("uid"), role + ".uid")
            for field in ("credential_enrollment", "provider_entitlement", "source_entitlement"):
                self.need(row.get(field) == "ACCEPTED", "ROLE_ENTITLEMENT_MISSING", role + "." + field)
            self.need(_hex(row.get("credential_metadata_sha256")) and _hex(row.get("provider_binding_sha256")),
                      "ROLE_ENROLLMENT_IDENTITY_MISSING", role)
        self.same(d.get("credential_contents_included"), False, "credential_contents_included")

    def serving(self):
        edge, d = self.receipt("edge"), self.receipt("serving")
        if edge:
            self.slot = "edge"
            self.bound(edge)
            self.fresh(edge.get("observed_at_utc"), "observed_at_utc")
            for field in ("C34_accepted", "incumbent_proxy_identity_verified", "tls_verified",
                          "vendor_connect_acl_verified", "cross_role_denial_verified"):
                self.need(edge.get(field) is True, "EDGE_PROOF_MISSING", field)
            self.need(_hex(edge.get("edge_metadata_sha256")), "EDGE_METADATA_MISSING")
        if not d:
            return
        self.slot = "serving"
        self.bound(d)
        self.fresh(d.get("observed_at_utc"), "observed_at_utc")
        self.need(d.get("authorized_release") is True, "SERVING_RELEASE_NOT_AUTHORIZED", state=REFUSED)
        self.same(d.get("issuer_sha256"), self.expected.issuer_sha256, "issuer_sha256")
        if "enrollment" in self.raw:
            self.same(d.get("enrollment_receipt_sha256"), _digest(self.raw["enrollment"]), "enrollment_receipt_sha256")
        self.same(d.get("edge_metadata_sha256"), edge.get("edge_metadata_sha256"), "edge_metadata_sha256")
        self.same(d.get("boot_id"), self.docs.get("qualification", {}).get("host", {}).get("boot_id"), "boot_id")
        self.same(set(_dict(d.get("roles"))), set(ROLES), "roles")
        for role, pair in d["roles"].items():
            before, after = _dict(pair.get("before")), _dict(pair.get("after"))
            self.same(after, before, role + ".process_identity")
            self.unit(before, role, inert=False)
            pin = self.role_pin(role)
            self.need(before.get("ActiveState") == "active" and before.get("SubState") == "running"
                      and _integer(before.get("MainPID"), 1) and _integer(before.get("start_ticks"), 1)
                      and _hex(before.get("invocation_id"), 32), "ACTUAL_ROLE_NOT_SERVING", role)
            for key, value in (("uid", pin.get("uid")), ("gid", pin.get("gid")),
                    ("image_sha256", pin.get("image_sha256")), ("manifest_sha256", self.docs.get("source", {}).get("manifest_sha256")),
                    ("boot_id", d.get("boot_id"))):
                self.same(before.get(key), value, role + "." + key)
            # Only Secretary publishes the incumbent v3 main-only socket
            # witness. Do not invent a Meta v3 witness or reuse a C26 fixture
            # listener as a production observation.
            if role == "mmsecretary":
                listener = validate_gateway_listener(before.get("gateway_listener"))
                self.same(listener["port"], PORTS[role][1], "gateway_listener.port")
                self.same(before.get("gateway_kernel_listeners"), [{"host": listener["host"],
                    "port": listener["port"], "inode": int(listener["inode"])}], "gateway_kernel_listeners")
                self.need(before.get("main_only_status_verified") is True,
                          "MAIN_ONLY_SOCKET_CUSTODY_MISSING", role)

    def authenticated_useful_turn(self):
        d = self.receipt("useful_turn")
        if not d:
            return
        self.bound(d)
        self.same(d.get("principal_id"), self.docs.get("enrollment", {}).get("principal_id"), "principal_id")
        self.same(d.get("issuer_sha256"), self.expected.issuer_sha256, "issuer_sha256")
        if "serving" in self.raw:
            self.same(d.get("serving_receipt_sha256"), _digest(self.raw["serving"]), "serving_receipt_sha256")
        role = d.get("role")
        if self.need(role in ROLES, "USEFUL_TURN_ROLE_MISSING"):
            observed = self.docs.get("serving", {}).get("roles", {}).get(role, {}).get("after", {})
            self.same(d.get("invocation_id"), observed.get("invocation_id"), "invocation_id")
        self.need(type(d.get("session_id")) is str and bool(d["session_id"]), "NATIVE_SESSION_ID_MISSING")
        self.need(d.get("authenticated") is True and d.get("original_operation_consumed") is True
                  and d.get("useful_result_accepted") is True and d.get("browser_path_accepted") is True,
                  "AUTHENTICATED_USEFUL_TURN_NOT_PROVEN")
        self.need(bool(d.get("operation_id")) and _hex(d.get("result_sha256")), "ORIGINAL_USEFUL_TURN_IDENTITY_MISSING")

    def cutover(self):
        d = self.receipt("cutover")
        if not d:
            return
        self.bound(d)
        self.need(d.get("explicit_authorization") is True and d.get("accepted") is True
                  and d.get("rollback_proven") is True, "CUTOVER_NOT_ACCEPTED")
        self.need(d.get("completed") is True and d.get("incumbent_transition_verified") is True
                  and type(d.get("operation_id")) is str and bool(d["operation_id"]),
                  "CUTOVER_EFFECT_NOT_PROVEN")
        self.same(d.get("useful_turn_operation_id"), self.docs.get("useful_turn", {}).get("operation_id"), "useful_turn_operation_id")
        if "useful_turn" in self.raw:
            self.same(d.get("useful_turn_sha256"), _digest(self.raw["useful_turn"]), "useful_turn_sha256")

    def run(self, target):
        if type(target) is not str or target not in DEPENDENCIES:
            raise _Invalid("UNKNOWN_TARGET")
        gates = {}
        for name, dependencies in DEPENDENCIES.items():
            self.gate = name
            offset = len(self.issues)
            try:
                getattr(self, name)()
            except (_Invalid, KeyError, TypeError, AttributeError, ValueError):
                self.add(REFUSED, "RECEIPT_STRUCTURE_INVALID")
            local = self.issues[offset:]
            inherited = [i for dep in dependencies for i in gates[dep]["blockers"]]
            inputs = [i for i in self.issues if i["gate"] == "input" and i["receipt"] in GATE_RECEIPTS[name]]
            blockers = list({(i["gate"], i["receipt"], i["code"], i["field"]): i
                             for i in inherited + inputs + local}.values())
            gates[name] = {"state": _state(blockers), "evidence_satisfied": not blockers,
                           "depends_on": list(dependencies), "blockers": blockers}
        blockers = gates[target]["blockers"]
        next_read = None
        for name, node in gates.items():
            if node["blockers"]:
                first = node["blockers"][0]
                slot = first["receipt"]
                next_read = {"receipt": slot, "owner": OWNERS.get(slot, "original-operation-owner"),
                             "action": "READ_ORIGINAL_RETAINED_RECEIPT",
                             "reason": first["code"]}
                break
        return {"schema": "mastermind.hermes_p0_readiness.v1", "state": _state(blockers),
                "target": target, "source_only": True, "authorization_granted": False,
                "permission_boundary": "ORIGINAL_OWNERS_RETAIN_INSTALL_ENROLLMENT_SERVING_AND_CUTOVER_AUTHORITY",
                "gates": gates, "missing_receipts": sorted({i["receipt"] for i in blockers if i["code"] == "RECEIPT_MISSING"}),
                "blockers": blockers, "next_permitted_read": next_read,
                "raw_probe_status": {k: self.docs[k].get("status") for k in RUNS if k in self.docs},
                "receipt_sha256": {k: _digest(v) for k, v in self.raw.items()},
                "dependency_graph": [{"gate": k, "depends_on": list(v), "state": gates[k]["state"]}
                                     for k, v in DEPENDENCIES.items()]}


def compile_readiness(receipts: Mapping[str, bytes], *, expected: ExpectedSource,
                      verify: Verifier, now: int,
                      target: str = "actual_unit_qualified") -> dict:
    """Reduce already acquired evidence; never acquire or execute anything.

    READY means the selected evidence set is internally qualified for its stated
    boundary. It grants no permission and predicts no later phase. The verifier
    is a trusted, non-effectful adapter to existing custody/signature owners; a
    JSON `verified: true` field is never an authentication mechanism.
    """
    try:
        return _Check(receipts, expected, verify, now).run(target)
    except _Invalid as exc:
        return {"schema": "mastermind.hermes_p0_readiness.v1", "state": REFUSED,
                "source_only": True, "authorization_granted": False,
                "blockers": [{"gate": "input", "receipt": "bundle", "state": REFUSED,
                              "code": str(exc), "field": ""}],
                "next_permitted_read": {"action": "READ_ORIGINAL_RETAINED_RECEIPT",
                                        "owner": "original-operation-owner", "receipt": "bundle"}}
