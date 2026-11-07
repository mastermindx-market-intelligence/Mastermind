"""Closed C4/admin and two ChatGPT3 workspaces enrollment via existing private-service owner.

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
# Two exact, manifest-pinned original accounts; no runtime account selector.
PROFILES = {
    ACCOUNT: {
        "account": ACCOUNT, "generation": GENERATION, "port": 45024,
        "before_manifest": BEFORE_MANIFEST, "before_config": BEFORE_CONFIG,
        "original_plan": ORIGINAL_PLAN,
    },
    "admin-business": {
        "account": "admin-business",
        "generation": "admin-business-closed-repositories-20261104-v1",
        "port": 45030,
        "before_manifest": "35903622d2e10b3ba56aedbf64cc2484d8b53bdb67ab71a8e0f9b0b7ebacc148",
        "before_config": "2f0fd933062a0168093caa6a675dc27c91746837701fd28d74b7baf5ff3f4863",
        "original_plan": "25870fe238760b16ccc41b005c3a4289b8327dbe5a4d8b10015c00faaac15bac",
    },
    "chatgpt3-w570f6f34": {
        "account": "chatgpt3-w570f6f34",
        "generation": "chatgpt3-workspaces-closed-repositories-20261104-v1",
        "port": 45032,
        "before_manifest": "aa24bddbad7e989cedf566f4fbf4288fa333ee8fac8d2585cdcd9c954736eab3",
        "before_config": "6e527360ba76034d0bde30943cb1025f82489525445bcac2ab86c8b190df8fbc",
        "original_plan": "1239d26202ea93279e356578910fd6ca326006cf39db41b82aefd3fb16213051",
    },
    "chatgpt3-wa2a9e6f9": {
        "account": "chatgpt3-wa2a9e6f9",
        "generation": "chatgpt3-workspaces-closed-repositories-20261104-v1",
        "port": 45034,
        "before_manifest": "38d5427f418f9f3f7aa1ff671befa55555f276cd4b639a6312e24fa0672965a3",
        "before_config": "4e9aad915c1ea46e5de79c158d233d911e5aef7832d2016a2616a2996fa8fa68",
        "original_plan": "bf798b50b2c25df035c6ddd7d4e9a09db8246423a2176c1983fdde56f8c2da45",
    },
}
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


def frozen_profile(account):
    if account == ACCOUNT:
        # Preserve the original C4 owner's exact mutable-constant fixture contract.
        # Production constants remain source-frozen; synthetic tests patch them.
        return {"account": ACCOUNT, "generation": GENERATION, "port": 45024,
                "before_manifest": BEFORE_MANIFEST, "before_config": BEFORE_CONFIG,
                "original_plan": ORIGINAL_PLAN}
    result = PROFILES.get(account)
    if result is None:
        fail("INPUT_REFUSED")
    return result


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    # Freeze this generation's representation independently of future installers.
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def target_config(home, before, profile=None):
    """One frozen account profile; neither caller nor a mutable config picks targets."""
    if profile is None:  # Retain exact C4's existing pure-function test contract.
        profile = frozen_profile(ACCOUNT)
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
    if (before.get("accountLabel") != profile["account"]
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
def _c4_publisher_native_context(svc, args):
    """Read the completed parent while retaining its canonical publication lock.

    This child does not install or select native code. Generic native modifying
    verbs keep their strict bootstrap reader; only this closed C4 continuation
    authenticates the historical parent through the existing status reader.
    """
    if args.account != ACCOUNT or args.operation not in ("apply", "reconcile"):
        fail("INPUT_REFUSED")
    proof_args = SimpleNamespace(**{**vars(args), "operation": "status"})
    with svc._pin_native_context(proof_args) as binding:
        first = copy.deepcopy(binding)
    if svc._INSTALLED_CONTROL_CONTEXT is not None:
        generation = svc._installed_control_module(
            "_studio_c4_parent_native_generation",
            "ops/native_fabric/quota_continuity/rollout/native_generation.py")
    else:
        import importlib.util
        source = (Path(svc.__file__).resolve().parents[2]
                  / "ops/native_fabric/quota_continuity/rollout/native_generation.py")
        spec = importlib.util.spec_from_file_location(
            "_studio_c4_parent_native_generation", source)
        generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generation)
    with generation.publication_lock(Path(first["store"])):
        with svc._pin_native_context(proof_args) as checked:
            if checked != first:
                fail("ORIGINAL_PIN_REFUSED")
            # Keep the same native lock through child publication and the final
            # original-pin fingerprint check. No nested native modifying lock.
            yield checked


@contextmanager
def original_pin(svc, roots, operation, profile, *, c4_publisher=False):
    """Authenticate retained proof with the actual existing native selection owner."""
    pin = svc._pin_owner_module()
    path = roots["state"] / "native-pool-pin"
    fingerprint = pin_fingerprint(svc, pin, path)
    p = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    if (fingerprint["plan.json"] != profile["original_plan"]
            or p.get("schema") != pin.SCHEMA or p.get("account") != profile["account"]
            or p.get("uid") != os.getuid()
            or p.get("manifest_after") != profile["before_manifest"]
            or p.get("config_after") != profile["before_config"]):
        fail("ORIGINAL_PIN_REFUSED")
    args = SimpleNamespace(
        account=profile["account"], expected_manifest_sha256=p["manifest_before"],
        successor_bundle=p["successor_bundle"],
        successor_plan_sha256=p["successor_digest"],
        expected_plan_sha256=pin.plan_sha(svc, p),
        # The existing owner takes its publication lock for these exact verbs.
        operation=operation if operation in ("apply", "reconcile") else "status",
    )
    context = (_c4_publisher_native_context(svc, args) if c4_publisher
               else svc._pin_native_context(args))
    with context as binding:
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


def projected(svc, pin, original, profile):
    before_config = original["config.after.json"]
    before_manifest = original["manifest.after.json"]
    if digest(before_config) != profile["before_config"] or digest(before_manifest) != profile["before_manifest"]:
        fail("PROFILE_REFUSED")
    after_config = encode(target_config(svc._user_root(), pin.decode(before_config), profile))
    manifest = pin.decode(before_manifest)
    if (manifest.get("account") != profile["account"] or manifest.get("port") != profile["port"]
            or manifest.get("host") != "127.0.0.1"
            or len(manifest.get("files", {})) != 11
            or "workspace-access.mjs" in manifest["files"]):
        fail("PROFILE_REFUSED")
    after = copy.deepcopy(manifest)
    after["configHash"] = digest(after_config)
    after["files"].update(TARGET_FILES)
    if not svc._native_pin_manifest_valid(after, profile["account"], after["label"]):
        fail("PROFILE_REFUSED")
    return {"config.before": before_config, "config.after": after_config,
            "manifest.before": before_manifest, "manifest.after": encode(after)}


def expected_plan(raw, modes, original_fingerprint, profile):
    return {
        "schema": SCHEMA, "generation": profile["generation"], "account": profile["account"],
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


def candidate(svc, pin, args, roots, original, original_fingerprint, profile):
    source = Path(args.source) if isinstance(args.source, str) else Path(".")
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        fail("SOURCE_REFUSED")
    # Reviewed payload staged beneath this owner's home, not an alternate runtime.
    try:
        source.relative_to(svc._user_root())
    except ValueError:
        fail("SOURCE_REFUSED")
    raw = projected(svc, pin, original, profile)
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
    plan = expected_plan(raw, modes, original_fingerprint, profile)
    if observe(svc, roots, plan, raw) != 0:
        fail("FOREIGN_STATE")
    static_seal(svc, pin, roots, original)
    return plan, raw


def retained(svc, pin, roots, path, expected_sha, original, original_fingerprint, profile):
    pin.directory(svc, path)
    names = set(x.name for x in path.iterdir())
    if not FILES - {"result.json"} <= names or names - FILES:
        fail("TRANSACTION_REFUSED")
    plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    if digest(encode(plan)) != expected_sha:
        fail("PLAN_REFUSED")
    raw = {name: svc._fabric_release_bytes(path / name) for name in PAYLOADS}
    if any(raw[name] != data for name, data in projected(svc, pin, original, profile).items()):
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
            or plan != expected_plan(raw, modes, original_fingerprint, profile)
            or pin.decode(svc._fabric_release_bytes(path / "intent.json"))
               != {"schema": SCHEMA, "planSha256": expected_sha}):
        fail("TRANSACTION_REFUSED")
    return plan, raw


def stopped(svc, roots, profile):
    if svc._lifecycle_inspect(profile["account"], "com.mastermind.studio-direct-private." + profile["account"],
                              roots, require_positive=True) is not None:
        fail("SERVICE_LOADED")


def result_record(plan):
    return {"schema": SCHEMA, "planSha256": digest(encode(plan)), "effect": "APPLIED"}


def report(plan, progress, committed, profile):
    phase = "OLD" if progress == 0 else "COMPLETE" if progress == len(ORDER) else "PARTIAL"
    return {
        "schema": SCHEMA, "generation": profile["generation"], "account": profile["account"],
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
    if (args.account == ACCOUNT
            and args.expected_manifest_sha256 == C4_INVENTORY_BEFORE_MANIFEST):
        return _run_c4_inventory(svc, args, effect)
    if (args.account == ACCOUNT
            and args.expected_manifest_sha256 == C4_PUBLISHER_BEFORE_MANIFEST):
        return _run_c4_publisher(svc, args, effect)
    profile = frozen_profile(args.account)
    if (args.operation not in ("preview", "apply", "status", "reconcile")
            or args.expected_manifest_sha256 != profile["before_manifest"]
            or (args.operation != "preview" and not svc._sha256_hex(args.expected_plan_sha256))):
        fail("INPUT_REFUSED")
    roots = svc._build_runtime_roots(profile["account"])
    path = roots["state"] / TRANSACTION
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(profile["account"]) if modifying else nullcontext()
    with lock, original_pin(svc, roots, args.operation, profile) as (pin, original, fingerprint):
        if args.operation in ("preview", "apply"):
            if os.path.lexists(path):
                fail("RECONCILIATION_REQUIRED")
            if modifying:
                stopped(svc, roots, profile)
            plan, raw = candidate(svc, pin, args, roots, original, fingerprint, profile)
            if args.operation == "preview":
                value = report(plan, 0, False, profile)
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
        plan, raw = retained(svc, pin, roots, path, args.expected_plan_sha256, original, fingerprint, profile)
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
            result = report(plan, progress, committed, profile)
            if paper_v20_selected:
                result["paperV20Selected"] = True
            return result
        stopped(svc, roots, profile)
        if committed:
            return report(plan, progress, True, profile)
        changed = False
        try:
            for index in range(progress, len(ORDER)):
                stopped(svc, roots, profile)
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
            stopped(svc, roots, profile)
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
        return report(plan, len(ORDER), True, profile)


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
    profile = frozen_profile(account)
    pin = svc._pin_owner_module()
    path = roots["state"] / TRANSACTION
    plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    with original_pin(svc, roots, "status", profile) as (pin, original, fingerprint):
        plan, raw = retained(svc, pin, roots, path, digest(encode(plan)), original, fingerprint, profile)
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


# One exact C4 publisher successor of the completed enrollment/Paper/status chain.
# The original transaction and every other account remain immutable.
C4_PUBLISHER_SCHEMA = "mastermind.studio_c4_enrollment_publisher.v1"
C4_PUBLISHER_GENERATION = "c4-publisher-recovery-20261107-v4"
C4_PUBLISHER_TRANSACTION = "native-pool-pin-enrollment-publisher"
C4_PUBLISHER_BEFORE_MANIFEST = "c440f2ba4c0bdfbba3aff86303a483e3ab42a1093f330ba9e3fd6c6f923783b4"
C4_PUBLISHER_BEFORE_CONFIG = "f06dc822015fc11f34d7e1142bdf1b016cb985af701ba929f33b313ff3a570df"
C4_PUBLISHER_BEFORE = "f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c"
C4_PUBLISHER_AFTER = "a8ce5f25f4fc606e294f58de5748a73a36de5178d8e30b27132c3660e161d58e"
C4_ADAPTER_BEFORE = "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5"
C4_ADAPTER_AFTER = "290cf5e961db2fa30e37c32da473595518df0ded80fc850a84cf5bdae1a1ec3c"
C4_PUBLISHER_PAYLOADS = (
    "publisher.before", "publisher.after", "adapter.before", "adapter.after",
    "manifest.before", "manifest.after",
)
C4_PUBLISHER_FILES = frozenset((*C4_PUBLISHER_PAYLOADS,
                              "plan.json", "intent.json", "result.json"))

# One exact child of the already committed v4 pair. Its retained transaction
# stays immutable; the adapter/config and all earlier proofs are invariants.
C4_INVENTORY_GENERATION = "c4-publisher-inventory-20261107-v1"
C4_INVENTORY_TRANSACTION = "native-pool-pin-enrollment-publisher-inventory"
C4_INVENTORY_PARENT_PLAN = "7d0112d29668a3bb4ef26790387d1010fedd638895088cd08a34d9d893a12301"
C4_INVENTORY_BEFORE_MANIFEST = "8af46ae3e2ffea1ed0af23c78f9ed11dedb3411f05118937679fb535c5048d76"
C4_INVENTORY_AFTER = "6b50521c6d94c83a2f68a700f6f658c4d52ec91cd7fc29bedb00a9d4f6647f05"
C4_INVENTORY_PAYLOADS = ("publisher.before", "publisher.after", "manifest.before", "manifest.after")
C4_INVENTORY_FILES = frozenset((*C4_INVENTORY_PAYLOADS, "plan.json", "intent.json", "result.json"))


def _c4_publisher_fingerprint(svc, pin, path, names):
    pin.directory(svc, path)
    if {p.name for p in path.iterdir()} != set(names):
        fail("TRANSACTION_REFUSED")
    return {name: digest(svc._fabric_release_bytes(path / name))
            for name in sorted(names)}


def _c4_publisher_parents(svc, pin, roots, original, original_fingerprint):
    """Authenticate retained owners, not a caller's hashes or installed likeness."""
    profile = frozen_profile(ACCOUNT)
    ep = roots["state"] / TRANSACTION
    enrollment_fingerprint = _c4_publisher_fingerprint(svc, pin, ep, FILES)
    stored = pin.decode(svc._fabric_release_bytes(ep / "plan.json"))
    ep_plan, ep_raw = retained(svc, pin, roots, ep, digest(encode(stored)),
                               original, original_fingerprint, profile)
    if (pin.decode(svc._fabric_release_bytes(ep / "result.json"))
            != result_record(ep_plan)):
        fail("RESULT_REFUSED")
    owner = svc._fleet_status_successor_owner_module()
    sp = roots["state"] / owner.TRANSACTION
    status_fingerprint = _c4_publisher_fingerprint(svc, pin, sp, owner.FILE_NAMES)
    status_plan, status_raw, status_sha = owner._retained(svc, ACCOUNT, roots, sp)
    if (pin.decode(svc._fabric_release_bytes(sp / "result.json"))
            != {"schema": owner.SCHEMA, "planSha256": status_sha, "effect": "APPLIED"}
            or status_plan["originalPinPlan"] != original_fingerprint["plan.json"]
            or digest(status_raw["manifest.before"])
               != owner.PAPER_V20_PREDECESSOR_MANIFEST_SHA256[ACCOUNT]
            or digest(status_raw["manifest.after"]) != C4_PUBLISHER_BEFORE_MANIFEST
            or status_plan["configSha256"] != C4_PUBLISHER_BEFORE_CONFIG):
        fail("ORIGINAL_PIN_REFUSED")
    before = pin.decode(status_raw["manifest.after"])
    if (before.get("account") != ACCOUNT
            or before.get("label") != "com.mastermind.studio-direct-private." + ACCOUNT
            or before.get("host") != "127.0.0.1" or before.get("port") != 45024
            or before.get("configHash") != C4_PUBLISHER_BEFORE_CONFIG
            or before.get("files", {}).get("git-publish.mjs") != C4_PUBLISHER_BEFORE
            or any(before["files"].get(name) != wanted
                   for name, wanted in TARGET_FILES.items())
            or before["files"].get(owner.MODULE) != owner.TARGET_SOURCE_SHA256):
        fail("PROFILE_REFUSED")
    # _retained requalifies Paper v20 from the original enrollment config,
    # manifest and plist, and authenticates the protected status source.
    return owner, status_plan, status_raw, {
        "nativePin": original_fingerprint,
        "enrollment": enrollment_fingerprint,
        "fleetStatus": status_fingerprint,
        "preservedModes": {name: mode(roots["base"] / name)
                           for name in before["files"]
                           if name not in ("git-publish.mjs", "workspace-access.mjs")},
    }


def _c4_publisher_plan(raw, modes, parents):
    return {
        "schema": C4_PUBLISHER_SCHEMA, "generation": C4_PUBLISHER_GENERATION,
        "account": ACCOUNT, "uid": os.getuid(), "parents": parents,
        "configSha256": C4_PUBLISHER_BEFORE_CONFIG,
        "publisherBeforeSha256": C4_PUBLISHER_BEFORE,
        "publisherAfterSha256": C4_PUBLISHER_AFTER,
        "adapterBeforeSha256": C4_ADAPTER_BEFORE,
        "adapterAfterSha256": C4_ADAPTER_AFTER,
        "manifestBeforeSha256": C4_PUBLISHER_BEFORE_MANIFEST,
        "manifestAfterSha256": digest(raw["manifest.after"]),
        "modes": modes,
    }


def _c4_publisher_raw(svc, pin, roots, before, incoming, adapter):
    if digest(before) != C4_PUBLISHER_BEFORE_MANIFEST:
        fail("PROFILE_REFUSED")
    if (digest(incoming) != C4_PUBLISHER_AFTER
            or digest(adapter) != C4_ADAPTER_AFTER):
        fail("SOURCE_REFUSED")
    projected = copy.deepcopy(pin.decode(before))
    projected["files"]["git-publish.mjs"] = C4_PUBLISHER_AFTER
    projected["files"]["workspace-access.mjs"] = C4_ADAPTER_AFTER
    if not svc._native_pin_manifest_valid(
            projected, ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT):
        fail("PROFILE_REFUSED")
    return {"publisher.after": incoming, "adapter.after": adapter, "manifest.before": before,
            "manifest.after": encode(projected)}


def _c4_publisher_retained(svc, pin, roots, target, status_raw, parents):
    pin.directory(svc, target)
    names = {p.name for p in target.iterdir()}
    if (names - C4_PUBLISHER_FILES
            or C4_PUBLISHER_FILES - {"result.json"} - names):
        fail("TRANSACTION_REFUSED")
    plan = pin.decode(svc._fabric_release_bytes(target / "plan.json"))
    raw = {name: svc._fabric_release_bytes(target / name)
           for name in C4_PUBLISHER_PAYLOADS}
    projected = _c4_publisher_raw(svc, pin, roots, status_raw["manifest.after"],
                                raw["publisher.after"], raw["adapter.after"])
    if (any(raw[name] != value for name, value in projected.items())
            or digest(raw["publisher.before"]) != C4_PUBLISHER_BEFORE
            or digest(raw["adapter.before"]) != C4_ADAPTER_BEFORE):
        fail("TRANSACTION_REFUSED")
    modes = plan.get("modes")
    if (type(modes) is not dict or set(modes) != {"publisher", "adapter", "manifest", "config"}
            or any(type(m) is not int or m not in (0o400, 0o600)
                   for m in modes.values())
            or plan != _c4_publisher_plan(raw, modes, parents)):
        fail("PLAN_REFUSED")
    pd = digest(encode(plan))
    if pin.decode(svc._fabric_release_bytes(target / "intent.json")) != {
            "schema": C4_PUBLISHER_SCHEMA, "planSha256": pd}:
        fail("TRANSACTION_REFUSED")
    return plan, raw, pd


def _c4_publisher_phase(svc, pin, roots, plan, raw):
    publisher = roots["base"] / "git-publish.mjs"
    adapter = roots["base"] / "workspace-access.mjs"
    for name, path in (("publisher", publisher), ("adapter", adapter),
                       ("manifest", roots["manifest"]),
                       ("config", roots["config"])):
        if mode(path) != plan["modes"][name]:
            fail("FOREIGN_STATE")
    if digest(svc._fabric_release_bytes(roots["config"])) != C4_PUBLISHER_BEFORE_CONFIG:
        fail("FOREIGN_STATE")
    state = (svc._fabric_release_bytes(publisher),
             svc._fabric_release_bytes(adapter),
             svc._fabric_release_bytes(roots["manifest"]))
    phase = {
        (raw["publisher.before"], raw["adapter.before"], raw["manifest.before"]): "OLD",
        (raw["publisher.after"], raw["adapter.before"], raw["manifest.before"]): "PUBLISHER_ONLY",
        (raw["publisher.after"], raw["adapter.after"], raw["manifest.before"]): "MODULES",
        (raw["publisher.after"], raw["adapter.after"], raw["manifest.after"]): "COMMITTED",
    }.get(state)
    if phase is None:
        fail("FOREIGN_STATE")
    _c4_publisher_static_seal(svc, pin, roots, raw)
    return phase


def _c4_publisher_static_seal(svc, pin, roots, raw):
    before = pin.decode(raw["manifest.before"])
    for name, wanted in before["files"].items():
        if name not in ("git-publish.mjs", "workspace-access.mjs"):
            if (mode(roots["base"] / name) not in (0o400, 0o600)
                    or digest(svc._fabric_release_bytes(roots["base"] / name)) != wanted):
                fail("STATIC_SEAL_REFUSED")
    if (digest(svc._fabric_release_bytes(roots["plist"])) != before["plistHash"]
            or svc._stable_regular_file_hash(Path(before["node"]),
                    label="preserved C4 node") != before["nodeHash"]
            or svc._stable_regular_file_hash(Path(before["backend"]),
                    label="preserved C4 backend") != before["backendHash"]
            or svc._dependency_tree_hash(roots["node_modules"]) != before["dependencyTreeHash"]):
        fail("STATIC_SEAL_REFUSED")


def _c4_publisher_result(plan):
    return {"schema": C4_PUBLISHER_SCHEMA, "planSha256": digest(encode(plan)),
            "effect": "APPLIED"}


def _c4_publisher_record(plan, phase, committed, *, durable=False):
    return {
        "schema": C4_PUBLISHER_SCHEMA, "generation": C4_PUBLISHER_GENERATION,
        "account": ACCOUNT, "planSha256": digest(encode(plan)), "phase": phase,
        "effect": "APPLIED" if committed else "NOT_APPLIED" if phase in ("PREVIEW", "OLD")
                  else "EFFECT_UNKNOWN" if phase == "COMMITTED" else "PARTIAL",
        "publisherSha256": C4_PUBLISHER_AFTER,
        "adapterSha256": C4_ADAPTER_AFTER,
        "manifestSha256": plan["manifestAfterSha256"],
        "receiptCommitted": committed, "durabilityConfirmed": durable,
        "originalOwnersPreserved": True, "serviceStarted": False,
        "clientAdoptionProven": False, "retryAllowed": False,
    }


def _c4_publisher_prepare(svc, pin, roots, owner, plan, raw, status_raw, parents, effect,
                          *, inventory=False):
    """Use the incumbent exclusive publication primitive, never replace a journal."""
    import shutil
    import tempfile
    target = roots["state"] / (C4_INVENTORY_TRANSACTION if inventory else C4_PUBLISHER_TRANSACTION)
    stage = Path(tempfile.mkdtemp(prefix=".c4-publisher-intent.", dir=target.parent))
    identity = owner._identity(stage)
    try:
        svc._fabric_release_new(stage / "plan.json", encode(plan))
        for name, data in raw.items():
            svc._fabric_release_new(stage / name, data)
        svc._fabric_release_new(stage / "intent.json", encode({
            "schema": C4_PUBLISHER_SCHEMA, "planSha256": digest(encode(plan))}))
        read_retained = _c4_inventory_retained if inventory else _c4_publisher_retained
        checked, checked_raw, pd = read_retained(
            svc, pin, roots, stage, status_raw, parents)
        if checked != plan or checked_raw != raw or pd != digest(encode(plan)):
            fail("TRANSACTION_REFUSED")
        owner._sync_directory(svc, stage)
        effect["started"] = True  # Covers a lost callback after exclusive rename.
        owner._rename_new(svc, stage, target)
    finally:
        if owner._same_identity(stage, identity):
            shutil.rmtree(stage)


def _run_c4_publisher(svc, args, effect):
    if (args.account != ACCOUNT or args.expected_manifest_sha256 != C4_PUBLISHER_BEFORE_MANIFEST
            or args.operation not in ("preview", "apply", "status", "reconcile")
            or (args.operation != "preview"
                and not svc._sha256_hex(args.expected_plan_sha256))):
        fail("INPUT_REFUSED")
    profile = frozen_profile(ACCOUNT)
    roots = svc._build_runtime_roots(ACCOUNT)
    target = roots["state"] / C4_PUBLISHER_TRANSACTION
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(ACCOUNT) if modifying else nullcontext()
    with lock, original_pin(svc, roots, args.operation, profile,
                            c4_publisher=modifying) as (pin, original, fingerprint):
        owner, status_plan, status_raw, parents = _c4_publisher_parents(
            svc, pin, roots, original, fingerprint)
        if args.operation in ("preview", "apply"):
            if os.path.lexists(target):
                fail("RECONCILIATION_REQUIRED")
            source = Path(args.source) if isinstance(args.source, str) else Path(".")
            if not source.is_absolute() or source.is_symlink() or not source.is_dir():
                fail("SOURCE_REFUSED")
            try:
                source.relative_to(svc._user_root())
            except ValueError:
                fail("SOURCE_REFUSED")
            svc._assert_no_symlink_ancestors(source)
            incoming = svc._fabric_release_bytes(source / "git-publish.mjs")
            adapter = svc._fabric_release_bytes(source / "workspace-access.mjs")
            raw = _c4_publisher_raw(svc, pin, roots, status_raw["manifest.after"], incoming, adapter)
            raw["publisher.before"] = svc._fabric_release_bytes(roots["base"] / "git-publish.mjs")
            raw["adapter.before"] = svc._fabric_release_bytes(roots["base"] / "workspace-access.mjs")
            modes = {name: mode(path) for name, path in (
                ("publisher", roots["base"] / "git-publish.mjs"),
                ("adapter", roots["base"] / "workspace-access.mjs"),
                ("manifest", roots["manifest"]), ("config", roots["config"]))}
            plan = _c4_publisher_plan(raw, modes, parents)
            if (digest(raw["publisher.before"]) != C4_PUBLISHER_BEFORE
                    or digest(raw["adapter.before"]) != C4_ADAPTER_BEFORE
                    or _c4_publisher_phase(svc, pin, roots, plan, raw) != "OLD"):
                fail("FOREIGN_STATE")
            if args.operation == "preview":
                return _c4_publisher_record(plan, "PREVIEW", False)
            if digest(encode(plan)) != args.expected_plan_sha256:
                fail("PLAN_REFUSED")
            stopped(svc, roots, profile)
            _c4_publisher_prepare(svc, pin, roots, owner, plan, raw, status_raw, parents, effect)
        plan, raw, pd = _c4_publisher_retained(svc, pin, roots, target, status_raw, parents)
        if pd != args.expected_plan_sha256:
            fail("PLAN_REFUSED")
        phase = _c4_publisher_phase(svc, pin, roots, plan, raw)
        result = target / "result.json"
        committed = os.path.lexists(result)
        if committed and (phase != "COMMITTED"
                          or pin.decode(svc._fabric_release_bytes(result)) != _c4_publisher_result(plan)):
            fail("RESULT_REFUSED")
        if args.operation == "status":
            return _c4_publisher_record(plan, phase, committed)
        if committed:
            owner._confirm_retained_durability(svc, roots, target)
            return _c4_publisher_record(plan, phase, True, durable=True)
        stopped(svc, roots, profile)
        for current, expected, path, data, file_mode in (
                ("OLD", "PUBLISHER_ONLY", roots["base"] / "git-publish.mjs",
                 raw["publisher.after"], plan["modes"]["publisher"]),
                ("PUBLISHER_ONLY", "MODULES", roots["base"] / "workspace-access.mjs",
                 raw["adapter.after"], plan["modes"]["adapter"]),
                ("MODULES", "COMMITTED", roots["manifest"],
                 raw["manifest.after"], plan["modes"]["manifest"])):
            if phase != current:
                continue
            stopped(svc, roots, profile)
            if (_c4_publisher_parents(svc, pin, roots, original, fingerprint)[3] != parents
                    or _c4_publisher_phase(svc, pin, roots, plan, raw) != current):
                fail("FOREIGN_STATE")
            effect["started"] = True
            svc._atomic_write_bytes(path, data, mode=file_mode)
            phase = _c4_publisher_phase(svc, pin, roots, plan, raw)
            if phase != expected:
                fail("FOREIGN_STATE")
        if phase != "COMMITTED":
            fail("START_REFUSED")
        owner._confirm_retained_durability(svc, roots, target)
        svc._verify_staged_install(ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT,
                                  roots, require_runtime_seal=True)
        stopped(svc, roots, profile)
        if _c4_publisher_parents(svc, pin, roots, original, fingerprint)[3] != parents:
            fail("ORIGINAL_PIN_REFUSED")
        effect["started"] = True
        owner._publish_result(svc, target, _c4_publisher_result(plan))
        if (pin.decode(svc._fabric_release_bytes(result)) != _c4_publisher_result(plan)
                or _c4_publisher_phase(svc, pin, roots, plan, raw) != "COMMITTED"):
            fail("RESULT_REFUSED")
        owner._confirm_retained_durability(svc, roots, target)
        return _c4_publisher_record(plan, phase, True, durable=True)


def c4_publisher_postimage(svc, account, roots, status_plan=None, status_raw=None, *, durable=False):
    """The existing status/start owner recognizes only this fully committed child."""
    if account != ACCOUNT:
        return False
    if os.path.lexists(roots["state"] / C4_INVENTORY_TRANSACTION):
        # An incomplete or foreign child must never fall back to v4 admission.
        return _c4_inventory_postimage(svc, roots, status_plan, status_raw, durable=durable)
    target = roots["state"] / C4_PUBLISHER_TRANSACTION
    if not os.path.lexists(target):
        return False
    with original_pin(svc, roots, "status", frozen_profile(ACCOUNT)) as (pin, original, fingerprint):
        owner, prior_plan, prior_raw, parents = _c4_publisher_parents(
            svc, pin, roots, original, fingerprint)
        if ((status_plan is not None and status_plan != prior_plan)
                or (status_raw is not None and status_raw != prior_raw)):
            fail("ORIGINAL_PIN_REFUSED")
        plan, raw, pd = _c4_publisher_retained(svc, pin, roots, target, prior_raw, parents)
        if (_c4_publisher_phase(svc, pin, roots, plan, raw) != "COMMITTED"
                or pin.decode(svc._fabric_release_bytes(target / "result.json"))
                   != _c4_publisher_result(plan)):
            fail("START_REFUSED")
        if durable:
            owner._confirm_retained_durability(svc, roots, target)
            svc._verify_staged_install(
                ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT,
                roots, require_runtime_seal=True)
    return True


def _c4_inventory_parents(svc, pin, roots, original, fingerprint):
    owner, status_plan, status_raw, parents = _c4_publisher_parents(
        svc, pin, roots, original, fingerprint)
    path = roots["state"] / C4_PUBLISHER_TRANSACTION
    retained_fingerprint = _c4_publisher_fingerprint(svc, pin, path, C4_PUBLISHER_FILES)
    plan, raw, pd = _c4_publisher_retained(svc, pin, roots, path, status_raw, parents)
    if (pd != C4_INVENTORY_PARENT_PLAN
            or retained_fingerprint["plan.json"] != C4_INVENTORY_PARENT_PLAN
            or digest(raw["manifest.after"]) != C4_INVENTORY_BEFORE_MANIFEST
            or pin.decode(svc._fabric_release_bytes(path / "result.json"))
               != _c4_publisher_result(plan)):
        fail("ORIGINAL_PIN_REFUSED")
    return owner, status_plan, status_raw, raw, {
        **parents, "publisherV4": retained_fingerprint,
        "publisherV4Modes": copy.deepcopy(plan["modes"]),
    }


def _c4_inventory_raw(svc, pin, before, incoming):
    if digest(before) != C4_INVENTORY_BEFORE_MANIFEST:
        fail("PROFILE_REFUSED")
    if digest(incoming) != C4_INVENTORY_AFTER:
        fail("SOURCE_REFUSED")
    projected = copy.deepcopy(pin.decode(before))
    if (projected.get("files", {}).get("git-publish.mjs") != C4_PUBLISHER_AFTER
            or projected["files"].get("workspace-access.mjs") != C4_ADAPTER_AFTER
            or projected.get("configHash") != C4_PUBLISHER_BEFORE_CONFIG):
        fail("PROFILE_REFUSED")
    projected["files"]["git-publish.mjs"] = C4_INVENTORY_AFTER
    if not svc._native_pin_manifest_valid(
            projected, ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT):
        fail("PROFILE_REFUSED")
    return {"publisher.after": incoming, "manifest.before": before,
            "manifest.after": encode(projected)}


def _c4_inventory_plan(raw, parents):
    return {
        "schema": C4_PUBLISHER_SCHEMA, "generation": C4_INVENTORY_GENERATION,
        "account": ACCOUNT, "uid": os.getuid(), "parents": parents,
        "configSha256": C4_PUBLISHER_BEFORE_CONFIG,
        "publisherBeforeSha256": C4_PUBLISHER_AFTER,
        "publisherAfterSha256": C4_INVENTORY_AFTER,
        "adapterSha256": C4_ADAPTER_AFTER,
        "manifestBeforeSha256": C4_INVENTORY_BEFORE_MANIFEST,
        "manifestAfterSha256": digest(raw["manifest.after"]),
        "modes": copy.deepcopy(parents["publisherV4Modes"]),
    }


def _c4_inventory_retained(svc, pin, roots, target, parent_raw, parents):
    pin.directory(svc, target)
    names = {p.name for p in target.iterdir()}
    if names - C4_INVENTORY_FILES or C4_INVENTORY_FILES - {"result.json"} - names:
        fail("TRANSACTION_REFUSED")
    plan = pin.decode(svc._fabric_release_bytes(target / "plan.json"))
    raw = {name: svc._fabric_release_bytes(target / name) for name in C4_INVENTORY_PAYLOADS}
    projected = _c4_inventory_raw(svc, pin, parent_raw["manifest.after"], raw["publisher.after"])
    if (any(raw[name] != value for name, value in projected.items())
            or raw["publisher.before"] != parent_raw["publisher.after"]
            or plan != _c4_inventory_plan(raw, parents)):
        fail("PLAN_REFUSED")
    pd = digest(encode(plan))
    if pin.decode(svc._fabric_release_bytes(target / "intent.json")) != {
            "schema": C4_PUBLISHER_SCHEMA, "planSha256": pd}:
        fail("TRANSACTION_REFUSED")
    return plan, raw, pd


def _c4_inventory_phase(svc, pin, roots, plan, raw):
    for name, path in (("publisher", roots["base"] / "git-publish.mjs"),
                       ("adapter", roots["base"] / "workspace-access.mjs"),
                       ("manifest", roots["manifest"]), ("config", roots["config"])):
        if mode(path) != plan["modes"][name]:
            fail("FOREIGN_STATE")
    if (digest(svc._fabric_release_bytes(roots["config"])) != C4_PUBLISHER_BEFORE_CONFIG
            or digest(svc._fabric_release_bytes(roots["base"] / "workspace-access.mjs"))
               != C4_ADAPTER_AFTER):
        fail("FOREIGN_STATE")
    state = (svc._fabric_release_bytes(roots["base"] / "git-publish.mjs"),
             svc._fabric_release_bytes(roots["manifest"]))
    # The adapter is unchanged: a four-state pair map would have duplicate keys.
    phase = {
        (raw["publisher.before"], raw["manifest.before"]): "OLD",
        (raw["publisher.after"], raw["manifest.before"]): "PUBLISHER_ONLY",
        (raw["publisher.after"], raw["manifest.after"]): "COMMITTED",
    }.get(state)
    if phase is None:
        fail("FOREIGN_STATE")
    _c4_publisher_static_seal(svc, pin, roots, raw)
    return phase


def _c4_inventory_record(plan, phase, committed, *, durable=False):
    value = _c4_publisher_record(plan, phase, committed, durable=durable)
    value.update(generation=C4_INVENTORY_GENERATION, publisherSha256=C4_INVENTORY_AFTER)
    return value


def _run_c4_inventory(svc, args, effect):
    if (args.account != ACCOUNT or args.expected_manifest_sha256 != C4_INVENTORY_BEFORE_MANIFEST
            or args.operation not in ("preview", "apply", "status", "reconcile")
            or (args.operation != "preview" and not svc._sha256_hex(args.expected_plan_sha256))):
        fail("INPUT_REFUSED")
    profile = frozen_profile(ACCOUNT)
    roots = svc._build_runtime_roots(ACCOUNT)
    target = roots["state"] / C4_INVENTORY_TRANSACTION
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(ACCOUNT) if modifying else nullcontext()
    with lock, original_pin(svc, roots, args.operation, profile,
                            c4_publisher=modifying) as (pin, original, fingerprint):
        owner, _, _, parent_raw, parents = _c4_inventory_parents(svc, pin, roots, original, fingerprint)
        if args.operation in ("preview", "apply"):
            if os.path.lexists(target):
                fail("RECONCILIATION_REQUIRED")
            source = Path(args.source) if isinstance(args.source, str) else Path(".")
            if not source.is_absolute() or source.is_symlink() or not source.is_dir():
                fail("SOURCE_REFUSED")
            try:
                source.relative_to(svc._user_root())
            except ValueError:
                fail("SOURCE_REFUSED")
            svc._assert_no_symlink_ancestors(source)
            raw = _c4_inventory_raw(svc, pin, parent_raw["manifest.after"],
                                    svc._fabric_release_bytes(source / "git-publish.mjs"))
            raw["publisher.before"] = parent_raw["publisher.after"]
            plan = _c4_inventory_plan(raw, parents)
            if _c4_inventory_phase(svc, pin, roots, plan, raw) != "OLD":
                fail("FOREIGN_STATE")
            if args.operation == "preview":
                return _c4_inventory_record(plan, "PREVIEW", False)
            if digest(encode(plan)) != args.expected_plan_sha256:
                fail("PLAN_REFUSED")
            stopped(svc, roots, profile)
            _c4_publisher_prepare(svc, pin, roots, owner, plan, raw, parent_raw,
                                  parents, effect, inventory=True)
        plan, raw, pd = _c4_inventory_retained(svc, pin, roots, target, parent_raw, parents)
        if pd != args.expected_plan_sha256:
            fail("PLAN_REFUSED")
        phase = _c4_inventory_phase(svc, pin, roots, plan, raw)
        result = target / "result.json"
        committed = os.path.lexists(result)
        if committed and (phase != "COMMITTED"
                          or pin.decode(svc._fabric_release_bytes(result)) != _c4_publisher_result(plan)):
            fail("RESULT_REFUSED")
        if args.operation == "status":
            return _c4_inventory_record(plan, phase, committed)
        if committed:
            owner._confirm_retained_durability(svc, roots, target)
            return _c4_inventory_record(plan, phase, True, durable=True)
        stopped(svc, roots, profile)
        for current, expected, path, data, file_mode in (
                ("OLD", "PUBLISHER_ONLY", roots["base"] / "git-publish.mjs",
                 raw["publisher.after"], plan["modes"]["publisher"]),
                ("PUBLISHER_ONLY", "COMMITTED", roots["manifest"],
                 raw["manifest.after"], plan["modes"]["manifest"])):
            if phase != current:
                continue
            stopped(svc, roots, profile)
            if (_c4_inventory_parents(svc, pin, roots, original, fingerprint)[4] != parents
                    or _c4_inventory_phase(svc, pin, roots, plan, raw) != current):
                fail("FOREIGN_STATE")
            effect["started"] = True
            svc._atomic_write_bytes(path, data, mode=file_mode)
            phase = _c4_inventory_phase(svc, pin, roots, plan, raw)
            if phase != expected:
                fail("FOREIGN_STATE")
        if phase != "COMMITTED":
            fail("START_REFUSED")
        owner._confirm_retained_durability(svc, roots, target)
        svc._verify_staged_install(ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT,
                                  roots, require_runtime_seal=True)
        stopped(svc, roots, profile)
        if _c4_inventory_parents(svc, pin, roots, original, fingerprint)[4] != parents:
            fail("ORIGINAL_PIN_REFUSED")
        effect["started"] = True
        owner._publish_result(svc, target, _c4_publisher_result(plan))
        if (pin.decode(svc._fabric_release_bytes(result)) != _c4_publisher_result(plan)
                or _c4_inventory_phase(svc, pin, roots, plan, raw) != "COMMITTED"):
            fail("RESULT_REFUSED")
        owner._confirm_retained_durability(svc, roots, target)
        return _c4_inventory_record(plan, phase, True, durable=True)


def _c4_inventory_postimage(svc, roots, status_plan, status_raw, *, durable=False):
    target = roots["state"] / C4_INVENTORY_TRANSACTION
    with original_pin(svc, roots, "status", frozen_profile(ACCOUNT)) as (pin, original, fingerprint):
        owner, prior_plan, prior_raw, parent_raw, parents = _c4_inventory_parents(
            svc, pin, roots, original, fingerprint)
        if ((status_plan is not None and status_plan != prior_plan)
                or (status_raw is not None and status_raw != prior_raw)):
            fail("ORIGINAL_PIN_REFUSED")
        plan, raw, _ = _c4_inventory_retained(svc, pin, roots, target, parent_raw, parents)
        if (_c4_inventory_phase(svc, pin, roots, plan, raw) != "COMMITTED"
                or pin.decode(svc._fabric_release_bytes(target / "result.json"))
                   != _c4_publisher_result(plan)):
            fail("START_REFUSED")
        if durable:
            owner._confirm_retained_durability(svc, roots, roots["state"] / C4_PUBLISHER_TRANSACTION)
            owner._confirm_retained_durability(svc, roots, target)
            svc._verify_staged_install(ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT,
                                      roots, require_runtime_seal=True)
    return True
