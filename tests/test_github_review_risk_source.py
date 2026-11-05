"""Exact authenticated PR-file census tests; no network or GitHub writes."""
from dataclasses import replace

import pytest

from control_plane.github_review_risk_policy import ReviewTier
from control_plane.github_review_risk_source import (
    PAGE_SIZE,
    RiskSourceUnavailable,
    SourceFile,
    SourcePR,
    assess_current_pr_risk,
)

REPO = "mastermindx-market-intelligence/Mastermind"
HEAD = "a" * 40
BASE = "b" * 40


def snap(*, changed_files=1, additions=4, deletions=2, **kwargs):
    return SourcePR(
        repository=REPO, pull_number=101, head_sha=HEAD, base_sha=BASE,
        head_repository=REPO, base_repository=REPO, open=True, draft=False,
        changed_files=changed_files, additions=additions, deletions=deletions,
        **kwargs,
    )


def file(path="docs/guide.md", status="modified", additions=4, deletions=2,
         previous_filename=None, patch_available=True):
    return SourceFile(
        filename=path, status=status, additions=additions,
        deletions=deletions, previous_filename=previous_filename,
        patch_available=patch_available,
    )


class Reader:
    def __init__(self, first=None, pages=None, final=None):
        self.first = first or snap()
        self.final = final if final is not None else self.first
        self.pages = pages if pages is not None else {1: (file(),)}
        self.reads = 0
        self.file_reads = []

    def read_pr_risk_source(self, *, repository, pull_number):
        assert repository == REPO and pull_number == 101
        self.reads += 1
        return self.first if self.reads == 1 else self.final

    def read_pr_risk_file_page(self, *, repository, pull_number, page, per_page):
        assert repository == REPO and pull_number == 101
        assert per_page == PAGE_SIZE
        self.file_reads.append(page)
        return self.pages.get(page, ())


def assess(reader):
    return assess_current_pr_risk(reader, repository=REPO, pull_number=101)


def test_complete_current_docs_can_skip_review():
    reader = Reader()
    result = assess(reader)
    assert result.tier is ReviewTier.FAST
    assert reader.reads == 2
    assert reader.file_reads == [1]


def test_renamed_from_protected_source_is_critical_even_if_new_name_looks_safe():
    reader = Reader(pages={1: (file(
        "docs/guide.md", status="renamed",
        previous_filename="control_plane/github_review_intent.py",
    ),)})
    assert assess(reader).tier is ReviewTier.CRITICAL


def test_one_line_auth_filename_is_critical():
    reader = Reader(
        first=snap(additions=1, deletions=0),
        pages={1: (file("backend/auth.py", additions=1, deletions=0),)},
    )
    assert assess(reader).tier is ReviewTier.CRITICAL


def test_bounded_backend_file_still_needs_smoke_ci():
    reader = Reader(pages={1: (file("server/handler.py"),)})
    assert assess(reader).tier is ReviewTier.STANDARD


def test_file_deletion_escalates_even_docs():
    reader = Reader(
        first=snap(additions=0, deletions=2),
        pages={1: (file("docs/help.md", status="removed", additions=0, deletions=2),)},
    )
    assert assess(reader).tier is ReviewTier.STANDARD


def test_complete_two_page_census():
    items = tuple(file(f"docs/user/page{i}.md", additions=1, deletions=0) for i in range(101))
    reader = Reader(first=snap(changed_files=101, additions=101, deletions=0),
                    pages={1: items[:100], 2: items[100:]})
    assert assess(reader).tier is ReviewTier.FAST
    assert reader.file_reads == [1, 2]


@pytest.mark.parametrize("changed", [
    {"head_sha": "c" * 40}, {"base_sha": "d" * 40},
    {"changed_files": 2}, {"additions": 5}, {"draft": True},
])
def test_recheck_catches_moved_or_changed_pr(changed):
    reader = Reader(final=replace(snap(), **changed))
    with pytest.raises(RiskSourceUnavailable):
        assess(reader)


@pytest.mark.parametrize("initial", [
    {"open": False}, {"draft": True},
    {"head_repository": "outside/fork"},
    {"changed_files": 0}, {"changed_files": 257},
    {"head_sha": "abc"}, {"base_sha": "def"},
])
def test_wrong_initial_source_never_enters_fast_lane(initial):
    reader = Reader(first=replace(snap(), **initial))
    with pytest.raises(RiskSourceUnavailable):
        assess(reader)
    assert reader.file_reads == []


def test_incomplete_final_page_refused():
    reader = Reader(first=snap(changed_files=2), pages={1: (file(),)})
    with pytest.raises(RiskSourceUnavailable, match="PAGINATION"):
        assess(reader)


def test_stats_mismatch_refused():
    reader = Reader(first=snap(additions=5))
    with pytest.raises(RiskSourceUnavailable, match="STATS"):
        assess(reader)


@pytest.mark.parametrize("bad_file", [
    file(status="unknown"),
    file(status="renamed", previous_filename=None),
    file("backend/server.py", patch_available=False),
    file("docs/guide.md", additions=-1),
    file("../escape.md"),
    file("docs/README.md", previous_filename="old.md"),
])
def test_malformed_file_source_refused(bad_file):
    reader = Reader(pages={1: (bad_file,)})
    with pytest.raises(RiskSourceUnavailable):
        assess(reader)


def test_binary_image_without_patch_can_still_be_fast():
    reader = Reader(
        first=snap(additions=0, deletions=0),
        pages={1: (file("docs/chart.png", additions=0, deletions=0, patch_available=False),)},
    )
    assert assess(reader).tier is ReviewTier.FAST



def test_visual_code_with_executable_test_change_is_standard_even_with_large_proof():
    """Source budget excludes verified screenshots/logs/tests, not code."""
    files = (
        file("terminal/components/ChartPanel.tsx", additions=20, deletions=5),
        file("terminal/docs/verification/prophet-marker/run.log",
             additions=1200, deletions=0, patch_available=False),
        file("terminal/e2e/replay-temporal-authority.spec.ts",
             additions=100, deletions=0),
        file("terminal/docs/verification/prophet-marker/crop.webp",
             additions=0, deletions=0, patch_available=False),
    )
    reader = Reader(
        first=snap(changed_files=4, additions=1320, deletions=5),
        pages={1: files},
    )
    # An executable e2e test is not passive evidence. The final review gate
    # remains unless a trusted semantic qualifier proves it presentation-only.
    assert assess(reader).tier is ReviewTier.STANDARD


def test_proof_artifact_missing_patch_does_not_hide_authority_path():
    reader = Reader(
        first=snap(additions=1, deletions=0),
        pages={1: (file("docs/DELIVERY_WORKFLOW.md",
                         additions=1, deletions=0, patch_available=False),)},
    )
    with pytest.raises(RiskSourceUnavailable, match="PR_CODE_PATCH_MISSING"):
        assess(reader)


def test_sensitive_renamed_code_not_masked_by_evidence_scope():
    reader = Reader(
        first=snap(additions=1, deletions=0),
        pages={1: (file("docs/verification/new.md", status="renamed",
                         additions=1, deletions=0,
                         previous_filename="backend/auth.py"),)},
    )
    assert assess(reader).tier is ReviewTier.CRITICAL
