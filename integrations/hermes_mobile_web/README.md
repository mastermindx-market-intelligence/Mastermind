# Mastermind mobile integration for Hermes

Operation: `hermes-mobile-web-20261107`, existing PR #2245.
Parent and acceptance remain in `research/mastermind_os_production_fasttrack_2026-11-07/MOBILE_WEB_DELIVERY.md`.

## Current assignment boundary

The Chairman directed this continuation to advance other elements and integrations first. Do not restart, interrupt, replace or reconfigure the running M2 gateway. Preserve the existing browser build, Nous registration, Tailscale route, staff profiles and other writers' source changes. Production activation and physical-phone acceptance remain pending.

## Implementation slice

1. Add a native Hermes Desktop/Webapp plugin using the installed `@hermes/plugin-sdk`, not a replacement chat UI. A responsive Mastermind page discovers real profile routes, opens the exact selected saved conversation through native navigation and creates a new draft only on an explicit user action. Core Hermes retains streaming, tools, sessions and authentication.
2. Add optional install metadata under Hermes's existing authenticated plugin API: a web-app manifest, original icons and mobile home-screen shortcuts. No service worker, transcript cache, offline mutation queue, credential store, public listener or independent server.
3. Qualify route/source identity, stale asynchronous results, missing profiles, disconnected states, mobile controls, install metadata and authentication boundaries in an isolated test home. Never use production data or credentials for fixtures.
4. Publish exact source and evidence on this branch. Production adoption remains a separately verified operation; a fixture browser or source commit is not live deployment.

## Source and ownership

Donor: installed MIT-licensed NousResearch/hermes-agent at `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Retain its SDK and package-discovery contracts. The M2's existing `omh` plugin and broader Mastermind OS/DeepSeek integration are not edited. New source lives only in this directory; test staging is disposable and not a second publisher.

Direct implementation rationale: `LOWER_TOTAL_OVERHEAD` for the small SDK-bound integration and `UNIQUE_APPROVED_ACCESS` for the existing installed donor and isolated qualification environment. No worker, runtime admission or background executor is claimed.
