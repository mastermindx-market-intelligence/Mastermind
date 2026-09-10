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


def test_launchctl_exit_113_requires_exact_absence_grammar():
    module = subject()
    label = module.LABELS[0]
    argv = ("/bin/launchctl", "print", f"system/{label}")
    accepted = Completed(
        returncode=113,
        stderr=f'Could not find service "{label}" in domain for system\n'.encode(),
    )
    assert module.CommandAdapter(runner=lambda *_a, **_k: accepted).run(argv) == {
        "status": "absent",
        "stdout": "",
    }
    rejected = Completed(returncode=113, stderr=b"permission denied\n")
    with pytest.raises(module.PreimageUnsettled) as error:
        module.CommandAdapter(runner=lambda *_a, **_k: rejected).run(argv)
    assert error.value.code == "COMMAND_NONZERO"


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
    for text in ("", "450 450 412\n", "450 450 412 nope\n"):
        with pytest.raises(module.PreimageUnsettled) as error:
            module.parse_process_identity(text, expected_pid=412)
        assert error.value.code == "MALFORMED_PROCESS"


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
    assert flags_seen[0] & getattr(os, "O_NONBLOCK", 0)

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

    def read(self, path, *, expected=None):
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
        return {"status": "absent", "stdout": ""}


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
    assert module.service_owned(
        label,
        plist,
        process,
        program_matches=True,
        arguments_match=True,
        release_matches=True,
    ) is True
    assert (
        module.service_owned(
            label,
            {**plist, "Label": "foreign"},
            process,
            program_matches=True,
            arguments_match=True,
            release_matches=True,
        )
        is False
    )
    assert (
        module.service_owned(
            label,
            plist,
            {**process, "uid": 999},
            program_matches=True,
            arguments_match=True,
            release_matches=True,
        )
        is False
    )
    assert module.service_owned(
        label,
        plist,
        process,
        program_matches=False,
        arguments_match=True,
        release_matches=True,
    ) is False
    assert module.service_owned(
        label,
        plist,
        process,
        program_matches=True,
        arguments_match=False,
        release_matches=True,
    ) is False
    assert module.service_owned(
        label,
        plist,
        process,
        program_matches=True,
        arguments_match=True,
        release_matches=False,
    ) is False


def test_loaded_program_expectation_covers_every_frozen_label():
    module = subject()
    expected = {
        "com.mastermind.executive.control": module.PYTHON_BINARY,
        "com.mastermind.executive.worker.codex": module.PYTHON_BINARY,
        "com.mastermind.executive.backup": "/bin/bash",
        "com.mastermind.executive.sol-state-relay": module.PYTHON_BINARY,
        "com.mastermind.executive.agent-relay": module.PYTHON_BINARY,
    }
    assert {
        label: module.expected_loaded_program(label, SHA)
        for label in module.LABELS
    } == expected


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
        expected = module.expected_document_fixture(SHA, TREE)
        self.payloads = {}
        for path in (
            module.CONTROL_CONFIG,
            module.WORKER_CONFIG,
            module.PYTHON_PROVENANCE,
            module.CODEX_ATTESTATION,
        ):
            value = {**expected[path], "ignored": "not projected"}
            if path == module.PYTHON_PROVENANCE:
                value.update(
                    {
                        "prior_runtime_archive": "",
                        "prior_runtime_receipt_archive": "",
                    }
                )
            if path == module.CODEX_ATTESTATION:
                value.update(
                    {
                        "recorded_at": "2026-09-09T19:00:00+00:00",
                        "identity": {
                            "device": 1,
                            "inode": 2,
                            "size": 3,
                            "mode": 0o755,
                            "uid": 0,
                            "gid": 0,
                            "mtime_ns": 4,
                            "ctime_ns": 5,
                        },
                    }
                )
            self.payloads[path] = json.dumps(value).encode()
        self.payloads[self.manifest_path] = json.dumps(
            {**expected["release_manifest"], "entries": ["not projected"]}
        ).encode()
        for label, path in zip(module.LABELS, module.PLISTS, strict=True):
            if label == "com.mastermind.executive.agent-relay":
                arguments = [
                    module.PYTHON_BINARY,
                    "-I",
                    "-S",
                    "-B",
                    f"{release_root}/scripts/slack_agent_dialogue_service.py",
                    "--socket-path",
                    "/var/run/mastermind-agent-relay/agent-relay.sock",
                    "--token-file",
                    f"{module.SYSTEM_ROOT}/config/agent-relay.token",
                    "--workspace-id",
                    "T0BRD2AQXQV",
                    "--channel-id",
                    "C0BSBM78V1N",
                    "--bot-user-id",
                    "U0BRGTF1H26",
                    "--allowed-peer-uid",
                    "450",
                    "--allowed-sol-user-id",
                    "U0BRETDUAS2",
                    "--allowed-sol-user-id",
                    "U0BSB73JWNL",
                    "--allowed-parent-user-id",
                    "U0BRETDUAS2",
                    "--dialogue-coordination-socket-path",
                    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
                ]
            else:
                arguments = module.expected_program_arguments(label, SHA)
            self.payloads[path] = plistlib.dumps(
                {
                    "Label": label,
                    "UserName": module.SERVICE_OWNERS[label][0],
                    "GroupName": module.SERVICE_OWNERS[label][0],
                    "WorkingDirectory": release_root,
                    "ProgramArguments": arguments,
                    "EnvironmentVariables": {"PRIVATE": "not projected"},
                }
            )
        self.present = set(self.payloads) | {release_root}
        self.metadata_overrides = {}

    def metadata(self, path):
        if path in self.metadata_overrides:
            return {"path": path, "exists": True, **self.metadata_overrides[path]}
        if path not in self.present:
            return {"path": path, "exists": False}
        contracts = {
            **{plist: (0, 0, 0o644) for plist in subject().PLISTS},
            subject().CONTROL_CONFIG: (0, 450, 0o440),
            subject().WORKER_CONFIG: (0, 451, 0o440),
            subject().PYTHON_PROVENANCE: (0, 0, 0o400),
            subject().CODEX_ATTESTATION: (0, 451, 0o440),
            self.manifest_path: (0, 0, 0o444),
        }
        uid, gid, mode = contracts.get(path, (0, 0, 0o755))
        return {
            "path": path,
            "exists": True,
            "type": "file" if path in self.payloads else "directory",
            "device": 1,
            "inode": abs(hash(path)),
            "link_count": 1,
            "uid": uid,
            "gid": gid,
            "mode": mode,
            "size": len(self.payloads.get(path, b"")),
            "mtime_ns": 1,
            "ctime_ns": 1,
        }

    def read(self, path, *, expected=None):
        assert expected["inode"] == abs(hash(path))
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
            return {
                "status": "ok",
                "stdout": (
                    f"program = {module.PYTHON_BINARY}\n"
                    "state = running\npid = 99\n"
                    "arguments = {\n"
                    + "\n".join(module.expected_program_arguments(module.LABELS[0], SHA))
                    + "\n}\n"
                ),
            }
        if command[:3] == ("/bin/ps", "-o", "uid=,gid=,pid=,ppid="):
            return {"status": "ok", "stdout": "999 999 99 1\n"}
        return {"status": "absent", "stdout": ""}


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


def metadata_fixture(*, kind="file", uid=452, gid=452, mode=0o400):
    return {
        "type": kind,
        "device": 1,
        "inode": 987,
        "link_count": 1,
        "uid": uid,
        "gid": gid,
        "mode": mode,
        "size": 12,
        "mtime_ns": 1,
        "ctime_ns": 1,
    }


@pytest.mark.parametrize(
    "override",
    [
        metadata_fixture(mode=0o644),
        metadata_fixture(kind="directory", mode=0o700),
    ],
)
def test_metadata_contract_rejects_world_readable_or_wrong_type_relay_token(override):
    module = subject()
    filesystem = InstalledFilesystem(module)
    token_path = f"{module.SYSTEM_ROOT}/config/sol-state-relay.token"
    filesystem.metadata_overrides[token_path] = override
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["classification"] == "UNSAFE"
    assert receipt["reason_codes"] == ["UNSAFE_METADATA"]


def test_metadata_contract_preserves_canonical_relay_token_and_release_root():
    module = subject()
    filesystem = InstalledFilesystem(module)
    token_path = f"{module.SYSTEM_ROOT}/config/sol-state-relay.token"
    filesystem.metadata_overrides[token_path] = metadata_fixture()
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert "UNSAFE_METADATA" not in receipt["reason_codes"]


def test_release_root_without_service_traversal_is_unsafe():
    module = subject()
    filesystem = InstalledFilesystem(module)
    release_root = f"{module.SYSTEM_ROOT}/releases/{SHA}"
    filesystem.metadata_overrides[release_root] = metadata_fixture(
        kind="directory", uid=0, gid=0, mode=0o700
    )
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["classification"] == "UNSAFE"
    assert receipt["classification"] != "MATCHING_STOPPED"
    assert receipt["reason_codes"] == ["UNSAFE_METADATA"]


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


def test_collect_coherent_older_documents_without_expected_manifest_is_stale():
    module = subject()
    stale_sha = "c" * 40
    filesystem = InstalledFilesystem(module)
    control = json.loads(filesystem.payloads[module.CONTROL_CONFIG])
    control.update(
        {
            "proof_base_sha": stale_sha,
            "proof_source_repository": (
                f"{module.RUNTIME_ROOT}/control/admin-checkout/{stale_sha}"
            ),
        }
    )
    filesystem.payloads[module.CONTROL_CONFIG] = json.dumps(control).encode()
    stale_root = f"{module.SYSTEM_ROOT}/releases/{stale_sha}"
    for label, path in zip(module.LABELS, module.PLISTS, strict=True):
        value = plistlib.loads(filesystem.payloads[path])
        value["WorkingDirectory"] = stale_root
        if label == "com.mastermind.executive.agent-relay":
            value["ProgramArguments"][4] = (
                f"{stale_root}/scripts/slack_agent_dialogue_service.py"
            )
        else:
            value["ProgramArguments"] = module.expected_program_arguments(
                label, stale_sha
            )
        filesystem.payloads[path] = plistlib.dumps(value)
    filesystem.payloads.pop(filesystem.manifest_path)
    filesystem.present.remove(filesystem.manifest_path)
    filesystem.present.remove(f"{module.SYSTEM_ROOT}/releases/{SHA}")
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["classification"] == "STALE_STOPPED"
    encoded = module.canonical_receipt(receipt)
    assert stale_sha.encode() not in encoded

    class ActiveStaleCommands(InstalledCommands):
        def run(self, argv):
            command = tuple(argv)
            if command == (
                "/bin/launchctl",
                "print",
                "system/com.mastermind.executive.control",
            ):
                arguments = "\n".join(
                    module.expected_program_arguments(module.LABELS[0], stale_sha)
                )
                return {
                    "status": "ok",
                    "stdout": (
                        f"program = {module.PYTHON_BINARY}\n"
                        "state = running\npid = 99\n"
                        f"arguments = {{\n{arguments}\n}}\n"
                    ),
                }
            if command == (
                "/bin/ps",
                "-o",
                "uid=,gid=,pid=,ppid=",
                "-p",
                "99",
            ):
                return {"status": "ok", "stdout": "450 450 99 1\n"}
            return super().run(argv)

    active_stale = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=ActiveStaleCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert active_stale["classification"] == "ACTIVE_FOREIGN"

    missing_principals = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=MissingPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert missing_principals["classification"] == "EFFECT_UNKNOWN"


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


def test_generic_launchctl_nonzero_remains_unsettled():
    module = subject()

    class Commands(AbsentCommands):
        def run(self, argv):
            if tuple(argv) == ("/bin/launchctl", "print-disabled", "system"):
                return super().run(argv)
            raise module.PreimageUnsettled("COMMAND_NONZERO")

    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=EmptyFilesystem(),
        commands=Commands(),
        principals=MissingPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["state"] == "UNSETTLED"
    assert receipt["classification"] == "UNKNOWN"


def test_residual_socket_and_principals_only_are_never_absent_clean():
    module = subject()
    filesystem = EmptyFilesystem()
    residual = module.METADATA_PATHS[-1]

    def metadata(path):
        if path != residual:
            return {"path": path, "exists": False}
        return {
            "path": path,
            "exists": True,
            "type": "socket",
            "device": 1,
            "inode": 2,
            "link_count": 1,
            "uid": 457,
            "gid": 457,
            "mode": 0o660,
            "size": 0,
            "mtime_ns": 1,
            "ctime_ns": 1,
        }

    filesystem.metadata = metadata
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=MissingPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["classification"] == "EFFECT_UNKNOWN"

    principals_only = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=EmptyFilesystem(),
        commands=AbsentCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert principals_only["classification"] == "EFFECT_UNKNOWN"


def test_unknown_launchd_state_and_pid_relationship_are_unsettled():
    module = subject()
    for value in (
        "state = nonsense\n",
        "state = nonsense\npid = 99\n",
        "state = waiting\npid = 99\n",
        "state = running\n",
    ):
        with pytest.raises(module.PreimageUnsettled) as error:
            module.parse_launchd_state(value)
        assert error.value.code == "MALFORMED_LAUNCHD"


def test_documented_ps_command_reaches_runner_and_wrong_uid_stays_foreign():
    module = subject()
    calls = []

    def runner(argv, **_kwargs):
        calls.append(tuple(argv))
        return Completed(stdout=b"450 450 99 1\n")

    result = module.CommandAdapter(runner=runner).run(
        ("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99")
    )
    assert result["status"] == "ok"
    assert calls == [("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99")]
    assert collect_installed(foreign_active=True)["classification"] == "ACTIVE_FOREIGN"


@pytest.mark.parametrize(
    ("process_line", "classification"),
    [
        (b"450 450 99 1\n", "ACTIVE_OWNED"),
        (b"450 450 99 777\n", "ACTIVE_FOREIGN"),
        (b"999 999 99 1\n", "ACTIVE_FOREIGN"),
    ],
)
def test_command_adapter_is_joined_to_active_service_ownership(
    process_line, classification
):
    module = subject()
    control = module.LABELS[0]

    def runner(argv, **_kwargs):
        command = tuple(argv)
        if command[:3] == ("/usr/bin/stat", "-f", "%Sp"):
            return Completed(stdout=b"-r--r-----\n")
        if command == ("/bin/launchctl", "print-disabled", "system"):
            entries = b"".join(
                f'    "{label}" => true\n'.encode() for label in module.LABELS
            )
            return Completed(stdout=b"disabled services = {\n" + entries + b"}\n")
        if command == ("/bin/launchctl", "print", f"system/{control}"):
            return Completed(
                stdout=(
                    f"program = {module.PYTHON_BINARY}\n"
                    "state = running\npid = 99\n"
                    "arguments = {\n"
                    + "\n".join(module.expected_program_arguments(control, SHA))
                    + "\n}\n"
                ).encode()
            )
        if command[:2] == ("/bin/launchctl", "print"):
            label = command[2].removeprefix("system/")
            return Completed(
                returncode=113,
                stderr=(
                    f'Could not find service "{label}" in domain for system\n'.encode()
                ),
            )
        if command == ("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"):
            return Completed(stdout=process_line)
        raise AssertionError(command)

    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=InstalledFilesystem(module),
        commands=module.CommandAdapter(runner=runner),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["classification"] == classification


def test_duplicate_projected_plist_key_is_refused():
    module = subject()
    payload = (
        b'<?xml version="1.0"?><plist version="1.0"><dict>'
        b"<key>Label</key><string>foreign</string>"
        b"<key>Label</key><string>accepted</string></dict></plist>"
    )
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_plist(payload, fields={"Label": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"


def test_plist_duplicate_rejection_covers_every_accepted_xml_form():
    module = subject()
    body = (
        b'<plist version="1.0"><dict>'
        b"<key>Label</key><string>foreign</string>"
        b"<key>Label</key><string>accepted</string></dict></plist>"
    )
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_plist(body, fields={"Label": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"

    unique = {"Label": "accepted"}
    assert module.parse_projected_plist(
        b'<plist version="1.0"><dict><key>Label</key>'
        b"<string>accepted</string></dict></plist>",
        fields={"Label": str},
    ) == unique
    assert module.parse_projected_plist(
        plistlib.dumps(unique, fmt=plistlib.FMT_BINARY),
        fields={"Label": str},
    ) == unique


def test_binary_plist_duplicate_is_rejected_before_overwrite():
    module = subject()
    unique = {"Label": "accepted"}
    assert module.parse_projected_plist(
        plistlib.dumps(unique, fmt=plistlib.FMT_BINARY),
        fields={"Label": str},
    ) == unique

    binary_duplicate = plistlib.dumps(
        {"Label": "foreign", "Other": "accepted"},
        fmt=plistlib.FMT_BINARY,
        sort_keys=False,
    )
    assert binary_duplicate.count(b"Other") == 1
    binary_duplicate = binary_duplicate.replace(b"Other", b"Label")
    with pytest.raises(module.PreimageRefusal) as error:
        module.parse_projected_plist(binary_duplicate, fields={"Label": str})
    assert error.value.code == "MALFORMED_TRUSTED_DOCUMENT"


def test_active_ownership_binds_loaded_program_identity():
    module = subject()
    control = module.LABELS[0]

    class Commands(InstalledCommands):
        def __init__(self, program, arguments=None):
            super().__init__()
            self.program = program
            self.arguments = (
                module.expected_program_arguments(control, SHA)
                if arguments is None
                else arguments
            )

        def run(self, argv):
            command = tuple(argv)
            if command == ("/bin/launchctl", "print", f"system/{control}"):
                program = "" if self.program is None else f"program = {self.program}\n"
                arguments = "\n".join(self.arguments)
                return {
                    "status": "ok",
                    "stdout": (
                        f"{program}state = running\npid = 99\n"
                        f"arguments = {{\n{arguments}\n}}\n"
                    ),
                }
            if command == (
                "/bin/ps",
                "-o",
                "uid=,gid=,pid=,ppid=",
                "-p",
                "99",
            ):
                return {"status": "ok", "stdout": "450 450 99 1\n"}
            return super().run(argv)

    def collect(program, arguments=None, filesystem=None):
        return module.collect_preimage(
            expected_release_sha=SHA,
            expected_tree_sha=TREE,
            filesystem=filesystem or InstalledFilesystem(module),
            commands=Commands(program, arguments),
            principals=InstalledPrincipals(),
            clock=lambda: "2026-09-09T19:00:00+00:00",
            platform="darwin",
            uid=0,
            euid=0,
        )

    assert collect(module.PYTHON_BINARY)["classification"] == "ACTIVE_OWNED"
    assert collect("/synthetic/foreign-executable")["classification"] == "ACTIVE_FOREIGN"
    foreign_arguments = module.expected_program_arguments(control, SHA)
    foreign_arguments[4] = "/synthetic/foreign-entrypoint.py"
    foreign = collect(module.PYTHON_BINARY, foreign_arguments)
    assert foreign["classification"] == "ACTIVE_FOREIGN"
    serialized = module.canonical_receipt(foreign)
    assert b"/synthetic/foreign-entrypoint.py" not in serialized
    assert foreign["facts"]["services"][0]["arguments_match"] is False
    assert collect(None)["state"] == "UNSETTLED"

    missing_arguments = Commands(module.PYTHON_BINARY, [])
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=InstalledFilesystem(module),
        commands=missing_arguments,
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["state"] == "UNSETTLED"


def test_decoy_release_argument_and_rejected_values_never_cross_receipt():
    module = subject()
    filesystem = InstalledFilesystem(module)
    sentinel = "SYNTHETIC_PRIVATE_SENTINEL"
    for path in module.PLISTS:
        value = plistlib.loads(filesystem.payloads[path])
        value["ProgramArguments"] = [
            "/bin/echo",
            f"/untrusted/releases/{SHA}/decoy",
        ]
        filesystem.payloads[path] = plistlib.dumps(value)
    invalid = json.loads(filesystem.payloads[module.CODEX_ATTESTATION])
    invalid["schema_version"] = sentinel
    filesystem.payloads[module.CODEX_ATTESTATION] = json.dumps(invalid).encode()
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    encoded = module.canonical_receipt(receipt)
    assert receipt["classification"] == "UNSAFE"
    assert sentinel.encode() not in encoded
    assert b"/untrusted/" not in encoded


def test_rejected_schema_value_is_not_serialized_even_in_unsafe_receipt():
    module = subject()
    filesystem = InstalledFilesystem(module)
    sentinel = "SYNTHETIC_PRIVATE_SENTINEL"
    invalid = json.loads(filesystem.payloads[module.CODEX_ATTESTATION])
    invalid["schema_version"] = sentinel
    filesystem.payloads[module.CODEX_ATTESTATION] = json.dumps(invalid).encode()
    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=filesystem,
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert sentinel.encode() not in module.canonical_receipt(receipt)


def test_filesystem_adapter_manifest_read_requires_exact_admitted_sha(monkeypatch):
    module = subject()
    reads = []
    monkeypatch.setattr(
        module,
        "_read_anchored_content",
        lambda path, **_kwargs: reads.append(path) or b"{}",
    )
    adapter = module.FilesystemAdapter(expected_release_sha=SHA)
    adapter._validate_ancestors = lambda _path: None
    expected = f"{module.SYSTEM_ROOT}/releases/{SHA}/.executive-release-manifest.json"
    assert adapter.read(expected) == b"{}"
    with pytest.raises(module.PreimageRefusal) as error:
        adapter.read("/outside/.executive-release-manifest.json")
    assert error.value.code == "PATH_ESCAPE"
    assert reads == [expected]


@pytest.mark.parametrize("present", [True, False])
def test_metadata_observation_closes_over_var_alias_ancestor_identity(
    monkeypatch, present
):
    module = subject()
    adapter = module.FilesystemAdapter(expected_release_sha=SHA)
    path = f"{module.RUNTIME_ROOT}/control/dr/executive-dr-token"
    samples = iter(
        (
            (("/var", 1, 2, 3, 4),),
            (("/var", 1, 999, 3, 4),),
        )
    )
    validated_paths = []

    def validate(candidate):
        validated_paths.append(candidate)
        return next(samples)

    def lstat(_path):
        if not present:
            raise FileNotFoundError
        return os.stat_result(
            (stat.S_IFREG | 0o400, 12, 1, 1, 450, 450, 1, 1, 1, 1)
        )

    monkeypatch.setattr(adapter, "_validate_ancestors", validate)
    monkeypatch.setattr(module.os, "lstat", lstat)
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.metadata(path)
    assert error.value.code == "FILESYSTEM_TORN"
    assert validated_paths == [path, path]


def test_collector_binds_initial_metadata_identity_into_content_read():
    module = subject()

    class ReplacedFilesystem(InstalledFilesystem):
        def read(self, path, *, expected=None):
            assert expected is not None
            raise module.PreimageUnsettled("FILESYSTEM_TORN")

    receipt = module.collect_preimage(
        expected_release_sha=SHA,
        expected_tree_sha=TREE,
        filesystem=ReplacedFilesystem(module),
        commands=InstalledCommands(),
        principals=InstalledPrincipals(),
        clock=lambda: "2026-09-09T19:00:00+00:00",
        platform="darwin",
        uid=0,
        euid=0,
    )
    assert receipt["state"] == "UNSETTLED"
    assert receipt["reason_codes"] == ["FILESYSTEM_TORN"]


def test_content_contracts_are_path_specific():
    module = subject()
    assert module._content_contract(module.PLISTS[0]) == (0, 0, 0o644)
    assert module._content_contract(module.CONTROL_CONFIG) == (0, 450, 0o440)
    assert module._content_contract(module.WORKER_CONFIG) == (0, 451, 0o440)
    assert module._content_contract(module.PYTHON_PROVENANCE) == (0, 0, 0o400)
    assert module._content_contract(module.CODEX_ATTESTATION) == (0, 451, 0o440)


def test_anchored_content_read_holds_directory_descriptors_and_final_identity(
    monkeypatch,
):
    module = subject()
    opened = []
    closed = []
    next_fd = iter((10, 11, 12, 13, 14, 99))

    def fake_open(path, flags, **kwargs):
        descriptor = next(next_fd)
        opened.append((path, flags, kwargs.get("dir_fd"), descriptor))
        return descriptor

    def result(mode, *, inode, uid=0, gid=0, size=2):
        values = [mode, inode, 1, 1, uid, gid, size, 1, 1, 1]
        return os.stat_result(values)

    def fake_fstat(descriptor):
        if descriptor == 99:
            return result(stat.S_IFREG | 0o440, inode=99, gid=450)
        return result(stat.S_IFDIR | 0o755, inode=descriptor, size=0)

    reads = iter((b"{}", b""))
    monkeypatch.setattr(module.os, "open", fake_open)
    monkeypatch.setattr(module.os, "fstat", fake_fstat)
    monkeypatch.setattr(
        module.os,
        "stat",
        lambda *_args, **_kwargs: result(stat.S_IFREG | 0o440, inode=99, gid=450),
    )
    monkeypatch.setattr(module.os, "read", lambda _fd, _size: next(reads))
    monkeypatch.setattr(module.os, "close", closed.append)
    bound = fake_fstat(99)
    expected = {
        "device": bound.st_dev,
        "inode": bound.st_ino,
        "size": bound.st_size,
        "mtime_ns": bound.st_mtime_ns,
        "ctime_ns": bound.st_ctime_ns,
    }
    assert module._read_anchored_content(
        module.CONTROL_CONFIG, expected=expected
    ) == b"{}"
    assert opened[0][0] == "/"
    assert [item[0] for item in opened[1:-1]] == [
        "Library",
        "Application Support",
        "MastermindExecutive",
        "config",
    ]
    assert opened[-1][0] == "control.json"
    assert opened[-1][2] == 14
    assert opened[-1][1] & os.O_NOFOLLOW
    assert opened[-1][1] & os.O_NONBLOCK
    assert closed == [99, 14, 13, 12, 11, 10]


class FakeStream:
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.closed = False

    def fileno(self):
        return self.descriptor

    def close(self):
        self.closed = True


class FakeChild:
    def __init__(self):
        self.pid = 4242
        self.stdout = FakeStream(101)
        self.stderr = FakeStream(102)
        self.running = True
        self.killed = False

    def wait(self, timeout):
        assert timeout >= 0
        self.running = False
        return 0

    def poll(self):
        return None if self.running else 0

    def kill(self):
        self.killed = True
        self.running = False


@dataclass
class SelectorKey:
    fileobj: FakeStream
    data: str


class FakeSelector:
    def __init__(self):
        self.mapping = {}

    def register(self, stream, _events, data):
        self.mapping[stream.fileno()] = SelectorKey(stream, data)

    def unregister(self, stream):
        self.mapping.pop(stream.fileno())

    def get_map(self):
        return self.mapping

    def select(self, timeout):
        assert 0 <= timeout <= 0.1
        return [(key, 1) for key in list(self.mapping.values())]

    def close(self):
        self.mapping.clear()


def test_real_command_path_bounds_reads_and_reports_owned_child_settlement(monkeypatch):
    module = subject()
    child = FakeChild()
    chunks = {101: [b"450 450 99 1\n", b""], 102: [b""]}
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    monkeypatch.setattr(module.os, "read", lambda fd, _size: chunks[fd].pop(0))
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=FakeSelector,
        monotonic=lambda: 0.0,
    )
    result = adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert result["stdout"] == "450 450 99 1\n"
    assert result["probe"] == {
        "child_pid": 4242,
        "timed_out": False,
        "terminated": False,
        "reaped": True,
        "partial_output_bytes": 13,
    }
    assert child.stdout.closed and child.stderr.closed


def test_real_command_path_kills_only_owned_child_and_reaps_on_bound(monkeypatch):
    module = subject()
    child = FakeChild()
    chunks = {101: [b"x" * 16384] * 5, 102: [b""]}
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    def bounded_read(fd, size):
        chunk = chunks[fd][0]
        value, remainder = chunk[:size], chunk[size:]
        if remainder:
            chunks[fd][0] = remainder
        else:
            chunks[fd].pop(0)
        return value

    monkeypatch.setattr(module.os, "read", bounded_read)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=FakeSelector,
        monotonic=lambda: 0.0,
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.code == "COMMAND_OUTPUT_OVERSIZED"
    assert error.value.facts == {
        "child_pid": 4242,
        "timed_out": False,
        "terminated": True,
        "reaped": True,
        "partial_output_bytes": 65537,
    }
    assert child.killed is True


def test_real_command_timeout_preserves_partial_and_reap_facts(monkeypatch):
    module = subject()
    child = FakeChild()

    class NoEventSelector(FakeSelector):
        def select(self, timeout):
            assert 0 <= timeout <= 0.1
            return []

    ticks = iter((0.0, 1.0, 2.0, 3.0, 4.0, 4.1, 4.2, 4.3))
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=NoEventSelector,
        monotonic=lambda: next(ticks),
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.code == "COMMAND_TIMEOUT"
    assert error.value.facts == {
        "child_pid": 4242,
        "timed_out": True,
        "terminated": True,
        "reaped": True,
        "partial_output_bytes": 0,
    }
    assert child.killed is True


def test_post_spawn_selector_failure_still_settles_owned_child(monkeypatch):
    module = subject()
    child = FakeChild()
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)

    def selector_failure():
        raise OSError("synthetic selector setup failure")

    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=selector_failure,
        monotonic=lambda: 0.0,
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.facts == {
        "child_pid": 4242,
        "timed_out": False,
        "terminated": True,
        "reaped": True,
        "partial_output_bytes": 0,
    }
    assert child.killed is True
    assert child.stdout.closed and child.stderr.closed


def test_post_spawn_cleanup_failure_preserves_unknown_custody(monkeypatch):
    module = subject()

    class UnsettledChild(FakeChild):
        def kill(self):
            raise OSError("synthetic kill failure")

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("synthetic", timeout)

    class RegistrationFailure(FakeSelector):
        def register(self, stream, _events, data):
            raise OSError("synthetic registration failure")

    child = UnsettledChild()
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=RegistrationFailure,
        monotonic=lambda: 0.0,
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.facts == {
        "child_pid": 4242,
        "timed_out": False,
        "terminated": False,
        "reaped": False,
        "partial_output_bytes": 0,
        "termination_unknown": True,
        "reap_unknown": True,
    }
    assert child.stdout.closed and child.stderr.closed


@pytest.mark.parametrize(
    ("completed_at", "accepted"),
    [(3.5, True), (5.0, True), (5.000001, False)],
)
def test_command_result_is_accepted_only_after_fresh_deadline_sample(
    monkeypatch, completed_at, accepted
):
    module = subject()
    now = [0.0]

    class DelayedChild(FakeChild):
        def wait(self, timeout):
            assert timeout >= 0
            now[0] = completed_at
            self.running = False
            return 0

    class EmptySelector(FakeSelector):
        def get_map(self):
            return {}

    child = DelayedChild()
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=EmptySelector,
        monotonic=lambda: now[0],
    )
    command = ("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99")
    if accepted:
        assert adapter.run(command)["probe"]["reaped"] is True
    else:
        with pytest.raises(module.PreimageUnsettled) as error:
            adapter.run(command)
        assert error.value.code == "COMMAND_TIMEOUT"
        assert error.value.facts["timed_out"] is True
        assert error.value.facts["reaped"] is True
        assert error.value.facts["partial_output_bytes"] == 0


def test_error_settlement_lateness_is_reported_with_reaped_facts(monkeypatch):
    module = subject()
    now = [0.0]

    class LateSettlementChild(FakeChild):
        def wait(self, timeout):
            now[0] = 5.25
            self.running = False
            return 0

    class RegistrationFailure(FakeSelector):
        def register(self, stream, _events, data):
            raise OSError("synthetic registration failure")

    child = LateSettlementChild()
    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=RegistrationFailure,
        monotonic=lambda: now[0],
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.code == "COMMAND_TIMEOUT"
    assert error.value.facts["timed_out"] is True
    assert error.value.facts["terminated"] is True
    assert error.value.facts["reaped"] is True


def test_stream_cleanup_failure_is_unsettled_and_deadline_checked(monkeypatch):
    module = subject()
    now = [0.0]

    class ClosingStream(FakeStream):
        def close(self):
            now[0] = 5.25
            raise OSError("synthetic close failure")

    child = FakeChild()
    child.stdout = ClosingStream(101)
    child.stderr = ClosingStream(102)

    class EmptySelector(FakeSelector):
        def get_map(self):
            return {}

    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=EmptySelector,
        monotonic=lambda: now[0],
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.code == "COMMAND_TIMEOUT"
    assert error.value.facts["reaped"] is True
    assert error.value.facts["cleanup_unknown"] is True
    assert error.value.facts["timed_out"] is True


def test_late_bounded_read_retains_known_partial_byte_count(monkeypatch):
    module = subject()
    now = [0.0]
    child = FakeChild()

    class ReadSelector(FakeSelector):
        def select(self, timeout):
            assert 0 <= timeout <= 0.1
            return [(SelectorKey(child.stdout, "stdout"), 1)]

    def late_read(_fd, size):
        assert size == 16 * 1024
        now[0] = 4.1
        return b"late"

    monkeypatch.setattr(module.os, "set_blocking", lambda _fd, _value: None)
    monkeypatch.setattr(module.os, "read", late_read)
    adapter = module.CommandAdapter(
        popen_factory=lambda *_args, **_kwargs: child,
        selector_factory=ReadSelector,
        monotonic=lambda: now[0],
    )
    with pytest.raises(module.PreimageUnsettled) as error:
        adapter.run(("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", "99"))
    assert error.value.code == "COMMAND_TIMEOUT"
    assert error.value.facts["partial_output_bytes"] == 4
    assert error.value.facts["terminated"] is True
    assert error.value.facts["reaped"] is True
