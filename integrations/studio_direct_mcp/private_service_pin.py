"""One sealed-seat native-pool pin transition; called only by private_service.

No lifecycle control, pool selection, admission, provider access or enrollment.
The existing seat lifecycle and native publication locks serialize cooperative
owners; private directories do not claim atomic CAS against an adversarial UID.
"""

from contextlib import nullcontext
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat

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
    if not svc._valid_manifest(m, args.account, label):
        fail("PROFILE_REFUSED")
    svc._verify_staged_install(args.account, label, roots)
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
    if not svc._valid_manifest(m_post, args.account, label):
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
        or not svc._valid_manifest(old, args.account, label)
        or not svc._valid_manifest(new, args.account, label)
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
    fail("FOREIGN_STATE")


def static_seal(svc, args, roots, raw, current):
    """Qualify the intentional manifest-last gap without accepting other drift."""
    before = decode(raw["manifest.before.json"])
    if current != "CONFIG_ONLY":
        svc._verify_staged_install(
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
    args = type(
        "PinStartInputs",
        (),
        {
            "account": account,
            "expected_manifest_sha256": p["manifest_before"],
            "successor_bundle": p["successor_bundle"],
            "successor_plan_sha256": p["successor_digest"],
            "expected_plan_sha256": plan_sha(svc, p),
            "operation": "status",
        },
    )()
    with svc._pin_native_context(args) as binding:
        plan, raw = read_transaction(svc, path, args, binding)
        result = decode(svc._fabric_release_bytes(path / "result.json"))
        if (
            result
            != {"schema": SCHEMA, "planSha256": plan_sha(svc, p), "effect": "APPLIED"}
            or state(svc, roots, raw, plan) != "COMPLETE"
            or binding.get("phase") != "SELECTED"
            or svc._stable_regular_file_hash(
                Path(p["pool_target"]), label="native pool"
            )
            != p["pool_bridge"]
        ):
            fail("FUTURE_PIN_NOT_READY")
