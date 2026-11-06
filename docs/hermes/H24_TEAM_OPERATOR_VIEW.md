# H24-06 — Shared team operator projection

## Source delivery and scope

Packet: **H24-06**, concurrent placement authorized by the Chairman on 2026-11-06.
Source base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437` in
`mastermindx-market-intelligence/Mastermind`.
Branch: `sol/h24-06-team-projection-20261106`.
Procedure pin: protected master `88a8b103a5a69e4b4e870a184655dde9fd5875c3`,
`mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap major 1.
Continuation compatibility pin: protected master
`28a894186eb56654ab4e833eb11a183d2eed46ae`; same schema/version/bootstrap.
The changed governing files were checked; unchanged companions retain their verified
contents. The immutable implementation base remains the packet's original base.

This source delivery adds exactly three files:

- `integrations/secretary_team_access/team_projection.py`
- `tests/test_h24_team_projection.py`
- `docs/hermes/H24_TEAM_OPERATOR_VIEW.md`

The bounded worker scope is a pure read model, fixtures, and adoption guidance.
Runtime activation, enrollment, credentials, service installation, deployment,
production serving, UI navigation, source-authority changes, merging and approval
are outside this delivery. PR #2120 and C29–C34 integration writers remain separate.
No H24-01 completion or soft wave seal is a source-work dependency for this packet.

The implementation retains direct ownership of the tightly coupled join and its
tests (`LOWER_TOTAL_OVERHEAD`). A read-only native advisor supplied contract
judgment about authentication, acceptance and result association. This was
advisory design work, not a mandatory review gate or a formal GitHub approval.

## What becomes useful

`project_team` turns one already-authorized Mission v3 into compact operator cards.
The cards preserve the original root, immediate parent, depth, role, Job status,
available Attempt evidence, result reference, qualified result state, review,
acceptance and coverage. A missing parent remains a missing relationship; the
projector never invents a new root for that child. Pending work and observed
Attempt starts have distinct fields.

The same mission can be displayed to GB1/Meta-CEO and Secretary 2. Each host read
still uses that caller's own verified principal and current grant. Role names,
workstream strings, root IDs, fingerprints and shared view bytes confer no access.

There is no IO, clock acquisition, identity store, mission store, cache, command
API, timer, polling service, subscription, provider selection, retry or dispatch in
the new module. `now` is an explicit host input. All mutable input and output
containers are detached; concurrent calls share no mutable state.

## Existing owners and exact trust boundary

The source contracts below are pinned to the immutable base above:

| Concern | Existing owner / source | H24-06 use |
| --- | --- | --- |
| Primary mission | `control_plane/mission_workspace.py::compose_mission_workspace_v3` | Retain Mission v3 and its read state, lineage, missingness and result-reference partitions. |
| Existing bounded Secretary facts | `integrations/secretary_team_access/mission.py::_consumed_facts`, `_fingerprint_facts` | Reuse consumed fields and semantic facts. H24 consumes nullable owner subreceipts separately because the incumbent summary requires non-null subreceipts. No changes to that module. |
| Source acquisition and authorization | `control_plane/workspace_read_service.py` | Host owns before/after authorization, source observations and bounded Runtime reads. |
| Result association | `common/executive_workspace_mission_result_contract.py`, `WorkspaceReadService._mission_result_associated` | Consume the existing compound Mission/Result response; match its embedded Mission exactly. |
| Result meaning | `control_plane/fabric_result_projection.py::project_fabric_role_result` | Consume its already-qualified public result and validate the fields used by this display. Do not revalidate raw Runtime envelopes in a second owner. |
| Product acceptance | `common/product_acceptance_read_contract.py`, Mission v4 companion | Reuse `validate_view`, require the exact original request and current parent/subject result references. |
| Delivery / Wake | Mission `transport` and `transport.w3c` | Preserve mission-scoped delivery, uncertainty and receipt facts; never reinterpret them as per-child consumption. |
| UI decode | `app/mastermind_os/src/mission.ts::decodeMissionv3`, `decodeMissionv4` | Existing UI decoder remains the consumer boundary; H24 adds no navigation or build hook. |

“Signed Mission read” means the existing signed JWT request, verifier, Workspace
App and host/service authorization path. **Mission JSON has no standalone document
signature.** This module adds no signature format and cannot authenticate arbitrary
JSON. The host must acquire the original owner response and revalidate permissions
before releasing a projection. It must discard denied/revoked responses and any
previously cached projection. A digest here checks association/integrity; it is not
authentication.

The original Secretary `read_mission()` returns a smaller summary. That summary
is deliberately **not** accepted as a Mission v3 input to this module.

## Pure API

```python
view = project_team(
    mission_v3_body,
    selection={"work_ref": work_ref, "root_job_id": root_job_id},
    now=host_time,
    result_pairs=(),
    acceptance_companion=None,
    request_message_key=None,
    previous_fingerprint=None,
    limit=8,
    suppress_unchanged_details=False,  # Full display; True is the compact default.
)
text = render_operator_text(view)
```

`selection` and the optional `request_message_key` come from the host's original
request, independently of the response under validation. There is no principal,
credential, URL, host, permission flag or dispatch callback argument.

Optional `result_pairs` are complete existing
`mastermind.workspace_mission_result.v1` bodies. Each AVAILABLE pair must contain
exactly the supplied Mission v3, its exact selected reference and the same
qualified source observation. Standalone result bodies and separately sampled
Mission/result reads are not joined optimistically. Independent reads intentionally
have different observation identities. A host should project the Mission embedded
in a compound result response. Multiple pairs are supported only when their
embedded Mission bytes are identical. The projector never rewrites receipts to make
independent reads appear atomic.

An optional `mastermind.mission_workspace.v4` companion must likewise contain the
exact supplied Mission v3. Its acceptance selection includes the original
`request_message_key`. The acceptance receipt must match the selected root, parent
Attempt, parent result-envelope digest, subject Job and subject result-envelope
digest, qualified ruling and source-continuity declaration. The existing owner
has already established the source bracket; H24 checks the consumed public facts.

Malformed structures, foreign or contradictory joins and over-budget input raise
`ValueError` before returning a view. Missing/invalid source time is represented as
UNAVAILABLE. Typed owner unavailability remains visible. Lowering a display limit
changes only visibility and omission counts, not source activity.

The actual Mission reducer can emit UNKNOWN observation with null Control Room and
Runtime subreceipts, or CONFLICT observation with a missing subreceipt. These valid
noncurrent responses retain their cards, missingness and unknowns in an UNAVAILABLE
operator view; `decision_needed` is null. H24 validates the original nullable receipt
and consumes other facts through the incumbent reducer without modifying the input
Mission, minting a substitute receipt or making missing digests non-null. A forged
CURRENT/SAME claim with missing receipts, a foreign selection or malformed digest
is refused.

## Output schema

Version: **`mastermind.secretary_team_operator_view.v1`**. This is a derived display
contract, not an Executive lifecycle or authorization schema.

| Top-level field | Contract |
| --- | --- |
| `schema`, `selection` | Version and exact original work/root selection. |
| `currentness` | Closed schema exported as `CURRENTNESS_SCHEMA`; defined below. |
| `source` | Owner label, exact input Mission digest, Runtime snapshot digest, Control Room document digest, source coverage. |
| `fingerprint`, `changed` | SHA-256 semantic comparison; `changed` is null on the first view. |
| `attention` | `reasoning_wake_recommended` is true only on a changed fingerprint; `dispatch_permitted` is always false. |
| `coverage` | Source totals, unknown counts, omissions, unjoined IDs, reference/detail counts, display omissions and unchanged suppression. `full_fleet=false`; unseen population is always UNKNOWN. |
| `cards`, `hierarchy` | Bounded flat cards plus parent edges; original IDs and depths are retained. `parent_visible` describes only the display window. |
| `principal` | Existing accountable seat, current worker/target observations and owed turn; these are observed mission facts, not the viewer's identity. |
| `transport` | Mission scope, dispatch state, historical/watch facts, W3C state, wake/terminal states and receipt. |
| `acceptance` | Owner state, reasons and receipt; separate from execution and review. |
| `missingness`, `missingness_omitted_count` | Bounded original missingness rows with explicit remaining count. |
| `display_only`, `details_included` | Display-only is always true. Compact mode suppresses unchanged details; full display mode returns the selected cards and hierarchy while the reasoning wake remains false. |

Each card has these exact fields:

```text
job_id, original_root_job_id, parent_job_id, depth, lineage, role,
job_state, current_attempt_id, latest_attempt, start_evidence, currentness,
effects, placement, result, product_acceptance,
decision_needed, decision_reason_codes, display_actions
```

`lineage` is ROOT, JOINED, MISSING_PARENT or DEPTH_CONFLICT. Duplicate IDs, self
parenting and cycles refuse the view. Missing parents and inconsistent depths
remain visible and downgrade an otherwise CURRENT operator view to PARTIAL.

`start_evidence` is OBSERVED only when the canonical child Attempt has a start
timestamp or RUNNING status; otherwise it is UNPROVEN. A Job's QUEUED, CLAIMED or
COMPLETED appearance does not manufacture a start timestamp. Root Attempt detail
is not synthesized from a mission-level principal card. Result references retain
their own exact Attempt IDs.

`result.state` is REFERENCE_ONLY, AVAILABLE, CONTENT_OVER_BUDGET,
ABSENT_IN_SNAPSHOT, OMITTED or UNAVAILABLE. A reference always retains its owner
`validation=UNVALIDATED` navigation label; an associated qualified result is a
separate facet. Raw result text, artifacts and arbitrary model instructions are
not copied into operator cards. Review metadata retains
`latest_revision_currentness=UNPROVEN` and the distinct reviewed **role-result**
digest; that digest is never substituted for the **envelope** selector digest.

### Currentness

The exported JSON Schema `CURRENTNESS_SCHEMA` is closed. Its keys are:

```text
state: CURRENT | PARTIAL | HISTORICAL | UNAVAILABLE
owner_state: CURRENT | PARTIAL | HISTORICAL | UNAVAILABLE
freshness: FRESH | AGED | UNKNOWN | FUTURE
generated_at: string | null
age_seconds: nonnegative integer | null
guard_seconds: 120
reason_codes: string[]
```

Owner state is preserved. The effective display state can only become more
conservative: incomplete coverage or lineage is PARTIAL; an expired local
freshness guard is HISTORICAL; invalid/future source time or an unqualified owner
observation is UNAVAILABLE. CURRENT
means the Mission observation qualifies, not that placement, result content or
acceptance is available. Missing coverage is never zero activity.

`decision_needed` is a display hint from observed owed turns, rejected reviews,
execution failures and lineage problems. Stale or unavailable cards return null,
not an actionable decision. False means no such reason was observed in this card;
it does not claim there is no unobserved work.

### Acceptance, rejection and consumption

Mission v3 and the qualified result projector emit NOT_PROJECTED acceptance.
Only the existing Mission v4 product receipt can set a subject card's
`product_acceptance.accepted=true`. Its `current` flag becomes false when local
freshness expires; the historical receipt is retained as historical evidence.
Other cards keep accepted=null.

The current product-acceptance owner defines ACCEPTED and UNAVAILABLE, **not
REJECTED**. Review `verdict=reject` is displayed as a review rejection with a
review/repair attention hint. It never becomes a fabricated product rejection or
acceptance. CI green, exit zero, a terminal Attempt, review approval and Wake
ACCEPTED never set product acceptance.

Per-result consumption is UNPROVEN unless the qualified acceptance owner proves
the original parent's consumption for that exact subject. Mission-level
DELIVERED_UNACKNOWLEDGED, TARGET_ACKNOWLEDGED and SOURCE_RESOLVED stay mission-level
facts. They cannot identify which child result was consumed.

### Quiet semantic comparison and bounds

The fingerprint includes roles, lineage, lifecycle facts/times, snapshot/source
digests, results, acceptance, coverage, meaningful Wake state and freshness class.
It excludes generated-at churn, observation handles/samples, age seconds and
display-window size. A FRESH-to-AGED transition is material; subsequent unchanged
aged reads remain quiet. Equal fingerprints recommend no reasoning wake and
retain stale/partial warnings and omission counts. This is comparison only: no
event cursor, grant, scheduler or actual wake is created.

Use `suppress_unchanged_details=False` for a freshly authorized full display. The
host can expand or repaint the card window without a synthetic source change or a
reasoning wake. No previous card cache is required. The default True preserves the
compact Secretary response; its text explicitly explains detail suppression so an
empty detail window cannot be mistaken for zero observed activity. This presentation
option is excluded from the semantic fingerprint and confers no permission.

Bounds: 2,000,000 bytes per Mission/compound/acceptance input; at most 17 result
pairs; each nested Result socket envelope including LF must fit 16,384 bytes;
30,000 JSON nodes and depth 32 per input; at most 32 cards; default display 8;
32,768-byte serialized output including LF. Over-limit data is refused, never
silently truncated into a successful result. Cumulative UTF-8 JSON bytes, escape
expansion, separators and trailing LF are counted before whole-container encoding;
repeated references count at every occurrence. Public identity strings are validated
and are not shortened into aliases. Display omissions have separate counts from
source omissions and unchanged-detail suppression.

Display action vocabulary is limited to: **Inspect evidence**, **Inspect result**,
**Review result**, **Review rejection**, **Inspect lineage**, **Reconcile source**,
and **Inspect acceptance**. These are accessible labels only, with no action URLs,
callbacks, buttons or decisions dispatched.

## Representative textual views

The following excerpt was generated by `render_operator_text` from the real
Mission reducer fixture in `tests/test_h24_team_projection.py`:

```text
WS:ONE / JOB-1 — CURRENT (owner CURRENT)
JOB-2 [aggregation] parent=JOB-1 depth=1 RUNNING; start OBSERVED; result ABSENT_IN_SNAPSHOT; acceptance NOT_PROJECTED; consumption UNPROVEN; lineage JOINED
JOB-3 [work] parent=JOB-2 depth=2 QUEUED; start UNPROVEN; result ABSENT_IN_SNAPSHOT; acceptance NOT_PROJECTED; consumption UNPROVEN; lineage JOINED
JOB-4 [review] parent=JOB-2 depth=2 COMPLETED; start OBSERVED; result ABSENT_IN_SNAPSHOT; acceptance NOT_PROJECTED; consumption UNPROVEN; lineage JOINED
JOB-5 [repair] parent=JOB-2 depth=2 QUEUED; start UNPROVEN; result ABSENT_IN_SNAPSHOT; acceptance NOT_PROJECTED; consumption UNPROVEN; lineage JOINED
Coverage: 5/5 cards; source omitted=0; unjoined=0; unseen population UNKNOWN
Mission delivery: RETURNED; wake=DELIVERED_UNACKNOWLEDGED; per-result consumption stays separate
```

An actual compound Runtime/reducer fixture returns this distinct review row:

```text
JOB-004 [review] parent=JOB-001 depth=1 COMPLETED; start OBSERVED; result AVAILABLE; review reject; acceptance NOT_PROJECTED; consumption UNPROVEN; lineage JOINED
```

The accepted-result fixture separately traverses the existing acceptance reader
and Workspace service. It proves PRODUCT_ACCEPTED for the exact subject only after
the original parent return and consumption exist. Omitting either produces
PARENT_RETURN_UNVERIFIED or PARENT_CONSUMPTION_UNPROVEN.

## Actual missing fields and adoption recommendations

| Missing field / boundary | Truth at the base | File-specific next step for the existing owner |
| --- | --- | --- |
| Child host, provider pool, model, worker placement | Closed Mission child/Attempt cards expose no host/pool/model; `_project_child` deliberately makes worker_id null. | Placement owner may later supply a separately authorized, sanitized, exact Job/Attempt/observation-qualified companion. H24 accepts no arbitrary placement dictionary. Keep the existing `workspace_read_service.py` owner; do not add an endpoint here. |
| Per-child effects | Mission principal runtime cards expose effects; child cards do not. | Existing runtime/Mission owners must supply exact child effect evidence. UI can show principal effects separately now; never spread a principal effect across children. |
| Per-child return delivery/consumption | W3C receipt is mission-scoped and has no child result tuple. | Existing Dialogue/Wake/result owner must provide exact subject evidence if finer display is required. Acceptance already proves consumption for its exact subject. |
| Product rejection | Product acceptance defines ACCEPTED/UNAVAILABLE; review defines approve/reject. | Keep review rejection distinct. Any broader product disposition belongs to the existing acceptance owner, not this read model. |
| Original acceptance request key | Not present in Mission v3. | Existing host selects the original request and provides the complete v4 companion plus separately bound request_message_key. Never derive it from model text. |
| Raw authenticated Mission at Secretary consumer seam | `SecretaryAccessClient.read_mission` currently returns an incumbent summary. | The owner of `integrations/secretary_team_access/client.py` can adopt `project_team` at the already-authorized raw response boundary. Preserve fixed endpoints, independent clients and before/after grant checks. This packet edits none of those files. |
| UI adoption | Existing `app/mastermind_os/src/mission.ts` decodes v3 and v4; this packet adds no frontend code. | C33/UI owner keeps `decodeMissionv3`/`decodeMissionv4` unchanged, uses `suppress_unchanged_details=False` for freshly authorized full displays, renders cards and coverage additively in the existing Mission surface, and treats display labels as text. Any later command must use the existing host-bound action owner with fresh authorization. |

`docs/GROK_SECRETARY_TEAM_INTEGRATION.md` and issue #2082 remain the consumer
coordination references. H24 creates no new identity or coordination registry.

## Verification and parent handback

The fixture suite covers nested coordinators, pending/started children, review and
repair, missing parents, cycles, available-but-unconsumed results, rejection versus
acceptance, partial/omitted observations, stale parents, source/digest/Attempt
mismatches, bounded result overflow, quiet unchanged snapshots, concurrent detached
projections and two distinct signed fixture principals with independent revocation.
The multi-principal test uses the actual JWT verifier, sealed member authorizers,
Workspace service and Runtime fixtures; revocation before a read and after the owner
read both refuse disclosure. No live credential or account enrollment is exercised.

The initial source checkpoint passed **104 tests in 57.98s** with exit code 0.
The continuation adds 24 H24 cases and passes **128 tests in 38.66s**, exit code 0,
using this exact command on an isolated archive of published head
`b0c763c7e9622e48c7bab4d316d503354a41eabd` with only the two owned Python files replaced:

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.11 -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_h24_team_projection.py \
  tests/test_secretary_team_mission.py \
  tests/test_secretary_team_access.py \
  tests/test_workspace_mission_result_service.py \
  tests/test_product_acceptance_workspace_read.py --tb=short
```

The host's default Python 3.14 could not collect signed fixtures because PyJWT was
absent. The already-installed Python 3.11 has the required dependencies; no package
installation or environment change was performed. An early fixture omitted required
Fabric v2 child keys; another used noncanonical Wake receipt labels. Both fixtures
were repaired against the existing owner contracts before qualification.

The continuation first reproduced five failing regression cases against the
published implementation: actual missing/conflicting source subreceipts, unchanged
full display, explicit suppression text and pre-serialization input budgeting.
The finished suite has 77 H24 cases, including false CURRENT/SAME claims with null
receipts, foreign nullable receipts, exact UTF-8/escape/LF budgets and conservative
malformed enum/time handling. A fixture initially used the noncanonical label
CHANGED; it was corrected to the owner's CONFLICT value, and now asserts the actual
owner-produced state before exercising the projection.

The consumed Mission/result/acceptance contracts, Secretary modules and direct
owner-fixture dependencies were compared between the immutable base and protected
`28a894186eb56654ab4e833eb11a183d2eed46ae`; none of those paths changed. This bounded
compatibility check does not claim full current-master or installed qualification.

### Continuation publication and inherited CI

The original managed checkout was already cleanly released. Its installed launcher
returned `NOT_APPLIED` when asked to reopen the same operation because the retained
branch existed without its former checkout. The permitted exact-head GitHub source
route retains the original branch and ancestry. The isolated archive is only a test
fixture, with no Git branch, installation, service or credential enrollment.

PR #2120 merged after the initial checkpoint, and draft PR #2136 subsequently
compared against master. That broader comparison contains the foundation's old
ancestry; the authoritative H24 packet remains the three-path diff from the frozen
base. This continuation neither rewrites the branch nor edits integration files.

At the original H24 head, hosted Hermes harness run
[42208283181](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208283181)
and Hermes runtime run
[42208283053](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208283053)
passed. General CI run
[42208283030](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208283030)
failed inherited SessionBridge/Secretary-forwarder and Executive fixture checks;
Mastermind OS run
[42208283106](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42208283106)
failed the inherited ProjectConversations Open-button test. These failures are
outside the three H24-owned files. No repair, rerun, queue or release of those
lanes is performed by this packet, and no new-head hosted CI success is inferred
from the local source/fixture result.

Source handback includes immutable base, branch/head, exact three-file diff,
SHA-256 of `git diff --binary <base> <head> -- <three-owned-paths>`, test results,
this schema and the generated samples. The bounded H24-06 source outcome can be
complete while the wider Hermes/UI/always-on deployment remains unproven. Adoption
and production proof belong to the existing integration owners; this packet makes
no production-serving or acceptance claim for that wider program.
