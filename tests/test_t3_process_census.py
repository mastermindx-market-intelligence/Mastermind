"""T3 process census tests — table-driven over argv shapes OBSERVED LIVE on
m2studio (2026-11-09, recorded in integrations/mmos/LANE_FLEET_DIRECTOR_G.md)
plus adversarial negatives.  No test shells out to the real ``ps``."""
import pytest

from control_plane.t3_process_census import (
    CENSUS_SCHEMA,
    KIND_CODEX_CLI,
    KIND_DSH_DIRECT,
    KIND_OTHER,
    KIND_T3_HARNESS,
    CensusProcess,
    T3ProcessCensusError,
    census_from_dict,
    classify,
    redact_argv,
    redact_token,
    take_census,
)

WORKTREE = "/Users/chriswong/.t3/worktrees/Mastermind/t3-3e1025bb"

# The claude-provider T3 harness, exactly as observed (pid 11790 that day);
# the glm-5.3 one (pid 27913) differs only in --model.
CLAUDE_HARNESS_ARGV = (
    "claude --output-format stream-json --verbose --input-format stream-json "
    "--thinking adaptive --thinking-display summarized --effort xhigh "
    "--model glm-5.3 --permission-prompt-tool stdio "
    "--allowedTools mcp__t3-code__* --tools default "
    "--permission-mode bypassPermissions "
    "--allow-dangerously-skip-permissions --include-partial-messages "
    f"--add-dir {WORKTREE} --add-dir /Users/chriswong/.t3/userdata/attachments "
    "--session-id=19478ad9-7ec0-4642-b7ce-f98d5d605059 "
    '--settings {"showThinkingSummaries":true}'
).split()

# The /bin/sh -c wrapper around the same harness (pid 27914), observed with
# its trap/read-fd preamble and an inline `exec ... t3-claude claude ...`.
SH_WRAPPER_ARGV = (
    "/bin/sh -c { trap '' TERM; read -r _ <&3; kill -TERM 0; sleep 5; "
    "kill -KILL 0; } </dev/null >/dev/null 2>&1 & "
    'exec "$@" 3<&- t3-claude claude --output-format stream-json '
    "--allowedTools mcp__t3-code__* "
    f"--add-dir {WORKTREE} --session-id=19478ad9-7ec0-4642-b7ce-f98d5d605059"
).split()

DSH_ATTENDED_LAUNCHER = (
    "/opt/homebrew/Cellar/node/26.5.0/bin/node "
    "/Users/chriswong/Library/Application Support/Mastermind/DeepSeek/releases/"
    "dsh-687f282e-company-d5d1232-20261107-c2/launch_attended.mjs"
).split()

DSH_ATTENDED_WEB = (
    "/opt/homebrew/Cellar/node/26.5.0/bin/node "
    "/Users/chriswong/Library/Application Support/Mastermind/DeepSeek/releases/"
    "dsh-687f282e-company-d5d1232-20261107-c2/app/apps/cli/lib/bin.js web "
    "--patch /Users/chriswong/Library/Application Support/Mastermind/DeepSeek/"
    "releases/dsh-687f282e-company-d5d1232-20261107-c2/company.patch.yml "
    "--host 127.0.0.1 --port 4180 --no-open"
).split()

CODEX_APP_SERVER_NODE = "node /opt/homebrew/bin/codex app-server".split()
CODEX_APP_SERVER_VENDOR = (
    "/opt/homebrew/lib/node_modules/@openai/codex/node_modules/"
    "@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex app-server"
).split()

T3_DESKTOP_APP = (
    "/Applications/T3 Code (Beta).app/Contents/MacOS/T3 Code (Beta)"
).split()
T3_TOOL_SERVER = (
    "/Applications/T3 Code (Beta).app/Contents/MacOS/T3 Code (Beta) "
    "/Users/chriswong/.t3/tools/expo-device-hub/0.19.1/node_modules/"
    "expo-device-hub/dist/server/cli.mjs --port 53010 --host 127.0.0.1"
).split()


CLASSIFY_TABLE = [
    # (name, argv, kind, provider, model)
    ("claude harness glm", CLAUDE_HARNESS_ARGV, KIND_T3_HARNESS, "claude", "glm-5.3"),
    ("sh wrapper", SH_WRAPPER_ARGV, KIND_T3_HARNESS, "claude", None),
    ("dsh acp shipped profile", "dsh --profile acp".split(), KIND_T3_HARNESS, "dsh", None),
    ("dsh acp mmx profile", "dsh --profile mmx-acp".split(), KIND_T3_HARNESS, "dsh", None),
    ("dsh attended launcher", DSH_ATTENDED_LAUNCHER, KIND_DSH_DIRECT, "dsh", None),
    ("dsh attended web", DSH_ATTENDED_WEB, KIND_DSH_DIRECT, "dsh", None),
    ("bare dsh", "dsh".split(), KIND_DSH_DIRECT, "dsh", None),
    ("dsh exec prompt", "dsh exec do work".split(), KIND_DSH_DIRECT, "dsh", None),
    ("codex node app-server", CODEX_APP_SERVER_NODE, KIND_CODEX_CLI, "codex", None),
    ("codex vendor binary", CODEX_APP_SERVER_VENDOR, KIND_CODEX_CLI, "codex", None),
    ("codex cli cwd", f"codex --model gpt-5.2 --cwd {WORKTREE}".split(),
     KIND_CODEX_CLI, "codex", "gpt-5.2"),
    ("t3 desktop app", T3_DESKTOP_APP, KIND_OTHER, None, None),
    ("t3 tool server", T3_TOOL_SERVER, KIND_OTHER, None, None),
    ("plain claude cli", f"claude --add-dir {WORKTREE}".split(), KIND_OTHER, "claude", None),
    ("python script", "python3 scripts/check.py --all".split(), KIND_OTHER, None, None),
    ("empty argv", [], KIND_OTHER, None, None),
    # adversarial negatives: each harness marker ALONE is not a harness
    ("worktree ref without t3 tools", f"claude --add-dir {WORKTREE}".split(),
     KIND_OTHER, "claude", None),
    ("t3 tools without agent exec",
     "node server.js --allowTools mcp__t3-code__*".split(), KIND_OTHER, None, None),
    ("worktree ref on non-agent", f"tail -f {WORKTREE}/log.txt".split(),
     KIND_OTHER, None, None),
]


@pytest.mark.parametrize(
    "name,argv,kind,provider,model", CLASSIFY_TABLE, ids=[row[0] for row in CLASSIFY_TABLE]
)
def test_classify_table(name, argv, kind, provider, model):
    result = classify(argv)
    assert result.kind == kind, (name, result)
    assert result.provider == provider, (name, result)
    assert result.model == model, (name, result)
    assert result.kind in {"t3_harness", "dsh_direct", "codex_cli", "other"}
    assert set(result.labels) <= {
        "t3_worktree_ref", "t3_tool_ref", "t3_claude_ref", "acp_profile_rows",
        "dsh_release_ref", "attended_web_ref", "model_flag",
    }


def test_harness_workspace_refs_extracted():
    result = classify(CLAUDE_HARNESS_ARGV)
    assert result.workspace_refs == (WORKTREE,)


def test_classify_is_stable_under_redaction():
    """The stored census is redacted; classification must not change."""
    for _, argv, _, _, _ in CLASSIFY_TABLE:
        assert classify(argv) == classify(redact_argv(argv))


# ── redaction ────────────────────────────────────────────────────────────────


def test_token_like_substrings_redacted():
    assert redact_token("a" * 64) == "[REDACTED]"
    assert redact_token("mcp:launch:" + "b" * 64) == "mcp:launch:[REDACTED]"
    assert (
        redact_token("--session-id=19478ad9-7ec0-4642-b7ce-f98d5d605059")
        == "--session-id=[REDACTED]"
    )


def test_path_shaped_tokens_keep_their_segments():
    # Long path segments are directory names, not secrets: token-likes inside a
    # slash-bearing token survive (only credential-shaped content is scrubbed).
    token = (
        "/Users/chriswong/.t3/worktrees/Mastermind/"
        "t3-3e1025bb-with-a-very-long-segment-name-over-32-chars"
    )
    assert redact_token(token) == token


def test_credential_shaped_tokens_scrubbed_everywhere():
    assert "sk-" not in redact_token("env sk-abcdefghijklmnop1234")
    assert redact_token("flag=/Users/x/-Users-chriswong-Documents-Cluade-Mastermind/y") == (
        "flag=/Users/x/-Users-chriswong-Documents-Cluade-Mastermind/y"
    )


def test_oversized_token_redacted_whole():
    assert redact_token("x" * 3000) == "[REDACTED]"


def test_redact_token_refuses_non_string():
    with pytest.raises(T3ProcessCensusError) as exc:
        redact_token(42)
    assert exc.value.code == "ARGV_TOKEN_INVALID"


# ── ps parsing (injected stdout only) ───────────────────────────────────────


PS_STDOUT = (
    "  PID  PPID LSTART  COMMAND\n"  # ps emits no header with =; adversarial junk row
    f"11790 27914 Sun Nov  9 00:03:29 2026 {' '.join(CLAUDE_HARNESS_ARGV)}\n"
    f"27914     1 Sun Nov  9 00:03:29 2026 {' '.join(SH_WRAPPER_ARGV)}\n"
    f"11638     1 Sun Nov  8 22:00:01 2026 {' '.join(DSH_ATTENDED_LAUNCHER)}\n"
    "garbage line without columns\n"
)


def test_take_census_parses_pid_ppid_and_redacts():
    snapshot = take_census(run_ps=lambda: PS_STDOUT)
    assert snapshot.schema == CENSUS_SCHEMA
    assert len(snapshot.processes) == 3
    by_pid = {process.pid: process for process in snapshot.processes}
    harness = by_pid[11790]
    assert harness.ppid == 27914
    assert harness.argv == redact_argv(CLAUDE_HARNESS_ARGV)
    assert not any(
        "19478ad9" in token for token in harness.argv
    ), "session id must not survive into the stored census"
    assert by_pid[11638].argv == redact_argv(DSH_ATTENDED_LAUNCHER)


def test_take_census_ps_failure_is_empty_not_fabricated():
    snapshot = take_census(run_ps=lambda: "")
    assert snapshot.processes == ()
    assert snapshot.observed_at_utc


def test_take_census_injected_stdout_must_be_string():
    with pytest.raises(T3ProcessCensusError) as exc:
        take_census(run_ps=lambda: None)
    assert exc.value.code == "PS_STDOUT_INVALID"


# ── snapshot round-trip (closed, fail-closed) ───────────────────────────────


def _sample_snapshot_dict():
    snapshot = take_census(
        run_ps=lambda: PS_STDOUT,
        clock=lambda: __import__("datetime").datetime(
            2026, 11, 9, 8, 0, 0, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    return snapshot.to_dict()


def test_census_round_trip():
    document = _sample_snapshot_dict()
    rebuilt = census_from_dict(document)
    assert rebuilt.to_dict() == document


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda d: d.update(schema="other/v9"), "CENSUS_SCHEMA_INVALID"),
        (lambda d: d.update(observed_at_utc=""), "CENSUS_OBSERVED_AT_INVALID"),
        (lambda d: d.update(observed_at_utc="not-a-time"), "CENSUS_OBSERVED_AT_INVALID"),
        (lambda d: d.update(processes={}), "CENSUS_PROCESSES_INVALID"),
        (lambda d: d["processes"][0].update(pid=0), "CENSUS_PROCESS_FIELDS_INVALID"),
        (lambda d: d["processes"][0].update(extra=1), "CENSUS_PROCESS_FIELDS_INVALID"),
        (lambda d: d["processes"][0].update(argv=["ok", 3]), "CENSUS_PROCESS_FIELDS_INVALID"),
        (lambda d: d["processes"][0].update(started_epoch_s=-1), "CENSUS_PROCESS_FIELDS_INVALID"),
        (lambda d: d.pop("source"), "CENSUS_FIELDS_INVALID"),
    ],
)
def test_census_from_dict_fail_closed(mutate, code):
    document = _sample_snapshot_dict()
    mutate(document)
    with pytest.raises(T3ProcessCensusError) as exc:
        census_from_dict(document)
    assert exc.value.code == code


def test_census_from_dict_rebuild_with_real_row_type():
    document = _sample_snapshot_dict()
    rebuilt = census_from_dict(document)
    assert all(isinstance(p, CensusProcess) for p in rebuilt.processes)
