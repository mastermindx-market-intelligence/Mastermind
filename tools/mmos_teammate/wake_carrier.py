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


def log(message: str) -> None:
    print(f"[t2-carrier] {message}", flush=True)  # secrets are never logged


def op_id(issue_id: str, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"pc-{issue_id}-{digest}"


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
    not. Oldest update first."""
    def eligible(row):
        if row.get("status") not in ("todo", "in_progress"):
            return False
        if not row.get("dependencyReady", True):
            return False
        active = active_run_id(row)
        return active is None or active == my_run_id
    return sorted([r for r in rows if eligible(r)],
                  key=lambda r: r.get("updatedAt") or "")


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

    def checkout(self, issue_id, agent_id):
        # todo: human-created, untouched. in_progress: the assignment
        # automation already moved it; activeRun-null means unowned.
        return self._request(
            "POST", f"/api/issues/{issue_id}/checkout",
            {"agentId": agent_id, "expectedStatuses": ["todo", "in_progress"]},
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

    def request_confirmation(self, issue_id, idem_key, prompt):
        """A pending request_confirmation interaction is this build's review
        path: without it, an agent PATCH to in_review is refused with
        invalid_issue_disposition (422). CAUTION: re-POSTing an idempotencyKey
        that already exists from ANOTHER run is answered with 409, not a
        dedupe — callers check interactions() first."""
        return self._request(
            "POST", f"/api/issues/{issue_id}/interactions",
            {"kind": "request_confirmation", "idempotencyKey": idem_key,
             "payload": {"version": 1, "prompt": prompt}},
        )

    def set_status(self, issue_id, status):
        return self._request("PATCH", f"/api/issues/{issue_id}", {"status": status})


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


def deliver(pc, issue, reply, op, crash_after=None):
    """Deliver the thread's answer onto the issue, idempotently ACROSS RUNS:
    comment (skip if the exact text is already posted), a pending
    request_confirmation addressed to the board (skip if this op's key already
    exists — a re-POST from another run is a 409 in this build, not a dedupe),
    then status -> in_review. A crash between steps is repaired by the next
    run without duplicating anything."""
    if crash_after == "pre-comment":
        log(f"CRASH_SWITCH pre-comment (run {pc.run_id}); no comment will be posted")
        os._exit(97)
    if not comment_already_present(pc, issue["id"], reply):
        pc.add_comment(issue["id"], reply)
    if not confirmation_already_present(pc, issue["id"], op):
        pc.request_confirmation(
            issue["id"], f"{op}-confirm",
            "The teammate answered in its T3 thread and the answer is posted as a "
            "comment. Confirm it completes this issue (accept) or send it back "
            "(reject with a reason).")
    pc.set_status(issue["id"], "in_review")
    log(f"posted reply as comment on {issue.get('identifier')}; "
        "request_confirmation pending; status -> in_review")


def run_carrier(pc, t3_factory, opts):
    """One wake. Returns an exit code; raises nothing."""
    crash_after = opts.get("crash_after")
    me = pc.me()
    if me.get("id") != os.environ.get("PAPERCLIP_AGENT_ID"):
        raise CarrierError("run token is for a different agent")
    binding = binding_of(me)
    thread_id = binding["primaryThreadId"]
    t3 = t3_factory(thread_id)

    candidates = choose_issue(pc.inbox(), pc.run_id)
    if not candidates:
        log("no ready issue in inbox; nothing to do")
        return 0
    issue = None
    for row in candidates:
        full = pc.issue(row["id"])
        mine = active_run_id(row) == pc.run_id
        try:
            pc.checkout(row["id"], me["id"])
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
        content = (issue.get("title") or "") + "\n" + (issue.get("description") or "")
        op = op_id(issue["id"], content)
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
        deliver(pc, issue, reply, op, crash_after)
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
