# Document contracts

Start from assignment.json and replace every field with the original canonical assignment. Do not reuse the canary scope or dates for another task. Examples of actual completion, critique, validation and continuation are in docs/hermes/design-director/examples.

Completion fields: schema, operation_id, assignment_id, assignment_sha256, session_ref, account_alias, summary, continuation, status, reported_at, decisions, interactions, gaps, limitations, checks, screens, coverage. Each screen has exact file_id/page_id/node_id, name, change and a screenshot with path, sha256, source_ref and observed_at. `coverage` has preserve/states/viewports/acceptance, each listing the exact original requirements in order with observed/missing status, specific evidence and screenshot_sha256 list. Images cannot prove nonvisual runtime requirements; leave those missing.

Critique fields: schema, completion_sha256, reviewer, evidence_ref, observed_at, viewed_screenshot_sha256, all twelve dimensions with rating/evidence, and issues with priority/dimension/finding/evidence/requested_change. `not_observed` withholds candidacy.

Handoff fields: schema, completion_sha256, decision_ref, decision_actor, implementation_repo, target_paths, component_mapping, tokens, interactions, data_contracts, responsive, accessibility, verification, known_gaps. Every field is nonempty and must describe the real accepted design. Citing a decision does not authenticate it.

Observation fields: schema mastermind.design.observation.v1, original operation_id/assignment_id, source_ref, state, observed_at. States are prepared/delivered/started/running/completed/failed/effect_unknown. The helper returns advice, not a verified lifecycle transition.
