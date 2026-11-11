# Native T3 transport dependency

Upstream: `https://github.com/pingdotgg/t3code`, MIT license (included).
Pinned source: `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`.

`t3-native.patch` is the completed `web-t3-cli-adapter-20261109-a1` native CLI
candidate. Empty context lines are normalized for repository whitespace checks;
the applied source is identical to the completed candidate. Original patch SHA-256:
`6ce1853635819631d35353c5e6c2f4596931d3d57493d396d82e5b50901ccb0c`. Stored patch SHA-256:
`74e107769c3b02cba635fd7f64e0ca13eaf1be5c6b5180f221d891df296fd956`.
Original native coordinator: `mcp:5b3b360e-1842-4b27-b510-e38b9546941b`.
The coordinator completed its task before this adoption. Its worktree is not
modified or used as the installed runtime.

The patch adds an allowlisted `thread native` command and `thread native-catalog`.
It reuses the native CLI's `withThreadTools` / EnvironmentAuth session issuance
and revocation. It does not borrow an agent's authorization environment, install
an authentication service, change the running T3 server, or retry native calls.
Provider selection remains restricted to `capacity_fabric`.

The Paperclip port exposes only environment/project/thread observations and
`t3_thread_send` in queue mode; the wider operator CLI does not enlarge the
Paperclip tool surface. The port discovers actual live schemas and uses the
existing Mastermind `integrations/session_bridge/t3_native_client.py`.

Build in an isolated source tree at the pinned source. Apply `t3-native.patch`
first, then `t3-realtime.patch`. Use the frozen upstream dependency lock, run
`thread.test.ts`, `thread.native.test.ts`, `thread-watch.test.ts` and
`AcpMcpStdioBridge.test.ts`, and run
`vp pack --out-dir <fresh-build-dir>` in `apps/server`. Then use
`package_runtime.py --source <checkout> --built <fresh-build-dir> --output <fresh-runtime-dir>`.
The packager copies the installed lockfile-resolved external dependency graph
with relative internal symlinks. It records dependency provenance and includes
the upstream license. It does not require the build worktree at runtime.

Install only from the merged Mastermind source receipt. Keep the native bundle
under an immutable release directory and configure the plugin's exact absolute
path. Never overwrite `/Applications/T3 Code (Beta).app` or restart user sessions.


## Native event subscription upgrade

The original Fabric root `paperclip-teamlink-t3-20261110`, run
`teamlink-native-watch-upgrade-20261110-01`, returned on its original ubuntu2
carrier with rc 0 and a verified root. Its returned patch SHA-256 is
`9c2c19ae6b47e019ceca092004428be6c2b4d771d9aa6c90557d98e0558851b9`;
the returned response digest is
`af0050dbd25bb5634b3ed63affbcac23f1625eb7fcfa2781eaedc07dea7d0acb`.
The parent composed the returned artifact and corrected scope, failure
classification, pagination and output ownership before qualification.

The integrated `t3-realtime.patch` SHA-256 is
`5495395fe53c834112067e9220bc6c5456f02a32c5b361090ad73cda962057b7`.
It adds `thread native-watch`: one bounded JSON request on stdin, exact
native environment/project/root qualification, and compact JSONL notices from
T3's existing orchestration subscription. Native source sequences are hints;
Paperclip's SQL receipts and durable timeline cursor remain authoritative.

The qualification MCP session explicitly requests read-only access. Both it and
the socket session have only `orchestration:read`, a 15-minute TTL and a 10-minute
owned rotation. An optional native `issueMcpClientSession` TTL parameter lets the
watch select that expiry; all existing callers retain their previous default. Both sessions revoke through native scope finalizers. Closing stdin
cancels connection setup as well as an established watch. No agent credential is
inherited. Only identified transport failures reconnect; auth/scope/protocol
refusals and ambiguous failures remain held. Bounded pagination refuses stalled
or incomplete scans and stops as soon as every requested identity is proven.
A bounded queue and the native Stdio sink honor actual pipe backpressure;
output failure or a one-second stalled write terminates the watch and its scopes.

Parent qualification on M2 used the frozen upstream lock, Node 26.8.2, all 61
focused tests, clean Effect type checking, clean lint and `vp pack`. The upstream
root engine preference is 26.12.1; the server declares Node 26.8.2 compatible.
Exact patch reapplication reproduces every tested source byte. The relocatable
runtime has 22 dependency packages and internal relative symlinks. Packaging
records both patch digests and the exact compiled source-file digests; it refuses
a baseline patch different from the canonical pin.

This runtime qualification does not install the Paperclip plugin or establish
agent consumption, message latency, or project acceptance. Use the protected
merged-source receipt and the plan's real consumer acceptance sequence.
