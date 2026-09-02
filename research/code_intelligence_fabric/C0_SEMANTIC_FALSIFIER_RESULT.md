# C0 Semantic Falsifier — Result (B1–B8 repair)

`operation_key: mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001`
`canonical_packet: Mastermind #365` · `PR: #375 (DRAFT / HOLD-FOR-SOL)`
`artifact_version: mastermind.codeintel_c0_result.v1`
`wave_status: DISPOSABLE FALSIFIER / PRODUCTION_INERT`
`return: DECISION_REQUEST / PINNED_BACKEND_ACQUISITION_REQUIRED`

> **This experiment grants nothing.** No capability, MCP server, registry entry,
> workspace registry, lifecycle, retry, service, credential, deployment, market or
> trading authority is created. Nothing is installed, armed or deployed.

---

## 1. Decision

**`decision_state: BLOCKED_MISSING_PINNED_DEPENDENCY`** — **no decision enum is published.**

Neither candidate could be exercised with real pinned bytes: this host has no
Python LSP, no TypeScript/TSX LSP, and no Serena bundle at
`949a27ef1e5fda1a6e7b561e777bcece345c6ffd`. The network *is* reachable, so the
blocker is **provisioning, not connectivity**, and F0 (`network_policy = disabled`,
"immutable installed bundle"), the language/deployment amendment, the C0 plan and
Sol's own rulings all forbid this wave from resolving it. No exception was
self-authorised.

`NO_SAFE_BACKEND` was deliberately **not** emitted. It is a real result only when
both candidates were genuinely exercised and neither qualified.

---

## 2. B1–B8 closure

| Blocker | Status | Evidence |
|---|---|---|
| **B1** repository gate red | **CLOSED** | `scripts/ci_pytest.py` discovers with `rglob("test_*.py")` and passes each hit **explicitly**; pytest's ignore contract does not apply to explicit paths — measured for both `pytest_ignore_collect` **and** `collect_ignore`, so the 09:01 prescription would have left CI red. The corpus module is renamed to `consumer_case.py` and the fragile hook removed. The gate now discovers **470** modules with **zero** corpus paths (was 471 with one). |
| **B2** no path to any decision | **CLOSED** | `decision.py` is the sole ruler; the runner exercises both candidates × both languages × 5 cases × cold/warm. Per-execution binding receipts replace the single overwritten one; `--serena-sha256` is enforced; an unpinned LSP digest is a hard failure rather than an ambient recompute. |
| **B3** Candidate S was a stub | **CLOSED** | Arguments are forwarded and bounded, MCP content decoded, every returned location strict-checked against the seal, results mapped into the closed facade. A hit and a miss now differ — a stub that discards arguments cannot pass. Bundle digest enforced at start; the config-influence differential is actually executed. |
| **B4** guard insufficient | **CLOSED** | Schema requires exactly one of each candidate kind and non-synthetic coverage of every required language/case/phase before `DECIDED` is expressible; nested objects are closed; `cross_check_result()` re-derives the winner and refuses an inconsistent artifact. 15 discriminating mutants. |
| **B5** containment lexical | **CLOSED** | URIs are strict-resolved and proven regular files inside the seal, so percent-encoded traversal and escaping symlinks are refused before any read. Real `DocumentSymbol{range}` shape supported. Wire payloads bounded for size and width; one universal publication guard in the facade. |
| **B6** isolation was a claim | **CLOSED** | Network denial is **enforced** by `sandbox-exec` and **attested by a discriminating canary** (reachable without the sandbox, `PermissionError` with it). Limits are measured, not assumed. Process group isolation, descendant shutdown receipt, bounded headers, argv-artifact digests, and server-initiated mutation as a hard failure. |
| **B7** matrix incomplete | **PARTIAL** | A `.ts`/`.tsx` corpus with LSP-independent ground truth now exists and both languages execute. The protected Terminal `migrateLegacy` case is **not** materialized — see §5. A deterministic semantic-evidence digest excludes volatile observation fields. |
| **B8** cleanup unproven | **CLOSED** | Deterministic teardown with a scratch census, retained-path count and typed failure; process-group descendant receipt from the transport. |

---

## 3. The harness runs the complete contract

Sol required a demonstration that the repaired harness can execute the whole
matrix using digest-bound stand-ins that **cannot win**. It does:

| Candidate | Status | Languages | Cases | Correct |
|---|---|---|---|---|
| `direct_lsp` | EXERCISED | python, typescript | 5 | 20/20 |
| `serena` | EXERCISED | python, typescript | 5 | 12/20 |

`decision_state` for that run is still **`BLOCKED_MISSING_PINNED_DEPENDENCY`** with gate
`real_evidence_required`: every trial is marked `synthetic`, and the ruler and
schema both discard synthetic trials as evidence. Serena's 8 failures are its two
unavailable capabilities (implementations, diagnostics) recorded as **preserved
failed trials**, not omitted.

---

## 4. Source identity

| Field | Value |
|---|---|
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Branch | `sol/codeintel-c0-semantic-falsifier-20260830` |
| Base (current protected) | `cba0424f10ad6a9a917234c6740d92b19b018642` |
| Head at artifact generation | `220f5e1dd171664a494cba3b833aa5802d4d206c` |
| Changed paths vs base | 38 |
| Result digest | `f68bdacce449370786a6057bd89cc7d0db414d9aead7a248a04d18a8a00f0058` |
| Semantic evidence digest | `fcb94a787fc9cecbf965269497804b61a95cc2b0412e4c7e499c5fba5089182c` |

Protected source moved three times during execution
(`ae483cc5…` → `162af533…` → `24fa9bc4…` → `cba0424f…`). Each was joined
**history-preservingly** as a merge — never a reset, rebase, force or
regeneration — after proving the movement path- and authority-disjoint from the
C0 ceiling. The three controlling CodeIntel blobs are byte-identical at every one
of those heads.

### Changed paths and blob digests

| Path | Blob |
|---|---|
| `experiments/code_intelligence/__init__.py` | `d36f9078232118355908c5485a5ada0e0a9efa98` |
| `experiments/code_intelligence/backend.py` | `7c1fa052eea8c18bc5362a4a661f2317a8182c15` |
| `experiments/code_intelligence/c0_runner.py` | `61a355eeb4fb402ed55aef1d294d5f78273a0570` |
| `experiments/code_intelligence/decision.py` | `2e5aa9dd4e36a1659d22c8f8f511ca8f9feb982c` |
| `experiments/code_intelligence/ground_truth.py` | `6286a725e3fbae25e649a2937166265ebf98da59` |
| `experiments/code_intelligence/jsonrpc_stdio.py` | `fd2793e77bccffa41897effec24412b1a6251302` |
| `experiments/code_intelligence/lsp_backend.py` | `bcc5bb55c9bcd8445efc62d60e849b5b3f83abed` |
| `experiments/code_intelligence/sandbox.py` | `593c66c4d577f426f60e089e00c66c3caa6e94fd` |
| `experiments/code_intelligence/semantic_contract.py` | `f9cd10fbb787e20476ac9be087faf41fdeaed02f` |
| `experiments/code_intelligence/semantic_facade.py` | `c28874daee6e84c3dbdd3e51d3dd0c6fd35d66ba` |
| `experiments/code_intelligence/serena_backend.py` | `09dae38d99d9bb936d55f2775c5fb2582eb1ad68` |
| `experiments/code_intelligence/workspace_seal.py` | `5b826a70a84378c633455eac4c2ca18c224d9df6` |
| `research/code_intelligence_fabric/c0-result.schema.json` | `345ab972969fd7b8405940b6acfbb9f350609723` |
| `tests/code_intelligence/servers/fake_jsonrpc_server.py` | `9ed76e6126a3e6e26a3f32a085ad246af9af6417` |
| `tests/code_intelligence/servers/fake_lsp_server.py` | `cfa3ba55fb0730fc9fc4ed9bd66a793907ee1f73` |
| `tests/code_intelligence/servers/fake_serena_server.py` | `5cc33d9e174e12d75d771d81d45be76131626968` |
| `tests/code_intelligence/test_backend_contract.py` | `bc7b7219438ad3e5f4a7a3dd99b7f8313af5dbf6` |
| `tests/code_intelligence/test_c0_runner.py` | `47cb65490e4ab9ca90c1e05877ce3600f570769d` |
| `tests/code_intelligence/test_decision.py` | `9de989c3b622e4e6da82e6c2d61c454c578d7a6f` |
| `tests/code_intelligence/test_ground_truth.py` | `7f5ba7a5bf7731de6d8c82cde2a441c1266970c3` |
| `tests/code_intelligence/test_jsonrpc_stdio.py` | `a20d6c4f51cb9f0e3c20faf6c8e5e16612036957` |
| `tests/code_intelligence/test_lsp_backend.py` | `a8182562e98c246d3bfb2e203604b2391d04ba7c` |
| `tests/code_intelligence/test_sandbox.py` | `638265eff82e80eb0f7b2d208b22a9eda86766a8` |
| `tests/code_intelligence/test_semantic_contract.py` | `174b8606dc64269c11f6c8adf94e5d73d87ff14b` |
| `tests/code_intelligence/test_semantic_facade.py` | `acea1d10f0de51dd1f6ee0bad268c1f1733d7f28` |
| `tests/code_intelligence/test_serena_backend.py` | `7fb5ed3f79af0d38808da4ff9cc654d1e2b3e071` |
| `tests/code_intelligence/test_workspace_seal.py` | `521086628455f3f9acc4bdf1c489bdfce13bf795` |
| `tests/fixtures/code_intelligence/python_sample/answer_key.json` | `f60646ee7d18d02287cb293904fb526bf7e1c8fb` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/__init__.py` | `01d94305f6d87d0d55ba594303f7c4d73a1d0e22` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/consumer.py` | `028558dc5f6959c5df6d07b4df209356190d1b4b` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/producer.py` | `698bab9996ca4a02fe9a2ed70dce4420737f5f84` |
| `tests/fixtures/code_intelligence/python_sample/tests/consumer_case.py` | `257bbafb10a5896a0aebbefb8dbff5b949af3dfd` |
| `tests/fixtures/code_intelligence/typescript_sample/answer_key.json` | `e59c183b54136b54b0be13656b10c3e72d70c3d7` |
| `tests/fixtures/code_intelligence/typescript_sample/src/consumer.ts` | `07592c849c17dd6b37592a76d342a4ac4acb14b5` |
| `tests/fixtures/code_intelligence/typescript_sample/src/producer.ts` | `5d641e398f50970b19ceaedc1e8c13cf19085ab1` |
| `tests/fixtures/code_intelligence/typescript_sample/src/widget.tsx` | `c660fbb0ce75d4ccf2ce7fd9d9a1c37e2e997021` |
| `tests/fixtures/code_intelligence/typescript_sample/tests/consumer_case.ts` | `142e3c01b23d9cdc181a52ec66843ed2073d483a` |

Every path is inside the declared ceiling. No `control_plane/**`, `config/**`,
capability registry, workspace registry, Operator Harness, MCP profile, service,
host, credential, Slack, Linear, Agent OS, deployment, market, ranking, sizing or
trading path was modified. `integrations/code_intelligence/**` remains absent.

---

## 5. What is still NOT proven

- **No real backend semantics were measured.** Adapter proofs used stand-ins.
  They show what Mastermind's wrapper does; they say nothing about Serena or any
  real language server. Raw Serena `read_only` is treated as a negative control,
  never as a boundary.
- **The protected Terminal `migrateLegacy` case is not materialized.** It is not
  present on any pinned Terminal checkout reachable from this host — the only copy
  found is inside a *different session's* worktree, which is not a sound source
  pin. It is wired as a host-supplied input rather than vendored.
- **`RLIMIT_AS` is unenforceable on Darwin**, so address space is not bounded;
  this is reported in `unenforced_limits`, not silently swallowed.
- **No independent review.** See §7.

---

## 6. Proof summary

### Hostile checks

| Check | Outcome | Code |
|---|---|---|
| `contract_refuses_root_selection` | REFUSED_AS_REQUIRED | `SemanticContractError` |
| `contract_refuses_absolute_location` | REFUSED_AS_REQUIRED | `SemanticContractError` |
| `contract_refuses_path_traversal` | REFUSED_AS_REQUIRED | `SemanticContractError` |
| `contract_refuses_unknown_tool` | REFUSED_AS_REQUIRED | `SemanticContractError` |
| `contract_refuses_oversized_limit` | REFUSED_AS_REQUIRED | `SemanticContractError` |
| `payload_guard_refuses_absolute_path` | REFUSED_AS_REQUIRED | `PAYLOAD_ABSOLUTE_PATH` |
| `payload_guard_refuses_host_key` | REFUSED_AS_REQUIRED | `PAYLOAD_HOST_LEAK` |
| `payload_guard_refuses_secret` | REFUSED_AS_REQUIRED | `PAYLOAD_SECRET_SUSPECTED` |
| `payload_guard_refuses_unbounded_rows` | REFUSED_AS_REQUIRED | `PAYLOAD_TOO_MANY_ROWS` |
| `payload_guard_refuses_wide_collection` | REFUSED_AS_REQUIRED | `PAYLOAD_TOO_MANY_ROWS` |
| `seal_detects_candidate_tree_write` | REFUSED_AS_REQUIRED | `CANDIDATE_TREE_WRITE_DETECTED` |
| `seal_refuses_symlink_root` | REFUSED_AS_REQUIRED | `SYMLINK_ROOT_REFUSED` |
| `two_worktrees_carry_distinct_seals` | REFUSED_AS_REQUIRED | `—` |
| `scratch_refuses_candidate_tree` | REFUSED_AS_REQUIRED | `SCRATCH_INSIDE_CANDIDATE_TREE` |
| `serena_repository_config_differential` | NOT_RUN | `—` |

### Mutation kills — applied to real source, observed RED, reverted

| Mutation | Killed by |
|---|---|
| add a root-selecting field (project_path) to the find_symbol schema | `test_semantic_contract.py::test_no_schema_field_exposes_a_steering_token` |
| disable candidate-tree write detection in verify_workspace_seal | `test_workspace_seal.py::test_backend_writing_the_worktree_is_refused` |
| make the facade binding accept a foreign worktree seal | `test_semantic_facade.py::test_receipt_validation_against_a_foreign_seal_is_refused` |
| bypass the executable SHA-256 check before launch | `test_jsonrpc_stdio.py::test_wrong_digest_refuses_to_launch` |
| invert the lower-surface tie-break preference | `test_decision.py::test_tie_goes_to_the_lower_surface_candidate` |
| let latency rather than correctness select the winner | `test_decision.py::test_material_secondary_advantage_beats_the_surface_preference` |

The latency mutation is worth naming: it **survived** the first time, revealing
that the materiality band was unreachable dead code behind a `perfect` filter.
Adding the usefulness floor made the rule reachable, and the mutation now dies.

### Environment

| Item | Value |
|---|---|
| Network policy | `enforced_and_attested` |
| Sandbox available | True · profile `5c358b8d84721133…` |
| Network denied (attested) | True |
| Enforced limits | RLIMIT_CPU, RLIMIT_NOFILE, RLIMIT_NPROC |
| Unenforced limits | RLIMIT_AS |
| Third-party runtime deps added | **none** (standard library only) |
| Exposed model-facing tools | `workspace_status, symbol_overview, find_symbol, find_references, find_implementations, diagnostics` |

---

## 7. Effect state and the review gap

| Effect | State |
|---|---|
| Local | one isolated worktree, one branch |
| Remote | PR #375 DRAFT / HOLD — no `merge-on-green`, auto-merge null, not Ready |
| Production | **none** |

**Independent review remains open.** The only GitHub identity on this surface is
`chriswong6031-creator`, which also authored this branch. A review submitted from
here would be a self-review. A `DIRECT_TARGETED` independent-review operation was
delivered to this session on 2026-09-02 and was **refused**
(`PICKUP_REFUSED … LOCAL_EFFECT_CONFLICT`) on exactly that ground — it also named a
head branch, `…-20260902`, that does not exist. Sol should place the review with a
genuinely distinct reviewer identity.

---

## 8. Residual risks

- Adapter proofs used stand-in servers; real backend semantics remain unmeasured.
- The protected Terminal migrateLegacy case was not materialized: it is not present on any pinned Terminal checkout reachable from this host.
- Ground truth is a conservative census, not a type-checker.
- RLIMIT_AS is unenforceable on Darwin, so address space is not bounded.

---

## 9. Smallest next action

Provide, via B0 (`#371`) or an explicit authorisation, three immutable
digest-pinned bundles: Serena `949a27ef…`/v1.7.0, one pinned Python language
server, one pinned TypeScript/TSX language server. The harness then runs unchanged:

```
python3 -m experiments.code_intelligence.c0_runner \
  --scratch-parent <external-scratch> \
  --python-lsp-binary <pinned> --python-lsp-sha256 <digest> \
  --typescript-lsp-binary <pinned> --typescript-lsp-sha256 <digest> \
  --serena-bundle <bundle> --serena-sha256 <digest> \
  --serena-launcher-binary <pinned> --serena-launcher-sha256 <digest>
```

**No code change is required to reach a decision — only the bundles.**

---

## 10. Immutable artifact

`sha256(canonical) = f68bdacce449370786a6057bd89cc7d0db414d9aead7a248a04d18a8a00f0058`

```json
{
  "artifact_version": "mastermind.codeintel_c0_result.v1",
  "binding_receipt": {
    "facade_source_digest": "87feadaadc91aed27aefb684d24d75d8f5e18dbb07b422919870f710a2fd7bb7",
    "per_execution": [],
    "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
    "workspace_binding_digest": "0e2a58cbed86012305595b865bcee8336c718c4f6658a667354dbb26f5f5662f"
  },
  "blocking_reason": "No decision may be published: the required candidate x language x case x phase matrix was not genuinely exercised. direct_lsp missing 20 required trial(s); serena missing 20 required trial(s). Synthetic stand-in trials prove adapter behaviour and are categorically ineligible as empirical evidence.",
  "candidate_summaries": [
    {
      "complete": false,
      "correct": 0,
      "correctness": 0.0,
      "hard_failures": [
        "LSP_BINARY_UNAVAILABLE:python",
        "LSP_BINARY_UNAVAILABLE:typescript"
      ],
      "kind": "direct_lsp",
      "median_latency_ms": null,
      "missing": [
        "python/O1_definition_live_implementation/cold",
        "python/O1_definition_live_implementation/warm",
        "python/W1_references_across_files/cold",
        "python/W1_references_across_files/warm",
        "python/A3_implementations_of_protocol/cold",
        "python/A3_implementations_of_protocol/warm",
        "python/overview_single_file/cold",
        "python/overview_single_file/warm",
        "python/diagnostics_planted_undefined_name/cold",
        "python/diagnostics_planted_undefined_name/warm",
        "typescript/O1_definition_live_implementation/cold",
        "typescript/O1_definition_live_implementation/warm",
        "typescript/W1_references_across_files/cold",
        "typescript/W1_references_across_files/warm",
        "typescript/A3_implementations_of_protocol/cold",
        "typescript/A3_implementations_of_protocol/warm",
        "typescript/overview_single_file/cold",
        "typescript/overview_single_file/warm",
        "typescript/diagnostics_planted_undefined_name/cold",
        "typescript/diagnostics_planted_undefined_name/warm"
      ],
      "non_synthetic_trials": 0,
      "primary_correct": 0,
      "primary_trials": 0,
      "status": "UNEXERCISED_MISSING_BUNDLE",
      "useful": false
    },
    {
      "complete": false,
      "correct": 0,
      "correctness": 0.0,
      "hard_failures": [
        "SERENA_BUNDLE_UNAVAILABLE"
      ],
      "kind": "serena",
      "median_latency_ms": null,
      "missing": [
        "python/O1_definition_live_implementation/cold",
        "python/O1_definition_live_implementation/warm",
        "python/W1_references_across_files/cold",
        "python/W1_references_across_files/warm",
        "python/A3_implementations_of_protocol/cold",
        "python/A3_implementations_of_protocol/warm",
        "python/overview_single_file/cold",
        "python/overview_single_file/warm",
        "python/diagnostics_planted_undefined_name/cold",
        "python/diagnostics_planted_undefined_name/warm",
        "typescript/O1_definition_live_implementation/cold",
        "typescript/O1_definition_live_implementation/warm",
        "typescript/W1_references_across_files/cold",
        "typescript/W1_references_across_files/warm",
        "typescript/A3_implementations_of_protocol/cold",
        "typescript/A3_implementations_of_protocol/warm",
        "typescript/overview_single_file/cold",
        "typescript/overview_single_file/warm",
        "typescript/diagnostics_planted_undefined_name/cold",
        "typescript/diagnostics_planted_undefined_name/warm"
      ],
      "non_synthetic_trials": 0,
      "primary_correct": 0,
      "primary_trials": 0,
      "status": "UNEXERCISED_MISSING_BUNDLE",
      "useful": false
    }
  ],
  "candidates": [
    {
      "hard_failures": [
        "LSP_BINARY_UNAVAILABLE:python",
        "LSP_BINARY_UNAVAILABLE:typescript"
      ],
      "identity": null,
      "kind": "direct_lsp",
      "notes": "",
      "status": "UNEXERCISED_MISSING_BUNDLE",
      "trials": []
    },
    {
      "hard_failures": [
        "SERENA_BUNDLE_UNAVAILABLE"
      ],
      "identity": null,
      "kind": "serena",
      "notes": "No host-supplied immutable Serena bundle at the pinned commit was provided; the protected plan forbids acquiring one inside this wave.",
      "status": "UNEXERCISED_MISSING_BUNDLE",
      "trials": []
    }
  ],
  "cleanup": {
    "failure": null,
    "removed": true,
    "retained_paths": 0,
    "scratch_bytes_before": 101524,
    "scratch_files_before": 123
  },
  "corpora": [
    {
      "answer_key_digest": "a8fc681801339e5451b13cccc5716d423b4af02d32d792ef75bc23261755b6d5",
      "corpus_id": "python_sample",
      "language": "python",
      "manifest_digest": "6b42a5bfdd99aaeed8834fc61ebdac870af69cf6ca0c0b347d68d2d9de9d783f"
    },
    {
      "answer_key_digest": "7ae09d9b7ed75405adc0d1bcd5082f9ad9f64138a93cf1e23b1f77a89149c2bf",
      "corpus_id": "typescript_sample",
      "language": "typescript",
      "manifest_digest": "8ab20183b3a88aad31c1468112ce55a8819d717ead7f5b7d43aa2a40d2020037"
    }
  ],
  "decision_gates": [
    "real_evidence_required"
  ],
  "decision_state": "BLOCKED_MISSING_PINNED_DEPENDENCY",
  "environment": {
    "network_policy": "enforced_and_attested",
    "observations": [
      "macOS injects __CF_USER_TEXT_ENCODING into every spawned child; it carries the invoking uid and cannot be suppressed by this experiment.",
      "RLIMIT_NPROC on Darwin is per-user, not per process group.",
      "resource limits not enforceable on this host: RLIMIT_AS"
    ],
    "platform": "Darwin arm64",
    "python_version": "3.14.7",
    "sandbox": {
      "attestation": "dns gaierror: [Errno 8] nodename nor servname provided, or not known; tcp PermissionError: [Errno 1] Operation not permitted",
      "available": true,
      "enforced_limits": [
        "RLIMIT_CPU",
        "RLIMIT_NOFILE",
        "RLIMIT_NPROC"
      ],
      "network_denied": true,
      "profile_digest": "5c358b8d847211333e7ba22df82d84f796b5f30a41a2682209a949d783adbd08",
      "unenforced_limits": [
        "RLIMIT_AS"
      ]
    }
  },
  "exposed_tool_census": [
    "workspace_status",
    "symbol_overview",
    "find_symbol",
    "find_references",
    "find_implementations",
    "diagnostics"
  ],
  "generated_unix_ms": 1788346186128,
  "hostile_results": [
    {
      "check": "contract_refuses_root_selection",
      "code": "SemanticContractError",
      "detail": "find_symbol rejects unknown argument(s): ['project_root']",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "contract_refuses_absolute_location",
      "code": "SemanticContractError",
      "detail": "relative_file is absolute",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "contract_refuses_path_traversal",
      "code": "SemanticContractError",
      "detail": "relative_file contains an empty or traversing component",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "contract_refuses_unknown_tool",
      "code": "SemanticContractError",
      "detail": "unknown tool 'execute_shell_command'",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "contract_refuses_oversized_limit",
      "code": "SemanticContractError",
      "detail": "find_references.limit must be within 1..100",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "payload_guard_refuses_absolute_path",
      "code": "PAYLOAD_ABSOLUTE_PATH",
      "detail": "PAYLOAD_ABSOLUTE_PATH: <path>",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "payload_guard_refuses_host_key",
      "code": "PAYLOAD_HOST_LEAK",
      "detail": "PAYLOAD_HOST_LEAK: response key 'executable' exposes 'executable'",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "payload_guard_refuses_secret",
      "code": "PAYLOAD_SECRET_SUSPECTED",
      "detail": "PAYLOAD_SECRET_SUSPECTED: marker 'ghp_'",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "payload_guard_refuses_unbounded_rows",
      "code": "PAYLOAD_TOO_MANY_ROWS",
      "detail": "PAYLOAD_TOO_MANY_ROWS: 101 rows exceeds 100",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "payload_guard_refuses_wide_collection",
      "code": "PAYLOAD_TOO_MANY_ROWS",
      "detail": "PAYLOAD_TOO_MANY_ROWS: 1001 rows exceeds 100",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "seal_detects_candidate_tree_write",
      "code": "CANDIDATE_TREE_WRITE_DETECTED",
      "detail": "candidate tree bytes changed while sealed",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "seal_refuses_symlink_root",
      "code": "SYMLINK_ROOT_REFUSED",
      "detail": "<path>",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "two_worktrees_carry_distinct_seals",
      "code": null,
      "detail": "alpha and beta seals are distinct, so a cross-read cannot pass as a hit",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "scratch_refuses_candidate_tree",
      "code": "SCRATCH_INSIDE_CANDIDATE_TREE",
      "detail": "<path>",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "serena_repository_config_differential",
      "code": null,
      "detail": "no Serena bundle supplied",
      "outcome": "NOT_RUN"
    }
  ],
  "materiality_band": 0.1,
  "mutation_kills": [
    {
      "killed_by": "test_semantic_contract.py::test_no_schema_field_exposes_a_steering_token",
      "mutation": "add a root-selecting field (project_path) to the find_symbol schema"
    },
    {
      "killed_by": "test_workspace_seal.py::test_backend_writing_the_worktree_is_refused",
      "mutation": "disable candidate-tree write detection in verify_workspace_seal"
    },
    {
      "killed_by": "test_semantic_facade.py::test_receipt_validation_against_a_foreign_seal_is_refused",
      "mutation": "make the facade binding accept a foreign worktree seal"
    },
    {
      "killed_by": "test_jsonrpc_stdio.py::test_wrong_digest_refuses_to_launch",
      "mutation": "bypass the executable SHA-256 check before launch"
    },
    {
      "killed_by": "test_decision.py::test_tie_goes_to_the_lower_surface_candidate",
      "mutation": "invert the lower-surface tie-break preference"
    },
    {
      "killed_by": "test_decision.py::test_material_secondary_advantage_beats_the_surface_preference",
      "mutation": "let latency rather than correctness select the winner"
    }
  ],
  "next_action": "Sol/B0 to provide the pinned Serena bundle (949a27ef1e5fda1a6e7b561e777bcece345c6ffd / v1.7.0) and pinned Python and TypeScript/TSX language-server bundles as immutable host inputs; the harness then runs unchanged via c0_runner.",
  "operation_key": "mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001",
  "primary_cases": [
    "O1_definition_live_implementation",
    "W1_references_across_files",
    "A3_implementations_of_protocol"
  ],
  "residual_risks": [
    "Adapter proofs used stand-in servers; real backend semantics remain unmeasured.",
    "The protected Terminal migrateLegacy case was not materialized: it is not present on any pinned Terminal checkout reachable from this host.",
    "Ground truth is a conservative census, not a type-checker.",
    "RLIMIT_AS is unenforceable on Darwin, so address space is not bounded."
  ],
  "semantic_evidence_digest": "fcb94a787fc9cecbf965269497804b61a95cc2b0412e4c7e499c5fba5089182c",
  "source": {
    "base_sha": "cba0424f10ad6a9a917234c6740d92b19b018642",
    "branch": "sol/codeintel-c0-semantic-falsifier-20260830",
    "changed_paths": [
      "experiments/code_intelligence/__init__.py",
      "experiments/code_intelligence/backend.py",
      "experiments/code_intelligence/c0_runner.py",
      "experiments/code_intelligence/decision.py",
      "experiments/code_intelligence/ground_truth.py",
      "experiments/code_intelligence/jsonrpc_stdio.py",
      "experiments/code_intelligence/lsp_backend.py",
      "experiments/code_intelligence/sandbox.py",
      "experiments/code_intelligence/semantic_contract.py",
      "experiments/code_intelligence/semantic_facade.py",
      "experiments/code_intelligence/serena_backend.py",
      "experiments/code_intelligence/workspace_seal.py",
      "research/code_intelligence_fabric/C0_SEMANTIC_FALSIFIER_RESULT.md",
      "research/code_intelligence_fabric/c0-result.schema.json",
      "tests/code_intelligence/servers/fake_jsonrpc_server.py",
      "tests/code_intelligence/servers/fake_lsp_server.py",
      "tests/code_intelligence/servers/fake_serena_server.py",
      "tests/code_intelligence/test_backend_contract.py",
      "tests/code_intelligence/test_c0_runner.py",
      "tests/code_intelligence/test_decision.py",
      "tests/code_intelligence/test_ground_truth.py",
      "tests/code_intelligence/test_jsonrpc_stdio.py",
      "tests/code_intelligence/test_lsp_backend.py",
      "tests/code_intelligence/test_sandbox.py",
      "tests/code_intelligence/test_semantic_contract.py",
      "tests/code_intelligence/test_semantic_facade.py",
      "tests/code_intelligence/test_serena_backend.py",
      "tests/code_intelligence/test_workspace_seal.py",
      "tests/fixtures/code_intelligence/python_sample/answer_key.json",
      "tests/fixtures/code_intelligence/python_sample/src/sample/__init__.py",
      "tests/fixtures/code_intelligence/python_sample/src/sample/consumer.py",
      "tests/fixtures/code_intelligence/python_sample/src/sample/producer.py",
      "tests/fixtures/code_intelligence/python_sample/tests/consumer_case.py",
      "tests/fixtures/code_intelligence/typescript_sample/answer_key.json",
      "tests/fixtures/code_intelligence/typescript_sample/src/consumer.ts",
      "tests/fixtures/code_intelligence/typescript_sample/src/producer.ts",
      "tests/fixtures/code_intelligence/typescript_sample/src/widget.tsx",
      "tests/fixtures/code_intelligence/typescript_sample/tests/consumer_case.ts"
    ],
    "head_sha": "220f5e1dd171664a494cba3b833aa5802d4d206c",
    "protected_pickup_sha": "ae483cc5f101d369f368f217bb767c91fc9e0150",
    "repository": "mastermindx-market-intelligence/Mastermind"
  },
  "tie_break": "",
  "wave_status": "DISPOSABLE FALSIFIER / PRODUCTION_INERT"
}
```
