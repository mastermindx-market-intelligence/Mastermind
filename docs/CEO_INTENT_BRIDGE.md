# CEO intent bridge — Executive OS Phase 1E-A

A bounded, typed, idempotent **write** path from the AI CEO seat into the existing
Executive OS execution plane.

Phase 1D-A gave the CEO seat a way to *read* the organization (`docs/CEO_BOOT_PACKET.md`).
This is the deliberately narrow inverse. One trusted local caller submits a typed
`mastermind.ceo_intent.v1` envelope over the **existing** private AF_UNIX control
service; the service validates it, the **existing** authority policy adjudicates it,
the **existing** `Runtime.jobs.create_job(...)` inserts one durable Job — and then it
stops.

    CEO intent → validate → authority adjudication → create_job() → QUEUED Job + event trail → STOP

Module: `control_plane/ceo_intent.py` · runtime hook: `control_plane/executive_runtime.py`
· service command: `control_plane/executive_service.py` · CLI: `scripts/ceo_intent.py` ·
tests: `tests/test_ceo_intent.py` (wired into the hermetic governance gate in
`.github/workflows/ci.yml`).

## The boundary

**Submission is never execution — but read that as "no *automatic* dispatch", not
"unexecutable".** Accepting an intent creates a QUEUED Job and nothing else. Nothing on
this path dispatches, claims, leases, starts a process, or touches a supervisor, and
`control_plane/ceo_intent.py` imports no module that can — `executive_supervisor`,
`executive_worker_broker`, and `codex_worker` are all absent, and a test asserts it by
AST. The receipt carries an always-`False` `dispatched` field so a caller can never read
acceptance as execution. The control service's `dispatch` and `requeue` commands
additionally accept **only** the fixed harmless Phase 1C-A proof job, so the *service*
will not run a CEO Job.

Do not over-read that last sentence. `scripts/executive_os_phase1b.py run-once` calls
`ExecutiveSupervisor.run_once`, which has **no** proof-job gate: it claims and executes
**any** queued job, and builds its launch spec from that job's own `worktree`,
`allowed_write_paths`, and `validation_commands`. So the containment this phase provides
is that nothing runs a CEO Job *automatically* — an operator invoking `run-once` can.

State the actual novelty plainly: **what is new here is the PRINCIPAL.** This is the
first path on which an LLM-authored JSON envelope determines a job's worktree and argv.
That is why the worktree is fenced to the host's configured workspace root and why
`argv[0]` is shape-bounded (both below), and why neither fence may be relaxed without
review. Phase 1F must not add automatic dispatch without revisiting both.

What this phase does **not** add: no new queue, no scheduler, no intent database, no
status store, no state machine, no table, no migration. Every durable fact it produces
already had a home — the Job row and its `JOB_CREATED` event. A second control plane
hung off CEO intent is precisely what the Mastermind `constraints.duplicate_control_planes`
prohibition names.

It also adds no listener: the only transport is the existing local Unix-domain socket,
peer-uid checked and byte-bounded. There is no TCP, no HTTP, no network path.

**Agent OS is never written.** `workstream` is a string pointer recorded for provenance.
Nothing here opens, resolves, or mutates the Macro `agentos/` store. Executive OS reads
Agent OS and writes only its own runtime.

**The CEO is provenance, not root.** `actor` is a recorded fact with no privilege attached
to its value. Requested authorities travel to `create_job` unchanged and are adjudicated
by `ExecutiveAuthorityPolicy`; this module never widens, substitutes, defaults, or
re-signs a grant. `actor: "ceo-sol"` requesting `MERGE` is refused exactly as any other
caller is.

## The envelope — `mastermind.ceo_intent.v1`

Key sets are **exact at every level**. An unknown key anywhere is a refusal, not a
warning.

| Field | Req. | Type | Bounds |
| --- | --- | --- | --- |
| `schema` | yes | str | must equal `mastermind.ceo_intent.v1` |
| `intent_id` | yes | str | `^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$` — becomes the durable command id |
| `actor` | yes | str | `^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$`; provenance only |
| `objective` | yes | str | non-empty, ≤ 4000 chars |
| `department` | yes | str | `^[a-z][a-z0-9._-]{1,63}$` |
| `priority` | yes | int | −100 … 100; `bool` is refused |
| `grounding` | yes | object | see below |
| `execution_contract` | yes | object | see below |
| `workstream` | no | str | `WS:<KEY>` — an Agent OS pointer, never a write target |

### `grounding`

| Field | Req. | Type | Bounds |
| --- | --- | --- | --- |
| `mastermind_sha` | yes | str | full 40-char **lowercase** hex |
| `macro_sha` | yes | str | full 40-char **lowercase** hex |
| `boot_packet_schema` | no | str | e.g. `mastermind.ceo_boot_packet.v1` |

A short, uppercase, or malformed SHA **fails closed** and is never silently replaced with
current HEAD. The grounding is the CEO's claim about what it read when it formed the
intent; repairing it would destroy the only fact that makes the intent auditable.

### `execution_contract`

Bounded reviewed fields only. Every name is a `create_job` parameter spelled exactly as
the runtime spells it — no synonyms, nothing translated at the call site.

| Field | Req. | Type | Bounds |
| --- | --- | --- | --- |
| `requested_authorities` | **yes** | list[str] | 1 … 8 names; sorted+deduplicated; adjudicated downstream |
| `allowed_write_paths` | no | list[str] | ≤ 32 entries, ≤ 256 chars each; **requires `WRITE_BRANCH`** |
| `validation_commands` | no | list[list[str]] | ≤ 4 argv lists, ≤ 12 items each, ≤ 256 chars per item; `argv[0]` fenced (below); **required by `RUN_TESTS`** |
| `authority_level` | no | str | `A0` … `A7` (default `A0`) |
| `branch` | no | str | ≤ 200 chars, no `..` |
| `worktree` | no | str | absolute path ≤ 1024 chars, no `..`, **must resolve under the configured workspace root** (below); **required by `WRITE_BRANCH`** |
| `attempt_limit` | no | int | 1 … 20 (default 10); `bool` is refused |
| `constraints` | no | object | only `required_capabilities`, `eligible_quota_classes`, `effort`, `cost_class`, `base_sha`; lists ≤ 16 entries |

Whole-envelope ceiling: **48 KiB** of canonical UTF-8. The per-field limits above count
*characters* while the wire carries *bytes*, so multibyte padding is caught by the byte
ceiling rather than by the character bounds. The bounds are sized so a maximal legal
envelope (~30 KB all-ASCII) fits inside the control service's 64 KiB
`DEFAULT_MAX_REQUEST_BYTES` with margin — a test constructs the maximal envelope and pins
its wire size, because declared bounds that cannot travel are a trap, not a contract: the
caller would get a generic `request_too_large` naming no field.

The three "requires" rows are the *policy's* rules, surfaced here so a caller can satisfy
them up front: `ExecutiveAuthorityPolicy.authorize` refuses declared write paths without
`WRITE_BRANCH`, refuses `WRITE_BRANCH` without an absolute worktree and ≥ 1 declared path,
and refuses `RUN_TESTS` without ≥ 1 declared argv command.

`provider` and `model` are deliberately **absent** from `constraints`: choosing the
provider or credential home is worker composition, reviewed on the host, never a field a
submitted intent may set.

### The workspace fence

`worktree` is **not** a free choice of any absolute path. `submit_intent` takes a
`workspace_root`, and a `worktree` must **resolve** to a path strictly under it or the
intent is refused; when no root is configured, an intent carrying `worktree` is refused
outright (which means no `WRITE_BRANCH` intent can be submitted at all on such a path).

The service passes `ServiceConfig.proof_workspace_root`. Despite the Phase 1C name, that
field **is** the host's jobs-workspace root — `/var/db/mastermind-executive/jobs/workspaces`
in `control.json` — not a proof-only directory. It keeps its name because renaming it
would be a control-config schema change.

Comparison is on **resolved** paths, deliberately. `authorize()` itself stores the
resolved worktree, so a submitted `/etc` is durably recorded as `/private/etc` on Darwin;
a raw-string prefix check would compare the wrong two things. Resolution is also what
collapses `..` and what follows a symlink out of the root, so neither escapes.

Without this fence a `WRITE_BRANCH` intent could be queued against the Macro checkout
(with `agentos/…` declared), `$HOME` (with `.ssh/authorized_keys`), `/etc` (with
`sudoers.d/…`), or this repository itself. No write happens at submission — but the
durable Job carries that scope, and `run-once` builds its launch spec from it.

### The `argv[0]` fence

An argv *list* is not by itself a safety property: `["bash","-c","curl … | sh"]` and
`["/usr/bin/env","python3","-c","…"]` are well-formed argv lists, and the supervisor runs
`job.validation_commands` verbatim. So `argv[0]` is additionally fenced — it must be a
bare program name (no `/` or `\`, matching `^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$`) and must
not be one of `sh, bash, zsh, dash, ksh, csh, tcsh, fish, env, command`.

**Honest scope**: this bounds the *shape* only. It removes caller-chosen executable paths
and the obvious interpreter escapes. It does **not** contain what the named program does —
`["python3","-c","<anything>"]` is still accepted — and the program still resolves through
the worker's own PATH at execution time, which this bridge neither sees nor controls. It
is not a sandbox and is not claimed to be one.

### Worked example

```json
{
  "schema": "mastermind.ceo_intent.v1",
  "intent_id": "CEO-2026-08-13-A",
  "actor": "ceo-sol",
  "objective": "Draft the Phase 1E-B design note and run the governance gate.",
  "department": "executive-infrastructure",
  "priority": 5,
  "workstream": "WS:EXECUTIVE_OS",
  "grounding": {
    "mastermind_sha": "cc24224df75cbc3c861d3d395e3aaa22d7d387f9",
    "macro_sha": "431fb2b846b693c13fb6654901f0747e79f82534",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
  },
  "execution_contract": {
    "requested_authorities": ["READ", "RUN_TESTS", "WRITE_BRANCH"],
    "allowed_write_paths": ["research/phase1e_b_design_note.md"],
    "validation_commands": [["python3", "-m", "pytest", "-q", "tests/test_ceo_intent.py"]],
    "authority_level": "A0",
    "branch": "codex/phase1e-b-note",
    "worktree": "/var/db/mastermind-executive/jobs/workspaces/ws-1e-b",
    "attempt_limit": 3
  }
}
```

## The receipt — `mastermind.ceo_intent_receipt.v1`

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | str | `mastermind.ceo_intent_receipt.v1` |
| `intent_id` | str | echo of the submitted id |
| `fingerprint` | str | sha256 over canonical JSON of the whole normalized envelope |
| `job_id` | str | the durable Job, `JOB-nnn` |
| `status` | str | the Job's own status — `QUEUED` |
| `accepted` | bool | always `true` (a receipt exists only on acceptance) |
| `duplicate` | bool | `true` when reconciled to an already-accepted intent |
| `dispatched` | bool | **always `false`** — acceptance is never execution |
| `authority` | object | `{requested, policy_sha256, authority_level}`, read off the **durable Job** |
| `grounding` | object | echoed from the intent |
| `created_at_ms` | int | creation time from the durable `JOB_CREATED` event |

`authority` is read back from the persisted Job, never echoed from the request — so the
receipt reports what the policy actually granted, not what the caller asked for.

## Service command

`submit-ceo-intent` — args exactly `{"intent": <envelope>}`, over the existing
`mastermind.executive_control/v1` protocol on the private AF_UNIX socket.

`ceo-intent-status` — args exactly `{"intent_id": "<id>"}`; rebuilds the receipt from the
durable `JOB_CREATED` event plus the Job row. No status store is introduced.

Errors use the service's existing vocabulary: `request_failed` with a bounded message.
`CeoIntentError` subclasses `ValueError` precisely so a refusal lands on that legible code
instead of the opaque `internal_error` path. `peer_denied`, `request_too_large`, and
`invalid_json` are unchanged and still apply.

## CLI

```bash
# Submit; exit 0 on acceptance (including an idempotent duplicate), 2 on refusal
python3 scripts/ceo_intent.py submit intent.json --socket /var/run/mastermind-executive/control.sock

# Same, printing the raw receipt
python3 scripts/ceo_intent.py submit intent.json --socket <path> --json

# Read back by intent id, or by JOB-nnn
python3 scripts/ceo_intent.py status CEO-2026-08-13-A --socket <path>
python3 scripts/ceo_intent.py status JOB-001 --socket <path>

# Resolve the socket from the reviewed control config instead
python3 scripts/ceo_intent.py submit intent.json --config /etc/mastermind-executive/control.json
```

Unlike `scripts/ceo_boot_packet.py`, which fails **open** because an orientation gap must
still hand the CEO a packet, this is a *mutating* client and fails **closed**: a refused
intent is a non-zero exit carrying the service's error code. The CLI never opens the
SQLite database and never executes a job; a test asserts both by source and AST scan.

## Idempotency

The mechanism is the **existing** `command_id TEXT NOT NULL UNIQUE` index on the events
table. A CEO intent derives its command id as `ceo-intent:<intent_id>`, so:

1. **Identical retry** → reconciles against the durable event. No second Job. Receipt is
   the original one with `duplicate: true`.
2. **Conflicting retry** (same `intent_id`, any changed field) → refused. The fingerprint
   covers the *whole* envelope, so a changed objective is a different intent. An accepted
   intent is never rewritten; submit a new `intent_id`.
3. **Concurrent duplicate** → settled atomically by SQLite. Both writers pass the
   pre-read and call `create_job`; the loser's event INSERT is rejected *inside* its
   transaction and its Job row rolls back with it. Exactly one Job survives and both
   callers receive the same `job_id`. No advisory lock, no dedupe table.

`RuntimeStore.transaction` converts the UNIQUE rejection into `StateConflict`, the same
class an authority denial arrives as — so the adapter re-reads the command id to tell the
two apart: present means a sibling won, absent means the refusal was real. The recovery
read re-compares fingerprints for exactly this reason: in a *conflicting* concurrent race
the loser must be refused, never handed the winner's receipt for a Job whose objective and
authorities it never submitted.

One consequence worth knowing before you debug it: a resubmission under an **already
accepted** `intent_id` is refused by the pre-read as a "different envelope" and therefore
never reaches the authority policy at all. That is correct — an accepted intent is never
rewritten — but it means a caller who changed an intent to add a forbidden authority
learns about the *fingerprint conflict*, and only discovers the authority denial after
retrying under a new `intent_id`.

The `ceo-intent:` prefix is a namespace, not proof of origin: an in-process writer with
control-plane access can append an event under it. So the read-back path re-verifies the
durable provenance (schema tag, matching `intent_id`, well-formed fingerprint) before it
will build a receipt, and `create_job` bounds the shape of any caller-supplied
`command_id`.

## What is refused, and why

* **Forbidden authorities** (`MERGE`, `DEPLOY`, `OPEN_PR`, `SERVICE_CONTROL`,
  `CAPITAL_EXECUTION`, …) — by `ExecutiveAuthorityPolicy`, not by a courtesy check here.
  Phase 1B grants exactly `READ`, `RESEARCH`, `WRITE_BRANCH`, `RUN_TESTS`.
* **Shell strings** — `validation_commands` must be argv lists. A bare string is refused
  by this validator with a message naming shell strings, and independently by the policy.
  Note the honest limit: `["bash", "-c", "…"]` *is* a well-formed argv list and is
  accepted. The guarantee is that a bare string never becomes a command line — not that
  argv can never name a shell.
* **Unknown fields** — at any level, including inside `grounding`, `execution_contract`,
  and `constraints`.
* **Forbidden concepts** — credentials/tokens/secrets, environment variables, caller-chosen
  executables, raw SQL, database or socket paths, worker uid/gid, service-control verbs,
  provider/credential-home selection. Exact key sets already reject these structurally; an
  explicit denylist exists so the *error names the concept* the caller reached for.
* **Out-of-root worktrees** — see the workspace fence above.
* **Caller-chosen executable paths and shell escapes in `argv[0]`** — see the `argv[0]`
  fence above.
* **Oversized envelopes** — over 48 KiB canonical UTF-8, including via multibyte padding
  that stays inside the character bounds.
* **Malformed grounding** — short, uppercase, or missing SHAs.
* **Un-encodable text** — an unpaired surrogate is a bounded, field-named refusal rather
  than a raw `UnicodeEncodeError`.
* **Type confusion** — `bool` where `int` is expected (`isinstance(True, int)` is `True`
  in Python, so this needs saying out loud).

## Phase 1F begins here

Deliberately absent from 1E-A itself: automatic dispatch of a CEO-created Job.
The G1 service composition can advance only a strict-v2 root carrying the
host-derived exact execution binding, and only when reviewed host configuration
arms `run-coo-cycle`/the bounded tick. G4 may route only that cycle's read-only
`plan` role through the exact
`operator.appserver.readonly.docs-mcp.native-helper.v1` profile. Its sole remote
extension is the exact allow-listed OpenAI Docs MCP grant, and its sole native
helper is a hidden-override, inherited-parent, one-child, depth-one, 60-second
read-only subordinate inside the same Attempt. Work, review and repair remain
sealed CLI Attempts; a native helper never satisfies independent review; and
checked-in configuration keeps both the COO cycle and Operator Harness unarmed.
Jobs select only an already-ready dedicated provider realm and can never trigger
login or OAuth enrollment. V1 remains undispatchable. General scheduling,
new prioritization or admission policy over queued intents; multi-actor authorization or delegation;
intent amendment, withdrawal, or supersession; a remote or authenticated non-local
transport; and any write back into Agent OS to close the loop. Each of those is an
authority expansion and needs its own review — none of them arrive by adding a field
to this envelope.
