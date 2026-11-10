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
replace it (adversarial finding 2026-11-10). Delivery is idempotent across
runs: an already-posted comment body and an already-created confirmation are
both detected and skipped (this build answers a re-POSTed confirmation key
from another run with 409, not a dedupe).
See T2_TEAMMATE_BINDING_AND_DISPATCH.md.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

RETRYABLE_HTTP = (408, 429, 500, 502, 503, 504)


class CarrierError(Exception):
    """Fatal carrier failure; the process exits non-zero (run ends failed)."""


class NeedsHuman(Exception):
    """The teammate is waiting for an answer in its T3 thread."""


OUTPUT_BLOCK = "paperclip-output"
ASK_BLOCK = "paperclip-ask"


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
    for line in lines[start + 1:]:
        if line.strip().startswith("```"):
            closed = True
            break
        if assignee is None and line.strip().startswith("assignee:"):
            assignee = line.split(":", 1)[1].strip()
            continue
        if title is None and line.strip().startswith("title:"):
            title = line.split(":", 1)[1].strip()
            continue
        desc_lines.append(line)
    if not closed or not assignee or not (title or "").strip():
        return None
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
    for line in lines[start + 1:]:
        if line.strip().startswith("```"):
            closed = True
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
    if not key.replace("-", "").replace("_", "").isalnum():
        return None  # document keys stay safe identifiers
    return {"key": key, "title": title or key,
            "body": "\n".join(body_lines).strip() + "\n"}


def log(message: str) -> None:
    print(f"[t2-carrier] {message}", flush=True)  # secrets are never logged


def op_id(issue_id: str, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"pc-{issue_id}-{digest}"


# A child issue created by a teammate's ```paperclip-ask block carries its
# parent's ask op marker in its description: "Asked by X on MMO-17 [pc-…-ask]".
ASK_CHILD_MARKER_RE = re.compile(r"\[(pc-[A-Za-z0-9-]+-ask)\]")


def ask_child_op(text: str):
    """The ask op marker embedded in an issue description, if any."""
    match = ASK_CHILD_MARKER_RE.search(text or "")
    return match.group(1) if match else None


def build_message(identifier: str, title: str, body: str, op: str) -> str:
    body = (body or "").strip()
    return (
        f"[{op}]\n\n"
        f"You were woken for Paperclip issue {identifier}: {title}\n\n"
        f"{body}\n\n"
        "Do the task described above. Your reply to this message is posted as "
        "the issue comment and completes the issue."
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


def scan_marker(messages, op):
    """('reply', text) | ('pending', None) | (None, None) for `op` in a thread.

    `messages` is oldest-first [(role, run_id, text)] as returned by
    T3Thread.messages(). The marker's user message and its answer share a T3
    runId; only assistant messages of THAT run are the answer (a later turn —
    a human poke, an operator side message — has a different runId and must
    never replace it). A marker whose run has not answered yet is pending.
    """
    tag = f"[{op}]"
    marker_run = None
    seen_at = None
    for idx, (role, run_id, _text) in enumerate(messages):
        if role == "user" and tag in (_text or ""):
            marker_run = run_id  # the last marker for this op wins
            seen_at = idx
    if marker_run is None:
        return None, None
    reply = None
    for role, run_id, text in messages[seen_at:]:
        if role == "assistant" and run_id == marker_run and (text or "").strip():
            reply = text
    if reply is None:
        return "pending", None
    return "reply", reply


class PaperclipClient:
    """Minimal agent-authenticated Paperclip API client (stdlib urllib).

    The bearer token is held in memory only; error paths print status codes,
    never headers or bodies that could echo it back.
    """

    def __init__(self, base_url: str, token: str, run_id: str, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self._token = token
        self.run_id = run_id
        self._timeout = timeout

    def _request(self, method: str, path: str, body=None):
        url = f"{self.base}{path}"
        data = None
        headers = {"authorization": f"Bearer {self._token}"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"
        last = None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE_HTTP and attempt < 2:
                    last = exc.code
                    time.sleep(1.5 * (attempt + 1))
                    continue
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                raise CarrierError(f"{method} {path} -> HTTP {exc.code} {detail}") from None
            except urllib.error.URLError as exc:
                if attempt < 2:
                    last = str(exc.reason)
                    time.sleep(1.5 * (attempt + 1))
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
        """Issues whose parentId is this issue. The OpenAPI lists
        /api/issues/{id}/children but this build 404s it (verified live
        2026-11-10); the company issue list filtered by parentId is the
        implemented surface."""
        company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
        rows = self._request(
            "GET", f"/api/companies/{company_id}/issues?parentId={issue_id}&limit=50")
        if isinstance(rows, dict):
            rows = rows.get("issues") or rows.get("children") or rows.get("rows") or []
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

    def __init__(self, t3_bin: str, t3_home: str, thread_id: str, scratch_dir: str):
        self._bin = os.path.expanduser(t3_bin)
        self._home = os.path.expanduser(t3_home)
        self.thread_id = thread_id
        self._cwd = os.path.expanduser(scratch_dir)

    def _run(self, args, stdin_text=None):
        env = dict(os.environ)
        env["T3CODE_HOME"] = self._home
        # text=True: subprocess wants str input, not bytes
        proc = subprocess.run(  # noqa: S603 - fixed binary, fixed args
            [self._bin, *args],
            input=stdin_text,
            capture_output=True, text=True, cwd=self._cwd, env=env, timeout=1200,
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


def binding_of(agent_record):
    binding = (agent_record.get("metadata") or {}).get("teammate", {}).get("t3")
    if not binding or not binding.get("primaryThreadId"):
        raise CarrierError("agent metadata has no teammate.t3.primaryThreadId")
    return binding


def release_issue(pc, issue_id, note):
    """On failure leave the issue visible for a person, never silently held."""
    try:
        pc.add_comment(issue_id, f"[t2-carrier] did not complete this run: {note}")
        pc.set_status(issue_id, "todo")
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
    if not comment_already_present(pc, issue["id"], reply):
        pc.add_comment(issue["id"], reply)
    if ask_child:
        final = "done"
    else:
        if not confirmation_already_present(pc, issue["id"], op):
            pc.request_confirmation(
                issue["id"], f"{op}-confirm",
                "The teammate answered in its T3 thread and the answer is posted as a "
                "comment. Accept completes this issue; reject with a reason sends it "
                "back for one revision round.",
                target={"type": "custom", "key": "native_completion_review"})
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
    pc.set_status(issue["id"], final)
    log(f"posted reply as comment on {issue.get('identifier')}; "
        f"status -> {final}")


def last_result_comment(pc, issue_id):
    """The teammate's answer on a child issue: the last comment that is not a
    carrier release note. Falls back to a pointer when there is none."""
    try:
        rows = pc.comments(issue_id)
    except CarrierError:
        rows = []
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    for row in reversed(rows):
        body = (row.get("body") or "").strip()
        if body and not body.startswith("[t2-carrier]"):
            return body
    return "(no answer comment on the child issue)"


def handle_return(pc, t3, issue, ask_op, opts):
    """The issue_blockers_resolved return edge: this teammate's ask came back.

    The blocked parent was woken because every blocker (the ask child) reached
    done. Send ONE message with the child's result and link into the asker's
    primary thread — the return op is derived from the ask op, so the marker
    rule makes the send exactly-once across runs — and deliver the asker's
    final answer on the parent like any task."""
    child = None
    for row in pc.children(issue["id"]):
        if ask_child_op(row.get("description") or "") == ask_op \
                and row.get("status") == "done":
            child = row
            break
    if child is None:
        log(f"return wake on {issue.get('identifier')} but no done child for "
            f"{ask_op}; leaving the issue for a person")
        return 0
    result_text = last_result_comment(pc, child["id"])
    ret_op = f"{ask_op}-ret"
    state, existing = scan_marker(t3.messages()[1], ret_op)
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
        result = t3.send(message)
        reply = result.get("reply") or ""
    elif state == "pending":
        log(f"{ret_op} already in the thread and still pending; waiting, no resend")
        reply = wait_for_reply(t3, ret_op, opts)
    else:
        log(f"{ret_op} already answered in the thread; reconciling, no resend")
        reply = existing
    if not reply.strip():
        raise CarrierError("thread reply was empty")
    deliver(pc, issue, reply, ret_op)
    return 0


def handle_ask(pc, issue, reply, ask, op, roster):
    """A teammate's reply asked another teammate for work (```paperclip-ask).

    Creates the child issue under the current issue for the named teammate
    (only names in this company's roster resolve), leaves the parent blocked
    on it with an unblock descriptor, and posts the asking reply as the
    parent comment. No confirmation and no in_review: the parent is waiting,
    not ready for review. Idempotent across runs via the ask marker in the
    child description. Returns True when the ask was placed."""
    ask_op = f"{op}-ask"
    agent_id = (roster or {}).get(ask["assignee"])
    if not agent_id:
        log(f"ask block names unknown teammate {ask['assignee']!r}; "
            "reply delivered as a plain answer, no child issue")
        return False
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID")
    if not company_id:
        log("no PAPERCLIP_COMPANY_ID; cannot create the child issue")
        return False
    me = pc.me()
    child = None
    for row in pc.children(issue["id"]):
        if ask_op in (row.get("description") or ""):
            child = row
            break
    if child is None:
        child = pc.create_issue(company_id, {
            "title": ask["title"],
            "description": (f"{ask['description']}\n\n"
                            f"Asked by {me.get('name', 'a teammate')} on "
                            f"{issue.get('identifier')} [{ask_op}]"),
            "assigneeAgentId": agent_id,
            "parentId": issue["id"],
            "status": "todo",
        })
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


def board_feedback(pc, issue):
    """Unaddressed board feedback on an in_review issue: (reason, comment).

    A rejection is unaddressed exactly while NO pending request_confirmation
    exists: the carrier's own delivery always creates the next pending one,
    so pending present means the current round already answered the board.
    reason: the newest rejected request_confirmation's decline reason.
    comment: the newest USER comment posted after the last agent comment
    (the board's note on the answer). None when nothing new awaits."""
    reason = None
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
            text = ((row.get("result") or {}).get("reason") or "").strip()
            reason = text or reason
    if pending:
        return None  # the current round's delivery already answered the board
    comment = None
    try:
        rows = pc.comments(issue["id"])
    except CarrierError:
        rows = []
    if isinstance(rows, dict):
        rows = rows.get("comments") or rows.get("rows") or []
    last_agent = -1
    newest_user = None
    for idx, row in enumerate(rows):
        if row.get("authorType", "agent") == "agent":
            last_agent = idx
        elif idx > last_agent:
            newest_user = row
    if newest_user is not None:
        comment = (newest_user.get("body") or "").strip() or None
    if reason or comment:
        return reason, comment
    return None


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
    messages = t3.messages()[1]
    # A round is closed once its delivery created its confirmation; the live
    # round is the highest numbered one whose marker exists but whose
    # delivery never completed (crash between the thread turn and deliver).
    rounds = 0
    while True:
        candidate = f"{op}-rev{rounds + 1}"
        if scan_marker(messages, candidate)[0] is None:
            break
        if confirmation_already_present(pc, issue["id"], candidate):
            rounds += 1  # that round delivered; the next feedback is n + 1
            continue
        break  # started but undelivered: reconcile THIS round, no new round
    rev_op = f"{op}-rev{rounds + 1}"
    state, existing = scan_marker(messages, rev_op)
    if state is None:
        message = (f"[{rev_op}]\n\n"
                   f"The board declined the current answer on "
                   f"{issue.get('identifier')} and sent it back.\n")
        if reason:
            message += f"\nDecline reason: \"{reason}\"\n"
        if comment:
            message += f"\nThe board wrote on the issue:\n\n{comment}\n"
        message += ("\nSend a corrected final answer. Your reply to this "
                    "message is posted as the issue comment and re-enters "
                    "review.")
        log(f"sending {rev_op} (board feedback round {rounds + 1}) to the "
            "thread")
        result = t3.send(message)
        reply = result.get("reply") or ""
    elif state == "pending":
        log(f"{rev_op} already in the thread and still pending; waiting, no "
            "resend")
        reply = wait_for_reply(t3, rev_op, opts)
    else:
        log(f"{rev_op} already answered in the thread; reconciling, no resend")
        reply = existing
    if not reply.strip():
        raise CarrierError("thread reply was empty")
    deliver(pc, issue, reply, rev_op)
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
    """One wake. Returns an exit code; raises nothing."""
    crash_after = opts.get("crash_after")
    me = pc.me()
    if me.get("id") != os.environ.get("PAPERCLIP_AGENT_ID"):
        raise CarrierError("run token is for a different agent")
    binding = binding_of(me)
    thread_id = binding["primaryThreadId"]
    t3 = t3_factory(thread_id)

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
        mine = active_run_id(row) == pc.run_id
        try:
            pc.checkout(row["id"], me["id"],
                        allow_blocked=(row.get("status") == "blocked"))
        except CarrierError as exc:
            if mine and "HTTP 409" in str(exc):
                # The assignment wake bound this issue to THIS run before the
                # carrier started; a 409 here means "already checked out" by
                # us. That is not a refusal — proceed with our own issue.
                log(f"{row.get('identifier')} already checked out by this run "
                    f"({pc.run_id}); proceeding")
            else:
                log(f"checkout of {row.get('identifier')} refused ({exc}); next")
                continue
        issue = full
        break
    if issue is None:
        log("no issue could be checked out by this run")
        return 0
    log(f"checked out {issue.get('identifier')} (run {pc.run_id}); inbox "
        f"activeRun={active_run_id(row) or 'none'}")

    try:
        ask_children = [row for row in pc.children(issue["id"])
                        if ask_child_op(row.get("description") or "")]
        if issue.get("status") == "blocked" and not ask_children:
            log(f"blocked issue {issue.get('identifier')} has no ask child; "
                "leaving it for a person")
            return 0
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
        state, existing = scan_marker(t3.messages()[1], op)
        if state is None:
            message = build_message(issue.get("identifier"), issue.get("title"),
                                    issue.get("description"), op)
            log(f"sending {op} to thread {thread_id}")
            result = t3.send(message)
            reply = result.get("reply") or ""
        elif state == "pending":
            log(f"{op} already in the thread and still pending; waiting, no resend")
            reply = wait_for_reply(t3, op, opts)
        else:
            log(f"{op} already answered in the thread; reconciling, no resend")
            reply = existing
        if not reply.strip():
            raise CarrierError("thread reply was empty")
        ask = parse_ask_block(reply)
        if ask and handle_ask(pc, issue, reply, ask, op,
                              opts.get("roster") or {}):
            return 0
        deliver(pc, issue, reply, op, crash_after,
                ask_child=bool(ask_child_op(issue.get("description") or "")))
        return 0
    except NeedsHuman:
        try:
            pc.add_comment(issue["id"],
                           "[t2-carrier] teammate is waiting for an answer in its "
                           "T3 thread; issue left in_progress")
        except CarrierError:
            pass
        raise
    except Exception as exc:  # noqa: BLE001 - ANY failure must release the issue
        release_issue(pc, issue["id"], f"{type(exc).__name__}: {exc}")
        raise


def wait_for_reply(t3, op, opts):
    """A marker exists but its turn has not answered yet: poll, never resend."""
    deadline = time.time() + opts.get("pending_timeout_sec", 600)
    while time.time() < deadline:
        time.sleep(opts.get("poll_interval_sec", 5))
        state, reply = scan_marker(t3.messages()[1], op)
        if state == "reply":
            return reply
    raise CarrierError(f"{op} still pending after wait; left checked out for a person")


def comment_already_present(pc, issue_id, reply):
    try:
        rows = pc.comments(issue_id)
    except CarrierError:
        return False
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
    opts = {
        "crash_after": os.environ.get("MMOS_T2_CARRIER_CRASH_AFTER"),
        "pending_timeout_sec": cfg.get("pending_timeout_sec", 600),
        "poll_interval_sec": cfg.get("poll_interval_sec", 5),
        # Same-company teammate roster: display name -> agent id. An ask block
        # naming anyone else resolves to nothing (plain reply, no child issue).
        "roster": cfg.get("teammates") or {},
    }
    pc = PaperclipClient(os.environ["PAPERCLIP_API_URL"],
                         os.environ["PAPERCLIP_API_KEY"],
                         os.environ["PAPERCLIP_RUN_ID"])
    t3_factory = lambda thread_id: T3Thread(  # noqa: E731
        cfg["t3_bin"], cfg["t3_home"], thread_id, cfg.get("t3_cwd") or "/tmp")
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
