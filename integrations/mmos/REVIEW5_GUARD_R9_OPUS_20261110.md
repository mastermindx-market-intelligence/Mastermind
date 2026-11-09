# Distinct re-check #5 — guard r9 delta (`798152b7c..9bb9e9e8e`)

Reviewer: Claude Opus 5.5, READ_ONLY, distinct from the r9 author (C8). Technical assessment, not a GitHub approval.
Verdict: **F1 PARTIAL**, **F4 NEEDS_REWORK (narrow)**, overall NEEDS_REWORK. Ran: guard policy + d8 1159 passed; the 16
review-#4 shapes: 32 sealed-shell runs (16/16 run a fake wrapper in ≥1 shell), 64 real-hook-CLI runs (r8 ALLOW/ALLOW all
16; r9 deny/deny all 16 in ≤0.08 s, gate not reached); scope differential 33,456 generated commands → deny→allow 0, 130 newly
in scope; verdict differential 12,500 commands bound+unbound → deny→allow 0, allow→deny 84 judgments (30 of 32 sampled are
exact quote-deleted twins of r8 denials; 2 are shell syntax errors); 64 reader-attack probes with sealed ground truth
(`'p' 'ool'` two words; `"p"ool` in scope; `p\ ool` one word out; `$'\x70'ool` in; `“pool”` out — homoglyph limit; honest
forms keep r8 verdicts); F4 real CLI: unarmed `gh` text r8 12.94 s no output → r9 7.08 s no output; injected 30 s step at
budget 1.5 s → unarmed 1.57 s no output, armed DENY 1.57 s; armed budget-DENY stdout byte-identical r8/r9; budgets at
262,144: 23 r8 + 15 r9 rows, worst 0.95 s, 16 quote-heavy units linear; hard constraints hold (guard/tests/ledger only, 0 test
lines deleted, d8 green).

## New findings
- **N1 MAJOR (F1 class; pre-existing in r8):** `_r8_construct_spans` (~:1075) ignores quotes; `_R6_COMPUTED_RE` (~:723)
  skips a `$(…)` containing a paren; readers ~:1349/1358/1365. A quoted/escaped/commented bracket inside a construct
  defeats the bracket matcher in both views: `$(: "("; printf p)"ool" run grok …`, `$(: "("; printf p)ool`,
  `$(: ')'; printf p)ool`, `$(: \(; printf p)ool`, `${x:-p${y#"}"}}ool`, `$(printf p # (⏎)ool`, `echo $($(: "("; printf
  p)ool …)`, `bash -c '$(: "("; printf p)ool …'`, `$(: "("; printf s)ub.sh`, `$(: "("; printf sl)ot.py glm` — sealed zsh
  and bash RUN the wrapper; armed guard ALLOWS bound and unbound (0.05–0.07 s, no binding check). Fix: a lexer-driven
  reading over `_r6_lex` segments (lit/sq/dq/esc literal, ansi decoded, param → `_r8_construct_items`, cmdsub/arith "any",
  then `_r8_items_spell`, recursing into cmdsub bodies to the depth cap; lex failure with `$`/backtick ⇒ in scope; apply to
  `bash -c` bodies). Reviewer prototype catches all 11, leaves 10 honest forms out, ≤0.04 s at 262,144.
- **N2 MODERATE (F4 fails open; worse than the ledger says):** unarmed, the quadratic heredoc stripper runs before the
  legacy identity check: `pool run grok a /tmp grok-4⏎` + N×`<<A`, no `POOL_*` env — r8 DENIED within the 10 s timeout
  (7.27/8.33/9.48 s at N=21,000/22,500/24,000 → worked on every CLI); r9 returns NO decision at 7.08 s; sealed shells run the
  fake pool. Fix: keep choice (a); compute a cheap linear "names a wrapper" flag before the stripper; on watchdog fire in an
  unarmed session DENY if flagged, no decision otherwise.
- **N3 MINOR (availability, armed):** the joined reading puts idiomatic quoted operands in scope (`cat "$f".sh`,
  `python3 "$script".py`, `cp "${src}".py "${dst}".py`, `rm -f "$tmp".sh`, `chmod +x "$f".sh`, `sed -i '' … "$f".py`,
  `mv "$(mktemp)".py out.py`, `touch "$(date +%s)".sh`, `diff <(cat "$a".py) <(cat "$b".py)`, `printf '%s\n' "$x"ool`);
  consistent with r8's unquoted refusals; ledger names only `bash "$name".sh` — document the class.
- **N4 NIT:** over-reads of backslash-newline and `${…}` inside single quotes (widen scope only).

**Integrator disposition (Fable):** Director C9 (Opus, r10): N1 lexer-driven reading, N2 unarmed-deny-when-named flag,
N3/N4 ledger; fresh distinct re-check afterwards.

## Director C9's r10 disposition (appended from the lane's own record)


Reviewer: Claude Opus 5.5, READ_ONLY at `bfa233e9f`, distinct from the r9 author (C8). Technical assessment, not a
GitHub approval. Recorded by Director C9 from the principal's brief (the reviewer's own artifact was not present in this
checkout; findings below are transcribed as the brief states them, which it marks authoritative).

**Overall: NEEDS_REWORK.** F1 (quote-adjacent glue) PARTIAL; F4 (unarmed watchdog) NEEDS_REWORK (narrow).

| # | Sev | Finding |
|---|---|---|
| N1 | MAJOR | `_r8_construct_spans` (~:1075) ignores quotes; `_R6_COMPUTED_RE` (~:723) skips a `$(…)` containing a paren; readers ~:1349/1358/1365. A quoted, escaped or commented bracket inside a construct throws off the bracket matcher in both the raw and the quote-joined view. Sealed zsh AND bash run the wrapper; armed guard ALLOWS bound and unbound in 0.05–0.07 s with no binding check; unarmed with no identity env → no output. Escapes: `$(: "("; printf p)"ool" run grok a /tmp grok-4`, `$(: "("; printf p)ool …`, `$(: ')'; printf p)ool …`, `$(: \(; printf p)ool …`, `${x:-p${y#"}"}}ool …`, `$(printf p # (⏎)ool …`, `echo $($(: "("; printf p)ool …)`, `bash -c '$(: "("; printf p)ool …'`, `$(: "("; printf s)ub.sh …`, `$(: "("; printf sl)ot.py glm …`. Proposed fix (prototyped, ≤ 0.04 s at 262 144): a reading driven by `_r6_lex` (lit/sq/dq/esc → literal, ansi → decoded, param → `_r8_construct_items`, cmdsub/arith → any, `_r8_items_spell`, recurse into cmdsub bodies to the depth cap; lexing fails and the text holds `$`/backtick → in scope; `bash -c` bodies too). Honest forms must stay out (`x=$(grep "(" f)`, `echo "a (b" $(date)`, and others). |
| N2 | MODERATE | Unarmed: the heredoc stripper runs BEFORE the legacy identity check and is quadratic: `pool run grok a /tmp grok-4⏎` + N × `<<A⏎`, no `POOL_*` env — r8 DENIED ("missing POOL_ORCHESTRATOR_ID") at 7.27/8.33/9.48 s for N = 21 000/22 500/24 000 (inside the 10 s timeout → worked on every CLI); r9 returns NO decision at 7.08 s → fails open on every CLI; sealed shells run the fake pool. Fix: keep choice (a) but compute, before the stripper, a cheap linear "raw text names a wrapper" flag (plus the N1 reading); unarmed watchdog firing → DENY if set, no decision otherwise. Optionally the linear heredoc stripper. |
| N3 | MINOR (doc) | The joined reading puts idiomatic quoted operands in scope → armed denials (bound and unbound): `cat "$f".sh`, `python3 "$script".py`, `cp "${src}".py "${dst}".py`, `rm -f "$tmp".sh`, `chmod +x "$f".sh`, `sed -i '' … "$f".py`, `mv "$(mktemp)".py out.py`, `touch "$(date +%s)".sh`, `diff <(cat "$a".py) <(cat "$b".py)`, `printf '%s\n' "$x"ool` (r8 already refused the unquoted forms). Document the class; owner decides partial-name refusal outside command position. |
| N4 | NIT | Over-reads (scope only widens): backslash-newline inside single quotes; `${…}` inside single quotes. |

Reviewer measurements to preserve: the 16 review-#4 shapes deny/deny; scope differential over 33 456 commands deny→allow 0;
budgets ≤ 0.95 s at 262 144; armed budget-DENY stdout byte-identical to r8.

Disposition: N1 + N2 → Director C9 (guard r10, branch `t3/guard-r10-lexer-scope`); N3, N4 recorded in
`LANE_EXECUTIVE_DIRECTOR_C9.md`.
