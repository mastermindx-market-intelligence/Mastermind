# DeepSeek and Mastermind OS chat delivery

Operation: `deepseek-mastermind-chat-20261106-c2`.
Chairman assignment: finish DeepSeek integration, the Mastermind OS UI, and usable chat.
Source base: `af18454f0cd2086c7976e55e16fee1d8dd70f405`.
Branch: `sol/web-deepseek-mastermind-chat-20261106-c2`.

This is the implementation continuation of #687/#1037/#1142 and the merged full-application
pilot #1717; it does not replace their product requirements or the existing
`docs/superpowers/plans/2026-09-27-selective-harness-reuse.md` task tree.
The current integration contract is `integrations/deepseek_harness/README.md`.

## Product acceptance

An authenticated user opens the accepted Noir Atelier interface, chooses the correct
project/conversation, sends an explicit message once, reads a useful response, continues
the same conversation, and can recover the original conversation after navigation or
reconnection. Permission loss clears protected content. Unknown effects retain their
original request; no blind resend, alternate provider or synthetic target is introduced.
Retain the full DeepSeek app's native session/stream/render/plugin capabilities beneath
Mastermind's existing company authority and capability owners.

Paper design: file `01M3NRCX55B452A12819WNE1RH`, canonical page `p-D-0`,
conversation page `p-C-0`; CH1 `IZB-0`, CH6 `K5X-0`, CH91 `KDN-0`,
CV01 `SD8-0`. Existing app tokens and approved source design contracts remain controlling.

## Current blocking facts

- Full donor pilot #1717 and governed MCP proof #1790 are merged; do not rebuild them.
- The current attended fresh-conversation flow intentionally permits only one follow-up.
  Its service waiter, immutable request/reply records and UI all encode that ceiling.
  Removing UI text alone cannot implement multi-turn chat.
- The current Executive V3 session target read returned an empty list. This is a current
  target-availability observation, not permission to create target identities.
- Studio Paper inspect/catalog/exact-file reads returned INVALID_ARGUMENT; the independent
  Paper read carrier's inspect/catalog returned the same technical error. No Paper edit
  was attempted. Use preserved accepted design contracts until exact live reads recover.
- The original donor checkout is clean at `687f282e8625c6b8d11ff58211a90524be2e4317`.
  Keep that checkout intact; owned integration source belongs in this repository.

## Delivery nodes

| Node | Work | Acceptance |
| --- | --- | --- |
| CHAT-1 | Complete the existing conversation UI and continuation composition | Real mounted message/response/continuation journey; draft and unknown-request recovery preserved |
| CHAT-2 | Complete the donor app's company integration seam using its supported plugin boundaries | Actual pinned donor registration and UI mount, existing project/session owners, no parallel auth/session/company lifecycle |
| CHAT-3 | Connect eligible existing runtime and provider routes | Actual admitted original request, useful response, same-conversation follow-up and settled resources |
| CHAT-4 | Publish and release through the existing protected path | Exact source/CI, installed build identity, signed-in desktop and mobile user-path proof |

Every node retains its source versus runtime proof ceiling. Deliver useful code slices,
consume short validation in this session, and advance the next safe node without another
Chairman approval. Do not waive actual source-writer, permission, unknown-effect or
protected release controls.

## Execution ownership

The attended principal owns architecture, integration and product acceptance.
An existing native reasoning child supplies cross-system architectural judgment only.
Use admitted economical Fabric for independently bounded implementation where it improves
the completion cycle. Parent direct integration is justified by PRINCIPAL_JUDGMENT and
CRITICAL_PATH_SHORTCUT while interfaces are being resolved, not as a substitute native
labor pool. Preserve one modifying carrier per operation and disjoint worker paths.

## Verification and durable return

Run focused tests that discriminate changed message/continuation, auth invalidation,
duplicate-send and recovery behavior; build the actual app; inspect desktop/mobile and
dark/light layouts. Required hosted checks remain release gates. Record exact changed
source, commands/results, provider/runtime observations and remaining original-scope
obligations here at material milestones. An isolated fixture or merged source alone is
not production completion.
