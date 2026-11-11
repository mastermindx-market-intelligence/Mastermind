"""Research JSON identity checks use committed values, independent of layout."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests import test_ceo_submit_armed_composition as guard


def _run_committed_data_case(
    tmp_path: Path, monkeypatch, document: str, *, rejected: bool,
    path: str = "research/data/sample.json", before: str | None = None,
    working_document: str | None = None,
) -> None:
    # A disposable repository is input to the real guard, not a company workspace.
    root = tmp_path / "repo"
    root.mkdir()
    template = root / "control.json.template"
    template.write_bytes(guard.TEMPLATE.read_bytes())
    candidate = root / path
    candidate.parent.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=D8DataFixture",
             "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", *args],
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout

    git("init", "-q")
    if before is not None:
        candidate.write_text(before, encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "fixture baseline")
    git("update-ref", "refs/remotes/origin/master", "HEAD")
    candidate.write_text(document, encoding="utf-8")
    git("add", "--", path)
    git("commit", "-q", "-m", "fixture candidate")
    assert git("show", f"HEAD:{path}") == document
    if working_document is not None:
        candidate.write_text(working_document, encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", root)
    monkeypatch.setattr(guard, "TEMPLATE", template)
    if rejected:
        with pytest.raises(AssertionError):
            guard.test_d8_template_topology_and_protected_defaults()
    else:
        guard.test_d8_template_topology_and_protected_defaults()


@pytest.mark.parametrize("indent", [None, 2], ids=["compact", "pretty"])
@pytest.mark.parametrize("value,rejected", [
    ({"endpoint": "forward_max_drawdown", "size": {"cells": 800}}, False),
    ({"allowed_peer_uids": [501]}, True),
], ids=["ordinary-count", "peer-identity"])
def test_research_data_original_examples_are_layout_independent(
    tmp_path, monkeypatch, indent, value, rejected,
):
    _run_committed_data_case(
        tmp_path, monkeypatch, json.dumps(value, indent=indent), rejected=rejected,
    )


@pytest.mark.parametrize("indent", [None, 2], ids=["compact", "pretty"])
@pytest.mark.parametrize("value,rejected", [
    ({"account": {"members": [{"id": 501}]}}, True),
    ({"groups": {"459": "service"}}, True),
    ({"UIDs": [501]}, True),
    ({"ＧＩＤｓ": [501]}, True),
    ({"endpoint": {"port": 443}}, True),
    ({"socket": {"value": "0x1cb"}}, True),
    ({"topology": {"members": ["4.59e2"]}}, True),
    ({"note": "/tmp/_mastermind_shadow"}, True),
    ({"note": "/tmp/＿mastermind＿shadow"}, True),
    ({"_mastermind_shadow": None}, True),
    ({"note": "x_mastermind_shadow"}, False),
    ({"metrics": {"members": [{"cells": 501}], "459": "sample"}}, False),
    ({"account": {"members": []}, "metrics": {"cells": 800}}, False),
])
def test_research_data_keeps_identity_context_and_account_boundaries(
    tmp_path, monkeypatch, indent, value, rejected,
):
    _run_committed_data_case(
        tmp_path, monkeypatch, json.dumps(value, indent=indent, ensure_ascii=False),
        rejected=rejected,
    )


@pytest.mark.parametrize("path,rejected", [
    ("research/data/sample.json", False),
    ("research/data/identity.json", True),
    ("research/data/peer/metrics.json", True),
])
def test_research_data_keeps_identity_bearing_path_context(
    tmp_path, monkeypatch, path, rejected,
):
    _run_committed_data_case(
        tmp_path, monkeypatch, '{"cells":800}', path=path, rejected=rejected,
    )


@pytest.mark.parametrize("path", [
    "/research/data/sample.json", "research/data/../sample.json",
    "research/data-lookalike/sample.json", "other/research/data/sample.json",
    "research/config/sample.json", "research/data/install.py",
])
def test_research_data_route_does_not_exempt_other_source(path):
    assert not guard._identity_guard_data_json_path(path)
    assert guard._identity_guard_source_path(path)


@pytest.mark.parametrize("identity", [False, True], ids=["count-edit", "uid-edit"])
def test_research_data_partial_edit_uses_committed_parent_context(
    tmp_path, monkeypatch, identity,
):
    if identity:
        before = {"account": {"members": [{"id": 1000}]}}
        after = {"account": {"members": [{"id": 501}]}}
        dirty = {"account": {"members": [{"id": 1000}]}}
    else:
        before = {"endpoint": "forward_max_drawdown", "size": {"cells": 799}}
        after = {"endpoint": "forward_max_drawdown", "size": {"cells": 800}}
        dirty = {"allowed_peer_uids": [501]}
    _run_committed_data_case(
        tmp_path, monkeypatch, json.dumps(after, indent=2),
        before=json.dumps(before, indent=2),
        working_document=json.dumps(dirty, indent=2), rejected=identity,
    )


@pytest.mark.parametrize("value,rejected", [
    ([800, {"cells": 501}], False), (501, False), (None, False),
    ("ordinary data", False), ("/tmp/_mastermind_shadow", True),
    ([{"allowed_peer_uids": [501]}], True),
])
def test_research_data_keeps_valid_json_root_types(tmp_path, monkeypatch, value, rejected):
    _run_committed_data_case(
        tmp_path, monkeypatch, json.dumps(value, indent=2), rejected=rejected,
    )


@pytest.mark.parametrize("key", ["note", "endpoint"])
def test_research_data_long_benign_text_is_not_an_identity(tmp_path, monkeypatch, key):
    value = {key: "https://example.invalid/" + "long-label/" * 100}
    _run_committed_data_case(
        tmp_path, monkeypatch, json.dumps(value), rejected=False,
    )


@pytest.mark.parametrize("document", [
    '{"cells":1,}', '{"cells":1} trailing',
    '{"allowed_peer_uids":[501],"allowed_peer_uids":[]}',
    '{"cells":NaN}', '{"cells":1e10000}',
    json.dumps({"peer_uid": "0" * 256 + "501"}),
    json.dumps({"peer_uid": "0x" + "0" * 256 + "1f5"}),
])
def test_research_data_ambiguous_or_unbounded_numeric_values_fail_closed(
    tmp_path, monkeypatch, document,
):
    _run_committed_data_case(tmp_path, monkeypatch, document, rejected=True)


@pytest.mark.parametrize("bound", ["utf8-bytes", "nodes", "depth"])
def test_research_data_profile_has_finite_structural_budgets(tmp_path, monkeypatch, bound):
    if bound == "utf8-bytes":
        document = json.dumps({"note": "界" * (4 * 1024 * 1024 // 3 + 1)}, ensure_ascii=False)
        assert len(document) < 4 * 1024 * 1024 < len(document.encode("utf-8"))
    elif bound == "nodes":
        document = json.dumps({"measurements": [0] * 100001})
    else:
        value = 0
        for _ in range(34):
            value = {"nested": value}
        document = json.dumps(value)
    _run_committed_data_case(tmp_path, monkeypatch, document, rejected=True)


def test_research_data_actual_reference_dataset_fits_the_profile(tmp_path, monkeypatch):
    document = (
        guard.ROOT / "research/data/trend_persistence_b2_reference.json"
    ).read_text(encoding="utf-8")
    assert len(document.encode("utf-8")) > 1024 * 1024
    _run_committed_data_case(tmp_path, monkeypatch, document, rejected=False)
