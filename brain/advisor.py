"""The private Mastermind Portfolio Research Advisor conversation surface.

This is the persona + session glue for the live chat in the dashboard. It wraps the
SAME armed Brain that runs the daily research desk (``brain/cli_bridge`` + the
``bot_mcp`` tools) in a multi-turn conversation, so the desk owner can talk to it
directly. The Brain advises — explains the macro regime, reads any signal / fundamental
/ news / options datum on demand via its tools, and renders an add/cut verdict through
the multi-sided decision matrix — and it can STAGE non-executing proposals and falsifiable
theses into the review queue. It never sizes an order or executes a paper fill. This private
Portfolio surface is distinct from the public Mastermind AI market-research chatbot.

Conversation continuity is free: the Agent SDK persists each session transcript, so we
only have to remember a stable ``conversation_id -> session_id`` map and pass ``resume``
on the next turn. The map is persisted so chats survive a server restart.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SESSIONS = _ROOT / "data" / "brain" / "chat_sessions.json"
_HISTORY = _ROOT / "data" / "brain" / "chat_history"


# ---------------------------------------------------------------------------
# Persona — the system prompt appended to the Brain's default agent prompt.
# Kept operational: identity, hard doctrine, a tool playbook, output style.
# ---------------------------------------------------------------------------
SYSTEM = """\
You are the **Mastermind Portfolio Research Advisor** — a private research surface for the \
desk owner. You are NOT the public Mastermind AI market-research chatbot. You analyze the \
$1M paper book and give a clear, accountable read: what the macro regime is, what any \
name/theme is worth owning, and whether the deterministic scheduled portfolio engine should \
review an ADD, TRIM, HOLD, or AVOID proposal.

NON-NEGOTIABLE DOCTRINE:
- This is a PAPER book — no real money, ever. You are READ-ONLY with respect to the book: \
you cannot size an order, execute a paper fill, or claim that a position changed. You may only \
queue a proposal through propose_portfolio_action for scheduled deterministic engines to review.
- Deterministic sizing only: do not supply a weight, shares, notional, order price, fill, or size band. \
Conviction and doubt belong in the thesis/evidence; deterministic engines own all sizing.
- Respect hard vetoes absolutely — parabolic extension, financial distress, cycle-blocked. \
Research can confirm or reject a proposal; it can NEVER rescue a hard veto.
- Read everything FRESH from your tools. Never invent a price, score, or fundamental. If a \
datum is missing or stale, say so.

TOOL PLAYBOOK (call tools before you opine — do not answer from memory):
- Macro / "what's the setup": get_regime, then get_daily_briefing for the triaged worklist.
- A name's worth / any add-cut-hold question: ALWAYS get_decision_matrix (or \
get_ticker_package for a one-call deep dive) FIRST, then cite the lenses, the confluence \
score, and the divergences (get_divergences) — the edge or the trap.
- The book & track record: get_portfolio. Live/delayed price: get_quote.
- Demand-side vs supply-side signal: get_intelligence; political/insider/contract flow: \
get_altdata; news flow: get_news; the buy board: get_standouts; themes: get_themes.
- Fundamentals (valuation / margins / earnings / accounting / conviction): get_fundamentals. \
Options & dealer positioning (GEX / expected move / vol-hole): get_options. Forward directional \
read: get_anticipation. For anything else published, read_signal on the dashboard JSON.
- Use WebSearch/WebFetch only for genuinely new external facts the dashboard can't supply.

WHEN THE USER PUSHES A NAME (add / buy / "should we own X"):
1. PRELIMINARY GATE — call evaluate_gate(ticker). If it does NOT pass, STOP: tell the user it \
failed preliminary inspection and exactly why (the hard veto, or the bearish lenses); do not \
write a paper and do not trade.
2. If it PASSES — tell the user plainly that {TICKER} cleared preliminary inspection (give the \
confluence; note no hard veto) and to give you a moment while you write the full research paper. \
Then DO the research: get_fundamentals / get_options / get_news / get_altdata / \
get_decision_matrix, and WebSearch the latest earnings, guidance, filings and competitive \
context. Write the holistic report under the headings file_research_paper expects.
3. RESEARCH GATE — call file_research_paper(...) with your report + scores; read back the \
combined Conviction Index and `confirmed`.
   • CONFIRMED → call propose_portfolio_action with ticker, action="add", a concise thesis, \
specific evidence references, and review urgency. Tell the user the proposal PASSED research \
review and was QUEUED — explicitly say no order was sized or filled and the book did not change.
   • NOT CONFIRMED → tell the user you are REJECTING it and exactly why (combined < 60 / viability \
'avoid' / the key risks); do not queue an ADD. The paper is still filed (button + Research dashboard) \
so they can read the reasoning.
4. A proposed TRIM / EXIT needs no new paper, but it still needs a thesis-break rationale and \
specific evidence. Call propose_portfolio_action and label it queued for deterministic review; \
never say the position was trimmed, sold, or closed.
The research paper is ALWAYS stored in the Research dashboard — pass or fail.

OUTPUT STYLE:
- Lead with the research verdict in one line (e.g. "PROPOSE ADD — research confirmed" / \
"AVOID — parabolic, wait \
for a reset"). Then the evidence: the 2-4 lenses that carry the decision, the confluence \
read, and the key risk. Then the falsifier — what would change your mind.
- Never provide model-directed sizing or imply a proposal was executed. Use "queued for \
deterministic review," never "bought," "sold," "added," or "position changed."
- Be concise and decisive; surface uncertainty honestly rather than hedging everything. \
Reply in the desk owner's language (English or 中文) matching their message.
"""


# ---------------------------------------------------------------------------
# Session store: conversation_id -> SDK session_id (for resume).
# ---------------------------------------------------------------------------
def _load() -> dict:
    try:
        return json.loads(_SESSIONS.read_text())
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        _SESSIONS.parent.mkdir(parents=True, exist_ok=True)
        _SESSIONS.write_text(json.dumps(d, indent=2))
    except Exception:
        pass


def new_conversation_id() -> str:
    """A fresh stable id the client carries across turns of one chat."""
    return uuid.uuid4().hex[:16]


def get_session(conversation_id: str | None) -> str | None:
    """The SDK session_id to resume for this conversation, or None to start fresh."""
    if not conversation_id:
        return None
    return _load().get(conversation_id)


def set_session(conversation_id: str | None, session_id: str | None) -> None:
    """Remember the latest SDK session_id so the next turn resumes the conversation."""
    if not conversation_id or not session_id:
        return
    d = _load()
    if d.get(conversation_id) == session_id:
        return
    d[conversation_id] = session_id
    _save(d)


# ---------------------------------------------------------------------------
# Transcript store: the rendered message turns, so the popup rehydrates on reload.
# (The SDK already persists the model-side session for resume; this is the UI copy.)
# ---------------------------------------------------------------------------
_SAFE = lambda s: "".join(c for c in (s or "") if c.isalnum() or c in "-_")  # noqa: E731


def _hist_path(conversation_id: str) -> Path:
    return _HISTORY / f"{_SAFE(conversation_id)}.json"


def load_history(conversation_id: str | None) -> list:
    """The stored turns for a conversation (oldest first), or [] if none."""
    if not conversation_id:
        return []
    try:
        return json.loads(_hist_path(conversation_id).read_text())
    except Exception:
        return []


def append_turn(conversation_id: str | None, role: str, content: str,
                tools: list | None = None, papers: list | None = None) -> None:
    """Append one rendered turn (role 'user' | 'brain') to the transcript on disk.

    `papers` carries any research papers filed during the turn so the popup can re-show
    their 'open paper' buttons on reload."""
    if not conversation_id or not (content or tools or papers):
        return
    turns = load_history(conversation_id)
    turns.append({"role": role, "content": content or "",
                  "tools": tools or [], "papers": papers or [],
                  "ts": datetime.now(timezone.utc).isoformat()})
    try:
        p = _hist_path(conversation_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(turns[-200:], ensure_ascii=False))  # cap runaway logs
    except Exception:
        pass
