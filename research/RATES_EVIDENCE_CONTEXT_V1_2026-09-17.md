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
