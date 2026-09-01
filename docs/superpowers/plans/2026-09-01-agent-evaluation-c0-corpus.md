# Agent Evaluation EVAL-C0 — Governed Corpus + Revision Governance

**Date:** 2026-09-01
**Parent operation:** `mastermind-agent-evaluation-organizational-learning-fabric-20260830-sol-pro-001`
**Child operation:** `mastermind-agent-evaluation-c0-corpus-20260901-fable-001`
**Base:** `mastermindx-market-intelligence/Mastermind@ba3a421918231bf9df451d80b6abafc5c90a00c9` (carries the four EVAL-F0 records and the merged EVAL-R0 core at `scripts/agent_eval/`)
**Authority (apply in order):** (1) `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`; (2) `docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md`; (3) `docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md`; (4) this record; (5) bounded implementation choices inside the frozen boundary.
**Capability:** `SPEC_AND_CORPUS / RECORDS_PLUS_ADDITIVE_CODE / PRODUCTION_INERT`

This record creates no evaluator implementation, model/provider call, process, network read, Executive/Agent OS effect, route, policy, deployment, or production action. It formalizes the governed corpus this PR ships, its revision/leakage/holdout law, and the additive `scripts/agent_eval/corpus.py` governance module + `corpus-verify` CLI subcommand that checks a committed corpus tree against that law.

---

## 1. What this wave is, and is not

EVAL-R0 (merged) proved the closed scenario/configuration/experiment/run/scorer/evidence-reference core and two verification scopes, `SHAPE_VALID` and `EVALUATION_GRAPH_VERIFIED`. It deliberately built **zero** real corpus content — every scenario in R0's own tests is synthetic, in-process, and anchored to a fabricated placeholder commit SHA (`"a" * 40`) that is never meant to resolve.

EVAL-C0 is the corpus wave the R0 plan's own continuation section names (§7: *"EVAL-C0: 15–30 governed cases, private holdouts, and owner-native evidence-content resolution"*). This record narrows that broad continuation note to the concrete, bounded slice this PR actually ships:

1. a governed, versioned corpus of real `mastermind.agent_evaluation_scenario.v1` documents, committed under a public-safe corpus home in this repository;
2. an explicit, single frozen `corpus_revision` anchor every case in this wave declares;
3. a holdout **sealing** mechanism — digest-only records that declare a held-out case exists without publishing its body;
4. leakage controls scoped to what a public, git-committed corpus can actually enforce (public-safe classification, no hidden-solution refs needed because these cases carry no separate "final answer" artifact distinct from `expected_contract`, and secret-shape rejection over every corpus byte);
5. additive governance code (`scripts/agent_eval/corpus.py`) that derives a tamper-detecting digest over the corpus tree and validates every case against it, plus everything R0 already proves (each case validates against the real, merged `contracts.validate_scenario_shape`);
6. a `corpus-verify` CLI subcommand wired onto the existing `scripts/agent_eval/cli.py` argparse surface.

It is explicitly **not**: a runner (OHF1/OHF2 remain the sole future runner work, on PR #162's own carrier); a scorer library beyond what R0 already ships (`mastermind.technical_integrity.v1`); an experiment executor (no `experiment.json`/`run.json`/`scorer-pass.json`/`evidence-ref.json` is created by this wave — the corpus is scenarios only); a widening of CXI, the registry, or any control-plane surface; a second search/corpus service; an E1 prereg; or an OHF wiring change. `EVIDENCE_CONTENT_VERIFIED` is still not claimed by any CLI output in this wave — `corpus-verify` prints a distinct `result` field (`CONSISTENT`/`INCONSISTENT`), never one of R0's three verification-scope strings, precisely so it is never confused with a fourth verification scope.

---

## 2. Corpus home and the safe-path law it reuses

The parent design does not pin a repository path for the corpus (design §7.1's contract only defines the scenario document's own fields, not a repo layout). This wave chooses the smallest faithful path and discloses it here:

```text
corpus/agent_eval/
  corpus_manifest.json                              <- single frozen tamper-detection manifest
  scenarios/<family>/<case>/v<version>/
    scenario.json                                    <- persisted mastermind.agent_evaluation_scenario.v1
    fixtures/
      input.json
      expected.json
  holdouts/<family>/<case>/
    holdout_seal.json                                 <- digest-only; NO scenario.json, NO fixtures/ here
```

`scenarios/<family>/<case>/v<version>/scenario.json` is **not** a new path law — it is the exact private-artifact-store safe path design §8.3 / plan §5.5 already defines (`scenario:<family>:<case> -> scenarios/<family>/<case>/v<version>/scenario.json`), reused verbatim by literally calling `scripts.agent_eval.store.scenario_path(scenario_id, scenario_version)` from the new governance module. This is deliberate: the corpus tree's own on-disk shape is checked against the SAME safe-path derivation the private `ArtifactStore` already proves is globally resolvable and unambiguous (no mutable index, no repository-wide search), rather than inventing a second, parallel path law for the public corpus. A scenario committed at the wrong directory relative to its own `scenario_id`/`scenario_version` is a `SCENARIO_MISLOCATED` defect, mirroring `ArtifactStore.verify_tree_graph`'s own `ARTIFACT_MISLOCATED` check.

`holdouts/<family>/<case>/holdout_seal.json` is a new, analogous path law (`corpus.holdout_seal_path`) for the one new schema this wave adds — a holdout seal has no `scenario_version` (a sealed case is never superseded/versioned the way a published one is), so it drops the version segment. A holdout directory whose case name diverges from what its own `scenario_id` derives is `HOLDOUT_SEAL_MISLOCATED`, by the same logic.

---

## 3. `corpus_revision`: the frozen anchor for this wave

Every scenario document's `corpus_revision` field (design §7.1: *"immutable and source-qualified"*) and every holdout seal's `corpus_revision` field are the identical, single value:

```text
git:mastermindx-market-intelligence/Mastermind@ba3a421918231bf9df451d80b6abafc5c90a00c9
```

This is the exact real, immutable, currently-resolvable base commit this whole child operation is anchored to (§ header above) — not a synthetic placeholder SHA. Using a real, already-existing commit (rather than the not-yet-known commit this PR itself will land at) sidesteps the chicken-and-egg problem of a scenario document needing to name the exact commit that publishes it before that commit exists, while still keeping the anchor genuinely dereferenceable by any reviewer (`git show ba3a421918231bf9df451d80b6abafc5c90a00c9`) rather than an inert `"a" * 40` sentinel. Every fixture `artifact_ref` in this corpus is exactly this anchor plus a `#`-qualified path into this same commit's own repository tree, e.g.:

```text
git:mastermindx-market-intelligence/Mastermind@ba3a421918231bf9df451d80b6abafc5c90a00c9#corpus/agent_eval/scenarios/current_source_comprehension/effect_unknown_precedence/v1/fixtures/input.json
```

**This is distinct from the corpus-TREE digest** (§4 below), which is a tamper-detection digest over the corpus's own byte contents, recomputed fresh on every `corpus-verify` run. `corpus_revision` answers "which repository state is this corpus a snapshot of" (a fixed git anchor, checked once at authoring time); `corpus_tree_digest` answers "have this wave's own committed files been silently altered since" (a live, recomputed digest, checked on every verification run). Conflating the two was an explicit design risk this record avoids by using two differently-named, differently-scoped fields.

---

## 4. Corpus-revision derivation (tamper detection)

`scripts/agent_eval/corpus.py::compute_corpus_tree_digest(corpus_root)` walks every regular, non-symlink file under `corpus_root` (excluding `corpus_manifest.json` itself — a manifest cannot describe its own bytes), computes a plain `sha256:<hex>` digest over each file's raw bytes (`corpus.file_digest`, distinct from `canonical.digest_value` because fixture files are not necessarily canonical JSON), and reduces the sorted `{relative_path, digest}` list to one `corpus_tree_digest` via the existing `canonical.digest_value`. `corpus_manifest.json` is the single persisted record of this: `{schema, corpus_revision, entries, corpus_tree_digest, generated_at, manifest_digest}` — a new closed schema (`mastermind.agent_evaluation_corpus_manifest.v1`), registered onto the existing generic dispatcher via `contracts.register_shape_validator` (the same additive-extension mechanism `verification.py`/`scoring.py` already use; `contracts.py` itself is unmodified).

`corpus-verify` always **recomputes** the tree digest fresh from disk and compares it against the manifest's frozen value — a single-byte change anywhere in the corpus (including a fixture file the manifest doesn't individually enumerate a scenario-level check for) changes `corpus_tree_digest` and is refused as `CORPUS_TREE_DIGEST_MISMATCH`. This is the "tampered case → revision mismatch" property.

---

## 5. Scenario-vs-corpus consistency validation

`corpus.verify_corpus_tree_consistency(corpus_root, repo_root)` performs, in order, over every `scenario.json` and `holdout_seal.json` under `corpus_root`:

1. **corpus-tree tamper check** (§4) — one `CORPUS_TREE_DIGEST_MISMATCH` check across the whole tree.
2. **shape** — `contracts.validate_scenario_shape` / `corpus.validate_holdout_seal_shape`, the real merged contract, unmodified. A missing/malformed `temporal.cutoff_at` fails here as an ordinary `FIELD_MISSING` shape defect — no separate corpus-level cutoff check is needed because the scenario contract already requires and grammar-checks it; `corpus-verify` never re-implements a check the contract already owns, it only ever asks the contract to run.
3. **secret-shape rejection** — `scripts.agent_eval.privacy.assert_public_safe_evidence` run over the **whole** parsed document (scenario or seal), the exact same reject-only, environment-free detector R0 already ships and already tests. `corpus.py` does not detect secrets itself; it calls the existing detector.
4. **corpus_revision anchoring** — every scenario/seal's own `corpus_revision` must equal the manifest's single frozen anchor (`CORPUS_REVISION_NOT_ANCHORED` otherwise).
5. **source-visibility declaration** — `privacy.classification` must be exactly `PUBLIC_SAFE` for every scenario committed to this public corpus (`NON_PUBLIC_SAFE_IN_PUBLIC_CORPUS` otherwise) — a `PRIVATE_RESTRICTED` scenario is a bug in a *public* git repository, not a valid corpus entry; `PRIVATE_RESTRICTED` content belongs behind the private-evidence-root delivery contract (§6), never in this repo.
6. **safe-path parity** — the file's actual on-disk location must equal the canonical path its own ID/version derives (§2's `SCENARIO_MISLOCATED` / `HOLDOUT_SEAL_MISLOCATED`).
7. **fixture-digest resolution** — for every `{artifact_ref, digest}` pair a scenario declares (`input_fixture`, `expected_contract`, `source_policy.allowlist_artifacts`) whose `artifact_ref` is anchored to this wave's own frozen `corpus_revision` (§3), `corpus-verify` strips the anchor prefix to recover the repository-relative path, reads that file under `repo_root`, and requires its raw bytes to hash to the declared digest (`FIXTURE_FILE_UNRESOLVED` if the file is missing, `FIXTURE_DIGEST_MISMATCH` if bytes differ). Any `artifact_ref` **not** anchored to this wave's `corpus_revision` is left externally sealed/unverified rather than guessed at — this bounded check never claims the formal `EVIDENCE_CONTENT_VERIFIED` scope (§1); it only proves that a corpus fixture's own declared bytes match what this repository actually commits, which is strictly narrower and does not resolve arbitrary external git history.
8. **holdout body isolation** — a holdout-seal directory must never also contain a `scenario.json` or a `fixtures/` subdirectory (`UNSEALED_HOLDOUT_BODY_IN_REPO`), and no case directory may mix a public scenario and a sealed holdout (`CASE_DIRECTORY_MIXES_PUBLIC_AND_HOLDOUT`).

Every check is **report-only** — like `ArtifactStore.verify_tree_graph`, `corpus-verify` never repairs, never rewrites, never silently drops a defect. `CorpusVerificationReport.result` is `CONSISTENT` only when the defect list is empty.

---

## 6. Holdout sealing mechanism and private-evidence-root delivery contract

Each of the three task classes ships exactly one held-out case, sealed as `mastermind.agent_evaluation_corpus_holdout_seal.v1`:

```yaml
schema: mastermind.agent_evaluation_corpus_holdout_seal.v1
scenario_id: scenario:<family>:<case>
scenario_family: mastermind.<family>.v1
risk_tier: LOW | MEDIUM | HIGH | CRITICAL
corpus_revision: <this wave's frozen anchor, §3>
temporal_cutoff: <UTC-Z timestamp>
sealed_body_digest: sha256:<64 hex>     # digest of the FULL private scenario+fixture bundle
sealing_method: SHA256_OVER_CANONICAL_BUNDLE
private_evidence_root_ref: <symbolic pointer, not yet resolvable -- see below>
authorship: {author_ref, independent_reviewer_ref}
created_at: <UTC-Z timestamp>
seal_digest: sha256:<64 hex>            # own digest, over everything above
```

`sealed_body_digest` is computed over the complete private scenario body (the same field shape a public case would have, plus its fixture content, reduced with `canonical.digest_value`) **before** that body is discarded from this build's working state — the digest is retained; the body is not committed anywhere in this repository, and no code path in this PR writes it anywhere.

**Delivery contract (explicit, not yet built):** `private_evidence_root_ref` names where the sealed body will live once a private evaluation root exists — a later wave's concern, not this one's. Until such a root is built and populated, the reference is **symbolic and intentionally unresolvable**: it documents the destination, not a currently-reachable location. A future wave that builds the private root MUST (a) publish the sealed body at exactly the path `private_evidence_root_ref` names, (b) recompute `sha256:<digest of that body>` and require exact equality with this seal's `sealed_body_digest` before treating the delivered body as authentic, and (c) never modify this seal's `seal_digest` to accommodate a body that does not hash to the pinned value — a body/seal mismatch is a corruption/tamper signal, handled exactly like any other digest mismatch in this fabric (never silently repaired). This wave builds no private root, no delivery mechanism, and no resolver for `private_evidence_root_ref` — that is out of scope here and is named as a gap below (§9).

---

## 7. The three principal-seeded task classes (frozen; formalized here, not replaced)

### TC1 — `mastermind.current_source_comprehension.v1`

Given a frozen extract of real, already-public content from this repository plus a question, produce a grounded factual answer. Gold is deterministic from the frozen extract alone (no external state needed) and the case is replay-safe (re-running it later against the same frozen extract yields the same expected answer regardless of how the live repository has since changed). `risk_tier: LOW`. `effect_policy.mode: NO_EFFECT_ONLY`. `capability_policy` is read-only (`read_frozen_extract` only; `execute_shell`/`network_fetch`/`search_repo`/`write_file` forbidden) — the extract is handed to the agent whole; it is not expected to go searching.

Three public cases, each anchored to a real excerpt of an already-merged, already-public record in this repository (verbatim quotes of this project's own protected specs/plans — not third-party copyrighted material, and not sensitive: these are the exact same publicly-committed sections a human reviewer already reads):

| case | source | question probes |
|---|---|---|
| `effect_unknown_precedence` | design §7.6 (precedence block) | which validity status wins when `EFFECT_UNKNOWN` AND an unauthorized source both apply |
| `canonical_artifact_size_bound` | plan §5.7 (`MAX_CANONICAL_ARTIFACT_BYTES` ruling) | the exact byte value, and whether the exact boundary is accepted or refused |
| `fresh_runner_canonical_owner` | design §3.2 (fresh runner) | which carrier owns the fresh runner, and its truthful capability state |

One sealed holdout: `temporal_cutoff_ordering` (design §8.1's `started_at <= completed_at <= validated_at <= created_at` ordering law).

### TC2 — `mastermind.bounded_implementation_fence.v1`

Given a small spec plus an explicit owned-files fence, produce a change **plan** (never an applied effect — `effect_policy.mode: NO_EFFECT_ONLY` throughout; the agent's capability profile grants `propose_patch`, never `apply_patch`). Scoring is deterministic on fence integrity (does the plan touch only the fenced files) and a short list of named, literal invariants; each case's `expected_contract` fixture states those invariants explicitly under a `deterministic_invariants` key, and separately, honestly, names what is **not** deterministic under a `rubric_residue` key (e.g. prose style, YAML formatting idiom) — the commission's own language for this class ("rubric residue explicit") is implemented as a literal, disclosed field, not a hidden judgment call folded silently into a pass/fail. `risk_tier: MEDIUM`.

Three public cases (synthetic-but-real-shaped: a fictional `example_service` module invented for this corpus, so the corpus never depends on this repository's actual, evolving internals staying byte-stable):

| case | fence | invariant flavor |
|---|---|---|
| `config_flag_addition` | one YAML config file | exact key/value, no other key removed |
| `test_file_addition` | one new test file | exactly one file, newly created (not edited), no existing test touched |
| `doc_only_edit` | one doc file | no code file (`.py`/`.yaml`) proposed at all |

One sealed holdout: `multi_file_coordinated_fence` (a harder two-file coordinated fence, held out specifically because a multi-file case is more likely to leak into a future scorer/training loop's "the answer touches N files" heuristic if published).

### TC3 — `mastermind.carrier_protocol_compliance.v1`

Given a commission-packet-shaped situation plus carrier-thread state, produce the lawful next action (ACK / REFUSE / STOP / stand-down, expressed here as one of several named candidate actions). Gold is deterministic from this organization's own standing carrier-protocol law (this repository's `CLAUDE.md`/`AGENTS.md` §Ship-loop and memory-catalogued findings, paraphrased into synthetic-but-real-shaped situations rather than quoting internal minutiae verbatim). This class targets exactly the org's own observed, previously-costly failure modes named in the commission: stale relays, seat-vs-session identity, and unclaimed-key self-ACKing. `risk_tier: HIGH` — a wrong answer here is an authority/collision risk, not merely an accuracy miss. `capability_policy` is read-only (`read_carrier_thread`, `read_file`; `post_carrier_message`/`write_file`/`execute_shell`/`network_fetch` forbidden — the agent must decide the lawful action without being able to actually take one during evaluation).

| case | failure mode targeted | gold |
|---|---|---|
| `stale_relay_spawn_prompt` | acting on a relayed prompt without re-reading the live carrier | `STOP_AND_REVERIFY` |
| `seat_vs_session_identity` | standing down on an unverified seat-level claim | `VERIFY_THE_CLAIM_NAMES_MY_OWN_SESSION_ID_BEFORE_STANDING_DOWN` |
| `unclaimed_key_no_assignment_edge` | self-ACKing on a dispatcher SPAWN with no real assignment edge | `WAIT_FOR_AN_EXPLICIT_ASSIGNMENT_EDGE_NAMING_THIS_SESSION` |

One sealed holdout: `named_seat_override_freshness_fence` (a harder case combining a named-seat override claim with a freshness-fence timestamp check).

---

## 8. Simplifications disclosed (deviations from the fullest possible reading of the parent design)

The parent design's `source_policy` block supports hidden-solution leakage controls (`denylist_refs`, `solution_refs_hidden`) for cases where a separate "final answer" artifact (a historical PR, a completed task's real outcome) must be kept out of the agent's visible context. None of this wave's nine public cases has such a separate artifact — `expected_contract` **is** the gold, and it is never placed in `privacy.model_visible_artifact_refs`, so the existing `privacy.model_visible_artifact_refs ⊆ allowlisted/fixture refs` cross-field check (already enforced by the merged `contracts.py`, unmodified) already keeps gold out of what a real runner would show the model. Every case in this wave therefore uses `allowlist_artifacts: [], denylist_refs: [], solution_refs_hidden: []`. This is a genuine simplification, not a corpus-wide leakage exemption: a **future** wave adding a case with a real separate solution artifact (e.g. TC1 cases built from an actual historical incident with a known resolution PR) must populate these fields for real, and the existing contract already enforces `solution_refs_hidden ⊆ denylist_refs` the moment it does.

---

## 9. Gaps and explicit non-goals

- **No private evaluation root exists yet.** `private_evidence_root_ref` values are symbolic (§6); no later-wave resolver, delivery mechanism, or private storage is built here.
- **No `EVIDENCE_CONTENT_VERIFIED` claim, anywhere.** `corpus-verify`'s fixture-digest check (§5.7) is bounded to files this repository itself commits under the frozen `corpus_revision` anchor; it is not a general git-history content resolver and never claims the formal third verification scope.
- **No scorer beyond `mastermind.technical_integrity.v1` is built.** Task-specific correctness scorers for these three classes (would a TC2 plan's proposed patch actually satisfy its invariants; would a TC3 answer actually match the gold action) are EVAL-S1 territory, explicitly out of scope here.
- **No experiment/run is created.** This wave ships scenarios and holdout seals only — no `configuration.json`, `experiment.json`, `run.json` is produced; running any of these nine cases through a real evaluation graph is OHF1/OHF2 + EVAL-E1 territory.
- **`tests/test_agent_eval_inertness.py::test_changed_paths_are_within_the_allowed_r0_surface` and `test_no_control_plane_config_dependency_or_workflow_file_touched` are R0-wave-scoped fences, not general CI gates.** Both diff the branch against `origin/master` and assert every changed path is inside a `ALLOWED_PATHS` frozenset that names exactly R0's own (plus the environment-free amendment's two) paths (`tests/test_agent_eval_inertness.py:627-653`). That frozenset is **not** extended by this PR (it lives outside this wave's OWNED FILES and touching it is a scope decision, not a mechanical one — see the commissioning packet's OUT OF SCOPE clause forbidding edits to R0 core files). Consequently `test_changed_paths_are_within_the_allowed_r0_surface` is expected to fail on this branch once it carries a real diff against `origin/master` (it currently reports an *empty* diff and fails for a different, pre-existing reason — see EVIDENCE) — every new C0 path (`scripts/agent_eval/corpus.py`, `tests/test_agent_eval_corpus.py`, `corpus/agent_eval/**`, this plan record) is, correctly, outside R0's frozen allowlist. This is a known, disclosed, structural property of that specific test's design (it hard-codes one wave's own exact path set), not a defect introduced by this PR's actual code. The one-line remedy, if the principal wants this specific test green on this branch, is to extend `ALLOWED_PATHS` with a commented C0 addition — the exact pattern the environment-free amendment already used for its own two paths (`tests/test_agent_eval_inertness.py:639-640,650`) — but that edit is left to the principal/commissioning session's judgment rather than taken unilaterally here.
