# Review record: lr-e13-r1 (PR #1756, W3-E13 fail-closed Self-Directed account load)

**Lane:** pool `ubuntu1`, model glm-5.3, class review C2_COMPLEX_BOUNDED (escalation recorded), run-id `pbr-econ-lr-e13-r1`, 2026-10-22T15:13Z–15:24Z, rc=0. The lane worktree and its tmp were removed afterwards, and the removal was verified.

**Reviewed head:** #1756 15214fca6e66f644ac294f84f1ed213c075e43ff, on master 21f057dd.

**Verdict: PASS #1756.**
- Clauses C1–C6 all conform.
- All six mutations are caught.
- Adversarial cases (a)–(i) pass.
- Generic web error payloads are byte-identical to master on the book, history and order routes.
- Regression: HEAD 262 passed, master 242 passed. The shared node ids are identical, and no existing test was edited.
- Findings: three MINOR, no BLOCKER.

## ECON disposition
- **Finding 1, vacuous probe assertion: repaired, test-only.**
  - `test_account_file_status_reads_without_writing` now snapshots the tmp tree (paths and bytes) before and after every `account_file_status` call. It also asserts no quarantine copy, no ledger row and no run event.
  - Discrimination check: under a mutation where the probe quarantines on INVALID, the old assertion passes and the new one fails. A probe that writes a stray file also fails the new assertion.
  - Production code is unchanged since this review's head 15214fca.
- **Finding 2, no dedup for unreadable/quarantine_failed rows: recorded as debt D-E13-1.**
  - The repeat rows and events are what C3 prescribes. Without bytes there is no lawful dedup key short of a marker file. Each row is small and stops once the file is repaired, and the behavior matches #1747.
- **Finding 3, `Path.exists()` returns False when stat fails: recorded as debt D-E13-2.**
  - This is pre-existing stdlib behavior and identical on master and in #1747's pattern.
  - In that state the fabricated in-memory book cannot be persisted, because the writes fail too.
  - The fix would be `os.stat` with only `FileNotFoundError` mapped to a fresh book. That is a production change, so it is out of scope for a test-only repair. It would need a new review round, and both books should change together (self_directed and paper_account).
- **Q1 and Q2:** the reviewer ruled both acceptable. The verdicts are recorded below.
- **Merge:** #1756 is RESERVED for seat merge. The commit that adds this file also carries the finding-1 test repair, and it sits after the reviewed head 15214fca.

---

# Independent frontier review — PR #1756 (W3-E13 fail-closed Self-Directed account load)

**Contract conformance (C1–C6), all verified with file:line on head `15214fc`:**

- **C1** `_load_account` (`portfolio/self_directed.py:289-312`): MISSING → fresh book (298-299); `FileNotFoundError` on read → fresh book (302-303); other read errors → `unreadable:<ExcName>` typed raise (304-306); unparseable/schema-invalid bytes → typed raise (307-309); valid → legacy `setdefault` of `starting_nav`/`inception_date` (310-311). Paths read from module globals at call time.
- **C2** `SelfDirectedAccountInvalid(RuntimeError)` (72-85): `reason_code == "self_directed_account_invalid"`, `.problems`, `.record`; message `self-directed account state invalid: <problems>` (281, 321).
- **C3** `_quarantine_invalid_account` (207-273): sha-keyed byte-for-byte copy beside the original (233-240); statuses `quarantined`/`already_quarantined`/`quarantine_failed`, failed also when bytes unavailable (228, 232); one `account_quarantine.jsonl` row + one `run_events.append` (kind `account_state_invalid`, job/book `self_directed`, step `load_account`, status `error`, severity `HARD_STOP`, actor `deterministic_engine`, extra) only for quarantined/quarantine_failed (243-268); `logging.error` on every detection (269-272); all internal failures swallowed; original never moved/renamed/rewritten (`os.replace` only ever targets the tmp file at 190).
- **C4** `validate_account_state` (98-138): sorted codes, never raises, all nine codes exactly as specified; number = int/float, not bool, finite (88-95); extra keys allowed; negative cash/shares VALID. `account_file_status(path=)` (154-178) read-only classifier, never writes/raises (proven by adversarial runs).
- **C5** `_save_account` (315-338): refuses invalid in-memory state with record `None`, no quarantine, no write (318-323); invalid existing file → quarantine + raise (325-336); otherwise atomic write of the same `json.dumps(state, indent=2, default=str)` serialization (337-338). `book`/`settle_pending`/`place_order` propagate (no catch around their `_load_account` calls); closed-market pre-read at 643 before order creation (648) and `_save_pending` (661); `mark()` (793-797) and `publish()` (726-730) catch **only** the typed error and return None before any write; `history`/`cancel_order`/`set_thesis` untouched.
- **C6** `app/web.py:2428-2443` (book), `2457-2470` (history), `2500-2508` (order): typed error contributes `reason_code`/`problems` (+`quarantine_file` on the GET routes); order route keeps status 500. Generic-exception payloads proven **byte-identical to master** by `cmp` on all three routes.

No `except Exception` site in the module can yield a fresh/fabricated book: 304/331 convert to the typed error; 137/149/168/241/247/267 are fail-closed guards or swallowed audit failures; the rest (359-484, 780-875) are the pre-existing price/clock/fill/thesis paths unrelated to account state.

```
RETURN pbr-econ-lr-e13
head: 15214fca6e66f644ac294f84f1ed213c075e43ff
findings:
  1. MINOR — tests/test_self_directed_invalid_state.py:411-412 — `assert listing() == listing()` compares two listings both taken AFTER the probe calls; it is vacuously true and does not pin "the probe never writes" (needs a before/after comparison). Test fragility only; the probe is read-only by inspection and by adversarial runs (a)/(b)/(d).
  2. MINOR — portfolio/self_directed.py:243 — unreadable/quarantine_failed detections are not deduplicated (no bytes → no sha key): every dashboard GET / scheduler sweep on a persistently unreadable account.json appends one ledger row + one HARD_STOP event until repair; a concurrent first-detection race can also double-append rows for identical bytes (the copy itself stays byte-identical via atomic replace). This is exactly what C3 prescribes (row+event on quarantine_failed) and the BLOCKER clause is bytes-keyed, so audit-growth fragility only — not a blocker.
  3. MINOR — portfolio/self_directed.py:298 — `Path.exists()` returns False when stat itself fails (e.g. the data dir loses search permission), so `_load_account` can return an in-memory fresh $1M book. Pre-existing stdlib semantics, identical on master and in the #1747 pattern (not introduced by this PR); in that same permission state `_save_account`'s writes fail → the fabricated book cannot be persisted and the web routes render unavailable. Fragility note only.
fresh_book_sites:
  - portfolio/self_directed.py:299 (`if not _ACCOUNT_PATH.exists()`) -> reachable only when absent? yes (modulo stdlib exists()-on-stat-failure, finding 3)
  - portfolio/self_directed.py:303 (`except FileNotFoundError`) -> reachable only when absent? yes (file vanishes between exists() and read; legitimate per C1)
callers:
  - app/web.py:654 _persisted_book_quotes | typed -> broad except -> account={} (snapshot-only price candidates; no funded/zero book) | OK
  - app/web.py:1077+1097 api_live_marks | typed -> route except -> degraded `live_marks_unavailable`, positions [] | OK
  - app/web.py:1549-1550 _portfolio_status | typed -> except Exception: pass -> row lacks nav/holdings (dashes, no fabricated numbers) | OK
  - app/web.py:2413-2421 api_self_directed | typed -> 200 unavailable + reason_code/problems/quarantine_file | OK
  - app/web.py:2451-2456 api_self_directed_history | typed -> 200 unavailable + typed fields | OK
  - app/web.py:2500 api_self_directed_order | typed -> 500 {ok:false,error,reason_code,problems}; no pending.json written | OK
  - app/scheduler.py:1402-1419 _daily_mark_job | typed -> broad except -> mark/publish skipped (same visible outcome as the old fresh-empty-book skip) + quarantine/event fired | OK
  - app/web.py:2528 thesis/cancel + 2489 quote routes | never read account.json | OK (unchanged)
adversarial:
  (a) account.json as DIRECTORY -> typed `unreadable:IsADirectoryError`, dir intact, 1 event, order refused, no pending.json — PASS
  (b) top-level JSON array -> `not_an_object`, original intact — PASS
  (c) "" position key + bool shares -> `position_key_invalid:''` + `position_shares_invalid:`; non-str in-memory key handled, validator never raises — PASS
  (d) read-only data dir -> typed still raised, record quarantine_failed + quarantine_error, original bytes intact, no copy, 1 event — PASS
  (e) negative cash/shares classify VALID; _save_account round-trip reloads identical; zero events — PASS
  (f) closed-market BUY on invalid book -> refused, no pending.json, no fills.jsonl, account.json untouched — PASS
  (g) mark() -> None, no nav row (pre-existing nav_history row also untouched); publish() -> None, no published file — PASS
  (h) same bytes 3x -> exactly 1 copy/row/event; changed bytes -> 2nd copy/row/event; original bytes again -> still 2 — PASS
  (i) generic RuntimeError("synthetic") -> payload byte-identical to master (cmp) for book, history AND order routes — PASS
mutations: (each on a fresh copy of pristine head; 3 contract test files)
  (i) fresh-book fallback restored -> 14 failures: test_invalid_book_class_fails_closed_everywhere[all 9], test_unreadable_book_fails_closed_with_a_failed_quarantine_record, test_redetection_is_idempotent_and_new_bytes_get_their_own_copy, test_invalid_book_is_never_overwritten_and_the_fresh_branch_is_unreachable, test_web_book_route_reports_the_typed_invalid_account, test_web_order_route_reports_the_typed_invalid_account | CAUGHT
  (ii) quarantine by os.replace (move) -> 13 failures: fails_closed_everywhere[9], redetection, never_overwritten, test_save_refuses_to_overwrite_an_existing_invalid_file, web_order_route | CAUGHT
  (iii) closed-market pre-read removed -> 12 failures: fails_closed_everywhere[9], unreadable_book, never_overwritten, web_order_route | CAUGHT
  (iv) ledger row on already_quarantined -> 10 failures: fails_closed_everywhere[9] (single-detection asserts) + redetection | CAUGHT
  (v) web book route ignores typed reason_code -> 1 failure: test_web_book_route_reports_the_typed_invalid_account | CAUGHT
  (vi) _save_account writes without existing-file check -> 2 failures: test_save_refuses_to_overwrite_an_existing_invalid_file, test_invalid_book_is_never_overwritten_and_the_fresh_branch_is_unreachable | CAUGHT
  none UNCAUGHT
tests: (venv ~/lanes/tmp/pbr-econ-sh2-venv, -B -p no:cacheprovider -o addopts="")
  tests/test_self_directed.py | HEAD pass | master pass
  tests/test_self_directed_invalid_state.py | HEAD pass (20) | n/a (new file)
  tests/test_pbr_self_unavailable.py | HEAD pass | master pass
  tests/test_web.py | HEAD pass | master pass
  tests/test_firm_exposure.py | HEAD pass | master pass
  tests/test_portfolio_dashboard_ui.py | HEAD pass | master pass
  tests/test_book_lifecycle.py | HEAD pass | master pass
  tests/test_portfolio_archival.py | HEAD pass | master pass
  tests/test_mw6_security.py | HEAD pass | master pass
  tests/test_scheduler_governance.py | HEAD pass | master pass
  HEAD 262 passed / master 242 passed; the 242 shared node ids are identical (collect-only diff empty); the diff contains NO edit to any existing test (excluded-diff empty)
open_questions: Q1 verdict: acceptable audit semantic — the idempotence guarantee is bytes-keyed by design and C3 itself mandates a row+event on quarantine_failed; with no bytes there is no lawful dedup key short of a marker file, each row is small and repair-bounded, and it matches the #1747 semantics; MINOR growth note (finding 2), not a BLOCKER ; Q2 verdict: acceptable — the packet named only reason_code + problems for the order route; the POST's recovery action is human repair of the file and quarantine_file is discoverable from the book-route payload and the ledger row; generic order errors keep the exact historical {ok,error} shape (byte-identity proven)
authority: every write in the diff — (1) quarantine copy via _atomic_write_bytes (incl. transient .tmp + os.replace) | expected; (2) account_quarantine.jsonl append | expected; (3) one lazy control_plane.run_events.append | expected; (4) _save_account atomic account.json write replacing the old non-atomic write_text | expected. No other writes; no change to NAV/mark/settlement math (mark/publish bodies untouched except the early typed return); no import from portfolio.paper_account (docstrings only); no path into sizing/ranking/execution (module consumers are the web routes and the scheduler mark/publish seam; firm_exposure reads only the published latest.json, which publish() declines to rewrite on an invalid book)
VERDICT: PASS #1756 — every clause C1–C6 conforms, all six mutations are caught, no fresh-book/overwrite path survives, generic web responses are byte-identical, and the three findings are MINOR fragility notes.
commands_run: git log/rev-parse/status/diff (worktree, read-only); grep/awk over app/, portfolio/, tests/; scratch setup: git archive HEAD/master -> ~/lanes/tmp/pbr-econ-lr-e13/{head,master} + vendor/macro_src symlink; 9 adversarial tests (tests/test_adv_lr_e13.py) on head + (i)/(generic-history/order) byte-compares vs master via cmp; mutate.py applying 6 mutations each on a fresh pristine copy + 3-file pytest runs; regression runs on head (262) and master (242); collect-only node-id diff
not_verified: #1747's actual code is not present in this master, so its parity is accepted from the packet, not independently diffed; concurrent first-detection race (finding 2) is reasoned, not stress-tested; the exists()-on-stat-failure path (finding 3) is stdlib semantics, not executed; no live data/, no network, no UI rendering beyond route payloads
```

All experiment artifacts live under `~/lanes/tmp/pbr-econ-lr-e13/`; the review worktree at `15214fc` is confirmed clean and unmodified.
