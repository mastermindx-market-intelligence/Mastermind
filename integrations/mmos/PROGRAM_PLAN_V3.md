# Mastermind OS program plan V3

Date: 2026-11-10. Owner: program principal (Fable). Source: Chairman rulings of
2026-11-10 (no login for local use; Paperclip with Hermes runtime is the always-on
team and the project shell; the principal may change the plan).

This plan replaces the lane map and DONE_WHEN of the earlier mission handoff where
they conflict. How the team works stays in `OPERATING_METHOD_V3.md`.

## 1. Why the plan changed

A month of work produced almost nothing the Chairman can see. The causes are
structural, not a lack of effort.

| Cause | Evidence |
| --- | --- |
| Every screen of the app calls a remote door (login, then the public edge). The edge drops 74 of the 83 paths the app calls. | L4 path census, `LANE_L4_INSTALLED_APP.md` |
| The backend the app reaches is the production Executive at an old release. New code cannot be installed while its Worker runs, and an older hold is still recorded. | `EXECUTIVE_READER_DIAGNOSIS.md`, L1 R6 memo |
| The session for Executive routes lives in memory only and has no refresh path. "Stay logged in" could not be fixed in the app alone. | L4 slice 5 |
| The app wrote no logs and agents could not drive it. Every repair session guessed. | L4 slice 1 |
| The app is two very large files (one screen file, one native file with 58 commands). Parallel work collides. | file sizes on trunk |
| We rebuilt by hand what Paperclip already gives: projects, tasks, agents, runs, routines, skills, and a plugin system. | installed Paperclip, `ops/paperclip_fleet/README.md` |
| Roughly 100k lines sit on a trunk that never reached the screen. We measured proofs and reviews, not a working screen. | trunk vs master diff |

## 2. Decisions

1. **Paperclip is the shell.** Projects, tasks, agents, runs, routines, skills and
   audit come from the installed Paperclip instance on the M2. We stop building
   those in a custom app.
2. **No login for local use.** Paperclip runs in its local trusted mode. Nothing in
   the local product calls Auth0 or the public edge. Login returns only if the
   product is hosted on the web.
3. **Every Mastermind feature is a module.** A module is a Paperclip plugin kept in
   this repository under `integrations/paperclip_plugins/`. A module can add a page,
   a sidebar entry, a dashboard widget, a tab on a task, project or agent, a tool
   agents can call, a scheduled job and a health check. Modules reload while the
   shell runs, write logs, and have a test harness. This is the surface agents use
   to change the product.
4. **The native app is a thin window.** The Mastermind OS Mac app opens the local
   shell. It holds no product logic. The old screens stay in the build behind the
   old switch until the modules replace what was worth keeping.
5. **Hermes is the runtime, not a second app.** The existing Paperclip agents run on
   Hermes profiles. We do not merge the Hermes desktop app into Mastermind OS. The
   Paperclip migration session owns the default instance, its agents and the Hermes
   profiles.
6. **Coding jobs start and end on a Paperclip task.** The request is a task; the
   verified GitHub result returns to the same task. Executive stays the admission
   owner for T3 coding jobs. The local door to Executive is a Unix socket with
   peer-uid admission (`LOCAL_OPERATOR_CONTRACT.md`); loopback TCP and headers are
   never trusted.
7. **The production Executive release is off the critical path.** It is one owner
   act at a quiet moment. Nothing visible waits for it except coding jobs through
   Executive. No agent stops or disarms the Worker to make a release eligible.
8. **The crew is permanent.** A standing improvement lane owns the dev skill, the
   module template, the scoreboard and the backlog of harness defects. Every lane
   ends by writing what slowed it into that backlog.

## 3. What stops

- Auth0 login repair, token persistence and refresh work in the app.
- Public edge allowlist work for app paths.
- Merging the Hermes desktop app into the Mastermind OS app.
- New features inside the two large app files.
- Per-lane guard and review rounds. One review happens at the release candidate.
- Proofs that target the Hermes desktop origin and the Secretary native-session
  return (old R8 and R9).

## 4. What carries over

- The T3 coding-job engine pieces that are green on trunk (admitted canary, native
  composition, gap fixes), re-pointed at a Paperclip task as origin and return.
- The Executive-side Unix socket listener (off unless configured).
- The dev log and dev bundle identity from the test-environment lane.
- The negative matrix and continuity states, as checks for module behaviour.
- The design boards, as the reference for module pages.

## 5. DONE_WHEN

1. Opening Mastermind OS on the M2 needs no login and shows the real company, its
   agents and its tasks.
2. One Mastermind module is loaded in the shell with a page, a sidebar entry, a
   widget and an agent tool, showing real local data.
3. A cold agent given only the dev skill adds a feature to a module and proves it
   in under one hour without human help.
4. A task assigned in the shell runs on its agent's Hermes runtime and returns the
   result on the same task. (Owned by the Paperclip migration session; we consume
   it and report defects.)
5. A task that needs code becomes one coding job, and the verified GitHub result
   returns to the same task.
6. After a restart of the shell or the app, tasks, runs and module state are
   truthful: nothing shown as running that is not, nothing lost.
7. Every module and the native window write logs agents can read, and every module
   tool can be called from the command line.
8. The improvement loop exists and has been used once: backlog, scoreboard, skill
   updated from a real lane's findings.

## 6. Lanes

| Lane | Outcome | State |
| --- | --- | --- |
| L9 module platform | Isolated dev instance, module template, first module, module map of the old app, cold-agent test | new, critical path |
| L8 native window and dev environment | Thin window on the local shell, dev log, dev skill | re-scoped |
| L4 local door | Executive-side socket listener, activation memo, corrected incident record | narrowed, then closes |
| L1 coding-job engine | Land what is green, write the reuse map for a Paperclip-origin job, then closes | narrowed, then closes |
| L6 trunk hygiene | Flake fixes, release-candidate manifest | finishing |
| L10 coding job on a task | DONE_WHEN 5, built as a module tool on the engine from L1 | starts after L9 proves the platform |
| L11 improvement crew | DONE_WHEN 8 | starts after the cold-agent test |

## 7. Boundaries

- Two Paperclip instances. Dev lanes build and test only against an isolated dev
  instance on its own data directory and port. The default instance is read-only
  for dev lanes. The one write to it is installing a proven module, done when no
  run is live.
- Dev lanes do not create a company, hire agents, create or assign tasks, or edit
  the service database in the default instance. They do not edit Hermes profiles or
  restart the Hermes gateway.
- The Chairman's installed app is not rebuilt, replaced, quit or driven by dev
  lanes. Dev builds use the dev bundle identity.
- Desktop captures are scoped to the product's own window. One GUI-driving child at
  a time.
- Protected `master`, review and release controls are unchanged.

## 8. Fallback

If the plugin runtime in the installed Paperclip build fails the L9 proof (page,
tool, reload, logs in the isolated instance), the shell decision stands and the
module surface changes: the native window frames the Paperclip shell beside our own
module host, with the same module contract. L9 reports the failing fact before any
such switch.
