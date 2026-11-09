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
#: ``${NAME…op`` openings (bash and zsh parameter operators, zsh ``(flags)``
#: and the empty name ``${:-…}``): for SCOPE only, the opening is read as a
#: space so the operator's literal word (``${x:-pool}``) is visible.
_R7_PARAM_OPERATOR_RE = re.compile(
    r"\$\{(?:\([^()]*\))?[#!]?(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])?"
    r"(?:\[[^\]]*\])?(?::?[-=+?]|//?|/[#%]|##?|%%?|\^\^?|,,?|:)"
)
#: A wrapper name glued to a short option (``git grep -O'pool run …'``,
#: ``-Opool``): the option letter hides the name from ``_WRAPPER_NAME_RE``.
#: (Single quantifier per alternative: linear on long words — a slow hook is
#: killed by the provider and a killed hook does not block.)
_R7_GLUED_OPTION_RE = re.compile(
    r"(?<![A-Za-z0-9_.])-[A-Za-z](?:[A-Za-z0-9_./-]*/|[A-Za-z]*)"
    r"(?:pool|sub\.sh|remote_sub\.sh|slot\.py)(?![A-Za-z0-9_.-])",
    re.I,
)
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
) -> tuple:
    """A closed option grammar: (short flags, short options taking a value,
    long flags, long options taking a value)."""
    return (
        frozenset(short_flags), frozenset(short_valued),
        frozenset(long_flags), frozenset(long_valued),
    )


_R7_GIT_DIFF_LONG_FLAGS = (
    "--stat", "--shortstat", "--numstat", "--name-only", "--name-status",
    "--patch", "--no-patch", "--raw", "--color", "--no-color",
    "--no-ext-diff", "--no-textconv", "--ignore-all-space",
    "--ignore-space-change", "--word-diff", "--summary", "--check",
    "--find-renames", "--no-renames", "--full-index", "--compact-summary",
    "--patch-with-stat", "--abbrev",
)
_R7_GIT_DIFF_LONG_VALUED = (
    "--unified", "--stat", "--color", "--word-diff", "--diff-filter",
    "--abbrev", "--relative",
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
        "pusMRwbiEFPC0123456789", "nSGUL",
        _R7_GIT_DIFF_LONG_FLAGS + _R7_GIT_LOG_LONG_FLAGS,
        _R7_GIT_DIFF_LONG_VALUED + (
            "--max-count", "--skip", "--since", "--after", "--until",
            "--before", "--author", "--committer", "--grep", "--format",
            "--pretty", "--date", "--decorate",
        ),
    ),
    "show": _r7_spec(
        "pusMRwb", "U",
        _R7_GIT_DIFF_LONG_FLAGS + ("--oneline", "--abbrev-commit", "--no-notes"),
        _R7_GIT_DIFF_LONG_VALUED + ("--format", "--pretty", "--date"),
    ),
    "diff": _r7_spec(
        "pusMRwb", "U",
        _R7_GIT_DIFF_LONG_FLAGS + (
            "--cached", "--staged", "--merge-base", "--exit-code", "--quiet",
            "--no-index", "--minimal", "--histogram", "--patience",
        ),
        _R7_GIT_DIFF_LONG_VALUED,
    ),
    "status": _r7_spec(
        "sbv", "u",
        ("--short", "--branch", "--porcelain", "--long", "--verbose",
         "--ignored", "--no-renames", "--ahead-behind", "--no-ahead-behind",
         "--show-stash"),
        ("--porcelain", "--untracked-files", "--ignored"),
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
_R6_COMPUTED_RE = re.compile(
    r"\$\{[^{}]*\}|\$\([^()]*\)|`[^`]*`|\$\[[^\]]*\]"
    r"|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]"
)
_R6_ROUGH_WORD_SPLIT_RE = re.compile(r"[\s;&|<>()\"'\\]+")
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
            digits = re.match(r"[0-7]{1,3}", body[index + 1:]).group(0)
            out.append(chr(int(digits, 8) & 0xFF))
            index += 1 + len(digits)
            continue
        if escape in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[escape]
            digits_match = re.match(rf"[0-9A-Fa-f]{{1,{width}}}", body[index + 2:])
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


def _r7_glob_atom_matches(atom: tuple, char: str) -> bool:
    if atom[0] == "?":
        return True
    if atom[0] == "lit":
        return atom[1] == char
    body, negate = atom[1], atom[2]
    hit = False
    index = 0
    while index < len(body):
        if index + 2 < len(body) and body[index + 1] == "-":
            hit = hit or body[index] <= char <= body[index + 2]
            index += 3
        else:
            hit = hit or body[index] == char
            index += 1
    return hit != negate


def _r7_glob_match(name: str, pattern: str) -> bool:
    """fnmatch-style ``*``/``?``/``[set]`` matching by a position-set walk,
    O(len(pattern) * len(name)). r7 replaces ``fnmatch`` here: its regex
    translation backtracks catastrophically on patterns like ``*?*?*?…``
    (a slow hook is killed and does not block)."""
    atoms: list[tuple] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if not atoms or atoms[-1] != ("*",):
                atoms.append(("*",))
            index += 1
            continue
        if char == "?":
            atoms.append(("?",))
            index += 1
            continue
        if char == "[":
            body_at = index + 1
            if body_at < len(pattern) and pattern[body_at] in "!^":
                body_at += 1
            if body_at < len(pattern) and pattern[body_at] == "]":
                body_at += 1
            close = pattern.find("]", body_at)
            if close >= 0:
                body = pattern[index + 1:close]
                negate = body[:1] in ("!", "^")
                atoms.append(("set", body[1:] if negate else body, negate))
                index = close + 1
                continue
        atoms.append(("lit", char))
        index += 1
    if sum(1 for atom in atoms if atom != ("*",)) > len(name):
        return False
    positions = {0}
    for atom in atoms:
        if atom == ("*",):
            positions = set(range(min(positions), len(name) + 1))
            continue
        positions = {
            position + 1 for position in positions
            if position < len(name) and _r7_glob_atom_matches(atom, name[position])
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
    """
    text = raw.replace("\\\n", "")
    text = _R6_ANSI_C_RE.sub(lambda match: _r6_decode_ansi_c(match.group(1)), text)
    widened = re.sub(
        r"[\"'\\]", "", _R7_PARAM_OPERATOR_RE.sub(" ", text).replace('$"', '"')
    )
    if _WRAPPER_NAME_RE.search(widened) or _R7_GLUED_OPTION_RE.search(widened):
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
    return False


class _R6Word:
    """One shell word as typed segments: ``lit`` (unquoted), ``sq``, ``dq``,
    ``esc`` (fixed text) and ``param``/``arith``/``cmdsub``/``ansi``/
    ``locale`` (computed or re-decoded at runtime)."""

    __slots__ = ("segments",)

    def __init__(self) -> None:
        self.segments: list[tuple[str, str]] = []

    def add(self, kind: str, text: str) -> None:
        if kind == "lit" and self.segments and self.segments[-1][0] == "lit":
            self.segments[-1] = ("lit", self.segments[-1][1] + text)
        else:
            self.segments.append((kind, text))

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
    seen: set[str] = set()
    index = 0
    while index < len(words):
        value = words[index].value
        if value == "--":
            break
        if value.startswith("--"):
            name, equals, _ = value.partition("=")
            if equals:
                if name not in long_valued:
                    return value, seen
            elif name in long_flags:
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
         if word.literal and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", word.value)),
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
    # Leading/trailing newlines are whitespace, not another command.
    while separators and separators[0] == "\n" and units[0].empty():
        units.pop(0)
        separators.pop(0)
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
    first_words: dict[int, tuple[int, int]] = {}

    def head_at(offset: int) -> str:
        count = bisect.bisect_right(separator_ends, offset)
        unit_start = separator_ends[count - 1] if count else 0
        if unit_start not in first_words:
            following = bisect.bisect_left(separator_starts, unit_start)
            unit_end = (
                separator_starts[following]
                if following < len(separator_starts) else len(canon)
            )
            first_words[unit_start] = (len(canon), len(canon))
            for word in _SHELL_WORD_RE.finditer(canon, unit_start, unit_end):
                text = word.group(0)
                if text in _COMMAND_PREFIX_WORDS or _ASSIGNMENT_WORD_RE.match(text):
                    continue
                first_words[unit_start] = word.span()
                break
        position, end = first_words[unit_start]
        if position >= offset:
            return ""
        return canon[position:min(end, offset)].rsplit("/", 1)[-1].lower()

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
                or re.fullmatch(r"-[A-Za-z]*[iS][A-Za-z]*", word)
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
    for match in occurrence.finditer(canon):
        start, end = match.span()
        if canon.startswith("=", end):
            value = _IDENTITY_VALUE_RE.match(canon, end).group(1)
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


def _guard_armed_launch(command: str, raw: str) -> None:
    """r7 armed gate (WO-11; REVIEW2 A1). The PARSE decides: out of scope
    (names no wrapper) → nothing to judge; refused shape → deny; closed read
    forms only → no unit executes a wrapper; otherwise EVERY wrapper-head
    unit reaches the binding gate — there is no early return for it."""
    parse = r7_parse(
        raw,
        force=bool(FABRIC_LAUNCH_RE.search(raw) or _wrapper_invocations(raw)),
    )
    if parse is None:
        return
    if parse.refused:
        deny(_r6_reason(parse.codes, launch_like=parse.launch_like))
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
        clean = strip_heredocs(command)
    else:
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
