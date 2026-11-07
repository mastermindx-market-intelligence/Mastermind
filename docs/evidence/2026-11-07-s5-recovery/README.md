# S5 bounded service recovery source qualification — 2026-11-07

Status: source-only qualification on original [PR #1887](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1887). No installed-service acceptance.

Original head: `daa033f71fa2c9a7e342bce2a879c2c4c1687e87`.
Protected integration/law pin: `5f8c13da926011fb5fdc8cea21287b532ac968db`.
S5 parent/root: `01a1b498-2e4c-746b-bdea-77b474c900c4`.

## Behavior qualified in disposable fixtures

The existing recovery owner keeps one durable ledger and one serialization boundary. A corrective attempt is reserved durably before its effect; interrupted, refused or ambiguous outcomes retain the reservation. An acknowledged restart also retains its reservation until a strictly newer, identity-qualified first-party heartbeat proves recovery. Log-file mtime and a present PID alone remain diagnostic.

The policy permits only one unconfirmed acknowledgement in an episode. Fresh proof must be newer than the reservation and pre-attempt heartbeat, carry new provenance, and have a validated age in the incumbent closed 0–300-second window. Freshness is checked at both release admission and the release mutation boundary. A newer-but-stale heartbeat cannot erase pending state, reset the attempt counter, create a recovery claim or start another restart.

Persisted recovery proof is validated against its own recorded observation time. A valid historical proof remains valid as wall-clock time advances; a proof already stale when recorded is rejected. Existing cooldown anchors are preserved. There is no free-form reset/reconciliation API, replacement ledger, general watchdog or new heartbeat producer.

The atomic writer's post-rename directory-open/fsync failures are explicitly tested. A failed durability acknowledgement does not assert that the old pathname survived; the next natural pass retains the conservative state. Multiprocess and repeated-pass fixtures preserve bounded behavior.

## Parent verification

The complete final patch was applied to a disposable fixture against the exact original head, after checking all prior candidate hashes. Parent verification ran the original source gate:

- `tests/test_subagent_fabric_tunnels_source.py`: **4 passed**, 7.921 seconds.
- Its nested colocated suite: **333 passed**, 7.808 seconds.
- All five postimage Git blob IDs matched the delivered candidate.

The six fresh-witness regressions cover advancing-but-stale polls, repeated natural passes, the exact 300-second boundary, direct mutation rejection, invalid persisted proof and valid historical proof. The earlier fixture that expected a 303-second-old heartbeat to release an attempt and permit another kick was corrected because it asserted the reported defect.

All installation, restart and heartbeat records emitted by these tests belong to disposable fixtures. They are not live host receipts. No installed poll, restart, service death, installation, permission/security change or maintenance cycle was executed.

## Artifact and contribution provenance

Final bounded paid run: `s5-recovery-fresh-witness-20261107-c1-01`.
Exact complete response SHA256: `4c56fe28b33a7cb48edf115899e5b2a17a67a2c127ad8e0497046ae8f08c1e21`.
Full patch against original daa: **195596 bytes**, SHA256 `943ec60dfa05807af619d02850be0f377e3b46546d5c271ae23dbad08d8c6d0e`.

| Path under integrations/subagent_fabric_tunnels | Verified Git blob |
| --- | --- |
| fabric_tunnel_health.py | `127807b961578f70502b12d4065ee4a4c521506d` |
| fabric_tunnel_common.py | `b8091d8f2d6f4bc9dbba7e98eb62e53244c28e61` |
| test_fabric_tunnel_health.py | `747c23ef62527df46feef50c7ce7c8f332967af6` |
| test_fabric_tunnel_recovery.py | `46fae05727947f59937b86b1016b85e3ba0e1f93` |
| RUNBOOK.md | `38e0b3b7bf1b1691073fdaac70b856e3d259d444` |

Earlier proposals remain superseded and unaccepted. Their source-linked findings and artifacts remain on #1887. Source acceptance of this final contribution does not mean formal GitHub approval, hosted CI success, deployment or operating acceptance.

## Holds and remaining installed proof

The original **HOLD_SECURITY** is unchanged: pathname-spawn qualification still has the Cellar rename window and ambient-interpreter finding. Historical native-generation mismatch and host-route refusal remain binding. The absence-before-initial-lstat qualification limitation is disclosed and not repaired by these ledger changes.

The original owner must qualify exact installed service identities, native generation and first-party heartbeat provenance before an authorized real cycle. Studio Direct's own remote carrier must not be restarted. No security/TCC change or general watchdog is authorized by this source work. Required hosted CI and genuine protected-branch requirements remain separate gates.

No physical fleet admission, elapsed service-recovery proof, reliability percentage or 24x7 claim follows from these fixtures. Attributable reclaimed bytes in this session remain zero.
