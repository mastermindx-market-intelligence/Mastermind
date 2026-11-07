# Hermes-backed mobile web delivery

Operation: `hermes-mobile-web-20261107`.
Parent: `WS:EXECUTIVE-ECOSYSTEM-COMPLETION`; supplement to this directory's README and HANDOFFS, not a new project/task/runtime registry.
Assignment: current Chairman request to implement secure mobile web access to the existing M2 Hermes Meta-CEO, Secretary and other profiles, preserving desktop streaming, history and tool rendering.
Procedure: Mastermind protected `4fb0d3825b5b4b4439e65e7382660112b7c2ef8c`, Skillpack 1.0.1/bootstrap 1. A later local origin/master comparison changed only BOOTSTRAP_KERNEL among the relevant procedure paths; continuation emphasis is compatible. No prior modifying operation is being transferred.
Source carrier: this isolated GitHub branch, `sol/hermes-mobile-web-20261107`. Installed-host changes use the original authorized Studio Direct local M2 carrier. Source publication is not protected release or production acceptance.

## Outcome and completion ruler

The Chairman can reach the existing M2 gateway from a phone, authenticate with an existing supported identity, select Meta-CEO or Secretary, receive a real streaming reply with desktop-equivalent formatting, reopen the same conversation and reconnect without duplicate sends. Native desktop operation and other exposed services must remain intact. Show what is actually tested; a mobile-sized browser is not physical iPhone acceptance.

## Reuse decision

Adopt the installed Hermes browser build of its Desktop renderer and native gateway. This is the actual shared renderer, not a hand-built chat clone. Preserve Hermes's profiles, sessions, memory, queues, tool rendering and sign-in. Do not introduce a DeepSeek client to translate Hermes's protocol, a second scheduler, another identity store or a new agent runtime. The existing Mastermind OS and DeepSeek PR #2177 remain separate live integration surfaces and must not be overwritten.

Private HTTPS through the existing Tailscale service is the preferred first connection. Its root and Studio MCP routes already exist and must be preserved; use an unoccupied dedicated HTTPS port after fresh preflight. Keep the Hermes listener on loopback and pin its external URL so Hermes's own authentication gate stays enabled. No public Funnel, router port-forwarding, anonymous proxy, bearer credential in a URL, or disabled origin/TLS/auth checks.

Existing Nous authentication is locally reported available. Reuse Hermes Web Access's own OAuth client registration, separate from dashboard registration. A valid local login is not proof of mobile sign-in. Human-only authentication/consent remains explicit if encountered.

## Observed starting point

- Installed Hermes: v0.23.0, source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
- Browser app is disabled and `apps/desktop/dist-webapp/index.html` is absent.
- Default gateway and existing staff/specialist profiles are present. Preserve their provider choices.
- Tailscale reports Running, online, and no health complaints; existing HTTPS routes must remain unchanged.
- Installed donor has unrelated live changes in agent fallback/session files. Do not reset, stash or edit them. Browser build uses the donor's isolated build workspace so native Desktop dependencies are not pruned.
- Studio fleet selection earlier returned NOT_APPLIED/FLEET_ROUTE_PREFLIGHT_REFUSED. No fleet-selection retry or host rebinding. Existing local Studio Direct calls independently identified the M2 and succeeded; this does not establish fleet routing readiness.

## Delivery nodes

| Node | Work | Acceptance | State |
|---|---|---|---|
| M1 | Build the installed upstream browser renderer without changing native dependencies | Build receipt, exact source inputs, intact live changes | ready |
| M2 | Register supported sign-in and enable loopback web listener | Auth-required configuration; safe restart or honest active-chat hold | ready |
| M3 | Add private HTTPS without disturbing existing routes | TLS/route checks; no anonymous API/WebSocket access | ready |
| M4 | Test phone-sized UI, profiles, streaming, history and reconnect | Actual browser and native gateway evidence; physical-device gap explicit | proposed |
| M5 | Repair only demonstrated mobile/installability gaps using existing renderer seams | Focused tests and original-source diff; no duplicate app framework | proposed |
| M6 | Record operating URL, auth path, rollback and remaining OS integration | Verified source evidence/readback, no secrets | proposed |

Dependencies: M1 and sign-in preflight precede M2; M2 auth readiness precedes exposing M3; M4 consumes M3. M5 only when M4 demonstrates a gap. The assignment is not reduced to source publication.

Execution decision: principal retains integration and verification due to UNIQUE_APPROVED_ACCESS and LOWER_TOTAL_OVERHEAD for the installed native build/configuration path. This is deterministic adoption rather than a separate routine coding commission; no worker or background executor is claimed.

## Safeguards and verification

Back up only exact affected configuration to an owner-only location; never emit tokens, cookies, provider keys or account-store contents. Bind any configuration update to its observed preimage and retain rollback. No forced gateway stop while active conversations exist. Use the supported graceful restart path, preserving the original process/result on interruption. A refused restart is not permission to kill the gateway.

Validate unauthenticated HTTP/API/WebSocket denial, intended OAuth callback, secure cookies/origins, correct profile routing, real stream event rendering, mobile viewport and keyboard behavior, history reload, stop/reconnect and desktop continuity. Keep synthetic/fixture, live-provider, remote-device and installation evidence distinct. No destructive testing of existing conversations; use one uniquely marked bounded verification conversation when admitted.

## Frontier

Last confirmed effect: this initial GitHub plan save. No build, OAuth registration, runtime configuration, tunnel change, gateway restart or live inference has been performed by this operation yet.
Next action: execute upstream browser build, then consume the build receipt while preparing secure native sign-in and non-disruptive activation.
Organizational linkage: PLAN_NOT_ORG_LINKED until the existing Agent OS writer records this supplement; it is source continuity, not a new lifecycle or admission record.
