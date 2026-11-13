"""Executable research-prose discovery over immutable Git blob Atlas records."""
from __future__ import annotations

from pathlib import Path
import subprocess

from control_plane.project_atlas import index_blob
from integrations.context_mcp.contracts import INPUT_SCHEMAS
from scripts import project_atlas as atlas


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Research Fixture")
    (root / "docs").mkdir()
    return root


def build(root: Path, cache: Path) -> dict:
    return atlas.build_atlas(
        repository="example/research", repo_root=root,
        cache_root=cache, revision="HEAD",
    )["manifest"]


def search(manifest: dict, cache: Path, phrase: str, limit: int = 10) -> dict:
    return atlas.query_atlas(
        manifest=manifest, cache_root=cache, term=phrase,
        kind="text", limit=limit,
    )


def test_markdown_prose_is_line_exact_but_code_fences_and_headings_are_excluded():
    content = (
        "# CPI Hot / PPI Cold\n"
        "\n"
        "Cold PPI is a candidate observation, not a proven standalone edge.\n"
        "~~~python\n"
        "cold PPI code should stay outside prose search\n"
        "~~~\n"
        "## Cold PPI heading only\n"
        "A final observation about cold PPI appears here.\n"
    )
    record = index_blob(blob_sha="b" * 40, language="markdown", content=content)
    assert record["prose"].splitlines()[2] == content.splitlines()[2]
    assert record["prose"].splitlines()[4] == ""
    assert record["prose"].splitlines()[6] == ""
    assert record["headings"][0]["text"] == "CPI Hot / PPI Cold"
    py = index_blob(blob_sha="c" * 40, language="python", content="x = 1\n")
    assert py["prose"] == ""


def test_query_matches_research_body_with_exact_commit_and_line(tmp_path: Path):
    root = repository(tmp_path)
    cache = tmp_path / "cache"
    (root / "docs" / "finding.md").write_text(
        "# Study\n\n"
        "The sector-rotation pivot is only a hypothesis until OOS verification.\n"
        "~~~python\n"
        "print('sector-rotation pivot inside fenced code')\n"
        "~~~\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "first")
    first = build(root, cache)
    first_sha = git(root, "rev-parse", "HEAD")
    result = search(first, cache, "sector-rotation pivot")
    assert result["commit_sha"] == first_sha
    assert result["manifest_digest"] == first["manifest_digest"]
    assert result["degraded"] == []
    assert result["truncated"] is False
    assert len(result["results"]) == 1
    line = result["results"][0]
    assert (line["path"], line["line"], line["end_line"], line["kind"]) == (
        "docs/finding.md", 3, 3, "text",
    )
    assert "hypothesis" in line["identity"]
    # Do not silently widen legacy catch-all queries with extra text hits.
    legacy = atlas.query_atlas(
        manifest=first, cache_root=cache, term="sector-rotation pivot",
        kind="any", limit=10,
    )
    assert legacy["results"] == []

    (root / "docs" / "finding.md").write_text(
        "# Study\n\nThe sector-rotation pivot was invalidated after a newer test.\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "revise")
    second = build(root, cache)
    assert second["manifest_digest"] != first["manifest_digest"]
    assert "invalidated" in search(second, cache, "sector-rotation pivot")["results"][0]["identity"]
    assert "hypothesis" in search(first, cache, "sector-rotation pivot")["results"][0]["identity"]


def test_text_search_caps_lines_and_discloses_truncation(tmp_path: Path):
    root = repository(tmp_path)
    cache = tmp_path / "cache"
    paragraphs = "".join(f"Unique research outcome line {i:03d}\n" for i in range(140))
    (root / "docs" / "mass.md").write_text(paragraphs, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "mass")
    m = build(root, cache)
    result = search(m, cache, "research outcome", limit=3)
    assert result["truncated"] is True
    assert [entry["line"] for entry in result["results"]] == [1, 2, 3]
    assert all(len(entry["identity"]) <= 320 for entry in result["results"])
    assert result["degraded"] == []


def test_sensitive_result_excerpt_withheld_without_losing_source_location(tmp_path: Path):
    root = repository(tmp_path)
    cache = tmp_path / "cache"
    secret = "sk-" + "m" * 30
    (root / "docs" / "notes.md").write_text(
        "Sensitive research conclusion " + secret + " should not print.\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "redaction")
    row = search(build(root, cache), cache, "research conclusion")["results"][0]
    assert row["identity"] == "[SENSITIVE_EXCERPT_WITHHELD]"
    assert secret not in row["identity"]
    assert row["line"] == 1


def test_existing_private_mcp_tool_and_cli_allow_explicit_text_kind():
    schema = INPUT_SCHEMAS["atlas_search"]
    assert "text" in schema["properties"]["kind"]["enum"]
    assert set(INPUT_SCHEMAS) == {
        "resolve_context", "expand_context", "diff_context",
        "atlas_search", "workspace_overlay",
    }
    args = atlas._parser().parse_args([
        "query", "--manifest", "/tmp/manifest.json", "--cache-root",
        "/tmp/cache", "--term", "observed signals", "--kind", "text",
    ])
    assert args.kind == "text"


def test_parser3_cannot_silently_reuse_cache_missing_its_prose_field():
    from control_plane.project_atlas import (
        ProjectAtlasError, record_digest, validate_cached_record,
    )
    import pytest

    record = index_blob(
        blob_sha="d" * 40, language="markdown", content="# Heading\nbody.\n",
    )
    del record["prose"]
    entry = {"record": record, "record_digest": record_digest(record)}
    with pytest.raises(ProjectAtlasError, match="prose"):
        validate_cached_record(entry, blob_sha="d" * 40, language="markdown")


def test_sensitive_text_not_exposed_when_secret_is_far_from_match(tmp_path: Path):
    root = repository(tmp_path)
    cache = tmp_path / "cache"
    secret = "Bearer " + "y" * 34
    body = "X" * 500 + " research outcomes " + secret
    (root / "docs" / "note.md").write_text(body + "\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "sensitive")
    hit = search(build(root, cache), cache, "research outcomes")["results"][0]
    assert hit["line"] == 1
    assert hit["identity"] == "[SENSITIVE_EXCERPT_WITHHELD]"
    assert "yyy" not in hit["identity"]


def test_missing_built_source_is_disclosed_even_if_all_remaining_cache_loads(tmp_path: Path):
    root = repository(tmp_path)
    cache = tmp_path / "cache"
    (root / "docs" / "evidence.md").write_text(
        "Sector rotation evidence must be out-of-sample.\n", encoding="utf-8",
    )
    (root / "bad.py").write_text("def syntax?(:\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "partial index")
    manifest = build(root, cache)
    assert any(r["path"] == "bad.py" for r in manifest["degraded"])
    response = search(manifest, cache, "Sector rotation evidence")
    assert len(response["results"]) == 1
    assert [r["path"] for r in response["degraded"]] == ["bad.py"]
