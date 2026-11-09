# Distinct technical review — Director C (guard r5, claim_job v1.1 join, lease join) + Director E (pin moves, route fix, hermeticity)

- **Reviewer:** Claude Opus 5.5, READ_ONLY, capacity_fabric path (distinct from the GLM-5.3 authors and the
  Fable integrator). Technical assessment only — **not** a GitHub approval.
- **Reviewed at:** merged head `e6f6ce1fe` (C files byte-identical to `f1bcac76a`; E head `30c9fdd31` is an ancestor).
- **Ran:** C files 208 passed; E files 707 passed; `test_ceo_submit_armed_composition.py` 320 passed / 1 failed
  (d8 identity literal — already fixed by `70dabba15`, which post-dates the reviewed head). 86 adversarial guard
  shapes + 7 honest controls through the real `guard_bash`; 28 shapes re-run against the r4 guard (`636424a1e`);
  throwaway probes for namespace handling, lease edge cases, a 3-way merge simulation against #2177
  (`refs/pull/2177/head` = `70a6cf453`, 0 conflicts, no hunk overlap), pin sha/token checks, snapshot and golden mutations.

## Verdicts

| Row | Verdict |
|---|---|
| A1 guard r5 (#2329) | **NEEDS_REWORK** — BLOCKER regression from r4; M-A / M-B not closed |
| A2 claim_job v1.1 join (#2314 seam) | **NEEDS_REWORK** — transaction/rollback correct; `caller_namespace` value wrong |
| A3 `attach_workspace_lease` | ACCEPT_WITH_MINORS |
| B1 pin moves | **ACCEPT** |
| B2 Executive transport route fix | **ACCEPT** |
| B3 hermeticity / golden fixes | ACCEPT_WITH_MINORS |

## A. Director C — confirmed findings

1. **BLOCKER (A1, regression from r4)** `ops/executive_os/provider_orchestrator_guard.py:676` — the interpreter check
   inspects only the first word; any runner in front hides the interpreter. `env python3 -c '…for _ in range(3):
   os.system("<launch>")'` is ALLOWED (one visible launch checked, runs three times). r4 refused all six:
   `env python3 -c`, `sudo -n perl -e`, `nice node -e`, `timeout ruby -e`, `exec python3 -c`, `uv run python -c`.
   `R|Rscript` (`:316`) can never match because `_command_head` lowercases (`:576`). Unlisted interpreters allowed
   (`swift -`). **Fix:** invert the rule — admit a visible launch only when it is a plain top-level command whose first
   word is the wrapper, optionally behind a small set of transparent prefixes (`env` without `-S`/`-i`, `nohup`,
   `nice`, `timeout`, `setsid`, `exec`, `command`), with no compound shape anywhere; refuse every other command that
   contains a wrapper name.
2. **MAJOR (A1, M-A not closed)** repeated launches caught only by a fixed list. ALLOWED multipliers: `f() if …; fi`,
   `f() case …`, `builtin trap`, `alias` reuse, `C='<launch>'; $C; $C`, `"${a[@]}"` twice, `hyperfine`,
   `git bisect run`, `entr`, `launchctl submit`, crontab, zsh `repeat 3` / `for i (1 2 3)`, fish/tcsh/busybox loops.
   `_function_body_spans` (`:770`) ends at the first separator; shadow substitution (`:642`) substitutes only a bare
   wrapper name.
3. **MAJOR (A1, M-B not closed)** nested shells scanned only when the flag is exactly `-c` (`:723`): `bash -lc`,
   `bash -xc`, `env bash -c` bodies unscanned for `source`/`.`/functions. `_UNOBSERVABLE_ENV_RE` (`:232`) matches
   `eval`/`source` only right after a separator: `builtin eval "$X$Y"`, `if :; then eval …`, `builtin source`,
   `command .`, `if source …` rewrite `POOL_ORCHESTRATOR_ID` unseen. `ZDOTDIR=/tmp/evil zsh -c '<launch>'` loads
   `$ZDOTDIR/.zshenv` (BASH_ENV handled, ZDOTDIR not).
4. **Note** early return when no wrapper name appears (`:1151`): `p=po; ${p}ol run glm …` and `$'\x70ool' run glm …`
   launch with zero binding check — the documented arbitrary-process limit (r2). r5 is a lexical fence, not
   structurally closed against a hostile principal.
5. **MINOR (A4)** `_mastermind_exec` literal (guard `:1372`, from the r4 import) → d8 failure; fixed by `70dabba15`.
6. **MAJOR (A2)** `control_plane/executive_runtime.py:18965` stamps `caller_namespace=T3_REQUEST_NAMESPACE`. The merged
   adapter treats `caller_namespace` as a principal and wraps it again (`t3_execution_adapter.py:1282-1295`):
   without a port principal the envelope namespace becomes `…/v1:mastermind.control_plane.t3_execution_adapter/v1`
   (differs from the pre-join fixed namespace; `_namespace_principal` reads the constant as a principal); with a
   principal it is `…/v1:oauth-client-X`. Docstring claim at `:18923` is false. The constant records nothing toward
   DONE_WHEN 4 (original OAuth client namespace). Proposal C-P1 as written would contradict per-principal namespaces.
   **Fix:** leave `caller_namespace` empty, or stamp the bare principal once known at claim; add a claim→adapter
   equality test.
7. **MINOR (A3)** `workspace_lease.py:183` checks only `lease_status`: active-but-expired (`expires_ms=1`) accepted;
   `active_assignment_refs` naming a different attempt accepted; re-attaching a different lease silently replaces
   `lease_ref`/`workspace_ref`; no production caller yet.
8. **MINOR (A4)** `quota_preview_os_current.json` carries absolute `/Users/chriswong/...` and `~/.hermes` paths, uid 501,
   account aliases; no credentials found; one token-shaped value already `<REDACTED>`.

What checks out (A2): join inside `store.transaction()` (`BEGIN IMMEDIATE`, `:5012`) before `append_event`; generic
exception path rolls back (0 commitments, 0 attempts, QUEUED). `operation_key` derived from admitted binding fields;
no request field reaches it. Byte-for-byte claim holds at this head (`derive_t3_client_request_id` ignores v1.1 fields;
`to_dict`/`from_dict` round trip reproduces the key). Observation: key excludes attempt/generation — a retry of the same
logical child reuses the clientRequestId (Director A derivation; intent unknown).
What checks out (A3): type/kind/`LEASE_NOT_ACTIVE` refusals; same-lease re-attach equal; input unchanged; pure.
A4: `executive_worker_routes.json` and every pin file absent from the C diff; #2177 no overlap confirmed (3-way merge,
0 conflicts; two #2177 hunks already fail against `bbfad42da` itself).

### A1 adversarial-shape table (reviewer's, verbatim)
Key: MULT = one visible launch run N times; ID = launch identity rewritten unseen; obs-1 = honest single launch checked;
doc-limit = no wrapper name present; REG = r4 refused this shape.

| shape | r5 | bypass? |
|---|---|---|
| env-S | ALLOW | no (obs-1) |
| xargs-sh-c / find-exec-sh-c / awk-BEGIN-system / perl-e / ruby-e / node-e / python3-m | DENY | – |
| exec / command | ALLOW | no (obs-1) |
| builtin-eval-split-identity / then-eval-split-identity | ALLOW | **ID** |
| ansi-c-quoting `$'\x70ool'` (+ token elsewhere) | ALLOW | doc-limit (zero-binding launch) |
| indirection `${!Q}` | DENY | – |
| array-expansion-twice / var-wordsplit-twice `$C;$C` | ALLOW | **MULT** |
| eval-cmdsubst / here-string-python / here-string-bash / procsubst-bash | DENY | – |
| script-file-multiplied (`yes\|head>f; bash f`) / make-stdin / printf-format-reuse-sh-file | ALLOW | **MULT** (staged file) |
| bash-lc-eval-split / env-bash-c-eval-split / sudo-bash-c-eval | DENY | – (incidental) |
| bash-lc-function-twice / env-bash-c-function-twice / busybox-sh-c-fn | ALLOW | **MULT** |
| zsh-c / fish-c-single | ALLOW | no (obs-1) |
| zsh-repeat / zsh-for-short / fish-c-loop / tcsh-c-repeat | ALLOW | **MULT** |
| func-if-body / func-case-body / alias-reuse / builtin-trap | ALLOW | **MULT** |
| hyperfine / git-bisect-run / entr / launchctl-submit / crontab | ALLOW | **MULT** |
| at-now | ALLOW | deferred-1 (outlives lease) |
| nohup / setsid / timeout / nice / chroot / tmux / screen | ALLOW | no (obs-1) |
| osascript-js / php-r / lua-e / expect-c / dash-c-eval / mksh-c-eval | DENY | – |
| pwsh-c / julia-e | DENY | – (incidental) |
| swift-stdin / Rscript-loop / R-e-loop | ALLOW | **MULT** (R regex dead) |
| env-python3-c-loop / sudo-perl-e-loop / nice-node-e / timeout-ruby-e / exec-python3-c / uv-run-python-c | ALLOW | **MULT, REG** |
| command-awk | ALLOW | **MULT** (r4 also allowed) |
| python3.12-c / path-python-c | DENY | – |
| bash-lc-dot-source / env-bash-c-dot-source / bash-xc-source | ALLOW | **ID** |
| bash-norc-c-source / bash-c-function-twice / set-a-dot-top / BASH_ENV-export | DENY | – |
| builtin-source-top / command-dot-top / if-source-top / zsh-ZDOTDIR | ALLOW | **ID** |
| controls: plain launch, `python3 …/slot.py glm -- run`, faithful `bash -c`, inherited bare launch, `cat sub.sh`, `python3 -m pytest`, `gh pr view` | ALLOW | correct |

Totals: 40 bypasses (31 MULT, 9 ID), 6 regressions from r4, 2 doc-limit cases; all 7 honest controls pass.

## B. Director E — confirmed findings

1. **B1 pin moves — all verified.** New sha256s match at `30c9fdd31` and HEAD. Each old pin matched an earlier
   revision (`paid_fabric_backend.py` → `a1e65c2fc`; `app.py`/`auth.rs` → `3295def09`; `workspace_read_service.py` →
   `81daaca60`) — already stale at `bbfad42da`. Every moved site's source line is byte-identical (501/450/501;
   8× 400/403/503; 4× 403; 3× 503; status sites 6002/6015/6017 → 6048/6061/6063). Claimed additions confirmed
   (+106 as +1/+4/+101; +1 route constant; +4; +30). Ingress anchor: one statement inserted at index 56; reviewed subtree
   `body[3]` AST-identical. Phase-1c pin: `d7558be03` adds only a constructor guard outside `serve_installed_control`.
   New 900 pins are elapsed-time bounds / a CSS breakpoint; nothing privileged laundered. web_ceo_v3: removing only `t3`
   reproduces the prior pin; `565cff9c2` only appends `"t3"`.
2. **B2 route fix.** One fixed GET route in `_WORKSPACE_ADDITIONAL_GET_ROUTES`, not in the query list; inherits the
   https/host/origin fence and duplicate-Authorization 401; handler authenticates, refuses query strings, rechecks
   principal/evidence expiry; negative tests pass.
3. **MINOR (B3)** `tests/test_provider_quota_observation.py:497` overwrites `source_config_digest` on both sides, so a
   mutation of only `source_config_digest` is not caught. **Fix:** assert the produced `source_config_digest` equals the
   digest of the produced config before normalizing. Hermeticity fix is test-only; `capacity_bridge.py:138-139`
   unchanged; new negative test proves the refusal.

**Next dependency (reviewer):** rework guard (A1 findings 1–3) and the namespace value (finding 6), then a fresh distinct
re-review of that delta only.

**Integrator disposition (Fable):** B1/B2 accepted; B3 minor fixed by the integrator. A1/A2/A3-minors delegated to
Director C3 (Opus, implementation) with this table as the regression suite; fresh Opus re-review on return.
