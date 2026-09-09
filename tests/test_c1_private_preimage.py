from __future__ import annotations

import importlib
import json
import math
import os
import plistlib
import stat
import subprocess
from dataclasses import dataclass

import pytest


MODULE = "ops.executive_os.c1_private_preimage"
SHA = "a" * 40
TREE = "b" * 40


def subject():
    return importlib.import_module(MODULE)


def snapshot(**changes):
    value = {
        "unsafe": False,
        "effect_unknown": False,
        "surface_present": False,
        "matching_installation": False,
        "coherent_stale_installation": False,
        "services": [],
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (snapshot(), "ABSENT_CLEAN"),
        (snapshot(surface_present=True, matching_installation=True), "MATCHING_STOPPED"),
        (snapshot(surface_present=True, coherent_stale_installation=True), "STALE_STOPPED"),
        (
            snapshot(
                surface_present=True,
                matching_installation=True,
                services=[{"active": True, "owned": True}],
            ),
            "ACTIVE_OWNED",
        ),
        (
            snapshot(
                surface_present=True,
                matching_installation=True,
                services=[{"active": True, "owned": False}],
            ),
            "ACTIVE_FOREIGN",
        ),
        (snapshot(effect_unknown=True), "EFFECT_UNKNOWN"),
        (snapshot(unsafe=True, effect_unknown=True), "UNSAFE"),
    ],
)
def test_classifier_uses_closed_precedence(value, expected):
    assert subject().classify_preimage(value) == expected


def test_canonical_receipt_is_finite_sorted_compact_utf8_with_one_newline():
    module = subject()
    value = {"z": [1, True, None], "a": "café"}
    encoded = module.canonical_receipt(value)
    assert encoded == b'{"a":"caf\xc3\xa9","z":[1,true,null]}\n'
    assert module.canonical_receipt(value) == encoded
    for nonfinite in (math.nan, math.inf, -math.inf):
        with pytest.raises(module.PreimageRefusal) as error:
            module.canonical_receipt({"value": nonfinite})
        assert error.value.code == "NONFINITE_RECEIPT"


def test_public_contract_enums_are_closed():
    module = subject()
    assert module.SCHEMA == "mastermind.c1_private_preimage/v1"
    assert module.STATES == frozenset({"FACTS", "DEGRADED", "REFUSED", "UNSETTLED"})
    assert module.CLASSIFICATIONS == frozenset(
        {
            "UNSAFE",
            "EFFECT_UNKNOWN",
            "ACTIVE_FOREIGN",
            "ACTIVE_OWNED",
            "MATCHING_STOPPED",
            "STALE_STOPPED",
            "ABSENT_CLEAN",
            "UNKNOWN",
        }
    )


def test_strict_json_rejects_duplicate_keys_and_projects_only_whitelist():
    module = subject()
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_json(
            b'{"schema_version":"one","schema_version":"two"}',
            fields={"schema_version": str},
        )
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"

    assert module.parse_projected_json(
        b'{"schema_version":"v1","secret":"must-not-escape"}',
        fields={"schema_version": str},
    ) == {"schema_version": "v1"}

    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_json(b'{"schema_version":7}', fields={"schema_version": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"


def test_plist_projection_rejects_malformed_and_unexpected_scalar_type():
    module = subject()
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_plist(b"not a plist", fields={"Label": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"

    payload = (
        b'<?xml version="1.0"?><plist version="1.0"><dict>'
        b"<key>Label</key><integer>7</integer></dict></plist>"
    )
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_plist(payload, fields={"Label": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"


def test_var_alias_is_the_only_accepted_lexical_alias():
    module = subject()
    expected = "/var/run/mastermind-executive/ceo-ingress.sock"
    assert module.validate_named_path(expected, "/private" + expected) == expected
    assert module.validate_named_path(expected, expected) == expected
    for observed in (
        "/tmp/elsewhere",
        "/private/tmp/elsewhere",
        "/private/var/run/../db/foreign",
    ):
        with pytest.raises(module.PreimageRefusal) as error:
            module.validate_named_path(expected, observed)
        assert error.value.code == "PATH_ESCAPE"


@dataclass
class Completed:
    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""


def test_command_adapter_has_exact_allowlist_and_nonmutating_subprocess_contract():
    module = subject()
    calls = []

    def runner(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return Completed(stdout=b"disabled services = {\n}\n")

    adapter = module.CommandAdapter(runner=runner)
    result = adapter.run(("/bin/launchctl", "print-disabled", "system"))
    assert result == {"status": "ok", "stdout": "disabled services = {\n}\n"}
    argv, kwargs = calls[0]
    assert argv == ("/bin/launchctl", "print-disabled", "system")
    assert kwargs == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
        "timeout": 5,
        "shell": False,
        "close_fds": True,
    }

    forbidden = (
        ("sudo", "launchctl", "print-disabled", "system"),
        ("/bin/launchctl", "kickstart", "system/com.mastermind.executive.control"),
        ("/bin/ps", "aux"),
        ("/usr/bin/stat", "-f", "%Sp", "/tmp/not-frozen"),
    )
    for argv in forbidden:
        with pytest.raises(module.PreimageRefusal) as error:
            adapter.run(argv)
        assert error.value.code == "COMMAND_REFUSED"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("completion", "code"),
    [
        (Completed(returncode=1, stderr=b"private detail"), "COMMAND_NONZERO"),
        (Completed(stdout=b"x" * (64 * 1024 + 1)), "COMMAND_OUTPUT_OVERSIZED"),
    ],
)
def test_command_adapter_closes_nonzero_and_oversized_output(completion, code):
    module = subject()
    adapter = module.CommandAdapter(runner=lambda *_args, **_kwargs: completion)
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/launchctl", "print-disabled", "system"))
    assert error.value.code == code
    assert "private detail" not in str(error.value)


def test_command_timeout_is_unsettled_and_not_retried():
    module = subject()
    calls = 0

    def timeout(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(cmd="probe", timeout=5)

    with pytest.raises(module.PreimageUnsettled) as error:
        module.CommandAdapter(runner=timeout).run(
            ("/bin/launchctl", "print-disabled", "system")
        )
    assert error.value.code == "COMMAND_TIMEOUT"
    assert calls == 1


def test_launchd_and_process_parsers_are_closed_and_reject_ambiguity():
    module = subject()
    assert module.parse_launchd_state("state = running\npid = 412\n") == {
        "active": True,
        "pid": 412,
        "state": "running",
    }
    assert module.parse_process_identity("450 450 412 1\n", expected_pid=412) == {
        "uid": 450,
        "gid": 450,
        "pid": 412,
        "ppid": 1,
    }
    for text in ("state = running\npid = 1\npid = 2\n", "state = running\npid = 0\n"):
        with pytest.raises(module.PreimageUnsettled):
            module.parse_launchd_state(text)
    with pytest.raises(module.PreimageUnsettled):
        module.parse_process_identity("451 451 99 1\n", expected_pid=412)


def test_metadata_projection_contains_no_content_or_hash():
    module = subject()
    info = os.stat_result((stat.S_IFREG | 0o400, 2, 3, 1, 450, 450, 99, 1, 2, 3))
    projected = module.project_metadata("/fixed/token", info)
    assert set(projected) == {
        "path",
        "exists",
        "type",
        "device",
        "inode",
        "link_count",
        "uid",
        "gid",
        "mode",
        "size",
        "mtime_ns",
        "ctime_ns",
    }
    assert not ({"bytes", "content", "hash", "sha256", "value"} & set(projected))


@pytest.mark.parametrize(
    ("state", "exit_code"),
    [("FACTS", 0), ("DEGRADED", 2), ("REFUSED", 2), ("UNSETTLED", 3)],
)
def test_cli_emits_canonical_receipt_and_maps_exit(monkeypatch, capsysbinary, state, exit_code):
    module = subject()
    receipt = {
        "schema": module.SCHEMA,
        "observed_at": "2026-09-09T12:00:00+00:00",
        "expected_release_sha": SHA,
        "expected_tree_sha": TREE,
        "state": state,
        "classification": "ABSENT_CLEAN" if state == "FACTS" else "UNKNOWN",
        "reason_codes": [],
        "facts": {},
        "probe_counts": {},
        "source_limits": {},
        "mutation_count": 0,
    }
    monkeypatch.setattr(module, "collect_preimage", lambda **_kwargs: receipt)
    assert (
        module.main(
            ["--expected-release-sha", SHA, "--expected-tree-sha", TREE],
            _platform="darwin",
            _uid=0,
            _euid=0,
        )
        == exit_code
    )
    assert capsysbinary.readouterr().out == module.canonical_receipt(receipt)


def test_cli_refuses_arguments_platform_and_euid_before_collection(monkeypatch, capsysbinary):
    module = subject()
    called = False

    def collect(**_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(module, "collect_preimage", collect)
    assert module.main(["--expected-release-sha", "BAD", "--expected-tree-sha", TREE]) == 64
    args = ["--expected-release-sha", SHA, "--expected-tree-sha", TREE]
    assert module.main(args, _platform="linux", _euid=0) == 64
    assert module.main(args, _platform="darwin", _euid=501) == 64
    assert capsysbinary.readouterr().out == b""
    assert called is False


def test_describe_is_static_and_does_not_collect(monkeypatch, capsysbinary):
    module = subject()
    monkeypatch.setattr(
        module,
        "collect_preimage",
        lambda **_kwargs: pytest.fail("describe must not collect"),
    )
    assert module.main(["--describe"], _platform="linux", _euid=501) == 0
    described = json.loads(capsysbinary.readouterr().out)
    assert described["schema"] == module.SCHEMA
    assert described["mutation_count"] == 0
    assert described["command_allowlist"]


def test_bounded_file_read_rejects_final_symlink_and_oversize(tmp_path):
    module = subject()
    target = tmp_path / "target"
    target.write_bytes(b"safe")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(module.PreimageRefusal) as error:
        module._read_bounded_file(os.fspath(link))
    assert error.value.code == "PATH_ESCAPE"

    target.write_bytes(b"x" * (module.MAX_CONTENT_BYTES + 1))
    with pytest.raises(module.PreimageRefusal) as error:
        module._read_bounded_file(os.fspath(target))
    assert error.value.code == "CONTENT_OVERSIZED"


def test_bounded_file_read_uses_readonly_nofollow_cloexec_and_detects_torn_identity(
    tmp_path, monkeypatch
):
    module = subject()
    target = tmp_path / "document"
    target.write_bytes(b"{}")
    real_open = module.os.open
    flags_seen = []

    def tracked_open(path, flags):
        flags_seen.append(flags)
        return real_open(path, flags)

    monkeypatch.setattr(module.os, "open", tracked_open)
    assert module._read_bounded_file(os.fspath(target)) == b"{}"
    assert flags_seen[0] & os.O_ACCMODE == os.O_RDONLY
    assert flags_seen[0] & getattr(os, "O_NOFOLLOW", 0)
    assert flags_seen[0] & getattr(os, "O_CLOEXEC", 0)

    real_lstat = module.os.lstat
    calls = 0

    def torn_lstat(path):
        nonlocal calls
        calls += 1
        value = real_lstat(path)
        if calls == 2:
            values = list(value)
            values[1] += 1
            return os.stat_result(values)
        return value

    monkeypatch.setattr(module.os, "lstat", torn_lstat)
    with pytest.raises(module.PreimageUnsettled) as error:
        module._read_bounded_file(os.fspath(target))
    assert error.value.code == "FILESYSTEM_TORN"


class EmptyFilesystem:
    def __init__(self):
        self.paths = []
        self.reads = []

    def metadata(self, path):
        self.paths.append(path)
        return {"path": path, "exists": False}

    def read(self, path):
        self.reads.append(path)
        raise AssertionError("absent paths must not be read")


class AbsentCommands:
    def __init__(self):
        self.calls = []

    def run(self, argv):
        self.calls.append(tuple(argv))
        if tuple(argv) == ("/bin/launchctl", "print-disabled", "system"):
            entries = "".join(f'    "{label}" => true\n' for label in subject().LABELS)
            return {"status": "ok", "stdout": f"disabled services = {{\n{entries}}}\n"}
        raise subject().PreimageUnsettled("COMMAND_NONZERO")


class MissingPrincipals:
    def lookup(self, name):
        assert name in subject().PRINCIPALS
        return None


def test_collect_absent_clean_is_deterministic_and_has_zero_mutations():
    module = subject()
    filesystem = EmptyFilesystem()
    commands = AbsentCommands()
    fixed = lambda: "2026-09-09T19:00:00+00:00"
    kwargs = dict(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=commands,
        principals=MissingPrincipals(),
        clock=fixed,
        platform="darwin",
        uid=0,
        euid=0,
    )
    first = module.collect_preimage(**kwargs)
    second = module.collect_preimage(**kwargs)
    assert first["state"] == "FACTS"
    assert first["classification"] == "ABSENT_CLEAN"
    assert first["mutation_count"] == 0
    assert module.canonical_receipt(first) == module.canonical_receipt(second)
    assert all(
        call[:2] == ("/bin/launchctl", "print-disabled")
        or call[:2] == ("/bin/launchctl", "print")
        for call in commands.calls
    )
    assert not filesystem.reads


def test_aggregate_content_ceiling_is_enforced_before_extra_read():
    module = subject()
    with pytest.raises(module.PreimageRefusal) as error:
        module.enforce_content_budget([module.MAX_CONTENT_BYTES] * 9 + [1])
    assert error.value.code == "CONTENT_AGGREGATE_OVERSIZED"


def test_acl_marker_requires_stable_identity_and_closed_marker():
    module = subject()
    metadata = {"exists": True, "device": 4, "inode": 9}

    class FS:
        def metadata(self, _path):
            return dict(metadata)

    class Commands:
        def __init__(self, marker):
            self.marker = marker

        def run(self, _argv):
            return {"status": "ok", "stdout": self.marker}

    assert module.inspect_acl(FS(), Commands("-rw-r--r-- \n"), module.CONTROL_CONFIG) is False
    assert module.inspect_acl(FS(), Commands("-rw-r--r--+\n"), module.CONTROL_CONFIG) is True
    with pytest.raises(module.PreimageUnsettled) as error:
        module.inspect_acl(FS(), Commands("unknown\n"), module.CONTROL_CONFIG)
    assert error.value.code == "ACL_UNKNOWN"


def test_installation_evaluation_distinguishes_matching_stale_and_conflicting():
    module = subject()
    documents = module.expected_document_fixture(SHA, TREE)
    assert module.evaluate_installation(documents, SHA, TREE) == {
        "matching_installation": True,
        "coherent_stale_installation": False,
        "effect_unknown": False,
    }

    stale = module.expected_document_fixture("c" * 40, "d" * 40)
    assert module.evaluate_installation(stale, SHA, TREE) == {
        "matching_installation": False,
        "coherent_stale_installation": True,
        "effect_unknown": False,
    }

    conflicting = dict(documents)
    conflicting[module.CONTROL_CONFIG] = {
        **conflicting[module.CONTROL_CONFIG],
        "proof_base_sha": "c" * 40,
    }
    assert module.evaluate_installation(conflicting, SHA, TREE)["effect_unknown"] is True


@pytest.mark.parametrize(
    ("label", "uid", "gid"),
    [
        ("com.mastermind.executive.control", 450, 450),
        ("com.mastermind.executive.worker.codex", 451, 451),
        ("com.mastermind.executive.backup", 450, 450),
        ("com.mastermind.executive.sol-state-relay", 452, 452),
        ("com.mastermind.executive.agent-relay", 457, 457),
    ],
)
def test_service_ownership_binds_label_plist_user_and_process_identity(label, uid, gid):
    module = subject()
    plist = {"Label": label, "UserName": module.SERVICE_OWNERS[label][0]}
    process = {"uid": uid, "gid": gid, "pid": 99, "ppid": 1}
    assert module.service_owned(label, plist, process) is True
    assert module.service_owned(label, {**plist, "Label": "foreign"}, process) is False
    assert module.service_owned(label, plist, {**process, "uid": 999}) is False


def test_disabled_state_parser_requires_one_closed_boolean_per_frozen_label():
    module = subject()
    lines = ["disabled services = {"]
    for index, label in enumerate(module.LABELS):
        value = "true" if index % 2 else "false"
        lines.append(f'    "{label}" => {value}')
    lines.append("}")
    parsed = module.parse_disabled_state("\n".join(lines) + "\n")
    assert set(parsed) == set(module.LABELS)
    assert parsed[module.LABELS[0]] is False
    with pytest.raises(module.PreimageUnsettled):
        module.parse_disabled_state("disabled services = {\n}\n")
    with pytest.raises(module.PreimageUnsettled):
        module.parse_disabled_state("\n".join(lines + [f'"{module.LABELS[0]}" => true']) + "\n")


class InstalledFilesystem:
    def __init__(self, module):
        release_root = f"{module.SYSTEM_ROOT}/releases/{SHA}"
        self.manifest_path = f"{release_root}/.executive-release-manifest.json"
        self.payloads = {
            module.CONTROL_CONFIG: json.dumps(
                {
                    "schema_version": "mastermind.executive_control_config/v1",
                    "proof_base_sha": SHA,
                    "ignored": "not projected",
                }
            ).encode(),
            module.WORKER_CONFIG: (
                b'{"schema_version":"mastermind.executive_worker_broker_config/v4"}'
            ),
            module.PYTHON_PROVENANCE: (
                b'{"schema_version":"mastermind.executive_python_runtime/v1"}'
            ),
            module.CODEX_ATTESTATION: (
                b'{"schema_version":"mastermind.executive_codex_attestation/v1"}'
            ),
            self.manifest_path: json.dumps(
                {
                    "schema_version": "mastermind.executive_release_manifest/v1",
                    "commit_sha": SHA,
                    "tree_sha": TREE,
                    "entries": ["not projected"],
                }
            ).encode(),
        }
        for label, path in zip(module.LABELS, module.PLISTS, strict=True):
            self.payloads[path] = plistlib.dumps(
                {
                    "Label": label,
                    "UserName": module.SERVICE_OWNERS[label][0],
                    "ProgramArguments": [f"{release_root}/entrypoint.py"],
                    "EnvironmentVariables": {"PRIVATE": "not projected"},
                }
            )
        self.present = set(self.payloads) | {release_root}

    def metadata(self, path):
        if path not in self.present:
            return {"path": path, "exists": False}
        return {
            "path": path,
            "exists": True,
            "type": "file" if path in self.payloads else "directory",
            "device": 1,
            "inode": abs(hash(path)),
            "link_count": 1,
            "uid": 0,
            "gid": 0,
            "mode": 0o440 if path in self.payloads else 0o755,
            "size": len(self.payloads.get(path, b"")),
            "mtime_ns": 1,
            "ctime_ns": 1,
        }

    def read(self, path):
        return self.payloads[path]


class InstalledPrincipals:
    def lookup(self, name):
        expected = subject().PRINCIPALS[name]
        return {
            "name": name,
            **expected,
            "group_gid": expected["gid"],
        }


class InstalledCommands:
    def __init__(self, *, foreign_active=False):
        self.foreign_active = foreign_active

    def run(self, argv):
        module = subject()
        command = tuple(argv)
        if command[:3] == ("/usr/bin/stat", "-f", "%Sp"):
            return {"status": "ok", "stdout": "-r--r----- \n"}
        if command == ("/bin/launchctl", "print-disabled", "system"):
            entries = "".join(f'    "{label}" => true\n' for label in module.LABELS)
            return {"status": "ok", "stdout": f"disabled services = {{\n{entries}}}\n"}
        if command == (
            "/bin/launchctl",
            "print",
            "system/com.mastermind.executive.control",
        ) and self.foreign_active:
            return {"status": "ok", "stdout": "state = running\npid = 99\n"}
        if command[:3] == ("/bin/ps", "-o", "uid=,gid=,pid=,ppid="):
            return {"status": "ok", "stdout": "999 999 99 1\n"}
        raise module.PreimageUnsettled("COMMAND_NONZERO")


def collect_installed(*, foreign_active=False):
    module = subject()
    return module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=InstalledFilesystem(module),
        commands=InstalledCommands(foreign_active=foreign_active),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )


def test_collect_matching_stopped_projects_only_public_documents():
    receipt = collect_installed()
    assert receipt["state"] == "FACTS"
    assert receipt["classification"] == "MATCHING_STOPPED"
    assert receipt["reason_codes"] == []
    serialized = subject().canonical_receipt(receipt)
    assert b"PRIVATE" not in serialized
    assert b"not projected" not in serialized


def test_collect_active_process_principal_mismatch_is_foreign():
    receipt = collect_installed(foreign_active=True)
    assert receipt["state"] == "FACTS"
    assert receipt["classification"] == "ACTIVE_FOREIGN"


@pytest.mark.parametrize(
    ("exception", "state", "classification"),
    [
        ("PATH_ESCAPE", "FACTS", "UNSAFE"),
        ("FILESYSTEM_DENIED", "UNSETTLED", "UNKNOWN"),
    ],
)
def test_collection_closes_filesystem_safety_and_observation_failures(
    exception, state, classification
):
    module = subject()

    class FailingFilesystem:
        def metadata(self, _path):
            if exception == "PATH_ESCAPE":
                raise module.PreimageRefusal(exception)
            raise module.PreimageUnsettled(exception)

    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=FailingFilesystem(),
        commands=AbsentCommands(),
        principals=MissingPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["state"] == state
    assert receipt["classification"] == classification
    assert receipt["reason_codes"] == [exception]
    assert receipt["mutation_count"] == 0
