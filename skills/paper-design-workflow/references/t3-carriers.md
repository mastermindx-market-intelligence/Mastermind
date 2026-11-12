# Paper from T3 sessions: carriers, the canvas writer, and unclear results

This reference covers T3 Code sessions on any linked host. Host names, addresses and
install receipts live in the operator's private evidence, never in this repository.
Ask your lead which host holds Paper Desktop (the "Paper host"); do not guess.

## 1. Which carrier you have

Check your own tool list first. Paper capability depends on the carrier, not the model.

| You see | Where you are | Reads | Edits |
|---|---|---|---|
| `paper_inspect`, `paper_catalog`, `paper_read`, `paper_prepare`, `paper_edit` from a guarded server | Any host with the guarded registration | yes | yes, guarded (snapshot + operation id) |
| `paper_inspect`, `paper_catalog`, `paper_read` only | Any host with the guarded read profile | yes | no |
| Raw vendor tools (`get_basic_info`, `get_screenshot`, `write_html`, …) from the `paper` relay | The Paper host itself | yes | named canvas writer only, see §3 |
| No Paper tools, but T3 `delegate_task` and a linked environment for the Paper host | A remote host | via a short-lived child on the Paper host (§2) | only if your brief names you the canvas writer, via that child |

A missing tool family is a carrier fact, not proof that Paper is down. A transport
error is a transport observation. Report the narrow state.

## 2. Remote session without Paper tools: a short-lived child on the Paper host

Use `delegate_task` with `target.environmentId` set to the Paper host's linked
environment id, a named model, and a self-contained brief:

- the exact `fileId`, page ids and node ids to read (never "the active file");
- read tools only (`get_basic_info` with `pageId`, `get_tree_summary`, `get_screenshot`,
  `get_jsx`, `get_computed_styles`), unless the brief names that child the canvas writer;
- where to write outputs on the Paper host (a private 0700 folder), and to return the
  absolute paths plus the sha256 of every image;
- the held targets it must never touch.

Images then reach your host as T3 attachments, or through the guarded route once it is
installed. Do not move files by ad-hoc copy tools that bypass your host's permissions.
One child per logical operation. If the child's result is unclear, reconcile on that
same child or its thread. Do not start a second child to "try again".

## 3. The one canvas writer per document

- Each active document, or each partitioned page within a shared document, has **one
  named canvas writer**. The programme's design lead names that writer in the
  programme's design log (see the design-director memory convention). Everyone else
  reads, screenshots and critiques.
- Pages shared between programmes take one writer at a time. The two leads agree the
  hand-over in writing, in both design logs.
- Mark live work with Paper's working indicator, and release it with
  `finish_working_on_nodes` on your own artboard ids when you stop.
- Read other people's work by explicit `fileId`, `pageId` and `nodeId`. Never switch
  the active page or file another designer may be viewing. Never read or edit a target
  listed as held.

## 4. Guarded edits are the standard

Use the guarded `paper_edit` wherever it is available, and always on a remote guarded
route. Every edit is: fresh read, then `paper_edit` with `expected_snapshot` and a stable
`operation_id`, then a post-read and a screenshot of the changed artboard. A
`TOOL_SCHEMA_INCOMPATIBLE` (or similar typed refusal) for one tool is a qualification
gap for that tool, not a reason to switch carriers.

## 5. The raw `paper` relay on the Paper host

The vendor relay is the only local write path on the Paper host until a guarded local
registration replaces it. Its write tools may be used **only by the one named canvas
writer of that document**. Know what it lacks:

- **no snapshot guard**: it will write over a target that changed since you read it;
- **no operation id**: nothing correlates a call with its effect afterwards;
- **no unknown-effect classification**: a timeout or lost reply looks like an error,
  though the edit may have landed.

Rules that follow:

1. Read the exact target immediately before each write.
2. Make one small, bounded write per call (one visual group). Never batch unrelated changes.
3. After an unclear result (timeout, lost reply, an error after the call was sent, an
   unexpected response shape): **stop writing. Inspect the original target by node id,
   and screenshot it. Never repeat the call.** Record what you observed in the design
   log, with the state `EFFECT_UNKNOWN` until the inspection settles it. If the
   inspection cannot settle it, the target becomes held, and only the lead releases it.
4. Never call deletion, export-to-path, file-open or resource tools through the relay.
5. Do not use the relay for a document another writer holds.

## 6. Quick decision

- Need pixels or structure only: read through whatever carrier you have.
- Need to edit and you are the named writer: guarded `paper_edit` if present; on the
  Paper host without it, the relay under §5; from a remote host without guarded
  tools, a child on the Paper host under §2 and §5.
- Not the named writer: do not edit. Write a critique or a change request to the writer.
