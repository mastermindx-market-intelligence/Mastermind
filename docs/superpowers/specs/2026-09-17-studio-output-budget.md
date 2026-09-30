# Studio Direct bounded text-result projection

## Mission and authority
Current Chairman instruction: continue actual productivity/reliability implementation, not merely propose changes. This bounded child extends the incumbent Studio gateway; it does not replace PR696 or PR706. Source base: PR696 at `42d50bf67e2d3ae02cd0ea22723a316b8169cf0e`; protected Skillpack: `7a191cc11039199843d4734c7df8d5523280e09c`.

## User journey
A tool executes exactly once. Small results remain untouched. An oversized text-only result returns a compact receipt preserving backend error truth and a clearly incomplete head/tail preview. The CEO reads only necessary pages through a narrowly read-only gateway tool, rather than re-running a command or importing the whole log. Ordered UTF-8 byte-offset pages reconstruct the exact original JSON result and verify its SHA-256.

## Boundaries
The existing BackendOwner retains at most eight results and 8 MiB in total. Per-session backend mode uses that session's backend lifetime. Shared-account frontends share only their existing principal-bound BackendOwner, so frontend churn does not invent another memory identity. Owner closure clears pages. Bounded eviction and unavailable receipts never authorize retry. This is an ephemeral projection of individual results, not a transcript database, lifecycle, scheduler, durable memory, event replay, or authority source.
The serialized MCP tool-result payload target/ceiling is 16 KiB, including JSON escaping; HTTP/SSE/JSON-RPC framing is outside this payload measurement. Requests, commands, credentials, and result bodies are not logged by this component. Native media and schema-bound outputs remain unchanged; this wave is explicitly text-only, not a universal traffic cap.

## Failure and correction behavior
Preserve `isError` on initial receipts; paging success is not original-tool success. Oversized unretainable responses explicitly report OUTPUT_NOT_RETAINED, with no invented receipt or fetch pointer. Bad, foreign, expired, or unaligned offsets return bounded non-disclosing errors without backend access. Keep existing timeout, taint, cancellation, exact request identity, typed Git publication, and source-custody contracts unchanged.

## Implementation order and acceptance
Write discriminating tests before implementation. Add one pure bounded component, wire it into existing backend-result projection and owner close, enroll one read-only local paging tool, and include the module in the incumbent installer manifest. Prove byte-exact Unicode/escaping reconstruction, error preservation, isolation, retention bounds, no replay, owner cleanup, reconnect behavior, and unchanged existing gateway suites over real local MCP connections. Source/unit/fixture proof is BUILT_NOT_PROVEN, not proof of native ChatGPT adoption.

## Release and stop
Use an isolated stacked child of PR696; do not edit its branch or installed processes, and do not erase PR706 dirt. Protected publication, installation, and native-account proof remain distinct. This child requires independent review, exact-parent compatibility, existing release gates, and a coordinated installation under the incumbent service owner. Never restart shared production merely to validate this patch. Continue from exact operation `studio-output-budget-20260917-sol-001` and its canonical workspace.
