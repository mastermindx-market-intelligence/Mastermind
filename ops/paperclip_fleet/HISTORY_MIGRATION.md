# Hermes history in Paperclip

This is the history lane of the Chairman's continued Paperclip fleet migration.
The original [fleet readiness plan](../../docs/superpowers/plans/2026-11-09-paperclip-fleet-readiness.md),
[merged integration #2399](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2399),
and [finite credential integration #2403](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2403)
retain their original acceptance and effect identities.

## Ownership and user experience

Paperclip is the operating interface for the 13 existing Hermes bots. Each bot
continues to use its original Hermes profile, SOUL, skills, OMH memory, session
database, and Capacity Fabric configuration. This history operation adds a private
Paperclip archive containing documents and downloadable native Hermes readers.
It does not create replacement bots, import historical messages as new activity,
or introduce a second writable memory or learning service.

The archive includes the legacy default Hermes home as well as all 13 named
profiles. It is private and unassigned. Historical session and message IDs are
retained; archived, inactive, and compacted message rows are included. A long
conversation may span several numbered parts. JSONL segments preserve each
message once and carry `archive_segment.message_offset` for reconstruction;
the profile index links all parts belonging to the original session.

This is a snapshot projection, not a native Paperclip chat import or a continuous
transcript sync. Every profile has its own consistent snapshot boundary. Live
messages written afterward remain in the original Hermes database, available to
the bot through its existing session-search capability. Referenced external media
is not automatically fetched or copied by these scripts. Media availability and
real browser access remain separate acceptance checks.

## Private export

Run `paperclip_history.py` through the installed Hermes managed Python runtime,
with its actual source root, existing home, and an operation-owned private output
directory. It imports the native dependency bootstrap, SessionDB exporter, secret
redactor, and HTML renderer. Do not install a separate Python dependency stack.

The exporter uses SQLite online backup, including WAL state, and checks snapshot
integrity. It reconciles every exported message ID and active/compacted flag with
that snapshot, then verifies totals. Raw databases stay private on the host and
are never uploaded. Redaction applies to all string values, including metadata.
The native redactor is a defensive filter, not a proof that arbitrary private
values can be identified automatically.

Completed profiles are retained. An interrupted profile is not automatically
retried. After reconciling the original process, `--resume-profile <name>` can
reuse the original consistent snapshot: it validates the saved receipt, or records
the observed snapshot hash and file timestamp if the earlier exporter did not
persist a receipt. Unpublished partial bundles are retained in
`interrupted-export-v1`; a second interrupted recovery requires explicit
reconciliation. No accepted profile is regenerated merely to unify timestamps.

## Native Paperclip publication

`publish_history.py --output <archive-directory>` is qualified against the
installed private local-trusted Paperclip 2026.1106.0 instance. It refuses another
deployment mode or version. The API client uses the fixed loopback origin,
disables environment proxies, and refuses redirects.

Before any publication, it verifies the original snapshot hash, ZIP and reader
hashes, record identities, segment continuity, counts, and index part mappings.
Bundles remain below the installed attachment limit. ZIPs contain only redacted
JSONL, a native reader, and an integrity manifest.

Publication uses one private, unassigned native issue, native file attachments,
and keyed Markdown documents. It saves intent receipts before mutations, never
automatically retries an interrupted write, and reconciles any existing object
on the original issue. Downloaded bytes and document bodies must match exactly.
Final issue visibility, assignment, native object membership, and zero wake
requests must be read back before `verified-publication.json` is written.

After verified publication, the archive card moves from `backlog` to `done`.
The completion step reconciles every attachment ID/hash and document body with
the saved publication receipts, including the asset supplement when present.
It refuses incomplete publication, assignment, active execution, related work,
reviews, interactions, or wake history. One status-only update is followed by
fresh status, ownership, live-run, and zero-wake readback. No comment, assignment,
or agent wake is needed to finish this archive.

For an already-published archive, run `publish_history.py --output <archive-directory>
--complete-only` to perform that reconciliation without exporting or uploading
again. A lost response stays bound to the same issue: an observed `done` state
is reconciled without another write; an unresolved pending update is not replayed.
`completion.verified.json` records the result. This terminal status covers the
imported snapshot only; the live fleet acceptance below remains separate.

The HTML attachment is downloaded for local viewing; it is not rendered inline
as trusted Paperclip UI. The native reader's security policy remains in effect.
The raw private snapshot and original Hermes data are retained for recovery.

## Qualification and remaining acceptance

Focused tests cover WAL snapshots, inactive-row preservation, metadata redaction,
oversized-session segmentation, interrupted-export retention, archive integrity,
private/unassigned scope, absence of execution, and uncertain-write reconciliation.
Run `python3 -m unittest discover -s tests -p 'test_paperclip_history*.py' -v`.

A successful export or upload is not full fleet acceptance. The parent mission
also owes actual browser access to a reader, media assessment, a fresh Paperclip
task returning to its original issue, runtime MCP and Capacity Fabric accounting,
OMH write/read across runs, profile isolation, leadership skill materialization,
and evidence that native learning remains usable. Credential activation stays on
the original #2403 carrier and its native release, source-custody, and live-work
controls. Do not restart active Hermes work to make the archive available.
