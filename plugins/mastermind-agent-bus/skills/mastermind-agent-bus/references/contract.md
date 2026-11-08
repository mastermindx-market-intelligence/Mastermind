# Current Mastermind Executive tool contract and limits

**Source of truth**: `mastermindx-market-intelligence/Mastermind` protected source at the compatible pin selected by the executing session; deployed metadata can differ. This is a skill reference, not a new API or permission.

| Existing MCP tool | Input | Interpretation |
|---|---|---|
| `session_targets` | `{ "kind": "hermes_meta" }` or `{ "kind": "hermes_secretary" }` | Current scoped exact target projection; might be unavailable until native role enrollment/tool refresh |
| `session_send` | `{ "target_ref": "<row.target_ref>", "operation_key": "<row.continuation_operation_key>", "instruction": "...", "stop_condition": "..." }` | Original owner handles commit and native attention; do not assume answer or consumption |
| `session_reply_read` | `{ "operation_key": "<same original key>" }` or `{ "read_ref": "<actual original read_ref>" }` | Read-only original result; absence/error not proof of queued, sent, failed or not-yet-existing operation |
| `session_reply_references` | Use only exact authorized selector exposed by current host | Read-only original references, not global ChatGPT archive |
| `session_summon` | `operation_key`, `objective`, `department`, `priority`, `execution_profile`, `workstream`, permitted write/test fields | Governing Executive admission / Capacity-selected provider; not raw DeepSeek harness pin |

Hermes original reply has an `admission` object with `status` (`queued`, `started`, `unknown`, `terminal`), `native_status` (`OBSERVED`, `ADMITTED`, `NOT_SUBMITTED`, `REFUSED`, `EFFECT_UNKNOWN`, `UNAVAILABLE`) and possibly `answer` / `successful`. A genuinely returned terminal answer requires `native_status=OBSERVED`, `admission.status=terminal` and original answer bytes. `parent_consumed=false` means Web read is not acceptance or parent consumption.

Only `hermes_meta` and `hermes_secretary` are currently public native target kinds in protected source. The full Hermes local bot roster (chief of staff, Engineering, Marketing and other profiles) is not automatically authorized or exposed to a Web caller. Expand through the existing native enrollment, composition and principal-projection owners, not through free-form bot IDs.

MCP Events upgrade: For an **authorized ChatGPT Work chat or dot**, a correctly installed Executive MCP endpoint can advertise `events` and `events/list` (`session.reply_committed`), support `events/subscribe` / `events/unsubscribe`, and deliver signed, callback-verified webhook events using the existing Runtime subscription and delivery owners. This is different from ordinary Instant chats, which have no guaranteed unsolicited wake-up. Ask Work to monitor the **exact original request_ref**, and to call `session_reply_read` upon delivery; the event summary is untrusted data. The existing event path currently covers canonical Agent Dialogue replies, and must **not** be presented as proven direct Hermes native push until the Hermes original-result integration is installed and a real Work callback is received. Source integration: `integrations/session_bridge/{web_reply_event_rpc.py,web_reply_event_asgi.py,installed_reply_events.py,reply_event_host_composition.py,runtime_reply_delivery.py}` and `docs/EXECUTIVE_MCP_REPLY_EVENTS_OWNER_INTEGRATION.md`. See https://developers.openai.com/plugins/build/mcp-events.
