"""Read-only installed-tree blob manifest (INSTALL_RUNBOOK T1/T4).

Runs on the VPS from stdin and writes nothing there:

    ssh -i KEY -o BatchMode=yes root@HOST 'python3 -I -B - /opt/mastermind' \
        < remote_blob_manifest.py > identity/installed_manifest.jsonl

Stdlib only. Walks the code root, pruning every directory and file whose
basename matches the deploy script's rsync exclusion list (the same
non-anchored, any-depth basename patterns as scripts/deploy_code_to_vps.sh
EXC), and prints one JSON line per remaining path:

    ["relative/path", "<git blob sha1>", <mtime>, <ctime>]

Symlinks are hashed by their target bytes (git mode 120000 semantics) and are
never followed. The first line is a {"meta": ...} object carrying the
.deployed_git_sha claim (40 hex, not a secret) and its mtime/ctime, which T4
orders against the service start. File contents never leave the host; only
digests and timestamps do.
"""

import fnmatch
import hashlib
import json
import os
import sys

EXCLUDES = (
    ".git", ".github", ".worktrees", ".venv", "venv", "data", "vendor",
    "vendor_*", "__pycache__", "*.pyc", "*.pyo", "node_modules", "*.sqlite",
    "*.sqlite-*", "*.db", "*.log", ".DS_Store", "*.lock", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".env", ".env.*", "tmp", "catboost_info",
    "{_DB}", "tests", ".deploy_prev", ".deployed_git_sha",
)


def excluded(name):
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in EXCLUDES)


def blob_sha1(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def entry(root, full):
    st = os.lstat(full)
    if os.path.islink(full):
        data = os.fsencode(os.readlink(full))
    else:
        with open(full, "rb") as handle:
            data = handle.read()
    rel = os.path.relpath(full, root)
    return [rel, blob_sha1(data), st.st_mtime, st.st_ctime]


def main(argv):
    root = os.path.abspath(argv[1] if len(argv) > 1 else "/opt/mastermind")
    marker = os.path.join(root, ".deployed_git_sha")
    meta = {"root": root, "deployed_git_sha": None}
    if os.path.isfile(marker):
        st = os.stat(marker)
        with open(marker, "rb") as handle:
            claim = handle.read(64).decode("ascii", "replace").strip()
        meta.update(
            deployed_git_sha=claim if len(claim) == 40 and all(c in "0123456789abcdef" for c in claim) else "malformed",
            marker_mtime=st.st_mtime,
            marker_ctime=st.st_ctime,
        )
    out = sys.stdout
    out.write(json.dumps({"meta": meta}) + "\n")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        keep = []
        for name in sorted(dirnames):
            if excluded(name):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                out.write(json.dumps(entry(root, full)) + "\n")
            else:
                keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            if not excluded(name):
                out.write(json.dumps(entry(root, os.path.join(dirpath, name))) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
