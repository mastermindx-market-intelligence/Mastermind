from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess

import pytest

from control_plane.project_atlas import (
    BLOB_SCHEMA,
    PARSER_VERSION,
    ProjectAtlasError,
    detect_language,
    index_blob,
    is_sensitive_path,
    record_digest,
    validate_cached_record,
)
from scripts import project_atlas as adapter


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "atlas-fixture@example.invalid")
    _git(root, "config", "user.name", "Atlas Fixture")

    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "example.py").write_text(
        """import os
from control_plane import session_truth

class Example:
    @classmethod
    def build(cls):
        return os.getcwd()

@router.get("/health")
async def health():
    return {"ok": True}
""",
        encoding="utf-8",
    )
    (root / "docs" / "guide.md").write_text(
        """# Context Fabric

Tracks WS:CTX and MAS-1206.

## Resolver

See mastermindx-market-intelligence/Mastermind and PR #1205.

### Exact lookup

Use explicit identities first.
""",
        encoding="utf-8",
    )
    (root / ".env.py").write_text("SECRET = 'fixture-only'\n", encoding="utf-8")
    (root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (root / "notes.txt").write_text("unsupported\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return root


def test_python_blob_index_is_deterministic_and_exact():
    source = """import os
from pkg import thing

class Parent:
    def child(self):
        return thing

@router.post("/run")
async def run_job():
    return os.getcwd()
"""
    one = index_blob(blob_sha="a" * 40, language="python", content=source)
    two = index_blob(blob_sha="a" * 40, language="python", content=source)

    assert one == two
    assert one["schema"] == BLOB_SCHEMA
    assert one["parser_version"] == PARSER_VERSION
    assert [item["qualname"] for item in one["symbols"]] == [
        "Parent",
        "Parent.child",
        "run_job",
    ]
    assert "os" in one["imports"]
    assert "pkg:thing" in one["imports"]
    run = one["symbols"][-1]
    assert "router.post:/run" in run["decorators"]
    assert record_digest(one) == record_digest(two)


def test_markdown_index_has_heading_ranges_and_exact_references():
    text = """# Top
intro WS:CTX

## Middle
MAS-42
mastermindx-market-intelligence/Mastermind

### Child
PR #1205
"""
    record = index_blob(blob_sha="b" * 40, language="markdown", content=text)
    assert record["headings"] == [
        {"level": 1, "text": "Top", "line": 1, "end_line": 9},
        {"level": 2, "text": "Middle", "line": 4, "end_line": 9},
        {"level": 3, "text": "Child", "line": 8, "end_line": 9},
    ]
    assert record["references"] == [
        "MAS-42",
        "PR #1205",
        "WS:CTX",
        "mastermindx-market-intelligence/Mastermind",
    ]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".env", True),
        (".env.local", True),
        (".env.py", True),
        ("keys/id_rsa", True),
        ("config/client.pem", True),
        (".ssh/config.py", True),
        (".git/config", True),
        (".git/worktrees/example/config.worktree", True),
        ("accounts/.netrc", True),
        ("config/.npmrc", True),
        ("config/.pypirc", True),
        ("config/secrets.yaml", True),
        ("config/secrets.yml", True),
        ("ssh/id_ecdsa", True),
        ("certs/host_sk", True),
        ("secrets/service.py", True),
        ("src/module.py", False),
        ("docs/.github-workflows.md", False),
        ("docs/guide.md", False),
    ],
)
def test_sensitive_path_filter(path, expected):
    assert is_sensitive_path(path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("x.py", "python"),
        ("README.md", "markdown"),
        ("doc.markdown", "markdown"),
        ("x.json", None),
    ],
)
def test_language_detection(path, expected):
    assert detect_language(path) == expected


def test_cached_record_validation_rejects_tamper_and_stale_parser():
    record = index_blob(blob_sha="c" * 40, language="python", content="x = 1\n")
    entry = {
        "schema": adapter.CACHE_SCHEMA,
        "record": record,
        "record_digest": record_digest(record),
    }
    assert validate_cached_record(entry, blob_sha="c" * 40, language="python") == record

    tampered = json.loads(json.dumps(entry))
    tampered["record"]["byte_length"] += 1
    with pytest.raises(ProjectAtlasError, match="digest"):
        validate_cached_record(tampered, blob_sha="c" * 40, language="python")

    stale = json.loads(json.dumps(entry))
    stale["record"]["parser_version"] = "old-parser"
    stale["record_digest"] = record_digest(stale["record"])
    with pytest.raises(ProjectAtlasError, match="parser version"):
        validate_cached_record(stale, blob_sha="c" * 40, language="python")


def test_build_reuses_unchanged_blobs_and_degrades_one_bad_file(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"

    first = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )
    second = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )

    assert first["manifest"] == second["manifest"]
    assert first["stats"] == {
        "cache_hits": 0,
        "parsed_blobs": 2,
        "indexed_files": 2,
        "excluded_files": 1,
        "degraded_files": 1,
    }
    assert second["stats"]["cache_hits"] == 2
    assert second["stats"]["parsed_blobs"] == 0
    assert second["manifest"]["excluded"] == [
        {"path": ".env.py", "reason": "SENSITIVE_PATH"}
    ]
    assert second["manifest"]["degraded"][0]["path"] == "bad.py"
    assert "syntax error" in second["manifest"]["degraded"][0]["reason"]
    assert [item["path"] for item in second["manifest"]["files"]] == [
        "docs/guide.md",
        "src/example.py",
    ]


def test_one_changed_blob_reparses_only_that_blob(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"
    before = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )

    path = root / "src" / "example.py"
    path.write_text(
        path.read_text(encoding="utf-8") + "\ndef added():\n    return 2\n",
        encoding="utf-8",
    )
    _git(root, "add", "src/example.py")
    _git(root, "commit", "-qm", "change")
    after = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )

    assert before["manifest"]["commit_sha"] != after["manifest"]["commit_sha"]
    assert after["stats"]["parsed_blobs"] == 1
    assert after["stats"]["cache_hits"] == 1
    assert before["manifest"]["manifest_digest"] != after["manifest"]["manifest_digest"]


def test_corrupt_cache_reparses_only_corrupt_blob(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"
    first = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )
    guide = next(
        item for item in first["manifest"]["files"] if item["path"] == "docs/guide.md"
    )
    cache_path = adapter._cache_path(cache, guide["language"], guide["blob_sha"])
    cache_path.write_text("{", encoding="utf-8")

    repaired = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )
    assert repaired["manifest"] == first["manifest"]
    assert repaired["stats"]["parsed_blobs"] == 1
    assert repaired["stats"]["cache_hits"] == 1


def test_query_uses_exact_cached_records(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"
    built = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )

    symbol = adapter.query_atlas(
        manifest=built["manifest"],
        cache_root=cache,
        term="Example.build",
        kind="symbol",
        limit=20,
    )
    reference = adapter.query_atlas(
        manifest=built["manifest"],
        cache_root=cache,
        term="WS:CTX",
        kind="reference",
        limit=20,
    )

    assert symbol["authoritative"] is False
    assert symbol["derived_read_only"] is True
    assert [(item["path"], item["identity"]) for item in symbol["results"]] == [
        ("src/example.py", "Example.build")
    ]
    assert [(item["path"], item["identity"]) for item in reference["results"]] == [
        ("docs/guide.md", "WS:CTX")
    ]


def test_cache_inside_repository_is_refused(tmp_path: Path):
    root = _repo(tmp_path)
    with pytest.raises(ProjectAtlasError, match="outside"):
        adapter.build_atlas(
            repository="example/repo",
            repo_root=root,
            cache_root=root / ".atlas-cache",
            revision="HEAD",
        )


def test_fixed_tree_manifest_is_cache_location_independent(tmp_path: Path):
    root = _repo(tmp_path)
    left = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=tmp_path / "cache-left",
        revision="HEAD",
    )
    right = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=tmp_path / "cache-right",
        revision="HEAD",
    )
    assert left["manifest"] == right["manifest"]


def test_pure_parser_has_no_filesystem_network_runtime_imports():
    source_path = Path(__file__).parents[1] / "control_plane" / "project_atlas.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    forbidden = {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "time",
        "random",
        "app",
        "runtime",
    }
    assert imports.isdisjoint(forbidden)


def test_tampered_manifest_digest_is_refused(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"
    built = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )
    manifest = json.loads(json.dumps(built["manifest"]))
    manifest["files"][0]["path"] = "tampered.py"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProjectAtlasError, match="digest"):
        adapter._load_manifest(path)


def test_manifest_cache_path_traversal_is_refused(tmp_path: Path):
    root = _repo(tmp_path)
    cache = tmp_path / "cache"
    built = adapter.build_atlas(
        repository="example/repo",
        repo_root=root,
        cache_root=cache,
        revision="HEAD",
    )
    manifest = json.loads(json.dumps(built["manifest"]))
    manifest["files"][0]["language"] = "../../escape"
    core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    import hashlib
    from control_plane.session_truth_contract import canonical_json

    manifest["manifest_digest"] = hashlib.sha256(
        canonical_json(core).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ProjectAtlasError, match="cache language"):
        adapter.query_atlas(
            manifest=manifest,
            cache_root=cache,
            term="anything",
            kind="any",
            limit=10,
        )


def test_atlas_git_process_is_identity_and_output_bounded(monkeypatch, tmp_path):
    from control_plane import ceo_boot_packet
    root = _repo(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/not/an/authorized/observer")
    monkeypatch.setenv("GIT_PAGER", "/not/a/safe/pager")
    captured = []
    owned = ceo_boot_packet.bounded_subprocess_runner

    def spy(argv, **kwargs):
        captured.append((tuple(argv), kwargs.copy()))
        return owned(argv, **kwargs)

    monkeypatch.setattr(adapter, "bounded_subprocess_runner", spy)
    assert adapter._commit_sha(root, "HEAD") == _git(root, "rev-parse", "HEAD")
    assert len(captured) == 1
    argv, values = captured[0]
    assert argv[0] == "/usr/bin/git"
    assert argv[1:3] == ("--no-pager", "-c")
    assert "core.fsmonitor=false" in argv
    assert "GIT_CONFIG_COUNT" not in values["env"]
    assert "GIT_PAGER" not in values["env"]
    assert values["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert values["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert values["env"]["HOME"] == "/nonexistent"
    assert values["max_bytes"] <= 64 * 1024 * 1024
    assert values["timeout"] <= adapter._GIT_TIMEOUT_SECONDS


def test_atlas_git_output_limit_refuses_before_parsing(monkeypatch, tmp_path):
    root = _repo(tmp_path)

    def over_bound(*_args, **_kwargs):
        return {
            "code": None, "stdout": "", "stderr": "",
            "timed_out": False, "limit_exceeded": True, "invalid_utf8": False,
        }

    monkeypatch.setattr(adapter, "bounded_subprocess_runner", over_bound)
    with pytest.raises(ProjectAtlasError, match="Git (read|output)"):
        adapter._tree_rows(root, "a" * 40)


def test_atlas_cache_writer_never_follows_predictable_symlink(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    destination = cache / ("a" * 40 + ".json")
    victim = tmp_path / "victim.txt"
    victim.write_text("preserve me", encoding="utf-8")
    attack = destination.with_name(f".{destination.name}.{__import__('os').getpid()}.tmp")
    attack.symlink_to(victim)
    # Even if the attacker has pre-planted the original predictable temp path,
    # the new owned temp must be O_EXCL/NOfollow and must not clobber victim.
    record = index_blob(blob_sha="a" * 40, language="python", content="x=1\n")
    adapter._write_cache(destination, record)
    assert victim.read_text(encoding="utf-8") == "preserve me"
    assert attack.is_symlink()
    assert destination.is_file()
    assert destination.read_bytes()


def test_historical_fabric_source_hashes_are_explicitly_pinned():
    import hashlib

    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / "research/fabric_launch/EVIDENCE.json").read_text())
    commit = evidence["affected_source_hashes_commit"]
    assert commit == "40a7f3986942c915198071cd8def92c53416f682"
    assert len(evidence["affected_source_hashes"]) == 8
    for relative, digest in evidence["affected_source_hashes"].items():
        payload = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{relative}"],
            capture_output=True, check=True, timeout=10,
        ).stdout
        assert hashlib.sha256(payload).hexdigest() == digest
