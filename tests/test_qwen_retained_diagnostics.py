"""Offline tests for the retained, credential-safe qwen_exec.sh diagnostics.

Everything here is synthetic: no provider, credential, network or live-store
operation is performed. The tests execute the ACTUAL candidate artifacts -- the
embedded final_response_stream.py heredoc and the real shell classifier /
provenance functions extracted from qwen_exec.sh -- and compare their behavior
with the legacy decisions, rc values and stdout contract.
"""
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import tempfile

import pytest

SCRIPT_PATH = os.environ.get(
    "QWEN_CANDIDATE_SCRIPT",
    str(Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate/qwen_exec.sh"),
)

PROJECTION_SENTINEL = "QWEN_FINAL_RESPONSE_UNCONFIRMED"
ARGS_SENTINEL = "QWEN_FINAL_RESPONSE_ARGUMENTS_INVALID"
PROJECTION_DIAG_RE = re.compile(
    r"^QWEN_PROJECTION_DIAG closed=(?P<closed>QWEN_CLOSED_[A-Z_]+) "
    r"completed=(?P<completed>true|false) thread=(?P<thread>true|false) "
    r"answer=(?P<answer>true|false) failed=(?P<failed>true|false) "
    r"basis=(?P<basis>[a-z_]+)$"
)
KNOWN_CLOSED = {
    "QWEN_CLOSED_COMPLETED",
    "QWEN_CLOSED_IO_ERROR",
    "QWEN_CLOSED_ENCODING_ERROR",
    "QWEN_CLOSED_MALFORMED_EVENT",
    "QWEN_CLOSED_NONOBJECT_EVENT",
    "QWEN_CLOSED_THREAD_INVALID",
    "QWEN_CLOSED_TURN_STATE_INVALID",
    "QWEN_CLOSED_STREAM_ERROR_EVENT",
    "QWEN_CLOSED_ITEM_INVALID",
    "QWEN_CLOSED_ANSWER_INVALID",
    "QWEN_CLOSED_NO_THREAD",
    "QWEN_CLOSED_NOT_COMPLETED",
    "QWEN_CLOSED_NO_FINAL_ANSWER",
}
KNOWN_CHANNELS = {"answer", "stderr", "raw_event", "multiple", "unknown", "none"}
KNOWN_STRUCTURES = {
    "json_error_code",
    "status_and_token_text",
    "numeric_text",
    "reconnect_text",
    "none",
}
KNOWN_RULE_KINDS = {
    "json_code_invalid_api_key": "401",
    "status_token_auth_401": "401",
    "json_code_access_denied": "403",
    "status_token_auth_403": "403",
    "rate_limit_429": "429",
    "json_code_quota": "402",
    "status_token_quota_402": "402",
    "reconnect_quota": "402",
    "none": "none",
    "unknown": "unknown",
}

SHELL_BLOCK_START = "# True when some line of file"
SHELL_BLOCK_END = "release_current() {"


def candidate_text():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def extract_embedded_python_source():
    """Pull the actual embedded final_response_stream.py heredoc body out."""
    text = candidate_text()
    marker = re.search(
        r"<<'QWEN_FINAL_RESPONSE_STREAM_PY'.*?\n(.*?)\nQWEN_FINAL_RESPONSE_STREAM_PY\n",
        text,
        re.S,
    )
    assert marker, "embedded projection helper heredoc not found"
    return marker.group(1)


def extract_shell_block():
    """Extract the real classifier + provenance + failover shell functions."""
    text = candidate_text()
    start = text.index(SHELL_BLOCK_START)
    end = text.index(SHELL_BLOCK_END)
    return text[start:end]


def load_projection_module(tmp_path):
    source = extract_embedded_python_source()
    path = tmp_path / "final_response_stream.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "candidate_final_response_stream", str(path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_projection_main(tmp_path, stdin_bytes, argv):
    """Run the actual embedded helper as a process, exactly like the wrapper."""
    source = extract_embedded_python_source()
    helper = tmp_path / "final_response_stream.py"
    helper.write_text(source, encoding="utf-8")
    thread_file = tmp_path / "thread"
    raw_file = tmp_path / "raw.jsonl"
    proc = subprocess.run(
        [sys.executable, str(helper), str(thread_file), str(raw_file)] + list(argv),
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "replace"),
        "stderr": proc.stderr.decode("utf-8", "replace"),
        "thread_file": thread_file,
        "raw_file": raw_file,
    }


def run_shell(body, env=None):
    """Execute the actual candidate shell classifier block under set -eu."""
    bash_env = dict(os.environ)
    bash_env.pop("QWEN_EXEC_SLOTTED", None)
    if env:
        bash_env.update(env)
    proc = subprocess.run(
        ["bash", "-c", "set -eu\n" + extract_shell_block() + "\n" + textwrap.dedent(body)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=bash_env,
    )
    return {
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "replace"),
        "stderr": proc.stderr.decode("utf-8", "replace"),
    }


def run_classifier(tmp_path, scan_content):
    """classify_limit on one synthetic scan file (legacy behavior probe)."""
    scan_file = tmp_path / "scan.txt"
    scan_file.write_text(scan_content, encoding="utf-8")
    return run_shell(
        """
        classify_limit "$TMP/scan.txt"
        """,
        {"TMP": str(tmp_path)},
    )


def classify_fixture(tmp_path, text="", err="", raw="", join_text_without_newline=False):
    """Build TEXT/ERR/RAW channel files plus the concatenated scan file."""
    text_file = tmp_path / "text.txt"
    err_file = tmp_path / "err.txt"
    raw_file = tmp_path / "raw.jsonl"
    scan_file = tmp_path / "scan.txt"
    if join_text_without_newline and text and not text.endswith("\n"):
        text_file.write_text(text, encoding="utf-8")
        joined = text + err + raw
    else:
        text_file.write_text(text if not text or text.endswith("\n") else text + "\n",
                             encoding="utf-8")
        joined = (text if not text or text.endswith("\n") else text + "\n") + err + raw
    err_file.write_text(err, encoding="utf-8")
    raw_file.write_text(raw, encoding="utf-8")
    scan_file.write_text(joined, encoding="utf-8")
    return {
        "TEXT_FILE": str(text_file),
        "ERR_FILE": str(err_file),
        "RAW_FILE": str(raw_file),
        "SCAN_FILE": str(scan_file),
    }


def provenance_of(tmp_path, channels, kind=None, join_text_without_newline=False):
    """Run the real classify_provenance over synthetic channel files."""
    paths = classify_fixture(
        tmp_path,
        channels.get("answer", ""),
        channels.get("stderr", ""),
        channels.get("raw_event", ""),
        join_text_without_newline=join_text_without_newline,
    )
    set_kind = (
        'KIND="$(classify_limit "$SCAN_FILE")"\n'
        if kind is None
        else 'KIND="%s"\n' % kind
    )
    body = """
    TEXT_FILE=%(TEXT_FILE)r
    ERR_FILE=%(ERR_FILE)r
    RAW_FILE=%(RAW_FILE)r
    SCAN_FILE=%(SCAN_FILE)r
    %(set_kind)s
    classify_provenance "$SCAN_FILE" || true
    printf 'kind=%%s rule=%%s channel=%%s structure=%%s\\n' "$KIND" "$CLASSIFIER_RULE" "$CLASSIFIER_CHANNEL" "$CLASSIFIER_STRUCTURE"
    """ % dict(paths, set_kind=set_kind)
    out = run_shell(body)
    assert out["rc"] == 0, out
    line = out["stdout"].strip()
    parsed = dict(
        part.split("=", 1) for part in line.split(" ") if "=" in part
    )
    return parsed


def diag_lines(stderr_text):
    return [
        line
        for line in stderr_text.splitlines()
        if line.startswith("QWEN_PROJECTION_DIAG ")
    ]


def completed_stream(thread_id="thread-1", answer="answer body", extra=()):
    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
    ]
    events.extend(extra)
    events.append(
        {"type": "item.completed", "item": {"type": "agent_message", "text": answer}}
    )
    events.append({"type": "turn.completed"})
    return "".join(
        (event if isinstance(event, str) else json_dumps(event)) + "\n"
        for event in events
    )


def json_dumps(obj):
    import json

    return json.dumps(obj)


# ---------------------------------------------------------------------------
# Embedded candidate Python: legacy projection contract + bounded diagnostics
# ---------------------------------------------------------------------------


def test_embedded_python_compiles_and_keeps_legacy_signature():
    source = extract_embedded_python_source()
    compile(source, "final_response_stream.py", "exec")
    assert (
        "def stream_final_jsonl(in_f: IO[str], out_f: IO[str], thread_path: str,"
        "\n                       raw_path: str) -> Optional[str]:"
    ) in source
    assert 'raise ValueError("QWEN_FINAL_RESPONSE_UNCONFIRMED")' in source


def test_successful_turn_returns_thread_id_and_publishes_answer(tmp_path):
    module = load_projection_module(tmp_path)
    out = io.StringIO()
    thread_id = module.stream_final_jsonl(
        io.StringIO(completed_stream()), out, str(tmp_path / "thread"),
        str(tmp_path / "raw.jsonl"),
    )
    assert thread_id == "thread-1"
    assert out.getvalue() == "answer body\n"
    assert (tmp_path / "thread").read_text() == "thread-1\n"
    snapshot = dict(module.LAST_PROJECTION_DIAG)
    assert snapshot["closed"] == "QWEN_CLOSED_COMPLETED"
    assert snapshot == {
        "closed": "QWEN_CLOSED_COMPLETED",
        "completed": True,
        "thread": True,
        "answer": True,
        "failed": False,
        "emitted": True,
    }


def test_success_stream_main_rc_stdout_and_single_bounded_diag(tmp_path):
    result = run_projection_main(
        tmp_path, completed_stream(answer="final answer text").encode(), []
    )
    assert result["rc"] == 0
    assert result["stdout"] == "final answer text\n"
    lines = diag_lines(result["stderr"])
    assert len(lines) == 1
    match = PROJECTION_DIAG_RE.match(lines[0])
    assert match and match.group("closed") == "QWEN_CLOSED_COMPLETED"
    assert match.group("completed") == "true"
    assert match.group("thread") == "true"
    assert match.group("answer") == "true"
    assert match.group("failed") == "false"
    # The answer text stays on stdout; the diagnostic never echoes it.
    assert "final answer text" not in result["stderr"]


def test_commentary_message_is_not_a_final_answer(tmp_path):
    module = load_projection_module(tmp_path)
    stream = completed_stream(
        extra=[{"type": "item.completed",
                "item": {"type": "agent_message", "text": "progress note",
                         "phase": "commentary"}}]
    )
    out = io.StringIO()
    assert module.stream_final_jsonl(
        io.StringIO(stream), out, str(tmp_path / "thread"), str(tmp_path / "raw.jsonl")
    ) == "thread-1"
    assert out.getvalue() == "answer body\n"


@pytest.mark.parametrize(
    "stream,closed,completed,thread,answer,failed",
    [
        ('{"type":"thread.started","thread_id":"t"}\nnot json\n',
         "QWEN_CLOSED_MALFORMED_EVENT", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n[1,2,3]\n',
         "QWEN_CLOSED_NONOBJECT_EVENT", False, True, False, True),
        ('{"type":"thread.started"}\n',
         "QWEN_CLOSED_THREAD_INVALID", False, False, False, True),
        ('{"type":"thread.started","thread_id":"a"}\n'
         '{"type":"thread.started","thread_id":"b"}\n',
         "QWEN_CLOSED_THREAD_INVALID", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.started"}\n'
         '{"type":"turn.started"}\n',
         "QWEN_CLOSED_TURN_STATE_INVALID", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.completed"}\n'
         '{"type":"turn.completed"}\n',
         "QWEN_CLOSED_TURN_STATE_INVALID", True, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"error"}\n',
         "QWEN_CLOSED_STREAM_ERROR_EVENT", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.failed"}\n',
         "QWEN_CLOSED_STREAM_ERROR_EVENT", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n'
         '{"type":"item.completed","item":"not-an-object"}\n',
         "QWEN_CLOSED_ITEM_INVALID", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n'
         '{"type":"item.completed","item":{"type":"agent_message","text":7}}\n',
         "QWEN_CLOSED_ANSWER_INVALID", False, True, False, True),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.started"}\n'
         '{"type":"item.completed","item":{"type":"agent_message","text":"x"}}\n',
         "QWEN_CLOSED_NOT_COMPLETED", False, True, True, False),
        ('{"type":"turn.started"}\n{"type":"item.completed",'
         '"item":{"type":"agent_message","text":"x"}}\n{"type":"turn.completed"}\n',
         "QWEN_CLOSED_NO_THREAD", True, False, True, False),
        ('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.started"}\n'
         '{"type":"turn.completed"}\n',
         "QWEN_CLOSED_NO_FINAL_ANSWER", True, True, False, False),
    ],
)
def test_unconfirmed_streams_keep_sentinel_and_closed_reason(
    tmp_path, stream, closed, completed, thread, answer, failed
):
    result = run_projection_main(tmp_path, stream.encode(), [])
    assert result["rc"] == 77
    # Legacy consumer contract: generic sentinel, nothing published on stdout.
    assert result["stdout"] == ""
    assert PROJECTION_SENTINEL in result["stderr"].splitlines()
    lines = diag_lines(result["stderr"])
    assert len(lines) == 1
    match = PROJECTION_DIAG_RE.match(lines[0])
    assert match, lines
    assert match.group("closed") == closed
    assert match.group("completed") == ("true" if completed else "false")
    assert match.group("thread") == ("true" if thread else "false")
    assert match.group("answer") == ("true" if answer else "false")
    assert match.group("failed") == ("true" if failed else "false")
    assert match.group("basis") == "stream_parse"
    assert closed in KNOWN_CLOSED
    # No thread id, answer text or raw event content may reach the diagnostic.
    assert '"thread_id"' not in result["stderr"]
    assert "not-an-object" not in result["stderr"]


def test_answer_content_never_leaks_into_stderr_diag(tmp_path):
    answer = "ANSWER-CONTENT-SENTINEL-7f3d"
    stream = (
        '{"type":"thread.started","thread_id":"TID-SENTINEL-91"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"%s"}}\n'
        '{"type":"error"}\n' % answer
    )
    result = run_projection_main(tmp_path, stream.encode(), [])
    assert result["rc"] == 77
    assert answer not in result["stderr"]
    assert "TID-SENTINEL-91" not in result["stderr"]
    assert PROJECTION_SENTINEL in result["stderr"].splitlines()
    assert PROJECTION_DIAG_RE.match(diag_lines(result["stderr"])[0]).group(
        "closed"
    ) == "QWEN_CLOSED_STREAM_ERROR_EVENT"


def test_empty_stream_reports_not_completed_and_no_thread(tmp_path):
    result = run_projection_main(tmp_path, b"", [])
    assert result["rc"] == 77
    assert result["stdout"] == ""
    match = PROJECTION_DIAG_RE.match(diag_lines(result["stderr"])[0])
    assert match.group("closed") == "QWEN_CLOSED_NO_THREAD"
    assert match.group("completed") == "false"


def test_wrong_argument_count_keeps_legacy_args_sentinel(tmp_path):
    result = run_projection_main(tmp_path, b"", ["only-one-arg"])
    assert result["rc"] == 77
    assert ARGS_SENTINEL in result["stderr"].splitlines()
    assert diag_lines(result["stderr"]) == []
    assert PROJECTION_SENTINEL not in result["stderr"]


def test_diag_line_is_bounded_and_enum_only(tmp_path):
    stream = completed_stream(
        thread_id="thread-with-an-extremely-long-identifier-" + "x" * 200,
        answer="y" * 5000,
    )
    result = run_projection_main(tmp_path, stream.encode(), [])
    assert result["rc"] == 0
    lines = diag_lines(result["stderr"])
    assert len(lines) == 1
    assert len(lines[0]) <= 200
    assert "x" * 200 not in lines[0]
    assert "yyy" not in lines[0]
    for token in lines[0].split(" "):
        if token.startswith("closed="):
            assert token.split("=", 1)[1] in KNOWN_CLOSED


# ---------------------------------------------------------------------------
# Real shell classifier: legacy decisions preserved exactly
# ---------------------------------------------------------------------------


def test_candidate_shell_block_parses(tmp_path):
    block_file = tmp_path / "classifier_block.sh"
    block_file.write_text("set -eu\n" + extract_shell_block(), encoding="utf-8")
    proc = subprocess.run(
        ["bash", "-n", str(block_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stderr.decode()


LEGACY_PATTERN_ORDER = [
    '"(code|error_code)"[[:space:]]*:[[:space:]]*"invalid[_[:space:]-]?api[_[:space:]-]?key',
    "invalid[_[:space:]-]?api[_[:space:]-]?key|unauthorized",
    '"(code|error_code)"[[:space:]]*:[[:space:]]*"access[_[:space:]-]?denied',
    "access[_[:space:]-]?denied",
    "HTTP[[:space:]]*429|[[:space:]]429[[:space:]]|429[[:space:]]|rate limit|too many requests",
    '"(InsufficientQuota|insufficient_quota|QuotaExceeded|Arrearage|AccessDenied\\.Unpurchased)',
    "quota|insufficient|exhausted|Arrearage",
    "reconnect",
]


def test_classify_limit_patterns_and_order_unchanged():
    block = extract_shell_block()
    body = block[block.index("classify_limit() {"):block.index("# ---- Retained")]
    positions = []
    for pattern in LEGACY_PATTERN_ORDER:
        found = body.find(pattern)
        assert found != -1, pattern
        positions.append(found)
    assert positions == sorted(positions), "classifier rule order changed"
    assert 'echo none' in body
    for kind in ("echo 401", "echo 403", "echo 429", "echo 402"):
        assert kind in body


@pytest.mark.parametrize(
    "scan,expected",
    [
        ('{"error":{"code":"InvalidApiKey","message":"x"}}', "401"),
        ('line with (401 Unauthorized) details', "401"),
        ('"status_code":401, unauthorized', "401"),
        ('HTTP/401 invalid_api_key', "401"),
        ('{"code":"AccessDenied"}', "403"),
        ('status=403 access_denied', "403"),
        ('(403 AccessDenied)', "403"),
        ('HTTP 429 too many requests', "429"),
        (' 429 ', "429"),
        ('429 rate limit hit', "429"),
        ('server said: too many requests', "429"),
        ('{"code":"InsufficientQuota"}', "402"),
        ('{"error_code":"QuotaExceeded"}', "402"),
        ('unexpected status 402 quota exhausted', "402"),
        ('HTTP 402 Arrearage', "402"),
        # Legacy Case 3 (reconnect + quota) is preserved byte-for-byte: its
        # `grep -q | grep -q` pipeline is inert in the pinned source, so this
        # fixture classifies as none. Retained behavior must not be "fixed".
        ('reconnect failed: insufficient quota', "none"),
        # Tight locality rules: bare prose never fires.
        ('the agent wrote: unauthorized access was denied yesterday', "none"),
        ('quota and insufficient on a bare line', "none"),
        ('high rate of requests but no trigger phrase', "none"),
        # Right-bounded numbers: 4013/1401/f401a are not 401.
        ('error 4013 occurred', "none"),
        ('code 1401 internal', "none"),
        ('ref f401a denied', "none"),
        ('', "none"),
    ],
)
def test_legacy_classify_decisions_unchanged(tmp_path, scan, expected):
    out = run_classifier(tmp_path, scan)
    assert out["rc"] == 0, out
    assert out["stdout"] == expected + "\n"


def test_auth_evidence_wins_over_earlier_429(tmp_path):
    scan = "server returned 429 too many requests\ncode 401 invalid_api_key\n"
    out = run_classifier(tmp_path, scan)
    assert out["stdout"] == "401\n"


def test_429_wins_over_later_402_json(tmp_path):
    scan = ' 429 too many requests\n{"code":"InsufficientQuota"}\n'
    out = run_classifier(tmp_path, scan)
    assert out["stdout"] == "429\n"


@pytest.mark.parametrize(
    "rc,kind,expected",
    [
        (0, "none", 1),
        (3, "none", 1),
        (1, "401", 0),
        (1, "403", 0),
        (1, "429", 0),
        (1, "402", 0),
        (0, "401", 1),
        (0, "403", 1),
        (0, "429", 0),
        (0, "402", 0),
    ],
)
def test_should_failover_matrix_unchanged(rc, kind, expected):
    out = run_shell(
        """
        if should_failover "$RC" "$KIND"; then echo failover; else echo stay; fi
        """,
        {"RC": str(rc), "KIND": kind},
    )
    assert out["stdout"] == ("failover\n" if expected == 0 else "stay\n")


# ---------------------------------------------------------------------------
# Real shell provenance: winning existing rule, channel, structure
# ---------------------------------------------------------------------------


def test_provenance_none_for_clean_output(tmp_path):
    parsed = provenance_of(tmp_path, {"answer": "just a normal answer\n"})
    assert parsed["kind"] == "none"
    assert parsed["rule"] == "none"
    assert parsed["channel"] == "none"
    assert parsed["structure"] == "none"


@pytest.mark.parametrize(
    "channels,kind,rule,structure",
    [
        ({"stderr": '{"code":"InvalidApiKey"}\n'}, "401",
         "json_code_invalid_api_key", "json_error_code"),
        ({"stderr": "(401 Unauthorized) invalid_api_key\n"}, "401",
         "status_token_auth_401", "status_and_token_text"),
        ({"stderr": '{"code":"AccessDenied"}\n'}, "403",
         "json_code_access_denied", "json_error_code"),
        ({"raw_event": 'status 403 access_denied\n'}, "403",
         "status_token_auth_403", "status_and_token_text"),
        ({"answer": ' 429 \n'}, "429", "rate_limit_429", "numeric_text"),
        ({"stderr": 'HTTP 429 rate limit\n'}, "429", "rate_limit_429",
         "numeric_text"),
        ({"raw_event": '{"code":"QuotaExceeded"}\n'}, "402",
         "json_code_quota", "json_error_code"),
        ({"stderr": 'unexpected status 402 quota exhausted\n'}, "402",
         "status_token_quota_402", "status_and_token_text"),
    ],
)
def test_provenance_reports_winning_rule_channel_and_structure(
    tmp_path, channels, kind, rule, structure
):
    parsed = provenance_of(tmp_path, channels)
    assert parsed["kind"] == kind
    assert parsed["rule"] == rule
    assert parsed["channel"] in KNOWN_CHANNELS
    assert parsed["structure"] == structure
    assert KNOWN_RULE_KINDS[rule] == kind


def test_numeric429_in_answer_differs_from_error_channels(tmp_path):
    answer_hit = provenance_of(tmp_path, {"answer": "the request got 429 back\n"})
    stderr_hit = provenance_of(tmp_path, {"stderr": "the request got 429 back\n"})
    raw_hit = provenance_of(
        tmp_path, {"raw_event": 'the request got 429 back\n'}
    )
    for parsed in (answer_hit, stderr_hit, raw_hit):
        # The classification outcome never changes with the source channel.
        assert parsed["kind"] == "429"
        assert parsed["rule"] == "rate_limit_429"
        assert parsed["structure"] == "numeric_text"
    assert answer_hit["channel"] == "answer"
    assert stderr_hit["channel"] == "stderr"
    assert raw_hit["channel"] == "raw_event"


def test_multiple_channel_matches_reported_conservatively(tmp_path):
    parsed = provenance_of(
        tmp_path,
        {
            "stderr": '{"code":"InvalidApiKey"}\n',
            "raw_event": '{"error_code":"invalid_api_key"}\n',
        },
    )
    assert parsed["kind"] == "401"
    assert parsed["rule"] == "json_code_invalid_api_key"
    assert parsed["channel"] in ("multiple", "unknown")


def test_channel_boundary_match_reports_unknown_channel(tmp_path):
    parsed = provenance_of(
        tmp_path,
        {"answer": "rate", "stderr": " limit exceeded\n"},
        join_text_without_newline=True,
    )
    assert parsed["kind"] == "429"
    assert parsed["rule"] == "rate_limit_429"
    assert parsed["channel"] == "unknown"


def test_legacy_reconnect_rule_is_inert_and_enum_mapping_is_fixed(tmp_path):
    """The pinned classifier's reconnect case is a suppressed pipeline, so the
    same fixture must stay unclassified (no behavioral 'fix'), while the
    provenance enum mapping still describes the rule it would report."""
    out = run_classifier(tmp_path, "reconnect failed: insufficient quota\n")
    assert out["stdout"] == "none\n"
    assert KNOWN_RULE_KINDS["reconnect_quota"] == "402"
    parsed = provenance_of(tmp_path,
                           {"raw_event": "reconnect: quota dry\n"}, kind="429")
    # KIND never equals this rule's kind (it cannot win), so no rule is
    # reported: conservative fallback, never a guess.
    assert parsed["rule"] in ("none", "unknown")
    assert parsed["structure"] == "none"


def test_provenance_drift_falls_back_conservatively(tmp_path):
    parsed = provenance_of(tmp_path, {"stderr": '{"code":"InvalidApiKey"}\n'},
                           kind="429")
    # Any drift between the duplicated rules and the actual classifier outcome
    # must be reported conservatively, never as a guessed rule or channel.
    assert parsed["rule"] in ("none", "unknown")
    assert parsed["channel"] in ("none", "unknown")
    assert parsed["structure"] == "none"


# ---------------------------------------------------------------------------
# Whole-candidate compatibility, hygiene and bounded output
# ---------------------------------------------------------------------------


def run_candidate(args, env=None, timeout=30):
    proc_env = dict(os.environ)
    if env:
        proc_env.update(env)
    # Never resolve adjacent helpers from the real source or installed runtime.
    with tempfile.TemporaryDirectory(prefix="qwen-inert-gates-") as directory:
        wrapper = Path(directory) / "qwen_exec.sh"
        wrapper.write_text(candidate_text())
        return subprocess.run(
            ["bash", str(wrapper)] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=proc_env,
            timeout=timeout,
        )


def test_usage_error_contract_unchanged():
    proc = run_candidate([])
    assert proc.returncode == 2
    assert proc.stdout == b""
    err = proc.stderr.decode()
    assert re.search(r"usage: qwen_exec\.sh <cwd> <model> <prompt-file>", err)


def test_outer_lease_gate_contract_unchanged(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("synthetic prompt\n", encoding="utf-8")
    proc = run_candidate(
        [str(tmp_path), "qwen3.8-flash", str(prompt)],
        {"LANE_LEASED": "1", "POOL_ACCOUNT": ""},
    )
    assert proc.returncode == 78
    assert proc.stdout == b""
    assert "OUTER_LEASE_ACCOUNT_REQUIRED" in proc.stderr.decode()


def test_provider_gate_refusal_contract_unchanged(tmp_path):
    """With slotting pre-set, the missing provider projection helper is the
    next gate: it must still refuse on rc 78 before any key/codex work."""
    prompt = tmp_path / "prompt.md"
    prompt.write_text("synthetic prompt\n", encoding="utf-8")
    proc = run_candidate(
        [str(tmp_path), "qwen3.8-flash", str(prompt)],
        {"QWEN_EXEC_SLOTTED": "1", "LANE_LEASED": "0"},
    )
    assert proc.returncode == 78
    assert proc.stdout == b""
    assert "STUDIO_MCP_PROJECTION_REFUSED provider=codex" in proc.stderr.decode()
    # No private run directory may be created before this gate.
    assert not any(tmp_path.glob("qwen_exec.*"))


def test_candidate_never_handles_credential_values():
    text = candidate_text()
    assert "unset BAILIAN_API_KEY" in text
    for line in text.splitlines():
        assert "BAILIAN_API_KEY=" not in line
    assert 'exec-codex "$NAME"' in text


def test_cleanup_contract_retained_and_runs_before_nothing_else():
    text = candidate_text()
    cleanup_body = text[text.index("cleanup() {"):text.index("terminate_from_signal() {")]
    assert 'python3 "$KEYS" release "$NAME" "$$" >/dev/null 2>&1 || true' in cleanup_body
    assert "unset BAILIAN_API_KEY" in cleanup_body
    assert 'rm -rf "$WORKDIR"' in cleanup_body
    assert "trap cleanup EXIT" in text
    # The diagnostic emitters live in the run body, never inside cleanup.
    assert "CLASSIFIER_PROVENANCE" not in cleanup_body
    assert "PROJECTION_DIAG outcome=" not in cleanup_body


def test_published_stdout_contract_is_projection_only():
    text = candidate_text()
    publish = text[text.index("# Publish once after the owned continuation loop."):]
    assert 'if [ "$FINAL_RC" -eq 0 ]; then' in publish
    assert 'cat "$TEXT_FILE" || exit 77' in publish
    # Only TEXT_FILE (the confirmed answer) is published on success; the
    # diagnostic helpers never write to stdout.
    assert "CLASSIFIER_PROVENANCE" not in publish.split("cat")[0]


def test_run_level_provenance_line_format_and_fixed_tokens():
    text = candidate_text()
    match = re.search(
        r"log \"CLASSIFIER_PROVENANCE (?P<body>[^\"]*)\"", text
    )
    assert match, "run-level provenance line missing"
    tokens = dict(
        piece.split("=", 1)
        for piece in match.group("body").split(" ")
        if "=" in piece
    )
    assert set(tokens) == {
        "kind_reported", "rule", "channel", "structure", "basis",
        "answer_match", "stderr_match", "raw_event_match",
        "http_observed",
    }
    assert tokens["basis"] == "classification_inference"
    assert tokens["http_observed"] == "false"


def test_projection_diag_never_claims_http_status():
    """No diagnostic line may carry an HTTP-status claim: the legacy classifier
    comments may mention HTTP statuses, but the emitted diagnostics may not."""
    forbidden = ("http_status=", "observed_http_status", "http_observed=true",
                 "HTTP 401", "HTTP 403", "HTTP 429", "HTTP 402")
    for blob in (candidate_text(), extract_embedded_python_source()):
        for line in blob.splitlines():
            if "PROJECTION_DIAG" in line or "CLASSIFIER_PROVENANCE" in line:
                for token in forbidden:
                    assert token not in line, (line, token)


def test_run_level_diag_lines_are_bounded_and_keyless():
    text = candidate_text()
    for marker in ("PROJECTION_DIAG outcome=", "CLASSIFIER_PROVENANCE "):
        for line in text.splitlines():
            if marker in line and line.lstrip().startswith("log "):
                assert len(line) <= 440
                assert "PICK_ERR" not in line
                assert "$RAW" not in line and "$TEXT_FILE" not in line


def run_candidate_shell_selfcheck(tmp_path, scan, kind):
    """Run the real classify+provenance pair exactly as the run loop does and
    return the bounded provenance line the wrapper would log."""
    paths = classify_fixture(tmp_path, scan)
    body = """
    TEXT_FILE=%(TEXT_FILE)r
    ERR_FILE=%(ERR_FILE)r
    RAW_FILE=%(RAW_FILE)r
    SCAN_FILE=%(SCAN_FILE)r
    KIND="$(classify_limit "$SCAN_FILE")"
    classify_provenance "$SCAN_FILE" || true
    printf 'qwen_exec: CLASSIFIER_PROVENANCE kind_reported=%%s rule=%%s channel=%%s structure=%%s basis=classification_inference http_observed=false\\n' "$KIND" "$CLASSIFIER_RULE" "$CLASSIFIER_CHANNEL" "$CLASSIFIER_STRUCTURE"
    """ % paths
    out = run_shell(body)
    assert out["rc"] == 0, out
    return out["stdout"].strip()


@pytest.mark.parametrize(
    "scan,kind,channel",
    [
        ('{"code":"InvalidApiKey"}\n', "401", "answer"),
        ("(401 Unauthorized) invalid_api_key\n", "401", "answer"),
        ('{"code":"AccessDenied"}\n', "403", "answer"),
        (" 429 too many requests\n", "429", "answer"),
        ('{"code":"QuotaExceeded"}\n', "402", "answer"),
        ("clean output with no signal\n", "none", "none"),
    ],
)
def test_logged_provenance_line_is_bounded_enum_only(tmp_path, scan, kind, channel):
    line = run_candidate_shell_selfcheck(tmp_path, scan, kind)
    assert len(line) <= 200
    prefix = "qwen_exec: CLASSIFIER_PROVENANCE "
    fields = dict(
        piece.split("=", 1)
        for piece in line[len(prefix):].split(" ")
        if "=" in piece
    )
    assert fields["kind_reported"] == kind
    assert fields["channel"] == channel
    assert fields["basis"] == "classification_inference"
    assert fields["http_observed"] == "false"
    if kind == "none":
        assert fields["rule"] == "none"
        assert fields["structure"] == "none"
    else:
        assert KNOWN_RULE_KINDS.get(fields["rule"], "unknown") == kind
        assert fields["structure"] in KNOWN_STRUCTURES


def test_structured_error_events_are_not_http_provenance(tmp_path):
    parsed = provenance_of(tmp_path, {"raw_event": '{"code":"InvalidApiKey"}\n'})
    assert parsed["structure"] == "json_error_code"
    assert parsed["channel"] == "raw_event"
    assert parsed["kind"] == "401"


SECRET_SENTINEL = "SK-SECRET-SENTINEL-DO-NOT-PRINT-3f91ac"


def test_secret_sentinel_never_reaches_any_output(tmp_path):
    env = {"BAILIAN_API_KEY": SECRET_SENTINEL, "TMP": str(tmp_path)}
    scan = (
        '{"code":"InvalidApiKey"}\n(401 Unauthorized)\n{"code":"InsufficientQuota"}\n'
        + SECRET_SENTINEL + "\n"
    )
    paths = classify_fixture(tmp_path, scan)
    body = """
    TEXT_FILE=%(TEXT_FILE)r
    ERR_FILE=%(ERR_FILE)r
    RAW_FILE=%(RAW_FILE)r
    SCAN_FILE=%(SCAN_FILE)r
    KIND="$(classify_limit "$SCAN_FILE")"
    classify_provenance "$SCAN_FILE" || true
    printf '%%s %%s %%s\\n' "$KIND" "$CLASSIFIER_RULE" "$CLASSIFIER_CHANNEL"
    """ % paths
    out = run_shell(body, env=env)
    assert out["rc"] == 0
    assert SECRET_SENTINEL not in out["stdout"]
    assert SECRET_SENTINEL not in out["stderr"]

    # The projection helper likewise never echoes inherited credentials.
    result = run_projection_main(
        tmp_path, completed_stream(answer="answer body").encode(), []
    )
    assert SECRET_SENTINEL not in result["stdout"]
    assert SECRET_SENTINEL not in result["stderr"]


def test_diag_emission_is_best_effort_and_never_breaks_projection(tmp_path):
    """A diagnostic failure must not change the projection outcome: even with
    stderr fully closed the legacy stdout/rc contract holds."""
    source = extract_embedded_python_source()
    helper = tmp_path / "final_response_stream.py"
    helper.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        "exec 2>&-; python3 %s %s %s"
        % (helper, tmp_path / "thread", tmp_path / "raw.jsonl"),
        shell=True,
        input=completed_stream().encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"answer body\n"


@pytest.mark.parametrize("failure", ["raw_open", "answer_write"])
def test_projection_io_error_is_closed_and_keeps_original_exception(tmp_path, capsys, failure):
    module = load_projection_module(tmp_path)
    class BrokenOutput(io.StringIO):
        def write(self, value):
            raise OSError("PRIVATE-IO-SENTINEL /private/example")
    raw = tmp_path / "raw"
    if failure == "raw_open":
        raw.mkdir()
    output = BrokenOutput() if failure == "answer_write" else io.StringIO()
    with pytest.raises(OSError):
        module.stream_final_jsonl(io.StringIO(completed_stream()), output,
                                  str(tmp_path / "thread"), str(raw))
    diagnostic = capsys.readouterr().err
    assert "closed=QWEN_CLOSED_IO_ERROR" in diagnostic
    assert "PRIVATE-IO-SENTINEL" not in diagnostic
    assert "/private/example" not in diagnostic
    assert output.getvalue() == ""


def test_diagnostic_shell_failure_is_best_effort_and_path_errors_stay_private(tmp_path):
    source = candidate_text()
    line = next(line for line in source.splitlines()
                if line.lstrip().startswith('log "CLASSIFIER_PROVENANCE '))
    # A failed diagnostic sink must not abort a set-e caller or alter its rc.
    body = """
    log() { return 9; }
    KIND=none
    CLASSIFIER_RULE=none
    CLASSIFIER_CHANNEL=none
    CLASSIFIER_STRUCTURE=none
    %s
    printf preserved
    """ % line
    result = run_shell(body)
    assert result["rc"] == 0 and result["stdout"] == "preserved"
    invocation = next(line for line in source.splitlines()
                      if line.lstrip().startswith('classify_provenance "$SCAN_FILE"'))
    result = run_shell('KIND=429; SCAN_FILE="$PRIVATE_PATH"; ' + invocation,
                       {"PRIVATE_PATH": str(tmp_path / "SECRET-PRIVATE-PATH")})
    assert result["rc"] == 0
    assert result["stdout"] == result["stderr"] == ""


@pytest.mark.parametrize("case,expected_rc,provider_rc,projection_rc,cooldowns", [
    ("success", 0, "zero", "zero", 0),
    ("truncated", 77, "zero", "nonzero", 0),
    ("provider_failed", 7, "nonzero", "zero", 0),
    ("error_event", 1, "nonzero", "nonzero", 1),
    ("answer_429", 0, "zero", "zero", 1),
])
def test_inert_wrapper_pipeline_cleanup_and_retained_failure_channel(
        tmp_path, case, expected_rc, provider_rc, projection_rc, cooldowns):
    import json
    ext = tmp_path / "ext"; ext.mkdir()
    wrapper = ext / "qwen_exec.sh"; wrapper.write_text(candidate_text())
    projection = ext / "studio_mcp_projection.sh"
    projection.write_text("#!/bin/sh\nexit 0\n"); projection.chmod(0o700)
    (ext / "pool_ledger.py").write_text("pass\n")
    (ext / "bailian_keys.py").write_text('''import json,os,sys
from pathlib import Path
command=sys.argv[1]
if command=='pick': print('FixtureAccount')
elif command=='model': print(sys.argv[2])
elif command=='cooldown':
 p=Path(os.environ['COOLDOWNS']);p.write_text(p.read_text()+'x' if p.exists() else 'x')
elif command=='exec-codex':
 sys.stdin.read()
 def emit(row): print(json.dumps(row))
 emit({'type':'thread.started','thread_id':'fixture-thread'})
 emit({'type':'turn.started'})
 case=os.environ['FIXTURE_CASE']
 if case=='error_event':
  emit({'type':'error','error':{'message':'rate limit PRIVATE-SENTINEL'}})
 else:
  text='STATUS: COMPLETE\\n'+('429 records' if case=='answer_429' else 'ANSWER')
  emit({'type':'item.completed','item':{'type':'agent_message','text':text}})
 if case!='truncated': emit({'type':'turn.completed'})
 sys.exit(7 if case=='provider_failed' else 1 if case=='error_event' else 0)
''')
    config = tmp_path / "lanes/codex_bailian/config.toml"
    config.parent.mkdir(parents=True); config.write_text('model="fixture"\n')
    private = tmp_path / "private"; private.mkdir()
    prompt = tmp_path / "prompt"; prompt.write_text("PRIVATE-PROMPT-SENTINEL")
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
           "HOME": str(tmp_path), "TMPDIR": str(private),
           "QWEN_EXEC_SLOTTED": "1", "LANE_LEASED": "1",
           "POOL_ACCOUNT": "FixtureAccount", "POOL_LEASE_ID": "",
           "QWEN_EXEC_KEY_WAIT": "0", "QWEN_EXEC_MAX_CONTINUES": "0",
           "FIXTURE_CASE": case, "COOLDOWNS": str(tmp_path / "cooldowns")}
    result = subprocess.run(["/bin/bash", str(wrapper), str(tmp_path), "fixture", str(prompt)],
                            env=env, capture_output=True, timeout=20)
    assert result.returncode == expected_rc, result.stderr
    expected = b"STATUS: COMPLETE\n" + (b"429 records\n" if case == "answer_429" else b"ANSWER\n")
    assert result.stdout == (expected if expected_rc == 0 else b"")
    stderr = result.stderr.decode()
    assert "provider_rc=" + provider_rc in stderr
    assert "projection_rc=" + projection_rc in stderr
    assert "basis=classification_inference http_observed=false" in stderr
    assert "PRIVATE-SENTINEL" not in stderr and "PRIVATE-PROMPT-SENTINEL" not in stderr
    assert "PROVIDER_TERMINAL" not in stderr
    assert not list(private.iterdir()), "existing EXIT cleanup must remove private home"
    cooldown_file = tmp_path / "cooldowns"
    assert (len(cooldown_file.read_text()) if cooldown_file.exists() else 0) == cooldowns
    # The existing collector drops successful stderr and retains bounded failure stderr.
    consumer_result = result.stdout if expected_rc == 0 else result.stderr
    if expected_rc == 0:
        assert b"DIAG" not in consumer_result and b"CLASSIFIER_PROVENANCE" not in consumer_result
    else:
        assert b"CLASSIFIER_PROVENANCE" in consumer_result


@pytest.mark.parametrize("failure", ["write", "flush"])
def test_encoding_failure_never_reports_completed_and_propagates(tmp_path, capsys, failure):
    module = load_projection_module(tmp_path)
    class BrokenOutput(io.StringIO):
        def write(self, text):
            if failure == "write":
                raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "synthetic")
            return super().write(text)
        def flush(self):
            raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "synthetic")
    with pytest.raises(UnicodeEncodeError):
        module.stream_final_jsonl(io.StringIO(completed_stream()), BrokenOutput(),
                                  str(tmp_path / "thread"), str(tmp_path / "raw"))
    line = capsys.readouterr().err.strip()
    assert "closed=QWEN_CLOSED_ENCODING_ERROR" in line
    assert "failed=true" in line
    assert "closed=QWEN_CLOSED_COMPLETED" not in line
    assert PROJECTION_DIAG_RE.fullmatch(line)


def test_real_unpaired_surrogate_preserves_unconfirmed_rc(tmp_path):
    import json
    rows = [{"type": "thread.started", "thread_id": "fixture"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "\ud800"}},
            {"type": "turn.completed"}]
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    result = run_projection_main(tmp_path, raw, [])
    assert result["rc"] == 77
    assert result["stdout"] == ""
    assert "closed=QWEN_CLOSED_ENCODING_ERROR" in result["stderr"]
    assert "failed=true" in result["stderr"]
    assert PROJECTION_SENTINEL in result["stderr"]


@pytest.mark.parametrize("answer,stderr,raw_event", [
    (a, e, r) for a in (False, True) for e in (False, True) for r in (False, True)])
def test_all_source_match_combinations_remain_distinguishable(tmp_path, answer, stderr, raw_event):
    import json
    text = "STATUS: COMPLETE\n429 records\n" if answer else ""
    error = "HTTP 429 too many requests\n" if stderr else ""
    raw = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "429 records"}}) + "\n" if raw_event else ""
    paths = classify_fixture(tmp_path, text, error, raw)
    body = """
    TEXT_FILE=%(TEXT_FILE)r
    ERR_FILE=%(ERR_FILE)r
    RAW_FILE=%(RAW_FILE)r
    SCAN_FILE=%(SCAN_FILE)r
    KIND="$(classify_limit "$SCAN_FILE")"
    classify_provenance "$SCAN_FILE" >/dev/null 2>&1 || true
    printf '%%s %%s %%s' "$CLASSIFIER_ANSWER_MATCH" "$CLASSIFIER_STDERR_MATCH" "$CLASSIFIER_RAW_EVENT_MATCH"
    """ % paths
    result = run_shell(body)
    expected = " ".join("true" if flag else "false" for flag in (answer, stderr, raw_event))
    assert result["rc"] == 0 and result["stdout"] == expected
    assert result["stderr"] == ""


def test_channel_flags_reset_and_are_fixed_booleans(tmp_path):
    paths = classify_fixture(tmp_path, "429 records\n", "", "429 mirror\n")
    body = """
    TEXT_FILE=%(TEXT_FILE)r
    ERR_FILE=%(ERR_FILE)r
    RAW_FILE=%(RAW_FILE)r
    SCAN_FILE=%(SCAN_FILE)r
    KIND=429
    classify_provenance "$SCAN_FILE" >/dev/null 2>&1 || true
    KIND=none
    classify_provenance /dev/null >/dev/null 2>&1 || true
    printf '%%s %%s %%s' "$CLASSIFIER_ANSWER_MATCH" "$CLASSIFIER_STDERR_MATCH" "$CLASSIFIER_RAW_EVENT_MATCH"
    """ % paths
    result = run_shell(body)
    assert result["rc"] == 0 and result["stdout"] == "false false false"


def test_actual_wrapper_record_contains_bounded_match_booleans():
    source = candidate_text()
    line = next(line for line in source.splitlines()
                if line.lstrip().startswith('log "CLASSIFIER_PROVENANCE '))
    result = run_shell('''log() { printf '%s\n' "$1"; }
KIND=429
CLASSIFIER_RULE=rate_limit_429
CLASSIFIER_CHANNEL=multiple
CLASSIFIER_STRUCTURE=numeric_text
CLASSIFIER_ANSWER_MATCH=true
CLASSIFIER_STDERR_MATCH=false
CLASSIFIER_RAW_EVENT_MATCH=true
'''+line)
    assert result["rc"] == 0
    output = result["stdout"]
    assert "answer_match=true stderr_match=false raw_event_match=true" in output
    assert "basis=classification_inference http_observed=false" in output
    assert len(output.encode()) <= 384
