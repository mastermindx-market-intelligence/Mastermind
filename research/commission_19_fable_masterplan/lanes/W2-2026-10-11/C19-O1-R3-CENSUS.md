C19-O1-R3-CENSUS — bare-CIK translator census (READ-ONLY)
Lane id: c19-o1-r3-cik-census-20261011 · Tier: glm-5.3-flash · Budget: 3600 s wall clock (return PARTIAL at 3000 s)
Host: ubuntu2, repo ~/lanes/repos/macro. The tree is DIRTY and shared: never checkout/reset/stash/add/commit; run ONE
`git fetch origin main`, record `git rev-parse origin/main`, and read every file with `git show origin/main:<path>`.

MISSION
Enumerate every code path on Macro origin/main that converts between a bare CIK (an int, or a 10-digit zero-padded
string) and an issuer / security / entity identity WITHOUT going through the canonical binder
engine/fundamental_forensics/statement_service.py bind_canonical_identity (:133-166) or the dated resolver
lib/dataos/identity.py VendorAliasTable.resolve (:811). Produce a table the seat can act on for ledger item G9.

WHY
DEC:FIF-ENTITY-ID-IS-NOT-CIK rules that FIF entity ids are not CIKs and that there is ONE binder. WP04 (ACCEPTED) found
the composer hard-codes `ISS:US-XNAS-AAPL` (app/integrated_answer.py:306) and that IssuerMaster.issuer_of_security :997,
securities_of_issuer :1004 and cik_of_issuer :1013 take no date. Before WP05 threads identity through the composer the
seat must know whether any OTHER translator exists that a builder would be tempted to copy (a second binder is
forbidden) and whether any existing translator is undated.

SCOPE (read-only, origin/main only)
- app/**, engine/fundamental_forensics/**, engine/company_theme_exposure/**, engine/press/**, lib/dataos/**,
  scripts/**/*.py. tests/** only to NAME the test that pins a translator; a test is never itself a translator.
- Grep patterns (use `git grep -n <pattern> origin/main -- <paths>`): zfill(10) · rjust(10 · :010d · %010d ·
  cik_of_issuer · issuer_of_security · securities_of_issuer · bind_canonical_identity · VendorAliasTable ·
  "ISS: and 'ISS: · int(…cik / str(…cik · sec.gov / edgar URL or path builders that interpolate a CIK.

OUT OF SCOPE
No edits, branches, commits, pushes, PRs, posts, labels. No pytest. No fixtures over 1 MB. No Mastermind or Terminal repo.

QUESTIONS — each answer is path:line @ the ONE origin/main sha you fetched
Q1 Every function/method that ACCEPTS a bare CIK and RETURNS an issuer/security/entity id, or the reverse. Columns:
   path:line · direction (CIK→id | id→CIK | both) · dated (takes date/as_of/decision_at: yes/no) · routes through
   bind_canonical_identity or VendorAliasTable.resolve (yes/no/partial) · caller count (grep) · pinning test
   (path::name) or NONE.
Q2 Which Q1 rows are reachable TODAY from app/integrated_answer.py's financial leg (transitively via
   app/forensics._financial_query_provider → engine/fundamental_forensics/query_service.execute_financial_query →
   provider.resolve)? Print the chain with path:line per hop.
Q3 Any code that builds an `ISS:` id by string formatting (f"ISS:{…}", "ISS:" + …) outside lib/dataos/identity.py?
   path:line each, or the exact grep that found none.
Q4 Any code that builds a sec.gov/EDGAR URL or path from a CIK without one shared helper? path:line each; name the
   helper(s) that do exist.
Q5 Absence claims carry their bounds: print every grep command verbatim with its hit count and the sha.

NOT DONE UNLESS
- Q1–Q5 answered; every claim cites path:line @ one sha; every re-check command printed verbatim.
- Q1 has ≥1 row or Q5 proves the search bounds that found none.
- Nothing was written in the repo: print `git status --porcelain | wc -l` at start and at end; they must match.

EVIDENCE REQUIRED
- `git rev-parse origin/main` after the single fetch.
- For each Q1 row, 3–8 quoted source lines via `git show origin/main:<path> | sed -n 'A,Bp'`.

RETURN — your final message is exactly this packet and nothing after it
STATUS: PASS | FAIL | PARTIAL
RESULT: Q1 table · Q2 chain · Q3/Q4 lists · one paragraph answering "is there a second binder on main?"
EVIDENCE: as required above
GAPS: what you could not read and why
DEVIATIONS: anything done outside this packet
NEXT SEAT ACT: one line
Last line, exactly: C19-O1-R3-CENSUS: <PASS|FAIL|PARTIAL> <origin/main sha>
Do not end a turn on "now let me…": emit this packet, or return what you have with honest GAPS. A status note is not a return.

HARD LAWS
- Read-only. Never git checkout/reset/stash/add/commit/push/rebase; never modify the dirty tree; never run pytest.
- Never read or print ~/.opencode-go, ~/.glm, ~/.minimax, ~/.bailian, ~/.codex/auth*, any ext/*/.token, any shim.log or
  usage.jsonl. Never print credentials. Never post to Slack or GitHub. Never invent ids or shas.
