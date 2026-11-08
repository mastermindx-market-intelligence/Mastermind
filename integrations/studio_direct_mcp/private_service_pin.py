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
import shutil
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
        "PREPARATION_EFFECT_UNKNOWN",
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


def fail(code):
    raise SystemExit("NATIVE_POOL_PIN_" + code)


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
    if not os.path.lexists(path):
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


# C2 Personal: one source-sealed publisher successor of an already completed
# native-pool pin AND an already completed fleet-status successor.
# This is part of the incumbent pin/installer owner, not another Git publisher.
PUBLISHER_ACCOUNT = "chatgpt2-personal"
PUBLISHER_SCHEMA = "mastermind.studio_native_pin_publisher_successor.v1"
PUBLISHER_TRANSACTION = "native-pool-pin-publisher"
PUBLISHER_FILES = ("git-publish.mjs", "workspace-access.mjs")
PUBLISHER_PREDECESSOR = {
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
# Freeze this exact reviewed successor generation. Never derive its identity
# from a future global fleet target that could change after installation.
PUBLISHER_SUCCESSOR = {
    "git-publish.mjs": "abc3b4dc6f3c9574ebb116e28a44f42136f8d8df3f2b0ec1504668daaf46b6bc",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}
PUBLISHER_JOURNAL_FILES = frozenset({
    "plan.json", "intent.json", "manifest.before", "manifest.after",
    "git-publish.mjs.before", "git-publish.mjs.after",
    "workspace-access.mjs.before", "workspace-access.mjs.after", "result.json",
})
PUBLISHER_PHASES = ("OLD", "PUBLISHER_ONLY", "MODULES_ONLY", "COMMITTED")


def _publisher_status_owner(svc, account, roots):
    """Authenticate the existing status successor and original selected pin."""
    if account != PUBLISHER_ACCOUNT:
        fail("ACCOUNT_REFUSED")
    owner = svc._fleet_status_successor_owner_module()
    path = roots["state"] / owner.TRANSACTION
    if not os.path.lexists(path):
        fail("RETAINED_PLAN_REFUSED")
    plan, raw, plan_digest = owner._retained(svc, account, roots, path)
    if (not os.path.lexists(path / "result.json")
            or owner.json.loads(svc._fabric_release_bytes(path / "result.json"))
            != {"schema": owner.SCHEMA, "planSha256": plan_digest,
                "effect": "APPLIED"}):
        fail("RESULT_REFUSED")
    return owner, plan, raw, plan_digest


def _publisher_inputs(svc, account, roots, source, expected_manifest):
    owner, status_plan, status_raw, status_digest = _publisher_status_owner(
        svc, account, roots)
    if (type(expected_manifest) is not str
            or expected_manifest != status_plan["manifestAfterSha256"]):
        fail("MANIFEST_CAS_REFUSED")
    # The old status owner validates the complete installed state, original pin,
    # sealed runtime and selected pool before any new transaction is prepared.
    if not owner.require_start(svc, account, roots):
        fail("RETAINED_PLAN_REFUSED")
    before = svc._fabric_release_bytes(roots["manifest"])
    if before != status_raw["manifest.after"]:
        fail("MANIFEST_CAS_REFUSED")
    old = decode(before)
    if (old.get("configHash") != status_plan["configSha256"]
            or any(old.get("files", {}).get(k) != v
                   for k, v in PUBLISHER_PREDECESSOR.items())):
        fail("RETAINED_BYTES_REFUSED")
    source = Path(source)
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        fail("INPUT_REFUSED")
    blobs = {}
    module_modes = {}
    for name in PUBLISHER_FILES:
        installed = roots["base"] / name
        info = installed.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)):
            fail("FOREIGN_MODE")
        module_modes[name] = stat.S_IMODE(info.st_mode)
        src = source / name
        if src.is_symlink() or not src.is_file():
            fail("RETAINED_BYTES_REFUSED")
        incoming = src.read_bytes()
        current = svc._fabric_release_bytes(roots["base"] / name)
        if (digest(incoming) != PUBLISHER_SUCCESSOR[name]
                or digest(current) != PUBLISHER_PREDECESSOR[name]):
            fail("RETAINED_TARGET_REFUSED")
        blobs[name + ".before"] = current
        blobs[name + ".after"] = incoming
    new = copy.deepcopy(old)
    for name in PUBLISHER_FILES:
        new["files"][name] = PUBLISHER_SUCCESSOR[name]
    after = svc._fabric_release_json(new)
    if not svc._native_pin_manifest_valid(
            new, account, "com.mastermind.studio-direct-private." + account):
        fail("POST_PROFILE_REFUSED")
    plan = {
        "schema": PUBLISHER_SCHEMA, "account": account, "uid": os.getuid(),
        "statusPlanSha256": status_digest,
        "manifestBeforeSha256": digest(before),
        "manifestAfterSha256": digest(after),
        "configSha256": status_plan["configSha256"],
        "mode": stat.S_IMODE(roots["manifest"].lstat().st_mode),
        "moduleModes": module_modes,
        "target": dict(PUBLISHER_SUCCESSOR),
        "predecessor": dict(PUBLISHER_PREDECESSOR),
    }
    blobs.update({"manifest.before": before, "manifest.after": after})
    return plan, blobs


def _publisher_read(svc, roots, *, staged=None):
    target = staged if staged is not None else roots["state"] / PUBLISHER_TRANSACTION
    directory(svc, target)
    names = {p.name for p in target.iterdir()}
    if names - PUBLISHER_JOURNAL_FILES or PUBLISHER_JOURNAL_FILES - {"result.json"} - names:
        fail("FOREIGN_TRANSACTION")
    plan = decode(svc._fabric_release_bytes(target / "plan.json"))
    required = {"schema", "account", "uid", "statusPlanSha256",
                "manifestBeforeSha256", "manifestAfterSha256",
                "configSha256", "mode", "moduleModes", "target", "predecessor"}
    if (set(plan) != required or plan["schema"] != PUBLISHER_SCHEMA
            or plan["account"] != PUBLISHER_ACCOUNT or plan["uid"] != os.getuid()
            or plan["target"] != PUBLISHER_SUCCESSOR
            or plan["predecessor"] != PUBLISHER_PREDECESSOR
            or plan["mode"] not in (0o400, 0o600)
            or set(plan["moduleModes"]) != set(PUBLISHER_FILES)
            or any(x not in (0o400, 0o600) for x in plan["moduleModes"].values())):
        fail("RETAINED_PLAN_REFUSED")
    digest_plan = digest(svc._fabric_release_json(plan))
    intent = decode(svc._fabric_release_bytes(target / "intent.json"))
    if intent != {"schema": PUBLISHER_SCHEMA, "planSha256": digest_plan}:
        fail("INTENT_REFUSED")
    blobs = {}
    for name in ("manifest", *PUBLISHER_FILES):
        for side in ("before", "after"):
            key = name + "." + side
            blobs[key] = svc._fabric_release_bytes(target / key)
            expected = (plan["manifestBeforeSha256"] if side == "before" else
                        plan["manifestAfterSha256"]) if name == "manifest" else (
                        PUBLISHER_PREDECESSOR[name] if side == "before" else
                        PUBLISHER_SUCCESSOR[name])
            if digest(blobs[key]) != expected:
                fail("RETAINED_BYTES_REFUSED")
    original, after = decode(blobs["manifest.before"]), decode(blobs["manifest.after"])
    projected = copy.deepcopy(original)
    if (original.get("configHash") != plan["configSha256"]
            or any(original.get("files", {}).get(n) != PUBLISHER_PREDECESSOR[n]
                   for n in PUBLISHER_FILES)):
        fail("RETAINED_PLAN_REFUSED")
    for name in PUBLISHER_FILES:
        projected["files"][name] = PUBLISHER_SUCCESSOR[name]
    if after != projected:
        fail("RETAINED_BYTES_REFUSED")
    return plan, blobs, digest_plan


def _publisher_prepare_intent(svc, roots, plan, blobs):
    """Publish one complete, checked journal using the incumbent exclusive rename.

    A crash while writing the private staging directory cannot leave a partial
    active transaction. A lost callback after atomic publication is EFFECT_UNKNOWN
    and can only be reconciled by the same retained plan; no second apply.
    """
    owner = svc._fleet_status_successor_owner_module()
    target = roots["state"] / PUBLISHER_TRANSACTION
    stage = Path(tempfile.mkdtemp(
        prefix=".native-pin-publisher-intent.", dir=target.parent))
    identity = owner._identity(stage)
    attempted = False
    try:
        svc._fabric_release_new(
            stage / "plan.json", svc._fabric_release_json(plan))
        for name, data in blobs.items():
            svc._fabric_release_new(stage / name, data)
        svc._fabric_release_new(
            stage / "intent.json", svc._fabric_release_json({
                "schema": PUBLISHER_SCHEMA,
                "planSha256": digest(svc._fabric_release_json(plan)),
            }))
        checked, retained, pd = _publisher_read(svc, roots, staged=stage)
        if (checked != plan or retained != blobs
                or pd != digest(svc._fabric_release_json(plan))):
            fail("RETAINED_BYTES_REFUSED")
        owner._sync_directory(svc, stage)
        attempted = True
        owner._rename_new(svc, stage, target)
    except BaseException:
        if attempted and not owner._same_identity(stage, identity):
            fail("PREPARATION_EFFECT_UNKNOWN")
        raise
    finally:
        if owner._same_identity(stage, identity):
            shutil.rmtree(stage)


def _publisher_phase(svc, roots, plan, blobs):
    if (stat.S_IMODE(roots["manifest"].lstat().st_mode) != plan["mode"]
            or digest(svc._fabric_release_bytes(roots["config"])) != plan["configSha256"]):
        fail("FOREIGN_MODE")
    for name in PUBLISHER_FILES:
        info = (roots["base"] / name).lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != plan["moduleModes"][name]):
            fail("FOREIGN_MODE")
    actual = tuple(svc._fabric_release_bytes(roots["base"] / n)
                   for n in PUBLISHER_FILES)
    before = tuple(blobs[n + ".before"] for n in PUBLISHER_FILES)
    after = tuple(blobs[n + ".after"] for n in PUBLISHER_FILES)
    manifest = svc._fabric_release_bytes(roots["manifest"])
    states = {
        (before, blobs["manifest.before"]): "OLD",
        ((after[0], before[1]), blobs["manifest.before"]): "PUBLISHER_ONLY",
        (after, blobs["manifest.before"]): "MODULES_ONLY",
        (after, blobs["manifest.after"]): "COMMITTED",
    }
    state = states.get((actual, manifest))
    if state is None:
        fail("FOREIGN_STATE")
    base = decode(blobs["manifest.before"])
    for name, expected in base["files"].items():
        if name not in PUBLISHER_FILES:
            if digest(svc._fabric_release_bytes(roots["base"] / name)) != expected:
                fail("RETAINED_BYTES_REFUSED")
    if svc._stable_regular_file_hash(Path(base["node"]), label="native publisher node") != base["nodeHash"]:
        fail("RETAINED_BYTES_REFUSED")
    if svc._stable_regular_file_hash(Path(base["backend"]), label="native publisher backend") != base["backendHash"]:
        fail("RETAINED_BYTES_REFUSED")
    if (digest(svc._fabric_release_bytes(roots["plist"])) != base["plistHash"]
            or svc._dependency_tree_hash(roots["node_modules"]) != base["dependencyTreeHash"]):
        fail("RETAINED_BYTES_REFUSED")
    return state


def publisher_postimage(svc, account, roots, status_plan, status_raw, observed_manifest):
    """Read-only postimage recognition for the *existing* fleet-status owner."""
    if account != PUBLISHER_ACCOUNT:
        return False
    target = roots["state"] / PUBLISHER_TRANSACTION
    if not os.path.lexists(target):
        return False
    plan, blobs, pd = _publisher_read(svc, roots)
    if (plan["statusPlanSha256"] != digest(svc._fabric_release_json(status_plan))
            or blobs["manifest.before"] != status_raw["manifest.after"]
            or blobs["manifest.after"] != observed_manifest):
        fail("RETAINED_PLAN_REFUSED")
    if _publisher_phase(svc, roots, plan, blobs) != "COMMITTED":
        fail("FOREIGN_STATE")
    result = decode(svc._fabric_release_bytes(target / "result.json"))
    if result != {"schema": PUBLISHER_SCHEMA, "planSha256": pd, "effect": "APPLIED"}:
        fail("RESULT_REFUSED")
    return True


def _publisher_record(plan, state, *, committed=False):
    return {"schema": PUBLISHER_SCHEMA, "account": PUBLISHER_ACCOUNT,
            "planSha256": digest(json.dumps(plan, indent=2, sort_keys=True).encode("utf-8")),
            "effect": "APPLIED" if committed else ("NOT_APPLIED" if state in ("PREVIEW", "OLD") else "PARTIAL"),
            "phase": state, "retainedOriginalNativePin": True,
            "retainedFleetStatusSuccessor": True, "serviceStarted": False,
            "receiptCommitted": committed, "retryAllowed": False}


def run_publisher(svc, args):
    """One native-pin-owner transaction; never calls git push or starts a service."""
    if args.account != PUBLISHER_ACCOUNT or args.operation not in (
            "preview", "apply", "status", "reconcile"):
        fail("ACCOUNT_REFUSED")
    if not svc._sha256_hex(args.expected_manifest_sha256):
        fail("INPUT_REFUSED")
    roots = svc._build_runtime_roots(args.account)
    target = roots["state"] / PUBLISHER_TRANSACTION
    readonly = args.operation in ("preview", "status")
    lock = nullcontext() if readonly else svc._c2_lifecycle_mutex(args.account)
    publication = (nullcontext() if readonly else
                   svc._native_selected_publication_lock_for_publisher(args.account))
    with lock, publication:
        if args.operation == "preview":
            if os.path.lexists(target):
                fail("TRANSACTION_EXISTS")
            plan, blobs = _publisher_inputs(
                svc, args.account, roots, args.source, args.expected_manifest_sha256)
            return _publisher_record(plan, "PREVIEW")
        if args.operation == "apply" and not os.path.lexists(target):
            # Nothing is written while the installed gateway can still execute.
            stopped(svc, args.account, roots)
            plan, blobs = _publisher_inputs(
                svc, args.account, roots, args.source, args.expected_manifest_sha256)
            pd = digest(svc._fabric_release_json(plan))
            if args.expected_plan_sha256 != pd:
                fail("PLAN_CAS_REFUSED")
            svc._ensure_secure_dir(roots["state"])
            svc._assert_dest_safe(target)
            _publisher_prepare_intent(svc, roots, plan, blobs)
        elif args.operation == "apply":
            # A persisted original intent must be reconciled explicitly.
            # A second apply is not a replay channel after a lost callback.
            fail("RECONCILIATION_REQUIRED")
        if not os.path.lexists(target):
            fail("TRANSACTION_EXISTS")
        plan, blobs, pd = _publisher_read(svc, roots)
        owner, status_plan, status_raw, status_digest = _publisher_status_owner(
            svc, args.account, roots)
        if (plan["manifestBeforeSha256"] != args.expected_manifest_sha256
                or plan["statusPlanSha256"] != status_digest
                or blobs["manifest.before"] != status_raw["manifest.after"]
                or (args.operation in ("apply", "reconcile")
                    and args.expected_plan_sha256 != pd)):
            fail("PLAN_CAS_REFUSED")
        phase = _publisher_phase(svc, roots, plan, blobs)
        result = target / "result.json"
        committed = os.path.lexists(result)
        if committed:
            if (decode(svc._fabric_release_bytes(result)) !=
                    {"schema": PUBLISHER_SCHEMA, "planSha256": pd, "effect": "APPLIED"}
                    or phase != "COMMITTED"):
                fail("RESULT_REFUSED")
        if args.operation == "status":
            return _publisher_record(plan, phase, committed=committed)
        stopped(svc, args.account, roots)
        if committed:
            return _publisher_record(plan, phase, committed=True)
        if args.operation == "apply" and phase != "OLD":
            fail("RECONCILIATION_REQUIRED")
        for current, following, file, payload in (
            ("OLD", "PUBLISHER_ONLY", roots["base"] / PUBLISHER_FILES[0],
             blobs[PUBLISHER_FILES[0] + ".after"]),
            ("PUBLISHER_ONLY", "MODULES_ONLY", roots["base"] / PUBLISHER_FILES[1],
             blobs[PUBLISHER_FILES[1] + ".after"]),
            ("MODULES_ONLY", "COMMITTED", roots["manifest"],
             blobs["manifest.after"]),
        ):
            if phase != current:
                continue
            stopped(svc, args.account, roots)
            if _publisher_phase(svc, roots, plan, blobs) != current:
                fail("FOREIGN_STATE")
            svc._atomic_write_bytes(
                file, payload,
                mode=plan["mode"] if file == roots["manifest"] else
                     plan["moduleModes"][file.name])
            phase = _publisher_phase(svc, roots, plan, blobs)
            if phase != following:
                fail("FOREIGN_STATE")
        if phase != "COMMITTED":
            fail("FOREIGN_STATE")
        stopped(svc, args.account, roots)
        svc._fsync_dir(roots["base"])
        svc._fsync_dir(roots["manifest"].parent)
        svc._fabric_release_new(result, svc._fabric_release_json(
            {"schema": PUBLISHER_SCHEMA, "planSha256": pd, "effect": "APPLIED"}))
        svc._fsync_dir(target)
        return _publisher_record(plan, phase, committed=True)
