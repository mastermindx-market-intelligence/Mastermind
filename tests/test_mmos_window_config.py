"""Lane T8 window config tool: what the person-opened window reads.

Covers ``tools/mmos_team_server/window_config.sh`` (write/show/clear of the
fixed per-user config), the mapping between bundle identifiers and config
directories staying in sync with the Rust loader, and the pairing helper's
extraction contract (``tools/mmos_team_server/window_pair_helper.sh``).
No T3 server is started and no real token is ever produced: the helper is
exercised against a fake ``t3`` that prints synthetic output.

Panel repair round (lane T8b, 2026-11-11): the helper's exit status must
propagate (repair C), ``write`` without ``--pair-helper`` removes an existing
helper unless ``--keep-pair-helper`` (F), localhost and /pair paths are
refused (F), staging leaves no temporaries (F), the open_team_window.sh
header matches the config-helper behaviour with the wrapper-script route (H),
and the single-instance plugin is declared and registered first (G).
"""

import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CONFIG_TOOL = REPO / "tools" / "mmos_team_server" / "window_config.sh"
HELPER = REPO / "tools" / "mmos_team_server" / "window_pair_helper.sh"
SHELL_MODE_RS = (
    REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "shell_mode.rs"
).read_text()
SECRETISH = re.compile(r"(token=[A-Za-z0-9]|Pairing URL: http.*token)", re.I)


def run_tool(*args, env_extra=None, check=True):
    env = dict(os.environ)
    env.pop("MMOS_T3_DEV_ROOT", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["sh", str(CONFIG_TOOL), *args],
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


def fake_t3(dir_path: Path, body: str) -> Path:
    """A stand-in t3 command; body is a shell snippet run with $1.. as args."""
    path = dir_path / "fake-t3"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o700)
    return path


def run_helper(t3_bin: Path, t3_home: Path, cwd: Path):
    env = dict(os.environ)
    env.pop("MMOS_T3_DEV_ROOT", None)
    env["WINDOW_PAIR_T3_BIN"] = str(t3_bin)
    env["WINDOW_PAIR_T3_HOME"] = str(t3_home)
    return subprocess.run(
        ["sh", str(HELPER)],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


class TestConfigDirs:
    def test_script_mapping_matches_the_rust_loader(self):
        source = SHELL_MODE_RS
        assert 'identifier == "com.mastermind.os"' in source
        assert '".mastermind").join("window")' in source
        assert '".mastermind")\n            .join("mmos_dev")' in source
        assert 'format!("window-{dashed}")' in source
        script = CONFIG_TOOL.read_text()
        assert '$HOME/.mastermind/window"' in script
        assert '$HOME/.mastermind/mmos_dev/window-dev"' in script
        assert '$HOME/.mastermind/mmos_dev/window-dev-t8"' in script

    def test_release_dev_and_t8_are_three_distinct_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            dirs = []
            for bundle, expected in [
                ("release", ".mastermind/window"),
                ("dev", ".mastermind/mmos_dev/window-dev"),
                ("t8", ".mastermind/mmos_dev/window-dev-t8"),
            ]:
                run_tool(
                    "write",
                    "--bundle",
                    bundle,
                    "--url",
                    "http://127.0.0.1:3780/env-1/thread-1",
                    env_extra={"HOME": str(home)},
                )
                dirs.append(home / expected)
                assert (home / expected / "shell-url").exists(), bundle
            assert len({str(d) for d in dirs}) == 3
            # The release file is not under any dev root.
            assert ".mastermind/mmos_dev" not in str(dirs[0])


class TestWriteShowClear:
    def test_write_creates_0600_files_and_show_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "http://127.0.0.1:3797/env-1/thread-9"
            helper = str(REPO / "tools/mmos_team_server/window_pair_helper.sh")
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                url,
                "--pair-helper",
                helper,
                env_extra={"HOME": tmp},
            )
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev-t8"
            url_file = config_dir / "shell-url"
            helper_file = config_dir / "pair-helper"
            assert url_file.read_text().strip() == url
            assert helper_file.read_text().strip() == helper
            assert stat.S_IMODE(url_file.stat().st_mode) == 0o600
            assert stat.S_IMODE(helper_file.stat().st_mode) == 0o600
            assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700

            shown = run_tool("show", "--bundle", "t8", env_extra={"HOME": tmp})
            assert url in shown.stdout
            assert helper in shown.stdout
            assert "mode=600" in shown.stdout

            run_tool("clear", "--bundle", "t8", env_extra={"HOME": tmp})
            assert not url_file.exists()
            assert not helper_file.exists()

    def test_write_refuses_non_loopback_root_and_fragment_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in [
                "http://example.com/thread-1",
                "https://127.0.0.1:3780/thread-1",
                "http://127.0.0.1:3780/",
                "http://127.0.0.1:3780",
                "http://127.0.0.1:3780/pair#token=abc",
            ]:
                with pytest.raises(subprocess.CalledProcessError):
                    run_tool(
                        "write", "--bundle", "dev", "--url", bad, env_extra={"HOME": tmp}
                    )
            assert not (Path(tmp) / ".mastermind/mmos_dev/window-dev/shell-url").exists()

    def test_write_refuses_relative_or_missing_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(subprocess.CalledProcessError):
                run_tool(
                    "write",
                    "--bundle",
                    "dev",
                    "--url",
                    "http://127.0.0.1:3780/env-1/t",
                    "--pair-helper",
                    "tools/window_pair_helper.sh",
                    env_extra={"HOME": tmp},
                )
            with pytest.raises(subprocess.CalledProcessError):
                run_tool(
                    "write",
                    "--bundle",
                    "dev",
                    "--url",
                    "http://127.0.0.1:3780/env-1/t",
                    "--pair-helper",
                    "/nonexistent/helper.sh",
                    env_extra={"HOME": tmp},
                )

    def test_write_without_helper_removes_an_existing_helper(self):
        # Panel repair F: a write without --pair-helper used to silently keep
        # an existing helper, so a config edit meant to withdraw minting left
        # it armed. Now the helper is removed unless --keep-pair-helper.
        with tempfile.TemporaryDirectory() as tmp:
            helper = str(HELPER)
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t",
                "--pair-helper",
                helper,
                env_extra={"HOME": tmp},
            )
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t2",
                env_extra={"HOME": tmp},
            )
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev-t8"
            assert not (config_dir / "pair-helper").exists(), "helper must be removed"
            assert (
                config_dir / "shell-url"
            ).read_text().strip() == "http://127.0.0.1:3780/env-1/t2"

    def test_write_keep_pair_helper_preserves_an_existing_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = str(HELPER)
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t",
                "--pair-helper",
                helper,
                env_extra={"HOME": tmp},
            )
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t2",
                "--keep-pair-helper",
                env_extra={"HOME": tmp},
            )
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev-t8"
            assert (config_dir / "pair-helper").read_text().strip() == helper
            assert (
                config_dir / "shell-url"
            ).read_text().strip() == "http://127.0.0.1:3780/env-1/t2"

    def test_write_refuses_localhost_and_pair_paths(self):
        # Panel repair F: localhost is refused (the server prints 127.0.0.1,
        # and the spellings must not diverge), and the path is checked
        # exactly — the root, /pair and anything under /pair belong to the
        # pairing flow and never to a saved config.
        with tempfile.TemporaryDirectory() as tmp:
            for bad in [
                "http://localhost:3780/env-1/t",
                "http://LOCALHOST:3780/env-1/t",
                "http://127.0.0.1:3780/pair",
                "http://127.0.0.1:3780/pair/",
                "http://127.0.0.1:3780/pair/more",
                "http://127.0.0.1:3780/pair?x=1",
            ]:
                result = run_tool(
                    "write", "--bundle", "dev", "--url", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
            assert not (Path(tmp) / ".mastermind/mmos_dev/window-dev/shell-url").exists()

    def test_write_leaves_no_temporaries_and_files_are_0600(self):
        # Panel repair F: temporaries are staged under umask 077 with a trap
        # that removes them; after any write the config directory holds
        # exactly the committed files, nothing else.
        with tempfile.TemporaryDirectory() as tmp:
            run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t",
                "--pair-helper",
                str(HELPER),
                env_extra={"HOME": tmp},
            )
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev-t8"
            names = sorted(p.name for p in config_dir.iterdir())
            assert names == ["pair-helper", "shell-url"], names
            for name in names:
                assert stat.S_IMODE((config_dir / name).stat().st_mode) == 0o600
            # A refused write (bad helper) stages nothing at all.
            result = run_tool(
                "write",
                "--bundle",
                "t8",
                "--url",
                "http://127.0.0.1:3780/env-1/t2",
                "--pair-helper",
                "/nonexistent/helper.sh",
                env_extra={"HOME": tmp},
                check=False,
            )
            assert result.returncode != 0
            names = sorted(p.name for p in config_dir.iterdir())
            assert names == ["pair-helper", "shell-url"], names
            assert (
                config_dir / "shell-url"
            ).read_text().strip() == "http://127.0.0.1:3780/env-1/t"

    def test_source_stages_under_umask_077_with_a_removing_trap(self):
        # Panel repair F source contract: both files are staged (not written
        # in place) and a trap removes the temporaries on any exit.
        script = CONFIG_TOOL.read_text()
        assert "umask 077" in script
        assert re.search(r"trap 'rm -f .*(url_tmp|helper_tmp).*' EXIT HUP INT TERM", script)

    def test_unknown_bundle_is_refused(self):
        with pytest.raises(subprocess.CalledProcessError):
            run_tool("write", "--bundle", "other", "--url", "http://127.0.0.1:1/a/b")

    def test_write_refuses_token_bearing_urls_without_echoing_them(self):
        # Attack finding: a `token=` query parameter slipped past the fragment
        # check, and refusals echoed the URL — a credential printed to a log.
        with tempfile.TemporaryDirectory() as tmp:
            for bad in [
                "http://127.0.0.1:3780/env-1/t?token=supersecret123",
                "http://127.0.0.1:3780/env-1/t?x=1&token=supersecret123",
            ]:
                result = run_tool(
                    "write", "--bundle", "dev", "--url", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
                assert "supersecret123" not in result.stderr, "refusal echoed the token"
                assert "token" in result.stderr
            assert not (Path(tmp) / ".mastermind/mmos_dev/window-dev/shell-url").exists()

    def test_show_never_echoes_a_multiline_config(self):
        # Panel round 2 (q1-4): the shell case patterns in `show` match
        # across newlines, so a hand-edited multi-line config file would be
        # echoed raw. The single-line guard runs first: no part of a
        # multi-line file is ever printed.
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev"
            config_dir.mkdir(parents=True)
            (config_dir / "shell-url").write_text(
                "http://127.0.0.1:3780/env-1/t\nsecond line\n"
            )
            shown = run_tool("show", "--bundle", "dev", env_extra={"HOME": tmp}, check=False)
            assert shown.returncode == 0
            assert "second line" not in shown.stdout
            assert "env-1" not in shown.stdout, (
                "no part of a multi-line config is echoed"
            )
            assert "(not shown: not a single line)" in shown.stdout
            # The same guard covers the helper file's line.
            (config_dir / "shell-url").unlink()
            (config_dir / "pair-helper").write_text("/bin/good\n/bin/second\n")
            shown = run_tool("show", "--bundle", "dev", env_extra={"HOME": tmp}, check=False)
            assert "second" not in shown.stdout
            assert "(not shown: not a single line)" in shown.stdout

    def test_show_prints_scheme_host_port_path_and_never_the_rest(self):
        # Panel repair L: `show` prints the scheme, host, port and path only;
        # a stored line carrying userinfo, a query or a fragment is never
        # echoed at all, and there is no redact() to get wrong.
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev"
            config_dir.mkdir(parents=True)
            (config_dir / "shell-url").write_text(
                "http://127.0.0.1:3780/env-1/t?token=supersecret123\n"
            )
            shown = run_tool("show", "--bundle", "dev", env_extra={"HOME": tmp}, check=False)
            assert shown.returncode == 0
            assert "supersecret123" not in shown.stdout
            assert "env-1" not in shown.stdout, "the path is not printed for a query-carrying line"
            assert "(not shown: carries a query, fragment or userinfo)" in shown.stdout

    def test_refusals_name_the_reason_only_never_the_value(self):
        # Panel repair L: no refusal echoes the address, not even partially.
        with tempfile.TemporaryDirectory() as tmp:
            for bad, needle in [
                ("http://127.0.0.1:3780/env-1/t?token=supersecret123", "supersecret123"),
                ("http://user:pass@127.0.0.1:3780/env-1/t", "user:pass"),
                ("http://127.0.0.1:3780/env-1/t#token=supersecret123", "supersecret123"),
                ("http://localhost:3780/env-1/t", "localhost:3780/env-1/t"),
            ]:
                result = run_tool(
                    "write", "--bundle", "dev", "--url", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
                assert needle not in result.stderr, f"refusal echoed the value: {needle}"
                assert needle not in result.stdout, bad

    def test_write_exact_shape_rules_ports_and_paths(self):
        # Panel repair M: the cheap refusals are exact, not globs — port all
        # digits in 1..65535, host exactly 127.0.0.1, and no control
        # characters.
        with tempfile.TemporaryDirectory() as tmp:
            for bad in [
                "http://127.0.0.1:0/env-1/t",
                "http://127.0.0.1:65536/env-1/t",
                "http://127.0.0.1:99999/env-1/t",
                "http://127.0.0.1:37a8/env-1/t",
                "http://127.0.0.1:/env-1/t",
                "http://127.0.0.1:3780/env-1/t\nx",
                "http://127.0.0.1:3780/env-1/\tt",
            ]:
                result = run_tool(
                    "write", "--bundle", "dev", "--url", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
            assert not (Path(tmp) / ".mastermind/mmos_dev/window-dev/shell-url").exists()
            # Boundary ports are accepted.
            for good in [
                "http://127.0.0.1:1/env-1/t",
                "http://127.0.0.1:65535/env-1/t",
            ]:
                run_tool(
                    "write", "--bundle", "dev", "--url", good,
                    env_extra={"HOME": tmp},
                )

    def test_write_refuses_helper_paths_with_dotdot(self):
        # Panel repair M: the helper path must be absolute with no `..`,
        # matching the app-side parser exactly.
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ["/tmp/../bin/helper.sh", "/tmp/a..b/helper.sh"]:
                result = run_tool(
                    "write", "--bundle", "dev",
                    "--url", "http://127.0.0.1:3780/env-1/t",
                    "--pair-helper", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
            assert not (Path(tmp) / ".mastermind/mmos_dev/window-dev/pair-helper").exists()

    def test_write_refuses_dot_segment_disguised_pair_paths(self):
        # Attack round: `/a/../pair` and its percent-encoded spellings pass a
        # literal `/pair` case pattern, but the app's url parser normalizes
        # dot segments, so the window would open on the pairing page. The
        # writer must refuse the disguise, not the literal spelling only.
        with tempfile.TemporaryDirectory() as tmp:
            for bad in [
                "http://127.0.0.1:3780/a/../pair",
                "http://127.0.0.1:3780/%2e%2e/pair",
                "http://127.0.0.1:3780/%2E%2E/pair",
                "http://127.0.0.1:3780/.%2e/pair",
                "http://127.0.0.1:3780/%2e./pair",
                "http://127.0.0.1:3780//pair",
                "http://127.0.0.1:3780/PAIR",
                "http://127.0.0.1:3780/Pair/x",
            ]:
                result = run_tool(
                    "write", "--bundle", "t8", "--url", bad,
                    env_extra={"HOME": tmp}, check=False,
                )
                assert result.returncode != 0, bad
                assert "refusing the address" in result.stderr, bad
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev-t8"
            assert not (config_dir / "shell-url").exists()

    def test_write_refuses_oversized_ports_with_a_named_reason(self):
        # Attack round: a 19-digit port overflows the shell numeric test and
        # exits with an arithmetic error instead of the named refusal. The
        # refusal must be named for every bad port.
        with tempfile.TemporaryDirectory() as tmp:
            result = run_tool(
                "write", "--bundle", "t8",
                "--url", "http://127.0.0.1:9999999999999999999/env-1/t",
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode != 0
            assert "port must be between 1 and 65535" in result.stderr

    def test_write_never_touches_a_symlinked_config_directory(self):
        # Attack round: `chmod 700` ran before the symlink refusal, so a
        # planted symlink had its target directory's mode rewritten before
        # the write was refused. The refusal must come first and touch
        # nothing.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            victim = home / "victim"
            victim.mkdir()
            victim.chmod(0o755)
            (home / ".mastermind/mmos_dev").mkdir(parents=True)
            (home / ".mastermind/mmos_dev/window-dev-t8").symlink_to(victim)
            result = run_tool(
                "write", "--bundle", "t8",
                "--url", "http://127.0.0.1:3780/env-1/t",
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode != 0
            assert "symlink" in result.stderr
            assert stat.S_IMODE(victim.stat().st_mode) == 0o755
            assert not (victim / "shell-url").exists()

    def test_show_and_clear_refuse_a_symlinked_config_directory(self):
        # Same rule for the readers: a symlinked config directory is never
        # followed, not for display and not for deletion.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            victim = home / "victim"
            victim.mkdir()
            (victim / "shell-url").write_text("http://127.0.0.1:3780/env-1/t\n")
            (home / ".mastermind/mmos_dev").mkdir(parents=True)
            (home / ".mastermind/mmos_dev/window-dev-t8").symlink_to(victim)
            for args in (["show"], ["clear"]):
                result = run_tool(
                    *args, "--bundle", "t8", env_extra={"HOME": tmp}, check=False
                )
                assert result.returncode != 0, args
                assert "symlink" in result.stderr, args
            assert (victim / "shell-url").exists()

    def test_show_prints_single_digit_ports(self):
        # Attack round: the show filter required two port digits, so a
        # legitimately written `:1` address printed as unrecognized.
        with tempfile.TemporaryDirectory() as tmp:
            url = "http://127.0.0.1:1/env-1/thread-9"
            run_tool("write", "--bundle", "t8", "--url", url, env_extra={"HOME": tmp})
            shown = run_tool("show", "--bundle", "t8", env_extra={"HOME": tmp})
            assert url in shown.stdout
            assert "unrecognized" not in shown.stdout

    def test_check_command_runs_the_app_judge_and_propagates_it(self):
        # Panel repair M: `check --bundle <b> --app <path>` execs the app
        # binary in --check-window-config mode, passing its lines and exit
        # code through untouched.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app = tmp_path / "fake-app"
            app.write_text(
                "#!/bin/sh\n"
                '[ "$#" -eq 1 ] && [ "$1" = "--check-window-config" ] || exit 9\n'
                "printf 'config-dir: ok\\nshell-url: refused missing\\n'\n"
                "exit 1\n"
            )
            app.chmod(0o755)
            result = run_tool(
                "check", "--bundle", "t8", "--app", str(app),
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode == 1
            assert "config-dir: ok" in result.stdout
            assert "shell-url: refused missing" in result.stdout
            # Missing --app is a usage error.
            result = run_tool("check", "--bundle", "t8", env_extra={"HOME": tmp}, check=False)
            assert result.returncode == 2

    def test_usage_prints_only_the_help_text(self):
        # Panel repair P: usage() is a help heredoc, not a slice of the
        # file header.
        result = run_tool(env_extra={"HOME": tempfile.gettempdir()}, check=False)
        assert result.returncode == 2
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        assert lines, "usage must print something"
        for line in lines:
            assert line.startswith("usage:") or line.startswith("       "), line
        assert "Secret handling" not in result.stderr
        assert "Address shape" not in result.stderr

    def test_write_refuses_substitutable_pair_helpers(self):
        # Attack finding: the 0600 config file's checks said nothing about the
        # executable it named. A symlinked, group-writable, or planted-in-a-
        # writable-directory helper must be refused at configuration time.
        import stat as stat_mod

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clean = tmp_path / "clean-helper.sh"
            clean.write_text("#!/bin/sh\ntrue\n")
            clean.chmod(0o755)
            run_tool(
                "write", "--bundle", "dev",
                "--url", "http://127.0.0.1:3780/env-1/t",
                "--pair-helper", str(clean),
                env_extra={"HOME": tmp},
            )  # the clean helper is accepted

            groupy = tmp_path / "groupy-helper.sh"
            groupy.write_text("#!/bin/sh\ntrue\n")
            groupy.chmod(0o770)
            result = run_tool(
                "write", "--bundle", "dev",
                "--url", "http://127.0.0.1:3780/env-1/t",
                "--pair-helper", str(groupy),
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode != 0
            assert "group- or other-writable" in result.stderr

            open_dir = tmp_path / "open-dir"
            open_dir.mkdir()
            open_dir.chmod(0o777)
            planted = open_dir / "planted-helper.sh"
            planted.write_text("#!/bin/sh\ntrue\n")
            planted.chmod(0o755)
            result = run_tool(
                "write", "--bundle", "dev",
                "--url", "http://127.0.0.1:3780/env-1/t",
                "--pair-helper", str(planted),
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode != 0
            assert "writable directory" in result.stderr

            linked = tmp_path / "linked-helper.sh"
            linked.symlink_to(clean)
            result = run_tool(
                "write", "--bundle", "dev",
                "--url", "http://127.0.0.1:3780/env-1/t",
                "--pair-helper", str(linked),
                env_extra={"HOME": tmp}, check=False,
            )
            assert result.returncode != 0
            assert "symlink" in result.stderr
            assert stat_mod.S_ISLNK(linked.lstat().st_mode)  # untouched by the refusal


class TestPairHelper:
    def test_extracts_the_pairing_url_line_and_only_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            # Same shape as t3 pair's output: QR block, Pairing URL, App link,
            # Token, Expires (values are synthetic, never a real credential).
            fake = fake_t3(
                tmp_path,
                "printf 'Pairing with m2studio (http://127.0.0.1:3797).\\n\\n"
                "████▀▀▀▀\\n\\n"
                "Pairing URL: http://127.0.0.1:3797/pair#token=synthetic0123456789abcd\\n"
                "App link: t3code://pair?u=http%%3A%%2F%%2F127.0.0.1%%3A3797%%2Fpair%%23token%%3Dsynthetic\\n"
                "Token: synthetic0123456789abcd\\n"
                "Expires: 2026-11-10T00:00:00.000Z\\n'\n"
                'printf "stderr noise\\n" >&2',
            )
            result = run_helper(fake, home, tmp_path)
            assert result.returncode == 0, result.stderr
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            assert lines == [
                "http://127.0.0.1:3797/pair#token=synthetic0123456789abcd"
            ], "stdout must be exactly the pairing URL line"
            assert "synthetic" not in result.stderr

    def test_missing_url_line_fails_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            fake = fake_t3(tmp_path, "printf 'Token: synthetic-only\\n'")
            result = run_helper(fake, home, tmp_path)
            assert result.stdout.strip() == ""
            # t3 itself succeeded, so the helper exits 0 with empty stdout; the
            # window treats empty output as a failed parse (HelperOutput).
            assert result.returncode == 0

    def test_failing_t3_exits_nonzero_and_produces_no_url(self):
        # Panel repair C: the minting command's own exit status must become
        # the helper's exit status. Before the repair the `| sed | head`
        # pipeline masked it, so a dead server looked like a silent success
        # and the window's helper_exit path was unreachable.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            fake = fake_t3(tmp_path, "echo 'No running T3 Code server found.' >&2; exit 1")
            result = run_helper(fake, home, tmp_path)
            assert result.stdout.strip() == ""
            assert result.returncode != 0, "helper must fail when the minting command fails"

    def test_helper_header_documents_the_env_cleared_wrapper_route(self):
        # Panel repair H: the helper's header must state that the window
        # clears the environment, so WINDOW_PAIR_T3_* only reach a helper run
        # directly and the config must name a wrapper script instead.
        text = HELPER.read_text()
        assert "clears" in text and "wrapper" in text
        assert "WINDOW_PAIR_T3_BIN" in text and "WINDOW_PAIR_T3_HOME" in text

    def test_open_team_window_header_matches_the_config_helper_behaviour(self):
        # Panel repair H: the header used to claim the env-launched flow
        # "keeps its old behaviour" of never re-pairing. The window starts
        # the watchdog whenever the fixed config names a helper — env launch
        # included — so the header must say that and point at the wrapper
        # script as the supported way to aim re-pairing at a dev server.
        text = (REPO / "tools" / "mmos_team_server" / "open_team_window.sh").read_text()
        assert "keeps its old behaviour" not in text
        assert "pair-helper" in text
        assert "wrapper" in text
        assert "WINDOW_PAIR_T3_BIN" in text and "WINDOW_PAIR_T3_HOME" in text

    def test_refuses_missing_bin_or_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            missing_bin = run_helper(tmp_path / "absent-t3", home, tmp_path)
            assert missing_bin.returncode != 0
            missing_home = run_helper(
                fake_t3(tmp_path, "true"), tmp_path / "absent-home", tmp_path
            )
            assert missing_home.returncode != 0

    def test_helper_passes_ttl_label_and_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            capture = tmp_path / "capture.txt"
            # The fake records what the helper actually invoked it with; its
            # stderr is discarded by the helper, so the record goes to a file.
            fake = fake_t3(
                tmp_path,
                'printf "T3CODE_HOME=%s\\nARGS=%s\\n" "$T3CODE_HOME" "$*" > "$CAPTURE"\n'
                "printf 'Pairing URL: http://127.0.0.1:3797/pair#token=synthetic\\n'",
            )
            env = dict(os.environ)
            env["CAPTURE"] = str(capture)
            env["WINDOW_PAIR_T3_BIN"] = str(fake)
            env["WINDOW_PAIR_T3_HOME"] = str(home)
            result = subprocess.run(
                ["sh", str(HELPER)], capture_output=True, text=True, env=env, check=False
            )
            assert result.returncode == 0, result.stderr
            assert "http://127.0.0.1:3797/pair#token=synthetic" in result.stdout
            recorded = capture.read_text()
            assert f"T3CODE_HOME={home}" in recorded
            assert f"--base-dir {home}" in recorded
            assert "--ttl 2m" in recorded
            assert "--label Mastermind OS window" in recorded
            assert "pair" in recorded

    def test_no_real_credentials_in_repo_scripts(self):
        for script in [CONFIG_TOOL, HELPER]:
            text = script.read_text()
            assert not SECRETISH.search(text), f"{script.name} must not embed a token"


class TestOpenTeamWindow:
    OPEN = REPO / "tools" / "mmos_team_server" / "open_team_window.sh"

    @staticmethod
    def roster(tmp_path: Path, entries) -> Path:
        root = tmp_path / "team"
        (root / "run").mkdir(parents=True, exist_ok=True)
        urls = root / "run" / "team_urls.json"
        urls.write_text(json.dumps({"teammates": entries}))
        return urls

    def run_open(self, tmp_path: Path, arg: str):
        env = dict(os.environ)
        env["HOME"] = str(tmp_path)
        env["MMOS_TEAM_ROOT"] = str(tmp_path / "team")
        env["MMOS_TEAM_WINDOW_DIR"] = str(tmp_path / "work")
        env["MMOS_DEV_APP"] = str(tmp_path / "fake-app")
        return subprocess.run(
            ["sh", str(self.OPEN), arg],
            capture_output=True, text=True, env=env, cwd=tmp_path, check=False,
        )

    def make_app(self, tmp_path: Path):
        app = tmp_path / "fake-app"
        app.write_text("#!/bin/sh\nexit 0\n")
        app.chmod(0o755)

    def test_instance_ids_are_validated_typed_and_from_the_roster(self):
        # Panel repair O: the id becomes a file name; both the typed id and
        # the roster entry's own id must be one [A-Za-z0-9._-] word with no
        # `..`, or the script refuses.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.make_app(tmp_path)
            self.roster(tmp_path, [
                {"instanceId": "ok-1", "name": "One", "url": "http://127.0.0.1:3780/env-1/t"},
                {"instanceId": "../evil", "name": "Evil", "url": "http://127.0.0.1:3780/env-1/t"},
            ])
            # Typed id with a path separator / traversal is refused. (The
            # roster-side id check is the same rule applied to the matched
            # entry — depth-in-depth; it cannot be reached with a different
            # string because lookup is by exact id.)
            for bad in ["../evil", "a/b", "a..b", "sp ace", "id;ls"]:
                result = self.run_open(tmp_path, bad)
                assert result.returncode != 0, bad
            assert not (tmp_path / "work").exists() or not list(
                (tmp_path / "work").glob("thread-*")
            )
            # The clean entry writes the 0600 address file.
            result = self.run_open(tmp_path, "ok-1")
            assert result.returncode == 0, result.stderr
            written = tmp_path / "work" / "thread-ok-1.txt"
            assert written.exists()
            assert stat.S_IMODE(written.stat().st_mode) == 0o600
            assert written.read_text().strip() == "http://127.0.0.1:3780/env-1/t"

    def test_roster_addresses_are_parsed_not_prefix_matched(self):
        # Panel repair O: the same exact rule as window_config.sh (repair M)
        # — scheme http, host exactly 127.0.0.1, a real port, no userinfo,
        # no query, no fragment, path neither the root nor /pair nor under
        # it. A `startswith("http://127.0.0.1:")` prefix check is not enough.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.make_app(tmp_path)
            for bad in [
                "http://localhost:3780/env-1/t",
                "http://127.0.0.1.evil.com:3780/env-1/t",
                "http://user@127.0.0.1:3780/env-1/t",
                "http://127.0.0.1:3780/env-1/t?x=1",
                "http://127.0.0.1:3780/env-1/t#f",
                "http://127.0.0.1:3780/pair",
                "http://127.0.0.1:3780/",
                "http://127.0.0.1:0/env-1/t",
                "https://127.0.0.1:3780/env-1/t",
            ]:
                self.roster(tmp_path, [{"instanceId": "bad-1", "name": "Bad", "url": bad}])
                result = self.run_open(tmp_path, "bad-1")
                assert result.returncode != 0, bad
                assert "refusing a roster address" in result.stderr, bad

    def test_roster_refuses_dot_segments_control_chars_and_uppercase(self):
        # Attack round: the roster writer must not validate one string and
        # write another. Dot segments (raw or percent-encoded, either case)
        # smuggle the path past the /pair rule because urlsplit does not
        # normalize; ASCII control characters are stripped by urlsplit before
        # parsing, so a tab-carrying URL would validate and the raw string be
        # written; an uppercase scheme survives urlsplit's lowercasing. All
        # three are refused on the raw string.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.make_app(tmp_path)
            for bad in [
                "http://127.0.0.1:3780/a/../pair",
                "http://127.0.0.1:3780/%2e%2e/pair",
                "http://127.0.0.1:3780/%2E%2E/pair",
                "http://127.0.0.1:3780/.%2e/pair",
                "http://127.0.0.1:3780/%2e./pair",
                "http://127.0.0.1:3780//pair",
                "http://127.0.0.1:3780/env-1/t\t",
                "HTTP://127.0.0.1:3780/env-1/t",
            ]:
                self.roster(tmp_path, [{"instanceId": "bad-1", "name": "Bad", "url": bad}])
                result = self.run_open(tmp_path, "bad-1")
                assert result.returncode != 0, bad
                assert not (
                    tmp_path / "work" / "thread-bad-1.txt"
                ).exists(), bad


class TestSingleInstanceRegistration:
    def test_single_instance_plugin_is_a_dependency_and_registered_first(self):
        # Panel repair G: the maintained tauri-plugin-single-instance (v2,
        # matching the locked Tauri 2 line) must be a declared dependency and
        # the first plugin registered, with a focus-only callback — a second
        # launch focuses the first window and starts nothing.
        manifest = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "Cargo.toml"
        ).read_text()
        assert 'tauri-plugin-single-instance = "2"' in manifest
        main_rs = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "main.rs"
        ).read_text()
        single = main_rs.index("tauri_plugin_single_instance::init")
        opener = main_rs.index("tauri_plugin_opener::init")
        deep_link = main_rs.index("tauri_plugin_deep_link::init")
        assert single < opener and single < deep_link, (
            "single-instance must be registered before every other plugin"
        )
        # Focus-only: the callback routes through reopen/focus, never through
        # a second watchdog, auth restore or pairing start.
        callback = main_rs[single:opener]
        assert "reopen_main_window" in callback or "set_focus" in callback

class TestUrlPollGate:
    def test_watchdog_never_polls_the_url_before_a_committed_load(self):
        # Live-proof round 1 crashed at every launch (launch3-backtrace.log:
        # wry 0.55.1 unwraps a nil WKWebView URL in its url getter and the
        # panic lands on the event loop, taking the app down). Until the
        # window's first load commits the URL is nil — the initial
        # tauri:// load is refused by the allowlist — so the watchdog may
        # call url() only behind a gate keyed to the window generation that
        # finished a load, and a stale commit from a closed window must not
        # open it for its successor.
        pairing = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "shell_pairing.rs"
        ).read_text()
        polls = [
            line
            for line in pairing.splitlines()
            if "window.url()" in line
        ]
        assert polls, "the watchdog's url() poll is gone; re-check the gate"
        gated = re.findall(
            r"filter\(\|_\| url_poll_is_safe\([^)]*\)\)\s*"
            r"\.and_then\(\|window\| window\.url\(\)",
            pairing,
        )
        assert len(polls) == len(gated), (
            "every window.url() call must sit behind the url_poll_is_safe gate"
        )
        main_rs = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "main.rs"
        ).read_text()
        assert "on_page_load" in main_rs, (
            "the window must record its first committed load"
        )
        assert "PageLoadEvent::Finished" in main_rs, (
            "only a finished load proves the webview URL is non-nil"
        )
        assert "mark_window_committed" in main_rs
        assert "window_generation() + 1" in main_rs, (
            "the callback must carry the generation captured at build time, not the current one"
        )

    def test_generation_is_reread_after_the_window_fetch(self):
        # Panel round 2 (the lead's finding): between the watchdog's
        # generation read and its window fetch the event loop can complete a
        # rebuild — the window then held belongs to a newer generation whose
        # gate has not opened, and applying the stale first read to it is
        # exactly the pre-first-commit poll the gate exists to prevent. The
        # generation must be re-read after the fetch and that value is what
        # the gate checks.
        pairing = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "shell_pairing.rs"
        ).read_text()
        loop = pairing.split("let generation = window_generation();", 1)[1]
        loop = loop.split("core.observe", 1)[0]
        fetch = loop.find("get_webview_window")
        assert fetch != -1, "the watchdog's window fetch is gone; re-check the loop"
        reread = loop.find("window_generation()", fetch)
        gate = loop.find("url_poll_is_safe", reread)
        assert reread > fetch, (
            "the generation must be re-read after the window fetch"
        )
        assert gate > reread, (
            "the re-read generation is the one the poll gate must check"
        )

    def test_external_opens_share_one_opener_throttle(self):
        # Panel round 2, item 1: the default-browser opener call itself —
        # not just the log record — must sit behind one sliding-window
        # throttle; the WebKit new-window path funnels into the same
        # External arm, so one throttle bounds both paths, and a dropped
        # open is never queued.
        main_rs = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "main.rs"
        ).read_text()
        external_arm = main_rs.split("NavDecision::External", 1)[1]
        throttle = external_arm.find("allow_external_open()")
        spawn = external_arm.find("std::thread::spawn")
        opener_call = external_arm.find("open_url")
        assert "if shell_pairing::allow_external_open()" in external_arm, (
            "the opener call must be gated by the one shared throttle"
        )
        assert -1 not in (throttle, spawn, opener_call)
        assert throttle < spawn < opener_call, (
            "the opener call must sit behind the throttle, inside the arm"
        )
        pairing = (
            REPO / "app" / "mastermind_os" / "src-tauri" / "src" / "shell_pairing.rs"
        ).read_text()
        assert "const OPENER_WINDOW" in pairing and "const OPENER_BURST" in pairing, (
            "the throttle's window and burst must be named constants"
        )
        slot = pairing.split("fn external_open_slot", 1)[1]
        assert "duration_since" in slot.split("pub fn", 1)[0], (
            "the slot math must age entries out by elapsed time"
        )
