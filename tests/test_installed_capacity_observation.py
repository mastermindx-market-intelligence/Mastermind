"""Real CLI/Runtime/receipt reads with an explicit modeled installed boundary.

These fixtures do not certify a Mac install. The existing release/Python/plist
owners are modeled; Control projection, physical file identity, observer,
exclusive evidence custody and offline report execute their real code.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from control_plane import capacity_observation_evidence as evidence
from ops.executive_os import installed_capacity_observation as installed
from scripts import executive_wake_reconcile as cli
from tests.test_capacity_campaign_observation import owner_stream, snapshot
from tests.test_capacity_observation_evidence import rewrite
from tests.test_executive_wake_reconcile_observe_cli import image, unchanged_authoritative

SHA = "a" * 40


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overwrite_fixture(path, raw):
    mode = path.stat().st_mode & 0o777
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(mode)


@pytest.fixture
def bound(tmp_path, monkeypatch):
    """Map only synthetic root roles; retain real current-UID file custody."""
    actual_os, actual_file = evidence.os, evidence._EvidenceFile
    # Darwin inherits the parent directory GID, which need not be our EGID.
    # Pin that fixture group once so the real reader still rejects group drift.
    fixture_gid = tmp_path.stat().st_gid
    root_os = SimpleNamespace(**vars(actual_os))
    root_os.geteuid = lambda: 0

    @contextmanager
    def actual_custody():
        previous, evidence.os = evidence.os, actual_os
        try:
            yield
        finally:
            evidence.os = previous

    class RootRoleEvidence(actual_file):
        def __init__(self, *args, **kwargs):
            with actual_custody():
                super().__init__(*args, **kwargs)

        def check(self, **kwargs):
            with actual_custody():
                return super().check(**kwargs)

        def write(self, raw):
            with actual_custody():
                return super().write(raw)

        def read(self):
            with actual_custody():
                return super().read()

    monkeypatch.setattr(evidence, "os", root_os)
    monkeypatch.setattr(evidence, "_EvidenceFile", RootRoleEvidence)
    system = tmp_path / "installed"
    release = system / "releases" / SHA
    repo = Path(__file__).resolve().parents[1]
    for relative in installed.SOURCE_FILES:
        path = release / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((repo / relative).read_bytes())
        path.chmod(0o644)
    config = system / "config" / "control.json"
    config.parent.mkdir()
    receipt = config.with_name("control-observation.json")
    marker = config.with_name("autonomy-transaction.lock")
    runtime_base = tmp_path / "runtime"
    runtime, _, _ = owner_stream(runtime_base / "control" / "db", retry=True)
    document = dict(schema_version="mastermind.executive_control_config/v1",
                    proof_base_sha=SHA, control_uid=installed.contract.CONTROL_UID,
                    python_runtime_provenance_digest="b" * 64,
                    runtime_root=str(runtime.store.root))
    config.write_text(json.dumps(document))
    config.chmod(0o440)
    original_read = installed.owner._read_root_file

    def root_read(path, *, modes, uid=0, gid=None):
        raw, info = original_read(path, modes=modes, uid=os.geteuid(), gid=fixture_gid)
        values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        values.update(st_uid=uid, st_gid=0 if gid is None else gid)
        return raw, SimpleNamespace(**values)

    def trusted(path, *, budget, maximum, expected_mode=None, expected_gid=None, **_):
        budget.check()
        raw, info = root_read(Path(path), modes=frozenset({expected_mode or 0o644}),
                              gid=0 if expected_gid is None else expected_gid)
        assert len(raw) <= maximum
        return raw, info

    def ancestors(path, budget):
        budget.check()
        directory = Path(path).parent
        return ((str(directory), installed.contract.object_identity(directory.lstat())),)

    monkeypatch.setattr(installed.owner, "SYSTEM_ROOT", system)
    monkeypatch.setattr(installed.owner, "RUNTIME_ROOT", runtime_base)
    monkeypatch.setattr(installed.owner, "AUTONOMY_TRANSACTION", marker)
    monkeypatch.setattr(installed.contract, "CONTROL_PATH", str(config))
    monkeypatch.setattr(installed.contract, "OBSERVATION_PATH", str(receipt))
    monkeypatch.setattr(installed.peer_owner, "_CONTROL_CONFIG_PATH", str(config))
    monkeypatch.setattr(installed.owner, "_read_root_file", root_read)
    monkeypatch.setattr(installed.peer_owner, "_read_trusted_bytes", trusted)
    monkeypatch.setattr(installed.peer_owner, "_observe_ancestors", ancestors)
    receipt.write_bytes(installed.control_owner._snapshot(SHA)[0])
    receipt.chmod(0o444)
    plist, python = tmp_path / "control.plist", tmp_path / "pinned-python"
    plist.write_bytes(b"MODELED CLOSED CONTROL PLIST")
    python.write_bytes(b"MODELED SIGNED PSF RUNTIME")
    calls = []

    def origin(expected):
        calls.append("origin")
        assert expected == SHA

    def plist_read(topology, budget, *, expected_release):
        calls.append("plist")
        budget.check()
        assert topology.role == "control" and expected_release == SHA
        return installed.peer_owner._PlistObservation(SHA, digest(plist), (),
            installed.contract.object_identity(plist.stat()), ())

    def tree_rows():
        return tuple((name, "file", 0o644, 0, 0, (release / name).stat().st_size,
                      digest(release / name), installed.contract.object_identity((release / name).stat()))
                     for name in installed.SOURCE_FILES)

    def tree_read(topology, expected, budget):
        calls.append("release")
        budget.check()
        assert expected == SHA
        return SimpleNamespace(manifest_digest="c" * 64, digests=tree_rows())

    def tree_recheck(previous, budget):
        calls.append("release_recheck")
        budget.check()
        if previous.digests != tree_rows():
            raise installed.peer_owner._refuse("SERVICE_RELEASE_CHANGED")

    def python_read(budget):
        calls.append("python")
        budget.check()
        return SimpleNamespace(launcher_digest=digest(python), dylib_digest=digest(python),
            main_digest=digest(python), identity=installed.contract.object_identity(python.stat()))

    def python_recheck(previous, budget):
        calls.append("python_recheck")
        if previous != python_read(budget):
            raise installed.peer_owner._refuse("SERVICE_PYTHON_CHANGED")

    monkeypatch.setattr(installed, "_execution_origin", origin)
    monkeypatch.setattr(installed.peer_owner, "_verify_role_plist", plist_read)
    monkeypatch.setattr(installed.peer_owner, "_verify_release", tree_read)
    monkeypatch.setattr(installed.peer_owner, "_recheck_release", tree_recheck)
    monkeypatch.setattr(installed.peer_owner, "_verify_python_runtime", python_read)
    monkeypatch.setattr(installed.peer_owner, "_recheck_python_runtime", python_recheck)
    monkeypatch.setattr(cli, "collect_source_snapshot", lambda *a, **kw: snapshot())
    directory = tmp_path / "evidence"
    directory.mkdir(mode=0o700)
    return SimpleNamespace(release=release, config=config, receipt=receipt, marker=marker,
        runtime=runtime, directory=directory, plist=plist, python=python, calls=calls,
        root_os=root_os, document=document)


def capture(bound, name="point.json", *extra):
    path = bound.directory / name
    code = cli.main(["--observe-only", "--observation-receipt", str(path),
                     "--installed-release-sha", SHA, *extra])
    return path, code


def test_installed_cli_actual_runtime_to_receipt_to_offline_report(bound, monkeypatch, capsys):
    runtime = bound.runtime
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    try:
        before = image(runtime.store.root)
        events = tuple(keeper.execute("SELECT * FROM events ORDER BY event_id"))
        path, code = capture(bound)
        assert code == 0
        streams = capsys.readouterr()
        value = json.loads(path.read_text())
        assert value["stdout"] == streams.out and value["stderr"] == streams.err
        assert value["schema"] == evidence.INSTALLED_RECEIPT_SCHEMA
        assert value["runtime_root"] == str(runtime.store.root)
        binding = value["installed_source_binding"]
        assert binding["control_observation"] == json.loads(bound.receipt.read_text())
        assert binding["control_observation_sha256"] == digest(bound.receipt)
        assert binding["control_observation"]["control_sha256"] == digest(bound.config)
        assert binding["installed_source_qualified"] is binding["installed_config_custody_qualified"] is True
        assert binding["installed_service_peer_attested"] is binding["runtime_namespace_continuity_attested"] is False
        assert set(binding["qualified_source_files"]) == set(installed.SOURCE_FILES)
        assert sum(value["acquisition_phases_monotonic_ns"].values()) == value["acquisition_monotonic_ns"]
        assert path.stat().st_mode & 0o777 == 0o400
        point = json.loads(streams.out)["capacity_observation"]
        assert point["interval_summaries"]["request_to_ack_ms"]["p95"] == 5000
        assert point["runtime_workload"]["jobs_by_status"]
        assert bound.calls == ["origin", "plist", "release", "python", "origin", "release_recheck",
                               "python_recheck", "python", "plist"]
        monkeypatch.setattr(cli.Runtime, "at", lambda *a, **kw: pytest.fail("offline Runtime read"))
        monkeypatch.setattr(installed, "InstalledSourceObservation", lambda *a: pytest.fail("offline host read"))
        assert cli.main(["--summarize-observations", str(path)]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["observations"][0]["installed_source_binding"] == binding
        assert report["observations"][0]["runtime_workload"] == point["runtime_workload"]
        assert report["installed_source_bound_observation_count"] == 1
        assert report["healthy_installed_source_bound_observation_count"] == 1
        assert report["installed_source_and_config_custody_qualified"] is True
        assert report["unproven_requirements"]["installed_source_and_runtime_attestation"]["state"] == "PARTIAL"
        assert report["installed_service_peer_attested"] is report["runtime_namespace_continuity_attested"] is False
        assert report["installed_coverage_claimed"] is report["campaign_qualified"] is False
        unchanged_authoritative(runtime.store.root, before)
        assert tuple(keeper.execute("SELECT * FROM events ORDER BY event_id")) == events
    finally:
        keeper.close()


@pytest.mark.parametrize("extra", [
    ["--root", "/caller-selected"], ["--boot-packet-file", "/saved"],
    ["--summarize-observations", "/old-receipt"],
])
def test_installed_cli_overrides_refuse_before_reservation_or_owner(bound, extra):
    with pytest.raises(SystemExit):
        capture(bound, "refused.json", *extra)
    assert not (bound.directory / "refused.json").exists() and not bound.calls


@pytest.mark.parametrize("extra", [[], ["--observe-only"], ["--observation-receipt", "/unused"]])
def test_installed_flag_never_selects_mutating_or_unretained_owner(monkeypatch, extra):
    monkeypatch.setattr(cli, "_run", lambda *a: pytest.fail("owner invoked"))
    with pytest.raises(SystemExit):
        cli.main(["--installed-release-sha", SHA, *extra])


def test_wrong_release_identifier_refuses_before_qualification(bound, monkeypatch):
    monkeypatch.setattr(cli, "_run", lambda *a: pytest.fail("observer invoked"))
    path = bound.directory / "bad-release.json"
    assert cli.main(["--observe-only", "--observation-receipt", str(path),
                     "--installed-release-sha", SHA.upper()]) == 2
    assert not bound.calls and path.read_bytes() == b""


def test_offline_report_refuses_even_empty_installed_selector(monkeypatch):
    monkeypatch.setattr(cli, "summarize_observations", lambda *a: pytest.fail("selector ignored"))
    with pytest.raises(SystemExit):
        cli.main(["--summarize-observations", "/retained.json", "--installed-release-sha", ""])


def test_configured_runtime_cannot_override_fixed_installed_runtime(bound):
    changed = dict(bound.document, runtime_root=str(bound.directory))
    overwrite_fixture(bound.config, json.dumps(changed).encode())
    overwrite_fixture(bound.receipt, installed.control_owner._snapshot(SHA)[0])
    with pytest.raises(evidence.ObservationEvidenceError, match="INSTALLED_RUNTIME_CONFIG_MISMATCH"):
        installed.InstalledSourceObservation(SHA)


def replace_same(path):
    other = path.with_name(path.name + ".replacement")
    other.write_bytes(path.read_bytes())
    other.chmod(path.stat().st_mode & 0o777)
    os.replace(other, path)


@pytest.mark.parametrize("damage", ["config_bytes", "config_replace", "receipt_replace", "source_bytes",
                                    "source_replace", "plist_replace", "python_replace", "transaction", "budget"])
def test_drift_or_same_byte_replacement_refuses_completed_installed_receipt(bound, monkeypatch, capsys, damage):
    original_run = cli._run
    original_init = installed.InstalledSourceObservation.__init__
    live = []
    damage_applied = []
    def remember(self, *args):
        original_init(self, *args)
        live.append(self)
    monkeypatch.setattr(installed.InstalledSourceObservation, "__init__", remember)

    def run(args):
        code = original_run(args)
        if damage == "config_bytes":
            overwrite_fixture(bound.config, bound.config.read_bytes() + b" ")
        elif damage == "source_bytes":
            source = bound.release / installed.SOURCE_FILES[1]
            source.write_bytes(source.read_bytes() + b"\n")
        elif damage == "transaction":
            bound.marker.write_bytes(b"another original owner")
        elif damage == "budget":
            live[0]._budget._deadline = 0
        else:
            path = {"config_replace": bound.config, "receipt_replace": bound.receipt,
                    "source_replace": bound.release / installed.SOURCE_FILES[1],
                    "plist_replace": bound.plist, "python_replace": bound.python}[damage]
            replace_same(path)
        damage_applied.append(damage)
        return code
    monkeypatch.setattr(cli, "_run", run)
    path, code = capture(bound, damage + ".json")
    assert code == 2
    assert damage_applied == [damage]
    assert "observation evidence unavailable" in capsys.readouterr().err
    assert path.read_bytes() == b"" and path.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(cli, "_run", lambda *a: pytest.fail("replayed after refusal"))
    assert capture(bound, path.name)[1] == 2
    assert not evidence.summarize_observations([path])["observations"]


@pytest.mark.parametrize("damage", ["mode", "hardlink", "missing", "active_transaction"])
def test_initial_custody_and_transaction_refusals_precede_observer(bound, monkeypatch, capsys, damage):
    if damage == "mode":
        bound.config.chmod(0o640)
    elif damage == "hardlink":
        os.link(bound.receipt, bound.receipt.with_suffix(".alias"))
    elif damage == "missing":
        bound.receipt.unlink()
    else:
        bound.marker.write_bytes(b"original owner")
    monkeypatch.setattr(cli, "_run", lambda *a: pytest.fail("observer invoked"))
    path, code = capture(bound)
    assert code == 2 and path.read_bytes() == b""
    assert "observation evidence unavailable" in capsys.readouterr().err


def test_source_checkout_cannot_claim_installed_entry(bound, monkeypatch):
    # Use the real origin check, modeling only host platform/root qualification.
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("origin_check", Path(installed.__file__))
    fresh = module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setattr(installed.owner.ProductionStatusHost, "_require_host", lambda self: None)
    with pytest.raises(evidence.ObservationEvidenceError, match="INSTALLED_OBSERVER_ENTRY_REQUIRED"):
        fresh._execution_origin(SHA)


def test_heavy_qualification_cost_and_week_labels_remain_separate_from_campaign(bound, monkeypatch, capsys):
    times = iter(["2026-01-01T00:00:00.000000Z", "2026-01-01T00:00:21.000000Z",
                  "2026-01-08T00:00:00.000000Z", "2026-01-08T00:00:21.000000Z"])
    ticks = iter([0, 7_000_000_000, 10_000_000_000, 21_000_000_000,
                  30_000_000_000, 37_000_000_000, 40_000_000_000, 51_000_000_000])
    monkeypatch.setattr(evidence, "_utc_now", lambda: next(times))
    monkeypatch.setattr(evidence, "time", SimpleNamespace(monotonic_ns=lambda: next(ticks)))
    first, code = capture(bound, "first.json")
    assert code == 0
    last, code = capture(bound, "last.json")
    assert code == 0
    capsys.readouterr()
    report = evidence.summarize_observations([last, first])
    assert report["installed_source_bound_observation_count"] == 2
    assert report["recorded_wall_clock_span_seconds"] == 604821
    for row in report["observations"]:
        assert row["acquisition_monotonic_ns"] == 21_000_000_000
        assert row["acquisition_phases_monotonic_ns"] == dict(
            installed_preflight=7_000_000_000, observer=3_000_000_000, installed_recheck=11_000_000_000)
    assert report["campaign_qualified"] is report["installed_coverage_claimed"] is False
    for name in ("model_reasoning_duration", "original_parent_disposition_consumption",
                 "actual_total_cost_per_accepted_outcome", "continuous_seven_day_coverage"):
        assert report["unproven_requirements"][name]["state"] == "UNAVAILABLE"


@pytest.mark.parametrize("change", [
    lambda d: d["installed_source_binding"].update(installed_service_peer_attested=True),
    lambda d: d["installed_source_binding"].update(runtime_namespace_continuity_attested=True),
    lambda d: d["installed_source_binding"].update(control_observation={}),
    lambda d: d.update(runtime_root="/different/runtime"),
    lambda d: d.update(boot_packet_origin="saved_file"),
    lambda d: d["source_files_before"].update({"/extra/source": "f" * 64}),
    lambda d: d["acquisition_phases_monotonic_ns"].update(observer=True),
    lambda d: d.update(writer_uid=501),
])
def test_offline_claim_or_binding_tampering_never_upgrades_evidence(bound, capsys, change):
    path, code = capture(bound)
    assert code == 0
    capsys.readouterr()
    rewrite(path, change)
    report = evidence.summarize_observations([path])
    assert report["failures"] and report["observation_count"] == 0
    assert report["installed_source_and_config_custody_qualified"] is False


def test_source_only_and_installed_receipts_do_not_silently_share_provenance(bound, capsys):
    installed_path, code = capture(bound)
    assert code == 0
    source = bound.directory / "source.json"
    assert cli.main(["--root", str(bound.runtime.store.root), "--observe-only",
                     "--observation-receipt", str(source)]) == 0
    capsys.readouterr()
    report = evidence.summarize_observations([installed_path, source])
    assert report["installed_source_bound_observation_count"] == 1
    assert report["observation_count"] == 2
    assert report["failures"][0]["reason"] == "MIXED_RUNTIME_SOURCE_OR_BOOT_INPUTS"
    assert report["installed_source_and_config_custody_qualified"] is False


def test_partial_observer_retains_source_custody_without_healthy_point(bound, monkeypatch, capsys):
    def unavailable(args):
        print("actual observer unavailable", file=cli.sys.stderr)
        return 2
    monkeypatch.setattr(cli, "_run", unavailable)
    path, code = capture(bound)
    assert code == 2
    capsys.readouterr()
    report = evidence.summarize_observations([path])
    assert report["installed_source_bound_observation_count"] == 1
    assert report["healthy_installed_source_bound_observation_count"] == 0
    assert report["observer_failure_count"] == 1
    assert report["observations"][0]["point_status"] == "UNAVAILABLE"
    assert report["campaign_qualified"] is report["installed_coverage_claimed"] is False


@pytest.mark.parametrize('damage', [
    'partial', 'contradictory', 'plan_degraded', 'plan_contradictions',
    'unsupported_attention', 'runtime_health', 'inbox_runtime_health',
    'agentos_health', 'measurement_degraded', 'measurement_contradictions',
])
def test_zero_exit_receipt_cannot_contradict_its_observed_outcome(
    bound, monkeypatch, capsys, damage,
):
    path, code = capture(bound)
    assert code == 0
    capsys.readouterr()

    def change(value):
        report = json.loads(value['stdout'])
        point = report['capacity_observation']
        if damage in {'partial', 'contradictory'}:
            point['point_status'] = damage.upper()
        elif damage.startswith('plan_'):
            report[damage.removeprefix('plan_')] = ['TESTDATA retained contradiction']
        elif damage.startswith('measurement_'):
            point[damage.removeprefix('measurement_')] = ['TESTDATA retained contradiction']
        elif damage == 'unsupported_attention':
            report[damage] = ['TESTDATA unsupported attention']
        else:
            report[damage] = 'degraded'
        value['stdout'] = json.dumps(report, sort_keys=True)
        value['stdout_sha256'] = hashlib.sha256(value['stdout'].encode()).hexdigest()
        assert value['observer_return_code'] == 0

    rewrite(path, change)
    retained = path.read_bytes()
    monkeypatch.setattr(cli.Runtime, 'at', lambda *a, **kw: pytest.fail('offline Runtime read'))
    monkeypatch.setattr(installed, 'InstalledSourceObservation', lambda *a: pytest.fail('offline host read'))
    report = evidence.summarize_observations([path])
    assert report['observation_count'] == 0
    assert report['healthy_installed_source_bound_observation_count'] == 0
    assert report['installed_source_and_config_custody_qualified'] is False
    assert report['failures'] == [{'path': str(path), 'reason': 'OBSERVER_SUCCESS_OUTCOME_MISMATCH'}]
    assert cli.main(['--summarize-observations', str(path)]) == 2
    assert json.loads(capsys.readouterr().out) == report
    assert path.read_bytes() == retained


def test_nonzero_partial_observation_retains_qualified_source_custody(bound, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'collect_source_snapshot', lambda *a, **kw: snapshot(degraded=True))
    path, code = capture(bound)
    assert code == 2
    point = json.loads(capsys.readouterr().out)['capacity_observation']
    assert point['point_status'] == 'PARTIAL'
    report = evidence.summarize_observations([path])
    assert report['failures'] == [] and report['observation_count'] == 1
    assert report['installed_source_and_config_custody_qualified'] is True
    assert report['healthy_installed_source_bound_observation_count'] == 0
    assert report['observer_failure_count'] == 1
    assert report['installed_service_peer_attested'] is report['campaign_qualified'] is False
    assert cli.main(['--summarize-observations', str(path)]) == 2
    assert json.loads(capsys.readouterr().out) == report
