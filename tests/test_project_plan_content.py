"""Actual negative and positive tests for the pure plan-content comparator.

These tests exercise the real producer directly. No producer behavior is
mocked, no private repository data is embedded, and no adoption/first-pass or
product claim is made: this is a bounded pure-function contract suite.
"""

import hashlib
import json

import pytest

from control_plane.project_plan_content import compare_plan_content

MACRO_REPO = "mastermindx-market-intelligence/macro"
MASTERMIND_REPO = "mastermindx-market-intelligence/Mastermind"

AVAILABLE_KEYS = {
    "state",
    "base_source",
    "candidate_sha256",
    "base_text",
    "candidate_text",
    "diff",
    "identical",
    "added_lines",
    "removed_lines",
}

RESULT_BUDGET_BYTES = 65536


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def synthetic_commit():
    return "0123456789abcdef0123456789abcdef01234567"


_UNSET = object()


def make_source(
    path="docs/plans/proposal.md",
    body=b"# plan\n\ntext\n",
    repository=MACRO_REPO,
    commit=_UNSET,
    content_sha256=_UNSET,
):
    return {
        "repository": repository,
        "path": path,
        "commit": synthetic_commit() if commit is _UNSET else commit,
        "content_sha256": (
            sha256_hex(body) if content_sha256 is _UNSET else content_sha256
        ),
    }


def compare(source, base, candidate_sha, candidate):
    return compare_plan_content(
        base_source=source,
        base_bytes=base,
        candidate_sha256=candidate_sha,
        candidate_bytes=candidate,
    )


def assert_available(result):
    assert isinstance(result, dict)
    assert set(result) == AVAILABLE_KEYS
    assert result["state"] == "AVAILABLE"
    return result


def assert_refusal(result, reason):
    assert result == {"state": "UNAVAILABLE", "reason": reason}
    return result


def serialized_available_length(result):
    payload = json.dumps(
        result,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return len(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
# Positive: authentic bodies
# ---------------------------------------------------------------------------


def test_authentic_identical_bodies_are_available_with_empty_diff():
    body = b"# Plan\n\n- item one\n- item two\n"
    result = assert_available(compare(make_source(body=body), body, sha256_hex(body), body))
    assert result["identical"] is True
    assert result["diff"] == ""
    assert result["added_lines"] == 0
    assert result["removed_lines"] == 0
    assert result["base_text"] == body.decode("utf-8")
    assert result["candidate_text"] == body.decode("utf-8")
    assert result["base_source"] == make_source(body=body)
    assert result["candidate_sha256"] == sha256_hex(body)


def test_second_mastermind_repository_is_accepted():
    body = b"# Plan\n"
    source = make_source(body=body, repository=MASTERMIND_REPO)
    result = assert_available(compare(source, body, sha256_hex(body), body))
    assert result["base_source"]["repository"] == MASTERMIND_REPO


def test_source_ref_equality_alone_never_returns_available():
    body = b"# Plan\n"
    source = make_source(body=body)
    # Recorded digest matches the actual base bytes exactly, but the
    # candidate body is absent: still honestly unavailable.
    assert_refusal(
        compare(source, body, sha256_hex(body), None),
        "SOURCE_UNAVAILABLE",
    )
    assert_refusal(compare(source, None, sha256_hex(body), body), "SOURCE_UNAVAILABLE")
    assert_refusal(compare(source, None, sha256_hex(body), None), "SOURCE_UNAVAILABLE")


def test_available_serialization_is_compact_utf8_within_budget():
    body = b"# Plan\n\ncaf\xc3\xa9 \xe2\x9c\x93 line\n" * 4
    result = assert_available(compare(make_source(body=body), body, sha256_hex(body), body))
    length = serialized_available_length(result)
    assert length <= RESULT_BUDGET_BYTES
    # Non-ASCII content survives as exact characters, not escapes.
    assert "café ✓ line\n" in result["base_text"]


# ---------------------------------------------------------------------------
# Newline, BOM, Unicode fidelity
# ---------------------------------------------------------------------------


def test_lf_vs_crlf_is_meaningful_and_hashes_differ():
    lf_body = b"# Plan\nalpha\nbeta\n"
    crlf_body = b"# Plan\r\nalpha\r\nbeta\r\n"
    assert sha256_hex(lf_body) != sha256_hex(crlf_body)
    result = assert_available(
        compare(make_source(body=lf_body), lf_body, sha256_hex(crlf_body), crlf_body)
    )
    assert result["identical"] is False
    assert result["diff"] != ""
    assert result["base_text"] == lf_body.decode("utf-8")
    assert result["candidate_text"] == crlf_body.decode("utf-8")
    assert result["candidate_sha256"] == sha256_hex(crlf_body)


def test_lf_vs_crlf_hash_substitution_is_bytes_mismatch():
    lf_body = b"# Plan\nalpha\nbeta\n"
    crlf_body = b"# Plan\r\nalpha\r\nbeta\r\n"
    source = make_source(body=lf_body)
    # Candidate digest recorded for the LF body but CRLF bytes supplied.
    assert_refusal(
        compare(source, lf_body, sha256_hex(lf_body), crlf_body),
        "SOURCE_BYTES_MISMATCH",
    )


def test_bom_difference_is_meaningful_and_preserved():
    with_bom = b"\xef\xbb\xbf# Plan\nalpha\n"
    without_bom = b"# Plan\nalpha\n"
    result = assert_available(
        compare(
            make_source(body=with_bom),
            with_bom,
            sha256_hex(without_bom),
            without_bom,
        )
    )
    assert result["identical"] is False
    assert result["base_text"].startswith("\ufeff")
    assert result["candidate_text"].startswith("# Plan")
    assert result["base_text"] == with_bom.decode("utf-8")
    assert result["diff"] != ""


def test_unicode_bodies_preserved_without_normalization():
    nfc = "café\n".encode("utf-8")
    nfd = "cafe\u0301\n".encode("utf-8")
    assert nfc != nfd
    result = assert_available(compare(make_source(body=nfc), nfc, sha256_hex(nfd), nfd))
    assert result["identical"] is False
    assert result["base_text"] == "café\n"
    assert result["candidate_text"] == "cafe\u0301\n"
    assert result["diff"] != ""
    assert serialized_available_length(result) <= RESULT_BUDGET_BYTES


def test_no_final_newline_difference_is_meaningful():
    with_newline = b"# Plan\nbody\n"
    without_newline = b"# Plan\nbody"
    result = assert_available(
        compare(
            make_source(body=without_newline),
            without_newline,
            sha256_hex(with_newline),
            with_newline,
        )
    )
    assert result["identical"] is False
    assert result["diff"] != ""
    assert result["candidate_text"] == "# Plan\nbody\n"


# ---------------------------------------------------------------------------
# Digest substitution / invalid UTF-8
# ---------------------------------------------------------------------------


def test_base_hash_substitution_is_bytes_mismatch():
    body = b"# Plan\nalpha\n"
    other = b"# Plan\nALPHA\n"
    source = make_source(body=body, content_sha256=sha256_hex(body))
    assert_refusal(
        compare(source, other, sha256_hex(other), other),
        "SOURCE_BYTES_MISMATCH",
    )


def test_candidate_hash_substitution_is_bytes_mismatch():
    body = b"# Plan\nalpha\n"
    other = b"# Plan\nALPHA\n"
    source = make_source(body=body)
    assert_refusal(
        compare(source, body, sha256_hex(body), other),
        "SOURCE_BYTES_MISMATCH",
    )


def test_invalid_utf8_body_is_bytes_mismatch():
    body = b"# Plan\n\xff\xfe\x80\n"
    source = make_source(body=body)
    assert_refusal(
        compare(source, body, sha256_hex(body), body),
        "SOURCE_BYTES_MISMATCH",
    )
    assert_refusal(
        compare(source, body, sha256_hex(body), b"# ok\n"),
        "SOURCE_BYTES_MISMATCH",
    )


# ---------------------------------------------------------------------------
# Absent body vs malformed metadata precedence
# ---------------------------------------------------------------------------


def test_null_body_with_invalid_metadata_is_invalid_content():
    body = b"# Plan\n"
    source = make_source(body=body, commit="ZZZZ")
    assert_refusal(compare(source, body, sha256_hex(body), None), "INVALID_CONTENT")
    assert_refusal(compare(source, None, "not-a-hash", None), "INVALID_CONTENT")


def test_null_body_with_invalid_candidate_digest_is_invalid_content():
    body = b"# Plan\n"
    for bad in ("", "A" * 64, sha256_hex(body) + "\n", 123, True, None):
        assert_refusal(
            compare(make_source(body=body), body, bad, None),
            "INVALID_CONTENT",
        )


# ---------------------------------------------------------------------------
# Body type refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_body", [True, False, 123, "bytes", [b"# Plan\n"], bytearray(b"# Plan\n"), memoryview(b"# Plan\n")])
def test_non_bytes_body_is_invalid_content(bad_body):
    body = b"# Plan\nalpha\n"
    source = make_source(body=body)
    digest = sha256_hex(body)
    assert_refusal(compare(source, bad_body, digest, body), "INVALID_CONTENT")
    assert_refusal(compare(source, body, digest, bad_body), "INVALID_CONTENT")


# ---------------------------------------------------------------------------
# Recorded path refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "/docs/plans/proposal.md",
        "docs\\plans\\proposal.md",
        "docs\\proposal.md",
        "",
        ".",
        "..",
        "docs/../proposal.md",
        "docs//proposal.md",
        "docs/",
        "https://example.com/proposal.md",
        "docs/plan\x00.md",
        "docs/plan\r.md",
        "docs/plan\n.md",
        "docs/proposal.txt",
        "a" * 513,
    ],
)
def test_malformed_paths_are_invalid_content(bad_path):
    body = b"# Plan\n"
    source = make_source(path=bad_path, body=body)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize("bad_path", [123, True, None, b"docs/proposal.md", ["docs/proposal.md"]])
def test_non_string_paths_are_invalid_content(bad_path):
    body = b"# Plan\n"
    source = make_source(path=bad_path, body=body)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


def test_path_length_boundaries():
    body = b"# Plan\n"
    prefix = "docs/"
    path_512 = prefix + "a" * (512 - len(prefix) - 3) + ".md"
    assert len(path_512) == 512
    source = make_source(path=path_512, body=body)
    assert_available(compare(source, body, sha256_hex(body), body))
    path_513 = prefix + "a" * (513 - len(prefix) - 3) + ".md"
    assert len(path_513) == 513
    assert_refusal(
        compare(make_source(path=path_513, body=body), body, sha256_hex(body), body),
        "INVALID_CONTENT",
    )


# ---------------------------------------------------------------------------
# Repository / commit / digest shape refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_repository",
    [
        "other/repo",
        "mastermindx-market-intelligence/Macro",
        "mastermindx-market-intelligence/macro/",
        "mastermindx-market-intelligence/macro/extra",
        "/mastermindx-market-intelligence/macro",
        "mastermindx-market-intelligence",
        "",
        "mastermindx-market-intelligence/macro\n",
        123,
        True,
        None,
    ],
)
def test_wrong_repositories_are_invalid_content(bad_repository):
    body = b"# Plan\n"
    source = make_source(repository=bad_repository, body=body)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize(
    "bad_commit",
    [
        "A" * 40,
        "0" * 39,
        "0" * 41,
        synthetic_commit() + "\n",
        synthetic_commit()[:-1] + "g",
        123,
        True,
        None,
        [],
    ],
)
def test_malformed_commits_are_invalid_content(bad_commit):
    body = b"# Plan\n"
    source = make_source(commit=bad_commit, body=body)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize(
    "bad_digest",
    [
        "A" * 64,
        "0" * 63,
        "0" * 65,
        sha256_hex(b"# Plan\n") + "\n",
        "  " + sha256_hex(b"# Plan\n"),
        "0x" + "0" * 62,
        123,
        True,
        None,
        {},
    ],
)
def test_malformed_digests_are_invalid_content(bad_digest):
    body = b"# Plan\n"
    source = make_source(body=body, content_sha256=bad_digest)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize(
    "field",
    ["repository", "path", "commit", "content_sha256"],
)
def test_non_string_field_values_are_invalid_content(field):
    body = b"# Plan\n"
    for bad_value in (True, 123, None, ["x"], {"x": 1}):
        source = make_source(body=body)
        source[field] = bad_value
        assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update({"extra": 1}),
        lambda s: s.pop("content_sha256"),
        lambda s: s.pop("repository"),
        lambda s: s.pop("path"),
        lambda s: s.pop("commit"),
    ],
)
def test_extra_or_missing_source_fields_are_invalid_content(mutate):
    body = b"# Plan\n"
    source = make_source(body=body)
    mutate(source)
    assert_refusal(compare(source, body, sha256_hex(body), body), "INVALID_CONTENT")


@pytest.mark.parametrize("bad_source", [None, 123, True, "source", ["x"], ("docs/a.md",), {}])
def test_non_dict_source_is_invalid_content(bad_source):
    body = b"# Plan\n"
    assert_refusal(
        compare(bad_source, body, sha256_hex(body), body),
        "INVALID_CONTENT",
    )


# ---------------------------------------------------------------------------
# Input cap boundaries
# ---------------------------------------------------------------------------


def _exact_base_limit_body():
    return b"x\n" * 131072  # exactly 262144 bytes


def _exact_candidate_limit_body():
    return b"y\n" * 65536  # exactly 131072 bytes


def test_base_body_one_byte_over_input_cap_is_content_over_budget():
    base = _exact_base_limit_body() + b"x"  # 262145 bytes
    candidate = b"# small\n"
    source = make_source(body=base)
    result = compare(source, base, sha256_hex(candidate), candidate)
    assert_refusal(result, "CONTENT_OVER_BUDGET")


def test_candidate_body_one_byte_over_input_cap_is_content_over_budget():
    base = b"# small\n"
    candidate = _exact_candidate_limit_body() + b"y"  # 131073 bytes
    source = make_source(body=base)
    result = compare(source, base, sha256_hex(candidate), candidate)
    assert_refusal(result, "CONTENT_OVER_BUDGET")


def test_bodies_at_exact_input_caps_are_honestly_unavailable():
    # Both exact-limit bodies are valid inputs, but any AVAILABLE payload would
    # embed the full texts, so the 65536-byte result budget is exceeded and the
    # outcome is honestly CONTENT_OVER_BUDGET with no partial body.
    base = _exact_base_limit_body()
    source = make_source(body=base)
    assert_refusal(
        compare(source, base, sha256_hex(base), base),
        "CONTENT_OVER_BUDGET",
    )
    candidate = _exact_candidate_limit_body()
    small = b"# small\n"
    assert_refusal(
        compare(make_source(body=small), small, sha256_hex(candidate), candidate),
        "CONTENT_OVER_BUDGET",
    )


def test_oversize_body_is_refused_before_digest_verification():
    base = b"a" * 262145
    source = make_source(body=base)  # digest does not match these bytes
    candidate = b"# small\n"
    result = compare(source, base, sha256_hex(candidate), candidate)
    assert_refusal(result, "CONTENT_OVER_BUDGET")


def test_empty_body_is_outside_input_range():
    body = b"# Plan\n"
    source = make_source(body=body)
    assert_refusal(compare(source, b"", sha256_hex(body), body), "CONTENT_OVER_BUDGET")
    assert_refusal(compare(source, body, sha256_hex(body), b""), "CONTENT_OVER_BUDGET")


def test_absent_body_takes_precedence_over_oversize():
    base = b"a" * 262145
    source = make_source(body=base)
    assert_refusal(compare(source, base, sha256_hex(base), None), "SOURCE_UNAVAILABLE")
    assert_refusal(compare(source, None, sha256_hex(base), base), "SOURCE_UNAVAILABLE")


def test_body_type_takes_precedence_over_oversize():
    base = "a" * 262145  # a str, not bytes: malformed type wins
    source = make_source(body=b"# small\n")
    assert_refusal(
        compare(source, base, sha256_hex(b"# small\n"), b"# small\n"),
        "INVALID_CONTENT",
    )


# ---------------------------------------------------------------------------
# Result budget boundary (exact, no hidden clipping)
# ---------------------------------------------------------------------------


def _padded_candidate(padding_len):
    return b"# Plan\nline\n" + b"x" * padding_len + b"\n"


def _probe_output_budget(padding_len):
    """Return True when this candidate still fits the fixed output budget.

    Every probe independently asserts the producer's budget claim: an
    AVAILABLE payload serializes at or under 65536 bytes, and a refusal is the
    exact closed dict with no partial diff or body.
    """
    base = b"# Plan\nline\n"
    candidate = _padded_candidate(padding_len)
    result = compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    if result["state"] == "AVAILABLE":
        assert serialized_available_length(result) <= RESULT_BUDGET_BYTES
        return True
    assert_refusal(result, "CONTENT_OVER_BUDGET")
    return False


def test_output_budget_boundary_is_exact():
    assert _probe_output_budget(0)
    assert not _probe_output_budget(60000)
    lo, hi = 0, 60000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _probe_output_budget(mid):
            lo = mid
        else:
            hi = mid
    # lo is the largest padding whose payload still fits; one more byte and
    # the whole result is refused, never clipped.
    assert _probe_output_budget(lo)
    assert not _probe_output_budget(lo + 1)
    boundary = _padded_candidate(lo)
    result = compare(
        make_source(body=b"# Plan\nline\n"),
        b"# Plan\nline\n",
        sha256_hex(boundary),
        boundary,
    )
    assert serialized_available_length(result) <= RESULT_BUDGET_BYTES


# ---------------------------------------------------------------------------
# Repeated lines and counts
# ---------------------------------------------------------------------------


def test_many_repeated_lines_stay_within_budget():
    base = b"dup\n" * 400
    candidate = b"dup\n" * 401
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["identical"] is False
    assert result["diff"] != ""
    assert serialized_available_length(result) <= RESULT_BUDGET_BYTES
    # Counts mirror the pinned unified_diff's own matcher, whatever its
    # repeated-line heuristic decides, so they are asserted only as bounded
    # non-negative integers here.
    assert isinstance(result["added_lines"], int)
    assert isinstance(result["removed_lines"], int)
    assert result["added_lines"] >= 1
    assert result["removed_lines"] >= 0


def test_huge_repeated_lines_exceeding_result_budget_are_honestly_unavailable():
    base = b"dup\n" * 20000  # 80000 bytes, still inside the input caps
    source = make_source(body=base)
    result = compare(source, base, sha256_hex(base), base)
    assert_refusal(result, "CONTENT_OVER_BUDGET")


def test_line_counts_pure_insert():
    base = b"a\nb\n"
    candidate = b"a\nnew\nb\n"
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["added_lines"] == 1
    assert result["removed_lines"] == 0


def test_line_counts_pure_delete():
    base = b"a\nold\nb\n"
    candidate = b"a\nb\n"
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["added_lines"] == 0
    assert result["removed_lines"] == 1


def test_line_counts_replace_contributes_both_sides():
    base = b"a\nold\nb\n"
    candidate = b"a\nnew1\nnew2\nb\n"
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["added_lines"] == 2
    assert result["removed_lines"] == 1


def test_line_counts_same_arity_replacement():
    base = b"a\nold1\nb\n"
    candidate = b"a\nold2\nb\n"
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["added_lines"] == 1
    assert result["removed_lines"] == 1
    assert result["identical"] is False


def test_line_counts_multiple_hunks_sum_over_all_changes():
    base = b"one\ntwo\nthree\nfour\nfive\n"
    candidate = b"ONE\ntwo\nthree\nfour\nFIVE\nSIX\n"
    result = assert_available(
        compare(make_source(body=base), base, sha256_hex(candidate), candidate)
    )
    assert result["added_lines"] == 3
    assert result["removed_lines"] == 2


# ---------------------------------------------------------------------------
# Diff labels and detachment
# ---------------------------------------------------------------------------


def test_diff_labels_are_fixed_and_never_caller_paths():
    base = b"# Plan\nalpha\n"
    candidate = b"# Plan\nalpha\nbeta\n"
    path = "docs/plans/proposal.md"
    source = make_source(path=path, body=base)
    result = assert_available(compare(source, base, sha256_hex(candidate), candidate))
    diff_lines = result["diff"].splitlines()
    assert diff_lines[0] == "--- recorded-base"
    assert diff_lines[1] == "+++ proposal-candidate"
    assert path not in result["diff"]
    assert MACRO_REPO not in result["diff"]
    assert "proposal.md" not in result["diff"]


def test_source_output_is_detached_and_closed():
    body = b"# Plan\nalpha\n"
    source = make_source(body=body)
    snapshot = dict(source)
    result = assert_available(compare(source, body, sha256_hex(body), body))
    assert result["base_source"] is not source
    assert result["base_source"] == snapshot
    source["path"] = "docs/tampered.md"
    source["extra"] = "no"
    assert result["base_source"] == snapshot
    assert set(result["base_source"]) == {
        "repository",
        "path",
        "commit",
        "content_sha256",
    }
    for forbidden in ("current", "adopted", "version", "approved"):
        assert forbidden not in result
        assert forbidden not in result["base_source"]
    result["base_source"]["path"] = "docs/mutated.md"
    assert source["path"] == "docs/tampered.md"


# ---------------------------------------------------------------------------
# Robustness: malformed plain data never raises
# ---------------------------------------------------------------------------


def test_malformed_plain_data_never_raises_and_never_echoes_caller_values():
    body = b"# Plan\n"
    digest = sha256_hex(body)
    good = make_source(body=body)
    malformed_sources = [
        None,
        123,
        True,
        "source",
        ["x"],
        ("docs/a.md",),
        {"repository": MACRO_REPO},
        dict(good, extra=1),
        {
            b"repository": MACRO_REPO,
            "path": "docs/a.md",
            "commit": synthetic_commit(),
            "content_sha256": digest,
        },
        dict(good, repository=5),
        dict(good, path=True),
        dict(good, commit=None),
        dict(good, content_sha256=[]),
    ]
    candidate_values = [
        None,
        body,
        True,
        "text",
        1.5,
        [],
        {},
        bytearray(body),
        memoryview(body),
    ]
    allowed_reasons = {
        "SOURCE_UNAVAILABLE",
        "SOURCE_BYTES_MISMATCH",
        "INVALID_CONTENT",
        "CONTENT_OVER_BUDGET",
    }
    for bad_source in malformed_sources:
        for candidate_value in candidate_values:
            result = compare(bad_source, body, digest, candidate_value)
            assert isinstance(result, dict)
            assert set(result) == {"state", "reason"}
            assert result["state"] == "UNAVAILABLE"
            assert result["reason"] in allowed_reasons


def test_signature_is_keyword_only():
    body = b"# Plan\n"
    with pytest.raises(TypeError):
        compare_plan_content(make_source(body=body), body, sha256_hex(body), body)
