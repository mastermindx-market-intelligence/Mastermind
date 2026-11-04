"""Exact owner-scoped source qualifier for a post-native-pin fleet-status module.

This is a pure planner, *not* a second installer or start authority.
The existing private_service native pool owner must validate SELECTED receipts,
hold the original lifecycle lock, stop the exact seat, commit with manifest last,
and preserve original pin/enrollment provenance before any production effect.
"""
import copy
from dataclasses import dataclass
import hashlib
import json

SCHEMA = "mastermind.studio_fleet_status_successor_plan.v1"
MODULE = "fleet-status.mjs"
TARGET_SOURCE_SHA256 = "1a6fe88c8323be307dae487f0999606f2c69ee6fb7fd5e73ff4f6e308679ec92"
SOURCE_GENERATION = "full-owner-redacted-14-profile-20261103"
# Actual enrolled private manifest preimages, observed under original M2 owner.
# The current actor cannot select, invent or broaden a predecessor at runtime.
PREDECESSOR_MANIFEST_SHA256 = {
    "admin-business": "35903622d2e10b3ba56aedbf64cc2484d8b53bdb67ab71a8e0f9b0b7ebacc148",
    "chatgpt1": "f05c412f1a5e9076b5804aed547b1c85cfc9f00dcea0c4c2342698f20eac9aa1",
    "chatgpt2-business": "9f2f1cdecdd99b1673181b0109d8e6b11896d95541ad42d5e087fb64c2646d3b",
    "chatgpt2-personal": "b1b1232ae64417e9cf69d8f373c8c2978ed642ec72250470645a5cb39428e61a",
    "chatgpt3": "f826239592b62512dbbcd3f3546facc71e1d3696bdda150666711d50d6ae20f7",
    "chatgpt3-w570f6f34": "aa24bddbad7e989cedf566f4fbf4288fa333ee8fac8d2585cdcd9c954736eab3",
    "chatgpt3-wa2a9e6f9": "38d5427f418f9f3f7aa1ff671befa55555f276cd4b639a6312e24fa0672965a3",
    "chatgpt4": "3648a9a8e9711bab7be9fc7a3950f73579ce7d78358a18c15ac7d39adf924a9f",
}
LEGACY_MODULE_SHA256 = {
    "admin-business": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "chatgpt1": "cd9765636a2ac57572f1498f9be7235c953c33096c8f941e7672bb7880fbf78d",
    "chatgpt2-business": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "chatgpt2-personal": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "chatgpt3": "cd9765636a2ac57572f1498f9be7235c953c33096c8f941e7672bb7880fbf78d",
    "chatgpt3-w570f6f34": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "chatgpt3-wa2a9e6f9": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "chatgpt4": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
}


POST_MANIFEST_RAW_SHA256 = {
    'admin-business': '598c026d1e929f7a1ee801836b7aa3c966df20820e012cc0f39f63c2d980ef7f',
    'chatgpt1': 'd4e83dce983045adf043e4e38094c9b6e37ed818698ed935af9ede265a93afe1',
    'chatgpt2-business': '75ed6b2901c6ac617a8ada28d17a267ff66a89dd08f3c3f6f8c296ab856b8753',
    'chatgpt2-personal': '09d28e4c2ed0b3e7117238654eeacca646429eb8fdd6e24a0c9d44a7aa760f3e',
    'chatgpt3': '8261d40f1a0af3a1d8f05857179a9546b37dbce2eda9a6258c12a602be07caf4',
    'chatgpt3-w570f6f34': 'a017482a0e59e6f5d00573a001c56d0efb048172eb37c8f4a0ab6004c5b1c800',
    'chatgpt3-wa2a9e6f9': 'b23a413d3f313383ebbfb29b29769c04f358567c5b9337114549119312478f28',
    'chatgpt4': '97879f00020215c99c4e21f94d90bdd3defc13f5618a23aa05dec317c377dc6c',
}
POST_MANIFEST_CANONICAL_SHA256 = {
    'admin-business': 'd9ca87ef89e50860be8f2c7effddc839d301875f3431fd676d2ac05698026e46',
    'chatgpt1': 'b833bd5a2ac92e6da678a9eda85d14fc5e77149d6abc424baf45f3c41853dd92',
    'chatgpt2-business': '78a605519cd90d4be80295cd53b4900411dfa38e2424fbceb2b25398c0ccf12b',
    'chatgpt2-personal': 'b0c2f8dffbebf632cd3c722fe8fc33d39899a4ef13c77733ba04ba5a86079a1d',
    'chatgpt3': '49f24d7288ff77224fcf400db26b15766392ec3c22c4818ffc8a9175e0906b88',
    'chatgpt3-w570f6f34': '120a18f53a39dfc1e2c262b0b643d533eb3b378aa3b2b7d799fb609af814681a',
    'chatgpt3-wa2a9e6f9': '3126a0c147faaecc9d85e2de7edfb481cd273f282db3aa34710335e76b1c7cbd',
    'chatgpt4': '5eb80fb17723e995f6726044a82cdc5e91c654fa300dee58a14b1835ad05dfea',
}



class SourceRefused(ValueError):
    """Qualification failed, no file/process/manifest effect permitted."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_bytes(value, *, max_bytes=256 * 1024):
    if not isinstance(value, bytes) or not 1 <= len(value) <= max_bytes:
        raise SourceRefused("SOURCE_BYTES_UNQUALIFIED")
    return value


def manifest_from(raw):
    try:
        result = json.loads(strict_bytes(raw))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise SourceRefused("MANIFEST_UNQUALIFIED") from exc
    if not isinstance(result, dict) or not isinstance(result.get("files"), dict):
        raise SourceRefused("MANIFEST_UNQUALIFIED")
    return result


def encoded_manifest(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Preview:
    account: str
    manifest_before_sha256: str
    manifest_after_sha256: str
    module_before_sha256: str
    module_after_sha256: str
    config_sha256: str
    manifest_after_bytes: bytes
    no_runtime_effect: bool = True

    def public_receipt(self):
        return {
            "schema": SCHEMA,
            "generation": SOURCE_GENERATION,
            "account": self.account,
            "manifestBeforeSha256": self.manifest_before_sha256,
            "manifestAfterSha256": self.manifest_after_sha256,
            "moduleBeforeSha256": self.module_before_sha256,
            "moduleAfterSha256": self.module_after_sha256,
            "effect": "NOT_APPLIED",
            "runtimeReady": False,
            "sourceOwner": "private_service",
        }


def qualify_exact_predecessor(account, *, manifest_bytes, config_bytes,
                              module_before_bytes, source_module_bytes):
    """Pure exact observed cohort projection, not authority to modify a seat.

    The accepted source-owner caller must independently prove the original
    selected pin and any later Paper/C4 enrollment; this routine never
    accepts a caller-provided authentication flag or modifies files.
    """
    if not isinstance(account, str) or account not in PREDECESSOR_MANIFEST_SHA256:
        raise SourceRefused("ACCOUNT_UNQUALIFIED")
    strict_bytes(config_bytes)
    old = strict_bytes(module_before_bytes)
    future = strict_bytes(source_module_bytes)
    raw = strict_bytes(manifest_bytes)
    if digest(raw) != PREDECESSOR_MANIFEST_SHA256[account]:
        raise SourceRefused("PREDECESSOR_MANIFEST_CHANGED")
    if digest(old) != LEGACY_MODULE_SHA256[account]:
        raise SourceRefused("PREDECESSOR_MODULE_CHANGED")
    if digest(future) != TARGET_SOURCE_SHA256:
        raise SourceRefused("TARGET_SOURCE_NOT_ACCEPTED")
    manifest = manifest_from(raw)
    if (manifest.get("version") != 2
            or manifest.get("account") != account
            or manifest.get("label") != "com.mastermind.studio-direct-private." + account
            or manifest["files"].get(MODULE) != digest(old)
            or manifest.get("configHash") != digest(config_bytes)):
        raise SourceRefused("PREDECESSOR_IDENTITY_INVALID")
    # Before and after differ in exactly one source-module digest. Original
    # config, other files, plugin grants, node, backend and plist stay fixed.
    projected = copy.deepcopy(manifest)
    projected["files"][MODULE] = digest(future)
    updated = encoded_manifest(projected)
    canonical = digest(json.dumps(
        projected, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    if (digest(updated) != POST_MANIFEST_RAW_SHA256[account]
            or canonical != POST_MANIFEST_CANONICAL_SHA256[account]):
        raise SourceRefused("TARGET_COHORT_NOT_SEALED")
    if updated == raw:
        raise SourceRefused("NO_SOURCE_DELTA")
    observed = manifest_from(updated)
    if (observed["files"] != {**manifest["files"], MODULE: digest(future)}
            or any(observed[k] != manifest[k] for k in manifest if k != "files")):
        raise SourceRefused("PROJECTION_UNQUALIFIED")
    return Preview(
        account=account,
        manifest_before_sha256=digest(raw),
        manifest_after_sha256=digest(updated),
        module_before_sha256=digest(old),
        module_after_sha256=digest(future),
        config_sha256=digest(config_bytes),
        manifest_after_bytes=updated,
    )


def qualify_unchanged_transition(preview, *, manifest_before_bytes,
                                 module_before_bytes, config_bytes,
                                 manifest_after_bytes, module_after_bytes):
    """Re-qualify the original exact transition from immutable observations.

    Not a startup proof: the private pin/enrollment owner must still prove
    selected generation + original retained transaction and apply receipt.
    """
    if not isinstance(preview, Preview):
        raise SourceRefused("PREVIEW_UNQUALIFIED")
    if (digest(strict_bytes(manifest_before_bytes)) != preview.manifest_before_sha256
            or digest(strict_bytes(module_before_bytes)) != preview.module_before_sha256
            or digest(strict_bytes(config_bytes)) != preview.config_sha256
            or digest(strict_bytes(manifest_after_bytes)) != preview.manifest_after_sha256
            or digest(strict_bytes(module_after_bytes)) != preview.module_after_sha256
            or manifest_after_bytes != preview.manifest_after_bytes):
        raise SourceRefused("STATE_OR_SOURCE_CHANGED")
    return True

# One transaction under the EXISTING private-service owner and lifecycle lock.
# This module does not start, stop, repair or reselect any account.
import ctypes
import os
from pathlib import Path
import shutil
import sys
import tempfile
import re
import stat
import subprocess
from types import SimpleNamespace
from contextlib import contextmanager, nullcontext

TRANSACTION = "fleet-status-module-successor"
FILE_NAMES = frozenset((
    "plan.json", "intent.json", "result.json",
    "manifest.before", "manifest.after", "module.before", "module.after",
))
SOURCE_GIT_PATH = "integrations/studio_direct_mcp/fleet-status.mjs"


def fail(reason):
    raise SystemExit("FLEET_STATUS_SUCCESSOR_" + reason)


def _encode(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def _plan_digest(plan):
    return digest(_encode(plan))


def _protected_source(svc, commit):
    """Read module bytes ONLY from a verified ancestor of observed protected master."""
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        fail("RELEASE_COMMIT_UNQUALIFIED")
    repo = svc._user_root() / svc.TYPED_GIT_SOURCE_REPOSITORY_REL
    svc._assert_no_symlink_ancestors(repo)
    if not repo.is_dir():
        fail("SOURCE_REPO_MISSING")
    prefix = [svc.TYPED_GIT_BINARY, "--no-replace-objects", "-C",
              str(repo), "--git-dir", str(repo / ".git")]

    def git(*argv):
        try:
            r = subprocess.run(prefix + list(argv), check=False,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            fail("PROTECTED_SOURCE_UNAVAILABLE")
        if r.returncode:
            fail("PROTECTED_SOURCE_UNQUALIFIED")
        return r.stdout

    remote = git("remote", "get-url", "--all", "origin")
    if remote.decode("utf-8").splitlines() != [svc.TYPED_GIT_REMOTE_URL]:
        fail("PROTECTED_ORIGIN_CHANGED")
    observed = git("rev-parse", "--verify",
                   "refs/remotes/origin/master^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", observed):
        fail("PROTECTED_REF_INVALID")
    exact = git("rev-parse", "--verify", commit + "^{commit}").decode().strip()
    if exact != commit:
        fail("COMMIT_CHANGED")
    git("merge-base", "--is-ancestor", commit, observed)
    tree = git("ls-tree", "--full-tree", commit, "--", SOURCE_GIT_PATH).decode()
    match = re.fullmatch(r"100(?:644|755) blob ([0-9a-f]{40})\t" +
                         re.escape(SOURCE_GIT_PATH) + r"\n", tree)
    if not match:
        fail("SOURCE_BLOB_UNQUALIFIED")
    raw = git("cat-file", "blob", match.group(1))
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") +
                        b"\0" + raw).hexdigest()
    if (blob != match.group(1)
            or digest(strict_bytes(raw)) != TARGET_SOURCE_SHA256):
        fail("PROTECTED_SOURCE_CHANGED")
    return raw, observed


def _original_pin(svc, account, roots):
    """Re-read the original immutable selection evidence, never reselect it."""
    pin = svc._pin_owner_module()
    path = roots["state"] / "native-pool-pin"
    pin.directory(svc, path)
    original_plan = pin.decode(svc._fabric_release_bytes(path / "plan.json"))
    if (original_plan.get("schema") != pin.SCHEMA
            or original_plan.get("account") != account
            or original_plan.get("uid") != os.getuid()):
        fail("PIN_ORIGIN_INVALID")
    args = SimpleNamespace(
        account=account, expected_manifest_sha256=original_plan["manifest_before"],
        successor_bundle=original_plan["successor_bundle"],
        successor_plan_sha256=original_plan["successor_digest"],
        expected_plan_sha256=pin.plan_sha(svc, original_plan),
        operation="status",
    )
    with svc._pin_native_context(args) as binding:
        plan, retained = pin.read_transaction(svc, path, args, binding)
        expected = {"schema": pin.SCHEMA,
                    "planSha256": pin.plan_sha(svc, plan), "effect": "APPLIED"}
        result = pin.decode(svc._fabric_release_bytes(path / "result.json"))
        if (result != expected or binding.get("phase") != "SELECTED"
                or svc._stable_regular_file_hash(
                    Path(plan["pool_target"]), label="selected native pool")
                != plan["pool_bridge"]):
            fail("PIN_SELECTION_INVALID")
        original_pin_sha = pin.plan_sha(svc, plan)
    # C4 has a newer, separate selected repository-enrollment successor.
    # Check retained original evidence even after this source-only module
    # update; never skip the original selection or rewrite that receipt.
    if account == "chatgpt4":
        enrollment = svc._pin_enrollment_owner_module()
        ep = roots["state"] / enrollment.TRANSACTION
        if not ep.is_dir():
            fail("C4_ENROLLMENT_MISSING")
        profile = enrollment.frozen_profile("chatgpt4")
        with enrollment.original_pin(svc, roots, "status", profile) as (
                enpin, enoriginal, fingerprint):
            stored = enpin.decode(svc._fabric_release_bytes(ep / "plan.json"))
            eplan, eraw = enrollment.retained(
                svc, enpin, roots, ep,
                enrollment.digest(enrollment.encode(stored)),
                enoriginal, fingerprint, profile,
            )
            receipt = enpin.decode(svc._fabric_release_bytes(ep / "result.json"))
            if receipt != enrollment.result_record(eplan):
                fail("C4_ENROLLMENT_INVALID")
            # Original accepted enrollment modules are immutable; the
            # status module is NOT among enrollment.TARGET_FILES.
            for name, expected_hash in enrollment.TARGET_FILES.items():
                installed = svc._fabric_release_bytes(roots["base"] / name)
                if digest(installed) != expected_hash:
                    fail("C4_MODULE_DRIFT")
    return original_pin_sha


def _static_state(svc, account, roots, plan, raw):
    """Verify selected original bytes and the only three allowed write states."""
    if set(x.name for x in (roots["state"] / TRANSACTION).iterdir()) - FILE_NAMES:
        fail("FOREIGN_TRANSACTION")
    current_config = svc._fabric_release_bytes(roots["config"])
    if digest(current_config) != plan["configSha256"]:
        fail("CONFIG_CHANGED")
    for field, path in (
        ("module", roots["base"] / MODULE),
        ("manifest", roots["manifest"]),
    ):
        p = path.lstat()
        if (not stat.S_ISREG(p.st_mode) or p.st_uid != os.getuid()
                or stat.S_IMODE(p.st_mode) != plan[field + "Mode"]
                or p.st_nlink != 1):
            fail("FILE_MODE_CHANGED")
    state = (
        svc._fabric_release_bytes(roots["base"] / MODULE),
        svc._fabric_release_bytes(roots["manifest"]),
    )
    if state == (raw["module.before"], raw["manifest.before"]):
        phase = "OLD"
    elif state == (raw["module.after"], raw["manifest.before"]):
        phase = "MODULE_ONLY"
    elif state == (raw["module.after"], raw["manifest.after"]):
        phase = "COMMITTED"
    else:
        fail("FOREIGN_STATE")
    before = manifest_from(raw["manifest.before"])
    for name, h in before["files"].items():
        if name != MODULE and digest(svc._fabric_release_bytes(
                roots["base"] / name)) != h:
            fail("OTHER_MODULE_CHANGED")
    if (digest(svc._fabric_release_bytes(roots["plist"])) != before["plistHash"]
            or svc._stable_regular_file_hash(
                Path(before["node"]), label="preserved node") != before["nodeHash"]
            or svc._stable_regular_file_hash(
                Path(before["backend"]), label="preserved backend") != before["backendHash"]
            or svc._dependency_tree_hash(roots["node_modules"]) != before["dependencyTreeHash"]):
        fail("RUNTIME_CHANGED")
    if _original_pin(svc, account, roots) != plan["originalPinPlan"]:
        fail("ORIGINAL_PIN_CHANGED")
    return phase


def _source_plan(svc, args, roots):
    account = args.account
    if account not in PREDECESSOR_MANIFEST_SHA256:
        fail("ACCOUNT_NOT_ENROLLED")
    if args.expected_manifest_sha256 != PREDECESSOR_MANIFEST_SHA256[account]:
        fail("PREDECESSOR_CAS_INVALID")
    current = svc._verify_staged_install(
        account, "com.mastermind.studio-direct-private." + account,
        roots, require_runtime_seal=True)
    if current is None:
        fail("ORIGINAL_INSTALL_INVALID")
    source, observed = _protected_source(svc, args.release_commit)
    original = {
        "module.before": svc._fabric_release_bytes(roots["base"] / MODULE),
        "manifest.before": svc._fabric_release_bytes(roots["manifest"]),
    }
    future = qualify_exact_predecessor(
        account,
        manifest_bytes=original["manifest.before"],
        config_bytes=svc._fabric_release_bytes(roots["config"]),
        module_before_bytes=original["module.before"],
        source_module_bytes=source,
    )
    mp = roots["manifest"].lstat()
    md = (roots["base"] / MODULE).lstat()
    if (stat.S_IMODE(mp.st_mode) not in (0o400, 0o600)
            or stat.S_IMODE(md.st_mode) not in (0o400, 0o600)):
        fail("ORIGINAL_MODE_INVALID")
    pin_plan = _original_pin(svc, account, roots)
    plan = {
        "schema": SCHEMA, "generation": SOURCE_GENERATION,
        "account": account, "uid": os.getuid(),
        "releaseCommit": args.release_commit,
        "observedProtectedMaster": observed,
        "originalPinPlan": pin_plan,
        "configSha256": future.config_sha256,
        "manifestBeforeSha256": future.manifest_before_sha256,
        "manifestAfterSha256": future.manifest_after_sha256,
        "moduleBeforeSha256": future.module_before_sha256,
        "moduleAfterSha256": future.module_after_sha256,
        "manifestMode": stat.S_IMODE(mp.st_mode),
        "moduleMode": stat.S_IMODE(md.st_mode),
    }
    raw = {
        **original,
        "manifest.after": future.manifest_after_bytes,
        "module.after": source,
    }
    return plan, raw



@contextmanager
def _owned_directory_fd(svc, path):
    """Anchor a private owner directory; opening or syncing must never be ignored."""
    svc._assert_dest_safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != svc.DIR_MODE):
            fail("PUBLICATION_DIRECTORY_UNSAFE")
        yield fd
    finally:
        os.close(fd)


def _sync_directory(svc, path):
    with _owned_directory_fd(svc, path) as fd:
        os.fsync(fd)


def _identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino


def _same_identity(path, identity):
    try:
        return _identity(path) == identity
    except OSError:
        return False


def _rename_new(svc, source, destination):
    """Atomic no-replacement publication, retaining the single-link contract.

    Darwin renameatx_np(RENAME_EXCL=4), Linux renameat2(RENAME_NOREPLACE=1).
    Unsupported symbols/filesystems fail closed; ordinary rename is no fallback.
    """
    if sys.platform not in ("darwin", "linux"):
        fail("EXCLUSIVE_PUBLICATION_UNAVAILABLE")
    try:
        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, "renameatx_np" if sys.platform == "darwin" else "renameat2")
    except (AttributeError, OSError):
        fail("EXCLUSIVE_PUBLICATION_UNAVAILABLE")
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    svc._assert_dest_safe(source)
    svc._assert_dest_safe(destination)
    identity = _identity(source)
    with _owned_directory_fd(svc, source.parent) as source_fd:
        with _owned_directory_fd(svc, destination.parent) as destination_fd:
            if (source.name == destination.name
                    and _identity(source.parent) == _identity(destination.parent)):
                fail("PUBLICATION_IDENTITY_INVALID")
            flag = 4 if sys.platform == "darwin" else 1
            if rename(source_fd, os.fsencode(source.name), destination_fd,
                      os.fsencode(destination.name), flag) != 0:
                raise OSError(ctypes.get_errno(), "exclusive publication refused")
            if (not _same_identity(destination, identity)
                    or os.path.lexists(source)):
                fail("PUBLICATION_IDENTITY_UNKNOWN")
            # Confirm both the new name and removal of the old name. A failure
            # here occurs AFTER publication and must retain the final evidence.
            os.fsync(destination_fd)
            os.fsync(source_fd)


def _publish_intent(svc, account, roots, target, plan, raw):
    stage = Path(tempfile.mkdtemp(prefix=".fleet-status-intent.", dir=target.parent))
    identity = _identity(stage)
    attempted = False
    try:
        svc._fabric_release_new(stage / "plan.json", _encode(plan))
        for name, blob in raw.items():
            svc._fabric_release_new(stage / name, blob)
        svc._fabric_release_new(stage / "intent.json", _encode({
            "schema": SCHEMA, "planSha256": _plan_digest(plan)}))
        retained_plan, retained_raw, pd = _retained(svc, account, roots, stage)
        if (retained_plan != plan or retained_raw != raw or pd != _plan_digest(plan)):
            fail("PREPARED_INTENT_CHANGED")
        _sync_directory(svc, stage)
        attempted = True
        _rename_new(svc, stage, target)
    except BaseException:
        # A signal may arrive after rename but before any Python bookkeeping.
        # The source inode, not a post-call boolean, distinguishes that boundary.
        if attempted and not _same_identity(stage, identity):
            fail("EFFECT_UNKNOWN_PREPARATION_RECONCILE_SAME_OWNER")
        raise
    finally:
        # Never remove the final name or a replacement/foreign staging directory.
        if _same_identity(stage, identity):
            shutil.rmtree(stage)


def _publish_result(svc, target, value):
    # Keep temporary names outside the strict active-transaction file set.
    stage = Path(tempfile.mkdtemp(prefix=".fleet-status-result.", dir=target.parent))
    identity = _identity(stage)
    try:
        source = stage / "result.json"
        encoded = _encode(value)
        svc._fabric_release_new(source, encoded)
        if svc._fabric_release_bytes(source) != encoded:
            fail("PREPARED_RESULT_CHANGED")
        _sync_directory(svc, stage)
        _rename_new(svc, source, target / "result.json")
    finally:
        if _same_identity(stage, identity):
            shutil.rmtree(stage)


def _confirm_retained_durability(svc, roots, target):
    try:
        # Reconciliation may observe both installed postimages after a rename
        # whose directory sync failed. Confirm those parents even when no
        # replacement needs replay, including the existing-result/start path.
        for directory in dict.fromkeys((
                target, target.parent, roots["base"], roots["manifest"].parent)):
            _sync_directory(svc, directory)
    except BaseException:
        fail("EFFECT_UNKNOWN_DURABILITY_RECONCILE_SAME_OWNER")


def _retained(svc, account, roots, path):
    svc._assert_dest_safe(path)
    if not path.is_dir() or path.is_symlink():
        fail("TRANSACTION_UNAVAILABLE")
    files = {q.name for q in path.iterdir()}
    if files - FILE_NAMES or not FILE_NAMES - {"result.json"} <= files:
        fail("TRANSACTION_INCOMPLETE")
    plan = json.loads(svc._fabric_release_bytes(path / "plan.json"))
    if (plan.get("schema") != SCHEMA or plan.get("account") != account
            or plan.get("uid") != os.getuid()
            or plan.get("manifestBeforeSha256") != PREDECESSOR_MANIFEST_SHA256[account]
            or plan.get("moduleBeforeSha256") != LEGACY_MODULE_SHA256[account]
            or plan.get("manifestAfterSha256") != POST_MANIFEST_RAW_SHA256[account]
            or plan.get("moduleAfterSha256") != TARGET_SOURCE_SHA256
            or plan.get("generation") != SOURCE_GENERATION
            or plan.get("manifestMode") not in (0o400, 0o600)
            or plan.get("moduleMode") not in (0o400, 0o600)
            or not re.fullmatch(r"[0-9a-f]{40}", str(plan.get("releaseCommit", "")))):
        fail("RETAINED_PLAN_INVALID")
    digest_plan = _plan_digest(plan)
    intent = json.loads(svc._fabric_release_bytes(path / "intent.json"))
    if intent != {"schema": SCHEMA, "planSha256": digest_plan}:
        fail("INTENT_CHANGED")
    raw = {f: svc._fabric_release_bytes(path / f) for f in (
        "manifest.before", "manifest.after", "module.before", "module.after")}
    before = qualify_exact_predecessor(
        account, manifest_bytes=raw["manifest.before"],
        config_bytes=svc._fabric_release_bytes(roots["config"]),
        module_before_bytes=raw["module.before"],
        source_module_bytes=raw["module.after"],
    )
    if (digest(raw["manifest.after"]) != before.manifest_after_sha256
            or raw["manifest.after"] != before.manifest_after_bytes
            or plan["configSha256"] != before.config_sha256
            or plan["manifestBeforeSha256"] != before.manifest_before_sha256):
        fail("RETAINED_SOURCE_CHANGED")
    source, observed = _protected_source(svc, plan["releaseCommit"])
    if source != raw["module.after"]:
        fail("MERGED_SOURCE_CHANGED")
    return plan, raw, digest_plan


def _record(svc, plan, effect, phase, receipt, *, durable=False):
    return {
        "schema": SCHEMA, "generation": SOURCE_GENERATION,
        "account": plan["account"], "planSha256": _plan_digest(plan),
        "effect": effect, "phase": phase,
        "manifestSha256": plan["manifestAfterSha256"],
        "moduleSha256": plan["moduleAfterSha256"],
        "serviceStarted": False, "existingNativePinPreserved": True,
        "receiptCommitted": receipt, "durabilityConfirmed": durable,
        "retryAllowed": False,
    }


def _stopped(svc, account, roots):
    label = "com.mastermind.studio-direct-private." + account
    if svc._lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        fail("SERVICE_LOADED_STOP_FIRST")


def require_start(svc, account, roots):
    """Only a completed original-owner status successor may start."""
    path = roots["state"] / TRANSACTION
    if not os.path.lexists(path):
        return False
    plan, raw, pd = _retained(svc, account, roots, path)
    phase = _static_state(svc, account, roots, plan, raw)
    if (phase != "COMMITTED" or not os.path.lexists(path / "result.json")
            or json.loads(svc._fabric_release_bytes(path / "result.json"))
            != {"schema": SCHEMA, "planSha256": pd, "effect": "APPLIED"}):
        fail("START_NOT_COMMITTED")
    _confirm_retained_durability(svc, roots, path)
    svc._verify_staged_install(
        account, "com.mastermind.studio-direct-private." + account,
        roots, require_runtime_seal=True)
    return True


def run(svc, args):
    """Original private_service-owned preview/apply/status/reconcile; no stop/start."""
    if args.account not in PREDECESSOR_MANIFEST_SHA256:
        fail("ACCOUNT_NOT_ENROLLED")
    if args.operation not in ("preview", "apply", "status", "reconcile"):
        fail("OPERATION_REFUSED")
    roots = svc._build_runtime_roots(args.account)
    target = roots["state"] / TRANSACTION
    modifying = args.operation in ("apply", "reconcile")
    lock = svc._c2_lifecycle_mutex(args.account) if modifying else nullcontext()
    with lock:
        if args.operation in ("preview", "apply"):
            if os.path.lexists(target):
                fail("TRANSACTION_EXISTS_RECONCILE")
            if args.operation == "apply":
                _stopped(svc, args.account, roots)
            plan, raw = _source_plan(svc, args, roots)
            if args.operation == "preview":
                return _record(svc, plan, "NOT_APPLIED", "PREVIEW", False)
            if args.expected_plan_sha256 != _plan_digest(plan):
                fail("PLAN_CAS_INVALID")
            # Pre-dispatch: snapshot original service and all immutable inputs.
            _stopped(svc, args.account, roots)
            if (svc._fabric_release_bytes(roots["manifest"]) != raw["manifest.before"]
                    or svc._fabric_release_bytes(roots["base"] / MODULE) != raw["module.before"]):
                fail("PREIMAGE_CHANGED")
            svc._ensure_secure_dir(roots["state"])
            svc._assert_dest_safe(target)
            _publish_intent(svc, args.account, roots, target, plan, raw)
        plan, raw, pd = _retained(svc, args.account, roots, target)
        phase = _static_state(svc, args.account, roots, plan, raw)
        result = target / "result.json"
        has_result = os.path.lexists(result)
        if has_result:
            observed = json.loads(svc._fabric_release_bytes(result))
            if (observed != {"schema": SCHEMA, "planSha256": pd,
                             "effect": "APPLIED"} or phase != "COMMITTED"):
                fail("RESULT_OR_STATE_CHANGED")
        if args.operation == "status":
            return _record(svc, plan,
                           "APPLIED" if has_result else
                           "NOT_APPLIED" if phase == "OLD" else "PARTIAL",
                           phase, has_result)
        if has_result:
            _confirm_retained_durability(svc, roots, target)
            return _record(svc, plan, "APPLIED", phase, True, durable=True)
        if args.operation == "reconcile":
            _confirm_retained_durability(svc, roots, target)
        _stopped(svc, args.account, roots)
        changed = False
        try:
            for current, next_state, path, blob, mode in (
                ("OLD", "MODULE_ONLY", roots["base"] / MODULE,
                 raw["module.after"], plan["moduleMode"]),
                ("MODULE_ONLY", "COMMITTED", roots["manifest"],
                 raw["manifest.after"], plan["manifestMode"]),
            ):
                if phase != current:
                    continue
                _stopped(svc, args.account, roots)
                if _static_state(svc, args.account, roots, plan, raw) != current:
                    fail("STATE_MOVED")
                changed = True
                svc._atomic_write_bytes(path, blob, mode=mode)
                phase = _static_state(svc, args.account, roots, plan, raw)
                if phase != next_state:
                    fail("WRITE_NOT_OBSERVED")
            if phase != "COMMITTED":
                fail("UNCOMMITTED")
            svc._verify_staged_install(
                args.account, "com.mastermind.studio-direct-private." + args.account,
                roots, require_runtime_seal=True)
            _stopped(svc, args.account, roots)
            changed = True
            _publish_result(svc, target, {
                "schema": SCHEMA, "planSha256": pd, "effect": "APPLIED"})
            if not require_start(svc, args.account, roots):
                fail("START_GUARD_INVALID")
        except BaseException:
            if changed:
                fail("EFFECT_UNKNOWN_RECONCILE_SAME_OWNER")
            raise
        return _record(svc, plan, "APPLIED", "COMMITTED", True, durable=True)
