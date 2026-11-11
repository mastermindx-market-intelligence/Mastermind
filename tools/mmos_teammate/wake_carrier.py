#!/usr/bin/env python3
"""MMOS lane T2 wake carrier — Paperclip `process` adapter child for a T3 teammate.

Spawned by Paperclip's process adapter on wake with PAPERCLIP_AGENT_ID,
PAPERCLIP_COMPANY_ID, PAPERCLIP_API_URL, PAPERCLIP_RUN_ID and a per-run
PAPERCLIP_API_KEY (48h agent JWT). It receives no task id and no prompt.

Sequence: authenticate as the agent -> find the assigned issue -> check it out
with this run -> read the `teammate.t3` binding from the agent's metadata ->
forward the issue (title + body) as ONE message to the teammate's primary T3
thread via the stock `t3 thread send --wait --json` CLI -> post the thread's
answer as a comment on the same issue -> move the issue to in_review -> exit 0.

The run token stays in this process: it is never written to a prompt, an
argument list, a log or evidence. The T3 side needs no credential at all —
`t3 thread send` mints its own short-lived MCP session from T3CODE_HOME.

Exactly-once discipline (smallest honest rule): the operation id
`pc-<issueId>-<sha256(title+body)[:10]>` is embedded in the message sent to the
thread. On re-entry the carrier scans the thread for that marker first: a
pending marker is waited on (the turn may still be running server-side), a
completed marker's reply is reconciled onto the issue, and the task is never
sent twice. The marker's user turn and its answer share a T3 runId, so the
reply is bound to that run — a later unrelated turn in the thread can never
replace it (adversarial finding 2026-11-10), and a run that has not ended is
never a reply even when it already shows assistant text (MAS-9, 2026-11-10:
half-finished text was delivered as the answer). Delivery is idempotent
across runs: an already-posted comment body and an already-created
confirmation are both detected and skipped (this build answers a re-POSTed
confirmation key from another run with 409, not a dedupe).

When the teammate stops on a question for a person, this same carrier run
stays with it (MAS-9: nothing used to wake the task after the answer): it
posts one line that says where to answer and for how long, then polls the
thread until the marker's turn ends, bounded by question_wait_sec and the
carrier's own run budget. An unanswered question ends the run with the issue
left in_progress — a board comment on the issue wakes it again.
See T2_TEAMMATE_BINDING_AND_DISPATCH.md.
"""
import fcntl
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

RETRYABLE_HTTP = (408, 429, 500, 502, 503, 504)


class CarrierError(Exception):
    """Fatal carrier failure; the process exits non-zero (run ends failed)."""


class NeedsHuman(Exception):
    """The teammate is waiting for an answer in its T3 thread."""


OUTPUT_BLOCK = "paperclip-output"
ASK_BLOCK = "paperclip-ask"
CODING_JOB_BLOCK = "paperclip-coding-job"
CODING_JOB_DEFAULT_KEY = "coding-job-1"


def parse_coding_job_block(reply):
    """The LAST ```paperclip-coding-job fenced block in a reply, if any.

        ```paperclip-coding-job
        key: coding-job-1
        ```

    -> {"key"} or None. The block names WHICH job of this task it is (the
    task's title+description is the brief); a block without a key means the
    default. Malformed -> None (plain answer; a trigger can never fail the
    run). Blocks count only in the teammate's OWN reply AND only as its LAST
    word (attack review F9): a block the teammate QUOTED back — from the
    task description or anywhere else — is followed by the teammate's own
    prose and is not a trigger. Example `<...>` keys die at the identifier
    regex, never as a trigger."""
    lines = (reply or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") and CODING_JOB_BLOCK in stripped:
            start = idx
    if start is None:
        return None
    key, closed, close_idx = None, False, None
    for idx in range(start + 1, len(lines)):
        if lines[idx].strip().startswith("```"):
            closed = True
            close_idx = idx
            break
        if key is None and lines[idx].strip().startswith("key:"):
            key = lines[idx].split(":", 1)[1].strip()
            continue
        return None  # any other content makes it malformed, not a trigger
    if not closed:
        return None
    # F9: anything but whitespace after the closing fence means the block
    # was quoted or documented, not emitted as the reply's own last word
    if any(line.strip() for line in lines[close_idx + 1:]):
        return None
    key = key or CODING_JOB_DEFAULT_KEY
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", key):
        return None  # job keys stay safe identifiers (and `<...>` examples)
    return {"key": key}


def coding_job_command(issue_id, key=CODING_JOB_DEFAULT_KEY):
    """The frozen coding-job command for one task+key — a six-line stdlib
    mirror of the engine's ``admission_command_id`` over the idempotency
    triple (roots/paperclip-<id>, parents/paperclip-<id>, key). Pinned
    byte-identical by tests/test_mmos_teammate_coding_job.py; the carrier
    names a COMMAND only and never carries the envelope."""
    material = "\x1f".join((
        f"roots/paperclip-{issue_id}",
        f"parents/paperclip-{issue_id}",
        str(key),
    ))
    return "child-request:" + hashlib.sha256(
        material.encode("utf-8")).hexdigest()


class DoorClient:
    """The coding-job door on the Executive local-operator socket (L4). The
    socket itself is the admission (kernel peer uid); no token, no headers."""

    def __init__(self, socket_path, timeout=60.0):
        self._path = str(socket_path)
        self._timeout = timeout

    def _request(self, method, path, body=None):
        payload = json.dumps(body).encode() if body is not None else b""
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self._timeout)
        conn.connect(self._path)
        try:
            head = (f"{method} {path} HTTP/1.0\r\nHost: door\r\n"
                    f"Content-Length: {len(payload)}\r\n"
                    "Content-Type: application/json\r\n\r\n").encode("ascii")
            conn.sendall(head + payload)
            chunks = []
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                chunks.append(data)
        finally:
            conn.close()
        raw = b"".join(chunks)
        status_line, _, resp = raw.partition(b"\r\n\r\n")
        status = int(status_line.split(b" ", 2)[1]) if b" " in status_line else 0
        try:
            return status, json.loads(resp or b"{}")
        except ValueError:
            return status, {}


def handle_coding_job(pc, issue, reply, block, opts):
    """The third block: this task needs code, so ONE governed coding job.

    Called AFTER the reply is delivered as the task's comment. The carrier
    computes the frozen command locally, makes exactly ONE admit call through
    the door socket, and maps the answer honestly onto the task: an honest
    admission/replay comment (the job id is the identity the result will
    carry home), or ONE blocker comment with the exact reason (WAIT detail,
    refusal code, unreachable door). Terminal outcomes carry the idempotency
    marker; TRANSIENT ones (WAIT, unreachable door) deliberately do not, so
    a later wake retries the one call — the door itself is idempotent by
    command. Never raises — a blocked job must not fail the delivered
    answer."""
    socket_path = (opts.get("coding_job_door") or "").strip()
    if not socket_path:
        log("coding-job block present but no coding_job_door in config; "
            "nothing to do")
        return
    command = coding_job_command(issue["id"], block["key"])
    marker = f"coding-job-command: {command}"
    try:
        rows = pc.comments(issue["id"])
    except CarrierError:
        rows = []
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    if any(marker in (row.get("body") or "") for row in rows):
        log(f"coding job for {issue.get('identifier')} already surfaced "
            f"({block['key']}); no second call")
        return
    door = DoorClient(socket_path)
    try:
        status, body = door._request(
            "POST", "/paperclip/coding-job/admit", {"command": command})
    except OSError as exc:
        # F4 (attack review): DOOR_UNREACHABLE is TRANSIENT — the door may
        # just be restarting.  The comment deliberately carries NO marker so
        # the next wake retries the one admit call (the door is idempotent
        # by command).
        pc.add_comment(issue["id"], (
            f"[t2-carrier] coding job blocked — DOOR_UNREACHABLE\n\n"
            f"The Executive door socket is not answering ({exc}); the task's "
            f"governed coding job could not be requested and will be "
            f"retried on the next wake."))
        log(f"coding-job door unreachable for {issue.get('identifier')}")
        return
    result = body.get("result") if isinstance(body, dict) else None
    state = (result or {}).get("state") if isinstance(result, dict) else None
    if status == 200 and state in ("ADMITTED", "REPLAY"):
        job_id = (result or {}).get("job_id")
        pc.add_comment(issue["id"], (
            f"[t2-carrier] coding job {block['key']} {state} — "
            f"job `{job_id}`\n\n"
            "The Executive admitted this task's governed coding job; its "
            "verified result (with branch evidence) returns to this task "
            "when the attempt seals.\n\n"
            f"{marker}"))
        log(f"coding job for {issue.get('identifier')} {state} as {job_id}")
        return
    if status == 200 and state == "WAIT":
        # F4: WAIT is TRANSIENT capacity — no marker, so the next wake
        # retries when the queue drains; only terminal outcomes suppress.
        reason = (result or {}).get("wait_reason") or "queue full"
        detail = (result or {}).get("wait_detail") or {}
        pc.add_comment(issue["id"], (
            f"[t2-carrier] coding job blocked — WAIT ({reason})\n\n"
            f"The Executive ready queue has no capacity for this task's "
            f"coding job right now{': ' + json.dumps(detail) if detail else ''}"
            f"; it will be retried on the next wake."))
        log(f"coding job for {issue.get('identifier')} WAIT: {reason}")
        return
    error = (body.get("error") or {}) if isinstance(body, dict) else {}
    code = error.get("code") or f"HTTP_{status or 'EMPTY'}"
    message = error.get("message") or "the Executive refused the coding job"
    pc.add_comment(issue["id"], (
        f"[t2-carrier] coding job blocked — {code}\n\n{message}\n\n{marker}"))
    log(f"coding job for {issue.get('identifier')} refused: {code}")


def parse_ask_block(reply):
    """The LAST ```paperclip-ask fenced block in a reply, if any.

        ```paperclip-ask
        assignee: Atlas-TEST
        title: Count lines in t45_alpha.txt
        description: <may span lines until the fence>
        ```

    -> {"assignee", "title", "description"} or None. Malformed -> None (the
    reply is delivered as a plain answer; an ask can never fail the run)."""
    lines = (reply or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") and ASK_BLOCK in stripped:
            start = idx
    if start is None:
        return None
    assignee, title, desc_lines, closed = None, None, [], False
    close_at = None
    for off, line in enumerate(lines[start + 1:]):
        if line.strip().startswith("```"):
            closed = True
            close_at = start + 1 + off
            break
        if assignee is None and line.strip().startswith("assignee:"):
            assignee = line.split(":", 1)[1].strip()
            continue
        if title is None and line.strip().startswith("title:"):
            title = line.split(":", 1)[1].strip()
            continue
        # R2a finding 28: the block format shows `description:` as a labeled
        # field like assignee/title. A first description line that carries
        # the label loses it — `description: please` -> `please`. Later
        # lines are kept verbatim; an unlabeled first line is kept verbatim.
        if not desc_lines and line.strip().startswith("description:"):
            desc_lines.append(line.split(":", 1)[1].strip())
            continue
        desc_lines.append(line)
    if not closed or not assignee or not (title or "").strip():
        return None
    # R2a finding 18 (the F9 guard): the ask block must END the reply. Words
    # after the closing fence mean the teammate kept talking past the ask —
    # a reconsidered or quoted block is not a live ask. Whitespace is fine.
    if any(line.strip() for line in lines[close_at + 1:]):
        return None
    if title.strip().startswith("<") and title.strip().endswith(">"):
        return None  # the how-to-ask example quoted back, not a real ask
    return {"assignee": assignee, "title": title.strip(),
            "description": "\n".join(desc_lines).strip()}


def parse_output_block(reply):
    """The LAST ```paperclip-output fenced block in a reply, if any.

        ```paperclip-output
        key: summary
        title: One-page summary
        <markdown body lines...>
        ```

    -> {"key", "title", "body"} or None. A malformed block is ignored (the
    reply is still delivered as a comment); it can never fail the run."""
    lines = (reply or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") and OUTPUT_BLOCK in stripped:
            start = idx
    if start is None:
        return None
    key, title, body_lines, closed = None, None, [], False
    close_at = None
    for off, line in enumerate(lines[start + 1:]):
        if line.strip().startswith("```"):
            closed = True
            close_at = start + 1 + off
            break
        if key is None and line.strip().startswith("key:"):
            key = line.split(":", 1)[1].strip()
            continue
        if title is None and line.strip().startswith("title:"):
            title = line.split(":", 1)[1].strip()
            continue
        body_lines.append(line)
    if not closed or not key:
        return None
    # R2a finding 27 (the F9 guard, as the ask block got it): the output
    # block must END the reply. Words after the closing fence mean the
    # teammate kept talking — the block is not written as a document; the
    # reply is still delivered as a plain comment. Whitespace is fine.
    if any(line.strip() for line in lines[close_at + 1:]):
        return None
    # R2a finding 22: ASCII only — str.isalnum accepts accented letters,
    # and a document key is a filename-shaped identifier.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", key):
        return None  # document keys stay safe identifiers
    return {"key": key, "title": title or key,
            "body": "\n".join(body_lines).strip() + "\n"}


def log(message: str) -> None:
    print(f"[t2-carrier] {message}", flush=True)  # secrets are never logged


def op_id(issue_id: str, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"pc-{issue_id}-{digest}"


# A child issue created by a teammate's ```paperclip-ask block carries its
# parent's ask op marker at the very END of its description — the carrier
# writes "Asked by X on MMO-17\n[pc-…-ask]" (children created before
# 2026-11-11 end with "... on MMO-17 [pc-…-ask]" instead; both end with the
# marker, which is what the anchored scan reads). A `[pc-…-ask]` token
# anywhere else in a description is teammate text (R2a finding 3).
# Attack finding 13: op_id interpolates the raw issue id, so the recognized
# shape must cover every id it can produce (is_issued_ask_child already
# escaped the id; the two sites now agree). Equality with the carrier's
# computed op still gates everything downstream.
ASK_CHILD_MARKER_RE = re.compile(r"\[(pc-[A-Za-z0-9_.-]+-ask)\]\s*$")


def ask_child_op(text: str):
    """The ask op marker at the very END of an issue description, if any."""
    match = ASK_CHILD_MARKER_RE.search((text or "").rstrip())
    return match.group(1) if match else None


def expected_ask_op(parent):
    """The ask marker this carrier computes for a child of `parent`: the
    parent issue's own op with the -ask suffix — exactly what handle_ask
    writes into the child description."""
    content = (parent.get("title") or "") + "\n" + (parent.get("description") or "")
    return f"{op_id(parent['id'], content)}-ask"


def is_ask_child_of(row, parent):
    """True when `row` is an ask child this carrier created under `parent`:
    parented on it AND ending with exactly the carrier-computed marker.
    Anything a teammate wrote inside a description cannot satisfy this."""
    if not parent or row.get("parentId") != parent.get("id"):
        return False
    return ask_child_op(row.get("description") or "") == expected_ask_op(parent)


def asked_child_of(pc, issue):
    """The parent issue record when THIS issue is an ask child of it (the
    structural test of R2a finding 3). None otherwise — including when the
    parent cannot be read or the parent's content no longer matches the
    marker, which degrades to a plain task rather than a guess."""
    parent_id = issue.get("parentId")
    if not parent_id or not ask_child_op(issue.get("description") or ""):
        return None
    try:
        parent = pc.issue(parent_id)
    except CarrierError as exc:
        log(f"parent of {issue.get('identifier')} unreadable ({exc}); "
            "treating the issue as a plain task")
        return None
    if is_ask_child_of(issue, parent):
        return parent
    log(f"{issue.get('identifier')} ends with ask-like text but is not the "
        "carrier's ask child of its parent; plain task")
    return None


def strip_markers(text: str):
    """Teammate-written text with any complete `[pc-…]` token removed, so
    what a teammate wrote can never pose as a carrier marker downstream."""
    return re.sub(r"\[pc-[^\]\n]*\]", "", text or "").strip()


def is_issued_ask_child(row, issue):
    """True when `row` looks like an ask child the carrier issued from
    `issue` under ANY content revision: parented on it and ending with a
    marker of this issue's op family (`pc-<issue id>-<hex10>-ask`). The
    per-issue ask cap counts these (R2a finding 4); a hand-written child
    that fits the shape counts too — overcounting only refuses asks."""
    if row.get("parentId") != issue.get("id"):
        return False
    marker = ask_child_op(row.get("description") or "")
    if not marker:
        return False
    return re.fullmatch(
        rf"pc-{re.escape(str(issue.get('id')))}-[0-9a-f]{{10}}-ask",
        marker) is not None


def _ask_cap(raw):
    """The per-issue ask cap as one coerced int (attack finding 15): a
    non-numeric value keeps the default 3; a value below 1 is taken literally
    as zero asks rather than silently loosening to the default."""
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        return 3
    return max(cap, 0)


def issue_link(template, identifier):
    """A labelled link to the issue page for the conversation, or None.

    `template` comes from the carrier config (`issue_url_template`, with
    `{identifier}`), never from issue text. Only a loopback http address is
    accepted, and only for an identifier shaped like MAS-12, so nothing a task
    author writes can turn into a link target."""
    if not template or not identifier:
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,15}-[0-9]{1,9}", identifier):
        return None
    if not re.match(r"http://(127\.0\.0\.1|localhost):[0-9]{2,5}/", template):
        return None
    if template.count("{identifier}") != 1:
        return None
    return f"[{identifier}]({template.replace('{identifier}', identifier)})"


def ask_help(roster, my_agent_id):
    """One short paragraph telling a teammate whom it may ask and how. Names
    come from carrier config only; the teammate itself is left out. None when
    there is nobody else to ask."""
    names = sorted(n for n, aid in (roster or {}).items()
                   if aid != my_agent_id and re.fullmatch(r"[A-Za-z0-9 _-]{1,40}", n))
    if not names:
        return None
    return (
        "If part of this needs another teammate (" + ", ".join(names) + "), "
        "end your reply with one block like this and nothing after it; the "
        "work is handed over and you are woken with their answer:\n"
        f"```{ASK_BLOCK}\nassignee: {names[0]}\ntitle: <short title>\n"
        "description: <what you need back>\n```\n"
        "Only ask when you cannot do that part yourself."
    )


def build_message(identifier: str, title: str, body: str, op: str,
                  link: str = None, asking: str = None, job_help: str = None,
                  notes: list = None, no_ask: str = None) -> str:
    body = (body or "").strip()
    if notes:
        body += ("\n\nNotes the board wrote on the issue before you were "
                 "woken (oldest first):\n\n"
                 + "\n\n".join(f"- {note}" for note in notes))
    where = (f"Issue page (the board accepts or declines the answer there): "
             f"{link}\n\n") if link else ""
    how_to_ask = f"\n\n{asking}" if asking else ""
    how_to_job = f"\n\n{job_help}" if job_help else ""
    why_no_ask = f"\n\n{no_ask}" if no_ask else ""
    return (
        f"[{op}]\n\n"
        f"You were woken for Paperclip issue {identifier}: {title}\n\n"
        f"{where}"
        f"{body}\n\n"
        "Do the task described above. Your reply to this message is posted as "
        "the issue comment and completes the issue."
        f"{how_to_ask}"
        f"{how_to_job}"
        f"{why_no_ask}"
    )


def coding_job_help(door_socket):
    """The third-block instruction, only when a door is configured. The
    example uses a placeholder key, so a teammate quoting the instruction
    back verbatim is ignored by the parser's example guard."""
    if not door_socket:
        return None
    return (
        "If this task needs CODE you cannot finish in this reply, end your "
        "reply with a fenced block:\n"
        "```paperclip-coding-job\n"
        "key: <only for a second, different job; default coding-job-1>\n"
        "```\n"
        "The task itself (title + description) is the job's brief. The block "
        "requests ONE governed coding job: the Executive admits it, a worker "
        "runs it, and its verified result (branch evidence included) returns "
        "to this task as a comment. Do not put the brief in the block."
    )


def active_run_id(row):
    """The run id an inbox row names as its active run (str or {id: …})."""
    active = row.get("activeRun")
    if isinstance(active, dict):
        return active.get("id")
    return active or None


def choose_issue(rows, my_run_id=None):
    """Assigned issues eligible for this run: todo or in_progress (Paperclip's
    assignment automation moves a freshly assigned issue to in_progress before
    the agent run starts — inbox-lite serves both), dependencies ready, and
    either no active run or an active run that IS this run. An issue whose
    active run is this very run (the assignment wake binds it before the
    carrier starts) is this run's to do; an issue held by another live run is
    not. A BLOCKED issue is eligible only when its dependencies are explicitly
    ready — that is the issue_blockers_resolved return wake (every blocker
    done); a blocked issue still waiting on a blocker is not. Oldest first."""
    def eligible(row):
        status = row.get("status")
        if status == "blocked":
            if row.get("dependencyReady") is not True:
                return False
        elif status not in ("todo", "in_progress"):
            return False
        if not row.get("dependencyReady", True):
            return False
        active = active_run_id(row)
        return active is None or active == my_run_id

    # The issue Paperclip bound to THIS run (assignment or repair wake) comes
    # first — it is this run's to do. Everything else is oldest-first.
    return sorted([r for r in rows if eligible(r)],
                  key=lambda r: (0 if active_run_id(r) == my_run_id else 1,
                                 r.get("updatedAt") or ""))


def _marker_run_open(marker_run, thread):
    """True when the marker's turn has not ended (rule A). A run that has not
    ended is never a reply, whatever assistant text it already shows: on
    MAS-9 half-finished text of a run still waiting on its question was
    delivered as the answer. The turn is open when it is the thread's active
    run, or when a human question waits and it is the latest run. A thread
    dict without these fields says nothing (behave as before).

    Attack findings 2 and 3 (attack round on R2a findings 2/3/4): two
    degraded shapes said "ended" when they could not know. A thread that
    omits activeRunId entirely while status says the thread is running is a
    mid-turn read with the field dropped — the turn stays open. A thread
    that positively reports the marker's own run ended failed/cancelled
    keeps the turn open too: dead-run prose is never the answer; the carrier
    waits out and releases the issue for a person instead of delivering it.
    Both apply only when a LATER run has not superseded the marker's (a
    newer latestRunId ends the marker's turn whatever the status says)."""
    if not isinstance(thread, dict) or not marker_run:
        return False
    if thread.get("activeRunId") == marker_run:
        return True
    if _pending_requests(thread) > 0 and \
            thread.get("latestRunId") == marker_run:
        return True
    latest = thread.get("latestRunId")
    if latest and latest != marker_run:
        return False  # a later turn superseded the marker's
    status = str(thread.get("status") or "").lower()
    if "activeRunId" not in thread and status in ("running", "queued"):
        return True  # degraded read of a mid-turn thread
    if thread.get("activeRunId") is None and "activeRunId" in thread \
            and status in ("running", "queued", "failed", "cancelled",
                           "error", "stopped"):
        return True  # the marker's own run ended without completing
    return False


# R2a finding 16: the stated lookback bound before a first send. The thread
# read serves the latest `count` messages; 61 newer ones hide an older
# marker, and a second wake would send the task again. Four reads deep.
MARKER_LOOKBACK_STEPS = (60, 180, 540, 1620)


def scan_marker_deep(t3, op):
    """(state, reply, thread) with the bounded lookback of finding 16.

    Walks MARKER_LOOKBACK_STEPS. A found marker returns its state; a SHORT
    read means the whole thread was seen, so None is proven absence; a page
    that stays full to the bound returns "window_exhausted" — absence cannot
    be proven and the caller must guard its send another way (the send
    record on the issue)."""
    thread = None
    for count in MARKER_LOOKBACK_STEPS:
        thread, msgs = t3.messages(count)
        state, existing = scan_marker(msgs, op, thread)
        if state is not None:
            return state, existing, thread
        if len(msgs) < count:
            return None, None, thread
    return "window_exhausted", None, thread


def scan_marker(messages, op, thread=None):
    """('reply', text) | ('pending', None) | (None, None) for `op` in a thread.

    `messages` is oldest-first [(role, run_id, text)] and `thread` the same
    read's thread dict, both as returned by T3Thread.messages(). The marker's
    user message and its answer share a T3 runId; only assistant messages of
    THAT run are the answer (a later turn — a human poke, an operator side
    message — has a different runId and must never replace it). A marker
    whose run has not answered yet is pending — including when its run is
    still open by rule A, even if assistant text of that run exists.

    R2a finding 2: the marker counts ONLY when a user message BEGINS with
    exactly "[op]" followed by a newline — the shape every carrier message
    has always had (build_message writes "[op]\\n\\n...") — and the FIRST
    such message wins. A marker quoted inside other text (a teammate echoing
    its instructions, a side message) is someone's words, never a task; a
    later duplicate never replaces the first turn's answer.
    """
    tag = f"[{op}]\n"
    marker_run = None
    seen_at = None
    for idx, (role, run_id, _text) in enumerate(messages):
        if role == "user" and (_text or "").startswith(tag):
            marker_run = run_id  # the FIRST marker for this op wins
            seen_at = idx
            break
    if marker_run is None:
        return None, None
    reply = None
    for role, run_id, text in messages[seen_at:]:
        if role == "assistant" and run_id == marker_run and (text or "").strip():
            reply = text
    if reply is None or _marker_run_open(marker_run, thread):
        return "pending", None
    return "reply", reply


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every 3xx: a redirect becomes an HTTPError, never a follow.

    The per-run bearer token is pinned to the loopback base. urllib's default
    opener follows 3xx and re-sends the Authorization header to the Location
    target, which would leak the token off-base.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())
_STOCK_URLOPEN = urllib.request.urlopen


def _open(req, timeout):
    """Open a request through the no-redirect opener.

    urllib.request.urlopen is the transport seam (an embedder or test may
    replace it); when it is the stock function, route through _OPENER so a
    3xx is refused instead of followed.
    """
    if urllib.request.urlopen is not _STOCK_URLOPEN:
        return urllib.request.urlopen(req, timeout=timeout)
    return _OPENER.open(req, timeout=timeout)


class PaperclipClient:
    """Minimal agent-authenticated Paperclip API client (stdlib urllib).

    The bearer token is held in memory only; error paths print status codes,
    never headers or bodies that could echo it back.
    """

    def __init__(self, base_url: str, token: str, run_id: str, timeout: int = 30,
                 budget_left=None):
        self.base = base_url.rstrip("/")
        self._token = token
        self.run_id = run_id
        self._timeout = timeout
        # R2a finding 8 (addition): a callable returning the seconds this run
        # may still spend waiting (budget minus the delivery reserve), or
        # None when unknown. It CAPS every request timeout and retry sleep.
        self._budget_left = budget_left

    def _request(self, method: str, path: str, body=None):
        url = f"{self.base}{path}"
        data = None
        headers = {"authorization": f"Bearer {self._token}"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"
        # R2a finding 6: only reads and keyed upserts are retried. A POST
        # (a create) fails fast — a blind retry is how duplicate children and
        # duplicate interactions happen; the callers read back instead.
        retryable = method in ("GET", "PUT", "PATCH")
        last = None
        for attempt in range(3):
            cap = self._budget_left() if self._budget_left else None
            timeout = self._timeout
            if cap is not None:
                # Floor of 1s: the delivery writes themselves spend the
                # reserve and must stay alive (loopback answers in far less).
                timeout = max(1, min(self._timeout, cap))
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with _open(req, timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if retryable and exc.code in RETRYABLE_HTTP and attempt < 2:
                    last = exc.code
                    pause = 1.5 * (attempt + 1)
                    if cap is not None:
                        # R2a finding 8 (addition): no retry sleep eats the
                        # delivery reserve; nothing left means retry now.
                        pause = min(pause, max(0.0, cap))
                    if pause > 0:
                        time.sleep(pause)
                    continue
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                raise CarrierError(f"{method} {path} -> HTTP {exc.code} {detail}") from None
            except urllib.error.URLError as exc:
                if retryable and attempt < 2:
                    last = str(exc.reason)
                    pause = 1.5 * (attempt + 1)
                    if cap is not None:
                        pause = min(pause, max(0.0, cap))
                    if pause > 0:
                        time.sleep(pause)
                    continue
                raise CarrierError(f"{method} {path} unreachable: {exc.reason}") from None
        raise CarrierError(f"{method} {path} failed after retries ({last})")

    def me(self):
        return self._request("GET", "/api/agents/me")

    def inbox(self):
        return self._request("GET", "/api/agents/me/inbox-lite")

    def issue(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}")

    def checkout(self, issue_id, agent_id, allow_blocked=False):
        # todo: human-created, untouched. in_progress: the assignment
        # automation already moved it; activeRun-null means unowned. blocked:
        # only for the return wake, after every blocker reached done.
        expected = ["todo", "in_progress"]
        if allow_blocked:
            expected.append("blocked")
        return self._request(
            "POST", f"/api/issues/{issue_id}/checkout",
            {"agentId": agent_id, "expectedStatuses": expected},
        )

    def comments(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}/comments")

    def add_comment(self, issue_id, body):
        return self._request(
            "POST", f"/api/issues/{issue_id}/comments",
            {"clientRequestId": str(uuid.uuid4()), "body": body},
        )

    def interactions(self, issue_id):
        return self._request("GET", f"/api/issues/{issue_id}/interactions")

    def request_confirmation(self, issue_id, idem_key, prompt, target=None):
        """A pending request_confirmation interaction is this build's review
        path: without it, an agent PATCH to in_review is refused with
        invalid_issue_disposition (422). With the native_completion_review
        target, a board accept completes the issue (done) and a reject
        resumes it to todo for revision. CAUTION: re-POSTing an idempotencyKey
        that already exists from ANOTHER run is answered with 409, not a
        dedupe — callers check interactions() first."""
        payload = {"version": 1, "prompt": prompt}
        if target is not None:
            payload["target"] = target
        return self._request(
            "POST", f"/api/issues/{issue_id}/interactions",
            {"kind": "request_confirmation", "idempotencyKey": idem_key,
             "payload": payload},
        )

    def set_status(self, issue_id, status):
        return self._request("PATCH", f"/api/issues/{issue_id}", {"status": status})

    def issue_document(self, issue_id, key):
        """GET one issue document; None if absent (a 404 from this build)."""
        try:
            return self._request("GET", f"/api/issues/{issue_id}/documents/{key}")
        except CarrierError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def put_issue_document(self, issue_id, key, title, body):
        """Upsert one markdown document on the issue (this build's existing
        output surface; PUT is keyed, so a re-run is a no-op revision)."""
        return self._request(
            "PUT", f"/api/issues/{issue_id}/documents/{key}",
            {"format": "markdown", "title": title, "body": body,
             "changeSummary": f"teammate output via {OUTPUT_BLOCK} block"})

    def children(self, issue_id):
        """Issues whose parentId is this issue, PAGED: the old single 50-row
        page silently hid older children (R2a finding 4 — a cap count or a
        return scan that stops at 50 is wrong). Attack finding 6: a SHORT
        page is not proof of the end — a server that clamps `limit` below
        the request serves short pages forever, and the old walk truncated
        at the first one. The walk continues on any non-empty page, steps
        `offset` by what the server actually served, deduplicates by id
        (offset paging over a list that changes between calls can serve a
        row twice), and stops at the first EMPTY page, bounded at ten pages
        — beyond that this returns a truncated set rather than looping
        forever. Attack finding 7: the query is parentId-filtered
        server-side, so a row from it belongs to this issue even when the
        list projection omits the field — the walk stamps it, and the
        return edge cannot be stranded by a row shape."""
        company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
        rows = []
        seen = set()
        limit = 1000
        offset = 0
        for _ in range(10):
            batch = self._request(
                "GET",
                f"/api/companies/{company_id}/issues?parentId={issue_id}"
                f"&limit={limit}&offset={offset}")
            if isinstance(batch, dict):
                batch = batch.get("issues") or batch.get("children") \
                    or batch.get("rows") or []
            for row in batch:
                row = dict(row)
                row.setdefault("parentId", issue_id)
                key = row.get("id")
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            if not batch:
                break
            offset += len(batch)
        return rows

    def create_issue(self, company_id, payload):
        return self._request(
            "POST", f"/api/companies/{company_id}/issues", payload)

    def block_issue(self, issue_id, blocker_ids, owner_agent_id, action):
        return self._request("PATCH", f"/api/issues/{issue_id}", {
            "status": "blocked",
            "blockedByIssueIds": blocker_ids,
            "unblockDescriptor": {
                "owner": {"agentId": owner_agent_id}, "action": action},
        })


class T3Thread:
    """The teammate's primary thread, driven through the stock `t3` CLI.

    `t3 thread send <id> - --wait --json` reads the message from stdin (never
    argv), waits for that exact run, and prints
    {"threadId","runId","status","reply","error"}. Exit codes: 0 completed,
    1 failed, 2 the run waits for a human answer. The CLI mints its own
    short-lived MCP session from T3CODE_HOME, so no credential is passed here.
    """

    def __init__(self, t3_bin: str, t3_home: str, thread_id: str, scratch_dir: str,
                 t3_port=None, budget_left=None):
        self._bin = os.path.expanduser(t3_bin)
        self._home = os.path.expanduser(t3_home)
        self.thread_id = thread_id
        self._cwd = os.path.expanduser(scratch_dir)
        # A T3 server that is not on the CLI's default port (the team server)
        # must be named, or the CLI would dial the default port instead.
        self._port = int(t3_port) if t3_port else None
        # R2a finding 8: the CLI subprocess timeout comes from the run
        # budget (what is left before the delivery reserve), capped by the
        # stock 1200s. None when the budget is unknown: the stock 1200s.
        self._budget_left = budget_left

    def _run(self, args, stdin_text=None):
        # The Paperclip run token and run identity stay in this process: the
        # T3 CLI has no use for them, so its environment does not carry them.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("PAPERCLIP_")}
        env["T3CODE_HOME"] = self._home
        if self._port:
            env["T3CODE_PORT"] = str(self._port)
        timeout = 1200
        if self._budget_left:
            left = self._budget_left()
            if left is not None:
                timeout = max(1, min(1200, int(left)))
        # text=True: subprocess wants str input, not bytes
        proc = subprocess.run(  # noqa: S603 - fixed binary, fixed args
            [self._bin, *args],
            input=stdin_text,
            capture_output=True, text=True, cwd=self._cwd, env=env,
            timeout=timeout,
        )
        return proc

    def send(self, message: str):
        """Send one message, wait for the turn. -> dict with status/reply/error."""
        proc = self._run(["thread", "send", self.thread_id, "-", "--wait", "--json"],
                         stdin_text=message)
        payload = {}
        for line in proc.stdout.splitlines():
            if line.startswith("{"):
                payload = json.loads(line)
        if not payload:
            raise CarrierError(
                f"t3 thread send failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()[:300]}")
        if proc.returncode == 2:
            raise NeedsHuman(payload.get("threadId") or self.thread_id)
        if proc.returncode != 0 or payload.get("status") != "completed":
            raise CarrierError(
                "t3 run ended: status=%s error=%s"
                % (payload.get("status"), (payload.get("error") or "")[:300]))
        return payload

    def messages(self, count: int = 60):
        """Oldest-first [(role, runId, text)] of the latest `count` messages."""
        proc = self._run(["thread", "show", self.thread_id, "--json",
                          "--messages", str(count)])
        if proc.returncode != 0:
            raise CarrierError(f"t3 thread show failed: {proc.stderr.strip()[:300]}")
        data = json.loads(proc.stdout)
        out = []
        for item in data.get("messages", []):
            out.append((item.get("role"), item.get("runId"), item.get("text") or ""))
        return data.get("thread") or {}, out


def send_once(t3, message):
    """Send `message` unless a question is already waiting in the thread.

    A turn that waits for a person holds the thread: anything sent now is
    queued behind it, is not in what `messages()` returns, and so would be
    sent again by every later wake (seen on the installed app: one revision
    queued three times). Nothing is sent until the question is answered."""
    thread = t3.messages(1)[0]
    if _pending_requests(thread) > 0:
        raise NeedsHuman(_thread_id(t3, thread))
    return t3.send(message)


def _pending_requests(thread):
    """The thread's pendingRequestCount as an int; 0 when absent or odd."""
    try:
        return int((thread or {}).get("pendingRequestCount") or 0)
    except (TypeError, ValueError):
        return 0


def _thread_id(t3, thread=None):
    return getattr(t3, "thread_id", None) or (thread or {}).get("threadId")


def _now(opts):
    """The clock: time.time(), or the injected clock a test provides."""
    clock = opts.get("clock")
    return clock() if clock else time.time()


def _doze(opts, seconds):
    """Sleep between polls: time.sleep(), or the injected sleep a test
    provides (which also never really sleeps)."""
    sleeper = opts.get("sleep")
    if sleeper:
        sleeper(seconds)
    else:
        time.sleep(seconds)


def run_budget_end(opts):
    """The end of the carrier's own budget — run_budget_sec from process
    start, recorded once in main(). None when the start time is not known
    (a test, or an old config): no wait is capped then, as before."""
    start, budget = opts.get("run_start"), opts.get("run_budget_sec")
    if start is None or not budget:
        return None
    return float(start) + float(budget)


def question_wait_deadline(opts):
    """The earlier of question_wait_sec from now and the run budget's end
    MINUS the stated delivery reserve: no question wait may outlive the
    carrier's own process limit, and the budget's tail belongs to delivering
    the answer, never to more waiting (R2a finding 8 addition)."""
    end = _now(opts) + float(opts.get("question_wait_sec", 900) or 0)
    budget = run_budget_end(opts)
    if budget is not None:
        end = min(end, budget - float(
            opts.get("delivery_reserve_sec", DELIVERY_RESERVE_SEC) or 0))
    return end


# R2a finding 8 (addition): the delivery reserve — a stated slice of the run
# budget that no wait, poll, HTTP timeout or retry sleep may eat, so the
# comment/confirmation/status writes always have time of their own.
DELIVERY_RESERVE_SEC = 120


def budget_left(opts):
    """Seconds the carrier may still spend WAITING: run budget end minus the
    delivery reserve, from now. None when the budget is unknown (a test, or
    an old config): nothing is capped then, as before."""
    end = run_budget_end(opts)
    if end is None:
        return None
    return end - _now(opts) - float(
        opts.get("delivery_reserve_sec", DELIVERY_RESERVE_SEC) or 0)


# R2a finding 7: the twin-carrier overlap is real. One teammate agent binds
# ONE t3 thread for every issue it owns, and the installed Paperclip CAN run
# two processes for one agent at once — per-agent concurrency defaults to 20
# runs with one child process each (`AGENT_DEFAULT_MAX_CONCURRENT_RUNS` in
# paperclipai shared/dist/constants.js:61; slot accounting in
# @paperclipai/server dist/services/heartbeat/queue.js
# startNextQueuedRunForAgent; the process spawn per run in
# server/dist/adapters/process/execute.js). Only the per-ISSUE execution run
# is single-flight. An advisory flock per thread, held from the scan to the
# end of the run, serializes the two processes on the one shared thread; a
# runner that cannot take it within its budget leaves the inbox untouched
# for the next wake (its twin already owns the thread), and a run with no
# lock directory configured behaves exactly as before.
THREAD_LOCK_BUSY = object()


def thread_lock_path(lock_dir, thread_id):
    """The advisory lock file for one t3 thread. Thread ids can contain ':'
    (node:thread:...), so keep only file-system-safe characters."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(thread_id))
    return os.path.join(str(lock_dir), f"thread-{safe}.lock")


def acquire_thread_lock(lock_dir, thread_id, opts):
    """Take the advisory lock for the bound thread (R2a finding 7).

    Returns an open file handle held by the caller for the rest of the run,
    None when no lock can be used at all (no directory configured, or the
    lock file cannot be opened — the run then proceeds exactly as before
    this guard existed), or the THREAD_LOCK_BUSY sentinel when a twin
    carrier holds the lock for longer than this run's budget allows
    waiting. The file is never removed after use: an unlink would let a
    third process lock a fresh inode beside a holder that still owns the
    old one."""
    if not lock_dir:
        return None
    path = thread_lock_path(lock_dir, thread_id)
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        log(f"thread lock {path} cannot be opened ({exc}); continuing "
            "without it")
        return None
    interval = float(opts.get("poll_interval_sec", 5) or 5)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return os.fdopen(fd, "a")
        except OSError:
            left = budget_left(opts)
            if left is not None and left <= 0:
                os.close(fd)
                return THREAD_LOCK_BUSY
            _doze(opts, min(interval, left) if left is not None
                  else interval)


def release_thread_lock(handle):
    """Drop the advisory lock at the end of the run. Closing the file
    handle releases the flock; a missing handle is a no-op."""
    if handle is not None:
        try:
            handle.close()
        except OSError:
            pass


def question_waiting(t3):
    """True when a human question waits in the thread right now."""
    thread = t3.messages(1)[0]
    return _pending_requests(thread) > 0


def thread_url(template, thread_id):
    """The conversation URL for the waiting line, or None. Same law as
    issue_url_template: carrier config only, a loopback http address only —
    the port followed by a "/", so a userinfo trick
    (`http://127.0.0.1:80@example.com/…`) cannot smuggle a foreign host
    through — never anything from issue text. `{thread}` becomes the thread
    id with `:` written as %3A."""
    if not template or not thread_id:
        return None
    if not re.match(r"http://(127\.0\.0\.1|localhost):[0-9]{2,5}/", template):
        return None
    if template.count("{thread}") != 1:
        return None
    return template.replace("{thread}", str(thread_id).replace(":", "%3A"))


def waiting_note(opts, thread_id):
    """The line that tells the reader exactly what to do (rule D; reworded
    2026-11-11 to say who waits, where to answer, for how long, and how the
    work resumes after that). <Name> is the roster entry whose agent id is
    PAPERCLIP_AGENT_ID ("The teammate" without one), <N> minutes is
    question_wait_sec // 60, and the link comes from thread_url_template only
    when it is configured and loopback."""
    name = "The teammate"
    my_id = os.environ.get("PAPERCLIP_AGENT_ID")
    for display, agent_id in (opts.get("roster") or {}).items():
        if my_id and agent_id == my_id and (display or "").strip():
            name = display
            break
    minutes = int(opts.get("question_wait_sec", 900) or 0) // 60
    url = thread_url(opts.get("thread_url_template"), thread_id)
    where = (f"Open its chat: {url} and reply there." if url
             else "Open its chat in the Team list and reply there.")
    return (f"[t2-carrier] {name}, an AI teammate, needs your answer to "
            f"continue this task. {where} If you answer within {minutes} "
            f"minutes the task continues by itself. Later than that, add "
            f"any comment here and {name} picks the work up again.")


def post_waiting_note_once(pc, issue, opts, thread_id):
    """Say the waiting line at most once in a row: when the newest comment on
    the issue already is this exact line, do not post it again. The newest
    comment is found with comment_rows, read first, as the old fixed line
    was. A Paperclip failure here must not end the wait behind it."""
    note = waiting_note(opts, thread_id)
    try:
        rows = comment_rows(pc, issue)
        if not rows or (rows[-1].get("body") or "") != note:
            pc.add_comment(issue["id"], note)
    except CarrierError:
        pass


def _read_thread_tolerant(t3, opts, deadline, interval):
    """One thread read that tolerates transient failures while a question
    wait is running: a read that fails once must not end the wait, but the
    third failure in a row does. None once the deadline has passed."""
    misses = 0
    while _now(opts) < deadline:
        try:
            return t3.messages()
        except CarrierError:
            misses += 1
            if misses >= 3:
                raise
            _doze(opts, interval)
    return None


def _poll_marker(t3, op, opts, deadline, interval):
    """Poll until marker `op` is a reply by rule A. Returns the reply text,
    or None at the deadline. Three failed thread reads in a row raise
    CarrierError; one or two do not end the wait."""
    misses = 0
    while _now(opts) < deadline:
        _doze(opts, interval)
        try:
            thread, msgs = t3.messages()
        except CarrierError:
            misses += 1
            if misses >= 3:
                raise
            continue
        misses = 0
        state, reply = scan_marker(msgs, op, thread)
        if state == "reply":
            return reply
    return None


def _poll_question_clear(t3, opts, deadline, interval):
    """Poll until no question waits in the thread: True once clear, False at
    the deadline. Three failed thread reads in a row raise CarrierError."""
    misses = 0
    while _now(opts) < deadline:
        _doze(opts, interval)
        try:
            thread = t3.messages(1)[0] or {}
            waiting = int(thread.get("pendingRequestCount") or 0)
        except CarrierError:
            misses += 1
            if misses >= 3:
                raise
            continue
        except (TypeError, ValueError):
            waiting = 0
        misses = 0
        if waiting <= 0:
            return True
    return False


def stay_with_question(pc, t3, issue, op, opts, message=None):
    """Stay with a waiting question, then finish in this same carrier run
    (rule B — fault 1 of MAS-9: nothing used to wake the task after the
    person answered).

    Three entries, one behaviour. With `message=None` the marker is already
    in the thread and pending on a question: post the waiting line once and
    poll until rule A calls the marker's run a reply. With `message` given,
    send_once has just raised NeedsHuman: either the message landed and its
    own turn stopped on a question (the marker is in the thread — same
    poll), or a question was already waiting and nothing was sent — poll
    until the question clears, scan the marker again (another wake may have
    sent it meanwhile) and only send when it is still absent. The thread
    itself tells the two apart, so nothing is ever sent twice.

    Returns the reply text. Raises NeedsHuman when the question wait
    deadline (rule C) passes without an answer — the issue stays in_progress
    and nothing is released — and CarrierError after three failed thread
    reads in a row."""
    post_waiting_note_once(pc, issue, opts, _thread_id(t3))
    deadline = question_wait_deadline(opts)
    interval = opts.get("question_poll_interval_sec", 10)
    log(f"staying with a waiting question on {issue.get('identifier')} "
        f"until {deadline:.0f}")
    if message is None:
        reply = _poll_marker(t3, op, opts, deadline, interval)
        if reply is None:
            raise NeedsHuman(_thread_id(t3))
        return reply
    sent_here = False
    while True:
        read = _read_thread_tolerant(t3, opts, deadline, interval)
        if read is None:
            raise NeedsHuman(_thread_id(t3))
        state, existing = scan_marker(read[1], op, read[0])
        if state == "reply":
            log(f"{op} answered after its question; continuing in this run")
            return existing
        if state == "pending":
            reply = _poll_marker(t3, op, opts, deadline, interval)
            if reply is None:
                raise NeedsHuman(_thread_id(t3))
            return reply
        if sent_here:
            # This stay already sent once and the marker still does not show:
            # the thread's story is inconsistent, so nothing is sent again —
            # wait on the marker to the deadline instead.
            log(f"{op} sent in this stay but not visible in the thread; "
                "waiting, no resend")
            reply = _poll_marker(t3, op, opts, deadline, interval)
            if reply is None:
                raise NeedsHuman(_thread_id(t3))
            return reply
        # The marker is absent: a question was already waiting before this
        # message. Stay until it clears, then send only if the marker is
        # still absent (another wake may have sent it meanwhile).
        if not _poll_question_clear(t3, opts, deadline, interval):
            raise NeedsHuman(_thread_id(t3))
        read = _read_thread_tolerant(t3, opts, deadline, interval)
        if read is None:
            raise NeedsHuman(_thread_id(t3))
        state, existing = scan_marker(read[1], op, read[0])
        if state == "reply":
            log(f"{op} was sent by another wake and answered; no send here")
            return existing
        if state == "pending":
            reply = _poll_marker(t3, op, opts, deadline, interval)
            if reply is None:
                raise NeedsHuman(_thread_id(t3))
            return reply
        # The send's own pre-check first (send_once's rule, inlined so the
        # flag can tell the two apart): a question that landed in the window
        # between the clear poll and now means NOTHING was sent — R2a
        # finding 24: sent_here is armed only as the send itself issues.
        thread = t3.messages(1)[0]
        if _pending_requests(thread) > 0:
            log("a question landed again just before the send; staying "
                "with it")
            continue
        try:
            log(f"question answered; sending {op} now")
            sent_here = True  # the send itself is issuing now — even a send
            # whose turn stops on a question landed (NeedsHuman below)
            result = t3.send(message)
            return result.get("reply") or ""
        except NeedsHuman:
            continue  # this fresh turn stopped on a question too: stay again


def send_and_stay(pc, t3, issue, message, op, opts):
    """Send `message`, staying with a question that comes up (rule B).

    A plain send returns its reply. When send_once raises NeedsHuman — a
    question was already waiting (nothing sent) or this very turn stopped on
    one (the message is in the thread) — stay_with_question sorts the two
    apart from the thread itself and finishes in this same run."""
    try:
        result = send_once(t3, message)
        return result.get("reply") or ""
    except NeedsHuman:
        return stay_with_question(pc, t3, issue, op, opts, message=message)


def binding_of(agent_record):
    binding = (agent_record.get("metadata") or {}).get("teammate", {}).get("t3")
    if not binding or not binding.get("primaryThreadId"):
        raise CarrierError("agent metadata has no teammate.t3.primaryThreadId")
    return binding


def public_error(exc):
    """An exception as it may appear ON an issue: the type and the status
    line only (R2a finding 13). HTTP error bodies and the t3 command's
    stderr carry server text that never belongs on a person's board — the
    full message still goes to the carrier log."""
    text = str(exc)
    text = re.sub(r"(HTTP \d{3})[\s\S]*", r"\1", text)
    text = re.sub(r"(exit \d+\)?)[\s\S]*", r"\1", text)
    text = text.split("\n")[0]
    return f"{type(exc).__name__}: {text[:200]}"


def loopback_base_error(url):
    """None when `url` is a plain loopback http base; a reason otherwise.
    Parsed with urlsplit, not hand-split, so a userinfo trick
    (`http://127.0.0.1:3100@evil.example`) or a subdomain lookalike cannot
    pass (the carrier-side pin of R2a finding 13; finding 29 states the law
    for the other tools)."""
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return "the base does not parse as a URL"
    if parts.scheme != "http":
        return f"the scheme {parts.scheme!r} is not http"
    if parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        return "the base is not loopback"
    if parts.username or parts.password:
        return "the base carries userinfo"
    if parts.port is None:
        return "the base names no port"
    if parts.path not in ("", "/"):
        return "the base carries a path"
    return None


def base_pin_error(cfg, env):
    """The refusal that stops the carrier before its first request when the
    configured `paperclip_base` (loopback only) and the PAPERCLIP_API_URL the
    adapter passed disagree (R2a finding 13). None when the config pins no
    base: the environment is then trusted, exactly as before."""
    pinned = str(cfg.get("paperclip_base") or "").strip()
    if not pinned:
        return None
    bad = loopback_base_error(pinned)
    if bad:
        return f"paperclip_base in the config is refused: {bad}"
    given = str(env.get("PAPERCLIP_API_URL") or "").strip()
    if given.rstrip("/") != pinned.rstrip("/"):
        return (f"PAPERCLIP_API_URL {given!r} differs from the pinned "
                f"paperclip_base in the config; refusing to run")
    return None


def release_issue(pc, issue_id, note):
    """On failure leave the issue visible for a person, never silently held.
    R2a finding 21: the status write reads the status first — only
    in_progress moves to todo; a done or cancelled issue keeps its status
    (the note is still posted)."""
    try:
        pc.add_comment(issue_id, f"[t2-carrier] did not complete this run: {note}")
        fresh = pc.issue(issue_id)
        if fresh.get("status") == "in_progress":
            pc.set_status(issue_id, "todo")
        else:
            log(f"release of {issue_id}: status is {fresh.get('status')!r}; "
                "left as it is")
    except CarrierError as exc:
        log(f"release of issue {issue_id} also failed: {exc}")


def deliver(pc, issue, reply, op, crash_after=None, ask_child=False):
    """Deliver the thread's answer onto the issue, idempotently ACROSS RUNS:
    comment (skip if the exact text is already posted), a pending
    request_confirmation addressed to the board (skip if this op's key already
    exists — a re-POST from another run is a 409 in this build, not a dedupe),
    then status -> in_review. A crash between steps is repaired by the next
    run without duplicating anything.

    An ask CHILD (created by another teammate's ```paperclip-ask) completes
    with done instead: its consumer is the asking teammate, whose
    issue_blockers_resolved wake fires only when every blocker reaches done —
    a pending board confirmation would strand the asker."""
    if crash_after == "pre-comment":
        log(f"CRASH_SWITCH pre-comment (run {pc.run_id}); no comment will be posted")
        os._exit(97)
    # R2a finding 26: a teammate answer that itself begins with a machine
    # prefix ([t2-carrier]/[coding-job]) would be stored looking like a
    # machine comment — last_result_comment, board_feedback and board_notes
    # all skip such bodies, so a later return edge would surface an OLDER
    # comment as "the answer". Such an answer is posted under one fixed
    # first line; the wrapper is a pure function of the answer text, so
    # exact-text dedupe across runs still matches.
    body = reply
    if is_machine_comment(reply):
        body = "Answer:\n\n" + reply
    if not comment_already_present(pc, issue["id"], body):
        pc.add_comment(issue["id"], body)
    if ask_child:
        final = "done"
    else:
        if not confirmation_already_present(pc, issue["id"], op):
            try:
                pc.request_confirmation(
                    issue["id"], f"{op}-confirm",
                    "The teammate answered in its T3 thread and the answer is posted as a "
                    "comment. Accept completes this issue; reject with a reason sends it "
                    "back for one revision round.",
                    target={"type": "custom", "key": "native_completion_review"})
            except CarrierError as exc:
                # R2a finding 6: a 409 means the key exists — this build does
                # not dedupe a re-POST. When the read-back finds THIS op's
                # key, the confirmation is already placed: success, not a
                # failure. Any other 409, or a key that is still absent,
                # fails the run as before.
                if "HTTP 409" not in str(exc) or \
                        not confirmation_already_present(pc, issue["id"], op):
                    raise
                log(f"{op}-confirm answered 409 but already exists; continuing")
        final = "in_review"
    doc = parse_output_block(reply)
    if doc:
        existing = pc.issue_document(issue["id"], doc["key"])
        if existing and (existing.get("body") or "") == doc["body"]:
            log(f"output document {doc['key']} already on "
                f"{issue.get('identifier')} with the same body; skipped")
        else:
            pc.put_issue_document(issue["id"], doc["key"],
                                  doc["title"], doc["body"])
            log(f"output document {doc['key']} written on "
                f"{issue.get('identifier')}")
    # R2a finding 21: every status write reads the status first. The board
    # may already have closed the issue (a replay wake, an accepted answer);
    # done and cancelled are never left by a delivery.
    fresh = pc.issue(issue["id"])
    if fresh.get("status") in ("done", "cancelled"):
        log(f"{issue.get('identifier')} is already {fresh.get('status')}; "
            f"the status write to {final} is skipped")
    else:
        pc.set_status(issue["id"], final)
    log(f"posted reply as comment on {issue.get('identifier')}; "
        f"status -> {final}")


def last_result_comment(pc, child):
    """The asked teammate's answer on a child issue (R2a finding 17): the
    LAST comment authored by that child's own assignee (authorType agent and
    author id equal to the child's assigneeAgentId) that is not a machine
    comment (carrier notes, coding-job results — R4b finding 5). A newer
    bystander comment never displaces the assignee's answer — only who was
    asked is being quoted to the asker. When the assignee wrote nothing
    readable, the newest non-machine comment is returned under a prefix that
    says it is NOT the asked teammate's own words; a pointer when there is
    no comment at all."""
    issue_id = child["id"] if isinstance(child, dict) else child
    assignee = child.get("assigneeAgentId") if isinstance(child, dict) else None
    try:
        rows = pc.comments(issue_id)
    except CarrierError:
        rows = []
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    if assignee:
        for row in reversed(rows):
            body = (row.get("body") or "").strip()
            # The served comment row carries authorAgentId — the board
            # serves no nested author object and no authorId (fixture
            # comments.json / child_comments.json).
            if (body and row.get("authorType") == "agent"
                    and row.get("authorAgentId") == assignee
                    and not is_machine_comment(body)):
                return body
    for row in reversed(rows):
        body = (row.get("body") or "").strip()
        if body and not is_machine_comment(body):
            return ("(the asked teammate's own comment was not found; this is "
                    "the newest comment on the child issue, not their "
                    "answer)\n\n" + body)
    return "(no answer comment on the child issue)"


def _return_op(ask_op, child, single):
    """The return marker for one ask child (R2a finding 19): the legacy
    unsuffixed op when this parent has exactly ONE ask child — existing
    in-flight threads keep their marker identity — else per-child with the
    child id, so two children of one parent never share a return turn."""
    if single:
        return f"{ask_op}-ret"
    return f"{ask_op}-{child.get('id')}-ret"


def recorded_blocker_ids(issue):
    """The blocker relation the board records for this parent, as a GET
    serves it. The installed board never serves ``blockedByIssueIds`` on
    GET /api/issues/:id — the relation arrives as ``blockedBy`` summaries
    (one projected row per blocker, each with the blocker's ``id``; fixture
    parent_2ad0bf92…). ``blockedByIssueIds`` is still read when a surface
    serves it (a PATCH response of a build that echoes the field), but it
    is never the primary signal again: code that depended on it alone was
    defending with a field that is always empty in production."""
    ids = []
    for row in (issue.get("blockedBy") or []):
        if isinstance(row, dict) and row.get("id"):
            ids.append(row["id"])
    ids.extend(iid for iid in (issue.get("blockedByIssueIds") or [])
               if isinstance(iid, str))
    seen = set()
    out = []
    for iid in ids:
        if iid not in seen:
            seen.add(iid)
            out.append(iid)
    return out


def handle_return(pc, t3, issue, ask_op, opts):
    """The issue_blockers_resolved return edge: this teammate's ask came back.

    The blocked parent was woken because every blocker (the ask child) reached
    done. Send ONE message with the child's result and link into the asker's
    primary thread — the return op is derived from the ask op, so the marker
    rule makes the send exactly-once across runs — and deliver the asker's
    final answer on the parent like any task.

    R2a finding 19: when several asks of one parent are done, every child's
    answer reaches the asker as its own return turn, OLDEST first (the
    children list serves them oldest first), and the parent's final delivery
    happens only when no ask child is open; the asker's newest answer is the
    one delivered."""
    blocker_ids = set(recorded_blocker_ids(issue))
    family = []
    for row in pc.children(issue["id"]):
        # Attack finding 5: the ask marker is derivable from public issue
        # text, so marker shape alone never selects the child whose answer
        # enters this authenticated thread. With a recorded blocker set only
        # a child in it counts; without the field (hand-blocked or legacy
        # parents) marker shape remains the only signal, as before.
        if blocker_ids and row.get("id") not in blocker_ids:
            continue
        if is_ask_child_of(row, issue):
            family.append(row)
    if not family:
        log(f"return wake on {issue.get('identifier')} but no done child for "
            f"{ask_op}; leaving the issue for a person")
        return 0
    open_rows = [row for row in family if row.get("status") != "done"]
    if open_rows:
        # R2a finding 19: the parent delivers only when no ask child is
        # open — a not-yet-done blocker keeps the parent waiting.
        log(f"return wake on {issue.get('identifier')} but ask child "
            f"{open_rows[0].get('identifier')} is still open; the parent "
            "stays blocked")
        return 0
    done_rows = family  # all done here; oldest first as the list serves them
    single = len(done_rows) == 1
    reply = None
    for child in done_rows:
        ret_op = _return_op(ask_op, child, single)
        # R2a finding 16: the bounded lookback applies to the return marker.
        state, existing, thread = scan_marker_deep(t3, ret_op)
        if state == "reply":
            log(f"{ret_op} already answered in the thread; reconciling, "
                "no resend")
            reply = existing  # the newest answered turn wins the delivery
            continue
        if state == "window_exhausted":
            # beyond the lookback bound without an answer this run can read:
            # nothing to send under the marker rule, nothing to deliver
            raise CarrierError(
                f"return marker {ret_op} is beyond the lookback bound and "
                "unreadable this run")
        result_text = last_result_comment(pc, child)
        if state is None:
            message = (
                f"[{ret_op}]\n\n"
                f"The teammate you asked finished. Their child issue "
                f"{child.get('identifier')} '{child.get('title')}' is done.\n\n"
                f"Their answer:\n\n{result_text}\n\n"
                "Use it to finish your original task: your reply to this message "
                "is posted as the issue comment and completes the issue."
            )
            log(f"sending {ret_op} to the asker's thread")
            reply = send_and_stay(pc, t3, issue, message, ret_op, opts)
        else:  # pending
            if _pending_requests(thread) > 0:
                log(f"{ret_op} is pending on a waiting question; staying with it")
                reply = stay_with_question(pc, t3, issue, ret_op, opts)
            else:
                log(f"{ret_op} already in the thread and still pending; waiting, no resend")
                reply = wait_for_reply(t3, ret_op, opts)
    if not (reply or "").strip():
        raise CarrierError("thread reply was empty")
    # Attack finding 12: the asker's post-return reply was never parsed for
    # an ask block — it was delivered raw with a confirmation and the parent
    # went in_review, so a teammate could never ask a second question after
    # a return, even inside the cap. The same ask path runs here first (and
    # depth one holds: an asked child's return never asks again).
    is_ask_child = asked_child_of(pc, issue) is not None
    ask = None if is_ask_child else parse_ask_block(reply)
    if ask:
        parent_op = op_id(issue["id"], (issue.get("title") or "")
                          + "\n" + (issue.get("description") or ""))
        if handle_ask(pc, issue, reply, ask, parent_op, opts):
            return 0
    # R2a finding 5: when the asker is ITSELF an ask child, this delivery
    # completes with done like any asked child — no board gate above it.
    deliver(pc, issue, reply, ret_op, ask_child=is_ask_child)
    return 0


# What an asked child is told instead of the ask help (depth one, R2a
# finding 4): the chain stops with it, so it must say what it still needs.
NO_ASK_NOTE = ("Another teammate asked you for this work. You cannot hand it "
               "on to a third teammate. If you cannot finish part of it "
               "yourself, say exactly what you still need in your answer.")


def machine_note_once(pc, issue_id, note):
    """One idempotent `[t2-carrier]` line on an issue: exact-text dedupe, so
    wake replays of a refusal never stack copies of the same note."""
    try:
        if not comment_already_present(pc, issue_id, note):
            pc.add_comment(issue_id, note)
    except CarrierError as exc:
        log(f"note on {issue_id} also failed: {exc}")


def handle_ask(pc, issue, reply, ask, op, opts):
    """A teammate's reply asked another teammate for work (```paperclip-ask).

    Creates the child issue under the current issue for the named teammate
    (only names in this company's roster resolve), leaves the parent blocked
    on it with an unblock descriptor, and posts the asking reply as the
    parent comment. No confirmation and no in_review: the parent is waiting,
    not ready for review. Idempotent across runs via the ask marker in the
    child description. Self-asks and asks past max_asks_per_issue (default
    3) are refused with one plain line and the reply stands as the answer.
    Returns True when the ask was placed."""
    roster = (opts or {}).get("roster") or {}
    ask_op = f"{op}-ask"
    agent_id = roster.get(ask["assignee"])
    if not agent_id:
        log(f"ask block names unknown teammate {ask['assignee']!r}; "
            "reply delivered as a plain answer, no child issue")
        return False
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID")
    if not company_id:
        log("no PAPERCLIP_COMPANY_ID; cannot create the child issue")
        return False
    me = pc.me()
    if agent_id == me.get("id"):
        # Depth zero of the depth-one rule: a teammate cannot ask itself.
        machine_note_once(pc, issue["id"],
                          f"[t2-carrier] ask {ask_op} for {ask['assignee']} "
                          "refused: a teammate cannot ask itself; the reply "
                          "stands as the answer")
        log(f"ask {ask_op} refused: {ask['assignee']} is the asker itself")
        return False
    child = None
    # Attack finding 16: the marker is the PARENT's content, so two different
    # asks on one parent share it. Reuse only the child that matches THIS ask
    # (same assignee, same sanitised title) — a revised ask to another
    # teammate gets its own child instead of being swallowed by the earlier
    # one, which left the second teammate never woken.
    want_title = strip_markers(ask["title"])
    for row in pc.children(issue["id"]):
        if (is_ask_child_of(row, issue)
                and row.get("assigneeAgentId") == agent_id
                and (row.get("title") or "") == want_title):
            child = row
            break
    if child is None:
        issued = [row for row in pc.children(issue["id"])
                  if is_issued_ask_child(row, issue)]
        # Attack finding 15: the cap comes from config; a non-numeric value
        # keeps the default (never a mid-handle crash that costs the run its
        # delivered reply), and a value below 1 is taken literally — zero
        # asks — instead of silently loosening to the default 3.
        cap = _ask_cap((opts or {}).get("max_asks_per_issue", 3))
        if len(issued) >= cap:
            machine_note_once(pc, issue["id"],
                              f"[t2-carrier] ask {ask_op} for "
                              f"{ask['assignee']} refused: the per-issue ask "
                              f"cap ({cap}) is already reached; the reply "
                              "stands as the answer")
            log(f"ask {ask_op} refused: per-issue ask cap ({cap}) reached")
            return False
        # The teammate's own words are sanitised first (R2a finding 3): no
        # `[pc-…` text it wrote can ride into the child description.
        # Attack finding 14: a title that is ONLY a marker strips to "" — the
        # fallback is a plain label, never the unsanitised ask text back.
        title = strip_markers(ask["title"]) or "Asked work"
        description = strip_markers(ask["description"])
        try:
            child = pc.create_issue(company_id, {
                "title": title,
                "description": (f"{description}\n\n"
                                f"Asked by {me.get('name', 'a teammate')} on "
                                f"{issue.get('identifier')}\n[{ask_op}]"),
                "assigneeAgentId": agent_id,
                "parentId": issue["id"],
                "status": "todo",
            })
        except CarrierError as exc:
            # R2a finding 6: the create is never retried, but its answer can
            # be lost while the server executed it — read the children back
            # for this marker before failing the run (the next wake's reuse
            # scan would find it too; this run can then finish cleanly).
            for row in pc.children(issue["id"]):
                if is_ask_child_of(row, issue):
                    log(f"ask create failed ({exc}) but child "
                        f"{row.get('identifier')} exists; continuing")
                    child = row
                    break
            if child is None:
                raise
        log(f"child issue created for {ask['assignee']}: "
            f"{child.get('identifier')} under {issue.get('identifier')}")
    else:
        log(f"ask {ask_op} already has child {child.get('identifier')}; reused")
    fresh = pc.issue(issue["id"])
    descriptor = fresh.get("unblockDescriptor") or {}
    if (fresh.get("status") != "blocked"
            or child.get("identifier") not in (descriptor.get("action") or "")):
        # This build refuses an agent naming ANOTHER agent as unblock owner
        # (403 "Agents may only name themselves as an unblock owner", live
        # 2026-11-10): the asker owns its own unblock; the action text still
        # names the teammate whose work it waits for.
        pc.block_issue(
            issue["id"], [child["id"]], me.get("id"),
            f"{ask['assignee']} completes {child.get('identifier')}: "
            f"{ask['title']}")
    if not comment_already_present(pc, issue["id"], reply):
        pc.add_comment(issue["id"], reply)
    log(f"parent {issue.get('identifier')} left blocked on "
        f"{child.get('identifier')}; no confirmation, not in_review")
    return True


def comment_rows(pc, issue):
    """An issue's comments, oldest first. Paperclip lists them newest first,
    so they are ordered here by their own timestamps; rows without one keep
    the order they came in."""
    try:
        rows = pc.comments(issue["id"])
    except CarrierError:
        return []
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    rows = list(rows)
    if rows and all(row.get("createdAt") for row in rows):
        rows.sort(key=lambda row: row["createdAt"])
    return rows


# The lane line with T4c (R4b findings 4/5): every comment the door or the
# result transport writes starts with `[coding-job]`, every note this carrier
# writes with `[t2-carrier]`. The installed Paperclip records loopback writes
# as authorType "user", so the prefix — not authorType — marks machine words.
MACHINE_COMMENT_PREFIXES = ("[coding-job]", "[t2-carrier]")


def is_machine_comment(body):
    """True when a comment body was written by a machine, not a person: after
    leading whitespace it starts with a lane prefix. Applied whatever
    authorType the row carries (R4b 4/5: machine writes come back as "user")."""
    return (body or "").lstrip().startswith(MACHINE_COMMENT_PREFIXES)


def board_feedback(pc, issue):
    """Unaddressed board feedback on an in_review issue: (reason, comment).

    A rejection is unaddressed exactly while NO pending request_confirmation
    exists: the carrier's own delivery always creates the next pending one,
    so pending present means the current round already answered the board.
    reason: the newest rejected request_confirmation's decline reason.
    comment: the newest USER comment posted after the last agent comment
    (the board's note on the answer). None when nothing new awaits.

    Feedback needs a declined answer: with no rejected confirmation nothing
    was ever sent back, so a board comment on a task that has no answer yet
    (a note left while assigning it, say) is not a revision round — the task
    itself still has to reach the teammate; board_notes() carries the note.
    A system notice is not the board speaking."""
    reason = None
    rejected = False
    try:
        rows = pc.interactions(issue["id"])
    except CarrierError:
        rows = []
    if isinstance(rows, dict):
        rows = rows.get("interactions") or rows.get("rows") or []
    pending = False
    for row in rows:  # oldest-first; the newest rejection wins
        if row.get("kind") != "request_confirmation":
            continue
        if row.get("status") == "pending":
            pending = True
        elif row.get("status") == "rejected":
            rejected = True
            text = ((row.get("result") or {}).get("reason") or "").strip()
            reason = text or reason
    if pending:
        return None  # the current round's delivery already answered the board
    if not rejected:
        return None  # no answer was declined: there is nothing to revise
    comment = None
    last_agent = -1
    newest_user = None
    for idx, row in enumerate(comment_rows(pc, issue)):
        if is_machine_comment(row.get("body")):
            continue  # a machine comment is neither the answer nor the board
        kind = row.get("authorType", "agent")
        if kind == "agent":
            last_agent = idx
            newest_user = None  # words from before this answer are not about it
        elif kind == "user" and idx > last_agent:
            newest_user = row
    if newest_user is not None:
        comment = (newest_user.get("body") or "").strip() or None
    if reason or comment:
        return reason, comment
    return None


def board_notes(pc, issue, limit=5, max_chars=2000):
    """What the board wrote on an issue that has no answer yet: the bodies of
    its user comments, oldest first, newest `limit` kept. They go into the
    first task message so a note left while assigning is not lost. Machine
    comments (is_machine_comment) are never board notes, whatever their
    authorType: the installed Paperclip records loopback writes as "user"."""
    mine = [row for row in comment_rows(pc, issue)
            if row.get("authorType") == "user"
            and (row.get("body") or "").strip()
            and not is_machine_comment(row.get("body"))]
    return [row["body"].strip()[:max_chars] for row in mine[-limit:]]


def handle_feedback(pc, t3, issue, opts):
    """The reject-with-comment edge: the board declined the teammate's answer
    on an in_review issue and left words for it. The board's comment wake
    bound this run to the issue (the inbox skips in_review rows, so the run
    binding in PAPERCLIP_ISSUE_ID is the only route to it).

    Sends ONE fresh revision marker op per feedback round — never a resend of
    the original task op — quoting the decline reason and the board's comment,
    then delivers the corrected answer like any task: comment, a NEW pending
    confirmation keyed to the round, status stays in_review."""
    feedback = board_feedback(pc, issue)
    if feedback is None:
        log(f"in_review issue {issue.get('identifier')} is bound to this run "
            "but has no board feedback; nothing to do")
        return 0
    reason, comment = feedback
    content = (issue.get("title") or "") + "\n" + (issue.get("description") or "")
    op = op_id(issue["id"], content)
    # R2a finding 16: read the deepest window for the revision scan, so a
    # round marker hidden under newer messages is still found.
    thread, messages = t3.messages(MARKER_LOOKBACK_STEPS[-1])
    # A round is closed once its delivery created its confirmation; the live
    # round is the highest numbered one whose marker exists but whose
    # delivery never completed (crash between the thread turn and deliver).
    rounds = 0
    while True:
        candidate = f"{op}-rev{rounds + 1}"
        if scan_marker(messages, candidate, thread)[0] is None:
            break
        if confirmation_already_present(pc, issue["id"], candidate):
            rounds += 1  # that round delivered; the next feedback is n + 1
            continue
        break  # started but undelivered: reconcile THIS round, no new round
    rev_op = f"{op}-rev{rounds + 1}"
    state, existing = scan_marker(messages, rev_op, thread)
    if state is None:
        message = (f"[{rev_op}]\n\n"
                   f"The board declined the current answer on "
                   f"{issue.get('identifier')} and sent it back.\n")
        if reason:
            message += f"\nDecline reason: \"{reason}\"\n"
        if comment:
            message += f"\nThe board wrote on the issue:\n\n{comment}\n"
        if scan_marker(messages, op, thread)[0] is None:
            # The task itself is not in the thread the teammate can see (it
            # was never sent here, or it has scrolled out of what the server
            # returns): a revision without the task cannot be answered.
            message += (f"\nThe task, in full:\n\n{issue.get('title') or ''}"
                        f"\n\n{(issue.get('description') or '').strip()}\n")
        message += ("\nSend a corrected final answer. Your reply to this "
                    "message is posted as the issue comment and re-enters "
                    "review.")
        log(f"sending {rev_op} (board feedback round {rounds + 1}) to the "
            "thread")
        reply = send_and_stay(pc, t3, issue, message, rev_op, opts)
    elif state == "pending":
        if _pending_requests(thread) > 0:
            log(f"{rev_op} is pending on a waiting question; staying with it")
            reply = stay_with_question(pc, t3, issue, rev_op, opts)
        else:
            log(f"{rev_op} already in the thread and still pending; waiting, "
                "no resend")
            reply = wait_for_reply(t3, rev_op, opts)
    else:
        log(f"{rev_op} already answered in the thread; reconciling, no resend")
        reply = existing
    if not reply.strip():
        raise CarrierError("thread reply was empty")
    # R2a finding 5: a revision on an ask CHILD completes with done like any
    # asked child — re-entering review would strand the asker above it.
    deliver(pc, issue, reply, rev_op,
            ask_child=asked_child_of(pc, issue) is not None)
    return 0


def confirmation_verdict(pc, issue_id, op):
    """The board's verdict on THIS op's confirmation: 'accepted', 'rejected',
    'pending', or None when the confirmation does not exist yet."""
    key = f"{op}-confirm"
    try:
        rows = pc.interactions(issue_id)
    except CarrierError:
        return None
    if isinstance(rows, dict):
        rows = rows.get("interactions") or rows.get("rows") or []
    for row in rows:
        if row.get("idempotencyKey") == key:
            return row.get("status")
    return None


def run_carrier(pc, t3_factory, opts):
    """One wake. Returns an exit code; raises nothing.

    R2a finding 7: before any scan, checkout or send, take the advisory
    lock for the bound thread and hold it for the whole run, so a second
    carrier process Paperclip started for the same agent (different issue,
    same one bound thread) cannot interleave its own send and waiting
    lines with this one's. A twin that holds the lock past this run's
    budget ends the run quietly — the twin already owns the thread, and
    the next wake picks the issue up."""
    me = pc.me()
    if me.get("id") != os.environ.get("PAPERCLIP_AGENT_ID"):
        raise CarrierError("run token is for a different agent")
    binding = binding_of(me)
    thread_id = binding["primaryThreadId"]
    lock = acquire_thread_lock(opts.get("thread_lock_dir"), thread_id, opts)
    if lock is THREAD_LOCK_BUSY:
        log(f"another carrier run holds thread {thread_id}; leaving the "
            "inbox for the next wake")
        return 0
    try:
        return _run_carrier_locked(pc, t3_factory, opts, me, binding,
                                   thread_id)
    finally:
        release_thread_lock(lock)


def _run_carrier_locked(pc, t3_factory, opts, me, binding, thread_id):
    """The carrier journey, under the thread lock taken by run_carrier."""
    crash_after = opts.get("crash_after")
    delivered = False  # R2a finding 22: set once the answer is on the issue
    t3 = t3_factory(thread_id)

    # R2a finding 12: the bound thread must belong to the bound provider
    # instance. A stale roster or a recovery that minted a second primary
    # thread on another instance would otherwise have this carrier wake a
    # DIFFERENT teammate's conversation. The thread record names its
    # instance (providerInstanceId, or the snake form) when the build
    # serves it; a mismatch is fatal before any checkout or send. A read
    # that fails here changes nothing — the normal scan below fails the
    # same way inside the protected flow — and a record that names no
    # instance cannot be checked (the journey must not break on a build
    # that lacks the field).
    try:
        first = t3.messages(1)[0] or {}
        instance = first.get("providerInstanceId") or \
            first.get("provider_instance_id")
    except Exception as exc:  # noqa: BLE001 - the scan below fails properly
        instance = None
        log(f"thread unreadable before the instance check ({exc}); "
            "continuing to the normal scan")
    if instance and binding.get("providerInstanceId") and \
            instance != binding["providerInstanceId"]:
        raise CarrierError(
            f"thread {thread_id} belongs to provider instance "
            f"{instance!r}, the binding says "
            f"{binding['providerInstanceId']!r}; refusing to send")
    if not instance:
        log("thread record names no provider instance; the instance check "
            "cannot fire this run")

    # An in_review issue is not in the inbox (inbox-lite serves
    # todo/in_progress/blocked only), so a board reply on one reaches this run
    # through the run binding: PAPERCLIP_ISSUE_ID names the issue the wake was
    # created for.
    bound = (os.environ.get("PAPERCLIP_ISSUE_ID") or "").strip()
    if bound:
        try:
            bound_issue = pc.issue(bound)
        except CarrierError as exc:
            log(f"bound issue {bound} unreadable ({exc}); continuing via the "
                "inbox")
            bound_issue = None
        if bound_issue is not None:
            if bound_issue.get("status") == "in_review":
                return handle_feedback(pc, t3, bound_issue, opts)
            log(f"bound issue {bound_issue.get('identifier')} is "
                f"{bound_issue.get('status')}; continuing via the inbox")

    candidates = choose_issue(pc.inbox(), pc.run_id)
    if not candidates:
        log("no ready issue in inbox; nothing to do")
        return 0
    issue = None
    for row in candidates:
        full = pc.issue(row["id"])
        try:
            pc.checkout(row["id"], me["id"],
                        allow_blocked=(row.get("status") == "blocked"))
        except CarrierError as exc:
            if "HTTP 409" not in str(exc):
                log(f"checkout of {row.get('identifier')} refused ({exc}); next")
                continue
            # R2a finding 25: the inbox row can predate the assignment wake
            # that bound this issue to THIS run — a 409 on a row that still
            # showed no active run must not read as a refusal. Re-read the
            # issue; the FRESH row decides: this run holds it -> proceed
            # with the fresh read; another run holds it -> real refusal.
            try:
                fresh = pc.issue(row["id"])
            except CarrierError as read_exc:
                log(f"checkout of {row.get('identifier')} got 409 and the "
                    f"re-read failed ({read_exc}); next")
                continue
            if active_run_id(fresh) == pc.run_id:
                log(f"{row.get('identifier')} already checked out by this run "
                    f"({pc.run_id}); proceeding")
                issue = fresh
                break
            log(f"checkout of {row.get('identifier')} refused ({exc}); held "
                f"by run {active_run_id(fresh) or 'unknown'}; next")
            continue
        issue = full
        break
    if issue is None:
        log("no issue could be checked out by this run")
        return 0
    log(f"checked out {issue.get('identifier')} (run {pc.run_id}); inbox "
        f"activeRun={active_run_id(row) or 'none'}")

    try:
        # Structural ask children only (R2a finding 3): parented on this
        # issue and ending with exactly the marker the carrier computes.
        ask_children = [row for row in pc.children(issue["id"])
                        if is_ask_child_of(row, issue)]
        # Attack findings 5 and 9 (attack round): the marker is derivable
        # from public issue text, so a forged or duplicate marker-matching
        # child can hijack the return edge or hold it shut forever. The
        # blocker relation the board records (the served blockedBy
        # summaries) is the binding: only a child in it can satisfy or
        # suppress the return edge. And a marker-matching family with NO
        # recorded relation is not a family the board knows — every parent
        # this carrier asked on records one (block_issue writes it before
        # the child is ever visible) — so that shape is a forged child: the
        # answer never enters this authenticated thread; a person decides.
        blocker_ids = recorded_blocker_ids(issue)
        if ask_children and not blocker_ids:
            log(f"issue {issue.get('identifier')} has marker-matching "
                "children but no recorded blocker relation; leaving it "
                "for a person")
            return 0
        if blocker_ids and ask_children:
            ask_children = [row for row in ask_children
                            if row.get("id") in blocker_ids]
            if not ask_children:
                log(f"blocked issue {issue.get('identifier')} has marker-"
                    "matching children but none of them is the recorded "
                    "blocker; leaving it for a person")
                return 0
        if issue.get("status") == "blocked" and not ask_children:
            # A blocked task with no ask child was blocked while the
            # teammate's turn may still have been in flight (a person or the
            # board blocked it). When this task's marker is in the thread the
            # normal path below finishes it — an ended run is delivered, a
            # question wait stays with it, a slow run is waited on — and
            # board feedback on it is handled there too. With no marker there
            # is nothing this run can do for it.
            content = ((issue.get("title") or "") + "\n"
                       + (issue.get("description") or ""))
            probe_op = op_id(issue["id"], content)
            try:
                probe_thread, probe_msgs = t3.messages()
            except CarrierError as exc:
                log(f"blocked issue {issue.get('identifier')} unreadable "
                    f"thread ({exc}); leaving it for a person")
                return 0
            probe_state = scan_marker(probe_msgs, probe_op, probe_thread)[0]
            if probe_state is None:
                log(f"blocked issue {issue.get('identifier')} has no ask "
                    "child and no marker in the thread; leaving it for a "
                    "person")
                return 0
            # R2a finding 15: a blocked issue with no ask child was blocked
            # by a person or the board. An ANSWERED marker alone is not
            # permission to deliver — the block is a review hold. Delivery
            # from blocked needs the carrier's own waiting line on the issue
            # (this task stopped on a question of ours; the MAS-11 journey).
            # A still-pending marker continues the normal path either way:
            # a question stay posts the waiting line itself, and the
            # slow-turn wait ends in a release for a person.
            if probe_state == "reply" and not any(
                    (row.get("body") or "").strip()
                    == waiting_note(opts, thread_id)
                    for row in comment_rows(pc, issue)):
                log(f"blocked issue {issue.get('identifier')} has an "
                    "answered marker but no carrier waiting line; a person "
                    "blocked it — leaving it for the board")
                return 0
            log(f"blocked issue {issue.get('identifier')} has its marker in "
                "the thread; continuing the normal path")
        if ask_children and all(row.get("status") == "done"
                                for row in ask_children):
            # The return edge: every ask child reached done, so this build
            # woke the asker (issue_blockers_resolved / issue_children_
            # completed — the latter may have resumed the parent out of
            # blocked already; the children, not the status, are the signal).
            return handle_return(pc, t3, issue,
                                 ask_child_op(ask_children[0]
                                              .get("description") or ""),
                                 opts)
        # The board sent a rejected answer back (often resuming the issue to
        # todo, which the inbox serves): one revision round, not a resend.
        if board_feedback(pc, issue) is not None:
            return handle_feedback(pc, t3, issue, opts)
        content = (issue.get("title") or "") + "\n" + (issue.get("description") or "")
        op = op_id(issue["id"], content)
        verdict = confirmation_verdict(pc, issue["id"], op)
        if verdict == "accepted":
            # The board accepted this op's answer (the build may have handed
            # the issue back to todo): the accepted work is complete.
            if issue.get("status") != "done":
                pc.set_status(issue["id"], "done")
            log(f"board accepted the answer on {issue.get('identifier')}; "
                "issue done")
            return 0
        # The structural test (R2a finding 3): one parent read settles
        # whether THIS issue is an ask child — used by the message build,
        # the depth-one ask rule and delivery below.
        ask_parent = asked_child_of(pc, issue)
        # R2a finding 16: the bounded lookback walks back past the latest-60
        # window before any first send, so a marker hidden under newer
        # messages cannot cause a second send of the task.
        state, existing, thread = scan_marker_deep(t3, op)
        if state == "window_exhausted":
            record = (f"[t2-carrier] sent task {op} to the teammate thread; "
                      "the thread window cannot show this turn, this line is "
                      "the record of the send")
            if comment_already_present(pc, issue["id"], record):
                log(f"{op} recorded as sent on the issue but beyond the "
                    "lookback bound; not sending again")
                reply = wait_for_reply(t3, op, opts)
                if not reply.strip():
                    raise CarrierError("thread reply was empty")
                deliver(pc, issue, reply, op,
                        ask_child=ask_parent is not None)
                return 0
            machine_note_once(pc, issue["id"], record)
            state = None  # send now, under the record
        if state is None:
            asked_child = ask_parent is not None
            message = build_message(
                issue.get("identifier"), issue.get("title"),
                issue.get("description"), op,
                link=issue_link(opts.get("issue_url_template"),
                                issue.get("identifier")),
                # An asked teammate answers; it does not pass the ask on...
                asking=None if asked_child
                else ask_help(opts.get("roster"),
                              os.environ.get("PAPERCLIP_AGENT_ID")),
                # ...and it is not offered the coding-job block either (R4b
                # finding 5): the asker owns the job decision.
                job_help=None if asked_child
                else coding_job_help(opts.get("coding_job_door")),
                notes=board_notes(pc, issue),
                # ...and it is told that it cannot ask (R2a finding 4,
                # depth one): the chain stops with it.
                no_ask=NO_ASK_NOTE if asked_child else None)
            log(f"sending {op} to thread {thread_id}")
            reply = send_and_stay(pc, t3, issue, message, op, opts)
        elif state == "pending":
            if _pending_requests(thread) > 0:
                log(f"{op} is pending on a waiting question; staying with it")
                reply = stay_with_question(pc, t3, issue, op, opts)
            else:
                log(f"{op} already in the thread and still pending; waiting, no resend")
                reply = wait_for_reply(t3, op, opts)
        else:
            log(f"{op} already answered in the thread; reconciling, no resend")
            reply = existing
        if not reply.strip():
            raise CarrierError("thread reply was empty")
        # Depth one (R2a finding 4): an asked child's reply is never parsed
        # for an ask block — the chain stops with it.
        ask = None if ask_parent else parse_ask_block(reply)
        if ask and handle_ask(pc, issue, reply, ask, op, opts):
            return 0
        deliver(pc, issue, reply, op, crash_after,
                ask_child=ask_parent is not None)
        delivered = True  # the answer is on the issue; nothing may undo it
        # Attack finding 8: depth one withholds the ask help AND the job help
        # from an asked child, but the reply was still parsed for a job block
        # — a block the asked teammate emitted anyway opened a governed door
        # the asker never authorised. The asker owns the job decision: an
        # asked child's reply is never parsed for one.
        job = None if ask_parent else parse_coding_job_block(reply)
        if job:
            handle_coding_job(pc, issue, reply, job, opts)
        return 0
    except NeedsHuman:
        try:
            # Say it once: Paperclip retries the wake, and each retry would
            # otherwise add the same line to the issue. stay_with_question
            # has usually said it already; this covers every other exit.
            post_waiting_note_once(pc, issue, opts, thread_id)
        except CarrierError:
            pass
        raise
    except Exception as exc:  # noqa: BLE001 - ANY failure must release the issue
        if delivered:
            # R2a finding 22: the answer is already on the issue in its final
            # state. A later step failing (a coding-job note, say) must never
            # release it again or move its status: log, one best-effort
            # machine note, and the delivered answer stands.
            log(f"after-delivery step failed on {issue.get('identifier')} "
                f"({public_error(exc)}); the delivered answer stands")
            machine_note_once(pc, issue["id"],
                              "[t2-carrier] a later step failed after this "
                              "answer was delivered; the answer stands")
            return 0
        release_issue(pc, issue["id"], public_error(exc))
        raise


def wait_for_reply(t3, op, opts):
    """A marker exists but its turn has not answered yet: poll, never resend.

    This is the slow-turn wait — no question is involved. Its own deadline is
    pending_timeout_sec, capped by the carrier's run budget, and a
    CarrierError at that deadline still releases the issue for a person, as
    before. When a question is waiting at the deadline the teammate is
    blocked on a person, not slow: NeedsHuman, so nothing is released (rule
    C)."""
    deadline = _now(opts) + opts.get("pending_timeout_sec", 600)
    budget = run_budget_end(opts)
    if budget is not None:
        # Same law as the question wait (R2a finding 8 addition): the tail of
        # the budget is the delivery reserve, not more waiting.
        deadline = min(deadline, budget - float(
            opts.get("delivery_reserve_sec", DELIVERY_RESERVE_SEC) or 0))
    while _now(opts) < deadline:
        _doze(opts, opts.get("poll_interval_sec", 5))
        thread, msgs = t3.messages()
        state, reply = scan_marker(msgs, op, thread)
        if state == "reply":
            return reply
    if question_waiting(t3):
        raise NeedsHuman(_thread_id(t3))
    raise CarrierError(f"{op} still pending after wait; left checked out for a person")


def comment_already_present(pc, issue_id, reply):
    """True when the exact reply text is already a comment on the issue.

    R2a finding 20: a failed comments read is NOT "not present". A comment
    POST is unkeyed (a fresh clientRequestId each time), so posting on a
    read failure can duplicate an answer that is already there — the read
    failure must fail the run before anything is posted (the best-effort
    note paths wrap this in their own try/except, as before)."""
    rows = pc.comments(issue_id)
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    for row in rows:
        if (row.get("body") or "").strip() == reply.strip():
            return True
    return False


def confirmation_already_present(pc, issue_id, op):
    """True if this op's request_confirmation already exists (a re-POST would
    be 409). An unreadable interaction list degrades to a POST attempt."""
    key = f"{op}-confirm"
    try:
        rows = pc.interactions(issue_id)
    except CarrierError:
        return False
    if isinstance(rows, dict):
        rows = rows.get("interactions") or rows.get("rows") or []
    for row in rows:
        if row.get("idempotencyKey") == key:
            return True
    return False


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_opts(cfg, environ, now, config_path=None):
    """One place that turns the carrier config file and the process
    environment into the run opts `run_carrier` takes.

    The coding-job door socket comes from the CONFIG FILE only
    (`coding_job_door`): absent means dormant — no block taught, no door
    call — exactly as before this key existed. `now` is the process start,
    recorded once by main(); the run budget is measured from it. Tests may
    override the clock, sleep and start time through these opts.

    `config_path` seeds the finding-7 thread-lock directory: the config
    file lives in the agent's own home, so its directory is the per-agent
    place for the lock file; an explicit `thread_lock_dir` key wins."""
    return {
        "crash_after": environ.get("MMOS_T2_CARRIER_CRASH_AFTER"),
        "pending_timeout_sec": cfg.get("pending_timeout_sec", 600),
        "poll_interval_sec": cfg.get("poll_interval_sec", 5),
        # The question wait (rule C): how long one carrier run stays with a
        # waiting question, the carrier's own budget from process start (the
        # process adapter allows 1500s; no wait may outlive it), and the poll
        # interval.
        "question_wait_sec": cfg.get("question_wait_sec", 900),
        "run_budget_sec": cfg.get("run_budget_sec", 1320),
        "question_poll_interval_sec": cfg.get("question_poll_interval_sec", 10),
        # Same-company teammate roster: display name -> agent id. An ask block
        # naming anyone else resolves to nothing (plain reply, no child issue).
        "roster": cfg.get("teammates") or {},
        # R2a finding 4: the per-issue ask cap; asks beyond it are refused
        # with one plain line and the reply stands as the answer. Attack
        # finding 15: coerced once here — a non-numeric value keeps the
        # default, a value below 1 is zero asks (never a silent loosening).
        "max_asks_per_issue": _ask_cap(cfg.get("max_asks_per_issue", 3)),
        # Optional: "http://127.0.0.1:<port>/<PREFIX>/issues/{identifier}".
        "issue_url_template": cfg.get("issue_url_template"),
        # Optional, same law: "http://127.0.0.1:<port>/<PREFIX>/{thread}".
        "thread_url_template": cfg.get("thread_url_template"),
        # The coding-job door (T4c owns the door itself); config only.
        "coding_job_door": cfg.get("coding_job_door"),
        # The budget clock starts once, at process start.
        "run_start": now,
        # R2a finding 8 (addition): the stated delivery reserve — the slice
        # of the run budget no wait, poll, HTTP timeout or retry sleep eats.
        "delivery_reserve_sec": cfg.get("delivery_reserve_sec",
                                        DELIVERY_RESERVE_SEC),
        # R2a finding 7: the directory for the advisory per-thread lock
        # (thread-<thread id>.lock). Defaults to the config file's own
        # directory — the agent's home — so two carrier processes Paperclip
        # starts for this agent on one host contend on one file.
        "thread_lock_dir": cfg.get("thread_lock_dir") or (
            os.path.dirname(os.path.abspath(config_path))
            if config_path else None),
    }


def main() -> int:
    required = ["PAPERCLIP_API_URL", "PAPERCLIP_API_KEY", "PAPERCLIP_RUN_ID",
                "PAPERCLIP_AGENT_ID"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        log(f"missing environment: {','.join(missing)}")
        return 2
    argv_config = sys.argv[1:]
    if not argv_config:
        log("usage: wake_carrier.py <config.json>")
        return 2
    cfg = load_config(argv_config[0])
    # R2a finding 13: a configured paperclip_base pins the address —
    # loopback only — and a different PAPERCLIP_API_URL refuses the run
    # before any request is made.
    pin = base_pin_error(cfg, os.environ)
    if pin:
        log(pin)
        return 2
    opts = build_opts(cfg, os.environ, time.time(), config_path=argv_config[0])
    # R2a finding 8: both transports take their waits from the run budget.
    pc = PaperclipClient(os.environ["PAPERCLIP_API_URL"],
                         os.environ["PAPERCLIP_API_KEY"],
                         os.environ["PAPERCLIP_RUN_ID"],
                         budget_left=lambda: budget_left(opts))
    t3_factory = lambda thread_id: T3Thread(  # noqa: E731
        cfg["t3_bin"], cfg["t3_home"], thread_id, cfg.get("t3_cwd") or "/tmp",
        t3_port=cfg.get("t3_port"), budget_left=lambda: budget_left(opts))
    try:
        return run_carrier(pc, t3_factory, opts)
    except NeedsHuman as nh:
        log(f"teammate thread {nh} is waiting for a human answer")
        return 0
    except CarrierError as exc:
        log(f"carrier failure: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - unexpected crash: one clean line, exit 1
        log(f"carrier crashed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
