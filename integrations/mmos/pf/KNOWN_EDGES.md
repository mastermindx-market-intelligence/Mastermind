# PF known edges: settled or recommended (PF-2 item 6)

Lead, 2026-11-14. Each edge: what it is, where, and what was done or what is recommended.

## 1. Bare path in a reply is not a link

- What: T3's markdown renderer makes a file link only from a markdown link or an inline
  code span. A bare `/Users/...` path in a teammate's reply is plain text.
- Settled for the team, without a T3 change: the charter tells the teammate to give
  output paths "as an absolute path inside single backticks so it opens as a file
  link". It is on Staging Scout (`charters/scout.md`, `teammates/scout/CHARTER.md`) and
  in the repo's PF staging spec (`team_roster_pf_staging.json`, commit `6533e29bc`).
  Proven in the wave-1 journey: the backticked path opened as a file link.
- Recommendation: add the same sentence to the common charter tail of the real roster
  (`tools/mmos_team_server/specs/team_roster.json`, all teammates) at the next roster
  apply on the real root (the principal's). Charters take effect when a teammate's
  session process next starts, not mid-run (`team_roster.py` reports this as
  "NOT IN FORCE until that teammate's session process starts").
- Not recommended now: auto-linking bare paths in T3. It changes rendering for every
  conversation and needs a guard against linking paths a person did not mean as files.

## 2. Port 0: loader and writer disagreed

- What: `window_config.sh` refuses port 0 ("the port must be between 1 and 65535");
  the window's loader accepted `http://127.0.0.1:0` (the url crate parses port 0).
  REV-WIN2 LOW-1.
- Settled: commit `d7c2652ba`. `parse_shell_url` and `parse_board_url`
  (`app/mastermind_os/src-tauri/src/shell_mode.rs`) refuse port 0 as `missing_port`;
  tests cover `:0`, `:00000/` (board) and `:0/env-1/t` (shell). `cargo test --bin
  mastermind-os shell_mode`: 24 passed. Source only. The placed app is unchanged and
  needs no rebuild for this (the files are 0600, owner-only, and port 0 cannot connect).
  It rides with the next window build.

## 3. Adopt-folder moving a thread out of a locked project

- What: `thread.project.adopt-folder` changes a thread's project, so it could take a
  thread out from under the lock (REV-LOCK finding 5).
- Settled, no change needed: it is an internal command
  (`packages/contracts/src/orchestrationV2.ts:3412`, `OrchestrationV2InternalCommand`),
  not accepted from a client. Its only sender is scratch-thread promotion
  (`apps/server/src/project/ScratchThreadPromotion.ts:57-125`). That refuses any thread
  whose folder is not directly under the scratch root, or whose project is not the
  scratch project ("Only a No project thread with its own folder can become a project.").
  A team-project thread works in the team project's folder, so it can never be
  promoted. Also: the server refuses the move unless the folder is unchanged and no
  work is running (`Orchestrator.ts`, `dispatchThreadProjectAdoptFolder`).

## 4. Window title "Mastermind OS" vs app name "Mastermind OS Next"

- What: the title bar reads "Mastermind OS"; the menu bar, Dock and Finder say
  "Mastermind OS Next". `tauri.conf.next.json` overrides only `productName`,
  `identifier` and the deep-link scheme, so the window inherits `title: "Mastermind OS"`
  from `tauri.conf.json`. The web page sets `document.title` from the server's
  `presentation.productName` (`apps/web/src/appInit.tsx`, `startDocumentTitle`), but
  the native title bar does not follow it (observed in wave 1: title bar "Mastermind
  OS" while productName was "Mastermind OS Next").
- Recommendation: keep it as is. The title bar names the product. The app name tells
  the Chairman which of his two apps he is in: the daily app stays "Mastermind OS"
  until Next replaces it. After part (c) on the real server, the in-window face reads
  "Mastermind OS" too (productName), so only the menu bar and Dock carry "Next".
  Renaming the app is part of the later decision to replace the daily app (ruling 18:
  never rebuild or replace `~/Applications/Mastermind OS.app`). It is not a defect to
  fix now.
