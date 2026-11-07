"""Pinned producer invocation with original-host private retention.

Default CLI behavior is read-only preflight. Explicit execution is a mechanism,
not writer admission: the existing workflow owner must first settle all writers
and qualify dependencies, source, original host retention and recovery. Nothing
here schedules, retries issued effects, installs, deletes evidence, or adopts
another process's BUILDING run. A still-present original parent may finish one
validated, wholly unissued tail after waiting for its own child.
The secure configuration/manifest digest must come from the existing owner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

# Direct ``python -I -B /release/ops/research_producer/launch.py`` has no
# checkout/PYTHONPATH import root. Bootstrap only this entry point's release;
# preflight still verifies the configured archives before reserving a run.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integrations.research_read_mcp.release_identity import verify_archive_release
from integrations.research_read_mcp.runtime import RuntimeRefused, _json, read_secure_json

SCHEMA = "mastermind.research_producer_launch.v1"
MODULE = "ops/research_producer/launch.py"
REPOSITORY = "mastermindx-market-intelligence/macro"
MIN_FREE_BYTES = 2 * 1024**3
MAX_LOG_BYTES = 32 * 1024**2
FIELDS = frozenset({
    "schema", "mastermind_release", "mastermind_commit", "mastermind_tree",
    "macro_release", "macro_commit", "macro_tree", "manifest_path",
    "manifest_sha256", "retention_root", "public_checkout", "runner_work_root",
})
CAPTURE = re.compile(rb"ingest_research: original_capture_sha256=([0-9a-f]{64})\n\Z")
CONTINUATION_CAPTURE = re.compile(rb"research_producer: continuation_capture_sha256=([0-9a-f]{64})\n\Z")


class OriginalRunUnsettled(RuntimeRefused):
    """A reservation or invocation needs same-run reconciliation, never replay."""


def _refuse(code="PRODUCER_LAUNCH_REFUSED"):
    raise RuntimeRefused(code)


def _directory(value, *, private=False):
    if type(value) is not str:
        _refuse()
    path = Path(value)
    if (not path.is_absolute() or str(path) != value
            or any(x in {".", ".."} for x in path.parts)
            or any(p.is_symlink() for p in (path, *path.parents))):
        _refuse()
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & (0o077 if private else 0o022)):
        _refuse()
    return path


def _overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def _identity(run_id, attempt):
    if any(type(x) is not str or re.fullmatch(r"[1-9][0-9]{0,19}", x) is None
           for x in (run_id, attempt)):
        _refuse("PRODUCER_RUN_ID_REFUSED")
    return {"repository": REPOSITORY, "run_id": run_id, "attempt": attempt,
            "generation_run": f"github:{REPOSITORY}:{run_id}:{attempt}"}


def preflight(config, run_id, attempt):
    """Verify bytes and placement without creating files or opening a Store.

    This receipt does not authenticate GitHub environment strings or grant a
    writer lease. The original workflow is the run identity/capture carrier.
    """
    try:
        if type(config) is not dict or set(config) != FIELDS or config["schema"] != SCHEMA:
            _refuse()
        identity = _identity(run_id, attempt)
        roots = {key: _directory(config[key], private=key == "retention_root")
                 for key in ("mastermind_release", "macro_release", "retention_root",
                             "public_checkout", "runner_work_root")}
        retention = roots["retention_root"]
        if any(_overlap(retention, value) for key, value in roots.items()
               if key != "retention_root"):
            _refuse("PRODUCER_PRIVATE_PLACEMENT_REFUSED")
        if _overlap(roots["public_checkout"], roots["macro_release"]) or _overlap(
                roots["public_checkout"], roots["mastermind_release"]):
            _refuse("PRODUCER_SOURCE_MIRROR_OVERLAP")
        receipts = []
        for project in ("mastermind", "macro"):
            receipts.append(verify_archive_release(
                config[project + "_release"], config[project + "_commit"],
                config[project + "_tree"], project=project,
                manifest_path=config["manifest_path"],
                expected_manifest_sha256=config["manifest_sha256"],
                manifest_owner_uid=os.getuid(), release_owner_uid=os.getuid()))
        # The parent must use these same launcher bytes. A source claim alone
        # must not turn a different local wrapper into the pinned launcher.
        if (roots["mastermind_release"] / MODULE).read_bytes() != Path(__file__).read_bytes():
            _refuse("PRODUCER_LAUNCHER_BYTES_MISMATCH")
        macro = roots["macro_release"]
        if not (macro / "scripts/ingest_research.py").is_file():
            _refuse("PRODUCER_CLI_MISSING")
        run_dir = retention / f"macro-{run_id}-{attempt}"
        if run_dir.exists() or run_dir.is_symlink():
            _refuse("PRODUCER_ORIGINAL_RUN_EXISTS")
        if shutil.disk_usage(retention).free < MIN_FREE_BYTES:
            _refuse("PRODUCER_RETENTION_SPACE_REFUSED")
        return {"state": "INERT_PRODUCER_PLAN", "identity": identity,
                "macro_commit": config["macro_commit"],
                "mastermind_commit": config["mastermind_commit"],
                "manifest_sha256": config["manifest_sha256"],
                "source_receipts": receipts, "writer_admission": False}
    except RuntimeRefused:
        raise
    except Exception:
        _refuse()


def _write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def _document(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _child(config, identity, run_dir):
    """Fresh isolated interpreter, private output already owned by the parent."""
    import runpy
    # Verification is repeated in the actual executor before any engine import.
    for project in ("mastermind", "macro"):
        verify_archive_release(
            config[project + "_release"], config[project + "_commit"],
            config[project + "_tree"], project=project,
            manifest_path=config["manifest_path"],
            expected_manifest_sha256=config["manifest_sha256"],
            manifest_owner_uid=os.getuid(), release_owner_uid=os.getuid())
    if any(name in {"engine", "lib"} or name.startswith(("engine.", "lib."))
           for name in sys.modules):
        _refuse("PRODUCER_IMPORT_ALREADY_LOADED")
    sys.dont_write_bytecode = True
    sys.path.insert(0, config["macro_release"])
    cli = Path(config["macro_release"]) / "scripts/ingest_research.py"
    # Legacy RESEARCH_LOCAL_STORE is not an admitted production Store override.
    if os.environ.get("RESEARCH_LOCAL_STORE"):
        _refuse("PRODUCER_LOCAL_STORE_OVERRIDE_REFUSED")
    sys.argv = [str(cli), "--require-store", "--repo-dir",
                str(Path(config["public_checkout"]) / "data/research_vault"),
                "--generation-source-commit", config["macro_commit"],
                "--generation-run", identity["generation_run"],
                "--generation-evidence-path", str(Path(run_dir) / "journal.jsonl")]
    result = runpy.run_path(str(cli), run_name="research_producer_cli")["main"]()
    return result


_BOOTSTRAP = """import json,sys
c,i,p=json.loads(sys.argv[1])
sys.path.insert(0,c['mastermind_release'])
from ops.research_producer.launch import _child
raise SystemExit(_child(c,i,p))
"""


def _continuation_child(config, identity, run_dir, original_capture):
    """Fresh private executor commissioned only by the original waiting parent.

    This function is not an authenticated external API or a resume command.
    The original parent's control flow owns the actual wait/capture provenance.
    Any failed continuation stays in the same reserved run; no recursive retry.
    """
    import hashlib
    import runpy
    import sqlite3

    for project in ("mastermind", "macro"):
        verify_archive_release(
            config[project + "_release"], config[project + "_commit"],
            config[project + "_tree"], project=project,
            manifest_path=config["manifest_path"],
            expected_manifest_sha256=config["manifest_sha256"],
            manifest_owner_uid=os.getuid(), release_owner_uid=os.getuid())
    if any(name in {"engine", "lib"} or name.startswith(("engine.", "lib."))
           for name in sys.modules):
        _refuse("PRODUCER_IMPORT_ALREADY_LOADED")
    if os.environ.get("RESEARCH_LOCAL_STORE"):
        _refuse("PRODUCER_LOCAL_STORE_OVERRIDE_REFUSED")
    sys.dont_write_bytecode = True
    sys.path.insert(0, config["macro_release"])
    from engine.research_vault.generation_recovery import inspect_settled_publication
    from engine.research_vault.generation_continuation import _continue_after_original_exit
    from engine.research_vault import r2_store, producer_generation, excerpt

    expected = {"source_commit": config["macro_commit"], "run": identity["generation_run"]}
    original = Path(run_dir) / "journal.jsonl"
    inspect_settled_publication(original, expected_identity=expected,
                               original_capture_sha256=original_capture)
    # The protocol check above precedes any Store construction. A no-Store or
    # unsupported original cut cannot turn into another ingestion attempt.
    store = r2_store.build_store(single_attempt_writes=True)
    if store is None:
        _refuse("PRODUCER_STORE_UNAVAILABLE")
    completed = _continue_after_original_exit(
        store, original, expected_identity=expected,
        original_capture_sha256=original_capture)
    # Capture survives a later local snapshot failure, but a nonzero exit still
    # fails the workflow. It never grants another continuation attempt.
    print("research_producer: continuation_capture_sha256="
          + completed["continuation_capture_sha256"], flush=True)
    canonical = completed["catalog_bytes"]
    cli = runpy.run_path(str(Path(config["macro_release"]) / "scripts/ingest_research.py"),
                         run_name="research_producer_projection")
    mirror = cli["_public_mirror_bytes"](canonical)
    if mirror is None:
        _refuse("PRODUCER_PUBLIC_MIRROR_UNAVAILABLE")
    document = json.loads(canonical)
    corpus_path = original.with_name(original.name + ".workspace") / "corpus.sqlite"
    # Never project an unrelated or subsequently changed local corpus. The
    # COMPLETE record already binds the actual store corpus independently.
    if corpus_path.stat().st_size > producer_generation.CORPUS_MAX_BYTES:
        _refuse("PRODUCER_PUBLIC_MIRROR_UNAVAILABLE")
    corpus_bytes = corpus_path.read_bytes()
    if hashlib.sha256(corpus_bytes).hexdigest() != document[producer_generation.GENERATION_FIELD]["corpus_sha256"]:
        _refuse("PRODUCER_PUBLIC_MIRROR_UNAVAILABLE")
    ids = {row["id"] for row in document.get("items", []) if isinstance(row, dict) and row.get("id")}
    # SQLite percent-DECODES the path of a ``file:`` URI, so the raw f-string
    # form silently retargeted any corpus whose retention path carries ``%``,
    # ``?`` or ``#`` — opening a decoy at the decoded path, or failing the
    # open outright. ``as_uri()`` re-encodes the exact digest-checked corpus
    # above, and the read-only snapshot is computed BEFORE anything public is
    # written, so a wrong or unreadable corpus cannot leave a partially
    # published mirror behind.
    connection = sqlite3.connect(corpus_path.as_uri() + "?mode=ro", uri=True)
    try:
        excerpts = excerpt.snapshot(connection, ids)
    finally:
        connection.close()
    public = Path(config["public_checkout"]) / "data/research_vault"
    public.mkdir(parents=True, exist_ok=True)
    # Both public candidates are staged on the public filesystem and only then
    # atomically replaced, so an excerpt.snapshot failure above or a
    # write_repo_snapshot refusal below leaves the existing public catalog and
    # excerpts pair byte-identical. The excerpt stage is seeded with the
    # committed snapshot so the existing collapse guard reads the REAL prior
    # excerpts, never an absent temp path. Cleanup touches only these two
    # staged names, and no cross-file crash atomicity is claimed.
    staged_catalog = public / f".catalog.json.staged-{os.getpid()}"
    staged_excerpts = public / f".excerpts.json.staged-{os.getpid()}"
    try:
        committed = public / "excerpts.json"
        if committed.is_file():
            _write_new(staged_excerpts, committed.read_bytes())
        # Same public-safe excerpt projection as the ordinary CLI; no original
        # journal, corpus bytes, generation record or receipts enter the mirror.
        if not excerpt.write_repo_snapshot(excerpts, staged_excerpts):
            _refuse("PRODUCER_PUBLIC_MIRROR_UNAVAILABLE")
        _write_new(staged_catalog, mirror)
        for staged, target in ((staged_catalog, public / "catalog.json"),
                               (staged_excerpts, public / "excerpts.json")):
            os.chmod(staged, 0o644)
            os.replace(staged, target)
    finally:
        for staged in (staged_catalog, staged_excerpts):
            try:
                os.unlink(staged)
            except FileNotFoundError:
                pass
    return 0


_CONTINUATION_BOOTSTRAP = """import json,sys
c,i,p,h=json.loads(sys.argv[1])
sys.path.insert(0,c['mastermind_release'])
from ops.research_producer.launch import _continuation_child
raise SystemExit(_continuation_child(c,i,p,h))
"""


def execute(config, run_id, attempt):
    """Explicit original invocation; callers retain admission and recovery duties.

    Never retries issued effects or kills a subprocess. An interrupted/lost parent does not
    prove settlement. Existing run directories are permanent collision fences;
    their absence or a new workflow attempt is not recovery authorization.
    """
    plan = preflight(config, run_id, attempt)
    retention = Path(config["retention_root"])
    run_dir = retention / f"macro-{run_id}-{attempt}"
    run_dir.mkdir(mode=0o700)  # no exist_ok; never adopt an original invocation
    try:
        return _run_reserved(config, plan, run_dir, retention)
    except BaseException as exc:
        # Preserve cancellation as cancellation, and never fabricate child exit.
        if not isinstance(exc, Exception):
            raise
        raise OriginalRunUnsettled("PRODUCER_ORIGINAL_RUN_REQUIRES_RECONCILIATION") from None


def _run_private_child(command, *, cwd, environment, output_path, capture_pattern):
    """Return only after the actual child wait and durable private-output close."""
    captures, pending, log_bytes, overflow = [], b"", 0, False
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as log:
        child = subprocess.Popen(command, cwd=cwd, env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # Drain even after the bound: killing a producer cannot establish whether
        # its last request settled. Oversized output suppresses capture receipt.
        while chunk := child.stdout.read(65536):
            log_bytes += len(chunk)
            if log_bytes <= MAX_LOG_BYTES:
                log.write(chunk)
            else:
                overflow = True
            if not overflow:
                pending += chunk
                lines = pending.split(b"\n")
                pending = lines.pop()
                for line in lines:
                    match = capture_pattern.fullmatch(line + b"\n")
                    if match:
                        captures.append(match.group(1).decode())
                if len(pending) > 65536 or len(captures) > 1:
                    overflow = True
                    pending = b""
        child.stdout.close()
        rc = child.wait()
        log.flush()
        os.fsync(log.fileno())
    capture = captures[0] if len(captures) == 1 and not overflow else None
    return rc, capture, overflow


def _run_reserved(config, plan, run_dir, retention):
    _sync_directory(retention)
    _write_new(run_dir / "launch.json", _document(plan))
    private_tmp = run_dir / "tmp"
    private_tmp.mkdir(mode=0o700)
    _sync_directory(run_dir)
    command = [sys.executable, "-I", "-B", "-c", _BOOTSTRAP,
               json.dumps([config, plan["identity"], str(run_dir)])]
    environment = dict(os.environ)
    environment.update(TMPDIR=str(private_tmp), TMP=str(private_tmp), TEMP=str(private_tmp))
    rc, capture, overflow = _run_private_child(
        command, cwd=config["mastermind_release"], environment=environment,
        output_path=run_dir / "output.log", capture_pattern=CAPTURE)
    result = {"state": "ORIGINAL_PROCESS_EXITED", "identity": plan["identity"],
              "macro_commit": config["macro_commit"],
              "mastermind_commit": config["mastermind_commit"],
              "manifest_sha256": config["manifest_sha256"], "exit_code": rc,
              "original_capture_sha256": capture, "output_bound_exceeded": overflow,
              "publication_complete": None, "recovery_authorized": False}
    _write_new(run_dir / "process-result.json", _document(result))
    _sync_directory(run_dir)
    # This edge is reached only in the original parent after its actual wait.
    # No saved process-result, run-dir adoption or manual resume enters it.
    # The fresh pinned child first checks the original closed plan without a
    # Store. Unknown/unsupported cuts refuse, even when postimages match.
    if rc != 0 and capture is not None and not overflow:
        _write_new(run_dir / "continuation-launch.json", _document({
            "identity": plan["identity"], "original_capture_sha256": capture,
            "manifest_sha256": config["manifest_sha256"]}))
        _sync_directory(run_dir)
        continuation_command = [sys.executable, "-I", "-B", "-c", _CONTINUATION_BOOTSTRAP,
            json.dumps([config, plan["identity"], str(run_dir), capture])]
        tail_rc, tail_capture, tail_overflow = _run_private_child(
            continuation_command, cwd=config["mastermind_release"], environment=environment,
            output_path=run_dir / "continuation-output.log", capture_pattern=CONTINUATION_CAPTURE)
        tail = {"state": "ORIGINAL_CONTINUATION_PROCESS_EXITED", "exit_code": tail_rc,
                "continuation_capture_sha256": tail_capture,
                "output_bound_exceeded": tail_overflow}
        _write_new(run_dir / "continuation-process-result.json", _document(tail))
        _sync_directory(run_dir)
        result["continuation"] = tail
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = _json(read_secure_json(args.config, expected_owner_uid=os.getuid(),
                                       maximum=32768), 32768)
        result = (execute if args.execute else preflight)(config, args.run_id, args.attempt)
        # Only fixed-schema public metadata. Raw child output stays private.
        print(json.dumps(result, sort_keys=True), flush=True)
        if not args.execute:
            return 0
        original_ok = result["exit_code"] == 0 and bool(result["original_capture_sha256"])
        tail = result.get("continuation", {})
        tail_ok = (tail.get("exit_code") == 0
                   and bool(tail.get("continuation_capture_sha256"))
                   and tail.get("output_bound_exceeded") is False)
        return 0 if original_ok or tail_ok else 1
    except Exception as exc:
        # No arbitrary exception, configured path, Store error or raw log leak.
        code = str(exc) if isinstance(exc, RuntimeRefused) else "PRODUCER_LAUNCH_FAILED"
        state = "ORIGINAL_RUN_UNSETTLED" if isinstance(exc, OriginalRunUnsettled) else "REFUSED"
        print(json.dumps({"state": state, "code": code}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
