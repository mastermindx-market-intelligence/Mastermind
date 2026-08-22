"""integrations.chairman_surfaces — Chairman Control Room P0 Wave B tests.

Falsifiers for the provider navigation adapters: given a validated
``mastermind.surface_bindings.v1`` binding, an adapter may only focus/open/
launch — never send a message, never inject a keystroke, never persist a
locator value into an outcome. Every test here runs against an injected
fake runner; the real ``osascript``/``open``/``claude``/``cursor-agent``/
``codex`` binaries are never invoked.

Hermetic: the real filesystem outside ``tmp_path`` is never read (except for
the safe existence checks the package itself does against ``/Applications``
and managed-browser profile-store paths in a couple of capability/chatgpt
tests, which only ever return booleans and never open a file).

``test_sol_corr_*`` prove the Sol architecture correction (MAS-113,
2026-08-22): ChatGPT seats live in persistent GoLogin/Multilogin
managed-browser environments, never a Chrome profile, and
``chatgpt.open_surface`` refuses closed on every path — the installed
vendors document no surface that can address an already-running profile.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import (
    capability,
    chatgpt,
    claude,
    codex,
    contract,
    cursor,
)
from integrations.chairman_surfaces import runner as runner_module

PACKAGE_DIR = Path(runner_module.__file__).resolve().parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "chairman_surfaces"


# ---------------------------------------------------------------------------
# fake runner
# ---------------------------------------------------------------------------


class FakeRunner:
    """Records every call; returns canned responses in order, then a default."""

    def __init__(self, responses=None, default=None):
        self.calls: list[tuple[list[str], float]] = []
        self._responses = list(responses or [])
        self._default = default or {"code": 0, "stdout": "", "stderr": "", "timed_out": False}

    def __call__(self, argv, *, timeout: float = 20.0):
        self.calls.append((list(argv), timeout))
        if self._responses:
            return self._responses.pop(0)
        return dict(self._default)


def never_called_runner():
    def _boom(argv, *, timeout=20.0):  # pragma: no cover - only reached on regression
        raise AssertionError(f"runner must not be invoked; got argv={argv!r}")
    return _boom


# ---------------------------------------------------------------------------
# binding builders
# ---------------------------------------------------------------------------


#: A syntactically valid GoLogin profile id (24 lowercase hex chars).
GOLOGIN_PROFILE_ID = "aaaaaaaaaaaaaaaaaaaaaaaa"
MLX_FOLDER_ID = "11111111-1111-4111-8111-111111111111"
MLX_PROFILE_ID = "22222222-2222-4222-8222-222222222222"


def _gologin_binding(*, url="https://chatgpt.com/c/session-alpha", profile_id=GOLOGIN_PROFILE_ID, **overrides):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={"env_manager": "gologin", "profile_id": profile_id, "url": url},
        observed_at="2026-08-22T00:00:00Z",
        seat_ref="chatgpt-seat-1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )
    binding.update(overrides)
    return binding


def _multilogin_binding(
    *, url="https://chatgpt.com/c/session-alpha", folder_id=MLX_FOLDER_ID, profile_id=MLX_PROFILE_ID, **overrides,
):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={"env_manager": "multilogin", "folder_id": folder_id, "profile_id": profile_id, "url": url},
        observed_at="2026-08-22T00:00:00Z",
        seat_ref="chatgpt-seat-1",
        binding_id="77777777-7777-4777-8777-777777777777",
    )
    binding.update(overrides)
    return binding


#: Back-compat alias: most cross-cutting tests below (unrelated to the
#: chatgpt adapter's own internals) only need SOME valid chatgpt binding.
_chatgpt_binding = _gologin_binding


def _claude_code_binding(*, project_dir, session_id="22222222-2222-4222-8222-222222222222", **overrides):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="claude_code",
        locator_kind="claude_code_session",
        locator={"project_dir": project_dir, "session_id": session_id},
        observed_at="2026-08-22T00:00:00Z",
        binding_id="33333333-3333-4333-8333-333333333333",
    )
    binding.update(overrides)
    return binding


def _claude_desktop_binding(*, url="https://claude.ai/chat/session-beta", **overrides):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="claude_desktop",
        locator_kind="claude_desktop_url",
        locator={"url": url},
        observed_at="2026-08-22T00:00:00Z",
        binding_id="44444444-4444-4444-8444-444444444444",
    )
    binding.update(overrides)
    return binding


def _cursor_binding(*, chat_id="cursor-chat-gamma", workspace_dir=None, **overrides):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="cursor_agent",
        locator_kind="cursor_agent_thread",
        locator={"chat_id": chat_id, "workspace_dir": workspace_dir},
        observed_at="2026-08-22T00:00:00Z",
        binding_id="55555555-5555-4555-8555-555555555555",
    )
    binding.update(overrides)
    return binding


def _codex_binding(*, session_id="codex-session-delta", cwd=None, **overrides):
    binding = sb.new_binding(
        work_ref="WS:CCR",
        role="chairman",
        provider="codex",
        locator_kind="codex_session",
        locator={"session_id": session_id, "cwd": cwd},
        observed_at="2026-08-22T00:00:00Z",
        binding_id="66666666-6666-4666-8666-666666666666",
    )
    binding.update(overrides)
    return binding


_FIXTURE_PROFILES = {"Default": "Personal", "Profile 2": "Work Ops"}


# ---------------------------------------------------------------------------
# native-existence-gate fixture helpers (claude_code / codex session stores)
# ---------------------------------------------------------------------------


def _write_claude_transcript(claude_projects_dir: Path, project_dir: str, session_id: str) -> None:
    """Create a fixture Claude Code transcript so the existence gate passes."""
    slug = claude._slugify_project_dir(project_dir)
    project_slug_dir = claude_projects_dir / slug
    project_slug_dir.mkdir(parents=True, exist_ok=True)
    (project_slug_dir / f"{session_id}.jsonl").write_text("", encoding="utf-8")


def _write_codex_transcript(codex_sessions_dir: Path, session_id: str) -> None:
    """Create a fixture Codex transcript so the existence gate passes."""
    codex_sessions_dir.mkdir(parents=True, exist_ok=True)
    (codex_sessions_dir / f"{session_id}.jsonl").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# falsifier 1: unsafe token in a chat_id/session_id refuses, runner untouched
# ---------------------------------------------------------------------------

BAD_TOKENS = [
    "has space",
    "semi;colon",
    "cmd$(sub)",
    "backtick`x`",
    "line\nbreak",
    "../escape",
]


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_falsifier_cursor_chat_id_unsafe_token_refused(bad):
    fake = FakeRunner()
    binding = _cursor_binding(chat_id=bad)
    outcome = cursor.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "unsafe_token"
    assert fake.calls == []


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_falsifier_codex_session_id_unsafe_token_refused(bad):
    fake = FakeRunner()
    binding = _codex_binding(session_id=bad)
    outcome = codex.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "unsafe_token"
    assert fake.calls == []


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_falsifier_claude_code_session_id_unsafe_token_refused(bad, tmp_path):
    fake = FakeRunner()
    binding = _claude_code_binding(project_dir=str(tmp_path), session_id=bad)
    outcome = claude.open_claude_code(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "unsafe_token"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# falsifier 2: chatgpt binding URL host not in the allowlist -> invalid_binding
# ---------------------------------------------------------------------------


def test_falsifier_chatgpt_bad_host_refused_at_open_binding():
    fake = FakeRunner()
    binding = _chatgpt_binding(url="https://evil.example.com/c/session-alpha")
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "invalid_binding"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# falsifier 3: chatgpt managed-environment identity absence -> not_found
# ---------------------------------------------------------------------------


def test_falsifier_chatgpt_environment_absent_from_store_not_found(tmp_path):
    fake = FakeRunner()
    binding = _gologin_binding()
    outcome = chatgpt.open_surface(
        binding, fake, mlx_profiles_root=str(tmp_path / "mlx"), gologin_profiles_root=str(tmp_path / "gologin"),
    )
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == []


def test_falsifier_chatgpt_malformed_gologin_profile_id_unsafe_token():
    fake = FakeRunner()
    binding = _gologin_binding(profile_id="not-hex-not-24")
    outcome = chatgpt.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "unsafe_token"
    assert fake.calls == []


def test_falsifier_chatgpt_gologin_with_folder_id_invalid_binding():
    fake = FakeRunner()
    binding = _gologin_binding()
    binding["locator"] = dict(binding["locator"])
    binding["locator"]["folder_id"] = MLX_FOLDER_ID
    outcome = chatgpt.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "invalid_binding"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# falsifier 4: unknown provider / locator_kind -> refused
# ---------------------------------------------------------------------------


def test_falsifier_unknown_provider_refused():
    fake = FakeRunner()
    binding = _chatgpt_binding()
    binding["provider"] = "smoke_signal"
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "refused"
    assert fake.calls == []


def test_falsifier_locator_kind_mismatch_refused():
    fake = FakeRunner()
    binding = _chatgpt_binding()
    binding["locator_kind"] = "codex_session"
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "refused"
    assert fake.calls == []


def test_falsifier_non_dict_binding_refused():
    fake = FakeRunner()
    outcome = contract.open_binding("not-a-binding", fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "invalid_binding"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# falsifier 5: a lifecycle key smuggled into the binding -> invalid_binding
#              (proves re-validation happens again at open time)
# ---------------------------------------------------------------------------


def test_falsifier_lifecycle_key_refused_at_open_time():
    fake = FakeRunner()
    binding = _chatgpt_binding()
    binding["status"] = "done"  # forbidden semantic key, not part of the closed schema
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "invalid_binding"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# falsifier 6: AppleScript constants never interpolate a locator value
# (Terminal-launch adapters only — chatgpt uses no AppleScript at all, see
# test_sol_corr_r4_no_chrome_machinery below)
# ---------------------------------------------------------------------------


def test_falsifier_terminal_launch_argv_identical_across_bindings():
    argv_a = contract.terminal_launch_argv("claude --resume aaaa")
    argv_b = contract.terminal_launch_argv("codex resume bbbb")
    assert argv_a[:-1] == argv_b[:-1]
    assert argv_a[-1] != argv_b[-1]
    for line in argv_a[:-1]:
        assert "aaaa" not in line
    for line in argv_b[:-1]:
        assert "bbbb" not in line


# ---------------------------------------------------------------------------
# falsifier 7: subprocess isolated to runner.py; run_argv rejects bad argv
# ---------------------------------------------------------------------------


def test_falsifier_run_argv_rejects_non_list():
    with pytest.raises(ValueError):
        runner_module.run_argv("osascript -e foo")


def test_falsifier_run_argv_rejects_nul_byte():
    with pytest.raises(ValueError):
        runner_module.run_argv(["osascript", "bad\x00arg"])


def test_falsifier_run_argv_rejects_newline():
    with pytest.raises(ValueError):
        runner_module.run_argv(["osascript", "bad\narg"])


def test_falsifier_run_argv_rejects_non_str_element():
    with pytest.raises(ValueError):
        runner_module.run_argv(["osascript", 5])


# ---------------------------------------------------------------------------
# falsifier 7b: the runner's 64 KiB cap must be overridable on purpose —
# a silent truncation of the ps snapshot hid every running managed browser
# (running seat read as stopped, measured live 2026-08-22)
# ---------------------------------------------------------------------------


def test_run_argv_default_cap_still_64k():
    big = str(200_000)
    result = runner_module.run_argv(
        [sys.executable, "-c", f"print('x' * {big})"]
    )
    assert result["code"] == 0
    assert len(result["stdout"].encode()) <= 64 * 1024


def test_run_argv_max_bytes_override_preserves_large_output():
    result = runner_module.run_argv(
        [sys.executable, "-c", "print('x' * 200_000)"],
        max_bytes=4 * 1024 * 1024,
    )
    assert result["code"] == 0
    assert len(result["stdout"]) >= 200_000


def test_default_ps_reader_requests_large_cap(monkeypatch):
    seen = {}

    def fake_run_argv(argv, *, timeout=20.0, max_bytes=None):
        seen["argv"] = argv
        seen["max_bytes"] = max_bytes
        return {"code": 0, "stdout": "line-one\nline-two\n", "stderr": "", "timed_out": False}

    monkeypatch.setattr(runner_module, "run_argv", fake_run_argv)
    lines = chatgpt._default_process_args_reader()
    assert lines == ["line-one", "line-two"]
    assert seen["argv"] == ["/bin/ps", "-axo", "args="]
    assert seen["max_bytes"] is not None and seen["max_bytes"] >= 1024 * 1024


def test_falsifier_subprocess_isolated_to_runner():
    py_files = sorted(PACKAGE_DIR.glob("*.py"))
    assert py_files, "expected package sources to scan"
    offenders = []
    for path in py_files:
        if path.name == "runner.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "subprocess":
                        offenders.append(path.name)
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "subprocess":
                    offenders.append(path.name)
    assert offenders == [], f"only runner.py may import subprocess; found imports in: {offenders}"


# ---------------------------------------------------------------------------
# falsifier 8: zero-message law — no keystroke/GUI-scripting vocabulary
# ---------------------------------------------------------------------------


_BANNED_PHRASES = ("keystroke", "key code", "type text", "System Events")


def test_falsifier_zero_message_law_no_gui_scripting_vocabulary():
    py_files = sorted(PACKAGE_DIR.glob("*.py"))
    offenders = []
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for phrase in _BANNED_PHRASES:
            if phrase.lower() in lowered:
                offenders.append((path.name, phrase))
    assert offenders == [], f"zero-message law violated: {offenders}"


# ---------------------------------------------------------------------------
# Sol architecture correction (MAS-113, 2026-08-22): open_surface REFUSES
# CLOSED on every path — no chrome/AppleScript, no vendor binary execution,
# no fallback navigation mechanism. These replace the superseded Chrome-
# profile "blocker 1" regressions above (review 5000169412).
# ---------------------------------------------------------------------------

#: The two exact, static ``detail`` strings open_surface may report once an
#: environment's existence is proven — copied verbatim from
#: ``chatgpt.open_surface`` so a drift between the source and this test is
#: caught by a plain string mismatch rather than silently passing.
_MSG_RUNNING = (
    "the bound environment is running, but the installed managed-browser surface "
    "documents no way to open a URL in, focus, or attach to a running profile; "
    "seat navigation is held rather than using an unofficial mechanism"
)
_MSG_NOT_RUNNING = (
    "the bound environment is not running; starting it requires cloud authentication "
    "and an undocumented restart path that could disrupt the persistent seat; "
    "navigation is held"
)


def test_sol_corr_r1_runner_never_invoked(tmp_path):
    """Zero runner calls across all four outcome paths: invalid, missing
    environment, running environment, stopped environment."""
    fake = FakeRunner()

    invalid = _gologin_binding()
    invalid["locator"] = dict(invalid["locator"])
    invalid["locator"]["env_manager"] = "chrome"
    outcome_invalid = chatgpt.open_surface(invalid, fake)
    assert outcome_invalid["ok"] is False
    assert outcome_invalid["failure_kind"] == "invalid_binding"

    missing = _gologin_binding()
    outcome_missing = chatgpt.open_surface(
        missing, fake,
        gologin_profiles_root=str(tmp_path / "empty_gologin"),
        mlx_profiles_root=str(tmp_path / "empty_mlx"),
    )
    assert outcome_missing["ok"] is False
    assert outcome_missing["failure_kind"] == "not_found"

    gologin_root = tmp_path / "gologin_profiles"
    (gologin_root / GOLOGIN_PROFILE_ID).mkdir(parents=True)

    def running_reader():
        return [f"/Applications/GoLogin.app/orbita --user-data-dir=/x/{GOLOGIN_PROFILE_ID} --proxy-server=1.2.3.4:9"]

    outcome_running = chatgpt.open_surface(
        _gologin_binding(), fake, gologin_profiles_root=str(gologin_root), process_args_reader=running_reader,
    )
    assert outcome_running["ok"] is False
    assert outcome_running["failure_kind"] == "unsupported_surface"
    assert outcome_running["detail"] == _MSG_RUNNING

    outcome_stopped = chatgpt.open_surface(
        _gologin_binding(), fake, gologin_profiles_root=str(gologin_root), process_args_reader=lambda: [],
    )
    assert outcome_stopped["ok"] is False
    assert outcome_stopped["failure_kind"] == "unsupported_surface"
    assert outcome_stopped["detail"] == _MSG_NOT_RUNNING

    assert fake.calls == []


def test_sol_corr_r2_no_cross_env_fallback(tmp_path):
    """Env B present+running must never leak into env A's outcome — A's
    detail is one of the two static strings, never dynamic content about B."""
    fake = FakeRunner()
    profile_a = "aaaaaaaaaaaaaaaaaaaaaaaa"
    profile_b = "bbbbbbbbbbbbbbbbbbbbbbbb"
    root = tmp_path / "gologin_profiles"
    (root / profile_a).mkdir(parents=True)
    (root / profile_b).mkdir(parents=True)

    def reader():
        return [f"/Applications/GoLogin.app/orbita --user-data-dir=/x/{profile_b} --proxy-server=9.9.9.9:1"]

    binding_a = _gologin_binding(profile_id=profile_a)
    outcome = chatgpt.open_surface(binding_a, fake, gologin_profiles_root=str(root), process_args_reader=reader)

    assert outcome["ok"] is False
    assert outcome["detail"] in (_MSG_RUNNING, _MSG_NOT_RUNNING)
    assert outcome["detail"] == _MSG_NOT_RUNNING  # A itself is not the running process — B's aliveness never leaks in
    assert profile_b not in outcome["detail"]
    assert fake.calls == []


def test_sol_corr_r3_never_verified(tmp_path):
    fake = FakeRunner()

    invalid = _gologin_binding()
    invalid["locator"] = dict(invalid["locator"])
    invalid["locator"]["env_manager"] = "chrome"
    outcomes = [chatgpt.open_surface(invalid, fake)]

    outcomes.append(chatgpt.open_surface(
        _gologin_binding(), fake,
        gologin_profiles_root=str(tmp_path / "empty_gologin"), mlx_profiles_root=str(tmp_path / "empty_mlx"),
    ))

    gologin_root = tmp_path / "gologin_profiles"
    (gologin_root / GOLOGIN_PROFILE_ID).mkdir(parents=True)
    running_reader = lambda: [f"--user-data-dir=/x/{GOLOGIN_PROFILE_ID}"]  # noqa: E731
    outcomes.append(chatgpt.open_surface(
        _gologin_binding(), fake, gologin_profiles_root=str(gologin_root), process_args_reader=running_reader,
    ))
    outcomes.append(chatgpt.open_surface(
        _gologin_binding(), fake, gologin_profiles_root=str(gologin_root), process_args_reader=lambda: [],
    ))

    for outcome in outcomes:
        assert outcome["ok"] is False
        assert outcome["verified"] is False


def test_sol_corr_r4_no_chrome_machinery():
    source = inspect.getsource(chatgpt)
    for banned in ("Google Chrome", "osascript", "open -na", "AppleScript"):
        assert banned not in source, f"chatgpt.py must never mention {banned!r}"


def test_argv_privacy(tmp_path):
    marker = "SECRETMARKER"
    root = tmp_path / "gologin_profiles"
    (root / GOLOGIN_PROFILE_ID).mkdir(parents=True)

    def reader():
        return [f"/Applications/GoLogin.app/orbita --user-data-dir=/x/{GOLOGIN_PROFILE_ID} --proxy-password={marker}"]

    fake = FakeRunner()
    binding = _gologin_binding()
    outcome = chatgpt.open_surface(binding, fake, gologin_profiles_root=str(root), process_args_reader=reader)
    for value in outcome.values():
        assert marker not in str(value)

    running = chatgpt.env_running(binding["locator"], process_args_reader=reader)
    assert running is True  # documented shape: exactly a bool, never the raw line

    envs = chatgpt.list_local_environments(
        gologin_profiles_root=str(root), mlx_profiles_root=str(tmp_path / "no_mlx"), process_args_reader=reader,
    )
    assert set(envs.keys()) == {"multilogin", "gologin"}
    for entry in envs["gologin"]:
        assert set(entry.keys()) == {"profile_id", "running"}
        assert marker not in entry["profile_id"]
    for entry in envs["multilogin"]:
        assert set(entry.keys()) == {"workspace_id", "folder_id", "profile_id", "running"}

    def _raising_reader():
        raise RuntimeError(f"boom {marker}")

    assert chatgpt.env_running(binding["locator"], process_args_reader=_raising_reader) is False


# ---------------------------------------------------------------------------
# env_exists — bounded, tolerant existence gates (both managers)
# ---------------------------------------------------------------------------


def test_env_exists_multilogin_true_with_non_uuid_sibling_skipped(tmp_path):
    root = tmp_path / "mlx"
    workspace_id = "99999999-9999-4999-8999-999999999999"
    (root / workspace_id / MLX_FOLDER_ID / MLX_PROFILE_ID).mkdir(parents=True)
    (root / "branding").mkdir(parents=True)  # non-UUID sibling — must be skipped, not raise
    locator = {"env_manager": "multilogin", "folder_id": MLX_FOLDER_ID, "profile_id": MLX_PROFILE_ID, "url": "https://chatgpt.com/c/x"}
    assert chatgpt.env_exists(locator, mlx_profiles_root=str(root)) is True


def test_env_exists_multilogin_missing_is_false(tmp_path):
    root = tmp_path / "mlx"
    root.mkdir()
    locator = {"env_manager": "multilogin", "folder_id": MLX_FOLDER_ID, "profile_id": MLX_PROFILE_ID, "url": "https://chatgpt.com/c/x"}
    assert chatgpt.env_exists(locator, mlx_profiles_root=str(root)) is False


def test_env_exists_gologin_true_and_missing(tmp_path):
    root = tmp_path / "gologin"
    (root / GOLOGIN_PROFILE_ID).mkdir(parents=True)
    locator = {"env_manager": "gologin", "profile_id": GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"}
    assert chatgpt.env_exists(locator, gologin_profiles_root=str(root)) is True
    other = {"env_manager": "gologin", "profile_id": "b" * 24, "url": "https://chatgpt.com/c/x"}
    assert chatgpt.env_exists(other, gologin_profiles_root=str(root)) is False


def test_env_exists_unreadable_root_returns_false(tmp_path):
    missing_root = tmp_path / "does_not_exist_at_all" / "nested"
    locator = {"env_manager": "gologin", "profile_id": GOLOGIN_PROFILE_ID, "url": "https://chatgpt.com/c/x"}
    assert chatgpt.env_exists(locator, gologin_profiles_root=str(missing_root)) is False


# ---------------------------------------------------------------------------
# list_local_environments — shape, sorting, 200-cap, running from injected
# reader
# ---------------------------------------------------------------------------


def test_list_local_environments_shape_sorting_and_running(tmp_path):
    mlx_root = tmp_path / "mlx"
    gologin_root = tmp_path / "gologin"
    workspace_id = "99999999-9999-4999-8999-999999999999"
    folder_a, folder_b = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    profile_a, profile_b = "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"
    (mlx_root / workspace_id / folder_b / profile_b).mkdir(parents=True)
    (mlx_root / workspace_id / folder_a / profile_a).mkdir(parents=True)
    (mlx_root / "branding").mkdir(parents=True)

    gologin_a, gologin_b = "aaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbb"
    (gologin_root / gologin_b).mkdir(parents=True)
    (gologin_root / gologin_a).mkdir(parents=True)

    def reader():
        return [f"/x --user-data-dir=/y/{folder_a}/{profile_a}"]

    envs = chatgpt.list_local_environments(
        mlx_profiles_root=str(mlx_root), gologin_profiles_root=str(gologin_root), process_args_reader=reader,
    )

    assert [e["folder_id"] for e in envs["multilogin"]] == [folder_a, folder_b]
    assert envs["multilogin"][0]["running"] is True
    assert envs["multilogin"][1]["running"] is False
    assert [e["profile_id"] for e in envs["gologin"]] == [gologin_a, gologin_b]
    assert all(e["running"] is False for e in envs["gologin"])


def test_list_local_environments_200_cap(tmp_path):
    gologin_root = tmp_path / "gologin"
    gologin_root.mkdir()
    for i in range(201):
        (gologin_root / f"{i:024x}").mkdir()
    envs = chatgpt.list_local_environments(
        gologin_profiles_root=str(gologin_root), mlx_profiles_root=str(tmp_path / "no_mlx"),
        process_args_reader=lambda: [],
    )
    assert len(envs["gologin"]) == 200


# ---------------------------------------------------------------------------
# falsifier 11: outcome privacy — no locator literal ever appears in detail
# ---------------------------------------------------------------------------


_SECRET_URL = "https://chatgpt.com/c/super-secret-session-token-9f8e"
_SECRET_CLAUDE_URL = "https://claude.ai/chat/super-secret-claude-token-7a6b"
_SECRET_SESSION_UUID = "77777777-7777-4777-8777-777777777777"
_SECRET_CHAT_ID = "cursor-super-secret-chat"
_SECRET_CODEX_ID = "codex-super-secret-session"


def _assert_no_leak(outcome, *secrets):
    detail = outcome.get("detail", "")
    for secret in secrets:
        assert secret not in detail, f"outcome leaked a locator value: {secret!r} in {detail!r}"


def test_falsifier_privacy_chatgpt_refusals(tmp_path):
    # chatgpt.open_surface refuses on every path (Sol architecture correction,
    # MAS-113, 2026-08-22) — every refusal kind must still carry no locator
    # value, including the not_found path exercised via an empty tmp store.
    fake_missing = FakeRunner()
    missing_binding = _gologin_binding(url=_SECRET_URL)
    missing_outcome = chatgpt.open_surface(
        missing_binding, fake_missing,
        gologin_profiles_root=str(tmp_path / "empty_gologin"), mlx_profiles_root=str(tmp_path / "empty_mlx"),
    )
    _assert_no_leak(missing_outcome, _SECRET_URL)

    fake_bad_host = FakeRunner()
    bad_binding = _gologin_binding(url="https://evil.example.com/c/" + _SECRET_URL)
    bad_outcome = contract.open_binding(bad_binding, fake_bad_host)
    _assert_no_leak(bad_outcome, _SECRET_URL)


def test_falsifier_privacy_claude_code(tmp_path):
    fake = FakeRunner()
    project_dir = str(tmp_path)
    claude_projects_dir = tmp_path / "claude_store"
    _write_claude_transcript(claude_projects_dir, project_dir, _SECRET_SESSION_UUID)
    binding = _claude_code_binding(project_dir=project_dir, session_id=_SECRET_SESSION_UUID)
    outcome = claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))
    assert outcome["ok"] is True
    _assert_no_leak(outcome, _SECRET_SESSION_UUID, str(tmp_path))


def test_falsifier_privacy_claude_desktop():
    fake = FakeRunner()
    binding = _claude_desktop_binding(url=_SECRET_CLAUDE_URL)
    outcome = claude.open_claude_desktop(binding, fake)
    assert outcome["ok"] is True
    _assert_no_leak(outcome, _SECRET_CLAUDE_URL)


def test_falsifier_privacy_cursor(tmp_path):
    fake = FakeRunner()
    binding = _cursor_binding(chat_id=_SECRET_CHAT_ID, workspace_dir=str(tmp_path))
    outcome = cursor.open_surface(binding, fake)
    assert outcome["ok"] is True
    _assert_no_leak(outcome, _SECRET_CHAT_ID, str(tmp_path))


def test_falsifier_privacy_codex(tmp_path):
    fake = FakeRunner()
    codex_sessions_dir = tmp_path / "codex_store"
    _write_codex_transcript(codex_sessions_dir, _SECRET_CODEX_ID)
    workdir = tmp_path / "work"
    workdir.mkdir()
    binding = _codex_binding(session_id=_SECRET_CODEX_ID, cwd=str(workdir))
    outcome = codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))
    assert outcome["ok"] is True
    _assert_no_leak(outcome, _SECRET_CODEX_ID, str(workdir))


def test_falsifier_privacy_refusals_carry_no_locator(tmp_path):
    fake = FakeRunner()
    binding = _cursor_binding(chat_id="bad token " + _SECRET_CHAT_ID)
    outcome = cursor.open_surface(binding, fake)
    assert outcome["ok"] is False
    _assert_no_leak(outcome, _SECRET_CHAT_ID)


# ---------------------------------------------------------------------------
# falsifier 12: capability census — absent everything, never invokes runner
# ---------------------------------------------------------------------------


def test_falsifier_capability_census_all_absent():
    fake = FakeRunner()
    result = capability.census(fake, which=lambda _name: None, app_exists=lambda _path: False)

    assert set(result.keys()) == {"chatgpt", "claude_code", "claude_desktop", "cursor_agent", "codex", "aionui"}
    for provider, info in result.items():
        if provider == "aionui":
            assert info["state"] == contract.UNSUPPORTED
            assert info["installed"] is False
        else:
            assert info["state"] == contract.NOT_INSTALLED, f"{provider} expected NOT_INSTALLED, got {info}"
            assert info["installed"] is False
        assert info["version"] is None
    assert fake.calls == []


def test_falsifier_capability_census_never_raises_without_runner():
    result = capability.census(None, which=lambda _name: None, app_exists=lambda _path: False)
    assert all(info["version"] is None for info in result.values())


def test_falsifier_capability_census_installed_binary_is_partial_never_proven():
    fake = FakeRunner(responses=[{"code": 0, "stdout": "1.2.3\n", "stderr": "", "timed_out": False}])
    result = capability.census(fake, which=lambda name: f"/usr/local/bin/{name}", app_exists=lambda _path: True)
    for provider in ("claude_code", "cursor_agent", "codex"):
        assert result[provider]["state"] == contract.PARTIAL
        assert result[provider]["state"] != contract.PROVEN
        assert result[provider]["installed"] is True
    # chatgpt/claude_desktop are app-bundle based, never PROVEN from census either
    assert result["chatgpt"]["state"] in (contract.PARTIAL, contract.NOT_INSTALLED)
    assert result["chatgpt"]["state"] != contract.PROVEN
    assert result["claude_desktop"]["state"] == contract.PARTIAL
    assert result["claude_desktop"]["state"] != contract.PROVEN
    assert result["aionui"]["state"] == contract.UNSUPPORTED


def test_falsifier_capability_census_version_capture_failure_is_none_not_exception():
    def _raising_runner(argv, *, timeout=20.0):
        raise RuntimeError("boom")

    result = capability.census(_raising_runner, which=lambda name: f"/usr/local/bin/{name}", app_exists=lambda _path: True)
    assert result["claude_code"]["version"] is None
    assert result["claude_code"]["state"] == contract.PARTIAL


# ---------------------------------------------------------------------------
# Terminal shell-string construction: exact composed command + quoting
# ---------------------------------------------------------------------------


def test_claude_code_command_composition_exact_string(tmp_path):
    fake = FakeRunner()
    session_id = "88888888-8888-4888-8888-888888888888"
    project_dir = str(tmp_path)
    claude_projects_dir = tmp_path / "claude_store"
    _write_claude_transcript(claude_projects_dir, project_dir, session_id)
    binding = _claude_code_binding(project_dir=project_dir, session_id=session_id)
    claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))

    assert len(fake.calls) == 1
    argv, _ = fake.calls[0]
    command = argv[-1]
    expected = f"cd {project_dir} && claude --resume {session_id}"
    assert command == expected


def test_claude_code_command_composition_quotes_space_in_path(tmp_path):
    spaced_dir = tmp_path / "My Project"
    spaced_dir.mkdir()
    fake = FakeRunner()
    session_id = "99999999-9999-4999-9999-999999999999"
    claude_projects_dir = tmp_path / "claude_store"
    _write_claude_transcript(claude_projects_dir, str(spaced_dir), session_id)
    binding = _claude_code_binding(project_dir=str(spaced_dir), session_id=session_id)
    claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))

    argv, _ = fake.calls[0]
    command = argv[-1]
    import shlex as _shlex
    expected = "cd " + _shlex.quote(str(spaced_dir)) + " && claude --resume " + session_id
    assert command == expected
    assert "'" in command  # the space forced shlex to quote the path


def test_cursor_command_composition_exact_string_no_workspace():
    fake = FakeRunner()
    binding = _cursor_binding(chat_id="chat-123", workspace_dir=None)
    cursor.open_surface(binding, fake)
    argv, _ = fake.calls[0]
    assert argv[-1] == "cursor-agent --resume chat-123"


def test_cursor_command_composition_with_workspace_quotes_space(tmp_path):
    spaced_dir = tmp_path / "Cursor Workspace"
    spaced_dir.mkdir()
    fake = FakeRunner()
    binding = _cursor_binding(chat_id="chat-123", workspace_dir=str(spaced_dir))
    cursor.open_surface(binding, fake)
    argv, _ = fake.calls[0]
    import shlex as _shlex
    expected = "cd " + _shlex.quote(str(spaced_dir)) + " && cursor-agent --resume chat-123"
    assert argv[-1] == expected
    assert "'" in argv[-1]


def test_codex_command_composition_exact_string_no_cwd(tmp_path):
    fake = FakeRunner()
    codex_sessions_dir = tmp_path / "codex_store"
    _write_codex_transcript(codex_sessions_dir, "session-xyz")
    binding = _codex_binding(session_id="session-xyz", cwd=None)
    codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))
    argv, _ = fake.calls[0]
    assert argv[-1] == "codex resume session-xyz"


def test_codex_command_composition_with_cwd_quotes_space(tmp_path):
    spaced_dir = tmp_path / "Codex Dir"
    spaced_dir.mkdir()
    fake = FakeRunner()
    codex_sessions_dir = tmp_path / "codex_store"
    _write_codex_transcript(codex_sessions_dir, "session-xyz")
    binding = _codex_binding(session_id="session-xyz", cwd=str(spaced_dir))
    codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))
    argv, _ = fake.calls[0]
    import shlex as _shlex
    expected = "cd " + _shlex.quote(str(spaced_dir)) + " && codex resume session-xyz"
    assert argv[-1] == expected
    assert "'" in argv[-1]


# ---------------------------------------------------------------------------
# missing-directory -> not_found (project_dir / workspace_dir / cwd)
# ---------------------------------------------------------------------------


def test_claude_code_missing_project_dir_not_found():
    fake = FakeRunner()
    binding = _claude_code_binding(project_dir="/nonexistent/definitely/not/here")
    outcome = claude.open_claude_code(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == []


def test_cursor_missing_workspace_dir_not_found():
    fake = FakeRunner()
    binding = _cursor_binding(chat_id="chat-1", workspace_dir="/nonexistent/definitely/not/here")
    outcome = cursor.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == []


def test_codex_missing_cwd_not_found():
    fake = FakeRunner()
    binding = _codex_binding(session_id="session-1", cwd="/nonexistent/definitely/not/here")
    outcome = codex.open_surface(binding, fake)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Sol regressions C.R1-R3 (blocker 2): claude_code/codex must prove the
# bound session actually exists in the local session store BEFORE ever
# launching Terminal. A syntactically valid but nonexistent session id must
# refuse not_found with the runner never invoked, even when the runner is
# primed to ACK the Terminal launch ("osascript success + provider resume
# failure" read as an existence-gate case — the launch that would produce
# that ACK must never be attempted in the first place). Only a session
# PRESENT in the local store, with a launch ACK, may report verified=True.
# ---------------------------------------------------------------------------


def test_sol_c_r1_claude_code_nonexistent_session_refused_not_found_no_launch(tmp_path):
    fake = FakeRunner()
    project_dir = str(tmp_path)
    session_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    claude_projects_dir = tmp_path / "claude_store"
    claude_projects_dir.mkdir()  # store exists, but no transcript for this session
    binding = _claude_code_binding(project_dir=project_dir, session_id=session_id)
    outcome = claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))

    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert outcome["verified"] is False
    assert fake.calls == []


def test_sol_c_r1_codex_nonexistent_session_refused_not_found_no_launch(tmp_path):
    fake = FakeRunner()
    session_id = "definitely-not-a-real-session"
    codex_sessions_dir = tmp_path / "codex_store"
    codex_sessions_dir.mkdir()  # store exists, but no transcript for this session
    binding = _codex_binding(session_id=session_id, cwd=None)
    outcome = codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))

    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert outcome["verified"] is False
    assert fake.calls == []


def test_sol_c_r2_claude_code_terminal_would_ack_but_session_absent_never_launches(tmp_path):
    # Prime the fake runner to ACK the Terminal launch -- the existence gate
    # must still refuse BEFORE that ACK is ever produced.
    fake = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    project_dir = str(tmp_path)
    session_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    claude_projects_dir = tmp_path / "claude_store"
    claude_projects_dir.mkdir()
    binding = _claude_code_binding(project_dir=project_dir, session_id=session_id)
    outcome = claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))

    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == [], "a Terminal-ACK-primed runner must never be invoked when the session is absent"


def test_sol_c_r2_codex_terminal_would_ack_but_session_absent_never_launches(tmp_path):
    fake = FakeRunner(responses=[{"code": 0, "stdout": "", "stderr": "", "timed_out": False}])
    codex_sessions_dir = tmp_path / "codex_store"
    codex_sessions_dir.mkdir()
    binding = _codex_binding(session_id="absent-session", cwd=None)
    outcome = codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))

    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert fake.calls == [], "a Terminal-ACK-primed runner must never be invoked when the session is absent"


def test_sol_c_r3_claude_code_session_present_and_launch_acked_is_verified(tmp_path):
    fake = FakeRunner()
    project_dir = str(tmp_path)
    session_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    claude_projects_dir = tmp_path / "claude_store"
    _write_claude_transcript(claude_projects_dir, project_dir, session_id)
    binding = _claude_code_binding(project_dir=project_dir, session_id=session_id)
    outcome = claude.open_claude_code(binding, fake, claude_projects_dir=str(claude_projects_dir))

    assert outcome["ok"] is True
    assert outcome["verified"] is True
    assert len(fake.calls) == 1


def test_sol_c_r3_codex_session_present_and_launch_acked_is_verified(tmp_path):
    fake = FakeRunner()
    codex_sessions_dir = tmp_path / "codex_store"
    _write_codex_transcript(codex_sessions_dir, "present-session")
    binding = _codex_binding(session_id="present-session", cwd=None)
    outcome = codex.open_surface(binding, fake, codex_sessions_dir=str(codex_sessions_dir))

    assert outcome["ok"] is True
    assert outcome["verified"] is True
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# slug-rule receipt: the empirically pinned Claude Code project-dir slug
# mapping (see claude._slugify_project_dir's docstring for the source
# listing) against the exact real-path/slug pairs observed
# ---------------------------------------------------------------------------


def test_claude_code_slug_rule_matches_observed_real_store_entries():
    cases = [
        (
            "/Users/chriswong/Documents/Cluade/macro-main",
            "-Users-chriswong-Documents-Cluade-macro-main",
        ),
        (
            "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/13f-census-cadence-af87e7",
            "-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-13f-census-cadence-af87e7",
        ),
        (
            "/Users/chriswong/.openclaw-crestodian-workspace",
            "-Users-chriswong--openclaw-crestodian-workspace",
        ),
    ]
    for real_path, expected_slug in cases:
        assert claude._slugify_project_dir(real_path) == expected_slug


# ---------------------------------------------------------------------------
# cursor_agent / codex existence-unprovable / verified=False law
# ---------------------------------------------------------------------------


def test_cursor_launch_success_is_never_verified():
    fake = FakeRunner()
    binding = _cursor_binding(chat_id="chat-123", workspace_dir=None)
    outcome = cursor.open_surface(binding, fake)
    assert outcome["ok"] is True
    assert outcome["verified"] is False


# ---------------------------------------------------------------------------
# claude_desktop happy path
# ---------------------------------------------------------------------------


def test_claude_desktop_open_success():
    fake = FakeRunner()
    binding = _claude_desktop_binding(url="claude://open/session-xyz")
    outcome = claude.open_claude_desktop(binding, fake)
    assert outcome["ok"] is True
    assert outcome["action"] == "opened"
    assert outcome["verified"] is False
    argv, _ = fake.calls[0]
    assert argv == ["/usr/bin/open", "claude://open/session-xyz"]


# ---------------------------------------------------------------------------
# end-to-end open_binding happy paths (dispatch works for every provider)
# ---------------------------------------------------------------------------


def test_open_binding_dispatches_claude_desktop():
    fake = FakeRunner()
    binding = _claude_desktop_binding()
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is True
    assert outcome["provider"] == "claude_desktop"


def test_open_binding_dispatches_claude_code(tmp_path):
    fake = FakeRunner()
    project_dir = str(tmp_path)
    session_id = "22222222-2222-4222-8222-222222222222"
    claude_projects_dir = tmp_path / "claude_store"
    _write_claude_transcript(claude_projects_dir, project_dir, session_id)
    binding = _claude_code_binding(project_dir=project_dir, session_id=session_id)
    outcome = contract.open_binding(binding, fake, claude_projects_dir=str(claude_projects_dir))
    assert outcome["ok"] is True
    assert outcome["provider"] == "claude_code"
    assert outcome["verified"] is True


def test_open_binding_dispatches_cursor_agent():
    fake = FakeRunner()
    binding = _cursor_binding()
    outcome = contract.open_binding(binding, fake)
    assert outcome["ok"] is True
    assert outcome["provider"] == "cursor_agent"
    assert outcome["verified"] is False


def test_open_binding_dispatches_codex(tmp_path):
    fake = FakeRunner()
    codex_sessions_dir = tmp_path / "codex_store"
    _write_codex_transcript(codex_sessions_dir, "codex-session-delta")
    binding = _codex_binding()
    outcome = contract.open_binding(binding, fake, codex_sessions_dir=str(codex_sessions_dir))
    assert outcome["ok"] is True
    assert outcome["provider"] == "codex"
    assert outcome["verified"] is True


def test_open_binding_dispatches_chatgpt(tmp_path):
    # contract.open_binding's chatgpt path forwards mlx_profiles_root/
    # gologin_profiles_root/process_args_reader through to chatgpt.open_surface
    # — an empty tmp store keeps this hermetic instead of depending on
    # developer-machine managed-browser state.
    fake = FakeRunner()
    binding = _gologin_binding()
    outcome = contract.open_binding(
        binding, fake,
        mlx_profiles_root=str(tmp_path / "empty_mlx"), gologin_profiles_root=str(tmp_path / "empty_gologin"),
        process_args_reader=lambda: [],
    )
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "not_found"
    assert outcome["verified"] is False
    assert outcome["provider"] == "chatgpt"
    assert fake.calls == []
