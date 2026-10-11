# Read-only Codex desktop queue topology preflight

This is a **diagnostic for the existing #515 / #1143 Codex native-session work**, not a new
listener, an App Server client, a worker registry or a RuntimeBinding authority.
It supplements [codex-queued-wake.md](codex-queued-wake.md), which remains the
owner of the actual Wake reservation, queue-add, and read-only reconciliation.

## Run on an approved macOS host

Use an exact reviewed and installed Mastermind source revision, from its repo root:

```sh
python3 -B scripts/ohf/codex_desktop_queue_preflight.py
```

The command emits one bounded JSON record with schema
`mastermind.codex_desktop_queue_preflight.v1`. It performs no API login,
native App Server RPC, socket connection, account or thread discovery, queue
insertion, turn start, session resume, database-content read, browser action,
process restart or listener installation. It reads only process-parent
metadata, owner-only socket metadata, selected process open-file identities
and desktop app version metadata. Fixed local process-inspection commands use a 6-second
collection deadline with a hard stdout byte cap applied *while reading*;
oversized or stalled children are killed/reaped, not buffered first.
It checks that the executable is actually Codex instead of accepting an unrelated
process whose arguments merely mention `codex app-server`. It never returns
PIDs, raw process arguments, paths, file names, conversation content,
authentication material or transcript information. On non-macOS hosts it reports `UNSUPPORTED_OS`; it does not
attempt compatibility by choosing another transport.

`TOPOLOGY_CANDIDATE_ONLY` requires:
- exactly one directly desktop-owned Codex App Server rather than descendant
  helper processes or competing direct writers;
- one current owned native Unix App Server socket with owner-only permissions;
- exactly one managed App Server holding that socket;
- at least one shared state-database identity derived from each process's
  **open file descriptor** (the `lsof -F fDtin` device/inode fields), never
  from restatting a pathname that SQLite could have replaced; and
- a syntactically valid app version read from the bundle that actually owns
  the observed desktop process, never from a different installed app. The
  `Info.plist` descriptor must be a regular file, opened without following
  symlinks and without blocking on a FIFO; its bytes are capped at 64 KiB
  before property-list parsing.

Every error, incomplete inspection, missing observation or ambiguity keeps
the result `UNQUALIFIED`. This output is **not** an authorization token.

**Protocol qualification is separate.** In Codex CLI `0.159.3`, the native
`thread/queue/*` methods are experimental App Server API and require the
client to declare `initialize.capabilities.experimentalApi=true`. A fresh
isolated no-account probe without that opt-in returned protocol error `-32600`;
with the documented opt-in it advanced past that gate but still did not reach
an eligible real thread. Those tests used a disposable empty `CODEX_HOME`,
never a desktop-owned or account-bound thread. The preflight deliberately
never opens a protocol connection or opts into experimental capabilities;
its `queue_api_production_supported` and `experimental_api_enabled_by_preflight`
fields are always `false`. This experiment is not vendor production-support
qualification, and no installed owner should silently enable experimental
features or retry denied live effects to make a canary succeed.
A candidate cannot assert an eligible thread, supported account, matching
desktop-bundled protocol, actual queue consumption, output correctness,
completed provider turn, or original-parent result return. Those proof fields
remain permanently `false` for this diagnostic.

The bounded process scan is current-state metadata; it does not retain a
snapshot registry. A socket can disappear after inspection, so the native
host-owner/connection-generation admission is freshly rechecked by the actual
writer immediately before any effect. Nothing in this command removes or
replaces that check.

## Required next real proof — separate admitted operation

The existing #1143 integration owner selects one **disposable,
non-sensitive ordinary desktop-owned Codex thread** and confirms its exact
authenticated native RuntimeBinding, account, current writer, provider
generation, original parent and current Wake reservation. Do not discover
a random existing ChatGPT conversation by newest title, window or timestamp.
Do not substitute a newly resumed CLI thread for the current GUI-owned writer.

Only the admitted existing Codex Wake owner may submit a single fixed
`thread/queue/add` through a qualified already-running App Server connection.
Treat `clientUserMessageId` as a correlation value, not vendor-enforced
idempotency. The desktop writer consumes the queued item at its permitted
turn boundary. Record accepted enqueue, target consumption, turn start,
completion, useful result, canonical result commitment and originating-parent
consumption **as distinct observations**.

Test busy/unloaded/archived targets, wrong account/thread, missing or changed
native generation, concurrent human draft or action, host sleep/app close,
provider error, authorization revocation, lost queue response, queue-item
consumption before reconciliation, duplicate return and changed original
parent. A missing queue item does not prove no effect: reconcile the same
operation, never submit a second queue-add or switch writer/host/account.

If a qualified provider-native reply producer is not installed and selected
through its actual current owner, keep original-parent consumption unproven.
The ongoing CODEX-02 NativeReplyWriter repair under #1143 is separately
owned; do not create a parallel callback or install its unpublished patch.

## Source verification

```sh
python3 -B -m pytest -q -p no:cacheprovider tests/test_codex_desktop_queue_preflight.py
```

Focused unit tests use synthetic process trees and disposable local Unix
sockets; neither they nor `TOPOLOGY_CANDIDATE_ONLY` meet the real-path
acceptance above. The script has no always-running daemon and adds no
configuration state. This is a source-only qualification contribution until
review, release and selection are independently proven.
