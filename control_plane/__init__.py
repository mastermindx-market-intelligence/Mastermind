"""control_plane — job governance substrate for Mastermind (MW1).

Modules
-------
run_events   Append-only event log at data/governance/run_events.jsonl.
guardrail    R3 severity taxonomy + GuardrailResult reporting dataclass.
locks        Advisory file locks (fcntl.flock, non-blocking) per book/op.
run_ledger   Job-level run records (extends brain/runlog scope — see docstring).
flags        Enumerate every MASTERMIND_* env var currently set.
worker_runtime  Local persisted Worker/Job lifecycle proof (Executive OS Phase 1A).

No implicit execution integration: runtime workers are registered labels only.
No third-party dependencies; stdlib only.
"""
