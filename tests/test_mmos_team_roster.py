"""Lane T7 team-roster tool: spec, settings-merge and refusal tests.

Pure unit tests — no server is started or contacted. They exercise
``tools/mmos_team_server/team_roster.py`` against throwaway directories.
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "team_roster.py"

spec_loader = importlib.util.spec_from_file_location("team_roster", TOOL)
team_roster = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(team_roster)


def make_spec(tmp_path, root=None, home=None, port=3780):
    root = root or str(tmp_path / "t3-team")
    home = home or os.path.join(root, "home")
    return {
        "server": {"root": root, "home": home,
                   "t3_bin": "/bin/echo", "port": port,
                   "provider_source_instance": "capacity_fabric"},
        "project": {"title": "Team",
                    "workspace_root": os.path.join(root, "team-project")},
        "model": "glm-5.3",
        "deny_write_roots": ["/tmp"],
        "teammates": [
            {"name": "A", "slug": "a", "role": "qa", "role_line": "quality",
             "accent_color": "#e0b64d", "instance": "a",
             "charter": "# A charter\n"},
            {"name": "B", "slug": "b", "role": "designer",
             "role_line": "design", "accent_color": "#3fb6a8", "instance": "b",
             "charter": "# B charter\n"},
        ],
    }


def load(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return team_roster.load_spec(str(path))


def fake_home(tmp_path, extra_instances=None, top_unknown=True):
    home = tmp_path / "t3-team" / "home"
    (home / "userdata").mkdir(parents=True)
    settings = {
        "providerInstances": {
            "capacity_fabric": {
                "driver": "claudeAgent", "displayName": "Capacity Fabric",
                "enabled": True, "environment": ["SHOULD_NOT_BE_COPIED"],
                "config": {"homePath": "/old", "customModels":
                           [{"slug": "glm-5.3", "name": "GLM 5.3"}]},
            },
            "someone_else": {"driver": "claudeAgent", "displayName": "Other"},
        },
    }
    if extra_instances:
        settings["providerInstances"].update(extra_instances)
    if top_unknown:
        settings["aFutureUnknownKey"] = {"keep": ["me"]}
    path = home / "userdata" / "settings.json"
    path.write_text(json.dumps(settings, indent=2))
    path.chmod(0o600)
    return home, path


class TestSpecValidation:
    def test_valid_spec_loads(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        assert spec["model"] == "glm-5.3"

    def test_missing_key_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        del spec["project"]
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    @pytest.mark.parametrize("port", [3773, 3774])
    def test_reserved_ports_refused(self, tmp_path, port):
        with pytest.raises(SystemExit):
            load(tmp_path, make_spec(tmp_path, port=port))

    def test_root_at_dot_t3_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            load(tmp_path,
                 make_spec(tmp_path, root=os.path.expanduser("~/.t3")))

    def test_root_inside_dot_t3_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            load(tmp_path,
                 make_spec(tmp_path,
                           root=os.path.expanduser("~/.t3/anything")))

    def test_root_symlink_into_dot_t3_refused(self, tmp_path):
        link = tmp_path / "link-to-t3"
        os.symlink(os.path.expanduser("~/.t3"), link)
        with pytest.raises(SystemExit):
            load(tmp_path, make_spec(tmp_path, root=str(link)))

    def test_duplicate_name_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][1]["name"] = "A"
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_duplicate_accent_color_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][1]["accent_color"] = \
            spec["teammates"][0]["accent_color"].upper()
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_empty_teammates_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"] = []
        with pytest.raises(SystemExit):
            load(tmp_path, spec)


class TestSettingsMerge:
    def test_merge_adds_instances_and_keeps_neighbours(self, tmp_path):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        changed = team_roster.ensure_instances(spec)
        assert changed == ["a", "b"]
        settings = json.loads(path.read_text())
        assert "someone_else" in settings["providerInstances"]
        assert settings["aFutureUnknownKey"] == {"keep": ["me"]}
        assert settings["providerInstances"]["a"]["displayName"] == "A"
        assert settings["providerInstances"]["a"]["accentColor"] == "#e0b64d"
        assert settings["providerInstances"]["a"]["config"]["customModels"] == \
            [{"slug": "glm-5.3", "name": "GLM 5.3"}]
        # the source instance's environment values are never copied
        assert settings["providerInstances"]["a"]["environment"] == []

    def test_merge_is_idempotent(self, tmp_path):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        team_roster.ensure_instances(spec)
        first = path.read_text()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        changed = team_roster.ensure_instances(spec)
        assert changed == []
        assert path.read_text() == first

    def test_merge_updates_stale_teammate_instance(self, tmp_path):
        home, path = fake_home(tmp_path, extra_instances={
            "a": {"driver": "claudeAgent", "displayName": "Old Name"}})
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        changed = team_roster.ensure_instances(spec)
        assert changed == ["a", "b"]  # a was stale, b was new
        settings = json.loads(path.read_text())
        assert settings["providerInstances"]["a"]["displayName"] == "A"


class TestToolLimits:
    def test_home_allowed_workspace_denied(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        limits = team_roster.tool_limits(spec, mate)
        home = team_roster.teammate_home(spec, mate)
        workspace = team_roster.expand(spec["project"]["workspace_root"])
        joined = " ".join(limits["permissions"]["allow"] +
                          limits["permissions"]["deny"])
        assert f"Write(/{home}/**)" in limits["permissions"]["allow"]
        assert f"Write(/{workspace}/**)" in limits["permissions"]["deny"]
        assert "Bash" in limits["permissions"]["deny"]
        # deny_write_roots are kept through the rule-layer cut (realpath
        # spelling; /tmp resolves to /private/tmp on macOS)
        assert f"Write(/{os.path.realpath('/tmp')}/**)" in joined


class TestToolLimitsCredentials:
    """Review R2a finding 1: a teammate cannot read credentials or other
    teammates' homes, and cannot rewrite its own limits or charter."""

    def test_server_private_and_other_homes_unreadable(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate, other = spec["teammates"][0], spec["teammates"][1]
        root = team_roster.expand(spec["server"]["root"])
        os.makedirs(os.path.join(root, "run"), exist_ok=True)
        os.makedirs(team_roster.teammate_home(spec, other), exist_ok=True)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert f"Read(/{root}/run/**)" in deny
        assert f"Read(/{team_roster.teammate_home(spec, other)}/**)" in deny
        home = team_roster.teammate_home(spec, mate)
        assert not any(d.startswith(f"Read(/{home}/**") for d in deny)
        assert f"Read(/{home}/cutover-preimage.json)" in deny

    def test_own_limits_and_charter_not_writable(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("tool-limits.json", "CHARTER.md", "carrier.json",
                     "cutover-preimage.json",
                     ".claude.json.backup", "CLAUDE.md.backup"):
            assert f"Write(/{home}/{name})" in deny
            assert f"Edit(/{home}/{name})" in deny
        # plain CLAUDE.md (memory) stays writable; CLAUDE.md.backup does
        # not make plain CLAUDE.md denied (exact forms, not substrings)
        assert f"Write(/{home}/CLAUDE.md)" not in deny
        assert f"Edit(/{home}/CLAUDE.md)" not in deny

    def test_own_claude_configuration_not_writable(self, tmp_path):
        """The home is the teammate's Claude configuration folder: a settings
        file, an MCP entry, a skill or a plugin written there would run."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("settings.json", "settings.local.json", ".claude.json",
                     ".mcp.json", "plugins", "skills", "agents", "commands",
                     "hooks", "rules", ".claude"):
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{home}/{name})" in deny
                assert f"{tool}(/{home}/{name}/**)" in deny
        assert f"Write(/{home}/CLAUDE.md)" not in deny
        assert f"Edit(/{home}/CLAUDE.md)" not in deny
        allow = team_roster.tool_limits(spec, mate)["permissions"]["allow"]
        assert f"Write(/{home}/**)" in allow

    def test_spec_roots_and_siblings(self, tmp_path):
        raw = make_spec(tmp_path)
        secret_dir = tmp_path / "elsewhere" / "secrets"
        secret_dir.mkdir(parents=True)
        raw["deny_read_roots"] = [str(secret_dir)]
        raw["deny_read_root_siblings"] = True  # inert since the cut
        spec = load(tmp_path, raw)
        root = team_roster.expand(spec["server"]["root"])
        os.makedirs(root, exist_ok=True)
        sibling = os.path.join(os.path.dirname(root), "sibling-proofs")
        os.makedirs(sibling, exist_ok=True)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert f"Read(/{secret_dir}/**)" in deny
        # rule-layer cut (repair round 2): siblings of the server root are
        # no longer enumerated as deny rules — the gate refuses every read
        # outside the roots at call time, including folders created after
        # apply; the snapshot layer keeps only named paths
        assert not any(sibling in d for d in deny)
        assert not any(d.startswith(f"Read(/{root}/**") for d in deny)


def freeze_listings(monkeypatch):
    """Snapshot each directory listing once: the equality and idempotence
    tests compare two enumerations of the LIVE filesystem, and the rooted
    fence walks the home chain all the way to /, so a world-writable
    parent like /tmp churns underneath them — a file appearing between
    the two calls would change the deny rules spuriously."""
    real = os.listdir
    cache = {}
    def frozen(path):
        key = os.path.realpath(path)
        if key not in cache:
            cache[key] = list(real(path))
        return cache[key]
    monkeypatch.setattr(team_roster.os, "listdir", frozen)


class TestToolLimitsNewKeys:
    """Part B Q2/Q3: allow_read_roots and home_write_allow compile to deny
    rules; a spec WITHOUT the keys must generate exactly the default rules
    (the server-infrastructure write denies below are always on — whoever
    can write the team server's own folders chooses which program it runs
    at its next start, and the limits, not the installer, must prevent
    that)."""

    @staticmethod
    def today_rules(spec, mate):
        """The default generation, reconstructed from the module's own
        tuples so the absent-key test fails if the output changes in any
        way. Since the rule-layer cut (repair round 2) the reconstruction
        is the whole story: the census bare denies plus the named
        write/read surfaces — no sibling enumerations remain."""
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        home = os.path.realpath(team_roster.teammate_home(spec, mate))
        deny_roots = [os.path.realpath(
            team_roster.expand(spec["project"]["workspace_root"]))]
        deny_roots += [os.path.realpath(r)
                       for r in spec.get("deny_write_roots", [])]
        deny_roots += [a for r in deny_roots
                       for a in team_roster.firmlink_aliases(r)]
        deny = list(team_roster.TOOL_DENY_CENSUS)
        for r in deny_roots:
            deny += [f"Write(/{r})", f"Write(/{r}/**)",
                     f"Edit(/{r})", f"Edit(/{r}/**)"]
        for name in team_roster.HOME_LOCKED:
            locked = os.path.join(home, name)
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{locked})", f"{tool}(/{locked}/**)"]
        for name in team_roster.HOME_CONFIG:
            config = os.path.join(home, name)
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{config})", f"{tool}(/{config}/**)"]
        # other teammates' homes deny writes too (repair round 1, P1/P6)
        for path in team_roster.other_home_paths(spec, mate):
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{path})", f"{tool}(/{path}/**)"]
        for name in team_roster.SERVER_INFRASTRUCTURE:
            infra = os.path.join(root, name)
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{infra})", f"{tool}(/{infra}/**)"]
        t3_dir = os.path.dirname(os.path.realpath(
            team_roster.expand(spec["server"]["t3_bin"])))
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{t3_dir})", f"{tool}(/{t3_dir}/**)"]
        # user-level protected names, absent or not (repair round 1, P3)
        for path in team_roster._user_protected_paths(spec):
            base = path[:-1] if path.endswith("*") else path
            for tool in ("Write", "Edit"):
                if path.endswith("*"):
                    deny += [f"{tool}(/{base}*)", f"{tool}(/{base}*/**)"]
                else:
                    deny += [f"{tool}(/{base})", f"{tool}(/{base}/**)"]
        for path in team_roster.deny_read_paths(spec, mate):
            deny += team_roster._read_deny(path)
        # same first-occurrence dedupe as tool_limits
        seen = set()
        deny = [d for d in deny if not (d in seen or seen.add(d))]
        allow = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
                 "ToolSearch", f"Write(/{home}/**)", f"Edit(/{home}/**)"]
        return {"permissions": {"allow": allow, "deny": deny}}

    def test_infrastructure_folders_never_writable(self, tmp_path):
        """Server-root bin/, config/, runtime/ and run/ are denied for
        Write and Edit even in a spec with none of the new keys: whoever
        can write them chooses which program the server runs next start."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        root = team_roster.expand(spec["server"]["root"])
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in team_roster.SERVER_INFRASTRUCTURE:
            infra = os.path.join(root, name)
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{infra})" in deny, name
                assert f"{tool}(/{infra}/**)" in deny, name

    def test_locked_names_have_binding_tree_denies(self, tmp_path):
        """Every HOME_LOCKED name must carry a Write/Edit tree member
        (/**): an exact-path Write deny alone never binds (live-proved
        2026-11-11, evidence 10 D3), and these files are the teammate's
        own limits and charter — the one overwrite that binds at the next
        process restart, with no rooted keys needed to mask it."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in team_roster.HOME_LOCKED:
            locked = os.path.join(home, name)
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{locked})" in deny, name
                assert f"{tool}(/{locked}/**)" in deny, name

    @staticmethod
    def freeze_listings(monkeypatch):
        # resolves to the module-level helper (class scope is not in a
        # function body's lookup chain)
        freeze_listings(monkeypatch)

    def test_absent_keys_give_exactly_today_rules(self, tmp_path,
                                                  monkeypatch):
        self.freeze_listings(monkeypatch)
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        os.makedirs(team_roster.teammate_home(spec, spec["teammates"][1]))
        assert team_roster.tool_limits(spec, mate)["permissions"] == \
            self.today_rules(spec, mate)["permissions"]

    def test_absent_keys_despite_empty_values(self, tmp_path, monkeypatch):
        """Empty lists are not the new regime either: only present-and-set
        keys turn the rooted rules on, so [] must equal absent."""
        self.freeze_listings(monkeypatch)
        raw = make_spec(tmp_path)
        raw["allow_read_roots"] = []
        raw["home_write_allow"] = []
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        os.makedirs(team_roster.teammate_home(spec, spec["teammates"][1]))
        assert team_roster.tool_limits(spec, mate)["permissions"] == \
            self.today_rules(spec, mate)["permissions"]

    def test_allow_read_roots_enforced_by_named_rules_and_gate(self,
                                                               tmp_path):
        """Rooted reads after the rule-layer cut (repair round 2): the rule
        layer keeps the named read denies and root-scoped allows; reads
        outside the roots are the GATE's call at run time (it refuses
        every read outside the roots, including folders created after
        apply — see the gate tests and the post-apply-folder test)."""
        extra_root = tmp_path / "elsewhere" / "ws2"
        extra_root.mkdir(parents=True)
        raw = make_spec(tmp_path)
        raw["allow_read_roots"] = [str(extra_root)]
        spec = load(tmp_path, raw)
        mate, other = spec["teammates"][0], spec["teammates"][1]
        os.makedirs(team_roster.teammate_home(spec, other))
        home = team_roster.teammate_home(spec, mate)
        sibling_dir = tmp_path / "elsewhere" / "unrelated-dir"
        sibling_dir.mkdir()
        limits = team_roster.tool_limits(spec, mate)
        allow, deny = (limits["permissions"]["allow"],
                       limits["permissions"]["deny"])
        # plain read tools replaced by rooted allows
        for bare in ("Read", "Glob", "Grep"):
            assert bare not in allow
        assert f"Read(/{extra_root}/**)" in allow
        assert f"Glob(/{extra_root}/**)" in allow
        assert f"Grep(/{extra_root}/**)" in allow
        assert f"Read(/{home}/**)" in allow  # own home stays readable
        # named read denies survive: other homes, server-private folders
        assert f"Read(/{team_roster.teammate_home(spec, other)}/**)" in deny
        root = team_roster.expand(spec["server"]["root"])
        assert f"Read(/{os.path.join(root, 'run')}/**)" in deny
        assert "Bash" in deny
        # nothing denies the allowed roots or the chain parents as trees
        chain_parent = os.path.dirname(str(extra_root))
        for tool in ("Read", "Glob", "Grep"):
            assert f"{tool}(/{chain_parent})" not in deny
            assert f"{tool}(/{chain_parent}/**)" not in deny
        for allowed in (str(extra_root), home):
            assert not any(d.startswith(f"Read(/{allowed}/**)")
                           for d in deny)
        # no enumeration: an unrelated sibling dir has NO rule deny — the
        # gate refuses it at call time instead (cut semantics)
        sibling = str(sibling_dir)
        assert not any(sibling in d for d in deny)

    def test_home_write_allow_denies_other_home_children(self, tmp_path):
        """Rooted writes: only CLAUDE.md and notes/ stay writable in the
        home; every other existing child plus all config names are denied."""
        raw = make_spec(tmp_path)
        raw["home_write_allow"] = ["CLAUDE.md", "notes/"]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        os.makedirs(os.path.join(home, "notes"), exist_ok=True)
        os.makedirs(os.path.join(home, "skills"), exist_ok=True)
        open(os.path.join(home, "stray.md"), "w").write("x")
        limits = team_roster.tool_limits(spec, mate)
        allow, deny = (limits["permissions"]["allow"],
                       limits["permissions"]["deny"])
        # home-wide write allow replaced by named allows
        assert f"Write(/{home}/**)" not in allow
        assert f"Edit(/{home}/**)" not in allow
        assert f"Write(/{home}/CLAUDE.md)" in allow
        assert f"Edit(/{home}/CLAUDE.md)" in allow
        assert f"Write(/{home}/notes/**)" in allow
        assert f"Edit(/{home}/notes/**)" in allow
        # allowed names never denied (exact forms; CLAUDE.md.backup being
        # denied must not deny plain CLAUDE.md)
        for tool in ("Write", "Edit"):
            assert f"{tool}(/{home}/CLAUDE.md)" not in deny
            assert f"{tool}(/{home}/CLAUDE.md/**)" not in deny
            assert f"{tool}(/{home}/notes)" not in deny
            assert not any(d.startswith(f"{tool}(/{home}/notes/")
                           for d in deny)
        # other existing children denied, config names denied regardless
        for tool in ("Write", "Edit"):
            assert f"{tool}(/{home}/stray.md)" in deny
            assert f"{tool}(/{home}/skills)" in deny
            assert f"{tool}(/{home}/skills/**)" in deny
            assert f"{tool}(/{home}/settings.json)" in deny
            assert f"{tool}(/{home}/.mcp.json)" in deny
            assert f"{tool}(/{home}/tool-limits.json)" in deny

    def test_assets_dir_refused(self, tmp_path, capsys):
        """Q4 verdict, live-proved 2026-11-11: a --settings file outside the
        teammate home loads, but its Read/Glob/Grep deny rules silently do
        not bind — the teammate then reads everything the spec denies. The
        key must be refused loudly, never silently ignored."""
        raw = make_spec(tmp_path)
        raw["assets_dir"] = str(tmp_path / "assets")
        with pytest.raises(SystemExit):
            load(tmp_path, raw)
        assert "assets_dir" in capsys.readouterr().err

    def test_session_processes_match_any_marker_path(self, tmp_path,
                                                     monkeypatch):
        """Process detection takes every identifying path: the spawn argv
        carries the workspace cwd, while the home is an env var — a single
        fixed marker under-reports running sessions (live-proved)."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        workspace = team_roster.expand(spec["project"]["workspace_root"])
        line = f" 4242   Tue Nov 10 19:34:11 2026 t3-claude --cwd {workspace}"

        class Proc:
            returncode = 0
            stdout = "  PID   LSTART  TIME COMMAND\n" + line + "\n"
            stderr = ""

        monkeypatch.setattr(team_roster.subprocess, "run",
                            lambda a, **k: Proc())
        found = team_roster.session_processes(workspace)
        assert found == [{"pid": 4242, "started": "Tue Nov 10 19:34:11 2026"}]
        # a path that appears in no command line matches nothing
        assert team_roster.session_processes(
            team_roster.teammate_home(spec, mate)) == []


class TestAtomicWrites:
    """Review R2a finding 11: the server watches settings.json and reloads it
    about 100 ms after a change, and a teammate process reads tool-limits.json
    and CHARTER.md when it starts. A write that truncates the destination in
    place can be read half-written. Every file another process reads while
    running must be swapped in with os.replace from a same-directory temporary
    that is 0600 from creation and fsynced first."""

    def replace_probe(self, monkeypatch, targets):
        """Capture the temp file's directory, mode and full text at the moment
        os.replace is called, for each destination in ``targets``."""
        seen = {t: [] for t in targets}
        real_replace = os.replace

        def replace(src, dst):
            for target in targets:
                if os.path.abspath(dst) == os.path.abspath(target):
                    st = os.stat(src)
                    with open(src) as fh:
                        seen[target].append({
                            "same_dir": os.path.dirname(
                                os.path.abspath(src)) ==
                            os.path.dirname(os.path.abspath(target)),
                            "src_dir": os.path.dirname(
                                os.path.abspath(src)),
                            "mode": stat.S_IMODE(st.st_mode),
                            "text": fh.read()})
            return real_replace(src, dst)

        monkeypatch.setattr(team_roster.os, "replace", replace)
        return seen

    def test_settings_json_replaced_atomically(self, tmp_path, monkeypatch):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        seen = self.replace_probe(monkeypatch, [str(path)])
        team_roster.ensure_instances(spec)
        assert seen[str(path)], "settings.json was not written via os.replace"
        probe = seen[str(path)][0]
        assert probe["same_dir"], "temp file must live in the same directory"
        assert probe["mode"] == 0o600, "temp must be 0600 from creation"
        assert json.loads(probe["text"]), "replaced file must be complete"
        # nothing half-visible: the destination is the temp, moved in one step
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_home_assets_replaced_atomically(self, tmp_path, monkeypatch):
        freeze_listings(monkeypatch)
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        team_roster.write_file_assets(spec, mate)  # first write
        mate["charter"] = "# changed charter\n"
        targets = [os.path.join(home, "CHARTER.md"),
                   os.path.join(home, "tool-limits.json")]
        seen = self.replace_probe(monkeypatch, targets)
        wrote = team_roster.write_file_assets(spec, mate)
        assert wrote == ["CHARTER.md"]
        charter = targets[0]
        assert seen[charter], "CHARTER.md was not written via os.replace"
        # attack round, finding 5: home assets stage under <root>/run
        # (Write-denied for teammates), never next to the destination
        # where a temp name matches no deny rule
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        staging = os.path.join(root, "run")
        assert not seen[charter][0]["same_dir"]
        assert seen[charter][0]["src_dir"] == staging
        assert seen[charter][0]["mode"] == 0o600
        # tool-limits.json was identical, so apply correctly wrote nothing;
        # a first creation (file missing) is atomic too
        assert seen[targets[1]] == []
        os.unlink(targets[1])
        seen2 = self.replace_probe(monkeypatch, [targets[1]])
        team_roster.write_file_assets(spec, mate)
        assert seen2[targets[1]]
        assert seen2[targets[1]][0]["mode"] == 0o600

    def test_state_and_urls_files_replaced_atomically(
            self, tmp_path, monkeypatch):
        spec = load(tmp_path, make_spec(tmp_path))
        root = team_roster.expand(spec["server"]["root"])
        home = team_roster.expand(spec["server"]["home"])
        os.makedirs(os.path.join(home, "userdata"), exist_ok=True)
        open(os.path.join(home, "userdata", "environment-id"),
             "w").write("env-1")
        state_path = os.path.join(root, "run", "team_roster_state.json")
        urls_path = os.path.join(root, "run", "team_urls.json")
        spec["state_file"] = state_path
        spec["urls_file"] = urls_path
        seen = self.replace_probe(monkeypatch, [state_path, urls_path])
        team_roster.save_state(spec, {"teammates": {}}, state_path)
        threads = {m["name"]: {"threadId": f"t-{m['slug']}", "title": "x"}
                   for m in spec["teammates"]}
        team_roster.write_urls_file(spec, threads)
        for target in (state_path, urls_path):
            assert seen[target], f"{target} was not written via os.replace"
            assert seen[target][0]["same_dir"]
            assert seen[target][0]["mode"] == 0o600
            assert json.loads(seen[target][0]["text"])

    def test_temp_is_fsynced_before_replace(self, tmp_path, monkeypatch):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        fsynced = []
        real_fsync = os.fsync

        def fsync(fd):
            fsynced.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr(team_roster.os, "fsync", fsync)
        monkeypatch.setattr(team_roster.os, "replace",
                            lambda s, d: fsynced.append("replace"))
        team_roster.ensure_instances(spec)
        assert "replace" in fsynced, "os.replace ran without a prior fsync"
        assert any(isinstance(f, int) for f in fsynced)

    def test_no_temp_files_left_behind(self, tmp_path):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        team_roster.ensure_instances(spec)
        leftovers = [p.name for p in Path(path).parent.iterdir()
                     if ".tmp" in p.name]
        assert leftovers == []
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        leftovers = [p.name for p in Path(
            team_roster.teammate_home(spec, mate)).iterdir()
            if ".tmp" in p.name]
        assert leftovers == []

    def test_failed_write_leaves_destination_untouched(
            self, tmp_path, monkeypatch):
        home, path = fake_home(tmp_path)
        spec = load(tmp_path, make_spec(tmp_path, home=str(home)))
        team_roster.ensure_instances(spec)
        before = path.read_text()

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(team_roster.os, "replace", boom)
        spec["teammates"][0]["accent_color"] = "#123456"
        with pytest.raises(OSError):
            team_roster.ensure_instances(spec)
        assert path.read_text() == before
        leftovers = [p.name for p in Path(path).parent.iterdir()
                     if ".tmp" in p.name]
        assert leftovers == [], "a failed write must clean up its temp file"


class FakeT3Launch:
    """Records every thread launch; never runs a process."""

    def __init__(self):
        self.calls = []

    def __call__(self, spec, args, stdin_text=None, timeout=900):
        self.calls.append(list(args))

        class Proc:
            returncode = 0
            stdout = json.dumps({"threadId": f"mcp:new-{len(self.calls)}"}) + "\n"
            stderr = ""
        return Proc()


@pytest.fixture
def fake_t3(monkeypatch):
    fake = FakeT3Launch()
    monkeypatch.setattr(team_roster, "t3", fake)
    return fake


PROJECT = "project-1"


THREADS_DDL = """
CREATE TABLE orchestration_v2_projection_threads (
  thread_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  default_provider TEXT NOT NULL,
  runtime_mode TEXT NOT NULL,
  interaction_mode TEXT NOT NULL,
  active_provider_thread_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived_at TEXT,
  deleted_at TEXT,
  payload_json TEXT NOT NULL,
  provider_instance_id TEXT
)
"""


def make_db(spec, threads=()):
    import sqlite3
    path = team_roster.db_path(spec)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(THREADS_DDL)
    for t in threads:
        payload = {"id": t["threadId"], "projectId": PROJECT,
                   "title": t["title"], "providerInstanceId": t.get("instance")}
        conn.execute(
            "INSERT INTO orchestration_v2_projection_threads "
            "(thread_id, project_id, title, default_provider, runtime_mode, "
            "interaction_mode, created_at, updated_at, payload_json, "
            "provider_instance_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (t["threadId"], PROJECT, t["title"], "claudeAgent", "full-access",
             "default", "2026-11-10T00:00:00Z", "2026-11-10T00:00:00Z",
             json.dumps(payload), t.get("instance")))
    conn.commit()
    conn.close()
    return path


class TestPaperclipBinding:
    """Review R2a finding 12, roster side: the carrier sends each task to the
    thread id recorded on the agent in Paperclip; the roster tool kept its own
    state and never read that field, so a lost state file could create a
    second primary thread. With a binding source configured, apply does one
    GET per agent and refuses to create or adopt a thread the binding
    contradicts. Without a source, behaviour is unchanged."""

    def with_binding(self, tmp_path, **extra):
        raw = make_spec(tmp_path)
        raw["paperclip_base"] = "http://127.0.0.1:3100"
        for mate in raw["teammates"]:
            mate["paperclip_agent_id"] = f"agent-{mate['slug']}"
        raw.update(extra)
        return load(tmp_path, raw)

    @pytest.mark.parametrize("bad", [
        "http://10.0.0.5:3100",                       # not loopback
        "https://127.0.0.1:3100",                     # not http
        "http://127.0.0.1:3100@example.com/",         # userinfo smuggles a host
        "http://127.0.0.1.example.com:3100/",         # host is a subdomain
        "http://[::1]:3100@evil.example/",            # bracketed userinfo
        "ftp://127.0.0.1:3100",
        "not a url",
    ])
    def test_non_loopback_base_refused(self, tmp_path, bad):
        raw = make_spec(tmp_path)
        raw["paperclip_base"] = bad
        with pytest.raises(SystemExit):
            load(tmp_path, raw)

    @pytest.mark.parametrize("good", ["http://127.0.0.1:3100",
                                      "http://localhost:3100",
                                      "http://127.0.0.1:3100/"])
    def test_loopback_base_accepted(self, tmp_path, good):
        raw = make_spec(tmp_path)
        raw["paperclip_base"] = good
        spec = load(tmp_path, raw)
        assert spec["paperclip_base"] == good

    def test_one_get_per_agent_and_thread_id_read(self, tmp_path):
        import io
        import urllib.error

        spec = self.with_binding(tmp_path)
        mate = spec["teammates"][0]

        class Opener:
            def __init__(self, payload):
                self.payload = payload
                self.calls = []

            def open(self, req, timeout=None):
                self.calls.append(req.full_url)
                return io.BytesIO(json.dumps(self.payload).encode())

        bound = {"metadata": {"teammate": {"t3": {"primaryThreadId": "mcp:x"}}}}
        opener = Opener(bound)
        assert team_roster.paperclip_binding(
            spec, mate, opener=opener) == "mcp:x"
        assert opener.calls == ["http://127.0.0.1:3100/api/agents/agent-a"]
        unbound = Opener({"metadata": {}})
        assert team_roster.paperclip_binding(
            spec, mate, opener=unbound) is None
        assert len(unbound.calls) == 1

        class Boom:
            def open(self, req, timeout=None):
                raise urllib.error.URLError("connection refused")

        with pytest.raises(SystemExit):
            team_roster.paperclip_binding(spec, mate, opener=Boom())

    def test_no_get_without_a_full_source(self, tmp_path):
        import io

        class Opener:
            calls = []

            def open(self, req, timeout=None):
                Opener.calls.append(req.full_url)
                return io.BytesIO(b"{}")

        # agent ids but no base (the real spec today): no request, no refusal
        raw = make_spec(tmp_path)
        for mate in raw["teammates"]:
            mate["paperclip_agent_id"] = f"agent-{mate['slug']}"
        spec = load(tmp_path, raw)
        assert team_roster.paperclip_binding(
            spec, spec["teammates"][0], opener=Opener()) is None
        # base but no agent id for the teammate: also no request
        raw = make_spec(tmp_path)
        raw["paperclip_base"] = "http://127.0.0.1:3100"
        spec = load(tmp_path, raw)
        assert team_roster.paperclip_binding(
            spec, spec["teammates"][0], opener=Opener()) is None
        assert Opener.calls == []

    def test_matching_binding_adopts_thread_and_creates_none(
            self, tmp_path, fake_t3, monkeypatch):
        spec = self.with_binding(tmp_path)
        monkeypatch.setattr(team_roster, "paperclip_binding",
                            lambda s, m: "t1" if m["name"] == "A" else None)
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"}])
        threads, _ = team_roster.ensure_threads(spec, PROJECT)
        assert threads["A"]["threadId"] == "t1"
        assert threads["A"]["created"] is False
        # B has no binding and no live thread: unchanged behaviour, it creates
        assert len(fake_t3.calls) == 1
        assert fake_t3.calls[0][fake_t3.calls[0].index("--provider") + 1] == "b"

    def test_bound_thread_unknown_refuses_before_creating(
            self, tmp_path, fake_t3, monkeypatch, capsys):
        spec = self.with_binding(tmp_path)
        make_db(spec, [])  # nothing live: apply would create
        monkeypatch.setattr(team_roster, "paperclip_binding",
                            lambda s, m: "mcp:bound-elsewhere")
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == [], \
            "no thread may be created while the binding is unknown"
        out = capsys.readouterr().err
        assert "mcp:bound-elsewhere" in out
        assert "state" in out  # the message says what to do

    def test_bound_to_different_thread_than_roster_refuses(
            self, tmp_path, fake_t3, monkeypatch):
        spec = self.with_binding(tmp_path)
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"}])
        monkeypatch.setattr(team_roster, "paperclip_binding",
                            lambda s, m: "mcp:other" if m["name"] == "A"
                            else None)
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == []

    def test_binding_checked_before_any_thread_is_created(
            self, tmp_path, fake_t3, monkeypatch):
        """A refuses (unknown binding) and B would create: no thread at all
        may be created by that apply."""
        spec = self.with_binding(tmp_path)
        make_db(spec, [])
        monkeypatch.setattr(
            team_roster, "paperclip_binding",
            lambda s, m: "mcp:unknown" if m["name"] == "A" else None)
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == []


class TestLimitsPendingRestart:
    """A teammate session is one long-lived process that reads
    tool-limits.json and CHARTER.md only when it starts. When apply changes
    either file, the report must say so per teammate and print one plain
    line that the new limits are not in force until that session process
    restarts (principal, 2026-11-11)."""

    def fake_apply(self, tmp_path, monkeypatch, wrote_by_name,
                   sessions_by_home=None):
        spec = load(tmp_path, make_spec(tmp_path))
        homes = {m["name"]: team_roster.teammate_home(spec, m)
                 for m in spec["teammates"]}
        monkeypatch.setattr(team_roster, "ensure_project", lambda s: "proj-1")
        monkeypatch.setattr(
            team_roster, "write_file_assets",
            lambda s, m: wrote_by_name.get(m["name"], []))
        monkeypatch.setattr(team_roster, "ensure_instances",
                            lambda s, disable=(): [])
        monkeypatch.setattr(team_roster, "acquire_apply_lock",
                            lambda s: None)
        monkeypatch.setattr(team_roster, "ensure_gate",
                            lambda s: "0" * 64)
        threads = {m["name"]: {"threadId": f"t-{m['slug']}", "title": "x",
                               "created": False} for m in spec["teammates"]}
        monkeypatch.setattr(team_roster, "ensure_threads",
                            lambda s, p: (threads, "/tmp/state.json"))
        monkeypatch.setattr(team_roster, "rename_threads",
                            lambda s, t: ({n: False for n in t}, []))
        monkeypatch.setattr(team_roster, "write_urls_file",
                            lambda s, t: "/tmp/urls.json")
        if sessions_by_home is not None:
            if callable(sessions_by_home):
                monkeypatch.setattr(team_roster, "session_processes",
                                    sessions_by_home)
            else:
                monkeypatch.setattr(
                    team_roster, "session_processes",
                    lambda *paths: sessions_by_home.get(paths[0], []))
        return team_roster.cmd_apply(spec)

    def test_changed_limits_reported_with_plain_line(self, tmp_path,
                                                     monkeypatch, capsys):
        code = self.fake_apply(tmp_path, monkeypatch,
                               {"A": ["tool-limits.json"]},
                               sessions_by_home={})
        assert code == 0
        out = capsys.readouterr().out
        report = json.loads(out[out.index("{"):])
        by_name = {r["name"]: r for r in report["teammates"]}
        assert by_name["A"]["limitsPendingRestart"] == ["tool-limits.json"]
        assert by_name["B"]["limitsPendingRestart"] == []
        assert "not in force" in out.lower()

    def test_line_names_the_running_session_pid(self, tmp_path, monkeypatch,
                                                capsys):
        def sessions(*paths):
            if paths[0].endswith("/a"):
                return [{"pid": 4242, "started": "Tue Nov 10 19:34:11 2026"}]
            return []

        self.fake_apply(tmp_path, monkeypatch,
                        {"A": ["tool-limits.json", "CHARTER.md"],
                         "B": ["CHARTER.md"]},
                        sessions_by_home=sessions)
        out = capsys.readouterr().out
        a_lines = [l for l in out.splitlines() if l.startswith("[team_roster] A:")]
        assert any("4242" in l and "restart" in l for l in a_lines), out
        assert any("[team_roster] B:" in l and "none is running" in l
                   for l in out.splitlines()), out

    def test_workspace_sessions_reported_without_attribution(
            self, tmp_path, monkeypatch, capsys):
        """The spawn argv carries only the workspace cwd (live-proved), so a
        running session may be unattributable: the report must say sessions
        exist and a restart is needed, never 'none is running'."""
        def sessions(*paths):
            if "team-project" in paths[0]:
                return [{"pid": 99, "started": "Tue Nov 10 19:34:11 2026"}]
            return []

        self.fake_apply(tmp_path, monkeypatch,
                        {"A": ["tool-limits.json"]},
                        sessions_by_home=sessions)
        out = capsys.readouterr().out
        assert any("cannot be attributed" in l and "assume a restart" in l
                   for l in out.splitlines()), out
        assert "none is running" not in out

    def test_no_change_no_pending_line(self, tmp_path, monkeypatch, capsys):
        self.fake_apply(tmp_path, monkeypatch, {})
        out = capsys.readouterr().out
        assert "not in force" not in out.lower()
        report = json.loads(out[out.index("{"):])
        assert all(r["limitsPendingRestart"] == []
                   for r in report["teammates"])


class TestSessionProcesses:
    PS_SAMPLE = """  PID   LSTART  TIME COMMAND
    1   Tue Nov 10 09:00:00 2026 /sbin/launchd
 4242   Tue Nov 10 19:34:11 2026 claude --resume=abc --settings {home}/tool-limits.json
 4243   Tue Nov 10 20:01:02 2026 claude --resume=def --settings {other}/tool-limits.json
"""

    def test_returns_pid_and_start_only(self, tmp_path, monkeypatch):
        home = str(tmp_path / "t3-team" / "teammates" / "a")
        other = str(tmp_path / "t3-team" / "teammates" / "b")

        class Proc:
            returncode = 0
            stdout = self.PS_SAMPLE.format(home=home, other=other)
            stderr = ""

        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return Proc()

        monkeypatch.setattr(team_roster.subprocess, "run", run)
        found = team_roster.session_processes(home)
        assert calls == [["ps", "-axo", "pid,lstart,command"]]
        assert found == [{"pid": 4242, "started": "Tue Nov 10 19:34:11 2026"}]

    def test_never_returns_or_prints_command_text(self, tmp_path, monkeypatch,
                                                  capsys):
        home = str(tmp_path / "t3-team" / "teammates" / "a")

        class Proc:
            returncode = 0
            stdout = self.PS_SAMPLE.format(home=home, other="/x")
            stderr = ""

        monkeypatch.setattr(team_roster.subprocess, "run",
                            lambda a, **k: Proc())
        found = team_roster.session_processes(home)
        blob = json.dumps(found) + capsys.readouterr().out + \
            capsys.readouterr().err
        assert "resume=abc" not in blob
        assert "--settings" not in blob

    def test_own_pid_excluded_and_ps_failure_is_empty(self, tmp_path,
                                                      monkeypatch):
        home = str(tmp_path / "t3-team" / "teammates" / "a")
        mine = f"{os.getpid()}   Tue Nov 10 19:34:11 2026 grep {home}"

        class Proc:
            returncode = 0
            stdout = "  PID   LSTART  TIME COMMAND\n" + mine + "\n"
            stderr = ""

        monkeypatch.setattr(team_roster.subprocess, "run",
                            lambda a, **k: Proc())
        assert team_roster.session_processes(home) == []

        class Bad:
            returncode = 1
            stdout = ""
            stderr = "ps: error"

        monkeypatch.setattr(team_roster.subprocess, "run",
                            lambda a, **k: Bad())
        assert team_roster.session_processes(home) == []


class TestFileAssets:
    def test_write_and_rewrite_home(self, tmp_path, monkeypatch):
        freeze_listings(monkeypatch)
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        wrote = team_roster.write_file_assets(spec, mate)
        assert set(wrote) == {"CLAUDE.md", "CHARTER.md", "tool-limits.json"}
        home = team_roster.teammate_home(spec, mate)
        assert stat.S_IMODE(os.stat(home).st_mode) == 0o700
        assert stat.S_IMODE(
            os.stat(os.path.join(home, "CHARTER.md")).st_mode) == 0o600
        assert team_roster.write_file_assets(spec, mate) == []
        mate["charter"] = "# changed\n"
        assert team_roster.write_file_assets(spec, mate) == ["CHARTER.md"]

    def test_memory_file_never_rewritten_by_apply(self, tmp_path):
        # CLAUDE.md is the teammate's live long-term memory: once it exists,
        # apply must leave it alone even though it differs from the seed.
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        memory = os.path.join(team_roster.teammate_home(spec, mate), "CLAUDE.md")
        remembered = open(memory).read() + "- check-in word: MARLIN-77\n"
        open(memory, "w").write(remembered)
        wrote = team_roster.write_file_assets(spec, mate)
        assert "CLAUDE.md" not in wrote
        assert open(memory).read() == remembered


class TestAttackRoundFixes:
    """Fixes from the attack round (deepseek-v4.1-flash, effort max,
    frozen commit caf98855e; evidence 11-*). Each test names the finding
    it pins."""

    def _spec_with_layout(self, tmp_path):
        raw = make_spec(tmp_path)
        root = raw["server"]["root"]
        os.makedirs(os.path.join(root, "home", "userdata"), exist_ok=True)
        open(os.path.join(root, "fabric.env"), "w").write("x")
        os.makedirs(os.path.join(root, "teammates", "b"), exist_ok=True)
        open(os.path.join(str(tmp_path), "zshenv"), "w").write("x")
        return load(tmp_path, raw), raw

    def test_write_fence_covers_server_and_user_surfaces(self, tmp_path):
        """Findings 1/2/4: with NO rooted keys, the always-on Write/Edit
        fence denies the server's own home (its settings.json is reloaded
        live by the running server), fabric.env, other teammates' homes
        (their limits bind at their next start), and user-home siblings —
        while the teammate's own home stays writable."""
        spec, raw = self._spec_with_layout(tmp_path)
        mate = spec["teammates"][0]
        root = os.path.realpath(raw["server"]["root"])
        home = os.path.realpath(team_roster.teammate_home(spec, mate))
        os.makedirs(home, exist_ok=True)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        denied_paths = [os.path.join(root, "home"),
                        os.path.join(root, "fabric.env"),
                        os.path.join(root, "teammates", "b")]
        # rule-layer cut: named surfaces keep their Write/Edit denies; a
        # mere chain sibling (tmp_path/zshenv below) has NO rule deny any
        # more — the gate refuses every write outside the home at call
        # time (gate tests), and the real ~/.zshenv stays covered by
        # USER_PROTECTED
        for path in denied_paths:
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{path})" in deny, (tool, path)
                assert f"{tool}(/{path}/**)" in deny, (tool, path)
        assert not any(os.path.join(str(tmp_path), "zshenv") in d
                       for d in deny)
        # the teammate's own home and its chain stay writable
        assert f"Write(/{home})" not in deny
        assert f"Write(/{home}/**)" not in deny

    def test_t3_bin_dir_not_writable(self, tmp_path):
        """Finding 3: the t3 CLI install dir gets an explicit always-on
        deny even when it sits nowhere near the home chain (apply/status
        execute the binary with the team home — a replacement is code
        execution with principal privileges)."""
        raw = make_spec(tmp_path)
        raw["server"]["t3_bin"] = str(tmp_path / "tools" / "t3")
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        tools_dir = os.path.realpath(str(tmp_path / "tools"))
        for tool in ("Write", "Edit"):
            assert f"{tool}(/{tools_dir})" in deny
            assert f"{tool}(/{tools_dir}/**)" in deny

    def test_atomic_write_stages_outside_writable_dirs(self, tmp_path,
                                                       monkeypatch):
        """Finding 5: a temp staged next to a teammate-writable destination
        sits at a name no deny rule covers; the staging dir (server run/)
        must hold it instead."""
        staging = tmp_path / "run"
        staging.mkdir()
        dest_dir = tmp_path / "home"
        dest_dir.mkdir()
        seen = {}
        real_replace = os.replace
        def replace(src, dst):
            seen["src"] = src
            return real_replace(src, dst)
        monkeypatch.setattr(team_roster.os, "replace", replace)
        team_roster.atomic_write(str(dest_dir / "f.txt"), "body", 0o600,
                                 staging_dir=str(staging))
        assert seen["src"].startswith(str(staging) + os.sep)
        assert not seen["src"].startswith(str(dest_dir) + os.sep)
        assert open(dest_dir / "f.txt").read() == "body"

    def test_write_file_assets_stages_in_run(self, tmp_path, monkeypatch):
        """Finding 5, apply path: write_file_assets passes the server run/
        dir as staging for every home write."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        calls = []
        real = team_roster.write_if_changed
        monkeypatch.setattr(
            team_roster, "write_if_changed",
            lambda path, text, mode, staging_dir=None:
                calls.append((path, staging_dir)) or
                real(path, text, mode, staging_dir=staging_dir))
        team_roster.write_file_assets(spec, mate)
        assert calls and all(c[1] for c in calls), calls
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        assert all(c[1] == os.path.join(root, "run") for c in calls), calls

    def test_existing_file_read_denies_have_tree_member(self, tmp_path):
        """Finding 6 + P4: _read_deny never relies on an exact-path rule
        alone — the Write/Edit exact form proved inert live (evidence 10
        D3), so no emitter may depend on an exact form binding — and every
        read deny covers Grep/Glob too (content and names)."""
        f = tmp_path / "secret.txt"
        f.write_text("x")
        assert team_roster._read_deny(str(f)) == \
            [f"Read(/{f})", f"Read(/{f}/**)",
             f"Glob(/{f})", f"Glob(/{f}/**)",
             f"Grep(/{f})", f"Grep(/{f}/**)"]

    def test_firmlink_alias_read_denies(self, tmp_path):
        """Finding 7: a /Users deny root also emits its firmlink twin
        (/System/Volumes/Data/...) — realpath does not canonicalize the
        firmlink, so both spellings need their own rule."""
        raw = make_spec(tmp_path)
        raw["deny_read_roots"] = ["/Users/nightguard/.ssh"]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        paths = team_roster.deny_read_paths(spec, mate)
        assert "/Users/nightguard/.ssh" in paths
        assert "/System/Volumes/Data/Users/nightguard/.ssh" in paths

    def test_write_deny_roots_realpath(self, tmp_path):
        """Finding 8: a symlinked deny_write_roots spelling compiles to the
        real path (the matcher resolves links, so a symlink spelling would
        never match)."""
        real = tmp_path / "realroot"
        real.mkdir()
        link = tmp_path / "linkroot"
        os.symlink(str(real), str(link))
        raw = make_spec(tmp_path)
        raw["deny_write_roots"] = [str(link)]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        # the real spelling is denied by the deny_write_roots mechanism
        # itself (the symlink spelling may also appear from the sibling
        # enumeration — harmless, and it cannot substitute for the real)
        assert f"Write(/{real})" in deny and f"Write(/{real}/**)" in deny

    def test_home_enumeration_fails_closed(self, tmp_path, monkeypatch):
        """Finding 9 (carried through the rule-layer cut): a listdir
        failure on an EXISTING home dies instead of silently emitting a
        weakened write fence; a home that does not exist is skipped
        (fresh installs). The sibling enumerations are gone; the home
        children enumeration in rooted_home_write_rules keeps the rule."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        home = team_roster.teammate_home(spec, mate)
        real_listdir = os.listdir
        def fake(p):
            if os.path.realpath(p) == os.path.realpath(home):
                raise PermissionError(13, "simulated denial")
            return real_listdir(p)
        monkeypatch.setattr(team_roster.os, "listdir", fake)
        with pytest.raises(SystemExit):
            team_roster.rooted_home_write_rules(spec, mate)
        monkeypatch.undo()
        # nonexistent home: skipped, no exception (fresh install)
        spec2 = load(tmp_path, make_spec(tmp_path, root=str(tmp_path / "fresh")))
        allow, deny = team_roster.rooted_home_write_rules(spec2, spec2["teammates"][0])
        assert allow == [] and isinstance(deny, list)

    def test_home_write_allow_rejects_config_and_traversal(self, tmp_path):
        """Finding 10: locked/config names, absolute paths, ~ and traversal
        spellings are refused at spec load — the 'never granted' promise
        must not depend on an unrelated deny loop still covering it."""
        for bad in ("settings.json", "tool-limits.json", "/abs/x", "~/x",
                    "../out", "a/../b", ""):
            raw = make_spec(tmp_path)
            raw["home_write_allow"] = [bad]
            with pytest.raises(SystemExit):
                load(tmp_path, raw)

    def test_symlinked_asset_refused(self, tmp_path):
        """Finding 11: write_if_changed refuses a symlinked destination —
        writing (and chmod) through a planted link sends bytes outside
        the fence."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        os.makedirs(home, exist_ok=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("do not touch\n")
        os.symlink(str(victim), os.path.join(home, "CHARTER.md"))
        with pytest.raises(SystemExit):
            team_roster.write_file_assets(spec, mate)
        assert victim.read_text() == "do not touch\n"

    def test_server_bin_runtime_unreadable(self, tmp_path):
        """Finding 12: the server root's bin/ and runtime/ (runner script,
        pinned server bundle) are read-denied like the other private
        entries."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        paths = team_roster.deny_read_paths(spec, mate)
        for name in ("bin", "runtime"):
            assert os.path.join(root, name) in paths, name


class TestRepairRound1:
    """The blind panel's 19 findings (P1–P19, commit 4f10f4345 vs trunk),
    each pinned by the test the score named. The gate-side companions live
    in tests/test_mmos_teammate_gate.py; these pin the GENERATOR (the
    second layer) and the apply/status machinery."""

    # ---- P1: one apply that adds a teammate fences it everywhere ----

    def test_add_teammate_apply_fences_new_home_same_apply(self, tmp_path,
                                                           monkeypatch):
        freeze_listings(monkeypatch)
        spec = load(tmp_path, make_spec(tmp_path))
        team_roster.write_file_assets(spec, spec["teammates"][0])
        # mate E joins the roster; its home dir does not exist yet
        raw = make_spec(tmp_path)
        raw["teammates"].append(
            {"name": "E", "slug": "e", "role": "extra", "role_line": "extra",
             "accent_color": "#aa33cc", "instance": "e",
             "charter": "# E charter\n"})
        spec2 = load(tmp_path, raw)
        for mate in spec2["teammates"]:
            team_roster.write_file_assets(spec2, mate)
        for mate in spec2["teammates"]:
            if mate["slug"] == "e":
                continue
            limits = json.load(open(os.path.join(
                team_roster.teammate_home(spec2, mate),
                "tool-limits.json")))
            e_home = team_roster.teammate_home(spec2, spec2["teammates"][2])
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{e_home})" in limits["permissions"]["deny"]
                assert f"{tool}(/{e_home}/**)" in \
                    limits["permissions"]["deny"]

    # ---- P2: a read root never becomes writable ----

    def test_read_root_never_becomes_writable(self, tmp_path):
        """Naming another teammate's home as a read root must not remove
        its write deny (the panel proved the old code did exactly
        that)."""
        raw = make_spec(tmp_path)
        b_home = os.path.join(raw["server"]["root"], "teammates", "b")
        raw["allow_read_roots"] = [b_home]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        b_real = os.path.realpath(b_home)
        for tool in ("Write", "Edit"):
            assert f"{tool}(/{b_real})" in deny
            assert f"{tool}(/{b_real}/**)" in deny
        # the gate side: the home is a read root AND still write-refused
        cfg = team_roster.gate_config(spec, mate)
        assert os.path.realpath(b_home) in cfg["read_roots"]

    # ---- P3: absent user-level autoload names are not creatable ----

    def test_absent_user_autoload_names_denied(self, tmp_path, monkeypatch):
        fake_user = tmp_path / "userhome"
        fake_user.mkdir()
        real_expanduser = os.path.expanduser

        def fake_expanduser(path):
            if path == "~":
                return str(fake_user)
            if path.startswith("~/"):
                return str(fake_user / path[2:])
            return real_expanduser(path)

        monkeypatch.setattr(team_roster.os.path, "expanduser",
                            fake_expanduser)
        assert not (fake_user / ".zshenv").exists()  # absent, like the attack
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in (".zshenv", ".zprofile", ".zshrc", ".bash_profile",
                     ".gitconfig", ".ssh", ".gnupg", "Library/LaunchAgents"):
            target = str(fake_user / name)
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{target})" in deny, name
                assert f"{tool}(/{target}/**)" in deny, name

    # ---- P4: deny_read_paths compiles for Grep/Glob too ----

    def test_deny_read_paths_emit_grep_glob_too(self, tmp_path):
        raw = make_spec(tmp_path)
        secret = tmp_path / "secret.d"
        secret.mkdir()
        raw["deny_read_roots"] = [str(secret)]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for tool in ("Read", "Glob", "Grep"):
            assert f"{tool}(/{secret})" in deny, tool
            assert f"{tool}(/{secret}/**)" in deny, tool

    # ---- P5: the production spec's read fence covers Containers and
    # ~/.claude.json, by rule or by rooting ----

    def test_production_spec_read_fence_covers_containers_and_claude_json(
            self, tmp_path):
        prod = json.loads((REPO / "tools" / "mmos_team_server" / "specs" /
                           "team_roster.json").read_text())
        prod["server"]["root"] = str(tmp_path / "prod-team")
        prod["server"]["home"] = str(tmp_path / "prod-home")
        spec = load(tmp_path, prod)
        mate = spec["teammates"][0]
        user = os.path.realpath(os.path.expanduser("~"))
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("Library/Containers", ".claude.json", ".git-credentials",
                     "Documents", "Desktop", "Downloads"):
            target = os.path.join(user, name)
            assert f"Read(/{target})" in deny, name
            assert f"Read(/{target}/**)" in deny, name
        # and the primary fence roots reads, so the same paths are outside
        # every root the gate would allow
        cfg = team_roster.gate_config(spec, mate)
        for root in cfg["read_roots"]:
            assert not (os.path.join(user, "Library/Containers")
                        .startswith(root.rstrip("/") + "/")), root

    # ---- P6: dropping a teammate is defined behavior, never silent ----

    def _drop_rig(self, tmp_path, monkeypatch):
        raw = make_spec(tmp_path)
        raw["teammates"].append(
            {"name": "C", "slug": "c", "role": "gone", "role_line": "gone",
             "accent_color": "#33aa55", "instance": "c",
             "charter": "# C charter\n"})
        home, _ = fake_home(tmp_path, extra_instances={
            "c": {"driver": "claudeAgent", "displayName": "C",
                  "enabled": True, "config": {"homePath": "/c"}}})
        spec = load(tmp_path, raw)
        for mate in spec["teammates"]:  # C's home exists on disk
            os.makedirs(team_roster.teammate_home(spec, mate), exist_ok=True)
        state_path = tmp_path / "t3-team" / "run" / "team_roster_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"teammates": {
            "C": {"instance": "c", "threadId": "mcp:c-1", "title": "C — gone",
                  "threadInstance": "c", "recoveredBy": None}}}))
        monkeypatch.setattr(team_roster, "ensure_project", lambda s: "proj-1")
        monkeypatch.setattr(team_roster, "acquire_apply_lock",
                            lambda s: None)
        monkeypatch.setattr(team_roster, "ensure_gate", lambda s: "0" * 64)
        monkeypatch.setattr(team_roster, "session_processes",
                            lambda *paths: [])
        # the real ensure_threads runs (state preservation is part of the
        # P6 behavior under test); only the T3 CLI and web list are faked
        monkeypatch.setattr(team_roster, "list_threads", lambda s, p: [])

        def fake_t3(spec, args, stdin_text=None, timeout=900):
            title = args[args.index("--title") + 1]

            class Proc:
                returncode = 0
                stdout = json.dumps({"threadId": f"t-{title}"})
                stderr = ""
            return Proc()

        monkeypatch.setattr(team_roster, "t3", fake_t3)
        monkeypatch.setattr(team_roster, "rename_threads",
                            lambda s, t: ({n: False for n in t}, []))
        monkeypatch.setattr(team_roster, "write_urls_file",
                            lambda s, t: "/tmp/urls.json")
        return raw, spec

    def test_drop_teammate_defined_behavior(self, tmp_path, monkeypatch,
                                            capsys):
        raw, spec = self._drop_rig(tmp_path, monkeypatch)
        # spec without C; C's home and state entry still exist
        raw2 = make_spec(tmp_path)
        spec2 = load(tmp_path, raw2)
        # 1. unconfirmed drop: apply refuses loudly
        with pytest.raises(SystemExit):
            team_roster.cmd_apply(spec2)
        assert "refusing" in capsys.readouterr().err
        # 2. confirmed drop (--drop covers both identifiers: the slug from
        # disk and the name from state): instance disabled in place, home
        # kept, state entry kept with removedAt, other mates' fences keep
        # denying C's home
        assert team_roster.cmd_apply(spec2, drop=("c", "C")) == 0
        capsys.readouterr()
        settings = json.load(open(os.path.join(
            raw["server"]["home"], "userdata", "settings.json")))
        assert settings["providerInstances"]["c"]["enabled"] is False
        c_home = os.path.join(raw["server"]["root"], "teammates", "c")
        assert os.path.isdir(c_home)  # kept, not deleted
        state = json.load(open(tmp_path / "t3-team" / "run" /
                               "team_roster_state.json"))
        assert state["teammates"]["C"]["removedAt"]
        assert state["teammates"]["C"]["threadId"] == "mcp:c-1"
        deny = json.load(open(os.path.join(
            c_home.replace("/c", "/a"), "tool-limits.json"))
        )["permissions"]["deny"]
        for tool in ("Write", "Edit", "Read", "Glob", "Grep"):
            assert f"{tool}(/{os.path.realpath(c_home)})" in deny, tool

    # ---- P7/P13: one apply at a time ----

    def test_apply_lock_serializes_concurrent_applies(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        holder = team_roster.acquire_apply_lock(spec)
        assert holder is not None
        # a second apply (its own open file description) must refuse
        with pytest.raises(SystemExit):
            team_roster.acquire_apply_lock(spec)
        lock_path = os.path.join(
            team_roster.expand(spec["server"]["root"]), "run",
            "team_roster.apply.lock")
        assert os.path.isfile(lock_path)

    # ---- P8: slug charset ----

    def test_slug_must_match_charset(self, tmp_path):
        for bad in ("/tmp/evil", "../..", "a/", "a b", "", "a.b", "a:b"):
            raw = make_spec(tmp_path)
            raw["teammates"][0]["slug"] = bad
            with pytest.raises(SystemExit):
                load(tmp_path, raw)
        for good in ("a", "A-1_b", "nightguard"):
            raw = make_spec(tmp_path)
            raw["teammates"][0]["slug"] = good
            load(tmp_path, raw)  # must not raise

    # ---- P9: server.home at/inside ~/.t3 refused ----

    def test_server_home_at_dot_t3_refused(self, tmp_path):
        for home in ("~/.t3", "~/.t3/sub"):
            raw = make_spec(tmp_path)
            raw["server"]["home"] = home
            with pytest.raises(SystemExit):
                load(tmp_path, raw)

    # ---- P10: non-list values die ----

    def test_non_list_root_values_die(self, tmp_path):
        for key in ("allow_read_roots", "deny_read_roots",
                    "deny_write_roots", "home_write_allow"):
            raw = make_spec(tmp_path)
            raw[key] = "~/x"  # the panel's exact string
            with pytest.raises(SystemExit):
                load(tmp_path, raw)

    # ---- P11: rstrip before the locked-name check ----

    def test_locked_name_with_trailing_slash_refused(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["home_write_allow"] = ["settings.json/"]
        with pytest.raises(SystemExit):
            load(tmp_path, raw)

    # ---- P12: ~ entries in deny_write_roots expand ----

    def test_deny_write_roots_tilde_expands(self, tmp_path):
        raw = make_spec(tmp_path)
        raw["deny_write_roots"] = ["/tmp", "~/ssh-cache-standin"]
        spec = load(tmp_path, raw)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        expanded = os.path.realpath(os.path.expanduser("~/ssh-cache-standin"))
        for tool in ("Write", "Edit"):
            assert f"{tool}(/{expanded})" in deny
            assert f"{tool}(/{expanded}/**)" in deny

    # ---- P14: unknown fields inside an existing instance survive ----

    def test_unknown_fields_inside_instance_preserved(self, tmp_path):
        home, path = fake_home(tmp_path, extra_instances={
            "a": {"driver": "claudeAgent", "displayName": "A",
                  "enabled": True, "x_server_field": {"keep": "me"},
                  "config": {"homePath": "/old", "x_nested": 1}}})
        spec = load(tmp_path, make_spec(tmp_path))
        team_roster.ensure_instances(spec)
        settings = json.load(open(path))
        mine = settings["providerInstances"]["a"]
        assert mine["x_server_field"] == {"keep": "me"}
        assert mine["config"]["x_nested"] == 1

    # ---- P15: home-child enumeration fails closed ----

    def test_home_child_enumeration_fails_closed(self, tmp_path,
                                                 monkeypatch):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        os.makedirs(home, exist_ok=True)
        real = os.listdir

        def broken(path):
            if os.path.realpath(path) == os.path.realpath(home):
                raise OSError("permission denied (planted)")
            return real(path)

        monkeypatch.setattr(team_roster.os, "listdir", broken)
        with pytest.raises(SystemExit):
            team_roster.rooted_home_write_rules(spec, mate)

    # ---- P16: the pending-restart warning precedes later failures ----

    def test_pending_restart_warning_precedes_later_failure(
            self, tmp_path, monkeypatch, capsys):
        spec = load(tmp_path, make_spec(tmp_path))
        monkeypatch.setattr(team_roster, "ensure_project",
                            lambda s: "proj-1")
        monkeypatch.setattr(team_roster, "acquire_apply_lock",
                            lambda s: None)
        monkeypatch.setattr(team_roster, "ensure_gate", lambda s: "0" * 64)
        monkeypatch.setattr(team_roster, "session_processes",
                            lambda *paths: [])

        def die_later(spec, disable=()):
            raise SystemExit("paperclip refusal (simulated)")

        monkeypatch.setattr(team_roster, "ensure_instances", die_later)
        with pytest.raises(SystemExit):
            team_roster.cmd_apply(spec)
        out = capsys.readouterr().out
        assert "NOT IN FORCE" in out  # warned before the die()
        assert "tool-limits.json" in out

    # ---- P17: status checks the limits file, wiring and the gate ----

    def test_status_reports_limits_instance_gate_state(self, tmp_path,
                                                       monkeypatch, capsys):
        freeze_listings(monkeypatch)
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        # untouched roster: limits missing -> problems
        limits_ok, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not limits_ok and not gate_ok and problems
        # apply the file assets and install the gate: clean
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        limits_ok, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert limits_ok and gate_ok and not problems, problems
        # tamper with the limits file: stale fence is reported
        limits_path, _ = team_roster.limits_paths(spec, mate)
        saved = open(limits_path).read()
        tampered = json.loads(saved)
        tampered["permissions"]["deny"] = \
            tampered["permissions"]["deny"][:5]
        open(limits_path, "w").write(json.dumps(tampered, indent=2) + "\n")
        limits_ok, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not limits_ok and problems
        # restore, then corrupt the installed gate: reported, loudly
        open(limits_path, "w").write(saved)
        gate_path = team_roster.gate_install_path(spec)
        os.chmod(gate_path, 0o644)  # ensure_gate made it 0555
        open(gate_path, "a").write("# tampered\n")
        limits_ok, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert limits_ok and not gate_ok and problems
        assert any("does not match" in p for p in problems)
        os.chmod(gate_path, 0o755)

    def test_cmd_status_fails_loudly_on_broken_fence(self, tmp_path,
                                                     monkeypatch, capsys):
        spec = load(tmp_path, make_spec(tmp_path))
        fake_home(tmp_path)
        monkeypatch.setattr(team_roster, "project_by_root", lambda s: None)
        monkeypatch.setattr(team_roster, "list_threads", lambda s, p: [])
        code = team_roster.cmd_status(spec)
        out = capsys.readouterr()
        assert code == 1
        assert "FENCE BROKEN" in out.err

    # ---- P18: a rename-driver timeout is reported, not a traceback ----

    def test_rename_timeout_caught_reported(self, tmp_path, monkeypatch,
                                            capsys):
        raw = make_spec(tmp_path)
        profile = os.path.join(raw["server"]["root"], "browser-profile")
        os.makedirs(profile)
        os.chmod(profile, 0o700)
        raw["browser_profile"] = profile
        raw["browser_node"] = "/bin/echo"
        spec = load(tmp_path, raw)
        home = tmp_path / "t3-team" / "home" / "userdata"
        home.mkdir(parents=True)
        (home / "environment-id").write_text("env-1")
        threads = {"A": {"threadId": "t-a", "title": "wrong",
                         "currentTitle": "wrong", "pinnedAt": None,
                         "projectId": "p1", "instance": "a"},
                   "B": {"threadId": "t-b", "title": "B — design",
                         "currentTitle": "B — design", "pinnedAt": None,
                         "projectId": "p1", "instance": "b"}}

        def hang(*a, **k):
            raise subprocess.TimeoutExpired(a[0], 120)

        monkeypatch.setattr(team_roster.subprocess, "run", hang)
        renames, failures = team_roster.rename_threads(spec, threads)
        assert failures == ["A"]  # B needed no rename
        assert renames["A"] is False
        evidence = os.path.join(raw["server"]["root"], "run",
                                "team_renames.jsonl")
        row = json.loads(open(evidence).read().splitlines()[-1])
        assert row["verified"] is False
        assert "timed out" in row["error"]

    # ---- P19: a 0600 settings.json preimage before the live merge ----

    def test_settings_preimage_written_0600(self, tmp_path):
        home, path = fake_home(tmp_path)
        before = open(path).read()
        spec = load(tmp_path, make_spec(tmp_path))
        changed = team_roster.ensure_instances(spec)
        assert changed
        preimage = tmp_path / "t3-team" / "run" / \
            "team_roster_settings.preimage.json"
        assert preimage.exists()
        assert stat.S_IMODE(os.stat(preimage).st_mode) == 0o600
        assert open(preimage).read() == before  # the way back

    # ---- TSHc: server run/ unreadable, window/launch surfaces
    # unwritable ----

    def test_run_tree_unreadable_and_window_unwritable(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        # run/ unreadable for every read tool (pairing file, server log,
        # browser profile)
        for tool in ("Read", "Glob", "Grep"):
            assert f"{tool}(/{os.path.join(root, 'run')})" in deny
            assert f"{tool}(/{os.path.join(root, 'run')}/**)" in deny
        # server-root infrastructure + TSHc window surfaces unwritable
        user = os.path.realpath(os.path.expanduser("~"))
        for target in (os.path.join(root, name)
                       for name in ("bin", "config", "runtime", "run")):
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{target})" in deny, target
                assert f"{tool}(/{target}/**)" in deny, target
        for name in ("Library/LaunchAgents", ".mastermind/window",
                     ".mastermind/mmos_dev/window-dev*", ".t3"):
            base = os.path.join(user, name.rstrip("*").rstrip("/"))
            if name.endswith("*"):
                forms = [f"{tool}(/{base}*)", f"{tool}(/{base}*/**)"]
            else:
                forms = [f"{tool}(/{base})", f"{tool}(/{base}/**)"]
            for tool in ("Write", "Edit"):
                for form in forms:
                    assert form in deny, form
        # rule-layer cut: an EXISTING sibling of the spec root has NO
        # Write/Edit rule deny any more — the gate refuses it at call time
        # (and the post-apply-folder test below proves that live)
        sibling = os.path.join(os.path.dirname(root), "sibling-build")
        os.makedirs(sibling, exist_ok=True)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert not any(sibling in d for d in deny)

    # ---- step 6: a new folder needs no regeneration (hook is primary) ----

    def test_gate_refuses_post_apply_folder_without_regeneration(
            self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        cfg_path = team_roster.gate_config_path(spec, mate)
        gate = team_roster.gate_install_path(spec)
        home = team_roster.teammate_home(spec, mate)
        # a folder created AFTER apply, outside every root
        new_folder = tmp_path / "created-after-apply"
        new_folder.mkdir()
        (new_folder / "x.md").write_text("x")

        def call(tool, tool_input):
            payload = json.dumps({"tool_name": tool,
                                  "tool_input": tool_input,
                                  "cwd": home})
            return subprocess.run([sys.executable, gate, "--config",
                                   cfg_path], input=payload,
                                  capture_output=True, text=True, timeout=30)

        assert call("Read", {"file_path": str(
            new_folder / "x.md")}).returncode == 2
        assert call("Write", {"file_path": str(
            new_folder / "y.md"), "content": "x"}).returncode == 2
        assert call("Glob", {"pattern": "*", "path": str(
            new_folder)}).returncode == 2

    # ---- the gate is wired into the generated limits ----

    def test_tool_limits_wire_gate_hook(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        limits = team_roster.tool_limits(spec, mate)
        wired = limits.get("hooks", {}).get("PreToolUse", [])
        assert wired and wired[0]["matcher"] == "*"
        command = wired[0]["hooks"][0]["command"]
        assert team_roster.gate_install_path(spec) in command
        assert team_roster.gate_config_path(spec, mate) in command
        # apply writes that config 0600 under server-private config/
        team_roster.write_file_assets(spec, mate)
        cfg_path = team_roster.gate_config_path(spec, mate)
        assert os.path.isfile(cfg_path)
        assert stat.S_IMODE(os.stat(cfg_path).st_mode) == 0o600
        assert os.path.dirname(cfg_path).startswith(os.path.join(
            team_roster.expand(spec["server"]["root"]), "config"))


class TestRepairRound2:
    """Panel 2 repairs R4/R6b/R6c (R1-R3/R5/R6a live in the gate tests)."""

    # ---- R4: quoted, isolated, fail-closed hook command (M2 + N1) ----

    def test_r4_gate_command_shape(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        command = team_roster.gate_command(spec, mate)
        # M-R2 (panel 3) tightened R4: the interpreter is the pinned
        # absolute binary, never a PATH lookup
        assert command.startswith("/usr/bin/python3 -I ")
        assert "/usr/bin/env" not in command
        assert command.endswith("|| exit 2")
        # both paths quoted: a server root with a space must still parse
        assert f"'{team_roster.gate_install_path(spec)}'" in command
        assert f"'{team_roster.gate_config_path(spec, mate)}'" in command

    def test_r4_fail_closed_through_the_wired_command(self, tmp_path):
        # a root with a SPACE in it: the quoting must survive sh -c
        root = tmp_path / "server root"
        spec = load(tmp_path, make_spec(tmp_path, root=str(root)))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        command = team_roster.gate_command(spec, mate)
        allowed = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": str(
                team_roster.teammate_home(spec, mate) + "/CLAUDE.md")},
            "cwd": team_roster.teammate_home(spec, mate)})
        # working gate: the allowed call passes through the wired command
        proc = subprocess.run(command, shell=True, input=allowed,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        # gate unreadable (python3 cannot open it): refused. NOTE: the exec
        # bit alone is NOT a failure mode — `env python3 <gate>` reads the
        # file, so 0644 still runs; integrity of the mode is status's job
        # (R6c), and the command fails closed on real failures
        gate_path = team_roster.gate_install_path(spec)
        os.chmod(gate_path, 0o000)
        proc = subprocess.run(command, shell=True, input=allowed,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2
        # gate missing (python3 exits 2 on "can't open file"): refused
        os.chmod(gate_path, 0o555)
        os.remove(gate_path)
        proc = subprocess.run(command, shell=True, input=allowed,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2
        # gate that raises at import (exit 1): refused
        open(gate_path, "w").write("raise RuntimeError('boom')\n")
        os.chmod(gate_path, 0o555)
        proc = subprocess.run(command, shell=True, input=allowed,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2

    # ---- R6b: the census bare denies (M4 + N4) ----

    def test_r6b_bare_denies_cover_census(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        # every offered non-allowlisted client tool from the live census
        for tool in ("Agent", "AskUserQuestion", "ListAgents",
                     "ReportFindings", "ScheduleWakeup", "Skill",
                     "Workflow"):
            assert tool in deny, f"census tool {tool} must be bare-denied"
        # belt: client tools this build may offer under other configs
        for tool in ("Bash", "Task", "LS", "NotebookEdit", "NotebookRead",
                     "SlashCommand", "BashOutput", "KillShell",
                     "EnterPlanMode", "ExitPlanMode", "Monitor",
                     "ReadMcpResource", "ListMcpResources", "MultiEdit",
                     "SendMessage", "CronCreate", "CronDelete", "CronList"):
            assert tool in deny, f"belt tool {tool} must be bare-denied"
        # MCP names: exact names only — live-proved (N4) that neither the
        # wildcard mcp__* nor prefix forms bind
        for tool in ("mcp__t3-code__request_secret",
                     "mcp__web_reader__webReader"):
            assert tool in deny
        assert not any("*" in d and d.startswith("mcp__") for d in deny), \
            "wildcard mcp denies do not bind (live-proved); name each"
        # the allowlist is untouched by the census denies
        for tool in ("Read", "Glob", "Grep", "WebFetch", "WebSearch",
                     "TodoWrite", "ToolSearch"):
            assert tool not in deny

    # ---- R6c: status catches mode, interpreter, disabled hooks, canary ----

    def test_r6c_status_catches_mode_python3_hooks_canary(self, tmp_path,
                                                          monkeypatch):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        limits_ok, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert limits_ok and gate_ok and not problems, problems
        # 1) mode must be exactly 0555
        gate_path = team_roster.gate_install_path(spec)
        os.chmod(gate_path, 0o755)  # executable but not 0555
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not gate_ok and any("0555" in p for p in problems), problems
        os.chmod(gate_path, 0o555)
        # 2) the pinned interpreter missing for the hook command (M-R2
        #    replaced the PATH lookup with one absolute binary)
        monkeypatch.setattr(team_roster, "GATE_INTERPRETER",
                            "/nonexistent/python3")
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not gate_ok and any("pinned hook interpreter" in p
                                   for p in problems), problems
        monkeypatch.setattr(team_roster, "GATE_INTERPRETER",
                            "/usr/bin/python3")
        # 3) hooks disabled in a settings file that applies to the teammate
        home = team_roster.teammate_home(spec, mate)
        settings = os.path.join(home, "settings.json")
        open(settings, "w").write('{"disableAllHooks": true}\n')
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not gate_ok and any("disableAllHooks" in p for p in problems)
        os.remove(settings)
        # 4) a canary call that does NOT exit 2 (gate replaced by an
        #    allow-all stub with the right wiring)
        with open(gate_path) as fh:
            original = fh.read()
        os.chmod(gate_path, 0o644)  # installed 0555 is not writable
        open(gate_path, "w").write("#!/usr/bin/env python3\nimport sys\n"
                                   "sys.exit(0)\n")
        os.chmod(gate_path, 0o555)
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not gate_ok and any("canary" in p for p in problems)
        os.chmod(gate_path, 0o644)
        open(gate_path, "w").write(original)
        os.chmod(gate_path, 0o555)
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert gate_ok and not problems, problems

    # ---- R3 rule-layer companion: the unreadable set, extended (M5) ----

    def test_r3_home_unreadable_set_extended_and_synced(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in ("cutover-preimage.json", ".credentials.json",
                     ".claude.json", ".claude.json.backup", "carrier.json",
                     "tool-limits.json", "settings.json", "projects"):
            for tool in ("Read", "Glob", "Grep"):
                assert f"{tool}(/{home}/{name})" in deny, (tool, name)
                assert f"{tool}(/{home}/{name}/**)" in deny, (tool, name)
        # the gate's unreadable set covers the roster's exact names
        gate = importlib.util.spec_from_file_location(
            "teammate_gate_r3", team_roster.GATE_SOURCE)
        module = importlib.util.module_from_spec(gate)
        gate.loader.exec_module(module)
        assert set(team_roster.HOME_UNREADABLE) <= set(
            module.UNREADABLE_NAMES)


class TestRepairRound3:
    """Panel 3: H-2 (unreadable set from one list), M-R1 (firmlink
    canonicalization of config paths), M-R2 (pinned interpreter)."""

    @staticmethod
    def _gate_module():
        loader = importlib.util.spec_from_file_location(
            "teammate_gate_r3b", team_roster.GATE_SOURCE)
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        return module

    # ---- H-2: the unreadable set is DERIVED from the gate's one list ----

    def test_h2_unreadable_set_derived_from_one_list(self):
        gate = self._gate_module()
        # the roster does not keep its own copy: both classes come from the
        # gate's canonical sets, so they cannot drift apart again
        assert set(team_roster.HOME_UNREADABLE) == set(gate.UNREADABLE_NAMES)
        assert set(team_roster.HOME_CONFIG) == set(gate.CLAUDE_CONFIG_NAMES)
        # everything HOME_CONFIG classes as Claude configuration is covered
        # by the read fence, including the panel's named items
        assert set(team_roster.HOME_CONFIG) <= set(team_roster.HOME_UNREADABLE)
        for name in (".claude", ".mcp.json", "keybindings.json", "sessions",
                     "CLAUDE.md.backup", ".claude.json.backup"):
            assert name in team_roster.HOME_UNREADABLE, name
        # the readable memory surfaces are not collateral damage
        for name in ("CLAUDE.md", "CHARTER.md", "notes"):
            assert name not in team_roster.HOME_UNREADABLE, name

    def test_h2_rule_layer_denies_the_config_class(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        for name in (".mcp.json", "keybindings.json", "sessions",
                     "CLAUDE.md.backup", ".claude"):
            for tool in ("Read", "Glob", "Grep"):
                assert f"{tool}(/{home}/{name})" in deny, (tool, name)
                assert f"{tool}(/{home}/{name}/**)" in deny, (tool, name)

    # ---- M-R1: config paths canonicalized before comparison/dedupe ----

    def test_mr1_gate_config_home_canonical_across_firmlink_spellings(
            self, tmp_path):
        # a spec that spells server.root in the Data-volume form must emit
        # a gate config whose home matches the primary spelling the gate
        # compares tool paths against (panel 3 MIXED: the unreadable check
        # was skipped entirely)
        root = str(tmp_path / "t3-team")
        data_root = "/System/Volumes/Data" + root
        spec = load(tmp_path, make_spec(tmp_path, root=data_root))
        mate = spec["teammates"][0]
        home = team_roster.teammate_home(spec, mate)
        assert home.startswith("/System/Volumes/Data")  # the mixed shape
        cfg = team_roster.gate_config(spec, mate)
        # canonical: the /System/Volumes/Data prefix is stripped to the
        # primary spelling so rel_first_component can never miss the home —
        # and it is exactly what the primary-spelled spec would emit
        assert not cfg["home"].startswith("/System/Volumes/Data"), cfg["home"]
        primary_spec = load(tmp_path, make_spec(tmp_path, root=root))
        assert cfg["home"] == team_roster.gate_config(
            primary_spec, primary_spec["teammates"][0])["home"]
        assert cfg["read_roots"] == team_roster.gate_config(
            primary_spec, primary_spec["teammates"][0])["read_roots"]

    def test_mr1_gate_config_dedupe_is_normalization_aware(self, tmp_path):
        # the same root in both firmlink spellings is ONE entry, not two
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        ws = spec["project"]["workspace_root"]
        spec["allow_read_roots"] = [ws, "/System/Volumes/Data" + ws]
        cfg = team_roster.gate_config(spec, mate)
        roots = cfg["read_roots"]
        assert len(roots) == len(set(roots)), roots
        assert len([r for r in roots
                    if r.startswith("/System/Volumes/Data")]) == 0, roots

    # ---- M-R2: the hook interpreter is one absolute, validated binary ----

    def test_mr2_gate_command_pins_absolute_interpreter(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        command = team_roster.gate_command(spec, mate)
        # the exact pinned binary, isolated, fail-closed — no PATH lookup
        assert command.startswith(team_roster.GATE_INTERPRETER + " -I ")
        assert command.startswith("/")
        assert "/usr/bin/env" not in command
        assert command.endswith("|| exit 2")
        # the pinned interpreter is a real executable on this machine
        assert os.path.isfile(team_roster.GATE_INTERPRETER)
        assert os.access(team_roster.GATE_INTERPRETER, os.X_OK)

    def test_mr2_wired_command_runs_under_the_pinned_interpreter(
            self, tmp_path):
        # end to end through sh -c: the command executes and fails closed
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        allowed = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": str(
                team_roster.teammate_home(spec, mate) + "/CLAUDE.md")},
            "cwd": team_roster.teammate_home(spec, mate)})
        proc = subprocess.run(team_roster.gate_command(spec, mate),
                              shell=True, input=allowed,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr

    def test_mr2_status_flags_missing_pinned_interpreter(
            self, tmp_path, monkeypatch):
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        team_roster.write_file_assets(spec, mate)
        team_roster.ensure_gate(spec)
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert gate_ok and not problems, problems
        monkeypatch.setattr(team_roster, "GATE_INTERPRETER",
                            "/nonexistent/python3")
        _, gate_ok, problems = team_roster._fence_status(spec, mate)
        assert not gate_ok
        assert any("pinned hook interpreter" in p for p in problems), problems

    def test_mr2_apply_dies_when_pinned_interpreter_missing(
            self, tmp_path, monkeypatch):
        spec = load(tmp_path, make_spec(tmp_path))
        monkeypatch.setattr(team_roster, "GATE_INTERPRETER",
                            "/nonexistent/python3")
        with pytest.raises(SystemExit):
            team_roster.ensure_gate(spec)
