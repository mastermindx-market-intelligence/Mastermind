# Attended Agent OS context on Codex startup and compaction

This adapter connects the existing Agent OS context compiler to Codex's `SessionStart` input. It restores recorded project direction for an explicitly selected workstream and workspace. It does not create a new memory store, select a company priority, create a runtime assignment, or recover live worker custody.

## Existing owner and observable result

`integrations/session_bridge/agentos_session_start.py` calls `ops.fabric_launch.agentos.read_context()` exactly once for a matching event. That owner invokes Macro's `scripts/agentos.py compile-context` with a 25-second runtime bound, a 128-KiB output bound, exact-workstream validation, and process-group settlement. The adapter preserves the owner's complete `context_bundle.v1` bytes, including the objective, constraints, accepted work, latest handoff, citations, exclusions, omissions and degradation that the owner actually included. It neither synthesizes missing records nor rewrites their priority.

`read_context()` inherits the existing process-local `MACRO_MASTERMIND_REPO` setting into the compiler process. For the attended canary, set it to the intended reviewed Mastermind Git checkout, then verify the checkout revision and regular `config/strategic_state.yml` before reading. Sibling autodiscovery can stop at a non-Git directory and omit P0; path existence alone is not owner provenance.

The read observation binds the returned bundle hash. `source_script_sha256` identifies the compiler entrypoint; it does not attest the entire imported compiler closure. Repository and generation fields are source observations, not evidence that every runtime fact is current. The adapter labels current runtime ownership, original-parent custody and outstanding effects `UNOBSERVED`. It creates no SessionTruth, Runtime PREPARE, supplied-input receipt, ACK, START or acceptance fact.

ContextResolver remains the cross-owner reference-selection seam for authentic SessionTruth inputs. This exact Agent OS expansion reuses the existing owner directly; it does not fabricate a SessionTruth receipt to wrap a single read. Full continuation that depends on Executive evidence must still acquire that evidence through its current owner.

## Scope and event behavior

The reviewed invocation must explicitly name `--workstream WS:<KEY>` and `--workspace-root /ABSOLUTE/INTENDED/WORKSPACE`. The native event's absolute `cwd` must resolve to that exact directory. A sibling or child directory receives no injection and does not invoke the compiler. The adapter checks directory equality, syntax-validates the observed native session ID and reports it; it does not compare that ID with an expected session. Two sessions using the same configured workspace receive the same selected workstream context. These observations confer no permission and do not transfer an old parent's workers to a fork or fresh session. Current assignment and governing instructions take precedence over recorded next actions.

Supported sources are `startup`, `resume`, `clear`, `compact` and `fork`. Each event rereads the owner; there is no adapter cache or new mapping registry. Transcript paths, provider credentials, subscription contents and worker results are not read. The adapter does not call a model or dispatch work.

A failed read produces a short, sanitized context-unavailable notice. Unknown or mismatched workstreams never produce substitute project content. Uncertain reads are not retried. Invalid event/configuration input produces `{}` plus a bounded error code on stderr. Orientation gaps do not become an execution gate; normal results exit 0 and never return a blocking hook decision.

## Preserve the complete bundle at the native boundary

Codex ordinarily spills large hook context into a saved file and a model-visible preview. That preview cannot serve as proof that mandatory project context reached the immediate continuation. This adapter therefore enforces a **32-KiB limit on the entire additional-context string**. It emits all owner bytes or an explicit `AGENTOS_CONTEXT_DELIVERY_TOO_LARGE` notice, never a clipped bundle. The requested compiler budget defaults to 4,000 estimated tokens; mandatory owner content can exceed that request, so the final byte limit remains necessary.

For this bounded handler only, the reviewed definition uses `additionalContextLimit: 0` to preserve its complete output. Keep the handler synchronous and give the incumbent reader enough time to settle. Example definition, with every placeholder replaced during normal native review:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "^(startup|resume|clear|compact|fork)$",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -B '/ABSOLUTE/REVIEWED/MASTERMIND/integrations/session_bridge/agentos_session_start.py' --workspace-root '/ABSOLUTE/INTENDED/WORKSPACE' --workstream WS:EXISTING-WORKSTREAM --macro-root '/ABSOLUTE/QUALIFIED/MACRO' --budget 4000",
            "timeout": 35,
            "async": false,
            "additionalContextLimit": 0
          }
        ]
      }
    ]
  }
}
```

This is a review template, not an installer. Preserve other definitions and existing source custody. Pin the actual reviewed source and dependencies through the current installation owner. Do not write a `trusted_hash`, replace a trusted immutable helper in place, change security settings, or claim native loading from a manual invocation. A changed non-managed Codex definition requires the actual native review/trust flow. No live settings are modified by this source change.

The protocol basis is the official [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks), checked 2026-10-21: `SessionStart` accepts `hookSpecificOutput.additionalContext`; matching `compact` hooks run before the next root-model request, including automatic mid-turn compaction. This supports the proposed ingress contract; it is not installed-version proof for a particular seat.

Installed protocol evidence (2026-10-21): ordinary standalone generation from `codex-cli 0.163.0` exposes `SessionStart`; the generated handler contract says `additionalContextLimit: 0` disables spilling. The inspected artifacts were `v2/ConfiguredHookHandler.ts` (SHA-256 `b52a77fa08ea3695ad128f5d184c7b464bbf4dd66e93850434c0b8e3f02322e1`) and `v2/ConfigRequirementsReadResponse.json` (SHA-256 `dd95f94ca4f89b87f63151c570c1b16a771cda9bb17445d6650a633eb55a9f05`). These artifacts provide protocol evidence only; native loading, trust, context delivery and model use require the separate attended check below.

## Acceptance evidence

Source tests must prove exact-workspace exclusion, exact-workstream selection, retention of all owner bytes and accounting, fresh reads on repeated compaction, output caps, sanitized errors, no uncertain retry, and absence of fabricated execution receipts. The existing owner/process suites cover the subprocess boundary and settlement.

A manual invocation using a qualified Macro checkout proves that the source wrapper and compiler compose and records the actual source/bundle observations. It does not prove that Codex trusted, loaded or delivered the hook, or that a model used the recovered state.

Native adoption requires a controlled attended Astra session at the actual intended entrypoint:

1. Record an objective, mandatory constraint, accepted outcome and next action in an existing workstream through its normal owner.
2. Review and trust the exact scoped definition through Codex's supported flow. Observe startup delivery in the intended session and no delivery into a sibling workspace.
3. Change a relevant recorded decision, also change an unrelated workstream, and trigger supported compaction or resume.
4. Verify that the same intended session identifies the current goal and changed decision, preserves the mandatory constraint, avoids redoing accepted work, ignores the unrelated change, and continues with the next justified substantive action without another user instruction to continue.
5. Separately reconcile real worker returns, original-parent custody and any uncertain effects through their existing owners. A new session must not claim an old parent's child by inference.

An end-to-end long-horizon canary additionally needs real delegation, result retention, review, acceptance and continued phase execution. This orientation adapter does not provide idle wake, guarantee automatic post-crash execution, or implement the missing semantic-continuation source builder.

## Owner boundary inside an already active turn (P7.T5)

`project_owner_continuation.py` adds a read-only, attended companion to this
adapter. It does not wait for a new SessionStart. The original assigned owner
can invoke the reviewed source directly from its current project workspace:

```sh
python3 -B /ABSOLUTE/REVIEWED/MASTERMIND/integrations/session_bridge/project_owner_continuation.py \
  --workspace-root /ABSOLUTE/PROJECT/WORKSPACE \
  --charter-root /ABSOLUTE/EXISTING/CHARTER \
  --macro-root /ABSOLUTE/QUALIFIED/MACRO \
  --workstream WS:EXISTING-WORKSTREAM \
  --owner ORIGINAL-OWNER-ROLE --owner-session ORIGINAL-NATIVE-SESSION \
  --budget 4000
```

The process's actual `cwd` and existing `CODEX_THREAD_ID` must match the explicit
focus. These observations do not authenticate a caller, grant assignment, bind a
Runtime Job, or establish custody. The command supplies context to the already
running owner; it cannot start, resume, block, or force a model turn. It does not
invoke Stop or create a subscriber, watcher, queue, registry, or persistent cursor.
No command is derived from a title, `next_action`, note, handoff, or other prose.

The companion uses the exact frozen source copy at
`mmtask_restore/payload/mmtask`, SHA-256
`711ba4f46c80e518d99167877738db9e92182b78bf7b4e3052bcfee79316d54a`.
It calls that owner's actual `next_tasks` and `recovery_scope_issues`, then applies
narrower focus/freshness filters. It is not a replacement task selector. The
source restoration package and its offline/private-HOME qualification are
explained in [its README](mmtask_restore/README.md). The installed helper is never
loaded or changed by this companion.

A missing, legacy, empty, or unbound task buffer supplies passive canonical
recovery context. No task is manufactured. The owner must use the incumbent
explicit rebind/import procedure only after verifying the real workstream,
latest handoff, original versioned plan, source custody and effects. The command
never writes the charter or interprets a recovery suggestion as permission.
An artifact listed under `omitted_due_to_budget` has **not** been read; acquire
the original plan at its recorded source before pickup.

A candidate is at most one existing READY row in the exact workstream owned by
the focused role, admitted by the incumbent selector, mapped to one active
imported wave, without recorded reason/supersession or an already-started task
for that owner. Duplicate or multiple candidates are never truncated into a
singleton. Task and buffer timestamps must be timezone-qualified, nonfuture,
and no older than the configured observational limit (default one hour).
The buffer's imported source SHA and workstream path/status must agree with the
compiler's observed source SHA and structured active workstream record. A
freshly edited READY row cannot bypass an old/unqualified import or closed
canonical record. A new unrelated canonical commit can conservatively require
an ordinary import; the companion never performs it.

That agreement establishes consistency, **not** latest protected-master
freshness, authenticity, effect eligibility or release. Source, current
commission, permissions, outstanding effects, exact holds, live writers and
actual original-parent custody remain action-time checks through their existing
owners. `action_recommendation` is always false and `effect_eligibility` is
`UNOBSERVED`. A candidate must not override an explicit stop or an unobserved
hold. A historical handoff's blocked label is likewise not a blanket authority
for every independent project task. Inspect the exact scope of each real hold.

After current eligibility is independently established, the already-active
owner uses normal `mmtask show`/`start`, performs its authorized bounded action,
consumes the actual result and records the required acceptance through that same
owner. Started, accepted and superseded rows cease to be new candidates. Stable
candidate identity uses workstream, task/evidence generation and the canonical
`source_records_digest`; raw bundle hashes, generated timestamps and incidental
checkout SHA changes are not new observations of progress. Repeating an unchanged
read without uptake returns the same inert identity, without prompts or effects.

The new companion delivers the complete **parsed** owner bundle, including all
omission/degradation fields; its raw acquisition observation still binds the
original compiler bytes. No owner fields are dropped to make the delivery bound
pass. The owner bound derives from the upstream canonical bundle maximum
(`MAX_BUNDLE_BYTES` in `ops/fabric_launch/agentos.py`) plus a fixed metadata
allowance; both entrypoints check the bounded non-bundle metadata and the final
serialized context including owner metadata; oversized output becomes a small
unavailable result, never a preview presented as complete. Legacy adapter calls
still preserve their original verbatim-bundle format and behavior.

For an optional actual original-owner **resume** event, the existing adapter
accepts `--charter-root`, `--owner`, and `--owner-session` together. Configure only
a separately reviewed synchronous `resume` handler with the normal 35-second
bound and `additionalContextLimit: 0`. Other events with that owner mode return
no projection. A new/forked session cannot acquire the old focus by matching
cwd. This is a definition interface, not an installed hook or native-loading
proof: no definition, trusted hash, global Fabric Stop helper or local helper is
changed here. In-session boundaries without a new resume use the attended
command above; no SessionStart event is forged.

Portable tests use explicit inert inputs and the committed frozen helper, not
M2 HOME paths or `vendor/macro_src/scripts`. A separate recorded M2 rehearsal
uses the actual compiler, reads the omitted original plan and latest handoff at
their recorded source, and uses the frozen task owner only in a disposable
charter: empty/unbound recovery, current owned candidate, actual source assertion,
consumed/accepted result and suppressed reentry. It proves that bounded source
consumer path; it does not prove automatic wake, a new model turn, native hook
installation or an end-to-end product/Runtime job.

The compiler's old W3 `next_action` mentioning PR1289 is a concrete stale-prose
example: that PR subsequently landed. It is never converted into a new task by
this integration, and no historical operation is reopened.

### Exact frozen-source audit exception

The restored helper uses `compact(..., 500)` as a display bound on a line with an
em dash. The existing ASCII-only review format cannot describe that Constant's
Python byte columns without changing the frozen source. This contribution keeps
that source unchanged and adds a strictly opt-in `utf8_sites` format to the
existing exact-file review matcher, used only for that pinned payload. The
preimage and its ordinary ASCII `400` display bound retain the original format.

A UTF-8 site needs the exact path/full-file SHA, complete byte slice on valid
character boundaries, and exactly one complete Python AST Constant matching
line, byte start/end, integer type/value and spelling. Masking receives converted
character columns only after every check succeeds. A string substring, partial
adjacent integer, normalization, changed hash, wrong path/column, or new identity
literal is not covered. Legacy records keep the existing ASCII requirement.
This is source-review accounting, not runtime authorization or a generic scanner
exemption; the consequential matcher change requires nonauthor review.

### Repeat the attended source rehearsal locally

From an active Codex turn with Python, PyYAML, Git, and a local Macro checkout
that already contains the pinned commit, run:

```sh
python3 -B /ABSOLUTE/REVIEWED/MASTERMIND/integrations/session_bridge/rehearse_project_owner.py \
  --macro-repo /ABSOLUTE/MACRO/CHECKOUT --result /ABSOLUTE/NEW/receipt.json
```

The rehearsal reads a local archive of a specified immutable Macro revision.
It creates a temporary, independent Git repository with no remotes or alternate
object stores, plus a fresh home and charter. The private commit identifies this
subset, separately from the donor commit. The import explicitly uses
`--no-fetch`. During owner pickup the fixture permits only read-only Git
commands inside its temporary root and records their names. The action verifies
the seven frozen package members. Acceptance and two subsequent reads show that
the task was consumed. The receipt describes source behavior in that attended
turn. It does not establish that an installed Codex hook delivered context.

An earlier development rehearsal omitted `--no-fetch` and invoked a pull on
a shared mirror. Its tracking ref and fetch metadata changed while the checkout
HEAD stayed in place. That run is excluded from isolation evidence. The
standalone rehearsal above is the reproducible path.
