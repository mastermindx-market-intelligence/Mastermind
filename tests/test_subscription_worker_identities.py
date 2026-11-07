from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.subscription_harness_bindings import get_binding
from ops.executive_os import provider_worker_slots as slots


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "ops" / "executive_os" / "bootstrap-host.sh"


def test_legacy_codex_inventory_is_byte_contract_unchanged() -> None:
    assert tuple(row.slot_id for row in slots.all_slots()) == (
        "codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03"
    )
    assert tuple(row.worker_uid for row in slots.all_slots()) == (451, 454, 455, 456)


def test_subscription_inventory_has_two_held_codex_backed_realms() -> None:
    catalog = slots.subscription_slots()
    assert tuple(row.slot_id for row in catalog) == (
        "alibaba-token-01", "minimax-token-01"
    )
    assert tuple(row.worker_uid for row in catalog) == (459, 460)
    assert tuple(row.worker_gid for row in catalog) == (459, 460)
    assert tuple(row.worker_user for row in catalog) == (
        "_mastermind_alibaba_01", "_mastermind_minimax_01"
    )
    for row in catalog:
        binding = get_binding(row.harness_binding_id)
        assert binding.provider == row.provider
        assert binding.profile_id == row.profile_id
        assert binding.adapter_id == "codex-cli"
        assert binding.implementation_state == "BUILT_NOT_PROVEN"
        assert binding.autonomous_allowed is False


def test_subscription_inventory_is_collision_free_and_has_no_capacity_authority() -> None:
    legacy = slots.all_slots()
    subscription = slots.subscription_slots()
    assert not ({row.worker_uid for row in legacy} & {row.worker_uid for row in subscription})
    assert not ({row.worker_gid for row in legacy} & {row.worker_gid for row in subscription})
    assert not ({row.provider_home for row in legacy} & {row.provider_home for row in subscription})
    rendered = json.dumps([row.public_descriptor() for row in subscription])
    for forbidden in (
        "capacity_capability_id", "capability_generation", "account_label",
        "credential", "api_key", "auth.json", "/Library/", "/var/db/", "@",
    ):
        assert forbidden not in rendered
    assert all(row.public_descriptor()["admission_state"] == "HELD_FOR_REAL_CANARY" for row in subscription)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: [replace(rows[0], worker_uid=458), rows[1]],
        lambda rows: [replace(rows[0], worker_gid=451), rows[1]],
        lambda rows: [replace(rows[0], worker_user="_mastermind_minimax_01"), rows[1]],
        lambda rows: [replace(rows[0], harness_binding_id="minimax-token-plan.codex-responses"), rows[1]],
        lambda rows: [rows[0], replace(rows[1], worker_uid=459)],
    ],
)
def test_subscription_inventory_refuses_identity_or_binding_mutation(mutation) -> None:
    with pytest.raises(slots.SlotCatalogError):
        slots.validate_subscription_slots(mutation(list(slots.subscription_slots())))


def test_subscription_cli_requires_explicit_catalog_switch() -> None:
    assert slots.main(["--subscription", "alibaba-token-01", "worker_uid"]) == 0
    assert slots.main(["alibaba-token-01", "worker_uid"]) == 2
    assert slots.main(["--subscription", "codex-pro-01", "worker_uid"]) == 2


def test_bootstrap_prepares_subscription_principals_without_capacity_or_service_arming() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'SUBSCRIPTION_SLOT_IDS=("alibaba-token-01" "minimax-token-01")' in source
    assert 'subscription_slot_field()' in source
    assert 'for slot_id in "${SUBSCRIPTION_SLOT_IDS[@]}"; do' in source
    assert 'ensure_group "$slot_group" "$slot_gid"' in source
    assert 'ensure_user "$slot_user" "$slot_uid" "$slot_gid" "$slot_home"' in source
    assert '"/var/log/mastermind-executive/workers/$slot_id"' in source
    for forbidden in (
        "capacity_capability_id", "register-worker", "bootstrap system",
        "launchctl bootstrap", "subscription_provider_credential.py --enroll",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("field", ["worker_uid", "worker_gid"])
@pytest.mark.parametrize("value", [459.0, 460.0, True, False, "459", None, [459], {"value": 459}])
def test_subscription_numeric_identity_requires_exact_integer(field, value):
    catalog = list(slots.subscription_slots())
    catalog[0] = replace(catalog[0], **{field: value})
    with pytest.raises(slots.SlotCatalogError):
        slots.validate_subscription_slots(catalog)


@pytest.mark.parametrize("field", ["worker_uid", "worker_gid"])
def test_subscription_numeric_identity_refuses_integer_subclass(field):
    class AlternateInt(int):
        pass
    catalog = list(slots.subscription_slots())
    catalog[0] = replace(catalog[0], **{field: AlternateInt(459)})
    with pytest.raises(slots.SlotCatalogError):
        slots.validate_subscription_slots(catalog)


def test_legacy_cli_does_not_validate_the_unselected_subscription_catalog(monkeypatch, capsys):
    def unavailable():
        raise slots.SlotCatalogError("held_subscription_catalog_unavailable")
    monkeypatch.setattr(slots, "subscription_slots", unavailable)
    assert slots.main(["codex-pro-01", "worker_uid"]) == 0
    assert capsys.readouterr().out == "454\n"
    assert slots.main(["--subscription", "alibaba-token-01", "worker_uid"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("args", [
    ["--subscription", "alibaba-token-01", "oauth_seat_ref"],
    ["--subscription", "minimax-token-01", "auth_path"],
    ["--subscription", "missing-token-01", "worker_uid"],
    ["codex-01", "profile_id"],
])
def test_selected_catalog_refuses_wrong_field_or_identity_without_output(args, capsys):
    assert slots.main(args) == 2
    assert capsys.readouterr().out == ""


def test_subscription_bootstrap_uses_current_native_acl_guard():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    marker = 'for slot_id in "${SUBSCRIPTION_SLOT_IDS[@]}"; do'
    section = source[source.rindex(marker):]
    assert 'require_native_no_acl one "$protected_path"' in section
    assert "unexpected or unreadable filesystem ACL" in section
    assert "stat -f '%Sp'" not in section
    assert source.index("bootstrap_secondary_worker\n  exit 0") < source.index(
        'ensure_numeric_unused Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"'
    )


def test_subscription_descriptors_do_not_change_native_provider_projection():
    legacy = slots.all_slots()
    assert all(row.provider_family == "openai" for row in legacy)
    assert all(row.auth_path == row.provider_home / "auth.json" for row in legacy)
    worker_name = "_mastermind_fixture_native"
    config = {
        "native_provider": "claude",
        "native_realm_enrollment": {"slot_id": "claude-native-01"},
        "worker_user": worker_name,
        "worker_uid": 470,
        "worker_gid": 471,
        "control_uid": 450,
    }
    row = slots.native_slot_from_config(config)
    assert (row.worker_user, row.worker_uid, row.worker_gid) == (worker_name, 470, 471)
    assert row.provider_family == "anthropic"
    assert row.auth_path == row.provider_home / ".claude" / ".credentials.json"
    assert tuple(item.slot_id for item in slots.all_slots()) == (
        "codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03"
    )


# Frozen exact sites in the composed source. Tests never refresh these from a
# changed file; the registry and these assertions must retain the reviewed scope.
_SUBSCRIPTION_IDENTITY_SITES = ((168, 20, 44, "str", "\"_mastermind_alibaba_01\""), (169, 21, 45, "str", "\"_mastermind_alibaba_01\""), (170, 19, 22, "int", "459"), (171, 19, 22, "int", "459"), (180, 20, 44, "str", "\"_mastermind_minimax_01\""), (181, 21, 45, "str", "\"_mastermind_minimax_01\""), (182, 19, 22, "int", "460"), (183, 19, 22, "int", "460"), (288, 12, 36, "str", "\"_mastermind_alibaba_01\""), (296, 12, 36, "str", "\"_mastermind_minimax_01\""))
_SUBSCRIPTION_BOOTSTRAP_SITES = ((784, 21, 43, "str", "_mastermind_[a-z0-9_]*"), (786, 97, 120, "str", "_mastermind_agent_relay"), (792, 89, 92, "int", "457"))
_SUBSCRIPTION_IDENTITY_FINDINGS = [
    "_mastermind_alibaba_01", "_mastermind_alibaba_01", "459", "459",
    "_mastermind_minimax_01", "_mastermind_minimax_01", "460", "460",
    "_mastermind_alibaba_01", "_mastermind_minimax_01",
]


def _scoped_identity_diff(path, text, sites):
    lines = text.splitlines()
    result = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}"]
    for number in sorted({row[0] for row in sites}):
        result.extend([f"@@ -0,0 +{number},1 @@", "+" + lines[number - 1]])
    return "\n".join(result)


def _identity_scan(diff, postimages=None):
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
    return _scan_added_identity_diff(diff, source_postimages=postimages)


@pytest.mark.parametrize("path,expected", [
    ("ops/executive_os/provider_worker_slots.py", _SUBSCRIPTION_IDENTITY_SITES),
    ("ops/executive_os/bootstrap-host.sh", _SUBSCRIPTION_BOOTSTRAP_SITES),
])
def test_subscription_identity_records_preserve_exact_frozen_sites(path, expected):
    from tests.executive_fabric_release_identity_review import REVIEWED_FILES
    from tests.executive_identity_review import reviewed_literal_spans
    text = (ROOT / path).read_text(encoding="utf-8")
    assert REVIEWED_FILES[path]["sites"] == expected
    assert reviewed_literal_spans(path, text) == tuple(row[:4] for row in expected)
    assert _identity_scan(_scoped_identity_diff(path, text, expected), {path: text}) == []


def test_d8_provider_worker_identity_owner_admits_only_reviewed_subscription_rows():
    path = "ops/executive_os/provider_worker_slots.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    diff = _scoped_identity_diff(path, text, _SUBSCRIPTION_IDENTITY_SITES)
    assert _identity_scan(diff, {path: text}) == []
    assert _identity_scan(diff) == _SUBSCRIPTION_IDENTITY_FINDINGS
    foreign = "ops/other/provider_worker_slots.py"
    assert _identity_scan(
        _scoped_identity_diff(foreign, text, _SUBSCRIPTION_IDENTITY_SITES),
        {foreign: text},
    ) == _SUBSCRIPTION_IDENTITY_FINDINGS


@pytest.mark.parametrize("kind", ["unrelated", "token", "context", "relocation", "deleted"])
def test_subscription_identity_record_refuses_complete_source_drift(kind):
    from tests.executive_identity_review import reviewed_literal_spans
    from tests.test_ceo_submit_armed_composition import _d8_frozen_source_diff
    path = "ops/executive_os/provider_worker_slots.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    anchor = '        worker_user="_mastermind_alibaba_01",'
    if kind == "unrelated":
        changed = text + "\n# Unrelated byte drift still withdraws qualification.\n"
    elif kind == "token":
        changed = text.replace('worker_uid=459,', 'worker_uid=461,', 1)
    elif kind == "context":
        changed = text.replace(anchor, anchor + "  # context changed", 1)
    elif kind == "relocation":
        changed = "\n" + text
    else:
        changed = text.replace(anchor + "\n", "", 1)
    assert changed != text
    assert reviewed_literal_spans(path, changed) == ()
    findings = _identity_scan(_d8_frozen_source_diff(path, changed), {path: changed})
    assert "_mastermind_alibaba_01" in findings
    assert "_mastermind_minimax_01" in findings


def test_d8_provider_worker_identity_owner_refuses_duplicate_approved_line():
    from tests.executive_identity_review import reviewed_literal_spans
    path = "ops/executive_os/provider_worker_slots.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    duplicate = '        worker_user="_mastermind_alibaba_01",'
    changed = text + "\nif False:\n" + duplicate + "\n"
    assert changed.splitlines().count(duplicate) == 2
    assert reviewed_literal_spans(path, changed) == ()
    diff = _scoped_identity_diff(path, changed, _SUBSCRIPTION_IDENTITY_SITES)
    number = len(changed.splitlines())
    diff += f"\n@@ -0,0 +{number},1 @@\n+" + duplicate
    assert _identity_scan(diff, {path: changed}) == (
        _SUBSCRIPTION_IDENTITY_FINDINGS + ["_mastermind_alibaba_01"]
    )


def test_subscription_identity_record_exposes_added_unrelated_principal():
    from tests.executive_identity_review import reviewed_literal_spans
    path = "ops/executive_os/provider_worker_slots.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    changed = text + '\nworker_user="_mastermind_shadow"\nworker_uid=461\n'
    assert reviewed_literal_spans(path, changed) == ()
    diff = _scoped_identity_diff(path, changed, _SUBSCRIPTION_IDENTITY_SITES)
    first = len(changed.splitlines()) - 1
    diff += f"\n@@ -0,0 +{first},2 @@\n" + "\n".join(
        "+" + line for line in changed.splitlines()[-2:]
    )
    assert _identity_scan(diff, {path: changed}) == (
        _SUBSCRIPTION_IDENTITY_FINDINGS + ["_mastermind_shadow", "461"]
    )


def test_subscription_identity_diff_must_match_its_complete_postimage():
    path = "ops/executive_os/provider_worker_slots.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    diff = _scoped_identity_diff(path, text, _SUBSCRIPTION_IDENTITY_SITES)
    forged = diff.replace('worker_uid=459,', 'worker_uid=461,', 1)
    assert forged != diff
    with pytest.raises(AssertionError, match="diff/postimage line mismatch"):
        _identity_scan(forged, {path: text})


@pytest.mark.parametrize("change_mode", [False, True])
def test_subscription_bootstrap_identity_review_requires_the_exact_source(change_mode):
    from tests.executive_identity_review import reviewed_literal_spans
    path = "ops/executive_os/bootstrap-host.sh"
    text = (ROOT / path).read_text(encoding="utf-8")
    if change_mode:
        changed = text.replace("-m 0700", "-m 0710", 1)
    else:
        changed = text + "\n# Unrelated byte drift.\n"
    assert changed != text
    assert reviewed_literal_spans(path, changed) == ()
    assert _identity_scan(
        _scoped_identity_diff(path, changed, _SUBSCRIPTION_BOOTSTRAP_SITES),
        {path: changed},
    ) == ["_mastermind_", "_mastermind_agent_relay", "457"]


def test_subscription_private_directories_use_owner_only_permissions():
    import re
    import shlex
    from tests.test_secondary_worker_bootstrap import run

    source = BOOTSTRAP.read_text(encoding="utf-8")
    loops = re.findall(
        r'^for slot_id in "\$\{SUBSCRIPTION_SLOT_IDS\[@\]\}"; do\n.*?^done$',
        source, flags=re.MULTILINE | re.DOTALL,
    )
    blocks = [loop for loop in loops if "/usr/bin/install -d" in loop]
    assert len(blocks) == 2
    assert sum(block.count("/usr/bin/install -d") for block in blocks) == 4
    catalog = slots.subscription_slots()
    script = [
        "SUBSCRIPTION_SLOT_IDS=(" + " ".join(shlex.quote(row.slot_id) for row in catalog) + ")",
        "secondary_refuse() { return 65; }",
        "subscription_slot_field() {",
        '  case "$1:$2" in',
    ]
    for row in catalog:
        for field in ("worker_user", "worker_group", "provider_home"):
            key = shlex.quote(row.slot_id + ":" + field)
            value = shlex.quote(str(getattr(row, field)))
            script.append(f'    {key}) printf "%s\\n" {value} ;;')
    script.extend([
        "    *) return 65 ;;",
        "  esac",
        "}",
        'mock_install() { printf "%s\\0" "$@"; }',
    ])
    script.extend(block.replace("/usr/bin/install", "mock_install") for block in blocks)
    result = run("\n".join(script))
    assert result.returncode == 0, result.stderr
    arguments = result.stdout.split("\0")
    assert arguments.pop() == ""
    calls = [arguments[index:index + 8] for index in range(0, len(arguments), 8)]
    expected = []
    for row in catalog:
        for path in (row.provider_home.parent, row.provider_home, row.provider_home.parent / "state"):
            expected.append(["-d", "-o", row.worker_user, "-g", row.worker_group, "-m", "0700", str(path)])
    for row in catalog:
        expected.append([
            "-d", "-o", row.worker_user, "-g", row.worker_group, "-m", "0700",
            f"/var/log/mastermind-executive/workers/{row.slot_id}",
        ])
    assert calls == expected
