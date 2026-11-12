"""TECHNICIAN — the entry-timing seat. Judges "is NOW the right time to enter THIS chart?"

The audit found no seat owns entry timing: the pipeline confirms a *name* (FORGE) and reads the
*macro backdrop* (STRATEGIST) and the *bear case* (SENTINEL), but nobody rules on whether the
chart deserves an entry TODAY, a staged starter, or a WAIT-for-setup. This module fills that gap.
It is the TECHNICIAN / TACTICIAN role from ``docs/design/desk/02-organization-structure.md`` §2.2
and the ``TECH_NOW / TECH_STAGE / TECH_WAIT`` verdict from ``03-buy-pipeline-and-watchlist.md``.

Mirrors the committee seat pattern (``brain/committee.py`` — ``_sentinel_input`` / ``sentinel_assess``):
an information-boundary input builder → a seat executor returning a normalised, gradable verdict
dict → a durable per-name artifact writer for the outcome/timing grader.

STRUCTURAL BLINDNESS INVARIANT (mirrors SENTINEL). The Technician rules ONLY on the CHART / TIMING
— never on thesis quality. Its input MUST NOT carry the bull thesis, the combined/conviction score,
viability, fair value, recommend, or size_mult. This blindness is a hard invariant (see
``tests/test_technician.py::test_technician_input_is_blind_to_thesis``) so the timing call cannot
be anchored by how much the desk likes the *idea*.

FAIL-CONSERVATIVE DEFAULT (the INVERSE of the old SENTINEL "no-LLM → CONFIRM" hole). When no LLM is
reachable (``cli_bridge`` unavailable) OR on ANY error/parse failure, the verdict is ``"wait"`` — the
seat can only ever WITHHOLD or stage, NEVER force a buy. Subtract-only: this seat's authority is to
ADD ``wait``/``staged_starter`` on top of the deterministic floor; it can never turn a would-be-no
into a yes and never escalate a would-be-starter to a full entry.

RELATION TO THE DETERMINISTIC FLOOR. ``portfolio.watchlist.timing_withhold()`` remains the HARD
timing predicate (extended / weak-RS / parabolic / 'avoid' / weak-eq → park). THIS seat is an
ADDITIVE judgment layer *on top* of that floor (it can only withhold/stage further), gated behind
``MASTERMIND_TECHNICIAN`` (default OFF) and — eventually — the desk quorum / A/B experiment. It is
NOT wired into ``bot/phase2.py`` in this increment (that is the separate desk-quorum wiring step);
building it DARK and TESTABLE is the whole of this increment.

Model tier: Sonnet (``role="analyst"`` per ``config/agents.yml`` — the Technician is a
per-name analytical pass, not a deep-synthesis Opus seat). Invoked headlessly via
``brain.cli_bridge`` (the Claude Code subscription bridge). Degrades to ``"wait"`` fully offline,
so the seat is testable without a live LLM.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from brain import cli_bridge

_ARTIFACTS = Path(__file__).resolve().parent.parent / "data" / "committee"

# The three entry-timing verdicts (TECH_NOW / TECH_STAGE / TECH_WAIT). "wait" is the
# fail-conservative default and the only verdict the seat may reach without an LLM.
_VERDICTS = ("now", "staged_starter", "wait")
_DEFAULT_VERDICT = "wait"

# Fields the input must NEVER contain — the blindness invariant. The Technician rules on the
# CHART, never on the thesis. Kept as a module constant so the guard and the test share one list.
_FORBIDDEN_INPUT_KEYS = (
    "combined", "conviction", "viability", "fair_value", "fair_val", "recommend",
    "research_score", "engine_score", "size_mult", "bull", "thesis", "confirmed",
    "report_md", "paper",
)


def technician_enabled() -> bool:
    """The Technician seat runs only when explicitly armed via ``MASTERMIND_TECHNICIAN``.

    DARK by default: unset or falsy → OFF (byte-identical to base; the seat never runs). Only an
    explicit truthy value ({1, true, yes, on}) arms it. Note this is a pure *gating* read — even
    when armed, the assess path still fails CONSERVATIVE (→ "wait") if no LLM is reachable."""
    flag = os.environ.get("MASTERMIND_TECHNICIAN", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────────────────────
# input — the ONLY context the Technician sees. Entry-timing data ONLY: risk levels,
# chart extension/momentum, catalyst proximity, options geometry. Deliberately EXCLUDES
# the bull thesis / combined score / viability / fair_value (the blindness invariant).
# ─────────────────────────────────────────────────────────────────────────────
def technician_input(ticker: str, *, entry_signal: dict | None, tech: dict | None,
                     anticipation: dict | None = None, options: dict | None = None) -> dict:
    """Assemble the Technician's input slice from ENTRY-TIMING data ONLY.

    Parameters
    ----------
    entry_signal : the published per-name risk levels — ``{stop, buy_zone, entry_grade, chase_above}``
        (``bot.phase2._published_entry_signal`` shape).
    tech : the entry-technical block — ``{pct_vs_50dma, pct_vs_200dma, rsi14, off_52w_high_pct, rs,
        urgency, eq_grade, parabolic}`` (a superset of ``bot.phase2._entry_tech_fields``; only the
        chart/timing fields are read — every field nullable, missing → None).
    anticipation : optional catalyst/earnings window — ``{next_date, days_to_event, vol_cone, sue_z,
        horizon}``.
    options : optional entry geometry — ``{gamma_flip, expected_move, magnets, walls}``.

    BLINDNESS: no thesis/combined/viability/fair_value/recommend/size_mult field may appear — the
    output is defensively re-filtered against ``_FORBIDDEN_INPUT_KEYS`` before return, so even a
    caller that stuffs a forbidden key into ``tech``/``entry_signal`` cannot leak it into the seat.
    Pure; never raises (a non-dict argument degrades to {} for that slice)."""
    es = entry_signal if isinstance(entry_signal, dict) else {}
    tc = tech if isinstance(tech, dict) else {}
    an = anticipation if isinstance(anticipation, dict) else {}
    op = options if isinstance(options, dict) else {}

    payload = {
        "ticker": str(ticker or "").upper(),
        # risk levels — where's the stop, the buy zone, the entry grade, the do-not-chase line
        "entry_signal": {
            "stop": es.get("stop"),
            "buy_zone": es.get("buy_zone"),
            "entry_grade": es.get("entry_grade"),
            "chase_above": es.get("chase_above"),
        },
        # the chart itself — extension vs the MAs, RSI, distance off the 52w high, RS, quality/urgency
        "tech": {
            "pct_vs_50dma": tc.get("pct_vs_50dma"),
            "pct_vs_200dma": tc.get("pct_vs_200dma"),
            "rsi14": tc.get("rsi14"),
            "off_52w_high_pct": tc.get("off_52w_high_pct"),
            "rs": tc.get("rs"),
            "urgency": tc.get("urgency"),
            "eq_grade": tc.get("eq_grade"),
            "parabolic": bool(tc.get("parabolic")) if tc.get("parabolic") is not None else None,
        },
        # catalyst window — is an earnings/Fed/expiry event near enough to size around
        "anticipation": {
            "next_date": an.get("next_date"),
            "days_to_event": an.get("days_to_event") or an.get("days_to_next"),
            "vol_cone": an.get("vol_cone"),
            "sue_z": an.get("sue_z"),
            "horizon": an.get("horizon"),
        } if an else {},
        # options geometry — gamma flip, expected move, magnets/walls that shape the tranche timing
        "options": {
            "gamma_flip": op.get("gamma_flip"),
            "expected_move": op.get("expected_move"),
            "magnets": op.get("magnets"),
            "walls": op.get("walls"),
        } if op else {},
    }
    return _strip_forbidden(payload)


def _strip_forbidden(payload):
    """Recursively drop any key matching a forbidden thesis/score field (case-insensitive substring).

    The last line of defence for the blindness invariant: even if a caller's ``tech``/``entry_signal``
    dict carried an out-of-contract key (e.g. a stray ``combined`` or ``fair_value``), it is removed
    here so it can never reach the LLM or the artifact. Pure; never raises."""
    if isinstance(payload, dict):
        clean = {}
        for k, v in payload.items():
            kl = str(k).lower()
            if any(bad in kl for bad in _FORBIDDEN_INPUT_KEYS):
                continue
            clean[k] = _strip_forbidden(v)
        return clean
    if isinstance(payload, list):
        return [_strip_forbidden(x) for x in payload]
    return payload


_TECHNICIAN_SYS = (
    "You are the TECHNICIAN (tactician) on an equity investment committee. You rule ONLY on the "
    "CHART and the TIMING — is NOW the right moment to enter THIS name? You have deliberately NOT "
    "seen the bull thesis, the conviction score, the fair value, or the recommendation, and you "
    "MUST NOT speculate about them: reason ONLY from the price structure, extension, relative "
    "strength, entry/stop geometry, catalyst proximity, and options geometry you are given. "
    "Judge: is the entry clean (valid base / constructive setup, not extended or distributing, RS "
    "leading), or is it a chase into a stretched/parabolic/weak-RS tape that should WAIT for a "
    "better setup? A binary event inside the window with no defined risk caps you to a starter. "
    "Reply ONLY with JSON: {\"verdict\": \"now|staged_starter|wait\", \"confidence\": 0.0-1.0, "
    "\"rationale\": str}. "
    "now = enter now (clean setup); staged_starter = enter a STARTER only (acceptable but imperfect "
    "setup — imperfect base, catalyst pending, RS below leader); wait = do NOT enter now, park for a "
    "better setup. You can only WITHHOLD or stage; you can never force a full entry. Be blunt and "
    "specific about the price structure; no thesis talk, no moralizing."
)

_JSON_ONLY = (
    "\n\nCRITICAL OUTPUT CONTRACT: reply with ONLY a single valid JSON object — no markdown, no "
    "headers, no prose, no code fences. Your ENTIRE response must parse with json.loads, beginning "
    "with '{' and ending with '}'."
)


def _parse_json(txt: str | None) -> dict | None:
    if not txt:
        return None
    try:
        return json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception:  # noqa: BLE001
        return None


def _clamp01(x, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return default


def _wait(rationale: str, *, confidence: float = 0.0) -> dict:
    """The fail-conservative verdict. The ONLY verdict the seat reaches with no LLM / on any error."""
    return {"agent": "technician", "verdict": _DEFAULT_VERDICT,
            "confidence": round(_clamp01(confidence), 3), "rationale": str(rationale)[:600]}



# Fabric extends the existing per-name artifact. The native application owner
# retains admission, account choice, usage, close, and portfolio workload policy.
_FABRIC_KEY = "_fabric_technician"
_FABRIC_LANE = "mastermind-technician"
_FABRIC_WORKLOAD = "portfolio_analysis"
_FABRIC_MAX_TOKENS = 1500


def _fabric_location(asof, ticker, inp, *, create=False):
    import re
    supplied = inp.get("ticker") if isinstance(inp, dict) else None
    if ticker and supplied and str(ticker).upper() != str(supplied).upper():
        raise ValueError("technician_ticker_conflict")
    tk = str(ticker or supplied or "UNK").upper()
    day = str(asof)[:10] if asof else date.today().isoformat()
    if (re.fullmatch(r"[A-Z0-9][A-Z0-9._^-]{0,31}", tk) is None
            or date.fromisoformat(day).isoformat() != day):
        raise ValueError("technician_artifact_identity_invalid")
    base = Path(_ARTIFACTS).absolute()
    if base.is_symlink():
        raise ValueError("technician_artifact_root_invalid")
    if create:
        base.mkdir(parents=True, exist_ok=True)
    root = base.resolve(strict=create)
    path = root / day / tk / "technician.json"
    return root, path, day, tk


def _fabric_presence(path):
    """Pure local discriminator; a corrupt existing artifact is a barrier."""
    import stat
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
            raise ValueError("technician_artifact_invalid")
        raw = stream.read(4 * 1024 * 1024 + 1)
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("technician_artifact_invalid")
    return _FABRIC_KEY in value


def _fabric_owner():
    from brain import fabric_inference
    modes, shared, root = fabric_inference._owner()
    from engine import catalyst_tone as cache
    if Path(cache.__file__).resolve().parent.parent != root:
        raise ImportError("technician_cache_owner_mismatch")
    return modes, shared, root, cache


def _fabric_source(root, day, ticker):
    return {"consumer": "mastermind-technician", "root": str(root), "asof": day, "ticker": ticker}


def _fabric_prompt(inp):
    return json.dumps(inp, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _fabric_public(row):
    # A held row may retain a parseable model result. It is evidence, not an
    # eligible verdict. The artifact must still expose conservative WAIT.
    receipt = row["receipt"]
    if (row["state"] == "terminal" and row["result"] is not None
            and receipt is not None and not receipt["effect_unknown"]
            and receipt["close"] == {"disposition": "closed", "closed": True,
                                     "effect_unknown": False, "attempted": True}):
        return {**row["result"], "model": receipt["served_model"], "served_by": receipt["provider"]}
    reason = ("Fabric original pending or held — fail-conservative WITHHOLD."
              if row["state"] != "terminal" else
              "Fabric returned no usable result — fail-conservative WITHHOLD.")
    return {**_wait(reason), "model": None, "served_by": None}


def _fabric_document(value, root, day, ticker, cache):
    if value is None:
        return None
    if (type(value) is not dict or value.get("agent") != "technician"
            or not {"agent", "input", "verdict"} <= set(value)):
        raise ValueError("technician_artifact_invalid")
    if _FABRIC_KEY not in value:
        return value
    if set(value) != {"agent", "input", "verdict", _FABRIC_KEY}:
        raise ValueError("technician_artifact_fields_invalid")
    owned = value[_FABRIC_KEY]
    if (type(owned) is not dict or set(owned) != {"schema", "cache", "requests"}
            or owned["schema"] != "mastermind.technician.fabric.v1"
            or type(owned["requests"]) is not dict):
        raise ValueError("technician_original_invalid")
    state = cache._fabric_cache_value(owned["cache"], _fabric_source(root, day, ticker))
    if not state["entries"] or set(owned["requests"]) != {r["operation_id"] for r in state["entries"]}:
        raise ValueError("technician_request_set_invalid")
    for row in state["entries"]:
        request = owned["requests"][row["operation_id"]]
        if (type(request) is not dict or set(request) != {"input", "system", "user", "context", "max_tokens"}
                or type(request["input"]) is not dict or _strip_forbidden(request["input"]) != request["input"]
                or request["input"].get("ticker") != ticker
                or request["system"] != _TECHNICIAN_SYS + _JSON_ONLY
                or request["user"] != _fabric_prompt(request["input"])
                or request["max_tokens"] != _FABRIC_MAX_TOKENS
                or request["context"] != {"asof": day, "ticker": ticker, "input": request["input"],
                                         "workload": _FABRIC_WORKLOAD}):
            raise ValueError("technician_frozen_input_invalid")
        commitment = {"system": request["system"], "user": request["user"],
                      "max_tokens": request["max_tokens"], "context": request["context"]}
        if row.get("schema") == cache._AUTO_CACHE_ENTRY:
            commitment.update(application_inspection=row["inspection"], application_mode=row["mode_id"])
            original, actual = cache._cache_auto_request(row["operation_id"],
                request["system"], request["user"], request["max_tokens"])
            if row["request"] != actual:
                raise ValueError("technician_request_changed")
            cache._cache_auto_validate(row, original)
        if (row["input_digest"] != cache._cache_hash(commitment)
                or row["result"] is not None and row["result"] != _normalise_reply(row["text"], strict=True)):
            raise ValueError("technician_result_changed")
    current = state["entries"][-1]
    if (value["input"] != owned["requests"][current["operation_id"]]["input"]
            or value["verdict"] != _fabric_public(current)):
        raise ValueError("technician_projection_changed")
    return value


def _fabric_assess(inp, *, asof=None, ticker=None):
    try:
        modes, shared, macro_root, cache = _fabric_owner()
        root, path, day, tk = _fabric_location(asof, ticker, inp, create=True)
        if not isinstance(inp, dict) or tk == "UNK":
            return _wait("Technician input unavailable — fail-conservative WITHHOLD.")
        clean = cache._cache_decode(cache._cache_json(_strip_forbidden(inp)))
        clean["ticker"] = tk
        source = _fabric_source(root, day, tk)
        def read():
            return _fabric_document(cache._cache_read(path), root, day, tk, cache)
        with cache._cache_lock(path, root):
            doc = read()
            if doc is not None and _FABRIC_KEY in doc:
                saved = doc[_FABRIC_KEY]
                if any(r["state"] != "terminal" for r in saved["cache"]["entries"]):
                    return _wait("Fabric original pending or held — fail-conservative WITHHOLD.")
                prior = next((r for r in reversed(saved["cache"]["entries"])
                              if saved["requests"][r["operation_id"]]["input"] == clean), None)
                if prior is not None:
                    if prior["operation_id"] != saved["cache"]["entries"][-1]["operation_id"]:
                        return _wait("Technician input has a newer original — fail-conservative WITHHOLD.")
                    return _fabric_public(prior)
        # BOT/config Fabric selection without a valid host application mode stays
        # exclusive and unavailable; no default mode or native CLI is invented.
        if not cli_bridge._application_fabric_selected() or shared.application_mode_id() is None:
            return _wait("Fabric application selection unavailable — fail-conservative WITHHOLD.")
        selected, factory = modes.configured_application_fabric(
            lane=_FABRIC_LANE, workload_profile=_FABRIC_WORKLOAD, root=macro_root)
        cfg = {"provider_order": ["fabric"], "workload_profile": _FABRIC_WORKLOAD,
               "max_tokens": _FABRIC_MAX_TOKENS}
        if selected is not True or type(factory) is not modes.ApplicationFabricFactory:
            return _wait("Fabric application binding unavailable — fail-conservative WITHHOLD.")
        inspection = factory.inspect(cfg)  # Pure qualification, before an original claim.
        mode_id = shared.application_mode_id()
        request = {"input": clean, "system": _TECHNICIAN_SYS + _JSON_ONLY,
                   "user": _fabric_prompt(clean), "max_tokens": _FABRIC_MAX_TOKENS,
                   "context": {"asof": day, "ticker": tk, "input": clean, "workload": _FABRIC_WORKLOAD}}
        def load_cache():
            current = read()
            return (current[_FABRIC_KEY]["cache"] if current and _FABRIC_KEY in current
                    else cache._fabric_cache_value(None, source))
        def store_cache(value):
            current = read()
            owned = (current[_FABRIC_KEY] if current and _FABRIC_KEY in current else
                     {"schema": "mastermind.technician.fabric.v1",
                      "cache": cache._fabric_cache_value(None, source), "requests": {}})
            before = owned["cache"]["entries"]
            rows = value["entries"]
            if len(rows) not in (len(before), len(before) + 1):
                raise ValueError("technician_original_count_changed")
            if len(rows) == len(before) + 1:
                if (rows[:-1] != before or rows[-1]["state"] != "pending"
                        or rows[-1]["inspection"] != inspection or rows[-1]["mode_id"] != mode_id):
                    raise ValueError("technician_claim_changed")
                owned["requests"][rows[-1]["operation_id"]] = cache._cache_decode(cache._cache_json(request))
            else:
                changed = [(old, new) for old, new in zip(before, rows) if old != new]
                if (len(changed) != 1 or changed[0][0]["state"] != "pending"
                        or changed[0][1]["state"] not in ("terminal", "held")
                        or any(old["operation_id"] != new["operation_id"] for old, new in zip(before, rows))):
                    raise ValueError("technician_original_transition_invalid")
            owned["cache"] = value
            newest = rows[-1]
            document = {"agent": "technician", "input": owned["requests"][newest["operation_id"]]["input"],
                        "verdict": _fabric_public(newest), _FABRIC_KEY: owned}
            _fabric_document(document, root, day, tk, cache)
            cache._cache_save(path, document)
            read()
        observed = cache._fabric_cached_document(path=path, root=macro_root, cache_root=root,
            logical_source=source, cfg=cfg, lane=_FABRIC_LANE,
            system=request["system"], user=request["user"], input_context=request["context"],
            validate=lambda text: _normalise_reply(text, strict=True),
            load_cache=load_cache, store_cache=store_cache, startup_workload=_FABRIC_WORKLOAD)
        if observed is None or observed["receipt"] is None:
            return _wait("Fabric original unavailable or held — fail-conservative WITHHOLD.")
        with cache._cache_lock(path, root):
            current = read()
            row = next(r for r in current[_FABRIC_KEY]["cache"]["entries"]
                       if r["operation_id"] == observed["receipt"]["operation_id"])
            return _fabric_public(row)
    except Exception:
        return _wait("Fabric original unavailable or held — fail-conservative WITHHOLD.")


def technician_assess(inp: dict, *, asof: str | None = None, ticker: str | None = None) -> dict:
    """Use the existing artifact for selected model-only analysis and recovery."""
    try:
        _, path, day, tk = _fabric_location(asof, ticker, inp)
        if _fabric_presence(path) or cli_bridge._application_fabric_selected():
            return _fabric_assess(inp, asof=day, ticker=tk)
        before = path.read_bytes() if path.exists() else None
        verdict = _legacy_assess(inp, asof=day, ticker=tk)
        if (cli_bridge._application_fabric_selected() or _fabric_presence(path)
                or (path.read_bytes() if path.exists() else None) != before):
            return _wait("Technician selection or original changed — fail-conservative WITHHOLD.")
        return verdict
    except Exception:
        return _wait("Technician original unavailable — fail-conservative WITHHOLD.")


def _legacy_assess(inp: dict, *, asof: str | None = None, ticker: str | None = None) -> dict:
    """Rule on the entry timing for one name. Returns ``{agent, verdict, confidence, rationale}`` with
    ``verdict ∈ {"now","staged_starter","wait"}``.

    Uses ``cli_bridge`` (Sonnet ``role="analyst"``) when a local Claude Code LLM is available.

    FAIL-CONSERVATIVE: if no LLM is reachable (``cli_bridge.available()`` is False) OR the call/parse
    fails for ANY reason → verdict ``"wait"`` (the seat can only ever withhold/stage — never force a
    buy). SUBTRACT-ONLY: an unrecognised verdict is coerced to ``"wait"``, never to a more aggressive
    entry. Never raises."""
    _inp_tk = inp.get("ticker") if isinstance(inp, dict) else None
    tk = str(ticker or _inp_tk or "").upper() or None

    # fail-conservative gate: no LLM → WITHHOLD (the inverse of the old SENTINEL default-CONFIRM hole)
    try:
        if not cli_bridge.available():
            return _wait("no LLM available — fail-conservative WITHHOLD (Technician can only wait/stage).")
    except Exception:  # noqa: BLE001 — an availability probe failure is itself a reason to withhold
        return _wait("LLM availability probe failed — fail-conservative WITHHOLD.")

    prompt = json.dumps(inp or {}, default=str)
    try:
        res = cli_bridge.reason_sync(prompt, role="analyst", system=_TECHNICIAN_SYS + _JSON_ONLY,
                                     log_run=False)
    except Exception:  # noqa: BLE001 — any call failure fails conservative, never breaks the caller
        return _wait("Technician LLM call failed — fail-conservative WITHHOLD.")
    if not isinstance(res, dict) or not res.get("ok"):
        return _wait("Technician LLM returned no usable result — fail-conservative WITHHOLD.")

    return _normalise_reply(res.get("text"))


def _normalise_reply(text, *, strict=False):
    j = _parse_json(text)
    if strict:
        try:
            json.dumps(j, allow_nan=False)
            if isinstance(j, dict) and "confidence" in j:
                import math
                if isinstance(j["confidence"], bool) or not math.isfinite(float(j["confidence"])):
                    j = None
        except (ValueError, TypeError):
            j = None
    if not isinstance(j, dict):
        j = None
    if not j:
        return _wait("Technician reply did not parse as JSON — fail-conservative WITHHOLD.")

    verdict = str(j.get("verdict", "")).strip().lower().replace("-", "_").replace(" ", "_")
    # normalise the design's TECH_* / enum spellings onto the canonical three
    _alias = {"tech_now": "now", "enter_now": "now", "buy_now": "now",
              "tech_stage": "staged_starter", "stage": "staged_starter", "starter": "staged_starter",
              "stage_starter": "staged_starter", "tech_wait": "wait"}
    verdict = _alias.get(verdict, verdict)
    if verdict not in _VERDICTS:
        # SUBTRACT-ONLY: an unknown/garbage verdict can only degrade to the conservative floor.
        return _wait(f"Technician returned an unrecognised verdict ({j.get('verdict')!r}) — "
                     "coerced to conservative WITHHOLD.", confidence=j.get("confidence", 0.0))

    return {
        "agent": "technician",
        "verdict": verdict,
        "confidence": round(_clamp01(j.get("confidence", 0.5), default=0.5), 3),
        "rationale": str(j.get("rationale", ""))[:600],
    }


def _legacy_write_artifact(root, path, inp, verdict):
    """The stdlib writer shares the same selected-owner lock inode.

    Unselected persistence does not require Macro imports. Recheck ownership
    under technician.json.lock so a late native completion cannot erase a claim.
    """
    import fcntl
    import stat
    import tempfile
    current = root
    for part in path.parent.relative_to(root).parts:
        child = current / part
        child.mkdir(exist_ok=True)
        if child.is_symlink() or not child.is_dir():
            raise ValueError("technician_artifact_directory_invalid")
        current = child
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    temporary = None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("technician_artifact_lock_invalid")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if cli_bridge._application_fabric_selected() or _fabric_presence(path):
            return None
        raw = json.dumps({"agent": "technician", "input": inp, "verdict": verdict},
                         indent=2, default=str).encode()
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="technician.json.tmp-",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if path.read_bytes() != raw:
            raise ValueError("technician_artifact_readback_mismatch")
        return str(path.parent)
    finally:
        os.close(fd)
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _write_artifact(asof: str | None, ticker: str | None, inp: dict | None,
                    verdict: dict | None) -> str | None:
    """Fence the legacy writer against the existing selected artifact owner."""
    root, path, day, tk = _fabric_location(asof, ticker, inp, create=True)
    if not (_fabric_presence(path) or cli_bridge._application_fabric_selected()):
        return _legacy_write_artifact(root, path, inp, verdict)
    _, _, _, cache = _fabric_owner()
    with cache._cache_lock(path, root):
        current = _fabric_document(cache._cache_read(path), root, day, tk, cache)
        if current is not None and _FABRIC_KEY in current:
            rows = current[_FABRIC_KEY]["cache"]["entries"]
            clean = _strip_forbidden(inp) if isinstance(inp, dict) else inp
            if isinstance(clean, dict):
                clean = {**clean, "ticker": tk}
            if (any(r["state"] != "terminal" for r in rows)
                    or current["input"] != clean or current["verdict"] != verdict):
                return None
            return str(path.parent)  # Already atomically published with the original receipt.
        if cli_bridge._application_fabric_selected():
            return None
        cache._cache_save(path, {"agent": "technician", "input": inp, "verdict": verdict})
        return str(path.parent)


def run(ticker: str, *, entry_signal: dict | None, tech: dict | None,
        anticipation: dict | None = None, options: dict | None = None,
        asof: str | None = None) -> dict:
    """Convenience wrapper: build the blind input → assess → persist the artifact, in one call.

    Returns the verdict dict (fail-conservative ``"wait"`` when no LLM is available). The artifact is
    written best-effort for native calls. Fabric results require the matching original artifact
    to be confirmed before delivery; unresolved publication returns conservative wait. Never raises."""
    try:
        inp = technician_input(ticker, entry_signal=entry_signal, tech=tech,
                               anticipation=anticipation, options=options)
    except Exception:  # noqa: BLE001 — an input-build failure still yields a conservative verdict
        inp = {"ticker": str(ticker or "").upper()}
    try:
        _, path, day, tk = _fabric_location(asof, ticker, inp)
        fabric_owned = _fabric_presence(path) or cli_bridge._application_fabric_selected()
    except Exception:
        return _wait("Technician artifact identity invalid — fail-conservative WITHHOLD.")
    verdict = technician_assess(inp, asof=day, ticker=tk)
    published = None
    try:
        published = _write_artifact(day, tk, inp, verdict)
    except Exception:  # noqa: BLE001 — unselected legacy persistence remains best-effort
        pass
    if published is None:
        try:
            fabric_owned = (fabric_owned or cli_bridge._application_fabric_selected()
                            or _fabric_presence(path))
        except Exception:
            fabric_owned = True  # An unreadable original cannot become a legacy result.
        if fabric_owned:
            return _wait("Technician artifact unavailable — fail-conservative WITHHOLD.")
    return verdict
