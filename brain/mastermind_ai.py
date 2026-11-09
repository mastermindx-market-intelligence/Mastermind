"""brain/mastermind_ai.py — legacy Mastermind Portfolio improvement coordinator (W-AI).

This compatibility-named module owns the *portfolio* loop the operator sees in the admin panel;
it is not the public Mastermind AI chatbot.  Each nightly tick runs the
observational self-improvement cycle (journal drafting + pin recompute + NW reflection), writes a
loop-log row, advances the three active regional books' post-sell learning ledgers, and every N
loops writes a review with a deterministic progress assessment. It also owns the
operator-adjustable settings and the operator→orchestrator directive queue.

AUTHORITY: none. The cycle writes files only — it never trades, never flips a flag, never mutates
a seat, a prompt, or a book. The only actors with any authority remain self_tune (through the Lab
harness gates, MASTERMIND_SELF_TUNE) and the operator.

FLAGS
  MASTERMIND_AI_LOOP        default ON  — the observational cycle (files only). '0' disables.
  MASTERMIND_AI_REVIEW_LLM  default OFF — allows an LLM prose assessment on review rows
                            (capability gate; the runtime setting llm_review must ALSO be on).

DATA LAYOUT (data/mastermind_ai/ — rsynced to the public mirror: counts/codes only, no prompts,
no sizes, no secrets; directive text is operator-authored OR auto-drafted from a nudge template,
both scrubbed on intake)
  settings.json    — operator overrides for the doctrine `mastermind_ai:` block (bounded keys).
  loop_log.jsonl   — one row per cycle {ts, asof, run_id, trigger, loop_n, steps, nudges_open,
                     summary, review?}.
  reviews.jsonl    — one row per N-loop review {ts, asof, loop_n, window, completed, assessment}.
  directives.jsonl — operator directives {id, ts, text, source: operator|nudge:<code>,
                     status: queued|published|acknowledged|expired}.
  last_ack.json    — the last macro ack observed {ts, nudge_codes_seen, directive_ids_seen_n}.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_DIR = _ROOT / "data" / "mastermind_ai"
_SETTINGS = _DIR / "settings.json"
_LOOP_LOG = _DIR / "loop_log.jsonl"
_REVIEWS = _DIR / "reviews.jsonl"
_DIRECTIVES = _DIR / "directives.jsonl"
_LAST_ACK = _DIR / "last_ack.json"

# ── settings (doctrine defaults + bounded operator overrides) ────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "loop_enabled": True,          # soft switch inside the MASTERMIND_AI_LOOP env gate
    "review_every_n_loops": 5,     # the user's "every five loops" review cadence
    "nudges_max": 10,              # cap on nudges emitted to the orchestrator
    "attribution_min_n": 12,       # cold-start guard for NW attribution
    "llm_review": False,           # runtime half of the LLM-review double gate
    "directives_max_open": 10,     # queued+published directives the publisher may carry
    "directive_expiry_days": 14,   # published-but-never-acknowledged directives expire after N days
    "auto_act_on_findings": False, # standing grant: run_cycle drafts directives from open nudges
}
# bounds enforced on operator writes — a settings API must never widen its own surface
_BOUNDS: dict[str, tuple] = {
    "loop_enabled": (bool,),
    "review_every_n_loops": (int, 2, 50),
    "nudges_max": (int, 1, 10),
    "attribution_min_n": (int, 6, 100),
    "llm_review": (bool,),
    "directives_max_open": (int, 1, 10),
    "directive_expiry_days": (int, 3, 60),
    "auto_act_on_findings": (bool,),
}

_DIRECTIVE_MAX_CHARS = 280
# intake refusal patterns (public artifact downstream): secrets, env names, $ amounts, key-shaped.
# Each carries its category label — rejections name the CATEGORY, never echo the matched text.
_DIRECTIVE_DENY: list[tuple[str, re.Pattern]] = [
    ("env-flag name", re.compile(r"MASTERMIND_[A-Z_]+")),
    ("dollar amount", re.compile(r"\$[\d,]+")),
    ("key-shaped token", re.compile(r"(?i)\b[A-Za-z0-9+/]{40,}\b")),
    ("credential assignment", re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]")),
]

_NUDGE_CODE_RE = re.compile(r"^[a-z0-9_]{1,60}$")
_DIRECTIVE_SOURCE_RE = re.compile(
    r"^(operator|nudge:[a-z0-9_]{1,60}|context:ctx-[a-f0-9]{16})$"
)
_CONTEXT_REQUEST_PREFIX = (
    "UNTRUSTED PM CONTEXT REQUEST; REQUEST ONLY; NO DATA, TOOL, CODE, SIZING, OR EXECUTION AUTHORITY. "
)

# nudge code -> auto-drafted directive text (draft_directives_from_nudges). Public-surface law:
# every template must clear _DIRECTIVE_DENY and the 280 cap — add_directive re-gates them anyway
# (no scrub exemption for the auto-draft path; tested in tests/test_mastermind_ai.py).
_NUDGE_DIRECTIVE_TEMPLATES: dict[str, str] = {
    "fdr_cleared_absent": (
        "Restore kernel.fdr_cleared production in candidate_context — zero rows currently clear, "
        "which deadens the bot's entire typed decision ladder. "
        "(auto-drafted from nudge fdr_cleared_absent)"),
    "bottom_state_vocabulary_drift": (
        "Publish BOTTOMING/CONFIRMED bottom states when detected — the artifact only ever shows "
        "WATCH, so candidacy priors above WATCH can never fire. "
        "(auto-drafted from nudge bottom_state_vocabulary_drift)"),
    "graph_conflicts_sparse": (
        "Raise graph_conflicts coverage in candidate_context — almost no rows carry it, keeping "
        "conflict-aware entry logic dark. (auto-drafted from nudge graph_conflicts_sparse)"),
    "graph_conflicts_absent": (
        "Populate graph_conflicts in candidate_context — no rows carry it, so the entry-shrink "
        "and clean-in-conflicted legs can never fire. "
        "(auto-drafted from nudge graph_conflicts_absent)"),
    "liquidity_plumbing_absent": (
        "Populate the market lobe liquidity block — it ships all-null, so liquidity context is "
        "unusable. (auto-drafted from nudge liquidity_plumbing_absent)"),
    "candidate_context_empty": (
        "candidate_context published with zero rows — restore candidate production. "
        "(auto-drafted from nudge candidate_context_empty)"),
    "coverage_below_half": (
        "Fewer than half of the bot's decided names have a candidate_context row — widen "
        "candidate coverage toward the bot's active universe. "
        "(auto-drafted from nudge coverage_below_half)"),
    "context_stale_streak": (
        "The NW context artifact has been stale for 3+ consecutive bot runs — check the publish "
        "lane. (auto-drafted from nudge context_stale_streak)"),
    "context_absent_streak": (
        "The NW context artifact has been absent for 3+ consecutive bot runs — check the publish "
        "lane. (auto-drafted from nudge context_absent_streak)"),
    "gap_notes_elevated": (
        "The context audit reports elevated gap notes — review the gaps list in the latest "
        "audit. (auto-drafted from nudge gap_notes_elevated)"),
}


def loop_flag_on() -> bool:
    return os.environ.get("MASTERMIND_AI_LOOP", "1").strip().lower() in ("1", "true", "yes", "on")


def llm_review_flag_on() -> bool:
    return os.environ.get("MASTERMIND_AI_REVIEW_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


def _doctrine_block() -> dict:
    try:
        from bot.doctrine_config import load_doctrine
        return load_doctrine().get("mastermind_ai") or {}
    except Exception:  # noqa: BLE001
        return {}


def _overrides() -> dict:
    try:
        if _SETTINGS.exists():
            v = json.loads(_SETTINGS.read_text())
            return v if isinstance(v, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _coerce(key: str, value: Any) -> Any | None:
    """Validate one settings value against _BOUNDS; None = rejected."""
    spec = _BOUNDS.get(key)
    if not spec:
        return None
    if spec[0] is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, str)):
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        return None
    if spec[0] is int:
        if isinstance(value, bool):
            return None   # int(True)==1 would silently pass bounds — reject bools outright
        try:
            iv = int(value)
        except Exception:  # noqa: BLE001
            return None
        lo, hi = spec[1], spec[2]
        return iv if lo <= iv <= hi else None
    return None


def settings() -> dict:
    """Effective settings: defaults ← doctrine block ← operator overrides (all bounded)."""
    out = dict(_DEFAULTS)
    for src in (_doctrine_block(), _overrides()):
        for k in _DEFAULTS:
            if k in src:
                v = _coerce(k, src[k])
                if v is not None:
                    out[k] = v
    return out


def update_settings(patch: dict) -> dict:
    """Apply a bounded operator patch to settings.json. Returns {ok, settings, rejected}."""
    rejected: list[str] = []
    try:
        cur = _overrides()
        for k, v in (patch or {}).items():
            if k not in _DEFAULTS:
                rejected.append(str(k))
                continue
            cv = _coerce(k, v)
            if cv is None:
                rejected.append(str(k))
                continue
            cur[k] = cv
        _DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS.write_text(json.dumps(cur, indent=2))
        return {"ok": True, "settings": settings(), "rejected": rejected}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}", "settings": settings(),
                "rejected": rejected}


# ── jsonl helpers ─────────────────────────────────────────────────────────────────────────────

def _read_jsonl(p: Path, limit: int | None = None) -> list[dict]:
    try:
        if p in (_LOOP_LOG, _REVIEWS):
            return _portfolio_public_rows(p, limit=limit)
        if not p.exists():
            return []
        rows = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(r, dict):
                rows.append(r)
        return rows[-limit:] if limit else rows
    except Exception:  # noqa: BLE001
        return []


def _append_jsonl(p: Path, row: dict) -> bool:
    """Append one complete row and report durability to state-machine callers."""
    if p in (_LOOP_LOG, _REVIEWS):
        return _portfolio_legacy_append(p, row)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: str) -> datetime | None:
    """Parse a _now_iso timestamp; None on failure (P2 — an unparseable ts never expires)."""
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


# ── directives (operator → orchestrator) ─────────────────────────────────────────────────────

def add_directive(text: str, source: str | None = None) -> dict:
    """Queue a scrubbed directive/request envelope for the next feedback publish.

    ``context:ctx-*`` rows are explicitly untrusted, request-only PM output.  Transporting that
    envelope cannot promote its authority; the downstream orchestrator must review it separately.
    Other invalid sources degrade to ``operator``.  Every text passes the same public-surface gate.
    """
    try:
        t = str(text or "").strip()
        if not t:
            return {"ok": False, "error": "empty"}
        if len(t) > _DIRECTIVE_MAX_CHARS:
            return {"ok": False, "error": f"too long (max {_DIRECTIVE_MAX_CHARS} chars)"}
        for cat, pat in _DIRECTIVE_DENY:
            if pat.search(t):
                # name the category only — echoing the match would republish the very
                # string the pattern exists to keep off the public artifact
                return {"ok": False,
                        "error": f"directive matches a public-surface deny pattern ({cat})"}
        # cap on the FOLDED latest-status view — raw rows would double-count a directive's
        # queued row + its published delta, and an expired/acked row must free its slot
        open_n = sum(1 for d in directives(limit=500)
                     if d.get("status") in ("queued", "published"))
        if open_n >= settings()["directives_max_open"]:
            return {"ok": False, "error": "too many open directives — wait for acknowledgement"}
        src = source if isinstance(source, str) and _DIRECTIVE_SOURCE_RE.match(source) else "operator"
        row = {
            "id": hashlib.sha256(f"{_now_iso()}|{t}".encode()).hexdigest()[:16],
            "ts": _now_iso(),
            "text": t,
            "source": src,
            "status": "queued",
        }
        if src.startswith("context:"):
            row.update({
                "kind": "pm_context_request",
                "provenance": "untrusted_pm_generated",
                "authority": "request_only",
                "execution_authority": False,
            })
        if not _append_jsonl(_DIRECTIVES, row):
            return {"ok": False, "error": "directive_write_failed"}
        return {"ok": True, "directive": row}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def _directive_text_for_nudge(code: str, detail: str) -> str:
    """Template text for a known nudge code; unknown codes get the truncated generic form."""
    t = _NUDGE_DIRECTIVE_TEMPLATES.get(code)
    if t:
        return t
    head = f"Address reflection finding {code}: "
    tail = ". (auto-drafted)"
    room = max(0, _DIRECTIVE_MAX_CHARS - len(head) - len(tail))
    body = str(detail or "").strip()
    # deny-scan the FULL detail before truncating — [:room] could cut a >=40-char key-shaped
    # run below the pattern floor and slip a credential prefix past add_directive's gate
    if any(p.search(body) for _, p in _DIRECTIVE_DENY):
        body = "detail withheld by the public-surface deny filter"
    return head + body[:room] + tail


def draft_directives_from_nudges(codes: list[str] | None = None) -> dict:
    """Draft directives from the currently open reflection nudges — operator bulk authoring.
    Authority is operator-granted: per-click via the API, or as a STANDING grant via the
    auto_act_on_findings setting. The loop calls this only under that standing grant; without
    it, authority still requires an explicit operator click.

    codes missing/empty means all currently open nudges. Returns
    {ok, queued: [{id, code, text}], skipped: [{code, reason}], open_slots}."""
    try:
        from brain import nw_reflection
        open_nudges: dict[str, dict] = {}
        report = nw_reflection.latest()
        for n in (report.get("nudges") or []):
            if isinstance(n, dict) and n.get("code") and nw_reflection.nudge_is_evaluable(report, n):
                open_nudges.setdefault(str(n["code"]), n)
        skipped: list[dict] = []
        wanted: list[str] = []
        for c in ([str(c) for c in codes] if codes else list(open_nudges)):
            if c in wanted:
                continue
            if c not in open_nudges:
                skipped.append({"code": c[:60], "reason": "no such open nudge"})
                continue
            wanted.append(c)
        # highest-severity first, oldest first within a severity — the slots should go to
        # the longest-standing asks
        sev_rank = {"high": 0, "medium": 1, "low": 2}
        wanted.sort(key=lambda c: (sev_rank.get(open_nudges[c].get("severity"), 3),
                                   str(open_nudges[c].get("first_seen") or ""), c))
        view = directives(limit=500)
        open_sources = {d.get("source") for d in view
                        if d.get("status") in ("queued", "published")}
        slots = max(0, settings()["directives_max_open"]
                    - sum(1 for d in view if d.get("status") in ("queued", "published")))
        queued: list[dict] = []
        for c in wanted:
            if f"nudge:{c}" in open_sources:
                skipped.append({"code": c, "reason": "open directive already exists for this nudge"})
                continue
            if slots <= 0:
                skipped.append({"code": c, "reason": "no open directive slots"})
                continue
            res = add_directive(_directive_text_for_nudge(c, str(open_nudges[c].get("detail") or "")),
                                source=f"nudge:{c}")
            if res.get("ok"):
                d = res["directive"]
                queued.append({"id": d["id"], "code": c, "text": d["text"]})
                open_sources.add(f"nudge:{c}")
                slots -= 1
            else:
                skipped.append({"code": c, "reason": str(res.get("error") or "rejected")})
        return {"ok": True, "queued": queued, "skipped": skipped, "open_slots": slots}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def draft_directives_from_context_requests() -> dict:
    """Forward typed portfolio context gaps into the existing audited Macro dialogue.

    This is request transport only.  It cannot expose a new file, alter a tool allowlist, edit code,
    or promote signal authority.  Macro's orchestrator still decides whether a request is useful and
    acknowledges the directive through the same bounded channel as every other improvement ask.
    """
    try:
        from brain import portfolio_learning

        view = directives(limit=500)
        # Repair either half of a previously interrupted two-ledger transition before selecting
        # new work. This is idempotent and cannot elevate the originating request's authority.
        for directive in view:
            if str(directive.get("source") or "").startswith("context:"):
                _sync_context_request(directive)
        pending = [
            row for row in portfolio_learning.context_requests(limit=None)
            if row.get("status") == "queued_for_orchestrator_review"
        ]
        slots = max(
            0,
            settings()["directives_max_open"]
            - sum(1 for row in view if row.get("status") in ("queued", "published")),
        )
        directive_by_source = {
            str(row.get("source") or ""): row
            for row in view
            if str(row.get("source") or "").startswith("context:")
        }
        queued: list[dict] = []
        skipped: list[dict] = []
        for request in pending:
            request_id = str(request.get("id") or "")
            source = f"context:{request_id}"
            existing_directive = directive_by_source.get(source)
            if existing_directive:
                repaired = _sync_context_request(existing_directive)
                skipped.append({
                    "id": request_id,
                    "reason": (
                        "directive already exists"
                        if repaired else "directive exists but request transition write failed"
                    ),
                })
                continue
            if slots <= 0:
                skipped.append({"id": request_id, "reason": "no open directive slots"})
                continue
            ticker = f" for {request.get('ticker')}" if request.get("ticker") else ""
            text = _CONTEXT_REQUEST_PREFIX + (
                f"Review {request.get('book')} portfolio request for context plane "
                f"{request.get('plane')}{ticker}: {request.get('reason')}"
            )
            text = text[:_DIRECTIVE_MAX_CHARS]
            result = add_directive(text, source=source)
            if not result.get("ok"):
                skipped.append({"id": request_id, "reason": str(result.get("error") or "rejected")})
                continue
            directive = result["directive"]
            advanced = portfolio_learning.advance_context_request(
                request_id,
                "directive_queued",
                directive_id=directive["id"],
            )
            if not advanced:
                skipped.append({"id": request_id,
                                "reason": "directive queued but request transition write failed"})
                directive_by_source[source] = directive
                slots -= 1
                continue
            queued.append({"id": request_id, "directive_id": directive["id"]})
            directive_by_source[source] = directive
            slots -= 1
        return {"ok": True, "queued": queued, "skipped": skipped, "open_slots": slots}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def directives(limit: int = 50) -> list[dict]:
    """Latest-status view of the directive queue (last write per id wins)."""
    by_id: dict[str, dict] = {}
    for row in _read_jsonl(_DIRECTIVES):
        rid = row.get("id")
        if rid:
            by_id[rid] = {**by_id.get(rid, {}), **row}
    # str() the key — a corrupt hand-edited ts (e.g. an int) must degrade the ordering,
    # never raise a TypeError up through status() and blank the whole admin snapshot
    rows = sorted(by_id.values(), key=lambda r: str(r.get("ts", "")))
    return rows[-limit:]


def _advance_directive(rid: str, status: str) -> bool:
    return _append_jsonl(_DIRECTIVES, {"id": rid, "ts": _now_iso(), "status": status})


def _sync_context_request(directive: dict) -> bool:
    """Mirror one durable directive state without ever promoting the PM request's authority."""
    source = str(directive.get("source") or "")
    if not source.startswith("context:"):
        return True
    request_status = {
        "queued": "directive_queued",
        "published": "published_to_orchestrator",
        "acknowledged": "acknowledged_by_orchestrator",
        "expired": "expired_unacknowledged",
    }.get(str(directive.get("status") or ""))
    if not request_status:
        return True
    try:
        from brain import portfolio_learning
        return portfolio_learning.advance_context_request(
            source.removeprefix("context:"),
            request_status,
            directive_id=directive.get("id"),
        )
    except Exception:  # noqa: BLE001
        return False


def open_directives_for_publish() -> list[dict]:
    """The rows bridge/nw_feedback ships (queued+published, capped FIFO).

    Truncates FIRST (oldest-first, so early directives are never starved), then advances
    queued→published ONLY for rows actually included in the publish payload — a row must
    never read 'published' unless it shipped (review finding, 2026-07-13)."""
    out: list[dict] = []
    try:
        cap = settings()["directives_max_open"]
        open_rows = [d for d in directives()
                     if d.get("status") in ("queued", "published") and d.get("text")]
        for d in open_rows[:cap]:   # directives() is ts-ascending → FIFO
            if d.get("status") == "queued":
                if not _advance_directive(d["id"], "published"):
                    continue
                d = {**d, "status": "published"}
            # A context request is not put on the wire unless both local ledgers agree that it is
            # published. If the second append fails, compensate the directive back to queued so the
            # next call retries the paired transition before transport.
            if not _sync_context_request(d):
                # The directive ledger is writable (the published append above succeeded), so
                # compensate back to queued. No request is emitted unless both ledgers agree.
                _advance_directive(d["id"], "queued")
                continue
            out.append({"id": d["id"], "created": d.get("ts", "")[:10], "text": d["text"]})
        return out
    except Exception:  # noqa: BLE001
        return out


def _write_last_ack(seen_codes: set, seen_ids: set) -> None:
    """Persist the ack sighting for dialogue_health. Fail-soft; codes re-validated —
    this file lands on the public mirror."""
    try:
        codes = sorted(c for c in seen_codes if isinstance(c, str) and _NUDGE_CODE_RE.match(c))
        _DIR.mkdir(parents=True, exist_ok=True)
        _LAST_ACK.write_text(json.dumps({
            "ts": _now_iso(),
            "nudge_codes_seen": codes,
            "directive_ids_seen_n": len(seen_ids),
        }, indent=2))
    except Exception:  # noqa: BLE001
        pass


def reconcile_ack() -> dict:
    """Advance directive statuses from the macro ack (lobes.mastermind_ai in the NW context)."""
    try:
        from brain import neural_web_context as nwc
        # The context reader caches for the process lifetime; without a reset a long-lived
        # process could never observe an ack published after its first read (review finding).
        try:
            nwc._reset_context_cache()
        except Exception:  # noqa: BLE001
            pass
        lobe = (nwc.context() or {}).get("lobes", {}).get("mastermind_ai") or {}
        ack = lobe.get("ack") or {}
        seen_ids = set(ack.get("directive_ids_seen") or [])
        seen_codes = set(ack.get("nudge_codes_seen") or [])
        if ack:
            _write_last_ack(seen_codes, seen_ids)
        advanced = 0
        durably_acknowledged: set[str] = set()
        for d in directives():
            if (d.get("status") == "published" and d.get("id") in seen_ids and
                    _advance_directive(d["id"], "acknowledged")):
                advanced += 1
                durably_acknowledged.add(str(d["id"]))
        context_advanced = 0
        try:
            from brain import portfolio_learning
            context_advanced = portfolio_learning.acknowledge_context_directives(
                durably_acknowledged
            )
        except Exception:  # noqa: BLE001
            pass
        return {"state": "ok" if lobe else "absent",
                "directives_acknowledged": advanced,
                "context_requests_acknowledged": context_advanced,
                "nudge_codes_seen_n": len(seen_codes)}
    except Exception:  # noqa: BLE001
        return {"state": "absent", "directives_acknowledged": 0,
                "context_requests_acknowledged": 0, "nudge_codes_seen_n": 0}


def expire_stale_published() -> dict:
    """Expire published directives never acknowledged within directive_expiry_days.

    Judged on the LAST transition to published; appends 'expired' delta rows so the fold
    drops them from the publish wire and the open cap. Never raises."""
    out = {"expired": 0}
    try:
        days = int(settings()["directive_expiry_days"])
        cut = datetime.now(timezone.utc) - timedelta(days=days)
        last_pub: dict[str, str] = {}
        for row in _read_jsonl(_DIRECTIVES):
            if row.get("id") and row.get("status") == "published":
                last_pub[row["id"]] = row.get("ts", "")
        for d in directives(limit=500):
            if d.get("status") != "published":
                continue
            ts = _parse_ts(last_pub.get(d.get("id"), ""))
            if ts is not None and ts < cut:
                if not _advance_directive(d["id"], "expired"):
                    continue
                out["expired"] += 1
                _sync_context_request({**d, "status": "expired"})
    except Exception:  # noqa: BLE001
        pass
    return out


def dialogue_health() -> dict:
    """The bot↔orchestrator dialogue health block for status() (W-AI.1 contract).

    counterparty is 'live' once ANY macro ack has ever been observed (loop-log ack state 'ok'
    or a persisted last_ack.json) — 'absent' means we have only ever spoken into the void."""
    out: dict[str, Any] = {"counterparty": "absent", "ack_seen_ever": False,
                           "loops_since_ack": None, "published_open_n": 0, "queued_n": 0,
                           "expired_n": 0, "oldest_published_age_days": None, "last_ack": None}
    try:
        rows = _read_jsonl(_LOOP_LOG)
        for i, r in enumerate(rows):
            if ((r.get("steps") or {}).get("ack") or {}).get("state") == "ok":
                out["ack_seen_ever"] = True
                out["loops_since_ack"] = len(rows) - 1 - i
        try:
            if _LAST_ACK.exists():
                v = json.loads(_LAST_ACK.read_text())
                if isinstance(v, dict):
                    out["last_ack"] = v
                    out["ack_seen_ever"] = True
        except Exception:  # noqa: BLE001
            pass
        out["counterparty"] = "live" if out["ack_seen_ever"] else "absent"
        last_pub: dict[str, str] = {}
        for row in _read_jsonl(_DIRECTIVES):
            if row.get("id") and row.get("status") == "published":
                last_pub[row["id"]] = row.get("ts", "")
        oldest: datetime | None = None
        for d in directives(limit=500):
            st = d.get("status")
            if st == "queued":
                out["queued_n"] += 1
            elif st == "published":
                out["published_open_n"] += 1
                ts = _parse_ts(last_pub.get(d.get("id"), ""))
                if ts is not None and (oldest is None or ts < oldest):
                    oldest = ts
            elif st == "expired":
                out["expired_n"] += 1
        if oldest is not None:
            out["oldest_published_age_days"] = max(0, (datetime.now(timezone.utc) - oldest).days)
    except Exception:  # noqa: BLE001
        pass
    return out


# ── the cycle ─────────────────────────────────────────────────────────────────────────────────

def _self_tune_state() -> dict:
    try:
        p = _ROOT / "data" / "self_tune" / "state.json"
        if p.exists():
            v = json.loads(p.read_text())
            if isinstance(v, dict):
                fams = v.get("families") or {}
                return {"families_n": len(fams),
                        "locked": [k for k, f in fams.items()
                                   if isinstance(f, dict) and f.get("proposal_only")],
                        "armed": bool(os.environ.get("MASTERMIND_SELF_TUNE", "0").strip()
                                      .lower() in ("1", "true", "yes", "on"))}
    except Exception:  # noqa: BLE001
        pass
    return {"families_n": 0, "locked": [], "armed": False}


def _journal_counts() -> dict:
    out = {"drafts": 0, "pending": 0, "lessons": 0, "pins_active": 0, "pins_unpinned": 0}
    try:
        from brain import journal
        for seat in journal.SEATS:
            out["drafts"] += len(journal.load_drafts(seat))
            out["pending"] += len(journal.pending_for(seat))
            out["lessons"] += len(journal.load_lessons(seat))
            for pin in journal.load_pins(seat):
                if pin.get("status") == "active":
                    out["pins_active"] += 1
                elif pin.get("status") == "unpinned":
                    out["pins_unpinned"] += 1
    except Exception:  # noqa: BLE001
        pass
    return out


def _agenda_top(n: int = 3) -> list[str]:
    # Titles land in loop_log.jsonl / reviews.jsonl, which rsync to the public mirror. Scrub
    # them like the LLM assessment: today every title is a code-authored count template, but a
    # future agenda source must not leak a secret / env name / $ amount through this seam.
    try:
        from brain import improvement_agenda as agenda
        rep = agenda.latest() or {}
        out: list[str] = []
        for it in (rep.get("items") or [])[:n]:
            title = str(it.get("title", ""))[:120]
            if any(p.search(title) for _, p in _DIRECTIVE_DENY):
                title = "agenda item withheld by the public-surface deny filter"
            out.append(title)
        return out
    except Exception:  # noqa: BLE001
        return []


def _cycle_snapshot(asof_s: str, trigger: str, cfg: dict, loop_n: int, loop_rows: list) -> tuple[dict, dict | None]:
    """Existing deterministic business steps; the caller owns reservation/publication."""
    steps: dict[str, Any] = {}

    # 1. journal maintenance (idempotent, deterministic — the seats still own their lessons)
    try:
        from brain import journal
        d = journal.draft_all()
        steps["journal_drafts_added"] = sum(v for v in d.values() if isinstance(v, int)) if isinstance(d, dict) else 0
        pins_changed = 0
        for seat in journal.SEATS:
            try:
                pins_changed += len(journal.recompute_pins(seat) or [])
            except Exception:  # noqa: BLE001
                continue
        steps["pins_recomputed"] = pins_changed
    except Exception as exc:  # noqa: BLE001
        steps["journal_error"] = type(exc).__name__

    # 2. NW reflection (the dialogue substrate)
    try:
        from brain import nw_reflection
        rep = nw_reflection.persist(asof_s, nudges_max=cfg["nudges_max"],
                                    attribution_min_n=cfg["attribution_min_n"])
        steps["reflection"] = {
            "drift_n": len(rep.get("contract_drift") or []),
            "nudges_n": len(rep.get("nudges") or []),
            "coverage_rate": (rep.get("coverage") or {}).get("coverage_rate"),
            "seen_rate": (rep.get("context_quality") or {}).get("seen_rate"),
        }
        nudges_open = len(rep.get("nudges") or [])
    except Exception as exc:  # noqa: BLE001
        steps["reflection_error"] = type(exc).__name__
        nudges_open = 0

    # 3. ack reconciliation (macro → bot half of the dialogue) + directive expiry
    steps["ack"] = reconcile_ack()
    steps["directive_expiry"] = expire_stale_published()

    # Typed PM context requests have an independent request-only transport lane. Forwarding the
    # explicitly untrusted envelope does not grant the requested plane, alter tools, or authorize an
    # implementation; Macro/operator review remains the separate authority boundary.
    try:
        context_result = draft_directives_from_context_requests()
        steps["context_request_transport"] = {
            "ok": bool(context_result.get("ok")),
            "queued_n": len(context_result.get("queued") or []),
            "skipped_n": len(context_result.get("skipped") or []),
            **({"error": context_result.get("error")} if context_result.get("error") else {}),
        }
    except Exception as exc:  # noqa: BLE001
        steps["context_request_transport"] = {"ok": False, "queued_n": 0,
                                              "skipped_n": 0, "error": type(exc).__name__}

    # Auto-drafting deterministic NW findings remains separately operator-gated. It runs after
    # request transport so model-authored context gaps cannot be starved by the nudge queue.
    if cfg.get("auto_act_on_findings"):
        try:
            nudge_result = draft_directives_from_nudges()  # no codes = all open nudges
            if nudge_result.get("ok"):
                queued_n = len(nudge_result.get("queued") or [])
                skipped_n = len(nudge_result.get("skipped") or [])
                steps["auto_draft"] = {
                    "queued_n": queued_n,
                    "skipped_n": skipped_n,
                    "nw_nudges_queued": len(nudge_result.get("queued") or []),
                }
            else:
                steps["auto_draft"] = {
                    "error": str(nudge_result.get("error") or "draft_failed")
                }
        except Exception as exc:  # noqa: BLE001
            steps["auto_draft"] = {"error": type(exc).__name__}

    # 4. portfolio behavioural learning.  This is bounded memory, not self-modifying code:
    # it grades completed exits, derives evidence-labelled lessons, and queues typed context
    # requests for operator/orchestrator review.  It cannot trade, resize a book, change a
    # prompt on disk, or grant itself new infrastructure authority.
    try:
        from brain import portfolio_learning
        learned = portfolio_learning.refresh_all(asof_s)
        steps["portfolio_learning"] = {
            book: {
                "ok": state.get("ok", False),
                "lessons_n": state.get("lessons_n", 0),
                "post_sell": state.get("post_sell") or {},
                **({"error": state.get("error")} if state.get("error") else {}),
            }
            for book, state in (learned.get("books") or {}).items()
            if isinstance(state, dict)
        }
    except Exception as exc:  # noqa: BLE001
        steps["portfolio_learning_error"] = type(exc).__name__

    # 5. state snapshots for the log
    jc = _journal_counts()
    steps["journal"] = jc
    steps["self_tune"] = _self_tune_state()
    steps["agenda_top"] = _agenda_top()

    summary = (f"loop {loop_n}: {steps.get('journal_drafts_added', 0)} new journal drafts, "
               f"{jc['pending']} lessons pending, {jc['pins_active']} pinned rules, "
               f"{nudges_open} open nudges to the orchestrator"
               + (f", {steps['ack']['directives_acknowledged']} directives acknowledged"
                  if steps.get("ack", {}).get("directives_acknowledged") else "")
               + (f", {steps['auto_draft']['queued_n']} directives auto-drafted"
                  if steps.get("auto_draft", {}).get("queued_n") else ""))
    # one honest clause when nobody has been listening — the loop must not read as healthy
    # dialogue while every publish lands in the void
    try:
        if (steps.get("ack") or {}).get("state") != "ok":
            absent = 1
            for r in reversed(loop_rows):
                if ((r.get("steps") or {}).get("ack") or {}).get("state") == "ok":
                    break
                absent += 1
            if absent >= 3:
                summary += f"; macro ack absent {absent} loops"
    except Exception:  # noqa: BLE001
        pass

    row: dict[str, Any] = {
        "ts": _now_iso(), "asof": asof_s, "trigger": trigger, "loop_n": loop_n,
        "steps": steps, "nudges_open": nudges_open, "summary": summary, "ok": True,
    }
    try:
        from brain import runlog as _runlog  # optional run id correlation
        row["run_id"] = getattr(_runlog, "current_run_id", lambda: None)() or None
    except Exception:  # noqa: BLE001
        pass

    review = (_deterministic_review(loop_n, cfg)
              if loop_n % max(2, int(cfg["review_every_n_loops"])) == 0 else None)
    if review is not None:
        row["review"] = {"loop_n": loop_n, "assessment_n": len(review.get("assessment") or [])}
    return row, review


def _trend(first, last) -> str:
    try:
        if first is None or last is None:
            return "flat"
        return "up" if last > first else ("down" if last < first else "flat")
    except Exception:  # noqa: BLE001
        return "flat"


def _deterministic_review(loop_n: int, cfg: dict) -> dict:
    """Deterministic N-loop review: what was completed + an honest progress assessment."""
    n = max(2, int(cfg["review_every_n_loops"]))
    window = _read_jsonl(_LOOP_LOG, limit=n - 1)  # current row not yet appended
    completed = {
        "loops": n,
        "journal_drafts_added": sum(int(r.get("steps", {}).get("journal_drafts_added") or 0)
                                    for r in window),
        "directives_acknowledged": sum(int(r.get("steps", {}).get("ack", {})
                                           .get("directives_acknowledged") or 0) for r in window),
    }
    assessment: list[str] = []

    # nudge trajectory
    hist = []
    try:
        from brain import nw_reflection
        hist = nw_reflection._read_jsonl(nw_reflection._HISTORY, limit=n)
    except Exception:  # noqa: BLE001
        pass
    if len(hist) >= 2:
        first, last = hist[0], hist[-1]
        assessment.append(f"open nudges {_trend(first.get('nudges_n'), last.get('nudges_n'))} "
                          f"({first.get('nudges_n')} -> {last.get('nudges_n')}); "
                          f"context seen-rate {_trend(first.get('seen_rate'), last.get('seen_rate'))} "
                          f"({first.get('seen_rate')} -> {last.get('seen_rate')}); "
                          f"coverage {_trend(first.get('coverage_rate'), last.get('coverage_rate'))} "
                          f"({first.get('coverage_rate')} -> {last.get('coverage_rate')})")

    # learning-floor status (W-L falsifiers, honestly cold-start)
    try:
        from brain import outcome_ledger
        s = outcome_ledger.summary() or {}
        assessment.append(f"outcome ledger: n={s.get('n', 0)}, "
                          f"hit_rate={s.get('hit_rate')}, brier={s.get('brier')} "
                          f"(status {'scoring' if (s.get('n') or 0) >= 12 else 'building'})")
    except Exception:  # noqa: BLE001
        pass
    try:
        from brain import portfolio_learning
        learning = portfolio_learning.status()
        active_summary: dict[str, dict] = {}
        for book, block in (learning.get("books") or {}).items():
            lessons = (block.get("lessons") or {}).get("lessons") or []
            post_sell = block.get("post_sell") or {}
            active_summary[book] = {
                "lesson_codes": [str(row.get("code")) for row in lessons if row.get("code")],
                "post_sell_n": post_sell.get("n_sales", post_sell.get("n_exits", 0)),
                "full_exits_n": post_sell.get("n_exits", 0),
                "partial_trims_n": post_sell.get("n_partial_trims", 0),
            }
        completed["active_portfolio_learning"] = active_summary
        requests = learning.get("context_requests") or []
        request_states: dict[str, int] = {}
        for request in requests:
            state = str(request.get("status") or "unknown")
            request_states[state] = request_states.get(state, 0) + 1
        assessment.append(
            "active portfolio learning: "
            + json.dumps(active_summary, separators=(",", ":"), sort_keys=True)
            + "; context requests "
            + json.dumps(request_states, separators=(",", ":"), sort_keys=True)
        )
    except Exception:  # noqa: BLE001
        pass
    jc = _journal_counts()
    assessment.append(f"journal: {jc['lessons']} lessons banked, {jc['pins_active']} rules pinned "
                      f"({jc['pins_unpinned']} unpinned by their own falsifiers), "
                      f"{jc['pending']} lessons still owed by seats")
    st = _self_tune_state()
    assessment.append(f"self_tune: {'ARMED' if st['armed'] else 'dark'}, "
                      f"{st['families_n']} families tracked, {len(st['locked'])} locked proposal-only")
    dh = dialogue_health()
    if dh["counterparty"] == "absent":
        assessment.append(f"orchestrator dialogue: no macro ack ever seen — "
                          f"{dh['published_open_n']} directives published into the void, "
                          f"{dh['expired_n']} expired unacknowledged")
    else:
        assessment.append(f"orchestrator dialogue: counterparty live "
                          f"({dh['loops_since_ack']} loops since last ack), "
                          f"{dh['published_open_n']} published open, {dh['expired_n']} expired")

    review = {
        "ts": _now_iso(), "loop_n": loop_n, "window_loops": n,
        "completed": completed, "assessment": assessment,
        "agenda_top": _agenda_top(5),
    }

    return review


# The existing two public journals own cycle and optional-prose custody. Nested
# versions replace one logical row atomically; no private sidecar or usage sink.
_PORTFOLIO_CYCLE = "_portfolio_cycle"
_PORTFOLIO_REVIEW = "_portfolio_review"
_PORTFOLIO_ANCHOR = "_portfolio_anchor"
_PORTFOLIO_LANE = "mastermind-portfolio-review"
_PORTFOLIO_SERVICE = "macro_portfolio_fabric"
_PORTFOLIO_WORKLOAD = "portfolio_analysis"
_PORTFOLIO_MAX_TOKENS = 1500
_PORTFOLIO_LOCK = "global:mastermind-portfolio-review"
_PORTFOLIO_PROMPT_VERSION = "portfolio-progress-v1"
_PORTFOLIO_PRIVATE = re.compile(
    r"(?i)(?:https?://|file://|(?:^|\s)/(?:Users|Volumes|home|root|opt|tmp)/|"
    r"(?:api[_-]?key|token|secret|password|credential)[a-z0-9_-]*\s*[:=])")
_PORTFOLIO_REASONS = frozenset({
    "pending", "accepted", "prose_rejected", "response_unusable",
    "binding_unavailable", "close_unsettled", "observation_unsettled",
    "journal_unavailable", "original_incomplete", "selection_changed", "disabled",
})
_REVIEW_FIELDS = frozenset({"ts", "loop_n", "window_loops", "completed", "assessment", "agenda_top"})


class _PortfolioHeld(ValueError):
    """A bounded local reason; private exception text never enters public data."""


def _portfolio_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _portfolio_hash(value):
    return hashlib.sha256(_portfolio_json(value)).hexdigest()


def _portfolio_decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise _PortfolioHeld("journal_unavailable")
            value[key] = item
        return value
    def invalid(_):
        raise _PortfolioHeld("journal_unavailable")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _portfolio_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _portfolio_id(value):
    return (type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value)
            is not None)


def _portfolio_label(value):
    return (type(value) is str and 0 < len(value) <= 128 and "://" not in value
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value) is not None
            and not _PORTFOLIO_PRIVATE.search(value)
            and not any(pattern.search(value) for _, pattern in _DIRECTIVE_DENY))


def _portfolio_text(text):
    # Sweep the COMPLETE candidate before truncation. Rejected output is never
    # written to a public journal, including internal observation versions.
    if (type(text) is not str or not text.strip() or len(text.encode("utf-8")) > 1048576
            or any(pattern.search(text) for _, pattern in _DIRECTIVE_DENY)
            or _PORTFOLIO_PRIVATE.search(text)):
        return None
    return text[:2000]


def _portfolio_public_input(value):
    """Check already public facts, not opaque owner commitments."""
    if isinstance(value, dict):
        return all(type(k) is str and _portfolio_public_input(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_portfolio_public_input(v) for v in value)
    if isinstance(value, str):
        return (len(value) <= 16000 and not any(p.search(value) for _, p in _DIRECTIVE_DENY)
                and not _PORTFOLIO_PRIVATE.search(value))
    if value is None or type(value) in (bool, int):
        return True
    if type(value) is float:
        import math
        return math.isfinite(value)
    return False


def _portfolio_path(path, *, create=False):
    path = Path(path).absolute()
    declared = Path(_ROOT).absolute()
    root = declared.resolve(strict=True)
    try:
        relative = path.parent.relative_to(declared)
    except ValueError:
        relative = path.parent.relative_to(root)
    path = root / relative / path.name
    current = root
    for part in relative.parts:
        if part in (".", ".."):
            raise _PortfolioHeld("journal_unavailable")
        current = current / part
        if create:
            current.mkdir(exist_ok=True)
        if current.is_symlink() or current.exists() and not current.is_dir():
            raise _PortfolioHeld("journal_unavailable")
        if create:
            _portfolio_sync(current.parent)
    if create:
        _portfolio_sync(current)
    return path


def _portfolio_sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _portfolio_read(path):
    """Strict bounded authority read, retaining exact legacy line bytes."""
    import stat
    path = _portfolio_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return b"", [], []
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32 * 1024 * 1024:
            raise _PortfolioHeld("journal_unavailable")
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024 or raw and not raw.endswith(b"\n"):
        raise _PortfolioHeld("journal_unavailable")
    lines, rows = raw.splitlines(keepends=True), []
    if len(lines) > 50000:
        raise _PortfolioHeld("journal_unavailable")
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if len(line) > 262144:
            raise _PortfolioHeld("journal_unavailable")
        value = _portfolio_decode(line)
        if type(value) is not dict:
            raise _PortfolioHeld("journal_unavailable")
        rows.append((index, value))
    return raw, lines, rows


def _portfolio_store(path, *, expected, row, index=None):
    """CAS one row in the existing journal; retain all other bytes exactly.

    Callers hold the existing root lock. A failed write/readback leaves the
    original record or the new complete version for subsequent local inspection.
    """
    import tempfile
    path = _portfolio_path(path, create=True)
    before, lines, _ = _portfolio_read(path)
    if before != expected:
        raise _PortfolioHeld("journal_unavailable")
    encoded = _portfolio_json(row) + b"\n"
    if len(encoded) > 262144:
        raise _PortfolioHeld("journal_unavailable")
    if index is None:
        lines.append(encoded)
    else:
        if type(index) is not int or not 0 <= index < len(lines):
            raise _PortfolioHeld("journal_unavailable")
        lines[index] = encoded
    raw = b"".join(lines)
    if len(raw) > 32 * 1024 * 1024:
        raise _PortfolioHeld("journal_unavailable")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".tmp-",
                                         delete=False) as target:
            temporary = Path(target.name)
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        if _portfolio_read(path)[0] != expected:
            raise _PortfolioHeld("journal_unavailable")
        os.replace(temporary, path)
        _portfolio_sync(path.parent)
        _portfolio_sync(path.parent.parent)
        if _portfolio_read(path)[0] != raw:
            raise _PortfolioHeld("journal_unavailable")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _portfolio_lock():
    from contextlib import contextmanager
    @contextmanager
    def locked():
        import stat
        from control_plane import locks
        # The incumbent lock owner retains the one mutex. Reject changed or
        # symlinked directory/lock identities before trusting it.
        _portfolio_path(Path(_ROOT) / "data/locks/guard", create=True)
        lock = locks.acquire(_PORTFOLIO_LOCK, root=_ROOT)
        if lock is None:
            raise _PortfolioHeld("journal_unavailable")
        with lock:
            actual, opened = os.lstat(lock._path), os.fstat(lock._fd)
            if (not stat.S_ISREG(actual.st_mode)
                    or (actual.st_dev, actual.st_ino) != (opened.st_dev, opened.st_ino)):
                raise _PortfolioHeld("journal_unavailable")
            _portfolio_sync(lock._path.parent)
            yield
    return locked()


def _portfolio_selected():
    from brain import cli_bridge
    return cli_bridge._application_fabric_selected()


def _portfolio_base(review):
    base = {key: review[key] for key in _REVIEW_FIELDS if key in review}
    if (set(base) != _REVIEW_FIELDS or type(base["loop_n"]) is not int or base["loop_n"] < 1
            or type(base["window_loops"]) is not int or not 2 <= base["window_loops"] <= 50
            or type(base["completed"]) is not dict or type(base["assessment"]) is not list
            or any(type(item) is not str for item in base["assessment"])
            or type(base["agenda_top"]) is not list or type(base["ts"]) is not str
            or _parse_ts(base["ts"]) is None or not _portfolio_public_input(base)):
        raise _PortfolioHeld("journal_unavailable")
    _portfolio_json(base)
    return base


def _portfolio_prompt(base):
    return ("You are the Mastermind Portfolio reviewing your bounded improvement loop. "
            "In <=150 words, assess progress honestly (no alpha claims): "
            + json.dumps({"completed": base["completed"], "assessment": base["assessment"]},
                         sort_keys=True, separators=(",", ":"))[:4000])


def _portfolio_request(base, operation_id):
    from engine import fabric_inference_client as transport
    _, raw = transport._request({"model": None, "request_id": operation_id + ":brain:0",
        "max_tokens": _PORTFOLIO_MAX_TOKENS,
        "messages": [{"role": "user", "content": _portfolio_prompt(base)}]}, None, False)
    original = transport._load_json(raw, unknown=False)
    return original, {"request_id": operation_id + ":brain:0",
        "digest": transport._auto_request_digest(original),
        "max_tokens": _PORTFOLIO_MAX_TOKENS, "requested_model": None}


def _portfolio_ref(row):
    owned = row[_PORTFOLIO_REVIEW]
    return {"loop_n": row["loop_n"], "operation_id": owned["operation_id"],
            "input_digest": owned["input_digest"]}


def _portfolio_ref_valid(value):
    return (type(value) is dict and set(value) == {"loop_n", "operation_id", "input_digest"}
            and type(value["loop_n"]) is int and value["loop_n"] > 0
            and _portfolio_id(value["operation_id"]) and _portfolio_digest(value["input_digest"]))


def _portfolio_close(value):
    if value is None:
        return None
    fields = {"disposition", "closed", "effect_unknown", "attempted"}
    if (type(value) is not dict or set(value) != fields
            or value["disposition"] not in ("closed", "not_bound", "not_admitted", "refused",
                                             "pending", "effect_unknown", "not_required")
            or any(type(value[k]) is not bool for k in ("closed", "effect_unknown", "attempted"))):
        raise _PortfolioHeld("journal_unavailable")
    closed = {"disposition": "closed", "closed": True, "effect_unknown": False, "attempted": True}
    if (value["closed"] or value["disposition"] == "closed") and value != closed:
        raise _PortfolioHeld("journal_unavailable")
    if value["disposition"] == "not_bound" and value != {
            "disposition": "not_bound", "closed": False, "effect_unknown": False, "attempted": False}:
        raise _PortfolioHeld("journal_unavailable")
    return value


def _portfolio_validate_review(row):
    base = _portfolio_base(row)
    owned = row.get(_PORTFOLIO_REVIEW)
    if owned is None:
        return row
    fields = {"schema", "operation_id", "cycle_id", "input_digest", "prompt_version",
              "authority", "request", "phase", "approved_text", "text_digest",
              "receipt", "reason", "revision", "original_digest"}
    if (set(row) != _REVIEW_FIELDS | {_PORTFOLIO_REVIEW} or type(owned) is not dict
            or set(owned) != fields or owned["schema"] != "mastermind.portfolio_review.fabric.v1"
            or not _portfolio_id(owned["operation_id"])
            or owned["cycle_id"] is not None and not _portfolio_id(owned["cycle_id"])
            or owned["input_digest"] != _portfolio_hash(base)
            or owned["prompt_version"] != _PORTFOLIO_PROMPT_VERSION
            or owned["phase"] not in ("pending", "observed", "terminal", "held")
            or type(owned["revision"]) is not int
            or owned["revision"] != {"pending": 0, "observed": 1, "terminal": 2, "held": 2}[owned["phase"]]
            or owned["reason"] not in _PORTFOLIO_REASONS):
        raise _PortfolioHeld("journal_unavailable")
    from engine import fabric_inference_client as transport
    authority = owned["authority"]
    if (type(authority) is not dict or set(authority) != {
            "service", "workload", "inspection_digest", "route_scope", "route_scope_digest"}
            or authority["service"] != _PORTFOLIO_SERVICE
            or authority["workload"] != _PORTFOLIO_WORKLOAD
            or not _portfolio_digest(authority["inspection_digest"])):
        raise _PortfolioHeld("journal_unavailable")
    _, scope_digest = transport.validate_auto_route_scope(authority["route_scope"])
    if scope_digest != authority["route_scope_digest"]:
        raise _PortfolioHeld("journal_unavailable")
    original, request = _portfolio_request(base, owned["operation_id"])
    if owned["request"] != request:
        raise _PortfolioHeld("journal_unavailable")
    commitment = {key: owned[key] for key in ("schema", "operation_id", "cycle_id",
        "input_digest", "prompt_version", "authority", "request")}
    if owned["original_digest"] != _portfolio_hash(commitment):
        raise _PortfolioHeld("journal_unavailable")
    text = owned["approved_text"]
    if (text is not None and _portfolio_text(text) != text
            or owned["text_digest"] != (_portfolio_hash(text) if text is not None else None)):
        raise _PortfolioHeld("journal_unavailable")
    receipt = owned["receipt"]
    if owned["phase"] == "pending":
        if receipt is not None or text is not None or owned["reason"] != "pending":
            raise _PortfolioHeld("journal_unavailable")
        return row
    fields = {"disposition", "effect_unknown", "pool", "selected_model", "serving_model",
              "selection_digest", "recipe_digest", "protocol", "routed_request_digest",
              "input_tokens", "output_tokens", "usage", "close"}
    if (type(receipt) is not dict or set(receipt) != fields
            or receipt["disposition"] not in ("terminal", "effect_unknown", "unobserved")
            or type(receipt["effect_unknown"]) is not bool
            or receipt["disposition"] == "effect_unknown" and receipt["effect_unknown"] is not True):
        raise _PortfolioHeld("journal_unavailable")
    for key in ("input_tokens", "output_tokens"):
        value = receipt[key]
        if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
            raise _PortfolioHeld("journal_unavailable")
    usage = receipt["usage"]
    if usage is not None:
        if (type(usage) is not dict or set(usage) != {"usage_state", "input_tokens", "output_tokens",
                "completed_input_tokens", "completed_output_tokens"}
                or usage["usage_state"] not in ("known", "unknown")):
            raise _PortfolioHeld("journal_unavailable")
        for key in ("input_tokens", "output_tokens", "completed_input_tokens", "completed_output_tokens"):
            value = usage[key]
            if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                raise _PortfolioHeld("journal_unavailable")
        if usage["usage_state"] == "known" and any(usage[k] is None for k in ("input_tokens", "output_tokens")):
            raise _PortfolioHeld("journal_unavailable")
    if receipt["serving_model"] is not None and not _portfolio_label(receipt["serving_model"]):
        raise _PortfolioHeld("journal_unavailable")
    if receipt["pool"] is None:
        if (any(receipt[k] is not None for k in ("selected_model", "selection_digest",
                "recipe_digest", "protocol", "routed_request_digest")) or text is not None
                or receipt["disposition"] != "unobserved"):
            raise _PortfolioHeld("journal_unavailable")
    else:
        if (receipt["pool"] not in authority["route_scope"]["pools"]
                or not _portfolio_label(receipt["selected_model"])
                or not _portfolio_digest(receipt["selection_digest"])
                or receipt["protocol"] not in ("chat", "responses", "harness")
                or receipt["routed_request_digest"] != transport._auto_request_digest(
                    dict(original, model=receipt["selected_model"]))):
            raise _PortfolioHeld("journal_unavailable")
        if ((receipt["pool"] == "go" and (receipt["recipe_digest"] is not None
                                         or receipt["protocol"] != "chat"))
                or receipt["pool"] == "bailian" and receipt["protocol"] != "responses"
                or receipt["pool"] not in ("go", "bailian") and receipt["protocol"] != "harness"
                or receipt["pool"] != "go" and not _portfolio_digest(receipt["recipe_digest"])):
            raise _PortfolioHeld("journal_unavailable")
    if text is not None and (receipt["disposition"] != "terminal" or receipt["effect_unknown"]
                              or receipt["serving_model"] != receipt["selected_model"]):
        raise _PortfolioHeld("journal_unavailable")
    close = _portfolio_close(receipt["close"])
    if owned["phase"] == "observed" and close is not None:
        raise _PortfolioHeld("journal_unavailable")
    if owned["phase"] == "terminal":
        closed = {"disposition": "closed", "closed": True, "effect_unknown": False, "attempted": True}
        not_bound = {"disposition": "not_bound", "closed": False, "effect_unknown": False, "attempted": False}
        no_binding = (close == not_bound and receipt["disposition"] == "unobserved"
                      and receipt["usage"] is None and text is None
                      and all(receipt[k] is None for k in (
                          "pool", "selected_model", "serving_model", "input_tokens", "output_tokens")))
        if (receipt["effect_unknown"] or not (close == closed or no_binding)
                or owned["reason"] not in ("accepted", "prose_rejected", "response_unusable", "binding_unavailable")):
            raise _PortfolioHeld("journal_unavailable")
        if (text is not None) != (owned["reason"] == "accepted"):
            raise _PortfolioHeld("journal_unavailable")
    return row


def _portfolio_review_public(row):
    if _PORTFOLIO_REVIEW not in row:
        public = dict(row)
        if "llm_assessment" in public and _portfolio_text(public["llm_assessment"]) != public["llm_assessment"]:
            public.pop("llm_assessment", None)
        return public
    _portfolio_validate_review(row)
    public, owned = _portfolio_base(row), row[_PORTFOLIO_REVIEW]
    receipt = owned["receipt"] or {}
    state = ("complete" if owned["phase"] == "terminal" and owned["approved_text"] is not None
             else "rejected" if owned["phase"] == "terminal" else "held")
    public["llm_review"] = {"state": state, "reason": owned["reason"],
        "model": receipt.get("serving_model"), "provider": receipt.get("pool"),
        "input_tokens": receipt.get("input_tokens"), "output_tokens": receipt.get("output_tokens")}
    if state == "complete":
        public["llm_assessment"] = owned["approved_text"]
    return public


def _portfolio_cycle_validate(row):
    if _PORTFOLIO_ANCHOR in row:
        owned = row[_PORTFOLIO_ANCHOR]
        if (set(row) != {_PORTFOLIO_ANCHOR} or type(owned) is not dict
                or set(owned) != {"schema", "cycle_highwater", "review_highwater", "open_review"}
                or owned["schema"] != "mastermind.portfolio_review_anchor.v1"
                or any(type(owned[k]) is not int or owned[k] < 0 for k in ("cycle_highwater", "review_highwater"))
                or owned["open_review"] is not None and not _portfolio_ref_valid(owned["open_review"])):
            raise _PortfolioHeld("journal_unavailable")
        return owned
    if type(row.get("loop_n")) is not int or row["loop_n"] < 1:
        raise _PortfolioHeld("journal_unavailable")
    owned = row.get(_PORTFOLIO_CYCLE)
    if owned is None:
        return None
    fields = {"schema", "cycle_id", "phase", "review_highwater", "open_review", "review",
              "review_operation_id", "review_started", "llm_requested", "fabric_selected", "snapshot_digest"}
    if (type(owned) is not dict or set(owned) != fields
            or owned["schema"] != "mastermind.portfolio_cycle.v1" or not _portfolio_id(owned["cycle_id"])
            or owned["phase"] not in ("claimed", "frozen", "complete")
            or type(owned["review_highwater"]) is not int or owned["review_highwater"] < 0
            or any(type(owned[k]) is not bool for k in ("review_started", "llm_requested", "fabric_selected"))
            or owned["open_review"] is not None and not _portfolio_ref_valid(owned["open_review"])
            or owned["review_operation_id"] is not None and not _portfolio_id(owned["review_operation_id"])):
        raise _PortfolioHeld("journal_unavailable")
    base = {key: value for key, value in row.items() if key != _PORTFOLIO_CYCLE}
    required = {"ts", "asof", "trigger", "loop_n", "steps", "nudges_open", "summary", "ok"}
    if (not required <= set(base) or set(base) - required - {"run_id", "review"}
            or type(base["steps"]) is not dict or type(base["ok"]) is not bool
            or type(base["nudges_open"]) is not int or base["nudges_open"] < 0
            or not _portfolio_id(base["trigger"])
            or type(base["ts"]) is not str or _parse_ts(base["ts"]) is None
            or type(base["summary"]) is not str or not _portfolio_public_input(base)):
        raise _PortfolioHeld("journal_unavailable")
    review = owned["review"]
    if review is not None:
        _portfolio_base(review)
        if set(review) != _REVIEW_FIELDS or review["loop_n"] != row["loop_n"]:
            raise _PortfolioHeld("journal_unavailable")
    if owned["phase"] == "claimed":
        if review is not None or owned["snapshot_digest"] is not None or owned["review_started"]:
            raise _PortfolioHeld("journal_unavailable")
    elif owned["snapshot_digest"] != _portfolio_hash({"row": base, "review": review}):
        raise _PortfolioHeld("journal_unavailable")
    return owned


def _portfolio_state():
    loop_raw, _, loops = _portfolio_read(_LOOP_LOG)
    review_raw, _, reviews_ = _portfolio_read(_REVIEWS)
    cycle_highwater = review_highwater = 0
    open_ref, unfinished = None, None
    review_map, loop_numbers = {}, set()
    for index, row in loops:
        owned = _portfolio_cycle_validate(row)
        if _PORTFOLIO_ANCHOR in row:
            cycle_highwater = max(cycle_highwater, owned["cycle_highwater"])
        else:
            if row["loop_n"] in loop_numbers:
                raise _PortfolioHeld("journal_unavailable")
            loop_numbers.add(row["loop_n"])
            cycle_highwater = max(cycle_highwater, row["loop_n"])
            if owned is not None and owned["phase"] != "complete":
                if unfinished is not None:
                    raise _PortfolioHeld("journal_unavailable")
                unfinished = (index, row)
        if owned is not None:
            review_highwater = max(review_highwater, owned["review_highwater"])
            open_ref = owned["open_review"]  # Every later owned tail carries the current anchor.
    for index, row in reviews_:
        _portfolio_validate_review(row)
        number = row["loop_n"]
        if number in review_map:
            raise _PortfolioHeld("journal_unavailable")
        review_map[number] = (index, row)
        review_highwater = max(review_highwater, number)
    for _, cycle in loops:
        owned = cycle.get(_PORTFOLIO_CYCLE)
        if owned is not None and owned["review"] is not None:
            saved = review_map.get(cycle["loop_n"])
            if saved is not None:
                _portfolio_cycle_review(cycle, saved[1])
    if open_ref is not None:
        original = review_map.get(open_ref["loop_n"])
        if (original is None or _PORTFOLIO_REVIEW not in original[1]
                or _portfolio_ref(original[1]) != open_ref):
            raise _PortfolioHeld("original_incomplete")
    pending = [(index, row) for index, row in reviews_ if _PORTFOLIO_REVIEW in row
               and row[_PORTFOLIO_REVIEW]["phase"] != "terminal"]
    if len(pending) > 1:
        raise _PortfolioHeld("journal_unavailable")
    return {"loop_raw": loop_raw, "review_raw": review_raw, "loops": loops,
            "reviews": reviews_, "review_map": review_map, "cycle_highwater": cycle_highwater,
            "review_highwater": review_highwater, "open_ref": open_ref,
            "unfinished": unfinished, "pending": pending}


def _portfolio_anchor(state, reference):
    import copy
    if reference is not None and not _portfolio_ref_valid(reference):
        raise _PortfolioHeld("journal_unavailable")
    high = max(state["review_highwater"], reference["loop_n"] if reference else 0)
    if state["loops"] and any(key in state["loops"][-1][1] for key in (_PORTFOLIO_CYCLE, _PORTFOLIO_ANCHOR)):
        index, row = state["loops"][-1]
        row = copy.deepcopy(row)
        owned = row.get(_PORTFOLIO_CYCLE, row.get(_PORTFOLIO_ANCHOR))
        owned["review_highwater"], owned["open_review"] = high, reference
        _portfolio_cycle_validate(row)
        _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=row, index=index)
    else:
        row = {_PORTFOLIO_ANCHOR: {"schema": "mastermind.portfolio_review_anchor.v1",
            "cycle_highwater": state["cycle_highwater"], "review_highwater": high, "open_review": reference}}
        _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=row)


def _portfolio_reconcile(state):
    """Clear a retained open anchor only from its original terminal review.

    Called under the existing root lock, never by a public read surface.
    """
    reference = state["open_ref"]
    if reference is not None:
        found = state["review_map"].get(reference["loop_n"])
        if (found is not None and _PORTFOLIO_REVIEW in found[1]
                and _portfolio_ref(found[1]) == reference
                and found[1][_PORTFOLIO_REVIEW]["phase"] == "terminal"):
            _portfolio_anchor(state, None)
            return _portfolio_state()
    return state


def _portfolio_public_rows(path, limit=None):
    _, _, rows = _portfolio_read(path)
    public = []
    for _, row in rows:
        if path == _REVIEWS:
            _portfolio_validate_review(row)
            public.append(_portfolio_review_public(row))
        else:
            owned = _portfolio_cycle_validate(row)
            if _PORTFOLIO_ANCHOR in row or owned is not None and owned["phase"] != "complete":
                continue
            public.append({key: value for key, value in row.items() if key != _PORTFOLIO_CYCLE})
    return public[-limit:] if limit else public


def _portfolio_legacy_append(path, row):
    try:
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            if _portfolio_selected() or state["unfinished"] is not None or state["pending"] or state["open_ref"]:
                return False
            if any(_PORTFOLIO_REVIEW in value for _, value in state["reviews"]):
                return False
            raw = state["loop_raw"] if path == _LOOP_LOG else state["review_raw"]
            _portfolio_store(path, expected=raw, row=row)
        return True
    except Exception:
        return False


def _portfolio_held_review(base, reason="journal_unavailable"):
    return {**base, "llm_review": {"state": "held", "reason": reason,
        "model": None, "provider": None, "input_tokens": None, "output_tokens": None}}


def _portfolio_observation(provider, shared, transport, inspection, original, request, operation_id):
    receipt = {"disposition": "unobserved", "effect_unknown": False,
        "pool": None, "selected_model": None, "serving_model": None,
        "selection_digest": None, "recipe_digest": None, "protocol": None, "routed_request_digest": None,
        "input_tokens": None, "output_tokens": None,
        "usage": shared.fabric_usage(provider) if provider is not None else None, "close": None}
    if provider is None:
        return receipt
    observed = provider.get("_fabric_last_observation")
    if isinstance(observed, dict):
        if _portfolio_label(observed.get("serving_model")):
            receipt["serving_model"] = observed["serving_model"]
        for key in ("input_tokens", "output_tokens"):
            value = observed.get(key)
            if type(value) is int and 0 <= value <= 10**12:
                receipt[key] = value
    receipt["effect_unknown"] = bool(provider.get("_fabric_pending")
        or getattr(provider.get("_fabric_failure"), "effect_unknown", False))
    observation = shared._fabric_routed_observation(
        provider, shared.fabric_observation(provider), request["request_id"])
    if observation is not None:
        document = observation.document
        routed = transport._auto_request_digest(dict(original, model=document["routing"]["selected_model"]))
        document = transport.validate_auto_observation(document, inspection,
            operation_id=operation_id, request_id=request["request_id"],
            request_digest=request["digest"], routed_request_digest=routed,
            max_tokens=_PORTFOLIO_MAX_TOKENS)
        route = document["routing"]
        if not all(_portfolio_label(v) for v in (route["selected_model"], document["serving_model"]) if v is not None):
            receipt["effect_unknown"] = True
            return receipt
        receipt.update(disposition=document["disposition"],
            effect_unknown=receipt["effect_unknown"] or document["effect_unknown"],
            pool=route["pool"], selected_model=route["selected_model"], serving_model=document["serving_model"],
            selection_digest=route["selection_digest"], recipe_digest=route["recipe_digest"],
            protocol=route["protocol"], routed_request_digest=routed,
            input_tokens=document["usage"]["input_tokens"], output_tokens=document["usage"]["output_tokens"])
    return receipt


def _portfolio_update_review(expected, updated):
    _portfolio_validate_review(updated)
    with _portfolio_lock():
        state = _portfolio_reconcile(_portfolio_state())
        found = state["review_map"].get(expected["loop_n"])
        if found is None or found[1] != expected or state["open_ref"] != _portfolio_ref(expected):
            raise _PortfolioHeld("original_incomplete")
        _portfolio_store(_REVIEWS, expected=state["review_raw"], row=updated, index=found[0])


def _portfolio_infer(base, *, cycle_id=None, operation_id=None):
    import copy
    import secrets
    from brain import fabric_inference
    provider = operation = None
    try:
        modes, shared, root = fabric_inference._owner()
        from engine import fabric_inference_client as transport
        cfg = {"provider_order": ["fabric"], "workload_profile": _PORTFOLIO_WORKLOAD,
               "max_tokens": _PORTFOLIO_MAX_TOKENS, "usage_lane": _PORTFOLIO_LANE}
        mode_id = shared.application_mode_id()
        factory = modes.make_application_fabric_factory(mode_id=mode_id, lane=_PORTFOLIO_LANE,
            workload_cfg=cfg, root=root, service_mode_id=_PORTFOLIO_SERVICE)
        if type(factory) is not modes.ApplicationFabricFactory:
            raise _PortfolioHeld("binding_unavailable")
        inspection = transport.validate_auto_inspection(factory.inspect(cfg))
        operation_id = operation_id or "portfolio-review:" + secrets.token_hex(16)
        original, request = _portfolio_request(base, operation_id)
        owned = {"schema": "mastermind.portfolio_review.fabric.v1", "operation_id": operation_id,
            "cycle_id": cycle_id, "input_digest": _portfolio_hash(base), "prompt_version": _PORTFOLIO_PROMPT_VERSION,
            "authority": {"service": _PORTFOLIO_SERVICE, "workload": _PORTFOLIO_WORKLOAD,
                "inspection_digest": _portfolio_hash(inspection),
                "route_scope": inspection["route_scope"], "route_scope_digest": inspection["route_scope_digest"]},
            "request": request, "phase": "pending", "approved_text": None, "text_digest": None,
            "receipt": None, "reason": "pending", "revision": 0}
        owned["original_digest"] = _portfolio_hash({key: owned[key] for key in (
            "schema", "operation_id", "cycle_id", "input_digest", "prompt_version", "authority", "request")})
        pending = {**base, _PORTFOLIO_REVIEW: owned}
        _portfolio_validate_review(pending)
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            prior = state["review_map"].get(base["loop_n"])
            if prior is not None:
                return _portfolio_review_public(prior[1])
            if state["pending"] or state["open_ref"] or base["loop_n"] <= state["review_highwater"]:
                return _portfolio_held_review(base, "original_incomplete")
            current = state["unfinished"]
            if current is not None:
                cycle = current[1][_PORTFOLIO_CYCLE]
                if (cycle_id != cycle["cycle_id"] or cycle["phase"] != "frozen"
                        or cycle["review_started"]
                        or cycle["review"] != base or cycle["review_operation_id"] != operation_id):
                    return _portfolio_held_review(base, "original_incomplete")
            elif cycle_id is not None:
                return _portfolio_held_review(base, "original_incomplete")
            if not _portfolio_selected() or not llm_review_flag_on() or not settings().get("llm_review"):
                return _portfolio_held_review(base, "selection_changed")
            _portfolio_store(_REVIEWS, expected=state["review_raw"], row=pending)
            state = _portfolio_reconcile(_portfolio_state())
            _portfolio_anchor(state, _portfolio_ref(pending))
            if cycle_id is not None:
                state = _portfolio_reconcile(_portfolio_state())
                found = state["unfinished"]
                if found is None or found[1][_PORTFOLIO_CYCLE]["cycle_id"] != cycle_id:
                    raise _PortfolioHeld("original_incomplete")
                index, cycle = found
                cycle = copy.deepcopy(cycle)
                cycle[_PORTFOLIO_CYCLE]["review_started"] = True
                _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=cycle, index=index)
        text = None
        reason = "response_unusable"
        observed_saved = False
        try:
            provider = shared.build_fabric_provider(factory.with_inspection(inspection),
                request_id=operation_id, workload_cfg=cfg)
            provider["usage_lane"] = _PORTFOLIO_LANE
            operation = shared.begin_operation([provider], operation_id=operation_id, context=_PORTFOLIO_LANE)
            def call(client, model):
                response = client.messages.create(model=model, max_tokens=_PORTFOLIO_MAX_TOKENS,
                    messages=[{"role": "user", "content": _portfolio_prompt(base)}])
                if (getattr(response, "stop_reason", None) != "end_turn"
                        or not response.content
                        or any(getattr(block, "type", None) != "text" for block in response.content)):
                    raise ValueError("portfolio_prose_response_unusable")
                return "".join(block.text for block in response.content), None, response
            candidate, _, _ = shared.make_call(operation.providers, call, context=_PORTFOLIO_LANE)
            text = _portfolio_text(candidate)
            reason = "accepted" if text is not None else "prose_rejected"
        except Exception:
            reason = "binding_unavailable" if provider is None else "response_unusable"
        finally:
            # Observation is durably retained before close/public acceptance.
            # Cancellation still propagates; its pending record stays a barrier.
            import sys
            cancelling = sys.exc_info()[0] is not None
            try:
                if not cancelling:
                    try:
                        receipt = _portfolio_observation(provider, shared, transport, inspection,
                            original, request, operation_id)
                        if (receipt["disposition"] != "terminal" or receipt["effect_unknown"]
                                or receipt["serving_model"] != receipt["selected_model"]):
                            text = None
                            if reason == "accepted":
                                reason = "response_unusable"
                        observed = copy.deepcopy(pending)
                        observed[_PORTFOLIO_REVIEW].update(phase="observed", revision=1,
                            approved_text=text, text_digest=_portfolio_hash(text) if text is not None else None,
                            receipt=receipt, reason=reason)
                        _portfolio_update_review(pending, observed)
                        observed_saved = True
                    except Exception:
                        observed_saved = False
            finally:
                try:
                    if operation is not None:
                        operation.close()
                    elif provider is not None:
                        shared.close_fabric_provider(provider)
                except Exception:
                    # The original close may have executed. Do not repeat it.
                    pass
        if not observed_saved:
            return _portfolio_held_review(base)
        close = (provider.get("_fabric_close") if provider is not None else
                 {"disposition": "not_bound", "closed": False, "effect_unknown": False, "attempted": False})
        try:
            close = _portfolio_close(close)
        except Exception:
            close = None
        if close is None:
            close = {"disposition": "effect_unknown", "closed": False, "effect_unknown": True, "attempted": True}
        settled = copy.deepcopy(observed)
        saved = settled[_PORTFOLIO_REVIEW]
        saved["receipt"]["close"] = close
        uncertain = (saved["receipt"]["effect_unknown"] or close["effect_unknown"]
                     or provider is not None and not close["closed"])
        saved.update(phase="held" if uncertain else "terminal", revision=2,
                     reason="close_unsettled" if uncertain else reason)
        _portfolio_update_review(observed, settled)
        if not uncertain:
            with _portfolio_lock():
                state = _portfolio_reconcile(_portfolio_state())
                if state["open_ref"] == _portfolio_ref(settled):
                    _portfolio_anchor(state, None)
        return _portfolio_review_public(settled)
    except Exception:
        return _portfolio_held_review(base, "binding_unavailable" if provider is None else "journal_unavailable")


def _build_review(loop_n: int, cfg: dict, *, _snapshot=None, _cycle_id=None, _operation_id=None,
                  _fabric_selected=None, _llm_requested=None, _native_claim=None) -> dict:
    """Resolve an original before mutable inputs, selection, cadence or opt-ins."""
    try:
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            prior = state["review_map"].get(loop_n)
            if prior is not None:
                return _portfolio_review_public(prior[1])
            blocked = bool(state["pending"] or state["open_ref"]
                           or loop_n <= state["review_highwater"]
                           or state["unfinished"] is not None
                              and state["unfinished"][1][_PORTFOLIO_CYCLE]["cycle_id"] != _cycle_id)
        base = _portfolio_base(_snapshot if _snapshot is not None else _deterministic_review(loop_n, cfg))
        if blocked:
            return _portfolio_held_review(base, "original_incomplete")
        requested = (llm_review_flag_on() and cfg.get("llm_review")
                     if _llm_requested is None else _llm_requested)
        if not requested:
            return base
        if not llm_review_flag_on() or not cfg.get("llm_review"):
            return _portfolio_held_review(base, "disabled") if _llm_requested else base
        if _portfolio_selected() or _fabric_selected is True:
            if not _portfolio_selected() or not llm_review_flag_on() or not cfg.get("llm_review"):
                return _portfolio_held_review(base, "selection_changed")
            return _portfolio_infer(base, cycle_id=_cycle_id, operation_id=_operation_id)
        from brain import cli_bridge
        # Recheck immediately before the incumbent bridge, which also has its
        # own selected-path pre-start veto. A late selector cannot become a
        # native fallback for an original selected review.
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            if _portfolio_selected() or state["pending"] or state["open_ref"] or loop_n in state["review_map"]:
                return _portfolio_held_review(base, "selection_changed")
            if _cycle_id is not None:
                import copy
                current = state["unfinished"]
                if (current is None or current[1][_PORTFOLIO_CYCLE]["cycle_id"] != _cycle_id
                        or current[1][_PORTFOLIO_CYCLE]["review_started"]):
                    return _portfolio_held_review(base, "original_incomplete")
                index, cycle = current
                cycle = copy.deepcopy(cycle)
                cycle[_PORTFOLIO_CYCLE]["review_started"] = True
                _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=cycle, index=index)
                if _native_claim is not None:
                    _native_claim["owned"] = True
        result = cli_bridge.reason_sync(_portfolio_prompt(base), role="analyst", max_turns=1,
                                        allowed_tools=[], log_run=False)
        completed = isinstance(result, dict) and result.get("ok") is True
        if _native_claim is not None:
            _native_claim["completed"] = completed
        if not completed:
            return _portfolio_held_review(base, "original_incomplete")
        if _portfolio_selected():
            return _portfolio_held_review(base, "selection_changed")
        text = _portfolio_text(result.get("text"))
        return {**base, **({"llm_assessment": text} if text is not None else {})}
    except Exception:
        try:
            base = _portfolio_base(_snapshot if _snapshot is not None else _deterministic_review(loop_n, cfg))
        except Exception:
            base = {"ts": _now_iso(), "loop_n": loop_n, "window_loops": max(2, int(cfg.get("review_every_n_loops", 5))),
                    "completed": {}, "assessment": [], "agenda_top": []}
        return _portfolio_held_review(base)


def _portfolio_cycle_review(cycle, review):
    owned = cycle[_PORTFOLIO_CYCLE]
    if _portfolio_base(review) != owned["review"]:
        raise _PortfolioHeld("original_incomplete")
    original = review.get(_PORTFOLIO_REVIEW)
    if original is not None and (original["cycle_id"] != owned["cycle_id"]
                                 or original["operation_id"] != owned["review_operation_id"]):
        raise _PortfolioHeld("original_incomplete")


def _portfolio_finish_cycle(cycle):
    import copy
    owned = cycle[_PORTFOLIO_CYCLE]
    base = {key: value for key, value in cycle.items() if key != _PORTFOLIO_CYCLE}
    review = owned["review"]
    if review is not None:
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            found = state["review_map"].get(cycle["loop_n"])
            if found is not None:
                _portfolio_cycle_review(cycle, found[1])
                if (_PORTFOLIO_REVIEW in found[1]
                        and found[1][_PORTFOLIO_REVIEW]["phase"] != "terminal"):
                    return {**base, "review_state": "held"}
            else:
                current = state["unfinished"]
                if (current is None or current[1][_PORTFOLIO_CYCLE]["cycle_id"] != owned["cycle_id"]
                        or current[1][_PORTFOLIO_CYCLE]["review_started"]):
                    return {**base, "review_state": "held"}
        if found is None:
            native_claim = {}
            result = _build_review(cycle["loop_n"], {"review_every_n_loops": review["window_loops"],
                "llm_review": settings().get("llm_review")}, _snapshot=review,
                _cycle_id=owned["cycle_id"], _operation_id=owned["review_operation_id"],
                _fabric_selected=owned["fabric_selected"], _llm_requested=owned["llm_requested"],
                _native_claim=native_claim)
            with _portfolio_lock():
                state = _portfolio_reconcile(_portfolio_state())
                found = state["review_map"].get(cycle["loop_n"])
                if found is None:
                    current = state["unfinished"]
                    if (current is None or current[1][_PORTFOLIO_CYCLE]["cycle_id"] != owned["cycle_id"]
                            or current[1][_PORTFOLIO_CYCLE]["review_started"]
                               and (native_claim.get("owned") is not True
                                    or native_claim.get("completed") is not True)):
                        return {**base, "review_state": "held"}
                    # No Fabric intent was committed. Preserve deterministic
                    # output plus the bounded reason, without inventing a receipt.
                    _portfolio_store(_REVIEWS, expected=state["review_raw"], row=result)
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            found = state["review_map"].get(cycle["loop_n"])
            if found is None:
                raise _PortfolioHeld("original_incomplete")
            _portfolio_cycle_review(cycle, found[1])
            if (_PORTFOLIO_REVIEW in found[1] and found[1][_PORTFOLIO_REVIEW]["phase"] != "terminal"):
                return {**base, "review_state": "held"}
    with _portfolio_lock():
        state = _portfolio_reconcile(_portfolio_state())
        current = state["unfinished"]
        if current is None:
            matching = next((r for _, r in state["loops"]
                if _PORTFOLIO_CYCLE in r and r[_PORTFOLIO_CYCLE]["cycle_id"] == owned["cycle_id"]), None)
            if matching is None or matching[_PORTFOLIO_CYCLE]["phase"] != "complete":
                raise _PortfolioHeld("original_incomplete")
            return {key: value for key, value in matching.items() if key != _PORTFOLIO_CYCLE}
        index, current = current
        if current[_PORTFOLIO_CYCLE]["cycle_id"] != owned["cycle_id"]:
            raise _PortfolioHeld("original_incomplete")
        current = copy.deepcopy(current)
        current[_PORTFOLIO_CYCLE]["phase"] = "complete"
        current[_PORTFOLIO_CYCLE]["review_highwater"] = state["review_highwater"]
        _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=current, index=index)
    return base


def run_cycle(asof: date | str | None = None, trigger: str = "manual") -> dict:
    """Reserve the existing cycle before business effects; recover without replay."""
    import copy
    import secrets
    asof_s = (asof.isoformat() if isinstance(asof, date) else str(asof)) if asof else date.today().isoformat()
    try:
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            current = state["unfinished"]
            if current is not None:
                cycle = current[1]
                if cycle[_PORTFOLIO_CYCLE]["phase"] == "claimed":
                    return {"ok": False, "held": "original_incomplete", "asof": cycle["asof"],
                            "loop_n": cycle["loop_n"]}
                recover = True
            else:
                if state["pending"] or state["open_ref"]:
                    return {"ok": False, "held": "original_incomplete", "asof": asof_s}
                cfg = settings()
                if not (loop_flag_on() and cfg["loop_enabled"]):
                    return {"ok": False, "skipped": "loop disabled", "asof": asof_s}
                if not _portfolio_id(trigger) or date.fromisoformat(asof_s).isoformat() != asof_s:
                    raise _PortfolioHeld("journal_unavailable")
                number = max(state["cycle_highwater"], state["review_highwater"]) + 1
                cycle = {"ts": _now_iso(), "asof": asof_s, "trigger": trigger, "loop_n": number,
                    "steps": {}, "nudges_open": 0, "summary": "Original cycle reserved; business result pending.",
                    "ok": False, _PORTFOLIO_CYCLE: {"schema": "mastermind.portfolio_cycle.v1",
                        "cycle_id": "portfolio-cycle:" + secrets.token_hex(16), "phase": "claimed",
                        "review_highwater": state["review_highwater"], "open_review": None, "review": None,
                        "review_operation_id": None, "review_started": False,
                        "llm_requested": bool(llm_review_flag_on() and cfg.get("llm_review")),
                        "fabric_selected": _portfolio_selected(), "snapshot_digest": None}}
                _portfolio_cycle_validate(cycle)
                _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=cycle)
                recover = False
        if recover:
            return _portfolio_finish_cycle(cycle)
        # The durable claim prevents a second caller entering these existing
        # journal/reflection/directive/learning steps, without a lock over I/O.
        row, review = _cycle_snapshot(asof_s, trigger, cfg, number, loop_log(limit=None))
        frozen = {**row, _PORTFOLIO_CYCLE: copy.deepcopy(cycle[_PORTFOLIO_CYCLE])}
        frozen[_PORTFOLIO_CYCLE].update(phase="frozen", review=review,
            review_operation_id="portfolio-review:" + secrets.token_hex(16) if review is not None else None,
            snapshot_digest=_portfolio_hash({"row": row, "review": review}))
        _portfolio_cycle_validate(frozen)
        with _portfolio_lock():
            state = _portfolio_reconcile(_portfolio_state())
            current = state["unfinished"]
            if current is None or current[1] != cycle:
                raise _PortfolioHeld("original_incomplete")
            _portfolio_store(_LOOP_LOG, expected=state["loop_raw"], row=frozen, index=current[0])
        return _portfolio_finish_cycle(frozen)
    except Exception:
        return {"ok": False, "held": "journal_unavailable", "asof": asof_s}


def _portfolio_public_status():
    try:
        state = _portfolio_state()
        return {"state": "held" if state["unfinished"] or state["pending"] or state["open_ref"] else "ready",
                "allocated_loop_n": state["cycle_highwater"], "review_highwater": state["review_highwater"]}
    except Exception:
        return {"state": "held", "reason": "journal_unavailable"}


# ── read surfaces for the API/admin ───────────────────────────────────────────────────────────

def loop_log(limit: int = 50) -> list[dict]:
    return _read_jsonl(_LOOP_LOG, limit=limit)


def reviews(limit: int = 12) -> list[dict]:
    return _read_jsonl(_REVIEWS, limit=limit)


def improvements() -> dict:
    """The merged 'what has actually improved' feed for the admin panel."""
    out: dict[str, Any] = {"pins": [], "self_tune": _self_tune_state(),
                           "agenda_top": _agenda_top(10), "lessons_by_taxonomy": {}}
    try:
        from brain import journal
        for seat in journal.SEATS:
            for pin in journal.load_pins(seat):
                out["pins"].append({"seat": seat, "taxonomy": pin.get("taxonomy"),
                                    "rule": str(pin.get("rule", ""))[:200],
                                    "status": pin.get("status"),
                                    "confidence": pin.get("confidence"),
                                    "pinned_on": pin.get("pinned_on"),
                                    "unpin_reason": pin.get("unpin_reason")})
            for les in journal.load_lessons(seat):
                tax = les.get("why_wrong") or ("success" if les.get("kind") == "success" else "other")
                out["lessons_by_taxonomy"][tax] = out["lessons_by_taxonomy"].get(tax, 0) + 1
    except Exception:  # noqa: BLE001
        pass
    return out


def status() -> dict:
    """The one-call admin snapshot."""
    try:
        from brain import nw_reflection
        reflection = nw_reflection.latest()
    except Exception:  # noqa: BLE001
        reflection = {}
    try:
        from brain import portfolio_learning
        learning = portfolio_learning.status()
    except Exception:  # noqa: BLE001
        learning = {}
    log_rows = loop_log(limit=5)
    return {
        "schema": "mastermind_ai_status.v1",
        "generated_at": _now_iso(),
        "flags": {"loop": loop_flag_on(), "llm_review": llm_review_flag_on()},
        "settings": settings(),
        "loop_n": (log_rows[-1].get("loop_n") if log_rows else 0),
        "last_loops": log_rows,
        "last_review": (reviews(limit=1) or [None])[-1],
        "review_runtime": _portfolio_public_status(),
        "reflection": {
            "asof": reflection.get("asof"),
            "nudges": reflection.get("nudges") or [],
            "contract_drift_n": len(reflection.get("contract_drift") or []),
            "coverage": reflection.get("coverage") or {},
            "context_quality": reflection.get("context_quality") or {},
            "attribution": reflection.get("attribution") or {},
        },
        "journal": _journal_counts(),
        "directives": directives(limit=20),
        "dialogue": dialogue_health(),
        "portfolio_learning": learning,
        "product_scope": {
            "name": "Mastermind Portfolio",
            "public_chatbot": "Mastermind AI (separate product and authority)",
        },
    }
