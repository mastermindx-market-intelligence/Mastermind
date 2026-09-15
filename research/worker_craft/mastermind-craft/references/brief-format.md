# Complete worker brief: authoring format, not a runtime request

Use schema `mastermind.craft_brief.v1`. The compiler accepts exactly the following
fields; unknown fields, missing fields, invalid types, duplicate JSON keys, invalid
source SHAs, unsafe relative source/write paths, and oversized input are rejected.
All text must be non-secret. These syntax checks do not authenticate an assignment
or establish that its claims are true.

- `role`: orchestrator, designer, frontend, backend, researcher, data-scientist,
  reviewer, or verifier.
- `assignment_ref`: an existing opaque assignment reference, or null. Do not invent
  an Executive Job or claim an active workstream. Null means unbound authoring.
- `mission`, `why`, `user_journey`, `machine_outcome`: complete short descriptions.
- `source_refs`: one or more `{repository, commit, path}` objects. Use exact 40-hex
  commits and normalized repository-relative paths. The compiler does not fetch
  them or certify freshness, protected status, or contents.
- `scope`: `{proposed_write_paths, non_goals}`. Paths are proposed source scope,
  not effective grants; an empty path list means no source edit is proposed.
- `workspace`: `{workspace_ref, host_ref}`. Use owner-issued opaque references or
  null, never credentials, IP addresses, arbitrary filesystem roots, or browser homes.
- `inputs`: source/artifact descriptions, not private source bytes.
- `data_contract`: `{time, missing, corrections, rights}`. Explain material behavior;
  use an explicit reason when a dimension is not applicable.
- `methods`: `{deterministic, model}` lists. Do not delegate deterministic authority
  to an LLM or confuse synthesis with validated prediction.
- `deliverables`, `acceptance`, `stop_conditions`, `resource_constraints`: nonempty
  lists. Acceptance should identify the real producer-to-consumer evidence.
- `continuation`: `{record_owner, next_action}`. Cite the existing durable owner and
  exact next dependency; this file is not an organizational state store.

The compiler emits only a method-enriched brief. It is not a WorkerLaunchSpec,
CapabilityIdentity, CapabilityPackageGeneration, RuntimeBinding, Source Continuity
receipt, or Executive admission. Its input/method/output digests identify authoring
bytes, not authorization, provenance of the underlying evidence, or model behavior.

## Use the compiled result

Review the document against current intent and real source state. The existing
caller may use it as ordinary task content in its already-authorized prompt path.
This does not install a Skill, attest that a provider loaded one, add a tool, or
change the requested capability set. Native Skill enrollment is a separate path.

For an actual handoff, include any additional fields required by the current
protected commission/dialogue procedure. The generic authoring document does not
replace that procedure. A worker must still prove pickup, gates and actual START
through their owners before effects.

## Return format

Return mission outcome; capability delta; exact source/artifact references; checks
actually run and their outputs; real-path proof or its absence; unresolveds and
limitations; the durable record destination; and one exact next action. Preserve
existing WorkerResult/CollectionReceipt and dialogue schemas when those apply.
Do not introduce a new result schema or lifecycle store for this craft package.
