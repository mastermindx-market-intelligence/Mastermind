"""MAS-115 operator setup — hermetic privacy and fail-closed tests."""
from __future__ import annotations

import inspect
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import mas115_multilogin_port_policy as port_policy
from integrations.chairman_surfaces import nonseat_canary as canary
from scripts import mas115_keychain_store as keychain_store
from scripts import mas115_setup as setup


def test_documented_direct_status_command_bootstraps_repository_imports(tmp_path):
    repo_root = Path(setup.__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["HOME"] = os.fspath(tmp_path)

    completed = subprocess.run(
        [sys.executable, "scripts/mas115_setup.py", "status"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    status = json.loads(completed.stdout)
    assert status["bindings_healthy"] is True
    assert status["chairman_seats_enrolled"] == 0
    assert status["disposable_provision_code"] == "PROVISION_MISSING"


def _mlx(index: int, *, running: bool = True) -> dict:
    digit = str(index)
    return {
        "env_manager": "multilogin",
        "workspace_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "folder_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "profile_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "running": running,
    }


def _selections() -> dict:
    return {
        seat: (_mlx(index), f"https://chatgpt.com/c/seat-{index}")
        for index, seat in enumerate(setup.SEAT_REFS, start=1)
    }


def _local_census(*additional_rows: dict) -> dict:
    """Exact live shape: three running seats plus any explicit candidates."""
    def _raw(row: dict) -> dict:
        return {key: value for key, value in row.items() if key != "env_manager"}

    return {
        "gologin": [],
        "multilogin": [
            *(_raw(_mlx(index)) for index in range(1, 4)),
            *(_raw(row) for row in additional_rows),
        ],
    }


def test_build_enrollment_document_is_exact_three_distinct_seats_and_preserves_unrelated():
    unrelated = sb.new_binding(
        work_ref="WS:OTHER", role="worker", provider="codex",
        locator_kind="codex_session", locator={"session_id": "session-other"},
        observed_at="2026-08-23T12:00:00Z",
        binding_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    old_chatgpt = sb.new_binding(
        work_ref=setup.WORK_REF, role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin", "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "url": "https://chatgpt.com/c/old",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
        binding_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )
    seat_one = _mlx(1)
    work_specific_chat = sb.new_binding(
        work_ref="WS:OTHER-CHAT", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": seat_one["folder_id"],
            "profile_id": seat_one["profile_id"],
            "url": "https://chatgpt.com/c/work-specific",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
        binding_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )
    doc = setup.build_enrollment_document(
        {"schema": sb.SCHEMA, "bindings": [unrelated, old_chatgpt, work_specific_chat]},
        _selections(), observed_at="2026-08-23T12:00:00Z",
    )
    assert sb.validate_bindings_document(doc) == []
    assert doc["bindings"][0] == unrelated
    chatgpt_rows = [row for row in doc["bindings"] if row["provider"] == "chatgpt"]
    assert {row["seat_ref"] for row in chatgpt_rows} == set(setup.SEAT_REFS)
    assert {row["work_ref"] for row in chatgpt_rows} == {setup.WORK_REF, "WS:OTHER-CHAT"}
    assert {row["role"] for row in chatgpt_rows} == {"ceo"}
    assert work_specific_chat in chatgpt_rows
    initial_destinations = [row for row in chatgpt_rows if row["work_ref"] == setup.WORK_REF]
    assert len(initial_destinations) == 3
    assert all(row["observed_at"] == "2026-08-23T12:00:00Z" for row in initial_destinations)
    assert sb.find_conflicts(doc) == []


def test_build_enrollment_document_refuses_partial_or_duplicate_mapping():
    partial = _selections()
    partial.pop("chatgpt3")
    with pytest.raises(setup.SetupRefusal, match="all three"):
        setup.build_enrollment_document(None, partial, observed_at="2026-08-23T12:00:00Z")

    duplicate = _selections()
    duplicate["chatgpt3"] = duplicate["chatgpt2"]
    with pytest.raises(setup.SetupRefusal, match="cannot be assigned"):
        setup.build_enrollment_document(None, duplicate, observed_at="2026-08-23T12:00:00Z")


def test_reenrollment_refuses_to_orphan_existing_work_chat_on_different_environment():
    conflicting = sb.new_binding(
        work_ref="WS:OTHER-CHAT", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin", "profile_id": "a" * 24,
            "url": "https://chatgpt.com/c/work-specific",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
    )
    with pytest.raises(setup.SetupRefusal, match="different environment"):
        setup.build_enrollment_document(
            {"schema": sb.SCHEMA, "bindings": [conflicting]},
            _selections(), observed_at="2026-08-23T12:00:00Z",
        )


@pytest.mark.parametrize(
    "url",
    ["https://chatgpt.com/", "https://chatgpt.com/g/g-p-project/project"],
)
def test_private_url_refuses_non_conversation_addresses(monkeypatch, url):
    monkeypatch.setattr(setup.getpass, "getpass", lambda _prompt: url)
    with pytest.raises(setup.SetupRefusal, match="exact conversation URL"):
        setup._private_url("hidden: ")


def test_private_url_accepts_exact_project_conversation_address(monkeypatch):
    url = "https://chatgpt.com/g/g-p-project-alpha/c/conversation-beta"
    monkeypatch.setattr(setup.getpass, "getpass", lambda _prompt: url)
    assert setup._private_url("hidden: ") == url


def test_disposable_preflight_requires_fresh_exact_three_seat_census_and_refuses_collision():
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    complete = setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-23T12:00:00Z",
    )
    disposable = _mlx(4, running=False)
    setup.assert_current_nonseat(complete, disposable, now=now)

    partial = dict(complete)
    partial["bindings"] = partial["bindings"][:-1]
    with pytest.raises(setup.SetupRefusal, match="all three current"):
        setup.assert_current_nonseat(partial, disposable, now=now)

    with pytest.raises(setup.SetupRefusal, match="collides"):
        setup.assert_current_nonseat(complete, _mlx(1, running=False), now=now)


def test_candidate_rows_normalizes_only_supported_local_identity_shapes():
    row = _mlx(1)
    census = {
        "multilogin": [{
            "workspace_id": row["workspace_id"], "folder_id": row["folder_id"],
            "profile_id": row["profile_id"], "running": True,
        }],
        "gologin": [{"profile_id": "a" * 24, "running": False}],
    }
    rows = setup._candidate_rows(census)
    assert len(rows) == 2
    assert {row["env_manager"] for row in rows} == {"gologin", "multilogin"}


def test_build_provision_requires_stopped_profile_and_exact_multilogin_core():
    with pytest.raises(setup.SetupRefusal, match="must be stopped"):
        setup.build_provision(_mlx(1, running=True), browser_type="mimic")
    stopped = _mlx(1, running=False)
    with pytest.raises(setup.SetupRefusal, match="positively identified"):
        setup.build_provision(stopped, browser_type=None)
    provision = setup.build_provision(stopped, browser_type="stealthfox")
    assert provision == {
        "schema": canary.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": stopped["profile_id"],
        "folder_id": stopped["folder_id"],
        "browser_type": "stealthfox",
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }


def _legacy_v2_provision() -> dict:
    stopped = _mlx(4, running=False)
    return {
        "schema": port_policy.LEGACY_PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": stopped["profile_id"],
        "folder_id": stopped["folder_id"],
        "browser_type": "mimic",
        "benign_origin": port_policy.LEGACY_BENIGN_ORIGIN,
        "disposable_ack": canary.REQUIRED_ACK,
    }


def _migration_bindings_loader():
    return setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-23T12:00:00Z",
    ), []


def test_legacy_migration_accepts_only_exact_v2_origin_and_preserves_identity(tmp_path):
    """Catches migration loss, loose origin acceptance, or non-atomic permissions."""
    path = tmp_path / "provision.json"
    legacy = _legacy_v2_provision()
    setup._atomic_private_json(legacy, path)
    migrated, code = setup._migrate_legacy_provision(
        path,
        bindings_loader=_migration_bindings_loader,
        now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )
    assert code is None
    assert migrated == {
        "schema": "mastermind.mas115_nonseat_canary_provision.v3",
        "vendor": "multilogin",
        "profile_id": legacy["profile_id"],
        "folder_id": legacy["folder_id"],
        "browser_type": "mimic",
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == migrated


def test_legacy_migration_threads_one_live_snapshot_through_stale_bindings(
    tmp_path, monkeypatch,
):
    """The v2 and post-write v3 gates share one live proof without refreshing bindings."""
    path = tmp_path / "provision.json"
    legacy = _legacy_v2_provision()
    setup._atomic_private_json(legacy, path)
    bindings = setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-01T00:00:00Z",
    )
    bindings_before = json.loads(json.dumps(bindings))
    snapshot = canary._seal_current_environment_snapshot(  # noqa: SLF001
        _local_census(_mlx(4, running=False)),
    )
    assert snapshot is not None
    observed = []
    real_legacy_load = canary.load_legacy_provision_for_migration
    real_current_load = canary.load_provision

    def _legacy_load(*args, **kwargs):
        observed.append(kwargs.get("current_environment_snapshot"))
        return real_legacy_load(*args, **kwargs)

    def _current_load(*args, **kwargs):
        observed.append(kwargs.get("current_environment_snapshot"))
        return real_current_load(*args, **kwargs)

    monkeypatch.setattr(canary, "load_legacy_provision_for_migration", _legacy_load)
    monkeypatch.setattr(canary, "load_provision", _current_load)
    migrated, code = setup._migrate_legacy_provision(  # noqa: SLF001
        path,
        bindings_loader=lambda: (bindings, []),
        now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        current_environment_snapshot=snapshot,
    )
    assert code is None and migrated is not None
    assert observed == [snapshot, snapshot]
    assert bindings == bindings_before


@pytest.mark.parametrize(
    "origin",
    (
        "http://127.0.0.1:65535",
        "http://localhost:7777",
        "https://127.0.0.1:7777",
        "http://evil.example:7777",
    ),
)
def test_legacy_migration_refuses_every_nonhistorical_origin(tmp_path, origin):
    """Catches broad migration of an unrecognized or already-edited target."""
    legacy = _legacy_v2_provision()
    legacy["benign_origin"] = origin
    path = tmp_path / "provision.json"
    setup._atomic_private_json(legacy, path)
    migrated, code = setup._migrate_legacy_provision(
        path,
        bindings_loader=_migration_bindings_loader,
        now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )
    assert migrated is None
    assert code == "DISALLOWED_TARGET"
    assert json.loads(path.read_text(encoding="utf-8")) == legacy


@pytest.mark.parametrize("mutation", ("gologin", "stealthfox"))
def test_legacy_migration_refuses_non_multilogin_mimic_without_rewrite(tmp_path, mutation):
    """Catches rewriting a legacy provision outside the approved Mimic carrier."""
    legacy = _legacy_v2_provision()
    if mutation == "stealthfox":
        legacy["browser_type"] = "stealthfox"
    else:
        legacy = {
            "schema": port_policy.LEGACY_PROVISION_SCHEMA,
            "vendor": "gologin",
            "profile_id": "a" * 24,
            "benign_origin": port_policy.LEGACY_BENIGN_ORIGIN,
            "disposable_ack": canary.REQUIRED_ACK,
        }
    path = tmp_path / "provision.json"
    setup._atomic_private_json(legacy, path)
    migrated, code = setup._migrate_legacy_provision(
        path,
        bindings_loader=_migration_bindings_loader,
        now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )
    assert migrated is None
    assert code == "DISALLOWED_TARGET"
    assert json.loads(path.read_text(encoding="utf-8")) == legacy


@pytest.mark.parametrize(
    "marker,expected",
    [("Default", "mimic"), ("prefs.js", "stealthfox")],
)
def test_browser_core_detection_reads_shape_not_profile_content(tmp_path, marker, expected):
    row = _mlx(1, running=False)
    profile = tmp_path / row["workspace_id"] / row["folder_id"] / row["profile_id"]
    profile.mkdir(parents=True)
    target = profile / marker
    if marker == "Default":
        target.mkdir()
    else:
        target.write_text("private-content-never-read", encoding="utf-8")
    assert setup._detect_multilogin_browser_type(row, mlx_profiles_root=str(tmp_path)) == expected


def test_credential_setup_execs_fixed_secret_owner_with_no_secret_carrier():
    argv = setup.credential_setup_argv("multilogin")
    assert argv == [sys.executable, str(Path(keychain_store.__file__).resolve())]
    assert not any("token" in value.lower() or "password=" in value.lower() for value in argv)
    with pytest.raises(setup.SetupRefusal, match="GoLogin live lifecycle remains unsupported"):
        setup.credential_setup_argv("gologin")


def _synthetic_long_jwt() -> str:
    return ".".join(("a" * 200, "b" * 200, "c" * 333))


def test_long_multilogin_jwt_reaches_only_fixed_keychain_writer():
    token = _synthetic_long_jwt()
    assert len(token) == 735

    class _FakeApi:
        def __init__(self):
            self.added = None

        def find_item(self):
            return None

        def add_item(self, secret):
            self.added = secret

    api = _FakeApi()
    out = io.StringIO()
    err = io.StringIO()
    code = keychain_store.main(
        prompt_fn=lambda _prompt: token,
        api_factory=lambda: api,
        stdout=out,
        stderr=err,
    )
    assert code == 0
    assert api.added == token.encode("ascii")
    assert token not in out.getvalue()
    assert token not in err.getvalue()
    assert err.getvalue() == ""


def test_keychain_writer_coordinates_match_the_fixed_canary_reader():
    assert keychain_store._KEYCHAIN_SERVICE.decode("ascii") == setup.vendors._KEYCHAIN_SERVICE
    assert keychain_store._KEYCHAIN_ACCOUNT.decode("ascii") == setup.vendors._KEYCHAIN_ACCOUNT


def test_keychain_writer_launders_dynamic_framework_errors_without_echo():
    token = _synthetic_long_jwt()
    out = io.StringIO()
    err = io.StringIO()
    code = keychain_store.main(
        prompt_fn=lambda _prompt: token,
        api_factory=lambda: (_ for _ in ()).throw(RuntimeError(token)),
        stdout=out,
        stderr=err,
    )
    assert code == 2
    assert token not in out.getvalue()
    assert token not in err.getvalue()
    assert out.getvalue() == ""
    assert err.getvalue() == "REFUSED: Multilogin credential was not stored.\n"


def test_keychain_writer_updates_and_releases_only_existing_fixed_item():
    token = _synthetic_long_jwt()

    class _FakeApi:
        def __init__(self):
            self.calls = []

        def find_item(self):
            self.calls.append(("find",))
            return "fixed-item-ref"

        def add_item(self, secret):
            self.calls.append(("add", secret))

        def modify_item(self, item, secret):
            self.calls.append(("modify", item, secret))

        def release_item(self, item):
            self.calls.append(("release", item))

    api = _FakeApi()
    keychain_store._store_secret(token.encode("ascii"), api)
    assert api.calls == [
        ("find",),
        ("modify", "fixed-item-ref", token.encode("ascii")),
        ("release", "fixed-item-ref"),
    ]


@pytest.mark.parametrize(
    "value",
    [
        "a" * 126 + ".b",
        "a" * 40 + "." + "b" * 40 + "." + "c" * 40,
        " " + _synthetic_long_jwt(),
        _synthetic_long_jwt() + "\n",
        "a" * (keychain_store._MAX_SECRET_BYTES + 1) + ".b.c",
    ],
)
def test_keychain_writer_rejects_truncated_malformed_or_oversized_values_without_echo(value):
    out = io.StringIO()
    err = io.StringIO()
    code = keychain_store.main(
        prompt_fn=lambda _prompt: value,
        api_factory=lambda: (_ for _ in ()).throw(AssertionError("must not open Keychain")),
        stdout=out,
        stderr=err,
    )
    assert code == 2
    assert value not in out.getvalue()
    assert value not in err.getvalue()
    assert out.getvalue() == ""
    assert err.getvalue() == "REFUSED: Multilogin credential was not stored.\n"


def test_live_provision_loader_supplies_current_utc_to_fail_closed_census(monkeypatch):
    observed = {}

    def fake_load(path, *, now):
        observed["path"] = path
        observed["now"] = now
        return {"accepted": True}, None

    monkeypatch.setattr(setup.canary, "load_provision", fake_load)
    before = datetime.now(timezone.utc)
    loaded, code = setup._load_current_provision()
    after = datetime.now(timezone.utc)

    assert loaded == {"accepted": True}
    assert code is None
    assert observed["path"] == canary.DEFAULT_PROVISION_PATH
    assert before <= observed["now"] <= after
    assert observed["now"].tzinfo is timezone.utc


def test_atomic_private_provision_is_0600_and_canonical(tmp_path):
    path = tmp_path / "private" / "provision.json"
    doc = setup.build_provision(_mlx(1, running=False), browser_type="mimic")
    setup._atomic_private_json(doc, path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == doc
    assert path.read_text(encoding="utf-8") == json.dumps(doc, indent=2, sort_keys=True) + "\n"


def test_configure_command_migrates_then_routes_fixed_default_provision(monkeypatch):
    """Catches caller-selected configuration fields or a skipped legacy migration."""
    calls = []
    snapshot = canary._seal_current_environment_snapshot(  # noqa: SLF001
        _local_census(_mlx(4, running=False)),
    )
    assert snapshot is not None
    monkeypatch.setattr(setup, "_acquire_current_environment_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda **kwargs: (
            (None, "PROVISION_MISSING")
            if kwargs.get("current_environment_snapshot") is snapshot
            else (_ for _ in ()).throw(AssertionError("must thread the setup snapshot"))
        ),
    )
    monkeypatch.setattr(
        setup,
        "_migrate_legacy_provision",
        lambda *args, **kwargs: ({"vendor": "multilogin"}, None),
    )
    monkeypatch.setattr(setup.vendors, "main", lambda argv: calls.append(argv) or 0)
    assert setup.main(["configure-canary-port", "--vendor", "multilogin"]) == 0
    assert calls == [[
        "configure-canary-port",
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ]]


def test_configure_command_reuses_valid_v3_without_migration(monkeypatch):
    """Catches making the idempotent configuration command v2-only."""
    calls = []
    snapshot = canary._seal_current_environment_snapshot(  # noqa: SLF001
        _local_census(_mlx(4, running=False)),
    )
    assert snapshot is not None
    monkeypatch.setattr(setup, "_acquire_current_environment_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda **kwargs: (
            ({"vendor": "multilogin"}, None)
            if kwargs.get("current_environment_snapshot") is snapshot
            else (_ for _ in ()).throw(AssertionError("must thread the setup snapshot"))
        ),
    )
    monkeypatch.setattr(
        setup, "_migrate_legacy_provision",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not migrate v3")),
    )
    monkeypatch.setattr(setup.vendors, "main", lambda argv: calls.append(argv) or 0)
    assert setup.main(["configure-canary-port", "--vendor", "multilogin"]) == 0
    assert calls[0][0] == "configure-canary-port"


def test_run_canary_routes_run_operation_without_update_authority(monkeypatch):
    """Catches accidentally granting the ordinary run path configuration authority."""
    calls = []
    monkeypatch.setattr(setup.vendors, "main", lambda argv: calls.append(argv) or 0)
    assert setup.main(["run-canary", "--vendor", "multilogin"]) == 0
    assert calls == [[
        "run",
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ]]


def test_configure_command_refuses_gologin_before_provision_or_vendor(monkeypatch):
    """Catches widening the one-shot profile update beyond Multilogin."""
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda: (_ for _ in ()).throw(AssertionError("must refuse before provision")),
    )
    monkeypatch.setattr(
        setup.vendors, "main",
        lambda argv: (_ for _ in ()).throw(AssertionError("must refuse before vendor")),
    )
    assert setup.main(["configure-canary-port", "--vendor", "gologin"]) == 2


# ---------------------------------------------------------------------------
# REALM1-C1 — MAS-115 peer create/rollback coordinator (Mastermind #385)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic_peer_fixed_path_gates(request, monkeypatch):
    if not request.node.name.startswith("test_peer_setup_"):
        return
    monkeypatch.setattr(setup.vendors, "coordinator_peer_paths_safe", lambda _operation: True)
    monkeypatch.setattr(setup.vendors, "coordinator_peer_rollback_receipt_ready", lambda: True)


def _peer_anchor_provision(row: dict) -> dict:
    return {
        "schema": canary.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": row["profile_id"],
        "folder_id": row["folder_id"],
        "browser_type": "mimic",
        "origin_policy": port_policy.ORIGIN_POLICY,
        "disposable_ack": canary.REQUIRED_ACK,
    }


_BOOTSTRAP_EVIDENCE = object()


def _bootstrap_coordinator_state(monkeypatch, *, running=False):
    row = _mlx(4, running=running)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-23T12:00:00Z",
    )
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt,
        "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr(
        setup.vendors,
        "mint_coordinator_peer_bootstrap_evidence",
        lambda: _BOOTSTRAP_EVIDENCE,
        raising=False,
    )
    return row, provision


def test_peer_setup_bootstrap_command_delegates_only_after_exact_local_ceremony(monkeypatch):
    """The exact phrase precedes a fresh evidence mint and one delegation."""
    _row, _provision = _bootstrap_coordinator_state(monkeypatch)
    expected_phrase = getattr(setup, "_CONFIRM_BOOTSTRAP_PEER", None)
    assert expected_phrase == "BOOTSTRAP THE EXISTING DISPOSABLE PEER LIFECYCLE"
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: expected_phrase)
    calls = []
    monkeypatch.setattr(
        setup.vendors,
        "run_coordinator_peer_bootstrap",
        lambda **kwargs: calls.append(kwargs) or setup.vendors.CREATED_THIS_CALL,
        raising=False,
    )

    assert setup.main(["bootstrap-peer-lifecycle"]) == 0
    assert calls == [{"authorization": _BOOTSTRAP_EVIDENCE}]


def test_peer_setup_bootstrap_confirmation_mismatch_refuses_without_state_effect(monkeypatch):
    """A generic Boolean/string or either existing ceremony cannot bootstrap."""
    _bootstrap_coordinator_state(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: setup._CONFIRM_CREATE_PEER)
    monkeypatch.setattr(
        setup.vendors,
        "run_coordinator_peer_bootstrap",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("wrong phrase must create no bootstrap state"),
        ),
        raising=False,
    )
    handler = getattr(setup, "bootstrap_peer_interactive", None)
    assert callable(handler), "the distinct bootstrap coordinator is missing"
    with pytest.raises(setup.SetupRefusal, match="confirmation"):
        handler()


def test_peer_setup_bootstrap_running_anchor_refuses_before_confirmation_or_state(monkeypatch):
    """A locally running profile_A can never seed the lifecycle genesis."""
    _bootstrap_coordinator_state(monkeypatch, running=True)
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("running anchor must refuse before confirmation"),
        ),
    )
    monkeypatch.setattr(
        setup.vendors,
        "run_coordinator_peer_bootstrap",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("running anchor must create no bootstrap state"),
        ),
        raising=False,
    )
    handler = getattr(setup, "bootstrap_peer_interactive", None)
    assert callable(handler), "the distinct bootstrap coordinator is missing"
    with pytest.raises(setup.SetupRefusal, match="running|stop"):
        handler()


def test_peer_setup_bootstrap_refuses_failed_post_confirmation_evidence_mint(monkeypatch):
    """A changed post-phrase census never releases bootstrap authority."""
    _row, _provision = _bootstrap_coordinator_state(monkeypatch)
    censuses = iter((
        _local_census(_mlx(4, running=False)),
        _local_census(_mlx(4, running=True)),
    ))
    monkeypatch.setattr(setup.chatgpt, "list_local_environments", lambda: next(censuses))
    monkeypatch.setattr(
        "builtins.input", lambda *_a, **_k: setup._CONFIRM_BOOTSTRAP_PEER,
    )
    def _refusing_mint():
        census = setup.chatgpt.list_local_environments()
        candidate = next(
            item for item in census["multilogin"]
            if item["profile_id"] == _mlx(4)["profile_id"]
            and item["folder_id"] == _mlx(4)["folder_id"]
        )
        assert candidate["running"] is True
        return None

    monkeypatch.setattr(
        setup.vendors,
        "mint_coordinator_peer_bootstrap_evidence",
        _refusing_mint,
        raising=False,
    )
    monkeypatch.setattr(
        setup.vendors,
        "run_coordinator_peer_bootstrap",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("a newly running anchor must receive no authority"),
        ),
    )

    with pytest.raises(setup.SetupRefusal, match="evidence"):
        setup.bootstrap_peer_interactive()


def test_peer_setup_bootstrap_refuses_missing_bindings_before_anchor_or_confirmation(monkeypatch):
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (None, ["stale"]))
    monkeypatch.setattr(
        setup,
        "_load_current_provision",
        lambda: (_ for _ in ()).throw(AssertionError("must refuse before anchor")),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("must refuse before confirmation"),
        ),
    )
    handler = getattr(setup, "bootstrap_peer_interactive", None)
    assert callable(handler), "the distinct bootstrap coordinator is missing"
    with pytest.raises(setup.SetupRefusal, match="enroll"):
        handler()


def test_peer_setup_bootstrap_coordinator_never_touches_secret_http_or_vendor_cli(monkeypatch):
    """The ceremony performs local state bootstrap only, never profile work."""
    _bootstrap_coordinator_state(monkeypatch)
    handler = getattr(setup, "bootstrap_peer_interactive", None)
    assert callable(handler), "the distinct bootstrap coordinator is missing"
    source = inspect.getsource(handler)
    for forbidden in (
        "Credential(", ".expose(", "_open_keychain_credential_pipe",
        "BoundedHttpClient(", "httpx.", "vendors.main(",
    ):
        assert forbidden not in source
    monkeypatch.setattr(
        "builtins.input", lambda *_a, **_k: setup._CONFIRM_BOOTSTRAP_PEER,
    )
    monkeypatch.setattr(
        setup.vendors,
        "run_coordinator_peer_bootstrap",
        lambda **_kwargs: setup.vendors.EXISTING_EXACT,
        raising=False,
    )
    assert handler() == 0


def test_peer_setup_direct_vendor_cli_cannot_invoke_bootstrap():
    """Only mas115_setup exposes the ceremony; the secret helper CLI does not."""
    with pytest.raises(SystemExit) as exc_info:
        setup.vendors.main(["bootstrap-peer-lifecycle"])
    assert exc_info.value.code == 2


def test_peer_setup_prepare_disposable_does_not_create_a_competing_bootstrap_fence(tmp_path):
    """Ordinary new-anchor preparation keeps its existing genesis path only."""
    provision = _peer_anchor_provision(_mlx(4, running=False))
    anchor_path = tmp_path / "anchor.json"
    state_path = tmp_path / "peer-state.json"
    peer_path = tmp_path / "peer-provision.json"
    assert setup._prepare_anchor_with_peer_lifecycle(
        provision,
        anchor_path=anchor_path,
        state_path=state_path,
        peer_provision_path=peer_path,
    ) == setup.vendors.CREATED_THIS_CALL
    fence_path_for = getattr(setup.vendors, "_peer_bootstrap_fence_path", None)
    assert callable(fence_path_for), "the fixed bootstrap coordinate is missing"
    assert not fence_path_for(state_path).exists()


@pytest.mark.parametrize("deleted", ("anchor_and_state", "state_and_witness"))
def test_peer_setup_loss_fence_never_recreates_a_consumed_genesis(tmp_path, deleted):
    """Setup does not treat missing runtime records as a fresh installation."""
    provision = _peer_anchor_provision(_mlx(4, running=False))
    anchor_path = tmp_path / "anchor.json"
    state_path = tmp_path / "peer-state.json"
    peer_provision_path = tmp_path / "peer-provision.json"
    assert setup._prepare_anchor_with_peer_lifecycle(
        provision,
        anchor_path=anchor_path,
        state_path=state_path,
        peer_provision_path=peer_provision_path,
    ) == setup.vendors.CREATED_THIS_CALL
    witness_path = setup.vendors._peer_genesis_witness_path(state_path)  # noqa: SLF001
    assert setup.vendors._commit_peer_intent(  # noqa: SLF001
        state_path,
        folder_id=provision["folder_id"],
        anchor_profile_id=provision["profile_id"],
        peer_name=setup.vendors.peer_profile_name(
            provision["folder_id"], provision["profile_id"],
        ),
        peer_provision_path=peer_provision_path,
    ) == setup.vendors.CREATED_THIS_CALL

    if deleted == "anchor_and_state":
        anchor_path.unlink()
        state_path.unlink()
        witness_before = witness_path.read_bytes()
    else:
        state_path.unlink()
        witness_path.unlink()
        anchor_before = anchor_path.read_bytes()

    with pytest.raises(setup.SetupRefusal, match="genesis is unavailable|already consumed"):
        setup._prepare_anchor_with_peer_lifecycle(
            provision,
            anchor_path=anchor_path,
            state_path=state_path,
            peer_provision_path=peer_provision_path,
        )

    assert not state_path.exists()
    if deleted == "anchor_and_state":
        assert not anchor_path.exists()
        assert witness_path.read_bytes() == witness_before
    else:
        assert not witness_path.exists()
        assert anchor_path.read_bytes() == anchor_before


def _refuse_any_peer_dispatch(monkeypatch, message):
    def _raise(*_args, **_kwargs):
        raise AssertionError(message)

    monkeypatch.setattr(setup.vendors, "run_coordinator_peer_create", _raise)
    monkeypatch.setattr(setup.vendors, "run_coordinator_peer_rollback", _raise)


@pytest.mark.parametrize("command", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_setup_gologin_refuses_before_bindings_or_provision(monkeypatch, command):
    """Coordinator #385-2: GoLogin is refused before any local I/O."""
    monkeypatch.setattr(
        setup.sb, "load_bindings",
        lambda: (_ for _ in ()).throw(AssertionError("must refuse GoLogin before reading bindings")),
    )
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda: (_ for _ in ()).throw(AssertionError("must refuse GoLogin before loading a provision")),
    )
    _refuse_any_peer_dispatch(monkeypatch, "must refuse GoLogin before any dispatch")
    assert setup.main([command, "--vendor", "gologin"]) == 2


@pytest.mark.parametrize("command", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_setup_missing_bindings_refuses_before_provision_or_dispatch(monkeypatch, command):
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (None, ["stale"]))
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda: (_ for _ in ()).throw(AssertionError("must refuse before loading a provision")),
    )
    _refuse_any_peer_dispatch(monkeypatch, "must refuse before any dispatch")
    assert setup.main([command, "--vendor", "multilogin"]) == 2


@pytest.mark.parametrize("command", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_setup_missing_provision_refuses_after_one_census_without_dispatch(monkeypatch, command):
    row = _mlx(4, running=False)
    census_calls = []
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: ({"schema": sb.SCHEMA, "bindings": []}, []))
    monkeypatch.setattr(
        setup,
        "_load_current_provision",
        lambda **_kwargs: (None, "PROVISION_MISSING"),
    )
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: census_calls.append("inventory") or _local_census(row),
    )
    _refuse_any_peer_dispatch(monkeypatch, "must refuse before any dispatch")
    assert setup.main([command, "--vendor", "multilogin"]) == 2
    assert census_calls == ["inventory"]


@pytest.mark.parametrize("command", ("create-peer-profile", "rollback-peer-profile"))
def test_peer_setup_seat_collision_refuses_before_confirmation_or_dispatch(monkeypatch, command):
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(
        setup, "assert_current_nonseat",
        lambda *a, **k: (_ for _ in ()).throw(setup.SetupRefusal("the selected disposable profile collides with a Chairman seat")),
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must refuse before prompting for confirmation")),
    )
    _refuse_any_peer_dispatch(monkeypatch, "must refuse before any dispatch")
    with pytest.raises(setup.SetupRefusal, match="collides"):
        (setup.create_peer_interactive if command == "create-peer-profile" else setup.rollback_peer_interactive)()


@pytest.mark.parametrize(
    ("command", "confirm_const"),
    (
        ("create-peer-profile", "_CONFIRM_CREATE_PEER"),
        ("rollback-peer-profile", "_CONFIRM_ROLLBACK_PEER"),
    ),
)
def test_peer_setup_confirmation_mismatch_refuses_without_dispatch(monkeypatch, command, confirm_const):
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "the wrong phrase")
    _refuse_any_peer_dispatch(monkeypatch, "a confirmation mismatch must dispatch nothing")
    handler = setup.create_peer_interactive if command == "create-peer-profile" else setup.rollback_peer_interactive
    with pytest.raises(setup.SetupRefusal, match="confirmation"):
        handler()


def test_peer_setup_create_happy_path_delegates_to_exact_capability(monkeypatch):
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: setup._CONFIRM_CREATE_PEER)
    calls = []
    monkeypatch.setattr(
        setup.vendors, "run_coordinator_peer_create",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or 0,
    )
    assert setup.main(["create-peer-profile", "--vendor", "multilogin"]) == 0
    assert calls == [([
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ], {})]


def test_peer_setup_rollback_without_release_receipt_refuses_before_confirmation(monkeypatch):
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr(setup.vendors, "coordinator_peer_rollback_receipt_ready", lambda: False)
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("missing downstream ownership proof must refuse before confirmation"),
        ),
    )
    _refuse_any_peer_dispatch(monkeypatch, "missing downstream ownership proof must dispatch nothing")
    with pytest.raises(setup.SetupRefusal, match="ownership"):
        setup.rollback_peer_interactive()


def test_peer_setup_rollback_with_release_receipt_delegates_to_distinct_capability(monkeypatch):
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: setup._CONFIRM_ROLLBACK_PEER)
    calls = []
    monkeypatch.setattr(
        setup.vendors, "run_coordinator_peer_rollback",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or 0,
    )
    assert setup.rollback_peer_interactive() == 0
    assert calls == [([
        "--vendor", "multilogin",
        "--provision-path", str(Path(canary.DEFAULT_PROVISION_PATH).expanduser()),
    ], {})]


def test_peer_setup_coordinator_never_touches_credential_or_http(monkeypatch):
    """The coordinator forwards only argv/exit code — it never reads a
    credential, constructs vendor HTTP, or sees a raw vendor response."""
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    complete = setup.build_enrollment_document(None, _selections(), observed_at="2026-08-23T12:00:00Z")
    monkeypatch.setattr(setup.sb, "load_bindings", lambda: (complete, []))
    monkeypatch.setattr(setup, "_load_current_provision", lambda **_kwargs: (provision, None))
    monkeypatch.setattr(
        setup.chatgpt, "list_local_environments",
        lambda: _local_census(row),
    )
    monkeypatch.setattr(setup, "assert_current_nonseat", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: setup._CONFIRM_CREATE_PEER)

    source = inspect.getsource(setup.create_peer_interactive) + inspect.getsource(setup.rollback_peer_interactive)
    for forbidden in ("Credential(", ".expose(", "_open_keychain_credential_pipe", "BoundedHttpClient(", "httpx."):
        assert forbidden not in source

    monkeypatch.setattr(setup.vendors, "run_coordinator_peer_create", lambda argv, **kwargs: 0)
    assert setup.main(["create-peer-profile", "--vendor", "multilogin"]) == 0


def test_atomic_private_json_has_exactly_one_implementation(tmp_path):
    """#3.10: after the move, setup._atomic_private_json must be the same
    object as vendors.atomic_private_json — never a second copy."""
    assert setup._atomic_private_json is setup.vendors.atomic_private_json
    doc = {"a": 1}
    path = tmp_path / "x.json"
    setup.vendors.atomic_private_json(doc, path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == doc


def test_realm1_matching_local_row_seals_once_bypasses_reducer_and_threads_same_snapshot(monkeypatch):
    """The anchor check must not resample or pass through permissive candidate filtering."""
    row = _mlx(4, running=False)
    provision = _peer_anchor_provision(row)
    bindings = setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-01T00:00:00Z",
    )
    raw = _local_census(row)
    raw_before = json.loads(json.dumps(raw))
    bindings_before = json.loads(json.dumps(bindings))
    calls = []

    def _inventory():
        calls.append(("inventory", None))
        return raw

    def _load(**kwargs):
        snapshot = kwargs.get("current_environment_snapshot")
        assert canary._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001
        calls.append(("load", snapshot))
        return provision, None

    def _assert_nonseat(_bindings, _row, **kwargs):
        snapshot = kwargs.get("current_environment_snapshot")
        assert canary._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001
        calls.append(("nonseat", snapshot))

    monkeypatch.setattr(setup.chatgpt, "list_local_environments", _inventory)
    monkeypatch.setattr(setup, "_load_current_provision", _load)
    monkeypatch.setattr(setup, "assert_current_nonseat", _assert_nonseat)
    monkeypatch.setattr(
        setup,
        "_candidate_rows",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("strict snapshot rows must bypass the permissive reducer"),
        ),
    )
    monkeypatch.setattr(
        setup.sb,
        "save_bindings",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("a live census must never persist or refresh navigation bindings"),
        ),
    )

    matched = setup._matching_local_row(bindings)  # noqa: SLF001
    assert dict(matched) == row
    assert [name for name, _value in calls] == ["inventory", "load", "nonseat"]
    snapshots = [value for name, value in calls if name in ("load", "nonseat")]
    assert len(snapshots) == 2 and snapshots[0] is snapshots[1]
    assert raw == raw_before
    assert bindings == bindings_before


def test_realm1_setup_live_snapshot_uses_only_the_strict_private_producer(monkeypatch):
    """Hazardous setup gates may not fall back to capped tolerant discovery."""
    raw = _local_census(_mlx(4, running=False))
    calls = []

    def _strict():
        calls.append("strict")
        return raw

    monkeypatch.setattr(
        setup.chatgpt,
        "_strict_list_local_environments",
        _strict,
        raising=False,
    )
    monkeypatch.setattr(
        setup.chatgpt,
        "list_local_environments",
        lambda: (_ for _ in ()).throw(AssertionError("legacy discovery is not trusted")),
    )
    snapshot = setup._acquire_current_environment_snapshot()  # noqa: SLF001
    assert canary._is_current_environment_snapshot(snapshot) is True  # noqa: SLF001
    assert calls == ["strict"]
