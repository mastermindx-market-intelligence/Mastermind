# L4 local-operator listener — attack record (2026-11-10)

Writer: lane L4r implementation session. Target: `t3/mmos-v2-l4r`
(listener + tests as commissioned in `LOCAL_OPERATOR_CONTRACT.md`).

## Commissioned attack (grok-4.7, max two rounds) — both rounds discarded

Rule set by the principal: a finding counts only with a reproducing
command, written by the attacker to this file on a branch the writer can
read. Prose without a file does not count.

- **Round 1** — returned a report citing commit `a1b2c3d4e5f6` on
  `t3/mmos-v2-l4r-attack`. Verification: `git ls-remote origin
  t3/mmos-v2-l4r-attack` → no such ref; `git cat-file -t a1b2c3d4e5f6`
  → not a valid object. No file existed anywhere. **Discarded.**
- **Round 2** — returned "REPRODUCED" claims plus a literal ls-remote
  line `5f5f0e4a1e9b2c3d4e5f6a7b8c9d0e1f2a3b4c5d\tHEAD\tbranch
  't3/mmos-v2-l4r-attack'` (real ls-remote prints
  `<sha>\trefs/heads/<branch>`; the format itself is invented).
  Verification: no remote ref; object id does not exist; the child's
  worktree stayed clean at `073db8a5a` with no new file. **Discarded.**

Adjudication of the prose claims both rounds made (none accompanied by a
runnable command):

- *uid admission bypass via TCP tunnel* — not reproduced and internally
  incoherent: the tunnel terminates at loopback TCP; the only door the
  socket app exists behind is the Unix listener, whose sole admission is
  the kernel peer uid checked before any request byte. `tests/
  test_executive_local_operator.py::test_tcp_forged_headers_get_exactly_
  todays_refusal` proves forged loopback/XFF/invented local-operator
  headers on TCP get exactly today's refusals (403 `transport_refused`,
  401 `authentication_required`).
- *stale-socket TOCTOU / stop() inode confusion* — not an admission
  bypass: production socket parent is root-owned; a raced file is either
  refused (live) or replaced (stale). Cheap hardening landed anyway:
  `bind()` now refuses (never unlinks) a non-socket file at the path;
  `stop()` unlinks only on inode+socktype match (already true).
- *unbounded body / h11 DoS via recv loop* — false: 1 MiB app cap and
  16 MiB listener cap enforced before dispatch; the loop is
  single-threaded asyncio (there are no threads to exhaust).
- *raw subject leak* — not found: only the SHA-256 digest leaves the
  authenticator; tests assert the raw subject never appears in any
  response, `repr`, or scope.

## The principal's three h11 questions — answered by reproduction

Working state for all commands: repo root of `t3/mmos-v2-l4r`, run

```
/opt/homebrew/bin/python3.12 -m pytest -q tests/test_executive_local_operator.py -k "<selector>"
```

### A. `Expect: 100-continue` — REPRODUCED (stall), FIXED

Before the fix the listener never sent the interim response, so a
compliant client that waits for `100 Continue` before its body
deadlocked with the listener until the 300 s connection timeout.
Reproduce (at `073db8a5a`, the pre-fix parent): selector
`100_continue` — the client times out waiting for its first byte
(`step5-h11-red.txt` in the lane evidence dir). Fixed in `1e77c1bee`:
after the request event, if `http.they_are_waiting_for_100_continue`
(a **property** in h11 0.16), the listener sends
`h11.InformationalResponse(status_code=100, headers=[])` (the
`headers` kwarg is required). Test now asserts interim + final 200.

### B. Chunked request body — WORKS (no fix needed)

h11 dechunks transparently; the app receives the decoded body.
Selector `chunked`: request framed `Transfer-Encoding: chunked`
(`5\r\nhello\r\n3\r\nabc\r\n0\r\n\r\n`) arrives at the app as
`b"helloabc"` and returns 200. Green before and after the fix.

### C. App raising mid-response — REPRODUCED (silent close), FIXED

Before the fix an app exception closed the connection with zero bytes
on the wire (raw response `b''`; `step5-h11-red.txt`). Because the
listener buffers response start + body and writes only after the app
returns, the fix could send a clean `500 operator_app_failed` with
nothing partial exposed. Landed in `1e77c1bee`; selector
`mid_response` asserts `HTTP/1.1 500` with the error JSON.

### Discovered while fixing (recorded, all fixed in `1e77c1bee`)

h11 0.16 removed `Connection.they_should_keep_alive`, so the original
`try/except` around it silently returned "close" for every request —
keep-alive never worked. Keep-alive is now derived from the request's
`Connection` headers per RFC 7230 §6.3 and gated by `start_next_cycle`,
which raises when h11 knows reuse is impossible.

## Verdict

No admission bypass reproduced in two attacker rounds. Both real
defects found in this lane came from the writer's own reproduction of
the principal's three questions, not from the attacker, and both are
fixed with tests in `1e77c1bee` (suite: 28 passed).

## Second attack, 2026-11-10 (kimi-k3.1-pro tests, run by the principal)

The grok-4.7 rounds above were invented and count for nothing. A second
attacker (kimi-k3.1-pro, not the writer) was commissioned at trunk
`6a2634bb6`. Its two runs were cut short by harness turn replay: it wrote
`tests/test_executive_local_operator_attack.py` (15 tests, 18 cases) but
executed none of them and said so. The principal ran the file.

**Result: no defeat. 18 of 18 cases pass, with the 28 existing cases.**

```
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_executive_local_operator_attack.py tests/test_executive_local_operator.py
```

What the cases cover: an app that raises (500, service continues); idle
and slow connections (bounded by the 300 s connection timeout, no
starvation); oversized header block and 17 MB chunked body (closed, app
never called); conflicting `Content-Length`, and `Transfer-Encoding` with
`Content-Length` (one parser, refused or read one way); client-sent
identity headers (attribution unchanged); peer-uid lookup that raises or
returns a wrong, string or missing uid (closed before any byte); bind
over a symlink or regular file (refused, target kept) and socket mode
under a restrictive umask; the subject in logs and error bodies (absent);
TCP app refusals with the listener bound (identical).

Four corrections the principal made to the drafted tests, all in the test
client, none in the listener:

1. Header test sent 20 KB and expected a refusal. Measured: a 20 KB block
   that arrives inside one 64 KiB read is parsed and answered, because
   h11's 16 KiB cap applies to an incomplete event. The real bound is one
   read plus 16 KiB. The test now sends 200 KB, which is refused.
   **Recorded as LOW, no fix:** only a peer already admitted by uid can
   send it, and the size is bounded.
2. Body test asserted the app saw nothing, but its own follow-up GET
   reaches the app. It now asserts the app saw exactly that GET.
3. TCP test lacked the signed-token fixture the existing suite reuses.
4. The test client treated a close during send as an error; it is the
   refusal being tested.

Mutation check (listener weakened in a scratch checkout, then restored):
uid check removed, 3 peer-uid cases fail; body cap removed, the body case
fails; crash handler removed, the raising-app case fails.

**Not covered:** a connection from a genuinely different uid (the lookup
is monkeypatched), a parent directory writable by others and wider
filesystem races, sustained concurrency, and the installed config that
turns the door on. This is a scripted probe list, not a free attack; the
read-only review of the socket door in the release tail still stands.

Evidence: `~/.mastermind/mmos_evidence/l4-attack-20261110/` (`LEDGER.md`,
`principal_run1_as_drafted.txt`, `principal_run3_after_harness_fixes.txt`).
