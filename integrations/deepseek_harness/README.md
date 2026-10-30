# DeepSeek Harness full-application adoption: developer pilot

**State: SOURCE PILOT — not installed into Mastermind OS, not Executive-authorized.**

The integration target is the **complete DeepSeek application**, not just React components. Upstream pin: [DeepSeek Harness @687f282](https://github.com/deepseek-ai/deepseek-harness/tree/687f282e8625c6b8d11ff58211a90524be2e4317), MIT license. Keep its license and notices when distributing.

## Local full-app pilot (M2)

**Current local proof, October 29, 2026:** the original
`/Volumes/Mastermind/agent-workspaces/dsh-donor-20261022` checkout was unavailable
because that external volume is not mounted. An isolated donor checkout on
M2 internal storage at `$HOME/agent-workspaces/dsh-donor-pinned-20261029`
was verified at `deepseek-ai/deepseek-harness@687f282e8625c6b8d11ff58211a90524be2e4317`
with a clean source tree. With pinned pnpm 11.28.5, the donor's
**dependency-aware** `build:artifacts` passed all seven stages and produced
325 client artifacts. An isolated, loopback-only donor Web pilot returned
unauthenticated HTTP **401** and authenticated HTML-shell HTTP **200**
(using a one-time local generated token), then stopped with the port closed.
This is **not** a connected company chat or an accepted Mastermind deployment.

Build in a disposable donor checkout at that exact pin (never on the
existing #1717 source branch). Avoid relying on the missing external mount.
Do not modify global npm configuration: on the observed M2, the global npm
cache itself points to the missing mount. A per-command cache was used:

```sh
export DSH_SOURCE="$HOME/agent-workspaces/dsh-donor-pinned-20261029"
cd "$DSH_SOURCE"
export NPM_CONFIG_CACHE="$HOME/Library/Caches/mastermind-dsh-20261029/npm"
CI=true npm exec --yes --package=pnpm@11.28.5 -- pnpm install --frozen-lockfile --ignore-scripts
CI=true npm exec --yes --package=pnpm@11.28.5 -- pnpm run build:artifacts
```

The **developer-only** launcher now requires explicit `DSH_SOURCE` and
refuses unpinned/unbuilt donors, public host flags, symlinked state and use
of the donor checkout as the model's workspace. It starts the full DSH
Web app only on `127.0.0.1`, from an isolated `HOME` / `DSH_HOME` /
empty workspace, with **no inherited provider, account or computer-use
environment credentials**. `DSH_PORT=0` lets the OS choose a free local
port. Before the launch, use the no-effect preflight:

```sh
export DSH_SOURCE="$HOME/agent-workspaces/dsh-donor-pinned-20261029"
export DSH_HOME="$HOME/agent-workspaces/dsh-preview-20261029"
sh integrations/deepseek_harness/run_local.sh --check-only
sh integrations/deepseek_harness/run_local.sh
```

The launcher prints an ephemeral local login URL; treat the token as a
secret and do not paste it into issues, logs or chats. `DSH_HOME` is a
private pilot root; user HOME, state, and default workspace live under its
`home/`, `state/`, and `workspace/` children, respectively. No arbitrary
CLI flags may be forwarded, so public binding and user data directory
selection are unavailable from this launch carrier. This launcher creates
**no** Hermes service, Executive Job, Fabric Attempt, Steward scope,
provider call, Mac computer actuation, or Slack cutover.

## Runtime convergence — keep the donor app

DSH `apps/web`, `packages/client/ui-chat`, `ui-session`, `ui-workspace`, `ui-plugin-manager`, `ui-schedule` and their supporting session/controller/agent-loop modules become the native chat and plugin substrate. Preserve actual DSH-native sessions and streaming behavior instead of reconstructing them from Executive Jobs.

Add a Mastermind Cordis plugin to expose authorized company project references, session targeting and tool grants through **existing** Executive OS/Agent OS contracts. Executive OS retains company Job/Attempt/Worker admission, authority, cost, effects, canonical result evidence and original-operation recovery. Agent OS retains organizational continuity. A DSH-native session isn't automatically a Mastermind company job.

## Integration acceptance ladder

1. Run and visually smoke-test pinned donor web and desktop app in isolated local development.
2. Build the company-aware project/session explorer as an app plugin while retaining the upstream bundle.
3. Bind its send, resume, stop and result views to exact Executive-owned session refs where offered, with original operation-key reconciliation and honest unavailable states.
4. Connect governed ACP/MCP grants and Fabric delegation using existing #825, #1060, #1196, #1142 integrations; no unadmitted tool escapes or duplicate company control plane.
5. Integrate Paper's original Noir design and the existing Mastermind OS Work/Project views into one branded web/Tauri/Electron decision, after qualifying real launch, shutdown, streaming and auth.
6. Test install, login, reconnect, multi-session navigation, effects, provider and parent-consumed results. Ship only with a signed-in actual system proof.

The upstream `ui-chat` package depends on Cordis session-controller, renderer and React 18 workspace modules. The current Mastermind OS is a React 19 Vite/Tauri client; a wholesale component paste would therefore discard the donor's working application wiring. Extend its bundle through Cordis instead.

**Existing artifacts to preserve:** `docs/superpowers/plans/2026-09-27-selective-harness-reuse.md`, `research/harness_reuse/2026-09-27-builder-packet.md`, `app/mastermind_os/src/conversations`, `SessionWorkspace.tsx`. Existing operations #687/#1037/#1142 and their active PR branches remain independent. Paper file `01M3NRCX55B452A12819WNE1RH`: Chat Atelier `p-C-0`, Sessions & Access `p-K-0`.

Never represent donor install or standalone development UI as accepted company integration; retain separate authority, result and deployment proof.
