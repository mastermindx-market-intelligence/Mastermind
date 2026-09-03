# C0 Semantic Falsifier — Real Paired Result

`publication_operation: mastermind-codeintel-c0-real-result-publication-20260903-sol-001`
`experiment_operation: mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001`
`canonical_carrier: C0BSBM78V1N/1788475769.871519`
`PR: #375 (DRAFT / HOLD-FOR-SOL)`
`artifact_version: mastermind.codeintel_c0_result.v1`
`wave_status: DISPOSABLE FALSIFIER / PRODUCTION_INERT`
`return: RESULT / HOLD-FOR-SOL`

> **This experiment grants nothing.** No capability, backend acceptance, MCP
> server, registry entry, profile, service, credential, deployment, market or
> trading authority is created. The result is source evidence on a Draft PR.

---

## 1. Decision

**`decision_state: DECIDED` — `decision: NO_SAFE_BACKEND`.**

The exact frozen ruler reached a real decision because both candidates completed
the full non-synthetic Python + TypeScript/TSX, five-case, cold/warm matrix with
no candidate-level hard failure. Neither candidate cleared the protected
primary-case usefulness floor:

| Candidate | Correct | Primary | Complete | Useful |
|---|---:|---:|---|---|
| `direct_lsp` | 16/20 | 10/12 | yes | **no** |
| `serena` | 8/20 | 4/12 | yes | **no** |

The decisive direct-LSP failure is Python
`A3_implementations_of_protocol` in both phases. Pyright 1.1.403 does not
serve `textDocument/implementation` for the fixture's structural
`typing.Protocol`, and `LiveProducer` / `DeadProducer` intentionally do
not inherit from `Producer`. A launcher-side structural-typing algorithm would
change candidate behavior to force the expected answer, so none was added.
TypeScript pull diagnostics were also empty in both phases, but diagnostics are
secondary and did not cause the usefulness failure.

Serena's four admitted retrieval tools correctly served definition and overview.
It missed the declaration row in Python references, returned no TypeScript
references, and its frozen adapter explicitly records implementations and
diagnostics as unavailable. Those preserved failures are evidence, not omitted
trials.

This result **does not reproduce** the earlier pre-canonical `DIRECT_LSP`
claim. It falsifies that claim on the exact published harness/tool versions.
That disagreement is the central result, not a reason to rewrite the harness.

---

## 2. Replay proof

Both accepted publication trials used the same finalized host launcher bytes,
fresh absent output/scratch paths, and the unchanged exact PR head.

| Run | Canonical result digest | Artifact-file SHA-256 | Semantic evidence digest | Decision |
|---|---|---|---|---|
| 1 | `e828f6c88a68fc04d957f1c2d772d59ee90114bf5333c1f9392fb983aed7f27f` | `cc4521b9c110256164969df0479b26d86d8af12d61185e4807a5947b045ebaad` | `fd84936688c1318d7832be281549a128b9e0a9cc04be8fdfb9a823bf18005330` | `NO_SAFE_BACKEND` |
| 2 | `ed458c3d760ceaf09e556b4ffb9457ef1605a041bd35ea9df54d699ba145d896` | `bae5775b7e5b15f73f2efb8d8131f12fdc21c08018ed99a4d68443f5e1c0607e` | `fd84936688c1318d7832be281549a128b9e0a9cc04be8fdfb9a823bf18005330` | `NO_SAFE_BACKEND` |

The canonical result digest and file digest differ across runs only because the
artifact retains wall-clock, latency, workspace-binding and scratch census
observations. The semantic evidence digest strips exactly those declared
volatile fields and is byte-identical across replay.

The earlier exploratory runs are not publication evidence: they established the
minimum launcher compatibility required by the frozen harness, then were
discarded from the accepted pair before the final launcher bytes were frozen.

---

## 3. Source binding

| Field | Value |
|---|---|
| Repository | `mastermindx-market-intelligence/Mastermind` |
| Existing remote branch | `sol/codeintel-c0-semantic-falsifier-20260830` |
| Harness head exercised | `ea9e591d9dfb2cdad384e6614644e6eb5bf8df65` |
| Harness tree | `741baf8fadd3aceb77706da1ffe0e3e97ff812d0` |
| Merge base recorded by the frozen artifact | `0d5c80bba8c69b5d1ed86aa3d32c9003a4252c73` |
| Protected ruling pin checked before START | `6aa94e3377086d8f862c4811a2ae87b94d4bd5a1` |
| PR paths at exercised head | 38, all frozen C0 paths |
| Publication edit | this result document only |

The quarantined predecessor worktree was not opened, read, cleaned, reset,
reused, cherry-picked, salvaged or used to infer any commit content.

---

## 4. Exact toolchain and launch identity

Acquisition occurred in a unique external temporary staging root before the
semantic calls. The semantic calls themselves ran with network denial enforced
and attested.

### Serena

| Item | Identity |
|---|---|
| Source | `oraios/serena@949a27ef1e5fda1a6e7b561e777bcece345c6ffd` / tag `v1.7.0` |
| Source tree | `6daa0fe28c2be66ed2462e02871426098ddecb69` |
| Frozen `uv.lock` SHA-256 | `48f88af6b9a7c942820b65d0321176b33b49f0012a8a0cd036ee1f5140cfe167` |
| Installed environment | Python 3.12.13; 77 locked packages; no dev/agno/google extras |
| Bundle digest | `397add65e1263194505ebb90cc6108ceea4d37d32ce9176b74cc7680f3dd9cd9` |
| Python executable SHA-256 | `94be2db6796807c796419e7adbc45cbff3e71966c107c2adcbf931cf70393941` |
| Serena launcher SHA-256 | `2743ccc40025ae84b3d4c36036da7415a5b67c039d34f0305194253e898ea525` |
| Fixed context SHA-256 | `c6ab04add6fddf1ac814b5d7eb358bc2f98c829493d08a4e945e0fe8f33bde35` |

The temporary Serena launcher translates the frozen harness's Content-Length
framing to upstream newline-framed MCP, supplies the initialize-bound disposable
root to Serena at process start, keeps project configuration in memory, moves
Serena data/cache/logs under external scratch, fixes `tools/list` to
`get_symbols_overview`, `find_symbol`,
`find_referencing_symbols`, and `list_dir`, and normalizes Serena's own JSON
string records into the adapter's frozen `symbols` envelope. It does not add an
implementation or diagnostics capability.

### Shared direct language engines

| Item | Version / identity |
|---|---|
| Pyright | `1.1.403`; registry SRI `sha512-OyslngwxftKgNfbiyR8WDadUoLHDoinwUfbd50P1VBfLWkR5cro9R52qMQMpVI/LiSVpWbzunToR2NX7SanwmA==` |
| `pyright/langserver.index.js` SHA-256 | `f200762078eb9880faf421a5b30f9ef3055b1d85c6f10780d75db4da8d8499f1` |
| TypeScript Language Server | `5.1.3`; registry SRI `sha512-r+pAcYtWdN8tKlYZPwiiHNA2QPjXnI02NrW5Sf2cVM3TRtuQ3V9EKKwOxqwaQ0krsaEXk/CbN90I5erBuf84Vg==` |
| `typescript-language-server/lib/cli.mjs` SHA-256 | `3c2a7818315bd8399e56f461fe7da01c0f8f67a9c66108af0b655605b088dd77` |
| TypeScript | `5.9.3`; registry SRI `sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==` |
| `typescript/lib/typescript.js` SHA-256 | `3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675` |
| npm `package-lock.json` SHA-256 | `38c445783e722200e93cf16aeff32604caf0a9d4d47a7e903a04dca0ab55ec39` |
| Complete installed npm tree digest | `1cd549b4f1763c7fe150d2540831986fd25c41bb218e2e7bdf64f472b1149e4a` |
| Node | `v26.5.0`; executable SHA-256 `70851490e028b3d699a8d6d4e1de909af2a989359ae807974c92af9c6580a8e8` |
| Direct-LSP launcher SHA-256 | `fb13c040a2cfded60f1e477659827ef1d80e8fd3a6ae687ad57eaf6c833a85c2` |
| Exact run driver SHA-256 | `5b5840a64585055d4bd9e6b00f6fd6bdc34596a34535ddb88005ccbd4b30efab` |

The temporary direct launcher performs only the compatibility that the frozen
adapter requires to exercise these real server bytes: it binds `rootUri` as a
workspace folder, opens the sealed corpus documents to create inferred projects,
bridges published diagnostics to the facade's pull request, removes nested
members from a top-level overview, and maps an unavailable implementation
request to the server's real references restricted to class-declaration
locations. That conservative mapping succeeds for explicit TypeScript
`implements` declarations but correctly produces no Python structural
implementations. This host launcher is a remaining local-bundle confound and is
not installed or published as a product capability.

---

## 5. Isolation, integrity, and cleanup

| Proof | Result |
|---|---|
| Semantic-call network boundary | `sandbox-exec` profile `5c358b8d84721133e7ba22df82d84f796b5f30a41a2682209a949d783adbd08`; DNS failed and TCP returned `PermissionError: Operation not permitted` in both accepted runs |
| Resource boundary | `RLIMIT_CPU`, `RLIMIT_NOFILE`, `RLIMIT_NPROC` enforced; Darwin `RLIMIT_AS` explicitly reported unenforceable |
| Credential environment | frozen transport child allowlist only: `HOME`, `LANG`, `LC_ALL`, `PATH`, `PYTHONDONTWRITEBYTECODE`, `PYTHONHASHSEED`, `TMPDIR`; no host credential variable or credential path supplied |
| Candidate source writes | 4/4 execution receipts per run have identical candidate-tree before/after fingerprints |
| Mastermind source during experiment | exact `ea9e591d…` / tree `741baf8…`, clean before and after accepted pair |
| Serena source during experiment | exact `949a27ef…` / tree `6daa0fe…`, clean before and after accepted pair |
| Toolchain drift | npm lock, Serena `uv.lock`, launchers and context retained identical SHA-256 before/after replay |
| Hostile boundary probes | 15/15 `REFUSED_AS_REQUIRED`, including root selection, absolute/traversal paths, secret/host-key payloads, candidate writes, symlink root, cross-worktree seal, internal scratch, and repository-config influence |
| Run 1 scratch | removed; zero retained paths; 305 files / 2,825,344 bytes censused before removal |
| Run 2 scratch | removed; zero retained paths; 305 files / 2,825,353 bytes censused before removal |
| Descendants | post-run process census empty for both launchers, Serena, Pyright and TypeScript Language Server |

The acquisition/staging root is not a production installation. It is retained
only through source publication verification so the reported digests can be
rechecked, then removed as the final local cleanup action.

---

## 6. Effect and hold state

| Plane | State |
|---|---|
| Source | one bounded evidence-only update on existing PR #375 |
| Review | no current independent exact-head approval |
| Remote | Draft / HOLD-FOR-SOL; no Ready; auto-merge remains absent |
| Merge/deploy | none |
| Installation/profile/service | none |
| Market/trading/production | none |

The earlier `DIRECT_LSP` observation must not be treated as accepted or
replay-stable evidence for this exact frozen matrix. Sol should review this
contradiction and either accept `NO_SAFE_BACKEND` or identify the exact
previous launcher/result artifact that produced Python structural
implementations without changing candidate behavior.

---

## 7. Complete machine artifact (accepted replay run 2)

`sha256(file) = bae5775b7e5b15f73f2efb8d8131f12fdc21c08018ed99a4d68443f5e1c0607e`
`sha256(canonical result) = ed458c3d760ceaf09e556b4ffb9457ef1605a041bd35ea9df54d699ba145d896`
`semantic_evidence_digest = fd84936688c1318d7832be281549a128b9e0a9cc04be8fdfb9a823bf18005330`

```json
{
  "artifact_version": "mastermind.codeintel_c0_result.v1",
  "binding_receipt": {
    "facade_source_digest": "495030c00167248fada016024f7275edf48a2a8ef64e2131db30b98ffd689afe",
    "per_execution": [
      {
        "backend_identity_digest": "22b60a12069bc9192ab4c2abea749a325bfa8a18bb4c6eb262c637490e9c211b",
        "backend_kind": "direct_lsp",
        "candidate": "direct_lsp",
        "candidate_tree_after": "f0fd9b3929e6d66d093e3c07709a5467ada09cef77c7258c5c926dc74da66598",
        "candidate_tree_before": "f0fd9b3929e6d66d093e3c07709a5467ada09cef77c7258c5c926dc74da66598",
        "facade_source_digest": "495030c00167248fada016024f7275edf48a2a8ef64e2131db30b98ffd689afe",
        "language": "python",
        "language_server_digests": [
          [
            "python:pyright",
            "94be2db6796807c796419e7adbc45cbff3e71966c107c2adcbf931cf70393941"
          ]
        ],
        "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
        "startup_unix_ms": 1788478866215,
        "workspace_binding_digest": "7a262ba6cd22a8f18fe7dd571aeaf66c5177dc1273cbf53cdd93121df6bd0843"
      },
      {
        "backend_identity_digest": "998501d8f3d7b8f09b3703dc4373bd6610ec34d236778805294ffb5e9ab7ac69",
        "backend_kind": "direct_lsp",
        "candidate": "direct_lsp",
        "candidate_tree_after": "57214efe14c7586e0542a07f493bd2af7e43af1a7434ea57209cbe56aaa53049",
        "candidate_tree_before": "57214efe14c7586e0542a07f493bd2af7e43af1a7434ea57209cbe56aaa53049",
        "facade_source_digest": "495030c00167248fada016024f7275edf48a2a8ef64e2131db30b98ffd689afe",
        "language": "typescript",
        "language_server_digests": [
          [
            "typescript:typescript-language-server",
            "94be2db6796807c796419e7adbc45cbff3e71966c107c2adcbf931cf70393941"
          ]
        ],
        "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
        "startup_unix_ms": 1788478868573,
        "workspace_binding_digest": "73be960b47775aa7b849154fd51d24da2378f2d5011756eeab1c5285602d8f90"
      },
      {
        "backend_identity_digest": "190817e3553be7879c5fc562b925d0702ca7eb7065c50e3c803d6c7d374004de",
        "backend_kind": "serena",
        "candidate": "serena",
        "candidate_tree_after": "f0fd9b3929e6d66d093e3c07709a5467ada09cef77c7258c5c926dc74da66598",
        "candidate_tree_before": "f0fd9b3929e6d66d093e3c07709a5467ada09cef77c7258c5c926dc74da66598",
        "facade_source_digest": "495030c00167248fada016024f7275edf48a2a8ef64e2131db30b98ffd689afe",
        "language": "python",
        "language_server_digests": [
          [
            "serena:bundle",
            "397add65e1263194505ebb90cc6108ceea4d37d32ce9176b74cc7680f3dd9cd9"
          ]
        ],
        "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
        "startup_unix_ms": 1788478883215,
        "workspace_binding_digest": "f7098139e27e84c810860b5328fade2bac397cc085e1f98e1f64861a2d26e982"
      },
      {
        "backend_identity_digest": "190817e3553be7879c5fc562b925d0702ca7eb7065c50e3c803d6c7d374004de",
        "backend_kind": "serena",
        "candidate": "serena",
        "candidate_tree_after": "57214efe14c7586e0542a07f493bd2af7e43af1a7434ea57209cbe56aaa53049",
        "candidate_tree_before": "57214efe14c7586e0542a07f493bd2af7e43af1a7434ea57209cbe56aaa53049",
        "facade_source_digest": "495030c00167248fada016024f7275edf48a2a8ef64e2131db30b98ffd689afe",
        "language": "typescript",
        "language_server_digests": [
          [
            "serena:bundle",
            "397add65e1263194505ebb90cc6108ceea4d37d32ce9176b74cc7680f3dd9cd9"
          ]
        ],
        "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
        "startup_unix_ms": 1788478888298,
        "workspace_binding_digest": "dadb4b5a81af89d127e4be1088e10e07fa5eab4e930fa56af5129401825b8428"
      }
    ],
    "semantic_schema_digest": "ee253db52b52d2cfc551c3c2091789251000ca3009c2afbe5df44937232dd8ce",
    "workspace_binding_digest": "7a262ba6cd22a8f18fe7dd571aeaf66c5177dc1273cbf53cdd93121df6bd0843"
  },
  "candidate_summaries": [
    {
      "complete": true,
      "correct": 16,
      "correctness": 0.8,
      "hard_failures": [],
      "kind": "direct_lsp",
      "median_latency_ms": 76,
      "missing": [],
      "non_synthetic_trials": 20,
      "primary_correct": 10,
      "primary_trials": 12,
      "status": "EXERCISED",
      "useful": false
    },
    {
      "complete": true,
      "correct": 8,
      "correctness": 0.4,
      "hard_failures": [],
      "kind": "serena",
      "median_latency_ms": 110,
      "missing": [],
      "non_synthetic_trials": 20,
      "primary_correct": 4,
      "primary_trials": 12,
      "status": "EXERCISED",
      "useful": false
    }
  ],
  "candidates": [
    {
      "hard_failures": [],
      "identity": {
        "configuration_digest": "7b9ae12872bba1e6864f94d93b41e5fc103554199eadac2bca0347e48ee64a01",
        "executable_sha256": "94be2db6796807c796419e7adbc45cbff3e71966c107c2adcbf931cf70393941",
        "kind": "direct_lsp",
        "source_commit": "unpinned",
        "source_version": "1.1.403"
      },
      "kind": "direct_lsp",
      "notes": "",
      "status": "EXERCISED",
      "trials": [
        {
          "actual": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "language": "python",
          "latency_ms": 1251,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "case": "W1_references_across_files",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 72,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "python",
          "latency_ms": 68,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "language": "python",
          "latency_ms": 67,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "case": "diagnostics_planted_undefined_name",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 72,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "language": "python",
          "latency_ms": 75,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "case": "W1_references_across_files",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 78,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "python",
          "latency_ms": 72,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "language": "python",
          "latency_ms": 70,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "case": "diagnostics_planted_undefined_name",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 70,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "language": "typescript",
          "latency_ms": 3300,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "case": "W1_references_across_files",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 86,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer"
          ],
          "case": "A3_implementations_of_protocol",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "typescript",
          "latency_ms": 103,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "language": "typescript",
          "latency_ms": 81,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 3074,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "language": "typescript",
          "latency_ms": 73,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "case": "W1_references_across_files",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 86,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer"
          ],
          "case": "A3_implementations_of_protocol",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "typescript",
          "latency_ms": 76,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "language": "typescript",
          "latency_ms": 71,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 3074,
          "phase": "warm",
          "synthetic": false
        }
      ]
    },
    {
      "advertised_tool_census": [],
      "hard_failures": [],
      "identity": {
        "configuration_digest": "66af61310ed0aafb66f8ed4128994bcbee6addaeb130e8adc34f78754669da82",
        "executable_sha256": "94be2db6796807c796419e7adbc45cbff3e71966c107c2adcbf931cf70393941",
        "kind": "serena",
        "source_commit": "949a27ef1e5fda1a6e7b561e777bcece345c6ffd",
        "source_version": "1.7.0"
      },
      "kind": "serena",
      "notes": "",
      "status": "EXERCISED",
      "trials": [
        {
          "actual": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "language": "python",
          "latency_ms": 730,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "case": "W1_references_across_files",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 2119,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream implementations tool",
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "python",
          "latency_ms": 35,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "language": "python",
          "latency_ms": 167,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream diagnostics tool",
          "expected": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 32,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/sample/producer.py",
              20
            ]
          ],
          "language": "python",
          "latency_ms": 75,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "case": "W1_references_across_files",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/sample/consumer.py",
              8
            ],
            [
              "tests/consumer_case.py",
              11
            ],
            [
              "tests/consumer_case.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 110,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream implementations tool",
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "python",
          "latency_ms": 34,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "make_dead_producer",
            "make_producer"
          ],
          "language": "python",
          "latency_ms": 175,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream diagnostics tool",
          "expected": [
            [
              "src/sample/consumer.py",
              15
            ]
          ],
          "language": "python",
          "latency_ms": 37,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "language": "typescript",
          "latency_ms": 830,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "W1_references_across_files",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 5132,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream implementations tool",
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "typescript",
          "latency_ms": 36,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "language": "typescript",
          "latency_ms": 170,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream diagnostics tool",
          "expected": [
            [
              "src/consumer.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 37,
          "phase": "cold",
          "synthetic": false
        },
        {
          "actual": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "case": "O1_definition_live_implementation",
          "correct": true,
          "error": null,
          "expected": [
            [
              "src/producer.ts",
              13
            ]
          ],
          "language": "typescript",
          "latency_ms": 171,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [],
          "case": "W1_references_across_files",
          "correct": false,
          "error": null,
          "expected": [
            [
              "src/consumer.ts",
              5
            ],
            [
              "src/widget.tsx",
              3
            ],
            [
              "src/widget.tsx",
              6
            ],
            [
              "tests/consumer_case.ts",
              8
            ],
            [
              "tests/consumer_case.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 106,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "A3_implementations_of_protocol",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream implementations tool",
          "expected": [
            "DeadProducer",
            "LiveProducer"
          ],
          "language": "typescript",
          "latency_ms": 36,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "case": "overview_single_file",
          "correct": true,
          "error": null,
          "expected": [
            "DeadProducer",
            "LiveProducer",
            "Producer",
            "makeDeadProducer",
            "makeProducer"
          ],
          "language": "typescript",
          "latency_ms": 186,
          "phase": "warm",
          "synthetic": false
        },
        {
          "actual": null,
          "case": "diagnostics_planted_undefined_name",
          "correct": false,
          "error": "SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: SERENA_CAPABILITY_UNAVAILABLE: no admitted upstream diagnostics tool",
          "expected": [
            [
              "src/consumer.ts",
              11
            ]
          ],
          "language": "typescript",
          "latency_ms": 37,
          "phase": "warm",
          "synthetic": false
        }
      ]
    }
  ],
  "cleanup": {
    "failure": null,
    "removed": true,
    "retained_paths": 0,
    "scratch_bytes_before": 2825353,
    "scratch_files_before": 305
  },
  "corpora": [
    {
      "answer_key_digest": "a8fc681801339e5451b13cccc5716d423b4af02d32d792ef75bc23261755b6d5",
      "corpus_id": "python_sample",
      "language": "python",
      "manifest_digest": "cc095175552d8a2c0d9307da29ef2b1f0339041319ce966355a88cb7f75b51c4"
    },
    {
      "answer_key_digest": "7ae09d9b7ed75405adc0d1bcd5082f9ad9f64138a93cf1e23b1f77a89149c2bf",
      "corpus_id": "typescript_sample",
      "language": "typescript",
      "manifest_digest": "8ab20183b3a88aad31c1468112ce55a8819d717ead7f5b7d43aa2a40d2020037"
    }
  ],
  "decision": "NO_SAFE_BACKEND",
  "decision_gates": [
    "direct_lsp failed the usefulness floor on primary cases (10/12)",
    "serena failed the usefulness floor on primary cases (4/12)"
  ],
  "decision_state": "DECIDED",
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
  "generated_unix_ms": 1788478897864,
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
      "detail": "tool census unchanged under a hostile repository configuration",
      "outcome": "REFUSED_AS_REQUIRED"
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
  "next_action": "Return the decision to Sol for C0 release adjudication.",
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
  "semantic_evidence_digest": "fd84936688c1318d7832be281549a128b9e0a9cc04be8fdfb9a823bf18005330",
  "source": {
    "base_sha": "0d5c80bba8c69b5d1ed86aa3d32c9003a4252c73",
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
    "head_sha": "ea9e591d9dfb2cdad384e6614644e6eb5bf8df65",
    "protected_pickup_sha": "6aa94e3377086d8f862c4811a2ae87b94d4bd5a1",
    "repository": "mastermindx-market-intelligence/Mastermind"
  },
  "tie_break": "Both candidates were genuinely exercised and neither cleared the safety and correctness floor.",
  "wave_status": "DISPOSABLE FALSIFIER / PRODUCTION_INERT"
}
```
