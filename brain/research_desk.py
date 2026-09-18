"""The research desk — the marriage of Claude's armed research to the doctrine gates.

run_daily_research(): runs an ARMED Claude session (reads the dashboard, searches the
web/news, reasons 2nd/3rd-order, writes proposals back via the MCP action tools).

ingest_proposals(): turns Claude's free-form proposals into first-class, gated objects —
each becomes a falsifiable brain_decision.v1 whose falsifier the ENGINE derives, clamped
by the risk officer (Claude can't escalate a blocked name or escalate while block evidence is
unavailable), appended to the same ledger + Brier scorer as the deterministic brain. Sizing still happens downstream via the
confluence scorecard — Claude proposes the hypothesis; it never pushes size. Paper-only.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import bot  # noqa: F401

from brain import cli_bridge, ledger
from brain.decision import DecisionDoc

_ROOT = Path(__file__).resolve().parent.parent
_PROPOSALS = _ROOT / "data" / "brain" / "proposals.jsonl"
_PROPOSAL_LOCAL_LOCK = threading.RLock()
_BULLISH = {"add", "overweight", "accumulate", "constructive", "buy"}


def _proposal_lock_path(queue: Path) -> Path:
    """Sibling lock derived from the selected queue at call time (test/alternate-root safe)."""
    return queue.with_name(f".{queue.name}.lock")


@contextmanager
def _proposal_lock(queue: Path):
    """Serialize producer enqueue with consumer read/effect/mark across threads and processes."""
    with _PROPOSAL_LOCAL_LOCK:
        queue.parent.mkdir(parents=True, exist_ok=True)
        with _proposal_lock_path(queue).open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    # Queue effect (if any) is already decided by atomic replace. Do not turn a
                    # known effect into an apparent failure because lock cleanup itself failed.
                    pass


def _read_proposals_unlocked(queue: Path) -> list[dict]:
    if not queue.exists():
        return []
    # Proposal evidence is accountability input. Malformed rows fail closed instead of being
    # skipped/quarantined into a second implicit queue.
    return [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines() if line.strip()]


def _atomic_write_proposals(queue: Path, rows: list[dict]) -> None:
    """Atomically replace the selected queue; failed replacement preserves prior bytes."""
    queue.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, default=str) + "\n" for row in rows)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=queue.parent,
            prefix=f".{queue.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, queue)
        tmp_name = None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def enqueue_proposal(row: dict, *, queue_path: Path | None = None) -> dict:
    """Append one model proposal through the same serialized queue owner used by ingestion.

    `queue_path` exists for explicit test/alternate-root custody; production callers pass the
    bot MCP's canonical path, which is the same file `_PROPOSALS` consumed by this module.
    """
    queue = Path(queue_path) if queue_path is not None else _PROPOSALS
    with _proposal_lock(queue):
        rows = _read_proposals_unlocked(queue)
        record = {**row, "logged_at": datetime.now(timezone.utc).isoformat()}
        rows.append(record)
        _atomic_write_proposals(queue, rows)
        return record

RESEARCH_PROMPT = """You are the Brain — the decision-making reasoning layer for the Mastermind, an
autonomous, paper-only narrative-investing bot. Today is {asof}; the macro regime is {quad} ({quad_name}).

WORK IN TWO STAGES.

STAGE 1 — SALIENCE (triage, don't research yet). Call get_daily_briefing FIRST: it gives you the macro
frame (regime, cycle, liquidity, Fed stance, posture, catalysts) AND a ranked priority_queue plus the
divergences list (names where the tape and smart-money DISAGREE). Then call get_intake_candidates to see
the full deduped candidate queue with provenance — which independent engines flagged each name (briefing /
radar / alt-data / buy-board / news-surge / open-thesis) and why. Corroboration across independent engines
is the strongest signal. Pick a SHORT list (≈3-6) to research in depth: prioritise the DIVERGENCES and the
high-confidence, multi-engine names. Skip names where everything already agrees and the move is spent.

STAGE 2 — DEPTH (research the shortlist). For each chosen name call get_intel_hub(ticker) — the deepest
single pull: the 5-desk fused dossier with composite conviction, the direction matrix, and the 2nd/3rd-order
flags (stealth_accumulation / early_edge / crowded_top / theme_wide / isolated / policy_conflict). Then
get_ticker_package (intelligence facets + lens divergences + intake provenance), get_quote for a live price
check, and WebSearch / WebFetch for recent news, events, filings, and narratives. A theme_wide flag means the
whole basket is moving (durable); isolated means name-specific (early or idiosyncratic) — weight accordingly.
The remaining tools — get_themes / get_standouts / get_portfolio / get_altdata / get_news / read_signal — are
there when you need to go deeper.

Reason through SECOND and THIRD-order effects — supply-chain flow, shortages/overages, earnings and
guidance, accounting events, institutional news and flow. Hunt for: emerging themes, themes rolling
over, and asymmetric single-name edges that others haven't connected yet.

APPROACH FROM ALL SIDES — before any verdict on a name or theme, call get_decision_matrix(subject).
You MUST address every lens with status in {validated, context, partial} — valuation, quality, growth,
narrative/leadership, asymmetry, risk (drawdown cone + extension), administration/policy tilt, Fed path,
institutional flows (13F + ETF), options positioning, rate sensitivity, cross-asset, conviction — and
say whether it agrees or disagrees. NEVER form a thesis from one side. Call get_divergences and rule on
each divergence: where the lenses disagree is the EDGE (e.g. cheap + flows-in + policy-tailwind before
price moves) or the TRAP (e.g. hot + expensive + smart-money exiting = distribution). Validated lenses
(drawdown cone, extension veto) hold authority; a hard veto (parabolic / Altman distress / cycle-blocked)
caps size at 0 no matter how bullish the rest. Confluence sets size; divergence names the edge.

Discipline (the house doctrine): CONFIRMATION over prediction — a story with no price/breadth/flow is
a value trap, not an edge. Tag inferred inputs as (unverified). Be selective. 13F / institutional-flow
lenses are LAGGED quarter-end snapshots (filed up to 45 days after the quarter closes) — treat them as
positioning CONTEXT, never as real-time flow, and NEVER tie them to a recent price move (no "accumulating
into the dip / buying the selloff / adding on weakness"): the snapshot predates the move. Live dip-buying
needs Form 4 insider buys, options flow or ETF creations — not 13F.

For each GENUINE edge you'd stake your reputation on:
  - call propose_thesis(subject, lean, conviction, horizon_d, thesis, evidence, prob_correct)
  - if it's a new narrative, call flag_emerging_theme(name, stage, tickers, rationale)
Then call save_research_note to summarize your conclusions and reasoning chain.

REQUIRED: every save_research_note body MUST be 250-500 words and contain ALL of these sections
(use these exact markdown headings so the parser can find them):

## Thesis
1-3 sentences: the core claim, why NOW, and the expected outcome if correct.

## Mechanism
The causal chain — what is actually happening operationally/financially/structurally that
makes this true. Not the conclusion; the plumbing that produces it.

## 2nd- and 3rd-order effects
Who else is touched? Supply-chain winners/losers, competitors that benefit or get hurt,
credit/refinancing knock-ons, labor / regulatory ripple effects. At least 3 specific points.

## Affected tickers
- Primary: the direct beneficiaries or victims (the subject + close peers).
- Secondary: 1-2 steps removed (suppliers, customers, substitutes, competitive set).
- Short candidates: names that are hurt if the thesis is right.

## What to watch
Specific measurable catalysts with approximate dates or thresholds — earnings dates, policy
announcements, data releases, price/volume triggers. At least 3 concrete watchpoints.

## Risk & invalidation
What specific evidence would prove this WRONG? Be precise — e.g. "revenue guidance cut >10%
in the next quarterly report" or "Fed hikes instead of cutting by September." Vague invalidators
(e.g. 'macro worsens') are not acceptable. The falsifier must be concrete.

## Lens summary
A compact table of the key lenses you checked (at minimum the validated + context lenses):
| Lens | Direction | Key value | Note |

Nothing you do executes a trade — the engine gates sizing and the falsifier. Propose, don't size."""


def _intake_brief(limit: int = 12) -> str:
    """Pre-context: the ranked intake worklist injected into the prompt so the brain starts
    FROM the dashboard's salience ranking instead of a cold hunt. Degrade-safe (returns '')."""
    try:
        from brain import intake
        q = intake.build(limit=limit)
    except Exception:  # noqa: BLE001
        return ""
    cands = q.get("candidates") or []
    if not cands:
        return ""
    lines = []
    for c in cands:
        lean = {1: "↑", -1: "↓", 0: "·"}.get(c.get("lean"), "?")
        flag = " ⚡DIVERGENT" if c.get("divergent") else ""
        why = c["reasons"][0] if c.get("reasons") else ""
        lines.append(f"  {c['ticker']:6} score={c['score']:.2f} {lean} "
                     f"[{','.join(c.get('sources') or [])}]{flag} — {why}")
    mc = q.get("macro_context") or {}
    frame = ", ".join(f"{k}={mc[k]}" for k in ("regime", "cycle", "liquidity", "fed_stance")
                      if mc.get(k))
    return ("\n\n--- TODAY'S INTAKE WORKLIST (pre-loaded from the dashboard signal engines; "
            "verify with get_daily_briefing / get_intake_candidates) ---\n"
            + (f"Macro frame: {frame}\n" if frame else "")
            + "\n".join(lines)
            + "\n(⚡DIVERGENT = tape vs smart-money disagree — highest-information; research these first.)")


def run_daily_research(asof: str | None = None, *, max_turns: int | None = None) -> dict:
    """Run the armed research session. Needs a subscription credential to reach Claude;
    degrades gracefully (ok=False) when unauthenticated."""
    regime = json.loads((Path(cli_bridge._ROOT) / "vendor" / "macro" / "data" / "regime" / "latest.json").read_text())
    asof = asof or regime["date"]

    # NIGHTLY COST TRIPWIRE (before the armed session) — same contract as the bot seats: when
    # the per-night USD cap is armed and the flagship book already hit it, skip the session.
    # OFF by default (cap <= 0 → over_budget always False) so this is a no-op when disarmed.
    try:
        from brain import cost_guard as _cg
        if _cg.over_budget("flagship", asof):
            return {"ok": False, "skipped": "over_budget", "asof": asof,
                    "error": f"nightly cost cap hit (${_cg.spent('flagship', asof):.2f} "
                             f"/ ${_cg.cap():.2f}); research session skipped"}
    except Exception:  # noqa: BLE001 — the tripwire is additive; never block research on a guard bug
        pass

    # NB: targeted replace (not str.format) — the prompt body contains literal
    # braces (e.g. "{validated, context, partial}") that .format() misreads as fields.
    prompt = (RESEARCH_PROMPT
              .replace("{asof}", asof)
              .replace("{quad}", regime["quad"])
              .replace("{quad_name}", regime.get("quad_name", "")))
    prompt += _intake_brief()             # stage-1 salience pre-context (degrade-safe)
    if not cli_bridge.available():
        return {"ok": False, "error": "claude CLI/SDK not available", "asof": asof}
    # book="flagship": attribute an all-pool-cooling marker to the flagship job so the
    # scheduler's retry-at-reset can key on it (the flagship BOOK is deterministic and never
    # blocked by cooling — only this research-ingest leg is skipped when the pool is exhausted).
    res = cli_bridge.research_sync(prompt, role="deep", max_turns=max_turns, book="flagship")
    # Record the armed session's cost explicitly (book= above makes cli_bridge skip its own
    # recorder — the caller-records contract). Before 2026-07-25 NOBODY recorded this leg, so
    # the desk's single biggest LLM session was invisible to cost_summary / the nightly cap.
    try:
        from brain import cost_guard as _cg
        _r = res or {}
        _usg = _r.get("usage") or {}
        _cg.record(
            "flagship",
            _r.get("cost_usd"),
            asof,
            seat="research_desk",
            model=str(_r.get("model") or ""),
            input_tokens=int(_usg.get("input_tokens") or 0),
            output_tokens=int(_usg.get("output_tokens") or 0),
            cache_read_tokens=int(_usg.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(_usg.get("cache_creation_input_tokens") or 0),
            key_id=_r.get("key_id"),
        )
    except Exception:  # noqa: BLE001 — the recorder must never break the research leg
        pass
    return res


def _clamp(lean: str, subject: str, blocked: set[str]) -> tuple[str, str]:
    """Risk officer: a bullish lean on a blocked name is clamped to a watch (de-escalate only)."""
    if lean in _BULLISH and subject.upper() in {b.upper() for b in blocked}:
        return "watch", "clamped: subject is engine-blocked (cannot escalate)"
    return lean, ""


def _engine_blocked(subject: str) -> bool | None:
    """Return hard-block truth from deterministic engine evidence.

    ``True`` means a real hard veto / ``size_authority=blocked``. ``False`` means the
    synthesis completed and is not hard-blocked. ``None`` means that evidence could not be
    read or did not satisfy the synthesis contract; callers must not reinterpret unknown as clean.
    """
    try:
        from portfolio import lenses

        matrix = lenses.full(subject, "name")
        if not isinstance(matrix, dict):
            return None
        syn = matrix.get("synthesis")
        if not isinstance(syn, dict):
            return None
        vetoes = syn.get("vetoes")
        authority = syn.get("size_authority")
        if not isinstance(vetoes, list):
            return None
        if authority not in {"up", "down", "hold", "blocked", "insufficient_data"}:
            return None
        return bool(vetoes) or authority == "blocked"
    except Exception:
        return None


def ingest_proposals(asof: str | None = None, *, blocked: set[str] | None = None,
                     con=None) -> dict:
    """Convert Claude's 'proposed' rows into gated, falsifiable ledger theses. Returns a summary."""
    blocked = blocked or set()
    asof = asof or date.today().isoformat()
    # Hold the same queue lock used by enqueue_proposal through read -> ledger effects -> status
    # publication. A model proposal arriving mid-ingest waits, then appends to the successor queue;
    # it can never be silently overwritten by this consumer's final replace.
    queue = _PROPOSALS
    with _proposal_lock(queue):
        rows = _read_proposals_unlocked(queue)
        if not rows:
            return {"ingested": 0, "theses": [], "note": "no proposals"}

        out, kept = [], []
        for i, r in enumerate(rows):
            if r.get("status") != "proposed":
                kept.append(r)
                continue
            subj = r.get("subject", "")
            # de-escalate a bullish lean on an engine-blocked name whether the caller flagged it OR the
            # engine itself vetoes it (the daily loop passes no `blocked` set, so self-derive it).
            eff_blocked = set(blocked)
            explicit_block = subj.upper() in {b.upper() for b in eff_blocked}
            engine_block_state: bool | None = None
            if not explicit_block:
                engine_block_state = _engine_blocked(subj)
                if engine_block_state is True:
                    eff_blocked.add(subj)
            proposed_lean = r.get("lean", "watch")
            lean, clamp_note = _clamp(proposed_lean, subj, eff_blocked)
            if not clamp_note and engine_block_state is None and proposed_lean in _BULLISH:
                lean = "watch"
                clamp_note = "clamped: engine block status unavailable (cannot escalate without risk evidence)"
            doc = DecisionDoc(
                id=f"{asof}-{r['subject']}-claude-{i}", subject=r["subject"], lean=lean,
                conviction=("low" if clamp_note else r.get("conviction", "low")),
                prob_correct=float(r.get("prob_correct") or 0.55), horizon_d=int(r.get("horizon_d") or 21),
                thesis=r.get("thesis", ""), state_asof=asof, evidence=r.get("evidence", []),
                dissent=clamp_note, sleeve="conviction",
            ).finalize()                 # engine-derives the falsifier + check_by + time_stop_by
            appended = ledger.append(doc.to_json())
            if con is not None:
                try:
                    from data_layer import store
                    store.insert_thesis(con, doc.to_json())
                except Exception:
                    pass
            out.append({"id": doc.id, "subject": doc.subject, "lean": doc.lean,
                        "clamped": bool(clamp_note), "appended": appended,
                        "falsifier_kind": doc.falsifier["check"]["kind"]})
            kept.append({**r, "status": "ingested", "thesis_id": doc.id})

        try:
            _atomic_write_proposals(queue, kept)
        except Exception:
            # Ledger effects above may already be committed. Do not imply that nothing happened, and
            # do not expose backend details. The unchanged proposal queue intentionally remains
            # retry/reconciliation evidence; ledger.append's open-subject invariant prevents duplicates.
            return {
                "ingested": len(out),
                "clamped": sum(1 for o in out if o["clamped"]),
                "theses": out,
                "asof": asof,
                "proposal_queue_status": "unavailable",
                "proposal_rows_marked": False,
                "error": "proposal_queue_update_unavailable",
                "note": (
                    "Thesis-ledger effects may already be committed, but proposal queue status "
                    "could not be advanced; reconcile before interpreting the rows as unprocessed."
                ),
            }
        return {"ingested": len(out), "clamped": sum(1 for o in out if o["clamped"]), "theses": out, "asof": asof}


def daily_research_and_ingest(asof: str | None = None, *, blocked: set[str] | None = None) -> dict:
    """One call: run the armed research session, then gate its proposals into the ledger."""
    res = run_daily_research(asof)
    ing = ingest_proposals(asof, blocked=blocked)
    return {"research": {"ok": res.get("ok"), "tools_used": res.get("tools_used"),
                         "summary": (res.get("text") or "")[:600], "error": res.get("error")},
            "ingest": ing}
