"""teammate_gate.py — the PRIMARY teammate fence (repair round 1).

Every test runs the real gate as a subprocess with a real config file and
real stdin JSON, asserting exit codes: 0 allows, 2 refuses. The filesystem
fixtures live under tmp_path; no test touches the user's real folders and no
test needs the network (literal IPs and .invalid hostnames only).
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import unicodedata

import pytest

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "tools" / "mmos_team_server" / "teammate_gate.py"
ROSTER = REPO / "tools" / "mmos_team_server" / "team_roster.py"

gate_loader = importlib.util.spec_from_file_location("teammate_gate", GATE)
teammate_gate = importlib.util.module_from_spec(gate_loader)
gate_loader.loader.exec_module(teammate_gate)

roster_loader = importlib.util.spec_from_file_location("team_roster_gate", ROSTER)
team_roster = importlib.util.module_from_spec(roster_loader)
roster_loader.loader.exec_module(team_roster)


class Rig:
    """A gate config + fixture tree for one spec shape."""

    def __init__(self, tmp_path, rooted=True, write_names=None,
                 extra_deny=None):
        self.root = tmp_path / "server-root"
        self.home = self.root / "teammates" / "a"
        self.other = self.root / "teammates" / "b"
        self.ws = tmp_path / "team-project"
        for d in (self.home, self.other, self.ws, self.root / "run",
                  self.root / "bin"):
            d.mkdir(parents=True, exist_ok=True)
        # stand-ins for the sensitive folders (never the real ones)
        self.dotssh = tmp_path / ".ssh"
        self.dotssh.mkdir()
        (self.dotssh / "id_rsa.stand-in").write_text("stand-in-key\n")
        (self.home / "CLAUDE.md").write_text("memory\n")
        (self.ws / "artifact.md").write_text("artifact\n")
        deny = [str(self.dotssh),
                "/System/Volumes/Data" + str(self.dotssh),
                str(tmp_path / "window-dev") + "*"]
        deny += extra_deny or []
        self.config = {
            "home": str(self.home),
            "read_roots": [str(self.ws)] if rooted else None,
            "deny_reads": deny,
            "write_names": write_names,
        }
        self.config_path = tmp_path / "gate-config.json"
        self.config_path.write_text(json.dumps(self.config))
        self.cwd = str(self.ws)

    def tmpdir(self):
        return self.config_path.parent

    def call(self, tool, tool_input, cwd=None, config=None):
        payload = {"tool_name": tool, "tool_input": tool_input,
                   "cwd": cwd or self.cwd, "hook_event_name": "PreToolUse"}
        proc = subprocess.run(
            [sys.executable, str(GATE), "--config",
             str(config or self.config_path)],
            input=json.dumps(payload), capture_output=True, text=True,
            timeout=30)
        return proc

    def allowed(self, tool, tool_input, **kw):
        proc = self.call(tool, tool_input, **kw)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        return proc

    def refused(self, tool, tool_input, **kw):
        proc = self.call(tool, tool_input, **kw)
        assert proc.returncode == 2, (proc.returncode, proc.stdout,
                                      proc.stderr)
        assert proc.stderr.strip(), "refusals carry a reason"
        return proc


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


class TestWrites:
    def test_write_inside_home_allowed(self, rig):
        rig.allowed("Write", {"file_path": str(rig.home / "notes.md"),
                              "content": "x"})

    def test_edit_inside_home_allowed(self, rig):
        target = rig.home / "CLAUDE.md"
        rig.allowed("Edit", {"file_path": str(target), "old_string": "memory",
                             "new_string": "memory2"})

    def test_write_outside_home_refused(self, rig):
        for target in (rig.root / "run" / "x", rig.other / "poison",
                       rig.ws / "artifact.md", rig.root / "bin" / "gate.py",
                       rig.dotssh / "authorized_keys"):
            rig.refused("Write", {"file_path": str(target), "content": "x"})

    def test_write_relative_and_escape_forms_refused(self, rig):
        # .. escape from the home, // and /./ spellings of an outside path
        forms = [
            os.path.join(rig.home, "..", "b", "poison"),
            str(rig.other).replace("/teammates/", "//teammates/"),
            str(rig.other).replace("/b", "/./b"),
        ]
        for form in forms:
            rig.refused("Write", {"file_path": form, "content": "x"})

    def test_write_through_home_symlink_out_refused(self, rig):
        link = rig.home / "out-link"
        os.symlink(str(rig.dotssh), link)
        rig.refused("Write", {"file_path": str(link / "newkey"),
                              "content": "x"})

    def test_protected_names_refused_for_write(self, rig):
        for name in ("tool-limits.json", "CHARTER.md", "settings.json",
                     ".mcp.json", ".claude.json.backup", "skills"):
            rig.refused("Write", {"file_path": os.path.join(rig.home, name),
                                  "content": "x"})

    def test_case_flip_of_protected_name_refused(self, rig):
        # macOS volumes are case-insensitive: SETTINGS.JSON is settings.json
        rig.refused("Write", {"file_path": os.path.join(rig.home,
                                                        "SETTINGS.JSON"),
                              "content": "x"})
        rig.refused("Write", {"file_path": os.path.join(
            rig.home, ".Claude", "settings.json"), "content": "x"})

    def test_write_names_mode_only_named_entries(self, tmp_path):
        strict = Rig(tmp_path, write_names=["CLAUDE.md", "notes/"])
        strict.allowed("Write", {"file_path": str(strict.home / "CLAUDE.md"),
                                 "content": "x"})
        (strict.home / "notes").mkdir()
        strict.allowed("Write", {"file_path": str(strict.home / "notes" /
                                                  "n.md"), "content": "x"})
        strict.refused("Write", {"file_path": str(strict.home / "free.md"),
                                 "content": "x"})

    def test_firmlink_spelling_write_refused(self, rig):
        spelled = "/System/Volumes/Data" + str(rig.other / "poison")
        rig.refused("Write", {"file_path": spelled, "content": "x"})

    def test_notebookedit_treated_as_write(self, rig):
        rig.refused("NotebookEdit", {
            "file_path": str(rig.root / "run" / "n.ipynb"),
            "new_source": "x"})


class TestReads:
    def test_read_home_and_root_allowed(self, rig):
        rig.allowed("Read", {"file_path": str(rig.home / "CLAUDE.md")})
        rig.allowed("Read", {"file_path": str(rig.ws / "artifact.md")})

    def test_read_outside_roots_refused(self, rig):
        rig.refused("Read", {"file_path": str(rig.root / "run" /
                                              "server.log")})
        rig.refused("Read", {"file_path": "/etc/passwd"})

    def test_read_denied_folder_refused_with_all_spellings(self, rig):
        nfd = unicodedata.normalize("NFD", str(rig.dotssh))
        forms = [
            str(rig.dotssh / "id_rsa.stand-in"),
            str(rig.dotssh).upper().replace(".SSH", ".SSH") + "/id_rsa.stand-in",
            nfd + "/id_rsa.stand-in",
            "/System/Volumes/Data" + str(rig.dotssh / "id_rsa.stand-in"),
            str(rig.dotssh) + "/../.ssh/id_rsa.stand-in",
        ]
        for form in forms:
            rig.refused("Read", {"file_path": form})

    def test_read_inside_root_via_symlink_out_refused(self, rig):
        link = rig.ws / "secret-link"
        os.symlink(str(rig.dotssh / "id_rsa.stand-in"), link)
        rig.refused("Read", {"file_path": str(link)})

    def test_deny_list_mode_reads_outside_except_denied(self, tmp_path):
        loose = Rig(tmp_path, rooted=False)
        loose.config["read_roots"] = None
        loose.config_path.write_text(json.dumps(loose.config))
        outside = tmp_path / "outside"
        outside.mkdir(exist_ok=True)
        (outside / "ok.md").write_text("ok")
        # outside-but-not-denied is readable in deny-list mode (today's
        # production semantics); the denied folder never is
        loose.allowed("Read", {"file_path": str(outside / "ok.md")})
        loose.refused("Read", {"file_path": str(
            loose.dotssh / "id_rsa.stand-in")})

    def test_preimage_unreadable_in_own_home(self, rig):
        preimage = rig.home / "cutover-preimage.json"
        preimage.write_text("preimage\n")
        rig.refused("Read", {"file_path": str(preimage)})

    def test_server_root_deny_does_not_deny_own_home(self, rig):
        rig.config["deny_reads"] = [str(rig.root)]
        rig.config_path.write_text(json.dumps(rig.config))
        rig.allowed("Read", {"file_path": str(rig.home / "CLAUDE.md")})
        rig.refused("Read", {"file_path": str(rig.root / "run" /
                                              "server.log")})

    def test_prefix_family_deny(self, rig):
        window = rig.tmp if hasattr(rig, "tmp") else None
        base = rig.config["deny_reads"][-1].rstrip("*").rstrip("/")
        target = base + "-7" + "/state.json"
        os.makedirs(os.path.dirname(target), exist_ok=True)
        open(target, "w").write("x")
        rig.refused("Read", {"file_path": target})
        rig.refused("Write", {"file_path": target, "content": "x"})

    def test_relative_path_resolved_against_cwd(self, rig):
        rig.allowed("Read", {"file_path": "artifact.md"})
        rig.refused("Read", {"file_path": "../.ssh/id_rsa.stand-in"})


class TestSearches:
    def test_glob_inside_home_allowed(self, rig):
        rig.allowed("Glob", {"pattern": "**/*.md",
                             "path": str(rig.home)})

    def test_grep_file_inside_home_allowed(self, rig):
        rig.allowed("Grep", {"pattern": "memory",
                             "path": str(rig.home / "CLAUDE.md")})

    def test_search_in_denied_folder_refused(self, rig):
        rig.refused("Grep", {"pattern": "KEY", "path": str(rig.dotssh)})
        rig.refused("Glob", {"pattern": "*", "path": str(rig.dotssh)})

    def test_search_at_or_above_denied_folder_refused(self, rig):
        # P4: enumerating a denied folder's parent leaks its names, and a
        # search rooted above a denied folder walks into it
        rig.refused("Grep", {"pattern": "KEY", "path": str(rig.tmpdir())})
        rig.refused("Glob", {"pattern": ".ssh/*", "path": str(rig.tmpdir())})
        rig.refused("Grep", {"pattern": "KEY", "path": str(rig.root)})

    def test_search_patterns_must_stay_relative(self, rig):
        rig.refused("Glob", {"pattern": "/**/*.key", "path": str(rig.ws)})
        rig.refused("Glob", {"pattern": "~/.ssh/*", "path": str(rig.ws)})
        rig.refused("Glob", {"pattern": "../../**", "path": str(rig.ws)})

    def test_search_outside_read_roots_refused(self, rig):
        rig.refused("Glob", {"pattern": "*", "path": "/etc"})
        rig.refused("Grep", {"pattern": "x", "path": "/etc"})


class TestWeb:
    def test_loopback_refused_by_address(self, rig):
        for url in ("http://127.0.0.1:50821/", "http://localhost:50821/",
                    "http://[::1]:50821/", "http://0.0.0.1/",
                    "http://169.254.169.254/latest/meta-data/",
                    "http://192.168.1.1/", "http://10.0.0.1/",
                    "http://172.16.0.1/"):
            rig.refused("WebFetch", {"url": url, "prompt": "x"})

    def test_public_literal_allowed(self, rig):
        # literal global IP: no DNS, no network request is made — the gate
        # only resolves
        rig.allowed("WebFetch", {"url": "http://93.184.216.34/",
                                 "prompt": "x"})

    def test_unresolvable_host_refused(self, rig):
        rig.refused("WebFetch", {"url": "http://nonexistent.invalid/",
                                 "prompt": "x"})

    def test_non_http_scheme_refused(self, rig):
        rig.refused("WebFetch", {"url": "file:///etc/passwd", "prompt": "x"})
        rig.refused("WebFetch", {"url": "ftp://93.184.216.34/",
                                 "prompt": "x"})

    def test_web_reader_tool_gated_by_url(self, rig):
        rig.refused("mcp__web_reader__webReader",
                    {"url": "http://127.0.0.1:50821/"})
        rig.allowed("mcp__web_reader__webReader",
                    {"url": "http://93.184.216.34/"})


class TestToolAllowlist:
    def test_free_tools_allowed(self, rig):
        for tool, inp in (("TodoWrite", {"todos": []}),
                          ("WebSearch", {"query": "example"}),
                          ("ToolSearch", {"query": "web"})):
            rig.allowed(tool, inp)

    def test_unknown_tools_refused(self, rig):
        for tool, inp in (("Bash", {"command": "id"}),
                          ("Agent", {"prompt": "x"}),
                          ("Workflow", {"script": "x"}),
                          ("SendMessage", {"to": "x", "message": "x"}),
                          ("ListAgents", {}),
                          ("ScheduleWakeup", {"delaySeconds": 60}),
                          ("Skill", {"skill": "x"}),
                          ("mcp__t3-code__request_secret",
                           {"name": "x"})):
            rig.refused(tool, inp)

    def test_unparseable_input_refused(self, rig):
        proc = subprocess.run(
            [sys.executable, str(GATE), "--config", str(rig.config_path)],
            input="not json", capture_output=True, text=True, timeout=30)
        assert proc.returncode == 2

    def test_tool_input_not_object_refused(self, rig):
        rig.refused("Write", "not-a-dict")

    def test_missing_config_refused(self, rig):
        rig.refused("Write", {"file_path": str(rig.home / "x"),
                              "content": "x"},
                    config=rig.home / "no-such-config.json")

    def test_corrupt_config_refused(self, tmp_path, rig):
        bad = tmp_path / "bad.json"
        bad.write_text("{nope")
        rig.refused("Write", {"file_path": str(rig.home / "x"),
                              "content": "x"}, config=bad)

    def test_config_without_home_refused(self, tmp_path, rig):
        bad = tmp_path / "nohome.json"
        bad.write_text(json.dumps({"read_roots": []}))
        rig.refused("Write", {"file_path": str(rig.home / "x"),
                              "content": "x"}, config=bad)

    def test_wired_without_config_flag_refused(self, rig):
        payload = {"tool_name": "Read",
                   "tool_input": {"file_path": str(rig.home / "CLAUDE.md")},
                   "cwd": rig.cwd}
        proc = subprocess.run([sys.executable, str(GATE)],
                              input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 2


class TestConstantsSync:
    def test_protected_names_cover_generator_tuples(self):
        expected = set(team_roster.HOME_LOCKED) | set(team_roster.HOME_CONFIG)
        expected |= {".claude.json.backup"}
        assert expected <= set(teammate_gate.PROTECTED_NAMES)

    def test_gate_file_is_executable_and_private(self):
        mode = stat.S_IMODE(GATE.stat().st_mode)
        assert mode & 0o111, "apply installs it executable"
