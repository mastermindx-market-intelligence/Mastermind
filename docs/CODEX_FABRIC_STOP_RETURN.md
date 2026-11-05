# Original-session Fabric return at Codex Stop

`integrations/session_bridge/fabric_stop_return.py` consumes an existing Fabric
operation at a native Codex Stop boundary. It never launches work or changes
provider, host, ledger, acceptance, permission or Runtime state.

Codex documents that a synchronous Stop hook returning `decision: block` creates
a continuation prompt in its invoking session. This is a supported path for a
result already retained when the parent stops. It is **not idle Wake**, and it
does not manufacture a RuntimeBinding, inherited grant, Worker or Attempt.

References: [Stop semantics](https://learn.chatgpt.com/docs/hooks#stop),
[hook trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks),
[common event fields](https://learn.chatgpt.com/docs/hooks#common-input-fields),
[background limitations](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background).

## One bounded operation

The reviewed hook definition supplies an exact original root, stable run ID,
installed adapter path and SHA256, and a pre-created private directory inside
that operation's evidence. Event input cannot choose these values. The handler
requires an actual `Stop` event with matching session ID, a valid turn ID, no
subagent fields and `stop_hook_active: false`. It emits no prompt for pending,
failed, uncertain, foreign-parent, already-adjudicated or unverified results.

The existing adapter remains the result and lineage owner. The handler reads
bounded local status/result, requires both root and parent to match, checks
stable status and result bytes, then exclusively creates and fsyncs an attention
attempt receipt. That receipt says `PREPARED_DELIVERY_UNCONFIRMED`: writing or
emitting it does not prove native delivery. An existing receipt, including a
partial or uncertain write, suppresses re-emission. There is no polling loop,
background watcher, replacement worker or automatic acceptance. Pending work is
left with its existing owner.

The continuation contains only fixed explanatory text, safe IDs, byte count and
result digest. Worker prose never becomes a privileged continuation instruction.
The original parent reads the retained result through the adapter and adjudicates
it normally. It records any qualified acceptance through the existing owner.

## Installation and activation

Install only through the current local source owner. Preserve existing hooks;
add a separate synchronous `Stop` command definition with timeout 25 seconds.
Do not modify an already-trusted hook to conceal a new behavior. The command
shape is:

```text
python3 /ABSOLUTE/REVIEWED/fabric_stop_return.py --root ORIGINAL_ROOT --run EXISTING_RUN --adapter /ABSOLUTE/INSTALLED/fabric_task.py --adapter-sha256 EXACT_SHA256 --receipt-dir /ABSOLUTE/OPERATION/private-attention
```

The receipt directory must be owned by the local user, mode0700 and not a
symlink. No hook code creates or changes this directory during a callback.
The configured adapter must be an owned regular file without group/world write;
source mismatch refuses attention. These checks protect a local consumer;
they are not authentication of an Executive grant or an arbitrary caller.

New or changed non-managed definitions require native review/trust. Never write
`trusted_hash`, use a hook-trust bypass flag, convert this into a managed hook,
or change accounts to skip that platform step. File installation is not proof
that an already-running Desktop has loaded the definition. Verify that on the
actual original session before dispatching a proof worker.

## Acceptance

The source checks are inert. Native acceptance additionally requires the exact
hook definition to be loaded/trusted, a newly authorized paid worker to run
through existing Fabric admission, a retained same-root/parent terminal result,
an actual Stop-created continuation in that original Desktop without a human
message, and useful parent consumption/acceptance. A manually invoked helper or
another CLI session cannot supply this evidence.

Wrong session, subagent event, stale/failed/uncertain lifecycle, malformed status,
changed result, prior outcome, prior uncertain attention and non-durable receipt
must not emit a continuation. Refused operations are never retried by this hook.
Native RuntimeBinding and arbitrary idle Wake require their separate real host
producer, writer and permission fences; this component makes no such claim.
