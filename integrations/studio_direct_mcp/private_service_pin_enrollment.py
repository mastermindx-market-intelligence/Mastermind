"""Exact C4 repository enrollment, owned by the existing private-service installer.

This extends the completed native-pool-pin chain; it never restages that chain,
controls service lifetime, publishes Git, selects a native generation, or grants
caller-selected repositories. Only the existing lifecycle and native publication
locks serialize this one manifest-last transaction. Same-UID hostile mutation is
not an atomic filesystem CAS; every observable foreign state refuses closed.
"""

from contextlib import contextmanager, nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

SCHEMA = "mastermind.studio_native_pin_enrollment.v1"
GENERATION = "c4-closed-repositories-20261103-v1"
ACCOUNT = "chatgpt4"
TRANSACTION = "native-pool-pin-enrollment"
BEFORE_MANIFEST = "168bb25afd7d710799fb86f8912389d49c86371c107ee9544d65fdc2b9d390e2"
BEFORE_CONFIG = "f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21"
ORIGINAL_PLAN = "4732de6c370ca3385d17749e411f634d149b7701971219baea65707d6c069818"
# Immutable generation, deliberately independent of all generic upgrade targets.
TARGET_FILES = {
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}
ORDER = ("gateway.mjs", "git-publish.mjs", "workspace-access.mjs", "config", "manifest")
PAYLOADS = tuple(
    name + "." + side
    for name in ORDER for side in ("before", "after")
    if (name, side) != ("workspace-access.mjs", "before")
)
FILES = frozenset((*PAYLOADS, "plan.json", "intent.json", "result.json"))
REFUSAL_CODES = frozenset((
    "INPUT_REFUSED", "PROFILE_REFUSED", "ORIGINAL_PIN_REFUSED", "SOURCE_REFUSED",
    "PLAN_REFUSED", "TRANSACTION_REFUSED", "RECONCILIATION_REQUIRED",
    "STATIC_SEAL_REFUSED", "FOREIGN_STATE", "RESULT_REFUSED", "START_REFUSED",
    "SERVICE_LOADED", "EFFECT_UNKNOWN", "OWNER_REFUSED",
))


def fail(code):
    raise SystemExit("NATIVE_PIN_ENROLLMENT_" + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    # Freeze this generation's representation independently of future installers.
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def target_config(home, before):
    """One fixed enrollment transformation; no future generic profile dependency."""
    common = {
        "enabled": True, "workspaceCli": str(home / ".local/bin/mmx-workspace"),
        "gitBinary": "/usr/bin/git", "commandTimeoutMs": 15000,
        "pushTimeoutMs": 60000,
    }
    profiles = (
        ("mastermind", "Documents/GitHub/Mastermind", "Mastermind"),
        ("macro", "Documents/Cluade/macro-main", "macro"),
        ("terminal", "Documents/Cluade/charting-app", "mastermind-terminal"),
    )
    remote = "https://github.com/mastermindx-market-intelligence/"
    original_git = dict(common, sourceRepository=str(home / profiles[0][1]),
                        allowedRemoteUrls=[remote + "Mastermind.git"])
    if (before.get("accountLabel") != ACCOUNT
            or before.get("gitPublish") != original_git
            or "repositoryWorkspaces" in before):
        fail("PROFILE_REFUSED")
    result = copy.deepcopy(before)
    # Measured owner status reached 24.256s under load. Use the already-reviewed
    # bounded C2 timeout policy, frozen here rather than a moving global value.
    # The original preimage remains exactly 15s and push keeps its 60s budget.
    common["commandTimeoutMs"] = 45000
    result["gitPublish"] = dict(common, repositories=[
        {"repository": alias, "sourceRepository": str(home / source),
         "allowedRemoteUrls": [remote + repository + ".git"]}
        for alias, source, repository in profiles
    ])
    result["repositoryWorkspaces"] = {
        "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
    return result


def destination(roots, name):
    return roots[name] if name in ("config", "manifest") else roots["base"] / name


def mode(path):
    info = path.lstat()
    value = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or value not in (0o400, 0o600)):
        fail("FOREIGN_STATE")
    return value


def pin_fingerprint(svc, pin, path):
    pin.directory(svc, path)
    if set(x.name for x in path.iterdir()) != set(pin.FILES):
        fail("ORIGINAL_PIN_REFUSED")
    return {name: digest(svc._fabric_release_bytes(path / name))
            for name in sorted(pin.FILES)}


@contextmanager
def original_pin(svc, roots, operation):
    """Authenticate retained proof with the actual existing native selection owner."""
    pin = svc._pin_owner_module()
    path = roots["state"] / "native-pool-pin"
    fingerprint = pin_fingerprint(svc, pin, path)
    p = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    if (fingerprint["plan.json"] != ORIGINAL_PLAN
            or p.get("schema") != pin.SCHEMA or p.get("account") != ACCOUNT
            or p.get("uid") != os.getuid()
            or p.get("manifest_after") != BEFORE_MANIFEST
            or p.get("config_after") != BEFORE_CONFIG):
        fail("ORIGINAL_PIN_REFUSED")
    args = SimpleNamespace(
        account=ACCOUNT, expected_manifest_sha256=p["manifest_before"],
        successor_bundle=p["successor_bundle"],
        successor_plan_sha256=p["successor_digest"],
        expected_plan_sha256=pin.plan_sha(svc, p),
        # The existing owner takes its publication lock for these exact verbs.
        operation=operation if operation in ("apply", "reconcile") else "status",
    )
    with svc._pin_native_context(args) as binding:
        prior, raw = pin.read_transaction(svc, path, args, binding)
        expected = {"schema": pin.SCHEMA, "planSha256": args.expected_plan_sha256,
                    "effect": "APPLIED"}
        if (pin.decode(svc._fabric_release_bytes(path / "result.json")) != expected
                or binding.get("phase") != "SELECTED"
                or svc._stable_regular_file_hash(Path(prior["pool_target"]),
                       label="original native pool") != prior["pool_bridge"]
                or pin_fingerprint(svc, pin, path) != fingerprint):
            fail("ORIGINAL_PIN_REFUSED")
        yield pin, raw, fingerprint
        if pin_fingerprint(svc, pin, path) != fingerprint:
            fail("ORIGINAL_PIN_REFUSED")


def projected(svc, pin, original):
    before_config = original["config.after.json"]
    before_manifest = original["manifest.after.json"]
    if digest(before_config) != BEFORE_CONFIG or digest(before_manifest) != BEFORE_MANIFEST:
        fail("PROFILE_REFUSED")
    after_config = encode(target_config(svc._user_root(), pin.decode(before_config)))
    manifest = pin.decode(before_manifest)
    if (manifest.get("account") != ACCOUNT or manifest.get("port") != 45024
            or manifest.get("host") != "127.0.0.1"
            or len(manifest.get("files", {})) != 11
            or "workspace-access.mjs" in manifest["files"]):
        fail("PROFILE_REFUSED")
    after = copy.deepcopy(manifest)
    after["configHash"] = digest(after_config)
    after["files"].update(TARGET_FILES)
    if not svc._native_pin_manifest_valid(after, ACCOUNT, after["label"]):
        fail("PROFILE_REFUSED")
    return {"config.before": before_config, "config.after": after_config,
            "manifest.before": before_manifest, "manifest.after": encode(after)}


def expected_plan(raw, modes, original_fingerprint):
    return {
        "schema": SCHEMA, "generation": GENERATION, "account": ACCOUNT,
        "uid": os.getuid(), "originalPin": original_fingerprint,
        "files": {name: {
            "before": digest(raw[name + ".before"]) if name + ".before" in raw else None,
            "after": digest(raw[name + ".after"]), "mode": modes[name],
        } for name in ORDER},
    }


def static_seal(svc, pin, roots, original):
    before = pin.decode(original["manifest.after.json"])
    for name, wanted in before["files"].items():
        if name not in TARGET_FILES and digest(svc._fabric_release_bytes(roots["base"] / name)) != wanted:
            fail("STATIC_SEAL_REFUSED")
    if (digest(svc._fabric_release_bytes(roots["plist"])) != before["plistHash"]
            or svc._stable_regular_file_hash(Path(before["node"]), label="enrollment node") != before["nodeHash"]
            or svc._stable_regular_file_hash(Path(before["backend"]), label="enrollment backend") != before["backendHash"]
            or svc._dependency_tree_hash(roots["node_modules"]) != before["dependencyTreeHash"]):
        fail("STATIC_SEAL_REFUSED")


def observe(svc, roots, plan, raw):
    """Only a prefix of the fixed manifest-last commit order is owned progress."""
    seen_old = False
    progress = 0
    for name in ORDER:
        path = destination(roots, name)
        if os.path.lexists(path):
            actual = svc._fabric_release_bytes(path)
            if mode(path) != plan["files"][name]["mode"]:
                fail("FOREIGN_STATE")
        else:
            actual = None
        before = raw.get(name + ".before")
        after = raw[name + ".after"]
        if actual == after:
            if seen_old:
                fail("FOREIGN_STATE")
            progress += 1
        elif actual == before:
            seen_old = True
        else:
            fail("FOREIGN_STATE")
    return progress


def candidate(svc, pin, args, roots, original, original_fingerprint):
    source = Path(args.source) if isinstance(args.source, str) else Path(".")
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        fail("SOURCE_REFUSED")
    # Reviewed payload staged beneath this owner's home, not an alternate runtime.
    try:
        source.relative_to(svc._user_root())
    except ValueError:
        fail("SOURCE_REFUSED")
    raw = projected(svc, pin, original)
    before = pin.decode(raw["manifest.before"])
    modes = {}
    for name in ORDER:
        path = destination(roots, name)
        if name == "workspace-access.mjs":
            if os.path.lexists(path):
                fail("FOREIGN_STATE")
            modes[name] = 0o600
        else:
            modes[name] = mode(path)
        if name in TARGET_FILES:
            raw[name + ".after"] = svc._fabric_release_bytes(source / name)
            if digest(raw[name + ".after"]) != TARGET_FILES[name]:
                fail("SOURCE_REFUSED")
            if name in before["files"]:
                raw[name + ".before"] = svc._fabric_release_bytes(path)
                if digest(raw[name + ".before"]) != before["files"][name]:
                    fail("FOREIGN_STATE")
    plan = expected_plan(raw, modes, original_fingerprint)
    if observe(svc, roots, plan, raw) != 0:
        fail("FOREIGN_STATE")
    static_seal(svc, pin, roots, original)
    return plan, raw


def retained(svc, pin, roots, path, expected_sha, original, original_fingerprint):
    pin.directory(svc, path)
    names = set(x.name for x in path.iterdir())
    if not FILES - {"result.json"} <= names or names - FILES:
        fail("TRANSACTION_REFUSED")
    plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    if digest(encode(plan)) != expected_sha:
        fail("PLAN_REFUSED")
    raw = {name: svc._fabric_release_bytes(path / name) for name in PAYLOADS}
    if any(raw[name] != data for name, data in projected(svc, pin, original).items()):
        fail("TRANSACTION_REFUSED")
    before = pin.decode(raw["manifest.before"])
    for name, wanted in TARGET_FILES.items():
        if digest(raw[name + ".after"]) != wanted:
            fail("TRANSACTION_REFUSED")
        if name in before["files"] and digest(raw[name + ".before"]) != before["files"][name]:
            fail("TRANSACTION_REFUSED")
    modes = {name: plan["files"][name]["mode"] for name in ORDER}
    if (any(type(value) is not int or value not in (0o400, 0o600) for value in modes.values())
            or modes["workspace-access.mjs"] != 0o600
            or plan != expected_plan(raw, modes, original_fingerprint)
            or pin.decode(svc._fabric_release_bytes(path / "intent.json"))
               != {"schema": SCHEMA, "planSha256": expected_sha}):
        fail("TRANSACTION_REFUSED")
    return plan, raw


def stopped(svc, roots):
    if svc._lifecycle_inspect(ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT,
                              roots, require_positive=True) is not None:
        fail("SERVICE_LOADED")


def result_record(plan):
    return {"schema": SCHEMA, "planSha256": digest(encode(plan)), "effect": "APPLIED"}


def report(plan, progress, committed):
    phase = "OLD" if progress == 0 else "COMPLETE" if progress == len(ORDER) else "PARTIAL"
    return {
        "schema": SCHEMA, "generation": GENERATION, "account": ACCOUNT,
        "planSha256": digest(encode(plan)), "phase": phase,
        "effect": "APPLIED" if committed else "NOT_APPLIED" if progress == 0
                  else "EFFECT_UNKNOWN" if progress == len(ORDER) else "PARTIAL",
        "completedWrites": progress, "resultCommitted": committed,
        "originalPinPreserved": True, "serviceStarted": False,
        "repositories": ["mastermind", "macro", "terminal"],
        "mergePublisherPrepared": True, "clientAdoptionProven": False,
        "retryAllowed": False,
    }


def run(svc, args):
    effect = {"started": False}
    try:
        return _run(svc, args, effect)
    except BaseException:
        # Includes preparation writes and the original-owner context's final
        # integrity check. Never report a pre-effect refusal after a write.
        if effect["started"]:
            fail("EFFECT_UNKNOWN")
        raise


def _run(svc, args, effect):
    if (args.account != ACCOUNT or args.operation not in ("preview", "apply", "status", "reconcile")
            or args.expected_manifest_sha256 != BEFORE_MANIFEST
            or (args.operation != "preview" and not svc._sha256_hex(args.expected_plan_sha256))):
        fail("INPUT_REFUSED")
    roots = svc._build_runtime_roots(ACCOUNT)
    path = roots["state"] / TRANSACTION
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(ACCOUNT) if modifying else nullcontext()
    with lock, original_pin(svc, roots, args.operation) as (pin, original, fingerprint):
        if args.operation in ("preview", "apply"):
            if os.path.lexists(path):
                fail("RECONCILIATION_REQUIRED")
            if modifying:
                stopped(svc, roots)
            plan, raw = candidate(svc, pin, args, roots, original, fingerprint)
            if args.operation == "preview":
                value = report(plan, 0, False)
                value["phase"] = "PREVIEW"
                return value
            if digest(encode(plan)) != args.expected_plan_sha256:
                fail("PLAN_REFUSED")
            # Persist complete intent before touching an installation byte. A
            # preparation interruption refuses closed; it never replays apply.
            pin.directory(svc, roots["state"])
            effect["started"] = True
            path.mkdir(mode=svc.DIR_MODE)
            svc._fsync_dir(path.parent)
            svc._fabric_release_new(path / "plan.json", encode(plan))
            for name, data in raw.items():
                svc._fabric_release_new(path / name, data)
            svc._fabric_release_new(path / "intent.json", encode({
                "schema": SCHEMA, "planSha256": args.expected_plan_sha256}))
        plan, raw = retained(svc, pin, roots, path, args.expected_plan_sha256, original, fingerprint)
        committed = os.path.lexists(path / "result.json")
        paper_v20_selected = False
        try:
            progress = observe(svc, roots, plan, raw)
        except SystemExit as exc:
            if (args.operation != "status" or not committed
                    or exc.code != "NATIVE_PIN_ENROLLMENT_FOREIGN_STATE"
                    or not _c4_paper_v20_post_enrollment(svc, roots, plan, raw)):
                raise
            progress = len(ORDER)
            paper_v20_selected = True
        static_seal(svc, pin, roots, original)
        if committed and (progress != len(ORDER)
                or pin.decode(svc._fabric_release_bytes(path / "result.json")) != result_record(plan)):
            fail("RESULT_REFUSED")
        if args.operation == "status":
            result = report(plan, progress, committed)
            if paper_v20_selected:
                result["paperV20Selected"] = True
            return result
        stopped(svc, roots)
        if committed:
            return report(plan, progress, True)
        changed = False
        try:
            for index in range(progress, len(ORDER)):
                stopped(svc, roots)
                static_seal(svc, pin, roots, original)
                if (observe(svc, roots, plan, raw) != index
                        or pin_fingerprint(svc, pin, roots["state"] / "native-pool-pin") != fingerprint):
                    fail("FOREIGN_STATE")
                name = ORDER[index]
                changed = True
                effect["started"] = True
                svc._atomic_write_bytes(destination(roots, name), raw[name + ".after"],
                                        mode=plan["files"][name]["mode"])
            if observe(svc, roots, plan, raw) != len(ORDER):
                fail("FOREIGN_STATE")
            static_seal(svc, pin, roots, original)
            stopped(svc, roots)
            if pin_fingerprint(svc, pin, roots["state"] / "native-pool-pin") != fingerprint:
                fail("ORIGINAL_PIN_REFUSED")
            changed = True
            effect["started"] = True
            svc._fabric_release_new(path / "result.json", encode(result_record(plan)))
            if pin.decode(svc._fabric_release_bytes(path / "result.json")) != result_record(plan):
                fail("RESULT_REFUSED")
        except BaseException:
            # A reported filesystem failure may follow an actual rename. Keep
            # the original transaction and observed bytes; never roll back/retry.
            if changed:
                fail("EFFECT_UNKNOWN")
            raise
        return report(plan, len(ORDER), True)


# One closed Paper v20 successor of the already completed C4 publisher
# enrollment. These are SHA-256s of exact source-projected bytes, not inputs.
# The enrollment owner remains the only startup attestor for that transaction.
C4_ENROLLED_CONFIG_SHA256 = "37680eb009b4199ffba209e0d88775b73e00a4ca0ca8f0785a22d33ec2d81d2b"
C4_ENROLLED_MANIFEST_SHA256 = "3648a9a8e9711bab7be9fc7a3950f73579ce7d78358a18c15ac7d39adf924a9f"
C4_PAPER_V20_CONFIG_SHA256 = "f06dc822015fc11f34d7e1142bdf1b016cb985af701ba929f33b313ff3a570df"
C4_PAPER_V20_MANIFEST_SHA256 = "06fd20cb3f50e0e7f909506e90773c80c228556eff8e7aba6bdb6085dcfc7de8"


def _c4_paper_v20_post_enrollment(svc, roots, plan, raw):
    """Read-only proof of exactly Paper-only v20 after completed enrollment.

    Called ONLY after retained original/second pin proofs, immutable enrollment
    plan, original selected pool and completed result are authenticated.
    """
    if (digest(raw["config.after"]) != C4_ENROLLED_CONFIG_SHA256
            or digest(raw["manifest.after"]) != C4_ENROLLED_MANIFEST_SHA256):
        return False
    # No module generation, publisher, adapter or file-mode drift is allowed.
    for name in ("gateway.mjs", "git-publish.mjs", "workspace-access.mjs"):
        target = destination(roots, name)
        if (mode(target) != plan["files"][name]["mode"]
                or svc._fabric_release_bytes(target) != raw[name + ".after"]):
            return False
    original = svc._pin_owner_module().decode(raw["config.after"])
    manifest = svc._pin_owner_module().decode(raw["manifest.after"])
    home = svc._user_root()
    if (original.get("paperDesign") != svc._paper_design_config(home)
            or manifest.get("configHash") != C4_ENROLLED_CONFIG_SHA256
            or manifest.get("account") != ACCOUNT):
        return False
    future = copy.deepcopy(original)
    future["paperDesign"] = svc._paper_design_config(
        home, rel=svc.PAPER_RUNTIME_V20_REL,
        bridge_sha256=svc.PAPER_V20_BRIDGE_SHA256)
    config = encode(future)
    expected_manifest = copy.deepcopy(manifest)
    expected_manifest["configHash"] = digest(config)
    manifest_bytes = encode(expected_manifest)
    if (digest(config) != C4_PAPER_V20_CONFIG_SHA256
            or digest(manifest_bytes) != C4_PAPER_V20_MANIFEST_SHA256):
        return False
    if any(mode(roots[name]) != plan["files"][name]["mode"]
           for name in ("config", "manifest")):
        return False
    return (svc._fabric_release_bytes(roots["config"]) == config
            and svc._fabric_release_bytes(roots["manifest"]) == manifest_bytes)


def require_start(svc, account, roots):
    if account != ACCOUNT:
        fail("START_REFUSED")
    pin = svc._pin_owner_module()
    path = roots["state"] / TRANSACTION
    plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    with original_pin(svc, roots, "status") as (pin, original, fingerprint):
        plan, raw = retained(svc, pin, roots, path, digest(encode(plan)), original, fingerprint)
        static_seal(svc, pin, roots, original)
        if pin.decode(svc._fabric_release_bytes(path / "result.json")) != result_record(plan):
            fail("START_REFUSED")
        try:
            complete = observe(svc, roots, plan, raw) == len(ORDER)
        except SystemExit as exc:
            if (exc.code != "NATIVE_PIN_ENROLLMENT_FOREIGN_STATE"
                    or not _c4_paper_v20_post_enrollment(svc, roots, plan, raw)):
                raise
            complete = True
        if not complete:
            fail("START_REFUSED")
