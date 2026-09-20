# Mastermind OS shared product

This package is the read-only React/TypeScript consumer for the frozen
`mastermind.mission_workspace.v1` contract. Its hierarchy and visual
composition follow the approved Mastermind #702 reference workspace, and its
decoder follows Mastermind #704 section 6.1.

The app starts at Today, uses real
`mastermind.chairman_control_room.v1.work[].agent_os` records for Programs,
and joins a Program to exactly one
`autonomy.responsibilities[]` row by `responsibility_ref`. A zero or
multiple-row join stays `UNKNOWN` or `CONFLICT`; it never selects a recent
root. Opening a mission requires exactly one validated `work_ref` and
`root_job_id` pair. The mission document is decoded with closed top-level and
nested shapes before any source value reaches the DOM.

Tests may inject an in-memory `window.MastermindMissionHost.readMission` port
to exercise lifecycle fences, but this package installs no reader or network
route. The native Tauri shell invokes only its fixed `readiness` command and
reports `UNCONFIGURED / BUILT_NOT_PROVEN`.

The current product has no qualified Steward endpoint, viewer grant, connected
reader, broker integration, conversation lifecycle, or content store.
Conversation therefore remains `UNAVAILABLE`. The app does not enroll a
viewer, mint a grant, read protected content, send a command, or infer
acceptance.

## Checks

```sh
npm ci
npm run typecheck
npm test
npm run build
```

The dedicated hosted workflow runs those four frontend checks. It performs no
native signing, packaging, deployment, or release.

## Native build receipt

A native build must bind the exact committed source revision and an operator
chosen build identity at compile time:

```sh
SOURCE_REVISION="$(git rev-parse HEAD)"
MM_SOURCE_REVISION="$SOURCE_REVISION" \
MM_BUILD_IDENTITY="mastermind-os-local-<receipt>" \
CARGO_BUILD_JOBS=2 \
CARGO_TARGET_DIR="$PWD/.cargo-target" \
npm exec tauri build -- --bundles app
codesign --force --deep --sign - \
  "$PWD/.cargo-target/release/bundle/macos/Mastermind OS.app"
codesign --verify --deep --strict \
  "$PWD/.cargo-target/release/bundle/macos/Mastermind OS.app"
```

`build.rs` refuses a missing or malformed receipt. The resulting readiness
payload contains the package version, full source revision, build identity,
transport state, and proof state. It never runs Git, a shell, or another
process at runtime.

The macOS bundle is an explicitly ad hoc signed local artifact. The strict
whole-bundle verification must succeed before its hash is recorded. Replacing
an existing copy is a manual filesystem action outside this package; the
package has no updater.
Rollback likewise means manually restoring a previously retained bundle whose
hash and readiness receipt were recorded. No notarization, automatic update,
installed service, authenticated source read, or product acceptance is claimed.

Approved references:

- `2ec7ea59f8b403d3cf0a31edff1b90af80685dee:research/mastermind_os/reference_workspace.html`
- `06ef2aea5843874341ddb4261b5a9fe9f411e3c8:docs/superpowers/specs/2026-09-16-mastermind-os-mission-workspace-consumer-freeze.md`
