# Hermes executive-team context and adviser budget

Status: callable source implementation and offline native-API qualification. Not an installed role rollout, worker admission, live spending gate, or completed autonomous organization.

Parent: Mastermind #2159, design comment6699721779; execution comment6700014545. Operation: `hermes-executive-team-implementation-20261107-c3`. Protected base: `ad6275a9c4d237bce75e52d0d6a8f41264b4ded5`.

## What the consumer does

`integrations.hermes_leadership` adds a role-specific briefing to the existing authenticated Mission v3 reader. Meta-CEO, Secretary, Delivery, Engineering, Reliability/Capacity/FinOps, Product, Intelligence, Assurance and the external Grok adviser have explicit objectives, wake conditions, evidence requirements and limits. These charters use the existing responsibility syntax. They are guidance, not identities, tool grants or model selections.

The installed host retains one logical Secretary and can resolve several separately authorized native session contexts. A native call cannot supply a different role, project, provider, account, endpoint or credential. No conversation transcript or company-state cache is created.

By default, `LeadershipReader` performs exactly one `SecretaryAccessClient.read_mission()` through its fixed authenticated Workspace client. The existing producer and summary validator own the source contract. The reader preserves source identity, coverage, child/result references, execution and acceptance as distinct facts. It requests full details on every read, including repeated unchanged reads, without asking a reasoning model to poll.

A wrong native session, denied access, changed host binding, revoked grant, stale/future source, invalid clock, malformed source or excessive output yields an explicit refusal/unavailability with no remembered mission attached. A grant revoked while the read is in flight discards its result. Cancellation propagates. Error messages are value-free.

## Host composition

This is an importable adapter, not an automatically self-enrolling plugin. Use the current installed native session/role owner to supply real bindings. A role string, environment token or model-created object is not authentication.

```python
from integrations.hermes_leadership import LeadershipReader
from integrations.hermes_leadership.native import (
    HostLeadershipBinding, register_native_tool,
)

# Construction belongs inside the existing host's authorized native session setup.
# These values/functions are supplied by that owner, not discovered by this package.
reader = LeadershipReader(
    charter_key=host_selected_charter,
    session_id=actual_native_session_id,
    access=existing_authenticated_secretary_access_client,
    currentness_guard=existing_session_role_grant_current,
    include_project_continuity=False,  # Host may explicitly opt into the same Workspace plan route.
)
# The host retains reader in its EXISTING native-session context. It does not
# create another session dictionary or credential owner for this feature.

binding = HostLeadershipBinding(
    profile_id=actual_native_profile_id,
    resolve_reader=existing_native_session_context_reader,
    currentness_guard=existing_native_profile_current,
)
registration = register_native_tool(
    actual_plugin_context, binding, profile_id=actual_native_profile_id,
)
# Retain the returned native lease in the incumbent host/plugin lifecycle.
# On unload: registration.dispose(). Never broadly unregister unrelated tools.
```

The illustrative `existing_*` names above describe required host-supplied bindings, not newly implemented global APIs. `existing_native_session_context_reader(session_id)` must return the same retained `LeadershipReader` while that session is current. Replacement during a read invalidates the returned result. Each reader's currentness guard must cover role/workstream authority and the authentication generation, including in-place credential changes. Client-object identity alone cannot prove those facts.

For a single exact native session, `register_native_tool` also accepts a `LeadershipReader` directly. The profile-level resolver is the preferred composition for multiple tasks. It delegates session lookup to the current owner and stores no session registry itself.

The only registered tool is `mmx_leadership_brief` in toolset `mmx_leadership`, with closed empty arguments. Actual `session_id`/`task_id` come from Hermes invocation metadata. Use the host's normal tool allowlist and release composition. Do not enable every upstream tool or install a separate listener to expose it.

Native registration uses the current PluginContext, scoped registry, replacement coordinator and returned lease. It does not override a collision. Failed readback disposes only the captured lease. An exception after registration may have taken effect: preserve the original context, scope and tool name, inspect that original owner, and never blindly register again. Disposed or replaced registrations cannot continue serving a retained handler.

## What continuity is and is not supplied

The existing Mission v3 summary does not supply an authoritative original objective, DONE_WHEN, next plan action or unresolved-effect list. The default Mission-only briefing explicitly reports those four missing fields and recommends consulting the canonical plan. It never invents a complete recovery packet from a mission title.

The existing Agent OS/native memory/continuation lane must provide those facts through its current source-bound contract. The reader does not duplicate that lane or claim that read-only context has implemented dispatch, result consumption, wake, project continuation or product acceptance. A result reference is not proof that a parent consumed it.

This first consumer therefore makes specialist context useful and safely callable while leaving exact missing integration visible. No existing native/OMH memory provider is replaced. No active #2134/H24/OMH/Capacity source is changed.

### Optional authored-plan continuity on the same reader

The host may set `include_project_continuity=True`. This adds exactly one
`SecretaryAccessClient.read_project_plan()` after a successful, current Mission
read, through the same already-authenticated Workspace client. The fixed GET
`/workspace/project-plan/current` receives only the host-selected `work_ref`.
The native tool still accepts empty arguments; the model cannot toggle the option
or choose another project. No second tool, credential, scope registry or cache is
introduced. Default-off behavior and one-Mission-read callers are unchanged.

The existing canonical v1/v2 validator qualifies the response. The brief includes
bounded authored objective/next action, title/status/owner, canonical source
commit/path/hash, adoption summary and explicit field coverage. An oversized field
is **omitted**, never silently truncated. Raw adoption bodies, proposals,
rationales, comparisons, wave text and version history are not exported. Wave
omission counts remain explicit. `done_when` and `unresolved_effects` remain
missing; no text is interpreted into either field. The original
`CONSULT_CANONICAL_PLAN` recommendation and all no-authority boundaries survive.

`AUTHORED_WORKSTREAM_RECORD` is not necessarily the adopted plan:
`matches_authored_record=false` stays visible when supplied by the v2 owner.
The workstream record is not a proven root-job binding. Mission and plan are
`SEPARATE_READS_NOT_ATOMIC`; the plan contract has no source freshness timestamp.
`read_completed_at` is only the local observation time, and source freshness is
explicitly `NOT_REPORTED_BY_OWNER`.

The guard is checked immediately before and after the extra await. Original
Mission freshness is checked again after the plan and optional adviser meter.
An authorization refusal (including an empty, malformed, oversized or interrupted
401/403 body) discards **all** earlier Mission/organization facts. Other plan
failures retain only a still-current Mission with explicit plan unavailability.
The 128 KiB plan wire cap and 24 KiB whole-brief cap are distinct; optional content
can be omitted if necessary to preserve the existing bounded Mission brief.

Focused regression and real signed-HTTP/native-handler path:
`tests/test_hermes_project_continuity.py`. The HTTP and native handlers are real;
owner records and credentials are synthetic. No installed role or browser read
is implied. Source master plan:
`docs/superpowers/plans/2026-11-06-chatgpt-session-observability.md`, O5A–O5D.

## Company organization and goal lineage (Paperclip-inspired)

The original `mmx_leadership_brief` now includes a bounded
`organization_context` (`mastermind.hermes_organization_context.v1`) on
**AVAILABLE** source only. It is part of the same one authenticated Mission v3
read and the same native host-bound session/role guard; it does not register a
second tool or call another backend.

- The nine existing charter keys form one explicit *advisory reporting tree*
  rooted in the human Chairman. Chief of Staff, Engineering, Reliability and
  other lead/reporting relationships are editorial guidance, not proof that
  any particular native role is enrolled, present, delegated or authorized.
  `live_roster_state=NOT_OBSERVED` and each seat is `NOT_OBSERVED`.
- The caller's current, already-authorized workstream and Executive root are
  shown as a read-only goal path. Company strategic goals remain
  `NOT_PROJECTED` until the original strategic owner supplies them.
  No employee/job assignment is inferred merely because a role reads a
  mission.
- Result reference count, review verdict and original acceptance state are
  separate observations. `original_parent_consumption=NOT_ESTABLISHED` and
  `product_acceptance=NOT_ESTABLISHED` are deliberately not manufactured from result
  availability or green CI. All original effect and permission holds survive.
- Source schema, selected workstream/root identity, freshness, one-mission
  scope and an 8 KiB organization budget are checked. A failed qualification
  yields the same value-free overall `UNAVAILABLE`/refusal behavior, without
  a cached org chart or privileged cross-role mission lookup.

This closes the initial *source* reporting/goal-path consumer, not the
full organizational product. The authenticated Mastermind OS view and genuine
Chairman assignment → admitted Fabric work → Hermes parent consumption remain
downstream of the active H24/#2134/#2166 owners and their installed evidence.
The editorial implementation plan is
`docs/superpowers/plans/2026-11-07-paperclip-company-organization-bridge.md`.
Paperclip's MIT code and separate runner/database were **not** imported.

## Grok adviser policy

The external Bot role is for a bounded strategic challenge or useful external investigation, not routine Secretary traffic, hourly polling or every-PR review. Its actual model is not promised by this adapter.

An optional `adviser_budget_reader` can be supplied when constructing a `grok_adviser` reader. The async host callback returns exactly `{"snapshot": ..., "request": ...}` from the existing capacity/meter owner. It accepts no model arguments. Without it, the briefing remains readable but budget status is `HOLD / meter_unbound`. Errors produce a value-free hold. Revocation during the meter read discards the entire briefing.

The pure `evaluate_adviser_budget(snapshot, request, now=...)` uses one actual seven-day provider meter, in integer basis points (10000 = full allowance): daily work 7000; weekly deep review 1000; urgent reserve 2000. Daily work is paced across the remaining reset-relative days and capped at 1000 basis points per day. Usage and reservations are separate; unclassified external usage can reduce the available allowance but cannot enlarge a bucket. Product labels or API keys cannot be added as independent quotas.

Required snapshot keys:

```text
schema = mastermind.hermes_adviser_meter.v1
meter_id, window_id
window_start, window_end, observed_at    (timezone-aware ISO timestamps)
remaining_bps                          (before reservations)
spent_daily_bps, spent_weekly_bps, spent_urgent_bps
spent_today_daily_bps                   (reset-relative current day)
reserved_daily_bps, reserved_weekly_bps, reserved_urgent_bps
```

Request keys are exactly `meter_id`, `window_id`, `purpose` (`daily`, `weekly`, `urgent`), and positive integer `estimate_bps`. Extra fields, booleans as counts, unknown quota, inconsistent accounting, wrong meter/window, non-seven-day windows, observations older than 300 seconds, future observations, or stale daily counters hold. Time is supplied by the trusted caller; the policy does not read a clock or provider.

Every result is advisory: `admitted=false`, `reservation_created=false`, `capacity_recheck_required=true`. **An eligible preflight is not an atomic reservation.** The incumbent Capacity owner must revalidate the actual meter, account entitlement, existing task/effect identity, concurrent reservations and actual task cost before dispatch. It must also enforce per-obligation deduplication and the intended daily/weekly request frequency; this stateless arithmetic is not a scheduler or event ledger. Estimates cannot guarantee final provider usage. Preserve margin and post-task meter reconciliation.

The 70/10/20 split is a selected product policy, not a claim about grandfathered billing terms or three independent pools. No account migration, cancellation, purchase, plan conversion or spending-cap change occurs here.

## Runnable offline consumer

```bash
python3 -m integrations.hermes_leadership charter secretary
python3 -m integrations.hermes_leadership charter engineering
python3 -m integrations.hermes_leadership budget < integrations/hermes_leadership/examples/budget.json
```

The checked-in example is synthetic and exercises no real account. Budget stdin is an exact JSON object with `snapshot`, `request`, and `now`; it is bounded to 65536 bytes and rejects duplicate keys, nonfinite numbers, excessive nesting and extra envelope fields. The CLI only emits policy output. It does not fetch a meter or connect to a live role. Invalid input/arguments produce short value-free errors without echoing secrets.

## Verification and rollout

Run the new tests and incumbent contracts:

```bash
HERMES_LEADERSHIP_UPSTREAM=/path/to/qualified/hermes-source \
python3 -m pytest -q -o addopts='' \
  tests/test_hermes_leadership.py tests/test_hermes_leadership_budget.py \
  tests/test_hermes_leadership_native.py tests/test_hermes_leadership_cli.py \
  tests/test_executive_responsibility.py tests/test_secretary_team_mission.py \
  tests/test_secretary_team_access.py --tb=short
```

Native-interface tests use the actual installed Hermes source with temporary profile homes and a fixture-backed Workspace transport, not the live bots or provider keys. An omitted upstream source skips those explicitly; it never counts as live qualification. Tests prove real registry API compatibility, scoped leases, multiple native sessions, denial/revocation, collision and ambiguous-registration behavior. They do not prove signed production authorization, live role installation, provider serving, autonomous project completion or seven-day quota endurance.

Release the exact published source through current repository controls. Then compose it through the incumbent live native role owner using its authentic session/Workspace binding and profile-specific allowlist. Prove an original live conversation read, wrong-role denial, revoke-during-read, simultaneous isolated sessions, and exact lease rollback before claiming activation. A missing host binding remains missing; do not invent a credential or broaden a role to manufacture a canary.

Broader acceptance remains the approved R2/H1-H8/native/Web and natural-time programme: original request to accepted result, recovery without duplicate effects, real result consumption/wake, memory correction, admitted routing, measured Grok usage across seven days and qualified Kimi comparison. The two currently working bots and their active routing integration are preserved.
