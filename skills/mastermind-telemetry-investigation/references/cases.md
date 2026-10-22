# Telemetry investigation cases

## Several browsers freeze, another stays healthy
Input: several managed browser processes freeze at similar times; a separate
browser remains usable.
Compare affected process/resource/extension evidence and shared dependencies.
The healthy control narrows scope but does not prove an extension is the cause.
Do not kill unrelated processes or disable security controls as an experiment.

## Timeout after a write
Input: client times out after a request might have reached a server.
Preserve original request/process/generation and use the same owner's reconciliation.
Do not retry via another host or classify the event as a permission denial without
explicit evidence. A missing client reply is not evidence of no effect.

## Recovery after restart
Input: an authorized service restart restores the user action.
Report mitigation proven for that action. Retain the original error evidence and
state root cause unresolved unless the causal explanation is established.

## Empty telemetry query
Input: no spans are returned for an incident window.
Check time basis, exact identity, sampling and retention. Empty results do not prove
there were no errors. Keep missing observability explicit and use an available
independent source rather than fabricating a healthy state.
