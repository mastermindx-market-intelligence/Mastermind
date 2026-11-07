"""In-process MCP server — the bot's data + action surface for Claude.

This is how the web app ARMS Claude and lets Claude COMMUNICATE BACK. The tools run
in THIS Python process (via the Agent SDK's in-process MCP), so Claude never touches
the filesystem directly — it calls typed tools we control.

READ tools  → give Claude the live dashboard + bot state to reason over.
ACTION tools → let Claude write conclusions back to the app's RESEARCH/PROPOSAL surface
               (research notes, proposed theses, emerging-theme flags, recommendations).

Accountability spine: action tools write to a REVIEW QUEUE (jsonl/markdown the web app
renders), never to the execution path. The engine still derives sizing + the falsifier;
nothing here auto-executes a trade. Paper-only.
"""
from __future__ import annotations

import json
import copy
import math
import re
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone
from pathlib import Path

import bot  # noqa: F401
from claude_agent_sdk import tool, create_sdk_mcp_server

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"
_RESEARCH = _ROOT / "data" / "research"
_PROPOSALS = _ROOT / "data" / "brain" / "proposals.jsonl"
_READ_ROOTS = [_V / "site", _V / "data", _ROOT / "data"]
# Portfolio BOOK state is not "published signal" data — block cross-book reads through this
# generic path reader. A Brain reads its OWN book via a dedicated tool (get_portfolio / the
# desk's get_my_book); reading ANOTHER book's positions / ledger / research via read_signal was
# the latent autonomous→flagship peek path (data/portfolio/* lives under the _ROOT/data root).
_DENY_ROOTS = [(_ROOT / "data" / "portfolio").resolve(), (_ROOT / "data" / "portfolios").resolve()]
_LEAK_AUDIT = _ROOT / "data" / "brain" / "read_signal_denied.jsonl"
_INFERENCE_PROVENANCE = ContextVar("bot_inference_provenance", default=None)


def _execution_provenance() -> dict:
    """Trusted invocation context; model arguments never supply these fields."""
    return dict(_INFERENCE_PROVENANCE.get() or {"source": "claude_cli"})


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _compact_json_value(
    value,
    *,
    list_limit: int,
    str_limit: int,
    depth: int = 0,
):
    """Recursively bound a tool payload while preserving valid JSON and top-level shape."""
    if depth >= 7:
        return "<nested context omitted>"
    if isinstance(value, dict):
        return {
            str(k): _compact_json_value(
                v,
                list_limit=list_limit,
                str_limit=str_limit,
                depth=depth + 1,
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _compact_json_value(
                v,
                list_limit=list_limit,
                str_limit=str_limit,
                depth=depth + 1,
            )
            for v in value[:list_limit]
        ]
    if isinstance(value, tuple):
        return _compact_json_value(
            list(value),
            list_limit=list_limit,
            str_limit=str_limit,
            depth=depth,
        )
    if isinstance(value, str) and len(value) > str_limit:
        return value[: max(0, str_limit - 1)] + "…"
    return value


def _json(obj) -> dict:
    """Return a valid JSON tool result under the 8k transport budget.

    The old implementation sliced serialized bytes, which emitted malformed JSON.  Progressive
    structural compaction keeps top-level keys and the highest-ranked list rows instead.
    """
    payload = json.dumps(obj, default=str, ensure_ascii=False)
    if len(payload) <= 8000:
        return _ok(payload)
    for list_limit, str_limit in ((20, 400), (10, 240), (5, 160), (3, 100), (1, 72)):
        compact = _compact_json_value(
            obj,
            list_limit=list_limit,
            str_limit=str_limit,
        )
        if isinstance(compact, dict):
            compact["_transport_truncated"] = True
        payload = json.dumps(compact, default=str, ensure_ascii=False)
        if len(payload) <= 8000:
            return _ok(payload)
    # Extremely wide objects still return valid JSON with their top-level scalar contract, plus
    # the small freshness blocks: a read must never reach the model without its clocks.
    fallback = {
        str(k): v
        for k, v in (obj.items() if isinstance(obj, dict) else [])
        if v is None or isinstance(v, (bool, int, float, str))
        or (k in _FRESHNESS_KEYS and isinstance(v, dict))
    }
    fallback["_transport_truncated"] = True
    fallback["_note"] = "Nested payload exceeded the MCP transport budget."
    return _ok(json.dumps(fallback, default=str, ensure_ascii=False))


def _mapping_field_checked(mapping, key):
    """Return one optional mapping field plus whether its persisted shape was invalid."""
    if mapping is None:
        return {}, False
    value = mapping.get(key)
    if value is None:
        return {}, False
    if not isinstance(value, dict):
        return {}, True
    return value, False

def _single_name_ticker(args):
    """Keep ticker lookups in one filename component without changing symbol normalization."""
    value = args.get("ticker")
    if not isinstance(value, str) or not value or any(char in value for char in ("/", "\\", "\x00")):
        return None
    return value.upper()

def _read_first_nonempty_mapping_checked(paths, *, allow_empty=False):
    """Read usable mappings without treating unavailable artifacts as absent.

    Empty mappings remain failed evidence unless the caller explicitly allows them.
    """
    had_failure = False
    for path in paths:
        try:
            value = json.loads(path.read_text())
        except FileNotFoundError:
            absent = False
            try:
                import stat

                candidate = path
                while True:
                    try:
                        info = candidate.lstat()
                    except FileNotFoundError:
                        if candidate.parent == candidate:
                            break
                        candidate = candidate.parent
                        continue
                    absent = candidate != path and stat.S_ISDIR(info.st_mode)
                    break
            except Exception:
                pass
            had_failure = had_failure or not absent
            continue
        except Exception:  # noqa: BLE001 - caller projects a closed source status
            had_failure = True
            continue
        if not isinstance(value, dict) or (not value and not allow_empty):
            had_failure = True
            continue
        return value, had_failure
    return None, had_failure



def _read_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


# --- vendored-file freshness (news estate D2, 2026-10-31) ---------------------------------------
# get_news / get_intelligence answer from a VENDORED Macro snapshot, not a live feed. Each answer
# names the file it came from and only the clocks that file itself carries: `asof` (the Macro
# build date), `source_asof` (when the underlying news fetch ran; differs from `asof` when the
# producer retained a previous build's feed), `retained_from_previous_build`, `generated_utc`.
# An absent clock is null — never inferred from the file's mtime or from today's date.
_FRESHNESS_BASIS = "vendored_macro_file"
_FRESHNESS_KEYS = ("freshness", "alt_freshness")


def _first_vendored(*rels: str):
    """(rel, payload) of the first vendored file with a non-empty payload — the same precedence
    as the `_read_json(site) or _read_json(data)` reads — else (None, {})."""
    for rel in rels:
        doc = _read_json(_V / rel)
        if doc:
            return rel, doc
    return None, {}


def _freshness(doc, rel) -> dict:
    doc = doc if isinstance(doc, dict) else {}

    def _clock(*keys):
        for k in keys:
            v = doc.get(k)
            if isinstance(v, str) and v:
                return v
        return None

    retained = doc.get("retained_from_previous_build")
    return {"asof": _clock("asof", "as_of"),
            "source_asof": _clock("source_asof"),
            "retained_from_previous_build": retained if isinstance(retained, bool) else None,
            "generated_utc": _clock("generated_utc"),
            "basis": _FRESHNESS_BASIS,
            "source_file": rel}


def _pick(d, keys):
    """Shallow projection — {k: d[k]} for the keys present (drops noise/bulk)."""
    d = d or {}
    return {k: d.get(k) for k in keys if k in d}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(p: Path, row: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({**row, "logged_at": _now()}, default=str) + "\n")


# Marker the streaming layer scans tool results for, to surface a research paper as a
# clickable button in the chat (followed by a JSON blob with the paper meta).
PAPER_MARKER = "__PAPER__"


def _today() -> str:
    d = _read_json(_V / "data" / "regime" / "latest.json") or {}
    return d.get("date") or datetime.now(timezone.utc).date().isoformat()


def _stock_price(t: str):
    d = _read_json(_V / "site" / "stockdata" / f"{t.upper()}.json") or {}
    return (d.get("tech") or {}).get("price")


# ---------------- READ tools ----------------
@tool("get_regime", "Current US macro regime read (quad, growth/inflation scores, liquidity).", {})
async def get_regime(args):
    d = _read_json(_V / "data" / "regime" / "latest.json") or {}
    keys = ["date", "quad", "quad_name", "growth_score", "inflation_score", "liquidity_overlay", "cycle_tag"]
    out = {k: d.get(k) for k in keys} | {"sector_rs_top": (d.get("sector_rs") or [])[:6]}
    # E1.1 — append the market_view brief + label_vs_planes line (ADDITIVE; absent view → keys absent).
    # This replaces the ad-hoc 7-key slice so the autonomous Brain reads the same perception layer as
    # the judgment seats — the incident's root cause was the Brain seeing ONLY the label.
    try:
        from brain.pm_conviction import _read_market_view, _market_view_enrichment
        mv = _read_market_view()
        enrichment = _market_view_enrichment(mv)
        if enrichment:
            compact_mv = dict(enrichment)
            compact_mv["plane_summaries"] = [
                {
                    "name": row.get("name"),
                    "direction": row.get("direction"),
                    "status": row.get("status"),
                    "asof": (row.get("freshness") or {}).get("asof"),
                    "stale": (row.get("freshness") or {}).get("stale"),
                    "age_sessions": (row.get("freshness") or {}).get("age_sessions"),
                }
                for row in (enrichment.get("plane_summaries") or [])
            ]
            out["market_view"] = compact_mv
    except Exception:  # noqa: BLE001 — additive; never break the tool
        pass
    try:
        from brain import decision_context as _dc

        dc = _dc.prompt_summary(
            expected_publication=(out.get("market_view") or {}).get("publication")
        )
        if dc:
            liquidity = dc.get("liquidity") or {}
            quality = liquidity.get("quality") or {}
            driver = dc.get("market_driver") or {}
            # Keep this tool's JSON safely below its transport cap. Rich fresh-lobe context remains
            # available to the strategist/PM; get_regime carries the precise regime core.
            out["decision_context"] = {
                "schema_version": dc.get("schema_version"),
                "market_asof": dc.get("market_asof"),
                "hard_label": dc.get("hard_label"),
                "probabilistic_state": dc.get("probabilistic_state"),
                "trajectory": dc.get("trajectory"),
                "axes": dc.get("axes"),
                "liquidity": {
                    "quantity_overlay": liquidity.get("quantity_overlay"),
                    "quality_label": quality.get("label"),
                    "quality_asof": quality.get("asof"),
                },
                "risk": dc.get("risk"),
                "market_driver": {
                    "label": driver.get("label"),
                    "direction": driver.get("direction"),
                    "confidence": driver.get("confidence"),
                    "strength": driver.get("strength"),
                    "evidence": driver.get("evidence"),
                    "invalidation": driver.get("invalidation"),
                },
                "governor": dc.get("governor"),
                "data_quality": dc.get("data_quality"),
                "neural_web_health": dc.get("neural_web_health"),
                "publication": dc.get("publication"),
                "serving_freshness": dc.get("serving_freshness"),
            }
    except Exception:  # noqa: BLE001
        pass
    return _json(out)


@tool("get_overnight_tape",
      "The LIVE overnight cross-asset tape — what's moving RIGHT NOW while the US cash market is shut, "
      "which the EOD macro dashboard CANNOT see. US index futures (ES/NQ/YM/RTY), international indices "
      "(Nikkei, Hang Seng, Shanghai, KOSPI, Euro Stoxx, DAX, FTSE), USD/JPY/DXY, the 10Y yield, VIX, oil, "
      "gold and BTC — each with its overnight % change — plus a distilled risk read (calm / elevated / "
      "stressed). Use this to position for the open the way a human trader watches the overnight tape; do "
      "NOT rely on the stale dashboard for the current risk.", {})
async def get_overnight_tape(args):
    try:
        from data_layer import overnight
        return _json(overnight.tape())
    except Exception as e:  # noqa: BLE001
        return _json({"error": repr(e)[:200], "note": "overnight tape unavailable"})


@tool("get_themes", "Narrative baskets with recent relative performance (the theme universe).",
      {"type": "object", "properties": {"region": {"type": "string"}}})
async def get_themes(args):
    data, read_failed = _read_first_nonempty_mapping_checked((
        _V / "site" / "basketdata" / "baskets.json",
    ))
    if data is None:
        return _json({
            "as_of": None,
            "themes": None,
            "read_status": "unavailable",
            "error": "themes_unavailable",
            "failed_sources": ["themes"],
        })
    baskets = data.get("baskets")
    if not isinstance(baskets, list):
        return _json({
            "as_of": data.get("as_of"),
            "themes": None,
            "read_status": "unavailable",
            "error": "themes_unavailable",
            "failed_sources": ["themes"],
        })
    out = []
    row_failed = read_failed
    for basket in baskets:
        if not isinstance(basket, dict) or not basket.get("id"):
            row_failed = True
            continue
        perf = basket.get("perf")
        if perf is None:
            perf = {}
        if not isinstance(perf, dict):
            perf = {}
            row_failed = True
        perf_20d = perf.get("20d")
        if perf_20d is None:
            perf_20d = {}
        if not isinstance(perf_20d, dict):
            perf_20d = {}
            row_failed = True
        out.append({
            "id": basket.get("id"),
            "name": basket.get("name"),
            "category": basket.get("category"),
            "perf_20d_rel": perf_20d.get("rel"),
            "n_members": basket.get("n_members"),
        })
    payload = {"as_of": data.get("as_of"), "themes": out}
    if row_failed:
        payload["read_status"] = "partial"
        payload["failed_sources"] = ["themes"]
        payload["note"] = "Theme-universe evidence is incomplete; malformed rows are unknown."
    return _json(payload)


@tool("get_standouts", "The ranked single-name buy board (top picks with suggested size).", {})
async def get_standouts(args):
    data, read_failed = _read_first_nonempty_mapping_checked((
        _V / "site" / "factordata" / "us_standouts.json",
    ))
    if data is None:
        if read_failed:
            return _json({
                "gate_go": None,
                "rank_by": None,
                "buy": None,
                "read_status": "unavailable",
                "error": "standouts_unavailable",
                "failed_sources": ["standouts"],
            })
        return _ok("us_standouts.json not built locally (ships in the Pages artifact).")

    buys_raw = data.get("buy")
    buys_failed = buys_raw is not None and not isinstance(buys_raw, list)
    if not buys_raw:
        fallback = data.get("standouts")
        # Keep usable legacy rows, but do not erase malformed primary evidence.
        if fallback is not None or not buys_failed:
            buys_raw = fallback
        buys_failed = buys_failed or (fallback is not None and not isinstance(fallback, list))
    selected_invalid = buys_raw is not None and not isinstance(buys_raw, list)
    buys = None if selected_invalid else list(buys_raw or [])[:20]
    row_failed = False
    if buys is not None:
        row_failed = any(not isinstance(row, dict) for row in buys)
        buys = [row for row in buys if isinstance(row, dict)]
    payload = {
        "gate_go": data.get("gate_go"),
        "rank_by": data.get("rank_by"),
        "buy": buys,
    }
    if read_failed or buys_failed or row_failed:
        payload["read_status"] = "partial"
        payload["failed_sources"] = ["standouts"]
        payload["note"] = "Standout-board evidence is incomplete; missing rows are unknown."
    return _json(payload)


@tool("get_portfolio", "The bot's current paper book + track record.", {})
async def get_portfolio(args):
    # This is the private Portfolio Advisor's own-book reader. ``flagship`` remains the
    # storage compatibility default, but it is archived and must never silently supply the
    # active US advisor context.
    portfolio_id = None
    try:
        from portfolio import registry

        portfolio_id = registry.DASHBOARD_DEFAULT_ID
        book_path = registry.data_dir(portfolio_id) / "latest.json"
    except Exception:  # noqa: BLE001
        return _json({
            "portfolio_id": portfolio_id,
            "read_status": "unavailable",
            "error": "portfolio_registry_unavailable",
            "failed_sources": ["portfolio_registry"],
        })

    latest, book_failed = _read_first_nonempty_mapping_checked((book_path,), allow_empty=True)
    if latest is None:
        if book_failed:
            return _json({
                "portfolio_id": portfolio_id,
                "read_status": "unavailable",
                "error": "portfolio_book_unavailable",
                "failed_sources": ["portfolio_book"],
            })
        return _json({"status": "no book yet", "portfolio_id": portfolio_id})
    if not latest:
        return _json({"status": "no book yet", "portfolio_id": portfolio_id})

    try:
        meta = registry.get(portfolio_id)
        if not isinstance(meta, dict):
            raise TypeError("portfolio registry metadata is not a mapping")
    except Exception:  # noqa: BLE001
        return _json({
            **latest,
            "portfolio_id": portfolio_id,
            "active": None,
            "lifecycle": None,
            "read_status": "partial",
            "failed_sources": ["portfolio_registry"],
            "note": "Book state is available; portfolio registry metadata did not complete.",
        })

    try:
        active = registry.is_active(portfolio_id)
        if not isinstance(active, bool):
            raise TypeError("portfolio active status is not a boolean")
    except Exception:  # noqa: BLE001
        return _json({
            **latest,
            "portfolio_id": portfolio_id,
            "active": None,
            "lifecycle": meta.get("status", "active"),
            "read_status": "partial",
            "failed_sources": ["portfolio_registry"],
            "note": "Book state is available; portfolio active-status read did not complete.",
        })

    return _json({
        **latest,
        "portfolio_id": portfolio_id,
        "active": active,
        "lifecycle": meta.get("status", "active"),
    })


@tool("get_decision_matrix", "The MULTI-SIDED decision matrix for a name or theme — every lens (valuation, quality, growth, narrative, leadership, asymmetry, risk, policy/admin tilt, Fed, institutional flows, options, rate sensitivity, cross-asset, conviction) with its read + honest status, plus the confluence/divergence synthesis. ALWAYS call this before any verdict.",
      {"type": "object", "properties": {"subject": {"type": "string"}, "kind": {"type": "string", "enum": ["name", "theme"]}}, "required": ["subject"]})
async def get_decision_matrix(args):
    subject = str(args["subject"])
    try:
        from portfolio import lenses
        payload = lenses.full(subject, args.get("kind", "name"))
        if (not isinstance(payload, dict)
                or not isinstance(payload.get("rows"), list)
                or not isinstance(payload.get("synthesis"), dict)):
            raise TypeError("decision matrix payload is malformed")
        return _json(payload)
    except Exception:  # noqa: BLE001
        return _json({
            "subject": subject,
            "read_status": "unavailable",
            "error": "decision_matrix_unavailable",
            "failed_sources": ["decision_matrix"],
        })


@tool("get_divergences", "Just the divergence patterns for a subject — where the lenses DISAGREE (the edge or the trap): distribution, early_edge, high_confluence_buy, crowded_top, policy_early.",
      {"type": "object", "properties": {"subject": {"type": "string"}, "kind": {"type": "string", "enum": ["name", "theme"]}}, "required": ["subject"]})
async def get_divergences(args):
    subject = str(args["subject"])
    try:
        from portfolio import lenses
        matrix = lenses.decision_matrix(subject, args.get("kind", "name"))
        if not isinstance(matrix, dict) or not isinstance(matrix.get("rows"), list):
            raise TypeError("decision matrix payload is malformed")
    except Exception:  # noqa: BLE001
        return _json({
            "subject": subject,
            "read_status": "unavailable",
            "error": "divergence_synthesis_unavailable",
            "failed_sources": ["decision_matrix"],
        })
    try:
        synthesis = lenses.synthesize(matrix)
        if not isinstance(synthesis, dict):
            raise TypeError("lens synthesis is not a mapping")
        divergences = synthesis["divergences"]
        confluence = synthesis["confluence"]
        vetoes = synthesis["vetoes"]
        if (
            not isinstance(confluence, (int, float)) or isinstance(confluence, bool)
            or (isinstance(confluence, float) and not math.isfinite(confluence))
        ):
            raise TypeError("lens synthesis confluence is malformed")
        if not isinstance(divergences, list) or not isinstance(vetoes, list):
            raise TypeError("lens synthesis lists are malformed")
        return _json({"divergences": divergences, "confluence": confluence, "vetoes": vetoes})
    except Exception:  # noqa: BLE001
        return _json({
            "subject": subject,
            "read_status": "unavailable",
            "error": "divergence_synthesis_unavailable",
            "failed_sources": ["divergence_synthesis"],
        })


@tool("get_altdata", "Alternative-data flow + Trump-family/administration linkage for a NAME — cross-signal convergence across congress/insider/government-contract/lobbying/Trump-trade channels, plus whether the name sits in the latent-stake entity graph (e.g. American Bitcoin -> Hut 8, branded crypto but the value accrues to an AI-power-infra parent). A QUALITATIVE research signal: politically-linked smart-money flow. Public-record + CONTEXT-ONLY (never a scored axis) — informs narrative/conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_altdata(args):
    t = (args.get("ticker") or "").upper()
    bt = (_read_json(_V / "site" / "altdata" / "by_ticker.json")
          or _read_json(_V / "data" / "altdata" / "by_ticker.json") or {})
    rec = (bt.get("tickers") or {}).get(t)
    latent = _read_json(_V / "site" / "altdata" / "latent.json") or {}
    graph = None
    for w in (latent.get("watch") or []):
        if (w.get("ticker") or "").upper() == t:
            graph = {"in_graph": True, "themes": [th.get("en") for th in (w.get("themes") or [])],
                     "trump_people": w.get("trump_people"), "top_holder": (w.get("top_holder") or {}).get("owner"),
                     "alt_corroborated": w.get("alt_corroborated"), "note": w.get("note")}
            break
    mismatch = next((m for m in (latent.get("mismatches") or [])
                     if t in {(m.get("repointed_ticker") or "").upper(), (m.get("entity_ticker") or "").upper()}), None)
    if rec is None and graph is None and mismatch is None:
        return _ok(f"no alt-data signal for {t} — not flagged by any political/insider/contract channel.")
    return _json({"ticker": t, "flow": rec, "latent_graph": graph, "label_mismatch": mismatch,
                  "note": "Public-record alt-data (congress/insider/govt-contract/SEC EDGAR — macro engine Signal Intelligence Desk). Context-only — informs narrative, never sizes alone."})


@tool("get_news",
      "Recent financial-news flow for a NAME — count of recent reputable headlines, a context-only "
      "sentiment lean aggregated from per-article tags, the baskets/sectors it touches, and the top "
      "headlines (title/source/url/summary). A QUALITATIVE research signal: what the tape is SAYING "
      "about this name. CONTEXT-ONLY (never a scored axis) — informs narrative/conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_news(args):
    t = (args.get("ticker") or "").upper()
    rel, bt = _first_vendored("site/news/by_ticker.json", "data/news/by_ticker.json")
    rec = (bt.get("tickers") or {}).get(t)
    if rec is None:
        return _ok(f"no news-flow signal for {t} — not covered by the macro news surface.")
    return _json({"ticker": t, "news": rec,
                  "note": "Public-record financial news flow. Context-only — informs narrative, never sizes alone.",
                  "freshness": _freshness(bt, rel), "evidence_grade": "vendored_snapshot"})


@tool("get_intelligence",
      "The UNIFIED News & Intelligence read for a NAME — both sides of the tape in ONE call: "
      "(1) news_flow (demand-side: what the market is SAYING — recent headline count, sentiment lean, "
      "top headlines) and (2) the alt-data signal (supply-side: what political/insider/contract/"
      "affiliation money is DOING — signal_score 0-100, action, conviction, channels, affiliations). "
      "Shown SIDE BY SIDE, never blended — the divergence between them is the edge (early = flow into a "
      "QUIET tape; crowded/late = flow into a LOUD tape). CONTEXT-ONLY — informs conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_intelligence(args):
    t = (args.get("ticker") or "").upper()
    urel, uni = _first_vendored("site/intelligence/by_ticker.json", "data/intelligence/by_ticker.json")
    rec = (uni.get("tickers") or {}).get(t)
    if rec is not None:
        labels = {"freshness": _freshness(uni, urel), "evidence_grade": "vendored_snapshot"}
    else:
        # the unified bundle isn't published yet — compose from the standalone feeds
        nrel = "site/news/by_ticker.json"
        ndoc = _read_json(_V / nrel) or {}
        news = (ndoc.get("tickers") or {}).get(t)
        arel = "site/altdata/mastermind.json"
        adoc = _read_json(_V / arel) or {}
        mm = adoc.get("signals") or []
        alt = next((s for s in mm if (s.get("ticker") or "").upper() == t), None)
        if news is None and alt is None:
            return _ok(f"no news or alt-data intelligence for {t}.")
        rec = {"ticker": t, "news": news, "alt": alt, "has_news": bool(news), "has_alt": bool(alt)}
        labels = {"missing_reason": "ticker_absent_in_vendored_file",
                  "fallback": "standalone_news_and_altdata_feeds",
                  "evidence_grade": "legacy_fallback",
                  "freshness": _freshness(ndoc, nrel if ndoc else None)}
        if alt is not None:
            labels["alt_freshness"] = _freshness(adoc, arel)
    return _json({"ticker": t, **rec,
                  "note": "News flow (what the tape says) + alt-data signal (what smart money does), side "
                          "by side. Context-only — the divergence between them is the read; never sizes alone.",
                  **labels})


@tool("get_quote",
      "Live (15-min delayed) market price(s) via Polygon for one or more tickers — the Brain's "
      "real-time price read: mark held positions, sanity-check an entry level, or confirm a move "
      "is real before forming a thesis. Returns {TICKER: price}. Prices are delayed and for "
      "reference/marks only — never a trade trigger on their own.",
      {"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}}},
       "required": ["tickers"]})
async def get_quote(args):
    tks = [str(t) for t in (args.get("tickers") or []) if t]
    try:
        from data_layer import polygon

        px = polygon.quotes(tks)
        if not isinstance(px, dict):
            raise TypeError("live quote result is not a mapping")
        if not any(v is not None for v in px.values()):
            return _ok("no live quotes returned for the requested tickers.")
        return _json({
            "quotes": px,
            "note": "Live 15-min delayed prices (Polygon). For marks/entry checks — not a signal.",
        })
    except Exception:  # noqa: BLE001 - setup, read and serialization share one evidence boundary
        return _json({
            "read_status": "unavailable",
            "error": "live_quotes_unavailable",
            "failed_sources": ["quotes"],
            "quotes": None,
        })


@tool("get_daily_briefing",
      "START HERE each session. The dashboard's RANKED daily briefing for the brain — the triaged "
      "worklist so you don't scan every name cold. Returns: macro_context (regime/quad, cycle, "
      "liquidity, Fed stance, plain-English posture, next catalysts) to frame the day; priority_queue "
      "(top names by transmission priority = facet-agreement × signal-strength, each with the "
      "FACTS-derived situation, lean, evidence, source mix, and falsifier); and divergences (the subset "
      "where the tape and smart-money DISAGREE — spend your depth budget here). Context-only — a triage, "
      "never a position size.",
      {"type": "object", "properties": {"top": {"type": "integer"}}})
async def get_daily_briefing(args):
    failed_sources = ["briefing"]
    try:
        top = int(args.get("top") or 20)
        briefing, briefing_failed = _read_first_nonempty_mapping_checked((
            _V / "site" / "intelligence" / "briefing.json",
            _V / "data" / "intelligence" / "briefing.json",
        ))
        if briefing is not None:
            queue_raw = briefing.get("priority_queue")
            divergences_raw = briefing.get("divergences")
            queue_failed = not isinstance(queue_raw, list)
            divergences_failed = divergences_raw is not None and not isinstance(divergences_raw, list)
            source_failed = briefing_failed or queue_failed or divergences_failed
            payload = {
                "as_of": briefing.get("as_of"),
                "macro_context": briefing.get("macro_context"),
                "n_actionable": briefing.get("n_actionable"),
                "n_divergences": briefing.get("n_divergences"),
                "priority_queue": None if queue_failed else queue_raw[:top],
                "divergences": None if divergences_failed else divergences_raw,
                "how_to_use": briefing.get("how_to_use"),
            }
            if source_failed:
                payload["read_status"] = "partial"
                payload["failed_sources"] = ["briefing"]
                payload["note"] = "Published briefing evidence is incomplete; missing fields are unknown."
            return _json(payload)

        # Missing publication permits a live briefing; a failed artifact remains visible.
        failed_sources = (["briefing"] if briefing_failed else []) + ["intake"]
        from brain import intake

        live = intake.build(limit=top)
        if not isinstance(live, dict):
            raise TypeError("intake briefing is not a mapping")
        candidates = live.get("candidates")
        if not isinstance(candidates, list):
            raise TypeError("intake candidates are not a list")
        payload = {
            "as_of": live.get("as_of"),
            "macro_context": live.get("macro_context"),
            "priority_queue": candidates,
            "note": "Composed live from the dashboard signal engines (briefing.json not built yet).",
        }
        if "note" in live:
            payload["intake_note"] = live["note"]
        if briefing_failed:
            payload["read_status"] = "partial"
            payload["failed_sources"] = ["briefing"]
        return _json(payload)
    except Exception:  # noqa: BLE001 - setup, composition and serialization share one boundary
        return _json({
            "as_of": None,
            "macro_context": None,
            "priority_queue": None,
            "read_status": "unavailable",
            "error": "daily_briefing_unavailable",
            "failed_sources": failed_sources,
        })


@tool("get_intel_hub",
      "The INTELLIGENCE HUB central command — the dashboard's deepest read, fusing ALL FIVE desks "
      "(news flow · alt-data smart-money · divergence radar · factor buy-board · POLICY intent) into "
      "one reasoned dossier per name. Each carries a composite CONVICTION (0-100, rewards independent "
      "cross-desk agreement, docked by an unanswered falsifier), the 5-desk direction matrix, and the "
      "2nd/3rd-order FLAGS that name the setup: stealth_accumulation / early_edge (smart money before "
      "the crowd) / crowded_top (distribution risk) / confirmed_trend / fading / policy_aligned / "
      "policy_conflict / THEME_WIDE (the whole basket is moving — durable) / ISOLATED (name-specific). "
      "Pass a ticker for that name's full dossier; omit it for the ranked command + divergence alerts + "
      "sector heat. The richest single pull; context-only, never sizes.",
      {"type": "object", "properties": {"ticker": {"type": "string"}, "top": {"type": "integer"}}})
async def get_intel_hub(args):
    try:
        ticker = args.get("ticker")
        if ticker is None:
            ticker = ""
        if not isinstance(ticker, str) or (ticker and not ticker.strip()):
            raise TypeError("intel-hub ticker is not a usable string")
        t = ticker.upper()
        hub, hub_failed = _read_first_nonempty_mapping_checked((
            _V / "site" / "intel_hub" / "hub.json",
            _V / "data" / "intel_hub" / "hub.json",
        ))
        if hub is None:
            if hub_failed:
                raise ValueError("intel-hub artifact is unavailable")
            return _ok("intel hub not built yet (site/intel_hub/hub.json absent — ships in the daily build).")

        command_raw = hub.get("command")
        sector_raw = hub.get("sector_heat")
        command_field_failed = not isinstance(command_raw, list)
        sector_field_failed = sector_raw is not None and not isinstance(sector_raw, list)
        command_rows = []
        row_failed = False
        for row in [] if command_field_failed else command_raw:
            row_ticker = row.get("ticker") if isinstance(row, dict) else None
            if not isinstance(row_ticker, str) or not row_ticker.strip():
                row_failed = True
                continue
            command_rows.append(row)
        sector_rows = [] if sector_field_failed else list(sector_raw or [])
        sector_row_failed = any(not isinstance(row, dict) for row in sector_rows)
        sector_rows = [row for row in sector_rows if isinstance(row, dict)]
        evidence_failed = hub_failed or command_field_failed or sector_field_failed or row_failed or sector_row_failed

        if t:
            dossier = next(
                (row for row in command_rows if row["ticker"].upper() == t),
                None,
            )
            if dossier is None and evidence_failed:
                return _json({
                    "ticker": t,
                    "dossier": None,
                    "macro_context": hub.get("macro_context"),
                    "read_status": "partial",
                    "failed_sources": ["intel_hub"],
                    "note": "Intel-hub evidence is incomplete; ticker absence cannot be confirmed.",
                })
            if dossier is None:
                return _ok(f"{t} not in the intel-hub command (no cross-desk signal today).")
            payload = {
                "ticker": t,
                **dossier,
                "macro_context": hub.get("macro_context"),
                "note": "Full 5-desk dossier. The flags name the setup; track the falsifier.",
            }
            if evidence_failed:
                payload["read_status"] = "partial"
                payload["failed_sources"] = ["intel_hub"]
            return _json(payload)

        top = int(args.get("top") or 15)

        def _slim(row):
            return {key: row.get(key) for key in (
                "ticker", "name", "composite_conviction", "lean", "n_confirm",
                "n_dissent", "flags", "read", "peers", "sectors", "falsifier",
            ) if key in row}

        payload = {
            "as_of": hub.get("as_of"),
            "macro_context": hub.get("macro_context"),
            "desks": hub.get("desks"),
            "counts": hub.get("counts"),
            "n_actionable": hub.get("n_actionable"),
            "command": None if command_field_failed else [_slim(row) for row in command_rows[:top]],
            "divergence_alerts": hub.get("divergence_alerts"),
            "sector_heat": None if sector_field_failed else sector_rows[:8],
            "how_to_use": hub.get("how_to_use"),
        }
        if evidence_failed:
            payload["read_status"] = "partial"
            payload["failed_sources"] = ["intel_hub"]
            payload["note"] = "Intel-hub evidence is incomplete; missing rows/fields are unknown."
        return _json(payload)
    except Exception:  # noqa: BLE001 - malformed inputs and unavailable evidence stay closed
        return _json({
            "read_status": "unavailable",
            "error": "intel_hub_unavailable",
            "failed_sources": ["intel_hub"],
            "command": None,
        })


@tool("get_intake_candidates",
      "The unified CANDIDATE QUEUE — every name the dashboard's signal engines flagged today, deduped "
      "and ranked with full PROVENANCE: for each ticker, which engines fired (briefing / divergence / "
      "buy-board / radar / alt-data / news-surge / open-thesis), why, the net lean, confidence, and "
      "falsifier. Corroboration across INDEPENDENT engines lifts a name. This is the intake funnel that "
      "replaces the old static shortlist — use it to choose what to research. Optional salience tiers "
      "split it into ACT (high-score, corroborated) / WATCH / DIVERGENT. Context-only — never sizes.",
      {"type": "object", "properties": {"limit": {"type": "integer"}, "tiers": {"type": "boolean"}}})
async def get_intake_candidates(args):
    try:
        from brain import intake

        limit = int(args.get("limit") or 30)
        out = intake.build(limit=limit)
        if not isinstance(out, dict):
            raise TypeError("intake queue is not a mapping")
        if args.get("tiers"):
            try:
                salience = intake.salience_tiers(limit)
                if not isinstance(salience, dict):
                    raise TypeError("salience tiers are not a mapping")
                json.dumps(salience, default=str, ensure_ascii=False)
                out["salience"] = salience
            except Exception:  # noqa: BLE001 - preserve the available candidate queue
                out["salience"] = None
                out["read_status"] = "partial"
                out["failed_sources"] = ["intake_salience"]
                note_key = "salience_note" if "note" in out else "note"
                out[note_key] = "Candidate queue is available; salience tiers did not complete."
        return _json(out)
    except Exception:  # noqa: BLE001 - setup, build and serialization share one boundary
        return _json({
            "read_status": "unavailable",
            "error": "intake_candidates_unavailable",
            "failed_sources": ["intake"],
            "candidates": None,
        })


@tool("get_ticker_package",
      "ONE-CALL DEEP DIVE for a name — bundles every per-ticker read so you don't chain five tools: the "
      "unified intelligence (news flow + alt-data signal + radar divergence + factor buy-board, side by "
      "side, with the brain summary), the decision-matrix divergences/confluence/vetoes (where the lenses "
      "agree or disagree), and the intake provenance (which engines flagged it). Call this once you've "
      "picked a name off the briefing/intake queue and want the full picture before a verdict. "
      "Context-only — informs conviction, never sizes alone.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_ticker_package(args):
    t = (args.get("ticker") or "").upper()
    uni = (_read_json(_V / "site" / "intelligence" / "by_ticker.json")
           or _read_json(_V / "data" / "intelligence" / "by_ticker.json") or {})
    intel = (uni.get("tickers") or {}).get(t)
    pkg = {"ticker": t, "intelligence": intel}
    try:
        from portfolio import lenses
        s = lenses.synthesize(lenses.decision_matrix(t, "name"))
        pkg["lenses"] = {"divergences": s.get("divergences"), "confluence": s.get("confluence"),
                         "vetoes": s.get("vetoes")}
    except Exception as e:  # noqa: BLE001
        pkg["lenses"] = {"error": f"decision matrix unavailable ({e})"}
    try:
        from brain import intake
        prov = next((c for c in intake.queue(60) if c["ticker"] == t), None)
        pkg["intake"] = prov
    except Exception:  # noqa: BLE001
        pkg["intake"] = None
    if intel is None and pkg.get("intake") is None:
        return _ok(f"no per-ticker intelligence for {t} — not flagged by any dashboard engine.")
    pkg["note"] = ("Full per-name picture: intelligence facets + lens divergences + intake provenance. "
                   "The divergence between demand-tape and supply-smart-money is the read; never sizes alone.")
    return _json(pkg)


@tool("get_fundamentals",
      "Valuation + financials + earnings + accounting-quality + the engine's conviction read for a NAME "
      "(from the per-ticker stock file). Use this for a fundamental picture before an add/cut verdict — "
      "P/E + forward tier, margins/growth/ROE/accruals, next earnings + SUE, analyst rating/target, the "
      "Piotroski/accounting verdict, and the composite conviction score/band/size with its cautions.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_fundamentals(args):
    t = _single_name_ticker(args)
    if t is None:
        return _json({
            "ticker": None,
            "read_status": "unavailable",
            "error": "ticker_fundamentals_unavailable",
            "failed_sources": ["fundamentals"],
        })
    data, read_failed = _read_first_nonempty_mapping_checked((
        _V / "site" / "stockdata" / f"{t}.json",
    ))
    if data is None:
        if read_failed:
            return _json({
                "ticker": t,
                "read_status": "unavailable",
                "error": "ticker_fundamentals_unavailable",
                "failed_sources": ["fundamentals"],
            })
        return _ok(f"no stock file for {t} (covered: S&P 1500 + crypto; ships in the Pages artifact).")

    specs = {
        "valuation": ["trailing_pe", "forward_pe", "forward_tier", "price_to_book",
                      "price_to_sales", "earnings_yield", "shareholder_yield", "value_z"],
        "financials": ["gross_margin", "net_margin", "fcf_margin", "rev_growth",
                       "ni_growth", "roe", "roa", "debt_to_assets", "accruals"],
        "earnings": ["next_date", "eps_forecast", "sue_z", "summary"],
        "analyst": ["rating", "target", "forward_pe", "div_yield"],
        "accounting_quality": ["verdict", "headline", "piotroski", "n_caution"],
        "factors": ["composite", "fundamental_score"],
        "tech": ["price", "pct_vs_50dma", "pct_vs_200dma", "rsi14", "off_52w_high_pct"],
        "conviction": ["score", "band", "verdict", "size", "risk", "cycle_blocked", "cautions"],
    }
    projected = {}
    section_failed = False
    for key, fields in specs.items():
        section, failed = _mapping_field_checked(data, key)
        section_failed = section_failed or failed
        projected[key] = None if failed else _pick(section, fields)

    payload = {
        "ticker": t,
        "name": data.get("name"),
        "sector": data.get("sector"),
        "asof": data.get("asof"),
        **projected,
    }
    if section_failed:
        payload["read_status"] = "partial"
        payload["failed_sources"] = ["fundamentals"]
        payload["note"] = "Fundamental evidence is incomplete; malformed sections are unknown."
    return _json(payload)


@tool("get_options",
      "Dealer-positioning / options read for a liquid NAME (gamma exposure): the GEX regime (long/short) + "
      "gamma-flip level + distance, magnets, IV30, put/call OI, max pain, call/put walls, the expected daily/"
      "weekly move, and the volatility-hole state (compression -> where price can vacuum to). Use for entry "
      "timing + risk bands, not stock selection.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_options(args):
    t = _single_name_ticker(args)
    if t is None:
        return _json({
            "ticker": None,
            "read_status": "unavailable",
            "error": "ticker_options_unavailable",
            "failed_sources": ["options"],
        })
    data, read_failed = _read_first_nonempty_mapping_checked((
        _V / "site" / "gex" / f"{t}.json",
    ))
    if data is None:
        if read_failed:
            return _json({
                "ticker": t,
                "read_status": "unavailable",
                "error": "ticker_options_unavailable",
                "failed_sources": ["options"],
            })
        return _ok(f"no options/GEX file for {t} (only the ~liquid options universe is covered).")

    meta, meta_failed = _mapping_field_checked(data, "meta")
    summary, summary_failed = _mapping_field_checked(data, "summary")
    expected_move, move_failed = _mapping_field_checked(data, "expected_move")
    vol_hole, vol_failed = _mapping_field_checked(data, "vol_hole")
    section_failed = meta_failed or summary_failed or move_failed or vol_failed
    payload = {
        "ticker": t,
        "asof": None if meta_failed else meta.get("asof"),
        "summary": None if summary_failed else _pick(summary, [
            "spot", "regime", "tier", "net_gex_bn", "gamma_flip", "dist_to_flip_pct",
            "magnet_up", "magnet_down", "iv30", "put_call_oi_ratio", "max_pain",
            "call_wall", "put_wall",
        ]),
        "expected_move": None if move_failed else _pick(expected_move, ["daily_pct", "weekly_pct", "front"]),
        "vol_hole": None if vol_failed else _pick(vol_hole, [
            "state", "bias", "upper", "lower", "to_upper_pct", "to_lower_pct", "compression",
        ]),
    }
    if section_failed:
        payload["read_status"] = "partial"
        payload["failed_sources"] = ["options"]
        payload["note"] = "Options evidence is incomplete; malformed sections are unknown."
    return _json(payload)


@tool("get_anticipation",
      "The forward-looking anticipation index for a watchlist NAME — a directional conviction read with "
      "multi-leg confluence: the index (-1..+1) + band, how many drivers align, how much to TRUST the "
      "direction, the realized-vol cone, and per-horizon (short/medium/long) expected moves + the drivers/"
      "guards/caveats. Context for a timing lean; honest about trust.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def get_anticipation(args):
    t = _single_name_ticker(args)
    if t is None:
        return _json({
            "ticker": None,
            "read_status": "unavailable",
            "error": "ticker_anticipation_unavailable",
            "failed_sources": ["anticipation"],
        })
    data, read_failed = _read_first_nonempty_mapping_checked((
        _V / "site" / "anticipationdata" / f"{t}.json",
    ))
    if data is None:
        if read_failed:
            return _json({
                "ticker": t,
                "read_status": "unavailable",
                "error": "ticker_anticipation_unavailable",
                "failed_sources": ["anticipation"],
            })
        return _ok(f"no anticipation file for {t} (only the curated forward-signal watchlist is covered).")
    return _json({
        "ticker": t, "name": data.get("name"), "group": data.get("group"), "as_of": data.get("as_of"),
        **_pick(data, ["anticipation_index", "index_band", "confluence_value", "n_go_legs",
                      "direction_trust", "trust", "vol_cone_ann", "horizons", "drivers", "guards", "caveats"]),
    })


@tool("read_signal", "Read a published signal/data JSON by path (allowlisted to the dashboard + bot data roots).",
      {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})
async def read_signal(args):
    def unavailable():
        return _json({
            "read_status": "unavailable",
            "error": "signal_read_unavailable",
            "failed_sources": ["signal"],
        })

    try:
        requested = Path(args["path"])
        if not requested.is_absolute():
            requested = _ROOT / requested
        # Retain the requested entry for absence proof; use the resolved,
        # authorized target for the content read.
        p = requested.resolve()
        roots = [r.resolve() for r in _READ_ROOTS]
    except Exception:  # noqa: BLE001 - resolution failure does not authorize a read
        return unavailable()
    if not any(p == root or root in p.parents for root in roots):
        return _ok("DENIED: path outside the allowed data roots.")
    if any(p == r or r in p.parents for r in _DENY_ROOTS):
        _audit_denied_book_read(p)
        return _ok("DENIED: portfolio book state (positions/ledger/research) is not readable "
                   "via read_signal — read your OWN book through your desk tool.")
    try:
        # JSON null is valid content. An exists() preflight cannot prove readable absence.
        return _json(json.loads(p.read_text()))
    except FileNotFoundError:
        try:
            import stat

            candidate = requested
            while True:
                try:
                    info = candidate.lstat()
                except FileNotFoundError:
                    if candidate.parent == candidate:
                        break
                    candidate = candidate.parent
                    continue
                if candidate != requested and stat.S_ISDIR(info.st_mode):
                    return _ok("not found: requested signal path")
                # A dangling entry or an entry that appeared after the read is not absence.
                break
        except Exception:
            pass
    except Exception:  # noqa: BLE001 - never disclose file/parser/serialization exceptions
        pass
    return unavailable()


def _audit_denied_book_read(p: Path) -> None:
    """Best-effort: record any attempt to read a portfolio book through read_signal, so a
    cross-book peek attempt is visible after the fact even though it was blocked."""
    try:
        _LEAK_AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with _LEAK_AUDIT.open("a") as fh:
            fh.write(json.dumps({"ts": _now(), "denied_path": str(p)}) + "\n")
    except Exception:
        pass


# ------------ proposal/write-back tools (never mutate a portfolio or paper account) ------------
@tool("save_research_note", "Persist a research note for the web app to render (Claude's conclusions/analysis).",
      {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"},
       "tickers": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "body"]})
async def save_research_note(args):
    slug = re.sub(r"[^a-z0-9]+", "-", args["title"].lower())[:48].strip("-")
    p = _RESEARCH / "notes" / f"{int(time.time())}_{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {args['title']}\n\n*tickers: {', '.join(args.get('tickers') or [])} · {_now()}*\n\n{args['body']}\n")
    return _ok(f"saved research note → {p.relative_to(_ROOT)}")


@tool("propose_thesis", "Propose a FALSIFIABLE investment thesis to the review queue (engine derives the falsifier + size; never auto-executed).",
      {"type": "object", "properties": {
          "subject": {"type": "string"}, "lean": {"type": "string", "enum": ["add", "overweight", "avoid", "underweight", "watch"]},
          "conviction": {"type": "string", "enum": ["low", "medium", "high"]}, "horizon_d": {"type": "integer"},
          "thesis": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}},
          "prob_correct": {"type": "number"}},
       "required": ["subject", "lean", "thesis"]})
async def propose_thesis(args):
    queue_owner = None
    try:
        from brain import research_desk as queue_owner
        queue_owner.enqueue_proposal(
            {**args, **_execution_provenance(), "status": "proposed"},
            queue_path=_PROPOSALS,
        )
    except Exception as exc:
        not_committed = queue_owner is None or isinstance(
            exc, queue_owner._ProposalQueueNotCommittedError
        )
        return _json({
            "write_status": "unavailable" if not_committed else "unknown",
            "error": (
                "research_proposal_queue_unavailable" if not_committed
                else "research_proposal_queue_outcome_unknown"
            ),
            "proposal_queued": False if not_committed else None,
            "note": (
                "This attempt did not replace the canonical proposal queue."
                if not_committed else
                "Proposal queue outcome is unknown. Reconcile it before considering retry."
            ),
        })
    return _ok(f"thesis proposed for {args['subject']} ({args['lean']}) → review queue. NOT executed.")


@tool("flag_emerging_theme", "Flag a newly-detected emerging narrative/theme for the web app.",
      {"type": "object", "properties": {"name": {"type": "string"}, "stage": {"type": "string"},
       "tickers": {"type": "array", "items": {"type": "string"}}, "rationale": {"type": "string"}},
       "required": ["name", "rationale"]})
async def flag_emerging_theme(args):
    _append(_RESEARCH / "emerging.jsonl", {**args, **_execution_provenance()})
    return _ok(f"flagged emerging theme '{args['name']}' → web app.")


# Legacy compatibility handler for non-Portfolio callers.  It is deliberately NOT registered in
# ``_ACTION`` below: the private Portfolio Advisor must use the validated proposal lifecycle, and
# legacy ``status=paper`` rows must not contaminate that homogeneous queue.
@tool("recommend_action", "LEGACY: log a paper recommendation outside the Portfolio Advisor queue.",
      {"type": "object", "properties": {"ticker": {"type": "string"},
       "action": {"type": "string", "enum": ["buy", "add", "trim", "exit", "watch"]},
       "rationale": {"type": "string"}}, "required": ["ticker", "action", "rationale"]})
async def recommend_action(args):
    _append(_RESEARCH / "legacy_recommendations.jsonl",
            {"source": "claude_cli", "status": "paper", **args})
    return _ok(f"legacy recommendation logged: {args['action']} {args['ticker']} "
               "(paper, outside the Portfolio Advisor queue).")


# -------- evaluate -> research paper -> non-executing proposal (user-pushed-name flow) --------
_ADVISOR_GATE_AUTHORITIES = {"up", "down", "hold", "blocked", "insufficient_data"}


def _advisor_gate_snapshot(ticker: str) -> dict | None:
    """One validated current lens snapshot for the user-pushed-name Advisor flow.

    ``None`` means the engine evidence did not complete or violated the public lens shape.
    Legitimate fail-closed engine states (for example ``insufficient_data``) remain real
    snapshots and are not relabelled as transport/read failure.
    """
    try:
        from portfolio import lenses

        matrix = lenses.full(ticker, "name")
        if not isinstance(matrix, dict):
            raise TypeError("advisor matrix is not a mapping")
        rows = matrix.get("rows")
        synthesis = matrix.get("synthesis")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise TypeError("advisor matrix rows are malformed")
        if not isinstance(synthesis, dict):
            raise TypeError("advisor synthesis is not a mapping")

        confluence = synthesis.get("confluence")
        authority = synthesis.get("size_authority")
        vetoes = synthesis.get("vetoes")
        divergences = synthesis.get("divergences")
        if (
            isinstance(confluence, bool)
            or not isinstance(confluence, (int, float))
            or not (-1.0 <= float(confluence) <= 1.0)
        ):
            raise TypeError("advisor confluence is malformed")
        if authority not in _ADVISOR_GATE_AUTHORITIES:
            raise TypeError("advisor size authority is malformed")
        if not isinstance(vetoes, list) or any(not isinstance(v, str) for v in vetoes):
            raise TypeError("advisor vetoes are malformed")
        if not isinstance(divergences, list):
            raise TypeError("advisor divergences are malformed")
        for row in rows:
            if row.get("direction") in ("bear", "bull"):
                if not isinstance(row.get("lens", ""), str):
                    raise TypeError("advisor display lens is malformed")
                if row.get("note") is not None and not isinstance(row["note"], str):
                    raise TypeError("advisor display note is malformed")
        # Validate the nested evidence we actually expose before any downstream effect.
        # A cycle, non-finite value or non-JSON object is unavailable evidence.
        json.dumps(divergences, allow_nan=False)
    except Exception:  # noqa: BLE001 - return only a closed evidence status to the model
        return None

    return {
        "matrix": matrix,
        "rows": rows,
        "synthesis": synthesis,
        "confluence": float(confluence),
        "size_authority": authority,
        "vetoes": vetoes,
        "divergences": divergences,
        "passed": authority == "up" and not vetoes,
    }


def _advisor_gate_reason(gate: dict) -> str:
    authority = gate["size_authority"]
    vetoes = gate["vetoes"]
    conf = gate["confluence"]
    if vetoes:
        return "hard veto — " + ", ".join(vetoes)
    if authority == "blocked":
        return "blocked (size_authority=blocked)"
    if authority == "insufficient_data":
        return "insufficient data (size_authority=insufficient_data)"
    if conf <= -0.3:
        return f"negative confluence ({conf:+.2f})"
    if authority != "up":
        return f"insufficient confluence ({conf:+.2f}; need > 0.30 with leadership + trend confirmation)"
    return f"cleared — confluence {conf:+.2f}, no hard veto"

@tool("evaluate_gate",
      "PRELIMINARY GATE for a name the user wants you to consider adding. Runs the multi-sided "
      "decision matrix and returns whether it passes the engine's size gate (size_authority 'up' "
      "AND no hard veto), the confluence, the hard vetoes, and the bearish/bullish lenses. Call "
      "this FIRST when the user pushes a ticker: if it does NOT pass or evidence is unavailable, "
      "explain why and stop; if it passes, tell the user it cleared preliminary inspection and that "
      "you're now writing the research paper before deciding.",
      {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]})
async def evaluate_gate(args):
    t = (args.get("ticker") or "").upper()
    gate = _advisor_gate_snapshot(t)
    if gate is None:
        return _json({
            "ticker": t,
            "read_status": "unavailable",
            "error": "advisor_gate_unavailable",
            "failed_sources": ["decision_matrix"],
            "passed": None,
            "confluence": None,
            "size_authority": None,
            "vetoes": None,
            "reason": "Preliminary gate unavailable; engine evidence did not complete.",
            "bear_lenses": None,
            "bull_lenses": None,
            "divergences": None,
        })
    rows = gate["rows"]
    bears = [(r.get("lens", "").replace("_", " ") + (f": {r['note']}" if r.get("note") else ""))
             for r in rows if r.get("direction") == "bear"][:5]
    bulls = [r.get("lens", "").replace("_", " ") for r in rows if r.get("direction") == "bull"][:6]
    return _json({
        "ticker": t,
        "passed": gate["passed"],
        "confluence": round(gate["confluence"], 3),
        "size_authority": gate["size_authority"],
        "vetoes": gate["vetoes"],
        "reason": _advisor_gate_reason(gate),
        "bear_lenses": bears,
        "bull_lenses": bulls,
        "divergences": gate["divergences"],
    })


@tool("file_research_paper",
      "File the holistic research paper YOU wrote for a name and get the combined Conviction-Index "
      "gate result. Call this AFTER evaluate_gate passes and you've done the deep research (tools + "
      "web) and written the full report in markdown. The tool combines the engine buy-score with "
      "your research score (combined = round(0.5*engine + 0.5*research); CONFIRMED if combined >= 60 "
      "and viability != avoid). The current preliminary engine gate must still be size_authority=up "
      "with no hard veto; otherwise nothing is stored. It STORES an eligible paper in the Research "
      "dashboard and returns paper_id + confirmed so the chat shows the user a button to open it. "
      "Use EXACTLY these report headings: "
      "## Thesis, ## Pros, ## Cons, ## Valuation, ## Fundamentals, ## Revenue streams, ## Competitive "
      "landscape & moat, ## Confirmed catalysts, ## Pending catalysts, ## Potential catalysts, "
      "## Forward earnings (recalculated), ## Bull / base / bear scenarios, ## Second- and third-order "
      "effects, ## Variant perception — what the market is missing, ## What to watch, ## Other factors.",
      {"type": "object", "properties": {
          "ticker": {"type": "string"},
          "report_md": {"type": "string"},
          "research_score": {"type": "integer"},
          "viability": {"type": "string", "enum": ["compelling", "fair", "rich", "avoid"]},
          "recommend": {"type": "boolean"},
          "summary": {"type": "string"},
          "key_risks": {"type": "array", "items": {"type": "string"}},
          "fair_value": {"type": "number"},
          "price_assessment": {"type": "string"},
          "confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
       "required": ["ticker", "report_md", "research_score", "viability", "recommend", "summary"]})
async def file_research_paper(args):
    from brain import research_paper as rp
    t = (args.get("ticker") or "").upper()
    gate = _advisor_gate_snapshot(t)
    if gate is None:
        return _json({
            "ticker": t,
            "read_status": "unavailable",
            "error": "research_paper_gate_unavailable",
            "failed_sources": ["decision_matrix"],
            "paper_saved": False,
            "note": "Research paper not filed because preliminary engine evidence is unavailable.",
        })
    if not gate["passed"]:
        return _json({
            "ticker": t,
            "gate_status": "failed",
            "error": "research_paper_preliminary_gate_failed",
            "paper_saved": False,
            "passed": False,
            "confluence": round(gate["confluence"], 3),
            "size_authority": gate["size_authority"],
            "vetoes": gate["vetoes"],
            "reason": _advisor_gate_reason(gate),
            "note": "Research paper not filed; the preliminary engine gate did not authorize ADD research flow.",
        })
    confluence = gate["confluence"]
    asof = _today()
    price = None
    try:
        from data_layer import polygon
        price = (polygon.quotes([t]) or {}).get(t)
    except Exception:
        price = None
    price = price if price else _stock_price(t)

    report_md = rp._strip_leading_narration(args["report_md"])
    paper = {
        "schema": rp.SCHEMA, "id": f"{asof}-{t}", "ticker": t, "asof": asof,
        "generated_at": rp._now(), "mode": "portfolio_research_advisor",
        "execution_provenance": _execution_provenance(),
        "model": "portfolio-research-advisor",
        "price_at_review": price, "research_score": int(args["research_score"]),
        "viability": args["viability"], "recommend": bool(args["recommend"]),
        "confidence": args.get("confidence") or "medium", "fair_value": args.get("fair_value"),
        "price_assessment": args.get("price_assessment") or "", "summary": args["summary"],
        "sections": rp._split_sections(report_md), "key_risks": args.get("key_risks") or [],
        "report_md": report_md,
    }
    rp._attach_gate(paper, confluence)          # -> engine_score, combined, confirmed, gate_reason
    try:
        rp.save_paper(paper)
    except rp._PaperSaveNotCommittedError:
        return _json({
            "ticker": t,
            "write_status": "unavailable",
            "error": "research_paper_save_unavailable",
            "paper_saved": False,
            "note": "This attempt did not replace the canonical paper; an older paper may remain.",
        })
    except Exception:
        return _json({
            "ticker": t,
            "write_status": "unknown",
            "error": "research_paper_save_outcome_unknown",
            "paper_saved": None,
            "note": "Canonical save outcome is unknown. Reconcile the paper before considering retry.",
        })
    try:
        rp.write_feed_note(paper)
    except Exception:
        pass
    meta = {"paper_id": paper["id"], "ticker": t, "title": f"{t} — Research Report",
            "combined": paper["combined"], "confirmed": paper["confirmed"],
            "research_score": paper["research_score"], "engine_score": paper["engine_score"],
            "viability": paper["viability"]}
    verdict = ("CONFIRMED (combined >= 60) — eligible for a non-executing ADD proposal."
               if paper["confirmed"] else f"NOT confirmed ({paper['gate_reason']}) — do not add it.")
    return _ok(f"{PAPER_MARKER} {json.dumps(meta)}\n"
               f"Filed research paper {paper['id']} → Research dashboard. Conviction Index "
               f"{paper['combined']}/100 (engine {paper['engine_score']} + research "
               f"{paper['research_score']}). {verdict}")


@tool("propose_portfolio_action",
      "Queue a NON-EXECUTING ADD / TRIM / EXIT proposal from the private Mastermind Portfolio "
      "Research Advisor. This tool accepts no size, shares, notional, price, or fill instruction; "
      "scheduled deterministic portfolio engines remain the sole sizing and paper-execution "
      "authority. An ADD proposal requires both a CONFIRMED research paper and a currently passing "
      "preliminary engine gate; TRIM/EXIT remain de-risking proposals and do not require the ADD gate. "
      "Urgency describes review priority only and never authorizes execution.",
      {"type": "object", "properties": {
          "ticker": {"type": "string"},
          "action": {"type": "string", "enum": ["add", "trim", "exit"]},
          "thesis": {"type": "string"},
          "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                       "maxItems": 12},
          "urgency": {"type": "string",
                      "enum": ["routine", "next_cycle", "urgent_review"]}},
       "required": ["ticker", "action", "thesis", "evidence", "urgency"]})
async def propose_portfolio_action(args):
    from brain import research_paper as rp
    from portfolio import advisor_trade

    # Defense in depth for direct handler callers that bypass JSON-schema validation. A
    # proposal carrying an order unit must be refused, not silently stripped and queued.
    forbidden = sorted({"weight", "size", "shares", "notional", "price", "fill"} & set(args or {}))
    if forbidden:
        return _ok(
            "REFUSED: Portfolio Advisor proposals cannot carry sizing or fill fields "
            f"({', '.join(forbidden)}). No proposal queued and no paper account changed."
        )

    t = (args.get("ticker") or "").upper()
    action = (args.get("action") or "").lower()
    if action == "add":
        try:
            paper = rp.latest_for(t, strict=True)
            if paper is not None and (
                not isinstance(paper, dict)
                or type(paper.get("confirmed")) is not bool
                or not isinstance(paper.get("ticker"), str)
                or paper["ticker"].upper() != t
            ):
                raise TypeError("confirmed paper evidence is malformed")
        except Exception:  # noqa: BLE001 - paper read occurs before any proposal effect
            return _ok(
                f"REFUSED: confirmed research-paper state is unavailable for {t}. "
                "No proposal queued and no paper account changed."
            )
        if paper is None or not paper["confirmed"]:
            return _ok(
                f"REFUSED: no CONFIRMED research paper on file for {t}. Run the flow first — "
                "evaluate_gate -> write + file_research_paper -> if confirmed, propose ADD. "
                "No proposal queued and no paper account changed."
            )
        gate = _advisor_gate_snapshot(t)
        if gate is None:
            return _ok(
                f"REFUSED: preliminary engine gate is unavailable for {t}; current ADD eligibility "
                "cannot be verified. No proposal queued and no paper account changed."
            )
        if not gate["passed"]:
            return _ok(
                f"REFUSED: preliminary engine gate does not authorize ADD for {t}: "
                f"{_advisor_gate_reason(gate)}. No proposal queued and no paper account changed."
            )
    res = advisor_trade.propose_action(
        t,
        action,
        thesis=args.get("thesis") or "",
        evidence=args.get("evidence") or [],
        urgency=args.get("urgency") or "",
        source="advisor_chat",
    )
    if not res.get("ok"):
        return _ok(
            f"proposal NOT queued for {t}: {res.get('error', 'unknown')}. "
            "No paper account changed."
        )
    proposal = res["proposal"]
    return _ok(
        f"PROPOSAL_QUEUED {json.dumps(proposal, ensure_ascii=False)}\n{res['note']}"
    )


_READ = [get_regime, get_overnight_tape, get_themes, get_standouts, get_portfolio, get_decision_matrix, get_divergences,
         get_altdata, get_news, get_intelligence, get_intel_hub, get_daily_briefing, get_intake_candidates,
         get_ticker_package, get_fundamentals, get_options, get_anticipation, get_quote,
         evaluate_gate, read_signal]
_ACTION = [save_research_note, propose_thesis, flag_emerging_theme,
           file_research_paper, propose_portfolio_action]
_ALL = _READ + _ACTION
SERVER_NAME = "bot"

# tool names as Claude sees them: mcp__<server>__<tool>
TOOL_NAMES = [f"mcp__{SERVER_NAME}__{t.name}" for t in _ALL]
WEB_TOOLS = ["WebSearch", "WebFetch"]


class InferenceToolError(ValueError):
    """Bounded protocol refusal before any registered handler executes."""


def inference_tool_catalog() -> list[dict]:
    """Describe exactly the incumbent registered roster, without SDK-only tools."""
    from jsonschema import Draft202012Validator

    catalog = []
    for tool in _ALL:
        schema = copy.deepcopy(tool.input_schema)
        if schema == {}:
            schema = {"type": "object", "properties": {}}
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise InferenceToolError("fabric_tool_schema_unavailable")
        # This adapter accepts the published argument contract only. In
        # particular, source/status, account identity and sizing cannot be
        # smuggled through JSON Schema's permissive extra-property default.
        schema["additionalProperties"] = False
        Draft202012Validator.check_schema(schema)
        catalog.append({"name": f"mcp__{SERVER_NAME}__{tool.name}",
                        "description": tool.description, "input_schema": schema})
    if len({row["name"] for row in catalog}) != len(catalog):
        raise InferenceToolError("fabric_tool_roster_invalid")
    return catalog


def _finite_json(value) -> bool:
    if value is None or isinstance(value, (str, bool)) or type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_json(item) for key, item in value.items())
    return False


def validate_inference_calls(blocks: list, *, used_ids=()) -> list[dict]:
    """Validate the entire completed batch before executing even its first tool."""
    from jsonschema import Draft202012Validator

    schemas = {row["name"]: row["input_schema"] for row in inference_tool_catalog()}
    seen, calls = set(used_ids), []
    for block in blocks:
        ident, name, args = block.id, block.name, block.input
        if (not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", ident)
                or ident in seen or name not in schemas or not isinstance(args, dict)
                or not _finite_json(args)):
            raise InferenceToolError("fabric_tool_request_invalid")
        # jsonschema's integer checker admits integral floats; the incumbent
        # tool contract is Python-typed, so keep explicit integer values exact.
        props = schemas[name].get("properties", {})
        if any(props.get(key, {}).get("type") == "integer" and type(value) is not int
               for key, value in args.items()):
            raise InferenceToolError("fabric_tool_arguments_invalid")
        if not Draft202012Validator(schemas[name]).is_valid(args):
            raise InferenceToolError("fabric_tool_arguments_invalid")
        seen.add(ident)
        calls.append({"id": ident, "name": name, "input": copy.deepcopy(args)})
    return calls


async def invoke_inference_tool(call: dict, *, provenance: dict) -> dict:
    """Invoke the existing handler once; errors after writes are not retry hints."""
    from types import SimpleNamespace

    validate_inference_calls([SimpleNamespace(**call)])
    if (set(provenance) != {"provider", "model", "turn_id"}
            or any(not isinstance(value, str) or not value for value in provenance.values())):
        raise InferenceToolError("fabric_tool_provenance_invalid")
    tools = {f"mcp__{SERVER_NAME}__{tool.name}": tool for tool in _ALL}
    token = _INFERENCE_PROVENANCE.set({"source": "fabric_application", **provenance})
    try:
        return await tools[call["name"]].handler(copy.deepcopy(call["input"]))
    finally:
        _INFERENCE_PROVENANCE.reset(token)


def tool_result_event(result, *, tool_name: str) -> dict:
    """A paper card can originate only in the registered filing handler's result."""
    if tool_name != f"mcp__{SERVER_NAME}__file_research_paper":
        return {"type": "tool_result"}
    blocks = result.get("content", []) if isinstance(result, dict) else result
    if not isinstance(blocks, (list, tuple)):
        blocks = [{"text": str(blocks or "")}]
    for block in blocks:
        raw = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
        if not isinstance(raw, str) or not raw.startswith(PAPER_MARKER + " "):
            continue
        try:
            meta, _ = json.JSONDecoder().raw_decode(raw[len(PAPER_MARKER):].lstrip())
            keys = {"paper_id", "ticker", "title", "combined", "confirmed",
                    "research_score", "engine_score", "viability"}
            if isinstance(meta, dict) and set(meta) == keys and isinstance(meta["paper_id"], str):
                return {"type": "paper", **meta}
        except (ValueError, TypeError):
            pass
    return {"type": "tool_result"}


def build_server():
    """Return the in-process MCP server config to hand the SDK via mcp_servers={SERVER_NAME: cfg}."""
    return create_sdk_mcp_server(name=SERVER_NAME, version="0.1.0", tools=_ALL)


def armed_allowed_tools() -> list[str]:
    """The tool allow-list for an armed research session: bot tools + web + read-only files."""
    return TOOL_NAMES + WEB_TOOLS + ["Read", "Grep", "Glob"]
