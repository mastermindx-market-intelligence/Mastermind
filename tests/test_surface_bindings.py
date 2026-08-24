"""control_plane.surface_bindings — Chairman Control Room P0 Wave A tests.

``mastermind.surface_bindings.v1`` is a small, local, private navigation cache:
"where is this seat's browser/session tab for this work item".  These tests
prove the properties that keep it from quietly becoming a second lifecycle
plane:

  1. ``test_falsifier_forbidden_lifecycle_key_*`` — a lifecycle/authority/
     credential key anywhere in the document is refused BY NAME.
  2. ``test_falsifier_unknown_key_*`` — an unknown key anywhere (document,
     binding, or locator level) is refused.
  3. ``test_falsifier_chatgpt_url_*`` — a disallowed host, non-https scheme,
     or embedded credential in a ``chatgpt_managed_env`` locator's ``url`` is
     refused; ``test_chatgpt_managed_env_*`` — GoLogin/Multilogin environment
     identity shape (Sol architecture correction, MAS-113, 2026-08-22).
  4. ``test_falsifier_save_bindings_*`` — writes are ``0600`` inside a
     ``0700`` parent, atomic (via a same-directory temp file plus
     ``os.replace``), and byte-deterministic.
  5. ``test_falsifier_missing_file_is_not_an_error`` — a missing bindings
     file is ``(None, [])``, not a problem.
  6. ``test_falsifier_duplicate_binding_conflict`` — two bindings sharing
     ``(work_ref, role)`` produce a visible conflict with no winner.

Hermetic: everything reads/writes only inside ``tmp_path``; no real
``~/Library/Application Support`` path is touched.
"""
from __future__ import annotations

import json
import os
import stat
import uuid

import pytest

from control_plane import surface_bindings as sb

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


#: A syntactically valid GoLogin profile id (24 lowercase hex chars) reused
#: across the schema tests below.
_GOLOGIN_PROFILE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"


def _valid_binding(**overrides) -> dict:
    binding = sb.new_binding(
        work_ref="WS:FOO",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin",
            "profile_id": _GOLOGIN_PROFILE_ID,
            "url": "https://chatgpt.com/c/abc123",
        },
        observed_at="2026-08-21T00:00:00Z",
        seat_ref="chatgpt1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )
    binding.update(overrides)
    return binding


def _doc(*bindings: dict) -> dict:
    return {"schema": sb.SCHEMA, "bindings": list(bindings)}


# ---------------------------------------------------------------------------
# schema pin
# ---------------------------------------------------------------------------


def test_schema_pin():
    assert sb.SCHEMA == "mastermind.surface_bindings.v1"


def test_valid_document_has_no_problems():
    assert sb.validate_bindings_document(_doc(_valid_binding())) == []


# ---------------------------------------------------------------------------
# falsifier 1 — forbidden lifecycle/authority/credential semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["status", "STATE", "next_action", "priority", "token", "credential"]
)
def test_falsifier_forbidden_lifecycle_key_at_binding_level(key):
    binding = _valid_binding()
    binding[key] = "whatever"
    doc = _doc(binding)

    problems = sb.validate_bindings_document(doc)
    assert any(key.lower() in p.lower() and "forbidden" in p.lower() for p in problems), problems

    with pytest.raises(sb.SurfaceBindingViolation) as excinfo:
        sb.save_bindings(doc, path="/tmp/should-not-be-reached.json")
    assert key.lower() in str(excinfo.value).lower()


def test_falsifier_forbidden_lifecycle_key_inside_locator():
    binding = _valid_binding()
    binding["locator"] = dict(binding["locator"])
    binding["locator"]["status"] = "active"
    doc = _doc(binding)

    problems = sb.validate_bindings_document(doc)
    assert any("status" in p and "forbidden" in p.lower() for p in problems), problems
    with pytest.raises(sb.SurfaceBindingViolation):
        sb.save_bindings(doc, path="/tmp/should-not-be-reached-2.json")


def test_falsifier_forbidden_key_does_not_raise_from_validate():
    """validate_bindings_document itself NEVER raises — it only returns problems."""
    binding = _valid_binding()
    binding["credential"] = "sk-should-never-be-here"
    doc = _doc(binding)
    # Must not raise.
    problems = sb.validate_bindings_document(doc)
    assert problems  # but the problem is still reported


# ---------------------------------------------------------------------------
# falsifier 2 — unknown key anywhere
# ---------------------------------------------------------------------------


def test_falsifier_unknown_key_at_document_level():
    doc = {"schema": sb.SCHEMA, "bindings": [], "extra_field": 1}
    problems = sb.validate_bindings_document(doc)
    assert any("extra_field" in p for p in problems), problems


def test_falsifier_unknown_key_at_binding_level():
    binding = _valid_binding()
    binding["mystery_field"] = "x"
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("mystery_field" in p for p in problems), problems


def test_falsifier_unknown_key_at_locator_level():
    binding = _valid_binding()
    binding["locator"] = dict(binding["locator"])
    binding["locator"]["extra_locator_field"] = "x"
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("extra_locator_field" in p for p in problems), problems


# ---------------------------------------------------------------------------
# falsifier 3 — chatgpt URL law
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://chatgpt.com/c/abc",  # not https
        "https://evil.example.com/c/abc",  # wrong host
        "https://user:pass@chatgpt.com/c/abc",  # embedded credentials
        "https://chatgpt.com:8443/c/abc",  # embedded port
        "https://chatgpt.com/",  # home, not one conversation
        "https://chatgpt.com/g/g-p-project/project",  # Project overview, not one conversation
        "https://chatgpt.com/c/abc?temporary=1",  # unstable query-bearing variant
        "",  # empty
    ],
)
def test_falsifier_chatgpt_url_refused(url):
    binding = _valid_binding()
    binding["locator"] = {"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": url}
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.url" in p for p in problems), problems


def test_chatgpt_url_chat_openai_com_host_allowed():
    binding = _valid_binding()
    binding["locator"] = {
        "env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chat.openai.com/c/abc",
    }
    assert sb.validate_bindings_document(_doc(binding)) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://chatgpt.com/c/conversation-alpha",
        "https://chatgpt.com/g/g-p-project-alpha/c/conversation-beta",
        "https://chat.openai.com/g/g-p-project_123/c/conversation-gamma/",
    ],
)
def test_chatgpt_exact_normal_and_project_conversation_urls_allowed(url):
    binding = _valid_binding()
    binding["locator"] = {
        "env_manager": "gologin",
        "profile_id": _GOLOGIN_PROFILE_ID,
        "url": url,
    }
    assert sb.validate_bindings_document(_doc(binding)) == []


# ---------------------------------------------------------------------------
# falsifier 3b — chatgpt_managed_env law (Sol architecture correction,
# MAS-113, 2026-08-22): GoLogin/Multilogin environment identity, never a
# Chrome profile.
# ---------------------------------------------------------------------------


def test_chatgpt_managed_env_multilogin_valid():
    binding = _valid_binding(
        locator={
            "env_manager": "multilogin",
            "folder_id": "11111111-1111-4111-8111-111111111111",
            "profile_id": "22222222-2222-4222-8222-222222222222",
            "url": "https://chatgpt.com/c/abc123",
        },
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_chatgpt_managed_env_gologin_valid():
    binding = _valid_binding(
        locator={"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/abc123"},
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_chatgpt_managed_env_gologin_with_folder_id_rejected_with_exact_text():
    binding = _valid_binding(
        locator={
            "env_manager": "gologin",
            "folder_id": "11111111-1111-4111-8111-111111111111",
            "profile_id": _GOLOGIN_PROFILE_ID,
            "url": "https://chatgpt.com/c/abc123",
        },
    )
    problems = sb.validate_bindings_document(_doc(binding))
    expected = (
        "gologin environments are addressed by profile_id only; folder_id is not part of the durable address"
    )
    assert any(expected in p for p in problems), problems


def test_chatgpt_managed_env_multilogin_missing_folder_id_rejected():
    binding = _valid_binding(
        locator={
            "env_manager": "multilogin",
            "profile_id": "22222222-2222-4222-8222-222222222222",
            "url": "https://chatgpt.com/c/abc123",
        },
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.folder_id" in p for p in problems), problems


@pytest.mark.parametrize(
    "bad_profile_id",
    [
        "AAAAAAAAAAAAAAAAAAAAAAAA",  # uppercase — the store is lowercase only
        "not-hex-not-24-chars",
        "short",
    ],
)
def test_chatgpt_managed_env_gologin_malformed_profile_id_rejected(bad_profile_id):
    binding = _valid_binding(
        locator={"env_manager": "gologin", "profile_id": bad_profile_id, "url": "https://chatgpt.com/c/abc123"},
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.profile_id" in p for p in problems), problems


def test_chatgpt_managed_env_multilogin_non_uuid_ids_rejected():
    binding = _valid_binding(
        locator={
            "env_manager": "multilogin",
            "folder_id": "not-a-uuid",
            "profile_id": "also-not-a-uuid",
            "url": "https://chatgpt.com/c/abc123",
        },
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.folder_id" in p for p in problems), problems
    assert any(".locator.profile_id" in p for p in problems), problems


def test_chatgpt_managed_env_unknown_env_manager_rejected():
    binding = _valid_binding(
        locator={"env_manager": "chrome", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/abc123"},
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.env_manager" in p for p in problems), problems


def test_chatgpt_old_url_locator_kind_rejected():
    """The pre-correction ``chatgpt_url`` locator_kind no longer exists."""
    binding = _valid_binding(locator_kind="chatgpt_url")
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("locator_kind" in p for p in problems), problems


def test_chatgpt_old_browser_profile_form_rejected():
    """The pre-correction ``browser_profile`` locator key is unknown now."""
    binding = _valid_binding(
        locator={"browser_profile": "Default", "url": "https://chatgpt.com/c/abc123"},
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("browser_profile" in p for p in problems), problems
    assert any(".locator.env_manager" in p for p in problems), problems


# ---------------------------------------------------------------------------
# falsifier 1b — proxy/IP/fingerprint/cookie/credential/token belt (Sol
# architecture correction, MAS-113, 2026-08-22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["proxy", "proxy_password", "fingerprint", "cookies", "ip", "access_token", "user_agent", "api_key"],
)
def test_falsifier_managed_env_belt_forbidden_key_in_locator(key):
    binding = _valid_binding()
    binding["locator"] = dict(binding["locator"])
    binding["locator"][key] = "should-never-be-here"
    doc = _doc(binding)

    problems = sb.validate_bindings_document(doc)
    assert any(key.lower() in p.lower() and "forbidden" in p.lower() for p in problems), problems
    with pytest.raises(sb.SurfaceBindingViolation) as excinfo:
        sb.save_bindings(doc, path="/tmp/should-not-be-reached-belt.json")
    assert key.lower() in str(excinfo.value).lower()


def test_claude_desktop_url_scheme_allowed():
    binding = _valid_binding(
        provider="claude_desktop",
        locator_kind="claude_desktop_url",
        locator={"url": "claude://conversation/abc123"},
        seat_ref=None,
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_claude_desktop_url_wrong_host_refused():
    binding = _valid_binding(
        provider="claude_desktop",
        locator_kind="claude_desktop_url",
        locator={"url": "https://evil.example.com/c/abc"},
        seat_ref=None,
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any(".locator.url" in p for p in problems), problems


# ---------------------------------------------------------------------------
# falsifier 4 — save_bindings atomic / private / deterministic
# ---------------------------------------------------------------------------


def test_falsifier_save_bindings_permissions_and_atomicity(tmp_path):
    target = tmp_path / "nested" / "surface_bindings.json"
    doc = _doc(_valid_binding())

    replaced = []
    real_replace = os.replace

    def _spy_replace(src, dst):
        replaced.append((src, dst))
        # The source must be a temp file already living in the SAME directory
        # as the destination (same-directory temp file, not /tmp) and must
        # still exist right up until the atomic replace.
        assert os.path.dirname(src) == os.path.dirname(os.fspath(dst))
        assert os.path.exists(src)
        return real_replace(src, dst)

    import control_plane.surface_bindings as mod
    orig = mod.os.replace
    mod.os.replace = _spy_replace
    try:
        sb.save_bindings(doc, path=target)
    finally:
        mod.os.replace = orig

    assert len(replaced) == 1
    assert target.is_file()
    file_mode = stat.S_IMODE(target.stat().st_mode)
    assert file_mode == 0o600, oct(file_mode)
    dir_mode = stat.S_IMODE(target.parent.stat().st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    # No leftover temp file.
    leftovers = [p for p in target.parent.iterdir() if p != target]
    assert leftovers == [], leftovers


def test_falsifier_save_bindings_deterministic_bytes(tmp_path):
    doc = _doc(_valid_binding())
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    sb.save_bindings(doc, path=path_a)
    sb.save_bindings(json.loads(json.dumps(doc)), path=path_b)  # fresh equal copy
    assert path_a.read_bytes() == path_b.read_bytes()
    assert path_a.read_text().endswith("\n")


def test_save_bindings_refuses_invalid_document_and_writes_nothing(tmp_path):
    target = tmp_path / "surface_bindings.json"
    binding = _valid_binding()
    binding["status"] = "active"
    with pytest.raises(sb.SurfaceBindingViolation):
        sb.save_bindings(_doc(binding), path=target)
    assert not target.exists()


# ---------------------------------------------------------------------------
# falsifier 5 — missing file is not an error
# ---------------------------------------------------------------------------


def test_falsifier_missing_file_is_not_an_error(tmp_path):
    missing = tmp_path / "does" / "not" / "exist.json"
    doc, problems = sb.load_bindings(path=missing)
    assert doc is None
    assert problems == []


def test_load_bindings_round_trip(tmp_path):
    target = tmp_path / "surface_bindings.json"
    original = _doc(_valid_binding())
    sb.save_bindings(original, path=target)
    doc, problems = sb.load_bindings(path=target)
    assert problems == []
    assert doc == original


def test_load_bindings_non_regular_file_refused(tmp_path):
    target = tmp_path / "a_directory.json"
    target.mkdir()
    doc, problems = sb.load_bindings(path=target)
    assert doc is None
    assert problems and "regular file" in problems[0]


def test_load_bindings_oversize_refused(tmp_path):
    target = tmp_path / "huge.json"
    target.write_bytes(b" " * (sb._MAX_BYTES + 1))
    doc, problems = sb.load_bindings(path=target)
    assert doc is None
    assert problems and "byte limit" in problems[0]


def test_load_bindings_invalid_json_refused(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text("{not json", encoding="utf-8")
    doc, problems = sb.load_bindings(path=target)
    assert doc is None
    assert problems and "invalid JSON" in problems[0]


def test_load_bindings_schema_mismatch_refused(tmp_path):
    target = tmp_path / "wrong_schema.json"
    target.write_text(json.dumps({"schema": "not.the.right.schema", "bindings": []}), encoding="utf-8")
    doc, problems = sb.load_bindings(path=target)
    assert doc is None
    assert problems and any("schema" in p for p in problems)


def test_load_bindings_permission_warning(tmp_path):
    target = tmp_path / "loose.json"
    sb.save_bindings(_doc(_valid_binding()), path=target)
    os.chmod(target, 0o644)
    doc, warnings = sb.load_bindings(path=target)
    assert doc is not None
    assert warnings and any("permission" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# falsifier 6 — duplicate binding conflicts, no winner
# ---------------------------------------------------------------------------


def test_falsifier_duplicate_binding_conflict():
    a = _valid_binding(binding_id="11111111-1111-4111-8111-111111111111")
    b = _valid_binding(binding_id="22222222-2222-4222-8222-222222222222", seat_ref="chatgpt1")
    doc = _doc(a, b)
    conflicts = sb.find_conflicts(doc)
    assert conflicts == [
        {
            "work_ref": "WS:FOO",
            "role": "ceo",
            "binding_ids": [
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
            ],
        }
    ]
    # Both bindings are still present — no automatic winner picked.
    assert len(doc["bindings"]) == 2


def test_distinct_named_chatgpt_seats_can_share_work_and_role_without_conflict():
    rows = [
        _valid_binding(
            binding_id=(
                f"{str(index) * 8}-{str(index) * 4}-4{str(index) * 3}-"
                f"8{str(index) * 3}-{str(index) * 12}"
            ),
            seat_ref=f"chatgpt{index}",
        )
        for index in (1, 2, 3)
    ]
    assert sb.find_conflicts(_doc(*rows)) == []


def test_mixed_provider_claim_for_same_work_and_role_remains_conflict():
    chatgpt = _valid_binding(binding_id="11111111-1111-4111-8111-111111111111")
    codex = sb.new_binding(
        work_ref="WS:FOO", role="ceo", provider="codex",
        locator_kind="codex_session", locator={"session_id": "session-other"},
        observed_at="2026-08-21T00:00:00Z",
        binding_id="22222222-2222-4222-8222-222222222222",
    )
    assert sb.find_conflicts(_doc(chatgpt, codex)) == [{
        "work_ref": "WS:FOO",
        "role": "ceo",
        "binding_ids": [
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
        ],
    }]


def test_find_conflicts_no_conflict_for_distinct_roles():
    a = _valid_binding(binding_id="11111111-1111-4111-8111-111111111111", role="ceo")
    b = _valid_binding(binding_id="22222222-2222-4222-8222-222222222222", role="coo")
    assert sb.find_conflicts(_doc(a, b)) == []


def test_find_conflicts_deterministic_order():
    doc = _doc(
        _valid_binding(binding_id="99999999-9999-4999-8999-999999999999", work_ref="WS:Z"),
        _valid_binding(binding_id="88888888-8888-4888-8888-888888888888", work_ref="WS:Z"),
        _valid_binding(binding_id="77777777-7777-4777-8777-777777777777", work_ref="WS:A"),
        _valid_binding(binding_id="66666666-6666-4666-8666-666666666666", work_ref="WS:A"),
    )
    conflicts = sb.find_conflicts(doc)
    assert [c["work_ref"] for c in conflicts] == ["WS:A", "WS:Z"]
    assert conflicts[0]["binding_ids"] == sorted(conflicts[0]["binding_ids"])


# ---------------------------------------------------------------------------
# structural / closed-key coverage
# ---------------------------------------------------------------------------


def test_binding_id_must_be_uuid():
    binding = _valid_binding(binding_id="not-a-uuid")
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("binding_id" in p for p in problems), problems


def test_work_ref_pattern_enforced():
    binding = _valid_binding(work_ref="NOTAPREFIX:foo")
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("work_ref" in p for p in problems), problems


@pytest.mark.parametrize("prefix", ["WS", "JOB", "PR"])
def test_work_ref_allows_all_three_prefixes(prefix):
    binding = _valid_binding(work_ref=f"{prefix}:something")
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_role_must_be_in_closed_set():
    binding = _valid_binding(role="president")
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("role" in p for p in problems), problems


def test_seat_ref_required_for_chatgpt():
    binding = _valid_binding(seat_ref=None)
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("seat_ref" in p for p in problems), problems


def test_seat_ref_optional_for_codex():
    binding = _valid_binding(
        provider="codex",
        locator_kind="codex_session",
        locator={"session_id": "sess-1", "cwd": "/abs/path"},
        seat_ref=None,
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_locator_kind_must_match_provider():
    binding = _valid_binding()
    binding["locator_kind"] = "codex_session"
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("locator_kind" in p for p in problems), problems


def test_claude_code_session_requires_absolute_project_dir_and_uuid_session():
    binding = _valid_binding(
        provider="claude_code",
        locator_kind="claude_code_session",
        locator={"project_dir": "relative/path", "session_id": "not-a-uuid"},
        seat_ref=None,
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("project_dir" in p for p in problems), problems
    assert any("session_id" in p for p in problems), problems


def test_claude_code_session_valid():
    binding = _valid_binding(
        provider="claude_code",
        locator_kind="claude_code_session",
        locator={
            "project_dir": "/Users/chris/checkout",
            "session_id": str(uuid.uuid4()),
        },
        seat_ref=None,
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_cursor_agent_chat_id_rejects_whitespace():
    binding = _valid_binding(
        provider="cursor_agent",
        locator_kind="cursor_agent_thread",
        locator={"chat_id": "has space", "workspace_dir": None},
        seat_ref=None,
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("chat_id" in p for p in problems), problems


def test_cursor_agent_workspace_dir_must_be_absolute_or_null():
    binding = _valid_binding(
        provider="cursor_agent",
        locator_kind="cursor_agent_thread",
        locator={"chat_id": "abc123", "workspace_dir": "relative"},
        seat_ref=None,
    )
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("workspace_dir" in p for p in problems), problems


def test_codex_session_valid():
    binding = _valid_binding(
        provider="codex",
        locator_kind="codex_session",
        locator={"session_id": "sess-abc", "cwd": None},
        seat_ref=None,
    )
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_observed_at_must_be_iso_z():
    binding = _valid_binding(observed_at="not-a-timestamp")
    problems = sb.validate_bindings_document(_doc(binding))
    assert any("observed_at" in p for p in problems), problems


def test_last_verified_at_null_is_allowed():
    binding = _valid_binding(last_verified_at=None)
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_document_must_be_an_object():
    assert sb.validate_bindings_document([1, 2, 3]) != []
    assert sb.validate_bindings_document(None) != []


def test_bindings_field_must_be_a_list():
    problems = sb.validate_bindings_document({"schema": sb.SCHEMA, "bindings": "not-a-list"})
    assert any("bindings" in p for p in problems), problems


# ---------------------------------------------------------------------------
# new_binding — no clock reads, caller supplies observed_at
# ---------------------------------------------------------------------------


def test_new_binding_requires_caller_supplied_observed_at():
    with pytest.raises(TypeError):
        sb.new_binding(  # missing observed_at
            work_ref="WS:FOO", role="ceo", provider="chatgpt",
            locator_kind="chatgpt_managed_env",
            locator={"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"},
        )


def test_new_binding_mints_uuid4_binding_id():
    binding = sb.new_binding(
        work_ref="WS:FOO", role="ceo", provider="chatgpt", locator_kind="chatgpt_managed_env",
        locator={"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"},
        observed_at="2026-08-21T00:00:00Z", seat_ref="chatgpt1",
    )
    assert sb._UUID_RE.match(binding["binding_id"])
    assert sb.validate_bindings_document(_doc(binding)) == []


def test_new_binding_is_deterministic_given_explicit_binding_id():
    a = sb.new_binding(
        work_ref="WS:FOO", role="ceo", provider="chatgpt", locator_kind="chatgpt_managed_env",
        locator={"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"},
        observed_at="2026-08-21T00:00:00Z", seat_ref="chatgpt1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )
    b = sb.new_binding(
        work_ref="WS:FOO", role="ceo", provider="chatgpt", locator_kind="chatgpt_managed_env",
        locator={"env_manager": "gologin", "profile_id": _GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"},
        observed_at="2026-08-21T00:00:00Z", seat_ref="chatgpt1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )
    assert a == b


# ---------------------------------------------------------------------------
# DEFAULT_PATH
# ---------------------------------------------------------------------------


def test_default_path_shape():
    assert sb.DEFAULT_PATH.startswith("~/Library/Application Support/Mastermind/")
    assert sb.DEFAULT_PATH.endswith("surface_bindings.json")
    assert "~" not in os.fspath(__import__("pathlib").Path(sb.DEFAULT_PATH).expanduser())
