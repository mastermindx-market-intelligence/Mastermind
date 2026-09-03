"""Independent, deterministic source-census baseline tests for Z0."""

from __future__ import annotations

import shutil
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from experiments.code_discovery.baseline_search import (
    BaselineQuery,
    SourceCensusError,
    SourceSnapshot,
    baseline_search,
    census_sealed_sources,
    census_sources,
    derive_answer_key,
)
from experiments.code_discovery.index_manifest import (
    load_index_manifest,
    source_tree_digest,
)


_ROOT = Path(__file__).parent.parent / "fixtures" / "code_discovery" / "synthetic_org"


def _snapshots(root: Path = _ROOT) -> tuple[SourceSnapshot, ...]:
    return (
        SourceSnapshot(
            logical_repo_id="alpha-mirror",
            canonical_repository="synthetic-org/alpha-mirror",
            ref="main",
            commit="a" * 40,
            tree="b" * 40,
            root=root / "alpha-mirror",
        ),
        SourceSnapshot(
            logical_repo_id="beta-mirror",
            canonical_repository="synthetic-org/beta-mirror",
            ref="main",
            commit="c" * 40,
            tree="d" * 40,
            root=root / "beta-mirror",
        ),
    )


def _portable_synthetic_root(tmp_path: Path) -> Path:
    """Copy only tracked fixture content, as a clean hosted checkout would."""

    root = tmp_path / "synthetic_org"
    shutil.copytree(_ROOT, root, ignore=shutil.ignore_patterns(".git"))
    submodule_gitfile = root / "alpha-mirror" / "submodule" / ".git"
    submodule_gitfile.parent.mkdir(parents=True, exist_ok=True)
    submodule_gitfile.write_text(
        "gitdir: ../../.git/modules/synthetic-submodule\n", encoding="utf-8"
    )
    return root


def test_source_census_is_identity_complete_and_excludes_non_source_bytes(
    tmp_path: Path,
) -> None:
    """Two same-basename repos stay distinct; excluded material is receipted."""

    root = _portable_synthetic_root(tmp_path)
    census = census_sources(_snapshots(root))

    identities = {(item.logical_repo_id, item.path) for item in census.records}
    assert ("alpha-mirror", "engine/core.py") in identities
    assert ("beta-mirror", "engine/core.py") in identities
    assert len(census.records) >= 4
    assert {item.reason for item in census.excluded} == {
        "binary",
        "generated",
        "oversize",
        "submodule",
        "vendor",
    }
    assert census.digest == census_sources(_snapshots(root)).digest


def test_baseline_applies_equivalent_filters_and_exposes_limit_truncation() -> None:
    """The baseline is a real exhaustive matcher, not a deliberately weak straw man."""

    census = census_sources(_snapshots())
    query = BaselineQuery(
        query=r"^(OWNER|CONSUMER)_SENTINEL =",
        regex=True,
        case_sensitive=False,
        repository_ids=("alpha-mirror", "beta-mirror"),
        refs=("main",),
        path_prefixes=("engine",),
        languages=("python",),
        limit=1,
        context_lines=1,
    )
    result = baseline_search(census, query)

    assert result.total_match_count == 2
    assert result.truncated is True
    assert len(result.matches) == 1
    assert result.matches[0].path == "engine/core.py"
    assert result.matches[0].context_before == ()
    assert result.matches[0].context_after == ("",)


def test_baseline_timeout_is_explicitly_incomplete_not_a_partial_answer() -> None:
    """A shared time ceiling must leave a typed non-authoritative result."""

    census = census_sources(_snapshots())
    ticks = iter((0.0, 0.002))
    result = baseline_search(
        census,
        BaselineQuery(query="SENTINEL", timeout_ms=1),
        monotonic_clock=lambda: next(ticks),
    )

    assert result.query_completed is False
    assert result.truncated is True
    assert result.failure_code == "TIMEOUT"


def test_synthetic_high_result_fixture_proves_limit_truncation_without_weakening_search() -> None:
    """A selected hit set above the shared limit stays explicit rather than silently shortened."""

    result = baseline_search(
        census_sources(_snapshots()),
        BaselineQuery(query="HIGH_RESULT_SENTINEL", limit=2),
    )

    assert result.total_match_count == 3
    assert len(result.matches) == 2
    assert result.truncated is True


def test_answer_key_is_source_derived_and_changes_when_the_source_answer_changes(
    tmp_path: Path,
) -> None:
    """Candidate output cannot bless itself, and changed answer bytes change the digest."""

    source_root = tmp_path / "repos"
    alpha = source_root / "alpha-mirror" / "engine"
    beta = source_root / "beta-mirror" / "engine"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "core.py").write_text('OWNER_SENTINEL = "one"\n', encoding="utf-8")
    (beta / "core.py").write_text('CONSUMER_SENTINEL = "two"\n', encoding="utf-8")

    query = BaselineQuery(query="OWNER_SENTINEL", limit=10)
    first = derive_answer_key(census_sources(_snapshots(source_root)), "E1", query)
    (alpha / "core.py").write_text('OWNER_SENTINEL = "changed"\n', encoding="utf-8")
    second = derive_answer_key(census_sources(_snapshots(source_root)), "E1", query)

    assert first.digest != second.digest
    assert first.canonical_bytes != second.canonical_bytes
    assert first.expected_identities == second.expected_identities
    assert first.forbidden_identities
    assert not set(first.expected_identities) & set(first.forbidden_identities)


def test_census_fails_closed_for_duplicate_or_external_or_symlinked_source_identity(
    tmp_path: Path,
) -> None:
    """A source epoch cannot silently collapse repositories or traverse another tree."""

    with pytest.raises(SourceCensusError, match="duplicate logical_repo_id"):
        census_sources(_snapshots() + (_snapshots()[0],))

    external = SourceSnapshot(
        logical_repo_id="external",
        canonical_repository="synthetic-org/external",
        ref="main",
        commit="e" * 40,
        tree="f" * 40,
        root=tmp_path / "missing",
    )
    with pytest.raises(SourceCensusError, match="source root"):
        census_sources((external,))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "safe.py").write_text("SAFE = 1\n", encoding="utf-8")
    (repo / "outside.py").symlink_to(_ROOT / "alpha-mirror" / "engine" / "core.py")
    symlinked = SourceSnapshot(
        logical_repo_id="symlinked",
        canonical_repository="synthetic-org/symlinked",
        ref="main",
        commit="1" * 40,
        tree="2" * 40,
        root=repo,
    )
    with pytest.raises(SourceCensusError, match="symlink"):
        census_sources((symlinked,))


def test_sealed_baseline_uses_manifest_selected_bytes_without_legacy_256_byte_cap(
    tmp_path: Path,
) -> None:
    """A real baseline must search the parent-sealed corpus, not a weaker local walk."""

    root = tmp_path / "sealed-source"
    root.mkdir()
    for args in (
        ("init", "-q", "-b", "master"),
        ("config", "user.name", "CodeIntel test"),
        ("config", "user.email", "codeintel@example.invalid"),
        ("remote", "add", "origin", "git@github.com:synthetic-org/sealed.git"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / "engine").mkdir()
    (root / "engine" / "ordinary.py").write_text(
        "SEALED_SENTINEL = '" + ("x" * 300) + "'\n", encoding="utf-8"
    )
    (root / "vendor").mkdir()
    (root / "vendor" / "ignored.py").write_text("SEALED_SENTINEL = 'wrong'\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "sealed source"], check=True)
    manifest_path = tmp_path / "index-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": [
                    {
                        "repository_id": "sealed",
                        "repository_name": "synthetic-org/sealed",
                        "source_snapshot_root": str(root),
                        "ref_label": "master",
                        "commit_sha": subprocess.check_output(
                            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
                        ).strip(),
                        "included_prefixes": ["engine/**"],
                        "excluded_globs": ["vendor/**"],
                        "source_tree_digest": source_tree_digest(
                            root, ("engine/**",), ("vendor/**",)
                        ),
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = load_index_manifest(manifest_path)

    census = census_sealed_sources(manifest)
    result = baseline_search(census, BaselineQuery(query="SEALED_SENTINEL"))

    assert [record.path for record in census.records] == ["engine/ordinary.py"]
    assert result.total_match_count == 1
    assert result.matches[0].source_content_digest == hashlib.sha256(
        (root / "engine" / "ordinary.py").read_bytes()
    ).hexdigest()

    (root / "engine" / "ordinary.py").write_text("SEALED_SENTINEL = 'moved'\n")
    with pytest.raises(SourceCensusError, match="sealed"):
        census_sealed_sources(manifest)
