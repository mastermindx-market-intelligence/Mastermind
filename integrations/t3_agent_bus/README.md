# Native T3 Agent Bus: qualified source overlay

This package completes the native CLI transport and strict lifecycle source seams
recovered from Mastermind PR #2374. It is **not an installed T3 server**, a new
scheduler, an authentication service, a provider router or a ChatGPT callback.

The original upstream is MIT-licensed `pingdotgg/t3code` at
`0770446869d247a8b28c27d7ed93f47f8ff0c1e4`. `UPSTREAM_LICENSE` retains the original
copyright and license. `manifest.json` binds all 13 affected paths to their exact
before/after hashes, the patch digest and the exact minimal upstream archive.
The two completed native donor conversations remain source provenance, not live
worker ownership or authority to install their output.

## What changes

The original native CLI gains `thread native-catalog --json` and
`thread native TOOL --json`. JSON arguments arrive on stdin. Its allowlist covers
environment/project/thread discovery, reads, launch, message/queue/steer, wait,
interrupt, configuration, organization, pending questions and the lifecycle tool.
Native MCP envelopes and typed errors are preserved. There is no shell input,
automatic retry, copied credential, alternate provider or second queue owner.

`--expected-environment-id EXACT_ID` qualifies the environment **inside the same
native authenticated session** before sending the requested action. A wrong
instance cannot receive the requested write. Input and ordinary output are capped
at 256 KiB; catalog discovery is capped at eight pages, 200 entries and 2 MiB.
Repeated tools/cursors, malformed JSON/UTF-8 and truncated output are failures,
not successful empty results. The caller's injected process runner still owns
hard process/time limits and recovery of its original invocation handle.

`t3_thread_lifecycle` adds these operations through existing native access checks:

| Action | Required qualification | Meaning of a successful receipt |
| --- | --- | --- |
| `inspect` | Exact authorized thread/environment | Bounded metadata and the existing per-thread native event sequence. It grants no write permission. |
| `set_model` | Exact observed event sequence; target and selection both `capacity_fabric`; no active, queued, pending or child work | Native command accepted at the original serialized and transactional boundary. Python additionally verifies the selected model on readback. |
| `delete` | Exact observed event sequence and title; no active, queued, pending or child work | The existing native tombstone command committed. No project/worktree/filesystem deletion is requested. |

The event sequence check runs twice: under the existing thread-command lock, and
inside the same native SQL transaction that writes command receipts, events and
outbox effects. A race between decision and commit writes only the native rejected
command receipt. The tests include same-millisecond title ABA and a mutation
injected between decision and commit; neither can slip past the revision guard.
Timestamp-only clients cannot invoke the strict integration mutations.

The existing ordinary T3 commands remain backward-compatible. Generic provider
switching is not added to this integration. Legacy Python `set_model` and archive
preflights retain their explicit non-atomic classification; they do not silently
inherit the strict extension's guarantees.

## Existing Python owners

`integrations/session_bridge/t3_cli_transport.py` composes the actual native catalog
with `T3NativeClient` using an independently authorized injected runner. It starts
no process itself. Failed discovery invalidates its capability snapshot; an absent
strict lifecycle tool stays unavailable. A modifying transport failure or lost
readback preserves the original uncertain effect and never selects another carrier.

Use `lifecycle_snapshot`, `set_model_atomic` and explicitly confirmed `delete`
only when actual native discovery advertises the strong revision schema. Existing
thread results, queue management, shared GitHub compare-and-swap notes and mission
briefs remain with their original owners. A receipt is not a completed task or
whole-project acceptance.

COO preparation and direct `ProjectTeamClient.launch` now require an explicit
logical Capacity model. Direct launch requires the existing `T3NativeClient` with
the exact environment/project and its live Capacity catalog. The legacy CLI is
retained for original reads, never as a provider-default launch fallback.

## Reproduce the affected source

Generate the minimal archive from an already authorized checkout containing the
exact upstream commit. This reads committed source; it does not check out or edit
the donor repository. Run from this Mastermind checkout and choose a fresh archive
path in your own build workspace:

```python
import json
import subprocess
from pathlib import Path

manifest = json.loads(Path("integrations/t3_agent_bus/manifest.json").read_text())
with Path("/absolute/owned-build/upstream-required.tar").open("xb") as output:
    subprocess.run(
        ["git", "-C", "/absolute/qualified-t3-source", "archive",
         manifest["upstream_revision"], "--", *manifest["base_archive_paths"]],
        stdout=output, check=True,
    )
```

```sh
python3 scripts/build_t3_agent_bus.py \
  --archive /absolute/owned-build/upstream-required.tar \
  --output /absolute/owned-build/new-agent-bus-source-overlay
```

The output must not exist and its parent must be an existing non-aliased directory.
The builder captures and verifies all inputs before creating it, rejects archive
links/path escapes, uses the original Git patch engine, checks every postimage,
and writes `source-build.json` only after verification. The output contains only
affected source and the upstream license, **not a runnable standalone server**.
A failed build may retain its own incomplete output for diagnosis; it never
reuses, replaces or deletes another target. No network/install/restart occurs.

The actual isolated qualification successfully rebuilt all 13 postimages. Unit
regressions cover tampered inputs, missing/duplicate paths, links/traversal, old
preimages, wrong postimages, existing destinations and deterministic receipts.

## Qualification and release boundary

Evidence is recorded in `docs/evidence/t3-agent-bus-v4-verification.json` and
`docs/evidence/t3-agent-bus-v4-native-read.json`. Native tests use the exact donor
source with this patch and its existing locked dependencies, not an invented API.

The live local server returned the 13 pre-existing collaboration tools and allowed
the new source client to read its environment, project thread list and original
lifecycle conversation. It did **not** advertise `t3_thread_lifecycle`. No live
thread was launched, messaged, stopped, re-modeled, archived or deleted by this
qualification. Connect and LAN were disabled on the latest explicit status read.

Native context measurement is 49,470 tool-list JSON bytes, versus the donor's
48,116. The increase must remain visible to the native release owner; an upstream
PR still needs its actual `agent-context-increase` policy approval where required.
Passing the measurement test does not waive a source or release control.

### Exact continuation for the existing native runtime owner

Mastermind PR #2338 retains active native runtime/admission/deployment custody.
Integrate this source only after reconciling that owner's actual T3 source head,
active work and release target. Do not overwrite a live checkout, force the patch
onto an unqualified base, copy a scratch repository over the app, change providers,
restart occupied sessions or create another admission/queue service.

Preserve unrelated continuity (#2375), browser/computer (#2401) and Capacity
(#2367) writers. Apply or deliberately rebase the 13-path patch in the authorized
native release workspace, rerun the focused suites, retain the loaded-byte and
rollback receipts, then use newly owned disposable targets for the complete
launch -> queue/steer -> result -> stop -> strict model switch -> archive ->
confirmed tombstone journey. Verify that Capacity is the only execution route.

Shared notes and long-horizon mission/team composition already exist; their next
acceptance is a real delegated run whose original parent consumes the actual
result, notes revision and remaining DONE_WHEN. Source compilation is not that
proof. For a direct ChatGPT connection, use the original T3 Connect/approved
endpoint and native OAuth consent. Ordinary foreground reads do not prove an
unsolicited ChatGPT wake or an always-running service.
