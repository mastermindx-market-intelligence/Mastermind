# C0 Semantic Falsifier — Result

`operation_key: mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001`
`canonical_packet: mastermindx-market-intelligence/Mastermind issue #365`
`artifact_version: mastermind.codeintel_c0_result.v1`
`wave_status: DISPOSABLE FALSIFIER / PRODUCTION_INERT`

> **This experiment grants nothing.** It is a disposable falsifier. It installs no
> capability, registers no MCP server, starts no service and selects no production
> backend.

---

## 1. Decision

**`decision_state: BLOCKED_MISSING_PINNED_DEPENDENCY`** — **no decision enum is published.**

`SERENA`, `DIRECT_LSP` and `NO_SAFE_BACKEND` are all empirical claims. None of them
was earned, because neither candidate could be run at all:

- **Candidate L (direct LSP):** `LSP_BINARY_UNAVAILABLE`. This host carries no Python
  language server and no TypeScript/TSX language server — no `pyright`, `pylsp`,
  `jedi-language-server`, `typescript-language-server` or `tsserver`, and no `uv`,
  `uvx` or `pipx` with which a pinned one could be resolved from an existing bundle.
- **Candidate S (pinned Serena):** `SERENA_BUNDLE_UNAVAILABLE`. No immutable bundle at
  `949a27ef1e5fda1a6e7b561e777bcece345c6ffd` / v1.7.0 exists anywhere on this host.

`NO_SAFE_BACKEND` was deliberately **not** emitted. The protected plan admits it as a
successful result only "when honestly proven"; proving it requires exercising both
candidates and finding both unsafe. Reporting it from an empty bench would assert a
measurement that never happened. The packet's own failure law resolves the tension:
*"missing pinned dependency ... fails closed."* So this fails closed.

The result schema enforces this structurally rather than trusting the author — see §6.

### Why this is a provisioning question, not a connectivity one

The host **can** reach `github.com`, `pypi.org` and `registry.npmjs.org` (HTTP 200,
measured). The blocker is therefore permission-shaped, and every authority level
forbids the experiment from resolving it itself:

| Authority | Binding text |
|---|---|
| F0 architecture (blob `987156c2…`) | `network_policy = disabled`; resolve the binary "from an immutable installed bundle" |
| Language/deployment amendment (blob `32e0b610…`) | forbids "automatic package download or type acquisition" and "network lookup" |
| C0 plan (blob `54a92715…`) | Global constraint "No network access"; Task 4 Step 5: absence of a pin-able server is a truthful `LSP_BINARY_UNAVAILABLE`, "**not permission to download latest or use PATH ambiently**" |

I did not self-authorise an exception. The bundles are a host-side input this wave
does not own.

---

## 2. Source identity

| Field | Value |
|---|---|
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Branch | `sol/codeintel-c0-semantic-falsifier-20260830` |
| Base (`merge-base` with `origin/master`) | `162af533a4bcf380125895d225b6962987c3c582` |
| Head at artifact generation | `9af49061b8558af4cb60672c6690b5eb0ab606ef` |
| Protected pickup SHA | `ae483cc5f101d369f368f217bb767c91fc9e0150` |
| Changed paths | 29 |

The head above is the code head. This report is the only later commit, and it is
documentation-only; re-running `c0_runner` at the report head reproduces the same
artifact apart from `generated_unix_ms`.

Authority blobs were verified identical at the protected pickup SHA **and** at current
`origin/master` before any edit — no source movement.

### Changed paths and blob digests

| Path | Blob |
|---|---|
| `experiments/code_intelligence/__init__.py` | `d36f9078232118355908c5485a5ada0e0a9efa98` |
| `experiments/code_intelligence/backend.py` | `5042b89f1ce40885740935832944b67a2f96e0f7` |
| `experiments/code_intelligence/c0_runner.py` | `d0e931732e742e7191972824a26aadcfefa92505` |
| `experiments/code_intelligence/ground_truth.py` | `549a4361e327e382f082a6ae5a814b4e04f330a6` |
| `experiments/code_intelligence/jsonrpc_stdio.py` | `4e50a62cccff5ddd670728646d06a8d421700b3e` |
| `experiments/code_intelligence/lsp_backend.py` | `8babe6082f32d8708d53770787f86dea264d2c9a` |
| `experiments/code_intelligence/semantic_contract.py` | `f9cd10fbb787e20476ac9be087faf41fdeaed02f` |
| `experiments/code_intelligence/semantic_facade.py` | `4b50d1440f5bf0371fe76252c534d1dd01cabdf0` |
| `experiments/code_intelligence/serena_backend.py` | `d10994dda0c5db349732980e11a1954bd4d0cc01` |
| `experiments/code_intelligence/workspace_seal.py` | `5b826a70a84378c633455eac4c2ca18c224d9df6` |
| `research/code_intelligence_fabric/c0-result.schema.json` | `5c398e639a855a8e747803145089296e9b30197e` |
| `tests/code_intelligence/servers/fake_jsonrpc_server.py` | `f4af2f9a6f911951e7127b22fa069199135e9511` |
| `tests/code_intelligence/servers/fake_lsp_server.py` | `4e4bc1694a06d477f928cafd16d349ee96371cae` |
| `tests/code_intelligence/servers/fake_serena_server.py` | `bdea797768cb4d97aec2be66ace5fc0f8dca83ae` |
| `tests/code_intelligence/test_backend_contract.py` | `bc7b7219438ad3e5f4a7a3dd99b7f8313af5dbf6` |
| `tests/code_intelligence/test_c0_runner.py` | `4c622624702d91ca246eadd702a0e5be4f3ccbf9` |
| `tests/code_intelligence/test_ground_truth.py` | `5587d1b78b52655a06ccb8909b4beb199b285358` |
| `tests/code_intelligence/test_jsonrpc_stdio.py` | `fb0bc3e938abf530462e2e6ae41f8bf8537ba5af` |
| `tests/code_intelligence/test_lsp_backend.py` | `6f62d5dda3689b3cd64dabd4228be3b73d8d409f` |
| `tests/code_intelligence/test_semantic_contract.py` | `174b8606dc64269c11f6c8adf94e5d73d87ff14b` |
| `tests/code_intelligence/test_semantic_facade.py` | `acea1d10f0de51dd1f6ee0bad268c1f1733d7f28` |
| `tests/code_intelligence/test_serena_backend.py` | `161a883d216d92b3be61e5300ecc9ced578b0e20` |
| `tests/code_intelligence/test_workspace_seal.py` | `521086628455f3f9acc4bdf1c489bdfce13bf795` |
| `tests/fixtures/code_intelligence/conftest.py` | `b395e20ea3e62f5159dbd7a46e1c56e337275be8` |
| `tests/fixtures/code_intelligence/python_sample/answer_key.json` | `67b0d1689739bd4747068a9071330878a09606aa` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/__init__.py` | `01d94305f6d87d0d55ba594303f7c4d73a1d0e22` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/consumer.py` | `028558dc5f6959c5df6d07b4df209356190d1b4b` |
| `tests/fixtures/code_intelligence/python_sample/src/sample/producer.py` | `698bab9996ca4a02fe9a2ed70dce4420737f5f84` |
| `tests/fixtures/code_intelligence/python_sample/tests/test_consumer.py` | `22772e58c9667c6598efb9f496bd098fa95b4aef` |

Every path is inside the declared ceiling; nothing outside it was touched. No
`control_plane/**`, `config/**`, capability registry, Operator Harness, MCP profile,
service, host, credential, Slack, Linear, Agent OS, deployment, market, ranking,
sizing or trading path was read for write or modified. `integrations/code_intelligence/**`
remains absent.

---

## 3. What was built

A complete, backend-neutral falsifier harness, RED→GREEN task by task:

| Task | Module | What it establishes |
|---|---|---|
| 1 | `semantic_contract.py` | The six-tool census, frozen and closed. No schema field may contain `root`, `path`, `project`, `attempt`, `worker`, `session`, `endpoint`, `command`, `executable`, `cwd`, `env`, `memory`, `edit` or `shell`. Bounded arguments (4 KiB) and limits (100). |
| 2 | `workspace_seal.py` | Exact worktree identity: resolved root, device, inode, uid, gid, git common dir, git dir, HEAD, porcelain-v2 digest, candidate-tree digest. Typed refusals for symlink root/ancestor, moved root, replaced inode, changed HEAD, tree writes and index drift. |
| 3 | `backend.py`, `ground_truth.py`, corpus | The backend protocol, a response guard that refuses (never trims) host leaks, and an **LSP-independent** `ast` ground truth so no candidate is graded against itself. |
| 4 | `jsonrpc_stdio.py`, `lsp_backend.py` | Bounded stdio JSON-RPC (4 MiB frames, 32 KiB stderr, closed env, digest checked before *and* after launch) and the direct-LSP adapter with a closed admitted-method set. |
| 5 | `serena_backend.py` | The pinned-Serena adapter, which refuses rather than patches on tool-surface widening, repository-config influence or candidate-tree writes. |
| 6 | `semantic_facade.py` | The sealed dispatcher: verify seal → one backend call → bound the response → **verify the seal again before publishing**. |
| 7 | `c0_runner.py`, `c0-result.schema.json` | The runner, the immutable result and the guard that makes a fabricated decision structurally impossible. |

**158 tests pass.** Each module's tests were observed RED before its implementation existed.

---

## 4. What was proven

### Hostile checks — 13/13 refused as required

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
| `seal_detects_candidate_tree_write` | REFUSED_AS_REQUIRED | `CANDIDATE_TREE_WRITE_DETECTED` |
| `seal_refuses_symlink_root` | REFUSED_AS_REQUIRED | `SYMLINK_ROOT_REFUSED` |
| `two_worktrees_carry_distinct_seals` | REFUSED_AS_REQUIRED | `—` |
| `scratch_refuses_candidate_tree` | REFUSED_AS_REQUIRED | `SCRATCH_INSIDE_CANDIDATE_TREE` |

### Mutation kills — each applied to real source, observed RED, reverted

| Mutation | Killed by |
|---|---|
| add a root-selecting field (project_path) to the find_symbol schema | `test_no_schema_field_exposes_a_steering_token[find_symbol]` |
| disable candidate-tree write detection in verify_workspace_seal | `test_backend_writing_the_worktree_is_refused` |
| make the facade binding accept a foreign worktree seal | `test_receipt_validation_against_a_foreign_seal_is_refused` |
| bypass the executable SHA-256 check before launch | `test_wrong_digest_refuses_to_launch` |

### Two-worktree isolation

Two simultaneous linked worktrees with identical package and symbol names but distinct
sentinels (`WORKTREE_ALPHA_ONLY` / `WORKTREE_BETA_ONLY`) never cross-read, at seal level
and through the facade. They share a `git_common_dir` and differ in `git_dir` and inode —
which is exactly why both fields are in the seal.

### Zero candidate-tree writes

Proven by before/after tree fingerprints around every facade call, and by a deliberately
misbehaving backend writing `.semantic-cache` into the worktree being caught as
`CANDIDATE_TREE_WRITE_DETECTED`. The same backend writing into external scratch passes.

---

## 5. What was NOT proven — stated plainly

- **No real backend semantics were measured.** Adapter proofs used stand-in servers
  written for this experiment. They demonstrate what Mastermind's wrapper does; they
  say nothing about what Serena or any real language server does.
- **No TypeScript/TSX evidence exists.** The required TS/TSX corpus and the protected
  Terminal `migrateLegacy` case were not exercised — there is no TS language server
  bundle on this host. This is a declared gap in the required language matrix, not an
  omission.
- **No latency, resource or cold/warm comparison between candidates exists**, because
  there is nothing to compare.
- **No independent review has been obtained** — see §8.

---

## 6. The anti-fabrication guard

`c0-result.schema.json` makes the honest outcome the only expressible one:

- every trial carries a `synthetic` flag;
- `decision_state: DECIDED` **requires** `decision`, and requires every candidate's
  `trials` to `contain` at least one entry with `synthetic: false`;
- `decision_state: BLOCKED_MISSING_PINNED_DEPENDENCY` **forbids** `decision` and
  requires `blocking_reason`.

A stand-in server therefore cannot produce a backend selection, no matter what a
future runner or author claims. This is covered by
`test_synthetic_trials_can_never_produce_a_decision`, and the complementary test
`test_a_decided_result_with_real_trials_is_accepted` proves the guard blocks
fabrication rather than decisions as such.

---

## 7. Supply chain, network and tool surface

| Item | Disposition |
|---|---|
| Third-party runtime dependencies added | **none** — standard library only (`jsonschema`, already present, is used for validation in tests/runner) |
| Network use by the experiment | none; `network_policy: disabled` is asserted in the artifact and the JSON-RPC child gets a closed environment |
| New executables, services, installs | none |
| Licences | no vendored third-party code |
| Exposed model-facing tools | exactly `workspace_status, symbol_overview, find_symbol, find_references, find_implementations, diagnostics` |
| Semantic schema digest | `ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce` |
| Facade source digest | `b00d4b2b776199fdc89ba468181f257f658fdf1f87e98e6bdfa255c7531446a6` |

The child environment is closed to `PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_ALL`,
`PYTHONHASHSEED` and `PYTHONDONTWRITEBYTECODE`, with `HOME`/`TMPDIR` pointed at external
scratch so a server that writes "next to the project" writes into the sandbox.

---

## 8. Effect state and the review gap

| Effect | State |
|---|---|
| Local | one isolated worktree, one branch, commits only |
| Remote | one Draft PR, held |
| Production | **none** — nothing installed, armed, deployed or registered |
| Ready / merge | not requested; gated on Macro #6756 |

**Independent review is an open gap, disclosed rather than papered over.** The only
GitHub identity available to this surface is `chriswong6031-creator`, which is also the
author identity of this branch. An "independent exact-head non-author review" cannot be
satisfied from here without it being a self-review, so I have not claimed one. Sol should
place this review with a distinct reviewer.

---

## 9. Residual risks

- Adapter proofs used stand-in servers; real backend semantics remain unmeasured.
- The TypeScript/TSX corpus and the protected Terminal migrateLegacy case were not exercised: no TypeScript language server bundle exists on this host.
- macOS injects __CF_USER_TEXT_ENCODING (uid-bearing) into child processes.
- Ground truth is a conservative AST census, not a full type-checker.

---

## 10. Smallest next action

Provision — or explicitly authorise acquisition of — three immutable, digest-pinned
host-side bundles:

1. Serena `949a27ef1e5fda1a6e7b561e777bcece345c6ffd` / v1.7.0
2. one pinned Python language server
3. one pinned TypeScript/TSX language server

The harness then runs unchanged:

```
python3 -m experiments.code_intelligence.c0_runner \
  --workspace <disposable-worktree> --scratch-parent <external-scratch> \
  --lsp-binary <pinned> --lsp-sha256 <digest> \
  --serena-bundle <pinned-bundle> --serena-sha256 <digest>
```

No code change is required to reach a decision — only the bundles.

---

## 11. Immutable artifact

`sha256(canonical) = 22d118f08a9bde51a1815b5a579f625f66fc1a6fae8b5cf317597c3b6c444131`

```json
{
  "artifact_version": "mastermind.codeintel_c0_result.v1",
  "binding_receipt": {
    "facade_source_digest": "b00d4b2b776199fdc89ba468181f257f658fdf1f87e98e6bdfa255c7531446a6",
    "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
    "workspace_binding_digest": "49ba3adbf8f2ca0a2cdcf4bb1a84b636ea58f916ecc0520efb92fd37ef4b6a6e"
  },
  "blocking_reason": "No decision may be published: candidate(s) ['direct_lsp', 'serena'] have no non-synthetic trial. The protected plan sets network_policy=disabled and requires host-supplied immutable bundles, and no such bundle exists on this host. Emitting NO_SAFE_BACKEND here would assert an empirical result that was never obtained.",
  "candidates": [
    {
      "hard_failures": [
        "LSP_BINARY_UNAVAILABLE"
      ],
      "identity": null,
      "kind": "direct_lsp",
      "notes": "No host-supplied pinned Python language server was provided. The protected plan forbids downloading one and requires an immutable installed bundle.",
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
  "corpora": [
    {
      "answer_key_digest": "fe78e8edc536d3d9bf960afae8f44f18a3c4212eb1f4f2735b782e950f5c644d",
      "corpus_id": "python_sample",
      "language": "python",
      "manifest_digest": "16b9f8f83347335c6c8b0e2f447e5593db8a2b8b67587295aeeb064d3d7e1d0c"
    }
  ],
  "decision_state": "BLOCKED_MISSING_PINNED_DEPENDENCY",
  "environment": {
    "network_policy": "disabled",
    "observations": [
      "macOS injects __CF_USER_TEXT_ENCODING into every spawned child; it carries the invoking uid and cannot be suppressed by this experiment."
    ],
    "platform": "Darwin arm64",
    "python_version": "3.14.7"
  },
  "exposed_tool_census": [
    "workspace_status",
    "symbol_overview",
    "find_symbol",
    "find_references",
    "find_implementations",
    "diagnostics"
  ],
  "generated_unix_ms": 1788338668440,
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
      "detail": "alpha and beta seals are distinct, so a cross-read cannot be mistaken for a hit",
      "outcome": "REFUSED_AS_REQUIRED"
    },
    {
      "check": "scratch_refuses_candidate_tree",
      "code": "SCRATCH_INSIDE_CANDIDATE_TREE",
      "detail": "<path>",
      "outcome": "REFUSED_AS_REQUIRED"
    }
  ],
  "mutation_kills": [
    {
      "killed_by": "tests/code_intelligence/test_semantic_contract.py::TestClosedSchemas::test_no_schema_field_exposes_a_steering_token[find_symbol]",
      "mutation": "add a root-selecting field (project_path) to the find_symbol schema"
    },
    {
      "killed_by": "tests/code_intelligence/test_workspace_seal.py::TestZeroWriteProof::test_backend_writing_the_worktree_is_refused",
      "mutation": "disable candidate-tree write detection in verify_workspace_seal"
    },
    {
      "killed_by": "tests/code_intelligence/test_semantic_facade.py::TestBindingReceipt::test_receipt_validation_against_a_foreign_seal_is_refused",
      "mutation": "make the facade binding accept a foreign worktree seal"
    },
    {
      "killed_by": "tests/code_intelligence/test_jsonrpc_stdio.py::TestDigestPinning::test_wrong_digest_refuses_to_launch",
      "mutation": "bypass the executable SHA-256 check before launch"
    }
  ],
  "next_action": "Sol to provision, or authorise acquisition of, the pinned Serena bundle (949a27ef1e5fda1a6e7b561e777bcece345c6ffd / v1.7.0) and pinned Python and TypeScript language-server bundles as immutable host-side inputs; the harness then runs unchanged via c0_runner.",
  "operation_key": "mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001",
  "residual_risks": [
    "Adapter proofs used stand-in servers; real backend semantics remain unmeasured.",
    "The TypeScript/TSX corpus and the protected Terminal migrateLegacy case were not exercised: no TypeScript language server bundle exists on this host.",
    "macOS injects __CF_USER_TEXT_ENCODING (uid-bearing) into child processes.",
    "Ground truth is a conservative AST census, not a full type-checker."
  ],
  "source": {
    "base_sha": "162af533a4bcf380125895d225b6962987c3c582",
    "branch": "sol/codeintel-c0-semantic-falsifier-20260830",
    "changed_paths": [
      "experiments/code_intelligence/__init__.py",
      "experiments/code_intelligence/backend.py",
      "experiments/code_intelligence/c0_runner.py",
      "experiments/code_intelligence/ground_truth.py",
      "experiments/code_intelligence/jsonrpc_stdio.py",
      "experiments/code_intelligence/lsp_backend.py",
      "experiments/code_intelligence/semantic_contract.py",
      "experiments/code_intelligence/semantic_facade.py",
      "experiments/code_intelligence/serena_backend.py",
      "experiments/code_intelligence/workspace_seal.py",
      "research/code_intelligence_fabric/c0-result.schema.json",
      "tests/code_intelligence/servers/fake_jsonrpc_server.py",
      "tests/code_intelligence/servers/fake_lsp_server.py",
      "tests/code_intelligence/servers/fake_serena_server.py",
      "tests/code_intelligence/test_backend_contract.py",
      "tests/code_intelligence/test_c0_runner.py",
      "tests/code_intelligence/test_ground_truth.py",
      "tests/code_intelligence/test_jsonrpc_stdio.py",
      "tests/code_intelligence/test_lsp_backend.py",
      "tests/code_intelligence/test_semantic_contract.py",
      "tests/code_intelligence/test_semantic_facade.py",
      "tests/code_intelligence/test_serena_backend.py",
      "tests/code_intelligence/test_workspace_seal.py",
      "tests/fixtures/code_intelligence/conftest.py",
      "tests/fixtures/code_intelligence/python_sample/answer_key.json",
      "tests/fixtures/code_intelligence/python_sample/src/sample/__init__.py",
      "tests/fixtures/code_intelligence/python_sample/src/sample/consumer.py",
      "tests/fixtures/code_intelligence/python_sample/src/sample/producer.py",
      "tests/fixtures/code_intelligence/python_sample/tests/test_consumer.py"
    ],
    "head_sha": "9af49061b8558af4cb60672c6690b5eb0ab606ef",
    "protected_pickup_sha": "ae483cc5f101d369f368f217bb767c91fc9e0150",
    "repository": "mastermindx-market-intelligence/Mastermind"
  },
  "wave_status": "DISPOSABLE FALSIFIER / PRODUCTION_INERT"
}
```
