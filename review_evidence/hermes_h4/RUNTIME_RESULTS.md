# H4 installed diagnostic and native startup evidence

Operation: `hermes-capacity-routing-completion-20261107-c4`.
Source: Mastermind #2166, implementation commit
`f008b67333ecf627270a7d8378720f1f034864ce`.

## Proven result

The narrow diagnostic implementation, reversible installation and default-profile
startup check are complete. Full H4 primary, native tool, delegated-worker,
parent-consumption and settlement acceptance remain incomplete.

The existing M2 read-only capacity MCP source now preserves the exact known
exit75 host-eligibility refusal as `FABRIC_PREVIEW_NO_ELIGIBLE_REMOTE_HOST`.
Unknown or unsafe diagnostics remain generic. Seven focused tests passed.
No raw owner stderr or host list is returned through the tool.

| Evidence | Actual result |
| --- | --- |
| `capacity-bridge-source-install-20261107.json` | Exact predecessor checked; rollback copy retained; successor installed and read back; original gateway PID/start unchanged. |
| `installed-diagnostic-native-proof-20261107.json` | Original idle canary returned the retained generic refusal, then detached; zero messages and running=false. New closed diagnostic was **not** observed. |
| `capacity-mcp-owner-reload-20261107.json` | Original private-control recovery succeeded. Default status succeeded; marketing status returned `profile_mismatch`. Global reload stopped before send. No command, resume or subscription was created by that preparation. |
| `capacity-default-startup-20261107.json` | Native `mcp.servers.test` for the permitted default profile passed and advertised exactly `fabric_capacity_catalog` and `fabric_route_preview`. Source hash unchanged; process60241 terminal exit0. |
| `capacity-bridge-predecessor-20261107.py` | Exact retained predecessor source for the original installed path; this file is evidence, not an auto-executed rollback. |

The original long-lived capacity MCP children predate this source installation.
A fresh default-profile startup does not establish that an existing child
adopted the new generation. The generic response is retained without relabelling
it as a successful preview or as a proven defect in the new classifier.

## Original identity and effects

Gateway PID48443, instance `a9115d5bee674ff98a3fac21d9ad5ca8`,
authority epoch3; original canary
`local-0b988abfa6d9d0e2a8916c713ece3c2c0032c979a70a178e6d4066ea1228c027`.
No gateway restart, global MCP reload, profile/grant write, APPLICATION service
activation, provider inference or worker dispatch occurred in this slice.

The earlier session-ticket timeout occurred before any reload. Its bounded
identify diagnostic proved recovery. The later marketing profile-scope error
ended that cross-profile action. The supported global reload would reinitialize
secondary profiles, so it was not sent. Do not repeat that read with another
profile identity or use another carrier to bypass the scope boundary. The
separate default startup check remained within the already successful scope.

## Source and rollback custody through the next release

Active H4 operator `mastermidx4` owns the combined native/TUI fixture and
primary-account/service activation:
https://github.com/mastermindx-market-intelligence/Mastermind/pull/2166#issuecomment-6707462682

This source contribution supplies `integrations/hermes_omh/capacity_bridge.py`.
Its installation target remains the existing
`/Users/chriswong/.hermes/bridges/fabric_capacity_mcp.py`, bound by the current
default-profile MCP declaration. It is not the OMH plugin artifact and is not a
new service, installer, connection manager or admission endpoint. No claim is
made that #2175's Fabric release payload includes it.

When consuming these path-disjoint files, retain the bridge's exact postimage
or explicitly reconcile it through the same existing MCP installation owner.
Do not replace newer #2175 source with the older #2166 tree. Before a write or
rollback, recheck actual path, regular-file identity, current hash, ownership
and concurrent custody. The recorded predecessor is
`4d3f88a1b0ef0cbb501439acacebcbb5aa874cbd84c27755e87becda4b8a245c`;
the installed successor is
`242c19aec6f13db182e5b51c2bf560d48e1280cba87e9410bed17848b0e0e832`.
Never restore the predecessor over a different successor or active writer.

The pending diagnostic acceptance predicate belongs to that existing activation
work: establish that the serving default capacity MCP child adopted the selected
source generation through a legitimately scoped lifecycle operation, then retain
one permitted native exec result with the canonical closed reason and truthful
preview/admission state. Source installation and startup are not that receipt.

Root #2175/#10740 retains protected composition, merge, release and selection.
The active c2 worker issuer retains the SessionGrant/original-run admission join.
No duplicate implementation, new runner, idle watcher or background execution is
created by this return. The first qualified primary plus harmless native-tool
journey remains useful independently of optional pools and scorers.

## Latest native source observation — 14:25–14:28 UTC

A final bounded read found two additional tracked on-disk edits,
`agent/agent_init_fallback.py` and `agent/chat_completion_helpers.py`,
plus untracked `tests/test_fallback_family_first.py`. The previously known
untracked `tests/tui_gateway/test_omit_messages_resume_bounded_ack.py` remains.
The new tracked diff adds an opt-in `fallback.family_first` chain reordering
helper, default off; this is another writer's source change, not an H4-installed
runtime feature or a proven effective configuration.

`native-writer-delta-20261107.json` captures all six tracked and two untracked
paths with stable file identities. All ten core preimage hashes remain unchanged
and the previous four TUI files retain exact bytes and identities. The new paths
do not overlap the ten-file activation patch. No second apply/reverse test was
needed to establish this path/hash comparison.

The active combined-fixture owner must consume this current source snapshot
before activation. The 13:31 preimage receipt is still a dated ten-file
preimage/rollback observation; it does not establish combined behavior for later
fallback changes. No live file was reset, patched or cleaned.

At 14:25 UTC the original gateway PID/start and installed bridge postimage were
unchanged, CURRENT remained sequence35/generation
`ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46`,
and no TCP4142 listener was present. A bounded local launch/process metadata
inspection did not identify a running `go_shim.py` or `go_router.py` process;
it does not establish fleet-wide service absence or authenticate any endpoint.
No provider request was made.
