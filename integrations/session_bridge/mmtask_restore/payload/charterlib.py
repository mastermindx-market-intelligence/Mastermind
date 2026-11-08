#!/usr/bin/env python3
"""charterlib — shared helpers for Codex continuity harnesses at ~/gwcap/project-charters/<slug>/.

Harness files (owned and maintained by the project's Codex Meta-CEO):
  NORTH_STAR.md  original goal, success criteria, non-goals   (changes only with a DECISIONS entry)
  PLAN.md        living goal tree / roadmap: milestones '### M1 — title' with status/next/paths/keywords
  STATE.md       'where am I now' snapshot, rewritten every checkpoint
  PROGRESS.log   append-only '<ISO time> <session> <milestone-id|-> <kind> <note>'
  DECISIONS.md   decisions, rationale, alternatives (incl. re-plans and north-star changes)
  HANDOFF.md     enough for a brand-new session to take over

CLI:
  charterlib.py prompt <slug> <workdir> [--resume] [--extra TEXT]   -> Meta-CEO session prompt
  charterlib.py show <slug>                                         -> parsed JSON
  charterlib.py append <slug> <session> <milestone|-> <kind> <note...>
"""
import json, os, re, sys, datetime

ROOT = os.path.expanduser(os.environ.get("MM_CHARTER_ROOT", "~/gwcap/project-charters"))
FILES = ["NORTH_STAR.md", "PLAN.md", "STATE.md", "PROGRESS.log", "DECISIONS.md", "HANDOFF.md"]
KINDS = ("start", "checkpoint", "done", "blocked", "replan", "self-review", "deviation", "decision", "handoff")
HEAD_RE = re.compile(r"^(#{3,5})\s+(M\d+(?:\.\d+)*)\b\s*[—:\-–]*\s*(.*)$")
FIELD_RE = re.compile(r"^\s*[-*]\s+(status|owner|next|paths|keywords|acceptance|depends|notes)\s*:\s*(.*)$", re.I)
SUB_RE = re.compile(r"^\s{2,}[-*]\s+(.*)$")
PROGRESS_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$")


def cdir(slug):
    return os.path.join(ROOT, slug)


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def section(text, title):
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if on:
                break
            on = line[3:].strip().lower().startswith(title.lower())
            continue
        if on:
            out.append(line)
    return "\n".join(out).strip()


def parse_plan(text):
    ms, cur, sub = [], None, None
    for line in text.splitlines():
        h = HEAD_RE.match(line)
        if h:
            cur = {"id": h.group(2), "title": h.group(3).strip(), "status": "", "owner": "", "next": "",
                   "paths": [], "keywords": [], "acceptance": [], "depends": "", "notes": ""}
            ms.append(cur); sub = None
            continue
        if line.startswith("## "):
            cur = None; sub = None
            continue
        if cur is None:
            continue
        f = FIELD_RE.match(line)
        if f:
            k, v = f.group(1).lower(), f.group(2).strip()
            sub = k if k == "acceptance" else None
            if k in ("paths", "keywords"):
                cur[k] = [x.strip().strip("`") for x in v.split(",") if x.strip()]
            elif k == "acceptance":
                if v: cur[k].append(v)
            else:
                cur[k] = v
            continue
        s = SUB_RE.match(line)
        if s and sub == "acceptance":
            cur["acceptance"].append(s.group(1).strip())
    return ms


def parse_progress(line):
    m = PROGRESS_RE.match(line.strip())
    if not m or line.startswith("#"):
        return None
    return {"time": m.group(1), "session": m.group(2), "milestone": m.group(3), "kind": m.group(4), "note": m.group(5)}


def progress(slug, n=0):
    rows = [p for p in (parse_progress(l) for l in read(os.path.join(cdir(slug), "PROGRESS.log")).splitlines()) if p]
    return rows[-n:] if n else rows


def load(slug):
    d = cdir(slug)
    if not os.path.isdir(d):
        raise SystemExit(f"no harness dir: {d}")
    ns = read(os.path.join(d, "NORTH_STAR.md"))
    plan = read(os.path.join(d, "PLAN.md"))
    return {"slug": slug, "dir": d,
            "files": {f: os.path.exists(os.path.join(d, f)) for f in FILES},
            "north_star_goal": section(ns, "Goal") or section(ns, "North-star"),
            "success_criteria": section(ns, "Success criteria"),
            "non_goals": section(ns, "Non-goals"),
            "milestones": parse_plan(plan),
            "stub": "STUB" in ns[:400]}


def append(slug, session, mid, kind, note):
    note = " ".join(str(note).split())
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {session} {mid} {kind} {note}"
    with open(os.path.join(cdir(slug), "PROGRESS.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return line


def build_prompt(slug, workdir, resume=False, extra=""):
    ch = load(slug); d = ch["dir"]
    name = slug
    for ln in read(os.path.join(d, "NORTH_STAR.md")).splitlines()[:3]:
        if ln.startswith("# ") and "—" in ln:
            name = ln.split("—", 1)[1].split("(")[0].strip()
    try:
        waves = json.load(open(os.path.join(d, "TASKS.json"))).get("waves") or []
    except Exception:
        waves = []
    open_ms = [w for w in waves if w.get("status") not in ("done", "dropped")]
    tree = "\n".join(f"  {w['p']} {w.get('workstream','')} {w['id']} [AO {w.get('status')}]{' (local proposal)' if w.get('source') == 'local-proposed' else ''} {w.get('title') or ''}"
                     for w in waves[:40]) or "  (no Agent OS waves imported — run `mmtask import`, or propose a wave)"
    prog = "\n".join(f"  {p['time']} {p['session']} {p['milestone']} {p['kind']} {p['note']}" for p in progress(slug, 10)) or "  (none yet)"
    try:
        tdb = json.load(open(os.path.join(d, "TASKS.json")))
        tl = tdb.get("tasks", [])
    except Exception:
        tl = []
    byid = {t["id"]: t for t in tl}
    ip = [t for t in tl if t["status"] == "in_progress"]
    okst = ("implementation_complete", "reviewed", "accepted", "superseded")
    kids = lambda t: any(c.get("parent") == t["id"] and c["status"] not in okst for c in tl)
    ready = [t for t in tl if t["status"] in ("ready", "proposed") and not kids(t) and all(byid.get(x, {}).get("status") in okst for x in t.get("depends_on") or [])]
    try:
        ws = json.load(open(os.path.join(d, "TASKS.json"))).get("workstream")
    except Exception:
        ws = None
    tasks_txt = ("\n".join(f"  {t['id']} [{t['status']}] {t.get('wave') or t.get('milestone') or '-'} {t['title']}" for t in (ip + ready)[:6])
                 if tl else "  (NO TASK PLAN YET — create the up-front breakdown with mmtask before executing anything)")
    open_n = sum(1 for t in tl if t["status"] not in ("accepted", "superseded"))
    mirror = os.path.expanduser("~/gwcap/agentos-mirror/macro")
    aocmd = (f"python3 {mirror}/scripts/agentos.py compile-context --workstream {ws.split(':',1)[1]} --text --root {mirror}/agentos" if ws else "(no workstream bound)")
    reanchor = ("RESUMED SESSION — RE-ANCHOR FIRST. Your earlier context may be stale or compacted. Before acting, "
                "re-read the harness and reconcile your own recent work against NORTH_STAR and PLAN; record a "
                "'self-review' PROGRESS line noting any drift and the correction.\n\n") if resume else ""
    stub_note = ("\nThe harness is a STUB: NORTH_STAR/PLAN are to be seeded from the project's Pro masterplan "
                 "(path in NORTH_STAR.md). If it exists, adopt it (log a DECISIONS entry); if not, census the "
                 "project yourself and draft them, marking the north star provisional.\n") if ch["stub"] else ""
    return f"""{reanchor}You own **{name}** (`{slug}`) end-to-end as its long-horizon autonomous Meta-CEO.

Canonical records: Agent OS workstream **{ws or '(pending)'}** (macro `agentos/`). This harness is its local write-ahead buffer.

**FIRST ACTIONS: (1) load canonical context: `{aocmd}` (or `scripts/agentos.py brief` / `compile-context --workstream …` from a macro checkout, if available); (2) read TASKS.json (`~/gwcap/bin/mmtask next`) and STATE.md. If there is no task plan, or it doesn't cover the work you are about to do, create or extend it with `~/gwcap/bin/mmtask add "…" --wave <P#|wave-id>` BEFORE executing anything.** Then mark your task `mmtask start <id>`. Finish it with `mmtask done <id> --evidence "<commit/PR/test>"` (→ implementation_complete), then `review`/`accept` when that evidence exists.

Your continuity harness is `{d}` (also $MM_CHARTER). It is your own durable project memory; it lives outside every worktree and survives pruning, compaction and session loss. Then read NORTH_STAR.md and PLAN.md (both carry generated Agent OS blocks) (and HANDOFF.md, recent PROGRESS.log and DECISIONS.md as needed), and drive the plan forward autonomously across as many milestones as it takes. The global AGENTS.md section "Codex long-horizon continuity harness" applies in full.

Working directory: `{workdir}`
{stub_note}
North star (summary only; NORTH_STAR.md is authoritative):
{ch['north_star_goal'] or '(see NORTH_STAR.md)'}

Pinned task list (TASKS.json: {len(tl)} tasks, {open_n} open) — in progress / ready next:
{tasks_txt}

Waves (Agent OS waves[] via TASKS.json, {len(open_ms)} open):
{tree}

Last 10 PROGRESS lines:
{prog}

Harness duties: Agent OS records are canonical (publish via `mmtask export` → a normal Macro PR by the record owner; never push records yourself unless your commission says so); plan before execute (task breakdown first; new discovered work is added as a task before doing it; re-plans supersede tasks, never silently drop them; one task, or a small explicit set, in_progress at a time; STATE.md names the current task id); re-read TASKS.json/STATE/NORTH_STAR/PLAN at each turn start and after compaction; re-plan freely in PLAN.md but log each re-plan in DECISIONS.md with a rationale tied to the north star; checkpoint (rewrite STATE.md, append PROGRESS.log, refresh HANDOFF.md) at natural boundaries, at least every ~30-45 minutes of work, and before any long wait or the end of a turn; run a continuity self-review every few milestones or when uncertain; record branch, base, remote and worktree path in STATE.md so pruned workdirs can be restored. Write the harness files directly (the directory is a writable root of this session). As a fallback, end your final message with the latest PROGRESS line in a fenced block beginning `PROGRESS: `.

LEADERSHIP CONTINUITY + HANDOFF_SOURCE_LINK_V1 (Chairman, 2026-10-24; aligned with PR #1842): (1) Ownership is a role, not a person or session. If work is held for a separate/named owner, owner session/acceptance, old PR author or archived chat that is absent, orphaned or not you, YOU assume leadership now, record the takeover (Agent OS decision/handoff, PR body or session registry) and proceed; never wait for an owner or ask Chris to find an old chat; protect real live writers and unknown effects. Independent review from any fresh non-authoring reviewer is still required; never self-merge or self-approve. (2) Handoffs are short and source-linked: full brief in reviewed GitHub; the message carries recipient, one bounded action, the source link and the return location. (3) An explicit tool safety/permission denial ends that action: no reworded, cross-tool or cross-account retry; continue other permitted work. (4) Rollouts count only after readback (installed Project instructions and fresh-chat behavior per account); unreached targets are UNKNOWN. No purchases, bypass flags or secrets in output.

GROK SECRETARY CONTACT (Chairman, 2026-10-30): to reach Grok Secretary, post in Slack #dotsandgroksecretary (C0CBC6AEAQZ) and @mention Grok Secretary (<@U0BTCHX8HMF>) in the message, as a new top-level post for a new ask or in the existing thread for follow-ups. Do NOT DM Grok Secretary: DMs are only checked about every 30 minutes, while @mentions in #dotsandgroksecretary reach it immediately.
{('\nAdditional instructions for this session:\n' + extra + '\n') if extra else ''}"""


def main(a):
    if len(a) < 3:
        print(__doc__); return 2
    if a[1] == "prompt":
        extra = ""
        if "--extra" in a:
            i = a.index("--extra"); extra = a[i + 1]; del a[i:i + 2]
        print(build_prompt(a[2], a[3], "--resume" in a, extra))
    elif a[1] == "show":
        print(json.dumps(load(a[2]), indent=2))
    elif a[1] == "append":
        print(append(a[2], a[3], a[4], a[5], " ".join(a[6:])))
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
