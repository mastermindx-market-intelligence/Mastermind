"""Actual imported-module checks for bounded request-local history batching.

The remote worker's AST-only evidence is retained separately. Repository
acceptance requires the real module and dependencies; there is no fallback
that can hide import or global-name defects. No subprocess/store effects.
"""
import ast
import hashlib
from pathlib import Path

import pytest

_HELPERS = ("_HISTORY_BATCH_BYTES", "_HISTORY_LOG_BYTES", "_RECORD_BYTES",
    "_history_request", "_parse_history_batch", "_parse_history_log",
    "ProjectPlanSourceUnavailable")

PATH = "agentos/workstreams/WS-ONE.md"
DATES = ["2026-11-0%dT00:00:00Z" % day for day in range(1, 9)]
CONTENTS = [b"revision %d of the authored workstream record\n" % index for index in range(1, 9)]
COMMITS = ["%040x" % index for index in range(1, 9)]
PAIRS = list(zip(COMMITS, DATES))


def _module_path():
    here = Path(__file__).resolve()
    for base in (here.parents[1], here.parent):
        candidate = base / "control_plane" / "agentos_project_plan.py"
        if not candidate.is_file():
            candidate = base / "agentos_project_plan.py"
        if candidate.is_file():
            return candidate
    return None


@pytest.fixture(scope="module")
def helpers():
    # Repository checks must import the real module and its dependencies. The
    # worker's AST-only remote fallback is not used for source acceptance.
    import control_plane.agentos_project_plan as module
    return {name: getattr(module, name) for name in _HELPERS}


def blob_oid(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def log_output(pairs):
    return "".join(commit + "\x00" + date + "\x00\n" for commit, date in pairs)


def batch_output(contents):
    pieces = []
    for content in contents:
        pieces.append(blob_oid(content).encode("ascii") + b" blob "
            + str(len(content)).encode("ascii") + b"\n" + content + b"\n")
    return b"".join(pieces).decode("utf-8")


def expected_records(pairs, contents):
    return [{"commit": commit, "committed_at": date,
             "content_sha256": hashlib.sha256(content).hexdigest()}
            for (commit, date), content in zip(pairs, contents)]


def test_eight_real_revisions_preserve_commit_date_order_and_identity(helpers):
    assert helpers["_parse_history_log"](log_output(PAIRS)) == PAIRS
    assert helpers["_parse_history_batch"](PAIRS, batch_output(CONTENTS)) == expected_records(PAIRS, CONTENTS)


def test_exact_ref_dedup_and_one_fixed_request_line_per_selector(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    duplicated = [(COMMITS[0], DATES[0]), (COMMITS[1], DATES[1]), (COMMITS[0], DATES[0])]
    pairs = helpers["_parse_history_log"](log_output(duplicated))
    assert pairs == [(COMMITS[0], DATES[0]), (COMMITS[1], DATES[1])]
    request = helpers["_history_request"](pairs, PATH)
    assert request == (COMMITS[0] + ":" + PATH + "\n"
                       + COMMITS[1] + ":" + PATH + "\n").encode("utf-8")
    assert helpers["_parse_history_batch"](pairs, batch_output(CONTENTS[:2])) == expected_records(pairs, CONTENTS[:2])
    for injected in ("agentos/other\ninjected.md", "agentos/other\rinjected.md", "other/WS-ONE.md", "agentos/workstreams/../WS-ONE.md"):
        with pytest.raises(unavailable):
            helpers["_history_request"]([PAIRS[0]], injected)


def test_log_deviations_are_refused_and_empty_log_selects_nothing(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    for log in ("short\n",
                COMMITS[0] + "\x002026-11-03T00:00:00Z\x00tail\n",
                "zz" + COMMITS[0][2:] + "\x002026-11-03T00:00:00Z\x00\n",
                COMMITS[0] + "\x00not-a-date\x00\n",
                COMMITS[0] + "\x002026-13-45T00:00:00Z\x00\n",
                COMMITS[0] + "\x002026-11-03T00:00:00Z\x00\n" + "g" * 40 + "\x002026-11-04T00:00:00Z\x00\n"):
        with pytest.raises(unavailable):
            helpers["_parse_history_log"](log)
    assert helpers["_parse_history_log"]("") == []


def test_missing_object_is_refused_without_partial_history(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    stream = COMMITS[0] + ":" + PATH + " missing\n" + batch_output(CONTENTS[1:2])
    with pytest.raises(unavailable):
        helpers["_parse_history_batch"]([PAIRS[0], PAIRS[1]], stream)
    # The same bytes decode when actually requested, so refusal is shape-driven.
    assert helpers["_parse_history_batch"]([PAIRS[1]], batch_output(CONTENTS[1:2])) == expected_records([PAIRS[1]], CONTENTS[1:2])


def test_wrong_type_and_malformed_headers_are_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    other = "%040x" % 0xF00D
    for header in (other + " commit 3\nabc\n", other + " tree 3\nab\n",
                   COMMITS[0] + " blob\n", COMMITS[0] + " blob abc\n",
                   COMMITS[0] + " blob -1\n"):
        with pytest.raises(unavailable):
            helpers["_parse_history_batch"]([PAIRS[0]], header)


def test_truncated_stream_is_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    full = batch_output(CONTENTS[:2])
    for stream in (full[:-2], full[:20]):
        with pytest.raises(unavailable):
            helpers["_parse_history_batch"]([PAIRS[0], PAIRS[1]], stream)


def test_extra_output_is_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    single = batch_output(CONTENTS[:1])
    for stream in (single + single, single + "\n", single + "tail"):
        with pytest.raises(unavailable):
            helpers["_parse_history_batch"]([PAIRS[0]], stream)


def test_oversized_record_is_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    content = b"o" * (helpers["_RECORD_BYTES"] + 1)
    with pytest.raises(unavailable):
        helpers["_parse_history_batch"]([(blob_oid(content), DATES[0])], batch_output([content]))
    edge = b"o" * helpers["_RECORD_BYTES"]
    assert helpers["_parse_history_batch"]([(blob_oid(edge), DATES[0])], batch_output([edge])) == expected_records([(blob_oid(edge), DATES[0])], [edge])


def test_identity_mismatch_is_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    content = CONTENTS[0]
    stream = ("%040x" % 0xF0F0 + " blob " + str(len(content)) + "\n").encode("ascii") + content + b"\n"
    with pytest.raises(unavailable):
        helpers["_parse_history_batch"]([PAIRS[0]], stream.decode("utf-8"))


def test_non_utf8_record_bytes_are_refused(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    payload = b"a\xffb"
    stream = (blob_oid(payload).encode("ascii") + b" blob 3\n" + payload + b"\n").decode("utf-8", "surrogateescape")
    with pytest.raises(unavailable):
        helpers["_parse_history_batch"]([PAIRS[0]], stream)


def test_two_calls_do_not_share_state_or_mutate_inputs(helpers):
    parse_batch = helpers["_parse_history_batch"]
    pairs = [PAIRS[0]]
    snapshot = list(pairs)
    first = parse_batch(pairs, batch_output(CONTENTS[:1]))
    second = parse_batch([PAIRS[1]], batch_output(CONTENTS[1:2]))
    assert pairs == snapshot
    assert first == expected_records([PAIRS[0]], CONTENTS[:1])
    assert second == expected_records([PAIRS[1]], CONTENTS[1:2])
    assert first != second
    assert parse_batch([PAIRS[1]], batch_output(CONTENTS[1:2])) == second


def test_batch_bound_is_the_fixed_total_history_bound(helpers):
    assert helpers["_RECORD_BYTES"] == 262144
    assert helpers["_HISTORY_LOG_BYTES"] == 8192
    assert helpers["_HISTORY_BATCH_BYTES"] == 8 * helpers["_RECORD_BYTES"] + helpers["_HISTORY_LOG_BYTES"]
    assert helpers["_HISTORY_BATCH_BYTES"] <= 8 * 262144 + 8192


def _git_call_nodes(tree):
    calls = {"show": [], "log": [], "cat-file": []}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "git" and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in calls):
            calls[node.args[0].value].append(node)
    return calls


def test_history_uses_one_request_local_batch_without_sequential_show():
    path = _module_path()
    if path is None:
        pytest.fail("supplied module source is unavailable")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = _git_call_nodes(tree)
    assert len(calls["show"]) == 1 and len(calls["log"]) == 1 and len(calls["cat-file"]) == 1
    batch = calls["cat-file"][0]
    assert any(keyword.arg == "input_bytes" for keyword in batch.keywords)
    assert any(keyword.arg == "limit" and isinstance(keyword.value, ast.Name)
               and keyword.value.id == "_HISTORY_BATCH_BYTES" for keyword in batch.keywords)
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in calls["show"] + calls["log"] + [batch]:
        walker = node
        while walker in parents:
            walker = parents[walker]
            assert not isinstance(walker, (ast.For, ast.While, ast.AsyncFor))


def test_conflicting_duplicate_or_more_than_eight_revisions_refuses(helpers):
    unavailable = helpers["ProjectPlanSourceUnavailable"]
    with pytest.raises(unavailable):
        helpers["_parse_history_log"](log_output([PAIRS[0], (COMMITS[0], DATES[1])]))
    nine = PAIRS + [("9" * 40, DATES[0])]
    with pytest.raises(unavailable):
        helpers["_parse_history_log"](log_output(nine))
    with pytest.raises(unavailable):
        helpers["_history_request"](nine, PATH)
    with pytest.raises(unavailable):
        helpers["_parse_history_batch"](nine, batch_output(CONTENTS + [CONTENTS[0]]))


def test_noncanonical_decimal_blob_size_is_refused(helpers):
    content = b"abc"
    # Hashing a fake leading-zero object header cannot qualify a Git blob.
    oid = hashlib.sha1(b"blob 03\0" + content).hexdigest()
    with pytest.raises(helpers["ProjectPlanSourceUnavailable"]):
        helpers["_parse_history_batch"]([PAIRS[0]], oid + " blob 03\nabc\n")
