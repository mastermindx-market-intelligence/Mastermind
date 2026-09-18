# Fabric job view — the truthful view of one Executive Runtime root

`control_plane/fabric_job_view.py` (+ CLI `scripts/fabric_job_view.py`) renders
`mastermind.fabric_job_view.v1`: one Executive Runtime **root** — the parent Job,
its child Jobs and Attempts, review, repair, and the accepted result — using only
existing Executive read paths, and rendering **explicit unknowns** wherever the
system has no answer yet.

Status: **BUILT_NOT_PROVEN**. This is a read-only projector. It proves nothing
about a host: it is not an install, not an arm, and has no production effect.
Nothing in it opens a socket, starts an MCP server, calls `launchctl`, or writes
any state.

## What it is for

Today the honest rendering of every production root is an **empty tree with named
reasons**: production CEO-intent submission is fenced closed (`ceo_submit_armed`
is `false` in the shipped control template) and the return path is disarmed, so
no Chairman-authenticated admitted job can exist yet. The value of this view is
therefore mostly in *how it renders nothing*: an absent runtime must read as a
typed refusal, never as "no work".


## Web-CEO Executive MCP access (`executive_fabric`)

The protected BSC-E1 / EXEC-MCP-A generation remains the exact five-tool
`1.0.0` contract and does **not** advertise `executive_fabric`.

The separately versioned static profile `web_ceo_v1` uses server version
`1.1.0` and adds one read-only tool named `executive_fabric`:

```json
{"view":"roots","limit":50}
{"view":"root","root_job_id":"JOB-1"}
```

Its schema digest is
`17e052ed734c2c4606094c49b0e9c057382a193fc181d595fc084da10809a5cd`.
Profile selection is host composition, never caller input. The profile reuses
the same authenticated App, CeoIngress, Executive Runtime and result-envelope
owners; it does not create a second MCP lifecycle or control plane.

`view=roots` calls the existing bounded `list_roots` projection; `view=root`
calls the existing `read_fabric_view` projection. The gateway does not recreate
job joins, review/result logic, or Runtime access. It replaces configured host
runtime coordinates with the stable non-secret runtime label before the document
crosses the MCP boundary. Projector failures return one typed, path-safe
`backend_unavailable` envelope.

This is **visibility only**. It does not dispatch, claim, spawn, cancel,
terminate, wake, retry, reassign, resume, merge, deploy, read credentials, or
call a provider. Installed read transport is explicitly versioned: legacy App
bindings default to `mastermind.executive_ceo_ingress_app_read.v1`, while
`web_ceo_v1` requires the host-bound v2 reader profile. See
`docs/EXECUTIVE_WEB_CEO_FABRIC_READ_AMENDMENT.md`.

The source remains `BUILT_NOT_PROVEN` for production until the separately
owned installed-read hardening and an explicitly activated Web-CEO app
generation prove current-runtime enumeration and one-root detail.

## Usage

```
python3 scripts/fabric_job_view.py --runtime-root <abs> --root-job-id <id> \
    [--control-config <abs>] [--json]

python3 scripts/fabric_job_view.py --list-roots --runtime-root <abs> [--limit N] [--json]

python3 scripts/fabric_job_view.py --describe [--json]
```

* `--list-roots` is a bounded enumerator (default 50) so an operator can find a
  root id: a *root* is a Job whose `root_job_id` equals its own `job_id`.
* `--describe` prints the capability object with `installed: false` and opens no
  runtime at all.
* Human mode prints schema, `generated_at`, counts, the `degraded` list (or
  `degraded: none`), then `capability: <state>`.

Library entry points: `read_fabric_view(runtime_root, root_job_id, *,
control_config_path=None)`, the pure `compose_fabric_view(...)`, `list_roots(...)`,
and `describe_capability()`.

## Document shape (closed key set, asserted)

```
{schema, generated_at, runtime, armed, root, children, unjoined_job_count,
 unjoined_job_ids, degraded, missingness, capability}
```

`runtime` = `{root, db_present, identity}`; `armed` = the five arm bits plus
`source` (`"control.json"` or `"absent"`); `capability` = the house A16 shape
`{state, installed, version, detail}` with `state` in `PROVEN | PARTIAL |
UNSUPPORTED | NOT_INSTALLED`.

Each job card carries the same five keys the EXEC-MCP `executive_job` tool
already publishes (`job_id`, `status`, `attempts`, `attempt_count`,
`attempt_limit`) plus the lineage the fabric needs (`parent_job_id`,
`root_job_id`, `depth`, `orchestration_role`, `plan_step_id`,
`current_attempt_id`, `latest_attempt`, `review`, `repair`, `result`), so the two
surfaces cannot disagree about one job. An attempt card never exposes the lease
token.

## The unknowns it must render, and why

| situation | rendered as |
|---|---|
| runtime database absent | whole call refuses: `degraded` names `executive_runtime: database missing at <path>`, `runtime.db_present: false`, `capability.state: NOT_INSTALLED`, `root: null`, `children: []` — no directory, file, or journal is created |
| runtime unreadable | `degraded: ["jobs unreadable: <first line>"]`, `capability.state: UNSUPPORTED` |
| Job admitted but never claimed | `attempts: []`, `latest_attempt: null`, `current_attempt_id: null`, `result.state: NOT_STARTED` — never `RUNNING`, never `FAILED` |
| review not performed yet | `review.verdict: "NOT_YET"` plus one `MISSING_PRODUCER` fact on `review.verdict` |
| `review_required` with no review job | `review.verdict: "NOT_YET"` plus one `MISSING_PRODUCER` fact on `review.reviews_job_id` |
| job with no CEO-intent workstream provenance | counted in `unjoined_job_count`, listed in `unjoined_job_ids` (first 50), and named once in `degraded` — never silently dropped |
| `control.json` absent or unreadable | every `armed.*` value `null`, `armed.source: "absent"`, one `degraded` entry — never `false` |
| nothing armed | one `degraded` entry naming `ceo_submit_armed` |
| COMPLETED job with no result payload | `result.state: ACCEPTED`, `summary: null`, plus a `DEGRADED` fact on `result.summary` |
| consultation / Wake return state | not rendered in v1: one `EXCLUDED` fact on `return_path` (the path is disarmed; the three-way delivered/consumed/never-delivered mapping is COULD-NOT-DETERMINE) |

### `children` vs `unjoined_job_count`

`children` holds the child Jobs the view could **join** to a CEO-intent
workstream. Every other job in scope is counted in `unjoined_job_count`, its id
(first 50) is listed in `unjoined_job_ids`, and the gap is named once in
`degraded`. The two sets are disjoint and
`len(children) + unjoined_job_count` is the size of the scope, so the rendered
tree is never a silent subset. This is deliberate: the Control Room's runtime
projection `continue`s past provenance-less jobs, which makes "no jobs exist"
and "jobs exist but none join" indistinguishable.

## Implementation notes

* The compositor is pure (`chairman_control_room.py:11`'s own split); the gather
  layer does all I/O. `read_fabric_view` opens the runtime with
  `Runtime.at(root, create=False)`, ALWAYS: a bare `Runtime.at(root)` defaults to
  `create=True` and would manufacture an empty database and then report a quiet,
  job-free company. The constructor is what fails closed — it raises
  `PersistenceError` (a `RuntimeProofError`) for an absent **or** unopenable
  store — and the database-file check that follows only *chooses the message*,
  telling a genuinely absent runtime (`executive_runtime: database missing at
  <path>`) apart from a present-but-unreadable one (`jobs unreadable: <detail>`,
  with `runtime.db_present: true` and `capability.state: UNSUPPORTED`). The
  check never gates the call, so the fail-closed path cannot be bypassed.
* `runtime.jobs.list_jobs()` takes no arguments and is a full table scan; the
  root filter happens in Python.
* The review verdict lives on the **review Job's** payload. `JobPayload.to_dict`
  omits an empty `verdict` key entirely, so an undecided review has no
  `verdict` key at all: both absent and `""` render `NOT_YET`.
* CEO-intent provenance is read through
  `control_plane.executive_inbox.ceo_intent_provenance` (a pure composition of
  two allowed reads); `Job` has no `workstream` attribute.

## Tests

`tests/test_fabric_job_view.py` carries D1–D6 of the frozen spec: absent-runtime
refusal, never-claimed ≠ running, undecided review ≠ verdict, unjoined jobs are
counted, capability state is derived, and the read surfaces are structurally
read-only (AST). Each row has a named mutant that turns it red, and each mutant
was restored byte-identically.

No fixture in those tests is evidence about the fabric. Constructed fixtures are
never real binding evidence: a green suite proves the *rendering contract*, never
the runtime.
