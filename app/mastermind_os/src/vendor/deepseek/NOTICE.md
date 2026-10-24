# Selective DeepSeek client reuse

Copyright (c) 2026 DeepSeek. The two donor source files and upstream license in this directory are copied byte-for-byte from `deepseek-ai/deepseek-harness` at `687f282e8625c6b8d11ff58211a90524be2e4317`. The complete MIT permission and disclaimer are retained in `LICENSE`. `manifest.json` records exact upstream paths and SHA-256 hashes; the provenance test fails on an unrecorded edit.

## Actual consumers

`keyboard-composition.ts` is used by Mastermind's selected-session composer through `orchestration/ui/useComposerKeyboard.ts`. It prevents ordinary and Safari-style late IME confirmation keys from becoming submissions. Mastermind intentionally retains newline-by-default. Only an explicit Ctrl/Cmd+Enter gesture requests the existing form submission. It does not import DeepSeek's accelerated-delivery route, grant a target, mint an operation, choose a provider, or bypass the incumbent pending-pointer controller.

`incremental-markdown.ts` is used by `conversations/SourceMarkdown.tsx`. The renderer supplies one pinned GFM grammar and always performs a complete parse for settled content. Incremental streaming support is tested; the current production-path consumer is the explicit, lazily loaded formatted preview in `ResultSourceReader`, whose existing owner supplies settled source text. No live streaming session is claimed by this addition.

Mastermind's renderer is an original, deliberately narrower adapter. It never interprets HTML, loads images, navigates Markdown destinations, or resolves workspace files. Copy-code requires an explicit user action and reports clipboard failure. The original source string, not formatted DOM, remains the excerpt/evidence input. Oversized or excessively complex previews are refused without changing that source.

## What was not imported

No DeepSeek branding, Electron host, Cordis runtime, provider credentials, telemetry, session database, job scheduler, plugin installer, queue, permissions owner, or automatic updater was copied. Executive OS, Agent OS, the existing ACP worker, and the current authenticated host retain their responsibilities.

The incremental-parser tests measure parser input volume, not wall-clock latency, model tokens, account spend, or production throughput. The donor's documented provisional reference-link behavior is resolved by the mandatory settled full parse.

## Upgrades

Keep the donor revision distinct from the older ACP proof/research pins in the selective-harness-reuse plan. An upstream change requires an explicit source comparison, updated file/license hashes, the relevant input/stream/correction/security tests, and normal protected delivery. A newer upstream commit does not inherit earlier runtime qualification.

## Distribution

The production public assets retain the exact DeepSeek MIT license at `third-party/deepseek-harness-LICENSE.txt` and full license texts for all 58 newly introduced runtime dependency packages at `third-party/deepseek-client-dependency-NOTICES.txt`. Every enumerated package declares MIT at this pinned lockfile. The provenance test binds the distributed notice bytes; the source-only fixture is not a production entrypoint.

The third byte-identical module, `use-scroll-follow.ts`, is from `packages/client/ui-chat/src/client/chat/use-scroll-follow.ts` at the same pinned revision. It is consumed by the observed-window reader only; no upstream session store or runtime is imported.
