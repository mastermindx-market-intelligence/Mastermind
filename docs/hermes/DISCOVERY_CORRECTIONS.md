# Canonical discovery corrections

## Outcome and ownership

This slice lets a qualified Workspace principal correct an existing project discovery without losing its original evidence. It uses the existing Project Knowledge compiler, private original-input custody, source-operation Events, Git publisher and canonical-data observation. Agent OS remains the durable knowledge owner; the UI and Hermes do not acquire a parallel memory store or publication queue.

The Macro compiler is introduced by Macro PR 10831, currently pinned at `a9906c9d5aaf816048d6467fa39d895034180c87`. This includes bounded validation of malformed sibling correction metadata before reference membership. The Workspace implementation requires that compiler in its installed CODE closure. A source PR, test fixture or current read is not an installed correction grant.

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

## Explicit native v4 integration

`mastermind.hermes_native_executive_consumer/v4` selects the finite `coo.discovery_correction.v1` catalogue. The disabled `principal.hermes-native.executive-coo.discovery-correction.v1` profile uses the existing single COO OAuth connection and its independently authenticated Workspace companion. Enrollment requires the exact Workspace privacy derivation. Earlier v2/v3 catalogues retain their closed meanings and digests.

The catalogue adds two tools:

| Tool | Closed operations and original owner |
|---|---|
| `executive_project_discovery_source` | `current` reads the selected DSC at an exact current DATA commit; `original` opens the pre-correction note retained by the exact eight-field original operation. |
| `executive_project_discovery_correction` | `prepare`, `read`, `submit`, `reconcile` call the original audited Workspace source-operation handlers with their existing grants, private input, Events and publisher. |

The current-read route is `/workspace/project-discovery-source/current`; it needs the distinct `read_latest_project_data` grant and the actual installed canonical DATA binding. It cannot fall back to adopted CODE. It bypasses catalogue sampling only: record validity, selected WS association, immutable blobs, size limits and owner/permission fences still apply. The returned Git blob revision and the two SHA-256 preimage digests have distinct fields.

The original-read route is `/workspace/source-operation/original`. It uses the retained Event/private-input custody and the current correction grant. Its explicit retained-original schema has no invented current DATA observation, Git blob revision or commit timestamp. It does not compile, prepare, restore, reconcile or publish. Loss of current note/compiler availability does not by itself erase verified retained history.

Signed COO forwarding authenticates both resources and rechecks the captured audited App/router and actual authority. Prepare/submit/reconcile use their own typed discovery result, not the read-only E1 result. Submission first inspects the full original lookup; only the original INTENT can enter its single submission. Already-progressed operations return their canonical status.

The native plugin registers two actual native registry leases under the existing replacement transaction. Both names are checked before registration. Partial failure disposes only captured leases; an unreturned lease remains uncertain on the original ConsumerSlot. Parent session/route, actual loaded plugin/entry/schema, release/package custody, current mandate and the incumbent trust/spend owner all remain live gates. Raw MCP exposure stays excluded, and no parent Job or child authority is manufactured.

The original SDK lock and in-flight set own transport. A positively proved refusal before `session.call_tool` is NOT_DISPATCHED; a timeout or malformed post-invocation mutation result retains the exact original lookup. A timed-out future and its uncertainty become visible together under the slot lock. The original future is neither cancelled nor replayed. Matching canonical read/reconcile can resolve uncertainty; a retained owner NOT_DISPATCHED result can prove no effect, while absence of a receipt alone cannot. A failed cost refund retains the original reservation and blocks replacement.

V4 serving readback includes the two observed tool-schema digests, any original uncertain operation and unresolved reservation state. The finite secondary-worker archive includes the original COO descriptor and Agent OS helper import closure; the held release loader still authenticates imported files.

## Acceptance still required

Source tests execute real temporary Git, compiler, Event/private-input, signed App/MCP, installed collector and held-source import paths with declared credential/host edges. Pinned native PluginContext/registry cases require the exact Hermes checkout and are not credited when skipped. Source qualification does not enable the profile.

Installed permission, serving v4 readback, original publication/current-context feedback, live browser/account/fleet journeys and held-out learning efficacy remain acceptance work. The original denied runtime action must be recovered through its original authorized connection; another host or test runner does not substitute for it.
