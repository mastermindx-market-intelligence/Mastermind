#!/usr/bin/env python3
"""Build and query a disposable content-addressed Mastermind Project Atlas.

The adapter reads one explicit local Git repository and writes only to an explicit
external cache root. It performs no network I/O, source mutation, workspace lifecycle
action, provider call, or authority decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.project_atlas import (  # noqa: E402
    BLOB_SCHEMA,
    MAX_BLOB_BYTES,
    PARSER_VERSION,
    ProjectAtlasError,
    detect_language,
    index_blob,
    is_sensitive_path,
    record_digest,
    validate_cached_record,
)
from control_plane.session_truth_contract import canonical_json  # noqa: E402

MANIFEST_SCHEMA = "mastermind.project_atlas_manifest.v1"
BUILD_SCHEMA = "mastermind.project_atlas_build.v1"
QUERY_SCHEMA = "mastermind.project_atlas_query.v1"
CACHE_SCHEMA = "mastermind.project_atlas_cache_entry.v1"

_GIT_TIMEOUT_SECONDS = 15
_MAX_MANIFEST_FILES = 100_000
_MAX_QUERY_RESULTS = 100
_CACHE_LANGUAGES = frozenset({"python", "markdown"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or query one deterministic Project Atlas."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build", help="build a manifest from one explicit local Git tree"
    )
    build.add_argument("--repository", required=True)
    build.add_argument("--repo-root", required=True)
    build.add_argument("--cache-root", required=True)
    build.add_argument("--revision", default="HEAD")
    build.add_argument("--json", action="store_true", dest="emit_json")

    query = sub.add_parser("query", help="query one manifest using its external cache")
    query.add_argument("--manifest", required=True)
    query.add_argument("--cache-root", required=True)
    query.add_argument("--term", required=True)
    query.add_argument(
        "--kind",
        choices=("any", "symbol", "heading", "reference", "import"),
        default="any",
    )
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--json", action="store_true", dest="emit_json")
    return parser


def _run_git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    try:
        proc = subprocess.run(
            ["git", "-C", os.fspath(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectAtlasError("local Git read failed") from exc
    if proc.returncode != 0:
        raise ProjectAtlasError("local Git read failed")
    return proc.stdout


def _canonical_root(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ProjectAtlasError(f"{label} is not an existing directory")
    return path


def _validate_repo_root(path: Path) -> None:
    top = _run_git(path, "rev-parse", "--show-toplevel")
    if not isinstance(top, str):
        raise ProjectAtlasError("repository root is invalid")
    observed = Path(top.strip()).resolve()
    if observed != path:
        raise ProjectAtlasError("repo-root must be the exact Git worktree root")


def _validate_cache_root(cache_root: Path, repo_root: Path | None = None) -> None:
    if repo_root is not None and (
        cache_root == repo_root or repo_root in cache_root.parents
    ):
        raise ProjectAtlasError("cache-root must be outside the source repository")


def _commit_sha(root: Path, revision: str) -> str:
    if not revision or "\x00" in revision or len(revision.encode("utf-8")) > 512:
        raise ProjectAtlasError("revision is invalid")
    value = _run_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not isinstance(value, str):
        raise ProjectAtlasError("commit resolution failed")
    sha = value.strip()
    if len(sha) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in sha):
        raise ProjectAtlasError("resolved commit identity is invalid")
    return sha


def _tree_rows(root: Path, commit_sha: str) -> list[dict[str, Any]]:
    raw = _run_git(root, "ls-tree", "-r", "-l", "-z", commit_sha, binary=True)
    if not isinstance(raw, bytes):
        raise ProjectAtlasError("Git tree output is invalid")
    rows: list[dict[str, Any]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, blob_sha, raw_size = metadata.split(b" ", 3)
            path = raw_path.decode("utf-8", errors="strict")
            size_text = raw_size.decode("ascii", errors="strict")
            size = int(size_text, 10) if size_text != "-" else -1
        except (ValueError, UnicodeError) as exc:
            raise ProjectAtlasError("Git tree contains an unsupported entry") from exc
        if object_type != b"blob":
            continue
        if len(rows) >= _MAX_MANIFEST_FILES:
            raise ProjectAtlasError("repository exceeds atlas file-count bound")
        rows.append(
            {
                "path": path,
                "mode": mode.decode("ascii", errors="strict"),
                "blob_sha": blob_sha.decode("ascii", errors="strict"),
                "size": size,
            }
        )
    return rows


def _cache_path(cache_root: Path, language: str, blob_sha: str) -> Path:
    if language not in _CACHE_LANGUAGES:
        raise ProjectAtlasError("cache language is invalid")
    if (
        not isinstance(blob_sha, str)
        or len(blob_sha) not in {40, 64}
        or any(ch not in "0123456789abcdef" for ch in blob_sha)
    ):
        raise ProjectAtlasError("cache blob identity is invalid")
    path = cache_root / "v1" / PARSER_VERSION / language / f"{blob_sha}.json"
    resolved_parent = path.parent.resolve()
    resolved_root = cache_root.resolve()
    if (
        resolved_root != resolved_parent
        and resolved_root not in resolved_parent.parents
    ):
        raise ProjectAtlasError("cache path escaped cache root")
    return path


def _load_cache(path: Path, *, blob_sha: str, language: str) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if len(raw) > 4 * MAX_BLOB_BYTES:
        return None
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
        if not isinstance(value, dict) or value.get("schema") != CACHE_SCHEMA:
            return None
        record = validate_cached_record(value, blob_sha=blob_sha, language=language)
    except (UnicodeError, json.JSONDecodeError, ProjectAtlasError):
        return None
    return record


def _write_cache(path: Path, record: dict[str, Any]) -> None:
    entry = {
        "schema": CACHE_SCHEMA,
        "record": record,
        "record_digest": record_digest(record),
    }
    payload = (canonical_json(entry) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_blob(root: Path, blob_sha: str) -> bytes:
    raw = _run_git(root, "cat-file", "blob", blob_sha, binary=True)
    if not isinstance(raw, bytes):
        raise ProjectAtlasError("Git blob output is invalid")
    if len(raw) > MAX_BLOB_BYTES:
        raise ProjectAtlasError("blob exceeds byte bound")
    return raw


def _file_projection(path: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": path,
        "blob_sha": record["blob_sha"],
        "language": record["language"],
        "record_digest": record_digest(record),
        "symbol_count": len(record["symbols"]),
        "import_count": len(record["imports"]),
        "heading_count": len(record["headings"]),
        "reference_count": len(record["references"]),
    }


def build_atlas(
    *,
    repository: str,
    repo_root: Path,
    cache_root: Path,
    revision: str,
) -> dict[str, Any]:
    if (
        not repository
        or "/" not in repository
        or "\x00" in repository
        or len(repository.encode("utf-8")) > 256
    ):
        raise ProjectAtlasError("repository identity is invalid")
    _validate_repo_root(repo_root)
    _validate_cache_root(cache_root, repo_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    commit_sha = _commit_sha(repo_root, revision)

    files: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    degraded: list[dict[str, str]] = []
    cache_hits = 0
    parsed_blobs = 0

    for row in _tree_rows(repo_root, commit_sha):
        path = row["path"]
        language = detect_language(path)
        if language is None:
            continue
        if is_sensitive_path(path):
            excluded.append({"path": path, "reason": "SENSITIVE_PATH"})
            continue
        if row["size"] < 0 or row["size"] > MAX_BLOB_BYTES:
            degraded.append({"path": path, "reason": "BLOB_SIZE_UNSUPPORTED"})
            continue

        blob_sha = row["blob_sha"]
        cache_path = _cache_path(cache_root, language, blob_sha)
        record = _load_cache(cache_path, blob_sha=blob_sha, language=language)
        if record is not None:
            cache_hits += 1
        else:
            try:
                record = index_blob(
                    blob_sha=blob_sha,
                    language=language,
                    content=_read_blob(repo_root, blob_sha),
                )
            except ProjectAtlasError as exc:
                degraded.append({"path": path, "reason": str(exc)[:256]})
                continue
            _write_cache(cache_path, record)
            parsed_blobs += 1
        files.append(_file_projection(path, record))

    files.sort(key=lambda item: item["path"])
    excluded.sort(key=lambda item: (item["path"], item["reason"]))
    degraded.sort(key=lambda item: (item["path"], item["reason"]))
    manifest_core = {
        "schema": MANIFEST_SCHEMA,
        "repository": repository,
        "commit_sha": commit_sha,
        "parser_version": PARSER_VERSION,
        "files": files,
        "excluded": excluded,
        "degraded": degraded,
    }
    manifest = dict(manifest_core)
    manifest["manifest_digest"] = hashlib.sha256(
        canonical_json(manifest_core).encode("utf-8")
    ).hexdigest()
    return {
        "schema": BUILD_SCHEMA,
        "manifest": manifest,
        "stats": {
            "cache_hits": cache_hits,
            "parsed_blobs": parsed_blobs,
            "indexed_files": len(files),
            "excluded_files": len(excluded),
            "degraded_files": len(degraded),
        },
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProjectAtlasError("manifest is unavailable") from exc
    if len(raw) > 32 * 1024 * 1024:
        raise ProjectAtlasError("manifest exceeds byte bound")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectAtlasError("manifest is invalid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ProjectAtlasError("manifest schema is invalid")
    expected_keys = {
        "schema",
        "repository",
        "commit_sha",
        "parser_version",
        "files",
        "excluded",
        "degraded",
        "manifest_digest",
    }
    if set(value) != expected_keys:
        raise ProjectAtlasError("manifest shape is invalid")
    if value.get("parser_version") != PARSER_VERSION:
        raise ProjectAtlasError("manifest parser version is stale")
    files = value.get("files")
    if not isinstance(files, list) or len(files) > _MAX_MANIFEST_FILES:
        raise ProjectAtlasError("manifest files are invalid")
    supplied_digest = value.get("manifest_digest")
    if not isinstance(supplied_digest, str):
        raise ProjectAtlasError("manifest digest is invalid")
    core = {key: value[key] for key in expected_keys if key != "manifest_digest"}
    expected_digest = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    if supplied_digest != expected_digest:
        raise ProjectAtlasError("manifest digest is invalid")
    return value


def _match_record(
    path: str, record: dict[str, Any], term: str, kind: str
) -> list[dict[str, Any]]:
    needle = term.casefold()
    results: list[dict[str, Any]] = []

    def add(
        match_kind: str,
        identity: str,
        line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        results.append(
            {
                "kind": match_kind,
                "path": path,
                "identity": identity,
                "line": line,
                "end_line": end_line,
            }
        )

    if kind in {"any", "symbol"}:
        for item in record["symbols"]:
            haystack = f"{item.get('name', '')} {item.get('qualname', '')}".casefold()
            if needle in haystack:
                add(
                    "symbol",
                    str(item.get("qualname") or item.get("name")),
                    item.get("line"),
                    item.get("end_line"),
                )
    if kind in {"any", "heading"}:
        for item in record["headings"]:
            text = str(item.get("text") or "")
            if needle in text.casefold():
                add("heading", text, item.get("line"), item.get("end_line"))
    if kind in {"any", "reference"}:
        for item in record["references"]:
            if needle in str(item).casefold():
                add("reference", str(item))
    if kind in {"any", "import"}:
        for item in record["imports"]:
            if needle in str(item).casefold():
                add("import", str(item))
    return results


def query_atlas(
    *,
    manifest: dict[str, Any],
    cache_root: Path,
    term: str,
    kind: str,
    limit: int,
) -> dict[str, Any]:
    if not term or "\x00" in term or len(term.encode("utf-8")) > 1024:
        raise ProjectAtlasError("query term is invalid")
    if (
        type(limit) is not int
        or isinstance(limit, bool)
        or not 1 <= limit <= _MAX_QUERY_RESULTS
    ):
        raise ProjectAtlasError("query limit is outside the closed bound")
    results: list[dict[str, Any]] = []
    degraded: list[dict[str, str]] = []
    for file_row in manifest["files"]:
        if not isinstance(file_row, dict):
            raise ProjectAtlasError("manifest file row is invalid")
        path = file_row.get("path")
        blob_sha = file_row.get("blob_sha")
        language = file_row.get("language")
        if not all(
            isinstance(value, str) and value for value in (path, blob_sha, language)
        ):
            raise ProjectAtlasError("manifest file row is invalid")
        record = _load_cache(
            _cache_path(cache_root, language, blob_sha),
            blob_sha=blob_sha,
            language=language,
        )
        if record is None:
            degraded.append({"path": path, "reason": "CACHE_RECORD_UNAVAILABLE"})
            continue
        for match in _match_record(path, record, term, kind):
            results.append(match)
    results.sort(
        key=lambda item: (
            item["kind"],
            item["path"],
            int(item["line"] or 0),
            item["identity"],
        )
    )
    truncated = len(results) > limit
    return {
        "schema": QUERY_SCHEMA,
        "authoritative": False,
        "derived_read_only": True,
        "repository": manifest.get("repository"),
        "commit_sha": manifest.get("commit_sha"),
        "manifest_digest": manifest.get("manifest_digest"),
        "term": term,
        "kind": kind,
        "results": results[:limit],
        "truncated": truncated,
        "degraded": degraded,
    }


def _render_build(value: dict[str, Any]) -> str:
    manifest = value["manifest"]
    stats = value["stats"]
    return (
        "Mastermind Project Atlas\n"
        f"repository: {manifest['repository']}\n"
        f"commit_sha: {manifest['commit_sha']}\n"
        f"manifest_digest: {manifest['manifest_digest']}\n"
        f"indexed_files: {stats['indexed_files']}\n"
        f"cache_hits: {stats['cache_hits']}\n"
        f"parsed_blobs: {stats['parsed_blobs']}\n"
        f"degraded_files: {stats['degraded_files']}\n"
    )


def _render_query(value: dict[str, Any]) -> str:
    lines = [
        "Mastermind Project Atlas Query",
        f"repository: {value.get('repository')}",
        f"commit_sha: {value.get('commit_sha')}",
        f"results: {len(value.get('results', []))}",
    ]
    for item in value.get("results", []):
        line = f":{item['line']}" if item.get("line") else ""
        lines.append(f"- {item['kind']} {item['path']}{line} {item['identity']}")
    return "\n".join(lines) + "\n"


def _error(message: str) -> int:
    safe = " ".join(str(message).replace("\r", " ").replace("\n", " ").split())
    sys.stderr.write(f"project-atlas error: {safe[:220] or 'invalid input'}\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cache_root = Path(args.cache_root).expanduser().resolve()
        if args.command == "build":
            repo_root = _canonical_root(args.repo_root, "repo-root")
            _validate_cache_root(cache_root, repo_root)
            value = build_atlas(
                repository=args.repository,
                repo_root=repo_root,
                cache_root=cache_root,
                revision=args.revision,
            )
            rendered = (
                canonical_json(value) + "\n" if args.emit_json else _render_build(value)
            )
        else:
            _validate_cache_root(cache_root)
            manifest = _load_manifest(Path(args.manifest).expanduser().resolve())
            value = query_atlas(
                manifest=manifest,
                cache_root=cache_root,
                term=args.term,
                kind=args.kind,
                limit=args.limit,
            )
            rendered = (
                canonical_json(value) + "\n" if args.emit_json else _render_query(value)
            )
    except ProjectAtlasError as exc:
        return _error(str(exc))
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
