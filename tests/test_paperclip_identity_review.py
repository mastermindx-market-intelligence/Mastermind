"""Preserve D8 while reviewing the exact Paperclip HTTPS default-port token."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import (
    _d8_frozen_source_diff,
    _scan_added_identity_diff,
)

ROOT = Path(__file__).parents[1]
SOURCE_PATH = "integrations/paperclip_hermes/core_overlay/agent/launch_credential_binding.py"
SOURCE_SHA256 = "376e06c81f0cf6dbf859931f76e58fb9784ccee3cc56236cb9f5fac20c45c318"


def _source():
    return (ROOT / SOURCE_PATH).read_text(encoding="utf-8")


def _scan(source, *, path=SOURCE_PATH, postimage=True):
    return _scan_added_identity_diff(
        _d8_frozen_source_diff(path, source),
        source_postimages={path: source} if postimage else None,
    )


def test_exact_source_and_single_added_line_review_only_https_token():
    source = _source()
    assert hashlib.sha256(source.encode()).hexdigest() == SOURCE_SHA256
    assert reviewed_literal_spans(SOURCE_PATH, source) == ((150, 19, 22, "int"),)
    assert _scan(source) == []
    line = source.splitlines()[149]
    diff = (f"--- a/{SOURCE_PATH}\n+++ b/{SOURCE_PATH}\n"
            f"@@ -150 +150 @@\n+{line}\n")
    assert _scan_added_identity_diff(diff, source_postimages={SOURCE_PATH: source}) == []


@pytest.mark.parametrize("postimage,path", [
    (False, SOURCE_PATH),
    (True, "integrations/paperclip_hermes/core_overlay/agent/unreviewed_binding.py"),
    (True, "control_plane/unreviewed_binding.py"),
])
def test_missing_postimage_or_different_path_remains_guarded(postimage, path):
    assert _scan(_source(), path=path, postimage=postimage) == ["443"]


@pytest.mark.parametrize("old,new,expected", [
    ("port = 443", "port = 444", ["444"]),
    ("if port is None:", "if port == 0:", ["443"]),
    ("else 80", "else 501", ["443", "501"]),
    ("port = 443", "port = (443, 501)[0]", ["443", "501"]),
    ("url.hostname.lower()", "url.hostname.upper()", ["443"]),
])
def test_numeric_or_origin_context_drift_is_not_reviewed(old, new, expected):
    source = _source()
    assert source.count(old) == 1
    changed = source.replace(old, new)
    assert reviewed_literal_spans(SOURCE_PATH, changed) == ()
    assert _scan(changed) == expected


@pytest.mark.parametrize("suffix,expected", [
    ("\npeer_uid = 443\n", ["443", "443"]),
    ("\npeer_gid = 501\n", ["443", "501"]),
    ('\naccount = "_mastermind_unreviewed"\n', ["443", "_mastermind_unreviewed"]),
    ("\n# unrelated byte drift\n", ["443"]),
])
def test_extra_identity_or_unrelated_drift_restores_original_guard(suffix, expected):
    assert _scan(_source() + suffix) == expected


def test_false_diff_postimage_pair_is_rejected():
    source = _source()
    changed_line = source.splitlines()[149].replace("443", "444")
    diff = (f"--- a/{SOURCE_PATH}\n+++ b/{SOURCE_PATH}\n"
            f"@@ -150 +150 @@\n+{changed_line}\n")
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(diff, source_postimages={SOURCE_PATH: source})


def test_removing_registry_entry_restores_original_finding(monkeypatch):
    monkeypatch.delitem(REVIEWED_FILES, SOURCE_PATH)
    assert reviewed_literal_spans(SOURCE_PATH, _source()) == ()
    assert _scan(_source()) == ["443"]


EVIDENCE_PATH = "ops/paperclip_fleet/evidence/2026-11-10-credential-qualification.json"
EVIDENCE_SHA256 = "a38fbcfe551c322dfc88d618b328ad9ab1438200493bdd2fe61aaeebe00f6554"
EVIDENCE_SPANS = ((604, 17, 20, "int"), (684, 15, 18, "int"), (690, 15, 18, "int"))


def _evidence():
    return (ROOT / EVIDENCE_PATH).read_text(encoding="utf-8")


def test_exact_metadata_record_reviews_only_existing_owner_observations():
    source = _evidence()
    assert hashlib.sha256(source.encode()).hexdigest() == EVIDENCE_SHA256
    assert reviewed_literal_spans(EVIDENCE_PATH, source) == EVIDENCE_SPANS
    assert _scan(source, path=EVIDENCE_PATH) == []


@pytest.mark.parametrize("postimage,path", [
    (False, EVIDENCE_PATH),
    (True, "ops/paperclip_fleet/evidence/unreviewed-qualification.json"),
    (True, "control_plane/unreviewed-qualification.json"),
])
def test_owner_metadata_requires_exact_record_path_and_postimage(postimage, path):
    assert _scan(_evidence(), path=path, postimage=postimage) == ["501"] * 3


@pytest.mark.parametrize("span", EVIDENCE_SPANS)
def test_each_owner_observation_drift_restores_all_checks(span):
    source = _evidence()
    lines = source.splitlines(keepends=True)
    row, start, end, _kind = span
    line = lines[row - 1]
    assert line[start:end] == "501"
    lines[row - 1] = line[:start] + "502" + line[end:]
    changed = "".join(lines)
    assert reviewed_literal_spans(EVIDENCE_PATH, changed) == ()
    findings = _scan(changed, path=EVIDENCE_PATH)
    assert findings.count("501") == 2 and findings.count("502") == 1


def test_metadata_whitespace_drift_restores_original_guard():
    assert _scan(_evidence() + "\n", path=EVIDENCE_PATH) == ["501"] * 3


def test_added_metadata_identity_is_not_hidden():
    import json

    value = json.loads(_evidence())
    value["peer_uid"] = 503
    changed = json.dumps(value, indent=2) + "\n"
    findings = _scan(changed, path=EVIDENCE_PATH)
    assert findings.count("501") == 3 and findings.count("503") == 1


def test_metadata_registry_removal_restores_original_findings(monkeypatch):
    monkeypatch.delitem(REVIEWED_FILES, EVIDENCE_PATH)
    assert reviewed_literal_spans(EVIDENCE_PATH, _evidence()) == ()
    assert _scan(_evidence(), path=EVIDENCE_PATH) == ["501"] * 3


def test_metadata_diff_cannot_claim_another_postimage():
    source = _evidence()
    row, _start, _end, _kind = EVIDENCE_SPANS[0]
    changed_line = source.splitlines()[row - 1].replace("501", "502")
    diff = (f"--- a/{EVIDENCE_PATH}\n+++ b/{EVIDENCE_PATH}\n"
            f"@@ -{row} +{row} @@\n+{changed_line}\n")
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(diff, source_postimages={EVIDENCE_PATH: source})
