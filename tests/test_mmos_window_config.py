"""Lane T8 window config tool: what the person-opened window reads.

Covers ``tools/mmos_team_server/window_config.sh`` (write/show/clear of the
fixed per-user config), the mapping between bundle identifiers and config
directories staying in sync with the Rust loader, and the pairing helper's
extraction contract (``tools/mmos_team_server/window_pair_helper.sh``).
No T3 server is started and no real token is ever produced: the helper is
exercised against a fake ``t3`` that prints synthetic output.
"""

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

    def test_write_without_helper_keeps_an_existing_helper(self):
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
            assert (config_dir / "pair-helper").read_text().strip() == helper
            assert (
                config_dir / "shell-url"
            ).read_text().strip() == "http://127.0.0.1:3780/env-1/t2"

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

    def test_show_redacts_a_token_that_reached_the_file_by_hand(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / ".mastermind/mmos_dev/window-dev"
            config_dir.mkdir(parents=True)
            (config_dir / "shell-url").write_text(
                "http://127.0.0.1:3780/env-1/t?token=supersecret123\n"
            )
            shown = run_tool("show", "--bundle", "dev", env_extra={"HOME": tmp}, check=False)
            assert shown.returncode == 0
            assert "supersecret123" not in shown.stdout
            assert "token=<redacted>" in shown.stdout

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
            assert result.returncode == 0  # sed produced nothing; window sees empty output

    def test_failing_t3_produces_no_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            fake = fake_t3(tmp_path, "echo 'No running T3 Code server found.' >&2; exit 1")
            result = run_helper(fake, home, tmp_path)
            assert result.stdout.strip() == ""

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
