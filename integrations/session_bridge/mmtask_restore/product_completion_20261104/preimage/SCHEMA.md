# Continuity harness schema — mm.harness v2.0.0 (interim Agent OS write-ahead buffer)

Status: INTERIM. Canonical records are Agent OS (macro `agentos/`; schemas `agentos/schema/*.schema.yml`,
prose spec `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`, handoff protocol `research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`).
This harness is a local buffer that migrates INTO Agent OS; it must never become a second task registry.
Retire the Codex AGENTS.md section once the W1 Agent OS SessionStart hook is installed.

Versioning: every machine file carries `schema` + `schema_version` (JSON) or a first-line
`<!-- schema: mm.harness.<name> vX.Y.Z -->` / `# schema: …` header (text). SemVer: MAJOR = breaking field change,
MINOR = additive, PATCH = docs. Readers must tolerate unknown fields. v1.0.0 (milestone/T### ids) → v2.0.0
(Agent OS ids/statuses) on 2026-10-24; v1 files are archived under `<slug>/archive/`.

## Directory layout
    ~/gwcap/project-charters/
      SCHEMA.md  README.md  TEMPLATE/
      active_codex.json          mm.harness.active_codex      registry of live Codex sessions
      drift-latest.json          mm.harness.continuity_audit  last auditor output
      <slug>/
        NORTH_STAR.md   mm.harness.north_star  → Agent OS workstream `objective` (+ project-scoped goal)
        PLAN.md         mm.harness.plan        → Agent OS workstream `waves[]` (generated block) + local notes
        TASKS.json      mm.harness.tasks       → task buffer (P#.T#.S#); summarized into handoffs/wave next_action
        TASKS.md        mm.harness.tasks_view  generated view of TASKS.json (never edited)
        STATE.md        mm.harness.state       → agentos.handoff.v1 state_before / unresolved / next_actions
        HANDOFF.md      mm.harness.handoff     → agentos.handoff.v1 (agentos/handoffs/<KEY>-<YYYY-MM-DD>.md)
        DECISIONS.md    mm.harness.decisions   → agentos/decisions/DEC-<KEY>.md (agentos.decision.v1)
        PROGRESS.log    mm.harness.progress    LOCAL SCRATCH ONLY (never exported as a record)
        export/<date>/  mm.harness.export      prepared handoff + WS wave patch + EXPORT.json (validated, unpublished)
        archive/        superseded harness files (never deleted)

## Workstream binding
`NORTH_STAR.md` line `- workstream: WS:<KEY>` and `TASKS.json.workstream` (+ optional `related_workstreams[]`).
Citation shape is exactly `WS:<KEY>` (Agent OS forbids bare keys). A key with no record is "pending": export
emits a new-record proposal instead of a patch.

## TASKS.json (mm.harness.tasks 2.0.0)
    {
      "schema": "mm.harness.tasks", "schema_version": "2.0.0",
      "project": "<slug>", "workstream": "WS:<KEY>", "related_workstreams": ["WS:<KEY>", ...],
      "updated": "<ISO-8601 Z>", "updated_by": "<session>",
      "agentos": {"mirror": path, "source_sha": macro sha, "imported_at": ISO, "last_export": ISO|null,
                  "records": [{workstream, record, exists, status, waves}], "objective", "ws_status", "next_action",
                  "owner", "program", "decisions": ["DEC:<KEY>"], "do_not_redo": [], "landmines": [], "latest_handoff": path},
      "waves": [ {"p": "P<n>", "workstream": "WS:<KEY>", "id": "<wave id>", "title", "status": todo|in_progress|awaiting_ci|done|dropped,
                  "pr": int|[int], "depends_on": [wave-id], "next_action",
                  "source": "agentos" | "local-proposed" | "agentos-missing"} ],
      "tasks": [ {"id": "P<n>.T<n>[.S<n>]", "kind": "task"|"subtask", "parent": id|null,
                  "workstream": "WS:<KEY>", "wave": "<wave id>", "title", "owner": str|null,
                  "depends_on": [id], "status": <task status>, "acceptance": [str],
                  "evidence": str|null  (commit / PR / test / run URL),
                  "superseded_by": [id], "reason": str|null, "notes": [str],
                  "aliases": [old ids], "created", "created_by", "updated", "history": [{at, by, event, note?}] } ]
    }
- `P<n>` = 1-based position in the workstream's `waves[]` (concatenated in `related_workstreams` order); local
  proposals append. P numbers are stable once assigned; vanished waves are retained as `agentos-missing`.
- Task statuses (= #1700 labels): proposed → ready → in_progress → implementation_complete → reviewed → accepted;
  side states blocked, superseded. "Dropped" = superseded with `reason: "DROPPED: …"` and empty superseded_by.
  A dependency is satisfied at implementation_complete or later. Entries are never deleted.
- Derived wave status (export only, never written into waves[].status locally): all tasks accepted/superseded → done;
  all superseded → dropped; any started → in_progress; else todo. Waves without local tasks are left untouched.
- Writers: only `~/gwcap/bin/mmtask` (flock + temp-file rename; regenerates TASKS.md and the PLAN.md waves block).

## Text files
- NORTH_STAR.md: header bullets (slug, workstream, Meta-CEO, source, version), `## Goal`, `## Success criteria`,
  `## Non-goals`, `## Hard constraints`, plus the generated `<!-- agentos-import:begin … end -->` block.
- PLAN.md: `## Local roadmap notes` + generated `<!-- agentos-waves:begin … end -->` table.
- STATE.md: `current task: <id>`, `## Workspaces` table `| path | repo | branch | base | remote | head | status |`,
  `## Open threads, PRs and operations`, `## Blockers / waiting on`. Rewritten at every checkpoint.
- HANDOFF.md: free text for a stranger; must not contain 'see above' / 'as discussed' (Agent OS banned phrases).
- DECISIONS.md: `### D<n> — <date> — <title>` with type, by, decision, rationale, alternatives, impact; maps to
  `agentos/decisions/DEC-<KEY>.md` (use `agentos.py draft-decision` when promoting).
- PROGRESS.log: `<ISO-8601 Z> <session> <task-or-milestone-id|-> <kind> <note>`; kinds start, checkpoint,
  implementation_complete, reviewed, accepted, blocked, replan, self-review, decision, handoff. Scratch only.

## Export (mmtask export) → Agent OS
- `export/<date>/<KEY>-<date>.md`: agentos.handoff.v1 front matter (workstream, session, model: codex, ended_because,
  mission, state_before, changed[{path,what}], verified[{claim,command,result}], unverified[{claim,what_would_verify}],
  unresolved, next_actions, do_not_redo, danger_areas, prs) + body.
- `export/<date>/WS-<KEY>.waves.patch`: minimal unified diff of `waves[].status` / new local waves against the mirror.
- Both are validated with `agentos.py validate --paths` in a scratch copy of the store; result in EXPORT.json.
- Export never pushes, commits or opens PRs.

## Registry / audit
- active_codex.json: `{schema: mm.harness.active_codex, schema_version, sessions: [{slug, session_id, workdir, log_path,
  rollout_path, status, active, registered, updated}]}`.
- drift-latest.json: `{schema: mm.harness.continuity_audit, schema_version, generated, thresholds, summary, sessions[], harnesses[]}`;
  session status FRESH | STALE_HARNESS | DRIFTING | LOST; Agent OS `brief` warnings are listed first when available.

## Executive OS compatibility rules
No new authority, admission, queue, lease, claim or lifecycle semantics; no timers/wakes inferred from fields; local
statuses never overwrite canonical `waves[].status` except via a reviewed Macro PR; all ids/citations use Agent OS
shapes (WS:/DEC:/DSC:); session ids are not owners (Agent OS `owner` is a seat).
