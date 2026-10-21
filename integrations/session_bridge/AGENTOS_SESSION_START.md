# Attended Agent OS context on Codex startup and compaction

This adapter connects the existing Agent OS context compiler to Codex's `SessionStart` input. It restores recorded project direction for an explicitly selected workstream and workspace. It does not create a new memory store, select a company priority, create a runtime assignment, or recover live worker custody.

## Existing owner and observable result

`integrations/session_bridge/agentos_session_start.py` calls `ops.fabric_launch.agentos.read_context()` exactly once for a matching event. That owner invokes Macro's `scripts/agentos.py compile-context` with a 25-second runtime bound, a 128-KiB output bound, exact-workstream validation, and process-group settlement. The adapter preserves the owner's complete `context_bundle.v1` bytes, including the objective, constraints, accepted work, latest handoff, citations, exclusions, omissions and degradation that the owner actually included. It neither synthesizes missing records nor rewrites their priority.

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
