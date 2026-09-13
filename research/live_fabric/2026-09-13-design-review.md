# Live Fabric design review and verification limits

**Operation:** `mastermind-live-fabric-design-freeze-20260913-sol-001`.  
**Classification:** author self-review and bounded design research. **Not independent review.**

This review covers the written architecture, delivery program, source/OSS ledger and 72-case acceptance matrix. It makes no software, installed-client or production claim. The final packet remains SPEC_ONLY until its appropriate acceptance/protection; even protected architecture remains distinct from built or proven capability.

## 1. Material changes from the conversational sketches

| Finding | Why the earlier idea was insufficient | Resolution in the written packet |
|---|---|---|
| A beautiful observer is not an autonomous organization | The UI could faithfully show an unserved obligation forever | Separate closed-GUI continuation/recovery milestone through existing owners |
| Dead-owner custody can become circular | Requiring a vanished session to acknowledge its own release can permanently stall work | Require accepted evidence-based recovery alternatives and finite escalation, without electing a new owner by recency |
| Lease expiry is not a physical write fence | Old processes can retain direct filesystem or provider access | Prove actual effect-sink fencing/workspace isolation before successor authority |
| One status dot loses critical meaning | Presence, lifecycle, consumption and capacity are different facts | Five display categories using existing owner states; no new lifecycle engine |
| Runtime RUNNING was overstated as active execution | The recorded lifecycle can outlive provider progress | Separately qualify provider activity; display recorded-running honestly |
| Singular query cannot enumerate a fleet | Current Steward deliberately rejects multiple runtime candidates | Preserve it; consume existing plural #508 producer family |
| The proposed stream ignored the real API | Current local read requires a custom header; bare EventSource cannot set it | Existing cached authenticated fetch first; owner-approved fetch-stream path later |
| A dependency does not establish server architecture | sse-starlette in the project does not turn stdlib HTTP into ASGI | No framework replacement hidden inside the GUI build |
| Chrome proof does not qualify a native WebView | Existing B5 profile and generic qualification seam are specific/unproven | Separate WKWebView/client proof; Mac viewer initially read-only |
| Tauri is not a privilege boundary by itself | Bundled origin and native IPC differ from local web; nonce is not local-user authentication | Fixed-target minimal native adapter, no generic proxy/shell, existing auth owner for actions |
| Dagre was recommended without its nested-edge limitation | Cross-subflow edges can break its advertised simple integration | Compartment layout with visual cross-group edges; measured ELK fallback only |
| Client idempotency keys do not settle a semantic race | Two tabs can generate different keys for the same single-consumption obligation | Atomic owner-side semantic applicability/consumption plus stable request-key handling |
| Complete inventory was being confused with complete probes | Lost probes do not necessarily make known inventory count unknown | Separate inventory/probe/history coverage; preserve exact totals only for the proposition proved |
| The early DAG advertised infrastructure as releases | A reducer or fixture graph alone does not help Chris with real work | Capability-level V1 through V5 plus web/Mac/actions/studio/fleet milestones |
| Old #424 debt was repeated after supersession | Historical PR text could force an unnecessary repair or dead-owner wait | Current #521 metadata/protected supersession closes that obsolete dependency |
| OSS survey missed closer company-facing donors | It emphasized generic observability while omitting a stronger company-UX match | Paperclip/Builderz added; Paperclip exact source excerpt and license inspected; no wholesale fork |
| Two unrelated Lattice projects were conflated | Names alone can transfer incorrect feature/license claims | Identify DahunHan/lattice exactly; unrelated LatticeNet claims excluded |
| Reference UX could leak sensitive content | Rich artifacts, terminal output and embedded browser pages are untrusted | Serialization redaction and isolated previews before any privileged rendering |

The current CSP must also be retained and exercised with the actual React Flow/build output, dynamic layout styles and any worker assets. Do not add global unsafe-inline/eval or broad connect permissions merely to make a component render. Any necessary narrowly scoped style/asset treatment belongs in the existing security/server review. This is an integration obligation, not a claim that the not-yet-built bundle already passes CSP.

## 2. Bounded two-client experiment actually executed

A standard-library Python experiment enumerated **252 order-preserving interleavings** of two clients, each with five steps: prepare, admit, dispatch, receipt read and repeat dispatch. Both clients had different request keys but targeted the same single-consumption semantic obligation and binding epoch. Dispatch used an assumed committed no-replay marker; reply loss did not erase it.

Observed result:

| Design in abstract model | Schedules with two effects | Schedules with exactly one effect |
|---|---:|---:|
| Request-key handling only, without semantic guard | 252 | 0 |
| Atomic semantic admission guard plus dispatch marker | 0 | 252 |

This motivates LF-T025. It does **not** satisfy LF-T025's real integration/production requirement. Atomic admission, persistence and effect fencing are assumptions of the experiment. No Mastermind SQLite transaction, provider, credential, host, process, browser or transport was exercised. It is not a proof of universal exactly-once effects. Legitimate distinct messages are not required to share one semantic obligation.

Reproduction of the bounded model:

```python
from itertools import combinations

steps = ('prepare', 'admit', 'dispatch', 'receipt_read', 'repeat_dispatch')

def schedules():
    for selected in combinations(range(10), 5):
        selected = set(selected)
        counters = {'A': 0, 'B': 0}
        result = []
        for slot in range(10):
            actor = 'A' if slot in selected else 'B'
            result.append((actor, steps[counters[actor]]))
            counters[actor] += 1
        yield result

def run(schedule, semantic_guard):
    admitted, dispatched = set(), set()
    consumed, effects = False, 0
    for actor, step in schedule:
        if step == 'admit':
            if not semantic_guard or not consumed:
                admitted.add(actor)
                consumed = True
        elif step in ('dispatch', 'repeat_dispatch'):
            if actor in admitted and actor not in dispatched:
                dispatched.add(actor)
                effects += 1
    return effects

cases = list(schedules())
assert len(cases) == 252
assert all(run(case, False) == 2 for case in cases)
assert all(run(case, True) == 1 for case in cases)
print('252 schedules; key-only double effects=252; guarded double effects=0')
```

The executed sandbox command was `python /mnt/data/live_fabric_packet/abstract_race_check.py`, exit 0. Its saved JSON result explicitly classifies itself ABSTRACT_DESIGN_EXPERIMENT_NOT_RUNTIME_PROOF. The code above expresses the same transition model; it is included as research prose, not application implementation.

## 3. Verification performed and limits

Performed:

- Fresh GitHub protected-ref reads and same-pin compatible procedural reads.
- Exact-source reads of the Control Room API/cache/validity boundary and the singular Steward query.
- Current PR metadata reads for #508, #546 and merged #521, preserving body-versus-lifecycle differences.
- Direct Agent OS workstream, README and actual handoff-schema reads at the pinned Macro revision.
- Source inspection of Paperclip OrgChart lines 1-205 at a fixed commit, plus its MIT license; Builderz license read separately.
- Current primary documentation checks for layout, EventSource and Tauri boundaries.
- The bounded abstract concurrency experiment above.
- Author inspection of the written architecture for contradictory ownership, capability inflation, placeholder owners, duplicate systems and circular gate assumptions.

Not performed:

- No product implementation, build, package installation or frontend runtime test.
- No real provider call, exact conversation wake, runtime admission, credential read or service mutation.
- No complete local repository test suite or production browser/WebView proof.
- No independent architecture or code review; another account is not presumed independent.
- No executed 72-case acceptance campaign; all cases remain REQUIRED / NOT_EXECUTED.
- No installed source, live fleet count, quota, model-mode or machine resource attestation.
- No complete donor source/security/license audit or adapted component benchmark.

The intended Mac ping timed out after device discovery. This is evidence of an unavailable bounded connectivity probe, not proof the machine or agents were dead. A direct sandbox attempt to retrieve newly published raw artifact bytes also failed because external resolution was unavailable; GitHub connector publication/readback remains the source path. No repository or host effect was retried through a different carrier.

## 4. Review questions that cannot be settled by prose

The independent reviewer should challenge whether a real authentic mission can be produced at the first consumer boundary without broadening a reserved source scope; whether semantic single-consumption is enforced atomically at the real effect owner; whether unavailable-owner recovery has a safe physical fence; and whether the actual renderer obeys CSP and the intended browser/WebView validity model.

The reviewer must distinguish a missing optional capability from a missing safety premise. A missing remote browser preview may be hidden. Missing action authentication cannot be hidden behind a disabled-looking button that the backend would still accept.

A genuinely absent upstream owner primitive requires one finite owner-delivered extension and an explicit acceptance test, not a second Live-owned primitive. The design also fails if it becomes a permanently blocked observer that cannot reach the separately declared autonomous outcome.

## 5. Completion and next action

This wave has created a reviewable architecture and delivery packet, not working harness software. Records publication, records protection, implementation, installation and final acceptance remain separate.

The next action is the written-spec review and exact-head independent architecture adjudication. After acceptance and current source/path reconciliation, produce the executor-ready plan for LF-V1: real owner producer through the existing compositor to the visible mission graph/list/inspector and evidence. Do not reopen #424, mint another WS, advertise a fixture-only UI as shipped, or place a worker merely by posting to an account with no verified receiver.
