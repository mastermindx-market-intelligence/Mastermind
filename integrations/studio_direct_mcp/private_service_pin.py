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
from types import SimpleNamespace
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
    fail("FOREIGN_STATE")


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


def require_start(svc, account, roots):
    """Only an OWNED future-pin transition adds a startup fence."""
    if os.path.lexists(roots["state"] / "native-pool-pin-publisher"):
        publisher_require_start(svc, account, roots)
        return
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


# A single exact native-pin-owner successor; NOT generic Studio restaging.
# Its original pin plan/result remain sealed and immutable. A sibling durable
# intent captures the two reviewed publisher files and manifest-last change.
PUBLISHER_SCHEMA = "mastermind.studio_native_pin_publisher.v1"
PUBLISHER_ACCOUNT = "chatgpt2-business"
PUBLISHER_BEFORE_MANIFEST = "9f2f1cdecdd99b1673181b0109d8e6b11896d95541ad42d5e087fb64c2646d3b"
PUBLISHER_FILES = ("git-publish.mjs", "workspace-access.mjs")
PUBLISHER_TX_FILES = frozenset({
    "plan.json", "intent.json", "result.json", "manifest.before.json",
    "manifest.after.json", *(name + "." + side + ".mjs"
        for name in ("git-publish", "workspace-access")
        for side in ("before", "after")),
})


def publisher_fail(code):
    raise SystemExit("NATIVE_POOL_PUBLISHER_" + code)


def publisher_plan_sha(svc, plan):
    return digest(svc._fabric_release_json(plan))


def publisher_record(svc, args, plan, phase, *, result=False):
    return {
        "schema": PUBLISHER_SCHEMA,
        "account": PUBLISHER_ACCOUNT,
        "planSha256": publisher_plan_sha(svc, plan),
        "originalPinPlanSha256": plan["original_pin_plan"],
        "effect": "APPLIED" if result else "NOT_APPLIED" if phase == "OLD"
                  else "PARTIAL" if phase == "PARTIAL" else "EFFECT_UNKNOWN",
        "phase": phase,
        "manifestBefore": plan["manifest_before"],
        "manifestAfter": plan["manifest_after"],
        "resultCommitted": result,
        "serviceStarted": False,
        "configChanged": False,
        "poolChanged": False,
    }


@contextmanager
def publisher_original_pin(svc, roots, *, write):
    """Authenticate the prior completed, selected native owner, not just hashes."""
    path = roots["state"] / "native-pool-pin"
    try:
        directory(svc, path)
        p = decode(svc._fabric_release_bytes(path / "plan.json"))
        if p.get("schema") != SCHEMA or p.get("account") != PUBLISHER_ACCOUNT:
            publisher_fail("ORIGINAL_PIN_UNQUALIFIED")
        a = SimpleNamespace(
            account=PUBLISHER_ACCOUNT,
            expected_manifest_sha256=p["manifest_before"],
            successor_bundle=p["successor_bundle"],
            successor_plan_sha256=p["successor_digest"],
            expected_plan_sha256=plan_sha(svc, p),
            operation="publisher-apply" if write else "status",
        )
        with svc._pin_native_context(a) as binding:
            oldplan, raw = read_transaction(svc, path, a, binding)
            result = decode(svc._fabric_release_bytes(path / "result.json"))
            if (result != {"schema": SCHEMA,
                           "planSha256": plan_sha(svc, oldplan),
                           "effect": "APPLIED"}
                    or binding.get("phase") != "SELECTED"
                    or svc._stable_regular_file_hash(
                        Path(oldplan["pool_target"]), label="original native pool"
                    ) != oldplan["pool_bridge"]):
                publisher_fail("ORIGINAL_PIN_UNQUALIFIED")
            if (digest(svc._fabric_release_bytes(roots["config"]))
                    != oldplan["config_after"]):
                publisher_fail("CONFIG_CHANGED")
            yield oldplan, raw, digest(svc._fabric_release_bytes(path / "result.json"))
    except (KeyError, ValueError, TypeError, OSError, RecursionError):
        publisher_fail("ORIGINAL_PIN_UNQUALIFIED")


def publisher_seal(svc, roots, original_raw, expected):
    """Inspect every non-publisher byte, including native pool and private runtime."""
    original = decode(original_raw["manifest.after.json"])
    if (digest(svc._fabric_release_bytes(roots["config"])) != original["configHash"]
            or digest(svc._fabric_release_bytes(roots["plist"])) != original["plistHash"]
            or svc._stable_regular_file_hash(
                Path(original["node"]), label="publisher node"
            ) != original["nodeHash"]
            or svc._stable_regular_file_hash(
                Path(original["backend"]), label="publisher backend"
            ) != original["backendHash"]
            or svc._dependency_tree_hash(roots["node_modules"])
               != original["dependencyTreeHash"]):
        publisher_fail("STATIC_SEAL_REFUSED")
    if (not svc._native_pin_manifest_valid(
            expected, PUBLISHER_ACCOUNT,
            "com.mastermind.studio-direct-private." + PUBLISHER_ACCOUNT)
            or set(expected["files"]) != set(original["files"])):
        publisher_fail("MANIFEST_PROFILE_REFUSED")
    for name, wanted in original["files"].items():
        if name not in PUBLISHER_FILES and (
            digest(svc._fabric_release_bytes(roots["base"] / name)) != wanted
        ):
            publisher_fail("UNRELATED_FILE_CHANGED")


def publisher_candidate(svc, args, roots, oldplan, original_raw, prior_result):
    if (args.account != PUBLISHER_ACCOUNT
            or args.expected_manifest_sha256 != PUBLISHER_BEFORE_MANIFEST
            or not isinstance(args.source, str)
            or not Path(args.source).is_absolute()
            or Path(args.source).is_symlink()
            or not Path(args.source).is_dir()):
        publisher_fail("PROFILE_REFUSED")
    source = Path(args.source)
    original_bytes = original_raw["manifest.after.json"]
    if (digest(original_bytes) != PUBLISHER_BEFORE_MANIFEST
            or svc._fabric_release_bytes(roots["manifest"]) != original_bytes):
        publisher_fail("ORIGINAL_MANIFEST_CHANGED")
    prior = decode(original_bytes)
    if prior["files"] != svc.C2_NATIVE_PUBLISHER_FILES_PREIMAGE:
        publisher_fail("ORIGINAL_PROFILE_CHANGED")
    publisher_seal(svc, roots, original_raw, prior)
    new = copy.deepcopy(prior)
    raw = {"manifest.before.json": original_bytes}
    modes = {}
    for name in PUBLISHER_FILES:
        installed_path, source_path = roots["base"] / name, source / name
        before = svc._fabric_release_bytes(installed_path)
        after = svc._fabric_release_bytes(source_path)
        if (digest(before) != svc.FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256[name]
                or digest(after) != svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256[name]
                or svc._stable_regular_file_hash(source_path, label="reviewed publisher source")
                   != digest(after)):
            publisher_fail("MODULE_SOURCE_REFUSED")
        stem = name.removesuffix(".mjs")
        raw[stem + ".before.mjs"], raw[stem + ".after.mjs"] = before, after
        modes[name] = stat.S_IMODE(installed_path.lstat().st_mode)
        new["files"][name] = digest(after)
    if new["files"] != svc.C2_NATIVE_PUBLISHER_FILES_POSTIMAGE:
        publisher_fail("TARGET_PROFILE_REFUSED")
    publisher_seal(svc, roots, original_raw, prior)
    new_bytes = svc._fabric_release_json(new)
    raw["manifest.after.json"] = new_bytes
    plan = {
        "schema": PUBLISHER_SCHEMA,
        "account": PUBLISHER_ACCOUNT,
        "uid": os.getuid(),
        "source": str(source),
        "original_pin_plan": plan_sha(svc, oldplan),
        "original_pin_result": prior_result,
        "manifest_before": digest(original_bytes),
        "manifest_after": digest(new_bytes),
        "module_before": {
            n: svc.FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256[n]
            for n in PUBLISHER_FILES
        },
        "module_after": {
            n: svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256[n]
            for n in PUBLISHER_FILES
        },
        "module_mode": modes,
        "manifest_mode": stat.S_IMODE(roots["manifest"].lstat().st_mode),
    }
    return plan, raw


def publisher_transaction(svc, args, roots, oldplan, original_raw, prior_result):
    path = roots["state"] / "native-pool-pin-publisher"
    directory(svc, path)
    if {p.name for p in path.iterdir()} - PUBLISHER_TX_FILES:
        publisher_fail("FOREIGN_TRANSACTION")
    plan = decode(svc._fabric_release_bytes(path / "plan.json"))
    if (set(plan) != {"schema", "account", "uid", "source",
                      "original_pin_plan", "original_pin_result",
                      "manifest_before", "manifest_after", "module_before",
                      "module_after", "module_mode", "manifest_mode"}
            or plan["schema"] != PUBLISHER_SCHEMA
            or plan["account"] != PUBLISHER_ACCOUNT
            or plan["uid"] != os.getuid()
            or plan["original_pin_plan"] != plan_sha(svc, oldplan)
            or plan["original_pin_result"] != prior_result
            or plan["manifest_before"] != PUBLISHER_BEFORE_MANIFEST
            or plan["module_before"] != svc.FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256
            or plan["module_after"] != svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256
            or not isinstance(plan["source"], str)
            or not Path(plan["source"]).is_absolute()
            or plan["source"] != str(Path(args.source))
            or plan["manifest_mode"] not in (0o400, 0o600, 0o644)):
        publisher_fail("PLAN_REFUSED")
    wanted = publisher_plan_sha(svc, plan)
    if wanted != args.expected_plan_sha256:
        publisher_fail("PLAN_CAS_REFUSED")
    raw = {}
    for name in PUBLISHER_TX_FILES - {"plan.json", "intent.json", "result.json"}:
        raw[name] = svc._fabric_release_bytes(path / name)
    if (digest(raw["manifest.before.json"]) != plan["manifest_before"]
            or digest(raw["manifest.after.json"]) != plan["manifest_after"]
            or raw["manifest.before.json"] != original_raw["manifest.after.json"]):
        publisher_fail("MANIFEST_BYTES_REFUSED")
    before = decode(raw["manifest.before.json"])
    after = decode(raw["manifest.after.json"])
    expected = copy.deepcopy(before)
    expected["files"].update(plan["module_after"])
    if (after != expected
            or expected["files"] != svc.C2_NATIVE_PUBLISHER_FILES_POSTIMAGE):
        publisher_fail("PROFILE_BYTES_REFUSED")
    for name in PUBLISHER_FILES:
        stem = name.removesuffix(".mjs")
        if (digest(raw[stem + ".before.mjs"]) != plan["module_before"][name]
                or digest(raw[stem + ".after.mjs"]) != plan["module_after"][name]
                or type(plan["module_mode"].get(name)) is not int
                or plan["module_mode"][name] not in (0o400, 0o600, 0o644)):
            publisher_fail("MODULE_BYTES_REFUSED")
    if decode(svc._fabric_release_bytes(path / "intent.json")) != {
        "schema": PUBLISHER_SCHEMA, "planSha256": wanted,
    }:
        publisher_fail("INTENT_REFUSED")
    return path, plan, raw


def publisher_phase(svc, roots, original_raw, plan, raw):
    before, after = (
        decode(raw["manifest.before.json"]),
        decode(raw["manifest.after.json"]),
    )
    publisher_seal(svc, roots, original_raw, after)
    if stat.S_IMODE(roots["manifest"].lstat().st_mode) != plan["manifest_mode"]:
        publisher_fail("FOREIGN_MODE")
    stages = []
    for name in PUBLISHER_FILES:
        stem = name.removesuffix(".mjs")
        path = roots["base"] / name
        if stat.S_IMODE(path.lstat().st_mode) != plan["module_mode"][name]:
            publisher_fail("FOREIGN_MODE")
        contents = svc._fabric_release_bytes(path)
        if contents == raw[stem + ".before.mjs"]:
            stages.append(False)
        elif contents == raw[stem + ".after.mjs"]:
            stages.append(True)
        else:
            publisher_fail("FOREIGN_MODULE")
    manifest = svc._fabric_release_bytes(roots["manifest"])
    if manifest == raw["manifest.after.json"] and all(stages):
        return "COMPLETE"
    if manifest == raw["manifest.before.json"]:
        return "OLD" if not any(stages) else "PARTIAL"
    publisher_fail("FOREIGN_MANIFEST")


def publisher_result(svc, path, plan):
    receipt = path / "result.json"
    if not os.path.lexists(receipt):
        return False
    observed = decode(svc._fabric_release_bytes(receipt))
    if observed != {
        "schema": PUBLISHER_SCHEMA,
        "planSha256": publisher_plan_sha(svc, plan),
        "effect": "APPLIED",
    }:
        publisher_fail("RESULT_REFUSED")
    return True


def run_publisher(svc, args):
    if args.account != PUBLISHER_ACCOUNT:
        publisher_fail("ACCOUNT_REFUSED")
    if (args.expected_manifest_sha256 != PUBLISHER_BEFORE_MANIFEST
            or (args.operation != "preview" and
                not svc._sha256_hex(args.expected_plan_sha256))):
        publisher_fail("INPUT_REFUSED")
    roots = svc._build_runtime_roots(PUBLISHER_ACCOUNT)
    path = roots["state"] / "native-pool-pin-publisher"
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(PUBLISHER_ACCOUNT) if modifying else nullcontext()
    with lock, publisher_original_pin(svc, roots, write=modifying) as original:
        oldplan, original_raw, prior_result = original
        if args.operation == "preview":
            if os.path.lexists(path):
                publisher_fail("TRANSACTION_EXISTS")
            plan, _ = publisher_candidate(
                svc, args, roots, oldplan, original_raw, prior_result
            )
            return publisher_record(svc, args, plan, "OLD") | {
                "effect": "NOT_APPLIED", "preflight": True
            }
        if args.operation == "apply" and os.path.lexists(path):
            publisher_fail("RECONCILIATION_REQUIRED")
        if args.operation == "apply":
            from_native = publisher_candidate(
                svc, args, roots, oldplan, original_raw, prior_result
            )
            plan, raw = from_native
            if publisher_plan_sha(svc, plan) != args.expected_plan_sha256:
                publisher_fail("PLAN_CAS_REFUSED")
            stopped(svc, PUBLISHER_ACCOUNT, roots)
            directory(svc, roots["state"])
            path.mkdir(mode=svc.DIR_MODE)
            svc._fsync_dir(path.parent)
            try:
                svc._fabric_release_new(path / "plan.json", svc._fabric_release_json(plan))
                for name, contents in raw.items():
                    svc._fabric_release_new(path / name, contents)
                svc._fabric_release_new(path / "intent.json", svc._fabric_release_json({
                    "schema": PUBLISHER_SCHEMA, "planSha256": args.expected_plan_sha256,
                }))
            except BaseException:
                publisher_fail("INTENT_EFFECT_UNKNOWN")
        tx, plan, raw = publisher_transaction(
            svc, args, roots, oldplan, original_raw, prior_result
        )
        phase = publisher_phase(svc, roots, original_raw, plan, raw)
        complete = publisher_result(svc, tx, plan)
        if complete and phase != "COMPLETE":
            publisher_fail("RESULT_STATE_REFUSED")
        if args.operation == "status":
            return publisher_record(
                svc, args, plan, phase, result=complete
            )
        stopped(svc, PUBLISHER_ACCOUNT, roots)
        if complete:
            # A completed transaction cannot be replayed or rewritten.
            publisher_fail("ALREADY_COMMITTED")
        try:
            if phase == "OLD" or phase == "PARTIAL":
                for name in PUBLISHER_FILES:
                    stem = name.removesuffix(".mjs")
                    path_name = roots["base"] / name
                    if svc._fabric_release_bytes(path_name) != raw[stem + ".after.mjs"]:
                        svc._atomic_write_bytes(
                            path_name, raw[stem + ".after.mjs"],
                            mode=plan["module_mode"][name],
                        )
                phase = publisher_phase(svc, roots, original_raw, plan, raw)
                if phase != "PARTIAL":
                    publisher_fail("PARTIAL_STATE_REFUSED")
                stopped(svc, PUBLISHER_ACCOUNT, roots)
                svc._atomic_write_bytes(
                    roots["manifest"], raw["manifest.after.json"],
                    mode=plan["manifest_mode"],
                )
            if publisher_phase(svc, roots, original_raw, plan, raw) != "COMPLETE":
                publisher_fail("FINAL_STATE_REFUSED")
            stopped(svc, PUBLISHER_ACCOUNT, roots)
            svc._fabric_release_new(tx / "result.json", svc._fabric_release_json({
                "schema": PUBLISHER_SCHEMA,
                "planSha256": publisher_plan_sha(svc, plan),
                "effect": "APPLIED",
            }))
            if publisher_phase(svc, roots, original_raw, plan, raw) != "COMPLETE":
                publisher_fail("FINAL_STATE_REFUSED")
        except BaseException:
            # Nothing is rolled back or retried; the original retained transaction
            # is the only lawful reconciliation carrier.
            publisher_fail("EFFECT_UNKNOWN")
        return publisher_record(svc, args, plan, "COMPLETE", result=True)


def publisher_require_start(svc, account, roots):
    """A completed chained publisher receipt is required before startup."""
    if account != PUBLISHER_ACCOUNT:
        publisher_fail("ACCOUNT_REFUSED")
    path = roots["state"] / "native-pool-pin-publisher"
    plan = decode(svc._fabric_release_bytes(path / "plan.json"))
    a = SimpleNamespace(
        account=account,
        expected_manifest_sha256=PUBLISHER_BEFORE_MANIFEST,
        expected_plan_sha256=publisher_plan_sha(svc, plan),
        source=plan.get("source"),
        operation="status",
    )
    with publisher_original_pin(svc, roots, write=False) as original:
        oldplan, raw_old, oldresult = original
        tx, checked, raw = publisher_transaction(
            svc, a, roots, oldplan, raw_old, oldresult
        )
        if (publisher_phase(svc, roots, raw_old, checked, raw) != "COMPLETE"
                or not publisher_result(svc, tx, checked)):
            publisher_fail("START_INCOMPLETE")
