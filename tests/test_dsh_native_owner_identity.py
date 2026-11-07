"""Source-bound HTTP response tokens; no generic identity-scan exclusion."""
import hashlib
import pytest
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import ROOT, _d8_frozen_source_diff, _scan_added_identity_diff

PATH = "integrations/deepseek_harness/runtime_compat/native-owner-access.patch"
SHA = "81658504603d40b53eb288c9f206ba7646128cfab9f4e81ff6c58863623bbb00"


def scan(source, path=PATH, postimage=True):
    return _scan_added_identity_diff(_d8_frozen_source_diff(path, source),
        source_postimages={path: source} if postimage else None)


def test_only_four_exact_http_status_tokens_are_reviewed():
    source = (ROOT / PATH).read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == SHA
    spans = reviewed_literal_spans(PATH, source)
    assert len(spans) == 4
    assert [source.splitlines()[line-1][start:end] for line, start, end, kind in spans] == ["403", "403", "403", "405"]
    assert all(kind == "int" for line, start, end, kind in spans)
    assert scan(source) == []


@pytest.mark.parametrize("path,postimage,expected", [
    (PATH, False, ["403", "403", "403", "405"]),
    ("integrations/foreign.patch", True, ["403", "403"]),
])
def test_original_path_and_complete_postimage_are_required(path, postimage, expected):
    source = (ROOT / PATH).read_text()
    if path != PATH:
        assert reviewed_literal_spans(path, source) == ()
    assert scan(source, path, postimage) == expected


@pytest.mark.parametrize("suffix", ["\n# changed source\n", "\n+peer_uid = 501\n"])
def test_drift_restores_status_visibility_and_preserves_added_identity_refusal(suffix):
    source = (ROOT / PATH).read_text() + suffix
    assert reviewed_literal_spans(PATH, source) == ()
    assert scan(source) == ["403", "403", "403", "405"] + (["501"] if "501" in suffix else [])


def test_false_postimage_cannot_reuse_the_witness():
    source = (ROOT / PATH).read_text()
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _scan_added_identity_diff(_d8_frozen_source_diff(PATH, source),
            source_postimages={PATH: source.replace("status: 403", "status: 459")})
