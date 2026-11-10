# Referenced files in the Hermes conversation archive

This is a passive supplement to the accepted fourteen-profile history export
and the same private, unassigned Paperclip issue. The original snapshots,
conversation bundles and publication receipts are retained without rewriting.

The capture command reads all stored message rows, including inactive and
compacted content, the model-facing sidecar, and accepted-session admission
payloads from those snapshots. It uses native content decoding and spill-pointer
parsing. No live history database, admission, memory or model is modified.

## Scope and integrity

- Only referenced files beneath explicitly listed native cache/attachment roots
  can be captured. No whole-home, browser-state, credential or workspace copy is
  performed. Remote URLs and arbitrary remote-home aliases are not fetched.
- Explicit host paths identify their actual known profile owner. Container and
  tilde aliases remain scoped to the owning conversation or captured spill.
  Current/legacy layouts with conflicting bytes require an expected digest.
- Every path component is opened without following links. Only regular files
  pass, with size/inode/device/timestamps compared before and after reading the
  same descriptor. Original expected digests and sizes are checked when present.
- Private original bytes and their hashes are retained. Published text receives
  the same forced native secret-redaction pass as the history export. Recognized
  binary files, including ASCII PDFs, retain their exact bytes. Known text that
  cannot be decoded remains private and is not mislabeled as a publishable binary.
- Spill references expand through a bounded graph with parent links, no repeated
  scan per source occurrence, and explicit depth/size/count limits. A limit is
  recorded or stops completion; it cannot silently become a complete claim.

The private manifest records message/admission provenance and observed source
identity. The published manifest omits filesystem inode/device metadata. Each
bundle has safe generated member names, per-part hashes and full-object hashes.
The reference index maps objects back to native relative paths and conversations.
Missing, ambiguous, unsupported, changed and mismatched references are distinct
outcomes. A missing reference does not establish why a file is absent.

## Execution

Use the existing native interpreter/dependency owner and the already installed
history export/publication helpers:

    python archive_assets.py capture \
      --archive /private/accepted/archive \
      --output /private/accepted/archive/asset-supplement \
      --source /inspected/native/hermes/source \
      --home /inspected/native/hermes/home

    python archive_assets.py publish \
      --archive /private/accepted/archive \
      --output /private/accepted/archive/asset-supplement

Capture writes a pending receipt before work and never automatically replays an
existing capture. Inspect the original process and files if interrupted.
Publication requires the original verified history-publication receipt. It
reuses the existing private-issue, zero-wake, immutable-attachment and exact-body
document helpers. Pending API effects reconcile against their original native
object; no blind retry or replacement issue is created. Final publication again
checks that the archive has no execution or checkout owner and zero wakes.

This preserves available referenced files at capture time. It is not a live
filesystem mirror or a promise to reconstruct already missing bytes. A final
history delta after the runtime cutover remains separate from these accepted
snapshot boundaries.
