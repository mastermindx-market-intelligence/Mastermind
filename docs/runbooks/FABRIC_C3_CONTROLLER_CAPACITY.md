# C3 controller tracking capacity and generation-local replay fencing

The facade's controller tracking is separate from worker admission, provider
capacity, task budgets, retained adapter results and acceptance. A returned
controller PID proves none of those later facts. No quota or execution-admission
policy changes here.

The prior source checked `attempted.size >= 512`. That counted every request
intent ever dispatched by the backend process, including terminal refusals and
settled controllers, and never removed an ID. It exhausted one process generation
after 512 attempts even when no controllers remained active. Its only capacity
check also preceded an async preflight, allowing 513 concurrent distinct calls
to pass it. Restarting reset that in-memory fence; a successful later request
therefore did not prove a lasting repair or settle any older operation.

## Separate bounded responsibilities

- **512 unresolved tracking reservations:** includes request preflights,
  dispatched controllers and no-PID/UNKNOWN requests. A reservation is made
  synchronously before request preflight awaits. Only a proved no-dispatch
  preflight error can refund its own temporary reservation directly.
- **8,192 exact attempted identities:** an internal anti-replay metadata bound.
  IDs are copied independently from the larger request and never deleted.
  With the existing maximum 128 UTF-16 code units, identity text is at most
  2 MiB plus bounded Set overhead. This is not permission for 8,192 workers or
  a new provider quota. At the memory ceiling, `GENERATION_TRACKING_CAPACITY`
  refuses new attempts without dispatch or evicting any old ID.
- **Existing process/result owners:** Desktop Commander still owns process
  activity and output retention. The installed Fabric adapter owns run status,
  results, admission and acceptance. The facade adds no ledger or background
  retention manager.

This exact-ID Set exists only in one backend process generation. It is never
serialized, reconstructed or presented as cross-restart protection. The
incumbent adapter's durable evidence and original uncertain effects remain
controlling across a restart. An old interrupted request must not be submitted
again merely because a new backend process has no in-memory record.

On Node v26.5.0, an isolated maximum-length 8,192-ID Set measured approximately
1.38 MB of additional JavaScript heap including its container. That measurement
is platform-specific, not a universal RSS bound; the structural count/text
bounds above are the implementation contract. Controller maps have at most
512 reservations and bindings. No unbounded identity or timer collection is
introduced.

## Reclaim only expired, authentically settled tracking

A normal root-bound status/wait/result observation may nominate a terminal
controller for later checking. It does not release tracking. When a new request
finds all 512 slots occupied, its capacity guard examines at most four nominees
and performs at most one fresh captured adapter status observation. A bounded
cursor avoids repeatedly selecting only the same retained nominees. At most
512 in-memory records are considered for nomination; there is no background
sweep or provider call.

A reservation and its PID binding may retire only when all three proofs hold:

1. Fresh captured status from the same installed adapter has the exact root,
   state `TERMINAL` or `TERMINAL_FAILURE`, a valid nonnegative exit code and no
   effect-unknown signal or unconfirmed continuation.
2. The same incumbent process owner's closed `list_sessions` metadata shows
   that PID is not active.
3. That owner's `read_process_output` returns the exact native error indicating
   no retained session for that PID. Worker text resembling completion or an
   expiration message is never accepted as this proof.

The output check uses absolute offset 1, length 1 and timeout 0, avoiding output
cursor changes and bulk retrieval. Inspected output is not returned to the new
requester. A retained output remains bound and readable through the original
run/root/PID interface. Missing/malformed/unavailable metadata, NOT_FOUND,
ACTIVE, UNKNOWN, no-PID and unconfirmed states keep their capacity reservation.
The exact ID fence remains even after a binding has legitimately expired.

A reused native PID invalidates the older output binding rather than granting
access to another operation's process. It does not authorize retirement,
replay or a replacement worker; affected unresolved reservations remain held.
Concurrent reclamation must still compare the exact reservation and PID binding
before removing anything, and the new reservation check remains synchronous.

## Source validation and host release remain separate

The offline injected-engine tests exercise the real facade's protocol decisions.
They do not establish live C3 settlement, retention or available Fabric capacity.
Two tests discriminate the original source: concurrent 513 admission exceeded
512, and sequential settled/expired controllers blocked the next unique ID.
The repair keeps all former IDs fenced, keeps adverse/UNKNOWN/live/retained
cases closed, and exercises the bounded history ceiling and reclamation races.

The existing `private_service.py fabric-backend-release` producer is the normal
release path for the fixed enrolled C3 account `fabric-c3-570f6f34` on port45280.
It requires an exact already-merged protected commit, immutable backend bytes,
expected sealed manifest and reviewed preview-plan digests. It preserves the
restricted profile, port, dependency tree and SDK binding, and changes only the
selected backend path and associated hashes. Apply refuses a loaded service.

This source change does not authorize stopping or restarting that service.
Before a host selection, its current owner must qualify the actual configured
engine protocol/seal and original-generation controllers and uncertain effects.
The locally installed default process-owner source keeps its last 100 completed
outputs; that source observation alone does not prove the deployed C3 engine or
any specific old handle has expired. Never clear a Set, evict live/UNKNOWN work,
reuse a terminal ID, retry an old request or deploy to obtain admission.

C3 gateway tracking and M2 Fabric host telemetry are separate. Repairing or
releasing this backend does not clear a host admission refusal, fix native
collector selection, prove a paid worker started or transfer an old operation.
