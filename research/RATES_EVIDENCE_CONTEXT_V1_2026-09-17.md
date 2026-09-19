# Rates evidence in the existing decision context

Operation: rates-evidence-context-20260917-sol-002. Source: Mastermind b731149296a9d837d426730813f68d5acc6133ac. Macro evidence: 63fb8dd9fa7dbe43c02ca6eac84b22fbbc9706dd.

Goal: the existing reasoning consumer can inspect bounded, per-maturity nominal-yield evidence without treating unknown receipt times, stale data, or daily momentum as actionable intraday knowledge.

Architecture: a pure projection in brain/rates_evidence.py consumes the existing rates_command.v1 artifact. brain/decision_context.py adds the projection to decision_context.v2 and prompt_summary and reads only the existing vendored RIC artifact through its existing JSON reader. There is no new collector, state writer, queue, feature score, rank, sizing, trade gate, or evaluation system.

Scope: this is an input-fidelity capability for the approved rates-aware leader-pullback workflow, not the entire workflow or a profitability claim. The three Chairman-delivered research lanes retain their assignments. Keep #7088 and Terminal #601 unchanged. Historical-vintage certification is unavailable in the consumed schema and must remain false.

Interfaces: project_rates(artifact, market_asof=None, analysis_cutoff=None) -> dict. assemble accepts optional rates_command and rates_cutoff; build reads the existing source only when rates_command is omitted. prompt_summary carries rates_evidence unchanged.

Task 1: write tests/test_rates_evidence.py::test_missing_rates_is_explicit and prove it fails because the field is missing. Then freeze the complete projection behavior with tests for normal input, unknown or date-only knowledge times, invalid/future dates, stale rows, non-finite/bool values, unit/source mismatches, immutability, bounded output, and strict cutoff withholding.

Task 2: implement the pure projector plus the smallest additive assemble/build/prompt_summary integration. Retain existing governor, signals and data-quality behavior byte-for-byte. Five existing nominal maturities and three source horizons only; never invent real yields, meeting probabilities, or intraday precision. Source horizon labels mean observed intervals in yield_momentum.v1, not verified exchange sessions.

Task 3: run focused and adjacent decision-context tests; exercise actual pinned RIC bytes through assemble and prompt_summary and a prior cutoff. Retain a compact source-digest and outcome receipt, never commit market data. Compile and diff-check the exact candidate.

Task 4: publish scoped source and evidence to a draft PR; obtain independent exact-head review and required concluded checks before release. No autonomous deployment or source-authority promotion. Persist the delivery frontier, exact branch/head and remaining upstream data requirements.

Direct execution rationale: CRITICAL_PATH_SHORTCUT; this bounded existing-consumer integration is independent of the researchers and does not select a trading model.


## Actual read consumer amendment

The existing `decision_context.v2` projection is now accompanied by one additive `get_rates_evidence` read in the existing `brain/bot_mcp.py` server. This is the concrete model-facing read path, not a new server, generic endpoint, registry, publication writer, lifecycle, or trading engine. It calls the canonical `decision_context.build(write=False)` and returns only the bounded rates projection. It accepts no source path, account, provider, policy or trade parameters.

The earlier prompt-summary preservation test was insufficient to establish actual seat visibility: `get_regime` deliberately narrows its payload, and PM prompt rendering selects named sections. This amendment closes that information-loss gap for the existing read-tool surface, without expanding the portfolio sizing prompt or changing a recommendation. Prophet/Terminal UI and strategy integration remain separate unproven steps.

Failure behavior is closed unavailable evidence with no raw exception detail. Per-maturity dates, missingness, percent/basis-point units, observed-interval horizons, New York observation date conventions, false replay certification and all-false action authority survive the SDK memory transport. The read never writes `data/decision_context`, and absence never becomes flat rates or calm risk.

Compatibility: exact #495 head `9dba2614b8394b75f23e8be77cf08bf21072dece` modifies the existing serializer helpers, while exact #772 head `cd34f2a9c1e94308e73cd86097037e3c131143f7` modifies `get_overnight_tape`. Our only named tool-server changes are the new function and `_READ` registration. The immutable sibling changes are AST-member disjoint. The #495 proposed serializer also round-trips the actual rates payload without alteration in an isolated in-memory test. This is compatibility evidence, not acceptance, custody transfer, or release of either sibling.


### Dated context is not current-session certification

The non-cutoff mode is `dated_context`, not `current_context`. All outputs explicitly retain `current_session_freshness=not_certified` with a basis limited to alignment with the supplied market-as-of date. Even two matching old snapshots cannot certify present-session freshness. This differs from—and does not replace—the separate `as_observed_replay_certified=false` limitation. No new market calendar, freshness owner or policy threshold is added.


## Existing stock-package integration and wire contract

Within the same original consumer operation, `get_ticker_package` now calls the existing read-only rates handler for names that already have intelligence/intake evidence. Unknown names keep their existing no-evidence response. `annotate_ticker_package` preserves the stock payload, attaches canonical all-false-authority rates and a separate date relationship, and does not infer ticker rate beta, leadership, historical candidate knowledge, an entry verdict or freshness.

`serialize_ticker_package` delegates to the unchanged generic serializer. It compares previously deliverable stock fields against the no-rates baseline and validates complete rates/qualification after serialization. Object-form is preferred; the alternative columnar representation factors shared row fields without dropping any information. For that representation, reconstruct each tenor with `{**series.shared, **dict(zip(series.columns, series.rows[tenor]))}` and restore `schema=source_schema`. `rates_context_encoding` identifies the representation. No new persistence, source authority, consumer registry or generic serialization owner is introduced.

When either rates or primary stock evidence would be lost, omit the whole rates payload explicitly and name `get_rates_evidence`. Responses unable to preserve the primary baseline within the 8,000-byte UTF-8 ceiling are explicitly unavailable, never represented as complete research. Existing lens/intake meanings, scores, ranking, generic JSON helpers, overnight read and action registration remain outside this amendment.

The test contract includes missing/wrong-source schema, forged authority, separate artifact dates, input immutability, no new candidate on rates alone, source-read exceptions, UTF-8 budget, rates qualification loss, primary-evidence displacement and exact lossless reconstruction. Source-body tests are distinct from real SDK tests. The existing SDK test file contains the latter for canonical CI; local SDK/runtime access is held after the platform refusal and is not retried on another environment.

Final captured-input/source-body differential, proof limits and continuation are recorded in the latest section of `RATES_AWARE_REPLAY_INPUT_BOUNDARY_2026-09-17.md`. This is still a rates-context consumer change, not the parent selection/timing suite or accepted release.


### Effective origin semantics after the controlled fill experiment

The source-origin finding in `RATES_OBSERVATION_ORIGIN_FINDING_2026-09-17.md` materially refines the original horizon/freshness wording. Effective outputs now use `observation_origin=unverified`, `horizon_basis=source_frame_intervals`, and `freshness_basis=frame_alignment_only`. Source-reported dates and numeric values are not rewritten; no raw observation is inferred merely because the aligned feature cell is populated. The acceleration description likewise refers to frame intervals, not necessarily newly observed market prints.

The frame can contain carried values. An unchanged five-row value is therefore not by itself evidence of observed rate exhaustion. The existing input/provenance owner must eventually carry origin/imputation information before an event detector can make that stronger claim. Current consumer context stays read-only and uncertified for source origin, present-session freshness and historical replay. This qualification survives both lossless wire forms and is covered by the latest 95-test / 3,401-name proof recorded in the continuation document.


### Effective primary-serializer integration

The final implementation refines the earlier multi-render transport plan. The existing generic serializer is called exactly once on the original stock fields. Its decoded result is the immutable primary baseline for this response. Optional rates are added afterward with lossless JSON whitespace removal and, only when necessary, the explicit lossless columnar representation. The augmented object never reenters the lossy primary serializer. This preserves the existing owner's stock projection without letting the optional rates addition crowd out or recompress its facts.

The budget regression tests require an 8,000-byte previously fitting stock result to remain available and prove that the generic serializer never receives `rates_context`. All source/clock/authority qualifiers survive; cases that cannot fit a complete rates object are explicit omissions. The 8,000 UTF-8 byte budget is this consumer's chosen ceiling, not an assertion about SDK capacity. Final current-source results are 97 local tests and 3,401-name differential proof, including zero newly unavailable previously fitting baselines, as recorded in the latest continuation section.
