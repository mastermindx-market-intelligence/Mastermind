"""Clock-only native patch qualification; never invoke the actual controller.

The fixtures contain only its public clock prefix and a plist whose native string
values are removed. The production transform, reload, credentials, and routes are
not executed. Publication and first-cutover/drain qualification remain separate.
"""
from datetime import datetime
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fabric_peak_clock"
PATCH = ROOT / "ops/native_fabric/patches/fabric_peak_clock_20261110.patch"
SCRIPT = "peak_router.sh"
PLIST = "ai.mastermind.fabric-peak-router.plist"


@pytest.fixture(scope="module")
def patched(tmp_path_factory):
    directory = tmp_path_factory.mktemp("peak-clock-only")
    for name in (SCRIPT, PLIST):
        shutil.copyfile(FIXTURE / (name + ".preimage"), directory / name)
    subprocess.run(
        ["git", "apply", "--unidiff-zero", "--check", str(PATCH)],
        cwd=directory, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "apply", "--unidiff-zero", str(PATCH)],
        cwd=directory, check=True, capture_output=True, text=True,
    )
    return directory


def clock_result(script: str, instant: str, *, override=None, provider_clock=None, clock_fails=False):
    at = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    assert at.tzinfo is not None
    local = at.astimezone(ZoneInfo("Asia/Singapore"))
    sgt = f"{local.isoweekday()} {local:%H%M}"
    # Execute only the inspected clock branch, stopping before even its log call.
    start = script.index("SGT_NOW=") if "SGT_NOW=" in script else script.index("ET_NOW=")
    stop = script.index('\nlog "run', start)
    fragment = script[start:stop]
    assert all(term not in fragment for term in ("launchctl", "RELOAD", "routes.json", "python3"))
    harness = '''
log() { :; }
date() {
  [ "$FAKE_DATE_FAIL" = 1 ] && return 42
  case "$TZ" in
    Asia/Singapore) printf '%s\\n' "$FAKE_SGT" ;;
    America/New_York) printf '%s\\n' "$FAKE_ET" ;;
    *) return 91 ;;
  esac
}
'''
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C",
        "FAKE_SGT": sgt if provider_clock is None else provider_clock,
        "FAKE_ET": at.astimezone(ZoneInfo("America/New_York")).strftime("%H%M"),
        "FAKE_DATE_FAIL": "1" if clock_fails else "0",
    }
    shell = shutil.which("zsh") or "bash"
    if shell == "bash" and "ET_NOW=" in fragment:
        # Native zsh treats HHMM as decimal unless OCTAL_ZEROES is enabled.
        # Bash otherwise changes the predecessor's meaning for 0130 / 0530.
        # Preserve the native semantics on Linux runners without zsh; the new
        # POSIX numeric-test branch needs no adaptation on either shell.
        original = "(( ET_NOW >= 100 && ET_NOW < 500 ))"
        assert original in fragment
        fragment = fragment.replace(original, "(( 10#$ET_NOW >= 100 && 10#$ET_NOW < 500 ))")
    return subprocess.run(
        [shell, "-f", "-c", harness + fragment + '\nprintf "%s\\n" "$WANT"',
         "clock-fixture", *([] if override is None else [override])],
        env=env, capture_output=True, text=True, timeout=5,
    )


@pytest.mark.parametrize("instant,expected", [
    ("2026-11-10T05:59:59Z", "offpeak"),
    ("2026-11-10T06:00:00Z", "peak"),
    ("2026-11-10T09:59:59Z", "peak"),
    ("2026-11-10T10:00:00Z", "offpeak"),
    ("2026-06-15T05:30:00Z", "offpeak"),
    ("2026-06-15T06:00:00Z", "peak"),
    ("2026-06-15T09:30:00Z", "peak"),
    ("2026-06-15T10:00:00Z", "offpeak"),
    ("2026-11-07T06:30:00Z", "offpeak"),
    ("2026-11-08T06:30:00Z", "offpeak"),
    ("2026-11-01T06:30:00Z", "offpeak"),
    ("2026-11-09T06:30:00Z", "peak"),
    ("2026-11-09T00:00:00Z", "offpeak"),
])
def test_provider_weekday_boundaries_and_dst(patched, instant, expected):
    result = clock_result((patched / SCRIPT).read_text(), instant)
    assert (result.returncode, result.stdout.strip()) == (0, expected)


@pytest.mark.parametrize("instant,expected,old_wrong", [
    ("2026-06-15T05:30:00Z", "offpeak", "peak"),
    ("2026-06-15T09:30:00Z", "peak", "offpeak"),
    ("2026-11-07T06:30:00Z", "offpeak", "peak"),
])
def test_discriminating_cases_reproduce_the_native_predecessor_bug(patched, instant, expected, old_wrong):
    before = clock_result((FIXTURE / (SCRIPT + ".preimage")).read_text(), instant)
    after = clock_result((patched / SCRIPT).read_text(), instant)
    assert (before.returncode, before.stdout.strip()) == (0, old_wrong)
    assert (after.returncode, after.stdout.strip()) == (0, expected)


@pytest.mark.parametrize("override,expected", [("on", "peak"), ("off", "offpeak")])
def test_explicit_operator_overrides_are_retained(patched, override, expected):
    result = clock_result((patched / SCRIPT).read_text(), "2026-11-10T07:00:00Z", override=override)
    assert (result.returncode, result.stdout.strip()) == (0, expected)


@pytest.mark.parametrize("bad_clock", ["", "8 1400", "1 2400", "1 1460", "1 14:00", "1 1400 extra"])
def test_bad_clock_does_not_invent_an_offpeak_discount(patched, bad_clock):
    result = clock_result((patched / SCRIPT).read_text(), "2026-11-10T07:00:00Z", provider_clock=bad_clock)
    assert result.returncode == 1
    assert result.stdout == ""


def test_failed_clock_does_not_invent_an_offpeak_discount(patched):
    result = clock_result((patched / SCRIPT).read_text(), "2026-11-10T07:00:00Z", clock_fails=True)
    assert result.returncode == 1
    assert result.stdout == ""


def test_same_existing_agent_not_a_host_timezone_calendar_or_new_daemon(patched):
    before = plistlib.loads((FIXTURE / (PLIST + ".preimage")).read_bytes())
    after = plistlib.loads((patched / PLIST).read_bytes())
    assert before["StartCalendarInterval"] == [{"Hour": 22, "Minute": 0}, {"Hour": 2, "Minute": 0}]
    assert "StartCalendarInterval" not in after
    assert after["StartInterval"] == 60
    assert after["RunAtLoad"] is True
    assert {k: v for k, v in before.items() if k != "StartCalendarInterval"} == {
        k: v for k, v in after.items() if k != "StartInterval"
    }


def test_patch_and_fixtures_contain_no_native_account_or_credential_rows(patched):
    for path in [PATCH, *FIXTURE.iterdir()]:
        text = path.read_text()
        assert all(token not in text for token in ("/Users/", "glm_chairman", "env_key", "api_key", "router.env"))
    # The fixture ends before the router's private transformation program.
    assert "RESULT=" not in (patched / SCRIPT).read_text()


def test_linux_runner_without_zsh_preserves_native_predecessor_semantics(patched, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda command: None)
    old = (FIXTURE / (SCRIPT + ".preimage")).read_text()
    new = (patched / SCRIPT).read_text()
    for instant, before_want, after_want in (
        ("2026-06-15T05:30:00Z", "peak", "offpeak"),
        ("2026-06-15T09:30:00Z", "offpeak", "peak"),
        ("2026-11-07T06:30:00Z", "peak", "offpeak"),
    ):
        before, after = clock_result(old, instant), clock_result(new, instant)
        assert (before.returncode, before.stdout.strip()) == (0, before_want)
        assert (after.returncode, after.stdout.strip()) == (0, after_want)
