# T3i — Team view options (stock T3 web client vs thin fork vs server-fed list)

Date: 2026-11-10. Read-only source investigation of the team-server build tree
`~/.mastermind/t3-team-server/pin-0770446-textdelta` (upstream `0770446` + T1s patch).
All `path:line` references are relative to that tree. No client was run; every
rendering claim is source-read, not observed.

## 1. Recommendation

Candidate 0, no code change. One T3 project "Team", one pinned primary thread per
teammate titled `Name — role`, provider instance displayName = teammate name with an
accent color, window opens a deep thread URL (never `/`). The stock sidebar already
renders that block as a roster with name, status word, live duration, time and provider
badge. It leaves unmet: a separate role line (only inside the title), an aggregate
"Needs you" surface, and Paperclip `request_confirmation` visibility unless the carrier
relays it into the thread. Keep candidate 1 as a named follow-up; do not build
candidate 2 now.

## 2. Candidates

| # | Reader sees | Meets | Size | Upstream-merge risk | What could falsify this |
| --- | --- | --- | --- | --- | --- |
| 0 | Pinned block: name-title, status word + duration, provider badge, time | List, selected conversation, busy/not, per-row needs-you, no-login (T1-proven) | none (T2 setup path only) | none (no fork) | A running client showing the pinned block unreadable at window width, or titles truncating roles away |
| 1 | Same rows plus role line, "needs you" emphasis | All of 0 plus role line, stronger orientation | ~1–2 web files, ~100–200 lines added | SidebarThreadRow.tsx changed 4×, Sidebar.tsx 6× in the 5 retained days; expect re-conflicts each pin bump | A running stock client already orienting in 3–4 s without the fork |
| 2 | Teammate list read live from Paperclip | All of 1 plus roster changes without touching T3 data | 5–8 files across contracts+server+web, few hundred lines; two-app fork | settings.ts 8×, ProjectStore and models also move; highest | Nothing stock reusing per-thread metadata — confirmed absent, so only a costlier path remains |

## 3. Candidate 0 in detail (field by field)

Setup facts: threads can be created with a title (`t3 thread start --title`, T2 note
step 3) and renamed later via MCP `t3_thread_update` `action:'rename'` with `title`
(`apps/server/src/mcp/toolkits/orchestrator/tools.ts:254-256`). Pinning is
`t3_thread_organize` `action:'pin'` (`apps/server/src/mcp/toolkits/thread/tools.ts:32-52`).

- **Thread title** — rendered as the row's main line (`apps/web/src/components/sidebar/SidebarThreadRow.tsx:1052-1054`); rename by double-click/F2 (`SidebarThreadRow.tsx:847-876`). Carries `Name — role`.
- **Pin state and ordering** — pinned threads form a top block in manual drag order via `pinOrderKey` (`packages/client-runtime/src/state/threadSort.ts:268-301`); section resolution keeps a pinned thread pinned even while working (`apps/web/src/components/Sidebar.tsx:661-673`, `apps/web/src/components/Sidebar.logic.ts:176-185`). The "Pinned"/"Active" boundary labels render only while dragging (`Sidebar.tsx:3499-3519`) — at rest the block is just the top of the list.
- **Run status** — a status word + icon on card rows: Setting up, Working, Goal, Waiting, Approval, Input, Request, Limited, Failed, Woke, Done (`SidebarThreadRow.tsx:730-790`), resolved from runtime/pending state (`Sidebar.logic.ts:861-891`). Pinned/active/working rows use the rich card variant (`Sidebar.tsx:3344-3353`). "Working" rows also tick a live duration (`SidebarThreadRow.tsx:164-177,1512-1516`).
- **Unread / attention marks** — unseen completion shows "Done" in success color (`SidebarThreadRow.tsx:715,784-789`; `Sidebar.logic.ts:698`); a snoozed thread that fails or asks shows "Woke" with a dismiss button (`packages/client-runtime/src/state/threadSettled.ts:168-190`; `SidebarThreadRow.tsx:1293-1299`). Caveat: `hasPendingUserInput` means a pending runtime request during a run (`packages/client-runtime/src/state/models.ts:315`) — a turn that merely ends with a question in text shows "ready", not "Input".
- **Provider instance name / icon** — each row renders the current provider instance icon with accent-color badge (`SidebarProviderStack`, `SidebarThreadRow.tsx:183-229`); the badge shows when the instance has an accent color or shares its driver with another instance (`packages/client-runtime/src/state/providerInstanceDisplay.ts:64-90`). Hover tooltip adds `model · instance displayName` (`SidebarThreadRow.tsx:309-330`).
- **Last activity time** — relative label from the latest user message or run timestamps (`SidebarThreadRow.tsx:1323-1327`; `packages/client-runtime/src/state/threadSort.ts:33-52`).
- **Project grouping and collapse** — default is NOT folder mode (`boringSidebarEnabled` default false, `packages/contracts/src/settings.ts:513`); default has a bottom "Working" shelf (`settings.ts:527`, shelf headers with counts at `Sidebar.tsx:3539-3586`). Folder mode exists (`SidebarProjectFolderHeader.tsx:38-119`, collapsed-folder status dot at `Sidebar.logic.ts:897-917`) if wanted later.
- **URLs** — threads open at `/<environmentId>/<threadId>` (`apps/web/src/threadRoutes.ts:68-72`, route `apps/web/src/routes/_chat.$environmentId.$threadId.tsx:4`). `/projects/<key>` only redirects to settings (`apps/web/src/routes/projects.$projectKey.tsx:11-15`). Warning: `/` auto-starts a NEW draft thread in the most recent project (`apps/web/src/routes/_chat.index.tsx:31-79`) — the window must deep-link a thread, never `/`.
- **Sidebar show/hide** — toggle button `aria-label="Toggle main sidebar"` + keyboard shortcut (`apps/web/src/components/AppSidebarLayout.tsx:392-397,327-365`); no URL parameter or setting for a default-hidden sidebar found (searched AppSidebarLayout.tsx and routes).

## 4. Candidates 1 and 2

**1 Thin web fork.** Edit `apps/web/src/components/sidebar/SidebarThreadRow.tsx` (card
variant, lines 1440–1600) to add a subtitle line and pass through data; possibly
`apps/web/src/components/Sidebar.tsx` for props. Field sources: status, time, provider
badge already exist in the row; the role line has no per-thread metadata field to read
(`packages/client-runtime/src/state/models.ts:137-200` has none) — it must parse the
title or show the provider instance `displayName` (already loaded per row,
`SidebarThreadRow.tsx:126-136`). Honest size: ~100–200 added lines, 1–2 files plus
tests. Churn in the retained history (2026-11-05..09, 200 commits — the tree carries
only those): SidebarThreadRow.tsx 4 changes (11-05, 11-07, 11-08, 11-09), Sidebar.tsx 6
(11-06 ×2, 11-08 ×2, 11-09), Sidebar.logic.ts 1, models.ts 1.

**2 Server-fed list.** No existing per-thread or per-project free-form metadata
mechanism was found: thread organize is pin/snooze/settle/archive/mark_unread only
(`apps/server/src/mcp/toolkits/thread/tools.ts:32-52`); projects carry title,
faviconPath, projectIcon (lucide/emoji/monogram + color), pinnedAt, archivedAt and no
metadata bag (`packages/contracts/src/project.ts:83-170`, store at
`apps/server/src/orchestration-v2/ProjectStore.ts:39-68`, update command at
`apps/web/src/hooks/useProjectGroupUpdate.ts:19-25`). So a Paperclip-fed list needs a
new route or field spanning `packages/contracts`, `apps/server` and `apps/web` — a
two-app fork, strictly larger than candidate 1. Its only unique value is roster changes
without the binding path writing T3 data.

## 5. Work cards

The stock renderer already does the useful things: a plain markdown link renders as an
anchor with the target host's favicon and opens in the in-app preview browser
(`apps/web/src/components/ChatMarkdown.tsx:1145-1146,1207,1270`), and a
`t3-thread://v2/<environmentId>/<threadId>` link renders as a rich thread chip showing
the target thread's live title (`ChatMarkdown.tsx:1082-1088`,
`apps/web/src/components/chat/MarkdownThreadLink.tsx:13-40`; protocol at
`packages/shared/src/threadLinks.ts:5-11`). The smallest improvement is therefore no
client change at all: the carrier writes the Paperclip issue as a labeled link
(`[Issue <id> — title](http://127.0.0.1:3190/...)`) next to its marker, and links the
asking thread with a `t3-thread://` chip when it returns work. A real card (issue state
live in the conversation) would be a fork item, not a first step.

## 6. Open questions only a running client can answer

1. At rest, does the pinned block read as a distinct roster without the drag-only boundary labels?
2. Are `Name — role` titles fully legible at the Mastermind window's sidebar width, or does the role truncate?
3. Does the provider accent-color badge actually render for the team's instances (badge rule needs accentColor set)?
4. In a fresh paired profile, is the sidebar expanded by default on a deep thread URL?
5. Does a teammate turn that ends with a plain question show anything beyond "ready" (source says no)?
6. Does the carrier's `[pc-<issue>-<hash>]` marker message wrap readably in the conversation?
7. After the Chairman opens a teammate thread, does the "Done" unread mark clear promptly?
8. Does snoozing a teammate thread and forcing a failure show "Woke" with its dismiss button on this build?

## 7. Not verified

- No client was run; all rendering claims are source-read.
- The tree's git history holds only 200 commits (2026-11-05 to 11-09); lifetime file churn is not measurable here.
- Sidebar-toggle persistence across window restarts (T1: not separately tested).
- The exact server HTTP registration point a candidate-2 route would use (not located; not needed for this recommendation).
- Linked-environment sidebar grouping rendering (not read; irrelevant to a one-environment team window).
- Provider instance displayName editing surface in the settings UI (read from the data shape only).
