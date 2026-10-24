# DeepSeek Harness full-application adoption: developer pilot

**State: SOURCE PILOT — not installed into Mastermind OS, not Executive-authorized.**

The integration target is the **complete DeepSeek application**, not just React components. Upstream pin: [DeepSeek Harness @687f282](https://github.com/deepseek-ai/deepseek-harness/tree/687f282e8625c6b8d11ff58211a90524be2e4317), MIT license. Keep its license and notices when distributing.

## Local full-app pilot (M2)

Clone the exact pin to the sibling donor checkout. Use upstream pnpm 11.28.5 (not the system pnpm 9):

```sh
cd /Volumes/Mastermind/agent-workspaces/dsh-donor-20261022
npx pnpm@11.28.5 install --frozen-lockfile
npx pnpm@11.28.5 run build
```

Launch using `integrations/deepseek_harness/run_local.sh`. It starts the donor's full web app on the default local port 3080 with a separate private DSH_HOME. No Mastermind company credential, public origin, provider account, Worker or Job admission is supplied by this launcher.

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
