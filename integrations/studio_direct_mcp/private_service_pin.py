"""One sealed-seat native-pool pin transition; called only by private_service.

No lifecycle control, pool selection, admission, provider access or enrollment.
The existing seat lifecycle and native publication locks serialize cooperative
owners; private directories do not claim atomic CAS against an adversarial UID.
"""

from contextlib import contextmanager, nullcontext
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile

SCHEMA = "mastermind.studio_native_pool_pin.v1"
REFUSAL_CODES = frozenset(
    (
        "ACCOUNT_REFUSED",
        "ALREADY_BOUND",
        "DIRECTORY_REFUSED",
        "FLEET_BINDING_REFUSED",
        "FLEET_SHAPE_REFUSED",
        "FOREIGN_MODE",
        "FOREIGN_STATE",
        "FOREIGN_TRANSACTION",
        "FUTURE_PIN_NOT_READY",
        "INPUT_REFUSED",
        "INTENT_REFUSED",
        "JSON_REFUSED",
        "MANIFEST_CAS_REFUSED",
        "PLAN_CAS_REFUSED",
        "POST_PROFILE_REFUSED",
        "PROFILE_REFUSED",
        "RECONCILIATION_REQUIRED",
        "RESULT_REFUSED",
        "RESULT_STATE_REFUSED",
        "RETAINED_BYTES_REFUSED",
        "RETAINED_PLAN_REFUSED",
        "RETAINED_TARGET_REFUSED",
        "SERVICE_LOADED",
        "START_PLAN_REFUSED",
        "STATIC_SEAL_REFUSED",
        "SUCCESSOR_ALREADY_ADVANCED",
        "SUCCESSOR_REFUSED",
        "TRANSACTION_EXISTS",
    )
)
FILES = {
    "plan.json",
    "intent.json",
    "config.before.json",
    "config.after.json",
    "manifest.before.json",
    "manifest.after.json",
    "result.json",
}

# The one closed forward transition: an already enrolled seat moves from its
# preserved original successor pin to a qualified retained-Go application
# ingress. It is a distinct transaction with a distinct artifact set, so the
# incumbent original plan, receipt and bytes stay immutable and readable.
FORWARD_SCHEMA = "mastermind.studio_native_pool_pin_forward.v1"
FORWARD_FILES = {
    "plan.json",
    "intent.json",
    "config.before.json",
    "config.after.json",
    "manifest.before.json",
    "manifest.after.json",
    "result.json",
}
FORWARD_PLAN_FIELDS = frozenset((
    "schema",
    "account",
    "uid",
    "go_bundle",
    "go_digest",
    "go_schema",
    "go_generation",
    "go_expected_selection",
    "go_bootstrap_digest",
    "go_prior_successor_digest",
    "go_component_sha256",
    "go_manifest_sha256",
    "pool_target",
    "pool_previous",
    "pool_bridge",
    "original_plan_sha256",
    "original_receipt_sha256",
    "original_successor_digest",
    "predecessor_records",
    "config_before",
    "config_after",
    "manifest_before",
    "manifest_after",
    "config_mode",
    "manifest_mode",
))
FORWARD_REFUSAL_CODES = frozenset(
    (
        "ACCOUNT_REFUSED",
        "ALREADY_BOUND",
        "DIRECTORY_REFUSED",
        "FLEET_BINDING_REFUSED",
        "FLEET_SHAPE_REFUSED",
        "FOREIGN_MODE",
        "FOREIGN_STATE",
        "FOREIGN_TRANSACTION",
        "GO_CHANGED",
        "GO_REFUSED",
        "INPUT_REFUSED",
        "INTENT_REFUSED",
        "JSON_REFUSED",
        "ORIGINAL_REFUSED",
        "PLAN_CAS_REFUSED",
        "PROFILE_REFUSED",
        "RECONCILIATION_REQUIRED",
        "RESULT_REFUSED",
        "RESULT_STATE_REFUSED",
        "RETAINED_BYTES_REFUSED",
        "RETAINED_PLAN_REFUSED",
        "RETAINED_TARGET_REFUSED",
        "START_HELD",
        "START_PLAN_REFUSED",
        "STATIC_SEAL_REFUSED",
        "SUCCESSOR_ALREADY_ADVANCED",
        "TRANSACTION_EXISTS",
        "PREDECESSOR_CHANGED",
        "EFFECT_UNKNOWN_RECONCILE_SAME_OWNER",
        "EFFECT_UNKNOWN_PREPARATION_RECONCILE_SAME_OWNER",
        "EFFECT_UNKNOWN_DURABILITY_RECONCILE_SAME_OWNER",
    )
)


def fail(code):
    raise SystemExit("NATIVE_POOL_PIN_" + code)


def fail_forward(code):
    raise SystemExit("NATIVE_POOL_PIN_FORWARD_" + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                fail("JSON_REFUSED")
            out[key] = value
        return out

    def nonfinite(_):
        fail("JSON_REFUSED")

    def finite(raw):
        value = float(raw)
        if not math.isfinite(value):
            fail("JSON_REFUSED")
        return value

    try:
        value = json.loads(
            raw, object_pairs_hook=unique, parse_constant=nonfinite, parse_float=finite
        )
    except (ValueError, UnicodeError, RecursionError):
        fail("JSON_REFUSED")
    if type(value) is not dict:
        fail("JSON_REFUSED")
    return value


def directory(svc, path):
    svc._assert_dest_safe(path)
    s = path.lstat()
    if (
        not stat.S_ISDIR(s.st_mode)
        or s.st_uid != os.getuid()
        or stat.S_IMODE(s.st_mode) != svc.DIR_MODE
    ):
        fail("DIRECTORY_REFUSED")


def payload(svc, roots, name):
    return svc._fabric_release_bytes(roots[name])


def stopped(svc, account, roots):
    label = "com.mastermind.studio-direct-private." + account
    if svc._lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        fail("SERVICE_LOADED")


def snapshot(svc, args, roots, binding):
    label = "com.mastermind.studio-direct-private." + args.account
    c_raw = payload(svc, roots, "config")
    m_raw = payload(svc, roots, "manifest")
    c = decode(c_raw)
    m = decode(m_raw)
    if digest(m_raw) != args.expected_manifest_sha256:
        fail("MANIFEST_CAS_REFUSED")
    if not svc._native_pin_manifest_valid(m, args.account, label):
        fail("PROFILE_REFUSED")
    svc._verify_native_pin_install(args.account, label, roots)
    f = c.get("fleetStatus")
    keys = {
        "enabled",
        "launcherPath",
        "launcherSha256",
        "timeoutMs",
        "fabricLauncherPath",
        "fabricLauncherSha256",
        "fabricTimeoutMs",
    }
    if type(f) is not dict or set(f) != keys or f["enabled"] is not True:
        fail("FLEET_SHAPE_REFUSED")
    if (
        f["fabricLauncherPath"] != binding["pool_target"]
        or not svc._sha256_hex(f["fabricLauncherSha256"])
        or not svc._sha256_hex(f["launcherSha256"])
        or type(f["launcherPath"]) is not str
        or not Path(f["launcherPath"]).is_absolute()
        or type(f["timeoutMs"]) is not int
        or not 1000 <= f["timeoutMs"] <= 30000
        or type(f["fabricTimeoutMs"]) is not int
        or not 1000 <= f["fabricTimeoutMs"] <= 30000
    ):
        fail("FLEET_BINDING_REFUSED")
    if f["fabricLauncherSha256"] == binding["pool_bridge"]:
        fail("ALREADY_BOUND")
    after = copy.deepcopy(c)
    after["fleetStatus"]["fabricLauncherSha256"] = binding["pool_bridge"]
    c_post = svc._fabric_release_json(after)
    m_post = copy.deepcopy(m)
    m_post["configHash"] = digest(c_post)
    if not svc._native_pin_manifest_valid(m_post, args.account, label):
        fail("POST_PROFILE_REFUSED")
    m_post_raw = svc._fabric_release_json(m_post)
    plan = {
        "schema": SCHEMA,
        "account": args.account,
        "uid": os.getuid(),
        "successor_bundle": str(Path(args.successor_bundle)),
        "successor_digest": binding["successor_digest"],
        "target_generation": binding["target_generation"],
        "expected_selection": binding["expected_selection"],
        "pool_target": binding["pool_target"],
        "pool_previous": binding["pool_previous"],
        "pool_bridge": binding["pool_bridge"],
        "config_before": digest(c_raw),
        "config_after": digest(c_post),
        "manifest_before": digest(m_raw),
        "manifest_after": digest(m_post_raw),
        "config_mode": stat.S_IMODE(roots["config"].lstat().st_mode),
        "manifest_mode": stat.S_IMODE(roots["manifest"].lstat().st_mode),
    }
    raw = {
        "config.before.json": c_raw,
        "config.after.json": c_post,
        "manifest.before.json": m_raw,
        "manifest.after.json": m_post_raw,
    }
    return plan, raw


def plan_sha(svc, plan):
    return digest(svc._fabric_release_json(plan))


def binding_matches(plan, binding, args):
    if (
        plan.get("account") != args.account
        or plan.get("uid") != os.getuid()
        or plan.get("manifest_before") != args.expected_manifest_sha256
        or plan.get("successor_bundle") != str(Path(args.successor_bundle))
    ):
        fail("RETAINED_PLAN_REFUSED")
    for key in (
        "successor_digest",
        "target_generation",
        "expected_selection",
        "pool_target",
        "pool_previous",
        "pool_bridge",
    ):
        if plan.get(key) != binding[key]:
            fail("RETAINED_TARGET_REFUSED")


def read_transaction(svc, path, args, binding):
    directory(svc, path)
    if set(p.name for p in path.iterdir()) - FILES:
        fail("FOREIGN_TRANSACTION")
    plan = decode(svc._fabric_release_bytes(path / "plan.json"))
    if plan_sha(svc, plan) != args.expected_plan_sha256:
        fail("PLAN_CAS_REFUSED")
    fields = {
        "schema",
        "account",
        "uid",
        "successor_bundle",
        "successor_digest",
        "target_generation",
        "expected_selection",
        "pool_target",
        "pool_previous",
        "pool_bridge",
        "config_before",
        "config_after",
        "manifest_before",
        "manifest_after",
        "config_mode",
        "manifest_mode",
    }
    if set(plan) != fields or plan["schema"] != SCHEMA:
        fail("RETAINED_PLAN_REFUSED")
    binding_matches(plan, binding, args)
    raw = {}
    for side in ("config", "manifest"):
        for suffix in ("before", "after"):
            name = side + "." + suffix + ".json"
            raw[name] = svc._fabric_release_bytes(path / name)
            if digest(raw[name]) != plan[side + "_" + suffix]:
                fail("RETAINED_BYTES_REFUSED")
    # Authenticate the exact one-field transformation, not merely four hashes.
    before = decode(raw["config.before.json"])
    after = decode(raw["config.after.json"])
    expected = copy.deepcopy(before)
    if (
        type(expected.get("fleetStatus")) is not dict
        or expected["fleetStatus"].get("fabricLauncherPath") != plan["pool_target"]
    ):
        fail("RETAINED_BYTES_REFUSED")
    expected["fleetStatus"]["fabricLauncherSha256"] = plan["pool_bridge"]
    if after != expected:
        fail("RETAINED_BYTES_REFUSED")
    old = decode(raw["manifest.before.json"])
    new = decode(raw["manifest.after.json"])
    expected = copy.deepcopy(old)
    expected["configHash"] = plan["config_after"]
    label = "com.mastermind.studio-direct-private." + args.account
    if (
        new != expected
        or old.get("configHash") != plan["config_before"]
        or not svc._native_pin_manifest_valid(old, args.account, label)
        or not svc._native_pin_manifest_valid(new, args.account, label)
    ):
        fail("RETAINED_BYTES_REFUSED")
    intent = {"schema": SCHEMA, "planSha256": args.expected_plan_sha256}
    if decode(svc._fabric_release_bytes(path / "intent.json")) != intent:
        fail("INTENT_REFUSED")
    return plan, raw


def state(svc, roots, raw, plan):
    if any(
        stat.S_IMODE(roots[name].lstat().st_mode) != plan[name + "_mode"]
        for name in ("config", "manifest")
    ):
        fail("FOREIGN_MODE")
    c = payload(svc, roots, "config")
    m = payload(svc, roots, "manifest")
    if c == raw["config.before.json"] and m == raw["manifest.before.json"]:
        return "OLD"
    if c == raw["config.after.json"] and m == raw["manifest.before.json"]:
        return "CONFIG_ONLY"
    if c == raw["config.after.json"] and m == raw["manifest.after.json"]:
        return "COMPLETE"
    # Derive only the accepted C1 gateway successor, optionally composed with
    # the existing frozen Paper selection. Never learn from installed bytes.
    successor = c1_gateway_successor_manifest(svc, plan, raw, roots=roots, current=c)
    if successor is not None and m == successor:
        return "COMPLETE"
    fail("FOREIGN_STATE")


def c1_gateway_successor_manifest(svc, plan, raw, *, roots=None, current=None):
    """Derive the one reviewed C1 gateway successor of a retained pin manifest.

    The retained record is the only input. The successor is the retained
    applied manifest with exactly one known gateway digest transition. A
    retained record for any other account, a retained manifest whose gateway
    is not the pinned predecessor, or a retained record whose own digests do
    not match its plan yields None. Nothing is written, cleared or relabelled.
    """
    if plan.get("account") != getattr(svc, "C1_GIT_FAILURE_COMPAT_ACCOUNT", None):
        return None
    applied = raw.get("manifest.after.json")
    previous = raw.get("manifest.before.json")
    if not isinstance(applied, bytes) or not isinstance(previous, bytes):
        return None
    if plan.get("manifest_after") != digest(applied):
        return None
    if plan.get("manifest_before") != digest(previous):
        return None
    if current is not None and current != raw.get("config.after.json"):
        if roots is None:
            return None
        paper = _fleet_paper_v20_selection(svc, plan["account"], roots, plan, raw)
        if paper is None or current != paper["configBytes"]:
            return None
        applied = paper["manifestBytes"]
    try:
        pinned = decode(applied)
    except SystemExit:
        return None
    files = pinned.get("files")
    if (
        type(pinned) is not dict
        or type(files) is not dict
        or files.get("gateway.mjs")
        != getattr(svc, "C1_GIT_FAILURE_COMPAT_PREDECESSOR_SHA256", None)
    ):
        return None
    successor = copy.deepcopy(pinned)
    successor["files"]["gateway.mjs"] = getattr(
        svc, "C1_GIT_FAILURE_COMPAT_SUCCESSOR_SHA256", None)
    if not successor["files"]["gateway.mjs"]:
        return None
    return svc._fabric_release_json(successor)


def static_seal(svc, args, roots, raw, current):
    """Qualify the intentional manifest-last gap without accepting other drift."""
    before = decode(raw["manifest.before.json"])
    if current != "CONFIG_ONLY":
        svc._verify_native_pin_install(
            args.account, "com.mastermind.studio-direct-private." + args.account, roots
        )
        return
    for name, h in before["files"].items():
        if digest(svc._fabric_release_bytes(roots["base"] / name)) != h:
            fail("STATIC_SEAL_REFUSED")
    if (
        digest(payload(svc, roots, "plist")) != before["plistHash"]
        or svc._stable_regular_file_hash(Path(before["node"]), label="pin node")
        != before["nodeHash"]
        or svc._stable_regular_file_hash(Path(before["backend"]), label="pin backend")
        != before["backendHash"]
        or svc._dependency_tree_hash(roots["node_modules"])
        != before["dependencyTreeHash"]
    ):
        fail("STATIC_SEAL_REFUSED")


def report(svc, args, plan, effect, phase, receipt_committed=False):
    return {
        "schema": SCHEMA,
        "account": args.account,
        "planSha256": plan_sha(svc, plan),
        "successorPlanSha256": plan["successor_digest"],
        "effect": effect,
        "phase": phase,
        "configSha256": plan["config_after"],
        "manifestSha256": plan["manifest_after"],
        "serviceStarted": False,
        "poolChanged": False,
        "receiptCommitted": receipt_committed,
    }


def run(svc, args):
    if args.account not in svc.NATIVE_POOL_PIN_ACCOUNTS:
        fail("ACCOUNT_REFUSED")
    if (
        not svc._sha256_hex(args.expected_manifest_sha256)
        or not svc._sha256_hex(args.successor_plan_sha256)
        or (
            args.operation != "preview"
            and not svc._sha256_hex(args.expected_plan_sha256)
        )
    ):
        fail("INPUT_REFUSED")
    roots = svc._build_runtime_roots(args.account)
    path = roots["state"] / "native-pool-pin"
    readonly = args.operation in ("preview", "status")
    lock = nullcontext() if readonly else svc._c2_lifecycle_mutex(args.account)
    with lock, svc._pin_native_context(args) as binding:
        if binding["successor_digest"] != args.successor_plan_sha256:
            fail("SUCCESSOR_REFUSED")
        if args.operation == "preview":
            if os.path.lexists(path):
                fail("TRANSACTION_EXISTS")
            plan, _ = snapshot(svc, args, roots, binding)
            return report(svc, args, plan, "NOT_APPLIED", "PREVIEW")
        if args.operation == "apply" and os.path.lexists(path):
            fail("RECONCILIATION_REQUIRED")
        if args.operation == "apply" and not os.path.lexists(path):
            stopped(svc, args.account, roots)
            plan, raw = snapshot(svc, args, roots, binding)
            if plan_sha(svc, plan) != args.expected_plan_sha256:
                fail("PLAN_CAS_REFUSED")
            if binding.get("phase", "PREVIOUS") != "PREVIOUS":
                fail("SUCCESSOR_ALREADY_ADVANCED")
            directory(svc, roots["state"])
            path.mkdir(mode=svc.DIR_MODE)
            svc._fsync_dir(path.parent)
            svc._fabric_release_new(path / "plan.json", svc._fabric_release_json(plan))
            for name, value in raw.items():
                svc._fabric_release_new(path / name, value)
            svc._fabric_release_new(
                path / "intent.json",
                svc._fabric_release_json(
                    {"schema": SCHEMA, "planSha256": args.expected_plan_sha256}
                ),
            )
        plan, raw = read_transaction(svc, path, args, binding)
        observed = state(svc, roots, raw, plan)
        static_seal(svc, args, roots, raw, observed)
        expected = {
            "schema": SCHEMA,
            "planSha256": args.expected_plan_sha256,
            "effect": "APPLIED",
        }
        if os.path.lexists(path / "result.json"):
            if decode(svc._fabric_release_bytes(path / "result.json")) != expected:
                fail("RESULT_REFUSED")
            if observed != "COMPLETE":
                fail("RESULT_STATE_REFUSED")
        if args.operation == "status":
            return report(
                svc,
                args,
                plan,
                {"OLD": "NOT_APPLIED", "CONFIG_ONLY": "PARTIAL", "COMPLETE": "APPLIED"}[
                    observed
                ],
                observed,
                receipt_committed=os.path.lexists(path / "result.json"),
            )
        stopped(svc, args.account, roots)
        if (
            args.operation == "apply"
            and observed != "OLD"
            and not os.path.lexists(path / "result.json")
        ):
            fail("RECONCILIATION_REQUIRED")
        if observed == "OLD":
            if binding.get("phase", "PREVIOUS") != "PREVIOUS":
                fail("SUCCESSOR_ALREADY_ADVANCED")
            if state(svc, roots, raw, plan) != "OLD":
                fail("FOREIGN_STATE")
            svc._atomic_write_bytes(
                roots["config"], raw["config.after.json"], mode=plan["config_mode"]
            )
            observed = state(svc, roots, raw, plan)
            if observed != "CONFIG_ONLY":
                fail("FOREIGN_STATE")
        if observed == "CONFIG_ONLY":
            stopped(svc, args.account, roots)
            static_seal(svc, args, roots, raw, observed)
            if state(svc, roots, raw, plan) != "CONFIG_ONLY":
                fail("FOREIGN_STATE")
            svc._atomic_write_bytes(
                roots["manifest"],
                raw["manifest.after.json"],
                mode=plan["manifest_mode"],
            )
        if state(svc, roots, raw, plan) != "COMPLETE":
            fail("FOREIGN_STATE")
        static_seal(svc, args, roots, raw, "COMPLETE")
        stopped(svc, args.account, roots)
        if not os.path.lexists(path / "result.json"):
            svc._fabric_release_new(
                path / "result.json", svc._fabric_release_json(expected)
            )
        return report(svc, args, plan, "APPLIED", "COMPLETE", receipt_committed=True)


def _c2_paper_v20_postpin_start(svc, account, roots, plan, raw, current, manifest):
    """Recognize ONLY the reviewed C2 v12 -> v20 Paper-only successor.

    A selected native-pool pin remains independently enforced: this does not
    alter its transaction states or allow subsequent unreviewed pin drift.
    """
    if (account != svc.C2_PAPER_ACCOUNT
            or plan.get("manifest_after") != svc.C2_PAPER_V12_MANIFEST_SHA256):
        return False
    if any(stat.S_IMODE(roots[n].lstat().st_mode) != plan[n + "_mode"]
           for n in ("config", "manifest")):
        return False
    pinned_config = decode(raw["config.after.json"])
    pinned_manifest = decode(raw["manifest.after.json"])
    root = svc._user_root()
    if (pinned_config.get("paperDesign") != svc._paper_design_config(root)
            or pinned_manifest.get("configHash") != digest(raw["config.after.json"])):
        return False
    expected_config = copy.deepcopy(pinned_config)
    expected_config["paperDesign"] = svc._paper_design_config(
        root, rel=svc.PAPER_RUNTIME_V20_REL,
        bridge_sha256=svc.PAPER_V20_BRIDGE_SHA256)
    config_bytes = json.dumps(expected_config, indent=2, sort_keys=True).encode("utf-8")
    expected_manifest = copy.deepcopy(pinned_manifest)
    expected_manifest["configHash"] = digest(config_bytes)
    manifest_bytes = json.dumps(
        expected_manifest, indent=2, sort_keys=True).encode("utf-8")
    return current == config_bytes and manifest == manifest_bytes


def _fleet_paper_v20_selection(svc, account, roots, plan, raw):
    """Compose only frozen eight-seat Paper CAS with the selected native-pool pin.

    The original native-pool result, selected phase and exact pool digest
    remain mandatory in require_start. No new cohort, pin or writer is created.
    """
    enrolled = getattr(svc, "FLEET_V20_ENROLLED_ACCOUNTS", ())
    if account not in enrolled or account == "mastermind-os-publication":
        return None  # The publication seat has no native-pool pin to compose.
    if any(stat.S_IMODE(roots[n].lstat().st_mode) != plan[n + "_mode"]
           for n in ("config", "manifest")):
        return None

    cohort = svc._frozen_paper_fleet_module()
    pinned = cohort.COHORTS.get(account)
    if (pinned is None
            or plan.get("manifest_after") != pinned.get("manifest_sha256")
            or digest(raw["manifest.after.json"]) != pinned.get("manifest_sha256")
            or digest(raw["config.after.json"]) != pinned.get("config_sha256")):
        return None

    # The already accepted pure planner checks original three byte-sealed
    # resources, exact immutable predecessor, non-Paper profile and target v20.
    plist_bytes = svc._fabric_release_bytes(roots["plist"], limit=64 * 1024)
    try:
        successor = cohort.plan_selection(
            account,
            manifest_bytes=raw["manifest.after.json"],
            config_bytes=raw["config.after.json"],
            plist_bytes=plist_bytes,
            home=svc._user_root(),
        )
    except ValueError:
        return None
    return successor


def _fleet_paper_v20_postpin_start(svc, account, roots, plan, raw, current, manifest):
    successor = _fleet_paper_v20_selection(svc, account, roots, plan, raw)
    return (successor is not None and current == successor["configBytes"]
            and manifest == successor["manifestBytes"])


def _c1_fleet_git_failure_postpin_start(svc, account, roots, plan, raw, current, manifest):
    """Recognize ONLY the reviewed C1 fleet-gateway Git-failure successor.

    A retained native-pool pin stays independently enforced: its own plan,
    result, native phase and bridge remain mandatory in require_start. This
    recognizes exactly one forward-selected successor of that retained
    applied manifest - the same manifest with one known gateway digest
    transition. A pending or unknown pin stays pending or unknown, and no
    retained record is edited, cleared or relabelled.
    """
    if account != getattr(svc, "C1_GIT_FAILURE_COMPAT_ACCOUNT", None):
        return False
    if any(stat.S_IMODE(roots[n].lstat().st_mode) != plan[n + "_mode"]
           for n in ("config", "manifest")):
        return False
    successor = c1_gateway_successor_manifest(svc, plan, raw, roots=roots, current=current)
    if successor is None:
        return False
    return manifest == successor


@contextmanager
def selected_applied_context(svc, account, roots, *, operation="status",
                             retained_proof_purpose=None):
    """Share the incumbent selected-pin proof without replaying its operation.

    An apply caller holds the same native publication lock until its own
    enclosing gateway transaction exits. No pin record or native selection is
    changed here; read_transaction remains the only retained-record verifier.

    ``retained_proof_purpose`` is the one closed chatgpt1 gateway-formatter
    artifact check. It is not a native operation. Generic apply stays strict.
    """
    closed_purpose = getattr(svc, "C1_GATEWAY_RETAINED_PROOF_PURPOSE", None)
    closed_account = getattr(svc, "C1_GIT_FAILURE_COMPAT_ACCOUNT", None)
    if retained_proof_purpose is not None:
        if (retained_proof_purpose != closed_purpose
                or account != closed_account
                or operation not in {"preview", "apply"}):
            fail("INPUT_REFUSED")
    elif operation not in {"status", "apply"}:
        fail("INPUT_REFUSED")
    path = roots["state"] / "native-pool-pin"
    directory(svc, path)
    p = decode(svc._fabric_release_bytes(path / "plan.json"))
    if (p.get("schema") != SCHEMA or p.get("account") != account
            or p.get("uid") != os.getuid()):
        fail("START_PLAN_REFUSED")
    try:
        args = type("PinStartInputs", (), {
            "account": account,
            "expected_manifest_sha256": p["manifest_before"],
            "successor_bundle": p["successor_bundle"],
            "successor_plan_sha256": p["successor_digest"],
            "expected_plan_sha256": plan_sha(svc, p),
            "operation": operation,
            "retained_proof_purpose": retained_proof_purpose or "",
        })()
    except KeyError:
        fail("RETAINED_PLAN_REFUSED")
    with svc._pin_native_context(args) as binding:
        plan, raw = read_transaction(svc, path, args, binding)
        result = decode(svc._fabric_release_bytes(path / "result.json"))
        if (result != {"schema": SCHEMA, "planSha256": plan_sha(svc, p), "effect": "APPLIED"}
                or binding.get("phase") != "SELECTED"
                or svc._stable_regular_file_hash(Path(p["pool_target"]), label="native pool")
                != p["pool_bridge"]):
            fail("FUTURE_PIN_NOT_READY")
        yield plan, raw


def require_start(svc, account, roots):
    """Only an OWNED future-pin transition adds a startup fence."""
    path = roots["state"] / "native-pool-pin"
    forward_path = roots["state"] / "native-pool-pin-forward"
    if not os.path.lexists(path) and not os.path.lexists(forward_path):
        return
    if os.path.lexists(forward_path):
        # The forward transition owns the fence once its record exists. The
        # seat stays start-held until the exact completed Go ingress is proven.
        with forward_selected_context(svc, account, roots):
            pass
        return
    directory(svc, path)
    p = decode(svc._fabric_release_bytes(path / "plan.json"))
    if (
        p.get("schema") != SCHEMA
        or p.get("account") != account
        or p.get("uid") != os.getuid()
    ):
        fail("START_PLAN_REFUSED")
    current = payload(svc, roots, "config")
    manifest = payload(svc, roots, "manifest")
    if digest(current) == p.get("config_before") and digest(manifest) == p.get(
        "manifest_before"
    ):
        return  # untouched incumbent behavior, including its historical pin drift
    with selected_applied_context(svc, account, roots) as (plan, raw):
        if (
            not (
                (current == raw["config.after.json"]
                 and manifest == raw["manifest.after.json"]
                 and state(svc, roots, raw, plan) == "COMPLETE")
                or _c2_paper_v20_postpin_start(
                    svc, account, roots, plan, raw, current, manifest)
                or _fleet_paper_v20_postpin_start(
                    svc, account, roots, plan, raw, current, manifest)
                or _c1_fleet_git_failure_postpin_start(
                    svc, account, roots, plan, raw, current, manifest)
            )
        ):
            fail("FUTURE_PIN_NOT_READY")


# ---------------------------------------------------------------------------
# The one closed forward Go bridge pin transition.
#
# It extends this incumbent owner and its locks. It creates no new lifecycle
# owner, registry, queue, identity or credential path, and it never edits,
# clears or relabels the incumbent original pin record.
# ---------------------------------------------------------------------------


def forward_binding_matches(plan, binding, args):
    """Bind a retained forward record to the exact authenticated Go artifact."""
    if (
        plan.get("account") != args.account
        or plan.get("uid") != os.getuid()
        or plan.get("go_bundle") != str(Path(args.forward_go_bundle))
    ):
        fail_forward("RETAINED_PLAN_REFUSED")
    for key in (
        "go_digest",
        "go_schema",
        "go_generation",
        "go_expected_selection",
        "go_bootstrap_digest",
        "go_prior_successor_digest",
        "go_component_sha256",
        "go_manifest_sha256",
        "pool_target",
        "pool_previous",
        "pool_bridge",
    ):
        if plan.get(key) != binding[key]:
            fail_forward("RETAINED_TARGET_REFUSED")


def original_pin_record(svc, account, roots, binding):
    """Read the complete original APPLIED history without replaying it."""
    path = roots["state"] / "native-pool-pin"
    try:
        directory(svc, path)
        if set(p.name for p in path.iterdir()) != FILES:
            fail_forward("ORIGINAL_REFUSED")
        p = decode(svc._fabric_release_bytes(path / "plan.json"))
        prior = binding["original_successor"]
        if (type(prior) is not dict or set(prior) != {
                "successor_bundle", "successor_digest", "target_generation",
                "expected_selection", "pool_target", "pool_previous", "pool_bridge"}
                or prior["successor_digest"] != binding["go_prior_successor_digest"]
                or prior["pool_target"] != binding["pool_target"]
                or prior["pool_bridge"] != binding["pool_previous"]
                or Path(p["successor_bundle"]).resolve(strict=True)
                != Path(prior["successor_bundle"]).resolve(strict=True)):
            fail_forward("ORIGINAL_REFUSED")
        args = type("HistoricalPinInputs", (), {
            "account": account,
            "expected_manifest_sha256": p["manifest_before"],
            "successor_bundle": p["successor_bundle"],
            "expected_plan_sha256": plan_sha(svc, p),
        })()
        plan, raw = read_transaction(svc, path, args, prior)
        receipt_raw = svc._fabric_release_bytes(path / "result.json")
        if decode(receipt_raw) != {
                "schema": SCHEMA, "planSha256": args.expected_plan_sha256,
                "effect": "APPLIED"}:
            fail_forward("ORIGINAL_REFUSED")
        if any(type(plan[n + "_mode"]) is not int
               or stat.S_IMODE(roots[n].lstat().st_mode) != plan[n + "_mode"]
               for n in ("config", "manifest")):
            fail_forward("ORIGINAL_REFUSED")
    except (OSError, ValueError, KeyError, TypeError, SystemExit):
        fail_forward("ORIGINAL_REFUSED")
    return {
        "plan_sha256": args.expected_plan_sha256,
        "receipt_sha256": digest(receipt_raw),
        "successor_digest": plan["successor_digest"],
        "pool_target": plan["pool_target"],
        "plan": plan, "raw": raw,
        "fingerprint": {name: digest(svc._fabric_release_bytes(path / name))
                        for name in sorted(FILES)},
    }


def forward_original_matches(svc, args, roots, binding, plan, raw):
    """Revalidate every authenticated predecessor before effects or acknowledgment."""
    require_forward_predecessor(svc, args, roots, binding, plan, raw)


def forward_sync(svc, roots, path, plan, raw, observed, *, receipt=None):
    """Re-establish durability of the existing bytes; never rewrite them.

    The incumbent strict sync verifies the exact inode and bytes, synchronizes
    the file and its parent, and verifies readback. Status and startup may
    reconcile this durability, but never create a plan or repair a pair.
    The immutable original pin history is not synchronized or changed here.
    """
    try:
        svc._original_install_fsync_parent(path.parent)
        records = {
            "plan.json": svc._fabric_release_json(plan),
            **raw,
            "intent.json": svc._fabric_release_json({
                "schema": FORWARD_SCHEMA, "planSha256": plan_sha(svc, plan)}),
        }
        for name, expected in records.items():
            svc._original_install_sync(path / name, expected)
        svc._original_install_sync(roots["config"], raw[
            "config.before.json" if observed == "OLD" else "config.after.json"])
        svc._original_install_sync(roots["manifest"], raw[
            "manifest.after.json" if observed == "COMPLETE" else "manifest.before.json"])
        if receipt is not None:
            svc._original_install_sync(
                path / "result.json", svc._fabric_release_json(receipt))
        confirm_forward_durability(svc, roots, path)
    except BaseException:
        fail_forward("EFFECT_UNKNOWN_DURABILITY_RECONCILE_SAME_OWNER")


def forward_snapshot(svc, args, roots, binding):
    """Derive the exact one-field forward target from the authenticated Go plan.

    Only ``fleetStatus.fabricLauncherSha256`` and the sealed ``configHash``
    change. Every other config value, manifest field, launcher path, owner,
    account, profile, module, plist, executable and dependency is preserved.
    """
    label = "com.mastermind.studio-direct-private." + args.account
    c_raw = payload(svc, roots, "config")
    m_raw = payload(svc, roots, "manifest")
    c = decode(c_raw)
    m = decode(m_raw)
    if not svc._native_pin_manifest_valid(m, args.account, label):
        fail_forward("PROFILE_REFUSED")
    svc._verify_native_pin_install(args.account, label, roots)
    f = c.get("fleetStatus")
    keys = {
        "enabled",
        "launcherPath",
        "launcherSha256",
        "timeoutMs",
        "fabricLauncherPath",
        "fabricLauncherSha256",
        "fabricTimeoutMs",
    }
    if type(f) is not dict or set(f) != keys or f["enabled"] is not True:
        fail_forward("FLEET_SHAPE_REFUSED")
    if (
        f["fabricLauncherPath"] != binding["pool_target"]
        or not svc._sha256_hex(f["fabricLauncherSha256"])
        or not svc._sha256_hex(f["launcherSha256"])
        or type(f["launcherPath"]) is not str
        or not Path(f["launcherPath"]).is_absolute()
        or type(f["timeoutMs"]) is not int
        or not 1000 <= f["timeoutMs"] <= 30000
        or type(f["fabricTimeoutMs"]) is not int
        or not 1000 <= f["fabricTimeoutMs"] <= 30000
    ):
        fail_forward("FLEET_BINDING_REFUSED")
    if f["fabricLauncherSha256"] == binding["pool_bridge"]:
        fail_forward("ALREADY_BOUND")
    after = copy.deepcopy(c)
    after["fleetStatus"]["fabricLauncherSha256"] = binding["pool_bridge"]
    c_post = svc._fabric_release_json(after)
    m_post = copy.deepcopy(m)
    m_post["configHash"] = digest(c_post)
    if not svc._native_pin_manifest_valid(m_post, args.account, label):
        fail_forward("PROFILE_REFUSED")
    m_post_raw = svc._fabric_release_json(m_post)
    original, records = forward_predecessor(
        svc, args.account, roots, binding, c_raw, m_raw)
    plan = {
        "schema": FORWARD_SCHEMA,
        "account": args.account,
        "uid": os.getuid(),
        "go_bundle": str(Path(args.forward_go_bundle)),
        "go_digest": binding["go_digest"],
        "go_schema": binding["go_schema"],
        "go_generation": binding["go_generation"],
        "go_expected_selection": binding["go_expected_selection"],
        "go_bootstrap_digest": binding["go_bootstrap_digest"],
        "go_prior_successor_digest": binding["go_prior_successor_digest"],
        "go_component_sha256": binding["go_component_sha256"],
        "go_manifest_sha256": binding["go_manifest_sha256"],
        "pool_target": binding["pool_target"],
        "pool_previous": binding["pool_previous"],
        "pool_bridge": binding["pool_bridge"],
        "original_plan_sha256": original["plan_sha256"],
        "original_receipt_sha256": original["receipt_sha256"],
        "original_successor_digest": original["successor_digest"],
        "predecessor_records": records,
        "config_before": digest(c_raw),
        "config_after": digest(c_post),
        "manifest_before": digest(m_raw),
        "manifest_after": digest(m_post_raw),
        "config_mode": stat.S_IMODE(roots["config"].lstat().st_mode),
        "manifest_mode": stat.S_IMODE(roots["manifest"].lstat().st_mode),
    }
    raw = {
        "config.before.json": c_raw,
        "config.after.json": c_post,
        "manifest.before.json": m_raw,
        "manifest.after.json": m_post_raw,
    }
    return plan, raw


def forward_read_transaction(svc, path, args, binding):
    """Authenticate the retained forward record and its exact one-field change."""
    directory(svc, path)
    if set(p.name for p in path.iterdir()) - FORWARD_FILES:
        fail_forward("FOREIGN_TRANSACTION")
    plan = decode(svc._fabric_release_bytes(path / "plan.json"))
    if plan_sha(svc, plan) != args.expected_plan_sha256:
        fail_forward("PLAN_CAS_REFUSED")
    if set(plan) != FORWARD_PLAN_FIELDS or plan["schema"] != FORWARD_SCHEMA:
        fail_forward("RETAINED_PLAN_REFUSED")
    forward_binding_matches(plan, binding, args)
    raw = {}
    for side in ("config", "manifest"):
        for suffix in ("before", "after"):
            name = side + "." + suffix + ".json"
            raw[name] = svc._fabric_release_bytes(path / name)
            if digest(raw[name]) != plan[side + "_" + suffix]:
                fail_forward("RETAINED_BYTES_REFUSED")
    before = decode(raw["config.before.json"])
    after = decode(raw["config.after.json"])
    expected = copy.deepcopy(before)
    if (
        type(expected.get("fleetStatus")) is not dict
        or expected["fleetStatus"].get("fabricLauncherPath") != plan["pool_target"]
    ):
        fail_forward("RETAINED_BYTES_REFUSED")
    expected["fleetStatus"]["fabricLauncherSha256"] = plan["pool_bridge"]
    if after != expected:
        fail_forward("RETAINED_BYTES_REFUSED")
    old = decode(raw["manifest.before.json"])
    new = decode(raw["manifest.after.json"])
    expected = copy.deepcopy(old)
    expected["configHash"] = plan["config_after"]
    label = "com.mastermind.studio-direct-private." + args.account
    if (
        new != expected
        or old.get("configHash") != plan["config_before"]
        or not svc._native_pin_manifest_valid(old, args.account, label)
        or not svc._native_pin_manifest_valid(new, args.account, label)
    ):
        fail_forward("RETAINED_BYTES_REFUSED")
    intent = {"schema": FORWARD_SCHEMA, "planSha256": args.expected_plan_sha256}
    if decode(svc._fabric_release_bytes(path / "intent.json")) != intent:
        fail_forward("INTENT_REFUSED")
    forward_original_matches(svc, args, svc._build_runtime_roots(args.account), binding, plan, raw)
    return plan, raw


def forward_state(svc, roots, raw, plan):
    """Only the exact old, config-only and complete pairs are recognized."""
    if any(
        stat.S_IMODE(roots[name].lstat().st_mode) != plan[name + "_mode"]
        for name in ("config", "manifest")
    ):
        fail_forward("FOREIGN_MODE")
    c = payload(svc, roots, "config")
    m = payload(svc, roots, "manifest")
    if c == raw["config.before.json"] and m == raw["manifest.before.json"]:
        return "OLD"
    if c == raw["config.after.json"] and m == raw["manifest.before.json"]:
        return "CONFIG_ONLY"
    if c == raw["config.after.json"] and m == raw["manifest.after.json"]:
        return "COMPLETE"
    fail_forward("FOREIGN_STATE")


def forward_report(svc, args, plan, effect, phase, receipt_committed=False):
    return {
        "schema": FORWARD_SCHEMA,
        "account": args.account,
        "planSha256": plan_sha(svc, plan),
        "goPlanSha256": plan["go_digest"],
        "originalPlanSha256": plan["original_plan_sha256"],
        "effect": effect,
        "phase": phase,
        "configSha256": plan["config_after"],
        "manifestSha256": plan["manifest_after"],
        "poolBridgeSha256": plan["pool_bridge"],
        "serviceStarted": False,
        "poolChanged": False,
        "receiptCommitted": receipt_committed,
    }


def run_forward(svc, args):
    """Continue the one original forward pin and acknowledge its durable result."""
    if args.account not in svc.NATIVE_POOL_PIN_FORWARD_ACCOUNTS:
        fail_forward("ACCOUNT_REFUSED")
    if args.operation not in ("preview", "apply", "status", "reconcile"):
        fail_forward("INPUT_REFUSED")
    if args.operation != "preview" and not svc._sha256_hex(
        args.expected_plan_sha256 or ""
    ):
        fail_forward("INPUT_REFUSED")
    roots = svc._build_runtime_roots(args.account)
    path = roots["state"] / "native-pool-pin-forward"
    readonly = args.operation in ("preview", "status")
    lock = nullcontext() if readonly else svc._c2_lifecycle_mutex(args.account)
    with lock, svc._pin_forward_native_context(args) as binding:
        phase = binding.get("phase")
        if phase not in ("PREVIOUS", "SELECTED"):
            fail_forward("GO_REFUSED")
        if phase == "SELECTED" and args.operation in ("preview", "apply"):
            fail_forward("SUCCESSOR_ALREADY_ADVANCED")
        if args.operation == "preview":
            if os.path.lexists(path):
                fail_forward("TRANSACTION_EXISTS")
            plan, _ = forward_snapshot(svc, args, roots, binding)
            return forward_report(svc, args, plan, "NOT_APPLIED", "PREVIEW")
        if args.operation == "apply" and os.path.lexists(path):
            fail_forward("RECONCILIATION_REQUIRED")
        if args.operation == "apply":
            stopped(svc, args.account, roots)
            plan, raw = forward_snapshot(svc, args, roots, binding)
            if plan_sha(svc, plan) != args.expected_plan_sha256:
                fail_forward("PLAN_CAS_REFUSED")
            publish_forward_intent(svc, path, args, binding, plan, raw)
        # Only a complete authenticated intent is active. Retain the same
        # transaction during reconciliation; never derive a replacement plan.
        plan, raw = forward_read_transaction(svc, path, args, binding)
        observed = forward_state(svc, roots, raw, plan)
        if phase == "SELECTED" and observed != "COMPLETE":
            fail_forward("SUCCESSOR_ALREADY_ADVANCED")
        static_seal(svc, args, roots, raw, observed)
        expected = {
            "schema": FORWARD_SCHEMA,
            "planSha256": args.expected_plan_sha256,
            "effect": "APPLIED",
        }
        has_result = os.path.lexists(path / "result.json")
        if has_result:
            if decode(svc._fabric_release_bytes(path / "result.json")) != expected:
                fail_forward("RESULT_REFUSED")
            if observed != "COMPLETE":
                fail_forward("RESULT_STATE_REFUSED")
        forward_sync(svc, roots, path, plan, raw, observed,
                     receipt=expected if has_result else None)
        forward_original_matches(svc, args, roots, binding, plan, raw)
        if forward_state(svc, roots, raw, plan) != observed:
            fail_forward("FOREIGN_STATE")
        if args.operation == "status":
            return forward_report(svc, args, plan, {
                "OLD": "NOT_APPLIED", "CONFIG_ONLY": "PARTIAL", "COMPLETE": "APPLIED"
            }[observed], observed, receipt_committed=has_result)
        stopped(svc, args.account, roots)
        if (args.operation == "apply" and observed != "OLD" and not has_result):
            fail_forward("RECONCILIATION_REQUIRED")
        attempted = False
        try:
            if observed == "OLD":
                if phase != "PREVIOUS":
                    fail_forward("SUCCESSOR_ALREADY_ADVANCED")
                forward_original_matches(svc, args, roots, binding, plan, raw)
                if forward_state(svc, roots, raw, plan) != "OLD":
                    fail_forward("FOREIGN_STATE")
                attempted = True
                svc._atomic_write_bytes(
                    roots["config"], raw["config.after.json"], mode=plan["config_mode"])
                observed = forward_state(svc, roots, raw, plan)
                if observed != "CONFIG_ONLY":
                    fail_forward("FOREIGN_STATE")
            if observed == "CONFIG_ONLY":
                if phase != "PREVIOUS":
                    fail_forward("SUCCESSOR_ALREADY_ADVANCED")
                stopped(svc, args.account, roots)
                forward_sync(svc, roots, path, plan, raw, observed)
                forward_original_matches(svc, args, roots, binding, plan, raw)
                static_seal(svc, args, roots, raw, observed)
                if forward_state(svc, roots, raw, plan) != "CONFIG_ONLY":
                    fail_forward("FOREIGN_STATE")
                attempted = True
                svc._atomic_write_bytes(
                    roots["manifest"], raw["manifest.after.json"],
                    mode=plan["manifest_mode"])
            if forward_state(svc, roots, raw, plan) != "COMPLETE":
                fail_forward("FOREIGN_STATE")
            static_seal(svc, args, roots, raw, "COMPLETE")
            stopped(svc, args.account, roots)
            forward_sync(svc, roots, path, plan, raw, "COMPLETE")
            forward_original_matches(svc, args, roots, binding, plan, raw)
            if not has_result:
                attempted = True
                svc._fleet_status_successor_owner_module()._publish_result(svc, path, expected)
            forward_sync(svc, roots, path, plan, raw, "COMPLETE", receipt=expected)
            forward_original_matches(svc, args, roots, binding, plan, raw)
            if forward_state(svc, roots, raw, plan) != "COMPLETE":
                fail_forward("FOREIGN_STATE")
        except BaseException as error:
            if (isinstance(error, SystemExit) and isinstance(error.code, str)
                    and error.code.startswith("NATIVE_POOL_PIN_FORWARD_EFFECT_UNKNOWN_")):
                raise
            if attempted:
                fail_forward("EFFECT_UNKNOWN_RECONCILE_SAME_OWNER")
            raise
        return forward_report(
            svc, args, plan, "APPLIED", "COMPLETE", receipt_committed=True)


@contextmanager
def forward_selected_context(svc, account, roots, *, operation="status"):
    """Authenticate the forward transition and the completed Go ingress.

    The incumbent original pin record, this forward record and the strict
    completed Go native proof are all required. A prepared seat stays
    start-held until the exact completed Go ingress is proven. This proof is
    never used to widen generic status or to repair native evidence.
    """
    if operation not in {"status", "apply"}:
        fail_forward("INPUT_REFUSED")
    path = roots["state"] / "native-pool-pin-forward"
    directory(svc, path)
    p = decode(svc._fabric_release_bytes(path / "plan.json"))
    if (
        p.get("schema") != FORWARD_SCHEMA
        or p.get("account") != account
        or p.get("uid") != os.getuid()
    ):
        fail_forward("START_PLAN_REFUSED")
    args = type("ForwardStartInputs", (), {
        "account": account,
        "forward_go_bundle": p.get("go_bundle", ""),
        "expected_plan_sha256": plan_sha(svc, p),
        "operation": operation,
    })()
    with svc._pin_forward_native_context(args) as binding:
        if binding.get("phase") != "SELECTED":
            fail_forward("START_HELD")
        plan, raw = forward_read_transaction(svc, path, args, binding)
        result = decode(svc._fabric_release_bytes(path / "result.json"))
        if result != {
            "schema": FORWARD_SCHEMA,
            "planSha256": plan_sha(svc, p),
            "effect": "APPLIED",
        }:
            fail_forward("RESULT_REFUSED")
        if forward_state(svc, roots, raw, plan) != "COMPLETE":
            fail_forward("RESULT_STATE_REFUSED")
        if (
            svc._stable_regular_file_hash(Path(plan["pool_target"]), label="native pool")
            != plan["pool_bridge"]
        ):
            fail_forward("START_HELD")
        forward_sync(svc, roots, path, plan, raw, "COMPLETE", receipt=result)
        forward_original_matches(svc, args, roots, binding, plan, raw)
        if forward_state(svc, roots, raw, plan) != "COMPLETE":
            fail_forward("RESULT_STATE_REFUSED")
        yield plan, raw


def forward_predecessor(svc, account, roots, binding, config, manifest):
    """Compose incumbent history with explicit retained before bytes."""
    original = original_pin_record(svc, account, roots, binding)
    records = {"native-pool-pin": original["fingerprint"]}
    status = svc._fleet_status_successor_owner_module()
    enrollment = svc._pin_enrollment_owner_module()
    status_path = roots["state"] / status.TRANSACTION
    enrollment_path = roots["state"] / enrollment.TRANSACTION
    if os.path.lexists(status_path):
        status.require_forward_predecessor(
            svc, account, roots, config, manifest, original)
    elif account in enrollment.PROFILES and os.path.lexists(enrollment_path):
        enrollment.require_forward_predecessor(
            svc, account, roots, config, manifest, original)
    else:
        p, raw = original["plan"], original["raw"]
        modes = all(stat.S_IMODE(roots[n].lstat().st_mode) == p[n + "_mode"]
                    for n in ("config", "manifest"))
        if not modes or not (
            (config == raw["config.after.json"] and manifest == raw["manifest.after.json"])
            or _c2_paper_v20_postpin_start(svc, account, roots, p, raw, config, manifest)
            or _fleet_paper_v20_postpin_start(svc, account, roots, p, raw, config, manifest)
            or _c1_fleet_git_failure_postpin_start(svc, account, roots, p, raw, config, manifest)
        ):
            fail_forward("ORIGINAL_REFUSED")
    for path, names in ((enrollment_path, enrollment.FILES),
                        (status_path, status.FILE_NAMES)):
        if os.path.lexists(path):
            directory(svc, path)
            if {p.name for p in path.iterdir()} != set(names):
                fail_forward("ORIGINAL_REFUSED")
            records[path.name] = {name: digest(svc._fabric_release_bytes(path / name))
                                  for name in sorted(names)}
    return original, records


def require_forward_predecessor(svc, args, roots, binding, plan, raw):
    original, records = forward_predecessor(
        svc, args.account, roots, binding,
        raw["config.before.json"], raw["manifest.before.json"])
    if (original["plan_sha256"] != plan["original_plan_sha256"]
            or original["receipt_sha256"] != plan["original_receipt_sha256"]
            or original["successor_digest"] != plan["original_successor_digest"]
            or records != plan["predecessor_records"]):
        fail_forward("PREDECESSOR_CHANGED")


def publish_forward_intent(svc, target, args, binding, plan, raw):
    """Publish the complete intent using the incumbent exclusive rename owner."""
    owner = svc._fleet_status_successor_owner_module()
    directory(svc, target.parent)
    stage = Path(tempfile.mkdtemp(prefix=".native-pool-pin-forward.", dir=target.parent))
    identity = owner._identity(stage)
    attempted = False
    try:
        svc._fabric_release_new(stage / "plan.json", svc._fabric_release_json(plan))
        for name, blob in raw.items():
            svc._fabric_release_new(stage / name, blob)
        svc._fabric_release_new(stage / "intent.json", svc._fabric_release_json({
            "schema": FORWARD_SCHEMA, "planSha256": args.expected_plan_sha256}))
        retained_plan, retained_raw = forward_read_transaction(svc, stage, args, binding)
        if retained_plan != plan or retained_raw != raw:
            fail_forward("RETAINED_BYTES_REFUSED")
        owner._sync_directory(svc, stage)
        attempted = True
        owner._rename_new(svc, stage, target)
    except BaseException:
        # Preserve failed preparation for inspection. A partial staging name
        # never becomes the active transaction or holds the incumbent start.
        if attempted and not owner._same_identity(stage, identity):
            fail_forward("EFFECT_UNKNOWN_PREPARATION_RECONCILE_SAME_OWNER")
        raise


def confirm_forward_durability(svc, roots, target):
    """Visible bytes alone cannot acknowledge a lost file or directory sync."""
    owner = svc._fleet_status_successor_owner_module()
    try:
        paths = [target / name for name in sorted(FORWARD_FILES)
                 if name != "result.json" or os.path.lexists(target / name)]
        paths.extend((roots["config"], roots["manifest"]))
        for path in paths:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                        or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)):
                    fail_forward("FOREIGN_MODE")
                os.fsync(fd)
                after = os.fstat(fd)
                current = path.lstat()
                fields = lambda x: (x.st_dev, x.st_ino, x.st_uid, x.st_mode,
                                    x.st_size, x.st_mtime_ns, x.st_ctime_ns, x.st_nlink)
                if fields(before) != fields(after) or fields(after) != fields(current):
                    fail_forward("RETAINED_BYTES_REFUSED")
            finally:
                os.close(fd)
        for path in dict.fromkeys((target, target.parent, roots["base"],
                                   roots["config"].parent, roots["manifest"].parent)):
            owner._sync_directory(svc, path)
    except BaseException:
        fail_forward("EFFECT_UNKNOWN_DURABILITY_RECONCILE_SAME_OWNER")
