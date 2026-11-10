# L2 UI lane — Paper board extractions (structure + copy, from get_tree_summary)

Source: file 01M3NRCX55B452A12819WNE1RH, tokens hash f3c5ac93 (the app's
accepted --noir/--mx shell already mirrors the token set). Exact px/color
values come from the tokens; never from screenshots. Shell (nav rail, pinned
project, settings footer) is already implemented — only the CONTENT column
matters below. The Paper roster (Meta-CEO, Engineering, Secretary, "Ryan",
"12 teammates"…) is SAMPLE DATA: never hardcode any of it in shipped paths.

## TD06 Route · Review execution (117C-0)
Breadcrumb "Projects / Mastermind OS / Request work" · chip "Design preview".
Heading "Teamlink adapter — Review coding route" + chip "Preview only".
Intro: "Confirm the work and proposed route. Nothing has started."
Columns (2×624): LEFT "Request details": Work request card (The work: title +
desc + detail), Owner, Project, Return rows; Workspace card (5 rows).
RIGHT "Placement details": Proposed route card rows: Route title, Host,
Runtime, Engine, Model, Proposed pool selection + link "View routing & limits";
Readiness card (5 rows, honest unknown-with-reason, never green).
Footer: "Execution begins only after admission." + "Follow this work from OS
launch team or the project." + primary submit (disabled while preview-only)
+ secondary back.

## TD07 Run · Result and return path (11GQ-0)
Breadcrumb "Code / Connect the team roster / Run". Heading "Engineering ·
Mastermind OS — Preparing the result" + action "Open coding session →".
Result status: state chips + "The coding turn has ended. Its result is still
being assembled." + "Engineering will receive the verified files, checks, and
source…". Columns: LEFT "Execution trail" (steps 0–5, title+detail+timestamp);
RIGHT "Run evidence": "Bound session" card (6 rows: attempt identity, thread,
harness — unknown-with-reason when not projected) + "Result artifacts" card
(5 rows: artifact refs, checks summary, source refs).

## HC07 Code · Thread, changes and host tools (14MJ-0)
Location bar "Code / Mastermind OS" + "← OS launch team". Three columns:
(1) Thread rail 248: project select "Mastermind OS ▾" + ⋯, "＋ New thread",
search "Find a thread…", "WORKING · 2" group (name + model · state, e.g.
"Teamlink adapter / DeepSeek Harness · Working"), "SETTLED · 8 ›" collapsed
group, environment identity ("Ubuntu 2 · Connected · Synced just now",
"Manage environments →"). (2) Code conversation 640: thread header (title +
"DeepSeek harness · GLM 5.3 · Capacity Fabric"), messages (brief, agent
reply, changed-files summary, current activity "Running the affected
checks…" / "Tool output appears in Terminal."), footer strip "2 related
tasks from Engineering · Open work →", composer "Ask anything, @ files, $
skills, / commands…" + note "New direction queues for the next turn. Current
work continues." (3) Work panels 480: tabs "Changes · 2 | Browser |
Terminal", file rows (name + "+28 −4"), working diff block, terminal block
("Conversation checks" + "✓ message identity…"), return footer "Result
returns to OS launch team" + "Return pending · Engineering receives the
result here."

## HC02 New bot · Role and launch (136T-0)
Toolbar: "Conversations / Roster" toggle + "New group" + "＋ New bot".
Conversation list (search "Find a conversation", PINNED groups, TEAMMATES
rows from the real roster read). New bot form 744: heading "New teammate —
Give your bot a role and a place on the team." Fields: Name ("You can change
this later."), "What should this bot do?" ("Clear scope helps the team know
when to involve this bot."), "Start from" select ("Or use an existing
teammate's instructions and capabilities."), Bot access card ("Access &
capabilities · Edit →", "Fresh personal memory. Credentials stay with the
connection."), Launch route card ("Team default · Change", "Model and
placement follow your team's policy."), "Advanced settings ›". Preview panel
344: "PREVIEW", teammate preview with "Not created yet", steps 01 Create a
profile / 02 Start the bot / 03 Open its conversation ("You'll see Ready
when the bot can respond."), "Make it part of the team" note.

## HC03 New group · Members and room behavior (13GW-0)
New group form 744: "Give the right teammates a shared place to work."
Group name, Purpose ("Everyone in the room can use this shared direction."),
member search "Search 12 teammates…" (count comes from the real roster),
"Members — 4 selected · up to 6 on this connection" (cap honest), selected
member rows + "＋ Add teammates", Cancel / Create group. Room behavior panel
344: "ROOM BEHAVIOR", "Who responds?" radios: Automatic ("The room brings in
the relevant members.") / Lead ("One teammate coordinates the responses.") /
Everyone ("Each selected teammate gets a turn."); Room availability
("Always-on available · Team gateway", "This room can continue when you
close the app."); Shared context ("＋ Add file or project").

## HC09 Bot settings · Models and capabilities (155S-0)
Tabs: Overview / Models / Capabilities / Memory / Routines. Models tab:
"Model defaults — Used when this bot starts a new session." Provider
connection select ("GLM Fabric · Connected ▾"), Main model + Reasoning
level, Fallback ("Follow team policy ▾", "Used only when the selected
provider is unavailable."), Auxiliary tasks ("Team default ▾") / Subagent
tasks ("Managed placement ›"), "Advanced · context and mixtures ›".
Scope panel 344 "APPLIES TO": selected bot, "Current conversation — GLM 5.3 ·
High" ("Use its composer to change the active model." "Open conversation →"),
"Connection — GLM Fabric · Ready" ("Credentials are held by this
connection." "Manage providers →"), Capabilities preview ("Manage
capabilities →").

## HC12 Room · Thread replies and message actions (15Z2-0)
Room identity row: Conversation / Shared files / Room settings + "Members ···".
Timeline messages (human + bot rows), selected message with action popover
(4 actions), activity strip "3 tasks · 2 working · 1 returned · View
activity →", composer "Add direction, attach a file, or /command…".
Reply thread panel 344: "Thread", origin ("Engineering · 20:05" + text +
"View original message →"), replies (author · time + text, task link
"Reconnect handling · Working →"), attachment ("reconnect-flow.png · Image ·
Open preview"), reply composer "Reply to this thread…" + "＋ @ Mention",
note "Replies stay with this message. Mention a teammate to bring them in."

## HC18 Team · Needs you and exact request (1NSP-0)
Newer Team header: tabs "Conversations | People | Routines", "Connected"
status, "New group" / "＋ New bot". Conversation inbox 304: search "Search
messages and people", filters, "WAITING FOR YOUR RESPONSE" section with
cards (avatar, name, ask, kind · age: "Question · 2 min" / "Result to
review · 8 min" / "Action needed · 12 min"), note "Reading keeps requests
open.", Pinned conversations (count), Archived "View →". Selected request
1064: header (avatar, name, "Always-on teammate · Waiting for your answer",
"Open beside", "Details", •••), request conversation, exact request block
("DAILY BRIEFING — Where should it go?" with option buttons), composer "To
Secretary · Private conversation", "Reply, attach a file, or /command…",
"+ Context", "Follow bot settings ⌄".

## HC19 Team · Two conversations, independent drafts (1OAV-0)
Split workspace: header "Two conversations" + workspace tabs strip
("Workspace saved on this device"), two side-by-side panes (684 each) each
with its own header/timeline/composer/footer — drafts stay independent per
pane.

## HC20 Team · Search with exact-message context (1OVH-0)
"/ Search" mode: results list 448 (query row, filters, "3 results in
available history", result rows grouped by conversation) + message context
pane 920 (conversation header, SURROUNDING MESSAGES window around the exact
match, footer actions). Counts and results come only from a real search
source; empty state must be honest.

## HC21 Team · Parent work and scoped task dialogue (1PB7-0)
"/ Work" mode: work hierarchy 448 (parent work rows, "DELEGATED WORK"
section with task rows + counts) + selected task dialogue 920 (header,
facts row, task timeline, scoped task composer, footer). Maps to the
delegated-task binding vocabulary (DelegatedTaskCard) at conversation level.

## Journey map (HB01 17GG-0)
Four steps: Gather the team → Delegate useful work → Work in Code → Return
the result. Coverage lists: Team & conversation / Code & results / Controls
& states. "HC frames extend the existing TD" — HC boards are conversation
extensions of the TD journey, not a second design system.
