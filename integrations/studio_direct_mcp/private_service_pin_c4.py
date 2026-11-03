"""Exact C4 repository enrollment successor within the existing Studio native-pin owner.

No new launcher, registry, credential, pool, scheduler, repository writer or
lifecycle control. The old seven-file native-pool-pin receipt is immutable.
The only modifying path is its existing account lifecycle lock plus a
manifest-last, same-owner, retained successor transaction.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
import hashlib
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

SCHEMA = "mastermind.studio_native_pin_c4_repositories.v1"
ACCOUNT = "chatgpt4"
TX_NAME = "native-pool-pin-c4-repositories"
ORIGINAL_MANIFEST = "168bb25afd7d710799fb86f8912389d49c86371c107ee9544d65fdc2b9d390e2"
ORIGINAL_CONFIG = "f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21"
POST_CONFIG = "fa00524fcade00b9fa6ffe33883600bec1856a41633f64b50c9f77e67527bfaa"
POST_MANIFEST = "0fef1fcdaa6fff1f8eb605ad62cf931aaddc7fcf3a1eddbfaaeb749f8741205f"
POST_MANIFEST_CANONICAL = "f7a737600b819deb0e9dbb746fa202d2777b0d6d4047f0c54d99b32f691ec79b"
GATEWAY_BLOB = "f87ac012339e82fe46bce5ddc70d1d04183d1b6e"
CLOSED_REPOSITORIES = ("mastermind", "macro", "terminal")
CHANGED = ("gateway.mjs", "git-publish.mjs", "workspace-access.mjs")
STEPS = (*CHANGED, "config", "manifest")

# Frozen C4 generation. Neither the generic fleet-publisher moving target nor
# a later native-pool generation may retroactively change this postimage.
POST_FILES = {
    "fleet-routing.mjs": "dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533",
    "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c",
    "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
    "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
    "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
    "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
    "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
    "private-tunnel-gateway.mjs": "fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540",
    "tailnet-gateway.mjs": "9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}
# The complete original profile is separately frozen, not looked up from a
# moving alias or C2's independent Paper runtime rollout.
PRE_FILES = {
    **{key: value for key, value in POST_FILES.items() if key not in CHANGED},
    "gateway.mjs": "92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8",
    "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
}
TRANSACTION_FILES = frozenset(
    {"plan.json", "intent.json", "result.json",
     "config.before", "config.after", "manifest.before", "manifest.after"}
    | {name + "." + side for name in CHANGED for side in ("before", "after")
       if name != "workspace-access.mjs" or side == "after"}
)
REFUSALS = frozenset((
    "ACCOUNT_REFUSED", "ARGS_REFUSED", "SOURCE_REFUSED", "TARGET_REFUSED",
    "ORIGINAL_PIN_REFUSED", "PREIMAGE_REFUSED", "PLAN_CAS_REFUSED",
    "TRANSACTION_EXISTS", "TRANSACTION_REFUSED", "FOREIGN_STATE",
    "MANIFEST_REFUSED", "STATIC_SEAL_REFUSED", "SERVICE_LOADED",
    "RECONCILIATION_REQUIRED", "RESULT_REFUSED", "START_REFUSED",
    "EFFECT_UNKNOWN",
))


def fail(code):
    if code not in REFUSALS:
        code = "TRANSACTION_REFUSED"
    raise SystemExit("NATIVE_POOL_C4_" + code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin_owner(svc):
    return svc._pin_owner_module()


@contextmanager
def original_pin(svc, roots, *, modifying=False):
    """Hold the original native selection fence through any successor mutation."""
    pin = pin_owner(svc)
    path = roots["state"] / "native-pool-pin"
    verified_before_yield = False
    try:
        pin.directory(svc, path)
        p = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
        if (p.get("schema") != pin.SCHEMA or p.get("account") != ACCOUNT
                or p.get("uid") != os.getuid()
                or p.get("config_after") != ORIGINAL_CONFIG
                or p.get("manifest_after") != ORIGINAL_MANIFEST):
            fail("ORIGINAL_PIN_REFUSED")
        args = SimpleNamespace(
            account=ACCOUNT,
            expected_manifest_sha256=p["manifest_before"],
            successor_bundle=p["successor_bundle"],
            successor_plan_sha256=p["successor_digest"],
            expected_plan_sha256=pin.plan_sha(svc, p),
            operation="apply" if modifying else "status",
        )
        with svc._pin_native_context(args) as binding:
            plan, _ = pin.read_transaction(svc, path, args, binding)
            result = pin.decode(svc._fabric_release_bytes(path / "result.json"))
            if (result != {"schema": pin.SCHEMA,
                           "planSha256": pin.plan_sha(svc, plan),
                           "effect": "APPLIED"}
                    or binding.get("phase") != "SELECTED"
                    or svc._stable_regular_file_hash(
                        Path(p["pool_target"]), label="C4 native pin selected pool"
                    ) != p["pool_bridge"]):
                fail("ORIGINAL_PIN_REFUSED")
            verified_before_yield = True
            yield pin.plan_sha(svc, p)
    except (OSError, ValueError, KeyError, TypeError):
        # Context managers forward caller exceptions through their yield.
        # Once verified, preserving the caller's exact error is essential:
        # a post-dispatch write failure must remain EFFECT_UNKNOWN.
        if verified_before_yield:
            raise
        fail("ORIGINAL_PIN_REFUSED")


def source_bytes(svc, source):
    """Read exact reviewed source objects; never fetch a remote or select a URL."""
    if not isinstance(source, str):
        fail("SOURCE_REFUSED")
    raw = Path(source)
    if (not raw.is_absolute() or raw.is_symlink()
            or raw.name != "studio_direct_mcp"
            or raw.parent.name != "integrations" or not raw.is_dir()):
        fail("SOURCE_REFUSED")
    root = raw.parent.parent
    try:
        response = subprocess.run(
            ["/usr/bin/git", "-C", str(root), "cat-file", "blob", GATEWAY_BLOB],
            env={"PATH": "/usr/bin:/bin", "GIT_NO_LAZY_FETCH": "1",
                 "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"},
            capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        fail("SOURCE_REFUSED")
    if (response.returncode != 0 or len(response.stdout) > 2 * 1024 * 1024
            or digest(response.stdout) != POST_FILES["gateway.mjs"]):
        fail("TARGET_REFUSED")
    # Reuse the existing source-installer file admission. The native-pin
    # retained-byte reader intentionally admits HOME-owned *install targets*
    # only and is not a source-checkout reader for managed /Volumes worktrees.
    try:
        allowed = {p.name: p for p in svc._check_source_files(raw)}
    except (OSError, ValueError, TypeError):
        fail("SOURCE_REFUSED")
    files = {"gateway.mjs": response.stdout}
    for name in CHANGED[1:]:
        source_file = allowed.get(name)
        if source_file is None or source_file.is_symlink():
            fail("SOURCE_REFUSED")
        try:
            fd = os.open(source_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                first = os.fstat(fd)
                if (not stat.S_ISREG(first.st_mode) or first.st_uid != os.getuid()
                        or first.st_size > 2 * 1024 * 1024
                        or first.st_mode & 0o022):
                    fail("SOURCE_REFUSED")
                with os.fdopen(fd, "rb", closefd=False) as source_stream:
                    content = source_stream.read(2 * 1024 * 1024 + 1)
                after = os.fstat(fd)
                if (len(content) > 2 * 1024 * 1024 or
                        (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
                        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                    fail("SOURCE_REFUSED")
            finally:
                os.close(fd)
        except OSError:
            fail("SOURCE_REFUSED")
        if digest(content) != POST_FILES[name]:
            fail("TARGET_REFUSED")
        files[name] = content
    return files


def sealed_before(svc, roots, original_pin_sha):
    label = "com.mastermind.studio-direct-private." + ACCOUNT
    svc._verify_native_pin_install(ACCOUNT, label, roots)
    if digest(svc._fabric_release_bytes(roots["manifest"])) != ORIGINAL_MANIFEST:
        fail("PREIMAGE_REFUSED")
    if digest(svc._fabric_release_bytes(roots["config"])) != ORIGINAL_CONFIG:
        fail("PREIMAGE_REFUSED")
    manifest = pin_owner(svc).decode(svc._fabric_release_bytes(roots["manifest"]))
    if manifest.get("files") != PRE_FILES:
        fail("PREIMAGE_REFUSED")
    config = pin_owner(svc).decode(svc._fabric_release_bytes(roots["config"]))
    if (config.get("accountLabel") != ACCOUNT
            or config.get("repositoryWorkspaces") is not None
            or not isinstance(config.get("gitPublish"), dict)
            or config["gitPublish"].get("enabled") is not True):
        fail("PREIMAGE_REFUSED")
    return manifest, config


def snapshot(svc, roots, source, original_sha):
    before_manifest, before_config = sealed_before(svc, roots, original_sha)
    projected_config = copy.deepcopy(before_config)
    projected_config["repositoryWorkspaces"] = {
        "enabled": True, "allowedRepositories": list(CLOSED_REPOSITORIES),
    }
    raw = {
        "config.before": svc._fabric_release_bytes(roots["config"]),
        "config.after": svc._fabric_release_json(projected_config),
        "manifest.before": svc._fabric_release_bytes(roots["manifest"]),
    }
    if digest(raw["config.after"]) != POST_CONFIG:
        fail("TARGET_REFUSED")
    after_manifest = copy.deepcopy(before_manifest)
    after_manifest["configHash"] = POST_CONFIG
    after_manifest["files"] = dict(POST_FILES)
    raw["manifest.after"] = svc._fabric_release_json(after_manifest)
    if digest(raw["manifest.after"]) != POST_MANIFEST:
        fail("TARGET_REFUSED")
    source_content = source_bytes(svc, source)
    modes = {}
    for name in CHANGED:
        target = roots["base"] / name
        if name == "workspace-access.mjs":
            if os.path.lexists(target):
                fail("PREIMAGE_REFUSED")
            modes[name] = svc.FILE_MODE
        else:
            raw[name + ".before"] = svc._fabric_release_bytes(target)
            if digest(raw[name + ".before"]) != PRE_FILES[name]:
                fail("PREIMAGE_REFUSED")
            modes[name] = stat.S_IMODE(target.lstat().st_mode)
        raw[name + ".after"] = source_content[name]
    for key in ("config", "manifest"):
        modes[key] = stat.S_IMODE(roots[key].lstat().st_mode)
    plan = {
        "schema": SCHEMA, "account": ACCOUNT, "uid": os.getuid(),
        "original_pin_plan": original_sha,
        "manifest_before": ORIGINAL_MANIFEST, "manifest_after": POST_MANIFEST,
        "config_before": ORIGINAL_CONFIG, "config_after": POST_CONFIG,
        "pre_files": dict(PRE_FILES), "post_files": dict(POST_FILES),
        "gateway_blob": GATEWAY_BLOB, "modes": modes,
    }
    return plan, raw


def plan_hash(svc, plan):
    return digest(svc._fabric_release_json(plan))


def transaction_dir(roots):
    return roots["state"] / TX_NAME


def transaction(svc, roots, expected_sha, original_sha):
    """Read and authenticate every retained byte, without accepting stale plans."""
    pin = pin_owner(svc)
    directory = transaction_dir(roots)
    try:
        pin.directory(svc, directory)
        names = {p.name for p in directory.iterdir()}
        if names - TRANSACTION_FILES or not TRANSACTION_FILES.issubset(
            names | {"result.json"}
        ) or not {"plan.json", "intent.json"}.issubset(names):
            fail("TRANSACTION_REFUSED")
        plan = pin.decode(svc._fabric_release_bytes(directory / "plan.json"))
        required = {"schema", "account", "uid", "original_pin_plan",
                    "manifest_before", "manifest_after", "config_before",
                    "config_after", "pre_files", "post_files", "gateway_blob",
                    "modes"}
        if (set(plan) != required or plan["schema"] != SCHEMA
                or plan["account"] != ACCOUNT or plan["uid"] != os.getuid()
                or plan["original_pin_plan"] != original_sha
                or plan["manifest_before"] != ORIGINAL_MANIFEST
                or plan["manifest_after"] != POST_MANIFEST
                or plan["config_before"] != ORIGINAL_CONFIG
                or plan["config_after"] != POST_CONFIG
                or plan["pre_files"] != PRE_FILES or plan["post_files"] != POST_FILES
                or plan["gateway_blob"] != GATEWAY_BLOB
                or not isinstance(plan["modes"], dict)
                or set(plan["modes"]) != set(STEPS)
                or any(type(mode) is not int or mode != svc.FILE_MODE
                       for mode in plan["modes"].values())
                or plan_hash(svc, plan) != expected_sha):
            fail("PLAN_CAS_REFUSED")
        if pin.decode(svc._fabric_release_bytes(directory / "intent.json")) != {
            "schema": SCHEMA, "planSha256": expected_sha,
        }:
            fail("TRANSACTION_REFUSED")
        retained = {}
        for key in sorted(TRANSACTION_FILES - {"plan.json", "intent.json", "result.json"}):
            retained[key] = svc._fabric_release_bytes(directory / key)
        if (digest(retained["manifest.before"]) != ORIGINAL_MANIFEST
                or digest(retained["manifest.after"]) != POST_MANIFEST
                or digest(retained["config.before"]) != ORIGINAL_CONFIG
                or digest(retained["config.after"]) != POST_CONFIG):
            fail("TRANSACTION_REFUSED")
        before_cfg = pin.decode(retained["config.before"])
        after_cfg = pin.decode(retained["config.after"])
        projected = copy.deepcopy(before_cfg)
        projected["repositoryWorkspaces"] = {
            "enabled": True, "allowedRepositories": list(CLOSED_REPOSITORIES),
        }
        if after_cfg != projected:
            fail("TRANSACTION_REFUSED")
        before_m = pin.decode(retained["manifest.before"])
        after_m = pin.decode(retained["manifest.after"])
        projected_m = copy.deepcopy(before_m)
        projected_m["configHash"] = POST_CONFIG
        projected_m["files"] = dict(POST_FILES)
        if (before_m.get("files") != PRE_FILES or after_m != projected_m
                or before_m.get("configHash") != ORIGINAL_CONFIG):
            fail("TRANSACTION_REFUSED")
        for name in CHANGED:
            if digest(retained[name + ".after"]) != POST_FILES[name]:
                fail("TRANSACTION_REFUSED")
            if name != "workspace-access.mjs" and digest(
                retained[name + ".before"]
            ) != PRE_FILES[name]:
                fail("TRANSACTION_REFUSED")
        if "result.json" in names:
            result = pin.decode(svc._fabric_release_bytes(directory / "result.json"))
            if result != {"schema": SCHEMA, "planSha256": expected_sha,
                          "effect": "APPLIED"}:
                fail("RESULT_REFUSED")
        return plan, retained, "result.json" in names
    except (OSError, ValueError, KeyError, TypeError):
        fail("TRANSACTION_REFUSED")


def restore_incomplete_prewrite_journal(svc, roots, args, original_sha):
    """Complete only missing journal entries of this exact original transaction.

    This is NOT an apply replay. A retained plan and unchanged installed
    predecessor must both exist; present bytes are immutable. Once a module
    may have been modified, journal repair is categorically unavailable.
    """
    tx = transaction_dir(roots)
    pin = pin_owner(svc)
    try:
        pin.directory(svc, tx)
        current_plan = pin.decode(svc._fabric_release_bytes(tx / "plan.json"))
        if plan_hash(svc, current_plan) != args.expected_plan_sha256:
            fail("PLAN_CAS_REFUSED")
        if not isinstance(args.source, str) or not args.source:
            fail("SOURCE_REFUSED")
        plan, payloads = snapshot(svc, roots, args.source, original_sha)
        if (plan != current_plan or
                plan_hash(svc, plan) != args.expected_plan_sha256):
            fail("PLAN_CAS_REFUSED")
        expected = {
            "plan.json": svc._fabric_release_json(plan),
            **payloads,
            "intent.json": svc._fabric_release_json({
                "schema": SCHEMA, "planSha256": args.expected_plan_sha256,
            }),
        }
        names = {p.name for p in tx.iterdir()}
        if names - set(expected):
            fail("TRANSACTION_REFUSED")
        # Read every existing value before creating a missing file. A crashed
        # partial write or foreign file never gets silently overwritten.
        for name in names:
            if svc._fabric_release_bytes(tx / name) != expected[name]:
                fail("TRANSACTION_REFUSED")
    except (OSError, ValueError, TypeError, KeyError):
        fail("TRANSACTION_REFUSED")
    # Missing journal writes are effects, even if no installed module moved.
    # A failed write must preserve uncertainty on this original transaction.
    try:
        for name in sorted(set(expected) - names - {"intent.json"}):
            svc._fabric_release_new(tx / name, expected[name])
        if "intent.json" not in names:
            svc._fabric_release_new(tx / "intent.json", expected["intent.json"])
    except BaseException:
        fail("EFFECT_UNKNOWN")


def current_state(svc, roots, retained):
    """Only accept a strict manifest-last prefix of the five fixed mutations."""
    states = []
    for key in STEPS:
        path = roots[key] if key in ("config", "manifest") else roots["base"] / key
        if key == "workspace-access.mjs" and not os.path.lexists(path):
            value = "BEFORE"
        else:
            raw = svc._fabric_release_bytes(path)
            if key == "workspace-access.mjs":
                value = "AFTER" if raw == retained[key + ".after"] else "FOREIGN"
            elif raw == retained[key + ".before"]:
                value = "BEFORE"
            elif raw == retained[key + ".after"]:
                value = "AFTER"
            else:
                value = "FOREIGN"
        if value == "FOREIGN":
            fail("FOREIGN_STATE")
        states.append(value)
    if states != sorted(states, key=lambda x: 0 if x == "AFTER" else 1):
        fail("FOREIGN_STATE")
    if all(x == "BEFORE" for x in states):
        return "OLD", 0
    if all(x == "AFTER" for x in states):
        return "COMPLETE", len(STEPS)
    return "PARTIAL", states.count("AFTER")


def static_seal(svc, roots, retained, state):
    """Check unchanged modules plus the original node/backend/plist/deps seal."""
    pre = pin_owner(svc).decode(retained["manifest.before"])
    if not svc._native_pin_manifest_valid(pre, ACCOUNT,
          "com.mastermind.studio-direct-private." + ACCOUNT):
        fail("STATIC_SEAL_REFUSED")
    for name, expected in PRE_FILES.items():
        if name not in CHANGED and digest(svc._fabric_release_bytes(
            roots["base"] / name
        )) != expected:
            fail("STATIC_SEAL_REFUSED")
    if (digest(svc._fabric_release_bytes(roots["plist"])) != pre["plistHash"]
            or svc._stable_regular_file_hash(
                Path(pre["node"]), label="C4 native publisher node"
            ) != pre["nodeHash"]
            or svc._stable_regular_file_hash(
                Path(pre["backend"]), label="C4 native publisher backend"
            ) != pre["backendHash"]
            or svc._dependency_tree_hash(roots["node_modules"])
            != pre["dependencyTreeHash"]):
        fail("STATIC_SEAL_REFUSED")
    if state == "COMPLETE":
        svc._verify_native_pin_install(
            ACCOUNT, "com.mastermind.studio-direct-private." + ACCOUNT, roots
        )


def stopped(svc, roots):
    label = "com.mastermind.studio-direct-private." + ACCOUNT
    if svc._lifecycle_inspect(ACCOUNT, label, roots, require_positive=True) is not None:
        fail("SERVICE_LOADED")


def report(svc, plan, phase, *, committed=False):
    return {
        "schema": SCHEMA, "account": ACCOUNT, "effect_state":
            "APPLIED" if phase == "COMPLETE" and committed
            else "NOT_APPLIED" if phase in ("PREVIEW", "OLD")
            else "PARTIAL",
        "phase": phase, "planSha256": plan_hash(svc, plan),
        "manifestBefore": ORIGINAL_MANIFEST, "manifestAfter": POST_MANIFEST,
        "configAfter": POST_CONFIG, "originalNativePinPreserved": True,
        "resultCommitted": committed, "serviceStarted": False,
        "repositoryAuthorityExpanded": False,
    }


def transition(svc, roots, plan, retained):
    """Replay only the SAME retained transaction under the exact native owner."""
    directory = transaction_dir(roots)
    for step in STEPS:
        state, applied = current_state(svc, roots, retained)
        if state == "COMPLETE":
            break
        if STEPS[applied] != step:
            continue
        stopped(svc, roots)
        static_seal(svc, roots, retained, state)
        path = roots[step] if step in ("config", "manifest") else roots["base"] / step
        if step == "workspace-access.mjs":
            svc._fabric_release_new(path, retained[step + ".after"])
        else:
            svc._atomic_write_bytes(
                path, retained[step + ".after"], mode=plan["modes"][step]
            )
        if current_state(svc, roots, retained)[1] != applied + 1:
            fail("FOREIGN_STATE")
    state, _ = current_state(svc, roots, retained)
    if state != "COMPLETE":
        fail("FOREIGN_STATE")
    static_seal(svc, roots, retained, "COMPLETE")
    stopped(svc, roots)
    if not os.path.lexists(directory / "result.json"):
        svc._fabric_release_new(directory / "result.json",
            svc._fabric_release_json({
                "schema": SCHEMA,
                "planSha256": plan_hash(svc, plan),
                "effect": "APPLIED",
            }))
    return report(svc, plan, "COMPLETE", committed=True)


def run(svc, args):
    if args.account != ACCOUNT:
        fail("ACCOUNT_REFUSED")
    if (args.operation not in ("preview", "apply", "status", "reconcile")
            or args.expected_manifest_sha256 != ORIGINAL_MANIFEST
            or (args.operation != "preview" and
                (not isinstance(args.expected_plan_sha256, str)
                 or len(args.expected_plan_sha256) != 64))):
        fail("ARGS_REFUSED")
    roots = svc._build_runtime_roots(ACCOUNT)
    tx = transaction_dir(roots)
    readonly = args.operation in ("preview", "status")
    mutex = nullcontext() if readonly else svc._c2_lifecycle_mutex(ACCOUNT)
    with mutex, original_pin(svc, roots, modifying=not readonly) as original_sha:
        if args.operation == "preview":
            if os.path.lexists(tx):
                fail("TRANSACTION_EXISTS")
            plan, _ = snapshot(svc, roots, args.source, original_sha)
            return report(svc, plan, "PREVIEW")
        if args.operation == "apply":
            if os.path.lexists(tx):
                fail("RECONCILIATION_REQUIRED")
            stopped(svc, roots)
            plan, retained = snapshot(svc, roots, args.source, original_sha)
            if plan_hash(svc, plan) != args.expected_plan_sha256:
                fail("PLAN_CAS_REFUSED")
            pin_owner(svc).directory(svc, roots["state"])
            tx.mkdir(mode=svc.DIR_MODE)
            svc._fsync_dir(tx.parent)
            # A lost return after creating this transaction is uncertain.
            try:
                svc._fabric_release_new(tx / "plan.json", svc._fabric_release_json(plan))
                for name, raw in sorted(retained.items()):
                    svc._fabric_release_new(tx / name, raw)
                svc._fabric_release_new(tx / "intent.json",
                    svc._fabric_release_json({
                        "schema": SCHEMA, "planSha256": args.expected_plan_sha256,
                    }))
                plan, retained, _ = transaction(
                    svc, roots, args.expected_plan_sha256, original_sha
                )
                return transition(svc, roots, plan, retained)
            except (Exception, SystemExit):
                fail("EFFECT_UNKNOWN")
        if not os.path.lexists(tx):
            fail("TRANSACTION_REFUSED")
        if args.operation == "reconcile":
            # Only prepare an incomplete journal against the untouched
            # predecessor, retaining the same plan SHA and original tx path.
            # No fallback is attempted for a completed/valid journal.
            pin = pin_owner(svc)
            pin.directory(svc, tx)
            if not os.path.lexists(tx / "intent.json"):
                try:
                    restore_incomplete_prewrite_journal(
                        svc, roots, args, original_sha
                    )
                except SystemExit:
                    raise
                except BaseException:
                    fail("EFFECT_UNKNOWN")
        plan, retained, committed = transaction(
            svc, roots, args.expected_plan_sha256, original_sha
        )
        phase, _ = current_state(svc, roots, retained)
        static_seal(svc, roots, retained, phase)
        if committed and phase != "COMPLETE":
            fail("RESULT_REFUSED")
        if args.operation == "status":
            return report(svc, plan, phase, committed=committed)
        stopped(svc, roots)
        try:
            return transition(svc, roots, plan, retained)
        except (Exception, SystemExit):
            fail("EFFECT_UNKNOWN")


def require_start(svc, roots):
    """A present successor demands complete retained proof before C4 starts."""
    path = transaction_dir(roots)
    if not os.path.lexists(path):
        return pin_owner(svc).require_start(svc, ACCOUNT, roots)
    with original_pin(svc, roots) as original_sha:
        return _require_start_selected(svc, roots, original_sha)


def _require_start_selected(svc, roots, original_sha):
    path = transaction_dir(roots)
    pin = pin_owner(svc)
    pin.directory(svc, path)
    plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    expected = plan_hash(svc, plan)
    plan, retained, committed = transaction(svc, roots, expected, original_sha)
    phase, _ = current_state(svc, roots, retained)
    if phase != "COMPLETE" or not committed:
        fail("START_REFUSED")
    static_seal(svc, roots, retained, "COMPLETE")
