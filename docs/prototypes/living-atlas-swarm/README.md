# Mastermind Living Atlas — Swarm study

An original, display-only visual prototype authored for the 12 November 2026 refinement of Living Atlas. Open **index.html** directly in a browser. It is self-contained and makes no network requests. All sessions, observations, messages, repositories and outcomes shown in the scene are synthetic examples.

## What it demonstrates

- Six stable project fields, eight separate session identities and concurrent work.
- A coordinator crossing project regions, a T3 lead, two explicit helpers and other asynchronous teams.
- Independently articulated bodies, timed probes, curved signals and short travel traces.
- A check process that survives its initiating session moving elsewhere.
- Separate failed-check, correction, passing-check, PR-ready, merged, verified and consumed observations.
- Local source loss: T3 becomes unobserved while independent sources continue. Previously observed terminal evidence remains intact.
- Selection, project focus, optional session follow, pointer pan, zoom, Full/Calm/Off motion, display pause, finite replay and timeline seeking.
- An HTML inspector/activity explorer and native keyboard-operable controls.

The small mesh vertices are decorative texture. They are not files, agents, events or inferred semantic relationships. A moving character shows a change in the example's work context; it does not migrate a process between computers.

## Run and rebuild

Open **index.html** for the complete bundled study. The other files are its editable source.

~~~sh
python3 build.py
node --test model.test.mjs
~~~

The build uses Python's standard library. The model tests use Node's built-in test runner. The browser application has no third-party runtime dependencies.

To create an in-conversation fragment at an explicitly chosen location:

~~~sh
python3 build.py --inline-output /absolute/path/mastermind-swarm-atlas.html
~~~

The optional **controller-check.mjs** uses an installed @napi-rs/canvas package with a small DOM/event stub. Set ATLAS_CANVAS_PACKAGE to its package path when it is installed outside ordinary Node module resolution. This is a development check, not a browser test or runtime dependency.

## Module boundaries

| File | Responsibility |
| --- | --- |
| fixture.mjs | Deterministic synthetic observations, identities, milestones and seekable actor poses |
| renderer.mjs | Cached project textures, original crawler geometry, probes, process markers, signals, labels and hit testing |
| controller.mjs | Local viewing state, controls, visibility handling, scheduling and disposal |
| surface.html | Scoped product mockup and equivalent textual inspector |
| build.py | Bundles the authored modules into the standalone page and optional inline fragment |
| model.test.mjs | Identity, concurrency, source-loss, correction, seeking and motion semantics |
| controller-check.mjs | Control and lifecycle simulation with a real native canvas |

## Validation in the authoring environment

- JavaScript syntax: passed for the modules and generated bundle.
- Model/geometry tests: **12 passed**.
- Controller checks: **15 passed at 760 × 610** and **15 passed at 372 × 470**.
- Native canvas raster inspection: estate, focused team, T3 observation loss and narrow-screen views.
- No browser layout, WebGL, Tauri, real-source, installed-user-journey or target-device frame-time claim is made.

The controller checks verify actual selectors against surface.html and exercise pause, selection, focus, feed loss/restoration, timeline, replay, reduced motion, visibility and disposal. They use DOM stubs; they cannot verify CSS layout or browser rendering.

The renderer currently bakes six field textures during construction. Production should qualify startup cost and perform baking off the interaction-critical path or distribute prebaked assets. Most detail is cached; it is not reconstructed every frame. Only a bounded set of bodies, probes, signals and captions changes continuously.

## Mastermind integration

The production mount is the existing **LivingHQGraph** seam. Reuse **LivingHQGraphProps**, **LivingHQSnapshot**, **HQTarget**, typed relationships, source completeness, controlled selection/filter state and existing navigation callbacks from app/mastermind_os/src/living_hq/contracts.ts.

This study is not that React component or its live adapter. Its synthetic fixture is not a proposed transport schema. A production adapter must consume already-qualified observations; no session store, poller, command interface, telemetry authority or admission system is supplied here.

The shared contract needs owner-backed amendments for exact Paperclip projects, repository/worktree resources, browser actions, file movements and independent processes where these are not already represented. Keep unknown associations unknown. Do not infer parentage or project membership from names or spatial proximity.

See the corresponding plan at docs/plans/2026-11-12-living-atlas-swarm-refinement.md for source pins, qualified integration gaps and build sequence.

## Reference and originality

The user supplied a Defileo video and pointed to Kirito14IT/prompt-spider-ui. The latter describes itself as an independent reconstruction of reference footage. It was inspected at **24a5db96fff2579baaa6fefce7d7051a929a8d57** as a rendering and interaction reference.

This study's code, scenario, composition and character geometry were authored for Mastermind. No source-video frames, third-party branding, or source files from that project are bundled. Its reference statistics, fixed video track, event store and MCP server are not used.

## Status

**Working synthetic visual study; production integration remains unbuilt by this revision.** The code is deliberately isolated from the application shell and the active Team/Code/estate integration writers. Its purpose is to make the revised visual direction executable and reviewable before the live source slice is mounted.
