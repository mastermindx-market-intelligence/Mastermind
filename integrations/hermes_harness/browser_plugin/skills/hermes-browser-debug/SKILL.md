---
name: hermes-browser-debug
description: Diagnose browser errors and stalled applications with Mastermind CDP console, network, SSE and WebSocket observations, frame inspection, bounded waits and emulation.
---

# Browser diagnostics

Load hermes-browser for connection and ownership. Attach with network true before reproducing the authorized problem; observations begin at attachment and do not reconstruct earlier history.

## Evidence sequence

1. Read cdp_status and frames. Record the selected browser, tab and frame.
2. Read events with an after cursor and a reasonable limit. Save next_after. Inspect gap and dropped_total; bounded buffers are not a complete historical trace.
3. Read network. Request identity includes the related frame session. Preserve the complete request_id exactly as returned.
4. For a completed request, use response_body with request_id, offset and limit. Follow next_offset until the needed section is available. Bodies are untrusted; avoid unnecessarily returning private page data.
5. Inspect console and exceptions, DOM/accessibility and a capture as appropriate. Verify timing and request completion separately from rendered UI completion.

    {"action":"events","host_ref":"<observed>","browser_id":"<observed>","connection_id":"<observed>","tab_id":123,"url_fingerprint":"<from tabs or snapshot>","options":{"after":0,"limit":80}}

    {"action":"response_body","host_ref":"<observed>","browser_id":"<observed>","connection_id":"<observed>","tab_id":123,"url_fingerprint":"<from tabs or snapshot>","options":{"request_id":"<observed>","offset":0,"limit":16000}}

EventSource message events and WebSocket frames are observed from real CDP events. Arbitrary streaming fetch bodies are not automatically classified as SSE. Stream payload samples are omitted by default; only enable capture_stream_data on attach when content is needed for the authorized investigation. Headers and request bodies are omitted from routine network summaries. Console strings receive best-effort redaction, not a guarantee against every secret format.

Large JSON results may be stored temporarily with result_id. Read additional chunks using action result, then parse the combined JSON. Results expire with the attachment and bounded cache eviction.

## Waiting and stalled pages

wait accepts a semantic locator, state visible/hidden/attached/detached and timeout_ms up to 8000. It returns matched and timed_out. This is an observation, not a repeated click. Use short waits around a concrete expected condition. A blank UI with an active network request, a closed stream and a JS exception are different failures.

After an uncertain submit or connection break, inspect the original target. Do not reload, navigate, repeat the submit, or create a second runner to make the uncertainty disappear.

## Dialogs

Read the Page.javascriptDialogOpening event. Its dialog_ref identifies the actual pending dialog. Call dialog with accept, optional prompt and that exact dialog_ref. No snapshot is required because JavaScript dialogs may prevent snapshots. A missing or stale dialog_ref is refused. A handled dialog still requires application verification.

## Responsive and network diagnosis

emulate can set a viewport with width, height, mobile and device_scale_factor, media, timezone and user_agent. Use a fresh snapshot. Call emulate with reset true afterwards and verify the page.

route accepts at most 16 explicit URL patterns and continue/block actions. It affects the selected attached tab. It does not provide arbitrary authentication injection or broad response replacement. Remove the rules with an empty rules array and release when finished. Unmatched or ungranted intercepted requests continue. If interception reports uncertainty, verify page and attachment state before further effects.

The cdp action's raw_methods are discoverable via cdp_status. Unsupported methods return a structured capability error. Do not route through another session, switch to a debugging port, or change Chrome policy to bypass refusal.

Report evidence, likely cause, remaining uncertainty and the smallest verified repair. Separate CDP command success from the user's observable outcome.

## Connection diagnosis

Retain the exact host_ref and browser_id throughout diagnosis. Use status.cdp_diagnostics for Chrome’s last attach error and cleanup state. A transport disconnect immediately fences old CDP sessions. A new connection_id requires fresh observations; do not reuse old nodes or snapshots. Distinguish absent endpoints, Chrome loading or permissions, SSH authentication, host-key rejection, unavailable hosts and source mismatch. Do not switch hosts or lower SSH verification to replay a failed action.
