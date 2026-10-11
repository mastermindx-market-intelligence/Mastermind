# Original-owner Fabric cleanup evidence transport

This source component delivers retained process-group cleanup evidence through
the existing Fabric bridge. It does not install a service, provide a production
Backend, create evidence, revoke an assignment, or change provider admission.

## Read contract

The existing authenticated `status` operation has one explicit closed extension,
`cleanup_query`, with schema `mastermind.executive_fabric_cleanup_query/v1`:

- `scope`: collection, validation, terminal, restart_absence or unbound_absence.
- `process_ref`: the complete immutable original `WorkerProcessRef`.
- `host_ref`: the physical host from the protected binding source.
- `observed_after`: the required observation floor, including later validation
  or cancellation activity. Restart absence requires its fresh request floor.
- `readback_sha256`: null for the first retrieval; the exact package digest for
  the independent second retrieval.

The normal outer binding retains root, Job, Attempt, effective grant, commission
and physical route. The broker first checks the owner's ordinary terminal
status and exact process reference. It then asks the same backend for the typed
read. The response contains only the common binding, `cleanup_query_sha256` and
the closed `mastermind.executive_fabric_cleanup_evidence/v1` package. The package
includes exact original lane JSONL bytes; its lineage, process generation,
principal, scope, timestamps, digests and complete cleanup/capture fields must
pass `fabric_cleanup_contract.py`.

The backend must perform a second retrieval from its original retained evidence
store. Echoing the supplied digest or reusing the first in-memory object is not
independent readback. This query must not launch a census, signal a process,
release a lease, seal paths or restamp an earlier observation. Missing evidence
or an insufficient timestamp is a refusal, not proof of absence.

The adapter publishes its pair to synchronous readers only after both
authenticated reads match and Runtime's original lease and launch pin still
match. Supervisor primes this evidence asynchronously under its existing
heartbeat loop. Validation/cancellation invalidate prior cached evidence;
reattachment discards it. Synchronous recovery can retrieve outside an event
loop; unprimed reads inside the loop refuse.

Received collection and validation data are retained separately as private
`mastermind.executive_fabric_unqualified_evidence/v1` records before cleanup
qualification. Their `eligible_for_terminalization` is false. They do not
replace qualified receipt paths. Truthful process-exit recording precedes the
cleanup gate. Failure retains the original Attempt and never manufactures a
passing terminal seal.

## Actual producers still required

An admitted host owner must supply real launch provenance and persist complete
original cleanup records, then implement this read-only query against that
store. The installed lane record alone lacks the complete boot/start provenance
required by the Executive contract. Hashing current bytes cannot supply it.

Assignment revocation is a different missing producer: the actual owner must
revoke every granted run resource through an enforceable host mechanism, retain
the exact before/after resource identities and access consequences, and support
authenticated independent readback. Group absence, forwarding shutdown, local
chmod, a broker PID, or a shared-UID sweep cannot substitute. No such producer
is configured here; `FABRIC_ASSIGNMENT_SEAL_UNAVAILABLE` remains mandatory.

Current subscription profile restrictions remain unchanged. Source fixtures,
successful status delivery and an attended Codex Stop return do not authorize
an unattended production backend or establish Executive RuntimeBinding/Wake.
