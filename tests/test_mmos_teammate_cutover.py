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
    assert http.agent["metadata"]["teammate"]["t3"]["bindingRevision"] == 2


def test_rollback_restores_the_saved_setup(wired, tmp_path):
    spec, http = wired
    before = old_agent()
    co.cmd_apply(spec)
    assert co.cmd_rollback(spec) == 0
    for key in co.PREIMAGE_KEYS:
        assert http.agent[key] == before[key]
    assert not (tmp_path / "home" / "cutover-preimage.json").exists()
    assert [p for p in os.listdir(tmp_path / "home") if ".restored-" in p]


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
    assert co.cmd_refresh_carrier(spec) == 0     # a second run changes nothing
    assert json.loads(capsys.readouterr().out)["changed"] is False


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
