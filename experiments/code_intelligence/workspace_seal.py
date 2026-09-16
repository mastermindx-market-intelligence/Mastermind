"""Exact-worktree sealing for the C0 falsifier.

The seal is the host's answer to "which bytes, in which worktree, on which
device". A backend never chooses a root; it is handed a sealed one. Every
facade call verifies the seal before invocation and again before publishing a
result, so a backend that writes into the candidate tree, a worktree that moves
or is replaced, or a HEAD that shifts under us is caught rather than answered.

Fail closed. Every refusal is typed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "MAX_TREE_BYTES",
    "MAX_TREE_FILES",
    "SEAL_FIELDS",
    "WorkspaceSeal",
    "WorkspaceSealError",
    "candidate_tree_fingerprint",
    "capture_workspace_seal",
    "create_external_scratch",
    "verify_workspace_seal",
    "workspace_binding_digest",
]

SEAL_FIELDS = (
    "resolved_root",
    "device",
    "inode",
    "uid",
    "gid",
    "git_common_dir",
    "git_dir",
    "head_sha",
    "status_porcelain_v2_sha256",
    "candidate_tree_sha256",
)

MAX_TREE_FILES = 20_000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TREE_BYTES = 512 * 1024 * 1024
_READ_CHUNK = 1024 * 1024

# git is invoked with a closed environment so that neither user nor system
# configuration can influence what the seal observes.
_GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "LC_ALL": "C",
}


class WorkspaceSealError(Exception):
    """Typed, fail-closed refusal from the sealing layer."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class WorkspaceSeal:
    resolved_root: str
    device: int
    inode: int
    uid: int
    gid: int
    git_common_dir: str
    git_dir: str
    head_sha: str
    status_porcelain_v2_sha256: str
    candidate_tree_sha256: str


def _git_executable() -> str:
    found = shutil.which("git")
    if not found:
        raise WorkspaceSealError("GIT_UNAVAILABLE", "no git executable on PATH")
    return found


def _git(root: str, *args: str) -> str:
    try:
        result = subprocess.run(
            [_git_executable(), "-C", root, *args],
            check=True,
            capture_output=True,
            text=True,
            env=_GIT_ENV,
            shell=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        raise WorkspaceSealError("GIT_TIMEOUT", " ".join(args)) from exc
    except subprocess.CalledProcessError as exc:
        raise WorkspaceSealError(
            "GIT_ROOT_MISMATCH", (exc.stderr or "").strip()[:400]
        ) from exc
    return result.stdout


def _require_unlinked_root(root: Path) -> Path:
    """Refuse a root that is a symlink or reached through one."""
    if os.path.islink(root):
        raise WorkspaceSealError("SYMLINK_ROOT_REFUSED", str(root))
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceSealError("ROOT_UNRESOLVABLE", str(root)) from exc
    if not resolved.is_dir():
        raise WorkspaceSealError("ROOT_UNRESOLVABLE", f"{root} is not a directory")
    if Path(os.path.abspath(root)) != resolved:
        raise WorkspaceSealError("SYMLINK_ANCESTOR_REFUSED", str(root))
    return resolved


def _hash_file(path: Path, digest: "hashlib._Hash") -> int:
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_READ_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise WorkspaceSealError("TREE_TOO_LARGE", str(path))
            digest.update(chunk)
    return size


def candidate_tree_fingerprint(root: Path | str) -> str:
    """Sorted, bounded manifest of repository-relative file identity and bytes.

    Only ``.git`` indirection metadata is excluded. Special files and symlinks
    that escape the root are refused rather than skipped, because silently
    ignoring them would let a candidate hide a write or read outside the seal.
    """
    resolved = _require_unlinked_root(Path(root))
    records: list[str] = []
    total_bytes = 0

    def walk(directory: Path) -> None:
        nonlocal total_bytes
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:  # pragma: no cover - defensive
            raise WorkspaceSealError("TREE_UNREADABLE", str(directory)) from exc
        for entry in entries:
            if entry.name == ".git":
                continue
            path = Path(entry.path)
            relative = path.relative_to(resolved).as_posix()

            if entry.is_symlink():
                try:
                    target = path.resolve(strict=False)
                except OSError as exc:  # pragma: no cover - defensive
                    raise WorkspaceSealError("TREE_TRAVERSAL_REFUSED", relative) from exc
                if not target.is_relative_to(resolved):
                    raise WorkspaceSealError("TREE_TRAVERSAL_REFUSED", relative)
                records.append(
                    f"{relative}\tsymlink\t{os.readlink(path)}"
                )
                continue

            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                walk(path)
                continue
            if not stat.S_ISREG(mode):
                raise WorkspaceSealError("SPECIAL_FILE_REFUSED", relative)

            if len(records) >= MAX_TREE_FILES:
                raise WorkspaceSealError("TREE_TOO_LARGE", "file count ceiling")
            file_digest = hashlib.sha256()
            size = _hash_file(path, file_digest)
            total_bytes += size
            if total_bytes > MAX_TREE_BYTES:
                raise WorkspaceSealError("TREE_TOO_LARGE", "byte ceiling")
            executable = "1" if mode & stat.S_IXUSR else "0"
            records.append(
                f"{relative}\tfile\t{size}\t{executable}\t{file_digest.hexdigest()}"
            )

    walk(resolved)
    records.sort()
    manifest = "\n".join(records).encode("utf-8")
    return hashlib.sha256(manifest).hexdigest()


def capture_workspace_seal(root: Path | str) -> WorkspaceSeal:
    """Bind the exact worktree identity the experiment is allowed to read."""
    resolved = _require_unlinked_root(Path(root))
    info = os.lstat(resolved)

    paths = _git(
        str(resolved),
        "rev-parse",
        "--path-format=absolute",
        "--show-toplevel",
        "--git-common-dir",
        "--git-dir",
    ).splitlines()
    if len(paths) != 3:
        raise WorkspaceSealError("GIT_ROOT_MISMATCH", "unexpected rev-parse output")
    toplevel, git_common_dir, git_dir = (item.strip() for item in paths)
    if Path(toplevel).resolve() != resolved:
        raise WorkspaceSealError(
            "GIT_ROOT_MISMATCH", f"{toplevel} is not the sealed root {resolved}"
        )

    head_sha = _git(str(resolved), "rev-parse", "HEAD").strip()
    status = _git(
        str(resolved),
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
        "--no-renames",
    )

    return WorkspaceSeal(
        resolved_root=str(resolved),
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        git_common_dir=str(Path(git_common_dir).resolve()),
        git_dir=str(Path(git_dir).resolve()),
        head_sha=head_sha,
        status_porcelain_v2_sha256=hashlib.sha256(status.encode("utf-8")).hexdigest(),
        candidate_tree_sha256=candidate_tree_fingerprint(resolved),
    )


def verify_workspace_seal(expected: WorkspaceSeal) -> None:
    """Re-capture and refuse on any drift.

    Ordering is deliberate: identity, then git topology, then HEAD, then tree
    bytes, then index state. A backend writing the candidate tree must surface
    as ``CANDIDATE_TREE_WRITE_DETECTED`` rather than as generic dirt.
    """
    root = Path(expected.resolved_root)
    if os.path.islink(root):
        raise WorkspaceSealError("SYMLINK_ROOT_REFUSED", expected.resolved_root)
    if not root.exists():
        raise WorkspaceSealError("ROOT_UNRESOLVABLE", expected.resolved_root)

    actual = capture_workspace_seal(root)

    if (actual.device, actual.inode) != (expected.device, expected.inode):
        raise WorkspaceSealError(
            "ROOT_IDENTITY_CHANGED",
            f"device/inode moved from {expected.device}/{expected.inode} "
            f"to {actual.device}/{actual.inode}",
        )
    if (actual.uid, actual.gid) != (expected.uid, expected.gid):
        raise WorkspaceSealError("ROOT_OWNER_CHANGED", expected.resolved_root)
    if actual.git_common_dir != expected.git_common_dir or actual.git_dir != expected.git_dir:
        raise WorkspaceSealError(
            "GIT_ROOT_MISMATCH",
            f"git dir {actual.git_dir} != sealed {expected.git_dir}",
        )
    if actual.head_sha != expected.head_sha:
        raise WorkspaceSealError(
            "HEAD_CHANGED", f"{expected.head_sha} -> {actual.head_sha}"
        )
    if actual.candidate_tree_sha256 != expected.candidate_tree_sha256:
        raise WorkspaceSealError(
            "CANDIDATE_TREE_WRITE_DETECTED",
            "candidate tree bytes changed while sealed",
        )
    if actual.status_porcelain_v2_sha256 != expected.status_porcelain_v2_sha256:
        raise WorkspaceSealError(
            "DIRTY_FINGERPRINT_DRIFT", "git status changed while sealed"
        )


def workspace_binding_digest(seal: WorkspaceSeal) -> str:
    """Stable digest of the whole seal, used in every facade response."""
    fields = asdict(seal)
    payload = "\n".join(f"{name}={fields[name]}" for name in SEAL_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_external_scratch(*, parent: Path | str, seal: WorkspaceSeal) -> Path:
    """Create mutable working space that provably lives outside the candidate tree."""
    root = Path(seal.resolved_root)
    requested = Path(os.path.abspath(parent))
    if requested == root or requested.is_relative_to(root):
        raise WorkspaceSealError("SCRATCH_INSIDE_CANDIDATE_TREE", str(requested))

    requested.mkdir(parents=True, exist_ok=True)
    resolved_parent = requested.resolve(strict=True)
    if resolved_parent == root or resolved_parent.is_relative_to(root):
        raise WorkspaceSealError("SCRATCH_INSIDE_CANDIDATE_TREE", str(resolved_parent))

    scratch = Path(
        tempfile.mkdtemp(
            prefix=f"codeintel-c0-{workspace_binding_digest(seal)[:16]}-",
            dir=str(resolved_parent),
        )
    )
    return scratch
