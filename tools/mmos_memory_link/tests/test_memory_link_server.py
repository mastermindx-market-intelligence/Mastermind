"""Tests for the memory-link stdio MCP server.

The store CLI is never the real `omh`; tests install a fake binary in tmp_path.
"""

from __future__ import annotations

import json
import os
import select
import stat
import subprocess
import time
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "memory_link_server.py"
PYTHON = "/opt/homebrew/bin/python3.12"
HYPHEN = "‐"  # U+2010, the leading-dash guard

CANNED_RECALL = {
    "included_records": [
        {
            "record_id": "rec-1",
            "summary": "Alpha uses confirmation over prediction",
            "subject": "doctrine",
            "tags": ["doctrine"],
            "record_type": "fact",
            "approved_at": "2026-11-01T00:00:00Z",
            "source": "omh_local",
            "staleness": {"state": "fresh"},
            "source_ref": "/secret/path/to/store.db",
            "payload_digest": "deadbeef",
        }
    ],
    "record_count": 1,
    "truncated": False,
    "excluded_records": [
        {"record_id": "rec-x", "source_ref": "/secret/path/to/store.db"}
    ],
    "source_ref": "/secret/path/to/store.db",
    "payload_digest": "deadbeef",
}

CANNED_CAPTURE = {
    "captured": True,
    "auto_approved": True,
    "record": {"record_id": "rec-new"},
    "candidate": {"candidate_id": "cand-1"},
}

FAKE_OMH = r'''#!/opt/homebrew/bin/python3.12
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
record = {"argv": sys.argv, "env": dict(os.environ)}
(HERE / "omh_last.json").write_text(json.dumps(record), encoding="utf-8")
with (HERE / "omh_log.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv}) + "\n")

if (HERE / "omh_sleep").exists():
    time.sleep(30)

if (HERE / "omh_fail").exists():
    if (HERE / "omh_secret").exists():
        sys.stderr.write("store refused: token: abc123\n")
    else:
        sys.stderr.write("store refused: not admissible\n")
    sys.exit(1)

args = sys.argv[1:]
sub = None
if "memory" in args:
    i = args.index("memory")
    if i + 1 < len(args):
        sub = args[i + 1]

if sub == "capture":
    out = {
        "captured": True,
        "auto_approved": True,
        "record": {"record_id": "rec-new"},
        "candidate": {"candidate_id": "cand-1"},
    }
else:
    kind = args[args.index("--scope-kind") + 1] if "--scope-kind" in args else ""
    ref = args[args.index("--scope-ref") + 1] if "--scope-ref" in args else ""
    secret = (HERE / "omh_secret").exists()
    out = {
        "included_records": [
            {
                "record_id": "rec-1" if kind == "user-global" else "rec-own",
                "scope": {"kind": kind, "ref": ref},
                "summary": ("Alpha uses confirmation token: abc123" if secret
                            else "Alpha uses confirmation over prediction"),
                "subject": "password: doctrine" if secret else "doctrine",
                "tags": ["doctrine"],
                "record_type": "fact",
                "approved_at": "2026-11-01T00:00:00Z",
                "source": "omh_local",
                "staleness": {"state": "fresh"},
                "source_ref": "/secret/path/to/store.db",
                "payload_digest": "deadbeef",
            }
        ],
        "record_count": 1,
        "truncated": False,
        "excluded_records": [
            {"record_id": "rec-x", "source_ref": "/secret/path/to/store.db"}
        ],
        "source_ref": "/secret/path/to/store.db",
        "payload_digest": "deadbeef",
    }

sys.stdout.write(json.dumps(out) + "\n")
'''


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.omh_home = tmp_path / "omh-home"
        self.hermes_home = tmp_path / "hermes-home"
        self.omh_home.mkdir()
        self.hermes_home.mkdir()
        self.omh_bin = tmp_path / "omh"
        self.omh_bin.write_text(FAKE_OMH, encoding="utf-8")
        self.omh_bin.chmod(0o755)
        self.stderr_file = tmp_path / "server.err"
        self.proc: subprocess.Popen[str] | None = None
        self._id = 0

    def write_config(self, **overrides):
        cfg = {
            "omh_bin": str(self.omh_bin),
            "omh_home": str(self.omh_home),
            "hermes_home_for_omh": str(self.hermes_home),
            "teammate": "testbot",
            "write_enabled": False,
            "limit_default": 8,
            "limit_max": 20,
            "max_chars": 6000,
            "call_timeout_sec": 20,
        }
        cfg.update(overrides)
        path = self.tmp / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        path.chmod(0o600)
        return path

    def start(self, config_path: Path, extra_env: dict | None = None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        err = self.stderr_file.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PYTHON, "-I", str(SERVER), "--config", str(config_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
            env=env,
            text=True,
            bufsize=1,
        )
        self._id = 0
        return self

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self.proc = None

    def read_line(self, timeout: float = 10.0) -> str:
        assert self.proc is not None and self.proc.stdout is not None
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError("no server response")
        line = self.proc.stdout.readline()
        if line == "" and self.proc.poll() is not None:
            raise RuntimeError(
                f"server exited {self.proc.returncode}; stderr={self.stderr_file.read_text()}"
            )
        return line

    def rpc(self, method: str, params=None, *, notification: bool = False, timeout: float = 10.0):
        assert self.proc is not None and self.proc.stdin is not None
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            self._id += 1
            msg["id"] = self._id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if notification:
            return None
        return json.loads(self.read_line(timeout=timeout))

    def handshake(self):
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        self.rpc("notifications/initialized", notification=True)
        return result

    def call_tool(self, name: str, arguments: dict, timeout: float = 10.0):
        return self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout=timeout,
        )

    def tool_text(self, response: dict) -> str:
        return response["result"]["content"][0]["text"]

    def omh_log(self) -> list:
        path = self.tmp / "omh_log.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def last_omh(self) -> dict:
        return json.loads((self.tmp / "omh_last.json").read_text(encoding="utf-8"))


@pytest.fixture
def harness(tmp_path: Path):
    h = Harness(tmp_path)
    yield h
    h.close()


def test_initialize_tools_list_hides_save_and_notes_when_disabled(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    init = harness.handshake()
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert init["result"]["serverInfo"]["name"] == "memory-link"
    listed = harness.rpc("tools/list", {})
    names = [t["name"] for t in listed["result"]["tools"]]
    assert names == ["memory_recall"]


def test_tools_list_includes_notes_and_save_when_enabled(harness: Harness):
    notes = harness.tmp / "notes"
    notes.mkdir()
    (notes / "MEMORY.md").write_text("mem-body", encoding="utf-8")
    (notes / "USER.md").write_text("user-body", encoding="utf-8")
    cfg = harness.write_config(
        write_enabled=True, profile_memory_dir=str(notes)
    )
    harness.start(cfg)
    harness.handshake()
    listed = harness.rpc("tools/list", {})
    names = [t["name"] for t in listed["result"]["tools"]]
    assert names == ["memory_recall", "memory_notes", "memory_save"]


def test_recall_formats_only_allowed_fields(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool("memory_recall", {"query": "confirmation doctrine"})
    text = harness.tool_text(resp)
    assert "source_ref" not in text
    assert "/secret/path" not in text
    assert "payload_digest" not in text
    assert "deadbeef" not in text
    assert '"included_records"' not in text
    assert "rec-1" in text
    assert "doctrine" in text
    assert "2026-11-01T00:00:00Z" in text
    assert "fresh" in text
    assert "Alpha uses confirmation over prediction" in text
    assert "included=1" in text
    assert "excluded=1" in text
    assert "truncated=false" in text
    assert resp["result"].get("isError") in (None, False)


def test_recall_argv_exact_and_hermes_home_is_empty_dir(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    harness.call_tool("memory_recall", {"query": "confirmation doctrine"})
    argv = harness.omh_log()[1]["argv"]  # [0] is the teammate's own scope
    assert argv[0] == str(harness.omh_bin)
    assert argv[1:7] == [
        "--omh-home",
        str(harness.omh_home),
        "--hermes-home",
        str(harness.hermes_home),
        "memory",
        "recall",
    ]
    assert argv[argv.index("--hermes-home") + 1] == str(harness.hermes_home)
    assert list(harness.hermes_home.iterdir()) == []
    assert "--observer" not in argv
    assert "--scope-kind" in argv
    assert argv[argv.index("--scope-kind") + 1] == "user-global"
    assert argv[argv.index("--scope-ref") + 1] == "default"
    assert argv[argv.index("--limit") + 1] == "8"
    assert argv[-2:] == ["confirmation", "doctrine"]


def test_leading_dash_words_are_neutralised(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    harness.call_tool("memory_recall", {"query": "-secret topic"})
    argv = harness.last_omh()["argv"]
    assert "-secret" not in argv
    assert f"{HYPHEN}secret" in argv
    assert "topic" in argv


def test_child_env_is_scrubbed(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg, extra_env={"MMOS_SENTINEL": "leak-me"})
    harness.handshake()
    harness.call_tool("memory_recall", {"query": "envcheck"})
    env = harness.last_omh()["env"]
    assert "MMOS_SENTINEL" not in env
    assert env.get("HOME") == str(harness.hermes_home)
    assert env.get("PATH") == "/usr/bin:/bin"
    assert env.get("LANG") == "C.UTF-8"
    # macOS CoreFoundation adds __CF_USER_TEXT_ENCODING inside the child itself.
    assert set(env.keys()) - {"__CF_USER_TEXT_ENCODING"} == {"HOME", "PATH", "LANG"}


def test_timeout_kills_child_and_returns_busy(harness: Harness):
    (harness.tmp / "omh_sleep").write_text("1", encoding="utf-8")
    cfg = harness.write_config(call_timeout_sec=1)
    harness.start(cfg)
    harness.handshake()
    t0 = time.monotonic()
    resp = harness.call_tool("memory_recall", {"query": "slow"}, timeout=10.0)
    elapsed = time.monotonic() - t0
    assert elapsed < 8
    assert "memory store busy; try again" in harness.tool_text(resp)
    assert resp["result"].get("isError") is True


def test_save_refused_when_disabled_is_error(harness: Harness):
    cfg = harness.write_config(write_enabled=False)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save",
        {"summary": "this is a valid summary text", "type": "fact"},
    )
    assert resp["result"].get("isError") is True
    assert not (harness.tmp / "omh_last.json").exists()


def test_save_credential_shaped_summary_does_not_invoke_omh(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save",
        {
            "summary": "keep this token: ghp_abcdefghijklmnopqrstuvwxyz0123",
            "type": "fact",
        },
    )
    text = harness.tool_text(resp)
    assert text == "not saved: looks like a credential"
    assert not (harness.tmp / "omh_last.json").exists()


def test_save_success_adds_both_required_tags(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save",
        {
            "summary": "we chose confirmation over prediction",
            "type": "decision",
            "tags": ["doctrine"],
        },
    )
    text = harness.tool_text(resp)
    assert text == "saved rec-new (auto_approved=true)"
    argv = harness.last_omh()["argv"]
    assert argv[1:7] == [
        "--omh-home",
        str(harness.omh_home),
        "--hermes-home",
        str(harness.hermes_home),
        "memory",
        "capture",
    ]
    assert argv[argv.index("--type") + 1] == "decision"
    assert argv[argv.index("--source-class") + 1] == "omh_local"
    assert "via-memory-link" in argv
    assert "teammate-testbot" in argv
    assert "doctrine" in argv
    tags = [argv[i + 1] for i, a in enumerate(argv) if a == "--tag"]
    assert "via-memory-link" in tags
    assert "teammate-testbot" in tags
    assert "doctrine" in tags


def test_notes_refuses_symlinked_memory_md(harness: Harness):
    notes = harness.tmp / "notes"
    notes.mkdir()
    target = harness.tmp / "real_memory.md"
    target.write_text("secret-note-body", encoding="utf-8")
    (notes / "MEMORY.md").symlink_to(target)
    (notes / "USER.md").write_text("user notes", encoding="utf-8")
    cfg = harness.write_config(profile_memory_dir=str(notes))
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool("memory_notes", {})
    assert resp["result"].get("isError") is True
    text = harness.tool_text(resp)
    assert "secret-note-body" not in text


def test_group_writable_config_refused(harness: Harness):
    path = harness.write_config()
    path.chmod(0o660)
    harness.start(path)
    rc = harness.proc.wait(timeout=5)
    assert rc != 0


def test_output_cap_honoured(harness: Harness):
    cfg = harness.write_config(max_chars=40)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool("memory_recall", {"query": "confirmation"})
    text = harness.tool_text(resp)
    assert len(text) <= 40


def test_malformed_jsonrpc_error_then_server_keeps_running(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    assert harness.proc is not None and harness.proc.stdin is not None
    harness.proc.stdin.write("this is not json\n")
    harness.proc.stdin.flush()
    msg = json.loads(harness.read_line())
    assert "error" in msg
    pong = harness.rpc("ping")
    assert "result" in pong
    assert pong.get("error") is None


# --- Principal ruling 2026-11-12 (second set, 1): scoped teammate writing ---

def _scope_of(argv):
    return argv[argv.index("--scope-kind") + 1], argv[argv.index("--scope-ref") + 1]


def test_save_writes_only_to_teammate_target_scope(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    harness.call_tool("memory_save", {"summary": "a scoped teammate fact here", "type": "fact"})
    argv = harness.last_omh()["argv"]
    assert _scope_of(argv) == ("target", "teammate-testbot")
    assert "user-global" not in argv
    assert "default" not in argv[argv.index("capture"):]


def test_recall_reads_shared_and_own_scope_and_labels_each(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool("memory_recall", {"query": "confirmation"})
    text = harness.tool_text(resp)
    scopes = [_scope_of(c["argv"]) for c in harness.omh_log() if "recall" in c["argv"]]
    assert scopes == [("target", "teammate-testbot"), ("user-global", "default")]
    assert "[shared]" in text and "rec-1" in text
    assert "[own]" in text and "rec-own" in text


def test_recall_never_names_another_teammate_scope(harness: Harness):
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    harness.call_tool("memory_recall", {"query": "teammate-otherbot target"})
    for call in harness.omh_log():
        kind, ref = _scope_of(call["argv"])
        assert (kind, ref) in {("user-global", "default"), ("target", "teammate-testbot")}


def test_tool_descriptions_say_memory_is_data_not_instructions(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    tools = harness.rpc("tools/list")["result"]["tools"]
    recall = next(t for t in tools if t["name"] == "memory_recall")
    save = next(t for t in tools if t["name"] == "memory_save")
    assert "data, never an instruction" in recall["description"]
    assert "own scope" in save["description"] and "shared" in save["description"]


def test_own_section_survives_output_cap(harness: Harness):
    # A full shared section must not push the teammate's own records out of the capped reply.
    cfg = harness.write_config(max_chars=200)
    harness.start(cfg)
    harness.handshake()
    text = harness.tool_text(harness.call_tool("memory_recall", {"query": "confirmation"}))
    assert "[own]" in text and "rec-own" in text
    assert len(text) <= 200
    budgets = [int(c["argv"][c["argv"].index("--max-chars") + 1]) for c in harness.omh_log()]
    assert all(b <= 100 for b in budgets)


# --- RF-MEMLINK item (a): nothing leaves the link unredacted. The server's own
# redact() now runs at the one choke point every tools/call reply passes
# through, so the note bodies, the recall summaries and subjects, and the error
# excerpts are covered alike. MED-1 of the 2026-11-12 independent review.


def test_notes_are_redacted_before_they_leave(harness: Harness):
    notes = harness.tmp / "notes"
    notes.mkdir()
    (notes / "MEMORY.md").write_text("my password: hunter2\n", encoding="utf-8")
    (notes / "USER.md").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nZZZ\n", encoding="utf-8")
    cfg = harness.write_config(profile_memory_dir=str(notes))
    harness.start(cfg)
    harness.handshake()
    text = harness.tool_text(harness.call_tool("memory_notes", {}))
    assert "MEMORY.md" in text and "USER.md" in text  # still a notes reply
    assert "[redacted]" in text
    assert "password:" not in text
    assert "PRIVATE KEY" not in text


def test_recall_redacts_summary_and_subject(harness: Harness):
    (harness.tmp / "omh_secret").write_text("1", encoding="utf-8")
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    text = harness.tool_text(harness.call_tool("memory_recall", {"query": "confirmation"}))
    assert "rec-own" in text and "rec-1" in text  # the records still arrive
    assert "[redacted]" in text
    assert "token:" not in text
    assert "password:" not in text


def test_error_excerpt_is_redacted(harness: Harness):
    (harness.tmp / "omh_secret").write_text("1", encoding="utf-8")
    (harness.tmp / "omh_fail").write_text("1", encoding="utf-8")
    cfg = harness.write_config()
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool("memory_recall", {"query": "confirmation"})
    assert resp["result"].get("isError") is True
    text = harness.tool_text(resp)
    assert "[redacted]" in text
    assert "token:" not in text


# --- RF-MEMLINK item (c): no tag may start with a dash. A caller-supplied tag
# is one argv token in option position; the store program must never see a
# value that begins with '-'. LOW of the 2026-11-12 independent review.


def test_tag_may_not_start_with_a_dash(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save",
        {
            "summary": "we chose confirmation over prediction",
            "type": "decision",
            "tags": ["--scope-kind"],
        },
    )
    assert resp["result"].get("isError") is True
    assert harness.tool_text(resp) == "invalid tags"
    assert harness.omh_log() == []  # the store program was never started


def test_tag_starting_with_a_digit_is_still_a_tag(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save",
        {
            "summary": "we chose confirmation over prediction",
            "type": "decision",
            "tags": ["2026-plan"],
        },
    )
    assert harness.tool_text(resp) == "saved rec-new (auto_approved=true)"
    assert "2026-plan" in harness.last_omh()["argv"]


def test_schema_pattern_and_tag_re_agree(harness: Harness):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    tools = harness.rpc("tools/list")["result"]["tools"]
    save = next(t for t in tools if t["name"] == "memory_save")
    pattern = save["inputSchema"]["properties"]["tags"]["items"]["pattern"]
    import re as _re
    assert _re.fullmatch(pattern, "2026-plan")
    assert not _re.fullmatch(pattern, "--scope-kind")
    assert not _re.fullmatch(pattern, "-x")



# --- RF-MEMLINK-R1 item 1 (principal ruling 2026-11-12 14:08Z): a label form
# consumes its VALUE, to the end of the value — not just the label. The
# round-0 tests asserted only that the label was gone, which is why they
# passed while "my password: hunter2" came out as "my [redacted] hunter2".
# Every test here asserts the VALUE itself is absent, and fails first on
# f4e94ead5.

import importlib.util as _ilu  # noqa: E402

_mod_spec = _ilu.spec_from_file_location("memory_link_server_r1", SERVER)
memory_link_server = _ilu.module_from_spec(_mod_spec)
_mod_spec.loader.exec_module(memory_link_server)

R1_LABEL_VALUE_CASES = [
    ("my password: hunter2", "hunter2"),
    ("passwd=hunter2", "hunter2"),
    ("secret: hunter2", "hunter2"),
    ("token = abc123 for the board", "abc123"),
    ("API key: abc123", "abc123"),
    ("api_key=abc123", "abc123"),
    ("apikey: abc123", "abc123"),
    ("Authorization: Bearer abc123", "abc123"),
    ("authorization: basic abc123", "abc123"),
    ("Bearer abc123", "abc123"),
]


@pytest.mark.parametrize("body,value", R1_LABEL_VALUE_CASES)
def test_redact_consumes_the_labelled_value(body, value):
    out = memory_link_server.redact(body)
    assert value not in out, f"value survived redaction: {out!r}"
    assert "[redacted]" in out


def test_redact_keeps_the_words_after_the_value():
    out = memory_link_server.redact("token = abc123 for the board")
    assert "abc123" not in out
    assert "for the board" in out


# The prefix forms and the label-only refusal must not be weakened by the
# value-consuming pattern: memory_save's refusal keeps using this same regex.
R1_NOT_WEAKENED_CASES = [
    "sk-live-abcdef123456",
    "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "github_pat_ABC123def",
    "xoxb-123456-abcdef",
    "AKIAIOSFODNN7EXAMPLE",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0",
    "-----BEGIN RSA PRIVATE KEY-----",
    "password:",
    "token =",
]


@pytest.mark.parametrize("text", R1_NOT_WEAKENED_CASES)
def test_prefix_and_label_only_forms_still_refuse(text):
    assert memory_link_server.looks_like_credential(text)
    out = memory_link_server.redact(text)
    assert "[redacted]" in out
    assert out != text


@pytest.mark.parametrize("body,value", R1_LABEL_VALUE_CASES)
def test_notes_never_leak_the_labelled_value(harness: Harness, body, value):
    notes = harness.tmp / "notes"
    notes.mkdir()
    (notes / "MEMORY.md").write_text(body + "\n", encoding="utf-8")
    (notes / "USER.md").write_text("user notes\n", encoding="utf-8")
    cfg = harness.write_config(profile_memory_dir=str(notes))
    harness.start(cfg)
    harness.handshake()
    text = harness.tool_text(harness.call_tool("memory_notes", {}))
    assert value not in text, f"value left the link unredacted: {text!r}"
    assert "[redacted]" in text


@pytest.mark.parametrize("summary", [
    "secret: hunter2",
    "passwd=hunter2",
    "API key: abc123",
    "Authorization: Bearer abc123",
    "Bearer abc123",
])
def test_save_refuses_every_label_form(harness: Harness, summary):
    cfg = harness.write_config(write_enabled=True)
    harness.start(cfg)
    harness.handshake()
    resp = harness.call_tool(
        "memory_save", {"summary": summary, "type": "fact"})
    assert harness.tool_text(resp) == "not saved: looks like a credential"
    assert not (harness.tmp / "omh_last.json").exists()
