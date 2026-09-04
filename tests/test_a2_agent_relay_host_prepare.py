from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "ops" / "executive_os" / "prepare-a2-agent-relay-host.sh"
RELEASES = "/Library/Application Support/MastermindExecutive/releases"


def test_refuses_non_root_before_any_host_preparation():
    """A privilege-gate regression must never reach a host mutation."""

    completed = subprocess.run(
        ["/bin/bash", str(PREP), "--release-root", f"{RELEASES}/{'a' * 40}"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 77
    assert "must run as root" in completed.stderr


@pytest.mark.parametrize("arguments", [(), ("--unexpected",), ("--release-root",)])
def test_refuses_ambiguous_invocation_before_any_host_preparation(arguments):
    """Removing the closed argument gate must fail before a host command runs."""

    completed = subprocess.run(
        ["/bin/bash", str(PREP), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 64
    assert "usage:" in completed.stderr


@pytest.mark.parametrize(
    ("release_root", "expected_error"),
    [
        ("/tmp/unreviewed-release", "beneath the reviewed releases root"),
        (f"{RELEASES}/not-a-sha", "full 40-character lowercase hexadecimal SHA"),
        (f"{RELEASES}/{'F' * 40}", "full 40-character lowercase hexadecimal SHA"),
    ],
)
def test_refuses_untrusted_release_identity_before_any_host_preparation(
    release_root, expected_error
):
    """Changing the release boundary or SHA parser must fail this host gate."""

    completed = subprocess.run(
        ["/bin/bash", str(PREP), "--release-root", release_root],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 65
    assert expected_error in completed.stderr


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _fake_host_script(tmp_path: Path) -> tuple[Path, Path, dict[str, Path]]:
    """Build a disposable macOS command/metadata boundary for the shell artifact."""

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    state_path = tmp_path / "state.json"
    system_root = tmp_path / "Library" / "Application Support" / "MastermindExecutive"
    runtime_root = tmp_path / "var" / "db" / "mastermind-agent-relay"
    plist_path = tmp_path / "Library" / "LaunchDaemons" / "com.mastermind.executive.agent-relay.plist"
    release_root = system_root / "releases" / ("a" * 40)
    release_root.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "groups": {"wheel": {"PrimaryGroupID": "0"}},
                "metadata": {
                    str(release_root): "0:0:755",
                    str(system_root): "0:0:755",
                },
                "users": {
                    "_mastermind_exec": {
                        "PrimaryGroupID": "450",
                        "UniqueID": "450",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    _write_executable(
        fake_bin / "uname",
        "#!/bin/sh\nprintf 'Darwin\\n'\n",
    )
    _write_executable(
        fake_bin / "uuidgen",
        "#!/bin/sh\nprintf '00000000-0000-4000-8000-000000000000\\n'\n",
    )
    _write_executable(
        fake_bin / "pwpolicy",
        "#!/bin/sh\nexit 0\n",
    )
    _write_executable(
        fake_bin / "forbidden-effect",
        "#!/bin/sh\nprintf 'unexpected effect command: %s\\n' \"$0\" >&2\nexit 99\n",
    )
    _write_executable(
        fake_bin / "id",
        """#!{python}
import json
import os
import sys

state = json.loads(open(os.environ["A2_FAKE_STATE"], encoding="utf-8").read())
if sys.argv[1:] == ["-u"]:
    print("0")
elif sys.argv[1:] == ["-G", "_mastermind_exec"]:
    members = state["groups"].get("_mastermind_agent_relay", {{}}).get("GroupMembership", [])
    print("450 457" if "_mastermind_exec" in members else "450")
else:
    raise SystemExit(64)
""".format(python=sys.executable),
    )
    _write_executable(
        fake_bin / "dscl",
        """#!{python}
import json
import os
import sys

state_path = os.environ["A2_FAKE_STATE"]
state = json.loads(open(state_path, encoding="utf-8").read())
kind_map = {{"Groups": "groups", "Users": "users"}}

def save():
    open(state_path, "w", encoding="utf-8").write(json.dumps(state, sort_keys=True))

def record(path):
    _, kind, name = path.split("/", 2)
    return kind_map[kind], name

args = sys.argv[1:]
if not args or args[0] != ".":
    raise SystemExit(64)
if args[1] == "-list":
    kind = kind_map[args[2].lstrip("/")]
    attribute = args[3]
    for name, values in sorted(state[kind].items()):
        if attribute in values:
            print(name, values[attribute])
    raise SystemExit(0)
if args[1] == "-read":
    kind, name = record(args[2])
    values = state[kind].get(name)
    if values is None:
        raise SystemExit(1)
    if len(args) == 3:
        for key, value in values.items():
            print(f"{{key}}: {{' '.join(value) if isinstance(value, list) else value}}")
    else:
        attribute = args[3]
        if attribute not in values:
            raise SystemExit(1)
        value = values[attribute]
        print(f"{{attribute}}: {{' '.join(value) if isinstance(value, list) else value}}")
    raise SystemExit(0)
if args[1] == "-create":
    kind, name = record(args[2])
    values = state[kind].setdefault(name, {{}})
    if len(args) > 3:
        values[args[3]] = args[4]
    save()
    raise SystemExit(0)
if args[1] == "-authonly":
    raise SystemExit(1)
raise SystemExit(64)
""".format(python=sys.executable),
    )
    _write_executable(
        fake_bin / "dseditgroup",
        """#!{python}
import json
import os
import sys

state_path = os.environ["A2_FAKE_STATE"]
state = json.loads(open(state_path, encoding="utf-8").read())
args = sys.argv[1:]
if args[:2] == ["-o", "edit"]:
    user = args[args.index("-a") + 1]
    group = args[-1]
    members = state["groups"][group].setdefault("GroupMembership", [])
    if user not in members:
        members.append(user)
    open(state_path, "w", encoding="utf-8").write(json.dumps(state, sort_keys=True))
    raise SystemExit(0)
if args[:2] == ["-o", "checkmember"]:
    user = args[args.index("-m") + 1]
    group = args[-1]
    if user in state["groups"].get(group, {{}}).get("GroupMembership", []):
        print(f"yes {{user}} is a member of {{group}}")
        raise SystemExit(0)
    print(f"no {{user}} is NOT a member of {{group}}")
    raise SystemExit(67)
raise SystemExit(64)
""".format(python=sys.executable),
    )
    _write_executable(
        fake_bin / "install",
        """#!{python}
import json
import os
from pathlib import Path
import sys

state_path = os.environ["A2_FAKE_STATE"]
state = json.loads(open(state_path, encoding="utf-8").read())
args = sys.argv[1:]
assert args[0] == "-d"
owner = args[args.index("-o") + 1]
group = args[args.index("-g") + 1]
mode = args[args.index("-m") + 1].lstrip("0") or "0"
path = Path(args[-1])
path.mkdir(parents=True, exist_ok=True)
ids = {{"root": "0", "wheel": "0", "_mastermind_agent_relay": "457"}}
state["metadata"][str(path)] = f"{{ids[owner]}}:{{ids[group]}}:{{mode}}"
open(state_path, "w", encoding="utf-8").write(json.dumps(state, sort_keys=True))
""".format(python=sys.executable),
    )
    _write_executable(
        fake_bin / "stat",
        """#!{python}
import json
import os
import sys

state = json.loads(open(os.environ["A2_FAKE_STATE"], encoding="utf-8").read())
format_string = sys.argv[sys.argv.index("-f") + 1]
metadata = state["metadata"].get(sys.argv[-1], "0:0:755")
uid, gid, mode = metadata.split(":")
if format_string == "%u:%g:%Lp":
    print(metadata)
elif format_string == "%u:%g":
    print(f"{{uid}}:{{gid}}")
elif format_string == "%Lp":
    print(mode)
elif format_string == "%Sp":
    print("drwx------")
else:
    raise SystemExit(64)
""".format(python=sys.executable),
    )

    artifact = tmp_path / "prepare-a2-agent-relay-host.sh"
    source = PREP.read_text(encoding="utf-8")
    replacements = {
        "/usr/bin/uname": str(fake_bin / "uname"),
        "/usr/bin/id": str(fake_bin / "id"),
        "/usr/bin/dscl": str(fake_bin / "dscl"),
        "/usr/sbin/dseditgroup": str(fake_bin / "dseditgroup"),
        "/usr/bin/install": str(fake_bin / "install"),
        "/usr/bin/stat": str(fake_bin / "stat"),
        "/usr/bin/uuidgen": str(fake_bin / "uuidgen"),
        "/usr/bin/pwpolicy": str(fake_bin / "pwpolicy"),
        "/bin/launchctl": str(fake_bin / "forbidden-effect"),
        "/usr/bin/curl": str(fake_bin / "forbidden-effect"),
        "/usr/bin/plutil": str(fake_bin / "forbidden-effect"),
        "/usr/bin/sudo": str(fake_bin / "forbidden-effect"),
        "/Library/LaunchDaemons/com.mastermind.executive.agent-relay.plist": str(plist_path),
        "/var/db/mastermind-agent-relay": str(runtime_root),
        "/Library/Application Support/MastermindExecutive": str(system_root),
    }
    for original, replacement in replacements.items():
        source = source.replace(original, replacement)
    _write_executable(artifact, source)
    return artifact, state_path, {
        "config": system_root / "config",
        "home": runtime_root / "home",
        "plist": plist_path,
        "release": release_root,
        "runtime": runtime_root,
        "system": system_root,
    }


def test_prepares_only_the_exact_principal_group_and_non_secret_directories_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Omitting an identity/path invariant or making run two mutate must fail."""

    artifact, state_path, paths = _fake_host_script(tmp_path)
    monkeypatch.setenv("A2_FAKE_STATE", str(state_path))
    command = ["/bin/bash", str(artifact), "--release-root", str(paths["release"])]

    first = subprocess.run(command, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    state_after_first = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_after_first["groups"]["_mastermind_agent_relay"] == {
        "GeneratedUID": "00000000-0000-4000-8000-000000000000",
        "GroupMembership": ["_mastermind_exec"],
        "PrimaryGroupID": "457",
        "RealName": "_mastermind_agent_relay service group",
    }
    assert state_after_first["users"]["_mastermind_agent_relay"] == {
        "IsHidden": "1",
        "NFSHomeDirectory": str(paths["home"]),
        "Password": "*",
        "PrimaryGroupID": "457",
        "RealName": "_mastermind_agent_relay service account",
        "UniqueID": "457",
        "UserShell": "/usr/bin/false",
    }
    for path, metadata in (
        (paths["system"], "0:0:755"),
        (paths["config"], "0:0:755"),
        (paths["runtime"], "0:0:711"),
        (paths["home"], "457:457:700"),
    ):
        assert path.is_dir()
        assert state_after_first["metadata"][str(path)] == metadata
    assert not (paths["config"] / "agent-relay.token").exists()
    assert not (paths["config"] / "agent-relay.json").exists()
    assert not paths["plist"].exists()

    second = subprocess.run(command, check=False, capture_output=True, text=True)

    assert second.returncode == 0, second.stderr
    assert json.loads(state_path.read_text(encoding="utf-8")) == state_after_first


def test_refuses_a_foreign_relay_gid_before_creating_any_partial_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Replacing exact collision refusal with creation must fail this hostile case."""

    artifact, state_path, paths = _fake_host_script(tmp_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["groups"]["foreign-service"] = {"PrimaryGroupID": "457"}
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv("A2_FAKE_STATE", str(state_path))
    before = json.loads(state_path.read_text(encoding="utf-8"))

    completed = subprocess.run(
        ["/bin/bash", str(artifact), "--release-root", str(paths["release"])],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 65
    assert "PrimaryGroupID 457 has an unexpected owner set" in completed.stderr
    assert json.loads(state_path.read_text(encoding="utf-8")) == before
    assert not paths["runtime"].exists()


def test_refuses_a_mismatched_existing_directory_before_creating_any_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Moving path validation after principal creation must fail this refusal test."""

    artifact, state_path, paths = _fake_host_script(tmp_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["metadata"][str(paths["system"])] = "0:0:700"
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv("A2_FAKE_STATE", str(state_path))
    before = json.loads(state_path.read_text(encoding="utf-8"))

    completed = subprocess.run(
        ["/bin/bash", str(artifact), "--release-root", str(paths["release"])],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 65
    assert "existing prerequisite directory differs from the reviewed identity" in completed.stderr
    assert json.loads(state_path.read_text(encoding="utf-8")) == before
    assert not paths["runtime"].exists()
