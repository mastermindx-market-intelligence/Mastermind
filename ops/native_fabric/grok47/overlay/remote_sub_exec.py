#!/usr/bin/env python3
"""Run one remote sub.sh task under the existing physical LaneLease.

This is not a scheduler. The Studio-side remote_sub.sh remains the placement and
provider-lease owner; this helper only closes the host-admission race between
telemetry selection and process start.
"""
from __future__ import annotations

import json
import hashlib
from contextlib import ExitStack
import os
import re
import selectors
import stat
import subprocess
import sys
from pathlib import Path
import native_remote
import time
from commission_deadline import (CommissionDeadlineExpired,
                                 narrow_deadline_ns, require_remaining)

from lane_runtime import (
    LaneAdmissionRefused,
    LaneLease,
    LaneRuntimeConfigError,
    LaneRuntimeError,
    OwnedProcessStartError,
    cleanup_receipt_is_proven,
    install_signal_cleanup,
    load_runtime_config,
    parse_bounded_seconds,
    run_owned_process,
)


def _fail(message: str, code: int) -> int:
    print(message, file=sys.stderr, flush=True)
    return code


def grok_plaintext_and_usage(raw: str, run_id: str, model: str):
    """Normalize one Grok headless JSON response using observed usage only.

    Legacy inert/older plain responders keep the exact plaintext result with
    unknown usage. Malformed structured results expose no JSON thought fields.
    """
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        # Non-JSON legacy plaintext is okay. A malformed structured payload
        # must not expose possible private reasoning on an error path.
        return ("", None) if raw.lstrip().startswith(("{", "[")) else (raw, None)
    if not isinstance(parsed, dict):
        return "", None
    text = parsed.get("text")
    if not isinstance(text, str):
        return "", None
    usage = parsed.get("usage")
    sid = parsed.get("sessionId")
    if not isinstance(usage, dict) or not isinstance(sid, str) or not 0 < len(sid) <= 256:
        return text, None
    names = ("input_tokens", "cache_read_input_tokens", "output_tokens", "total_tokens")
    if not all(type(usage.get(k)) is int and 0 <= usage[k] <= 2**53 for k in names):
        return text, None
    extra = usage.get("cache_creation_input_tokens", 0)
    if type(extra) is not int or not 0 <= extra <= 2**53:
        return text, None
    noncached, cached, output, observed_total = (usage[k] for k in names)
    full_input = noncached + cached + extra
    if full_input > 2**53 or full_input + output != observed_total:
        return text, None
    return text, {
        "schema": "mastermind.grok_usage.v1",
        "status": "observed",
        "reason": "native_headless_final",
        "session_ids": [sid],
        "input_tokens": full_input,
        "cached_tokens": cached,
        "output_tokens": output,
        "total_tokens": observed_total,
        "source": "grok_native_headless",
        "served_model": model,
        "run_id": run_id,
    }



def grok_output_binding(receipt, contract, manifest, raw_stdout, display_stdout, env, model):
    """Original producer binds normalized output; never backfills an old run."""
    import artifact_production
    if grok_plaintext_and_usage(raw_stdout, contract['run_id'], model)[0] != display_stdout:
        raise ValueError('grok_output_transform_mismatch')
    row = json.loads(Path(receipt).read_text().splitlines()[-1])
    raw = raw_stdout.encode('utf-8');normalized = display_stdout.encode('utf-8')
    if (row.get('schema') != 'mastermind.local_owned_process_receipt.v1'
            or row.get('label') != contract['run_id']
            or row.get('returncode') != 0 or row.get('timed_out') is not False
            or row.get('stdout_truncated') is not False or row.get('stderr_truncated') is not False
            or not cleanup_receipt_is_proven(row.get('cleanup') or {})
            or row.get('stdout_bytes') != len(raw)
            or row.get('stdout_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('grok_output_capture_unqualified')
    scope = {k:env.get(v,'') for k,v in {'root':'POOL_ORCHESTRATOR_ID',
        'parent':'POOL_PARENT_RUN_ID','run_id':'REMOTE_SUB_RUN_ID','host':'LANE_REMOTE_HOST',
        'lease_id':'POOL_LEASE_ID','account':'POOL_ACCOUNT','support_digest':'SUPPORT_DIGEST'}.items()}
    if any(scope[k] != contract[k] for k in ('root','parent','run_id','support_digest')):
        raise ValueError('grok_output_scope')
    if not all(native_remote.IDENT.fullmatch(scope[k]) for k in ('root','parent','run_id','host','lease_id','account')):
        raise ValueError('grok_output_scope')
    return dict(schema='mastermind.grok_normalized_output.v1', algorithm='grok_plaintext_and_usage_v1',
        **scope, mode='grok', model=model, raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_bytes=len(normalized),normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        contract=contract,manifest=manifest)


# The helper and its policy are independent, reviewed Git-blob pins. A source
# revision requires new review/test and an explicit update to these fences.
_MACRO_FABRIC_SPARSE_BLOB = "75297acb10d0cef4d01730a59fdcad19c7cfd3e6"
_MACRO_PREMERGE_SPARSE_BLOB = "296e47bab2d28f9a019e81b5aef76eeea62a6cc3"
_MACRO_PINNED_DONOR_COMMIT = "6ee058b0491a3f67e843f25d4379b94e98880e8b"
_MACRO_SPARSE_CONFIG_BLOB = "46b4d13bb5302a68b437a257eebe066d07bdc7ff"
# This is the pre-provisioned DONOR cone, not the new-worker exclude policy.
_MACRO_PINNED_DONOR_CONE = (".claude", ".codex", "config", "scripts")
_SPARSE_GIT_SETTINGS = (
    ("core.fsmonitor", "false"), ("core.hooksPath", "/dev/null"),
    ("core.untrackedCache", "false"), ("core.useReplaceRefs", "false"),
    ("maintenance.auto", "false"), ("gc.auto", "0"),
    ("protocol.allow", "never"),
)


class SparseWorkspaceRefused(ValueError):
    def __init__(self, reason: str, *, effect_unknown: bool = False):
        super().__init__(reason)
        self.effect_unknown = effect_unknown


def _sparse_stat(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid, info.st_gid)


def _sparse_owned_directory(path: Path) -> None:
    """Qualify the path up to this user's home; never change shared modes."""
    home = Path.home().resolve(strict=True)
    try:
        path.relative_to(home)
        if path.resolve(strict=True) != path:
            raise ValueError("noncanonical path")
        current = path
        while True:
            info = current.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022):
                raise ValueError("unqualified directory")
            if current == home:
                return
            current = current.parent
    except (OSError, RuntimeError, ValueError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_SOURCE_PATH_UNQUALIFIED") from exc


def _sparse_read(path: Path, limit: int = 131072) -> tuple[bytes, tuple]:
    """Bounded no-follow read with identity, mode and byte-length rechecks."""
    try:
        _sparse_owned_directory(path.parent)
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_mode & 0o022 or before.st_size > limit):
            raise ValueError("unqualified file")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _sparse_stat(opened) != _sparse_stat(before):
                raise ValueError("changed file")
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        if (len(content) != before.st_size or len(content) > limit
                or _sparse_stat(after) != _sparse_stat(before)
                or _sparse_stat(final) != _sparse_stat(before)):
            raise ValueError("changed file")
        return content, _sparse_stat(final)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_SOURCE_FILE_UNQUALIFIED") from exc


def _sparse_config(path: Path) -> tuple[dict, tuple | None]:
    """Read a strict data-only subset BEFORE Git can consult local config.

    No includes, aliases, command settings, filters, repository redirection or
    ambiguous Git syntax are accepted. Unknown keys refuse, even when their
    current value appears inert. This is not a general Git config parser.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        return {}, None
    except OSError as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_GIT_CONFIG_UNQUALIFIED") from exc
    data, identity = _sparse_read(path, 65536)
    bool_keys = {
        "core.filemode", "core.ignorecase", "core.precomposeunicode",
        "core.sparsecheckout", "core.sparsecheckoutcone", "core.trustctime",
        "core.preloadindex", "core.symlinks", "extensions.worktreeconfig",
        "index.sparse",
    }
    exact_values = {
        "core.repositoryformatversion": {"0", "1"}, "core.bare": {"false"},
        "core.logallrefupdates": {"true", "false", "always"},
        "core.autocrlf": {"false"}, "core.untrackedcache": {"false", "true"},
        "extensions.objectformat": {"sha1"}, "index.version": {"2", "3", "4"},
        "lfs.repositoryformatversion": {"0"},
    }
    found = {}
    section = ""
    try:
        for raw in data.decode("utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            match = re.fullmatch(r'\[([A-Za-z][A-Za-z0-9-]*)(?: "([A-Za-z0-9_./-]+)")?\]', line)
            if match:
                section = match[1].lower()
                if match[2] is not None:
                    if section not in {"remote", "branch"}:
                        raise ValueError("unsupported subsection")
                    section += "." + match[2] + "."
                else:
                    section += "."
                continue
            match = re.fullmatch(r"([A-Za-z][A-Za-z0-9-]*)\s*=\s*([^\\\x00-\x1f]*)", line)
            if not section or match is None:
                raise ValueError("unsupported syntax")
            key = section + match[1].lower()
            value = match[2].strip()
            # Reject quoting/comments/continuations rather than disagree with
            # Git about a value's boundary. These inputs are never rewritten.
            multivalue_fetch = section.startswith("remote.") and section.count(".") >= 2 and match[1].lower() == "fetch"
            if (not value or any(c in value for c in ('"', "#", ";"))
                    or (key in found and not multivalue_fetch)):
                raise ValueError("ambiguous value")
            if key in bool_keys:
                value = value.lower()
                if value not in {"true", "false"}:
                    raise ValueError("unsupported bool")
            elif key in exact_values:
                value = value.lower()
                if value not in exact_values[key]:
                    raise ValueError("unsupported value")
            elif key in {"user.name", "user.email"}:
                pass
            elif (section.startswith("remote.") and section.count(".") >= 2
                  and match[1].lower() in {"url", "pushurl", "fetch", "promisor", "partialclonefilter"}):
                # Existing donors are partial clones. These are data settings;
                # all transports remain disabled in controller and mint envs.
                if match[1].lower() == "promisor" and value.lower() not in {"true", "false"}:
                    raise ValueError("unsupported promisor value")
                if match[1].lower() == "partialclonefilter" and value != "blob:none":
                    raise ValueError("unsupported partial clone filter")
            elif (section.startswith("branch.") and section.count(".") >= 2
                  and match[1].lower() in {"remote", "merge"}):
                pass
            else:
                raise ValueError("unsupported key")
            found[key] = value
    except (UnicodeError, ValueError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_GIT_CONFIG_UNQUALIFIED") from exc
    return found, identity


def _sparse_git_context(root: Path, common: Path) -> tuple[Path, dict, tuple]:
    """Resolve linked Git metadata as data, without asking Git to trust it."""
    _sparse_owned_directory(root)
    _sparse_owned_directory(common)
    try:
        if root / ".git" == common:
            gitdir = common
        else:
            link, _ = _sparse_read(root / ".git", 4096)
            text = link.decode("utf-8").strip()
            if not text.startswith("gitdir: ") or "\n" in text:
                raise ValueError("gitfile")
            gitdir = (root / text[8:]).resolve(strict=True)
            if gitdir.parent != common / "worktrees":
                raise ValueError("unrelated gitdir")
            _sparse_owned_directory(gitdir)
            shared, _ = _sparse_read(gitdir / "commondir", 4096)
            if (gitdir / shared.decode("utf-8").strip()).resolve(strict=True) != common:
                raise ValueError("unrelated common dir")
            back, _ = _sparse_read(gitdir / "gitdir", 4096)
            if Path(back.decode("utf-8").strip()) != root / ".git":
                raise ValueError("backpointer")
        config, common_id = _sparse_config(common / "config")
        if common_id is None:
            raise ValueError("missing common config")
        worktree, worktree_id = _sparse_config(gitdir / "config.worktree")
        if config.get("extensions.worktreeconfig") == "true":
            config.update(worktree)
        return gitdir, config, (common_id, worktree_id)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        if isinstance(exc, SparseWorkspaceRefused):
            raise
        raise SparseWorkspaceRefused("FABRIC_SPARSE_GIT_METADATA_UNQUALIFIED") from exc


def _sparse_git_env(source: dict) -> dict:
    # The helper itself uses bare `git`; restrict its executable search too.
    env = {key: value for key, value in source.items()
           if not key.startswith(("GIT_", "LD_", "DYLD_"))}
    env.update({"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                # Empty allow-list disables every transport, including on
                # Git versions predating GIT_NO_LAZY_FETCH. Older Git may
                # create an internal fetch child, but cannot use a transport.
                "GIT_ALLOW_PROTOCOL": "",
                "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_COUNT": str(len(_SPARSE_GIT_SETTINGS))})
    for index, (key, value) in enumerate(_SPARSE_GIT_SETTINGS):
        env["GIT_CONFIG_KEY_" + str(index)] = key
        env["GIT_CONFIG_VALUE_" + str(index)] = value
    return env


def _sparse_git(root: Path, common: Path, *args: str,
                limit: int = 8192) -> bytes:
    """Read-only Git with bounded pipes and pre/post config qualification."""
    before = _sparse_git_context(root, common)
    command = ["/usr/bin/git", "--no-optional-locks", "--no-pager"]
    for key, value in _SPARSE_GIT_SETTINGS:
        command.extend(("-c", key + "=" + value))
    command.extend(("-C", str(root), *args))
    process = None
    observation_completed = False
    failure = None
    cleanup_failure = None
    output = b""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=_sparse_git_env(dict(os.environ)))
        buffers = [bytearray(), bytearray()]
        deadline = time.monotonic() + 12
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 0)
            selector.register(process.stderr, selectors.EVENT_READ, 1)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Git observation timeout")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buf = buffers[key.data]
                    if len(buf) + len(chunk) > (limit if key.data == 0 else 8192):
                        raise ValueError("Git observation too large")
                    buf.extend(chunk)
        rc = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        observation_completed = True
        if rc or buffers[1] or _sparse_git_context(root, common) != before:
            raise ValueError("Git observation unqualified")
        output = bytes(buffers[0])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        failure = exc
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired) as exc:
                cleanup_failure = exc
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except OSError as exc:
                    cleanup_failure = cleanup_failure or exc
    if cleanup_failure is not None:
        # Never let a finally-block exception unwind the physical lease as
        # though a process were proven gone. Retain the primary cause too.
        raise SparseWorkspaceRefused("FABRIC_SPARSE_GIT_CLEANUP_UNKNOWN",
                                     effect_unknown=True) from (failure or cleanup_failure)
    if failure is not None:
        if isinstance(failure, SparseWorkspaceRefused):
            raise failure
        # A forced observation abort reaps only our direct PID. In particular,
        # older partial-clone Git can have an internal fetch child even though
        # transports are denied. Preserve the lease until that scope is known.
        raise SparseWorkspaceRefused("FABRIC_SPARSE_GIT_OBSERVATION_UNQUALIFIED",
                                     effect_unknown=(process is not None and not observation_completed)) from failure
    return output


def _sparse_blob(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def _sparse_absent(root: Path, parts: tuple) -> bool:
    """Only ENOENT below real directories proves absence; links never do."""
    current = root
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return True
        except OSError as exc:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_INDEX_PATH_UNQUALIFIED") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022):
            return False
    return False


def _sparse_inputs(donor: Path, common: Path) -> dict:
    inputs = {}
    for name, expected in (("scripts/worktree_sparse.py", _MACRO_FABRIC_SPARSE_BLOB),
                           ("config/sparse_worktree.json", _MACRO_SPARSE_CONFIG_BLOB)):
        content, identity = _sparse_read(donor / name)
        if _sparse_blob(content) != expected:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_INPUT_BLOB_MISMATCH")
        head = _sparse_git(donor, common, "rev-parse", "--verify", "HEAD:" + name)
        record = _sparse_git(donor, common, "ls-files", "-v", "--stage", "-z", "--", name)
        accepted = {("H " + mode + " " + expected + " 0\t" + name + "\0").encode()
                    for mode in ("100644", "100755")}
        if head.strip() != expected.encode() or record not in accepted:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_INPUT_INDEX_UNQUALIFIED")
        inputs[name] = (content, identity)
    return inputs


def _qualify_sparse_donor(donor: Path, common: Path, *, pinned: bool) -> dict:
    gitdir, config, _ = _sparse_git_context(donor, common)
    if pinned and _sparse_git(donor, common, "rev-parse", "HEAD").strip() != _MACRO_PINNED_DONOR_COMMIT.encode():
        raise SparseWorkspaceRefused("FABRIC_SPARSE_REVIEWED_DONOR_UNQUALIFIED")
    inputs = _sparse_inputs(donor, common)
    cone = None
    if config.get("core.sparsecheckout") == "true":
        if config.get("core.sparsecheckoutcone") != "true":
            raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_PROFILE_UNQUALIFIED")
        if pinned:
            cone = set(_MACRO_PINNED_DONOR_CONE)
        else:
            trees = _sparse_git(donor, common, "ls-tree", "-d", "--name-only", "-z", "HEAD", limit=1048576)
            policy = json.loads(inputs["config/sparse_worktree.json"][0])
            cone = {os.fsdecode(p) for p in trees.split(b"\0") if p} - set(policy["exclude_dirs"])
        rules, _ = _sparse_read(gitdir / "info" / "sparse-checkout")
        expected = [b"/*", b"!/*/"] + sorted(("/" + p + "/").encode() for p in cone)
        if rules.splitlines() != expected:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_PROFILE_UNQUALIFIED")
    elif pinned:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_PROFILE_UNQUALIFIED")
    inventory = _sparse_git(donor, common, "ls-files", "-v", "--stage", "--sparse", "-z", limit=16777216)
    if not inventory.endswith(b"\0"):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_INDEX_UNQUALIFIED")
    for record in inventory[:-1].split(b"\0"):
        meta, tab, name = record.partition(b"\t")
        fields = meta.split(b" ")
        if (not tab or len(fields) != 4 or fields[0] not in {b"H", b"S"}
                or fields[3] != b"0"):
            # Lowercase tags include every assume-unchanged entry, even `s`.
            raise SparseWorkspaceRefused("FABRIC_SPARSE_INDEX_FLAGS_UNQUALIFIED")
        if fields[1] == b"160000":
            # Status can enter an initialized submodule whose local config is
            # outside the qualified common/worktree pair. Never recurse into
            # that separate trust boundary, including a staged Gitlink.
            raise SparseWorkspaceRefused("FABRIC_SPARSE_GITLINK_UNQUALIFIED")
        rel = os.fsdecode(name)
        parts = tuple(rel.rstrip("/").split("/"))
        if not parts or any(p in {"", ".", ".."} for p in parts):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_INDEX_PATH_UNQUALIFIED")
        if fields[0] == b"S":
            directory = fields[1] == b"040000" and rel.endswith("/")
            if (cone is None or parts[0] in cone
                    or (len(parts) == 1 and not directory)
                    or not _sparse_absent(donor, parts)):
                raise SparseWorkspaceRefused("FABRIC_SPARSE_INDEX_FLAGS_UNQUALIFIED")
    if (_sparse_git(donor, common, "status", "--porcelain=v1", "--untracked-files=all")
            or _sparse_git(donor, common, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_REVIEWED_DONOR_UNQUALIFIED")
    return inputs


def _clean_linked_sparse_donor(original: Path) -> Path:
    """Qualify the pre-provisioned linked donor without mutating either tree."""
    alternate = original.parent / "macro-fabric-pinned-20261016"
    common = original / ".git"
    _qualify_sparse_donor(alternate, common, pinned=True)
    return alternate


def _new_macro_workspace(key: str, cwd: str, here: Path, env: dict,
                         config) -> str:
    """Optional pre-mint within the incumbent LaneLease, before worker START.

    No parallel worker/queue/authority is created. This controller does not
    remove or reuse a checkout. Uncertain effects retain the incumbent lease
    for reconciliation; the pinned mint helper owns its own failure cleanup.
    """
    commit = os.environ.get("FABRIC_NEW_MACRO_COMMIT", "")
    if not commit:
        return cwd
    if (re.fullmatch(r"[0-9a-f]{40}", commit) is None
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", key) is None
            or os.environ.get("REMOTE_SUB_RUN_ID") != key
            or not os.environ.get("POOL_ORCHESTRATOR_ID")
            or not os.environ.get("POOL_PARENT_RUN_ID")
            or not os.environ.get("POOL_LEASE_ID")):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_SCOPE_REFUSED")
    donor = Path.home() / "lanes" / "repos" / "macro"
    original_donor = donor
    common = original_donor / ".git"
    try:
        if Path(cwd).resolve(strict=True) != donor.resolve(strict=True):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_REFUSED")
    except (OSError, RuntimeError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_UNAVAILABLE") from exc
    # Only this exact old helper qualifies for selection of the existing
    # linked source. Unknown source cannot silently reroute to a good donor.
    for attempt in (0, 1):
        helper = donor / "scripts" / "worktree_sparse.py"
        try:
            content, identity = _sparse_read(helper)
        except SparseWorkspaceRefused as exc:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_UNQUALIFIED") from exc
        blob = _sparse_blob(content)
        if attempt == 0 and blob == _MACRO_PREMERGE_SPARSE_BLOB:
            donor = _clean_linked_sparse_donor(original_donor)
            continue
        if blob != _MACRO_FABRIC_SPARSE_BLOB:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_BLOB_MISMATCH")
        break
    destination = Path.home() / "lanes" / "wt" / key
    if os.path.lexists(destination):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_DESTINATION_EXISTS")
    receipt = here / "lanes" / (key + ".workspace-mint.process.jsonl")
    if os.path.lexists(receipt):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_RECEIPT_EXISTS")
    try:
        if _sparse_read(helper) != (content, identity):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED")
    except SparseWorkspaceRefused as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED") from exc
    try:
        inputs = _qualify_sparse_donor(donor, common, pinned=donor != original_donor)
    except SparseWorkspaceRefused as exc:
        # Qualification raises on drift; comparing its deterministic return
        # path could never reach the old DONOR_DRIFT branch.
        if donor != original_donor:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_REVIEWED_DONOR_DRIFT",
                                         effect_unknown=exc.effect_unknown) from exc
        raise
    try:
        if _sparse_read(helper) != (content, identity):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED")
    except SparseWorkspaceRefused as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED") from exc
    # -I excludes the script directory, PYTHONPATH and user site. It does not
    # exclude interpreter site-packages/sitecustomize or lock same-UID writers.
    # Only this approved owner invocation receives the one-shot flag and Git
    # environment; root/parent/provider/lease fields and the worker env survive.
    mint_env = _sparse_git_env(env)
    mint_env["MASTERMIND_FABRIC_SPARSE_NEW"] = "1"
    try:
        result = run_owned_process(
            [sys.executable, "-I", str(helper), "fabric-mint", key, commit],
            cwd=str(donor), timeout=180.0, env=mint_env, nice=config.nice,
            label=key + ":workspace-mint", receipt_path=receipt,
            timeout_returncode=124,
        )
    except (OSError, ValueError, LaneRuntimeError, OwnedProcessStartError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_EFFECT_UNKNOWN",
                                     effect_unknown=True) from exc
    if (result.returncode != 0 or result.timed_out
            or not result.cleanup_proven or result.stdout_truncated
            or result.stderr_truncated):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_UNVERIFIED",
                                     effect_unknown=True)
    for name, expected in inputs.items():
        reason = ("FABRIC_SPARSE_HELPER_EFFECT_UNKNOWN" if name.startswith("scripts/")
                  else "FABRIC_SPARSE_POLICY_EFFECT_UNKNOWN")
        try:
            if _sparse_read(donor / name) != expected:
                raise SparseWorkspaceRefused(reason, effect_unknown=True)
        except SparseWorkspaceRefused as exc:
            raise SparseWorkspaceRefused(reason, effect_unknown=True) from exc

    def git_value(root: Path, *args: str) -> str:
        try:
            return _sparse_git(root, common, *args).decode("utf-8").strip()
        except (SparseWorkspaceRefused, UnicodeError) as exc:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_VERIFY_UNKNOWN",
                                         effect_unknown=True) from exc

    try:
        dstat = destination.lstat()
        gstat = (destination / ".git").lstat()
        donor_git = Path(git_value(donor, "rev-parse", "--path-format=absolute",
                                   "--git-common-dir")).resolve(strict=True)
        gitdir = Path(git_value(destination, "rev-parse", "--path-format=absolute",
                                "--git-dir")).resolve(strict=True)
        if (not stat.S_ISDIR(dstat.st_mode) or destination.is_symlink()
                or dstat.st_uid != os.getuid()
                or not stat.S_ISREG(gstat.st_mode)
                or (destination / ".git").is_symlink()
                or gitdir.parent != donor_git / "worktrees"
                or git_value(destination, "rev-parse", "HEAD") != commit
                or git_value(destination, "branch", "--show-current") != "lane/" + key
                or git_value(destination, "config", "--get", "core.sparseCheckout") != "true"
                or git_value(destination, "status", "--porcelain=v1", "-uall")):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_POSTCONDITION_REFUSED",
                                         effect_unknown=True)
    except (OSError, RuntimeError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_POSTCONDITION_UNKNOWN",
                                     effect_unknown=True) from exc
    return str(destination)


def _bound_lane_packet(key, mode, packet_path, cwd, here, env):
    """Recheck the v2 transport's physical layout before any worker invocation.

    The controller alone selects this tuple from the existing host registry.
    This check does not turn correlation metadata into authentication.
    """
    token = env.get('REMOTE_SUB_LANE_ROOT_LAYOUT')
    if token in (None, '-'):
        return None
    import base64
    import artifact_delivery as delivery
    import artifact_reader
    if (type(token) is not str or len(token) > 16384
            or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', token)
            or mode not in {'glm', 'qwen'} or cwd != '~'
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', key)
            or not env.get('POOL_ORCHESTRATOR_ID') or not env.get('POOL_PARENT_RUN_ID')
            or env.get('FABRIC_NEW_MACRO_COMMIT')
            or env.get('FABRIC_CPU_SCOPE_QUOTA_PCT')
            or env.get('FABRIC_OPERATOR_CAPSULE') or env.get('FABRIC_OPERATOR_CAPABILITY')
            or env.get('FABRIC_OPERATOR_CHILD_ID')
            or env.get('FABRIC_OPERATOR_PRELEASE_CONTINUATION')
            or env.get('FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION')):
        raise ValueError('REMOTE_SUB_LANE_ROOT_SCOPE_REFUSED')
    layout = delivery.validate_remote_lane_layout(artifact_reader.strict_json(
        base64.b64decode(token, altchars=b'-_', validate=True)))
    binding = layout['binding']
    if binding['host'] != env.get('LANE_REMOTE_HOST'):
        raise ValueError('REMOTE_SUB_LANE_ROOT_HOST_REFUSED')
    lane_root = Path(binding['path'])
    support = env.get('SUPPORT_DIGEST', '')
    if (not re.fullmatch(r'[a-f0-9]{64}', support)
            or packet_path != lane_root / 'tmp' / (key + '.txt')
            or here != lane_root / 'support-releases' / support / 'ext'):
        raise ValueError('REMOTE_SUB_LANE_ROOT_PATH_REFUSED')
    delivery.observe_remote_lane_layout(binding, layout)
    packet = delivery.strict_remote_lane_file(packet_path, 2 * 1024 * 1024)
    expected = env.get('REMOTE_SUB_LANE_PACKET_SHA256', '')
    if (not re.fullmatch(r'[a-f0-9]{64}', expected)
            or hashlib.sha256(packet).hexdigest() != expected
            or packet.startswith(b'FABRIC_ARTIFACT_REQUEST_V1 ')):
        raise ValueError('REMOTE_SUB_LANE_ROOT_PACKET_REFUSED')
    meta = artifact_reader.strict_json(delivery.strict_remote_lane_file(
        here.parent / 'RELEASE.json', 65536, mode=0o444))
    files = meta.get('files') if type(meta) is dict else None
    if (type(files) is not dict or not 1 <= len(files) <= 256
            or meta.get('digest') != support
            or hashlib.sha256(json.dumps({'schema': 'remote-support-code.v1', 'files': files},
                sort_keys=True, separators=(',', ':')).encode()).hexdigest() != support):
        raise ValueError('REMOTE_SUB_LANE_ROOT_SUPPORT_REFUSED')
    delivery.verify_remote_lane_release(layout, support, meta)
    for name, wanted in files.items():
        if (type(name) is not str or not name or Path(name).name != name
                or type(wanted) is not str or not re.fullmatch(r'[a-f0-9]{64}', wanted)
                or hashlib.sha256(delivery.strict_remote_lane_file(
                    here / name, 2 * 1024 * 1024, mode=0o555)).hexdigest() != wanted):
            raise ValueError('REMOTE_SUB_LANE_ROOT_SUPPORT_REFUSED')
    delivery.verify_remote_lane_release(layout, support, meta)
    delivery.observe_remote_lane_layout(binding, layout)
    return layout, packet


def _execute(argv: list[str], state: dict) -> int:
    if len(argv) != 6:
        return _fail(
            "usage: remote_sub_exec.py <key> <mode> <packet> <cwd> <model>", 2
        )
    _, key, mode, packet, cwd, model = argv
    # The controller sends a duration immediately before this transport's
    # launch, never its monotonic clock. Anchor in this host's own clock at
    # executor entry so admission/preparation cannot refresh the worker fuse.
    commission_budget = os.environ.get('REMOTE_SUB_COMMISSION_BUDGET_SECONDS')
    if commission_budget is not None:
        if (mode not in {'glm', 'glm-codex', 'minimax', 'minimax-codex', 'qwen'}
                or not re.fullmatch(r'[1-9][0-9]{0,3}', commission_budget)
                or int(commission_budget) > 7200):
            return _fail('REMOTE_SUB_COMMISSION_BUDGET_INVALID', 78)
        state['commission_deadline_ns'] = narrow_deadline_ns(
            None, int(commission_budget), now_ns=state['entered_monotonic_ns'])
    here = Path(__file__).resolve().parent
    packet_path = Path(packet)
    try:
        bound_packet = _bound_lane_packet(key, mode, packet_path, cwd, here, os.environ)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _fail("REMOTE_SUB_LANE_ROOT_REFUSED before_worker=1", 78)
    if not packet_path.is_file():
        return _fail("REMOTE_SUB_PACKET_MISSING", 2)
    try:
        prompt = (bound_packet[1].decode("utf-8") if bound_packet is not None
                  else packet_path.read_text(encoding="utf-8"))
    except OSError:
        return _fail("REMOTE_SUB_PACKET_UNREADABLE", 2)

    artifact_contract = None
    if prompt.startswith("FABRIC_ARTIFACT_REQUEST_V1 "):
        try:
            import artifact_production
            artifact_contract = artifact_production.parse_packet(prompt)
            artifact_production.bind(artifact_contract, key, mode, os.environ, here)
        except (ImportError, ValueError, TypeError, KeyError, RecursionError):
            return _fail("ARTIFACT_DELIVERY_CONTRACT_REFUSED", 65)
    artifact_failure = False

    # Tilde belongs to this host, not to the controller that selected it.
    if cwd.startswith("~") and cwd != "~" and not cwd.startswith("~/"):
        return _fail("REMOTE_SUB_CWD_REFUSED", 2)
    try:
        cwd = str(Path(cwd).expanduser())
        if not Path(cwd).is_dir():
            return _fail("REMOTE_SUB_CWD_MISSING", 2)
    except (OSError, RuntimeError):
        return _fail("REMOTE_SUB_CWD_UNREADABLE", 2)

    if mode in native_remote.MODES:
        try:
            native_remote.scope(key, mode, model, here, os.environ, timing=state.get("timing"))
        except (ValueError, OSError) as exc:
            return _fail(str(exc), 78)

    try:
        timeout = parse_bounded_seconds(
            os.environ.get("REMOTE_SUB_CHILD_TIMEOUT"),
            default=7000.0,
            minimum=0.05,
            maximum=7200.0,
            key="REMOTE_SUB_CHILD_TIMEOUT",
        )
    except LaneRuntimeConfigError as exc:
        return _fail("REMOTE_SUB_PREFLIGHT_REFUSED " + str(exc), 78)

    config = load_runtime_config(os.environ, cpu_count=os.cpu_count() or 1)
    install_signal_cleanup()
    state_ext = (Path(bound_packet[0]["binding"]["path"]) / "ext"
                 if bound_packet is not None else here)
    active_dir = state_ext / "active"
    try:
        lease = LaneLease.acquire(
            active_dir,
            key=key,
            label=key,
            env=os.environ,
            reconcile_unreleased=True,
        )
    except LaneAdmissionRefused as exc:
        payload = json.dumps(
            exc.snapshot.public_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return _fail("REMOTE_SUB_ADMISSION_REFUSED " + payload, 75)
    except LaneRuntimeError as exc:
        return _fail("REMOTE_SUB_ADMISSION_ERROR " + type(exc).__name__, 78)

    if 'commission_deadline_ns' in state:
        try:
            timeout = min(timeout, require_remaining(state['commission_deadline_ns'], minimum_seconds=0.05))
        except CommissionDeadlineExpired:
            lease.release()
            return _fail('REMOTE_SUB_COMMISSION_TIME_EXHAUSTED before_worker=1 stage=admission', 75)

    # Prompt bytes must not consume the operating system's per-argument limit.
    # The already-delivered file stays inside the existing per-run transport.
    packet_for_worker = packet_path if bound_packet is not None else packet_path.resolve()
    if mode in ("glm", "minimax", "qwen"):
        command = ["bash", str(here / "sub.sh"), "--prompt-file", mode, str(packet_for_worker), cwd]
    else:
        command = ["bash", str(here / "sub.sh"), mode, prompt, cwd]
    if model:
        command.append(model)
    if mode in native_remote.MODES:
        command = native_remote.command(mode, model, prompt, cwd, packet_path=packet_path.resolve())
    lanes_dir = state_ext / "lanes"
    child_env = dict(os.environ)
    if 'commission_deadline_ns' in state:
        # This envelope belongs to this executor, not to worker-created tasks.
        child_env.pop('REMOTE_SUB_COMMISSION_BUDGET_SECONDS', None)
        child_env.pop('POOL_COMMISSION_DEADLINE_NS', None)
    child_env.pop('FABRIC_OPERATOR_CAPABILITY', None)
    if child_env.get('FABRIC_OPERATOR_CAPSULE'):
        from fabric_operator_client import load_operator_environment
        try:
            child_env = load_operator_environment(child_env, key, mode, model, packet_path.read_bytes())
        except (OSError, ValueError, TypeError):
            lease.release()
            return _fail("OPERATOR_CAPSULE_REFUSED", 78)
    child_env["POOL_USAGE_FILE"] = str(lanes_dir / f"{key}.usage.json")
    child_env["POOL_USAGE_RUN_ID"] = key
    child_env["POOL_OUTCOME_FILE"] = str(lanes_dir / f"{key}.provider.json")
    if mode in native_remote.MODES:
        timeout = min(timeout, float(os.environ["NATIVE_LEASE_DEADLINE"])-time.time())
        if timeout <= 0:
            lease.release()
            return _fail("native_remote_lease_expired", 78)
    receipt = lanes_dir / f"{key}.process.jsonl"
    diagnostic_reader = None
    if child_env.get('FABRIC_OPERATOR_CAPABILITY'):
        from fabric_operator_diagnostics import collect
        diagnostic_reader = lambda: collect(here, key)
    try:
        with lease, ExitStack() as artifact_stack:
            artifact_owner = (artifact_stack.enter_context(artifact_production.NewDirectory(artifact_contract))
                              if artifact_contract is not None else None)
            if bound_packet is not None:
                try:
                    current_packet = _bound_lane_packet(
                        key, mode, packet_path, '~', here, child_env)
                    if current_packet != bound_packet:
                        raise ValueError('REMOTE_SUB_LANE_ROOT_PACKET_CHANGED')
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    lease.hold_for_reconciliation('remote_lane_root_changed')
                    return _fail("REMOTE_SUB_LANE_ROOT_REFUSED after_admission=1", 76)
            # Physical admission + original provider lease already succeeded.
            # Mint only this explicitly NEW, pinned workspace before worker START.
            try:
                cwd = _new_macro_workspace(key, cwd, here, child_env, config)
            except SparseWorkspaceRefused as exc:
                if exc.effect_unknown:
                    lease.hold_for_reconciliation("sparse_workspace_effect_unknown")
                return _fail(str(exc), 76 if exc.effect_unknown else 78)
            child_env.pop("MASTERMIND_FABRIC_SPARSE_NEW", None)
            child_env.pop("FABRIC_NEW_MACRO_COMMIT", None)
            if os.environ.get("FABRIC_NEW_MACRO_COMMIT"):
                child_env["FABRIC_WORKSPACE_READY"] = "1"
                child_env["FABRIC_WORKSPACE_RUN_ID"] = key
            # Do not alter any ordinary/legacy worker argv. Only a qualified
            # brand-new sparse checkout needs its CWD rebound before START.
            if os.environ.get("FABRIC_NEW_MACRO_COMMIT"):
                if mode in ("glm", "minimax", "qwen"):
                    command = ["bash", str(here / "sub.sh"), "--prompt-file", mode,
                               str(packet_path.resolve()), cwd]
                else:
                    command = ["bash", str(here / "sub.sh"), mode, prompt, cwd]
                if model:
                    command.append(model)
                if mode in native_remote.MODES:
                    command = native_remote.command(
                        mode, model, prompt, cwd, packet_path=packet_path.resolve()
                    )
            if mode in native_remote.MODES:
                child_env = native_remote.environment(mode, model, key, here, child_env)
            # Worker-spawned shell tools inherit PATH. The immutable, reviewed
            # "yes" shim bounds CPU-stealer lifetime even when an agent leaves
            # an unbounded background "taskset ... yes" shell running.
            if sys.platform.startswith("linux"):
                guard = here / "yes"
                if (not guard.is_file() or guard.is_symlink()
                        or not os.access(guard, os.X_OK)):
                    return _fail("FABRIC_CPU_STRESS_GUARD_UNAVAILABLE", 78)
                child_env["PATH"] = str(here) + os.pathsep + child_env.get("PATH", "/usr/bin:/bin")
            # Optional CPU fan-out budget is subordinate to the incumbent
            # physical LaneLease, not a replacement owner or a new worker.
            cpu_scope = None
            if child_env.get("FABRIC_CPU_SCOPE_QUOTA_PCT"):
                try:
                    import fabric_cpu_scope
                except ImportError:
                    return _fail("FABRIC_CPU_SCOPE_LIBRARY_UNAVAILABLE", 78)
                try:
                    cpu_scope = fabric_cpu_scope.prepare_scope(key, mode, command, child_env)
                except fabric_cpu_scope.CpuScopeRefused:
                    return _fail("FABRIC_CPU_SCOPE_PRESTART_REFUSED", 78)
                except fabric_cpu_scope.CpuScopeEffectUnknown:
                    lease.hold_for_reconciliation("cpu_scope_prestart_unknown")
                    return _fail("FABRIC_CPU_SCOPE_EFFECT_UNKNOWN", 76)
                if cpu_scope is not None:
                    command = list(cpu_scope.command)
                    child_env = dict(cpu_scope.env)
            install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)
            try:
                if 'commission_deadline_ns' in state:
                    try:
                        timeout = min(timeout, require_remaining(state['commission_deadline_ns'], minimum_seconds=0.05))
                    except CommissionDeadlineExpired:
                        return _fail('REMOTE_SUB_COMMISSION_TIME_EXHAUSTED before_worker=1 stage=launch', 75)
                state["started"] = True
                result = run_owned_process(
                    command,
                    cwd=cwd,
                    timeout=timeout,
                    env=child_env,
                    nice=config.nice,
                    label=key,
                    receipt_path=receipt,
                    timeout_returncode=124,
                    receipt_diagnostics=diagnostic_reader,
                )
            except OwnedProcessStartError as exc:
                state["started"] = False
                number = str(exc.error_number) if exc.error_number is not None else "unknown"
                return _fail("REMOTE_SUB_EXEC_NOT_STARTED errno=" + number, 78)
            finally:
                # run_owned_process owns the original process GROUP. When a
                # child calls setsid(), it can leave that group and survive
                # cleanup_proven=true. The original worker lease must not be
                # released until the exact quota cgroup also has no PIDs.
                if cpu_scope is not None and state["started"]:
                    try:
                        state["cpu_scope_settlement"] = fabric_cpu_scope.settle_scope(cpu_scope)
                    except fabric_cpu_scope.CpuScopeEffectUnknown:
                        state["cpu_scope_effect_unknown"] = True
                        lease.hold_for_reconciliation("cpu_scope_cleanup_unproven")
                    except (OSError, ValueError, TypeError):
                        state["cpu_scope_effect_unknown"] = True
                        lease.hold_for_reconciliation("cpu_scope_cleanup_unproven")
                if state["started"]:
                    proven = False
                    try:
                        row = json.loads(receipt.read_text().splitlines()[-1])
                        proven = row.get("label") == key and cleanup_receipt_is_proven(row.get("cleanup", {}))
                    except (OSError, ValueError, IndexError):
                        pass
                    if not proven:
                        lease.hold_for_reconciliation("worker_cleanup_unproven")
            if state.get("cpu_scope_effect_unknown"):
                return _fail("REMOTE_CPU_SCOPE_UNSETTLED", 76)

            display_stdout = result.stdout
            if mode == "grok":
                # Normalize even when the provider rc is nonzero. Never
                # echo structured JSON including its private thought field.
                display_stdout, usage_record = grok_plaintext_and_usage(result.stdout, key, model)
                if (usage_record is not None and result.returncode == 0
                        and result.cleanup_proven
                        and not result.stdout_truncated and not result.stderr_truncated):
                    usage_file = Path(child_env["POOL_USAGE_FILE"])
                    try:
                        fd = os.open(usage_file,
                                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(fd, "w") as output:
                            json.dump(usage_record, output, sort_keys=True)
                            output.write("\n")
                            output.flush()
                            os.fsync(output.fileno())
                    except OSError:
                        # Metering failure is unknown usage, never invented spend
                        # and never a reason to replay a completed provider call.
                        pass
            if (artifact_contract is not None and result.returncode == 0
                    and result.cleanup_proven and not result.stdout_truncated and not result.stderr_truncated):
                try:
                    manifest = artifact_production.verify_completion(
                        artifact_contract, artifact_owner, display_stdout, child_env["LANE_REMOTE_HOST"])
                    if mode == "grok":
                        state['output_binding'] = grok_output_binding(
                            receipt, artifact_contract, manifest, result.stdout, display_stdout, child_env, model)
                    if mode in artifact_production.ORDINARY_MODES:
                        artifact_production.record_ordinary_completion(
                            receipt, artifact_contract, manifest, result.stdout, mode=mode)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    artifact_failure = True

    except (LaneRuntimeError, OSError, ValueError) as exc:
        if state.get("started"):
            return _fail("REMOTE_CLEANUP_UNPROVEN " + type(exc).__name__, 76)
        return _fail("REMOTE_SUB_RUNTIME_ERROR " + type(exc).__name__, 78)

    if display_stdout:
        sys.stdout.write(display_stdout)
        sys.stdout.flush()
    # A successful worker's stderr is transport/diagnostic chatter, not its
    # return value. Keep it out of the parent result. On any worker/result/
    # cleanup failure, preserve the bounded stderr so diagnosis remains visible.
    result_failed = (
        int(result.returncode) != 0
        or not result.cleanup_proven
        or result.stdout_truncated
        or result.stderr_truncated
    )
    if result.stderr and result_failed:
        sys.stderr.write(result.stderr)
        sys.stderr.flush()
    if not result.cleanup_proven:
        return _fail("REMOTE_CLEANUP_UNPROVEN", 76)
    if result.stdout_truncated or result.stderr_truncated:
        marker = "NATIVE_CAPTURE_TRUNCATED" if mode in native_remote.MODES else "REMOTE_CAPTURE_TRUNCATED"
        return _fail(marker, 76)
    if artifact_failure:
        return _fail("ARTIFACT_DELIVERY_CONTRACT_FAILED", 65)
    return int(result.returncode)


def main(argv: list[str]) -> int:
    state = {"started": False, "entered_monotonic_ns": time.monotonic_ns()}
    if len(argv) == 6 and argv[2] in native_remote.MODES:
        state["timing"] = {"remote_exec_entered_at": time.time()}
    is_go = len(argv) == 6 and argv[2] == "go-codex"
    rc = 78
    try:
        rc = _execute(argv, state)
        return rc
    except BaseException as exc:
        if isinstance(exc, SystemExit) and isinstance(exc.code, int):
            rc = exc.code
        raise
    finally:
        if len(argv) == 6 and argv[2] in native_remote.MODES:
            native_remote.terminal(Path(__file__).resolve().parent, argv[1], argv[2], argv[5], os.environ, state["started"], rc, timing=state.get("timing"), output_binding=state.get("output_binding"))
        if is_go:
            from lane_runtime import cleanup_receipt_is_proven
            from go_remote_capsule import IDENT
            key = argv[1]
            if not IDENT.fullmatch(key):
                raise ValueError("invalid run key")
            names = {"root":"POOL_ORCHESTRATOR_ID", "lease_id":"POOL_LEASE_ID",
                     "account":"POOL_ACCOUNT", "run_id":"REMOTE_SUB_RUN_ID",
                     "host":"LANE_REMOTE_HOST"}
            scope = {k:os.environ.get(v, "") for k,v in names.items()}
            scope["model"] = argv[5]
            if scope["run_id"] != key or not all(IDENT.fullmatch(v) for v in scope.values()):
                raise ValueError("invalid worker scope")
            folder = Path(__file__).resolve().parent / "lanes"
            folder.mkdir(exist_ok=True)
            cleanup = None
            if state["started"]:
                try:
                    rows = (folder / (key+".process.jsonl")).read_text().splitlines()
                    record = json.loads(rows[-1])
                    if record.get("schema") == "mastermind.local_owned_process_receipt.v1" and record.get("label") == key:
                        cleanup = record.get("cleanup")
                except (OSError, ValueError, IndexError):
                    pass
            value = {"schema":"mastermind.go.worker-terminal.v1", **scope,
                     "started":state["started"], "returncode":rc, "cleanup":cleanup,
                     "cleanup_proven":(not state["started"] or cleanup_receipt_is_proven(cleanup or {}))}
            fd = os.open(folder / (key+".go-terminal.json"), os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(value, output); output.write("\n"); output.flush(); os.fsync(output.fileno())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
