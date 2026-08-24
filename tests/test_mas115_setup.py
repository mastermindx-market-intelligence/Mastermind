"""MAS-115 operator setup — hermetic privacy and fail-closed tests."""
from __future__ import annotations

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
    monkeypatch.setattr(setup, "_load_current_provision", lambda: (None, "PROVISION_MISSING"))
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
    monkeypatch.setattr(
        setup, "_load_current_provision",
        lambda: ({"vendor": "multilogin"}, None),
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
