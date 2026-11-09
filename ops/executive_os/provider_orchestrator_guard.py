#!/usr/bin/env python3
"""User-scope Mastermind provider guard.

This is a deployment artifact for local Codex/Claude CEO/orchestrator sessions.
It creates no lifecycle, queue, merge, retry, watcher, or source-custody authority.
It enforces bounded provider-edge anti-burn invariants inside Mastermind workspaces:
asynchronous CI waits, stable Fabric root accounting, and the standing native-Claude
child routing fence.

WO-11 (MMOS V1, CRITICAL): for sessions the placement owner has armed onto the
shared placement path, every paid launch and native delegation must be covered
by the CURRENT broker-issued ExecutionBinding.v1, validated against the
owner-issued placement receipt, accepted only from a path the fenced session
cannot write (owner service-account channel). Refusal classes: missing binding,
stale fence, provider substitution after reservation, unaccounted descendant.
The gate classifies the SHAPE of the command structurally (a quote-aware shell
scanner — see the ``_shell_scan`` layer): interpreter invocations judged by how
their program is delivered (inline flag text / pipe / heredoc / computed
argument — every flag spelling alike), computed words refused wherever a
wrapper name substituted for them would complete a paid launch (shadow
substitution — no runner allowlist), command substitution anywhere, launches
inside runtime-multiplying or deferred shapes (loop bodies, function bodies,
brace groups, xargs/parallel/find -exec, trap payloads, watch repeaters), and
eval/source/'.' inside the nested -c script that performs the launch. POSIX
line-continuation splits are canonicalised so no constructed path escapes
the gate.
There is no independent signing authority — the binding is only an assignment
of opaque references, trusted exactly as far as it matches the owner's current
lease. The gate fences every lexically observed launch in the commands it is
shown through this provider hook; it does not claim to fence arbitrary processes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import NoReturn


MIN_WATCH_INTERVAL_S = 60
RECOMMENDED_WATCH_INTERVAL_S = 150
POLL_COOLDOWN_S = 300

ROUTE_RE = re.compile(r"(?mi)^\s*ROUTE\s*:\s*(orchestration|audit|review|auditor)\s*$")
WHY_RE = re.compile(r"(?mi)^\s*WHY OPUS\s*:\s*(\S.{19,})$")
READ_ONLY_RE = re.compile(r"(?mi)^\s*(?:MODE|SCOPE)\s*:\s*READ[_ -]?ONLY\s*$")

HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.S | re.M,
)


def strip_heredocs(command: str) -> str:
    previous = None
    output = command
    while previous != output:
        previous = output
        output = HEREDOC_RE.sub("<<HEREDOC", output)
    return output


CMD_POS = r"(?:^|[;&|\n(]|\b(?:do|then|else)\s)\s*"
CI_WATCH_RE = re.compile(
    CMD_POS
    + r"(?P<call>gh\s+(?:run\s+watch\b[^;&|\n]*"
      r"|run\s+view\b[^;&|\n]*--watch\b[^;&|\n]*"
      r"|pr\s+checks\b[^;&|\n]*--watch\b[^;&|\n]*))",
    re.I,
)
CI_READ_RE = re.compile(
    CMD_POS
    + r"gh\s+(?:pr\s+(?:view|checks|status)\b"
      r"|run\s+(?:view|list|watch)\b"
      r"|api\b[^;&|\n]*(?:actions/runs|check-runs))",
    re.I,
)
INTERVAL_RE = re.compile(r"(?i)(?:--interval|(?<!\w)-i)[=\s]+(\d+)")
SLEEP_RE = re.compile(r"(?i)\bsleep\s+(\d+)\b")
DO_DONE_RE = re.compile(r"(?:^|[;&|\n)])\s*do\b(.*?)\bdone\b", re.S | re.I)

# Cooldown only direct CI-status reads. General `gh pr view` / `gh pr status`
# stays available for post-mutation/effect reconciliation; a rate guard must never
# prevent the readback needed to prove a write's outcome.
PR_READ_RE = re.compile(
    CMD_POS + r"gh\s+pr\s+checks\s+(?P<id>\d+)\b",
    re.I,
)
RUN_READ_RE = re.compile(
    CMD_POS + r"gh\s+run\s+(?:view|watch)\s+(?P<id>\d+)\b",
    re.I,
)
API_RUN_READ_RE = re.compile(
    CMD_POS + r"gh\s+api\b[^;&|\n]*/actions/runs/(?P<id>\d+)\b",
    re.I,
)
REPO_ARG_RE = re.compile(
    r"(?:^|\s)(?:-R|--repo)(?:=|\s+)(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    re.I,
)

_SUB_LAUNCH_MODE = (
    r"(?:grok|qwen|minimax|glm|minimax-codex|glm-codex|go-codex|"
    r"go-claude|oc-free|cursor|__glm_vision)"
)
_REMOTE_LAUNCH_MODE = (
    r"(?:glm|glm-codex|minimax|minimax-codex|grok|cursor|qwen|go-codex|"
    r"codex-native|claude-native|oc-free)"
)
_SLOT_POOL = (
    r"(?:grok|minimax|glm|glm-frontier|bailian|cursor|go|ocfree|"
    r"codex-native|claude-native)"
)
FABRIC_LAUNCH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"(?:[A-Za-z0-9_./-]+/)?pool\s+(?:run|remote)\b"
    r"|(?:[A-Za-z0-9_./-]+/)?sub\.sh\s+" + _SUB_LAUNCH_MODE + r"\b"
    r"|(?:[A-Za-z0-9_./-]+/)?remote_sub\.sh\s+\S+\s+"
    + _REMOTE_LAUNCH_MODE
    + r"\b"
    r"|(?:python(?:3(?:\.\d+)?)?\s+)?(?:[A-Za-z0-9_./-]+/)?slot\.py\s+"
    + _SLOT_POOL
    + r"\b"
    r")",
    re.I,
)
_FABRIC_IDENTITY_NAMES = (
    "POOL_ORCHESTRATOR_ID",
    "POOL_PARENT_RUN_ID",
    "POOL_TASK_CLASS",
)

# --- WO-11 shared-placement ExecutionBinding gate (engine independent) --------

#: Scoped arming (OQ-7): the placement owner sets these when the session's
#: work is claimed on the shared path (WO-14 claim -> binding at
#: claim_payload -> projection into the session environment). Sessions not
#: on the shared path keep the legacy identity checks unchanged.
SHARED_PLACEMENT_ENV = "MASTERMIND_SHARED_PLACEMENT"
#: The broker-issued ExecutionBinding.v1 (JSON), projected into the session
#: environment by the authenticated owner at claim. Never self-declared
#: authority: the guard trusts it only while it matches the owner receipt.
BINDING_ENV = "POOL_EXECUTION_BINDING"
#: Owner-written current-lease receipt (JSON file path). This is the
#: authenticated owner channel for the guard: no independent signing
#: authority exists, so the binding is validated for consistency against
#: this owner-issued projection of the CURRENT lease (attempt, fence,
#: child identity, lease state, expiry).
PLACEMENT_RECEIPT_ENV = "MASTERMIND_PLACEMENT_RECEIPT"
PLACEMENT_RECEIPT_SCHEMA = "mastermind.placement_receipt/v1"
EXECUTION_BINDING_SCHEMA = "ExecutionBinding.v1"
#: Fields that make the presented binding BE the owner's current fenced
#: assignment: the (root, immediate parent, logical child) identity triple,
#: the admitted request digest, and the fenced attempt.
_BINDING_IDENTITY_FIELDS = (
    "root_run_ref",
    "immediate_parent_run_ref",
    "logical_child_key",
    "request_digest",
    "attempt_ref",
    "assignment_generation",
)
_BINDING_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
#: Optional owner-projected integrity pin for the receipt file: the SHA-256
#: of the receipt bytes the owner wrote. Defence in depth only — the trust
#: basis is the owner-only receipt channel (see ``_receipt_channel_problem``).
PLACEMENT_RECEIPT_DIGEST_ENV = "MASTERMIND_PLACEMENT_RECEIPT_DIGEST"
#: Owner-projected positive allowlist for the receipt channel: the uids
#: allowed to own the receipt path and every component of it (root/uid 0 is
#: always allowed for components). Without it the channel would be only
#: negatively defined ("anything the principal cannot write"), which admits
#: any third local account as a counterfeit owner channel (REVIEW_2329 r2
#: N-4). Mandatory: an armed session without a projected allowlist gets no
#: launches (fail closed).
PLACEMENT_RECEIPT_OWNER_UIDS_ENV = "MASTERMIND_PLACEMENT_RECEIPT_OWNER_UIDS"
#: The only lease state that admits a launch (exact, case-sensitive).
LEASE_STATE_HELD = "HELD"
#: Exact env tokens that arm the gate (a projected binding also arms it).
SHARED_PLACEMENT_ARM_TOKENS = ("1", "true", "yes", "on")

#: Closed per-wrapper mode vocabularies (the alternations FABRIC_LAUNCH_RE
#: recognizes). Under shared placement a wrapper invoked with any OTHER
#: mode is an unknown paid launch and is refused, never ignored.
_SUB_MODES = frozenset(_SUB_LAUNCH_MODE[3:-1].split("|"))
_REMOTE_MODES = frozenset(_REMOTE_LAUNCH_MODE[3:-1].split("|"))
_SLOT_POOLS = frozenset(_SLOT_POOL[3:-1].split("|"))
#: Wrapper-internal pure helper modes that never acquire a slot or spawn a
#: provider (documented in sub.sh): not paid launches.
NON_LAUNCH_WRAPPER_MODES = frozenset({"__launch_plan", "__glm_memory"})
#: Every wrapper shape: (name, index of the mode/pool argument, closed mode
#: vocabulary or None for the open ``pool`` vocabulary, matched exactly).
_WRAPPER_SHAPES = {
    "pool run": (0, None),
    "pool remote": (1, None),
    "sub.sh": (0, _SUB_MODES),
    "remote_sub.sh": (1, _REMOTE_MODES),
    "slot.py": (0, _SLOT_POOLS),
}
_WRAPPER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?P<wrapper>pool[ \t]+(?:run|remote)|remote_sub\.sh|sub\.sh|slot\.py)"
    r"(?![A-Za-z0-9_.-])",
    re.I,
)
_WRAPPER_ARG_RE = re.compile(r"[ \t]+([^\s;&|<>()`{}]+)")
_SIMPLE_COMMAND_SPLIT_RE = re.compile(r"[;&|\n(){}`]|\$\(")
#: Read-only inspectors: a wrapper NAME given to them as an argument is a
#: file being read, not a launch (``grep -n slot.py docs/runbook.md``).
_INSPECTORS = frozenset({
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "wc", "ls", "stat", "file", "diff", "cmp", "shasum", "sha1sum",
    "sha256sum", "md5", "md5sum", "nl", "od", "xxd",
})
_COMMAND_PREFIX_WORDS = frozenset({
    "do", "then", "else", "elif", "if", "while", "until", "!",
})
#: Constructs that can change the launch environment outside lexical
#: observation: eval/source of computed text, shell startup files, and
#: assignments through a computed variable name.
#: Wrapper source fed to a shell (``cat sub.sh | bash -s grok``) launches
#: without a lexically visible invocation.
_SHELL_FEED_RE = re.compile(
    r"\|\s*(?:\S*/)?(?:ba|z|da|k)?sh\b"
    r"|(?:^|[\s;&|(])(?:\S*/)?(?:ba|z|da|k)?sh\s+(?:-\S+\s+)*<"
)
_UNOBSERVABLE_ENV_RE = re.compile(
    r"(?:^|[;&|(`{\n]|\$\()\s*(?:eval|source|\.)(?=\s)"
    r"|(?:^|[\s;&|(`{])(?:BASH_ENV|ENV)\+?="
    r"|(?:^|[\s;&|(`{])(?:export|declare|typeset|readonly|local)"
    r"(?:\s+-\S+)*\s+[A-Za-z0-9_]*\$"
    r"|(?:^|[\s;&|(`{])printf\s+-v\s*\$"
)
#: Wrapper names as bare words: the computed-launch refusals below fire only
#: when a wrapper token is present in the text (REVIEW_2329 r2 N-3). Computed
#: commands without wrapper tokens are the documented arbitrary-process limit.
_WRAPPER_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?:pool|sub\.sh|remote_sub\.sh|slot\.py)(?![A-Za-z0-9_.-])",
    re.I,
)
#: Loop bodies (for/while/until) execute their contents N times: one lexical
#: launch inside one is N paid children under one binding's single attempt
#: (REVIEW_2329 r2 N-2/C1).
_LOOP_BODY_RE = re.compile(r"\bdo\b.*?\bdone\b", re.S)
#: Batch executors that run their argument command once per input item
#: (REVIEW_2329 r2 N-2/C2-C3, find -exec).
_BATCH_EXECUTOR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?:xargs|parallel|find)\b[^;&|\n]*",
    re.I,
)

# --- structural shell-shape scanner (WO-11 r5; REVIEW_2329 r3 B-1/M-A/M-B) -----
#
# The r3 review's core finding was that the r4 refusals were pattern
# allowlists over an open shell grammar: a one-letter flag change
# (``python3 -Sc``), a long flag (``node --eval``), a stdin-fed program
# (``python3 - <<EOF``, ``echo code | python3``), an unlisted runner
# (``time/sudo/caffeinate/ssh $P run ...``), a function body, a brace-body
# loop or a nested-shell ``eval`` restored the original bypass. This layer
# replaces those lists with a real (small) shell scanner: the raw command is
# tokenised quote-aware into words/operators/heredocs, grouped into simple
# commands, and the SHAPE of each simple command is classified:
#
#   * an interpreter invocation is judged by HOW IT RECEIVES ITS PROGRAM
#     (inline flag text, pipe, heredoc, computed argument) — never by which
#     letters the flags spell — so every flag cluster and spelling variant
#     is refused equally, while the documented script-file form
#     (``python3 .../slot.py glm -- run``) stays observed;
#   * a computed word (``$P``, ``${P}``, ``$(...)``, backticks) is refused
#     wherever substituting a wrapper name for it would make the command a
#     paid launch (shadow substitution) — no runner allowlist to evade;
#   * a wrapper launch inside any shape that can execute it more than once
#     or later (function bodies, brace groups, trap payloads, watch) is a
#     runtime-multiplexed launch;
#   * ``eval``/``source``/``.`` inside the same nested ``-c`` script that
#     performs the launch makes the launch environment unobservable.
#
# The layer is conservative by design (over-refusal is honest, under-refusal
# is a bypass) and is gated on a wrapper NAME appearing anywhere in the
# canonical command, exactly like the r4 computed-launch gate it replaces.

#: Token kinds emitted by :func:`_shell_scan`.
_WORD, _OP, _HEREDOC = "word", "op", "heredoc"
#: Characters that terminate an unquoted word / act as shell operators.
_OP_CHARS = frozenset(";&|()<>\n")
#: Two/three-character operators, longest first for greedy matching.
_MULTI_OPS = (
    ";;&", "&&", "||", ";;", "<<-", "<<<", "<<", ">>", ">&", "<&", ">|",
)
#: Operators that separate one simple command from the next.
_SEPARATOR_OPS = frozenset({";", "&", "|", "&&", "||", ";;", "\n", "(", ")"})
#: Words that may precede the command word without being it (reserved words).
_COMMAND_KEYWORDS = frozenset({
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "in", "select", "time", "coproc", "function",
    "!", "{", "}", "[[", "]]",
})
#: A word whose text contains any of these is computed at runtime.
_COMPUTED_WORD_RE = re.compile(r"[$`]")
#: Runtime-computed segments inside a word (used for shadow substitution).
_COMPUTED_SEGMENT_RE = re.compile(
    r"\$\([^()]*\)|\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|`[^`]*`"
)
#: Interpreter programs: the launched program is text the command carries,
#: not a process the guard can attribute (REVIEW_2329 r3 B-1). Judged by
#: program-delivery shape, never by flag spelling.
_INTERPRETER_HEAD_RE = re.compile(
    r"^(?:python[23]?(?:\.\d+)?|pythonw|perl|ruby|irb|node|nodejs|deno|bun|"
    r"php|osascript|lua|luajit|tclsh|wish|R|Rscript)$"
)
#: Interpreters whose program text is ALWAYS an argument (no script-file
#: form exists): any invocation is an inline-program launch.
_ALWAYS_INLINE_HEAD_RE = re.compile(r"^(?:gawk|mawk|nawk|awk|sed|jq)$")
#: Shell programs whose ``-c`` argument is a nested script body.
_SHELL_HEAD_RE = re.compile(r"^(?:ba|z|da|k|a|l|po)?sh$")
#: Wrapper basenames used for shadow substitution.
_SHADOW_WRAPPER_TOKENS = ("pool", "sub.sh", "remote_sub.sh", "slot.py")
#: Units that only print or return status: a wrapper token inside them is
#: text being shown, never a launch (shadow-substitution scope only).
_PRINT_ONLY_HEADS = frozenset({
    "echo", "printf", "true", "false", ":", *sorted(_INSPECTORS),
})
#: Words of the trap/watch commands that stage or repeat a launch.
_LAUNCH_STAGE_HEADS = frozenset({"trap", "watch"})
_ASSIGNMENT_WORD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")


def _shell_scan(text: str, origin: int = 0, depth: int = 0) -> list[tuple[str, str, int, int]]:
    """Tokenise ``text`` into ``(kind, text, start, end)`` shell tokens.

    Quote-aware (single/double quotes, backslash escapes, POSIX
    line-continuation joins), tracks ``$(...)``/``${...}``/backtick
    segments verbatim inside words (so a word whose expansion decides what
    runs keeps its ``$``/backtick marker), and consumes heredoc bodies as
    single ``heredoc`` tokens. ``start``/``end`` are offsets into the
    ORIGINAL command (``origin`` maps nested bodies back to it). This is a
    refusal-scan aid, not a shell implementation: constructs it cannot
    model degrade towards MORE tokens, never fewer.
    """
    tokens: list[tuple[str, str, int, int]] = []
    length = len(text)
    index = 0
    at_word_start = True
    while index < length:
        char = text[index]
        if char in " \t\r":
            index += 1
            at_word_start = True
            continue
        if char == "#" and at_word_start:
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
            continue
        if char in _OP_CHARS:
            index = _scan_operator(text, index, tokens)
            at_word_start = True
            continue
        index = _scan_word(text, index, tokens, at_word_start, depth)
        at_word_start = False
    return [(kind, body, origin + start, origin + end)
            for kind, body, start, end in tokens]


def _scan_operator(
    text: str, index: int, tokens: list[tuple[str, str, int, int]]
) -> int:
    length = len(text)
    matched = next(
        (op for op in _MULTI_OPS if text.startswith(op, index)), None
    )
    if matched is None:
        matched = text[index]
    tokens.append((_OP, matched, index, index + len(matched)))
    index += len(matched)
    if matched in ("<<", "<<-"):
        # Consume the delimiter word, then the body up to its line.
        while index < length and text[index] in " \t":
            index += 1
        delimiter_start = index
        while index < length and text[index] not in " \t\r\n;&|<>":
            index += 1
        delimiter = text[delimiter_start:index].strip("'\"")
        newline = text.find("\n", index)
        if newline < 0 or not delimiter:
            return index
        body_start = newline + 1
        position = body_start
        body_end = length
        while position <= length:
            line_end = text.find("\n", position)
            line = text[position:] if line_end < 0 else text[position:line_end]
            stripped = line.lstrip("\t") if matched == "<<-" else line
            if stripped.strip() == delimiter:
                body_end = position
                position = length if line_end < 0 else line_end + 1
                break
            if line_end < 0:
                position = length + 1
                break
            position = line_end + 1
        tokens.append((_HEREDOC, text[body_start:body_end], body_start, body_end))
        return min(position, length)
    return index


def _scan_word(
    text: str,
    index: int,
    tokens: list[tuple[str, str, int, int]],
    at_word_start: bool,
    depth: int,
) -> int:
    length = len(text)
    parts: list[str] = []
    start = index
    while index < length:
        char = text[index]
        if char in " \t\r" or char in _OP_CHARS:
            break
        if char == "'":
            close = text.find("'", index + 1)
            if close < 0:
                parts.append(text[index + 1:])
                index = length
                break
            parts.append(text[index + 1:close])
            index = close + 1
            continue
        if char == '"':
            index += 1
            while index < length and text[index] != '"':
                if text[index] == "\\" and index + 1 < length:
                    parts.append(text[index + 1])
                    index += 2
                    continue
                parts.append(text[index])
                index += 1
            index += 1
            continue
        if char == "\\" and index + 1 < length:
            if text[index + 1] == "\n":
                index += 2  # POSIX continuation: join, keep scanning the word
                continue
            parts.append(text[index + 1])
            index += 2
            continue
        if char == "`":
            close = text.find("`", index + 1)
            close = length - 1 if close < 0 else close
            parts.append(text[index:close + 1])  # keep backticks as markers
            index = close + 1
            continue
        if char == "$" and index + 1 < length and text[index + 1] == "(":
            end = _match_paren(text, index + 1)
            parts.append(text[index:end])
            index = end
            continue
        parts.append(char)
        index += 1
    word = "".join(parts)
    if not word and start == index:
        index += 1
    tokens.append((_WORD, word, start, index))
    return index


def _match_paren(text: str, open_index: int) -> int:
    """Index just past the ``)`` matching the ``(`` at ``open_index``."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


class _Unit:
    """One simple command: its words, span and delivery context."""

    __slots__ = (
        "words", "start", "end", "pipe_fed", "has_heredoc", "head",
        "head_index",
    )

    def __init__(self) -> None:
        self.words: list[tuple[str, int, int]] = []  # (text, start, end)
        self.start = -1
        self.end = -1
        self.pipe_fed = False
        self.has_heredoc = False
        self.head = ""
        self.head_index = -1

    def arguments(self) -> list[str]:
        return [text for text, _, _ in self.words[1:]]

    def span_text(self, raw: str) -> str:
        return raw[self.start:self.end] if self.start >= 0 else ""


def _shell_units(
    tokens: list[tuple[str, str, int, int]]
) -> list[_Unit]:
    """Group tokens into simple commands with their delivery context.

    ``{``/``}`` are reserved WORDS that still delimit compound commands,
    so they end the current simple command like a separator would (a
    launch inside ``function f { pool run …; }`` must be its own unit with
    ``pool`` as its head, not an argument swallowed by ``f``)."""
    units: list[_Unit] = []
    unit: _Unit | None = None
    last_separator = ""
    pending_fd_word: tuple[str, int, int] | None = None
    for kind, body, start, end in tokens:
        if kind == _OP:
            if body in _SEPARATOR_OPS:
                unit = None
                last_separator = body
                pending_fd_word = None
            elif body.startswith("<<"):
                if unit is not None:
                    unit.has_heredoc = True
            elif unit is None:
                continue
            # Redirects (<, >, ...) end any pending fd word but stay in-unit.
            pending_fd_word = None
            continue
        if kind == _HEREDOC:
            if unit is not None:
                unit.has_heredoc = True
            continue
        if kind == _WORD and body in ("{", "}"):
            unit = None
            last_separator = ""
            pending_fd_word = None
            continue
        if unit is None:
            unit = _Unit()
            unit.pipe_fed = last_separator == "|"
            units.append(unit)
        if pending_fd_word is not None:
            # ``2>file``: the bare digits belonged to the redirect, not argv.
            unit.words.pop()
            pending_fd_word = None
        unit.words.append((body, start, end))
        if unit.start < 0:
            unit.start = start
        unit.end = end
        pending_fd_word = (body, start, end) if body.isdigit() else None
    for candidate in units:
        candidate.head, candidate.head_index = _command_head(candidate)
    return units


def _command_head(unit: _Unit) -> tuple[str, int]:
    """``(basename, index)`` of the unit's command word (assignments and
    keywords skipped), or ``("", -1)``."""
    for index, (text, _, _) in enumerate(unit.words):
        if text in _COMMAND_KEYWORDS or _ASSIGNMENT_WORD_RE.match(text):
            continue
        if text.startswith("-"):
            continue
        return text.rsplit("/", 1)[-1].lower(), index
    return "", -1


def _unit_is_launch(unit: _Unit) -> bool:
    """True when the unit IS a lexically visible wrapper launch."""
    head = unit.head
    words = [text for text, _, _ in unit.words]
    if head == "pool":
        after = words[unit.head_index + 1:unit.head_index + 2]
        return bool(after) and after[0] in ("run", "remote")
    if head in ("sub.sh", "remote_sub.sh", "slot.py"):
        return True
    if _INTERPRETER_HEAD_RE.match(head) or _ALWAYS_INLINE_HEAD_RE.match(head):
        return any(
            _COMPUTED_WORD_RE.search(text) is None
            and text.rsplit("/", 1)[-1] == "slot.py"
            for text in words[unit.head_index + 1:]
            if not text.startswith("-")
        )
    return False


def _shadow_launch_possible(unit: _Unit) -> bool:
    """True when substituting a wrapper name for a computed word of this
    unit would make it a paid launch (REVIEW_2329 r3 B-1 computed words).

    No runner allowlist: ANY simple command whose computed word could
    expand to a wrapper — ``$P run grok``, ``sudo -n $P run grok``,
    ``su -c '$P run grok'``, ``time $P run grok`` — is a possible
    unattributable launch, while a computed word that can never complete a
    wrapper shape (``echo "$POOL_ORCHESTRATOR_ID"``) stays allowed.
    Assignment VALUES are excluded (they cannot become the command word;
    their own law is the projection check), and a unit that already IS a
    lexically visible launch is left to the launch pipeline — the wrapper
    invocation is observed, and a computed mode token is refused there by
    token equality.
    """
    if _unit_is_launch(unit):
        return False
    if unit.head in _PRINT_ONLY_HEADS:
        return False
    words = [
        text for text, _, _ in unit.words
        if not _ASSIGNMENT_WORD_RE.match(text)
    ]
    computed = [
        text for text in words if _COMPUTED_WORD_RE.search(text)
    ]
    if not computed:
        return False

    def _shadow_variants(text: str, token: str) -> list[str]:
        # Each computed segment in turn becomes the wrapper token while the
        # word's other computed segments expand to nothing: a quoted word
        # never word-splits, so one word can only ever contribute ONE
        # wrapper-shaped argument.
        variants: list[str] = []
        for match in _COMPUTED_SEGMENT_RE.finditer(text):
            variants.append(
                _COMPUTED_SEGMENT_RE.sub("", text[:match.start()])
                + token
                + _COMPUTED_SEGMENT_RE.sub("", text[match.end():])
            )
        return variants

    for token in _SHADOW_WRAPPER_TOKENS:
        for text in computed:
            for variant in _shadow_variants(text, token):
                # Alone: the word may carry a whole launch body
                # (``su -c '$P run grok' root``).
                if _wrapper_invocations(variant):
                    return True
                # In place: the words around it keep their literal
                # positions (``sudo -n $P run grok``, ``time $P run …``).
                substituted = [
                    variant if other == text else other for other in words
                ]
                if _wrapper_invocations(" ".join(substituted)):
                    return True
    return False


def _interpreter_problem(unit: _Unit) -> str:
    """Why this interpreter invocation's program is unobservable, or ''.

    Judged by HOW the interpreter receives its program — flag text, pipe,
    heredoc, computed argument — never by which letters a flag spells, so
    ``-c``, ``-Sc``, ``-Bc``, ``-we``, ``-E``, ``-p``, ``--eval``, ``-ne``
    are all one refusal class. Following POSIX grammar, only option words
    BEFORE the first operand are the interpreter's own (anything after the
    script path — ``slot.py glm … -- run`` — belongs to the script), so the
    bare script-file form keeps its lexically observed launch.
    """
    head = unit.head
    if _ALWAYS_INLINE_HEAD_RE.match(head):
        return (
            f"{head}'s program text is always an inline argument, so a "
            "launch it carries is assembled at runtime"
        )
    if not _INTERPRETER_HEAD_RE.match(head):
        return ""
    operands_started = False
    for text in unit.arguments():
        if operands_started:
            if _COMPUTED_WORD_RE.search(text):
                return (
                    f"{head} receives a computed argument ({text!r}); the "
                    "program or its inputs are assembled at runtime"
                )
            continue
        if text == "-":
            return f"{head} reads its program from stdin ('-')"
        if text.startswith("-") and text != "--":
            return (
                f"{head} is invoked with option arguments ({text!r}); the "
                "program may be inline option text (one-liner), which the "
                "guard cannot attribute"
            )
        if text == "--":
            continue
        if _COMPUTED_WORD_RE.search(text):
            return (
                f"{head} receives a computed argument ({text!r}); the "
                "program or its inputs are assembled at runtime"
            )
        operands_started = True
    if unit.pipe_fed:
        return f"{head} reads its program from the pipe feeding it"
    if unit.has_heredoc:
        return f"{head} reads its program from a heredoc"
    return ""


def _nested_shell_bodies(
    units: list[_Unit], raw: str, depth: int
) -> list[tuple[_Unit, list[tuple[str, str, int, int]]]]:
    """``(shell_unit, body_tokens)`` for every ``sh -c <script>`` body."""
    bodies: list[tuple[_Unit, list[tuple[str, str, int, int]]]] = []
    if depth >= 4:
        return bodies
    for unit in units:
        if not _SHELL_HEAD_RE.match(unit.head):
            continue
        words = unit.words
        for position in range(1, len(words) - 1):
            text, start, end = words[position]
            if text != "-c":
                continue
            body_text, _, _ = words[position + 1]
            bodies.append((unit, _shell_scan(body_text, start, depth + 1)))
            break
    return bodies


def _all_units(
    tokens: list[tuple[str, str, int, int]], raw: str, depth: int = 0
) -> list[_Unit]:
    """Units of this token stream plus every nested ``-c`` body's units."""
    units = _shell_units(tokens)
    for _, body_tokens in _nested_shell_bodies(units, raw, depth):
        units.extend(_all_units(body_tokens, raw, depth + 1))
    return units


def _brace_group_spans(
    tokens: list[tuple[str, str, int, int]],
) -> list[tuple[int, int]]:
    """Spans of ``{ ... }`` groups (loop bodies, function bodies, grouped
    repeats) among these tokens (REVIEW_2329 r3 M-A). ``{``/``}`` are shell
    reserved WORDS, so they appear here as word tokens."""
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for kind, body, start, end in tokens:
        if kind != _WORD:
            continue
        if body == "{":
            stack.append(start)
        elif body == "}" and stack:
            opened = stack.pop()
            spans.append((opened, end))
    return spans


def _function_body_spans(
    tokens: list[tuple[str, str, int, int]], units: list[_Unit]
) -> list[tuple[int, int]]:
    """Spans of function-definition bodies: ``name() { … }`` / ``f() ( … )``
    / ``function f { … }`` (REVIEW_2329 r3 M-A)."""
    spans: list[tuple[int, int]] = []
    for position in range(len(tokens) - 2):
        kind, body, start, end = tokens[position]
        if kind != _WORD or _ASSIGNMENT_WORD_RE.match(body):
            continue
        if (tokens[position + 1][:2] == (_OP, "(")
                and tokens[position + 2][:2] == (_OP, ")")
                and tokens[position + 1][2] == end
                and tokens[position + 2][2] == tokens[position + 1][3]):
            body_start = tokens[position + 2][3]
            body_end = _compound_end(tokens, position + 3)
            if body_end > body_start:
                spans.append((body_start, body_end))
    return spans


def _compound_end(
    tokens: list[tuple[str, str, int, int]], index: int
) -> int:
    """End offset of the compound command starting at ``index``: a brace
    group (reserved-word ``{``), a parenthesised subshell, or one simple
    command up to its separator."""
    depth = 0
    brace_depth = 0
    for kind, body, _, end in tokens[index:]:
        if kind == _WORD:
            if body == "{":
                brace_depth += 1
                continue
            if body == "}":
                if brace_depth == 0:
                    return end
                brace_depth -= 1
                continue
            continue
        if body == "(":
            depth += 1
            continue
        if body == ")":
            if depth == 0:
                return end
            depth -= 1
            continue
        if body in _SEPARATOR_OPS and depth == 0 and brace_depth == 0:
            return end
    return tokens[-1][3] if tokens else 0


def _launch_in_text(text: str) -> bool:
    """A lexically visible wrapper launch inside a plain text span."""
    return bool(_wrapper_invocations(text))

def family(model: str) -> str:
    lowered = (model or "").strip().lower()
    for name in ("fable", "opus", "sonnet", "haiku"):
        if name in lowered:
            return name
    return lowered


def _emit(payload: dict[str, object]) -> NoReturn:
    print(json.dumps({"hookSpecificOutput": payload}, sort_keys=True))
    raise SystemExit(0)


def deny(reason: str) -> NoReturn:
    _emit(
        {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    )


def allow_context(context: str) -> None:
    _emit({"hookEventName": "PreToolUse", "additionalContext": context})


def _scope_roots(home: Path) -> tuple[Path, ...]:
    roots = [
        home / ".mastermind" / "worktrees",
        home / "lanes",
        home / "terminals",
        home / "Documents" / "Cluade",
        home / "Documents" / "GitHub",
        home / "Projects" / "MastermindX" / "repos",
        Path("/Volumes/Mastermind/agent-workspaces"),
    ]
    extra = os.environ.get("MASTERMIND_SCOPE_ROOTS", "")
    for raw in extra.split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw).expanduser())
    return tuple(Path(os.path.realpath(path)) for path in roots)


def is_project_scope(payload: dict[str, object]) -> bool:
    cwd = Path(os.path.realpath(str(payload.get("cwd") or os.getcwd())))
    home = Path(os.path.expanduser("~"))
    for root in _scope_roots(home):
        try:
            cwd.relative_to(root)
            return True
        except ValueError:
            if cwd == root:
                return True
    return False


def _session_scope(payload: dict[str, object]) -> str:
    """Return a stable best-effort provider-session scope for local cooldowns.

    Prefer explicit provider/session identifiers. Fall back to documented/installed
    environment identities, then the long-lived provider parent process. This state is
    only a local anti-poll hint; it is not lifecycle or RuntimeBinding authority.
    """

    for key in (
        "session_id",
        "sessionId",
        "thread_id",
        "threadId",
        "conversation_id",
        "conversationId",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_SESSION_ID"):
        value = os.environ.get(name, "").strip()
        if value:
            return f"{name}:{value}"
    return f"ppid:{os.getppid()}"


def _poll_key(command: str, cwd: str, session_scope: str) -> str | None:
    repo_match = REPO_ARG_RE.search(command)
    scope = repo_match.group("repo").lower() if repo_match else os.path.realpath(cwd)
    for label, regex in (
        ("pr", PR_READ_RE),
        ("run", RUN_READ_RE),
        ("run", API_RUN_READ_RE),
    ):
        match = regex.search(command)
        if match:
            return f"{session_scope}:{label}:{scope}:{match.group('id')}"
    return None


def _poll_state_dir() -> Path:
    uid = getattr(os, "getuid", lambda: 0)()
    return Path(
        os.environ.get(
            "MASTERMIND_CI_POLL_STATE_DIR",
            str(Path(tempfile.gettempdir()) / f"mastermind-ci-poll-{uid}"),
        )
    )


def repeat_poll_reason(key: str, *, now: float | None = None) -> str | None:
    moment = time.time() if now is None else now
    try:
        root = _poll_state_dir()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        path = root / f"{digest}.json"
        last = 0.0
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            last = float(value.get("at") or 0.0) if isinstance(value, dict) else 0.0
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError, OSError):
            last = 0.0
        waited = moment - last
        if 0 < waited < POLL_COOLDOWN_S:
            return (
                f"Mastermind CI wait guard: redundant status read for {key}; the same "
                f"target was read {int(waited)}s ago. Do not wait for the cooldown. "
                "The existing watcher/event is the next observation; immediately "
                "continue another independent authorized project lane."
            )
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps({"at": moment, "key": key}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return None
    return None


def _command_assignments(command: str, name: str) -> list[str]:
    """EVERY shell-level ``NAME=value`` assignment of ``name`` in the command,
    in positional order (prefix assignments, ``env NAME=…``, nested
    ``export NAME=…`` inside quoted sub-commands). A dynamic value (``$``,
    backtick) cannot prove stable identity and is recorded as ``''``.

    POSIX applies prefix assignments left-to-right (the LAST wins in the
    launched child) and a nested ``export`` overrides at runtime, so any
    check that inspects only the first occurrence compares a decoy while
    the child runs under a different identity. Callers must therefore
    judge all occurrences, never one.
    """
    pattern = re.compile(
        rf"(?:^|[\s;&|]){re.escape(name)}="
        rf"(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|]*))"
    )
    values: list[str] = []
    for match in pattern.finditer(command):
        value = next(
            (value for value in match.groups() if value is not None),
            "",
        ).strip()
        if any(token in value for token in ("$", "`")):
            value = ""
        values.append(value)
    return values


def _command_assignment(command: str, name: str) -> tuple[bool, str]:
    """(assigned?, effective value): the value the launched child actually
    receives — the LAST literal assignment — or ``''`` when any occurrence
    is empty/dynamic (an unstable identity is treated as missing)."""
    values = _command_assignments(command, name)
    if not values:
        return False, ""
    if not all(values):
        return True, ""
    return True, values[-1]


def _command_or_environment_value(command: str, name: str) -> str:
    # An explicit shell assignment wins over inherited process state, including
    # an explicit empty assignment. This mirrors the environment the launched
    # child will actually receive instead of letting a parent value mask a reset.
    found, value = _command_assignment(command, name)
    if found:
        return value
    return os.environ.get(name, "").strip()


def shared_placement_armed() -> bool:
    """True when this session's paid launches run under the shared placement
    path: the owner armed the scope (per-session, OQ-7 scoped arming) or has
    already projected a binding into the session environment."""
    if os.environ.get(BINDING_ENV, "").strip():
        return True
    return (
        os.environ.get(SHARED_PLACEMENT_ENV, "").strip().lower()
        in SHARED_PLACEMENT_ARM_TOKENS
    )


def _binding_problems(binding: object, owner: str) -> str:
    """Stdlib-only ExecutionBinding.v1 shape validation. The guard is a
    verbatim-copy deployment artifact and cannot import the shared contracts
    module, so it re-states the binding's structural law locally."""
    if not isinstance(binding, dict):
        return f"{owner}: binding is not a JSON object"
    if str(binding.get("schema") or "") != EXECUTION_BINDING_SCHEMA:
        return f"{owner}: schema must be {EXECUTION_BINDING_SCHEMA}"
    for name in ("root_run_ref", "immediate_parent_run_ref", "logical_child_key"):
        if not str(binding.get(name) or "").strip():
            return f"{owner}: {name} is required"
    if not _BINDING_HEX64_RE.match(str(binding.get("request_digest") or "")):
        return f"{owner}: request_digest must be a 64-char lowercase hex digest"
    for name in ("fence_counter", "assignment_generation"):
        # Required, never defaulted: an absent fence must not pass as fence 0.
        value = binding.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return f"{owner}: {name} must be present as an integer >= 0"
    return ""


def _canonical_command(command: str) -> str:
    """The command with shell quoting (quotes, backslashes) removed, so a
    name or mode split or hidden by quotes (``"POOL_ORCH""ESTRATOR_ID=x"``,
    ``sub.sh "grok"``) is scanned as the shell will see it. A backslash-
    newline is a POSIX line continuation and the shell joins it with
    NOTHING (REVIEW_2329 r2 N-1): ``POOL_ORCH\\<newline>ESTRATOR_ID=x`` and
    ``pool ru<newline>n`` canonicalise to the joined words, never to two
    words with an inserted space."""
    return re.sub(r"[\"'\\]", "", command.replace("\\\n", ""))


def _simple_command_head(canon: str, offset: int) -> str:
    """Basename of the first word of the simple command containing
    ``offset`` (assignments and compound-command keywords skipped)."""
    starts = [m.end() for m in _SIMPLE_COMMAND_SPLIT_RE.finditer(canon, 0, offset)]
    prefix = canon[(starts[-1] if starts else 0):offset].split()
    for word in prefix:
        if word in _COMMAND_PREFIX_WORDS or re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
            continue
        return word.rsplit("/", 1)[-1].lower()
    return ""


def _wrapper_invocations(command: str) -> list[tuple[int, str, str, bool]]:
    """EVERY wrapper invocation in ``command``, positional:
    ``(offset, wrapper, token, known_mode)`` for all five shapes, repeated.

    Unlike :data:`FABRIC_LAUNCH_RE`, the mode is NOT required to be on the
    wrapper's list: an off-list mode (``sub.sh zebra-glm``) is still an
    invocation (``known_mode=False``) so it can be refused instead of
    passing unobserved. A wrapper name with no argument, an argument of a
    read-only inspector (``cat sub.sh``), or a documented pure helper mode
    (``sub.sh __launch_plan``) is not a paid launch.
    """
    canon = _canonical_command(command)
    found: list[tuple[int, str, str, bool]] = []
    for match in _WRAPPER_RE.finditer(canon):
        wrapper = re.sub(r"\s+", " ", match.group("wrapper").lower())
        index, modes = _WRAPPER_SHAPES[wrapper]
        args: list[str] = []
        position = match.end()
        while len(args) < index + 2:
            arg = _WRAPPER_ARG_RE.match(canon, position)
            if not arg:
                break
            args.append(arg.group(1).lower())
            position = arg.end()
        if not args:
            continue
        head = _simple_command_head(canon, match.start())
        if head in _INSPECTORS:
            continue
        token = args[index] if len(args) > index else ""
        if token in NON_LAUNCH_WRAPPER_MODES or (
            len(args) > index + 1 and args[index + 1] == "__launch_plan"
        ):
            continue
        known = bool(token) and (modes is None or token in modes)
        found.append((match.start(), wrapper, token, known))
    return found


def launch_provider_tokens(command: str) -> list[tuple[int, str]]:
    """``(offset, token)`` for EVERY paid launch in ``command``, positional.

    Covers every wrapper shape: ``pool run <pool>``, ``pool remote <host>
    <pool>``, ``sub.sh <mode>``, ``remote_sub.sh <host> <mode>`` and
    ``slot.py <pool>`` — the same wrappers every engine's paid launch goes
    through. Each token is read from its own launch's arguments, so a later
    launch can never stand in for an earlier one.
    """
    return [(offset, token) for offset, _, token, _ in _wrapper_invocations(command)]


def launch_provider_token(command: str) -> str:
    """The provider/pool token of the FIRST paid launch (lowercased), or ''.
    Gate logic must use :func:`launch_provider_tokens` (all launches)."""
    tokens = launch_provider_tokens(command)
    return tokens[0][1] if tokens else ""


def _deny_structurally_unobservable(raw: str) -> None:
    """Refuse command SHAPES no lexically observed wrapper invocation can
    cover (WO-11 r5; REVIEW_2329 r3 B-1, M-A, M-B).

    Armed sessions only, and only when a wrapper NAME appears somewhere in
    the canonical command — otherwise the command is the documented
    arbitrary-process limit, not this gate's fence. The raw command is
    tokenised (quote-aware, heredoc and nested ``-c`` bodies included) and
    classified structurally:

    * interpreter invocations whose program is delivered as inline flag
      text / pipe / heredoc / computed argument (``python3 -Sc``,
      ``perl -we``, ``node --eval``, ``python3 - <<EOF``, ``echo | python3``,
      ``awk 'system("pool …")'``) — refused regardless of flag spelling;
    * computed words (``$P``, ``${P}``, ``$(...)``, backticks) wherever a
      wrapper name substituted for them would complete a paid launch —
      ``time|sudo|caffeinate|ssh|su -c|flock|systemd-run … $P run grok``,
      ``P=sub.sh; sudo $P glm`` — no runner allowlist to evade;
    * command substitution (``$(...)``, backticks) anywhere in the command
      — its expansion is executed and can hide a second launch;
    * wrapper launches inside shapes that execute them more than once or
      later: function-definition bodies, ``{ … }`` brace groups (including
      bash brace-body loops), ``trap`` payloads, ``watch`` repeaters;
    * ``eval``/``source``/``.`` inside the same nested ``-c`` script that
      performs the launch (the launch environment becomes unobservable).

    Conservative by design: over-refusal is honest, under-refusal is a
    bypass. The bare interpreter script-file form
    (``python3 …/slot.py glm -- run``) keeps its lexically observed launch.
    """
    canon = _canonical_command(raw)
    if not _WRAPPER_NAME_RE.search(canon):
        return
    tokens = _shell_scan(raw)
    units = _shell_units(tokens)
    nested = _nested_shell_bodies(units, raw, 0)
    all_units = list(units)
    for _, body_tokens in nested:
        all_units.extend(_all_units(body_tokens, raw, 1))
    all_tokens = list(tokens)
    for _, body_tokens in nested:
        all_tokens.extend(body_tokens)

    # B-1: interpreter program delivery.
    for unit in all_units:
        problem = _interpreter_problem(unit)
        if problem:
            deny(
                "Mastermind shared-placement guard: unobservable launch — "
                f"{problem}. The launch this interpreter could carry is "
                "assembled at runtime, so provider substitution, the "
                "identity projection and the one-attempt law cannot be "
                "checked. Run the paid launch as a plain command."
            )

    # M-B: eval/source/. inside the nested -c script that launches (before
    # the computed-word loop, so the nested launcher's own $X/$Y identity
    # assembly reports the environment it actually corrupts).
    for _, body_tokens in nested:
        body_text = " ".join(body for _, body, _, _ in body_tokens)
        if not (_launch_in_text(body_text)):
            continue
        for kind, body, _, _ in body_tokens:
            if kind == _WORD and body in ("eval", "source", "."):
                deny(
                    "Mastermind shared-placement guard: unobservable "
                    "launch environment — eval, source or '.' inside the "
                    "same nested shell script that performs the launch "
                    "can change the child's POOL_* identity outside what "
                    "this guard can check. Run the paid launch as a plain "
                    "command."
                )

    # B-1: computed words by shadow substitution; $(…)/backticks anywhere.
    for unit in all_units:
        for text, _, _ in unit.words:
            if "$(" in text or "`" in text:
                deny(
                    "Mastermind shared-placement guard: unobservable "
                    f"launch — the computed word {text!r} contains a "
                    "command substitution, whose expansion runs in this "
                    "very shell and can construct or hide a paid launch "
                    "the guard cannot attribute. Pass literal arguments."
                )
        if _shadow_launch_possible(unit):
            deny(
                "Mastermind shared-placement guard: unobservable launch — "
                "a computed word ($… or `…`) in this command could expand "
                "to a paid-launch wrapper (time/sudo/env/ssh/su/flock/"
                "systemd-run … $P run …), so the wrapper invocation and "
                "any identity assignment around it cannot be observed. "
                "Invoke the wrapper by its literal name."
            )

    # M-A: launches inside runtime-multiplying or deferred shapes.
    launch_spans = [
        (unit.start, unit.end)
        for unit in all_units
        if _unit_is_launch(unit)
    ]
    group_spans = _brace_group_spans(all_tokens)
    group_spans += _function_body_spans(all_tokens, all_units)
    for start, end in group_spans:
        if any(s >= start and e <= end for s, e in launch_spans):
            deny(
                "Mastermind shared-placement guard: runtime-multiplexed "
                "launch — a paid launch sits inside a function body or "
                "{ … } brace group (loop body / grouped repeat), which "
                "can execute it more than once or later, but the current "
                "binding covers exactly one attempt. Every paid child "
                "must be admitted and claimed through the placement "
                "authority before launch."
            )
    for unit in all_units:
        if unit.head not in _LAUNCH_STAGE_HEADS:
            continue
        role = "trap payload" if unit.head == "trap" else "watch repeater"
        arguments = " ".join(
            text for text, _, _ in unit.words[unit.head_index + 1:]
        )
        if _launch_in_text(arguments):
            deny(
                "Mastermind shared-placement guard: runtime-multiplexed "
                f"launch — a paid launch is staged inside a {role}, which "
                "can execute it more than once or later, but the current "
                "binding covers exactly one attempt. Every paid child "
                "must be admitted and claimed through the placement "
                "authority before launch."
            )


def _runtime_multiplexed(canon: str, offsets: list[int]) -> bool:
    """True when a wrapper invocation sits inside a construct that executes
    it N times at runtime: a for/while/until body (``do ... done``) or an
    xargs/parallel/find -exec executor's argument tail (REVIEW_2329 r2
    N-2). One binding covers exactly one attempt, so N runtime children
    under one lexical launch are refused as unaccounted descendants."""
    spans = [match.span() for match in _LOOP_BODY_RE.finditer(canon)]
    spans += [match.span() for match in _BATCH_EXECUTOR_RE.finditer(canon)]
    return any(
        start <= offset < end for start, end in spans for offset in offsets
    )


def _env_clear_offsets(canon: str) -> list[int]:
    """Offsets of ``env`` invocations that clear the inherited environment
    (``env -i``, ``env -``, ``--ignore-environment``, clustered ``-iv``) or
    re-split their arguments (``-S``), which can hide a clear."""
    offsets: list[int] = []
    for match in re.finditer(r"(?<![A-Za-z0-9_.-])env(?=[ \t])", canon):
        words = re.match(r"[^;&|\n()`]*", canon[match.end():]).group(0).split()
        index = 0
        while index < len(words):
            word = words[index]
            if (
                word in ("-", "--ignore-environment", "-S")
                or word.startswith("--split-string")
                or re.fullmatch(r"-[A-Za-z]*[iS][A-Za-z]*", word)
            ):
                offsets.append(match.start())
                break
            if word in ("-u", "-C", "-P", "--unset", "--chdir"):
                index += 2
                continue
            if word.startswith("-") or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", word):
                index += 1
                continue
            break
    return offsets


def _effective_identity_values(command: str, name: str) -> list[str] | None:
    """Canonical view of every way ``command`` sets ``name`` for its child.

    Returns ``None`` when the command does not touch ``name`` (the inherited
    session value governs); otherwise EVERY value the child could receive:
    each literal assignment in any form — prefix (last wins), ``env``,
    ``export``/``declare``/``readonly``, ``+=``, quoted or split by quotes,
    nested inside ``sh -c '…'`` — plus ``''`` for every clearing or
    non-literal form (``unset``, ``env -u``, ``env -i`` not followed by a
    reassignment, ``printf -v``, ``read``, ``declare -n``, ``${NAME:=…}``,
    dynamic ``$``/backtick values). The caller refuses unless every value
    equals the server-derived projection.
    """
    canon = _canonical_command(command)
    values = list(_command_assignments(command, name))
    events: list[tuple[int, str]] = []
    occurrence = re.compile(
        rf"(?:(?<![A-Za-z0-9_])|(?<=-u)){re.escape(name)}(?![A-Za-z0-9_])"
    )
    for match in occurrence.finditer(canon):
        before, after = canon[:match.start()], canon[match.end():]
        if after.startswith("="):
            value = re.match(r"=([^\s;&|<>()`{}]*)", after).group(1)
            events.append((match.start(), "" if "$" in value else value))
        elif before.endswith("$") or (
            before.endswith("${") and not re.match(r":?=", after)
        ):
            continue  # a read of the value, not a change
        elif re.search(r"(?:^|[\s;&|(])export\s+$", before) and re.match(
            r"(?:[\s;&|)]|$)", after
        ):
            continue  # bare `export NAME` re-exports the inherited value
        else:
            events.append((match.start(), ""))
    for offset in _env_clear_offsets(canon):
        if not any(at > offset and value for at, value in events):
            events.append((offset, ""))
    canonical = [value for _, value in events]
    extra = [value for value in values if value not in canonical]
    if not canonical and not extra:
        return None
    return canonical + extra


def _principal_ids() -> tuple[int, frozenset[int]]:
    """(effective uid, group ids) of the fenced principal (this session)."""
    return os.geteuid(), frozenset({os.getegid(), *os.getgroups()})


def _principal_controls(info: os.stat_result, uid: int, gids: frozenset[int]) -> bool:
    if uid == 0 or info.st_uid == uid:
        return True  # root, or the owner (who can always chmod/replace)
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        return False  # replacing a symlink is governed by its directory
    writable = bool(mode & stat.S_IWOTH) or (
        info.st_gid in gids and bool(mode & stat.S_IWGRP)
    )
    if writable and stat.S_ISDIR(mode) and mode & stat.S_ISVTX:
        return False  # sticky: entries the principal does not own are safe
    return writable


def _owner_uid_allowlist() -> tuple[int, ...] | None:
    """The owner-asserted uid allowlist for the receipt channel, ``()`` when
    malformed (refuse everything), or None when not projected."""
    raw = os.environ.get(PLACEMENT_RECEIPT_OWNER_UIDS_ENV, "").strip()
    if not raw:
        return None
    uids: list[int] = []
    for token in re.split(r"[,\s]+", raw):
        if not token.isdigit():
            return ()
        uids.append(int(token))
    return tuple(uids)


def _receipt_channel_problem(path_text: str) -> str:
    """'' when the receipt can only have been produced by the placement owner.

    Trust basis (no signing authority exists by design): the owner runs as
    its own dedicated Executive service account and projects the receipt
    into a path the fenced principal cannot write. The channel is defined
    POSITIVELY, not just negatively (REVIEW_2329 r2 N-4): every component
    of both the literal and the resolved path must be owned by root or by a
    uid on the owner-projected allowlist (``_owner_uid_allowlist``;
    mandatory — without it no path qualifies), AND outside the principal's
    control — not owned by it, not writable by it — so it can neither
    rewrite the receipt, restore an older copy, re-point a symlink, nor
    pass off another local account's file as the owner channel. A receipt
    the session could have written itself is refused outright.
    """
    uid, gids = _principal_ids()
    allowlist = _owner_uid_allowlist()
    if allowlist is None:
        return (
            "the owner-uid allowlist "
            f"({PLACEMENT_RECEIPT_OWNER_UIDS_ENV}) is not projected, so no "
            "receipt path can be positively attributed to the placement "
            "owner"
        )
    if not allowlist:
        return (
            "the owner-uid allowlist "
            f"({PLACEMENT_RECEIPT_OWNER_UIDS_ENV}) is malformed; expected "
            "comma-separated positive uids"
        )
    allowed_owners = {0, *allowlist}
    literal = Path(os.path.abspath(path_text))
    resolved = Path(os.path.realpath(path_text))
    for chain in (literal, resolved):
        for component in (*reversed(chain.parents), chain):
            try:
                info = os.lstat(component)
            except OSError:
                return f"{component} cannot be inspected"
            if _principal_controls(info, uid, gids):
                return (
                    f"{component} is owned or writable by this session's "
                    "principal"
                )
            if info.st_uid not in allowed_owners:
                return (
                    f"{component} is owned by uid {info.st_uid}, which is "
                    "neither root nor on the owner-uid allowlist the "
                    "placement owner projected"
                )
    try:
        if not stat.S_ISREG(os.stat(resolved).st_mode):
            return f"{resolved} is not a regular file"
    except OSError:
        return f"{resolved} cannot be inspected"
    return ""


def _expected_projection(binding: dict) -> dict[str, str]:
    """POOL_ORCHESTRATOR_ID / POOL_PARENT_RUN_ID are server-derived
    projections of the binding (Rev 4 l.287): children cannot promote,
    re-root or re-parent themselves by changing the environment."""
    root = str(binding.get("original_root_orchestrator_ref") or "").strip()
    if not root:
        root = str(binding.get("root_run_ref") or "").strip()
    return {
        "POOL_ORCHESTRATOR_ID": root,
        "POOL_PARENT_RUN_ID": str(
            binding.get("immediate_parent_run_ref") or ""
        ).strip(),
    }


def validate_execution_binding(command: str) -> None:
    """Refuse paid launches/delegations not covered by the CURRENT
    broker-issued ExecutionBinding (WO-11; Rev 4 S3.D l.287-289, S4 steps
    3-4).

    Refusal classes: missing binding, stale fence (the reservation moved,
    was released or expired), provider substitution after reservation, and
    unaccounted descendants (a binding that does not cover this launch's
    child identity, or more than one paid launch under one binding). The
    binding is only an assignment of opaque references — never a
    credential, and there is no independent signing authority: it is
    trusted exactly as far as it matches the owner's current lease receipt.

    Trust basis and what remains trusting:

    * Session environment (binding, receipt path, optional digest pin): the
      owner projects it into the provider process; a launched command cannot
      alter the environment this hook runs in, so command-level assignments
      of these names are ignored.
    * Receipt: accepted only from an owner-only channel — every component
      of its path must be owned by root or a uid on the owner-projected
      allowlist AND outside the fenced principal's control (see
      ``_receipt_channel_problem``). The principal therefore cannot forge,
      roll back or replay it, no third local account's file qualifies as
      the channel, and a receipt it could have written is refused. This
      relies on the OS uid boundary between the session and the owner's
      service account: a same-uid owner gets no shared-placement launches
      at all (fail closed), and root is outside this model.
    * Lease currency: the receipt is as current as the owner's re-projection
      (atomic replace per lease event, WO-18). If the owner stops
      re-projecting, ``lease_expires_at_ms`` still bounds the lease.

    Lexical scope (documented, not claimed): the gate judges the command
    text it is shown — every wrapper invocation in it (all five shapes,
    repeated, heredoc bodies included, off-list modes refused) and every
    identity assignment form, with backslash-newline canonicalised as a
    POSIX join (empty string). Command SHAPES are classified structurally
    (``_deny_structurally_unobservable``): interpreter invocations whose
    program is inline flag text, piped, heredoc-fed or computed are
    refused regardless of flag spelling; computed words are refused
    wherever a wrapper substituted for them would complete a launch
    (shadow substitution); command substitution is refused anywhere;
    launches inside loop bodies, function bodies, brace groups, batch
    executors (xargs/parallel/find -exec), trap payloads and watch
    repeaters are refused as unaccounted descendants; eval/source/'.' in
    the nested -c script that performs the launch is refused as an
    unobservable environment (conservative — the bare interpreter
    script-file form ``python3 …/slot.py glm -- run`` stays observed).
    Scripts staged in an EARLIER command or a
    file and executed later, and environment injected by provider-side
    mechanisms outside the command, are not observed; eval/source/
    computed-name assignments in a launch command are refused as
    unobservable.
    """
    raw_binding = os.environ.get(BINDING_ENV, "").strip()
    if not raw_binding:
        deny(
            "Mastermind shared-placement guard: missing binding — this "
            "session is armed for shared placement but carries no "
            f"broker-issued {EXECUTION_BINDING_SCHEMA} ({BINDING_ENV}). No "
            "paid launch may proceed without the placement authority's "
            "current binding; recover through the original operation key, "
            "never by launching locally."
        )
    try:
        binding = json.loads(raw_binding)
    except ValueError:
        deny(
            "Mastermind shared-placement guard: missing binding — "
            f"{BINDING_ENV} is not valid JSON."
        )
    problem = _binding_problems(binding, "shared-placement guard")
    if problem:
        deny(f"Mastermind shared-placement guard: {problem}.")

    receipt_path = os.environ.get(PLACEMENT_RECEIPT_ENV, "").strip()
    if not receipt_path:
        deny(
            "Mastermind shared-placement guard: the owner placement receipt "
            f"channel ({PLACEMENT_RECEIPT_ENV}) is unavailable; the binding "
            "cannot be checked against the current lease. Never launch a "
            "paid child while placement truth is uncertain."
        )
    channel_problem = _receipt_channel_problem(receipt_path)
    if channel_problem:
        deny(
            "Mastermind shared-placement guard: the placement receipt is not "
            f"owner-authenticated — {channel_problem}, so the fenced session "
            "could have forged, rolled back or replayed it. The receipt must "
            "be projected by the placement owner into a path this session "
            "cannot write. Never launch a paid child while placement truth "
            "is uncertain."
        )
    try:
        receipt_bytes = Path(receipt_path).read_bytes()
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (OSError, ValueError):
        deny(
            "Mastermind shared-placement guard: the owner placement receipt "
            f"at {receipt_path} is unreadable; the binding cannot be checked "
            "against the current lease. Never launch a paid child while "
            "placement truth is uncertain."
        )
    pinned_digest = os.environ.get(PLACEMENT_RECEIPT_DIGEST_ENV, "").strip().lower()
    if pinned_digest:
        if not _BINDING_HEX64_RE.match(pinned_digest):
            deny(
                "Mastermind shared-placement guard: receipt integrity — "
                f"{PLACEMENT_RECEIPT_DIGEST_ENV} must be the 64-char hex "
                "SHA-256 of the owner-written receipt."
            )
        if hashlib.sha256(receipt_bytes).hexdigest() != pinned_digest:
            deny(
                "Mastermind shared-placement guard: receipt integrity — the "
                f"placement receipt at {receipt_path} does not match the "
                "digest the owner pinned into this session; the receipt was "
                "rewritten, replayed or re-projected since claim. Re-claim "
                "through the placement authority instead of launching on an "
                "unverifiable lease."
            )
    if (
        not isinstance(receipt, dict)
        or str(receipt.get("schema") or "") != PLACEMENT_RECEIPT_SCHEMA
    ):
        deny(
            "Mastermind shared-placement guard: placement receipt schema "
            f"must be {PLACEMENT_RECEIPT_SCHEMA}."
        )
    current = receipt.get("execution_binding")
    problem = _binding_problems(current, "placement receipt")
    if problem:
        deny(f"Mastermind shared-placement guard: {problem}.")

    # Unaccounted descendants: the presented binding must BE the owner's
    # current fenced assignment — same (root, immediate parent, logical
    # child) identity, same admitted digest, same fenced attempt and
    # assignment generation.
    for name in _BINDING_IDENTITY_FIELDS:
        if str(binding.get(name)) != str(current.get(name)):
            deny(
                "Mastermind shared-placement guard: unaccounted descendant "
                f"— {name} in the presented binding does not match the "
                "owner's current assignment. Every paid child must be "
                "admitted and claimed through the placement authority "
                "before launch."
            )

    # Current lease: the fence must not have moved and the lease must be
    # held and unexpired. Launching on a stale fence double-spends the
    # reserved host slot, root concurrency and shared quota.
    fence_now = receipt.get("fence_counter")
    if isinstance(fence_now, bool) or not isinstance(fence_now, int):
        deny(
            "Mastermind shared-placement guard: placement receipt "
            "fence_counter must be an integer."
        )
    if fence_now != current.get("fence_counter") or str(
        receipt.get("attempt_ref")
    ) != str(current.get("attempt_ref")):
        deny(
            "Mastermind shared-placement guard: placement receipt is "
            "internally inconsistent (top-level fence_counter/attempt_ref "
            "disagree with its embedded execution_binding)."
        )
    fence_held = binding.get("fence_counter")
    lease_state = receipt.get("lease_state")
    expires_ms = receipt.get("lease_expires_at_ms")
    if isinstance(expires_ms, bool) or not isinstance(expires_ms, int):
        deny(
            "Mastermind shared-placement guard: placement receipt "
            "lease_expires_at_ms must be an integer (epoch milliseconds)."
        )
    expired = int(time.time() * 1000) >= expires_ms
    if fence_held != fence_now or lease_state != LEASE_STATE_HELD or expired:
        deny(
            "Mastermind shared-placement guard: stale fence — the presented "
            f"binding holds fence {fence_held} but the owner's current "
            f"lease is fence {fence_now} (lease_state="
            f"{lease_state or 'UNKNOWN'}" + (", lease expired" if expired else "")
            + "). The reservation moved; re-claim through the placement "
            "authority instead of launching on a superseded assignment."
        )

    if not command:
        launches: list[tuple[int, str, str, bool]] = []
    else:
        if _UNOBSERVABLE_ENV_RE.search(_canonical_command(command)):
            deny(
                "Mastermind shared-placement guard: unobservable launch "
                "environment — eval, source/., BASH_ENV/ENV or a computed "
                "variable name can change the child's POOL_* identity outside "
                "what this guard can check. Run the paid launch as a plain "
                "command."
            )
        launches = _wrapper_invocations(command)
        if launches and _runtime_multiplexed(
            _canonical_command(command),
            [offset for offset, _, _, _ in launches],
        ):
            deny(
                "Mastermind shared-placement guard: runtime-multiplexed "
                "launch — a for/while/until loop body or an xargs/parallel/"
                "find -exec executor repeats this paid launch at runtime, "
                "but the current binding covers exactly one attempt. Every "
                "paid child must be admitted and claimed through the "
                "placement authority before launch."
            )

    # Server-derived projections: EVERY identity value the launched child
    # could receive must equal what the binding projects (canonical view of
    # all assignment/clearing forms; see _effective_identity_values).
    for env_name, expected_value in _expected_projection(binding).items():
        declared = _effective_identity_values(command, env_name)
        if declared is None:
            declared = [os.environ.get(env_name, "").strip()]
        offending = [value for value in declared if value != expected_value]
        if offending:
            deny(
                "Mastermind shared-placement guard: "
                f"{env_name} is a server-derived projection of the current "
                f"{EXECUTION_BINDING_SCHEMA}; this launch declares "
                f"{offending[0]!r} but the binding projects {expected_value!r}"
                + (
                    f" ({len(declared)} assignments of {env_name} in one "
                    "command; every one must equal the projection)"
                    if len(declared) > 1
                    else ""
                )
                + ". A child cannot re-root, re-parent or promote itself by "
                "changing the environment (unset/env -i/nested shells count)."
            )

    # Every paid launch in the command, positionally: an off-list wrapper
    # mode is refused (never ignored); every token must equal the reserved
    # pool_ref EXACTLY (no composite/segment acceptance); one binding covers
    # one attempt, so a second launch is an unaccounted descendant.
    reserved = str(binding.get("pool_ref") or "").strip().lower()
    for _, wrapper, token, known in launches:
        if not known:
            deny(
                "Mastermind shared-placement guard: unknown wrapper mode — "
                f"{wrapper} {token or '<missing>'!r} is not on the recognised "
                "paid-launch vocabulary, so it is treated as a paid launch the "
                "guard cannot attribute and refused."
            )
        if token != reserved:
            deny(
                "Mastermind shared-placement guard: provider substitution — "
                f"the current binding reserved pool_ref {reserved!r} but this "
                f"launch requests {token!r}. Launch tokens must equal the "
                "reserved pool exactly; a reservation cannot be re-pointed at "
                "a different provider after the fact. Re-claim through the "
                "placement authority."
            )
    if len(launches) > 1:
        deny(
            "Mastermind shared-placement guard: unaccounted descendant — "
            f"this command carries {len(launches)} paid launches "
            f"{[token for _, _, token, _ in launches]} but the current binding "
            "covers exactly one attempt. Every paid child must be admitted "
            "and claimed through the placement authority before launch."
        )


def guard_fabric_launch(command: str, raw_command: str | None = None) -> None:
    raw = command if raw_command is None else raw_command
    launches = list(FABRIC_LAUNCH_RE.finditer(command))
    armed = shared_placement_armed()
    # An off-list wrapper mode is still an observed launch (REVIEW_2329
    # M-4): under shared placement it is refused by the gate; otherwise it
    # gets the legacy identity checks instead of passing unchecked.
    invocations = _wrapper_invocations(raw if armed else command)
    if armed:
        canon = _canonical_command(raw)
        if _WRAPPER_RE.search(canon) and _SHELL_FEED_RE.search(canon):
            deny(
                "Mastermind shared-placement guard: unobservable launch — "
                "wrapper source fed to a shell launches without a visible "
                "wrapper invocation. Invoke the wrapper directly."
            )
        # REVIEW_2329 r3 B-1/M-A/M-B: interpreter one-liners, computed
        # command words, runtime-multiplexing shapes and nested-shell
        # eval/source never reach the wrapper scan, so they are refused
        # here — BEFORE the no-launch early return that used to let an
        # armed session launch with zero binding validation.
        _deny_structurally_unobservable(raw)
    if not launches and not invocations:
        return

    # WO-11: shared-placement sessions validate the broker-issued
    # ExecutionBinding against the owner's current lease BEFORE any other
    # launch check — on the common paid-launch path, engine-independent.
    # The armed gate judges the raw command, heredoc bodies included.
    if armed:
        validate_execution_binding(raw)

    inherited_root = os.environ.get("POOL_ORCHESTRATOR_ID", "").strip()
    assigned_roots = _command_assignments(command, "POOL_ORCHESTRATOR_ID")
    if inherited_root and any(root != inherited_root for root in assigned_roots):
        deny(
            "Mastermind Fabric root-budget guard: POOL_ORCHESTRATOR_ID may not "
            "be rebound inside an already-rooted provider session. Preserve the "
            "original root identity; a new chat/helper is not a fresh budget."
        )

    missing = [
        name
        for name in _FABRIC_IDENTITY_NAMES
        if not _command_or_environment_value(command, name)
    ]
    if missing:
        deny(
            "Mastermind Fabric root-budget guard: provider launch is missing "
            + ", ".join(missing)
            + ". Every Fabric launch (pool run/remote or direct approved wrapper) "
            "must preserve the existing root "
            "orchestrator identity, true parent run, and task class so fair-share, "
            "descendant accounting, and routing economics cannot be reset by a new "
            "chat or helper."
        )


def guard_bash(payload: dict[str, object], tool_input: dict[str, object]) -> None:
    if not is_project_scope(payload):
        return
    command = str(tool_input.get("command") or "")
    clean = strip_heredocs(command)
    guard_fabric_launch(clean, command)
    if "gh " not in clean:
        return

    background = tool_input.get("run_in_background") is True
    watches = list(CI_WATCH_RE.finditer(clean))

    for watch in watches:
        call = watch.group("call")
        interval = INTERVAL_RE.search(call)
        if not interval or int(interval.group(1)) < MIN_WATCH_INTERVAL_S:
            deny(
                "Mastermind CI wait guard: GitHub watcher cadence must be explicit and "
                f"at least {MIN_WATCH_INTERVAL_S}s; {RECOMMENDED_WATCH_INTERVAL_S}s is "
                "preferred. Keep exactly one watcher for the exact PR/head/run."
            )
        if not background:
            deny(
                "Mastermind CI wait guard: foreground GitHub watch would pin this "
                "orchestrator for the external CI window. Launch exactly one watcher "
                "with run_in_background=true, then immediately continue another "
                "independent authorized project lane. The watcher notification is the "
                "next CI observation; repair/merge/live-proof accountability stays local."
            )

    loop_poll = any(
        CI_READ_RE.search(body) and SLEEP_RE.search(body)
        for body in (match.group(1) for match in DO_DONE_RE.finditer(clean))
    )
    delayed_poll = bool(CI_READ_RE.search(clean) and SLEEP_RE.search(clean))
    if not background and (loop_poll or delayed_poll):
        deny(
            "Mastermind CI wait guard: do not emulate a watcher with a foreground "
            "CI status + sleep/poll loop at any cadence. Perform one bounded state "
            "read, bind one asynchronous watcher (or the repository merge sweeper), "
            "then continue independent project work."
        )

    if not background and not watches and not loop_poll and not delayed_poll:
        key = _poll_key(
            clean,
            str(payload.get("cwd") or os.getcwd()),
            _session_scope(payload),
        )
        if key:
            repeat = repeat_poll_reason(key)
            if repeat:
                deny(repeat)

    if background and (watches or loop_poll or delayed_poll):
        allow_context(
            "CI WATCHER ARMED ASYNC: this background task is the CI observation owner. "
            "Do not tail or poll it and do not spend a reasoning cycle waiting for it. "
            "Immediately start the next highest-value independent authorized project "
            "lane. Return only on completion/event, genuine red, merge/conflict, or "
            "watcher failure/staleness."
        )


def guard_native_child(tool_input: dict[str, object]) -> None:
    # WO-11: native Agent/Task delegations under shared placement must be
    # covered by the CURRENT binding exactly like paid launches (missing
    # binding / stale fence / unaccounted descendant refusals; there is no
    # launch token to compare on this path, so no substitution check).
    if shared_placement_armed():
        validate_execution_binding("")
    model = str(tool_input.get("model") or "").strip()
    prompt = str(tool_input.get("prompt") or "")
    model_family = family(model)

    if not model:
        deny(
            "Mastermind fabric-first routing: native Claude children may not inherit "
            "the parent/default model. Send routine child work through the canonical "
            "Executive/Subagent Fabric. Native exception: explicit Opus orchestration "
            "or read-only audit/review with a WHY OPUS reason."
        )
    if model_family in ("sonnet", "haiku"):
        deny(
            f"Mastermind fabric-first routing: native {model_family} children are not "
            "default worker lanes. Route bounded labor through Executive/Subagent Fabric."
        )
    if model_family == "fable":
        deny(
            "Mastermind fabric-first routing: do not spend a second Fable child. Keep "
            "principal judgment in the Fable parent and route bounded labor through Fabric."
        )
    if model_family != "opus":
        deny(
            "Mastermind fabric-first routing: unrecognized native child model. Routine "
            "work belongs on Executive/Subagent Fabric; only explicit Opus "
            "orchestration/audit is a native exception."
        )

    route_match = ROUTE_RE.search(prompt)
    if not route_match:
        deny(
            "Opus native child requires an explicit ROUTE: ORCHESTRATION or "
            "ROUTE: AUDIT/REVIEW line."
        )
    route = route_match.group(1).lower()
    if not WHY_RE.search(prompt):
        deny("Opus native child requires WHY OPUS: <specific reason of at least 20 characters>.")
    if route in ("audit", "review", "auditor") and not READ_ONLY_RE.search(prompt):
        deny(
            "Opus audit/review child must declare MODE: READ_ONLY (or SCOPE: READ_ONLY). "
            "Proof-bearing child mutations belong to the canonical Fabric path."
        )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return

    if tool == "Bash":
        guard_bash(payload, tool_input)
        return

    if tool in ("Agent", "Task") and is_project_scope(payload):
        guard_native_child(tool_input)


if __name__ == "__main__":
    main()
