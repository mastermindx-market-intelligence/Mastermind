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
    def test_glob_inside_home_subfolder_allowed(self, rig):
        # repair round 2, R3: the home itself sits at/above protected
        # files and is refused as a search root; a clean subfolder is fine
        notes = rig.home / "notes"
        notes.mkdir()
        rig.allowed("Glob", {"pattern": "**/*.md", "path": str(notes)})
        rig.refused("Glob", {"pattern": "**/*.md", "path": str(rig.home)})

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

    def test_public_literal_refused(self, rig):
        # repair round 2, R2 (principal ruling, stricter than the panel):
        # the gate must NOT parse like the client — every address literal
        # is refused before resolution; only a plain DNS name passes
        for url in ("http://93.184.216.34/", "https://8.8.8.8/",
                    "http://1.1.1.1:80/"):
            rig.refused("WebFetch", {"url": url, "prompt": "x"})

    def test_unresolvable_host_refused(self, rig):
        rig.refused("WebFetch", {"url": "http://nonexistent.invalid/",
                                 "prompt": "x"})

    def test_non_http_scheme_refused(self, rig):
        rig.refused("WebFetch", {"url": "file:///etc/passwd", "prompt": "x"})
        rig.refused("WebFetch", {"url": "ftp://93.184.216.34/",
                                 "prompt": "x"})

    def test_web_reader_tool_gated_by_url(self, rig, monkeypatch):
        rig.refused("mcp__web_reader__webReader",
                    {"url": "http://127.0.0.1:50821/"})
        # allowed case needs a plain DNS name resolving publicly — faked
        # in-process (no network in tests), R2: literals never pass
        fake = [(2, 1, 6, "", ("93.184.216.34", 0))]
        monkeypatch.setattr(teammate_gate.socket, "getaddrinfo",
                            lambda *a, **k: fake)
        assert teammate_gate.check_web(
            {"url": "http://example.com/"}) is None


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


class TestRepairRound2:
    """Panel 2 findings (R1-R6a): each test names the repair it pins."""

    # --- R1: the web check reads exactly the `url` field (H1) ---

    def test_r1_web_reads_exact_url_field(self, rig):
        # a public `prompt` must not hide a loopback `url` (H1 example)
        rig.refused("WebFetch", {"prompt": "https://example.com",
                                 "url": "http://127.0.0.1:50821/"})
        # uppercase scheme spelled in the url, public decoy first
        rig.refused("WebFetch", {"prompt": "https://example.com",
                                 "url": "HTTP://127.0.0.1/"})
        # missing / non-string url
        rig.refused("WebFetch", {"prompt": "https://example.com"})
        rig.refused("WebFetch", {"url": 12345, "prompt": "x"})
        rig.refused("WebFetch", {"url": None})
        # leading/trailing whitespace on the url itself
        rig.refused("WebFetch", {"url": " http://127.0.0.1:50821/"})

    # --- R2: canonical host spelling, no address literals of any form ---

    def test_r2_address_literals_refused(self, rig):
        for url in ("http://0177.0.0.1/", "http://0177.0.0.0177/",
                    "http://2130706433/", "http://0x7f000001/",
                    "http://127.0.0.1\\@example.com/",
                    "http://example.com\\@127.0.0.1/",
                    "http://[::1]/", "http://[::ffff:93.184.216.34]/",
                    "http://::1/", "http://93.184.216.34/",
                    "http://1.2.3.4.5/", "http://example.1/",
                    "http://0x7f.0.0.1/"):
            rig.refused("WebFetch", {"url": url, "prompt": "x"})

    def test_r2_authority_abuse_refused(self, rig):
        for url in ("http://a:b@public.example/",       # userinfo
                    "http://ex%31mple.com/",             # percent in authority
                    "http://exämple.com/",               # non-ASCII authority
                    "http://pub\rlic.example/",          # control character
                    "http://pub lic.example/",           # whitespace
                    "http://public.example\\path/",      # backslash anywhere
                    "gopher://public.example/",          # scheme (lowercased)
                    "GOPHER://public.example/",
                    "file:///etc/passwd",
                    "http:93.184.216.34"):               # no authority
            rig.refused("WebFetch", {"url": url, "prompt": "x"})

    def test_r2_non_default_port_refused(self, rig):
        # refused before any DNS use, so no network is needed
        rig.refused("WebFetch", {"url": "http://public.example:8080/",
                                 "prompt": "x"})
        rig.refused("WebFetch", {"url": "https://public.example:8443/",
                                 "prompt": "x"})
        rig.refused("WebFetch", {"url": "http://public.example:notaport/",
                                 "prompt": "x"})

    def test_r2_plain_dns_allowed_when_resolution_is_public(self, rig,
                                                            monkeypatch):
        # in-process: fake resolution, no network. Only a plain DNS name
        # with a global resolved address passes.
        fake = [(2, 1, 6, "", ("93.184.216.34", 0))]
        monkeypatch.setattr(teammate_gate.socket, "getaddrinfo",
                            lambda *a, **k: fake)
        assert teammate_gate.check_web(
            {"url": "http://example.com/", "prompt": "x"}) is None
        assert teammate_gate.check_web(
            {"url": "https://example.com:443/x", "prompt": "x"}) is None
        # DNS name resolving into CGNAT (Tailscale range) is refused
        cgnat = [(2, 1, 6, "", ("100.101.1.2", 0))]
        monkeypatch.setattr(teammate_gate.socket, "getaddrinfo",
                            lambda *a, **k: cgnat)
        reason = teammate_gate.check_web({"url": "http://example.com/",
                                          "prompt": "x"})
        assert reason and "refused" in reason

    def test_r2_dns_timeout_refuses(self, monkeypatch):
        import socket as _socket

        def hang(*a, **k):
            import threading
            threading.Event().wait(30)

        monkeypatch.setattr(teammate_gate.socket, "getaddrinfo", hang)
        teammate_gate._RESOLVE_JOIN_SECONDS = 1  # keep the test fast
        reason = teammate_gate.check_web({"url": "http://example.com/",
                                          "prompt": "x"})
        assert reason and "timed out" in reason

    # --- R6a: explicit address-class refusal list (M1) ---

    def test_r6a_refused_address_classes(self):
        for ip_text in ("224.0.0.1",            # multicast v4
                        "239.1.1.1",
                        "ff02::1",               # multicast v6
                        "::127.0.0.1",           # IPv4-compatible
                        "::ffff:127.0.0.1",      # IPv4-mapped
                        "64:ff9b::7f00:1",       # NAT64 embedding loopback
                        "100.64.0.1",            # CGNAT (Tailscale)
                        "100.127.255.254",
                        "2002:7f00:1::",         # 6to4 embedding loopback
                        "2001:0:7f00:1::",       # Teredo prefix
                        "fe80::1", "fc00::1", "0.0.0.0", "240.0.0.1"):
            reason = teammate_gate.address_reason(ip_text)
            assert reason, f"{ip_text} must be refused"
        for ip_text in ("93.184.216.34", "2600::1"):
            assert teammate_gate.address_reason(ip_text) is None

    # --- R3: one unreadable set for Read, Glob and Grep (H3 + M5) ---

    def test_r3_unreadable_home_names_refused_for_read(self, rig):
        for name in ("cutover-preimage.json", ".credentials.json",
                     ".claude.json", ".claude.json.backup", "carrier.json",
                     "tool-limits.json", "settings.json",
                     "settings.local.json", "settings-managed.json"):
            target = rig.home / name
            target.write_text("stand-in\n")
            rig.refused("Read", {"file_path": str(target)})

    def test_r3_projects_folder_unreadable(self, rig):
        proj = rig.home / "projects" / "session.jsonl"
        proj.parent.mkdir(parents=True)
        proj.write_text("transcript stand-in\n")
        rig.refused("Read", {"file_path": str(proj)})

    def test_r3_search_at_home_refused_with_hints(self, rig):
        (rig.home / "cutover-preimage.json").write_text("stand-in\n")
        (rig.home / "notes").mkdir(exist_ok=True)
        proc = rig.refused("Grep", {"pattern": "STANDIN",
                                    "path": str(rig.home)})
        # the refusal names folders the teammate may search instead
        assert str(rig.ws) in proc.stderr or "search instead" in proc.stderr
        rig.refused("Glob", {"pattern": "*.json", "path": str(rig.home)})
        # no path at all: cwd is inside the home -> still refused
        rig.refused("Grep", {"pattern": "STANDIN"}, cwd=str(rig.home))

    def test_r3_search_in_clean_subfolder_and_workspace_allowed(self, rig):
        notes = rig.home / "notes"
        notes.mkdir(exist_ok=True)
        (notes / "n.md").write_text("word\n")
        rig.allowed("Grep", {"pattern": "word", "path": str(notes)})
        rig.allowed("Glob", {"pattern": "*.md", "path": str(rig.ws)})

    def test_r3_brace_and_backslash_patterns_refused(self, rig):
        for pattern in ("{..}", "{a,..}/x", "{a,/x}", "x/{..}/y", "a\\b"):
            rig.refused("Glob", {"pattern": pattern, "path": str(rig.ws)})
            rig.refused("Grep", {"pattern": pattern, "path": str(rig.ws)})

    # --- R5: @ import lines in client-loaded files (N2) ---

    def test_r5_at_import_line_refused(self, rig):
        target = rig.home / "CLAUDE.md"
        rig.refused("Write", {"file_path": str(target),
                              "content": "memory\n@/etc/passwd\n"})
        rig.refused("Edit", {"file_path": str(target), "old_string": "a",
                             "new_string": "@/etc/passwd"})
        rig.refused("MultiEdit", {
            "file_path": str(target),
            "edits": [{"old_string": "a", "new_string": "line\n@/x"}]})
        rig.refused("Write", {"file_path": str(
            rig.home / "CLAUDE.local.md"), "content": " @ spaced import"})
        # rules folder under the home
        rules = rig.home / "rules" / "r.md"
        rules.parent.mkdir(parents=True)
        rig.refused("Write", {"file_path": str(rules),
                              "content": "@/etc/passwd"})

    def test_r5_plain_memory_writes_still_allowed(self, rig):
        target = rig.home / "CLAUDE.md"
        rig.allowed("Write", {"file_path": str(target),
                              "content": "ordinary memory, no imports"})
        rig.allowed("Write", {"file_path": str(rig.home / "notes.md"),
                              "content": "contact me @work on slack"})
        # an @ that is not at line start is not an import line
        rig.allowed("Edit", {"file_path": str(target), "old_string": "x",
                             "new_string": "mention @user mid-line"})

    # --- BCU M14: one teammate writing into another teammate's home ---

    def test_bcu_m14_write_into_other_teammate_home_refused(self, rig):
        # rig.other is a sibling teammate home under the same root
        rig.refused("Write", {"file_path": str(rig.other / "poison"),
                              "content": "x"})
        rig.refused("Write", {"file_path": str(
            rig.other / "tool-limits.json"), "content": "x"})
        rig.refused("Edit", {"file_path": str(rig.other / "CLAUDE.md"),
                             "old_string": "a", "new_string": "b"})
