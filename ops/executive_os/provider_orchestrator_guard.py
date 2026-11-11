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
Runtime-multiplexed launches (for/while/until bodies AND their condition
headers, xargs/parallel/find -exec, brace groups, brace- and paren-bodied
function definitions, quote-aware trap programs, watch/timeout repeaters)
are refused as unaccounted descendants. When a wrapper name is present,
every interpreter invocation (the python/pypy/perl/ruby/node/php/Rscript/
R/sqlite3/tclsh/lua/deno/bun/julia/pwsh/jshell/java/osascript/awk/jq
families — flags, script files, stdin programmes and versioned/hyphenated
spellings alike), eval/source/. and every computed ($/backtick) or
shell-EXPANDED word outside an assignment (a glob, a brace expansion, an
extglob pattern) are refused as unobservable: the word, and therefore the
wrapper, its mode and its identity, become readable only at expansion
time. With no wrapper token in the text, an expanded word in COMMAND
position — the head itself or a transparent runner's payload
(env poo[l] …) — is refused for the same reason. POSIX
line-continuation splits are canonicalised so no constructed path escapes
the gate.
WO-11 r7 FAIL-CLOSED POSTURE (REVIEW_2329 r5, orchestrator-endorsed): an
ARMED command that carries a wrapper token — literal, or a shell-expanded
WRAPPER-SHAPED word at a position the guard cannot reduce to a plain data
argument — is admitted only when it fully reduces to a known-safe shape:
every word canonical, every command head recognized (wrapper, transparent
runner, shell keyword/builtin, data-only utility, shell), every span
parseable. Anything ambiguous is refused with a precise reason — an
unlisted runner (timeout/watch/strace/… or any word never enumerated), a
shell program (bash -c 'poo* run …'), an attached --flag=value, an
unlisted interpreter (R/sqlite3/jshell/groovy/…), a function call, a
do/done pair inside a loop condition, a concatenated trap program.
Refusing the irreducible replaces enumerating escape spellings: five
review rounds showed the shell surface always outruns a vocabulary, so
correctness no longer depends on the runner/interpreter lists' completeness.
WO-11 r8 POSTURE CLOSURE (REVIEW_2329 r6 B-R6-1/B-R6-2/M-R6-1): a GLUED
``<(…``/``>(…``/``$(…`` word is a process/command substitution — bash
runs the payload in a subshell — so the payload is an EXECUTED construct
that receives the full armed posture, alone and beside a faithful launch
alike (it used to be skipped as a redirection by every scanner); and a
shell keyword/prefix head (if/while/until/elif/!/time/…) does not OCCUPY
its segment's command slot, so the word the shell executes after it — an
if/while/until/elif/! CONDITION — is judged at command position and
wrapper-shape-checked as the head itself (the ``time`` transparent-runner
entry is thereby optimization-only, verified by a list-emptied pin).
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
#: Interpreters execute a PROGRAM the guard cannot read: ``-c``/``-e``/``-p``
#: one-liners, a script file, or a program fed on stdin. A wrapper name
#: anywhere in the command therefore makes EVERY interpreter invocation
#: unobservable — flag-independent by design (REVIEW_2329 r3 B-1): the r4
#: allowlist missed ``-Sc``/``-we``/``-E``/``-p``/``--eval``/``-ne``/``-nr``
#: and stdin-fed programs, each of which launched with zero binding checks.
#: r4 B-3: the list is FAMILIES with versioned/hyphenated tails
#: (``python3-3.12``, ``pypy3.10``, ``perl-5.38``, ``node-20``,
#: ``tclsh8.6``), not a closed spelling list — an unlisted spelling with an
#: argv-list program (``subprocess.run(["pool","run","grok",…])``) formed no
#: literal ``pool run`` sequence and launched with zero validation. The
#: trailing boundary also excludes ``/`` so a PATH-shaped word
#: (``node_modules/.bin/pool``, ``python3.12/bin``) is not an interpreter
#: word: only the final path segment can name the interpreter.
#: r5 M-3 extends the families with the probed spellings (``R``,
#: ``sqlite3``/``.read``, ``jshell``/``java``) so they get the precise
#: interpreter reason; closure no longer depends on this list — an
#: unlisted interpreter (groovy/scala/octave/gnuplot/dotnet/mono/erl/make)
#: is an UNRECOGNIZED HEAD under the r7 posture and is refused by
#: :func:`_unrecognized_head_word`.
_INTERPRETER_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?:python[23]?(?:[.-]\d+)*[a-z]?|pypy[23]?(?:[.-]\d+)*[a-z]?"
    r"|perl(?:[-0-9.]+)?|ruby(?:[-0-9.]+)?|node(?:js)?(?:[-0-9.]+)?"
    r"|php(?:[-0-9.]+)?|Rscript|tclsh(?:[0-9.]+)?|lua(?:[0-9.]+)?"
    r"|deno|bun|julia|pwsh|osascript|awk|gawk|mawk|nawk|jq"
    r"|R|sqlite3|jshell|java|groovy|scala|octave|gnuplot|dotnet|mono|erl)"
    r"(?![A-Za-z0-9_./-])"
)
#: A command word the SHELL expands before executing it: a glob (``pool*``,
#: ``poo[l]``, ``su?.sh``) or a brace expansion (``po{o,}l``). The word, and
#: therefore the wrapper it becomes, its mode and its identity, are readable
#: only at expansion time (REVIEW_2329 r4 B-2: ``pool* run grok`` reached the
#: no-launch early return with zero binding validation and launched a
#: substituted paid child). ``~`` is deliberately NOT here: a tilde prefix
#: only rewrites the path, so the wrapper basename stays literal and the
#: launch is still observed by :data:`_WRAPPER_RE`.
_GLOB_CHARS = "*?["
#: Extglob openers (``?(…)``/``*(…)``/``+(…)``/``!(…)``/``@(…)``): an extglob
#: word (``po+(o)l`` — REVIEW_2329 r5 m-1) is expansion-dependent. Extglob
#: needs a prior ``shopt -s extglob``, but persistent sessions are inside
#: this gate's threat model, so the word is treated as expanded (conservative
#: in the refusing direction).
_EXTGLOB_OPENER_RE = re.compile(r"[?*+!@]\(")
_BRACE_EXPANSION_RE = re.compile(r"\{[^{}]*,[^{}]*\}|\{[^{}]*\.\.[^{}]*\}")
#: Transparent runners: the payload after the runner chain is the command
#: the shell executes, so that payload is a COMMAND position for the
#: expansion-dependent scan (REVIEW_2329 r6 re-review B-3: ``env poo[l] run
#: grok`` was ALLOW — the expansion-dependent wrapper sat at argument
#: position behind ``env``, where neither the head-only scan nor the
#: wrapper-token scan looked, and live-confirmed reached the wrapper with
#: zero binding validation). Path spellings (``/usr/bin/env``) match by
#: basename.
_TRANSPARENT_RUNNERS = frozenset(
    {"env", "sudo", "nice", "nohup", "exec", "time", "command", "xargs"}
)
#: r7 note (REVIEW_2329 r5 B-1a): this list is an OPTIMIZATION, not the
#: boundary. Runners whose argument grammar is NOT modeled here (``timeout``
#: takes a bare duration before its payload, ``watch``/``strace``/
#: ``setsid``/``stdbuf``/``arch``/``script`` take flags the tables do not
#: know) are deliberately NOT added: modeling each grammar is the
#: enumeration that five review rounds showed always loses to the shell
#: surface. Instead such a head is UNCLASSIFIABLE and every word after it
#: sits at an unprovable position — :func:`_unprovable_position_word`
#: refuses a wrapper-shaped expanded word there, with or without a wrapper
#: token in the text. Correctness does not depend on this list's
#: completeness — r8 (REVIEW_2329 r6 M-R6-1): that claim is now true for
#: EVERY entry, ``time`` included. The r6 scratch falsification showed
#: ``time`` was load-bearing: a keyword head consumed the command slot in
#: :func:`_expanded_command_word` and the promoted head was never
#: wrapper-shape-checked in :func:`_unprovable_position_word`, so removing
#: the entry lost the token-free ``time poo? …`` refusal. Since r8 both
#: scanners judge the word that FOLLOWS a skipped keyword/prefix head, so
#: ``<keyword> <expanded-wrapper-word>`` refuses whether or not the
#: keyword is listed here (pinned by
#: ``test_r8_mr61_time_entry_is_optimization_only``).
#: Runner flags that CONSUME the following word as their own argument
#: (``sudo -u root …``, ``nice -n 5 …``): without this the consumed
#: argument would be mistaken for the runner's payload command.
_RUNNER_ARG_FLAGS: dict[str, frozenset[str]] = {
    "env": frozenset({"-S", "-u", "--split-string", "--unset"}),
    "sudo": frozenset(
        {
            "-C", "-U", "-g", "-p", "-u",
            "--chdir", "--close-from", "--group", "--host",
            "--login-user", "--other-user", "--prompt", "--role",
            "--type", "--user",
        }
    ),
    "nice": frozenset({"-n", "--adjustment"}),
    "exec": frozenset({"-a", "--argv0"}),
    "time": frozenset({"-f", "-o", "--format", "--output"}),
    "xargs": frozenset(
        {
            "-E", "-I", "-L", "-P", "-S", "-d", "-j", "-n", "-s",
            "--arg-file", "--max-args", "--max-chars", "--max-procs",
            "--separator",
        }
    ),
}
#: r7 FAIL-CLOSED posture (REVIEW_2329 r5, orchestrator-endorsed): for an
#: ARMED session, a command that contains a wrapper token — a literal
#: wrapper name anywhere, or a shell-expanded WRAPPER-SHAPED word at a
#: position the guard cannot reduce to a plain data argument — is admitted
#: only if it fully reduces: every word canonical, every command head
#: recognized, every span parseable. Anything ambiguous is refused with a
#: precise reason instead of enumerating escape spellings. The vocabularies
#: below are optimizations (precise reasons, precise flag grammar):
#: correctness no longer depends on their completeness, because an
#: unclassifiable head makes every word after it unprovable and the command
#: is refused.
_WRAPPER_BASENAMES = frozenset({"pool", "sub.sh", "remote_sub.sh", "slot.py"})
#: Shell keywords that can head a simple-command segment.
_SHELL_KEYWORDS = frozenset({
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "in", "function", "select", "coproc", "time",
    "{", "}", "!", "[[", "]]",
})
#: Shell builtins that never execute a program argument. ``eval``/``source``/
#: ``.`` are DELIBERATELY absent: with a wrapper token present they are
#: refused earlier as unobservable (``_UNOBSERVABLE_ANYWHERE_RE``), and if
#: an unusual spelling ever reached the head scan it is refused as
#: unrecognized — fail-closed either way.
_SHELL_BUILTINS = frozenset({
    ":", "echo", "printf", "true", "false", "test", "[", "cd", "pwd",
    "pushd", "popd", "dirs", "export", "unset", "local", "declare",
    "typeset", "readonly", "shift", "umask", "read", "wait", "trap", "set",
    "shopt", "hash", "type", "builtin", "let", "getopts", "break",
    "continue", "exit", "return", "kill", "jobs", "fg", "bg", "disown",
    "times", "ulimit", "history", "alias", "unalias", "enable", "mapfile",
    "readarray", "caller",
})
#: Data-only utilities: their arguments are never executed as programs.
#: ``sed`` (``e``/``r`` commands execute), ``find``/``xargs``/``parallel``
#: (``-exec``/payload), ``awk`` (an interpreter family) and every
#: interpreter are deliberately NOT here. ``trap`` is handled specially:
#: its program argument RUNS on signal delivery, so it is executed
#: position, not data.
_SAFE_DATA_HEADS = frozenset(
    _INSPECTORS | {
        "cp", "mv", "rm", "ln", "mkdir", "rmdir", "touch", "chmod",
        "chown", "chgrp", "install", "date", "du", "df", "ps", "id",
        "uname", "hostname", "whoami", "groups", "basename", "dirname",
        "realpath", "readlink", "sort", "uniq", "cut", "tr", "tee",
        "split", "seq", "sleep", "yes", "pkill", "killall", "cksum",
        "base64", "git", "gh", "curl", "wget", "tar", "zip", "unzip",
        "gzip", "gunzip", "xz",
    }
)
#: Shells: a recognized HEAD when a wrapper token is present (their program
#: text is canon-visible — quotes stripped — so a literal launch inside is
#: observed and judged by every other rule), but deliberately NOT a
#: safe-data head for the token-free position classifier: a ``-c``/``-s``
#: program is executed by the child shell, so every word after a shell
#: head is at an unprovable position (REVIEW_2329 r5 B-1c).
_SHELL_HEADS = frozenset({"bash", "sh", "dash", "ksh", "zsh", "ash"})
#: Every head the wrapper-present posture admits.
_RECOGNIZED_HEADS = frozenset(
    _WRAPPER_BASENAMES | _TRANSPARENT_RUNNERS | _SAFE_DATA_HEADS
    | _SHELL_BUILTINS | _SHELL_KEYWORDS | _SHELL_HEADS
)
#: Loop structure words, recognised only at COMMAND position (the head of a
#: simple command). ``do``/``done`` as ARGUMENTS (``echo do``, ``grep -q do
#: f``, ``"$x" = "do"``) are data; a ``do``/``done`` PAIR inside a while
#: condition (``while echo do echo done; L; do :; done``) used to truncate
#: BOTH the condition span (which ended at the first ``do`` word, an
#: argument of ``echo``) and the body span (first ``do`` to first
#: ``done``, both arguments), leaving the launch outside every span while
#: the loop live-ran it once per iteration (REVIEW_2329 r5 M-1, live 3
#: launches). :func:`_loop_spans` walks the command-position structure with
#: a do/done stack instead of pattern-matching words anywhere.
_LOOP_STRUCT_KEYWORDS = frozenset(
    {"while", "until", "do", "done", "for", "select"}
)
#: Paren-bodied function definitions ``name() ( … )`` / ``function f () (
#: … )``: the body runs zero-or-many times but carries no brace, so the
#: brace span never covered it (REVIEW_2329 r4 M-A2). Only a FUNCTION body
#: matches: a plain subshell group ``( launch )`` runs exactly once and
#: stays allowed. r5 M-1: the definition is matched on the RAW text —
#: newlines and comments between ``()`` and the body are legal bash
#: (``f()\n( L )``, ``f() # c\n( L )``), and a quoted ``")"`` inside the
#: body must not close the span early — canon, which deletes the quotes,
#: got all three wrong. :func:`_paren_body_spans_raw` walks the raw body
#: quote-aware and maps the span into canon coordinates via
#: :func:`_canonical_command_map`.
_FUNCTION_DEF_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[ \t]*\([ \t]*\)")
_TRAP_WORD_RE = re.compile(r"(?<![A-Za-z0-9_.-])trap(?=\s)")
_STATEMENT_END_RE = re.compile(r"[;&|\n]")
#: Batch executors that run their argument command once per input item
#: (REVIEW_2329 r2 N-2/C2-C3, find -exec).
_BATCH_EXECUTOR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?:xargs|parallel|find)\b[^;&|\n]*",
    re.I,
)
#: Repeaters: the following command runs more than once (or, for
#: ``timeout --foreground``, is a signal-forwarding wrapper the reviewer
#: grouped with repeaters). One binding covers one attempt (REVIEW_2329 r3 M-A).
_REPEATER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?watch\b[^;&|\n]*"
    r"|(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?timeout\s+"
    r"(?:-[A-Za-z]*f[A-Za-z]*\b|--foreground\b)[^;&|\n]*",
    re.I,
)
#: ``eval``/``source``/``.`` as a WORD anywhere in the text. Inside a
#: nested shell (``bash -c 'eval "$X$Y"; pool run ...'``) these words follow
#: a space after canonicalisation, so the separator-anchored
#: ``_UNOBSERVABLE_ENV_RE`` never saw them (REVIEW_2329 r3 M-B). Applied
#: wherever a wrapper name/launch is present.
_UNOBSERVABLE_ANYWHERE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:eval|source)(?![A-Za-z0-9_.-])"
    r"|(?:(?<=[\s;&|(`{])|^)\.(?=[\s;&|)`}]|$)"
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


def _canonical_command_map(command: str) -> tuple[str, list[int]]:
    """``_canonical_command`` plus a raw-offset index.

    ``raw_index[i]`` is the offset in ``command`` that produced canon[i] and
    ``raw_index[len(canon)] == len(command)``, so a span measured on the RAW
    text (where quoting is still visible) can be mapped into the canon
    coordinates every other span and wrapper offset uses."""
    out: list[str] = []
    raw_index: list[int] = []
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        if char == "\\" and index + 1 < length and command[index + 1] == "\n":
            index += 2
            continue
        if char in "\"'\\":
            index += 1
            continue
        out.append(char)
        raw_index.append(index)
        index += 1
    raw_index.append(length)
    return "".join(out), raw_index


def _expansion_dependent(word: str) -> bool:
    """True when the shell expands ``word`` before it becomes a command word:
    a glob (``*``, ``?``, ``[...]``), a brace expansion (``{a,b}``,
    ``{1..2}``) (REVIEW_2329 r4 B-2), or an extglob pattern (``po+(o)l``,
    ``su@(b).sh`` — REVIEW_2329 r5 m-1: the paren split in the word scanners
    used to dismember ``po+(o)l`` into ``po+``/``o``/``l``, none of which
    looked expanded). Extglob needs a prior ``shopt -s extglob``, but
    persistent sessions are inside this gate's threat model, so an
    extglob-shaped word is treated as expanded — conservative in the
    refusing direction."""
    if any(char in word for char in _GLOB_CHARS):
        return True
    if _EXTGLOB_OPENER_RE.search(word):
        return True
    return bool(_BRACE_EXPANSION_RE.search(word))


def _scan_command_words(canon: str) -> list[tuple[str, bool]]:
    """Every non-assignment, non-redirection word with its head flag.

    ``is_head`` marks the first such word of a simple command — the position
    where the shell would execute it as a command name. Segments split on
    ``;&|`` and newlines ONLY, and bare ``(``/``)``/``{``/``}`` grouping
    tokens are skipped: splitting on parentheses used to dismember extglob
    words (``po+(o)l`` → ``po+``/``o``/``l``, none of which looked expanded
    — REVIEW_2329 r5 m-1), so a word's parentheses now stay glued to it and
    a subshell- or brace-wrapped head is still found."""
    scan: list[tuple[str, bool]] = []
    for segment in re.split(r"[;&|\n]", canon):
        head_seen = False
        for word in segment.split():
            if word in ("(", ")", "{", "}"):
                continue  # grouping tokens, not words
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
                continue  # an assignment: its value is not a command word
            if word[0] in "<>" or re.match(r"\d*[<>]", word):
                continue  # a redirection operator
            scan.append((word, not head_seen))
            head_seen = True
    return scan


def _computed_command_word(canon: str) -> str | None:
    """The first shell word computed or expanded at runtime (``$P``,
    ``${P}``, ``$(...)``, a backtick word, a glob or a brace expansion) in a
    non-assignment position — or None.

    Structural, not positional (REVIEW_2329 r3 B-1): the r4 scan skipped a
    fixed runner vocabulary (``env``/``exec``/``time``/…), so any runner not
    on that list — ``sudo``, ``caffeinate``, ``script``, ``strace``,
    ``flock``, ``ssh host``, ``su -c``, a ``{ … }`` group — carried the
    computed launch past the gate. The guard therefore treats EVERY
    ``$``/backtick word outside an assignment as the command word it cannot
    read. Conservative by design: with a wrapper name in the text, a computed
    argument is refused too (documented over-refusal).

    Expansion-dependent words (glob/brace) are refused the same way in any
    position, because ``sudo pool* run grok`` reaches the wrapper only after
    the shell expands it (REVIEW_2329 r4 B-2)."""
    for word, _ in _scan_command_words(canon):
        if word[0] in "$`" or _expansion_dependent(word):
            return word
    return None


def _expanded_command_word(canon: str) -> str | None:
    """The first glob/brace/extglob-expanded word in COMMAND position — or
    None.

    This is the only class refused when NO wrapper token is in the text:
    ``su?.sh`` and ``poo*`` are wrapper names that exist only after
    expansion, so no literal token survives to trigger the scan above
    (REVIEW_2329 r4 B-2/G3). It is deliberately scoped to the command word:
    an argument glob (``ls tests/*.py``) is not this gate's business.

    COMMAND position includes the payload of a transparent runner chain
    (``env``, ``sudo``, ``nice``, ``exec``, ``time``, ``command``, ``xargs``,
    ``nohup`` and their path spellings): ``env poo[l] run grok`` and ``sudo
    -u root poo? run grok`` were ALLOW because the expanded wrapper sat at
    argument position behind the runner (REVIEW_2329 r6 re-review B-3,
    live-confirmed against the real wrapper). Runner flags that consume an
    argument (``sudo -u root``, ``nice -n 5``) skip theirs so the payload,
    not the flag's argument, is the word judged; a flag with an ATTACHED
    ``=value`` consumes no further word — ``sudo --user=root poo[l] …`` used
    to feed the payload to the flag and escape (REVIEW_2329 r5 B-1b, a
    two-line bug).

    r5 B-1a/r7: the runner list above is an OPTIMIZATION, not the boundary.
    This function still returns None behind runners it does not know
    (``timeout 5 poo[l] …``, ``nohup timeout 5 poo[l] …``); the fail-closed
    classifier :func:`_unprovable_position_word` then refuses the
    wrapper-shaped word at the unclassifiable position. Segments split on
    ``;&|`` and newlines ONLY (r5 m-1: splitting on parentheses used to
    dismember extglob heads like ``po+(o)l``); bare ``(``/``)``/``{``/``}``
    grouping tokens are skipped when hunting the head, so a subshell- or
    brace-wrapped glob head (``( poo* run … )``, ``{ poo* run …; }``) is
    still a command position.
    """
    for segment in re.split(r"[;&|\n]", canon):
        runner: str | None = None
        expect_arg = False
        command_seen = False
        for word in segment.split():
            if word in ("(", ")", "{", "}"):
                continue  # a subshell/brace grouping token, not a word
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
                continue  # an assignment (prefix or env NAME=value)
            if word[0] in "<>" or re.match(r"\d*[<>]", word):
                continue  # a redirection operator
            if expect_arg:
                expect_arg = False
                continue  # consumed as the runner flag's own argument
            if word.startswith("-"):
                flag = word.split("=", 1)[0]
                if (
                    runner is not None
                    and flag in _RUNNER_ARG_FLAGS.get(runner, frozenset())
                    and "=" not in word  # an attached =value consumes none
                ):
                    expect_arg = True
                continue  # a flag: never a command word
            base = word.rsplit("/", 1)[-1]
            if not command_seen and base in _TRANSPARENT_RUNNERS:
                runner = base  # transparent: its payload is the command
                continue
            if not command_seen and (
                base in _COMMAND_PREFIX_WORDS or base in _SHELL_KEYWORDS
            ):
                # r8 (REVIEW_2329 r6 B-R6-2/M-R6-1): a shell keyword or
                # command-prefix word HEADS a segment but does not OCCUPY
                # its command slot — the shell executes the word that
                # follows it (``if poo* run …; then``, ``while poo* …``,
                # ``! poo* …``, ``elif poo* …``). Letting the keyword set
                # ``command_seen`` left the expansion-dependent wrapper in
                # the condition position unjudged; skipping it keeps that
                # word in COMMAND position. This also makes the ``time``
                # entry in _TRANSPARENT_RUNNERS optimization-only: with it
                # removed, ``time`` is still skipped here (it is a shell
                # keyword) and the payload word is still judged.
                continue
            if not command_seen and _expansion_dependent(word):
                return word  # a head, or a runner chain's payload command
            command_seen = True  # this segment's command word is now fixed
            runner = None
    return None


def _read_pattern_group(pattern: str, open_index: int) -> tuple[str, int]:
    """The text inside the parenthesised group starting at ``open_index``
    and the index just past its closing paren (nested groups counted;
    running to the end of the pattern when unterminated)."""
    depth = 0
    index = open_index
    while index < len(pattern):
        char = pattern[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pattern[open_index + 1 : index], index + 1
        index += 1
    return pattern[open_index + 1 :], len(pattern)


def _split_pattern(text: str, separator: str) -> list[str]:
    """Split ``text`` on ``separator`` at group depth zero."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "({":
            depth += 1
        elif char in ")}":
            depth -= 1
        if char == separator and depth <= 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _matching_pattern_brace(pattern: str, open_index: int) -> int:
    """The index of the ``}`` matching the ``{`` at ``open_index``, or -1."""
    depth = 0
    for index in range(open_index, len(pattern)):
        char = pattern[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _translate_shell_pattern(pattern: str) -> str:
    """Translate a shell pattern (glob, brace expansion, extglob) into a
    regular-expression source matching exactly the words it can expand to.

    ``*`` does not cross ``/``; ``[...]`` classes, ``{a,b}`` alternations and
    single-character ``{x..y}`` ranges are translated; extglob groups
    ``?(…)``/``*(…)``/``+(…)``/``@(…)`` become optional / star / plus /
    exactly-one groups. Constructs that cannot be translated precisely
    (``!(…)`` negation, unparseable classes, wide ranges) over-approximate
    to ``.*`` or ``.`` so the can-match test stays conservative in the
    REFUSING direction."""
    out: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char in "?*+!@" and index + 1 < length and pattern[index + 1] == "(":
            body, index = _read_pattern_group(pattern, index + 1)
            subs = "|".join(
                _translate_shell_pattern(part)
                for part in _split_pattern(body, "|")
            )
            if char == "?":
                out.append(f"(?:{subs})?")
            elif char == "*":
                out.append(f"(?:{subs})*")
            elif char == "+":
                out.append(f"(?:{subs})+")
            elif char == "@":
                out.append(f"(?:{subs})")
            else:  # !(…): a negative pattern — over-approximate to any text
                out.append("(?:.*)")
            continue
        if char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append(".")
            index += 1
        elif char == "[":
            close = pattern.find("]", index + 1)
            if close < 0:
                out.append(re.escape(char))
                index += 1
                continue
            body = pattern[index + 1 : close]
            negative = body[:1] in ("!", "^")
            if negative:
                body = body[1:]
            if not body or "\\" in body or "[" in body:
                out.append(".")  # unparseable class: any single char
            else:
                if not negative and body[0] == "^":
                    body = "\\" + body
                out.append(("[^" if negative else "[") + body + "]")
            index = close + 1
        elif char == "{":
            close = _matching_pattern_brace(pattern, index)
            if close < 0:
                out.append(re.escape(char))
                index += 1
                continue
            inner = pattern[index + 1 : close]
            if ".." in inner:
                low, _, high = inner.partition("..")
                if (
                    len(low) == 1
                    and len(high) == 1
                    and ("a" <= low <= high or "0" <= low <= high or low == high)
                ):
                    out.append(f"[{low}-{high}]")
                else:
                    out.append("(?:.*)")  # untranslatable range: any text
            else:
                subs = "|".join(
                    _translate_shell_pattern(part)
                    for part in _split_pattern(inner, ",")
                )
                out.append(f"(?:{subs})")
            index = close + 1
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


def _pattern_can_match(pattern: str, target: str) -> bool:
    """True when the shell ``pattern`` can expand to exactly ``target``."""
    try:
        regex = re.compile(_translate_shell_pattern(pattern))
    except re.error:
        return True  # untranslatable: assume it can (fail closed)
    return regex.fullmatch(target) is not None


def _wrapper_shaped(word: str) -> bool:
    """True when ``word``, read as a shell pattern, can expand to a wrapper
    basename (``pool``, ``sub.sh``, ``remote_sub.sh``, ``slot.py``) — the
    word may BE the paid wrapper after expansion, wherever it sits. The
    basename (final ``/`` segment) is the unit because a glob never crosses
    ``/`` and every launch shape admits any path prefix. Glued fragments
    (``system(poo*``, ``--flag=po*``) are tested too: inside a program
    string or attached flag value the CHILD shell re-expands them
    (REVIEW_2329 r5 B-1c)."""
    candidates = [word] + [
        fragment for fragment in re.split(r"[()\[\]\"',=]", word) if fragment
    ]
    for candidate in candidates:
        if not _expansion_dependent(candidate):
            if candidate in _WRAPPER_BASENAMES:
                return True
            continue
        base = candidate.rsplit("/", 1)[-1]
        if any(_pattern_can_match(base, name) for name in _WRAPPER_BASENAMES):
            return True
    return False


#: r8 (REVIEW_2329 r6 B-R6-1): GLUED process-substitution / command-
#: substitution openers. Every word scanner above treats a word starting
#: with ``<``/``>`` as a REDIRECTION, but ``<(cmd)`` / ``>(cmd)`` glued to
#: the redirect is a PROCESS SUBSTITUTION: bash runs ``cmd`` in a subshell,
#: so the payload is an executed construct, not data (``$(cmd)`` command
#: substitution likewise). The payload therefore receives the FULL armed
#: posture — alone in the token-free leg and beside a faithful launch in
#: the wrapper-present leg alike — via
#: :func:`_process_substitution_payloads`. Canon-coordinate scanning (the
#: module-wide trade): a QUOTED ``'<(…)'`` string is seen as if the quotes
#: were gone, which can only over-refuse.
_PROC_SUB_OPEN_RE = re.compile(r"\d*[<>]\(|\$\(")


def _process_substitution_payloads(canon: str) -> list[str]:
    """The substituted text of every glued ``<(…``/``>(…``/``$(…`` group.

    The walk is nesting-aware (parens counted, so a payload containing
    further groups is extracted whole); an unterminated group spans to the
    end of the text — conservative in the refusing direction. Payloads of
    NESTED groups appear both here and inside their parent's payload; the
    recursion in :func:`_deny_computed_launch` judges every level, so the
    duplication is harmless.
    """
    payloads: list[str] = []
    for match in _PROC_SUB_OPEN_RE.finditer(canon):
        body, _ = _read_pattern_group(canon, match.end() - 1)
        payloads.append(body)
    return payloads


def _unprovable_position_word(canon: str) -> tuple[str, str] | None:
    """``(wrapper-shaped word, governing head)`` for the first shell-expanded
    word at a position the guard cannot reduce to a plain data argument —
    or None.

    Fires only when NO literal wrapper token is in the text (the
    wrapper-present branch refuses every expanded word in any position
    already). A word after a head the guard cannot classify — an
    unrecognized runner (``timeout``, ``watch``, ``strace``, ``setsid``,
    ``stdbuf``, ``arch``, ``script`` or ANY word never listed: the list is
    not the boundary), a shell/interpreter/ssh program carrier (``bash -c
    'poo* run …'``, ``ssh h 'poo* …'``), or an unclassifiable payload
    inside a recognized runner chain (``nohup timeout 5 poo[l] …``) — may
    be executed as a command word by that head or a child it spawns, so a
    WRAPPER-SHAPED expanded word there is refused (REVIEW_2329 r5
    B-1a/B-1c; the r7 fail-closed posture). Data-only utilities and
    builtins reduce their arguments to data; a ``trap`` program is
    executed position (it runs on signal delivery); recognized transparent
    runners reduce their payload through the flag tables."""
    for segment in re.split(r"[;&|\n]", canon):
        head: str | None = None
        governing = ""
        rest: list[str] = []
        for word in segment.split():
            if word in ("(", ")", "{", "}"):
                continue
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
                continue  # an assignment
            if word[0] in "<>" or re.match(r"\d*[<>]", word):
                continue  # a redirection
            if head is None:
                base = word.rsplit("/", 1)[-1].lower()
                if base in _COMMAND_PREFIX_WORDS or base in _SHELL_KEYWORDS:
                    governing = base  # r8: what was skipped before the head
                    continue  # a keyword: the command word follows it
                head = word
                # r8 (REVIEW_2329 r6 B-R6-2): the head itself was never
                # wrapper-shape-checked — only `rest` words were. After a
                # skipped keyword/prefix the head IS the word the shell
                # executes (``if poo* run …; then``, ``time poo? …``),
                # so an expansion-dependent wrapper-shaped head —
                # with or without a governing keyword — is refused.
                if _expansion_dependent(word) and _wrapper_shaped(word):
                    return word, governing
                continue
            rest.append(word)
        if head is None:
            continue
        head_base = head.rsplit("/", 1)[-1].lower()
        if head_base == "trap":
            for word in rest:  # the program runs on signal delivery
                if _expansion_dependent(word) and _wrapper_shaped(word):
                    return word, head_base
            continue
        if head_base in _TRANSPARENT_RUNNERS:
            payload: str | None = None
            index = 0
            while index < len(rest):
                word = rest[index]
                if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word) or (
                    word[0] in "<>" or re.match(r"\d*[<>]", word)
                ):
                    index += 1
                    continue
                if word.startswith("-") and word != "-":
                    flag = word.split("=", 1)[0]
                    if (
                        flag in _RUNNER_ARG_FLAGS.get(head_base, frozenset())
                        and "=" not in word
                    ):
                        index += 2  # the flag and its separate argument
                        continue
                    index += 1
                    continue
                payload = word
                break
            if payload is None:
                continue
            payload_base = payload.rsplit("/", 1)[-1].lower()
            if (
                payload_base in _SAFE_DATA_HEADS
                or payload_base in _SHELL_BUILTINS
                or payload_base in _SHELL_KEYWORDS
                or payload_base in _WRAPPER_BASENAMES
            ):
                continue  # the payload reduces: its own arguments are data
            for word in rest[index:]:  # the payload included: unclassifiable
                if _expansion_dependent(word) and _wrapper_shaped(word):
                    return word, payload_base
            continue
        if (
            head_base in _SAFE_DATA_HEADS
            or head_base in _SHELL_BUILTINS
            or head_base in _WRAPPER_BASENAMES
        ):
            continue  # a data-only utility/builtin/wrapper: args are data
        for word in rest:  # unrecognized head: every tail position unknown
            if _expansion_dependent(word) and _wrapper_shaped(word):
                return word, head_base
    return None


def _unrecognized_head_word(canon: str) -> str | None:
    """The first simple-command HEAD that is not in the recognized vocabulary
    (wrapper, transparent runner, shell keyword/builtin, data-only utility,
    shell) — or None.

    With a wrapper token in the text such a head makes the command
    irreducible: the program or payload behind it is unreadable, so a paid
    launch beside it cannot be attributed (REVIEW_2329 r5 M-3 —
    ``R``/``sqlite3 .read``/``jshell`` were merely the probed spellings;
    every unlisted interpreter or tool — groovy, scala, octave, gnuplot,
    ``make -f``, a renamed ``./p`` — is refused by this same rule, which is
    why closure no longer depends on the family list)."""
    for segment in re.split(r"[;&|\n]", canon):
        for word in segment.split():
            if word in ("(", ")", "{", "}"):
                continue
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
                continue
            if word[0] in "<>" or re.match(r"\d*[<>]", word):
                continue
            base = word.rsplit("/", 1)[-1].lower()
            if base in _COMMAND_PREFIX_WORDS or base in _SHELL_KEYWORDS:
                continue
            if base in _RECOGNIZED_HEADS:
                break  # this segment's head is recognized
            return word  # an unrecognized command head
    return None


def _brace_group_spans(canon: str) -> list[tuple[int, int]]:
    """Every ``{ … }`` group in ``canon`` as a span, nesting included.

    A wrapper launch inside one is runtime-multiplexed or function-defined
    (REVIEW_2329 r3 M-A): ``f() { pool run …; }; f; f``, ``for i in 1 2;
    { … }``, ``for ((…)) { … }`` and ``{ $P run …; }`` all execute the
    launch zero-or-many times, while one binding covers one attempt.
    ``${NAME}`` parameter expansion is not a group and is skipped."""
    spans: list[tuple[int, int]] = []
    open_stack: list[int] = []
    for index, char in enumerate(canon):
        if char == "{":
            if index and canon[index - 1] == "$":
                continue
            open_stack.append(index)
        elif char == "}" and open_stack:
            spans.append((open_stack.pop(), index + 1))
    spans.extend((start, len(canon)) for start in open_stack)
    return spans


def _deny_computed_launch(canon: str, raw: str | None = None) -> None:
    """Refuse launch-shaped text no lexically observed wrapper invocation can
    cover — structurally, and since r7 FAIL-CLOSED (REVIEW_2329 r5, the
    orchestrator-endorsed posture): an ARMED command is admitted only when
    it fully reduces to a known-safe shape; anything ambiguous is refused
    with a precise reason instead of enumerating escape spellings.

    * WRAPPER TOKEN PRESENT (a literal wrapper name anywhere, including
      inside quoted program text after canonicalisation): every word must
      be canonical — an interpreter invocation (the families in
      :data:`_INTERPRETER_WORD_RE`), ``eval``/``source``/``.``, or any
      computed (``$``/backtick) or shell-expanded word (glob, brace,
      extglob) outside an assignment is refused — AND every simple-command
      head must be recognized (wrapper, transparent runner, shell
      keyword/builtin, data-only utility, shell). An unrecognized head (an
      unlisted interpreter, ``ssh``, a renamed ``./p``, a function call)
      makes the command irreducible: the program or payload behind it is
      unreadable, so a paid launch beside it cannot be attributed.
    * NO WRAPPER TOKEN: an expanded word in COMMAND position — the head
      itself or a transparent runner's payload — is refused as before, and
      (r7) a WRAPPER-SHAPED expanded word at any position the guard cannot
      reduce to a plain data argument is refused: behind an unrecognized
      runner (``timeout 5 poo[l] …``, ANY word never listed), inside a
      shell/ssh program (``bash -c 'poo* run …'``), or in an unclassifiable
      runner-chain payload (``nohup timeout 5 poo[l] …``). Correctness does
      not depend on the runner/interpreter vocabularies: an unclassifiable
      head itself triggers the refusal.
    * r8 (REVIEW_2329 r6 B-R6-1): a GLUED ``<(…``/``>(…``/``$(…`` word is
      a process/command substitution — the payload runs in a subshell, so
      it is an executed construct, not a redirection. Every word scanner
      skips the glued word, so the payload text gets the FULL armed
      posture recursively (:func:`_process_substitution_payloads`), in the
      token-free leg and beside a faithful launch alike.
    * r8 (REVIEW_2329 r6 B-R6-2/M-R6-1): a shell keyword/prefix head
      (if/while/until/elif/!/time/…) does not occupy its segment's command
      slot — the word the shell EXECUTES after it (the loop/conditional's
      condition) stays at command position in
      :func:`_expanded_command_word`, and the head itself is
      wrapper-shape-checked in :func:`_unprovable_position_word`, so an
      expansion-dependent wrapper-shaped condition (``if poo* run …``,
      ``while poo* …``, ``! poo? …``, ``time poo[l] …``) is refused with
      or without any keyword/runner vocabulary entry.

    The head vocabulary is judged on the heredoc-stripped text so a staged
    body's words (and its delimiter line) are not command heads; the
    word-level rules stay on the full canon, heredoc bodies included.

    Conservative over-refusal is accepted under armed placement; it is
    documented in ``validate_execution_binding``."""

    wrapper_present = _WRAPPER_NAME_RE.search(canon) is not None
    posture_word: str | None = None
    posture_head = ""
    unrecognized: str | None = None
    if wrapper_present:
        scan = canon if raw is None else _canonical_command(strip_heredocs(raw))
        unrecognized = _unrecognized_head_word(scan)
    else:
        if _expanded_command_word(canon) is None:
            found = _unprovable_position_word(canon)
            if found is None:
                # r8 (B-R6-1): process-substitution payloads are executed
                # constructs, so the full posture runs inside them before
                # the token-free leg can admit the surrounding command.
                for payload in _process_substitution_payloads(canon):
                    _deny_computed_launch(payload)
                return
            posture_word, posture_head = found
    if _INTERPRETER_WORD_RE.search(canon):
        deny(
            "Mastermind shared-placement guard: unobservable launch — an "
            "interpreter (python/pypy/perl/ruby/node/php/Rscript/R/sqlite3/"
            "tclsh/lua/deno/bun/julia/pwsh/jshell/java/osascript/awk/jq …) "
            "runs a program the guard cannot read, whether from a flag, a "
            "script file or stdin, so a wrapper launch inside it cannot be "
            "checked against the binding. Run the paid launch as a plain "
            "command."
        )
    if _UNOBSERVABLE_ANYWHERE_RE.search(canon):
        deny(
            "Mastermind shared-placement guard: unobservable launch "
            "environment — eval/source/. can rewrite the child's POOL_* "
            "identity and command text at runtime (including inside a "
            "nested shell). Run the paid launch as a plain command."
        )
    if posture_word is not None:
        where = (
            f"behind {posture_head!r}, a command word whose argument "
            "grammar the guard cannot reduce to a plain data argument"
            if posture_head
            else "at a command position the guard cannot reduce to a "
            "plain data argument"
        )
        deny(
            "Mastermind shared-placement guard: unobservable launch — the "
            f"wrapper-shaped word {posture_word!r} is shell-expanded at "
            f"runtime and sits {where}, so the guard cannot prove it is "
            "not the paid wrapper (fail-closed posture, REVIEW_2329 r5 "
            "B-1, r6 B-R6-2). Invoke the wrapper by its literal name."
        )
    word = _computed_command_word(canon)
    if word is not None:
        deny(
            "Mastermind shared-placement guard: unobservable launch — the "
            f"word {word!r} is computed or shell-expanded at runtime (a "
            "$/backtick word, a glob, a brace or an extglob expansion), so "
            "the command it becomes, the wrapper invocation and any "
            "identity assignment around it cannot be observed. Invoke the "
            "wrapper by its literal name."
        )
    if unrecognized is not None:
        deny(
            "Mastermind shared-placement guard: unobservable launch — the "
            f"command word {unrecognized!r} is not a recognized wrapper, "
            "transparent runner, shell keyword/builtin or data-only "
            "utility, so with a paid launch in the same command this text "
            "cannot be reduced to an observable launch shape: the program "
            "or payload behind it is unreadable (fail-closed posture, "
            "REVIEW_2329 r5 M-3). Run the paid launch as a plain command."
        )

    # r8 (REVIEW_2329 r6 B-R6-1): with a wrapper token present, the glued
    # <( / >( / $( word is skipped by every scanner above (it looks like a
    # redirection), so an expansion-dependent wrapper inside the payload
    # escaped beside a faithful launch. The payload runs in a subshell —
    # the full armed posture applies inside it.
    for payload in _process_substitution_payloads(canon):
        _deny_computed_launch(payload)


def _paren_body_spans_raw(
    raw: str, raw_index: list[int]
) -> list[tuple[int, int]]:
    """CANON-coordinate spans of paren-bodied function definitions, measured
    on the RAW text (REVIEW_2329 r5 M-1).

    ``f() ( … )`` and ``function f () ( … )`` define a function whose body is
    a subshell: no brace span covers it, so one lexical launch inside it ran
    N paid children under one binding (REVIEW_2329 r4 M-A2). A plain
    subshell group ``( launch )`` runs its launch exactly once and is NOT
    spanned. RAW measurement makes the span quote- and layout-aware:
    newlines and comments between ``()`` and the body are legal bash
    (``f()\\n( L )``, ``f() # c\\n( L )``), and a quoted ``")"`` inside the
    body must not close the span early — canon, which deletes the quotes,
    got all three wrong. The walk is quote-aware (a ``"``/``'`` section
    hides parens; backslash escapes; a ``#`` comment runs to end of line),
    and an unterminated body spans to the end of the text: its multiplicity
    is unknown, so the fail-closed posture refuses any launch after it.
    ``raw_index`` is :func:`_canonical_command_map`'s offset map."""
    spans: list[tuple[int, int]] = []
    for match in _FUNCTION_DEF_RE.finditer(raw):
        index = match.end()
        while index < len(raw):
            char = raw[index]
            if char in " \t\r\n":
                index += 1
                continue
            if char == "#":
                newline = raw.find("\n", index)
                index = len(raw) if newline < 0 else newline + 1
                continue
            break
        if index >= len(raw) or raw[index] != "(":
            continue  # a brace body (brace spans cover it): not ours
        depth = 0
        quote: str | None = None
        cursor = index
        end: int | None = None
        while cursor < len(raw):
            char = raw[cursor]
            if quote is not None:
                if quote == '"' and char == "\\" and cursor + 1 < len(raw):
                    cursor += 2
                    continue
                if char == quote:
                    quote = None
                cursor += 1
                continue
            if char in "\"'":
                quote = char
                cursor += 1
                continue
            if char == "\\" and cursor + 1 < len(raw):
                cursor += 2
                continue
            if char == "#":
                newline = raw.find("\n", cursor)
                cursor = len(raw) if newline < 0 else newline + 1
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = cursor + 1
                    break
            cursor += 1
        if end is None:
            end = len(raw)  # unterminated: multiplicity unknown → cover all
        spans.append(
            (
                bisect.bisect_left(raw_index, match.start()),
                bisect.bisect_left(raw_index, end),
            )
        )
    return spans


def _loop_spans(canon: str) -> list[tuple[int, int]]:
    """Spans of every loop's CONDITION header and BODY, command-position
    aware (REVIEW_2329 r5 M-1).

    The r6 scanners pattern-matched words anywhere: a ``do``/``done`` PAIR
    inside a while condition (``while echo do echo done; L; do :; done``,
    live 3 launches) truncated BOTH the condition span (which ended at the
    first ``do`` word — an argument of ``echo``) and the body span (first
    ``do`` to first ``done``, both arguments), leaving the launch outside
    every span. This walk splits the canon into simple-command segments and
    recognises ``while``/``until``/``do``/``done`` only at a segment's
    command position: argument-position ``do``/``done`` words are data.
    Each command-position ``do`` closes the innermost pending
    ``while``/``until`` header (its CONDITION span) and opens a BODY span
    that the matching command-position ``done`` closes (nesting via a
    stack). A header or body left unmatched spans to the end of the text:
    its multiplicity is unknown, so the fail-closed posture refuses any
    launch after it."""
    spans: list[tuple[int, int]] = []
    open_bodies: list[int] = []
    pending_headers: list[int] = []
    segments: list[tuple[int, str]] = []
    prev = 0
    for sep in re.finditer(r"[;&|\n()]", canon):
        segments.append((prev, canon[prev : sep.start()]))
        prev = sep.end()
    segments.append((prev, canon[prev:]))
    for start, text in segments:
        for word_match in re.finditer(r"\S+", text):
            word = word_match.group(0)
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
                continue
            if word[0] in "<>" or re.match(r"\d*[<>]", word):
                continue
            lowered = word.lower()
            if (
                lowered not in _LOOP_STRUCT_KEYWORDS
                and lowered not in _COMMAND_PREFIX_WORDS
            ):
                break  # a real command word: no loop structure here
            absolute = start + word_match.start()
            if lowered in ("while", "until"):
                pending_headers.append(absolute)
            elif lowered == "do":
                if pending_headers:
                    spans.append((pending_headers.pop(), absolute))
                open_bodies.append(absolute)
            elif lowered == "done":
                if open_bodies:
                    spans.append(
                        (open_bodies.pop(), start + word_match.end())
                    )
            # for/select/!/in: nothing yet — their `do` arrives as a plain
            # command-position do with no pending header.
    spans.extend((start, len(canon)) for start in open_bodies)
    spans.extend((start, len(canon)) for start in pending_headers)
    return spans


def _trap_program_spans(raw: str) -> list[tuple[int, int]]:
    """RAW-text spans of ``trap`` programs, quote-aware.

    The span used to end at the first ``;`` even when that ``;`` was INSIDE
    the quoted program (REVIEW_2329 r4 n-2), so it is measured on the raw
    text where the quotes still stand; :func:`_runtime_multiplexed` maps
    the span back into canon coordinates. r5 M-2: the program is not
    always one pure quoted string — concatenated sections (``'a'\\;'b'``,
    ``'a'\\'''b'`` splices, ``"a""b"``) and a leading ``--`` option
    end-marker (``trap -- '…' USR1``) defeated the scanner and the launch
    fell outside the span. The scan now skips a leading ``--`` and keeps
    extending the program word while the next character is directly a
    quote or a backslash escape (concatenation); an unterminated quote
    runs to the end of the text — the multiplicity is unknown, so the span
    covers conservatively."""
    spans: list[tuple[int, int]] = []
    for match in _TRAP_WORD_RE.finditer(raw):
        index = match.end()
        while index < len(raw) and raw[index] in " \t":
            index += 1
        if raw.startswith("--", index):  # bash accepts the option end-marker
            index += 2
            while index < len(raw) and raw[index] in " \t":
                index += 1
        if index >= len(raw) or raw[index] not in "\"'":
            end = _STATEMENT_END_RE.search(raw, index)
            spans.append((match.start(), end.start() if end else len(raw)))
            continue
        while True:
            quote = raw[index]
            index += 1
            while index < len(raw):
                char = raw[index]
                if quote == "'":
                    index += 1
                    if char == "'":
                        break
                    continue
                if char == "\\" and index + 1 < len(raw):
                    index += 2
                    continue
                index += 1
                if char == '"':
                    break
            else:
                break  # unterminated quote: span to the end of the text
            if index < len(raw) and raw[index] == "\\":
                index += 2  # a glued escape extends the word ('a'\;'b')
                continue
            if index < len(raw) and raw[index] in "\"'":
                continue  # a glued quoted section ("a""b", '\'' splices)
            break
        spans.append((match.start(), index))
    return spans


def _runtime_multiplexed(
    canon: str, offsets: list[int], raw: str | None = None
) -> bool:
    """True when a wrapper invocation sits inside a construct that executes
    it zero-or-many times at runtime: a for/while/until loop body or
    CONDITION header (command-position matched), an xargs/parallel/find
    -exec executor's argument tail, any ``{ … }`` group or function body
    (brace- or paren-bodied, the paren body measured quote- and
    layout-aware on the raw text), a ``trap`` program (concatenated
    sections included), or a repeater (``watch``, ``timeout --foreground``)
    (REVIEW_2329 r2 N-2, r3 M-A, r4 M-A2, r5 M-1/M-2). One binding covers
    exactly one attempt, so N runtime children under one lexical launch
    are refused as unaccounted descendants."""
    spans = _loop_spans(canon)
    spans += [match.span() for match in _BATCH_EXECUTOR_RE.finditer(canon)]
    spans += [match.span() for match in _REPEATER_RE.finditer(canon)]
    spans += _brace_group_spans(canon)
    if raw is not None:
        raw_index = _canonical_command_map(raw)[1]
        spans += _paren_body_spans_raw(raw, raw_index)
        spans += [
            (
                bisect.bisect_left(raw_index, start),
                bisect.bisect_left(raw_index, end),
            )
            for start, end in _trap_program_spans(raw)
        ]
    else:
        identity = list(range(len(canon)))
        identity.append(len(canon))
        spans += _paren_body_spans_raw(canon, identity)
        for match in _TRAP_WORD_RE.finditer(canon):
            end = _STATEMENT_END_RE.search(canon, match.end())
            spans.append((match.start(), end.start() if end else len(canon)))
    return any(
        start <= offset < end for start, end in spans for offset in offsets
    )


def _deny_runtime_multiplexed() -> None:
    deny(
        "Mastermind shared-placement guard: runtime-multiplexed "
        "launch — a for/while/until loop body, a brace group or function "
        "body, a trap program, a watch/timeout repeater, or an "
        "xargs/parallel/find -exec executor repeats this paid launch at "
        "runtime, but the current binding covers exactly one attempt. Every "
        "paid child must be admitted and claimed through the placement "
        "authority before launch."
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
    its own dedicated service account and projects the receipt into a path
    the fenced principal cannot write. The channel is defined
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
    POSIX join (empty string). Runtime-multiplexed launches (for/while/
    until bodies and condition headers, xargs/parallel/find -exec
    executors, any ``{ … }`` group or function body, ``trap`` programs,
    ``watch``/``timeout --foreground`` repeaters) are refused as
    unaccounted descendants. Given a wrapper name in the text, EVERY
    interpreter invocation is refused as unobservable regardless of flags
    or input channel (a script file or a program on stdin counts), as are
    ``eval``/``source``/``.`` anywhere and any computed (``$``/backtick)
    or shell-expanded word outside an assignment — conservative
    over-refusal, documented here, preferred to a bypass. Since r7 the
    armed gate is FAIL-CLOSED (REVIEW_2329 r5): with a wrapper token
    present every command head must be recognized (wrapper, transparent
    runner, shell keyword/builtin, data-only utility, shell) and every
    span parseable — an unclassifiable head, an unterminated construct or
    an ambiguous shape is refused rather than admitted by blindness; with
    no wrapper token, a wrapper-shaped expanded word at a position that
    cannot be reduced to a plain data argument is refused for the same
    reason. Unarmed/legacy sessions keep the pre-posture behavior
    exactly. Scripts staged in an EARLIER command or a
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
        canon = _canonical_command(command)
        if _UNOBSERVABLE_ENV_RE.search(canon) or (
            _WRAPPER_NAME_RE.search(canon)
            and _UNOBSERVABLE_ANYWHERE_RE.search(canon)
        ):
            deny(
                "Mastermind shared-placement guard: unobservable launch "
                "environment — eval, source/., BASH_ENV/ENV or a computed "
                "variable name can change the child's POOL_* identity outside "
                "what this guard can check. Run the paid launch as a plain "
                "command."
            )
        launches = _wrapper_invocations(command)
        if launches and _runtime_multiplexed(
            canon,
            [offset for offset, _, _, _ in launches],
            command,
        ):
            _deny_runtime_multiplexed()

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
        # REVIEW_2329 r3 M-A: a launch inside a brace group / function body,
        # a trap program or a repeater runs zero-or-many times. Refuse it as
        # runtime-multiplexed HERE, before the computed-word scan can
        # reclassify the construct (a trap body typically carries `$$`, and
        # a brace body is the same construct under another name). The gate
        # repeats the same judgement inside validate_execution_binding.
        span_launches = _wrapper_invocations(raw)
        if span_launches and _runtime_multiplexed(
            canon, [offset for offset, _, _, _ in span_launches], raw
        ):
            _deny_runtime_multiplexed()
        # REVIEW_2329 r3 B-1 / M-B and r5 (the r7 fail-closed posture):
        # interpreter programs, eval/source/. anywhere, computed or expanded
        # words carrying a wrapper token, unrecognized command heads beside
        # a launch, and wrapper-shaped expanded words at unprovable
        # positions never reach the wrapper scan, so they are refused here
        # — BEFORE the no-launch early return that used to let an armed
        # session launch with zero binding validation.
        _deny_computed_launch(canon, raw)
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
