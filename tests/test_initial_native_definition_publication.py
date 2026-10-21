"""Initial native publication uses real rendering/writing with inert owner facts.

The fixtures supply source acceptance and OS custody; they are not production
receipts. No credential, provider, service, enrollment or Runtime effect occurs.
"""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from ops.executive_os import finite_definition_publication as pub
from ops.executive_os import capacity_source_contract as contract
from tests.test_finite_service_host import qualified_host


@pytest.fixture
def publisher(qualified_host, monkeypatch, tmp_path):
    from control_plane import codex_provider_realm as realm
    from ops.executive_os import capacity_host_artifacts as closure
    from ops.executive_os import finite_reference_assignment as references
    from ops.executive_os import finite_service_lifecycle as lifecycle
    from ops.executive_os import release_manifest

    host, prior, _, calls = qualified_host
    prior.control = {key: False for key in (
        "coo_autonomy_armed", "coo_operator_harness_armed",
        "coo_foreground_only", "ceo_submit_armed", "fabric_bridge_armed")}
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setattr(pub.owner, "CONFIG_ROOT", config)
    monkeypatch.setattr(pub, "DESTINATION", config / "fabric-minimax-finite-01")
    monkeypatch.setattr(pub.os, "geteuid", lambda: 0)
    monkeypatch.setattr(pub, "_trusted_control_root", lambda fd: os.fstat(fd))
    monkeypatch.setattr(pub, "_require_native_installed_owner", lambda sha: None)
    monkeypatch.setattr(pub, "_require_initial_native_context",
                        lambda prior, custody: calls.append("native-context"))
    host.owner._config_root_safe = lambda: calls.append("config-owned")
    monkeypatch.setattr(pub.owner, "ProductionCeoSubmitHost", lambda: host.owner)
    monkeypatch.setattr(pub.owner, "_read_root_file",
        lambda path, modes, uid, gid: (lifecycle.protected_bytes(
            path, mode=next(iter(modes)), gid=gid), None))
    monkeypatch.setattr(release_manifest, "verify", lambda *args: None)
    source = {"release_commit": "a"*40, "previous_release_commit": "b"*40,
              "material_source_digest": "c"*64, "export_sha256": "d"*64}
    row = {"schema": "mastermind.provider_native_capability_registration/v1",
        "capacity_capability_id": "fixture.minimax", "capability_generation": 1,
        "provider": "minimax", "billing_mode": "subscription", "credential_kind": "api_key",
        "execution_surface": "native_cli", "registration_state": "registered",
        "material_source_digest": source["material_source_digest"]}
    row["registration_receipt_digest"] = contract.canonical_digest(row)
    document = {"repository_commit": source["release_commit"],
        "previous_repository_commit": source["previous_release_commit"],
        "material_source_digest": source["material_source_digest"], "registrations": [row]}
    observed = SimpleNamespace(prior=prior, source=source, document=document,
        calls=calls, selections=0, references=[], renders=0, source_info=
        SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFDIR | 0o555),
        schema="mastermind.capacity_source_transport/native_v1",
        owner=host.owner)
    source_root = contract.SYSTEM_ROOT / "capacity-sources/macro" / source["release_commit"]
    export = contract.SYSTEM_ROOT / "config/capacity-source-components-native-v2" / (source["release_commit"]+".json")

    @contextmanager
    def native_open(path, **kwargs):
        assert path == source_root and kwargs == {"directory": True}
        calls.append("source-custody")
        yield -1, observed.source_info
    monkeypatch.setattr(realm, "_native_open", native_open)
    def complete(path, commit):
        assert path == source_root and commit == source["release_commit"]
        calls.append("complete-source")
        return {"schema_version": observed.schema}, object()
    monkeypatch.setattr(closure, "_verify_installed_repair_source", complete)
    def read_export(path, expected):
        assert path == export and expected == source["export_sha256"]
        calls.append("protected-export")
        return copy.deepcopy(observed.document)
    monkeypatch.setattr(realm, "_native_read_config", read_export)
    def select():
        observed.selections += 1
        calls.append("select")
        return copy.deepcopy(source)
    observed.select = select
    token = references.secrets.token_hex
    def mint(length):
        if length != 32:
            return token(length)
        value = str(len(observed.references) + 1) * 64
        observed.references.append(value)
        return value
    monkeypatch.setattr(references.secrets, "token_hex", mint)
    original_render = pub._render_owner_definition
    def render(*args, **kwargs):
        observed.renders += 1
        calls.append("render")
        return original_render(*args, **kwargs)
    monkeypatch.setattr(pub, "_render_owner_definition", render)
    writer = pub._write_exclusive
    def write(path, artifacts, *, uid, gid, parent_fd):
        assert (uid, gid) == (0, 0)
        calls.append("publish")
        # Real writer in the isolated, user-owned fixture directory.
        return writer(path, artifacts, uid=os.getuid(), gid=os.getgid(), parent_fd=parent_fd)
    monkeypatch.setattr(pub, "_write_exclusive", write)
    return observed


def invoke(publisher, **kwargs):
    return pub.publish_initial_native_from_installed_sources(
        "a"*40, publisher.prior.control_sha256,
        select_accepted_native_source=kwargs.get("selector", publisher.select))


def test_one_native_generation_uses_original_mutex_renderer_and_writer(publisher):
    import fcntl
    original = publisher.select
    def selected_under_lock():
        fd = os.open(pub.owner.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        return original()
    result = invoke(publisher, selector=selected_under_lock)
    assert result["effect"] == "APPLIED"
    assert result["admitted_worker"] is result["service_started"] is False
    assert publisher.selections == publisher.renders == 3
    assert len(publisher.references) == 3
    assert publisher.calls.count("complete-source") == 3
    assert publisher.calls.index("native-context") < publisher.calls.index("select")
    assert publisher.calls[:publisher.calls.index("publish")].count("render") == 2
    artifacts = {name: (pub.DESTINATION/name).read_bytes() for name in pub.FILES}
    assert result["artifacts"] == pub.verify_candidate(artifacts)
    worker = json.loads(artifacts["worker.json"])
    enrollment = worker["native_capacity_enrollment"]
    assert enrollment["enrollment_state"] == "unenrolled"
    assert enrollment["registration_source"] == publisher.source
    assert enrollment["host_ref"] == "host-" + publisher.references[0]
    assert enrollment["os_principal_ref"] == "principal-" + publisher.references[1]
    assert enrollment["config_custody_ref"] == "custody-" + publisher.references[2]
    assert worker["operator_harness_armed"] is False
    joined = pub._native_candidate_join(artifacts, publisher.document)
    assert joined["provider_capacity_schema"] == "mastermind.provider_capacity.v2"
    assert joined["worker_source_config_digest"] == pub.sha256(artifacts["worker.json"])


@pytest.mark.parametrize("prior", ["definition", "stage"])
def test_prior_effect_never_mints_or_selects_a_second_generation(publisher, prior):
    if prior == "definition":
        invoke(publisher)
    else:
        (pub.owner.CONFIG_ROOT/".fabric-minimax-finite-01.retained.stage").mkdir()
    before = (publisher.selections, len(publisher.references))
    with pytest.raises(pub.FinitePublicationRefused, match="already exists|prior finite"):
        invoke(publisher)
    assert (publisher.selections, len(publisher.references)) == before


@pytest.mark.parametrize("fault", ["missing", "bare-dict", "bad-pins", "same-commit",
    "root-uid", "root-gid", "root-mode", "legacy-profile", "export-current",
    "export-previous", "export-material", "revoked", "ambiguous", "foreign-provider",
    "generation-bool", "registration-digest"])
def test_source_refusals_preserve_all_protected_preimages(publisher, fault):
    selector = publisher.select
    if fault == "missing": selector = None
    if fault == "bare-dict": selector = publisher.source
    if fault == "bad-pins": selector = lambda: dict(publisher.source, extra="unaccepted")
    if fault == "same-commit": selector = lambda: dict(publisher.source,
        previous_release_commit=publisher.source["release_commit"])
    if fault == "root-uid": publisher.source_info.st_uid = 501
    if fault == "root-gid": publisher.source_info.st_gid = 20
    if fault == "root-mode": publisher.source_info.st_mode = stat.S_IFDIR | 0o755
    if fault == "legacy-profile": publisher.schema = "mastermind.capacity_source_transport/v3"
    if fault == "export-current": publisher.document["repository_commit"] = "f"*40
    if fault == "export-previous": publisher.document["previous_repository_commit"] = "f"*40
    if fault == "export-material": publisher.document["material_source_digest"] = "f"*64
    row = publisher.document["registrations"][0]
    if fault == "revoked": row["registration_state"] = "revoked"
    if fault == "ambiguous": publisher.document["registrations"].append(copy.deepcopy(row))
    if fault == "foreign-provider": row["provider"] = "claude"
    if fault == "generation-bool": row["capability_generation"] = True
    if fault == "registration-digest": row["registration_receipt_digest"] = "f"*64
    before = copy.deepcopy((publisher.prior.control, publisher.prior.worker))
    with pytest.raises(pub.FinitePublicationRefused):
        invoke(publisher, selector=selector)
    assert not pub.DESTINATION.exists()
    assert list(pub.owner.CONFIG_ROOT.iterdir()) == []
    assert (publisher.prior.control, publisher.prior.worker) == before
    assert "publish" not in publisher.calls


@pytest.mark.parametrize("step", [2, 3])
@pytest.mark.parametrize("kind", ["source-failure", "source-drift", "render-drift"])
def test_failure_classification_follows_the_original_publication(publisher, monkeypatch, step, kind):
    selected = publisher.select
    render = pub._render_owner_definition
    if kind.startswith("source"):
        def changed():
            source = selected()
            if publisher.selections == step:
                if kind == "source-failure":
                    raise pub.FinitePublicationRefused("selection unavailable")
                source["material_source_digest"] = "e"*64
            return source
        publisher.select = changed
    else:
        def changed_render(*args, **kwargs):
            result = render(*args, **kwargs)
            if publisher.renders == step:
                result["owner_entry.py"] += b"# source drift\n"
            return result
        monkeypatch.setattr(pub, "_render_owner_definition", changed_render)
    error = pub.FinitePublicationRefused if step == 2 else pub.FinitePublicationEffectUnknown
    with pytest.raises(error):
        invoke(publisher)
    assert pub.DESTINATION.exists() is (step == 3)
    assert len(publisher.references) == 3
    if step == 3:
        assert set(path.name for path in pub.DESTINATION.iterdir()) == pub.FILES
        before = (publisher.selections, len(publisher.references))
        with pytest.raises(pub.FinitePublicationRefused, match="already exists"):
            invoke(publisher)
        assert (publisher.selections, len(publisher.references)) == before


def test_postwrite_explicit_owner_refusal_is_effect_unknown(publisher):
    checked = publisher.owner.require_exact_install
    checks = []
    def installed(sha):
        checks.append(sha)
        if len(checks) == 3:
            raise pub.FinitePublicationRefused("installed owner drift")
        return checked(sha)
    publisher.owner.require_exact_install = installed
    with pytest.raises(pub.FinitePublicationEffectUnknown):
        invoke(publisher)
    assert pub.DESTINATION.is_dir()


def test_retained_custody_exit_failure_after_write_is_effect_unknown(publisher, monkeypatch):
    @contextmanager
    def held():
        yield
        raise pub.FinitePublicationRefused("retained HOME changed")
    def context(prior, custody):
        custody.enter_context(held())
    monkeypatch.setattr(pub, "_require_initial_native_context", context)
    with pytest.raises(pub.FinitePublicationEffectUnknown):
        invoke(publisher)
    assert pub.DESTINATION.is_dir()


def test_definite_private_stage_cleanup_remains_a_refusal(publisher, monkeypatch):
    original = pub.os.fchown
    attempts = []
    def fail_second(fd, uid, gid):
        attempts.append(fd)
        if len(attempts) == 2:
            raise OSError("private fixture write failed")
        return original(fd, uid, gid)
    monkeypatch.setattr(pub.os, "fchown", fail_second)
    with pytest.raises(pub.FinitePublicationRefused):
        invoke(publisher)
    assert list(pub.owner.CONFIG_ROOT.iterdir()) == []


def test_legacy_entry_never_launders_native_artifacts(publisher):
    invoke(publisher)
    artifacts = {name: (pub.DESTINATION/name).read_bytes() for name in pub.FILES}
    owner_calls = []
    with pytest.raises(pub.FinitePublicationRefused, match="native definition requires"):
        pub.publish_disarmed_definition("a"*40, publisher.prior.control_sha256,
            artifacts, verified_capacity_binding=lambda *args: owner_calls.append(args) or True)
    assert owner_calls == []


def test_native_entry_requires_installed_owner_before_selection(monkeypatch):
    monkeypatch.setattr(pub.os, "geteuid", lambda: 0)
    calls = []
    with pytest.raises(pub.FinitePublicationRefused, match="installed isolated"):
        pub.publish_initial_native_from_installed_sources("a"*40, "b"*64,
            select_accepted_native_source=lambda: calls.append(True))
    assert calls == []


def test_source_pin_validator_is_only_syntax_and_copies_its_input():
    value = {"release_commit": "a"*40, "previous_release_commit": "b"*40,
             "material_source_digest": "c"*64, "export_sha256": "d"*64}
    copied = contract.validate_native_registration_source(value)
    assert copied == value and copied is not value
    copied["export_sha256"] = "e"*64
    assert value["export_sha256"] == "d"*64


@pytest.mark.parametrize("fault", ["none", "incumbent-control", "incumbent-primary",
    "qualified-policy", "principal-uid", "principal-home", "principal-shell",
    "group", "home-uid", "home-gid", "home-mode", "live-worker",
    "loaded-idle", "enabled-override", "socket-file", "socket-directory", "socket-symlink"] )
def test_actual_initial_context_qualifies_principal_home_and_absent_coordinates(
        qualified_host, monkeypatch, tmp_path, fault):
    from contextlib import ExitStack
    import grp
    import pwd
    from control_plane import codex_provider_realm as realm
    from control_plane import executive_physical_resources as physical
    from ops.executive_os import subscription_provider_credential as credential
    from ops.executive_os import finite_service_lifecycle as lifecycle
    monkeypatch.setattr(pub.owner, "ProductionCeoSubmitHost", lambda: SimpleNamespace(
        _loaded_observe_only=lambda label: label == lifecycle.LABEL and fault == "loaded-idle"))
    override = ('disabled services = {\n"' + lifecycle.LABEL + '" => enabled\n}'
                if fault == "enabled-override" else "disabled services = {\n}")
    def observed_command(argv):
        assert argv == ["/bin/launchctl", "print-disabled", "system"]
        return SimpleNamespace(stdout=override.encode())
    socket_path = tmp_path/"finite.sock"
    monkeypatch.setattr(lifecycle, "SOCKET", str(socket_path))
    if fault == "socket-file": socket_path.write_bytes(b"retained object")
    if fault == "socket-directory": socket_path.mkdir()
    if fault == "socket-symlink": socket_path.symlink_to(tmp_path/"absent-target")
    _, prior, _, _ = qualified_host
    monkeypatch.setattr(lifecycle, "checked_command", observed_command)
    prior.control = {"ceo_submit_armed": False}
    policy = physical.load_physical_resource_policy()
    home = "/private/var/db/mastermind-executive/workers/minimax-finite-01/provider-home"
    user = SimpleNamespace(pw_uid=470, pw_gid=470, pw_dir=home, pw_shell="/usr/bin/false")
    group = SimpleNamespace(gr_gid=470)
    info = SimpleNamespace(st_uid=470, st_gid=470, st_mode=stat.S_IFDIR | 0o700)
    if fault == "incumbent-control": prior.control["fabric_bindings_path"] = "/old"
    if fault == "incumbent-primary": prior.worker["host_ref"] = "host-" + "9"*64
    if fault == "qualified-policy": policy["qualification"] = "QUALIFIED"
    if fault == "principal-uid": user.pw_uid = 471
    if fault == "principal-home": user.pw_dir = "/wrong"
    if fault == "principal-shell": user.pw_shell = "/bin/zsh"
    if fault == "group": group.gr_gid = 471
    if fault == "home-uid": info.st_uid = 471
    if fault == "home-gid": info.st_gid = 471
    if fault == "home-mode": info.st_mode = stat.S_IFDIR | 0o755
    monkeypatch.setattr(physical, "load_physical_resource_policy", lambda: copy.deepcopy(policy))
    monkeypatch.setattr(pwd, "getpwnam", lambda name: user)
    monkeypatch.setattr(grp, "getgrnam", lambda name: group)
    held = []
    @contextmanager
    def private_home(path, *, directory, private_uid):
        assert (str(path), directory, private_uid) == (home, True, 470)
        held.append("open")
        try:
            yield -1, info
        finally:
            held.append("closed")
    monkeypatch.setattr(realm, "_native_open", private_home)
    def quiescent(uid):
        assert uid == 470
        if fault == "live-worker":
            raise RuntimeError("worker uid active")
    monkeypatch.setattr(credential, "_assert_worker_quiescent", quiescent)
    monkeypatch.setattr(credential, "verify_provider_credential",
                        lambda *args: pytest.fail("initial publication must not read credentials"))
    with ExitStack() as custody:
        if fault == "none":
            pub._require_initial_native_context(prior, custody)
            assert held == ["open"]
        else:
            with pytest.raises((ValueError, RuntimeError)):
                pub._require_initial_native_context(prior, custody)
    if held:
        assert held == ["open", "closed"]


@pytest.mark.parametrize("gate", ["require_exact_install", "require_transaction_absent",
    "require_services_already_stopped", "require_service_uids_quiescent",
    "require_runtime_quiescent"])
def test_original_owner_gates_run_before_native_selection_or_reference_mint(publisher, gate):
    def refused(*args):
        raise RuntimeError("owner refused")
    setattr(publisher.owner, gate, refused)
    with pytest.raises(pub.FinitePublicationRefused):
        invoke(publisher)
    assert publisher.selections == 0 and publisher.references == []
    assert list(pub.owner.CONFIG_ROOT.iterdir()) == []
