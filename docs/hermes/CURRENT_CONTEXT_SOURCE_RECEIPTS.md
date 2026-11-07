# Current Agent OS record-source receipts

The installed current-context reader issues
mastermind.agentos_current_context_receipt.v2. Adopted receipt v1 and current
receipt v1 keep their historical field sets and validation.

Reading old receipts is supported; rolling producer/consumer compatibility is
not negotiated by the unchanged tool catalogue. Older strict v1 consumers
refuse a new v2 response. The original release owners must qualify the selected
producer and consumer source versions together before activation. No fallback
reader or alternate transport is introduced.

## Meaning

selected_record_sources identifies authored direct-record contributions to
selected excerpts in the exact returned context_bundle.v1. Each entry names an
ordinary file from the held Macro DATA commit, its Git blob and exact content
SHA-256/byte count, and every selected section/item position using it. Macro CODE
and DATA remain separate coordinates.

The closed initial kinds are workstream, constraint, dependency, decision,
discovery and handoff. A handoff item carries its associated WS key and its
actual direct-child filename. Artifact pointers, excluded/omitted records and
higher-law auxiliary inputs do not become direct-record contributions.

Coverage is always PARTIAL. These facts do not establish whole-document
delivery, exclusive provenance of an excerpt, provider delivery, a complete
source-policy set or evaluation acceptance. Workstream excerpts can contain PR
state; other text includes compiler labels, Git dates and selection reasons.
Full auxiliary coverage belongs to the original compiler's source annotations.

## Capture and limits

The incumbent installed reader captures bytes inside its existing qualified
materialization, result deadline and post-read generation checks. Membership,
ordinary-file mode and Git blob identity must agree. Integrity failures refuse
the read; they are not treated as capacity overflow.

Private inventory is limited to 6 KiB and a source file observation to 1 MiB.
On inventory or record-byte overflow, the complete original context remains
unchanged. The inventory retains explicit selected/retained/omitted counts,
retention OVERFLOW, a closed reason and no entries. A zero retained count with
omitted_items greater than zero never describes an empty source universe.

retention COMPLETE means every eligible direct-record contribution is retained.
It does not change coverage PARTIAL. Equal content hashes at distinct paths
remain distinct entries. Multiple uses of one DATA/path share one entry.

## Native snapshot

The existing provider validates and privately detaches the complete v2 receipt
and inventory. It keeps the full receipt digest, renders a named prompt
observation projection, and appends the exact original bundle bytes verbatim.
The model prompt does not copy the private entry array.

The private snapshot lookup requires the exact rendered-context hash and a
still-current, unexpired binding. It creates no read, delivery, publication or
memory store. Existing public readiness and delivery fields remain unchanged.
Historical v1 rendering is unchanged and produces no new inventory.

This component ends at qualified snapshot evidence. A later original EVAL
observer must qualify final post-hook prompt inclusion, request/transport joins,
frozen source policy and bounded retention before promoting any contribution
into delivered-source evidence.
