"""Exercise the real installer component functions without root or live services.

Darwin metadata/signature commands and chown are explicit OS fakes. File type,
links, modes, hashes, copy, publication and refusal flow operate on real temp files.
The production digest literals are checked separately from small fixture bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

INSTALL = Path(__file__).resolve().parents[1] / "ops/executive_os/install.sh"
MAIN = b"main-0147\n"
HELPER = b"helper-0147\n"
PREDECESSOR = b"helper-previous-generation\n"

FAKE = r'''
import json, os, shutil, stat, sys
from pathlib import Path
command, *args = sys.argv[1:]
path = Path(args[-1])
root = Path(os.environ['FIXTURE_ROOT'])
rooted = root / 'root-inodes'
known = set(rooted.read_text().split())
if path.name.startswith('.codex-code-mode-host.'):
    target = 'stage'
elif path.parent == root / 'Library/Application Support/MastermindExecutive/bin':
    target = 'installed'
elif path.is_dir():
    target = 'directory'
elif path.name == 'codex':
    target = 'main'
else:
    target = 'source'
fault = os.environ.get('FAULT', '') if target == os.environ.get('FAULT_TARGET', '') else ''
with (root/'calls').open('a') as f:
    f.write(json.dumps([command, *args])+'\n')
if command == 'stat':
    if fault == 'stat_failure': sys.exit(1)
    st = path.lstat()
    fmt = args[1]
    if fmt == '%l': print(st.st_nlink)
    elif fmt == '%Sp': print(stat.filemode(st.st_mode))
    elif fmt == '%u:%g:%Lp':
        # Only fake chown-marked inodes and the fixture's protected directory
        # ancestors are reported as root-owned; all others keep actual identity.
        trusted = str(st.st_ino) in known or path.is_dir()
        uid, gid = (0,0) if trusted else (st.st_uid,st.st_gid)
        if path == root / "Library/Application Support": gid = 80
        if fault == 'owner': uid = 501
        if fault == 'group': gid = 20
        print(f'{uid}:{gid}:{stat.S_IMODE(st.st_mode):o}')
    else: raise AssertionError(fmt)
elif command == 'ls':
    if fault == 'acl_observer_failure': sys.exit(1)
    print(stat.filemode(path.lstat().st_mode)+'@ 1 root wheel 1 Sep 29 00:00 '+str(path))
    if fault == 'acl': print(' 0: group:everyone allow write')
elif command == 'codesign':
    if fault == 'signature': sys.exit(1)
    if '--verify' not in args:
        print('TeamIdentifier='+('WRONGTEAM' if fault == 'team' else '2DC432GLL2'))
        identifier = 'codex' if path.read_bytes() == b'main-0147\n' else 'codex-code-mode-host'
        print('Identifier='+('wrong-helper' if fault == 'identifier' else identifier))
elif command == 'chown':
    with rooted.open('a') as f: f.write(str(path.lstat().st_ino)+'\n')
elif command == 'ditto':
    shutil.copyfile(args[-2], path)
    if os.environ.get('TAMPER_STAGE') == '1':
        path.write_bytes(b'corrupt after source validation\n')
    race = os.environ.get('RACE_DESTINATION')
    if race == '1':
        (path.parent/'codex-code-mode-host').write_bytes(b'foreign winner\n')
    elif race in ('directory', 'symlink_directory'):
        destination = path.parent/'codex-code-mode-host'
        if race == 'symlink_directory':
            foreign = root/'foreign-directory'; foreign.mkdir()
            destination.symlink_to(foreign, target_is_directory=True)
        else:
            destination.mkdir()
        (destination/'sentinel').write_bytes(b'untouched')
else: raise AssertionError(command)
'''


@pytest.fixture
def harness(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    binary = source / "codex"
    helper = source / "codex-code-mode-host"
    binary.write_bytes(MAIN)
    helper.write_bytes(HELPER)
    binary.chmod(0o555)
    helper.chmod(0o555)
    library = tmp_path / "Library"
    system = library / "Application Support/MastermindExecutive"
    dest = system / "bin/codex-code-mode-host"
    dest.parent.mkdir(parents=True)
    for path in (library, library / "Application Support", system, dest.parent):
        path.chmod(0o755)
    (tmp_path / "root-inodes").write_text("")
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    text = INSTALL.read_text()
    functions = text.split("# --- BEGIN Codex package component validation ---\n", 1)[1].split(
        "# --- END Codex package component validation ---", 1)[0]
    for command in ("stat", "codesign", "ditto", "chown"):
        functions = functions.replace(
            ("/usr/sbin/" if command == "chown" else "/usr/bin/") + command,
            f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))} {command}",
        )
    functions = functions.replace('/Library', str(library))
    preflight = text.split("# Check the complete package before stopping any service, even on reinstall.\n", 1)[1].split(
        'if [ -n "$CONTROL_CONFIG_SOURCE" ]; then', 1)[0]
    cleanup = text.split("leave_installed_services_stopped() {\n", 1)[1].split(
        '  /bin/launchctl disable', 1)[0]
    setup = {
        "SYSTEM_ROOT": str(system), "CODEX_BINARY": str(binary),
        "CODEX_VERSION": "0.159.2", "CODEX_SHA256": hashlib.sha256(MAIN).hexdigest(),
        "CODEX_CODE_MODE_HOST_SHA256": hashlib.sha256(HELPER).hexdigest(),
        "CODEX_CODE_MODE_HOST_PREDECESSOR_SHA256": hashlib.sha256(PREDECESSOR).hexdigest(),
        "CODEX_CODE_MODE_HOST_TEMP": "",
        "CODEX_CODE_MODE_HOST_ACTION": "",
        "PYTHON_BINARY": sys.executable,
    }

    def run(*, fault="", target="", tamper=False, race=False, replace_race=False,
            version="0.159.2", real_acl=False):
        setup["CODEX_VERSION"] = version
        script = "set -euo pipefail\n" + "\n".join(f"{k}={shlex.quote(v)}" for k, v in setup.items())
        observed_functions = functions if real_acl else functions.replace(
            "/bin/ls", f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))} ls"
        )
        script += "\n" + observed_functions + "\ncleanup() {\n" + cleanup + "}\ntrap cleanup EXIT\n"
        script += preflight + "\nprepare_codex_code_mode_host || exit 65\n"
        if replace_race:
            script += (
                'destination="$SYSTEM_ROOT/bin/codex-code-mode-host"\n'
                '/bin/chmod 0755 "$destination"\n'
                '/usr/bin/printf "raced-helper\\n" >"$destination"\n'
                '/bin/chmod 0555 "$destination"\n'
            )
        script += "install_codex_code_mode_host || exit 65\n"
        return subprocess.run(["/bin/bash", "-c", script], text=True, capture_output=True, timeout=15,
                              env={**os.environ, "FIXTURE_ROOT": str(tmp_path), "FAULT": fault,
                                   "FAULT_TARGET": target, "TAMPER_STAGE": str(int(tamper)),
                                   "RACE_DESTINATION": race if isinstance(race, str) else str(int(race))})

    def root_owned(path):
        with (tmp_path / "root-inodes").open("a") as f:
            f.write(str(path.lstat().st_ino) + "\n")

    return run, helper, binary, dest, tmp_path, root_owned


def test_exact_official_package_and_pre_mutation_wiring():
    text = INSTALL.read_text()
    assert 'CODEX_CODE_MODE_HOST_SHA256="ed79fbc9e1683feb29d73fb421f3e16932d178a459f63741754014c6c7ea6107"' in text
    assert 'CODEX_CODE_MODE_HOST_PREDECESSOR_SHA256="a059beb029cdbc989e72e23f8680be9f703cb6cf83d9598d91041f82178d018d"' in text
    assert 'CODEX_SHA256="16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704"' in text
    preflight = text.index('verify_codex_component "$CODEX_CODE_MODE_HOST_BINARY"')
    prepared = text.index('prepare_codex_code_mode_host || exit 65')
    teardown = text.index('trap leave_installed_services_stopped EXIT')
    installed = text.index('install_codex_code_mode_host || exit 65')
    assert preflight < prepared < teardown
    assert text.index('INSTALLED_CODEX="$SYSTEM_ROOT/bin/codex-$CODEX_VERSION"') < installed
    assert text.index('if [ "$ARM_PRIVILEGED_BROKER" = "1" ]; then') < installed
    assert installed < text.index('/bin/echo "installed exact Executive OS release $EXPECTED_SHA"')
    subprocess.run(["/bin/bash", "-n", str(INSTALL)], check=True)


def test_fresh_and_repeated_install_preserves_exact_inode(harness):
    run, _, _, dest, root, _ = harness
    result = run()
    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == HELPER
    assert dest.stat().st_mode & 0o777 == 0o555
    inode = dest.stat().st_ino
    result = run()
    assert result.returncode == 0, result.stderr
    assert dest.stat().st_ino == inode
    calls = [json.loads(line) for line in (root/"calls").read_text().splitlines()]
    assert sum(call[0] == "ditto" for call in calls) == 1
    assert not list(dest.parent.glob('.codex-code-mode-host.*'))


@pytest.mark.parametrize("case", ["missing", "symlink", "hardlink", "directory", "non_executable", "hash"])
def test_bad_source_refused_without_publication(harness, case):
    run, helper, _, dest, root, _ = harness
    if case == "missing": helper.unlink()
    elif case == "symlink":
        actual = helper.with_name("actual"); helper.rename(actual); helper.symlink_to(actual)
    elif case == "hardlink": os.link(helper, helper.with_name("link"))
    elif case == "directory": helper.unlink(); helper.mkdir()
    elif case == "non_executable": helper.chmod(0o444)
    elif case == "hash": helper.chmod(0o644); helper.write_bytes(b"different package")
    result = run()
    assert result.returncode == 65, result.stderr
    assert not dest.exists()
    assert '"ditto"' not in (root/"calls").read_text()


@pytest.mark.parametrize("fault", ["signature", "team", "identifier", "acl", "acl_observer_failure", "stat_failure"])
def test_source_attestation_refusals(harness, fault):
    run, _, _, dest, _, _ = harness
    assert run(fault=fault, target="source").returncode == 65
    assert not dest.exists()


def test_main_package_mismatch_and_version_refused(harness):
    run, _, binary, dest, _, _ = harness
    assert run(version="0.148.0").returncode == 65
    binary.chmod(0o644); binary.write_bytes(b"other-main")
    assert run().returncode == 65
    assert not dest.exists()


@pytest.mark.parametrize("fault", ["signature", "team", "identifier", "acl", "acl_observer_failure", "owner", "group", "stat_failure"])
def test_staged_attestation_failure_never_publishes_and_cleans(harness, fault):
    run, _, _, dest, _, _ = harness
    result = run(fault=fault, target="stage")
    assert result.returncode == 65, result.stderr
    assert not dest.exists()
    assert not list(dest.parent.glob('.codex-code-mode-host.*'))


def test_source_change_during_copy_rejected_and_stage_cleaned(harness):
    run, _, _, dest, _, _ = harness
    assert run(tamper=True).returncode == 65
    assert not dest.exists()
    assert not list(dest.parent.glob('.codex-code-mode-host.*'))


def test_publication_does_not_replace_concurrent_target(harness):
    run, _, _, dest, _, _ = harness
    assert run(race=True).returncode == 65
    assert dest.read_bytes() == b"foreign winner\n"
    assert not list(dest.parent.glob('.codex-code-mode-host.*'))


@pytest.mark.parametrize("fault", ["signature", "team", "identifier", "acl", "acl_observer_failure", "owner", "group", "stat_failure"])
def test_installed_postimage_refused(harness, fault):
    run, _, _, dest, _, _ = harness
    assert run().returncode == 0
    inode = dest.stat().st_ino
    assert run(fault=fault, target="installed").returncode == 65
    assert dest.stat().st_ino == inode
    assert dest.read_bytes() == HELPER


@pytest.mark.parametrize("case", ["symlink", "dangling_symlink", "hardlink", "directory", "mode", "hash"])
def test_bad_existing_destination_is_never_replaced(harness, case):
    run, _, _, dest, _, root_owned = harness
    if case == "directory": dest.mkdir()
    elif case in ("symlink", "dangling_symlink"):
        actual = dest.with_name("actual")
        if case == "symlink": actual.write_bytes(HELPER); actual.chmod(0o555)
        dest.symlink_to(actual)
    else:
        dest.write_bytes(b"foreign" if case == "hash" else HELPER)
        dest.chmod(0o755 if case == "mode" else 0o555)
        root_owned(dest)
        if case == "hardlink": os.link(dest, dest.with_name("second-link"))
    inode = dest.lstat().st_ino
    assert run().returncode == 65
    assert dest.lstat().st_ino == inode


def test_trusted_previous_generation_helper_is_replaced(harness):
    run, _, _, dest, _, root_owned = harness
    dest.write_bytes(PREDECESSOR)
    dest.chmod(0o555)
    root_owned(dest)
    inode = dest.lstat().st_ino
    result = run()
    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == HELPER
    assert dest.lstat().st_ino != inode
    assert not list(dest.parent.glob(".codex-code-mode-host.*"))


def test_prepared_replacement_refuses_changed_predecessor(harness):
    run, _, _, dest, _, root_owned = harness
    dest.write_bytes(PREDECESSOR)
    dest.chmod(0o555)
    root_owned(dest)
    inode = dest.lstat().st_ino
    result = run(replace_race=True)
    assert result.returncode == 65
    assert dest.lstat().st_ino == inode
    assert dest.read_bytes() == b"raced-helper\n"
    assert not list(dest.parent.glob(".codex-code-mode-host.*"))


@pytest.mark.parametrize("fault", ["owner", "group", "acl", "acl_observer_failure", "stat_failure"])
def test_untrusted_destination_ancestor_refused(harness, fault):
    run, _, _, dest, _, _ = harness
    assert run(fault=fault, target="directory").returncode == 65
    assert not dest.exists()


def test_fresh_installed_postimage_is_checked(harness):
    run, _, _, dest, _, _ = harness
    assert run(fault="signature", target="installed").returncode == 65
    assert dest.read_bytes() == HELPER


@pytest.mark.parametrize("race", ["directory", "symlink_directory"])
def test_concurrent_directory_is_not_treated_as_move_container(harness, race):
    run, _, _, dest, root, _ = harness
    assert run(race=race).returncode == 65
    assert (dest / "sentinel").read_bytes() == b"untouched"
    assert sorted(p.name for p in dest.iterdir()) == ["sentinel"]
    assert not list(dest.parent.glob('.codex-code-mode-host.*'))


@pytest.mark.skipif(sys.platform != "darwin", reason="real macOS ACL qualification")
@pytest.mark.parametrize("target", ["source", "main", "directory"])
def test_real_darwin_acl_is_refused_even_with_extended_attributes(harness, target):
    run, helper, binary, dest, _, _ = harness
    path = {"source": helper, "main": binary, "directory": dest.parent}[target]
    baseline = run(real_acl=True)
    assert baseline.returncode == 0, baseline.stderr
    original_mode = path.stat().st_mode & 0o777
    path.chmod(original_mode | 0o200)
    subprocess.run(["/usr/bin/xattr", "-w", "com.mastermind.sidecar-test", "disposable", str(path)], check=True)
    path.chmod(original_mode)
    try:
        subprocess.run(["/bin/chmod", "+a", "everyone allow write", str(path)], check=True)
        mode = subprocess.check_output(["/usr/bin/stat", "-f", "%Sp", str(path)], text=True)
        listing = subprocess.check_output(["/bin/ls", "-lde", str(path)], text=True)
        assert "+" not in mode
        assert "@" in listing.splitlines()[0]
        assert "group:everyone allow " in listing
        result = run(real_acl=True)
        assert result.returncode == 65, result.stderr
        assert not list(dest.parent.glob(".codex-code-mode-host.*"))
    finally:
        subprocess.run(["/bin/chmod", "-N", str(path)], check=True)
        path.chmod(original_mode | 0o200)
        subprocess.run(["/usr/bin/xattr", "-d", "com.mastermind.sidecar-test", str(path)], check=True)
        path.chmod(original_mode)
