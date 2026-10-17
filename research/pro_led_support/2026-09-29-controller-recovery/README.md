# Command recovery repair for the incumbent Mastermind OS frontend

Operation: `mastermind-pro-led-project-delivery-20260929-sol-001` (#1056).
Target: #1046, exact head `17ed169f071af69205cf7a074db32a7cd148c4c0`.
Procedure/source pin: `8b08228e6126fe4654b04ec4cf1b85ee7b00af3a`.
State: **BUILT_NOT_PROVEN / incumbent adoption, review and installed proof owed**.

## Capability delta

Before: a host submit/read method throwing before it returns a Promise can leave
OperationController permanently OPERATION_BUSY. Check status never reads the
original operation again. Synchronous host re-entry can also issue a second read.
After this repair in the exact source qualification copy: Check status reads the
original operation and recovers without a reload, second submit or replacement key.

Both `recover` and `_submit` assigned `_inflight = run()` after invoking the host.
A synchronous throw lets `run` clear the join in its catch/finally before that
assignment reinstalls the completed Promise. `_tracked` is already null.
The private `_startInflight` helper registers the join before calling the host.
It preserves immediate invocation, existing epoch/identity checks, pending hints,
receipt validation and read-only recovery. No retry, timer, transport or state owner.

## Exact tested contribution

`repair.patch` changes one production file, adds nine controller regressions, and
adds three App interaction regressions. It does not alter the incumbent branch.
SHA-256: `d2d3a00c2ae79a741f7e7dabc3295b9b5929baba89cfcc711465c4933a5b076a`.
Original controller blob: `d3bf12ac8936077778ddfc44121364cf2d468b5b`.
Repaired controller blob: `72b3be184cc8e7a730c958844eeb1386f3e9e8b9`.
All 77 original app files were compared; only controller and App test differ.

Unit RED: 7 failures / 2 passes on original; GREEN: 9 passes on repaired source.
App RED: Check status fails to read the original operation; GREEN: exact read,
correct navigation, one submit and pointer clearance. Uses real React/App/controller
with explicit injected host ports; it is not a live service/provider canary.
Conversation RED: 2 failures; GREEN: 2 passes, including draft retention and
exact message recovery after a synchronous read failure without another send.
Final full frontend: **558 PASS / 1 inherited skip**, 13 test files.
TypeScript, web build and native-mode Vite asset build: PASS. Byte-verified forward/apply/reverse patch roundtrip: PASS.
The existing Tauri static/dynamic import warning remains. Evidence details: `evidence.json`.
The added App test's intermediate TS2339 matcher error was corrected and all checks rerun.

## Incumbent integration

Read the patch and verify the current controller preimage before application.
Use the existing #1046 source carrier; do not create another frontend branch or owner.
Run `git apply --check <repair.patch>`, apply only after source-custody checks, then
`npm --prefix app/mastermind_os test`, `npm --prefix app/mastermind_os run typecheck`,
and `npm --prefix app/mastermind_os run build`. Current-head review remains required.

No independent review, repository-wide Python, native Rust, installed app, real
transport, automatic Web re-entry, or full #1056 acceptance is claimed.
No provider, Runtime, service, credentials, Paper, #633, #956 or foreign workspace changed.
