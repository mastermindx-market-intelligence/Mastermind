# Mastermind OS shared product

This package is a source-only React/TypeScript consumer of the frozen `mastermind.mission_workspace.v1` document. Its visual composition follows the approved #702 reference workspace while it renders only host-provided projection fields.

The browser uses a fixed, same-origin `GET /api/mission?work_ref=…&root_job_id=…` only when its host supplies the process-local CCR nonce in memory. A native host may instead provide `window.MastermindMissionHost.readMission` for that same fixed selection. `controlRoom` is optional host-provided `mastermind.chairman_control_room.v1` data used only to list its canonical `work` cards. It has no arbitrary remote URL, persisted credential, transcript store, provider control, filesystem access, or mutation controls.

When the endpoint, selection, or host bridge is unavailable, the workspace displays `UNAVAILABLE`; it does not substitute examples or infer zero work. Conversation is shown as unavailable until the incumbent qualified reader supplies a safe product integration. Source build and the optional Tauri shell are `BUILT_NOT_PROVEN`: neither establishes an installed service, authenticated product access, WKWebView behavior, signing/notarization, or product acceptance.

Run `npm install`, then `npm run typecheck`, `npm test`, and `npm run build`. The reference attribution is the approved source object `2ec7ea59f8b403d3cf0a31edff1b90af80685dee:research/mastermind_os/reference_workspace.html`.
