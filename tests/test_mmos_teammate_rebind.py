"""rebind-thread: a fresh primary conversation on the teammate's OWN provider
instance (ruling 20 — a teammate is its provider instance, not its
conversation)."""
import copy
import json
import os
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools",
                                "mmos_teammate"))
import cutover_installed as co  # noqa: E402
import setup_teammate as st  # noqa: E402

from test_mmos_teammate_cutover import AID, CID, FakeHttp, make_spec  # noqa: E402

OLD, NEW = "mcp:t", "mcp:new-1"


class FakeT3:
    """The t3 CLI as the rebind needs it: `thread show` answers from a
    scriptable thread table, `thread start` mints the next id. Every argv is
    recorded so a test can prove what was NEVER done."""

    def __init__(self, threads=None, new_id=NEW, fail_start=False,
                 start_rc=0, start_status="completed", timeout=False):
        self.threads = threads or {}
        self.new_id, self.fail_start = new_id, fail_start
        self.start_rc, self.start_status = start_rc, start_status
        self.timeout = timeout
        self.calls = []

    def proc(self, rc=0, stdout="", stderr=""):
        return types.SimpleNamespace(returncode=rc, stdout=stdout,
                                     stderr=stderr)

    def __call__(self, spec, args):
        self.calls.append(list(args))
        if args[:2] == ["thread", "show"]:
            tid = args[2]
            if tid not in self.threads:
                return self.proc(rc=1, stderr=f"thread {tid} not found")
            return self.proc(stdout=json.dumps(self.threads[tid]))
        if args[:2] == ["thread", "start"]:
            if self.fail_start:
                return self.proc(rc=1, stderr="start refused")
            if self.timeout:
                raise subprocess.TimeoutExpired(cmd="t3", timeout=900)
            # the CLI's own law: with --json the payload always reaches
            # stdout, even when the run failed (exit 1) or waits for an
            # answer (exit 2) — so the thread id is never lost.
            return self.proc(
                rc=self.start_rc, stderr="" if self.start_rc == 0 else
                f"Thread {self.new_id} failed",
                stdout=json.dumps(
                    {"threadId": self.new_id, "runId": "r-new",
                     "status": self.start_status, "reply": None,
                     "error": None if self.start_rc == 0
                     else "provider down"}) + "\n")
        return self.proc(rc=2, stderr=f"unexpected argv {args}")


def thread_row(instance, model="glm-5.3-flash"):
    return {"thread": {"id": "x", "providerInstanceId": instance,
                       "model": model},
            "messages": [{"role": "user", "runId": "r1",
                          "providerInstanceId": instance, "text": "hi"}]}


@pytest.fixture
def rebound(tmp_path, monkeypatch, capsys):
    """A MOVED teammate (apply ran for real: carrier installed, result file
    written) whose conversation sits on the general provider — the fault
    ruling 20 repairs. Board status `error`, like Secretary's."""
    spec, http = make_spec(tmp_path), FakeHttp(None)
    monkeypatch.setattr(co, "Http", lambda base: http)
    http.agent = {"id": AID, "name": "Assurance", "companyId": CID,
                  "status": "idle", "adapterType": "hermes_local",
                  "adapterConfig": {"command": "/old/hermes",
                                    "env": {}, "cwd": "/old/cwd",
                                    "timeoutSec": 1800},
                  "runtimeConfig": {"heartbeat": {"enabled": False}},
                  "metadata": None}
    assert co.cmd_apply(spec) == 0
    http.agent["status"] = "error"   # the carrier refused every wake
    t3 = FakeT3({OLD: thread_row("capacity_fabric"),   # the fault
                 NEW: thread_row("assurance")})         # the repair
    monkeypatch.setattr(co, "t3_installed", t3)
    capsys.readouterr()      # apply's own prints are drained here
    http.patches.clear()     # and apply's adapter patch: rebind adds none
    return spec, http, t3


def result_doc(spec):
    with open(os.path.join(spec["agent_dir"], "cutover-result.json")) as fh:
        return json.load(fh)


def result_bytes(spec):
    with open(os.path.join(spec["agent_dir"], "cutover-result.json"), "rb") as fh:
        return fh.read()


def live_binding(http):
    return ((http.agent.get("metadata") or {}).get("teammate") or {}).get("t3")


def printed_json(text):
    """The command's JSON answer, minus the writer's `[setup_teammate]` log
    lines that share stdout with it."""
    kept = "".join(line for line in text.splitlines(keepends=True)
                   if not line.startswith("["))
    return json.loads(kept)


def test_rebind_gives_the_teammate_its_own_instance_back(rebound, capsys):
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    out = printed_json(capsys.readouterr().out)
    # the fault is the status, and the status is REPORTED, not a blocker
    assert out["boardStatus"] == "error" and out["dryRun"] is False
    assert any("error" in n for n in out["notes"])
    assert out["oldThreadId"] == OLD
    assert out["oldThread"]["providerInstanceId"] == "capacity_fabric"
    assert out["newThreadId"] == NEW
    assert out["newThread"]["providerInstanceId"] == "assurance"
    assert out["title"] == "Assurance primary " + out["at"][:10]
    # the binding moved through the move's own writer: revision bumped,
    # read-back verified, everything else in the binding preserved
    got = live_binding(http)
    assert got["primaryThreadId"] == NEW
    assert got["providerInstanceId"] == "assurance"
    assert got["bindingRevision"] == 2
    # the record keeps the old id and the before/after sha256 of the file
    doc = result_doc(spec)
    rec = doc["rebinds"][-1]
    assert rec["oldThreadId"] == OLD and rec["newThreadId"] == NEW
    assert rec["newProviderInstanceId"] == "assurance"
    assert out["wrote"][0]["sha256Before"] != out["wrote"][0]["sha256After"]
    assert out["wrote"][0]["sha256After"] == co.sha256_file(
        os.path.join(spec["agent_dir"], "cutover-result.json"))
    # the start named the teammate's instance, the spec's project, a model
    start = [a for a in t3.calls if a[:2] == ["thread", "start"]][0]
    assert start[2] == spec["binding"]["projectId"]
    assert start[start.index("--provider") + 1] == "assurance"
    assert start[start.index("--model") + 1] == "glm-5.3-flash"
    assert out["model"] == "glm-5.3-flash"   # carried from the old thread


def test_the_old_conversation_is_only_ever_read(rebound):
    # ruling 20(b): the old conversation is left exactly as it is — never
    # sent into, archived or renamed; and no adapter PATCH rides a rebind.
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    for argv in t3.calls:
        assert argv[0] == "thread"
        assert argv[1] in ("show", "start"), argv   # no send/archive/rename
        if argv[1] == "start":
            continue
        assert argv[2] in (OLD, NEW)                # reads only these
        if argv[2] == OLD:
            assert "--messages" in argv             # a read, never a write
    # the sole board write is the binding (metadata); the adapter is untouched
    assert http.patches and all(set(p) == {"metadata"} for p in http.patches)
    assert http.agent["adapterType"] == "process"


def test_a_live_run_anywhere_in_the_company_refuses(rebound):
    spec, http, t3 = rebound
    before, binding_before = result_bytes(spec), copy.deepcopy(live_binding(http))
    http.live.append({"agentId": "another-agent"})   # not even this agent's
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert result_bytes(spec) == before
    assert live_binding(http) == binding_before
    assert not [a for a in t3.calls if a[:2] == ["thread", "start"]]


def test_open_work_refuses(rebound):
    spec, http, t3 = rebound
    http.issues.append({"identifier": "MAS-9", "status": "todo"})
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert live_binding(http)["primaryThreadId"] == OLD
    assert "rebinds" not in result_doc(spec)


def test_a_provider_mismatch_on_the_new_thread_writes_nothing(rebound, capsys):
    # the read-back, not the request, decides: a new thread that reports any
    # other instance refuses BEFORE the binding is written, and the stray
    # thread is left for a person.
    spec, http, t3 = rebound
    t3.threads[NEW] = thread_row("capacity_fabric")    # the fault again
    before, binding_before = result_bytes(spec), copy.deepcopy(live_binding(http))
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    said = capsys.readouterr().err
    assert "NOT writing the binding" in said
    assert NEW in said                              # the stray id is named
    assert result_bytes(spec) == before
    assert live_binding(http) == binding_before
    assert live_binding(http)["primaryThreadId"] == OLD


def test_a_model_mismatch_on_the_new_thread_writes_nothing(rebound, capsys):
    spec, http, t3 = rebound
    t3.threads[NEW] = thread_row("assurance", model="wrong-model")
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert "model" in capsys.readouterr().err
    assert live_binding(http)["primaryThreadId"] == OLD


def test_a_status_error_is_not_a_refusal_but_other_statuses_are(rebound):
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0          # status error proceeds
    # a rebind is not a general-purpose unstick: every other state refuses
    http.agent["status"] = "paused"
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)                  # (binding already NEW:
    # a paused board refuses before any thread is touched)
    http.agent["status"] = "running"
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)


def test_the_fence_still_refuses_unmoved_or_heartbeat_agents(tmp_path,
                                                             monkeypatch):
    spec, http = make_spec(tmp_path), FakeHttp(None)
    monkeypatch.setattr(co, "Http", lambda base: http)
    http.agent = {"id": AID, "name": "Assurance", "companyId": CID,
                  "status": "error", "adapterType": "hermes_local",
                  "adapterConfig": {"command": "/old/hermes", "env": {},
                                    "cwd": "/o", "timeoutSec": 60},
                  "runtimeConfig": {"heartbeat": {"enabled": True}},
                  "metadata": None}
    t3 = FakeT3({})
    monkeypatch.setattr(co, "t3_installed", t3)
    with pytest.raises(SystemExit):                 # not our carrier
        co.cmd_rebind_thread(spec)
    assert t3.calls == []
    moved = copy.deepcopy(http.agent)
    moved["adapterType"] = "process"
    carrier, _ = co.carrier_paths(spec)
    moved["adapterConfig"] = {"command": "/usr/bin/python3",
                              "args": ["-I", carrier, "c.json"]}
    moved["runtimeConfig"] = {"heartbeat": {"enabled": False}}
    http.agent = moved
    with pytest.raises(SystemExit):                 # still no move record
        co.cmd_rebind_thread(spec)


def test_an_unclear_record_or_state_refuses(rebound, capsys):
    spec, http, t3 = rebound
    result = os.path.join(spec["agent_dir"], "cutover-result.json")
    # a corrupt record is a refusal, not "no record"
    good = result_bytes(spec)
    with open(result, "w") as fh:
        fh.write("{ partial")
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    capsys.readouterr()
    # a rolled-back move has nothing to rebind
    doc = json.loads(good)
    doc["rolledBackAt"] = "2026-11-12T00:00:00Z"
    with open(result, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    capsys.readouterr()
    # a binding this spec does not know and no record explains (record good
    # again first: this arm is about the BINDING, not the record)
    doc.pop("rolledBackAt")
    with open(result, "w") as fh:
        json.dump(doc, fh)
    st.write_binding(http, AID, dict(spec["binding"],
                                     primaryThreadId="mcp:rotated"))
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert "refresh the spec" in capsys.readouterr().err
    assert t3.calls == []           # nothing was started on any of these


def test_a_chained_rebind_uses_the_recorded_thread(rebound):
    # after a first rebind the spec is stale in exactly one key — the id the
    # first rebind wrote. The record explains the difference, so a second
    # rebind runs against the LIVE binding.
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    t3.new_id = "mcp:new-2"
    t3.threads[NEW]["thread"]["providerInstanceId"] = "capacity_fabric"
    t3.threads["mcp:new-2"] = thread_row("assurance")
    assert co.cmd_rebind_thread(spec) == 0
    assert live_binding(http)["primaryThreadId"] == "mcp:new-2"
    rec = result_doc(spec)["rebinds"]
    assert rec[0]["newThreadId"] == NEW
    assert rec[1]["oldThreadId"] == NEW and rec[1]["newThreadId"] == "mcp:new-2"


def test_a_missing_model_everywhere_refuses(rebound, capsys):
    spec, http, t3 = rebound
    t3.threads[OLD]["thread"].pop("model")
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert "t3.model" in capsys.readouterr().err
    assert live_binding(http)["primaryThreadId"] == OLD


def test_dry_run_prints_the_plan_and_writes_nothing(rebound, capsys):
    spec, http, t3 = rebound
    before, binding_before = result_bytes(spec), copy.deepcopy(live_binding(http))
    assert co.cmd_rebind_thread(spec, dry_run=True) == 0
    out = printed_json(capsys.readouterr().out)
    assert out["dryRun"] is True
    assert out["oldThreadId"] == OLD
    assert out["oldThread"]["providerInstanceId"] == "capacity_fabric"
    assert out["newThreadId"] is None
    assert any("no thread started" in n for n in out["notes"])
    assert result_bytes(spec) == before
    assert live_binding(http) == binding_before
    # nothing was started: the only t3 call is the old conversation's read
    assert [a[:2] for a in t3.calls] == [["thread", "show"]]
    assert t3.calls[0][2] == OLD


def test_rebind_rollback_restores_the_old_id_and_the_fence(rebound, capsys):
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    capsys.readouterr()                      # the rebind's own answer, drained
    assert co.cmd_rebind_rollback(spec) == 0
    out = printed_json(capsys.readouterr().out)
    assert out["restoredThreadId"] == OLD
    assert out["retiredThreadId"] == NEW
    assert "refuses wakes again" in out["note"]
    got = live_binding(http)
    assert got["primaryThreadId"] == OLD and got["bindingRevision"] == 3
    rec = result_doc(spec)["rebinds"][-1]
    assert rec["rolledBackAt"] and rec["newThreadId"] == NEW
    # nothing further to roll back
    with pytest.raises(SystemExit):
        co.cmd_rebind_rollback(spec)
    # and the conversations were still only ever read
    for argv in t3.calls:
        assert argv[1] in ("show", "start")


def test_rebind_rollback_refuses_when_the_binding_moved_on(rebound):
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    # a third party rotated the binding after the rebind
    st.write_binding(http, AID, dict(spec["binding"],
                                     primaryThreadId="mcp:rotated"))
    with pytest.raises(SystemExit):
        co.cmd_rebind_rollback(spec)
    assert live_binding(http)["primaryThreadId"] == "mcp:rotated"


def test_rebind_rollback_open_work_refuses(rebound):
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    http.issues.append({"identifier": "MAS-4", "status": "blocked"})
    with pytest.raises(SystemExit):
        co.cmd_rebind_rollback(spec)
    assert live_binding(http)["primaryThreadId"] == NEW


def test_an_unreadable_board_shape_stops_the_rebind(rebound, monkeypatch):
    # the R2a finding 30 law, on the rebind path: an unrecognised shape is
    # not "no open issues, no live runs" — nothing starts, nothing writes.
    spec, http, t3 = rebound

    class BadLive(FakeHttp):
        def get(self, path):
            if "/live-runs" in path:
                return {"error": {"message": "boom"}}
            return super().get(path)

    http_bad = BadLive(http.agent)
    monkeypatch.setattr(co, "Http", lambda base: http_bad)
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert t3.calls == []


def test_a_failed_thread_start_writes_nothing(rebound):
    spec, http, t3 = rebound
    t3.fail_start = True
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert live_binding(http)["primaryThreadId"] == OLD
    assert "rebinds" not in result_doc(spec)


# --- review repairs (panel b97648f92: 1 HIGH, 2 MED, 3 LOW) ---------------

@pytest.mark.parametrize("key,value", [("providerInstanceId", "capacity_fabric"),
                                       ("projectId", "mcp:other-project")])
def test_a_foreign_instance_or_project_on_a_recorded_rebind_refuses(
        rebound, capsys, key, value):
    # review HIGH: after a rebind the record explains the moved THREAD ID and
    # nothing else. A live binding that keeps the recorded id but changes the
    # instance or the project is a rotate/foreign write — a rebind started on
    # it would run the teammate on a provider that is not its own.
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    capsys.readouterr()
    st.write_binding(http, AID, dict(live_binding(http), **{key: value}))
    started = len([a for a in t3.calls if a[:2] == ["thread", "start"]])
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert "refresh the spec" in capsys.readouterr().err
    assert len([a for a in t3.calls
                if a[:2] == ["thread", "start"]]) == started
    assert live_binding(http)[key] == value       # nothing was written by us


@pytest.mark.parametrize("rc,status", [(1, "failed"), (2, "waiting")])
def test_a_failed_or_waiting_start_names_the_stray_thread(
        rebound, capsys, rc, status):
    # review MED: the thread EXISTS on either exit code (the CLI prints the
    # id with --json even then). Losing the id leaves a stray conversation
    # with no record; the binding must not move on an unproven start.
    spec, http, t3 = rebound
    t3.start_rc, t3.start_status = rc, status
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    captured = capsys.readouterr()
    assert NEW in captured.err and "NOT writing the binding" in captured.err
    assert printed_json(captured.out)["newThreadId"] == NEW
    assert live_binding(http)["primaryThreadId"] == OLD
    assert "rebinds" not in result_doc(spec)


class LiveAfter(FakeHttp):
    """live-runs answers empty for the first `quiet` reads, then one run:
    a wake that starts while the rebind is being prepared."""

    def __init__(self, agent, quiet, run):
        super().__init__(agent)
        self.reads, self.quiet, self.run = 0, quiet, run

    def get(self, path):
        if "/live-runs" in path:
            self.reads += 1
            return [] if self.reads <= self.quiet else [self.run]
        return super().get(path)


def test_a_run_that_starts_after_the_first_look_refuses_before_the_start(
        rebound, monkeypatch):
    # review MED: the fence is read once at the top and must be read again
    # immediately before the irreversible steps.
    spec, http, t3 = rebound
    flaky = LiveAfter(http.agent, quiet=1, run={"agentId": "another-agent"})
    flaky.issues = http.issues
    monkeypatch.setattr(co, "Http", lambda base: flaky)
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert not [a for a in t3.calls if a[:2] == ["thread", "start"]]
    assert live_binding(http)["primaryThreadId"] == OLD


def test_a_run_that_starts_during_the_start_stops_the_write(
        rebound, monkeypatch, capsys):
    spec, http, t3 = rebound
    flaky = LiveAfter(http.agent, quiet=2, run={"agentId": "another-agent"})
    flaky.issues = http.issues
    monkeypatch.setattr(co, "Http", lambda base: flaky)
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    assert NEW in capsys.readouterr().err
    assert live_binding(http)["primaryThreadId"] == OLD
    assert "rebinds" not in result_doc(spec)


def test_instance_of_reads_the_latest_message_like_the_carrier():
    # review LOW: the carrier checks the LATEST message (a conversation
    # moved mid-way is its newest turn); reading the first would report a
    # stale instance.
    thread = {"providerInstanceId": "capacity_fabric"}
    messages = [{"providerInstanceId": "assurance"},
                {"role": "user", "text": "no instance here"},
                {"providerInstanceId": "capacity_fabric"}]
    assert co.instance_of(thread, messages) == "capacity_fabric"


def test_a_start_timeout_says_the_thread_may_exist(rebound, capsys):
    # delta check MED: with --wait the thread is minted before the turn runs,
    # so a 900s timeout almost certainly leaves one behind. The refusal must
    # not tell the operator that nothing exists to reconcile.
    spec, http, t3 = rebound
    t3.timeout = True
    with pytest.raises(SystemExit):
        co.cmd_rebind_thread(spec)
    err = capsys.readouterr().err
    assert "MAY already exist" in err
    assert "nothing was written" not in err
    assert live_binding(http)["primaryThreadId"] == OLD
    assert "rebinds" not in result_doc(spec)


def test_a_failed_rollback_record_write_names_the_reconciliation(
        rebound, monkeypatch, capsys):
    # review LOW: the rebind path logs before dying when its record write
    # fails; the rollback path must say what state it left behind too.
    spec, http, t3 = rebound
    assert co.cmd_rebind_thread(spec) == 0
    capsys.readouterr()

    def boom(path, doc):
        raise OSError("disk full")

    monkeypatch.setattr(co, "write_config_file", boom)
    with pytest.raises(OSError):
        co.cmd_rebind_rollback(spec)
    said = capsys.readouterr().out
    assert "was NOT written" in said and "rolledBackAt" in said
    # the binding write did happen: the file is what needs reconciling
    assert live_binding(http)["primaryThreadId"] == OLD
