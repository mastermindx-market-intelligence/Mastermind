"""control_plane — job governance substrate for Mastermind (MW1).

Modules
-------
run_events   Append-only event log at data/governance/run_events.jsonl.
guardrail    R3 severity taxonomy + GuardrailResult reporting dataclass.
locks        Advisory file locks (fcntl.flock, non-blocking) per book/op.
run_ledger   Job-level run records (extends brain/runlog scope — see docstring).
flags        Enumerate every MASTERMIND_* env var currently set.
worker_runtime  Compatibility facade for the durable Executive worker runtime.
executive_runtime  SQLite Worker/QuotaClass/Job/Attempt/Event source of truth.
executive_authority  Fail-closed executable worker capability reader.
codex_worker  Isolated one-shot Codex process adapter (Executive OS Phase 1B).

No implicit execution integration: the scheduler and application do not import or
start the Executive supervisor.  Provider execution exists only behind the
explicit Phase 1B operator entry point.
"""
