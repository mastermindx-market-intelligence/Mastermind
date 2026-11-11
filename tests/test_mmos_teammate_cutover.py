"""Moving one installed Paperclip agent onto its Team conversation."""
import copy
import json
import os
import stat
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools",
                                "mmos_teammate"))
import cutover_installed as co  # noqa: E402
import setup_teammate as st  # noqa: E402

AID, CID = "agent-1", "company-1"


def make_spec(tmp_path):
    return {
        "paperclip_base": "http://127.0.0.1:1", "company_id": CID,
        "agent_id": AID, "agent_name": "Assurance",
        "agent_dir": str(tmp_path / "home"),
        "carrier_install_dir": str(tmp_path / "carrier"),
        "python_bin": "/usr/bin/python3",
        "issue_url_template": "http://127.0.0.1:3100/MAS/issues/{identifier}",
        "t3": {"t3_bin": "/x/t3", "home": "/x/home", "port": 3780, "cwd": "/x/cwd"},
        "binding": {"environmentId": "e", "projectId": "p",
                    "providerInstanceId": "assurance", "primaryThreadId": "mcp:t"},
        "teammates": {"Assurance": AID},
    }


def old_agent():
    return {"id": AID, "name": "Assurance", "companyId": CID, "status": "idle",
            "adapterType": "hermes_local",
            "adapterConfig": {"command": "/old/hermes", "env": {"OLD_HOME": "/old"},
                              "cwd": "/old/cwd", "timeoutSec": 1800},
            "runtimeConfig": {"heartbeat": {"enabled": False}}, "metadata": None}


class FakeHttp:
    """Paperclip agent update as this build does it: env and cwd carry over
    when the adapter type changes unless the patch names them."""

    def __init__(self, agent, issues=(), live=()):
        self.agent, self.issues, self.live = agent, list(issues), list(live)
        self.patches = []

    def get(self, path):
        if path.startswith("/api/agents/"):
            return copy.deepcopy(self.agent)
        if "/live-runs" in path:
            return list(self.live)
        if "/issues?" in path:
            state = path.split("status=")[1].split("&")[0]
            return [i for i in self.issues if i["status"] == state]
        raise AssertionError(path)

    def patch(self, path, body):
        self.patches.append(copy.deepcopy(body))
        body = dict(body)
        replace = body.pop("replaceAdapterConfig", False)
        if "adapterConfig" in body:
            new = dict(body["adapterConfig"])
            if not replace:
                new = {**self.agent["adapterConfig"], **new}
            for key in ("env", "cwd"):
                if key not in new and key in self.agent["adapterConfig"]:
                    new[key] = self.agent["adapterConfig"][key]
            body["adapterConfig"] = new
        self.agent.update(body)
        return {}


@pytest.fixture
def wired(tmp_path, monkeypatch):
    spec, http = make_spec(tmp_path), FakeHttp(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http)
    return spec, http


def test_paperclip_base_must_be_plain_loopback_http():
    # R2a finding 29: Http pins the base by the urlsplit law, not string
    # splits. The board actor header rides every call this client makes, so
    # the base must be scheme http, a loopback host, no userinfo, a port,
    # and no path/query/fragment.
    for bad in ("http://user:pass@127.0.0.1:3100",   # userinfo: another origin
                "http://127.0.0.1.evil.example:3100",  # loopback-looking name
                "https://127.0.0.1:3100",             # scheme was unchecked
                "http://127.0.0.1",                   # no port
                "http://127.0.0.1:3100/proxy",        # a path rides into calls
                "http://127.0.0.1:3100?x=1",          # query
                "http://127.0.0.1:3100:80"):          # malformed port
        with pytest.raises(SystemExit):
            st.Http(bad)
    for ok in ("http://127.0.0.1:3100", "http://localhost:3100",
               "http://[::1]:3100", "http://127.0.0.1:3100/"):
        assert st.Http(ok).base.rstrip("/") == ok.rstrip("/")


def test_second_apply_reuses_a_preimage_when_the_agent_is_unchanged(
        wired, tmp_path, monkeypatch):
    # R2a finding 31: a first apply can stop at the SECOND blockers check
    # after the preimage was already saved (a wake started meanwhile); the
    # move never happened. The second apply reuses the saved file when the
    # agent still carries exactly the saved values, refuses when any value
    # changed, and never deletes or rewrites the file.
    spec, http = wired
    real = co.read_state
    calls = {"n": 0}

    def flaky(h, s):
        calls["n"] += 1
        agent, issues, live = real(h, s)
        if calls["n"] == 2:  # a wake started while preparing
            agent = dict(agent, status="running")
        return agent, issues, live

    monkeypatch.setattr(co, "read_state", flaky)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)  # first apply: stopped at the second check
    preimage = os.path.join(spec["agent_dir"], "cutover-preimage.json")
    assert os.path.exists(preimage)
    assert http.patches == []  # the agent was never patched
    before = open(preimage, "rb").read()

    # second apply, agent unchanged: reuses the saved bytes, finishes the move
    monkeypatch.setattr(co, "read_state", real)
    co.cmd_apply(spec)
    assert open(preimage, "rb").read() == before  # the file is untouched
    assert http.agent["adapterType"] == "process"  # the move happened

    # with the agent CHANGED since the save, the leftover file refuses
    spec2 = make_spec(tmp_path)
    http2 = FakeHttp(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http2)
    calls2 = {"n": 0}

    def flaky2(h, s):
        calls2["n"] += 1
        agent, issues, live = real(h, s)
        if calls2["n"] == 2:
            agent = dict(agent, status="running")
        return agent, issues, live

    monkeypatch.setattr(co, "read_state", flaky2)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec2)
    preimage2 = os.path.join(spec2["agent_dir"], "cutover-preimage.json")
    assert os.path.exists(preimage2)
    bytes2 = open(preimage2, "rb").read()
    http2.agent["adapterConfig"]["env"]["OLD_HOME"] = "/new/home"
    monkeypatch.setattr(co, "read_state", real)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec2)  # refuses: the saved file no longer describes it
    assert open(preimage2, "rb").read() == bytes2
    assert http2.patches == []


def test_unrecognised_board_shape_stops_every_write(tmp_path, monkeypatch):
    # R2a finding 30: rows_of treated any unrecognised dict as an EMPTY
    # result, so {"error": ...} read as "no open issues, no live runs" and
    # apply passed its blockers on a misread. An unknown shape must die for
    # apply, rollback and refresh-carrier, before anything is written.
    bad_shapes = ({"data": [{"identifier": "MAS-1"}]},   # a page we can't read
                  {"error": {"message": "internal error"}},
                  {})                                     # an empty object
    for bad in bad_shapes:
        class BadIssues(FakeHttp):
            def get(self, path):
                if "/issues?" in path:
                    return copy.deepcopy(bad)
                return super().get(path)
        spec = make_spec(tmp_path)
        http = BadIssues(old_agent())
        monkeypatch.setattr(co, "Http", lambda base: http)
        with pytest.raises(SystemExit):
            co.cmd_apply(spec)
        assert http.patches == []  # the agent is untouched
        assert not os.path.exists(os.path.join(spec["agent_dir"],
                                               "cutover-preimage.json"))

    class BadLive(FakeHttp):
        def get(self, path):
            if "/live-runs" in path:
                return {"error": {"message": "boom"}}
            return super().get(path)

    # a live-runs misread stops apply the same way
    spec = make_spec(tmp_path)
    http = BadLive(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)
    assert http.patches == []

    # rollback: a saved setup exists, a misread must not hand it back
    agent_dir = os.path.join(str(tmp_path), "rb-home")
    os.makedirs(agent_dir)
    saved = {k: old_agent().get(k) for k in co.PREIMAGE_KEYS}
    with open(os.path.join(agent_dir, "cutover-preimage.json"), "w") as fh:
        json.dump(saved, fh)
    spec = make_spec(tmp_path)
    spec["agent_dir"] = agent_dir
    http = BadLive(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http)
    with pytest.raises(SystemExit):
        co.cmd_rollback(spec)
    assert http.patches == []
    assert os.path.exists(os.path.join(agent_dir, "cutover-preimage.json"))

    # refresh-carrier: the agent is already moved; a misread changes nothing
    spec = make_spec(tmp_path)
    carrier_path, _ = co.carrier_paths(spec)
    moved = old_agent()
    moved["adapterType"] = "process"
    moved["adapterConfig"] = {"command": "/usr/bin/python3",
                              "args": ["-I", carrier_path, "carrier.json"]}
    http = BadLive(moved)
    monkeypatch.setattr(co, "Http", lambda base: http)
    with pytest.raises(SystemExit):
        co.cmd_refresh_carrier(spec)
    assert http.patches == []
    assert not os.path.exists(carrier_path)  # not even installed


def test_blockers_name_every_unsafe_state(tmp_path):
    spec = make_spec(tmp_path)
    assert co.blockers(spec, old_agent(), [], []) == []
    busy = dict(old_agent(), status="running", name="Other",
                runtimeConfig={"heartbeat": {"enabled": True}})
    found = co.blockers(spec, busy, [{"identifier": "MAS-1"}],
                        [{"agentId": AID}, {"agentId": "someone-else"}])
    text = " | ".join(found)
    for needle in ("name is", "not idle", "heartbeat", "MAS-1", "1 live run"):
        assert needle in text


def test_carrier_config_passes_the_question_wait_keys_and_template(tmp_path):
    # Defaults fit the 1500s process limit; the thread link is optional and
    # only written when the spec carries it.
    cfg = co.carrier_config(make_spec(tmp_path))
    assert cfg["question_wait_sec"] == 900
    assert cfg["run_budget_sec"] == 1320
    assert cfg["question_poll_interval_sec"] == 10
    assert "thread_url_template" not in cfg
    spec = make_spec(tmp_path)
    spec["question_wait_sec"] = 600
    spec["run_budget_sec"] = 1400
    spec["question_poll_interval_sec"] = 7
    spec["thread_url_template"] = "http://127.0.0.1:3774/thread/{thread}"
    cfg = co.carrier_config(spec)
    assert cfg["question_wait_sec"] == 600
    assert cfg["run_budget_sec"] == 1400
    assert cfg["question_poll_interval_sec"] == 7
    assert cfg["thread_url_template"] == "http://127.0.0.1:3774/thread/{thread}"


def test_apply_moves_the_agent_and_saves_the_old_setup(wired, tmp_path, capsys):
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    agent = http.agent
    cfg = agent["adapterConfig"]
    assert agent["adapterType"] == "process"
    assert cfg["env"] == {} and "OLD_HOME" not in json.dumps(cfg)
    assert cfg["command"] == "/usr/bin/python3" and cfg["args"][0] == "-I"
    carrier, config = cfg["args"][1], cfg["args"][2]
    assert os.path.dirname(carrier) == str(tmp_path / "carrier")
    assert co.sha256_file(carrier) == co.sha256_file(
        os.path.join(os.path.dirname(co.__file__), "wake_carrier.py"))
    saved_cfg = json.load(open(config))
    assert saved_cfg["t3_port"] == 3780 and saved_cfg["teammates"] == {"Assurance": AID}
    assert saved_cfg["issue_url_template"].endswith("{identifier}")
    t3 = agent["metadata"]["teammate"]["t3"]
    assert t3["primaryThreadId"] == "mcp:t" and t3["bindingRevision"] == 1
    preimage = tmp_path / "home" / "cutover-preimage.json"
    assert stat.S_IMODE(os.stat(preimage).st_mode) == 0o600
    assert json.load(open(preimage))["adapterConfig"]["env"] == {"OLD_HOME": "/old"}
    # the old environment is saved for rollback but never printed
    assert "OLD_HOME" not in capsys.readouterr().out


def test_apply_refuses_when_work_is_in_flight(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    http = FakeHttp(old_agent(), issues=[{"identifier": "MAS-9", "status": "todo"}])
    monkeypatch.setattr(co, "Http", lambda base: http)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)
    assert http.patches == []
    assert not (tmp_path / "home" / "cutover-preimage.json").exists()


def test_second_apply_keeps_the_first_saved_setup(wired, tmp_path):
    spec, http = wired
    co.cmd_apply(spec)
    first = (tmp_path / "home" / "cutover-preimage.json").read_text()
    assert co.cmd_apply(spec) == 0  # already moved: no new preimage
    assert (tmp_path / "home" / "cutover-preimage.json").read_text() == first
    # R13: an unchanged binding is NOT rewritten — no revision churn for a
    # no-op apply (a changed binding refuses instead of reverting).
    assert http.agent["metadata"]["teammate"]["t3"]["bindingRevision"] == 1


def test_rollback_restores_the_saved_setup(wired, tmp_path):
    spec, http = wired
    before = old_agent()
    co.cmd_apply(spec)
    assert co.cmd_rollback(spec) == 0
    # the run command comes back whole; metadata is NOT restored as an
    # object (R2a finding 10) — only the teammate key the move added is
    # removed, and the move wrote nothing else, so it ends empty
    for key in ("adapterType", "adapterConfig", "runtimeConfig"):
        assert http.agent[key] == before[key]
    assert http.agent["metadata"] == {}
    assert not (tmp_path / "home" / "cutover-preimage.json").exists()
    assert [p for p in os.listdir(tmp_path / "home") if ".restored-" in p]


def test_rollback_refuses_open_work_and_removes_only_the_teammate_key(
        wired, tmp_path):
    # R2a finding 10: rollback refuses on the same blockers as apply — an
    # open issue (a turn waiting on a question or an ask child) must not be
    # handed to the old runtime. And it never restores the whole metadata
    # object: only the teammate binding key the move added is removed;
    # metadata written after the move (a rotate's bump, another subsystem's
    # key) stands.
    spec, http = wired
    co.cmd_apply(spec)  # a completed move: preimage saved, agent on carrier
    patches_after_move = len(http.patches)

    # open work assigned to the agent: rollback must refuse
    http.issues.append({"identifier": "MAS-7", "status": "in_progress"})
    with pytest.raises(SystemExit):
        co.cmd_rollback(spec)
    assert len(http.patches) == patches_after_move  # nothing changed
    assert http.agent["adapterType"] == "process"
    http.issues.clear()

    # later metadata survives; only the teammate key goes
    http.agent["metadata"] = {"other": {"keep": True},
                              "teammate": {"t3": dict(spec["binding"],
                                                      bindingRevision=4)}}
    assert co.cmd_rollback(spec) == 0
    assert http.agent["adapterType"] == "hermes_local"  # run command restored
    assert http.agent["metadata"] == {"other": {"keep": True}}


def test_rollback_waits_for_a_live_run(wired):
    spec, http = wired
    co.cmd_apply(spec)
    http.live = [{"agentId": AID}]
    with pytest.raises(SystemExit):
        co.cmd_rollback(spec)
    assert http.agent["adapterType"] == "process"


def test_write_private_never_replaces(tmp_path):
    path = str(tmp_path / "f")
    co.write_private(path, "one")
    with pytest.raises(FileExistsError):
        co.write_private(path, "two")
    assert open(path).read() == "one"


def test_a_different_process_command_is_saved_before_the_move(tmp_path, monkeypatch):
    """`process` is a generic run type; only OUR carrier counts as moved."""
    spec = make_spec(tmp_path)
    other = dict(old_agent(), adapterType="process", adapterConfig={
        "command": "/other/tool", "args": ["--serve", "/other/x"],
        "env": {"OTHER": "1"}, "cwd": "/other"})
    http = FakeHttp(other)
    monkeypatch.setattr(co, "Http", lambda base: http)
    assert co.cmd_apply(spec) == 0
    saved = json.load(open(tmp_path / "home" / "cutover-preimage.json"))
    assert saved["adapterConfig"]["command"] == "/other/tool"
    assert co.cmd_rollback(spec) == 0
    assert http.agent["adapterConfig"]["command"] == "/other/tool"
    assert http.agent["adapterConfig"]["env"] == {"OTHER": "1"}


def test_a_failure_after_the_change_says_how_to_recover(wired, monkeypatch, capsys):
    spec, http = wired

    def boom(*a, **k):
        raise RuntimeError("connection cut")
    monkeypatch.setattr(co, "write_binding", boom)
    with pytest.raises(RuntimeError):
        co.cmd_apply(spec)
    said = capsys.readouterr()
    assert "apply` again" in said.out + said.err
    monkeypatch.undo()
    monkeypatch.setattr(co, "Http", lambda base: http)
    assert co.cmd_apply(spec) == 0  # the re-run finishes the link
    assert http.agent["metadata"]["teammate"]["t3"]["primaryThreadId"] == "mcp:t"


def test_apply_looks_again_right_before_the_change(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)

    class WakesMidway(FakeHttp):
        reads = 0

        def get(self, path):
            if path.startswith("/api/agents/"):
                self.reads += 1
                if self.reads == 2:
                    self.agent["status"] = "running"
            return super().get(path)
    http = WakesMidway(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)
    assert http.patches == []


def test_rollback_notices_a_restore_that_did_not_take(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)

    class DropsCommand(FakeHttp):
        def patch(self, path, body):
            if body.get("adapterType") == "hermes_local":
                body = dict(body, adapterConfig=dict(body["adapterConfig"],
                                                     command="/wrong"))
            return super().patch(path, body)
    http = DropsCommand(old_agent())
    monkeypatch.setattr(co, "Http", lambda base: http)
    co.cmd_apply(spec)
    with pytest.raises(SystemExit):
        co.cmd_rollback(spec)
    assert (tmp_path / "home" / "cutover-preimage.json").exists()


def test_refresh_carrier_swaps_the_file_for_a_moved_agent(wired, tmp_path, capsys):
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    carrier = tmp_path / "carrier" / "wake_carrier.py"
    carrier.write_text("# an older carrier\n")
    # open work blocks a move, and must not block a carrier fix
    http.issues.append({"identifier": "MAS-9", "status": "in_review"})
    capsys.readouterr()
    assert co.cmd_refresh_carrier(spec) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["changed"] and out["sha256Before"] != out["sha256After"]
    source = os.path.join(os.path.dirname(co.__file__), "wake_carrier.py")
    assert carrier.read_bytes() == open(source, "rb").read()
    assert os.listdir(tmp_path / "carrier") == ["wake_carrier.py"]  # no leftovers
    assert out["configChanged"] is False         # apply wrote this spec's file
    assert co.cmd_refresh_carrier(spec) == 0     # a second run changes nothing
    assert json.loads(capsys.readouterr().out)["changed"] is False


def test_refresh_carrier_brings_the_settings_file_up_to_its_spec(
        wired, tmp_path, capsys):
    # A carrier fix that adds a setting must not be installed without it.
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    config = tmp_path / "home" / "carrier.json"
    old = json.loads(config.read_text())
    old.pop("question_wait_sec")
    config.write_text(json.dumps(old))
    spec = dict(spec, thread_url_template="http://127.0.0.1:3780/env/{thread}")
    capsys.readouterr()
    assert co.cmd_refresh_carrier(spec) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["configChanged"] is True
    assert out["configKeysChanged"] == ["question_wait_sec",
                                        "thread_url_template"]
    assert json.loads(config.read_text()) == co.carrier_config(spec)
    assert sorted(os.listdir(tmp_path / "home")) == sorted(
        n for n in os.listdir(tmp_path / "home") if ".new-" not in n)
    assert co.cmd_refresh_carrier(spec) == 0
    assert json.loads(capsys.readouterr().out)["configChanged"] is False


def test_refresh_carrier_refuses_a_live_run_or_an_unmoved_agent(wired, tmp_path):
    spec, http = wired
    with pytest.raises(SystemExit):              # not moved yet
        co.cmd_refresh_carrier(spec)
    assert co.cmd_apply(spec) == 0
    carrier = tmp_path / "carrier" / "wake_carrier.py"
    carrier.write_text("# an older carrier\n")
    http.live.append({"agentId": "another-agent"})   # the file is shared
    with pytest.raises(SystemExit):
        co.cmd_refresh_carrier(spec)
    assert carrier.read_text() == "# an older carrier\n"


# --- R2a finding 9: apply never overwrites the shared carrier in place --------

def test_apply_refuses_to_overwrite_a_differing_installed_carrier(
        wired, tmp_path, capsys):
    # The carrier file is shared by every moved agent. `apply` is for moving
    # a NEW agent: when an installed file differs from this checkout's copy,
    # apply must refuse and point at `refresh-carrier` (which waits for live
    # runs and swaps in one rename) — never overwrite another version.
    spec, http = wired
    carrier, _ = co.carrier_paths(spec)
    os.makedirs(os.path.dirname(carrier), exist_ok=True)
    with open(carrier, "w") as fh:
        fh.write("# a newer carrier another lane installed\n")
    before = co.sha256_file(carrier)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)
    said = capsys.readouterr()
    assert "refresh-carrier" in said.err
    assert co.sha256_file(carrier) == before       # the file is untouched
    assert http.patches == []                      # the agent was not moved


def test_apply_installs_a_missing_carrier_and_leaves_no_staged_file(wired):
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    carrier, _ = co.carrier_paths(spec)
    here = os.path.dirname(os.path.abspath(co.__file__))
    assert co.sha256_file(carrier) == co.sha256_file(
        os.path.join(here, "wake_carrier.py"))
    assert [f for f in os.listdir(os.path.dirname(carrier))
            if ".new-" in f] == []                 # one rename, no leftovers


def test_reapply_after_a_rotate_refuses_instead_of_reverting(wired):
    # R13: a second apply rewrote the live binding from the (now stale)
    # spec without comparing it to what the agent runs today — a rotate's
    # fresh thread binding was silently reverted. An apply on an
    # already-moved agent refuses when the binding changed since the spec;
    # unchanged, it rewrites nothing.
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    # a rotate happened: the agent's binding moved on past the spec
    st.write_binding(http, AID, dict(spec["binding"],
                                     primaryThreadId="mcp:t-rotated"))
    with pytest.raises(SystemExit):
        co.cmd_apply(spec)
    got = http.agent["metadata"]["teammate"]["t3"]
    assert got["primaryThreadId"] == "mcp:t-rotated"  # the rotate stands


def test_reapply_with_an_unchanged_binding_rewrites_nothing(wired):
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    binding_before = copy.deepcopy(http.agent["metadata"]["teammate"])
    patches_before = len(http.patches)
    assert co.cmd_apply(spec) == 0
    assert http.agent["metadata"]["teammate"] == binding_before  # no churn
    # no METADATA write rides a no-op apply (the adapter patch repeats its
    # own values; the binding is what a rotate owns)
    assert not any("metadata" in p for p in http.patches[patches_before:])


def test_reapply_blocked_at_the_last_gate_writes_nothing_live(
        wired, tmp_path, monkeypatch):
    # R13: the live carrier.json was rewritten BEFORE the final blockers
    # gate, so an apply that died at the gate had already changed what the
    # next wake would read. The config write happens only after the gate.
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    config = os.path.join(spec["agent_dir"], "carrier.json")
    before = open(config).read()
    spec2 = dict(spec, t3=dict(spec["t3"], port=3781))  # a changed config
    calls = {"n": 0}
    real_read_state = co.read_state

    def read_state(http_, spec_):
        calls["n"] += 1
        agent_, issues_, live_ = real_read_state(http_, spec_)
        if calls["n"] >= 2:      # the re-check right before the change
            live_ = live_ + [{"id": "run-77", "agentId": AID}]
        return agent_, issues_, live_

    monkeypatch.setattr(co, "read_state", read_state)
    with pytest.raises(SystemExit):
        co.cmd_apply(spec2)
    assert open(config).read() == before   # the live config was untouched


def test_rollback_refuses_when_the_agent_changed_after_the_move(wired):
    # R14: rollback restored the saved setup wholesale with no staleness
    # check — a third-party change to the run command since the move was
    # silently overwritten. The move records its exact patch; rollback
    # refuses when the live agent no longer matches it.
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    http.agent["adapterConfig"] = dict(http.agent["adapterConfig"],
                                       timeoutSec=99)  # a third party
    with pytest.raises(SystemExit):
        co.cmd_rollback(spec)
    assert http.agent["adapterType"] == "process"  # nothing was rolled back


def test_rollback_marks_the_result_file(wired, tmp_path):
    # R26: rollback left cutover-result.json describing a live move. The
    # file now records the rollback.
    spec, http = wired
    assert co.cmd_apply(spec) == 0
    assert co.cmd_rollback(spec) == 0
    result = json.load(open(os.path.join(spec["agent_dir"],
                                         "cutover-result.json")))
    assert result.get("rolledBackAt")
    assert result.get("movedAt")     # the history is kept, not erased


def test_read_state_walks_past_the_first_page_of_open_issues():
    # The board caps a list page at 50 rows. With 53 open issues in one
    # state, the single fixed-limit read saw only the first 50: the move
    # believed 3 assigned issues did not exist. The read walks pages until
    # a short page comes back.
    from urllib.parse import parse_qs, urlsplit

    rows = [{"id": f"is-{i}", "status": "todo"} for i in range(53)]
    walked = []

    class PagedHttp(FakeHttp):
        def get(self, path):
            if "/issues?" in path:
                q = parse_qs(urlsplit(path).query)
                state = q["status"][0]
                offset = int(q.get("offset", ["0"])[0])
                limit = int(q.get("limit", ["50"])[0])
                page = [i for i in self.issues
                        if i["status"] == state][offset:offset + limit]
                walked.append((state, offset, len(page)))
                return page
            return super().get(path)

    http = PagedHttp(old_agent(), issues=rows)
    agent, open_issues, live = co.read_state(http, {"company_id": CID,
                                                    "agent_id": AID})
    assert len(open_issues) == 53
    assert any(offset > 0 for _, offset, _ in walked)
