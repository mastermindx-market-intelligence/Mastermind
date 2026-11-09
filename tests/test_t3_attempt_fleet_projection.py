"""T3 attempt-fleet projection tests — the DONE_WHEN row-3 invariant matrix.

Every adversarial row from the lane brief is here: two threads under one
(key, namespace) → VIOLATED; same key under a different namespace → two
attempts, not a violation; missing harness → UNKNOWN; stale census → UNKNOWN;
a direct DSH process beside a T3 run → duplicate observed; secret-like
substrings redacted; malformed rows → typed refusal.  Fixtures only; no test
touches a live T3 thread, process or state file."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.t3_attempt_fleet_projection import (
    FLEET_SCHEMA,
    AttemptAdapterRow,
    SavedThreadReads,
    T3AttemptFleetError,
    project_attempt,
    project_fleet,
    read_adapter_attempt_rows,
    validate_attempt,
)
from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore
from control_plane.t3_process_census import CensusProcess, CensusSnapshot

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
NOW_ISO = "2026-11-09T12:00:00+00:00"
KEY_A = "a" * 64
KEY_B = "b" * 64
NS = "mastermind.control_plane.t3_execution_adapter/v1"
NS_OTHER_PRINCIPAL = NS + ":another-oauth-client"
THREAD_1 = "mcp:launch:" + "1" * 64
THREAD_2 = "mcp:launch:" + "2" * 64
NATIVE_RUN_1 = "run:thread:mcp%3Alaunch%3A1:ordinal:1"
WORKSPACE = "/Users/chriswong/.t3/worktrees/Mastermind/t3-aaaaaaaa"
WORKSPACE_2 = "/Users/chriswong/.t3/worktrees/Mastermind/t3-bbbbbbbb"

CLAUDE_HARNESS_ARGV = (
    "claude --output-format stream-json --model glm-5.3 "
    "--allowedTools mcp__t3-code__* "
    f"--add-dir {WORKSPACE} --session-id=19478ad9-7ec0-4642-b7ce-f98d5d605059"
).split()
SH_WRAPPER_ARGV = (
    "/bin/sh -c exec t3-claude claude --output-format stream-json "
    f"--allowedTools mcp__t3-code__* --add-dir {WORKSPACE}"
).split()


# ── fixtures ────────────────────────────────────────────────────────────────


def row(
    run_id="runs/att-1",
    *,
    key=KEY_A,
    namespace=NS,
    thread_id=THREAD_1,
    native_run_id=NATIVE_RUN_1,
    workspace=WORKSPACE,
    model="glm-5.3",
    terminal=None,
) -> AttemptAdapterRow:
    has_receipt = thread_id is not None
    return AttemptAdapterRow(
        run_id=run_id,
        key=key,
        namespace=namespace,
        thread_id=thread_id,
        native_run_id=native_run_id if has_receipt else None,
        workspace_path=workspace,
        model_selection=model,
        has_intent=key is not None,
        has_receipt=has_receipt,
        terminal_native_status=terminal,
    )


def process(pid, ppid, argv):
    return CensusProcess(
        pid=pid, ppid=ppid, argv=tuple(argv), started_epoch_s=1_800_000_000.0
    )


def census(*processes, observed_at_utc=NOW_ISO):
    return CensusSnapshot(
        observed_at_utc=observed_at_utc, processes=tuple(processes)
    )


# ── the invariant matrix ────────────────────────────────────────────────────


def test_two_threads_same_key_and_namespace_is_violated():
    rows = [
        row("runs/att-1", thread_id=THREAD_1),
        row("runs/att-2", thread_id=THREAD_2),
    ]
    document = project_fleet(rows, census=census(), clock=NOW)
    assert len(document["attempts"]) == 2
    for attempt in document["attempts"]:
        assert attempt["thread_count_for_key"] == 2
        assert attempt["invariant"]["exactly_one_thread"] == "VIOLATED"
        assert attempt["duplicate_launcher"]["observed"] is True
        assert "second_t3_thread" in attempt["duplicate_launcher"]["kinds"]


def test_same_key_different_namespace_is_two_attempts_not_a_violation():
    rows = [
        row("runs/att-1", namespace=NS, workspace=WORKSPACE),
        row("runs/att-2", namespace=NS_OTHER_PRINCIPAL, workspace=WORKSPACE_2),
    ]
    document = project_fleet(
        rows,
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(
                200,
                1,
                [
                    "claude",
                    "--output-format",
                    "stream-json",
                    "--allowedTools",
                    "mcp__t3-code__*",
                    f"--add-dir",
                    WORKSPACE_2,
                ],
            ),
        ),
        clock=NOW,
    )
    assert len(document["attempts"]) == 2
    for attempt in document["attempts"]:
        assert attempt["thread_count_for_key"] == 1
        assert attempt["invariant"]["exactly_one_thread"] == "PROVEN"
        assert attempt["duplicate_launcher"]["observed"] is False
        assert attempt["duplicate_launcher"]["kinds"] == []


def test_exactly_one_harness_proven_with_wrapper_child_collapse():
    # The observed live shape: /bin/sh wrapper (ppid 1) + its claude child,
    # both carrying the T3 markers — ONE harness tree, not two.
    view = project_attempt(
        rows=[row()],
        census=census(
            process(11790, 27914, CLAUDE_HARNESS_ARGV),
            process(27914, 1, SH_WRAPPER_ARGV),
        ),
        clock=NOW,
    ).to_dict()
    assert view["harness_count_for_thread"] == 1
    assert view["invariant"]["exactly_one_harness"] == "PROVEN"
    assert view["harness_process"]["pid"] == 27914
    assert view["harness_process"]["provider"] == "claude"
    assert view["harness_process"]["model"] == "glm-5.3"
    assert view["invariant"]["exactly_one_thread"] == "PROVEN"
    validate_attempt(view)


def test_two_harness_trees_is_violated():
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(
                200,
                1,
                ["claude", "--allowedTools", "mcp__t3-code__*", f"--add-dir={WORKSPACE}"],
            ),
        ),
        clock=NOW,
    ).to_dict()
    assert view["harness_count_for_thread"] == 2
    assert view["invariant"]["exactly_one_harness"] == "VIOLATED"


def test_missing_harness_is_unknown_not_violated():
    view = project_attempt(
        rows=[row()], census=census(process(1, 0, ["python3", "unrelated.py"])), clock=NOW
    ).to_dict()
    assert view["harness_count_for_thread"] == 0
    assert view["harness_count_reason"] == "HARNESS_NOT_OBSERVED"
    assert view["invariant"]["exactly_one_harness"] == "UNKNOWN"
    assert view["harness_process"]["pid"] is None
    # Unknown never collapses to healthy OR to a violation:
    assert view["duplicate_launcher"]["observed"] is False  # thread side proven, census fresh
    validate_attempt(view)


def test_stale_census_is_unknown_everywhere_on_the_process_side():
    stale = (NOW - timedelta(hours=1)).isoformat()
    view = project_attempt(
        rows=[row()],
        census=census(process(100, 1, CLAUDE_HARNESS_ARGV), observed_at_utc=stale),
        clock=NOW,
    ).to_dict()
    assert view["freshness"]["census"] == "stale"
    assert view["harness_count_for_thread"] is None
    assert view["harness_count_reason"] == "CENSUS_STALE"
    assert view["invariant"]["exactly_one_harness"] == "UNKNOWN"
    assert view["duplicate_launcher"]["observed"] is None
    assert view["duplicate_launcher"]["unknown_reason"] == "CENSUS_STALE"


def test_absent_census_is_unknown():
    view = project_attempt(rows=[row()], census=None, clock=NOW).to_dict()
    assert view["freshness"]["census"] == "unknown"
    assert view["invariant"]["exactly_one_harness"] == "UNKNOWN"
    assert view["duplicate_launcher"]["observed"] is None


def test_dsh_direct_beside_t3_run_is_duplicate_launcher():
    dsh_direct_argv = (
        "node /Users/chriswong/Library/Application Support/Mastermind/DeepSeek/"
        "releases/dsh-687f282e-company/app/apps/cli/lib/bin.js web "
        f"--patch {WORKSPACE}/company.patch.yml --host 127.0.0.1 --port 4180"
    ).split()
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(11638, 1, dsh_direct_argv),
        ),
        clock=NOW,
    ).to_dict()
    assert view["duplicate_launcher"]["observed"] is True
    assert view["duplicate_launcher"]["kinds"] == ["dsh_direct"]
    assert any(
        ref == "census:pid:11638" for ref in view["duplicate_launcher"]["evidence_refs"]
    )
    # The T3-owned harness itself stays exactly one:
    assert view["invariant"]["exactly_one_harness"] == "PROVEN"


def test_codex_cli_in_attempt_workspace_is_duplicate_launcher():
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(300, 1, ["codex", "exec", f"--cwd={WORKSPACE}", "--model", "gpt-5.2"]),
        ),
        clock=NOW,
    ).to_dict()
    assert view["duplicate_launcher"]["observed"] is True
    assert view["duplicate_launcher"]["kinds"] == ["codex_cli"]


def test_uncorrelated_dsh_direct_is_not_a_duplicate_for_this_attempt():
    # Direct launchers exist on this machine all the time (attended web
    # server); only one correlated with THIS attempt's workspace counts.
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(11640, 1, ["node", "/opt/other/dsh-999/bin.js", "web", "--port", "1"]),
        ),
        clock=NOW,
    ).to_dict()
    assert view["duplicate_launcher"]["observed"] is False
    assert view["duplicate_launcher"]["kinds"] == []


def test_plain_claude_in_workspace_is_other_kind_duplicate():
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(400, 1, ["claude", "--add-dir", WORKSPACE]),
        ),
        clock=NOW,
    ).to_dict()
    assert view["duplicate_launcher"]["observed"] is True
    assert view["duplicate_launcher"]["kinds"] == ["other"]


def test_non_agent_process_in_workspace_is_not_a_duplicate():
    view = project_attempt(
        rows=[row()],
        census=census(
            process(100, 1, CLAUDE_HARNESS_ARGV),
            process(500, 1, ["python3", f"{WORKSPACE}/run_tests.py"]),
        ),
        clock=NOW,
    ).to_dict()
    assert view["duplicate_launcher"]["observed"] is False


def test_attempt_without_adapter_row_is_all_unknown():
    view = project_attempt(
        attempt_id="runs/never-started", rows=None, census=census(), clock=NOW
    ).to_dict()
    assert view["t3_thread"]["thread_id"] is None
    assert view["t3_thread"]["unknown_reason"] == "NO_ADAPTER_ROW"
    assert view["invariant"] == {
        "exactly_one_thread": "UNKNOWN",
        "exactly_one_harness": "UNKNOWN",
    }
    assert view["freshness"]["adapter_state"] == "unknown"
    validate_attempt(view)


def test_intent_without_receipt_is_effect_unknown_zone():
    view = project_attempt(
        rows=[row(thread_id=None, native_run_id=None)], census=census(), clock=NOW
    ).to_dict()
    assert view["t3_thread"]["thread_id"] is None
    assert view["t3_thread"]["unknown_reason"] == "NO_RECEIPT"
    assert view["thread_count_for_key"] is None
    assert view["thread_count_reason"] == "NO_RECEIPT_THREAD"
    assert view["invariant"]["exactly_one_thread"] == "UNKNOWN"
    assert view["duplicate_launcher"]["observed"] is None


def test_no_workspace_in_spec_keeps_harness_unknown():
    view = project_attempt(
        rows=[row(workspace=None)], census=census(process(100, 1, CLAUDE_HARNESS_ARGV)),
        clock=NOW,
    ).to_dict()
    assert view["harness_count_for_thread"] is None
    assert view["harness_count_reason"] == "NO_WORKSPACE_IN_SPEC"
    assert view["invariant"]["exactly_one_harness"] == "UNKNOWN"
    assert view["duplicate_launcher"]["observed"] is None


# ── thread read port ────────────────────────────────────────────────────────


def test_thread_read_port_supplies_state():
    port = SavedThreadReads(
        {
            THREAD_1: {
                "thread_id": THREAD_1,
                "run_id": NATIVE_RUN_1,
                "native_status": "running",
                "read_at_utc": NOW_ISO,
            }
        }
    )
    view = project_attempt(
        rows=[row()], thread_read_port=port, census=census(), clock=NOW
    ).to_dict()
    assert view["t3_thread"]["state"] == "running"
    assert view["freshness"]["thread_read"] == "fresh"


def test_terminal_native_status_falls_back_without_port():
    view = project_attempt(
        rows=[row(terminal="completed")], census=census(), clock=NOW
    ).to_dict()
    assert view["t3_thread"]["state"] == "completed"
    assert view["freshness"]["thread_read"] == "absent"


def test_unreachable_thread_read_port_is_unknown():
    class Unreachable:
        def read(self, thread_id):
            raise ConnectionError("gateway stopped")

    view = project_attempt(
        rows=[row(terminal=None)],
        thread_read_port=Unreachable(),
        census=census(),
        clock=NOW,
    ).to_dict()
    assert view["t3_thread"]["state"] is None
    assert view["freshness"]["thread_read"] == "unknown"


def test_saved_thread_reads_reject_malformed_and_foreign_echo():
    with pytest.raises(T3AttemptFleetError) as exc:
        SavedThreadReads(
            {
                THREAD_1: {
                    "thread_id": THREAD_2,
                    "run_id": None,
                    "native_status": None,
                    "read_at_utc": NOW_ISO,
                }
            }
        )
    assert exc.value.code == "THREAD_READ_INVALID"
    with pytest.raises(T3AttemptFleetError) as exc:
        SavedThreadReads({THREAD_1: {"thread_id": THREAD_1}})
    assert exc.value.code == "THREAD_READ_INVALID"


# ── durable state reading (real schema, read-only) ──────────────────────────


def _state_file(tmp_path, rows):
    """Create the REAL adapter-state schema, then insert raw JSON rows."""
    path = tmp_path / "t3_adapter_state.sqlite3"
    store = SQLiteT3AdapterStateStore(path)  # writes the reviewed schema only
    store.close()
    connection = sqlite3.connect(path)
    for record in rows:
        connection.execute(
            "INSERT INTO t3_adapter_runs (run_id, intent_json, receipt_json,"
            " spec_json, cursor_text, schema_version, updated_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                record["run_id"],
                json.dumps(record.get("intent")),
                json.dumps(record.get("receipt")) if record.get("receipt") else None,
                json.dumps(record.get("spec")) if record.get("spec") else None,
                "",
                "mastermind.t3_adapter_state/v1",
                1,
            ),
        )
    connection.commit()
    connection.close()
    return path


def _intent(key=KEY_A, namespace=NS, run_id="runs/att-1"):
    return {
        "schema": "mastermind.t3_launch_intent/v1",
        "run_id": run_id,
        "client_request_id": key,
        "request_namespace": namespace,
        "adapter_id": "t3-native",
        "envelope": {
            "schema": "mastermind.t3_thread_launch_envelope/v1",
            "request_namespace": namespace,
            "client_request_id": key,
            "run_id": run_id,
            "model_selection": "glm-5.3",
        },
        "created_at": NOW_ISO,
    }


def _receipt(thread_id=THREAD_1, key=KEY_A, namespace=NS):
    return {
        "schema": "mastermind.t3_thread_launch_receipt/v1",
        "thread_id": thread_id,
        "run_id": "run:thread:x:ordinal:1",
        "project_id": "",
        "status": "preparing",
        "link": "",
        "created_at": NOW_ISO,
        "request_namespace": namespace,
        "client_request_id": key,
    }


def _spec(workspace=WORKSPACE):
    return {"workspace_path": workspace}


def test_read_adapter_rows_round_trip(tmp_path):
    path = _state_file(
        tmp_path,
        [
            {
                "run_id": "runs/att-1",
                "intent": _intent(),
                "receipt": _receipt(),
                "spec": _spec(),
            }
        ],
    )
    rows = read_adapter_attempt_rows(path)
    assert len(rows) == 1
    assert rows[0].run_id == "runs/att-1"
    assert rows[0].key == KEY_A
    assert rows[0].namespace == NS
    assert rows[0].thread_id == THREAD_1
    assert rows[0].workspace_path == WORKSPACE
    assert rows[0].model_selection == "glm-5.3"
    # and it projects from the real store shape:
    view = project_attempt(
        rows=rows, all_rows=rows,
        census=census(process(100, 1, CLAUDE_HARNESS_ARGV)), clock=NOW,
    ).to_dict()
    assert view["invariant"] == {
        "exactly_one_thread": "PROVEN",
        "exactly_one_harness": "PROVEN",
    }


def test_read_adapter_rows_missing_file_is_empty(tmp_path):
    assert read_adapter_attempt_rows(tmp_path / "absent.sqlite3") == ()


def test_read_adapter_rows_foreign_schema_refused(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (x TEXT)")
    connection.commit()
    connection.close()
    with pytest.raises(T3AttemptFleetError) as exc:
        read_adapter_attempt_rows(path)
    assert exc.value.code == "ADAPTER_STATE_SCHEMA_UNKNOWN"


def test_malformed_row_is_typed_refusal(tmp_path):
    path = _state_file(tmp_path, [{"run_id": "runs/bad", "intent": None}])
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE t3_adapter_runs SET intent_json='not-json' WHERE run_id='runs/bad'"
    )
    connection.commit()
    connection.close()
    with pytest.raises(T3AttemptFleetError) as exc:
        read_adapter_attempt_rows(path)
    assert exc.value.code == "ADAPTER_ROW_MALFORMED"


def test_receipt_echoing_foreign_key_is_typed_refusal(tmp_path):
    path = _state_file(
        tmp_path,
        [
            {
                "run_id": "runs/att-1",
                "intent": _intent(key=KEY_A),
                "receipt": _receipt(key=KEY_B),
                "spec": None,
            }
        ],
    )
    with pytest.raises(T3AttemptFleetError) as exc:
        read_adapter_attempt_rows(path)
    assert exc.value.code == "ADAPTER_ROW_MALFORMED"


def test_intent_run_id_mismatch_is_typed_refusal(tmp_path):
    path = _state_file(
        tmp_path,
        [
            {
                "run_id": "runs/att-1",
                "intent": _intent(run_id="runs/other"),
                "receipt": None,
                "spec": None,
            }
        ],
    )
    with pytest.raises(T3AttemptFleetError) as exc:
        read_adapter_attempt_rows(path)
    assert exc.value.code == "ADAPTER_ROW_MALFORMED"


# ── fail-closed validation + closed vocabularies ────────────────────────────


def _healthy_view():
    return project_attempt(
        rows=[row()], census=census(process(100, 1, CLAUDE_HARNESS_ARGV)), clock=NOW
    ).to_dict()


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda v: v.update(attempt_id="../evil"), "ATTEMPT_ID_INVALID"),
        (lambda v: v["duplicate_launcher"].update(kinds=["free_shell"]), "DUPLICATE_FIELDS_INVALID"),
        (lambda v: v["duplicate_launcher"].update(observed=True, kinds=[]), "DUPLICATE_FIELDS_INVALID"),
        (lambda v: v["invariant"].update(exactly_one_thread="MOSTLY_FINE"), "INVARIANT_FIELDS_INVALID"),
        (lambda v: v["freshness"].update(census="ancient"), "FRESHNESS_FIELDS_INVALID"),
        (lambda v: v["t3_thread"].update(thread_id=None, unknown_reason=None), "THREAD_FIELDS_INVALID"),
        (lambda v: v["harness_process"].update(pid=-2), "HARNESS_FIELDS_INVALID"),
        (lambda v: v.update(thread_count_for_key="two"), "THREAD_COUNT_INVALID"),
        (lambda v: v.update(extra_field=1), "ATTEMPT_FIELDS_INVALID"),
    ],
)
def test_validate_attempt_fail_closed(mutate, code):
    view = _healthy_view()
    mutate(view)
    with pytest.raises(T3AttemptFleetError) as exc:
        validate_attempt(view)
    assert exc.value.code == code


def test_validate_attempt_accepts_the_healthy_document():
    validate_attempt(_healthy_view())


def test_unknown_never_collapses_to_healthy_strings():
    view = project_attempt(rows=None, attempt_id="runs/x", census=None, clock=NOW).to_dict()
    assert view["invariant"]["exactly_one_thread"] == "UNKNOWN"
    assert view["invariant"]["exactly_one_harness"] == "UNKNOWN"
    assert view["duplicate_launcher"]["observed"] is None


def test_secret_like_never_enters_the_projection(tmp_path):
    # A census process whose argv carries an opaque 40-char token: the census
    # stores it redacted (take_census path), and nothing re-exposes it.
    argv = ["claude", "--allowedTools", "mcp__t3-code__*", f"--add-dir", WORKSPACE,
            "--api-key", "z" * 40]
    snapshot = CensusSnapshot(
        observed_at_utc=NOW_ISO,
        processes=(process(100, 1, ["x" * 40]),),
    )
    view = project_attempt(rows=[row()], census=snapshot, clock=NOW).to_dict()
    dumped = json.dumps(view)
    assert "z" * 40 not in dumped
    assert "x" * 40 not in dumped


def test_fleet_document_shape():
    document = project_fleet([row()], census=census(), clock=NOW)
    assert document["schema"] == FLEET_SCHEMA
    assert document["evaluated_at_utc"].startswith("2026-11-09T12:00:00")
    assert [a["attempt_id"] for a in document["attempts"]] == ["runs/att-1"]
    assert document["notes"] == []


def test_fleet_empty_rows_note():
    document = project_fleet([], census=None, clock=NOW)
    assert document["notes"] == ["ADAPTER_STATE_EMPTY", "CENSUS_ABSENT"]
    assert document["attempts"] == []


def test_fleet_refuses_bad_clock():
    with pytest.raises(T3AttemptFleetError) as exc:
        project_fleet([row()], census=census(), clock=object())
    assert exc.value.code == "CLOCK_INVALID"


def test_fleet_refuses_bad_window():
    with pytest.raises(T3AttemptFleetError) as exc:
        project_fleet([row()], census=census(), clock=NOW, freshness_window_s=0)
    assert exc.value.code == "FRESHNESS_WINDOW_INVALID"


def test_fleet_refuses_census_wrong_schema():
    with pytest.raises(T3AttemptFleetError) as exc:
        project_fleet([row()], census={"schema": "other/v1"}, clock=NOW)
    assert exc.value.code == "CENSUS_INVALID"
