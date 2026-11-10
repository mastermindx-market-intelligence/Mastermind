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
The gate judges command SHAPE with an ADMIT rule (r6/r7 — see ``r7_parse``
and ``r6_refusal_codes``): a command that names a paid-launch wrapper is
admitted only as ONE plain top-level launch (optionally behind a closed set
of transparent prefixes, redirections only trailing), one faithful
``bash -c '<plain launch>'``, or a pipeline of closed read forms; every other
shape naming a wrapper is refused with a typed ``R6_*`` code, read by a real
tokenizer (a tokenizer failure refuses). POSIX line continuations are joined,
never split. r7: the binding gate's launch census and identity values come
from that same parse (the lexer's argv and exact literal values), so every
admitted unit whose command word is a wrapper reaches the binding gate; the
text regexes remain only as a cross-check that must agree.
r12 (re-check #7): in an ARMED session scope is STRUCTURAL — a command
holding any shell construct (quoted or not), or naming a wrapper literally,
is judged by that same ADMIT rule; only construct-free, literally unnamed
text is out of scope (``r12_armed_in_scope``). The hidden-name scanner
(``r6_names_wrapper``) is a secondary, widening-only reading there and the
mechanism of the unarmed checks.
r13 (re-check #8): one construct is invisible on the raw bytes — a line
continuation THIS shell's quote removal assembles from adjacent quoted
pieces and an admitted nested ``-c`` interpreter then joins — so ``\⏎`` is
also read on the quote-deleted, backslash-preserving view
(``_r12_unquoted_view``) and the literal name check joins it there first;
the ``slot`` module check also reads flag-combined ``-Bmslot`` forms.
There is no independent signing authority — the binding is only an assignment
of opaque references, trusted exactly as far as it matches the owner's current
lease. The gate fences every lexically observed launch in the commands it is
shown through this provider hook; it does not claim to fence arbitrary processes.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
from pathlib import Path
import re
import signal
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


#: (r8: ``[^\S\n]*``, not ``\s*``: a newline is itself a command position,
#: so a gap spanning newlines also matches from the last one; ``\s*`` made
#: every newline of a newline run rescan the run — quadratic.)
CMD_POS = r"(?:^|[;&|\n(]|\b(?:do|then|else)\s)[^\S\n]*"
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
#: r7: no optional ``(?:[A-Za-z0-9_./-]+/)?`` path group in front of a wrapper
#: name. The lookbehind already admits a name right after ``/``; the group
#: only widened ``match.start()`` and made every scan QUADRATIC on long path
#: words (a 20 KB ``/a/a/…`` word took >10 s — longer than the hook timeout,
#: and a timed-out hook does not block the command).
FABRIC_LAUNCH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"pool\s+(?:run|remote)\b"
    r"|sub\.sh\s+" + _SUB_LAUNCH_MODE + r"\b"
    r"|remote_sub\.sh\s+\S+\s+"
    + _REMOTE_LAUNCH_MODE
    + r"\b"
    r"|slot\.py\s+"
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
#: Broker-issued binding generations the guard admits. v1.1 is the sparse
#: native-runtime extension (runtime_kind / operation_key / caller_namespace /
#: lease join) issued by claim_job for t3-native routes; its v1 fields and
#: the fence/identity law below are unchanged, so the gate validates the
#: same required shape for both labels. Anything else is refused.
EXECUTION_BINDING_SCHEMAS = (EXECUTION_BINDING_SCHEMA, "ExecutionBinding.v1.1")
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
    r"(?<![A-Za-z0-9_.-])"
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
#: (r8: ``[^\S\n]*`` after the separator, not ``\s*``: a newline is itself a
#: separator, so a match whose gap spans newlines also starts at the last one;
#: with ``\s*`` every newline of a newline run rescanned the whole run.)
_UNOBSERVABLE_ENV_RE = re.compile(
    r"(?:^|[;&|(`{\n]|\$\()[^\S\n]*(?:eval|source|\.)(?=\s)"
    r"|(?:^|[\s;&|(`{])(?:BASH_ENV|ENV)\+?="
    r"|(?:^|[\s;&|(`{])(?:export|declare|typeset|readonly|local)"
    r"(?:\s+-\S+)*\s+[A-Za-z0-9_]*\$"
    r"|(?:^|[\s;&|(`{])printf\s+-v\s*\$"
)
#: Wrapper names as bare words: the computed-launch refusals below fire only
#: when a wrapper token is present in the text (REVIEW_2329 r2 N-3). Computed
#: commands without wrapper tokens are the documented arbitrary-process limit.
_WRAPPER_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?:pool|sub\.sh|remote_sub\.sh|slot\.py)(?![A-Za-z0-9_.-])",
    re.I,
)
#: Loop bodies (for/while/until) execute their contents N times: one lexical
#: launch inside one is N paid children under one binding's single attempt
#: (REVIEW_2329 r2 N-2/C1).
#: (Spans are found by a linear scan over these keywords, not a lazy
#: ``do.*?done`` regex, which is quadratic on many unmatched ``do`` words.)
_LOOP_KEYWORD_RE = re.compile(r"\b(?:done|do)\b")
#: Batch executors that run their argument command once per input item
#: (REVIEW_2329 r2 N-2/C2-C3, find -exec).
_BATCH_EXECUTOR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?:xargs|parallel|find)\b[^;&|\n]*",
    re.I,
)

# --- r6 ADMIT rule (WO-11 r6; REVIEW_C_E_OPUS_20261109 A1 findings 1-4) -------
#
# r3-r5 refused SHAPES from deny lists over an open shell grammar, and every
# list had a gap: a runner in front of an interpreter (``env python3 -c``), a
# function body ending at its first separator (``f() if …; fi``), a nested
# shell flag other than exactly ``-c`` (``bash -lc``), ``builtin eval``,
# ``alias``/``hyperfine``/``entr``/zsh ``repeat``. r6 INVERTS the rule. Under
# shared placement a command whose text names a paid-launch wrapper is
# ADMITTED only when the whole line is exactly one of three closed forms, read
# by a real tokenizer (quote, escape and line-continuation aware, explicit
# operator detection; a tokenizer failure REFUSES):
#
#   LAUNCH     [identity assignment]* [transparent prefix]*
#              ( <wrapper> | python[3[.N]] <path>/slot.py ) <literal arg>*
#   NESTED     [identity assignment]* [transparent prefix]*
#              ( bash | sh ) -c '<body>'     where <body> is itself one LAUNCH
#   INSPECTOR  <inspector> <literal arg>* ( | <inspector> <literal arg>* )*
#
#   identity assignment  a literal POOL_ORCHESTRATOR_ID / POOL_PARENT_RUN_ID /
#                        POOL_TASK_CLASS (still held to the binding's
#                        projection by validate_execution_binding)
#   transparent prefix   env NAME=value… (no options; same identity names),
#                        nohup, nice [-n N], timeout DURATION, setsid, exec,
#                        command (no other options)
#
# plus plain file redirections (``<``, ``>``, ``>>``, ``>|``, ``>&``, ``<&``,
# ``&>``, ``&>>``) with literal targets, and NOTHING else on the line. Every
# other command that names a wrapper is REFUSED with typed ``R6_*`` codes. The
# interpreter/runner lists of r3-r5 are no longer load-bearing: an unlisted
# interpreter or runner is simply not one of the admitted forms.
#
# Out of scope — the documented arbitrary-process limit (REVIEW_2329 r2): a
# command that names no wrapper at all. "Names a wrapper" is widened cheaply
# and honestly beyond the literal name: ANSI-C quoted text is decoded
# (``$'\x70ool'``), and a word that glues a $-expansion, command substitution
# or glob/brace pattern to a partial wrapper name (``${p}ol``, ``$s.sh``,
# ``po?l``, ``{p,}ool``) counts as naming it. A word that is ENTIRELY computed
# (``$W``, ``$(cmd)``, ``*``) names nothing and stays out of scope.
#
# --- r7: the parse drives the binding gate (REVIEW2 A1 findings 1-6) ---------
#
# r6 admitted by the parse but CENSUSED by text regexes that expect the mode
# right after the wrapper (``pool run``), so ``pool </dev/null run grok``
# passed r6 and then found no launch: the gate's early return skipped the
# binding check entirely. r7 makes the parse the single source of truth:
#
#  * Grammar order is enforced, not just documented: LAUNCH is
#    ``ASSIGN* PREFIX* HEAD ARG* REDIR*`` — a redirection before the command
#    word or between arguments refuses (``R6_REDIRECTION``). The same order
#    holds for NESTED and for every read form.
#  * Every admitted unit whose command word is a wrapper (or python + slot.py,
#    including the body of a NESTED form) becomes an ``_R7Launch`` carrying
#    the lexer's argv and the EXACT literal value of every identity
#    assignment that reaches it (prefix, ``env`` argument, nested outer and
#    body). The gate never returns early for such a unit; it reads wrapper,
#    mode and token from that argv and refuses unless the r4 text view finds
#    exactly the same invocations (``validate_execution_binding``).
#  * Command words other than the wrapper must be spelled exactly (lowercase)
#    and be bare names or live directly in /bin or /usr/bin; any other path
#    may name a staged binary (``R6_HEAD_SPELLING``). Wrapper words and the
#    slot.py operand keep any path: what they run is the binding-checked
#    launch (staged-file limit documented in the ledger).
#  * Read forms are closed: the inspectors (``xxd`` dropped; ``tail``
#    without follow; grep without ugrep's filter/pager/config/query options;
#    ``file`` without compile) plus ``git commit -m|-F`` /
#    ``git log|show|diff|status|grep|add`` with per-subcommand option
#    allowlists, ``rg`` with an option allowlist (no --pre, -z, --hostname-bin)
#    and ``sed -n N[,M]p``. A read form writes only to /dev/null or a
#    duplicated descriptor.
#
# Shell model: the lexer models bash/POSIX word rules. The Bash tool on this
# host runs ``zsh -c``; the known divergences that matter are refused rather
# than modelled: zsh ``<N-M>`` numeric globs (bash reads a redirection), zsh
# ``>!``/``>>!`` clobber operators (bash reads a target named ``!…``), zsh
# ``=(…)`` process substitution and glob qualifiers (both need ``(``),
# ``&!``/``&|`` (list operators). bash-only ``$"…"`` and zsh-only ``${:-x}``
# are computed segments (refused) and are decoded for SCOPE so they cannot
# hide a wrapper name.

_R6_WRAPPER_BASENAMES = ("pool", "sub.sh", "remote_sub.sh", "slot.py")
#: (stem, extension) per wrapper basename: a glob must spell at least one
#: character of the STEM before it counts as naming the wrapper (``*.sh``
#: alone does not; ``s*.sh`` / ``p*`` / ``po?l`` do — r7 lowered this from
#: two). A glob in COMMAND-WORD position counts whenever it can match a
#: wrapper basename at all (``* run …``, ``???? run …``).
_R6_WRAPPER_STEMS = {
    "pool": ("pool", ""),
    "sub.sh": ("sub", ".sh"),
    "remote_sub.sh": ("remote_sub", ".sh"),
    "slot.py": ("slot", ".py"),
}
#: The only assignments a launch may carry (shell prefix or ``env`` argument).
_R6_ADMITTED_ASSIGNMENTS = frozenset(_FABRIC_IDENTITY_NAMES)
#: Assignment names that make a shell, interpreter or loader run code, change
#: how the wrapper word resolves, or rewrite the guard's own channel. Every
#: non-identity assignment is refused anyway; these get the explicit
#: "unobservable launch environment" wording.
_R6_ENVIRONMENT_INPUT_NAMES = frozenset({
    "BASH_ENV", "ENV", "ZDOTDIR", "PROMPT_COMMAND", "PS4", "SHELLOPTS",
    "BASHOPTS", "IFS", "PATH", "CDPATH", "FPATH", "HOME", "GLOBIGNORE",
    "POOL_EXECUTION_BINDING",
})
_R6_ENVIRONMENT_INPUT_PREFIXES = (
    "BASH_FUNC_", "LD_", "DYLD_", "PYTHON", "NODE_", "PERL", "RUBY",
    "MASTERMIND_",
)
_R6_TRANSPARENT_PREFIXES = frozenset({
    "env", "nohup", "nice", "timeout", "setsid", "exec", "command",
})
_R6_MAX_PREFIXES = 4
_R6_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_R6_NICENESS_RE = re.compile(r"^-?\d+$")
_R6_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?)=")
_R6_PYTHON_RE = re.compile(r"^python(?:3(?:\.\d+)?)?$")
#: Shells admitted for the NESTED form (``bash -c`` / ``sh -c``):
#: non-interactive, they read no startup file except BASH_ENV/ENV, which the
#: guard checks in the session environment.
_R6_NESTED_SHELLS = frozenset({"bash", "sh"})
#: Shells recognised only to give a precise refusal (zsh reads .zshenv —
#: ZDOTDIR — and fish config.fish before every ``-c`` body; others differ in
#: grammar).
_R6_OTHER_SHELLS = frozenset({
    "zsh", "dash", "ksh", "mksh", "yash", "ash", "posh", "rbash", "fish",
    "tcsh", "csh", "pwsh",
})
#: Read-only inspectors admitted in the INSPECTOR form: none of them executes
#: an argument. Narrower than ``_INSPECTORS``: ``less``/``more`` (shell
#: escapes, LESSOPEN) execute; r7 drops ``xxd`` (``xxd -r IN OUT`` writes
#: OUT). ``rg`` is admitted only through its option allowlist (below).
_R6_INSPECTORS = frozenset({
    "cat", "head", "tail", "grep", "egrep", "fgrep", "wc", "ls", "stat",
    "file", "diff", "cmp", "shasum", "sha1sum", "sha256sum", "md5",
    "md5sum", "nl", "od", "echo",
})
#: r7 closed read forms: the inspectors plus three (head, option-allowlist)
#: carve-outs (REVIEW2 over-refusal note): git, rg and ``sed -n N[,M]p``.
_R7_READ_HEADS = _R6_INSPECTORS | {"git", "rg", "sed"}
#: Read heads whose options can execute, write or never finish: an unquoted
#: glob argument whose expansion could START with ``-`` (a staged file named
#: ``--filter=…``) would become an option, so it is refused for these.
_R7_GLOB_SENSITIVE = frozenset({
    "grep", "egrep", "fgrep", "tail", "file", "git", "rg", "sed",
})
#: Directories a non-wrapper command word may name explicitly (root-owned,
#: SIP-protected on macOS); every other path may be a staged binary.
_R7_SYSTEM_BIN_DIRS = ("/bin", "/usr/bin")
#: Transparent prefixes that are shell builtins: bare names only.
_R7_BUILTIN_ONLY = frozenset({"exec", "command"})
_R7_OUTPUT_REDIRECTIONS = frozenset({">", ">>", ">|", "&>", "&>>", ">&"})
_R7_DESCRIPTOR_RE = re.compile(r"^(?:[0-9]+|-)$")
#: r8 (REVIEW3 A3 BLOCKER 1 + MAJOR): r7 widened scope with two regexes that
#: were QUADRATIC — ``_R7_PARAM_OPERATOR_RE`` (``${NAME[sub]op`` openings,
#: the subscript ``\[[^\]]*\]`` rescanned to the end from every ``${x[``) and
#: ``_R7_GLUED_OPTION_RE`` (a match could start at every ``-X`` inside a
#: ``-a/-a/…`` run and scan to its end). Both are replaced by linear scans
#: whose scope is AT LEAST as wide (the r7 regexes are kept in the test
#: module as the reference they are fuzzed against):
#:
#:  * ``_r8_dash_view``: after the first ``${`` in the text every ``-`` reads
#:    as a word boundary. r7 replaced each ``${NAME…op`` opening by a space;
#:    the only operator character that also blocks ``_WRAPPER_NAME_RE``'s
#:    lookbehind is ``-`` (``:-`` / ``-``), so a name visible to r7 is visible
#:    here. Wider than r7 on purpose: nested ``${${x}:-pool}`` (zsh) and
#:    nested subscripts ``${x[a[1]]:-pool}`` are in scope now.
#:  * ``_r8_glued_option``: the same language as the r7 glued-option regex,
#:    decided per ``[A-Za-z0-9_./-]+`` run in one pass.
_R8_NAME_AT_RE = re.compile(
    r"(?=(?:pool|sub\.sh|remote_sub\.sh|slot\.py)(?![A-Za-z0-9_.-]))", re.I
)
_R8_OPTION_RUN_RE = re.compile(r"[A-Za-z0-9_./-]+")
_R8_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")
_R8_ASCII_LETTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _r8_option_cluster(value: str, letters: str) -> bool:
    """True when ``value`` is ``-`` followed by ASCII letters only, one of
    them in ``letters`` (r7 used ``re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*")``,
    which backtracks QUADRATICALLY on ``-ccc…c!``: 4.7 s at 32 KB)."""
    if len(value) < 2 or value[0] != "-":
        return False
    cluster = value[1:]
    return (
        frozenset(cluster) <= _R8_ASCII_LETTERS
        and any(letter in cluster for letter in letters)
    )


def _r8_dash_view(plain: str) -> str:
    """``plain`` with every ``-`` after its first ``${`` read as a space
    (scope only; linear)."""
    opening = plain.find("${")
    if opening < 0:
        return plain
    return plain[:opening] + plain[opening:].replace("-", " ")


def _r8_glued_option(text: str) -> bool:
    """True when a wrapper name is glued to a short option (``git grep
    -O'pool run …'``, ``-Opool``, ``-O/x/pool``): exactly r7's
    ``(?<![A-Za-z0-9_.])-[A-Za-z](?:[A-Za-z0-9_./-]*/|[A-Za-z]*)NAME(?![A-Za-z0-9_.-])``,
    decided in ONE linear pass per ``[A-Za-z0-9_./-]+`` run (a match lies
    inside one run): an option start is a ``-`` + letter at the run start or
    after ``/`` or ``-``; form (a) needs a name right after a ``/`` at least
    three characters past the FIRST option start; form (b) needs a name
    inside the letter run that follows an option start's letter."""
    for run in _R8_OPTION_RUN_RE.finditer(text):
        word = run.group(0)
        if "-" not in word:
            continue
        names = [match.start() for match in _R8_NAME_AT_RE.finditer(word)]
        if not names:
            continue
        starts: list[int] = []
        position = word.find("-")
        while 0 <= position < len(word) - 1:
            if (position == 0 or word[position - 1] in "/-") and (
                word[position + 1] in _R8_ASCII_LETTERS
            ):
                starts.append(position)
            position = word.find("-", position + 1)
        if not starts:
            continue
        first = starts[0]
        if any(at >= first + 3 and word[at - 1] == "/" for at in names):
            return True  # form (a): -X…/NAME
        for start in starts:
            letters_end = _R8_LETTER_RUN_RE.match(word, start + 1).end()
            found = bisect.bisect_left(names, start + 2)
            if found < len(names) and names[found] < letters_end:
                return True  # form (b): -XletterNAME
    return False


#: Armed sessions refuse a Bash command longer than this outright: the
#: provider kills a hook after its 10 s timeout and a killed hook does not
#: block, so the gate must finish. Every armed-path scan is linear; this cap
#: bounds the constant (measured in the C5 ledger).
R7_MAX_ARMED_COMMAND_CHARS = 262144
#: Nesting depth of ``${…}``/``$(…)`` the scope check unwraps; deeper text is
#: in scope (and then refused as computed) instead of costing a pass per level.
_R7_MAX_SUBSTITUTION_DEPTH = 32
#: A run of plain literal word characters (read in one step: per-character
#: string appends made long words quadratic in the lexer).
_R7_LITERAL_RUN_RE = re.compile(r"[^\x00-\x20\x7f;&|<>()'\"\\`$]+")
#: zsh ``<N-M>`` numeric glob; bash reads ``<`` ``N-M`` ``>`` redirections.
_R7_ZSH_NUMERIC_GLOB_RE = re.compile(r"<[0-9]*-[0-9]*>")


def _r7_spec(
    short_flags: str = "", short_valued: str = "",
    long_flags: tuple = (), long_valued: tuple = (),
    short_optional: str = "", long_optional: tuple = (),
) -> tuple:
    """A closed option grammar: (short flags, short options taking a value,
    long flags, long options taking a value, short options taking an
    OPTIONAL attached value, long options taking an optional ``=value``).

    r8 (REVIEW3 A2): an optional-argument option (``-U[<n>]``,
    ``--unified[=<n>]``, ``--relative[=<path>]``, ``--pretty[=<fmt>]``,
    status ``-u[<mode>]`` / ``--untracked-files[=<mode>]``) NEVER consumes
    the next word — the tool does not either, so a "value" the grammar
    skipped (``git log -U --output=<file>``) was parsed by git as an
    option. Consumption may never exceed the tool's: when unsure, a word is
    judged as an option."""
    return _R7Spec(
        (frozenset(short_flags), frozenset(short_valued),
         frozenset(long_flags), frozenset(long_valued)),
        frozenset(short_optional), frozenset(long_optional),
    )


class _R7Spec(tuple):
    """The four r7 option sets (unpacks as before) plus r8's optional-value
    sets as attributes."""

    def __new__(cls, required: tuple, short_optional: frozenset,
                long_optional: frozenset) -> "_R7Spec":
        spec = super().__new__(cls, required)
        spec.short_optional = short_optional
        spec.long_optional = long_optional
        return spec


_R7_GIT_DIFF_LONG_FLAGS = (
    "--stat", "--shortstat", "--numstat", "--name-only", "--name-status",
    "--patch", "--no-patch", "--raw", "--color", "--no-color",
    "--no-ext-diff", "--no-textconv", "--ignore-all-space",
    "--ignore-space-change", "--word-diff", "--summary", "--check",
    "--find-renames", "--no-renames", "--full-index", "--compact-summary",
    "--patch-with-stat", "--abbrev",
)
_R7_GIT_DIFF_LONG_VALUED = (
    "--stat", "--color", "--word-diff", "--diff-filter", "--abbrev",
)
#: r8: optional-argument diff options (``=value`` only, never a next word).
_R7_GIT_DIFF_LONG_OPTIONAL = ("--unified", "--relative")
#: r8: git arguments refused WHEREVER they appear (option, value, after
#: ``--``): they write a file (``--output``), run a program (``--ext-diff``,
#: ``--textconv``) or a pager (``-O``/``--open-files-in-pager``). The option
#: grammars already omit them; this holds even where a word is read as a
#: value (REVIEW3 A2).
_R8_GIT_FORBIDDEN_PREFIXES = (
    "--output", "--ext-diff", "--textconv", "-O", "--open-files-in-pager",
)
_R7_GIT_LOG_LONG_FLAGS = (
    "--oneline", "--graph", "--decorate", "--no-decorate", "--all",
    "--reverse", "--no-merges", "--merges", "--first-parent", "--follow",
    "--abbrev-commit", "--date-order", "--topo-order", "--left-right",
    "--regexp-ignore-case", "--all-match", "--invert-grep",
    "--extended-regexp", "--fixed-strings", "--perl-regexp", "--source",
)
#: git subcommand -> closed option grammar. Exec/write-capable options are
#: absent on purpose (-O/--open-files-in-pager, --ext-diff, --textconv,
#: --output, --exec, -e/--edit, -p/--patch on add, -S/--gpg-sign, -c on
#: commit), as are every git global option except --no-pager (-c,
#: --config-env, --exec-path, -C, --git-dir, …) and every other subcommand
#: (bisect run, rebase --exec, submodule foreach, config, …).
_R7_GIT_SPECS = {
    "commit": _r7_spec(
        "aqsn", "mF",
        ("--all", "--quiet", "--signoff", "--amend", "--no-edit",
         "--allow-empty", "--no-verify"),
        ("--message", "--file"),
    ),
    "log": _r7_spec(
        "pusMRwbiEFPC0123456789", "nSGL",
        _R7_GIT_DIFF_LONG_FLAGS + _R7_GIT_LOG_LONG_FLAGS,
        _R7_GIT_DIFF_LONG_VALUED + (
            "--max-count", "--skip", "--since", "--after", "--until",
            "--before", "--author", "--committer", "--grep", "--date",
            "--decorate",
        ),
        "U", _R7_GIT_DIFF_LONG_OPTIONAL + ("--format", "--pretty"),
    ),
    "show": _r7_spec(
        "pusMRwb", "",
        _R7_GIT_DIFF_LONG_FLAGS + ("--oneline", "--abbrev-commit", "--no-notes"),
        _R7_GIT_DIFF_LONG_VALUED + ("--date",),
        "U", _R7_GIT_DIFF_LONG_OPTIONAL + ("--format", "--pretty"),
    ),
    "diff": _r7_spec(
        "pusMRwb", "",
        _R7_GIT_DIFF_LONG_FLAGS + (
            "--cached", "--staged", "--merge-base", "--exit-code", "--quiet",
            "--no-index", "--minimal", "--histogram", "--patience",
        ),
        _R7_GIT_DIFF_LONG_VALUED,
        "U", _R7_GIT_DIFF_LONG_OPTIONAL,
    ),
    "status": _r7_spec(
        "sbv", "",
        ("--short", "--branch", "--porcelain", "--long", "--verbose",
         "--ignored", "--no-renames", "--ahead-behind", "--no-ahead-behind",
         "--show-stash"),
        ("--porcelain", "--ignored"),
        "u", ("--untracked-files",),
    ),
    "grep": _r7_spec(
        "niIlLcwvEFGPhHoqarWpz", "eABCmf",
        ("--line-number", "--ignore-case", "--files-with-matches",
         "--name-only", "--files-without-match", "--count", "--word-regexp",
         "--invert-match", "--extended-regexp", "--fixed-strings",
         "--basic-regexp", "--perl-regexp", "--full-name", "--cached",
         "--untracked", "--no-index", "--exclude-standard",
         "--only-matching", "--quiet", "--all-match", "--and", "--or",
         "--not", "--break", "--heading", "--color", "--no-color", "--text",
         "--recursive", "--column", "--show-function", "--function-context",
         "--null"),
        ("--max-count", "--context", "--after-context", "--before-context",
         "--max-depth", "--color", "--threads"),
    ),
    "add": _r7_spec(
        "AunvfN", "",
        ("--all", "--update", "--dry-run", "--verbose", "--force",
         "--intent-to-add", "--ignore-errors", "--renormalize", "--sparse",
         "--ignore-removal", "--no-all"),
        (),
    ),
}
#: rg option allowlist: --pre/--pre-glob (run a command per file),
#: -z/--search-zip (spawn decompressors) and --hostname-bin (runs a binary)
#: are absent on purpose.
_R7_RG_SPEC = _r7_spec(
    "isSwxvlcoFnNHILUPuqp0ab.", "efgtTABCmMdjrE",
    ("--ignore-case", "--smart-case", "--case-sensitive", "--word-regexp",
     "--line-regexp", "--invert-match", "--files-with-matches",
     "--files-without-match", "--count", "--count-matches",
     "--only-matching", "--fixed-strings", "--line-number",
     "--no-line-number", "--with-filename", "--no-filename", "--hidden",
     "--no-ignore", "--no-ignore-vcs", "--no-ignore-parent",
     "--no-ignore-dot", "--follow", "--multiline", "--multiline-dotall",
     "--pcre2", "--files", "--heading", "--no-heading", "--json",
     "--vimgrep", "--column", "--quiet", "--stats", "--trim", "--text",
     "--byte-offset", "--null", "--no-messages", "--unrestricted",
     "--no-config", "--type-list", "--passthru", "--sort-files", "--crlf",
     "--binary", "--no-binary", "--pretty", "--one-file-system",
     "--glob-case-insensitive", "--line-buffered", "--block-buffered"),
    ("--regexp", "--file", "--glob", "--iglob", "--type", "--type-not",
     "--after-context", "--before-context", "--context", "--max-count",
     "--max-depth", "--max-columns", "--max-filesize", "--threads",
     "--replace", "--color", "--colors", "--sort", "--sortr", "--encoding",
     "--type-add", "--type-clear", "--path-separator", "--context-separator",
     "--engine"),
)
_R7_SED_SCRIPT_RE = re.compile(r"^[0-9]+(?:,[0-9]+)?p$")
#: grep in Claude sessions is a snapshot function to ugrep: its options that
#: run a filter/pager, read or save a config, or open the query UI.
_R7_UGREP_EXEC_PREFIXES = (
    "--filter", "--pager", "--save-config", "--config", "--view", "--query",
    "--index",
)
#: Reserved words in command position (bash, plus the zsh/csh loop words).
_R6_RESERVED_WORDS = frozenset({
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "select", "function", "time", "coproc",
    "repeat", "foreach", "end", "in", "!", "{", "}", "[[", "]]",
})
#: Builtins in command position that rewrite identity, aliases, functions,
#: traps or shell options for what runs next.
_R6_ENV_BUILTINS = frozenset({
    "eval", "source", ".", "alias", "unalias", "trap", "builtin", "enable",
    "declare", "typeset", "export", "readonly", "local", "set", "shopt",
    "unset", "hash", "let", "read", "mapfile", "readarray", "emulate",
    "setopt", "unsetopt", "autoload", "zmodload", "functions", "fc", "bind",
})
#: Operators, longest first.
_R6_OPERATORS = (
    ";;&", "<<<", "<<-", "&>>", ";;", ";&", "&&", "||", "|&", "<<", "<>",
    "<&", "<(", ">>", ">&", ">|", ">(", "&>", ";", "&", "|", "<", ">", "(",
    ")", "\n",
)
_R6_LIST_OPERATORS = frozenset({";", "&", "&&", "||", "\n", ";;", ";&", ";;&"})
_R6_PIPE_OPERATORS = frozenset({"|", "|&"})
_R6_REDIRECTIONS = frozenset({"<", ">", ">>", ">|", ">&", "<&", "&>", "&>>", "<>"})
_R6_ADMITTED_REDIRECTIONS = _R6_REDIRECTIONS - {"<>"}
#: Word segment kinds whose text is fixed at parse time.
_R6_LITERAL_SEGMENTS = frozenset({"lit", "sq", "dq", "esc"})
_R6_GLOB_CHARS = frozenset("*?[{}")
_R6_ANSI_SIMPLE_ESCAPES = {
    "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n",
    "r": "\r", "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?",
}
_R6_ANSI_C_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
#: r8 (REVIEW3 A3 BLOCKER 2): the ``$[…]`` alternative may not run across
#: another ``$[`` (r7's ``\$\[[^\]]*\]`` rescanned to the end of the text
#: from every ``$[`` when no ``]`` followed: quadratic). Nested arithmetic is
#: unwrapped innermost-first by the repeated passes, as ``${…}``/``$(…)`` are.
_R6_COMPUTED_RE = re.compile(
    r"\$\{[^{}]*\}|\$\([^()]*\)|`[^`]*`|\$\[(?:[^\]$]|\$(?!\[))*\]"
    r"|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]"
)
_R6_ROUGH_WORD_SPLIT_RE = re.compile(r"[\s;&|<>()\"'\\]+")
#: r9 (REVIEW4 F1): the rough split above treats ``"``, ``'`` and ``\`` as
#: word SEPARATORS, but the shell's quote removal JOINS adjacent quoted and
#: unquoted segments into one word (``${x:-p}"ool"`` runs ``pool``). The
#: joined reading deletes those characters first (``$"`` → ``"`` too: bash
#: locale quoting) and then splits only on blanks and operators.
_R9_QUOTE_CHARS_RE = re.compile(r"[\"'\\]")
_R9_JOINED_WORD_SPLIT_RE = re.compile(r"[\s;&|<>()]+")


def _r9_joined(text: str) -> str:
    """The text with every quote character and backslash deleted (shell
    quote removal: quotes delimit, they do not separate; a backslash only
    makes the next character literal). Linear: one replace, one sub."""
    return _R9_QUOTE_CHARS_RE.sub("", text.replace('$"', '"'))
#: Codes that only explain a refusal; on their own they admit.
_R6_ADVISORY_CODES = frozenset({"R6_DEFERRED_EXPANSION"})
_R6_CLAUSES = {
    "R6_TOKENIZE_FAILED": (
        "the line could not be tokenised ({detail}); an unreadable line is "
        "refused, never guessed"
    ),
    "R6_COMPOUND_LIST": (
        "it sequences, conditions or backgrounds several commands "
        "({detail}); another command on the line can repeat the launch "
        "(runtime-multiplexed), add an unaccounted descendant or change its "
        "environment first, but the current binding covers exactly one "
        "attempt"
    ),
    "R6_PIPELINE": (
        "it pipes into or out of a stage that is not a read-only inspector "
        "({detail}); that stage can run, repeat or feed program text the "
        "guard cannot attribute"
    ),
    "R6_GROUPING": (
        "it uses a subshell, function definition, array or ( … ) group "
        "({detail}) that can execute the launch more than once or later "
        "(runtime-multiplexed), but the current binding covers exactly one "
        "attempt"
    ),
    "R6_KEYWORD": (
        "the shell keyword {detail} (loop, conditional, case, select, coproc, "
        "time, repeat or {{ … }} group) can execute the launch more than once "
        "or later (runtime-multiplexed), but the current binding covers "
        "exactly one attempt"
    ),
    "R6_ENV_BUILTIN": (
        "unobservable launch environment — {detail} can rewrite POOL_* "
        "identity, aliases, functions, traps or shell options outside what "
        "this guard can check, or stage the launch to run again later"
    ),
    "R6_COMMAND_SUBSTITUTION": (
        "command substitution ({detail}) runs inside this very shell and can "
        "construct or hide a paid launch"
    ),
    "R6_PROCESS_SUBSTITUTION": (
        "process substitution ({detail}) runs a hidden command"
    ),
    "R6_HEREDOC": (
        "a here-document or here-string ({detail}) feeds text that the "
        "command may execute as a program"
    ),
    "R6_EXPANSION": (
        "the computed word {detail} decides at runtime what runs or what the "
        "wrapper receives; invoke the wrapper by its literal name with "
        "literal arguments"
    ),
    "R6_DEFERRED_EXPANSION": (
        "quoted text {detail} carries $-expansions another shell or program "
        "may evaluate later; invoke the wrapper by its literal name"
    ),
    "R6_GLOB_OR_BRACE": (
        "the unquoted glob/brace pattern {detail} in a launch word expands "
        "at runtime; pass literal arguments"
    ),
    "R6_ASSIGNMENT": (
        "{detail}; only literal POOL_ORCHESTRATOR_ID / POOL_PARENT_RUN_ID / "
        "POOL_TASK_CLASS assignments are admitted on a launch (each is then "
        "held to the binding's projection)"
    ),
    "R6_PREFIX_FORM": (
        "{detail} is outside the transparent prefix grammar (env "
        "NAME=value, nohup, nice [-n N], timeout DURATION, setsid, exec, "
        "command — no other options)"
    ),
    "R6_REDIRECTION": (
        "the redirection {detail} is not admitted (redirections go after the "
        "last argument; a read form writes only to /dev/null or a duplicated "
        "descriptor; no network or dot-path targets)"
    ),
    "R6_NOT_A_PLAIN_LAUNCH": (
        "the wrapper name appears, but not as the command word of a plain "
        "launch, and {detail} is not an admitted read form — it receives the "
        "name as data or program text it can execute any number of times or "
        "later (runtime-multiplexed), write somewhere or never finish, while "
        "the current binding covers exactly one attempt"
    ),
    "R6_NESTED_SHELL": (
        "a nested shell is admitted only as bash -c / sh -c '<one plain "
        "launch>' with exactly -c and nothing after the body — {detail}"
    ),
    "R6_HEAD_SPELLING": (
        "the command word {detail} is not spelled as the admitted command: "
        "prefixes, shells, python and read forms must be their exact "
        "lowercase bare name (or /bin/… or /usr/bin/…), because any other "
        "path or spelling may resolve to a staged binary"
    ),
}
_R6_REMEDY = (
    "Run the paid launch as a plain command: the wrapper (or python3 "
    "…/slot.py) as the command word, optionally behind env NAME=value / "
    "nohup / nice -n N / timeout DURATION / setsid / exec / command, with "
    "literal arguments, redirections only at the end and nothing else on the "
    "line (or bash -c '<that one launch>')."
)
_R7_READ_REMEDY = (
    "Not launching? Drop the bare wrapper name from the command text, or use "
    "an admitted read form: cat/head/tail/grep/egrep/fgrep/wc/ls/stat/file/"
    "diff/cmp/shasum/sha1sum/sha256sum/md5/md5sum/nl/od/echo, git commit "
    "-m|-F, git log|show|diff|status|grep|add (allowlisted options, no git "
    "global option but --no-pager), rg (allowlisted options; no --pre, -z, "
    "--hostname-bin) or sed -n N[,M]p — piped only into each other, writing "
    "only to /dev/null."
)


_R8_OCTAL_RE = re.compile(r"[0-7]{1,3}")
_R8_HEX_RES = {
    escape: re.compile(rf"[0-9A-Fa-f]{{1,{width}}}")
    for escape, width in (("x", 2), ("u", 4), ("U", 8))
}


def _r6_decode_ansi_c(body: str) -> str:
    """Decode the body of a bash ``$'…'`` word (escape set of bash 5)."""
    out: list[str] = []
    index = 0
    length = len(body)
    while index < length:
        char = body[index]
        if char != "\\" or index + 1 >= length:
            out.append(char)
            index += 1
            continue
        escape = body[index + 1]
        if escape in _R6_ANSI_SIMPLE_ESCAPES:
            out.append(_R6_ANSI_SIMPLE_ESCAPES[escape])
            index += 2
            continue
        if escape in "01234567":
            # r8: match at a position, never on a slice of the rest of the
            # body (one copy per escape made ``$'\1\1…'`` quadratic).
            digits = _R8_OCTAL_RE.match(body, index + 1).group(0)
            out.append(chr(int(digits, 8) & 0xFF))
            index += 1 + len(digits)
            continue
        if escape in "xuU":
            digits_match = _R8_HEX_RES[escape].match(body, index + 2)
            if digits_match:
                digits = digits_match.group(0)
                try:
                    out.append(chr(int(digits, 16)))
                except (ValueError, OverflowError):
                    out.append("�")
                index += 2 + len(digits)
                continue
        if escape == "c" and index + 2 < length:
            out.append(chr(ord(body[index + 2]) & 0x1F))
            index += 3
            continue
        out.append(char + escape)
        index += 2
    return "".join(out)


def _r7_parts_match(name: str, parts: list[str]) -> bool:
    """``name`` fullmatches ``parts[0] .* parts[1] .* … parts[-1]`` (literal
    parts): greedy leftmost, linear — no regex backtracking."""
    first, last = parts[0], parts[-1]
    if not name.startswith(first):
        return False
    position = len(first)
    for part in parts[1:-1]:
        found = name.find(part, position)
        if found < 0:
            return False
        position = found + len(part)
    return len(name) - len(last) >= position and name.endswith(last)


_R8_GLOB_STAR = object()
_R8_GLOB_ANY = object()
_R8_WRAPPER_ALPHABET = frozenset("".join(_R6_WRAPPER_BASENAMES))
_R8_WRAPPER_NAME_LIMIT = max(len(name) for name in _R6_WRAPPER_BASENAMES)


def _r8_set_members(body: str, alphabet: frozenset) -> frozenset:
    """The characters of ``alphabet`` a ``[body]`` set names (fnmatch
    semantics: ``a-z`` ranges, a ``-`` first/last is literal); one pass."""
    if "-" not in body:
        return alphabet & frozenset(body)
    members: set[str] = set()
    index = 0
    length = len(body)
    while index < length:
        if index + 2 < length and body[index + 1] == "-":
            low, high = body[index], body[index + 2]
            members.update(char for char in alphabet if low <= char <= high)
            index += 3
        else:
            if body[index] in alphabet:
                members.add(body[index])
            index += 1
    return frozenset(members)


def _r8_glob_atoms(
    pattern: str, alphabet: frozenset, limit: int
) -> tuple[list, int] | None:
    """``(atoms, fixed-atom count)`` of an fnmatch pattern, each fixed atom
    reduced to the set of ``alphabet`` characters it admits (``?`` →
    ``_R8_GLOB_ANY``, runs of ``*`` → one ``_R8_GLOB_STAR``); None once the
    pattern has more than ``limit`` fixed atoms (nothing of length ≤ limit
    can match). r8: reading stops there, so a ``[[[…`` run costs at most
    ``limit + 1`` searches for ``]`` (r7 searched once per ``[``: quadratic,
    7 s at 256 KB), and a set body is read once, not once per position."""
    atoms: list = []
    fixed = 0
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if not atoms or atoms[-1] is not _R8_GLOB_STAR:
                atoms.append(_R8_GLOB_STAR)
            index += 1
            continue
        fixed += 1
        if fixed > limit:
            return None
        if char == "?":
            atoms.append(_R8_GLOB_ANY)
            index += 1
            continue
        if char == "[":
            body_at = index + 1
            if body_at < length and pattern[body_at] in "!^":
                body_at += 1
            if body_at < length and pattern[body_at] == "]":
                body_at += 1
            close = pattern.find("]", body_at)
            if close >= 0:
                body = pattern[index + 1:close]
                negate = body[:1] in ("!", "^")
                members = _r8_set_members(body[1:] if negate else body, alphabet)
                atoms.append(alphabet - members if negate else members)
                index = close + 1
                continue
        atoms.append(frozenset((char,)))
        index += 1
    return atoms, fixed


_R8_GLOB_CACHE: dict[str, tuple[list, int] | None] = {}


def _r7_glob_match(name: str, pattern: str) -> bool:
    """fnmatch-style ``*``/``?``/``[set]`` matching by a position-set walk.
    r7 replaced ``fnmatch`` here: its regex translation backtracks
    catastrophically on patterns like ``*?*?*?…`` (a slow hook is killed and
    does not block). r8: the pattern is read by ``_r8_glob_atoms`` — linear,
    bounded by the name length, once per pattern for all wrapper names."""
    if len(name) <= _R8_WRAPPER_NAME_LIMIT and frozenset(name) <= _R8_WRAPPER_ALPHABET:
        if pattern not in _R8_GLOB_CACHE:
            if len(_R8_GLOB_CACHE) > 64:
                _R8_GLOB_CACHE.clear()
            _R8_GLOB_CACHE[pattern] = _r8_glob_atoms(
                pattern, _R8_WRAPPER_ALPHABET, _R8_WRAPPER_NAME_LIMIT
            )
        parsed = _R8_GLOB_CACHE[pattern]
    else:
        parsed = _r8_glob_atoms(pattern, frozenset(name), len(name))
    if parsed is None:
        return False
    atoms, fixed = parsed
    if fixed > len(name):
        return False
    positions = {0}
    for atom in atoms:
        if atom is _R8_GLOB_STAR:
            positions = set(range(min(positions), len(name) + 1))
            continue
        positions = {
            position + 1 for position in positions
            if position < len(name)
            and (atom is _R8_GLOB_ANY or name[position] in atom)
        }
        if not positions:
            return False
    return len(name) in positions


def _r6_partial_wrapper(base: str) -> bool:
    """True when a word's basename, with computed parts (``\\x00``) or glob
    and brace patterns as wildcards, can spell a wrapper basename."""
    lowered = base.lower()
    if "\x00" in lowered:
        if not lowered.replace("\x00", ""):
            return False  # entirely computed: names nothing (r2 limit)
        parts = re.sub("\x00+", "\x00", lowered).split("\x00")
        return any(_r7_parts_match(name, parts) for name in _R6_WRAPPER_BASENAMES)
    if not any(char in lowered for char in "*?[{"):
        return False
    pattern = re.sub(r"\{[^{}]*\}", "*", lowered)
    for name in _R6_WRAPPER_BASENAMES:
        stem, extension = _R6_WRAPPER_STEMS[name]
        if not _r7_glob_match(name, pattern):
            continue
        stem_pattern = (
            pattern[:-len(extension)]
            if extension and pattern.endswith(extension) else pattern
        )
        literal = re.sub(r"\[[^\]]*\]|[*?{}\[\]]", "", stem_pattern)
        if len(literal) >= 1:
            return True
    return False


_R8_CLOSER = {"(": ")", "[": "]", "{": "}"}
_R8_PARAM_HEAD_RE = re.compile(
    r"(?:\([^()]*\))?[#!]?(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])?"
)
_R8_CHUNK_RE = re.compile(r"[a-z0-9_.]+")
_R8_DOLLAR_WORD_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])")


_R8_BRACKET_RE = re.compile(r"\$[(\[{]|[`()\[\]{}]")
#: Construct nesting the scope reader descends into; deeper text is in scope
#: (and then refused as computed) — r7 stopped at 32 regex passes.
#: r9 (REVIEW4 depth note), stated exactly: the reader recurses into a body
#: only when it holds a ``$``/backtick, so a chain of k nested constructs is
#: read down to reader depth k-1; the cap fires at reader depth 9, i.e. an
#: honest ``echo $(echo $(… echo hi))`` chain is in scope from k = 10 nested
#: constructs on (k ≤ 9 stays out). Pinned by
#: ``test_r9_construct_depth_boundary_is_ten_nested_constructs``.
_R8_MAX_CONSTRUCT_DEPTH = 8


def _r8_construct_spans(text: str) -> list[tuple[int, int, int]]:
    """Maximal closed ``$(…)``/``$((…))``/``$[…]``/``${…}``/backtick spans
    ``(start, end, opener length)``, found by ONE bracket-stack pass over the
    bracket characters only (rough, quote-unaware like r7's regex passes; a
    closer that does not match the innermost opener is text)."""
    stack: list[tuple[str, int, int]] = []
    closed: list[tuple[int, int, int]] = []
    for match in _R8_BRACKET_RE.finditer(text):
        token = match.group(0)
        index = match.start()
        if token[0] == "$":
            stack.append((_R8_CLOSER[token[1]], index, 2))
        elif token == "`":
            if stack and stack[-1][0] == "`":
                closed.append((stack.pop()[1], index + 1, 1))
            else:
                stack.append(("`", index, 1))
        elif stack:
            if token in "([{":
                stack.append((_R8_CLOSER[token], index, 0))
            elif stack[-1][0] == token:
                _, start, opener = stack.pop()
                if opener:
                    closed.append((start, index + 1, opener))
    closed.sort(key=lambda span: (span[0], -span[1]))
    maximal: list[tuple[int, int, int]] = []
    for span in closed:
        if maximal and span[0] < maximal[-1][1]:
            continue  # nested in the previous maximal span
        maximal.append(span)
    return maximal


_R8_PARAM_OP_RE = re.compile(r"(?:\[[^\]]*\])?(:?[-=?+]|/[/#%]?|##?|%%?|\^\^?|,,?|:)?")


def _r8_operator_word(word: str) -> list:
    """Items of a ``${x op WORD}`` operator word as the shell yields it: a
    plain literal word is one mandatory literal; a word with quotes removed
    that still carries ``$``/backtick/blank is read loosely (its literal
    chunks optional, glued to runtime text)."""
    plain_word = re.sub(r"[\"'\\]", "", word).lower()
    if not plain_word:
        return []
    if "$" in plain_word or "`" in plain_word or _R6_ROUGH_WORD_SPLIT_RE.search(plain_word):
        return (
            [("any", "")]
            + [("opt", chunk) for chunk in _R8_CHUNK_RE.findall(plain_word)]
            + [("any", "")]
        )
    return [("lit", plain_word)]


def _r8_construct_items(construct: str) -> list:
    """Scope items of one construct. Arithmetic and command substitution
    print runtime text (``any`` — zsh ``$[[##36]24]`` prints ``O``). A
    parameter expansion is its runtime value, except: ``${x[:]-|=|? WORD}``
    is the value OR the literal WORD and ``${x[:]+WORD}`` is WORD or
    nothing (an ``alt`` item); a form with no operator after the name
    (zsh ``${${x}:-pool}``) glues its literal chunks, optional, to the
    value."""
    if not construct.startswith("${"):
        return [("any", "")]
    body = construct[2:-1]
    head = _R8_PARAM_HEAD_RE.match(body).end()
    if head == len(body):
        return [("any", "")]  # a plain reference names nothing literal
    op = _R8_PARAM_OP_RE.match(body, head)
    operator, word = op.group(1) or "", body[op.end():]
    if not operator and op.end() == len(body):
        return [("any", "")]  # ``${a[i]}``: a subscripted plain reference
    if operator in ("-", ":-", "=", ":=", "?", ":?"):
        return [("alt", ([("any", "")], _r8_operator_word(word)))]
    if operator in ("+", ":+"):
        return [("alt", ([], _r8_operator_word(word)))]
    if operator:
        # /pat/repl, #, %, ^, ",", :offset — a transformed RUNTIME value: a
        # replacement appears only where the value matches (r7 parity; a
        # whole wrapper name in it is still seen by the name scan).
        return [("any", "")]
    # No operator after the name (zsh nested ``${${x}…}``, odd forms): the
    # literal chunks are optional, glued to the runtime value.
    chunks = _R8_CHUNK_RE.findall(re.sub(r"[\"'\\]", "", body[head:]).lower())
    return [("any", "")] + [("opt", chunk) for chunk in chunks] + [("any", "")]


def _r8_items_spell(items: list, name: str) -> bool:
    """True when the item sequence can produce exactly ``name`` as the
    basename of the word, using at least ONE fixed literal character (a
    wholly computed word names nothing: the arbitrary-process limit).
    Position-set DP (≤ len(name)+1 states), linear in the items. A ``/`` in
    a literal starts the basename over (r7's rsplit on literal ``/``)."""
    size = len(name)

    def step(state: tuple, item: tuple) -> tuple:
        free, fixed = state
        kind, payload = item
        if kind == "any":
            return (
                set(range(min(free), size + 1)) if free else set(),
                set(range(min(fixed), size + 1)) if fixed else set(),
            )
        if kind == "alt":
            result_free: set[int] = set()
            result_fixed: set[int] = set()
            for branch in payload:
                branch_state = (set(free), set(fixed))
                for sub in branch:
                    branch_state = step(branch_state, sub)
                result_free |= branch_state[0]
                result_fixed |= branch_state[1]
            return result_free, result_fixed
        text = payload
        if kind == "lit" and "/" in text:
            free, fixed, text = {0}, set(), text.rsplit("/", 1)[1]
            if not text:
                return free, fixed
        grown = {
            position + len(text) for position in free | fixed
            if name.startswith(text, position)
        }
        if kind == "lit":
            return set(), grown
        return free, fixed | grown

    state: tuple = ({0}, set())
    for item in items:
        state = step(state, item)
        if not state[0] and not state[1]:
            return False
    return size in state[1]


def _r8_computed_glue(text: str, depth: int = 0) -> bool:
    """r8 scope widening (closes r7 escapes, found while making r7 linear):
    a rough word that glues literal text to ``$``-constructs names a wrapper
    when SOME value of the constructs completes the name — read with real
    bracket nesting (r7's innermost-first regex never unwrapped
    ``$((…))``), with ``${…op WORD}`` operator words as optional literals,
    and INSIDE every construct body too (``echo $(p${x}ool run …)`` runs
    that launch). Linear per level: one stack pass, one item walk, a
    ≤14-state DP; levels are disjoint and capped (deeper → in scope)."""
    if depth > _R8_MAX_CONSTRUCT_DEPTH:
        return True  # nested beyond any honest command: judge it (fail closed)
    spans = _r8_construct_spans(text)
    for start, end, opener in spans:
        inner = text[start + opener:end - 1]
        if ("$" in inner or "`" in inner) and _r8_computed_glue(inner, depth + 1):
            return True  # (a body without $ or ` has no construct to glue)
    words: list[list[tuple[str, str]]] = [[]]

    def literal(piece: str) -> None:
        parts = _R6_ROUGH_WORD_SPLIT_RE.split(piece)
        for number, part in enumerate(parts):
            if number:
                words.append([])
            if part:
                words[-1].append(("lit", part.lower()))

    def plain(segment: str) -> None:
        position = 0
        for match in _R8_DOLLAR_WORD_RE.finditer(segment):
            literal(segment[position:match.start()])
            words[-1].append(("any", ""))
            position = match.end()
        literal(segment[position:])

    position = 0
    for start, end, _ in spans:
        plain(text[position:start])
        words[-1].extend(_r8_construct_items(text[start:end]))
        position = end
    plain(text[position:])
    for items in words:
        if all(kind == "lit" for kind, _ in items):
            continue  # literal and glob words: the other scope checks
        compact: list = []
        for item in items:
            if not (item[0] == "any" and compact and compact[-1][0] == "any"):
                compact.append(item)
        if all(kind == "any" for kind, _ in compact):
            continue  # wholly computed: names nothing (arbitrary-process limit)
        if any(_r8_items_spell(compact, name) for name in _R6_WRAPPER_BASENAMES):
            return True
    return False


def _r7_glob_head_names_wrapper(text: str) -> bool:
    """True when a unit's COMMAND WORD (after assignments and transparent
    prefixes) is an unquoted glob/brace pattern that can match a wrapper
    basename (``* run …``, ``p* run …``): the shell resolves it from the
    current directory, so it may BE the wrapper. An unreadable line is left
    to the other scope checks."""
    tokens, error = _r6_lex(text)
    if error:
        return False
    units: list[list[_R6Word]] = [[]]
    pending = False
    for kind, item in tokens:
        if kind == "word":
            if pending:
                pending = False
            else:
                units[-1].append(item)
            continue
        if kind == "op":
            operator = str(item)
            if operator in _R6_REDIRECTIONS or operator == "<<<":
                pending = True
                continue
            units.append([])
    for words in units:
        index = 0
        while index < len(words) and _R6_ASSIGNMENT_RE.match(
            words[index].leading_unquoted()
        ):
            index += 1
        while index < len(words):
            base = _r7_command_name(words[index])[0].lower()
            if base not in _R6_TRANSPARENT_PREFIXES:
                break
            index = _r6_prefix(base, words, index + 1, [], [])
        if index < len(words) and words[index].has_glob():
            pattern = re.sub(
                r"\{[^{}]*\}", "*", words[index].value.rsplit("/", 1)[-1].lower()
            )
            if any(_r7_glob_match(name, pattern) for name in _R6_WRAPPER_BASENAMES):
                return True
    return False


# --- r10: the lexer reading (REVIEW5 N1 MAJOR) -------------------------------
#
# Every earlier reading finds construct extents with a quote-UNAWARE bracket
# matcher (``_r8_construct_spans``) or regex (``_R6_COMPUTED_RE``), so a
# quoted, escaped or commented bracket inside a construct
# (``$(: "("; printf p)ool``, ``$(: \(; …)``, ``$(printf p # (⏎)ool``,
# ``${x:-p${y#"}"}}ool``) throws the extent off and the glued word is never
# read. r10 adds a reading driven by a quote-aware shell scanner — dedicated
# to SCOPE and not shared with ``_r7_parse`` (whose refusals must not move):
# like ``_r6_lex`` it reads quotes, escapes, ``$'…'``/``$"…"`` and every
# ``$``-construct with real nesting, and it ALSO reads what ``_r6_lex`` cannot
# (an ``_r6_lex``-only reading measured both an escape and a regression):
#
# * comments (a ``#`` at a word start, also inside ``$(…)``);
# * here-documents at every level, ``<<``/``<<-``, quoted or not, including
#   inside ``$(…)`` (``git commit -m "$(cat <<'EOF' … don't … EOF)"`` —
#   ``_r6_lex`` fails on the apostrophe, so "lex failure → in scope" would
#   refuse every such armed commit); bodies are read as script AND, when the
#   delimiter is unquoted, for the expansions the shell performs in them;
# * a ``case`` command inside ``$(…)``/``<(…)`` — its pattern ``)`` does not
#   close the substitution (zsh runs ``$(case x in x) printf p;; esac)ool``)
#   — is not modelled: FAIL CLOSED;
# * ``${…}`` extents the shells disagree on: bash 3.2 ends ``${x:-{}`` at
#   the first ``}`` (``x=p; ${x:-{}ool`` runs ``pool``), zsh counts braces —
#   FAIL CLOSED unless the two ends differ only by ``}`` characters
#   (``${{ github.token }}``, ``${CONFIG:-{}}``: same continuation); and a
#   ``'`` inside ``"${…}"`` (bash 3.2: a quote; zsh: literal) — FAIL CLOSED.
#
# Each word becomes items for the r8 spelling DP: literal text (unquoted,
# quoted, escaped, decoded ``$'…'``) → ``lit``; ``${…}`` → r8's construct
# items; ``$name``, ``$(…)``, ``$((…))``, ``$[…]``, backticks, ``<(…)`` →
# ``any``. Construct bodies are read recursively; so is every literal run of
# a word that holds ``$`` or a backtick (``bash -c '…'``, ``eval "…"``, a
# backslash-escaped ``\$(…)``) — that text is a script if a shell gets it.
#
# Outcomes: a word that can spell a wrapper → in scope. An unterminated
# ``$(``/``<(`` (the reviewer's "lex failure → in scope" rule, kept for the
# constructs), nesting deeper than the cap, a ``case`` in a substitution, a
# brace/quote disagreement, or more than ``_R10_MAX_RESYNCS`` unterminated
# quotes → in scope (fail closed). An unterminated QUOTE or backtick is a
# syntax error the shell refuses too (zsh refuses the whole ``-c`` text; bash
# has already run the earlier lines, which this reading has already read):
# the reading resynchronises one character after the opening quote and reads
# the rest as script — never narrower than the shell. A ``${``/``$[`` with no
# ``}``/``]`` anywhere after it is read as literal text (both shells refuse
# it). Text without ``$`` or a backtick cannot compute a word (glob and brace
# patterns are the partial reader's): the reading returns at once.
#
# Cost: one scan per text; a body or literal run is re-read at most once per
# nesting level (cap ``_R10_MAX_DEPTH``) and each text at most
# ``_R10_MAX_RESYNCS`` + 1 times; delimiters are found with a C-level regex.

#: Construct nesting the r10 reading descends into (a ``$(…)`` chain of k
#: constructs reaches depth k); deeper is in scope. Matches r9's boundary:
#: k ≤ 9 out, k ≥ 10 in (``test_r9_construct_depth_boundary_…``).
_R10_MAX_DEPTH = 9
#: Unterminated quotes per text before the reading gives up (fail closed).
_R10_MAX_RESYNCS = 4
_R10_PLAIN_RE = re.compile(r"[^ \t\n;&|<>()'\"\\`$]+")
_R10_BLANKS_RE = re.compile(r"[ \t]+")
_R10_DQ_PLAIN_RE = re.compile(r'[^"\\`$]+')
_R10_BRACE_PLAIN_RE = re.compile(r"[^{}'\"\\`$]+")
_R10_BRACKET_PLAIN_RE = re.compile(r"[^\[\]'\"\\`$]+")
_R10_EXPAND_RE = re.compile(r"[\\`$]")
_R10_BACKTICK_BODY_RE = re.compile(r"(?:[^`\\]|\\.)*`", re.S)
_R10_ANSI_BODY_RE = re.compile(r"(?:[^'\\]|\\.)*'", re.S)
_R10_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_R10_DELIMITER_RUN_RE = re.compile(r"[^ \t\n;&|<>()'\"\\]+")
#: Words after which the next word is still in command position.
_R10_KEEP_COMMAND_POSITION = frozenset({
    "!", "{", "do", "elif", "else", "if", "then", "time", "until", "while",
    "coproc",  # r12 (re-check #7 F1): ``coproc`` runs the command after it
})
#: r12 (re-check #7 F1): a word glued to ``<``/``>`` that is an fd number
#: or a zsh ``{name}`` is part of the redirection, not the command word
#: (``2>/dev/null case x in …`` — zsh runs the ``case``).
_R12_FD_WORD_RE = re.compile(r"[0-9]+|\{[a-z_][a-z0-9_]*\}")

# --- r11 (REVIEW6 N5/N6/N7) additions to the r10 reading ---------------------
#
# N5 — arithmetic. Inside ``$((…))``, a ``((…))`` command and ``for ((…))``
# neither bash 3.2 nor zsh reads ``#`` as a comment or ``<<`` as a
# here-document (measured: ``echo $(( 1 # 2⏎)) after`` → "operator expected
# at `# 2`" in both; ``echo $(( 1 << 2 ))⏎2`` prints 4 then runs ``2``);
# r10 read the text as a subshell, so ``(( 1 # $($(…)ool …) ))`` was a
# comment and ``(( y = 1 << 2 ))`` opened a here-document. r11 reads an
# ARITHMETIC CONTEXT (``_R10Text.arith``): ``#`` and ``<<`` are literal,
# parentheses nest, constructs are read (their bodies as script) and the
# words between them are still judged (an over-read: a shell that falls
# back to a subshell would run them). Fail closed (in scope) where the two
# shells' readings can part: a quote at the arithmetic level (zsh ignores
# quotes for the extent, bash honours them: ``$(( ")" ))``) — except a
# double-quoted span holding none of ``( ) { } ' ` \`` (``(( "$n" > 3 ))``,
# the same extent in both); ``$'``/``$"``;
# a quote inside a ``${…}`` there; a ``)`` closing the context that is not
# ``))`` (both shells fall back to a subshell/command substitution, by
# different rules); an unterminated context; a ``#`` at a word start (after
# a blank, newline or operator character) whose rest of line holds
# ``( ) ' " ` $ \`` (a shell reading it as a comment could end the context
# elsewhere; ``16#ff``, zsh ``[##36]`` are not word starts). Only a ``((``
# in command position (not glued, not inside an uncertain group, see N8)
# or after ``for`` is read this way; ``$((`` always is.
#
# N6 — ``${…}``. Inside double quotes BOTH shells end ``${`` at the FIRST
# ``}`` (measured: ``"[${x:-{}]"`` and ``"[${x:-{a}b}]"`` print ``[{]`` and
# ``[{ab}]`` in both); r10 counted braces there. Unquoted, bash ends at the
# first ``}`` and zsh counts: once bash's end is passed, any character but
# ``}`` fails closed at once (r10 read on and an unterminated quote there
# raised a resync that DROPPED the word). An unterminated quote/backtick
# inside any construct (``${…}``, ``$[…]``, ``$(…)``, ``$((…))``, ``<(…)``)
# is in scope (``_R10Fail``), never a silent resync.
#
# N7 — words as deferred script. A word is judged whole (r10) AND in
# FRAGMENTS: its literal parts split at blanks/newlines/operators (once as
# written, once with quotes and backslashes deleted), each fragment run
# through the r8 spelling DP — ``eval "$(…)ool run …"`` /
# ``bash -c "$(…)ool …"`` is the script ``<value>ool run …``. The deferred
# re-reading of a word holding a quoted ``$``/backtick now reads the WHOLE
# word once, a placeholder standing for each computed part (read as a
# computed item wherever it lands), instead of literal runs cut at each
# computed part (``"x=\$(cat ${F}); echo \$x"`` left ``x=$(cat `` open —
# an availability refusal — and a cut run never saw a construct glued to
# the literal text after it).
#
# N8 (found by Director C10) — parentheses that are not a subshell. zsh
# reads a ``(`` in argument position, glued to a word (also a here-document
# delimiter word), in a case pattern or as a redirection target as a GLOB
# GROUP: ``#`` is literal there, blanks and newlines do not end it, every
# construct in it runs, and ``;``/``&``/``<``/``>`` end the WORD, dropping
# the open group (measured: ``echo (1 # $(…))``, ``echo a(1 # $(…))``,
# ``case x in (x # $(…)) …``, ``for x in (a # $(…))``, ``: > (x # $(…))``,
# ``noglob (x # $(…)⏎)``; ``$(: a( "(" & printf p)`` ends at the ``)``);
# zsh AND bash read ``[[ a =~ (a # $(…)) ]]`` the same way. r10 read every
# ``(`` as a subshell, so the ``#`` hid the rest of the line. r11 keeps the
# subshell reading only for a ``(`` that is surely one: command position,
# not glued (no word in progress and no word character just before), not
# a redirection target, not inside ``[[ … ]]``, not inside such a group.
# Every other ``(`` opens an UNCERTAIN group, where a word-start ``#`` is
# read BOTH ways: the rest of the line is read on its own as script with
# every ``#`` in it literal, then skipped as the comment it is in a
# subshell. When that skipped region holds a paren, quote or backtick (zsh
# counts it, this reading did not: ``echo (a # (⏎)⏎(b # $(…))``) — or a
# ``;``/``&``/``<``/``>`` ends zsh's word inside an uncertain group — the
# structure past it may differ from zsh's: inside a ``$(…)``/``<(…)`` that
# fails closed (zsh may end the substitution elsewhere:
# ``$(printf p; : "("; : (a # )⏎)ool …; : (b # (⏎))`` runs ``pool``); at the
# top level every later ``(`` is uncertain and every later word-start ``#``
# is read both ways (sticky). A ``((`` in an uncertain position that is not
# glued may be arithmetic (zsh: ``repeat 1 ((``, ``coproc ((``, ``>f ((``;
# both shells: a case arm after ``(pattern)``, ``f() ((``): ``<<`` inside
# it fails closed (a shift there, a here-document in a subshell). Case
# patterns: after ``case WORD in`` and after a case terminator (``;;``,
# ``;&``, ``;;&``, zsh ``;|``) a pattern follows, also across newlines and
# ``;`` (zsh accepts ``;; ;`` and ``;;⏎(…)``), until a bare ``pattern)``
# (then a case arm: command position) or ``(pattern)``'s ``)`` (an arm,
# left uncertain); after a group's ``)`` an operator follows. Inside
# ``[[ … ]]`` no position is a command position (``[[ a =~ ⏎(…) ]]``).
#
# Line continuations: a backslash-newline joins ``$`` to ``(``/``{``
# (``$\⏎(…)ool`` runs in both shells; r10 missed it). The text is also read
# with every ``\⏎`` removed (union; an over-read inside single quotes).

#: Stands for a computed part inside re-read deferred text (never in
#: text a shell runs: argv cannot hold NUL); read as a computed item.
_R11_PLACEHOLDER = "\x00"
_R11_FRAGMENT_SPLIT_RE = re.compile(r"[ \t\n;&|<>()]+")
_R11_QUOTES_RE = re.compile(r"[\"'\\]")
_R11_FRAGMENT_TRIGGER_RE = re.compile(r"[ \t\n;&|<>()\"'\\]")
_R11_ARITH_PLAIN_RE = re.compile(r"[^ \t\n()\\'\"`$#;&|<>]+")
_R11_ARITH_COMMENT_RISK_RE = re.compile(r"[()'\"`$\\]")
#: A skipped comment region holding one of these makes uncertainty sticky.
_R11_REGION_STRUCTURE_RE = re.compile(r"[()'\"`]")
#: Characters that make a double-quoted span in arithmetic not inert.
_R11_ARITH_DQ_RISK_RE = re.compile(r"[(){}'`\\]")


class _R10Found(Exception):
    """A word can spell a wrapper: in scope."""


class _R10Fail(Exception):
    """Unreadable or unmodelled text holding a construct: in scope."""


class _R10Stop(Exception):
    """An unterminated quote/backtick opened at ``position`` (lenient)."""

    def __init__(self, position: int) -> None:
        super().__init__(position)
        self.position = position


class _R10Word:
    """Items of one shell word, and its text as deferred script. The word
    is re-read as script when a QUOTED or escaped piece of it holds ``$`` or
    a backtick (deferred text: ``bash -c '$(…)'``); an unquoted literal
    ``$`` (``${`` with no ``}`` after it) was already read as script here
    and does not make it live. r11 (REVIEW6 N7): the re-read text is the
    WHOLE word, each computed part replaced by ``_R11_PLACEHOLDER`` (r10 cut
    it into literal runs at each computed part)."""

    __slots__ = ("items", "parts", "live", "quoted", "mixed")

    def __init__(self) -> None:
        self.items: list = []
        self.parts: list[str] = []
        self.live = False
        self.quoted = False
        #: holds a computed item (fragment judging applies)
        self.mixed = False

    def lit(self, text: str, *, deferred: bool = True) -> None:
        if text:
            if _R11_PLACEHOLDER in text:
                # a computed part of re-read deferred text: a computed item
                for number, piece in enumerate(text.split(_R11_PLACEHOLDER)):
                    if number:
                        self.items.append(("any", ""))
                        self.mixed = True
                    if piece:
                        self.items.append(("lit", piece.lower()))
            else:
                self.items.append(("lit", text.lower()))
            self.parts.append(text)
            if deferred and ("$" in text or "`" in text):
                self.live = True

    def computed(self, items: list) -> None:
        self.items.extend(items)
        self.parts.append(_R11_PLACEHOLDER)
        self.mixed = True

    def plain(self) -> str:
        """The word's text when it is wholly unquoted literal (else "")."""
        if self.quoted or any(kind != "lit" for kind, _ in self.items):
            return ""
        return "".join(text for _, text in self.items)


def _r10_read(text: str, depth: int, *, comments: bool = True) -> None:
    """Read ``text`` as a script (raises ``_R10Found``/``_R10Fail``);
    ``comments=False`` (r11): a word-start ``#`` is literal."""
    if "$" not in text and "`" not in text:
        return  # nothing computed: literal and glob words are read elsewhere
    if depth > _R10_MAX_DEPTH:
        raise _R10Fail()
    reader = _R10Text(text)
    position = 0
    for _ in range(_R10_MAX_RESYNCS + 1):
        try:
            reader.script(position, depth, None, comments=comments)
            return
        except _R10Stop as stop:
            position = stop.position + 1
    raise _R10Fail()


def _r10_items_name_wrapper(items: list) -> bool:
    """r10's word rule over one item sequence: a wholly literal sequence
    whose basename is a wrapper, or a sequence with a computed item that can
    spell one using ≥ 1 fixed literal (a wholly computed one names nothing)."""
    if not items:
        return False
    if all(kind == "lit" for kind, _ in items):
        value = "".join(text for _, text in items)
        return value.rsplit("/", 1)[-1] in _R6_WRAPPER_BASENAMES
    compact: list = []
    for item in items:
        if not (item[0] == "any" and compact and compact[-1][0] == "any"):
            compact.append(item)
    return not all(kind == "any" for kind, _ in compact) and any(
        _r8_items_spell(compact, name) for name in _R6_WRAPPER_BASENAMES
    )


def _r11_fragments_name_wrapper(items: list) -> bool:
    """r11 (REVIEW6 N7): the word's items split at blanks/newlines/operators
    inside its literal parts — once as written, once with quotes and
    backslashes deleted (the script a shell re-reads joins them) — and each
    fragment judged by r10's word rule. ``eval "$(…)ool run …"`` → the
    fragment ``<any>ool``."""
    for strip in (False, True):
        fragment: list = []
        for kind, payload in items:
            if kind != "lit":
                fragment.append((kind, payload))
                continue
            text = _R11_QUOTES_RE.sub("", payload) if strip else payload
            for number, piece in enumerate(_R11_FRAGMENT_SPLIT_RE.split(text)):
                if number:
                    if _r10_items_name_wrapper(fragment):
                        return True
                    fragment = []
                if piece:
                    fragment.append(("lit", piece))
        if _r10_items_name_wrapper(fragment):
            return True
    return False


def _r10_judge(word: _R10Word, depth: int) -> None:
    items = word.items
    if _r10_items_name_wrapper(items):
        raise _R10Found()
    if word.mixed and any(
        kind == "lit" and _R11_FRAGMENT_TRIGGER_RE.search(text) for kind, text in items
    ) and _r11_fragments_name_wrapper(items):
        raise _R10Found()
    if word.live:
        _r10_read("".join(word.parts), depth + 1)


class _R10Text:
    """The r10 scanner over one text (see the block comment above)."""

    __slots__ = ("text", "size", "last_brace", "last_bracket", "last_paren")

    def __init__(self, text: str) -> None:
        self.text = text
        self.size = len(text)
        self.last_brace = text.rfind("}")
        self.last_bracket = text.rfind("]")
        self.last_paren = text.rfind(")")

    # -- script -----------------------------------------------------------
    def script(
        self, index: int, depth: int, closer: str | None, *, comments: bool = True
    ) -> int:
        """Read script text from ``index``; with ``closer`` ``")"`` return the
        index just past the ``)`` that closes the substitution. With
        ``comments=False`` a word-start ``#`` is a literal character (the
        rest of a line inside a zsh glob group, r11)."""
        if depth > _R10_MAX_DEPTH:
            raise _R10Fail()
        text, size = self.text, self.size
        word: _R10Word | None = None
        paren = 0
        command_position = True
        target_next = False
        after_for = False  # r11: ``for ((`` opens an arithmetic context
        last_command = False  # r11: the last word was a command word
        # r11 (N8): paren levels opened where a shell may NOT read a
        # subshell — zsh reads a glob group (``#`` literal) there, a shell
        # may read arithmetic (``<<`` a shift); 0 = no such level open.
        uncertain_from = 0
        arith_from = 0
        # r11 (N8): a skipped comment region held a paren/quote — zsh, for
        # which that ``#`` was literal, may count the text differently from
        # here on: every later ``(`` is uncertain, every ``#`` read both ways
        sticky = False
        # r11 (N8): a case header (2 after ``case``, 1 after its subject) and
        # pattern position (after ``case … in`` and a case terminator, kept
        # across newlines and ``;`` — zsh reads ``(`` there as a glob group)
        case_header = 0
        pattern_position = False
        pattern_group = 0
        # r11 (N8): inside ``[[ … ]]`` no position is a command position
        # (``[[ a =~ ⏎(a # $(…)) ]]`` — the ``(`` is a regex group)
        in_condition = False
        pending: list[tuple[str, bool, bool]] = []
        # r12 (re-check #7 F1): positions where zsh MAY read a command word
        # (after ``repeat N``, ``coproc``, ``for NAME (…)``, ``if [[ … ]]``,
        # ``((…))``, a ``(pattern)``): its keywords are recognised, but a
        # ``(`` there is never a certain subshell
        maybe_command = False
        repeat_next = 0  # 1/2: the next word is ``repeat``'s count (certain/maybe)
        for_state = 0  # 1 after ``for``/``select``/``foreach``, 2 after its NAME
        for_list = 0  # paren level + 1 of a ``for NAME (…)`` word list
        case_closer = "esac"  # r12: zsh ``case WORD { … }`` ends at ``}``

        def finish() -> None:
            nonlocal word, command_position, target_next, after_for, last_command
            nonlocal case_header, pattern_position, in_condition
            nonlocal maybe_command, repeat_next, for_state, case_closer
            if word is None:
                return
            after_for = last_command = False
            done, word = word, None
            _r10_judge(done, depth)
            if target_next:
                target_next = False
                return
            plain = done.plain()
            certain, keyword = command_position, command_position or maybe_command
            maybe_command = False
            # r12 (re-check #7 F1): ``case`` and ``[[`` are recognised
            # ANYWHERE — r11's command-position model missed them after
            # ``2>…``, ``repeat N``, ``coproc``, short forms and ``(pattern)``
            if plain == "case":
                if closer:
                    raise _R10Fail()  # pattern ``)`` would close the substitution
                case_header, for_state, repeat_next = 2, 0, 0
                command_position = False
                return
            if case_header:
                case_header -= 1
                if not case_header and plain in ("in", "{"):
                    pattern_position = True
                    case_closer = "esac" if plain == "in" else "}"
                    command_position = False
                    return
            if pattern_position and plain == case_closer:
                pattern_position = False
            if plain == "[[":
                in_condition = True
            elif in_condition and plain == "]]":
                in_condition = False
                command_position, maybe_command = False, True  # ``if [[ … ]] cmd``
                return
            if repeat_next:
                # ``repeat``'s count: a (sub)list follows
                command_position, maybe_command = repeat_next == 1, repeat_next == 2
                repeat_next = 0
                return
            if for_state == 1:
                for_state = 2  # the loop variable
                command_position = False
                return
            for_state = 0
            if keyword:
                after_for = plain == "for"
                if plain in ("for", "select", "foreach"):
                    for_state = 1
                last_command = True
                if plain == "repeat":
                    repeat_next = 1 if certain else 2
                    command_position = False
                    return
                keeps = (
                    plain in _R10_KEEP_COMMAND_POSITION
                    or bool(_R6_ASSIGNMENT_RE.match(plain))
                )
                command_position, maybe_command = keeps and certain, keeps and not certain

        while index < size:
            char = text[index]
            if char == " " or char == "\t":
                finish()
                index = _R10_BLANKS_RE.match(text, index).end()
                continue
            if char == "\n":
                finish()
                command_position = not (pattern_position or in_condition)
                after_for = last_command = maybe_command = False
                for_state = 0
                index += 1
                if pending:
                    index = self.heredoc_bodies(index, depth, pending)
                    pending = []
                continue
            if char == "\\":
                if text.startswith("\n", index + 1):
                    index += 2  # line continuation
                    continue
                if word is None:
                    word = _R10Word()
                word.quoted = True
                word.lit(text[index + 1:index + 2] or "\\")
                index += 2
                continue
            if char == "#" and word is None and comments:
                newline = text.find("\n", index)
                end = size if newline < 0 else newline
                if uncertain_from or sticky:
                    # r11 (N8): inside a zsh glob group ``#`` is literal (the
                    # rest of the line is read too, every ``#`` in it
                    # literal); a subshell skips it
                    _r10_read(text[index + 1:end], depth + 1, comments=False)
                    if _R11_REGION_STRUCTURE_RE.search(text, index + 1, end):
                        if closer:
                            # zsh may end the substitution elsewhere
                            raise _R10Fail()
                        sticky = True
                index = end
                continue
            if char in ";&|<>()":
                if (char in "<>" and word is not None
                        and _R12_FD_WORD_RE.fullmatch(word.plain())):
                    # r12 (re-check #7 F1): ``2>…``/``3<…``/``{fd}>…`` — the
                    # number is the redirection's, the command word follows
                    word = None
                # glued: a word is in progress, or the character before is a
                # word character (a here-document delimiter just read)
                glued = word is not None or (
                    index > 0 and text[index - 1] not in " \t\n;&|<>()"
                )
                finish()
                if uncertain_from and char in ";&<>":
                    # r11 (N8): zsh ends the word here, dropping the open glob
                    # group — its paren count leaves this reading's
                    if closer:
                        raise _R10Fail()  # zsh may end the substitution elsewhere
                    sticky = True
                if char in "<>" and text.startswith("(", index + 1):
                    word = _R10Word()  # process substitution: a computed word
                    try:
                        index = self.substitution(index + 2, depth)
                    except _R10Stop:
                        raise _R10Fail() from None  # r11 (N6): never resync inside
                    word.computed([("any", "")])
                    continue
                if char == "(":
                    if text.startswith(")", index + 1):
                        # ``name()`` / zsh ``() {…}``: a function body follows
                        command_position = command_position or last_command
                        after_for = last_command = False
                        index += 2
                        continue
                    certain = (
                        command_position and not glued and not target_next
                        and not uncertain_from and not sticky and not in_condition
                    )
                    if text.startswith("(", index + 1) and (certain or after_for):
                        # r11 (REVIEW6 N5): a ``((`` command / ``for ((``:
                        # an arithmetic context
                        try:
                            index = self.arith(index + 2, depth)
                        except _R10Stop:
                            raise _R10Fail() from None
                        command_position = after_for = last_command = False
                        maybe_command = True  # r12: ``if ((…)) cmd``, ``for ((…)) cmd``
                        for_state = 0
                        continue
                    after_for = last_command = maybe_command = False
                    if pattern_position and not pattern_group:
                        pattern_group = paren + 1  # ``(pattern)``
                    if for_state == 2 and not glued and not for_list:
                        for_list = paren + 1  # r12: ``for NAME (word …) cmd``
                    for_state = 0
                    if not certain:
                        # r11 (N8): argument position, glued to a word, a
                        # case pattern, a redirection target: zsh reads a
                        # glob group; a ``((`` there that is not glued may be
                        # arithmetic (zsh: ``repeat 1 ((``, ``coproc ((``,
                        # ``>f ((``; both: a case arm, ``f() ((``)
                        if not uncertain_from:
                            uncertain_from = paren + 1
                        if text.startswith("(", index + 1):
                            if not glued and not arith_from:
                                arith_from = paren + 1
                            paren += 1
                            index += 1
                    paren += 1
                    command_position = True
                    index += 1
                    continue
                after_for = last_command = False
                for_state = 0
                if char == ")":
                    maybe_command = False
                    index += 1
                    if paren:
                        paren -= 1
                        if paren < uncertain_from:
                            uncertain_from = 0
                        if paren < arith_from:
                            arith_from = 0
                        # r11 (N8): after a group an operator follows — or,
                        # after a ``(pattern)``, a case arm (left uncertain);
                        # r12 (F1): zsh may read a command word after a
                        # ``(pattern)`` and after a ``for NAME (…)`` list
                        command_position = False
                        if paren < pattern_group:
                            pattern_group = 0
                            pattern_position = False
                            maybe_command = True
                        if paren < for_list:
                            for_list = 0
                            maybe_command = True
                    elif closer:
                        return index
                    elif pattern_position:
                        command_position = True  # ``pattern)``: a case arm
                        pattern_position = False
                    elif not comments:
                        # r12: a dual-read comment region (rule D) ends at
                        # the ``)`` of the group it sits in: argument
                        # position follows, and the count is zsh's no more
                        command_position = False
                        sticky = True
                    else:
                        # r12 (re-check #7 F2): an unmatched ``)`` is a
                        # syntax error to both shells — here it means this
                        # reading's paren count left the shell's: in scope
                        raise _R10Fail()
                    continue
                if text.startswith("<<", index) and not text.startswith("<<<", index):
                    if arith_from:
                        raise _R10Fail()  # r11 (N5): a shift if this ``((`` is arithmetic
                    strip = text.startswith("<<-", index)
                    index = self.heredoc_word(index + (3 if strip else 2), pending, strip)
                    continue
                operator = next(op for op in _R6_OPERATORS if text.startswith(op, index))
                index += len(operator)
                if operator == ";" and text.startswith("|", index):
                    operator = ";|"  # zsh case terminator
                    index += 1
                if operator in (";;", ";&", ";;&", ";|"):
                    command_position = maybe_command = False  # r11 (N8): a case pattern follows
                    pattern_position = True
                elif operator in _R6_LIST_OPERATORS or operator in _R6_PIPE_OPERATORS:
                    command_position = not (pattern_position or in_condition)
                    maybe_command = False
                else:
                    target_next = True  # a redirection target follows
                continue
            if char == "=" and word is None and text.startswith("(", index + 1):
                # r12 (re-check #7 F2): zsh ``=(…)`` at a word start is a
                # process substitution (its body a script), read like ``<(…)``
                word = _R10Word()
                try:
                    index = self.substitution(index + 2, depth)
                except _R10Stop:
                    raise _R10Fail() from None
                word.computed([("any", "")])
                continue
            if word is None:
                word = _R10Word()
            if char == "'":
                close = text.find("'", index + 1)
                if close < 0:
                    raise _R10Stop(index)
                word.quoted = True
                word.lit(text[index + 1:close])
                index = close + 1
                continue
            if char == '"':
                word.quoted = True
                index = self.double(index + 1, depth, word)
                continue
            if char == "`":
                index = self.backtick(index, depth, word, in_dq=False)
                continue
            if char == "$":
                index = self.dollar(index, depth, word, quoted=False)
                continue
            run = _R10_PLAIN_RE.match(text, index)
            word.lit(run.group(0), deferred=False)
            index = run.end()
        finish()
        if closer:
            raise _R10Fail()  # unterminated $( / <( (fail closed)
        return size

    def substitution(self, index: int, depth: int) -> int:
        if index > self.last_paren:
            raise _R10Fail()  # no ``)`` anywhere after: unterminated
        return self.script(index, depth + 1, ")")

    # -- here-documents -----------------------------------------------------
    def heredoc_word(
        self, index: int, pending: list[tuple[str, bool, bool]], strip: bool
    ) -> int:
        text, size = self.text, self.size
        blanks = _R10_BLANKS_RE.match(text, index)
        if blanks:
            index = blanks.end()
        parts: list[str] = []
        quoted = False
        while index < size and text[index] not in " \t\n;&|<>()":
            char = text[index]
            if char == "'":
                close = text.find("'", index + 1)
                if close < 0:
                    raise _R10Stop(index)
                parts.append(text[index + 1:close])
                quoted, index = True, close + 1
            elif char == '"':
                close = index + 1
                while close < size and text[close] != '"':
                    close += 2 if text[close] == "\\" else 1
                if close >= size:
                    raise _R10Stop(index)
                parts.append(re.sub(r"\\(.)", r"\1", text[index + 1:close]))
                quoted, index = True, close + 1
            elif char == "\\":
                parts.append(text[index + 1:index + 2])
                quoted, index = True, index + 2
            else:
                run = _R10_DELIMITER_RUN_RE.match(text, index)
                parts.append(run.group(0))
                index = run.end()
        delimiter = "".join(parts)
        if delimiter or quoted:
            pending.append((delimiter, quoted, strip))
        return index

    def heredoc_bodies(
        self, index: int, depth: int, pending: list[tuple[str, bool, bool]]
    ) -> int:
        """Consume the bodies of ``pending`` from the line at ``index`` (the
        shell reads them after the newline that ends the operator's line);
        a missing delimiter line extends the body to the end of the text,
        as bash and zsh do. Every body is read as script (a shell may be its
        reader) and, unquoted, for the expansions the shell performs."""
        text = self.text
        for delimiter, quoted, strip in pending:
            pattern = re.compile(
                r"^" + (r"\t*" if strip else "") + re.escape(delimiter) + r"$", re.M
            )
            found = pattern.search(text, index)
            if found:
                body, index = text[index:found.start()], min(found.end() + 1, self.size)
            else:
                body, index = text[index:], self.size
            _r10_read(body, depth + 1)
            if not quoted:
                _R10Text(body).expand(depth + 1)
        return index

    def expand(self, depth: int) -> None:
        """The expansions of an unquoted here-document body: quotes are
        literal there, ``$``-constructs and backticks run."""
        if "$" not in self.text and "`" not in self.text:
            return
        if depth > _R10_MAX_DEPTH:
            raise _R10Fail()
        index, resyncs = 0, 0
        while True:
            found = _R10_EXPAND_RE.search(self.text, index)
            if not found:
                return
            index = found.start()
            try:
                if found.group(0) == "\\":
                    index += 2
                elif found.group(0) == "`":
                    index = self.backtick(index, depth, _R10Word(), in_dq=False)
                else:
                    index = self.dollar(index, depth, _R10Word(), quoted=True)
            except _R10Stop as stop:
                resyncs += 1
                if resyncs > _R10_MAX_RESYNCS:
                    raise _R10Fail() from None
                index = stop.position + 1

    # -- quoting and constructs --------------------------------------------
    def double(self, index: int, depth: int, word: _R10Word) -> int:
        """Read a double-quoted span starting after its ``"``."""
        text, size = self.text, self.size
        opening = index - 1
        while index < size:
            char = text[index]
            if char == '"':
                return index + 1
            if char == "\\":
                escaped = text[index + 1:index + 2]
                if escaped == "\n":
                    index += 2
                elif escaped and escaped in '$`"\\':
                    word.lit(escaped)
                    index += 2
                else:
                    word.lit("\\")
                    index += 1
                continue
            if char == "$":
                index = self.dollar(index, depth, word, quoted=True)
                continue
            if char == "`":
                index = self.backtick(index, depth, word, in_dq=True)
                continue
            run = _R10_DQ_PLAIN_RE.match(text, index)
            word.lit(run.group(0))
            index = run.end()
        raise _R10Stop(opening)

    def backtick(self, index: int, depth: int, word: _R10Word, *, in_dq: bool) -> int:
        found = _R10_BACKTICK_BODY_RE.match(self.text, index + 1)
        if not found:
            raise _R10Stop(index)
        body = self.text[index + 1:found.end() - 1]
        body = re.sub(r'\\([$`\\"])' if in_dq else r"\\([$`\\])", r"\1", body)
        word.computed([("any", "")])
        _r10_read(body, depth + 1)
        return found.end()

    def dollar(
        self, index: int, depth: int, word: _R10Word, *, quoted: bool, arith: bool = False
    ) -> int:
        text = self.text
        following = text[index + 1:index + 2]
        try:
            if following == "(":
                if text.startswith("(", index + 2):
                    # r11 (REVIEW6 N5): ``$((`` — an arithmetic context
                    end = self.arith(index + 3, depth + 1)
                else:
                    end = self.substitution(index + 2, depth)
                word.computed([("any", "")])
                return end
            if following == "{":
                if index + 2 > self.last_brace:
                    word.lit("${", deferred=False)  # no ``}`` after: both shells refuse it
                    return index + 2
                end = self.brace(index + 2, depth + 1, in_dq=quoted, strict=arith)
                construct = text[index:end].replace(_R11_PLACEHOLDER, "$_")
                word.computed(_r8_construct_items(construct))
                return end
            if following == "[":
                if index + 2 > self.last_bracket:
                    word.lit("$[", deferred=False)
                    return index + 2
                end = self.bracket(index + 2, depth + 1)
                word.computed([("any", "")])
                return end
        except _R10Stop:
            # r11 (REVIEW6 N6): an unterminated quote/backtick INSIDE a
            # construct is in scope — a resync would drop the word
            raise _R10Fail() from None
        if arith and following in ("'", '"'):
            raise _R10Fail()  # ``$'…'``/``$"…"`` in arithmetic: shells differ
        if following == "'" and not quoted:
            found = _R10_ANSI_BODY_RE.match(text, index + 2)
            if not found:
                raise _R10Stop(index + 1)
            word.quoted = True
            word.lit(_r6_decode_ansi_c(text[index + 2:found.end() - 1]))
            return found.end()
        if following == '"' and not quoted:
            word.quoted = True  # bash locale quoting (zsh: ``$`` + "…": wider)
            return self.double(index + 2, depth, word)
        name = _R10_NAME_RE.match(text, index + 1)
        if name:
            word.computed([("any", "")])
            return name.end()
        if following and following in "0123456789@*#?$!-":
            word.computed([("any", "")])
            return index + 2
        word.lit("$", deferred=quoted)
        return index + 1

    def brace(self, index: int, depth: int, *, in_dq: bool, strict: bool = False) -> int:
        """Index just past the ``}`` closing a ``${`` whose body starts at
        ``index``; nested constructs are read on the way. ``strict`` (inside
        arithmetic): any quote fails closed."""
        if depth > _R10_MAX_DEPTH:
            raise _R10Fail()
        text, size = self.text, self.size
        opening = index - 2
        scratch = _R10Word()
        # Bare braces: bash 3.2 ends an UNQUOTED ``${`` at the FIRST unquoted
        # ``}``, zsh counts them. Where the two ends differ only by ``}``
        # characters (``${{ github.token }}``, ``${CONFIG:-{}}``) the shells
        # continue at the same place and the zsh extent is read; any other
        # character after bash's end (``x=p; ${x:-{}ool …`` — bash runs
        # ``pool``) fails closed AT ONCE (r11, REVIEW6 N6: r10 read on, and
        # an unterminated quote there resynced past the word). Inside
        # double quotes both shells end at the first ``}`` (r11: measured
        # ``"[${x:-{a}b}]"`` → ``[{ab}]`` in both).
        bare = 0
        first_close = -1
        while index < size:
            run = _R10_BRACE_PLAIN_RE.match(text, index)
            if run:
                if first_close >= 0:
                    raise _R10Fail()  # text between bash's end and zsh's
                index = run.end()
                continue
            char = text[index]
            if char == "}":
                if in_dq or not bare:
                    if first_close >= 0 and text[first_close:index].strip("}"):
                        raise _R10Fail()
                    return index + 1
                if first_close < 0:
                    first_close = index + 1
                bare -= 1
                index += 1
                continue
            if first_close >= 0:
                raise _R10Fail()  # text between bash's end and zsh's
            if char == "{":
                if not in_dq:
                    bare += 1
                index += 1
                continue
            if strict and char in "'\"":
                raise _R10Fail()  # a quote in ``${…}`` inside arithmetic
            if char == "\\":
                index += 2
            elif char == "'":
                if in_dq:
                    raise _R10Fail()  # bash 3.2: a quote; zsh: literal
                close = text.find("'", index + 1)
                if close < 0:
                    raise _R10Stop(index)
                index = close + 1
            elif char == '"':
                index = self.double(index + 1, depth, scratch)
            elif char == "`":
                index = self.backtick(index, depth, scratch, in_dq=in_dq)
            else:
                index = self.dollar(index, depth, scratch, quoted=in_dq, arith=strict)
        if first_close >= 0:
            raise _R10Fail()  # bash closed it, zsh never does: they disagree
        raise _R10Stop(opening)  # r11: ``dollar`` turns this into _R10Fail

    def bracket(self, index: int, depth: int) -> int:
        """Index just past the ``]`` closing a ``$[`` (brackets counted)."""
        if depth > _R10_MAX_DEPTH:
            raise _R10Fail()
        text, size = self.text, self.size
        opening = index - 2
        scratch = _R10Word()
        level = 1
        while index < size:
            run = _R10_BRACKET_PLAIN_RE.match(text, index)
            if run:
                index = run.end()
                continue
            char = text[index]
            if char == "[":
                level += 1
                index += 1
            elif char == "]":
                level -= 1
                index += 1
                if not level:
                    return index
            elif char == "\\":
                index += 2
            elif char in "'\"":
                raise _R10Fail()  # quoting inside arithmetic: not modelled
            elif char == "`":
                index = self.backtick(index, depth, scratch, in_dq=False)
            else:
                index = self.dollar(index, depth, scratch, quoted=True)
        raise _R10Stop(opening)

    def arith(self, index: int, depth: int) -> int:
        """r11 (REVIEW6 N5): read an arithmetic context starting at
        ``index`` (just after ``$((``/``((``) and return the index just past
        the ``))`` that closes it (see the r11 block comment): ``#`` and
        ``<<`` are literal, parentheses nest, constructs are read, the words
        between them are judged; where bash and zsh may part, fail closed."""
        if depth > _R10_MAX_DEPTH:
            raise _R10Fail()
        text, size = self.text, self.size
        level = 0
        word: _R10Word | None = None

        def finish() -> None:
            nonlocal word
            if word is not None:
                done, word = word, None
                _r10_judge(done, depth)

        while index < size:
            run = _R11_ARITH_PLAIN_RE.match(text, index)
            if run:
                if word is None:
                    word = _R10Word()
                word.lit(run.group(0), deferred=False)
                index = run.end()
                continue
            char = text[index]
            if char in " \t\n":
                finish()
                index += 1
                continue
            if char == "(":
                finish()
                level += 1
                index += 1
                continue
            if char == ")":
                finish()
                if level:
                    level -= 1
                    index += 1
                    continue
                if text.startswith(")", index + 1):
                    return index + 2
                # not arithmetic: bash and zsh fall back to a subshell /
                # command substitution by different rules (``$((a) + (b))``
                # is arithmetic to bash only) — fail closed
                raise _R10Fail()
            if char == "<" and text.startswith("<<", index):
                finish()  # a shift (``((`` here is surely arithmetic)
                index += 2
                continue
            if char in ";&|<>":
                finish()
                index += 1
                continue
            if char == "'":
                raise _R10Fail()  # zsh ignores quotes for the extent, bash does not
            if word is None:
                word = _R10Word()
            if char == '"':
                # zsh ignores quotes for the extent, bash honours them: they
                # agree only on an inert span (``(( "$n" > 3 ))``)
                close = text.find('"', index + 1)
                if close < 0 or _R11_ARITH_DQ_RISK_RE.search(text, index + 1, close):
                    raise _R10Fail()
                word.quoted = True
                if self.double(index + 1, depth, word) != close + 1:
                    raise _R10Fail()
                index = close + 1
                continue
            if char == "#":
                # a shell comment starts only at a word start (after a
                # blank/newline/operator; ``16#ff``, zsh ``[##36]`` are not)
                if text[index - 1] in " \t\n;&|()<>":
                    newline = text.find("\n", index)
                    end = size if newline < 0 else newline
                    if _R11_ARITH_COMMENT_RISK_RE.search(text, index + 1, end):
                        raise _R10Fail()  # read as a comment, the context could end elsewhere
                word.lit("#", deferred=False)
                index += 1
                continue
            if char == "\\":
                if text.startswith("\n", index + 1):
                    index += 2  # line continuation
                    continue
                word.quoted = True
                word.lit(text[index + 1:index + 2] or "\\")
                index += 2
                continue
            if char == "`":
                index = self.backtick(index, depth, word, in_dq=False)
                continue
            index = self.dollar(index, depth, word, quoted=False, arith=True)
        raise _R10Fail()  # unterminated arithmetic context


def _r10_lexed_reading(raw: str) -> bool:
    """r10 (REVIEW5 N1): True when the quote-aware scanner finds a word that
    can spell a wrapper, or fails closed (see the block comment above)."""
    try:
        _r10_read(raw, 0)
        if "\\\n" in raw:
            # r11: also with every line continuation removed — ``$\⏎(…)``
            # is ``$(…)`` (an over-read inside single quotes; union)
            _r10_read(raw.replace("\\\n", ""), 0)
    except (_R10Found, _R10Fail):
        return True
    except RecursionError:
        return True  # nested beyond the interpreter: judge it (fail closed)
    except Exception:  # noqa: BLE001 — an unexpected reader failure
        return True  # is never an out-of-scope verdict (fail closed)
    return False


def r6_names_wrapper(raw: str) -> bool:
    """True when the command text names a paid-launch wrapper (r6/r7 scope).

    Literal wrapper names (quote/backslash/continuation-insensitive, like
    the r4 gate), ANSI-C quoted text decoded first, the literal word of a
    parameter operator read as a word (r7: ``${x:-pool}``, ``${x-sub.sh}``,
    zsh ``${:-pool}``), bash locale quoting read as plain quoting (r7:
    ``p$""ool``, ``p$"o"ol``), a wrapper name glued to a short option
    (r7: ``-O'pool run …'``), partial wrapper names glued to a
    $-expansion, command substitution or glob/brace pattern (r7: one
    literal stem character suffices — ``p*``, ``s*.py``), and any glob in
    command-word position that can match a wrapper basename. A wholly
    computed word names nothing: that is the documented arbitrary-process
    limit (REVIEW_2329 r2), not this gate's fence; so is a wholly wildcard
    operand (``python3 *.py``) and a name spelled with other characters
    (homoglyphs name a different file).

    r9 (REVIEW4 F1): quoting is shell-transparent for scope. Both partial-
    word readers also read the JOINED text (``"``, ``'``, ``\\`` deleted,
    ``$"`` read as ``"``, before splitting on blanks and operators), so
    ``${x:-p}"ool"``, ``"p"$(true)"ool"`` and ``$(printf p)"ool"`` are the
    one word the shell builds. The r8 readings are kept (union: never
    narrower than r8).
    """
    text = raw.replace("\\\n", "")
    text = _R6_ANSI_C_RE.sub(lambda match: _r6_decode_ansi_c(match.group(1)), text)
    # r8: one quote-free view; the glued-option scan reads it as is and the
    # name scan reads it with ``-`` after the first ``${`` as a boundary
    # (both linear, both at least as wide as r7's regex views).
    plain = re.sub(r"[\"'\\]", "", text.replace('$"', '"'))
    if _WRAPPER_NAME_RE.search(_r8_dash_view(plain)) or _r8_glued_option(plain):
        return True
    if _r7_glob_head_names_wrapper(raw):
        return True
    marked = text
    previous = None
    passes = 0
    while previous != marked:
        passes += 1
        if passes > _R7_MAX_SUBSTITUTION_DEPTH:
            return True  # nested beyond any honest launch: judge it (fail closed)
        previous = marked
        marked = _R6_COMPUTED_RE.sub("\x00", marked)
    for word in _R6_ROUGH_WORD_SPLIT_RE.split(marked):
        if word and _r6_partial_wrapper(word.rsplit("/", 1)[-1]):
            return True
    # r9 (REVIEW4 F1): the same partial-word reading on the JOINED text —
    # quotes and backslashes deleted before splitting, so ``$(printf p)"ool"``
    # is the one word ``\x00ool`` the shell builds. Additive: it can only
    # widen scope. Splitting also at a quoted blank or operator cannot cut a
    # word whose basename spells a wrapper (a wrapper basename holds neither;
    # one before the last literal ``/`` is followed by that basename restart).
    for word in _R9_JOINED_WORD_SPLIT_RE.split(_r9_joined(marked)):
        if word and _r6_partial_wrapper(word.rsplit("/", 1)[-1]):
            return True
    # r8: the nesting-aware construct reading (arithmetic glue, split
    # operator words) — additive: it can only widen scope. r9: read on the
    # raw text (r8) AND on the joined text (``${x:-p}"ool"``, nested bodies
    # included: each view recurses within itself, so the cost is 2× r8).
    if _r8_computed_glue(text) or _r8_computed_glue(_r9_joined(text)):
        return True
    # r10 (REVIEW5 N1): the quote-aware lexer reading of the RAW text —
    # construct extents that quoted/escaped/commented brackets cannot throw
    # off, here-documents and ``bash -c`` bodies read (union: never narrower).
    # r11 (REVIEW6 N5–N7, C10 N8): arithmetic contexts, ``${…}`` ends in
    # double quotes, word fragments / whole-word deferred text, uncertain
    # (glob-group) parentheses — see the r11 block comment.
    return _r10_lexed_reading(raw)


class _R6Word:
    """One shell word as typed segments: ``lit`` (unquoted), ``sq``, ``dq``,
    ``esc`` (fixed text) and ``param``/``arith``/``cmdsub``/``ansi``/
    ``locale`` (computed or re-decoded at runtime)."""

    __slots__ = ("_segments", "_pending")

    def __init__(self) -> None:
        self._segments: list[tuple[str, str]] = []
        #: r8: adjacent ``lit`` pieces are collected and joined once when
        #: the segments are read (r7 re-concatenated the growing segment on
        #: every piece: ``a$.a$.…`` was quadratic).
        self._pending: list[str] = []

    def add(self, kind: str, text: str) -> None:
        if kind == "lit":
            self._pending.append(text)
            return
        self._flush()
        self._segments.append((kind, text))

    def _flush(self) -> None:
        if not self._pending:
            return
        text = "".join(self._pending)
        self._pending = []
        if self._segments and self._segments[-1][0] == "lit":
            text = self._segments[-1][1] + text
            self._segments[-1] = ("lit", text)
        else:
            self._segments.append(("lit", text))

    @property
    def segments(self) -> list[tuple[str, str]]:
        self._flush()
        return self._segments

    @property
    def value(self) -> str:
        return "".join(text for _, text in self.segments)

    @property
    def literal(self) -> bool:
        return all(kind in _R6_LITERAL_SEGMENTS for kind, _ in self.segments)

    def leading_unquoted(self) -> str:
        if self.segments and self.segments[0][0] == "lit":
            return self.segments[0][1]
        return ""

    def has_glob(self) -> bool:
        return any(
            kind == "lit" and any(char in _R6_GLOB_CHARS for char in text)
            for kind, text in self.segments
        )

    def is_fd_number(self) -> bool:
        return (
            len(self.segments) == 1 and self.segments[0][0] == "lit"
            and self.segments[0][1].isdigit()
        )


def _r6_backtick_end(text: str, index: int) -> int:
    """Index just past the backtick closing the one at ``index`` (or -1)."""
    position = index + 1
    while position < len(text):
        if text[position] == "\\":
            position += 2
            continue
        if text[position] == "`":
            return position + 1
        position += 1
    return -1


def _r6_skip_double(text: str, index: int) -> int:
    """Index just past the ``"`` closing a double-quoted span (or -1)."""
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        if char == "$" and text.startswith("(", index + 1):
            index = _r6_match_paren(text, index + 1)
            if index < 0:
                return -1
            continue
        if char == "`":
            index = _r6_backtick_end(text, index)
            if index < 0:
                return -1
            continue
        index += 1
    return -1


def _r6_match_paren(text: str, open_index: int) -> int:
    """Index just past the ``)`` matching ``(`` at ``open_index`` (or -1);
    quotes, escapes and backticks are skipped."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "'":
            close = text.find("'", index + 1)
            if close < 0:
                return -1
            index = close + 1
            continue
        if char == '"':
            index = _r6_skip_double(text, index + 1)
            if index < 0:
                return -1
            continue
        if char == "`":
            index = _r6_backtick_end(text, index)
            if index < 0:
                return -1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _r6_match_brace(text: str, open_index: int) -> int:
    """Index just past the ``}`` closing ``${`` at ``open_index`` (or -1)."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "'":
            close = text.find("'", index + 1)
            if close < 0:
                return -1
            index = close + 1
            continue
        if char == '"':
            index = _r6_skip_double(text, index + 1)
            if index < 0:
                return -1
            continue
        if char == "$" and text.startswith("(", index + 1):
            index = _r6_match_paren(text, index + 1)
            if index < 0:
                return -1
            continue
        if char == "`":
            index = _r6_backtick_end(text, index)
            if index < 0:
                return -1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _r6_dollar(text: str, index: int, word: _R6Word, *, quoted: bool) -> int:
    """Read the ``$…`` construct at ``index`` into ``word``; new index or -1."""
    following = text[index + 1] if index + 1 < len(text) else ""
    if following == "(":
        end = _r6_match_paren(text, index + 1)
        if end < 0:
            return -1
        kind = "arith" if text.startswith("((", index + 1) else "cmdsub"
        word.add(kind, text[index:end])
        return end
    if following == "{":
        end = _r6_match_brace(text, index + 1)
        if end < 0:
            return -1
        word.add("param", text[index:end])
        return end
    if following == "[":
        close = text.find("]", index + 2)
        if close < 0:
            return -1
        word.add("arith", text[index:close + 1])
        return close + 1
    if following == "'" and not quoted:
        position = index + 2
        while position < len(text):
            if text[position] == "\\":
                position += 2
                continue
            if text[position] == "'":
                word.add("ansi", text[index:position + 1])
                return position + 1
            position += 1
        return -1
    if following == '"' and not quoted:
        inner = _R6Word()
        end = _r6_double_quoted(text, index + 2, inner)
        if end < 0:
            return -1
        for kind, segment in inner.segments:
            if kind not in _R6_LITERAL_SEGMENTS:
                word.add(kind, segment)
        word.add("locale", text[index:end])
        return end
    if re.match(r"[A-Za-z_]", following):
        end = index + 2
        while end < len(text) and re.match(r"[A-Za-z0-9_]", text[end]):
            end += 1
        word.add("param", text[index:end])
        return end
    if following and following in "0123456789@*#?$!-":
        word.add("param", text[index:index + 2])
        return index + 2
    word.add("dq" if quoted else "lit", "$")
    return index + 1


def _r6_double_quoted(text: str, index: int, word: _R6Word) -> int:
    """Read a double-quoted span starting after its ``"``; new index or -1."""
    buffer: list[str] = []
    word.add("dq", "")  # marks the quoting even for an empty ""

    def flush() -> None:
        if buffer:
            word.add("dq", "".join(buffer))
            buffer.clear()

    while index < len(text):
        char = text[index]
        if char == '"':
            flush()
            return index + 1
        if char == "\\" and index + 1 < len(text):
            escaped = text[index + 1]
            if escaped == "\n":
                index += 2
                continue
            if escaped in '$`"\\':
                buffer.append(escaped)
                index += 2
                continue
            buffer.append("\\")
            index += 1
            continue
        if char == "`":
            flush()
            end = _r6_backtick_end(text, index)
            if end < 0:
                return -1
            word.add("cmdsub", text[index:end])
            index = end
            continue
        if char == "$":
            flush()
            index = _r6_dollar(text, index, word, quoted=True)
            if index < 0:
                return -1
            continue
        buffer.append(char)
        index += 1
    return -1


def _r6_lex(text: str) -> tuple[list[tuple[str, object]], str]:
    """``_r6_lex_unbounded`` with nesting too deep to read (``"$("$(…``
    exhausts the recursion limit) reported as a tokenizer failure."""
    try:
        return _r6_lex_unbounded(text)
    except RecursionError:
        return [], "substitutions nested too deeply to read"


def _r6_lex_unbounded(text: str) -> tuple[list[tuple[str, object]], str]:
    """Tokenise a command line: ``("word", _R6Word)``, ``("op", str)`` and
    ``("procsub", str)`` tokens. Returns ``(tokens, error)``; a non-empty
    error means the line cannot be read and must be refused. Lexing stops
    at a here-document operator (its body is not read: the operator alone
    refuses)."""
    tokens: list[tuple[str, object]] = []
    word: _R6Word | None = None
    index = 0
    length = len(text)

    def flush() -> None:
        nonlocal word
        if word is not None:
            tokens.append(("word", word))
            word = None

    while index < length:
        char = text[index]
        if (ord(char) < 32 and char not in "\t\n") or char == "\x7f":
            return tokens, f"control character {char!r}"
        if char == "\\" and text.startswith("\n", index + 1):
            index += 2  # POSIX line continuation joins with nothing
            continue
        if char in " \t":
            flush()
            index += 1
            continue
        if char == "#" and word is None:
            newline = text.find("\n", index)
            index = length if newline < 0 else newline
            continue
        if char == "<" and _R7_ZSH_NUMERIC_GLOB_RE.match(text, index):
            # zsh: a numeric glob; bash: two redirections. Refuse, never pick.
            return tokens, (
                f"{_R7_ZSH_NUMERIC_GLOB_RE.match(text, index).group(0)} is a "
                "zsh numeric glob but bash redirections"
            )
        if char in ";&|<>()\n":
            if char in "<>" and word is not None and word.is_fd_number():
                word = None  # the fd number belongs to this redirection
            flush()
            operator = next(op for op in _R6_OPERATORS if text.startswith(op, index))
            if operator in ("<(", ">("):
                end = _r6_match_paren(text, index + 1)
                if end < 0:
                    return tokens, "unterminated process substitution"
                tokens.append(("procsub", text[index:end]))
                index = end
                continue
            tokens.append(("op", operator))
            index += len(operator)
            if operator in ("<<", "<<-"):
                return tokens, ""
            continue
        if word is None:
            word = _R6Word()
        if char == "'":
            close = text.find("'", index + 1)
            if close < 0:
                return tokens, "unterminated single quote"
            word.add("sq", text[index + 1:close])
            index = close + 1
            continue
        if char == '"':
            index = _r6_double_quoted(text, index + 1, word)
            if index < 0:
                return tokens, "unterminated double quote or substitution"
            continue
        if char == "\\":
            if index + 1 >= length:
                word.add("esc", "\\")
                index += 1
                continue
            word.add("esc", text[index + 1])
            index += 2
            continue
        if char == "`":
            end = _r6_backtick_end(text, index)
            if end < 0:
                return tokens, "unterminated backtick substitution"
            word.add("cmdsub", text[index:end])
            index = end
            continue
        if char == "$":
            index = _r6_dollar(text, index, word, quoted=False)
            if index < 0:
                return tokens, "unterminated $-expansion"
            continue
        run = _R7_LITERAL_RUN_RE.match(text, index)
        if run is not None:
            word.add("lit", run.group(0))
            index = run.end()
            continue
        word.add("lit", char)
        index += 1
    flush()
    return tokens, ""


class _R6Unit:
    """One simple command: argv words and its redirections.
    ``order_violation`` records the first redirection that was followed by
    another word (r7 grammar order: redirections only after the arguments)."""

    __slots__ = ("words", "redirects", "order_violation")

    def __init__(self) -> None:
        self.words: list[_R6Word] = []
        self.redirects: list[tuple[str, _R6Word]] = []
        self.order_violation = ""

    def empty(self) -> bool:
        return not self.words and not self.redirects


class _R7Launch:
    """One admitted unit whose command word is a wrapper (or python +
    slot.py), as the shell will run it: ``wrapper`` (lowercased basename),
    ``argv`` (the exact literal arguments after the wrapper word / slot.py
    operand) and ``assignments`` (every identity ``(NAME, exact value)``
    that reaches the child, in the order the shell and ``env`` apply them:
    nested outer unit first, prefix assignments before ``env`` arguments;
    the last one wins)."""

    __slots__ = ("wrapper", "argv", "assignments")

    def __init__(
        self, wrapper: str, argv: list[str], assignments: list[tuple[str, str]]
    ) -> None:
        self.wrapper = wrapper
        self.argv = argv
        self.assignments = assignments


class _R7Parse:
    """The r7 reading of one command line: every ``(code, detail)``
    (``refused`` when any is not advisory), every wrapper-head unit as an
    ``_R7Launch`` (the gate's launch census), and whether any unit's command
    word is a wrapper, python or a shell (selects the refusal wording)."""

    __slots__ = ("codes", "launches", "launch_like")

    def __init__(self) -> None:
        self.codes: list[tuple[str, str]] = []
        self.launches: list[_R7Launch] = []
        self.launch_like = False

    @property
    def refused(self) -> bool:
        return any(code not in _R6_ADVISORY_CODES for code, _ in self.codes)


def _r6_clip(text: str) -> str:
    return repr(text if len(text) <= 48 else text[:45] + "...")


def _r6_name(word: _R6Word) -> str:
    """The basename of a literal word (``""`` when computed)."""
    return word.value.rsplit("/", 1)[-1] if word.literal else ""


def _r7_command_name(word: _R6Word) -> tuple[str, bool]:
    """``(basename, resolvable)`` of a literal command word. ``resolvable``
    is True for a bare name (resolved through the session PATH) or a word
    naming exactly ``/bin/<name>`` or ``/usr/bin/<name>``; any other path —
    relative, ``/tmp/…``, ``~/…`` — may name a staged binary."""
    if not word.literal:
        return "", False
    value = word.value
    if "/" not in value:
        return value, True
    directory, base = value.rsplit("/", 1)
    return base, directory in _R7_SYSTEM_BIN_DIRS


def _r7_spelled(word: _R6Word, names: frozenset) -> bool:
    """True when a non-wrapper command word is admitted as written: exact
    (case-sensitive) name, bare or in a system bin directory, builtins bare."""
    base, resolvable = _r7_command_name(word)
    if base not in names or not resolvable:
        return False
    return not (base in _R7_BUILTIN_ONLY and "/" in word.value)


def _r7_value_problem(word: _R6Word) -> str:
    """'' when an assignment word's VALUE is exactly the literal text the
    child receives: no unquoted ``~`` (tilde expansion after ``=``) and no
    unquoted glob/brace character (an ``env`` argument is pathname- and
    brace-expanded)."""
    seen_equals = False
    for kind, text in word.segments:
        if not seen_equals:
            if "=" not in text:
                continue
            seen_equals = True
            if kind != "lit":
                continue
            text = text.split("=", 1)[1]
        if kind != "lit":
            continue
        if "~" in text:
            return "an unquoted ~ in its value (tilde expansion)"
        if any(char in _R6_GLOB_CHARS for char in text):
            return "an unquoted glob/brace character in its value"
    return ""


def _r6_assignment_problem(word: _R6Word, name: str, append: bool) -> str:
    if name not in _R6_ADMITTED_ASSIGNMENTS:
        if (name in _R6_ENVIRONMENT_INPUT_NAMES
                or name.startswith(_R6_ENVIRONMENT_INPUT_PREFIXES)):
            return (
                f"assignment {name}= is an unobservable launch environment "
                "input (startup file, hook, loader, search path or guard "
                "channel)"
            )
        return f"assignment {name}= is not a projected identity name"
    if append:
        return f"assignment {name}+= appends to a value the guard cannot see"
    if not word.literal:
        return f"assignment {name}= has a computed value"
    problem = _r7_value_problem(word)
    if problem:
        return f"assignment {name}= has {problem}"
    return ""


def _r6_prefix(
    name: str, words: list[_R6Word], index: int, codes: list[tuple[str, str]],
    assignments: list[tuple[str, str]],
) -> int:
    """Consume one transparent prefix's own arguments; the next index.
    ``env`` identity arguments are appended to ``assignments`` with their
    exact literal value."""
    if name == "env":
        while index < len(words):
            word = words[index]
            if word.value.startswith("-"):
                codes.append(("R6_PREFIX_FORM", f"env {word.value}"))
                index += 1
                continue
            match = _R6_ASSIGNMENT_RE.match(word.value)
            if match is None:
                break
            problem = _r6_assignment_problem(word, match.group(1), bool(match.group(2)))
            if problem:
                codes.append(("R6_ASSIGNMENT", problem))
            elif match.group(1) in _R6_ADMITTED_ASSIGNMENTS:
                assignments.append((match.group(1), word.value[match.end():]))
            index += 1
        return index
    if name == "nice" and index + 1 < len(words) and words[index].value == "-n":
        if words[index + 1].literal and _R6_NICENESS_RE.match(words[index + 1].value):
            return index + 2
    if name == "timeout":
        if (index < len(words) and words[index].literal
                and _R6_DURATION_RE.match(words[index].value)):
            return index + 1
        codes.append((
            "R6_PREFIX_FORM",
            "timeout without exactly one literal DURATION before the command",
        ))
    while index < len(words) and words[index].value.startswith("-"):
        codes.append(("R6_PREFIX_FORM", f"{name} {words[index].value}"))
        index += 1
    return index


def _r7_target_problem(operator: str, target: _R6Word, *, read_form: bool) -> str:
    """'' when a redirection target is admitted for this form.

    Descriptor duplication/close (``2>&1``, ``<&-``) and literal input files
    are admitted everywhere. A read form writes ONLY to /dev/null (REVIEW2
    finding 5: ``echo '…' >> ~/.zshenv`` stages a function every later zsh
    sources). A launch may log to a file, but never into a dot-path — a
    shell startup file, git hook, config or ``~/.local/bin`` wrapper that a
    later command would execute."""
    value = target.value
    if operator in ("<&", ">&") and _R7_DESCRIPTOR_RE.match(value):
        return ""
    if operator == "<":
        return ""
    if operator == "<&":
        return f"<& {value} (not a descriptor)"
    if value == "/dev/null":
        return ""
    if read_form:
        return f"{operator} {value} (a read form may write only to /dev/null)"
    if any(part.startswith(".") and part not in (".", "..")
           for part in value.split("/")):
        return (
            f"{operator} {value} (a dot-path: a startup file, hook, config or "
            "installed wrapper a later command executes)"
        )
    return ""


def _r7_options_problem(
    words: list[_R6Word], spec: tuple
) -> tuple[str, set[str]]:
    """Walk ``words`` with a closed option grammar ``spec`` (``_r7_spec``):
    ``(problem, seen option names)``. ``--`` ends option parsing; an
    option-looking word outside the grammar is the problem."""
    short_flags, short_valued, long_flags, long_valued = spec
    short_optional = getattr(spec, "short_optional", frozenset())
    long_optional = getattr(spec, "long_optional", frozenset())
    seen: set[str] = set()
    index = 0
    while index < len(words):
        value = words[index].value
        if value == "--":
            break
        if value.startswith("--"):
            name, equals, _ = value.partition("=")
            if equals:
                if name not in long_valued and name not in long_optional:
                    return value, seen
            elif name in long_flags or name in long_optional:
                pass
            elif name in long_valued:
                index += 1
                if index >= len(words):
                    return f"{value} without its value", seen
            else:
                return value, seen
            seen.add(name)
            index += 1
            continue
        if value.startswith("-") and len(value) > 1:
            cluster = value[1:]
            for position, char in enumerate(cluster):
                if char in short_flags:
                    seen.add("-" + char)
                    continue
                if char in short_optional:
                    seen.add("-" + char)
                    break  # the rest of the cluster is its value; no next word
                if char in short_valued:
                    seen.add("-" + char)
                    if position + 1 == len(cluster):
                        index += 1
                        if index >= len(words):
                            return f"{value} without its value", seen
                    break
                return f"-{char} (in {value})", seen
            index += 1
            continue
        index += 1
    return "", seen


def _r7_glob_may_inject(word: _R6Word) -> bool:
    """True when an unquoted glob/brace word may expand to a name that
    STARTS with ``-`` (its first fixed character is a pattern character)."""
    if not word.has_glob():
        return False
    for kind, text in word.segments:
        if text:
            return kind == "lit" and text[0] in "*?[{"
    return False


def _r7_git_problem(args: list[_R6Word]) -> str:
    values = [arg.value for arg in args]
    forbidden = next(
        (value for value in values if value.startswith(_R8_GIT_FORBIDDEN_PREFIXES)),
        None,
    )
    if forbidden is not None:
        return (
            f"git with {_r6_clip(forbidden)} (writes a file or runs a program "
            "or pager wherever it appears)"
        )
    index = 1 if values[:1] == ["--no-pager"] else 0
    if index >= len(values):
        return "git without a subcommand"
    sub = values[index]
    spec = _R7_GIT_SPECS.get(sub)
    if spec is None:
        return (
            f"git {_r6_clip(sub)} (read forms: commit -m|-F, log, show, diff, "
            "status, grep, add; no git global option but --no-pager)"
        )
    problem, seen = _r7_options_problem(args[index + 1:], spec)
    if problem:
        return (
            f"git {sub} {_r6_clip(problem)} (outside the option allowlist: it "
            "can execute, write, page or open an editor)"
        )
    if sub == "commit" and not (
        seen & {"-m", "-F", "--message", "--file"}
        or {"--amend", "--no-edit"} <= seen
    ):
        return "git commit without -m/-F (it opens an editor)"
    return ""


def _r7_read_form_problem(name: str, args: list[_R6Word]) -> str:
    """'' when ``name args`` is a closed read form (redirections aside)."""
    if name in _R7_GLOB_SENSITIVE and any(_r7_glob_may_inject(arg) for arg in args):
        return (
            f"{name} with a leading glob argument (an expanded file name "
            "starting with '-' becomes an option)"
        )
    values = [arg.value for arg in args]
    try:
        options = values[:values.index("--")]
    except ValueError:
        options = values
    if name == "git":
        return _r7_git_problem(args)
    if name == "rg":
        problem, _ = _r7_options_problem(args, _R7_RG_SPEC)
        return (
            f"rg {_r6_clip(problem)} (outside the rg option allowlist: --pre, "
            "-z/--search-zip and --hostname-bin execute programs)"
            if problem else ""
        )
    if name == "sed":
        if (len(values) >= 2 and values[0] == "-n"
                and _R7_SED_SCRIPT_RE.match(values[1])
                and not any(value.startswith("-") for value in values[2:])):
            return ""
        return "sed outside the read form sed -n N[,M]p FILE… (scripts can execute and write)"
    if name == "tail":
        for value in options:
            if (value.startswith(("--follow", "--retry"))
                    or (value[:1] in "-+" and not value.startswith("--")
                        and len(value) > 1 and ("f" in value or "F" in value))):
                return f"tail {_r6_clip(value)} (follow never finishes)"
        return ""
    if name in ("grep", "egrep", "fgrep"):
        for value in options:
            if value.startswith(_R7_UGREP_EXEC_PREFIXES) or (
                value.startswith("-") and not value.startswith("--")
                and "Q" in value
            ):
                return (
                    f"{name} {_r6_clip(value)} (ugrep runs filters/pagers, "
                    "reads or saves configs, or opens its query UI)"
                )
        return ""
    if name == "file":
        for value in options:
            if value == "--compile" or (
                value.startswith("-") and not value.startswith("--") and "C" in value
            ):
                return f"file {_r6_clip(value)} (compiles and writes a magic file)"
        return ""
    return ""


def _r7_nested(
    shell: str, args: list[_R6Word], *, nested: bool,
    codes: list[tuple[str, str]], parse: _R7Parse,
    outer: list[tuple[str, str]],
) -> str:
    """Judge ``<shell> …`` as the NESTED form; returns ``"nested"`` or ``""``.
    The body's launches join the census with the outer unit's identity
    assignments in front of their own."""
    problems: list[str] = []
    if nested:
        problems.append("a shell inside a nested -c body")
    if shell not in _R6_NESTED_SHELLS:
        problems.append(
            f"{shell} is not admitted (its startup files or a different "
            "grammar run with the body)"
        )
    if not args or not args[0].literal or args[0].value != "-c":
        problems.append(
            f"{shell} must take exactly -c as its only option "
            f"(got {_r6_clip(args[0].value) if args else 'no option'})"
        )
    if len(args) != 2:
        problems.append("exactly one -c body and nothing after it")
    for name in ("BASH_ENV", "ENV"):
        if os.environ.get(name, "").strip():
            problems.append(
                f"the session environment sets {name}, which the nested "
                "shell may load before the body"
            )
    body: _R7Parse | None = None
    body_at = next(
        (position for position, word in enumerate(args)
         if word.literal and _r8_option_cluster(word.value, "c")),
        None,
    )
    if not nested and body_at is not None and body_at + 1 < len(args):
        if args[body_at + 1].literal:
            body = _r7_parse(args[body_at + 1].value, nested=True)
        # A computed body is reported by the computed-word scan; a shell
        # inside a body is already refused and its body is not read.
    if problems:
        codes.append(("R6_NESTED_SHELL", "; ".join(problems)))
    if body is not None:
        codes.extend(body.codes)
        for launch in body.launches:
            parse.launches.append(_R7Launch(
                launch.wrapper, launch.argv, [*outer, *launch.assignments]
            ))
    return "" if problems or (body is not None and body.codes) else "nested"


def _r7_unit(
    unit: _R6Unit, *, nested: bool, codes: list[tuple[str, str]],
    parse: _R7Parse,
) -> str:
    """Classify one simple command: ``"launch"``, ``"nested"``,
    ``"inspector"`` (any closed read form) or ``""`` (not admitted; reason
    appended to codes). A launch (wrapper head, or python + slot.py) is
    appended to ``parse.launches`` with its exact argv and identity values."""
    for operator, target in unit.redirects:
        if target.has_glob():
            codes.append(("R6_GLOB_OR_BRACE", f"{operator} {target.value}"))
        if target.literal and target.value.startswith("!"):
            codes.append((
                "R6_TOKENIZE_FAILED",
                f"{operator}{target.value} (zsh reads {operator}! as a clobber "
                "operator, bash as a file named '!…')",
            ))
        if target.literal and target.value.startswith(("/dev/tcp/", "/dev/udp/")):
            codes.append(("R6_REDIRECTION", f"{operator} {target.value} (network)"))
    if unit.order_violation:
        codes.append((
            "R6_REDIRECTION",
            f"{unit.order_violation} before the command word or between "
            "arguments",
        ))
    words = unit.words
    if not words:
        codes.append(("R6_NOT_A_PLAIN_LAUNCH", "a command with no command word"))
        return ""
    assignments: list[tuple[str, str]] = []
    index = 0
    while index < len(words):
        match = _R6_ASSIGNMENT_RE.match(words[index].leading_unquoted())
        if match is None:
            break
        problem = _r6_assignment_problem(
            words[index], match.group(1), bool(match.group(2))
        )
        if problem:
            codes.append(("R6_ASSIGNMENT", problem))
        elif match.group(1) in _R6_ADMITTED_ASSIGNMENTS:
            assignments.append(
                (match.group(1), words[index].value[match.end():])
            )
        index += 1
    assigned = index > 0
    if index == len(words):
        codes.append((
            "R6_NOT_A_PLAIN_LAUNCH",
            "an assignment-only command (it changes this shell's state for "
            "the commands after it)",
        ))
        return ""
    prefixes = 0
    while index < len(words):
        base = _r7_command_name(words[index])[0]
        if base.lower() not in _R6_TRANSPARENT_PREFIXES:
            break
        if not _r7_spelled(words[index], _R6_TRANSPARENT_PREFIXES):
            codes.append(("R6_HEAD_SPELLING", _r6_clip(words[index].value)))
            return ""
        prefixes += 1
        if prefixes > _R6_MAX_PREFIXES:
            codes.append(("R6_PREFIX_FORM", "more than four stacked prefixes"))
            return ""
        index = _r6_prefix(base, words, index + 1, codes, assignments)
    if index >= len(words):
        codes.append(("R6_NOT_A_PLAIN_LAUNCH", "no command word after the prefixes"))
        return ""
    head = words[index]
    name = _r6_name(head)
    if name in _R6_RESERVED_WORDS:
        codes.append(("R6_KEYWORD", repr(name)))
        return ""
    if name in _R6_ENV_BUILTINS:
        codes.append(("R6_ENV_BUILTIN", repr(name)))
        return ""
    if not name or head.has_glob():
        codes.append((
            "R6_NOT_A_PLAIN_LAUNCH",
            f"the computed or pattern command word {_r6_clip(head.value)}",
        ))
        return ""
    lowered = name.lower()
    if lowered in _R6_WRAPPER_BASENAMES:
        parse.launch_like = True
        wrapper, args = lowered, words[index + 1:]
    elif _R6_PYTHON_RE.match(lowered):
        parse.launch_like = True
        if not (_R6_PYTHON_RE.match(name) and _r7_command_name(head)[1]):
            codes.append(("R6_HEAD_SPELLING", _r6_clip(head.value)))
            return ""
        script = words[index + 1] if index + 1 < len(words) else None
        if (script is None or not script.literal or script.has_glob()
                or script.value.startswith("-")
                or _r6_name(script).lower() != "slot.py"):
            codes.append((
                "R6_NOT_A_PLAIN_LAUNCH",
                f"{name} with anything but a literal …/slot.py first operand "
                "(inline program, option, stdin or another script)",
            ))
            return ""
        wrapper, args = "slot.py", words[index + 2:]
    elif lowered in _R6_NESTED_SHELLS or lowered in _R6_OTHER_SHELLS:
        parse.launch_like = True
        if lowered in _R6_NESTED_SHELLS and not _r7_spelled(head, _R6_NESTED_SHELLS):
            codes.append(("R6_HEAD_SPELLING", _r6_clip(head.value)))
            return ""
        form = _r7_nested(
            lowered, words[index + 1:], nested=nested, codes=codes,
            parse=parse, outer=assignments,
        )
        for operator, target in unit.redirects:
            problem = _r7_target_problem(operator, target, read_form=False)
            if problem:
                codes.append(("R6_REDIRECTION", problem))
                form = ""
        return form
    elif lowered in _R7_READ_HEADS and not assigned and not prefixes and not nested:
        if not _r7_spelled(head, _R7_READ_HEADS):
            codes.append(("R6_HEAD_SPELLING", _r6_clip(head.value)))
            return ""
        form = "inspector"
        problem = _r7_read_form_problem(name, words[index + 1:])
        if problem:
            codes.append(("R6_NOT_A_PLAIN_LAUNCH", problem))
            form = ""
        for operator, target in unit.redirects:
            problem = _r7_target_problem(operator, target, read_form=True)
            if problem:
                codes.append(("R6_REDIRECTION", problem))
                form = ""
        return form
    else:
        codes.append(("R6_NOT_A_PLAIN_LAUNCH", repr(name)))
        return ""
    for arg in args:
        if arg.has_glob():
            codes.append(("R6_GLOB_OR_BRACE", _r6_clip(arg.value)))
    for operator, target in unit.redirects:
        problem = _r7_target_problem(operator, target, read_form=False)
        if problem:
            codes.append(("R6_REDIRECTION", problem))
    parse.launches.append(
        _R7Launch(wrapper, [arg.value for arg in args], assignments)
    )
    return "launch"


def _r7_parse(text: str, *, nested: bool) -> _R7Parse:
    """The r7 reading of ``text`` (``nested`` judges a ``bash -c`` body:
    only a single LAUNCH is admitted there)."""
    parse = _R7Parse()
    codes = parse.codes
    tokens, error = _r6_lex(text)
    if error:
        codes.append(("R6_TOKENIZE_FAILED", error))
        parse.launch_like = True  # unreadable: never claim "only as data"
        return parse
    units = [_R6Unit()]
    separators: list[str] = []
    pending: str | None = None
    for kind, item in tokens:
        if kind == "word":
            if pending is not None:
                units[-1].redirects.append((pending, item))
                pending = None
            else:
                unit = units[-1]
                if unit.redirects and not unit.order_violation:
                    operator, target = unit.redirects[0]
                    unit.order_violation = _r6_clip(f"{operator} {target.value}")
                unit.words.append(item)
            continue
        if kind == "procsub":
            codes.append(("R6_PROCESS_SUBSTITUTION", _r6_clip(str(item))))
            continue
        operator = str(item)
        if pending is not None:
            codes.append(("R6_TOKENIZE_FAILED", f"{pending!r} has no target"))
            pending = None
        if operator in ("<<", "<<-"):
            codes.append(("R6_HEREDOC", operator))
            continue
        if operator == "<<<" or operator in _R6_REDIRECTIONS:
            if operator == "<<<":
                codes.append(("R6_HEREDOC", operator))
            elif operator not in _R6_ADMITTED_REDIRECTIONS:
                codes.append(("R6_REDIRECTION", operator))
            pending = operator
            continue
        if operator in ("(", ")"):
            codes.append(("R6_GROUPING", operator))
        separators.append(operator)
        units.append(_R6Unit())
    if pending is not None:
        codes.append(("R6_TOKENIZE_FAILED", f"{pending!r} has no target"))
    # Leading/trailing newlines are whitespace, not another command. (r8:
    # leading ones are dropped by one slice — ``pop(0)`` per newline was
    # quadratic on a newline run.)
    leading = 0
    while (leading < len(separators) and separators[leading] == "\n"
           and units[leading].empty()):
        leading += 1
    if leading:
        units = units[leading:]
        separators = separators[leading:]
    while separators and separators[-1] == "\n" and units[-1].empty():
        units.pop()
        separators.pop()
    for unit in units:
        for word in [*unit.words, *(target for _, target in unit.redirects)]:
            for segment_kind, segment in word.segments:
                if segment_kind == "cmdsub":
                    codes.append(("R6_COMMAND_SUBSTITUTION", _r6_clip(segment)))
                elif segment_kind not in _R6_LITERAL_SEGMENTS:
                    codes.append(("R6_EXPANSION", _r6_clip(segment)))
                elif segment_kind == "sq" and ("$" in segment or "`" in segment):
                    codes.append(("R6_DEFERRED_EXPANSION", _r6_clip(segment)))
    forms = [_r7_unit(unit, nested=nested, codes=codes, parse=parse) for unit in units]
    list_operators = sorted({op for op in separators if op in _R6_LIST_OPERATORS})
    if list_operators:
        codes.append((
            "R6_COMPOUND_LIST",
            " ".join("newline" if op == "\n" else op for op in list_operators),
        ))
    if any(op in _R6_PIPE_OPERATORS for op in separators) and (
        nested or any(form != "inspector" for form in forms)
    ):
        codes.append(("R6_PIPELINE", "| with a non-inspector stage"))
    return parse


def _r6_analyse(text: str, *, nested: bool) -> list[tuple[str, str]]:
    """Every r6/r7 code for ``text`` (``[]`` = admitted)."""
    return _r7_parse(text, nested=nested).codes


def r7_parse(raw: str, *, force: bool = False) -> _R7Parse | None:
    """The r7 reading of a command line, or None when it is out of scope
    (names no wrapper — the arbitrary-process limit). ``force`` parses
    regardless of scope (used when the r4 text view sees a launch)."""
    if not force and not r6_names_wrapper(raw):
        return None
    return _r7_parse(raw, nested=False)


def r6_refusal_codes(raw: str) -> list[tuple[str, str]]:
    """The r6/r7 ADMIT rule: ``[]`` when ``raw`` is out of scope (names no
    wrapper) or is exactly one admitted form; otherwise every typed
    ``(code, detail)`` explaining the refusal."""
    parse = r7_parse(raw)
    if parse is None or not parse.refused:
        return []
    return parse.codes


def _r6_reason(codes: list[tuple[str, str]], *, launch_like: bool = True) -> str:
    grouped: dict[str, list[str]] = {}
    for code, detail in codes:
        details = grouped.setdefault(code, [])
        if detail and detail not in details and len(details) < 3:
            details.append(detail)
    clauses = [
        _R6_CLAUSES[code].format(detail=", ".join(details) or "-")
        for code, details in grouped.items()
    ]
    summary = "; ".join(clauses) + ". "
    refusal = "(r7 admit rule; refusal codes: " + ", ".join(grouped) + "): "
    if launch_like:
        return (
            "Mastermind shared-placement guard: unobservable launch — this "
            "command names a paid-launch wrapper but is not one plain "
            "top-level launch " + refusal + summary + _R6_REMEDY
        )
    return (
        "Mastermind shared-placement guard: unobservable launch — this "
        "command mentions a paid-launch wrapper name (pool, sub.sh, "
        "remote_sub.sh, slot.py) only as data or program text, and it is "
        "not an admitted read form, so the guard cannot prove that text is "
        "never executed " + refusal + summary + _R7_READ_REMEDY
        + " Launching? " + _R6_REMEDY
    )


def family(model: str) -> str:
    lowered = (model or "").strip().lower()
    for name in ("fable", "opus", "sonnet", "haiku"):
        if name in lowered:
            return name
    return lowered


def _emit(payload: dict[str, object]) -> NoReturn:
    # r8: the budget watchdog is disarmed BEFORE anything is written, so a
    # late alarm can never interleave a second decision into the output.
    _r8_disarm_watchdog()
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
    if str(binding.get("schema") or "") not in EXECUTION_BINDING_SCHEMAS:
        return f"{owner}: schema must be {EXECUTION_BINDING_SCHEMA} or {EXECUTION_BINDING_SCHEMAS[1]}"
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


_SHELL_WORD_RE = re.compile(r"\S+")
_ASSIGNMENT_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")


def _wrapper_invocations(command: str) -> list[tuple[int, str, str, bool]]:
    """EVERY wrapper invocation in ``command``, positional:
    ``(offset, wrapper, token, known_mode)`` for all five shapes, repeated.

    Unlike :data:`FABRIC_LAUNCH_RE`, the mode is NOT required to be on the
    wrapper's list: an off-list mode (``sub.sh zebra-glm``) is still an
    invocation (``known_mode=False``) so it can be refused instead of
    passing unobserved. A wrapper name with no argument, an argument of a
    read-only inspector (``cat sub.sh``), or a documented pure helper mode
    (``sub.sh __launch_plan``) is not a paid launch.

    The inspector test reads the first word of the simple command around
    each invocation (assignments and compound-command keywords skipped),
    truncated at the invocation. r7: separator positions are computed once
    and each simple command's first word is found once (bounded by its
    next separator), so the scan stays linear in the command length.
    """
    canon = _canonical_command(command)
    separators = [match.span() for match in _SIMPLE_COMMAND_SPLIT_RE.finditer(canon)]
    separator_ends = [end for _, end in separators]
    separator_starts = [start for start, _ in separators]
    first_words: dict[int, tuple[int, int, str]] = {}

    def head_at(offset: int) -> str:
        count = bisect.bisect_right(separator_ends, offset)
        unit_start = separator_ends[count - 1] if count else 0
        if unit_start not in first_words:
            following = bisect.bisect_left(separator_starts, unit_start)
            unit_end = (
                separator_starts[following]
                if following < len(separator_starts) else len(canon)
            )
            first_words[unit_start] = (len(canon), len(canon), "")
            for word in _SHELL_WORD_RE.finditer(canon, unit_start, unit_end):
                text = word.group(0)
                if text in _COMMAND_PREFIX_WORDS or _ASSIGNMENT_WORD_RE.match(text):
                    continue
                # r8: the whole word's basename is computed ONCE per unit;
                # r7 re-sliced a long first word for every invocation in
                # the unit (quadratic).
                first_words[unit_start] = (
                    *word.span(), text.rsplit("/", 1)[-1].lower()
                )
                break
        position, end, head = first_words[unit_start]
        if position >= offset:
            return ""
        if end <= offset:
            return head
        return canon[position:offset].rsplit("/", 1)[-1].lower()

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
        if head_at(match.start()) in _INSPECTORS:
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


def _runtime_multiplexed(canon: str, offsets: list[int]) -> bool:
    """True when a wrapper invocation sits inside a construct that executes
    it N times at runtime: a for/while/until body (``do ... done``) or an
    xargs/parallel/find -exec executor's argument tail (REVIEW_2329 r2
    N-2). One binding covers exactly one attempt, so N runtime children
    under one lexical launch are refused as unaccounted descendants."""
    spans: list[tuple[int, int]] = []
    opened: int | None = None
    for match in _LOOP_KEYWORD_RE.finditer(canon):
        if match.group(0) == "do":
            if opened is None:
                opened = match.start()
        elif opened is not None:
            spans.append((opened, match.end()))
            opened = None
    spans += [match.span() for match in _BATCH_EXECUTOR_RE.finditer(canon)]
    return any(
        start <= offset < end for start, end in spans for offset in offsets
    )


#: Words of ``env`` options/assignments read per ``env`` (each ``env`` would
#: otherwise re-read ``env -u env -u …`` to the end: quadratic). More than
#: this many is judged as a clear (fail closed).
_R7_ENV_WORD_LIMIT = 32
_ENV_WORD_RE = re.compile(r"(?<![A-Za-z0-9_.-])env(?=[ \t])")
_ENV_SEPARATOR_RE = re.compile(r"[;&|\n()`]")


def _env_clear_offsets(canon: str) -> list[int]:
    """Offsets of ``env`` invocations that clear the inherited environment
    (``env -i``, ``env -``, ``--ignore-environment``, clustered ``-iv``) or
    re-split their arguments (``-S``), which can hide a clear. (r7: each
    ``env`` reads at most ``_R7_ENV_WORD_LIMIT`` words up to the next
    separator — linear.)"""
    separator_starts = [match.start() for match in _ENV_SEPARATOR_RE.finditer(canon)]
    offsets: list[int] = []
    for match in _ENV_WORD_RE.finditer(canon):
        following = bisect.bisect_left(separator_starts, match.end())
        limit = (
            separator_starts[following]
            if following < len(separator_starts) else len(canon)
        )
        skip = 0
        for count, found in enumerate(_SHELL_WORD_RE.finditer(canon, match.end(), limit)):
            if count >= _R7_ENV_WORD_LIMIT:
                offsets.append(match.start())  # unread options: treat as a clear
                break
            word = found.group(0)
            if skip:
                skip -= 1
                continue
            if (
                word in ("-", "--ignore-environment", "-S")
                or word.startswith("--split-string")
                or _r8_option_cluster(word, "iS")
            ):
                offsets.append(match.start())
                break
            if word in ("-u", "-C", "-P", "--unset", "--chdir"):
                skip = 1
                continue
            if word.startswith("-") or _ASSIGNMENT_WORD_RE.match(word):
                continue
            break
    return offsets


_IDENTITY_VALUE_RE = re.compile(r"=([^\s;&|<>()`{}]*)")


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
    equals the server-derived projection. (r7: every test reads a bounded
    window around the occurrence instead of slicing the whole command.)
    """
    canon = _canonical_command(command)
    values = list(_command_assignments(command, name))
    events: list[tuple[int, str]] = []
    occurrence = re.compile(
        rf"(?:(?<![A-Za-z0-9_])|(?<=-u)){re.escape(name)}(?![A-Za-z0-9_])"
    )
    # r8 (REVIEW3 A3 BLOCKER 3): a value is read once. An assignment that
    # starts INSIDE the previous value's run (``a=NAME=NAME=…``) would only
    # re-read a strict suffix of that run — quadratic, 13 s at 256 KB, and
    # the gate ran after it. Two assignments in one run cannot both equal
    # the projection (different lengths), so the inner one is recorded as
    # ``''`` (never the non-empty projection): the verdict is unchanged.
    value_end = -1
    for match in occurrence.finditer(canon):
        start, end = match.span()
        if canon.startswith("=", end):
            if start < value_end:
                events.append((start, ""))
                continue
            found = _IDENTITY_VALUE_RE.match(canon, end)
            value, value_end = found.group(1), found.end()
            events.append((start, "" if "$" in value else value))
        elif canon[start - 1:start] == "$" or (
            canon[max(0, start - 2):start] == "${"
            and not canon.startswith(("=", ":="), end)
        ):
            continue  # a read of the value, not a change
        elif _bare_export_before(canon, start) and (
            end == len(canon) or canon[end] in " \t\n\r\f\v;&|)"
        ):
            continue  # bare `export NAME` re-exports the inherited value
        else:
            events.append((start, ""))
    last_set = max((at for at, value in events if value), default=-1)
    for offset in _env_clear_offsets(canon):
        if not last_set > offset:
            events.append((offset, ""))
    canonical = [value for _, value in events]
    seen = set(canonical)
    extra = [value for value in values if value not in seen]
    if not canonical and not extra:
        return None
    return canonical + extra


def _bare_export_before(canon: str, start: int) -> bool:
    """True when ``export`` + whitespace ends exactly at ``start`` and the
    ``export`` word starts the text or follows whitespace/``;&|(``."""
    position = start
    while position > 0 and canon[position - 1].isspace():
        position -= 1
    if position == start or not canon.startswith("export", position - 6, position):
        return False
    before = position - 6
    return before == 0 or canon[before - 1].isspace() or canon[before - 1] in ";&|("


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


def validate_execution_binding(command: str, parse: _R7Parse | None = None) -> None:
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
    text it is shown. Before this function runs, the r6/r7 ADMIT rule
    (``r7_parse``) has already refused every command that names a wrapper
    but is not one plain launch / one faithful ``bash -c`` launch / a
    closed read form. r7: when ``parse`` is given (armed sessions), the
    launch census is the parse's — wrapper, mode and token read from the
    lexer's argv — and every identity assignment is compared by its EXACT
    literal value; the r4 text view (every wrapper invocation in the text,
    all five shapes, heredoc bodies included, backslash-newline joined) must
    find exactly the same invocations or the launch is refused. The r4
    identity and eval/loop/batch checks stay as defence in depth. Not
    observed: a command that names no wrapper at all (arbitrary-process
    limit), scripts or binaries staged in an EARLIER command or file and
    executed later (including a staged file shadowing the wrapper on PATH),
    and environment injected by provider-side mechanisms outside the
    command.
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

    text_view: list[tuple[int, str, str, bool]] = []
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
        text_view = _wrapper_invocations(command)
        launches = text_view
        if parse is not None:
            # r7: the census is the PARSE (the lexer's argv); the r4 text
            # view must find exactly the same invocations, in order.
            census = _r7_census(parse)
            parsed = [(wrapper, token) for wrapper, token, _ in census]
            seen = [(wrapper, token) for _, wrapper, token, _ in text_view]
            if parsed != seen:
                deny(
                    "Mastermind shared-placement guard: unaccounted descendant "
                    f"— the parsed command line carries the paid launch(es) "
                    f"{parsed} but its text carries the wrapper invocation(s) "
                    f"{seen}; the two readings must agree exactly, so a "
                    "launch the guard cannot attribute is refused. Pass task "
                    "text that names a wrapper in a packet file, not on the "
                    "command line."
                )
            launches = [(0, wrapper, token, known) for wrapper, token, known in census]
        if text_view and _runtime_multiplexed(
            _canonical_command(command),
            [offset for offset, _, _, _ in text_view],
        ):
            deny(
                "Mastermind shared-placement guard: runtime-multiplexed "
                "launch — a for/while/until loop body or an xargs/parallel/"
                "find -exec executor repeats this paid launch at runtime, "
                "but the current binding covers exactly one attempt. Every "
                "paid child must be admitted and claimed through the "
                "placement authority before launch."
            )

    expected_projection = _expected_projection(binding)
    if parse is not None:
        # r7 (REVIEW2 finding 3): the EXACT literal value the shell passes —
        # every assignment of every wrapper-head unit (prefix, env argument,
        # nested outer and body) — must equal the projection; with no
        # assignment the inherited session value governs.
        for launch in parse.launches:
            for env_name, expected_value in expected_projection.items():
                values = [v for n, v in launch.assignments if n == env_name]
                if not values:
                    values = [os.environ.get(env_name, "").strip()]
                for value in values:
                    if value != expected_value:
                        deny(
                            "Mastermind shared-placement guard: "
                            f"{env_name} is a server-derived projection of the "
                            f"current {EXECUTION_BINDING_SCHEMA}; this launch "
                            f"declares {value!r} (the exact value the shell "
                            f"passes) but the binding projects {expected_value!r}"
                            + (
                                f" ({len(values)} assignments of {env_name} in "
                                "one command; every one must equal the "
                                "projection)" if len(values) > 1 else ""
                            )
                            + ". A child cannot re-root, re-parent or promote "
                            "itself by changing the environment."
                        )

    # Server-derived projections: EVERY identity value the launched child
    # could receive must equal what the binding projects (canonical view of
    # all assignment/clearing forms; see _effective_identity_values).
    for env_name, expected_value in expected_projection.items():
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


def _r7_census(parse: _R7Parse) -> list[tuple[str, str, bool]]:
    """``(wrapper shape, token, known mode)`` for every PAID launch in the
    parse, read from the lexer's argv with the r4 shape law: ``pool run
    <pool>`` / ``pool remote <host> <pool>`` (other ``pool`` subcommands —
    status, plan, hosts, … — are not paid launches), ``sub.sh <mode>``,
    ``remote_sub.sh <host> <mode>``, ``slot.py <pool>``. A wrapper with no
    argument and the documented pure helper modes are not paid launches;
    an off-list or missing mode is (``known=False``) and is refused."""
    census: list[tuple[str, str, bool]] = []
    for launch in parse.launches:
        argv = [value.lower() for value in launch.argv]
        if launch.wrapper == "pool":
            if not argv or argv[0] not in ("run", "remote"):
                continue
            shape, rest = "pool " + argv[0], argv[1:]
        else:
            shape, rest = launch.wrapper, argv
        index, modes = _WRAPPER_SHAPES[shape]
        if not rest:
            continue
        token = rest[index] if len(rest) > index else ""
        if token in NON_LAUNCH_WRAPPER_MODES or (
            len(rest) > index + 1 and rest[index + 1] == "__launch_plan"
        ):
            continue
        census.append((shape, token, bool(token) and (modes is None or token in modes)))
    return census


def _r7_identity_values(parse: _R7Parse, name: str) -> tuple[list[str], list[str]]:
    """``(every exact assigned value, every effective value)`` of ``name``
    across the parse's wrapper-head units: the effective value is the last
    assignment that reaches the child, else the inherited session value."""
    assigned: list[str] = []
    effective: list[str] = []
    for launch in parse.launches:
        values = [value for found, value in launch.assignments if found == name]
        assigned.extend(values)
        effective.append(values[-1] if values else os.environ.get(name, "").strip())
    return assigned, effective


# --- r12: the STRUCTURAL scope rule for armed sessions (re-check #7) --------
#
# Seven distinct reviews found that every r6–r11 scope reading — "does this
# command name a wrapper, perhaps hidden inside a shell construct?" — leaks
# new shell grammar (r11: zsh command positions, ``=(…)``). In an ARMED
# session r12 takes that judgement out of the security decision:
#
#   OUT OF SCOPE (allowed without a binding check) only when the raw text
#   holds NO shell construct anywhere — quoted or not, see
#   ``_R12_CONSTRUCT_RE`` / ``_R12_CONSTRUCT_WORDS_RE`` — AND names no
#   wrapper by the literal, quote-joined check AND ``_r6_lex`` reads it AND
#   the r6–r11 scanner (kept as a SECONDARY reading: it can only widen) finds
#   no wrapper name;
#   IN SCOPE otherwise: the command must be exactly one admitted ADMIT form
#   (``_r7_parse``: LAUNCH / NESTED / READ with their carve-outs); every
#   other in-scope command is DENIED with the structural codes.
#
# "No construct" is decided on the RAW characters, ignoring quoting: quoted
# text is literal to THIS shell, but ``eval``, ``bash -c``, ``ssh HOST``,
# ``trap``, ``find -exec sh -c``, ``watch`` … hand it to another shell that
# expands it (``bash -c 'p*l run …'``, ``ssh h '$(…)ool …'``), and the set of
# such programs is open. Quotes and backslashes still delimit literal words
# (the literal check deletes them, joining the word the shells build).
#
# Construct-free text cannot make any shell compute a word: no parameter,
# command, arithmetic or process substitution, no glob/brace/tilde
# expansion (zsh ``EXTENDED_GLOB`` ``#``/``^``/``~`` too), no history
# expansion, no here-document body (a different quoting context), no line
# continuation (a word joined across lines — read on the raw text AND, r13,
# on the quote-deleted view, because ``"po\\"'⏎'"ol …"`` is construct-free
# byte for byte yet this shell's quote removal hands a nested ``-c``
# interpreter the single argument ``po\⏎ol …``, which it joins to ``pool …``;
# re-check #8 BLOCKER), no comment (whose model differs
# between shells), and no ``eval``/``source``/``alias``/``trap``/``coproc``/
# ``repeat`` word. Its words are literal byte strings in every shell; the
# literal check reads them all at once. What remains outside the rule (C11
# ledger): a literal word that resolves to a wrapper by something other than
# its bytes (homoglyphs, a staged copy/symlink/alias/function, PATH), and
# programs that compute and run text themselves (``python3 -c``,
# ``… | base64 -d | sh`` — the arbitrary-process limit since REVIEW_2329 r2).
#
# Trade (principal's decision, re-check #7): armed sessions refuse EVERY
# command that uses such a construct outside the admitted forms
# (``cd "$(git rev-parse --show-toplevel)"``, ``git commit -m "$(cat <<EOF``),
# with ``_R12_HEADLINE``; the admitted forms (``git commit -F FILE``,
# ``ls ~/x``, ``git log HEAD~1``, ``cat *.md`` …) keep working.
#
# Cost: two C-level regex scans and one ``_r9_joined`` view (linear); the
# scanner runs only for construct-free text.

#: Shell construct characters/sequences, wherever they occur (quoted or not).
#: A ``{`` followed by a blank, newline, ``;&|<>`` or the end is a word of
#: its own — never a brace expansion in bash or zsh (measured: ``{ a,b}``
#: prints ``{`` ``a,b}`` in bash and is a parse error in zsh) — so the
#: ``{ …; }`` group stays literal; ``{}`` is NOT exempt (bash expands
#: ``p{},ool}`` to ``p}`` ``pool``).
_R12_CONSTRUCT_RE = re.compile(
    r"\$|`|\\\n|<<|<[0-9]*-[0-9]*>|[*?\[()~#^]|\{(?=[^ \t\n;&|<>])"
    r"|![^ \t\n\"'=]|[\x00-\x08\x0b-\x1f\x7f]"
)
#: Words that re-evaluate text or change the grammar of what follows, on the
#: quote-joined text, wherever they occur (``e\val``, ``"ev"al`` too).
_R12_CONSTRUCT_WORDS_RE = re.compile(
    r"(?<![^ \t\n;&|<>])(?:eval|source|alias|trap|coproc|repeat)(?![^ \t\n;&|<>])",
    re.I,
)
#: ``python3 -m slot`` / ``-mslot`` / ``pkg.slot``: the module form of
#: ``slot.py`` (Python resolves ``slot`` to ``slot.py`` on sys.path, the
#: current directory first) — a literal name by resolution, not by bytes.
#: r13 (re-check #8 MINOR): the flag-combined forms ``-Bmslot`` / ``-sBmslot``
#: / ``-OOmslot`` (``python3 -B -m slot``) are the same module name.
_R12_SLOT_MODULE_RE = re.compile(
    r"(?:(?:^|[^A-Za-z0-9_])m?|-[A-Za-z]*m)slot(?![A-Za-z0-9_])", re.I
)
#: r13: quote characters only (backslashes kept), see ``_r12_unquoted_view``.
_R12_QUOTE_ONLY_RE = re.compile(r"[\"']")
_R13_ASSEMBLED_CONTINUATION = (
    "\\⏎ (line continuation assembled by quote removal from adjacent quoted "
    "pieces, joined by a nested interpreter)"
)
_R12_CONSTRUCT_KINDS = {
    "$(": "$( (command substitution)", "$((": "$(( (arithmetic)",
    "${": "${ (parameter expansion)", "$[": "$[ (arithmetic)",
    "$'": "$' (ANSI-C quoting)", '$"': '$" (locale quoting)',
    "`": "` (command substitution)", "\\\n": "\\⏎ (line continuation)",
    "<<": "<< (here-document or here-string)",
    "*": "* (glob)", "?": "? (glob)", "[": "[ (glob)",
    "{": "{ (brace expansion or group)",
    "(": "( ) (subshell, group, glob group, arithmetic, process "
    "substitution or case pattern)",
    ")": "( ) (subshell, group, glob group, arithmetic, process "
    "substitution or case pattern)",
    "~": "~ (tilde expansion or zsh exclusion glob)",
    "#": "# (comment or zsh extended glob)", "^": "^ (zsh negation glob)",
    "!": "! (history expansion)",
}
_R12_HEADLINE = (
    "armed session: shell expansion is not admitted; use a literal command "
    "or a file argument"
)
_R6_CLAUSES["R12_SHELL_CONSTRUCT"] = (
    _R12_HEADLINE + " — the shell construct {detail} decides at runtime what "
    "runs (quoted text counts: eval, bash -c, ssh or another program may "
    "expand it)"
)
#: r12 wording of the grammar's catch-all code for a command that is in
#: scope only by its construct (it names no wrapper).
_R12_NOT_ADMITTED_CLAUSE = (
    "{detail} is not an admitted launch or read form, which every armed "
    "command holding a shell construct must be"
)
_R12_REMEDY = (
    "Write it with literal words only — quoting is fine, but no $, "
    "backticks, globs (* ? [), braces, parentheses, ~, #, ^, ! history, "
    "here-documents or line continuations, even inside quotes; pass content "
    "through a file argument (git commit -F FILE); or use the Read/Grep/Glob "
    "tools. Admitted read forms with constructs: cat/head/tail/grep/egrep/"
    "fgrep/wc/ls/stat/file/diff/cmp/shasum/sha1sum/sha256sum/md5/md5sum/nl/"
    "od/echo, git commit -m|-F, git log|show|diff|status|grep|add, rg and "
    "sed -n N[,M]p (allowlisted options, literal words, piped only into each "
    "other, writing only to /dev/null). Launching? " + _R6_REMEDY
)


def _r12_construct_detail(text: str, index: int) -> str:
    char = text[index]
    if char == "$":
        following = text[index + 1:index + 3]
        for opener in ("$((", "$(", "${", "$[", "$'", '$"'):
            if ("$" + following).startswith(opener):
                return _R12_CONSTRUCT_KINDS[opener]
        return "$ (parameter expansion)"
    if text.startswith("\\\n", index):
        return _R12_CONSTRUCT_KINDS["\\\n"]
    if text.startswith("<<", index):
        return _R12_CONSTRUCT_KINDS["<<"]
    if char == "<":
        return "<N-M> (zsh numeric glob)"
    if char in _R12_CONSTRUCT_KINDS:
        return _R12_CONSTRUCT_KINDS[char]
    return f"{char!r} (control character)"


def _r12_unquoted_view(raw: str) -> str:
    """r13: the text with the quote characters deleted and the backslashes
    KEPT — the argument this shell's quote removal builds and hands to a
    nested interpreter, where an emergent ``\\⏎`` (``"po\\\\"'⏎'"ol"``) is a
    line continuation. Linear: one replace, one sub."""
    return _R12_QUOTE_ONLY_RE.sub("", raw.replace('$"', '"'))


def r12_constructs(raw: str, limit: int = 3) -> list[str]:
    """r12: the first ``limit`` distinct shell constructs in ``raw`` —
    quoted or not — as descriptions (``[]`` = construct-free). One linear
    regex scan, the r13 continuation scan on the quote-deleted view, plus
    the construct-word scan on the quote-joined text."""
    kinds: list[str] = []
    for match in _R12_CONSTRUCT_RE.finditer(raw):
        kind = _r12_construct_detail(raw, match.start())
        if kind not in kinds:
            kinds.append(kind)
            if len(kinds) >= limit:
                return kinds
    if "\\\n" in _r12_unquoted_view(raw):
        kinds.append(_R13_ASSEMBLED_CONTINUATION)
        if len(kinds) >= limit:
            return kinds
    word = _R12_CONSTRUCT_WORDS_RE.search(_r9_joined(raw))
    if word is not None:
        kinds.append(f"{word.group(0).lower()} (re-evaluating or grammar word)")
    return kinds


def r12_literal_names_wrapper(raw: str) -> bool:
    """r12: the LITERAL check — a wrapper name in the quote-joined text
    (``"``/``'``/``\\`` deleted: the word every shell builds from literal
    pieces; r13: a ``\\⏎`` assembled by quote removal is joined FIRST, as a
    nested interpreter would), glued to a short option, or seen by the
    launch regexes; also the ``slot`` module name. Linear."""
    plain = _r12_unquoted_view(raw).replace("\\\n", "").replace("\\", "")
    return bool(
        _WRAPPER_NAME_RE.search(_r8_dash_view(plain)) or _r8_glued_option(plain)
        or _R12_SLOT_MODULE_RE.search(plain)
        or FABRIC_LAUNCH_RE.search(raw) or _wrapper_invocations(raw)
    )


def r12_armed_in_scope(raw: str) -> bool:
    """r12: True when an ARMED session must judge ``raw`` by the ADMIT
    grammar (see the r12 block comment). The scanner is consulted only for
    construct-free, literally unnamed text, and can only widen."""
    if r12_constructs(raw, 1) or r12_literal_names_wrapper(raw):
        return True
    if _r6_lex(raw)[1]:
        return True  # the tokenizer must read it
    return bool(r6_names_wrapper(raw))


def _r12_reason(parse: _R7Parse, constructs: list[str], named: bool) -> str:
    codes = [("R12_SHELL_CONSTRUCT", kind) for kind in constructs] + parse.codes
    if not constructs or named:
        return _r6_reason(codes, launch_like=parse.launch_like)
    grouped: dict[str, list[str]] = {}
    for code, detail in codes:
        details = grouped.setdefault(code, [])
        if detail and detail not in details and len(details) < 3:
            details.append(detail)
    clauses = [
        (_R12_NOT_ADMITTED_CLAUSE if code == "R6_NOT_A_PLAIN_LAUNCH"
         else _R6_CLAUSES[code]).format(detail=", ".join(details) or "-")
        for code, details in grouped.items()
    ]
    return (
        "Mastermind shared-placement guard: unobservable launch — "
        + _R12_HEADLINE + ". In a shared-placement (paid-launch) session a "
        "command holding a shell construct must be exactly one admitted launch "
        "or read form, and this one is not; the guard does not search it for "
        "hidden wrapper names (r12 structural rule; refusal codes: "
        + ", ".join(grouped) + "): " + "; ".join(clauses) + ". " + _R12_REMEDY
    )


def _guard_armed_launch(command: str, raw: str) -> None:
    """r7 armed gate (WO-11; REVIEW2 A1). The PARSE decides: out of scope
    → nothing to judge; refused shape → deny; closed read forms only → no
    unit executes a wrapper; otherwise EVERY wrapper-head unit reaches the
    binding gate — there is no early return for it.

    r12 (re-check #7): scope is STRUCTURAL — a command is out of scope only
    when it is construct-free and names no wrapper literally (the scanner
    is a secondary, widening-only reading for construct-free text); any
    construct puts it in scope, where only an admitted form passes."""
    constructs = r12_constructs(raw)
    named = r12_literal_names_wrapper(raw)
    if not constructs and not named and not _r6_lex(raw)[1] and not r6_names_wrapper(raw):
        return
    parse = _r7_parse(raw, nested=False)
    if parse.refused:
        deny(_r12_reason(parse, constructs, named))
    if not parse.launches:
        return
    validate_execution_binding(raw, parse)

    inherited_root = os.environ.get("POOL_ORCHESTRATOR_ID", "").strip()
    assigned_roots = _r7_identity_values(parse, "POOL_ORCHESTRATOR_ID")[0]
    assigned_roots += _command_assignments(command, "POOL_ORCHESTRATOR_ID")
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
        or not all(value.strip() for value in _r7_identity_values(parse, name)[1])
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


def guard_fabric_launch(command: str, raw_command: str | None = None) -> None:
    raw = command if raw_command is None else raw_command
    if shared_placement_armed():
        # WO-11 r7: the armed gate is driven by the parse, never by the
        # legacy text regexes (REVIEW2 A1 finding 1).
        _guard_armed_launch(command, raw)
        return
    # Unarmed sessions: the legacy identity checks on the legacy census. An
    # off-list wrapper mode is still an observed launch (REVIEW_2329 M-4).
    # r7: a launch the parse finds but the text regexes miss
    # (``pool </dev/null run …``) is checked too, never skipped.
    launches = list(FABRIC_LAUNCH_RE.finditer(command))
    invocations = _wrapper_invocations(command)
    if not launches and not invocations and not (
        r6_names_wrapper(command) and _r7_census(_r7_parse(command, nested=False))
    ):
        return

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
    if shared_placement_armed():
        # r7: the armed launch gate judges the raw text FIRST and in linear
        # time; the heredoc stripper below serves only the CI-wait checks.
        if len(command) > R7_MAX_ARMED_COMMAND_CHARS:
            deny(
                "Mastermind shared-placement guard: this command is "
                f"{len(command)} characters, above the {R7_MAX_ARMED_COMMAND_CHARS}"
                "-character limit the guard judges within its hook budget; "
                "refused fail-closed. Write long content to a file with a "
                "non-shell tool and run a short command."
            )
        guard_fabric_launch(command, command)
        # r8: the CI-wait checks below need "gh " in the heredoc-stripped
        # text, and stripping never creates it; skip the (super-linear)
        # heredoc stripper for every armed command that cannot need it.
        if "gh " not in command:
            return
        clean = strip_heredocs(command)
    else:
        # r10 (REVIEW5 N2): before ANY super-linear scan (the heredoc
        # stripper below is quadratic on ``<<A`` runs), record whether the
        # RAW text names a wrapper — linear readings only. If the watchdog
        # then fires, ``main`` denies when it does (the legacy identity
        # check never got to judge a possible launch) and gives no decision
        # otherwise (CI-wait text keeps r9's availability gain).
        _r10_note_unarmed_scope(command)
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


# --- r8: the hook-budget watchdog (REVIEW3 A3 S1, recommendation (a)) -----
#
# The provider kills a PreToolUse command hook at its registered timeout
# (10 s) and, unless the row sets ``onFailure: "block"`` (see the C6 ledger
# for the host determination), a killed hook does NOT block the tool call.
# Every armed-path scan is linear and the command size is capped, but the
# constant depends on the host; so an ARMED session also runs under a
# SIGALRM watchdog that, when it fires, writes a DENY decision and exits 0
# well inside the provider's timeout. It interrupts Python code and long
# ``re`` searches (the regex engine checks for signals). r9 (REVIEW4 F4):
# unarmed sessions run the same watchdog, but its firing there is NO
# DECISION (exit 0, no output) — see ``main``.

#: Default budget in seconds; the provider's timeout is 10 s.
R8_WATCHDOG_DEFAULT_S = 7.0
#: Hard floor: an override can never make the watchdog fire sooner than this.
R8_WATCHDOG_FLOOR_S = 1.0
#: Session override, honoured only DOWNWARD (a value above the default, or
#: malformed, reads as the default; below the floor reads as the floor).
R8_WATCHDOG_ENV = "MASTERMIND_GUARD_BUDGET_S"


class _R8BudgetExceeded(BaseException):
    """Raised by the watchdog's SIGALRM handler (a BaseException, so no
    ``except Exception`` on the judging path can swallow it)."""


def r8_watchdog_seconds() -> float:
    raw = os.environ.get(R8_WATCHDOG_ENV, "").strip()
    try:
        value = float(raw) if raw else R8_WATCHDOG_DEFAULT_S
    except ValueError:
        value = R8_WATCHDOG_DEFAULT_S
    if not value == value or value > R8_WATCHDOG_DEFAULT_S:  # NaN, above default
        value = R8_WATCHDOG_DEFAULT_S
    return max(R8_WATCHDOG_FLOOR_S, value)


def _r8_on_alarm(_signum: int, _frame: object) -> None:
    raise _R8BudgetExceeded()


def _r8_arm_watchdog() -> object:
    """Arm the watchdog; returns the previous SIGALRM handler (or None when
    the platform has no interval timer)."""
    if not hasattr(signal, "setitimer"):
        return None
    previous = signal.signal(signal.SIGALRM, _r8_on_alarm)
    signal.setitimer(signal.ITIMER_REAL, r8_watchdog_seconds())
    return previous


def _r8_disarm_watchdog() -> None:
    if hasattr(signal, "setitimer"):
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except (OSError, ValueError):
            pass


# --- r10: the unarmed watchdog decision (REVIEW5 N2 MODERATE) ---------------
#
# r9 made an unarmed watchdog firing NO DECISION. But the unarmed path runs
# the heredoc stripper BEFORE the legacy identity check, and the stripper is
# quadratic: ``pool run grok a /tmp grok-4⏎`` + N × ``<<A⏎`` with no
# ``POOL_*`` identity was DENIED by r8 ("missing POOL_ORCHESTRATOR_ID", 7.3–
# 9.5 s, inside the 10 s timeout) and returned NO DECISION in r9 at 7 s —
# fail open on every CLI. r10 keeps choice (a) and records, before the
# stripper, whether the raw text names a wrapper:
#
#   "unset"   — the unarmed Bash path was not reached (other tool, out of
#               scope, unreadable payload): firing = no decision;
#   "pending" — the scope reading itself was still running: firing = DENY
#               (the reading is linear, ≤ ~1.7 s at 262 144 chars; only a
#               multi-megabyte command can still be reading at 7 s);
#   True      — the text names a wrapper: firing = DENY;
#   False     — it names none: firing = no decision (r9).
#
# The reading is the armed scope reading ``r6_names_wrapper`` (every r6–r10
# reader, so also the N1 lexer reading) after a cheap literal check, on the
# RAW text (heredoc bodies included: wider than the stripped text).
_R10_UNARMED_SCOPE: list = ["unset"]


def _r10_note_unarmed_scope(command: str) -> None:
    _R10_UNARMED_SCOPE[0] = "pending"
    plain = re.sub(r"[\"'\\]", "", command.replace('$"', '"'))
    if FABRIC_LAUNCH_RE.search(command) or _WRAPPER_NAME_RE.search(plain):
        _R10_UNARMED_SCOPE[0] = True
        return
    _R10_UNARMED_SCOPE[0] = bool(r6_names_wrapper(command))


def _r10_unarmed_budget_denial() -> NoReturn:
    missing = [name for name in _FABRIC_IDENTITY_NAMES if not os.environ.get(name, "").strip()]
    deny(
        "Mastermind Fabric root-budget guard: guard budget exceeded while "
        "judging a command that names a Fabric launch wrapper — fail closed. "
        f"Judging it took longer than {r8_watchdog_seconds():g} s, so the "
        "root-identity check could not complete"
        + (
            "; this session is also missing " + ", ".join(missing)
            + ", which every Fabric launch must preserve"
            if missing else ""
        )
        + ". Run the launch as a short, plain command; write long content "
        "to a file with a non-shell tool."
    )


def _r8_budget_denial() -> NoReturn:
    deny(
        "Mastermind shared-placement guard: guard budget exceeded — fail "
        f"closed. Judging this command took longer than {r8_watchdog_seconds():g} s "
        "(the hook's budget inside the provider's 10 s timeout, after which a "
        "killed hook would not block), so it is refused. Run a shorter, "
        "plain command; write long content to a file with a non-shell tool."
    )


def main() -> None:
    # r9 (REVIEW4 F4, choice (a)): the watchdog runs in EVERY session. Armed:
    # exactly r8 — firing is a fail-closed DENY. Unarmed: firing is NO
    # DECISION (exit 0, nothing written — never an allow), so adversarial
    # CI-wait text (``gh …`` + newline/``do`` runs, heredoc markers) no
    # longer stalls an unarmed hook into the provider's 10 s timeout, which
    # the ``onFailure: "block"`` row turns into a blocked tool call.
    armed = shared_placement_armed()
    _R10_UNARMED_SCOPE[0] = "unset"
    previous = _r8_arm_watchdog()
    try:
        _main_body()
        # Disarmed inside the try: an alarm landing between the verdict and
        # here is still a budget firing (armed: fail-closed denial; unarmed:
        # see below), never a traceback.
        _r8_disarm_watchdog()
    except _R8BudgetExceeded:
        if armed:
            _r8_budget_denial()
        # r10 (REVIEW5 N2): unarmed, a firing on a command that names a
        # wrapper (or whose scope reading had not finished) is a DENY; any
        # other unarmed firing is no decision — return normally.
        if _R10_UNARMED_SCOPE[0] is True or _R10_UNARMED_SCOPE[0] == "pending":
            _r10_unarmed_budget_denial()
    finally:
        _r8_disarm_watchdog()
        if previous is not None:
            signal.signal(signal.SIGALRM, previous)


def _main_body() -> None:
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

    try:
        if tool == "Bash":
            guard_bash(payload, tool_input)
            return

        if tool in ("Agent", "Task") and is_project_scope(payload):
            guard_native_child(tool_input)
    except Exception as error:  # noqa: BLE001 — a crashed hook does not block
        # r7: an unexpected guard failure must not fail OPEN for an armed
        # session (the provider treats a crashed hook as non-blocking).
        if shared_placement_armed():
            deny(
                "Mastermind shared-placement guard: internal guard error "
                f"({type(error).__name__}) while judging this command; refused "
                "fail-closed. Report the command to the guard owner."
            )
        raise


if __name__ == "__main__":
    main()
