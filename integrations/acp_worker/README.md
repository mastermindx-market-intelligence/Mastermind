# ACP SDK turn integration

This optional integration implements one read-only prompt using the official
`agent-client-protocol==0.12.1` SDK. It consumes a broker-owned exclusive stdio
pair and the existing `WorkerLaunchSpec`; it creates no process, queue, Runtime,
credential, session store, provider route or worker registration.

The driver negotiates protocol/agent expectations, uses only declared cached-token
self-authentication, requires advertised and observed model selection, refuses all
client filesystem/terminal/MCP/permission grants, bounds output, and observes the
original prompt terminal after cancellation. It never substitutes providers or
retries an ambiguous dispatch. The exact owning caller must retain the driver and
its `unsettled_tasks` for reconciliation. External cancellation is propagated after
cleanup; `last_candidate` records the observed terminal or uncertainty.

`AcpCandidate` is protocol evidence, not an accepted `CollectionReceipt`. The
existing broker must first establish process/binary/realm/workspace isolation,
bounded framing, and effective provider configuration. Its existing result/schema,
process cleanup, validation and Executive consumer remain mandatory after every
outcome. Provider-internal tools are NOT sandboxed by these client refusals.

Install `requirements/acp-worker.txt` only in the isolated integration environment.
The focused command is `python -m unittest discover -s tests -p test_acp_worker_turn.py`.
Missing the optional SDK produces an explicit skip, not ACP qualification.

Production registration and activation remain held by the existing HF/PF/Capacity
and provider-auth release gates. No Codex/Claude source or registry is changed.
