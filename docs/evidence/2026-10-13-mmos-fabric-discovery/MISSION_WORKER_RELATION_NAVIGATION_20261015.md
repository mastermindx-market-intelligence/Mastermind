# Mission worker relationships — source-qualified navigation

**Outcome: Source-built / not production released.** This delta is on existing Fabric Discovery PR #1426. Original base f5b63ab8e5e09ee532b57a0c09cbcf89650ee7f8 and previously merged inspector #1411 are preserved.

The existing MetaCeoOffice mission inspector now gives selected workers explicit View observed parent and View observed child controls. Only jobs already in the displayed 256-row slice and qualified as associated to the supplied resolved original Executive root can be selected. A root correlation label is not a worker. Cycles, malformed identities, duplicate identities, conflicted roots, unavailable sources and unassociated jobs cannot create a clickable relationship. When #1435's companion fix is integrated, an ancestor verified beyond the display cap is labelled as outside rendered rows rather than made into an invisible action.

This is pure local selection: no new Fabric status/catalog request, controller read, provider invocation, worker START, result fetch, acceptance or authorization change. Restrictive filter resets to All to show the real selected child. Changing the mission workstream/root clears previous selection and filter. English/zh-CN labels use keyboard-selectable buttons; no autofocus was attempted.

**Verification:** five new red-first DOM cases, full focused inspector suite 22 tests passed. Full current app suite **1,500 passed / one skipped / zero failed across 66 files**, and TypeScript/Vite build passed. Existing large bundle/mixed Tauri import warnings remain. Exact changed-source and test-log digests in peer JSON receipt.

**Unfinished:** #1426 Draft/Hold, independent review, current protected CI, signed-in browser proof, actual OS-principal-authenticated direct Fabric source and production installation. Ready C3 tunnel grants no OS user permission. Fleet #1425 and lineage #1435 remain separately owned.
