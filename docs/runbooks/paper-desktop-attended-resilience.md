# Paper Desktop attended resilience and Mastermind OS continuation

## Purpose and bounded authority

This is a supervised **GUI app**, not a new Paper execution server. The existing
Business direct tunnels, one guarded bridge, Paper login, exact design-file
identity and effect-recovery contract remain unchanged.

Operation: `paper-desktop-resilience-and-mmos-parity-20261107-sol-001`.
Protected source base: `20e17eb2985710f1509a5726f3719e5b8d6a37a7`.
Design file: `01M3NRCX55B452A12819WNE1RH`.
Mastermind OS canonical design: Page12 `p-D-0`, project and evidence
`p-H-0`, decisions and plans `p-I-0`, office `p-J-0`,
sessions/access `p-K-0`.

## Host observation: 2026-11-07

- M2 Studio macOS user GUI had the actual Paper.app installed at
  `~/Applications/Paper.app` but **no running GUI app** and no listener
  on `127.0.0.1:29979`; existing Paper Business tunnel LaunchAgents
  were already running. Native Mastermind Paper returned
  `UPSTREAM_UNAVAILABLE` for inspect and exact-file reads.
- Launching the installed app via `open -a` restored the existing Paper
  service and exact-file reads. The bridge read the 20-page Mastermind OS
  design and its current desktop/mobile artboards.
- The existing Aqua GUI session now has
  `com.mastermind.paper-desktop.attended` at
  `~/Library/LaunchAgents/com.mastermind.paper-desktop.attended.plist`,
  mode `0600`. A current post-bootstrap read observed the same label
  `running`, the original Paper GUI PID, the loopback listener, and an
  `OBSERVED` exact-file read from Mastermind Paper.
- The only supervising binary is Apple's existing
  `/usr/bin/open -W -a ~/Applications/Paper.app`, run by `launchd`.
  `RunAtLoad`, `KeepAlive`, `ThrottleInterval=30` and
  `LimitLoadToSessionType=Aqua` provide user-login startup and
  process-exit recovery. No background scheduler, Paper MCP proxy,
  credential, raw public listener or second bridge was created.

## Reproducible installation and verification

The source-owned fail-closed installer is
`integrations/paper_desktop/attended_gui_launchd.py`.
From the exact reviewed Mastermind checkout on the intended authorized
**macOS user**, run:

```bash
python3 -I -B integrations/paper_desktop/attended_gui_launchd.py verify
python3 -I -B integrations/paper_desktop/attended_gui_launchd.py install
python3 -I -B integrations/paper_desktop/attended_gui_launchd.py verify
```

The installer checks the actual owned app and launchd directories, the
app executable, the exact private plist bytes/semantics and the original
launchd service state. An existing different plist is **not overwritten**.
A refused/uncertain bootstrap is reconciled against the same label;
there is no blind bootstrap retry. Unit tests use a temporary fake
home and stubbed launchctl; they never quit the live application.

**Boundary:** launchd cannot operate a GUI while its Aqua session is
logged out, cannot prove a user's Paper login, and cannot detect a hung
but still-running process. Keep these limits visible; a future
hang-recovery capability must first reconcile active Paper edits and
same-carrier uncertain effects, rather than killing/restarting the
editor during an unknown write. Do not enable automatic macOS login
or introduce a competing watcher merely to erase the limitation.

## Current product mission: actual app parity

The canonical Atelier file is live and usable again. The existing
Mastermind OS `App.tsx` has a legacy Project > Plan branch rendering a
static `NOT_PROJECTED` placeholder despite the newer authenticated
`ProjectPlanPanel` being already mounted on the modern project route.
Reusing that existing owner-fed Plan panel for the legacy Plan tab is an
independent, backward-compatible vertical repair. It does not grant
approval/adoption or invent plan data.

Acceptance for that slice: the legacy Plan tab invokes the same
source-qualified reader and displays owner-issued plan/currentness or
honest source-unavailable state; no new plan store, controller or
project/mission association is created. Focused frontend tests must
prove the branch, including negative cases. The real authenticated
installed/browser path remains separately owed.

Other major project lanes remain on their incumbents: native DeepSeek
integration #2177, Fabric #2175, model pool #2109 and release #2107.
Preserve their source/effect ownership; this bounded repair neither
claims their production acceptance nor copies their harness.
