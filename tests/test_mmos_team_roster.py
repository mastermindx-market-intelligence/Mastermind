"""Lane T7 team-roster tool: spec, settings-merge and refusal tests.

Pure unit tests — no server is started or contacted. They exercise
``tools/mmos_team_server/team_roster.py`` against throwaway directories.
"""

import importlib.util
import json
import os
import stat
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
        assert "Write(//tmp/**)" in joined


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
                     "cutover-preimage.json"):
            assert f"Write(/{home}/{name})" in deny
            assert f"Edit(/{home}/{name})" in deny
        assert not any("CLAUDE.md" in d for d in deny)

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
        assert not any("CLAUDE.md" in d for d in deny)
        allow = team_roster.tool_limits(spec, mate)["permissions"]["allow"]
        assert f"Write(/{home}/**)" in allow

    def test_spec_roots_and_siblings(self, tmp_path):
        raw = make_spec(tmp_path)
        secret_dir = tmp_path / "elsewhere" / "secrets"
        secret_dir.mkdir(parents=True)
        raw["deny_read_roots"] = [str(secret_dir)]
        raw["deny_read_root_siblings"] = True
        spec = load(tmp_path, raw)
        root = team_roster.expand(spec["server"]["root"])
        os.makedirs(root, exist_ok=True)
        sibling = os.path.join(os.path.dirname(root), "sibling-proofs")
        os.makedirs(sibling, exist_ok=True)
        mate = spec["teammates"][0]
        deny = team_roster.tool_limits(spec, mate)["permissions"]["deny"]
        assert f"Read(/{secret_dir}/**)" in deny
        assert f"Read(/{sibling}/**)" in deny
        assert not any(d.startswith(f"Read(/{root}/**") for d in deny)


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
        way. The write fence enumeration is delegated to
        rooted_read_denies (its chain/sibling logic has its own direct
        tests); this reconstruction pins WHICH roots fence writes and how
        every other deny is composed."""
        root = os.path.realpath(team_roster.expand(spec["server"]["root"]))
        home = os.path.realpath(team_roster.teammate_home(spec, mate))
        deny_roots = [os.path.realpath(
            team_roster.expand(spec["project"]["workspace_root"]))]
        deny_roots += [os.path.realpath(r)
                       for r in spec.get("deny_write_roots", [])]
        deny_roots += [a for r in deny_roots
                       for a in team_roster.firmlink_aliases(r)]
        deny = ["Bash", "Agent", "NotebookEdit"]
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
        for name in team_roster.SERVER_INFRASTRUCTURE:
            infra = os.path.join(root, name)
            for tool in ("Write", "Edit"):
                deny += [f"{tool}(/{infra})", f"{tool}(/{infra}/**)"]
        t3_dir = os.path.dirname(os.path.realpath(
            team_roster.expand(spec["server"]["t3_bin"])))
        for tool in ("Write", "Edit"):
            deny += [f"{tool}(/{t3_dir})", f"{tool}(/{t3_dir}/**)"]
        for path in team_roster.deny_read_paths(spec, mate):
            deny += team_roster._read_deny(path)
        # always-on write fence (attack round): own home only when no
        # rooted key is set; the read roots join otherwise
        fence_roots = [home]
        deny += team_roster.rooted_read_denies(spec, mate, ("Write", "Edit"),
                                               roots=fence_roots)
        # same first-occurrence dedupe as tool_limits (components can now
        # overlap: the explicit t3_bin-dir deny collides with the
        # enumeration's deny of the same directory as a chain sibling)
        seen = set()
        deny = [d for d in deny if not (d in seen or seen.add(d))]
        allow = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
                 f"Write(/{home}/**)", f"Edit(/{home}/**)"]
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
        """Snapshot each directory listing once: the equality tests below
        compare two enumerations of the LIVE filesystem, and /private/tmp
        (on pytest's tmp_path chain) churns underneath them — a file
        appearing between the two calls would break equality spuriously."""
        real = os.listdir
        cache = {}
        def frozen(path):
            key = os.path.realpath(path)
            if key not in cache:
                cache[key] = list(real(path))
            return cache[key]
        monkeypatch.setattr(team_roster.os, "listdir", frozen)

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

    def test_allow_read_roots_denies_outside_roots(self, tmp_path):
        """Rooted reads: every directory NOT on the chain to an allowed root
        is denied for Read/Glob/Grep, in file and tree form; the allowed
        roots and the own home stay readable; plain Read/Glob/Grep allows
        are replaced by rooted ones."""
        extra_root = tmp_path / "elsewhere" / "ws2"
        extra_root.mkdir(parents=True)
        raw = make_spec(tmp_path)
        raw["allow_read_roots"] = [str(extra_root)]
        spec = load(tmp_path, raw)
        mate, other = spec["teammates"][0], spec["teammates"][1]
        os.makedirs(team_roster.teammate_home(spec, other))
        home = team_roster.teammate_home(spec, mate)
        # a sibling of the allowed root under a chain dir: exists at apply
        # time, so sibling enumeration must deny it (a name created after
        # apply is the stated future-name gap, not testable here)
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
        # every top-level directory not on the chain of an allowed root is
        # denied in file and tree form (chain names derived from the roots,
        # so the test holds on any host)
        roots = [os.path.realpath(str(extra_root)),
                 os.path.realpath(home)]
        chain_at_root = {r.strip("/").split("/")[0] for r in roots}
        for tool in ("Read", "Glob", "Grep"):
            for name in os.listdir("/"):
                if name in chain_at_root:
                    continue
                assert f"{tool}(//{name})" in deny, name
                assert f"{tool}(//{name}/**)" in deny, name
        # chain directories get NO deny in any form: a deny on a directory
        # matches its whole subtree (live-proved: "File is in a directory
        # that is denied"), so even a file-form deny would deny the allowed
        # root below it. Their non-chain children that exist at apply time
        # are denied in both forms.
        chain_parent = os.path.dirname(str(extra_root))
        sibling = str(sibling_dir)
        for tool in ("Read", "Glob", "Grep"):
            assert f"{tool}(/{chain_parent})" not in deny
            assert f"{tool}(/{chain_parent}/**)" not in deny
            assert f"{tool}(/{sibling})" in deny
            assert f"{tool}(/{sibling}/**)" in deny
        # the allowed root and the home are never denied as trees
        for allowed in (str(extra_root), home):
            assert not any(d.startswith(f"Read(/{allowed}/**)")
                           for d in deny)
        # every pre-existing deny survives (second layer)
        assert f"Read(/{team_roster.teammate_home(spec, other)}/**)" in deny
        assert "Bash" in deny

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
        # allowed names never denied
        for tool in ("Write", "Edit"):
            assert not any(d.startswith(f"{tool}(/{home}/CLAUDE.md")
                           for d in deny)
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
        monkeypatch.setattr(team_roster, "ensure_instances", lambda s: [])
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
    def test_write_and_rewrite_home(self, tmp_path):
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
                        os.path.join(root, "teammates", "b"),
                        os.path.join(str(tmp_path), "zshenv")]
        # a directory deny matches its whole subtree (live-proved D2), so
        # home/userdata needs no rule of its own — assert the cover exists
        for path in denied_paths:
            for tool in ("Write", "Edit"):
                assert f"{tool}(/{path})" in deny, (tool, path)
                assert f"{tool}(/{path}/**)" in deny, (tool, path)
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
        """Finding 6: _read_deny never relies on an exact-path rule alone
        — the Write/Edit exact form proved inert live (evidence 10 D3),
        so no emitter may depend on an exact form binding."""
        f = tmp_path / "secret.txt"
        f.write_text("x")
        assert team_roster._read_deny(str(f)) == \
            [f"Read(/{f})", f"Read(/{f}/**)"]

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

    def test_sibling_enumeration_fails_closed(self, tmp_path, monkeypatch):
        """Finding 9: a listdir failure on an EXISTING chain parent dies
        instead of silently emitting a fence with holes; a parent that
        does not exist is skipped (fresh installs, foreign paths)."""
        spec = load(tmp_path, make_spec(tmp_path))
        mate = spec["teammates"][0]
        os.makedirs(team_roster.teammate_home(spec, mate), exist_ok=True)
        parent = os.path.realpath(
            os.path.dirname(team_roster.teammate_home(spec, mate)))
        real_listdir = os.listdir
        def fake(p):
            if os.path.realpath(p) == parent:
                raise PermissionError(13, "simulated denial")
            return real_listdir(p)
        monkeypatch.setattr(team_roster.os, "listdir", fake)
        with pytest.raises(SystemExit):
            team_roster.rooted_read_denies(spec, mate, ("Write", "Edit"),
                                           roots=[team_roster.teammate_home(spec, mate)])
        # nonexistent parent: skipped, no exception
        rules = team_roster.rooted_read_denies(
            spec, mate, ("Write", "Edit"), roots=["/no/such/root"])
        assert isinstance(rules, list)

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
