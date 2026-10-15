# Final product acceptance in the authenticated Workspace reader

The separate Mission v4 read carries an unchanged Mission v3 document alongside
one closed product-acceptance observation. Existing Mission and Fabric v1-v3
contracts retain their original acceptance behavior. The original request key,
workstream and root form the exact selector; a caller cannot supply a verdict,
receipt, identity, path, Runtime or principal authority.

`GET /workspace/mission/v4/current` uses the existing Workspace JWT authenticator,
viewer permission owner, raw-path and GET-only fences, permission stamp and
post-read expiry check. It sends one v4 frame through the same App-peer socket.
Control requires the same App peer and Workspace provider; the new read does not
arm submission or acquire a principal COMMIT owner. The same owned-task helper
drains a cancelled physical read before propagating cancellation.

Only the new v4 exchange defaults to the existing 30-second client ceiling:
its canonical receipt reader can spend up to 15 seconds in the sealed Context
observation, plus bounded Runtime proof reads. Older operations retain their
10-second default. Each operation still honors an explicitly shorter client
deadline. This does not extend or renew any Context, Git, collector or admission
deadline and does not establish physical latency on the installed host.

The read service joins the selected workstream/root to the existing qualified
Control Room cache before any acceptance read. Its namespace-bound readonly
Runtime is the existing service owner's facade. The installed constructor passes
an `AgentOsProductAcceptanceBasisReader` backed by that Workspace's existing
sealed packet collector. This changes no installed reader implementation,
interpreter, read grant or source-release boundary; a missing or held Context CLI
still prevents a successful source read.

`ProductAcceptanceRulingReceiptReader.observe_acceptance` remains the only final
acceptance verifier. The adapter reads its original retained request, rejects a
foreign scope, and obtains the exact qualified ruling plus worker and original
aggregation-parent terminal proofs. A `COMPLETED` status only permits that
verifier to run; it never supplies acceptance. A pending root returns an explicit
unavailable reason. Source correction, missing consumption or invalid namespace
cannot disclose an accepted receipt.

Two bounded Fabric v3 observations bracket receipt acquisition. Both must have
qualified same-observation generation receipts, complete reference availability,
and matching materialized snapshot digests. The final parent attempt/result and
subject result must match the receipt. This compares materialized snapshots,
not numeric `data_version` values from different connections; it does not claim
continuous exclusion of Runtime writers. The Control Room publication bracket
and canonical Mission reducer still determine currentness. Noncurrent Mission
state removes the accepted receipt, including content-preserving publication ABA.

The TypeScript v4 decoder requires the exact request/work/root, current Mission,
closed receipt and source-continuity shape, and matching parent/subject result
references. Its committed fixture was generated from actual local Runtime,
terminal-return and receipt owners through the new Workspace service. Context,
Relay and namespace custody in that fixture are test-owned observations.

Qualification includes real JWT validation, local Unix/Control dispatch, the
UID458 outer route, namespace invalidation, cancellation settlement, wrong
selection, stale source and missing worker/parent consumption. These are local
source tests. The App host and authenticated web transport now select this read
and render its closed observation in the product-acceptance panel. Auth changes,
selection changes and stale responses cannot carry a prior accepted result into
the current view. Existing plan behavior remains separate. Installed endpoint
selection, real account permissions, live Context acquisition and original-parent
consumption remain separate acceptance obligations. No old uncertain operation
is replayed.
