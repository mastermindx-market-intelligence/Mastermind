# Codex Stop attention for explicitly subscribed Fabric jobs

Ordinary paid-worker delegation uses the installed M2 shell Fabric adapter. It
must not wait for Executive MCP, company Mission acceptance, RuntimeBinding or
idle Wake. Existing broker, host, process, result and outcome owners remain the
only worker lifecycle. This source adds attention to that path.

The adapter's opt-in `request --native-return` requires the verified current
native thread to equal both the explicit root and parent. It refuses existing
run evidence and records a subscription before dispatch. It does not adopt old
runs or authorize a retry. Ordinary requests have no subscription effect.

The separately reviewed/trusted Codex Stop definition invokes
`fabric_stop_return.py --subscribed-state-dir <private-state-dir>` with an exact
installed adapter hash. Each native parent sees only its explicitly registered
IDs. A callback has a ten-second budget and prepares at most four successful,
unaccepted retained results. Failed, pending, unknown, foreign and already
attempted results do not produce attention. The payload carries references,
lengths and digests; worker content is consumed by the parent through the adapter.

One atomically replaced, fsynced metadata record reserves the complete selected
frame before emission. An uncertain delivery never authorizes replay. The state
uses a held private directory descriptor, one nonblocking parent lock, strict
metadata shapes, exclusive pending files and readback. It refuses changed paths,
unsafe modes, corrupted metadata and interrupted writes. It never deletes or
repairs those records automatically.

There are at most 32 registered IDs per parent. Reaching the bound refuses a new
opt-in before dispatch; it does not silently evict an uncertain attempt. No
background process, timer, queue, worker launch, cancellation, lease release or
acceptance is implemented by the helper.

A changed hook definition requires native Codex review/trust. The old trusted
helper must not be overwritten to avoid that consent. Source tests and a trusted
fixed-run hook do not prove the new definition ran. Active Stop continuation also
does not establish idle Wake, Executive RuntimeBinding or production backend
admission.

Validation: 36 existing fixed-run checks, 24 subscription checks, and eight
adapter opt-in checks passed. The independent paid review
`fabric-native-subscriptions-review-01a11e90-v1` returned 3968 bytes, SHA256
`c0c858e5462f61bb29f002897079388d72f5026902609b3523fb7be653efb1ff`,
and was adjudicated and accepted by the original parent. General live delivery
remains a separate obligation after installation and native trust.
