# Canonical discovery corrections

## Outcome and ownership

This slice lets a qualified Workspace principal correct an existing project discovery without losing its original evidence. It uses the existing Project Knowledge compiler, private original-input custody, source-operation Events, Git publisher and canonical-data observation. Agent OS remains the durable knowledge owner; the UI and Hermes do not acquire a parallel memory store or publication queue.

The Macro compiler is introduced by Macro PR 10831 at `b4b08673508bb0aafe2aa729666f1aefab23911c`. The Workspace implementation requires that compiler in its installed CODE closure. A source PR, test fixture or current read is not an installed correction grant.

## One original operation

The public action is `correct_project_discovery`. The closed request schema is `mastermind.project_discovery_correct_request.v1`, with an original `mmos-project-discovery-correct-` identifier followed by 40 lower-case hexadecimal characters. It contains exactly:

| Field | Meaning |
|---|---|
| `schema`, `request_id` | Closed request type and original operation |
| `work_ref` | Selected canonical workstream |
| `source_commit` | Captured canonical DATA basis |
| `base_revision` | Exact workstream content SHA-256 |
| `discovery_ref` | Selected predecessor discovery |
| `expected_discovery_revision` | Exact predecessor content SHA-256, distinct from its Git blob revision |
| `correction_reason` | Literal reason for changing the finding |
| `replacement` | Explicit claim, falsifier, consequence, kind, confidence, evidence date, checking method, expiry, body and references |

No actor, principal, permission, clock, publication path or replacement reference is accepted from the caller. The replacement reference is derived from the authenticated principal scope, original request ID and workstream. Evidence date and confidence are explicit; editing a finding never automatically verifies it.

The original inspection/reconciliation lookup has exactly eight fields: `action`, `request_id`, `work_ref`, `source_commit`, `base_revision`, `request_sha256`, `discovery_ref`, and `expected_discovery_revision`. The file/preference seven-field forms remain unchanged. A correction never borrows `expected_preference_revision`.

## Atomic source semantics

Preparation captures the complete bounded WS/DEC/DSC/HND reference universe through the existing installed compiler. It qualifies the selected workstream, reciprocal correction lineage, absence of a replacement and absence of foreign effects. The owner retains the closure witness with the original private input. A later prepare with the same ID restores that original; changed same-ID content conflicts before a new capture.

Exactly three postimages are permitted:

1. The original DSC, preserving its evidence bytes and adding its supersession link.
2. The derived replacement DSC, with explicit workstream scope and typed provenance.
3. The selected WS, retaining the predecessor citation and adding the replacement.

The ordinary canonical validator checks the merged reference graph. Current context excludes invalid corrections and a superseded predecessor. The typed provenance marker records evidence; it grants no authority and does not establish the claim's truth.

The pure reference predicate does not certify arbitrary host filesystem aliases. The incumbent installed Git/materialization guard remains required. Capture retains the original process deadline and a bounded 32 MiB ceiling for this complete-reference operation; the old file/preference capture limit stays unchanged.

## Permission and transport

Workspace acquisition binding v6 adds the distinct `project_discovery_correct` slot. The project-access v3 response has eleven exact action rows. Old v4/v5 binding and v1/v2 projection shapes remain closed. General read, latest DATA read, file addition, preference editing, or Executive authority do not imply correction permission.

The existing fixed Workspace HTTP endpoints perform context, prepare, submit, operation read and reconcile. The original Tauri transport exposes the same endpoints; there is no new native command, OAuth issuer or credential store. Every receiver validates the closed request and current action-specific permission. A mutation that may have been invoked retains its original unknown state; it is not automatically resubmitted.

`SOURCE_OBSERVED` must contain the exact selected OLD path, independently derived NEW path and WS path, with no duplicates and one publication commit. When the prepared Review is present, the consumer also compares all three postimage hashes. Source-loss recovery uses the retained safe lookup and does not require the private body, current compiler or original Library read.

## User journey

The correction action appears only after the user opens a fully read, hash-checked discovery through the current Library owner and the distinct action context is available. Metadata alone cannot issue an editable discovery. The issued object retains the source read, catalogue, CODE, DATA, owner and method identity fences.

The form starts with blank evidence, confidence and date fields. It captures one original ID and freezes the literal request once handed to preparation. Review shows the correction reason, replacement, evidence, preserved original text and three source records. Only the explicit Publish gesture reserves the incumbent durable pointer and submits the reviewed witness.

If a preparation response is lost before that reservation, Check original operation uses the retained eight-field lookup and the existing read-only inspection route. It neither makes a second preparation nor recovers an unrelated pointer. It rechecks the exact action context ticket after the awaited response. Published-operation recovery uses the original controller and durable pointer.

Authentication, host, source owner, current CODE/DATA, opened discovery, or permission-ticket changes withdraw mutation controls. Original status inspection deliberately remains independent of the current source. Labels are provided in English and Simplified Chinese within the existing Knowledge editor styles.

## Source qualification and limits

The Macro source has 125 focused compiler tests, including actual CLI validation/current-context checks. The Workspace fixture drives the actual compiler, private-input owner, Events, fixed Git publisher and temporary upstream; it proves one original proposal, body-free reconciliation, exact three-source publication and preserved original history. The source suite covers changed same-ID payloads, permission withdrawal, incomplete references, aliases and post-invocation uncertainty.

The frontend's recorded owner fixture contains actual temporary-Git bytes and receipts. Native authentication, Programs orientation and initial installed CODE are explicit UI seams. The full App test opens the original discovery, reviews explicit evidence, submits once and refreshes the genuine read-only source frame. It does not claim an installed current-DATA compiler or live account. Additional tests cover closed contracts, legacy recovery, stale discovery, exact context-ticket withdrawal and lost-prepare inspection.

The existing CI owns full-checkout Python, Rust and frontend qualification. Local source results are not a production enrollment or live publication receipt.

## Remaining teammate integration

The native v2/v3 consumer meanings remain unchanged in this slice. A separately reviewed v4 catalogue must expose the correction lifecycle through the same paired Executive/Workspace OAuth connection, same audited Workspace handlers, mission grants and ConsumerSlot. It must not route durable preparation/submission through a read-only E1 envelope.

The current catalogue-sampled source selector remains exact. Direct current discovery reads, omitted records and original historical preimage views require explicit closed selectors under the existing reader/private-input owners. Arbitrary historical paths/commits and a second note store are not supported. Installed permission, native serving readback, actual publication/current-context feedback and held-out learning efficacy remain acceptance work.
