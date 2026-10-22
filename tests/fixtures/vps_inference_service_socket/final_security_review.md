**SCOPED CLEAR — both previously reported medium-severity defects are resolved in this frozen source. No new actionable causal findings in the reviewed repair.**

All **seven supplied SHA-256 digests matched at the beginning and end** of this review. Checkout HEAD remains the specified base, `85f34140f3f68c73b046263f1308fef48e4bd8a7`. All seven frozen files compiled in memory.

| Prior finding | Verification | Disposition |
|---|---|---|
| Non-consuming inference peer could retain the handler through `drain()` or `wait_closed()` | The successful service-response path applies `delivery_timeout=2.0` **after** `inference_ingress.handle_frame()` returns. A delivery timeout aborts the transport. Inference-peer closure independently bounds `wait_closed()` and aborts on timeout before removing the handler from the drain set. See [response delivery](./control_plane/executive_service.py:4941) and [handler teardown](./control_plane/executive_service.py:5293). | **Resolved** |
| UID 0 accepted under a non-root Executive | Binding construction now requires an exact integer strictly greater than zero. Root, negative UIDs and Boolean values are rejected before the existing Executive/Operator/C1/Web identity-collision checks. See [UID validation](./control_plane/executive_service.py:2031). | **Resolved** |

Independent in-memory probes of the frozen code also confirmed:

- **No timeout cancellation of canonical work:** pending canonical work remained active and registered beyond the probe’s transport deadline. Delivery and closure deadlines took effect only after it settled.
- **Teardown completes:** stalled delivery, stalled closure, and both stalled together each caused transport abort and eventual handler removal.
- **Effect uncertainty is preserved:** lost replies, post-send cancellation, and post-effect backend errors remained `EFFECT_UNKNOWN` for the original operation.
- **Reply budgets remain enforced:** a large in-budget reply received bounded delivery; an oversized reply produced a bounded refusal without returning a partial answer.
- **Incumbent behavior remains separate:** the exercised C1/Web paths denied service frames and acquired no new delivery or closure deadline.

The five earlier fixes remain unchanged in the relevant code. I found no new authorization, duplicate-reconciliation, peer-identity, socket/ACL, or authenticated direct-read regression introduced by these two repairs.

**Limitations:** These were source inspection and in-memory probes with dependency/transport doubles and shortened test deadlines. They did not exercise kernel backpressure, actual OS UID isolation, installed ACLs, production namespace custody, or provider execution. I inspected the new regressions but did not rerun the file-writing/socket/SQLite suite; its wider result remains outside this review’s independently verified evidence.

No files were modified. The refused Supervisor and Bot repair surfaces remained untouched. No network, credential, provider, child-agent, installation, or production actions were taken.
