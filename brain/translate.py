"""Cache-backed EN->Simplified-Chinese translator for the Mastermind dashboard.

Design:
- Cache file: data/brain/translations.json. Legacy English->Chinese maps remain
  readable; new writes preserve completed strings and original Fabric receipts
  in one versioned envelope, under the incumbent cross-process lock.
- cached_zh(text) -> str | None
  Pure cache lookup — NEVER calls the LLM; safe in the hot request path.
- translate_and_cache(texts) -> dict
  Uses the selected qualified Fabric subscription or the existing native scout
  bridge. Each short batch or long document owns one operation. Pending and
  unresolved original inputs stay held across restarts and selector changes.
  On failure, callers receive English; no hidden retry or provider fallback.
- translate_book(book) -> None
  Warms the cache for every translatable string in a portfolio.v1 dict.
- translate_notes(notes_dir) -> None
  Warms the cache for every research note body + title.
- translate_decisions() -> None
  Warms the cache for the autonomous daily-decision log write-ups (Daily Decision Log).
- translate_runs() -> None
  Warms the cache for run-log titles + summaries (the Brain Activity log's AI write-ups).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

# Matches the "*tickers: AVGO, SMH · 2026-06-20T...*" metadata line a research
# note carries on its second line. Kept in sync with app.web._parse_note so the
# body string we cache here is byte-identical to the body the /api/research route
# looks up — otherwise the zh translation never matches and the feed stays English.
_TICKER_LINE_RE = re.compile(r"\*tickers:\s*(.*?)\s*·\s*([\d\-T:.+Z]+)\*")

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_PATH = _ROOT / "data" / "brain" / "translations.json"

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

# In-process memo of the translations cache, invalidated by file mtime. The dashboard hot path
# (app/web.api_portfolio) calls cached_zh dozens-to-100+ times per request; re-reading + re-parsing
# the whole JSON file each time was pure wasted I/O. _save_cache replaces the file (mtime bumps), so a
# warm-cache write is picked up on the very next load.
_cache_mem: dict[str, str] | None = None
_cache_mtime = None
_CACHE_SCHEMA = "mastermind.translation_cache.v1"
_CACHE_LIMIT = 64 * 1024 * 1024
_MAX_OPERATIONS = 10000
_LOCK_NAME = "global:brain_translation"
_IDENTITY_FIELDS = {"provider", "model", "cap_id", "capability_id", "cost_basis",
                    "workload_policy", "transport_identity"}
_RECEIPT_FIELDS = {"inputs", "inputs_sha256", "identity", "state", "steps",
                   "usage", "close", "reason"}


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _inputs_digest(inputs: list[str]) -> str:
    return hashlib.sha256(_json_bytes(sorted(inputs))).hexdigest()


def _string_map(value) -> bool:
    return (type(value) is dict and all(type(k) is str and type(v) is str
                                      for k, v in value.items()))


def _identifier(value) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value) is not None


def _count(value, *, nullable=False) -> bool:
    return value is None and nullable or type(value) is int and 0 <= value <= 256 * 10 ** 12


def _identity_valid(value) -> bool:
    if (type(value) is not dict or set(value) != _IDENTITY_FIELDS
            or not all(_identifier(value[key]) for key in ("provider", "model", "cap_id", "capability_id"))
            or value["cost_basis"] != "subscription"
            or type(value["transport_identity"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value["transport_identity"]) is None):
        return False
    policy = value["workload_policy"]
    # Validate stored provenance shape, not current eligibility. Historical
    # cache reads must not consult a changing live policy or open a client.
    return (type(policy) is dict and set(policy) == {"schema", "policy_revision", "policy_hash",
            "profiles", "execution_surface", "allowed_order", "denied_order"}
            and policy["schema"] == "mastermind.provider_workload_decision.v1"
            and type(policy["policy_revision"]) is int and 1 <= policy["policy_revision"] <= 2147483647
            and type(policy["policy_hash"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", policy["policy_hash"]) is not None
            and policy["execution_surface"] == "inference"
            and all(type(policy[key]) is list and len(policy[key]) <= 64
                    and all(_identifier(item) for item in policy[key])
                    for key in ("profiles", "allowed_order", "denied_order")))


def _usage_valid(value) -> bool:
    if value is None:
        return True
    if (type(value) is not dict or set(value) != {"input_tokens", "output_tokens", "usage_state",
            "completed_input_tokens", "completed_output_tokens"}
            or value["usage_state"] not in {"known", "unknown"}
            or not all(_count(value[key]) for key in ("completed_input_tokens", "completed_output_tokens"))):
        return False
    if value["usage_state"] == "unknown":
        return value["input_tokens"] is None and value["output_tokens"] is None
    return all(_count(value[key]) and value[key] == value["completed_" + key]
               for key in ("input_tokens", "output_tokens"))


def _close_valid(value) -> bool:
    return value is None or (type(value) is dict and set(value) == {
        "disposition", "closed", "effect_unknown", "attempted"}
        and value["disposition"] in {"local_only", "refused", "pending", "effect_unknown", "closed"}
        and all(type(value[key]) is bool for key in ("closed", "effect_unknown", "attempted"))
        and (not value["closed"] or value["disposition"] == "closed" and not value["effect_unknown"]))


def _steps_valid(steps, operation_id) -> bool:
    if type(steps) is not list or len(steps) > 256:
        return False
    for i, step in enumerate(steps):
        if (type(step) is not dict or set(step) != {"ordinal", "state", "observation"}
                or type(step["ordinal"]) is not int or step["ordinal"] != i
                or step["state"] not in {"attempted", "complete"}):
            return False
        observation = step["observation"]
        if observation is not None and (type(observation) is not dict or set(observation) != {
                "request_id", "serving_model", "input_tokens", "output_tokens"}
                or observation["request_id"] != f"{operation_id}:brain:{i}"
                or observation["serving_model"] is not None and not _identifier(observation["serving_model"])
                or not all(_count(observation[key], nullable=True) for key in ("input_tokens", "output_tokens"))):
            return False
    return True


def _decode_state(raw: bytes) -> dict:
    if len(raw) > _CACHE_LIMIT:
        raise ValueError("translation_cache_bound")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("translation_cache_duplicate_key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique_pairs)
    # Legacy source strings can themselves be named "schema" or "operations".
    if _string_map(value):
        return {"schema": _CACHE_SCHEMA,
                "translations": {key: text for key, text in value.items() if text.strip()}, "operations": {}}
    if (type(value) is not dict or set(value) != {"schema", "translations", "operations"}
            or value["schema"] != _CACHE_SCHEMA or not _string_map(value["translations"])
            or any(not text.strip() for text in value["translations"].values())
            or type(value["operations"]) is not dict
            or len(value["operations"]) > _MAX_OPERATIONS):
        raise ValueError("translation_cache_invalid")
    claimed = set()
    for op_id, row in value["operations"].items():
        if (type(op_id) is not str or not re.fullmatch(r"mm-translate-[0-9a-f]{32}", op_id)
                or type(row) is not dict or set(row) != _RECEIPT_FIELDS):
            raise ValueError("translation_claim_invalid")
        inputs, identity = row["inputs"], row["identity"]
        if (type(inputs) is not list or not 1 <= len(inputs) <= 6
                or any(type(t) is not str or not t or t != t.strip() for t in inputs)
                or len(set(inputs)) != len(inputs) or claimed.intersection(inputs)
                or row["inputs_sha256"] != _inputs_digest(inputs)
                or not _identity_valid(identity)
                or row["state"] not in {"pending", "unknown", "terminal", "completed"}
                or not _steps_valid(row["steps"], op_id) or not _usage_valid(row["usage"])
                or not _close_valid(row["close"])
                or row["reason"] is not None and (type(row["reason"]) is not str
                    or re.fullmatch(r"[a-z_]{1,64}", row["reason"]) is None)):
            raise ValueError("translation_claim_invalid")
        if row["state"] == "pending" and (row["steps"] or any(row[key] is not None
                for key in ("usage", "close", "reason"))):
            raise ValueError("translation_pending_claim_invalid")
        if row["state"] == "completed" and any(not value["translations"].get(t) for t in inputs):
            raise ValueError("translation_result_missing")
        claimed.update(inputs)
    return value


def _read_state() -> dict:
    """Fresh mutation state; corruption or an unreadable hold never means empty."""
    try:
        with _CACHE_PATH.open("rb") as handle:
            return _decode_state(handle.read(_CACHE_LIMIT + 1))
    except FileNotFoundError:
        return {"schema": _CACHE_SCHEMA, "translations": {}, "operations": {}}


def _persist_state(state: dict) -> None:
    """Confirm the existing cache's atomic durable replacement before dispatch."""
    raw = _json_bytes(state)
    _decode_state(raw)
    parent, root = _CACHE_PATH.parent.resolve(), _ROOT.resolve()
    parent.relative_to(root)  # Only the incumbent cache tree is a write target.
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".translations-", suffix=".tmp", dir=_CACHE_PATH.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _CACHE_PATH)
        # The first fill may create data/brain (and the lock owner may just
        # have created data). Confirm every directory link through the existing
        # repository root, not only the file's immediate parent.
        while True:
            directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            if parent == root:
                break
            parent = parent.parent
        with _CACHE_PATH.open("rb") as handle:
            if handle.read(_CACHE_LIMIT + 1) != raw:
                raise ValueError("translation_cache_readback_mismatch")
    finally:
        temporary.unlink(missing_ok=True)


def _claimed_inputs(state: dict) -> set[str]:
    # Retain every original receipt. Terminal-without-answer is not a fresh miss.
    return {text for row in state["operations"].values() for text in row["inputs"]}


def _load_cache() -> dict[str, str]:
    """Load the translations cache from disk, memoized by mtime. Returns {} on any error."""
    global _cache_mem, _cache_mtime
    try:
        if _CACHE_PATH.exists():
            st = _CACHE_PATH.stat()
            mt = (st.st_mtime_ns, st.st_ino, st.st_size)
            if _cache_mem is not None and mt == _cache_mtime:
                return dict(_cache_mem)
            data = _read_state()["translations"]
            _cache_mem, _cache_mtime = data, mt
            return dict(data)
    except Exception:
        pass
    return dict(_cache_mem) if _cache_mem is not None else {}


def _save_cache(cache: dict[str, str]) -> None:
    """Compatibility merge; stale native updates cannot erase or fill a held input."""
    try:
        from control_plane.locks import acquire
        lock = acquire(_LOCK_NAME, root=_ROOT)
        if lock is None:
            return
        with lock:
            state = _read_state()
            claimed = _claimed_inputs(state)
            for text, value in cache.items():
                if (type(text) is str and type(value) is str and value.strip()
                        and text not in claimed):
                    state["translations"].setdefault(text, value)
            _persist_state(state)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cached_zh(text: str) -> str | None:
    """Return the cached Chinese translation for *text*, or None if not cached.

    NEVER calls the LLM. Safe to call in the FastAPI request path.
    """
    if not text or not text.strip():
        return None
    try:
        cache = _load_cache()
        return cache.get(text)
    except Exception:
        return None


# How many strings to send per Haiku request. One giant batch (e.g. all 30
# research notes at once) makes the model emit a ~100 KB JSON object whose
# escaping/length frequently breaks json.loads -> the WHOLE batch silently falls
# back to English. Small chunks keep each response parseable; the cache is saved
# after every chunk so partial progress survives an interruption.
_CHUNK_SIZE = 6


def _fabric_selected() -> bool:
    if "MM_PROVIDER_APPLICATION_MODE" in os.environ:
        return True
    from brain import cli_bridge
    return cli_bridge._selected_backend() == "fabric"


def _inspect_fabric():
    from brain import fabric_inference
    owner, shared, root = fabric_inference._owner()
    selected, factory = owner.configured_application_fabric(
        lane="mastermind-text", workload_profile="site_batch", root=root)
    if selected is not True or type(factory) is not owner.ApplicationFabricFactory:
        raise ValueError("translation_fabric_unavailable")
    cfg = {"provider_order": ["fabric"], "workload_profile": "site_batch"}
    identity = factory.inspect(cfg)
    if identity.get("cost_basis") != "subscription":
        raise ValueError("translation_subscription_required")
    return shared, factory.with_inspection(identity), identity, cfg


def translation_ready() -> bool:
    """Pure Fabric eligibility, or the incumbent native subscription readiness."""
    try:
        if _fabric_selected():
            _inspect_fabric()
            return True
        from brain import cli_bridge
        return cli_bridge.available()
    except Exception:
        return False


def _batch_prompt(texts: list[str]) -> str:
    index_json = json.dumps({str(i): text for i, text in enumerate(texts)}, ensure_ascii=False)
    return (
        "You are a professional financial translator. Translate each English string to fluent, "
        "natural Simplified Chinese (NOT literal word-for-word). Keep all ticker symbols "
        "(e.g. AVGO, SMH), numbers, percentages and markdown formatting (**, ##, -, |) unchanged. "
        "Output ONLY a valid JSON object mapping each input key (the number string) to its Chinese "
        "translation — no commentary, no markdown code fences.\n\n"
        f"Input:\n{index_json}"
    )


def _direct_prompt(text: str) -> str:
    return (
        "You are a professional financial translator. Translate the text below to "
        "fluent, natural Simplified Chinese (NOT literal word-for-word). Keep ALL "
        "ticker symbols (e.g. AVGO, SMH), numbers, percentages and markdown "
        "formatting (#, ##, ###, **, -, |, tables) EXACTLY as in the source. Output "
        "ONLY the Chinese translation — no preamble, no commentary, no code fences.\n\n"
        "--- TEXT TO TRANSLATE ---\n" + text
    )


def _unfence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(line for line in raw.splitlines() if not line.startswith("```")).strip()
    return raw


def _perform_fill(texts: list[str], kind: str, invoke) -> dict[str, str]:
    if kind == "batch":
        raw = _unfence(invoke(_batch_prompt(texts)))
        if not raw.startswith("{"):
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                raw = raw[start:end + 1]
        parsed = json.loads(raw)
        if type(parsed) is not dict:
            raise ValueError("translation_result_invalid")
        return {text: parsed[str(i)] for i, text in enumerate(texts)
                if type(parsed.get(str(i))) is str and parsed[str(i)].strip()}
    parts = _split_segments(texts[0]) if kind == "long" else [texts[0]]
    translated = []
    for part in parts:
        value = _unfence(invoke(_direct_prompt(part)))
        if not value:
            raise ValueError("translation_result_invalid")
        translated.append(value)
    return {texts[0]: "\n\n".join(translated)}


def _fabric_fill(state: dict, texts: list[str], kind: str) -> dict[str, str]:
    shared, factory, identity, cfg = _inspect_fabric()
    if len(state["operations"]) >= _MAX_OPERATIONS:
        return {}
    operation_id = "mm-translate-" + uuid.uuid4().hex
    if operation_id in state["operations"]:
        raise ValueError("translation_original_identity_exists")
    receipt = {"inputs": texts, "inputs_sha256": _inputs_digest(texts),
               "identity": identity, "state": "pending", "steps": [],
               "usage": None, "close": None, "reason": None}
    state["operations"][operation_id] = receipt
    # A failure here is strictly before binding/provider bytes. Never remove a
    # possibly committed claim as an error-recovery convenience.
    _persist_state(state)
    provider = operation = None
    results = {}
    effect_unknown = False
    try:
        provider = shared.build_fabric_provider(factory, request_id=operation_id, workload_cfg=cfg)
        provider.update(usage_lane="mastermind-text", usage_stage="translation", usage_cycle_id=operation_id)
        operation = shared.begin_operation([provider], operation_id=operation_id, context="translation")

        def invoke(prompt):
            before = provider.get("_fabric_step", 0)
            step = {"ordinal": len(receipt["steps"]), "state": "attempted", "observation": None}

            def call(client, model):
                response = client.messages.create(model=model, max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}])
                if (response.stop_reason != "end_turn" or not response.content
                        or any(block.type != "text" for block in response.content)):
                    raise shared.FabricProviderError("translation_complete_text_required")
                text = "".join(block.text for block in response.content)
                if not text.strip():
                    raise shared.FabricProviderError("translation_complete_text_required")
                return text, None, response

            try:
                text, reason, _ = shared.make_call(operation.providers, call, context="translation")
                if reason is not None or not isinstance(text, str) or not text.strip():
                    raise shared.FabricProviderError("translation_result_unavailable")
                step["state"] = "complete"
                return text
            finally:
                observation = provider.get("_fabric_last_observation")
                if (isinstance(observation, dict)
                        and observation.get("request_id") == f"{operation_id}:brain:{before}"):
                    step["observation"] = dict(observation)
                receipt["steps"].append(step)

        results = _perform_fill(texts, kind, invoke)
        receipt["reason"] = None if len(results) == len(texts) else "translation_result_incomplete"
    except shared.FabricProviderError as exc:
        effect_unknown = exc.effect_unknown
        receipt["reason"] = "fabric_effect_unknown" if effect_unknown else "fabric_unavailable"
    except Exception:
        effect_unknown = bool(provider and provider.get("_fabric_pending"))
        receipt["reason"] = "translation_result_unavailable"
    finally:
        if operation is not None:
            operation.close()
        elif provider is not None:
            shared.close_fabric_provider(provider)
        if provider is not None:
            receipt["usage"] = shared.fabric_usage(provider)
            close = provider.get("_fabric_close")
            receipt["close"] = dict(close) if isinstance(close, dict) else None
            effect_unknown |= bool(close and close.get("effect_unknown"))
    receipt["state"] = ("unknown" if effect_unknown else
                        "completed" if len(results) == len(texts) else "terminal")
    state["translations"].update(results)
    # A final-write failure retains the original claim in every possible
    # committed version. No path deletes it, retargets it or dispatches again.
    _persist_state(state)
    return results


def _guarded_fill(texts: list[str], kind: str) -> dict[str, str]:
    normalized = list(dict.fromkeys(t.strip() for t in texts if isinstance(t, str) and t.strip()))
    if not normalized or kind != "batch" and len(normalized) != 1 or len(normalized) > _CHUNK_SIZE:
        return {}
    result = {}
    try:
        from control_plane.locks import acquire
        lock = acquire(_LOCK_NAME, root=_ROOT)
        if lock is None:
            return {}
        with lock:
            state = _read_state()
            result = {text: state["translations"][text] for text in normalized
                      if state["translations"].get(text)}
            held = _claimed_inputs(state)
            missing = [text for text in normalized if text not in result and text not in held]
            if not missing:
                return result
            # Holds precede mutable selection; removing Fabric cannot evade an
            # earlier unknown request. The same lock also surrounds native I/O.
            if _fabric_selected():
                result.update(_fabric_fill(state, missing, kind))
            else:
                from brain import cli_bridge
                if not cli_bridge.available():
                    return result

                def before_provider_start():
                    if _fabric_selected():
                        raise ValueError("translation_selection_changed")

                def invoke(prompt):
                    before_provider_start()
                    out = cli_bridge.reason_sync(prompt, role="scout", log_run=False,
                        allowed_tools=[], add_dirs=[], before_provider_start=before_provider_start)
                    return (out.get("text") or "").strip()

                translated = _perform_fill(missing, kind, invoke)
                state["translations"].update(translated)
                _persist_state(state)
                result.update(translated)
    except Exception:
        pass  # Original holds survive; callers display the English source.
    return result


def translate_and_cache(texts: list[str]) -> dict[str, str]:
    """Warm completed strings through one selected operation per chunk/document."""
    unique = list(dict.fromkeys(t.strip() for t in texts if isinstance(t, str) and t.strip()))
    cache = _load_cache()
    result = {text: cache.get(text) or text for text in unique}
    missing = [text for text in unique if not cache.get(text)]
    short = [text for text in missing if len(text) <= _LONG_THRESHOLD]
    long_docs = [text for text in missing if len(text) > _LONG_THRESHOLD]
    for start in range(0, len(short), _CHUNK_SIZE):
        result.update(_call_haiku(short[start:start + _CHUNK_SIZE]))
    for text in long_docs:
        value = _translate_long(text)
        if value:
            result[text] = value
    return result


def _call_haiku(texts: list[str]) -> dict[str, str]:
    """Guarded short-batch entry; selected failures never enter the native bridge."""
    return _guarded_fill(texts, "batch")


_LONG_THRESHOLD = 1200
_SEGMENT_TARGET = 1000


def _call_haiku_direct(text: str) -> str | None:
    """Guarded direct entry, with the same original-input durable hold."""
    return _guarded_fill([text], "direct").get(text.strip()) if isinstance(text, str) else None


def _split_segments(text: str) -> list[str]:
    """Split markdown near the existing target, preserving paragraph boundaries."""
    segments, current, length = [], [], 0
    for paragraph in text.split("\n\n"):
        if current and length + len(paragraph) > _SEGMENT_TARGET:
            segments.append("\n\n".join(current))
            current, length = [], 0
        current.append(paragraph)
        length += len(paragraph) + 2
    if current:
        segments.append("\n\n".join(current))
    return segments


def _translate_long(text: str) -> str | None:
    """One whole-document claim and binding; publish only after every segment."""
    return _guarded_fill([text], "long").get(text.strip()) if isinstance(text, str) else None


# ---------------------------------------------------------------------------
# Warm-up helpers for the batch populate script
# ---------------------------------------------------------------------------

def translate_book(book: dict[str, Any]) -> None:
    """Gather every translatable string from a portfolio.v1 dict and warm the cache.

    Translatable strings:
    - positions[].thesis_full.{summary, why_now, sizing_rationale}
    - positions[].thesis_full.bull[]  (each item)
    - positions[].thesis_full.bear[]  (each item)
    - rejected[].reason
    - rejected[].bear[]  (each item)
    - decisions[].thesis  (each — backs the Brain Log decision events)
    - top-level disclaimer
    """
    texts: list[str] = []

    # disclaimer
    d = book.get("disclaimer")
    if d:
        texts.append(d)

    # positions
    for pos in book.get("positions", []):
        tf = pos.get("thesis_full") or {}
        for field in ("summary", "why_now", "sizing_rationale", "what_would_prove_wrong"):
            v = tf.get(field)
            if v:
                texts.append(v)
        for item in tf.get("bull", []) or []:
            if item:
                texts.append(item)
        for item in tf.get("bear", []) or []:
            if item:
                texts.append(item)

    # rejected
    for rej in book.get("rejected", []):
        r = rej.get("reason")
        if r:
            texts.append(r)
        for item in rej.get("bear", []) or []:
            if item:
                texts.append(item)

    # decision theses — these back the Brain Log (/api/activity) decision events;
    # the full thesis is cached so the zh detail can be built and sliced client-side
    for d in book.get("decisions", []):
        th = d.get("thesis")
        if th:
            texts.append(th)

    if texts:
        translate_and_cache(texts)


def translate_notes(notes_dir: str | Path) -> None:
    """Warm the cache for all research note bodies + titles found in *notes_dir*.

    The title + body strings are extracted exactly as app.web._parse_note builds
    them (title = first # heading; body = everything AFTER the title AND the
    `*tickers: … · date*` metadata line) so the cached keys match what the
    /api/research route looks up via cached_zh(). A mismatch here silently leaves
    body_md_zh None and the feed renders English.
    """
    notes_dir = Path(notes_dir)
    if not notes_dir.exists():
        return

    texts: list[str] = []
    for path in notes_dir.glob("*.md"):
        try:
            raw = path.read_text(encoding="utf-8")
            lines = raw.splitlines()
            if not lines:
                continue
            # title from the first # heading (matches _parse_note)
            title = lines[0].lstrip("# ").strip() if lines[0].startswith("#") else path.stem
            if title:
                texts.append(title)
            # find the *tickers: … · date* line; body starts after it (or after the
            # title if there is no ticker line)
            ticker_idx = None
            for i, ln in enumerate(lines[1:], 1):
                if _TICKER_LINE_RE.match(ln):
                    ticker_idx = i
                    break
            body_start = (ticker_idx + 1) if ticker_idx is not None else 1
            body = "\n".join(lines[body_start:]).strip()
            if body:
                texts.append(body)
        except Exception:
            continue

    if texts:
        translate_and_cache(texts)


def translate_papers(papers_dir: str | Path) -> None:
    """Warm the cache for every research paper's summary + full markdown report.

    These back the Research page thesis modal: /api/research_papers injects
    summary_zh and report_md_zh via cached_zh(). Each report can be ~17 KB, so we
    translate one paper at a time (its own batch) — a single oversized batched
    request is far likelier to come back as malformed JSON and fall back to English.
    """
    papers_dir = Path(papers_dir)
    if not papers_dir.exists():
        return

    for path in sorted(papers_dir.glob("*.json")):
        try:
            paper = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        batch: list[str] = []
        for field in ("summary", "report_md"):
            v = paper.get(field)
            if v and isinstance(v, str):
                batch.append(v)
        if batch:
            # one paper per call so a parse failure on a huge report can't poison
            # the other papers' translations
            translate_and_cache(batch)


def translate_decisions(limit: int = 60) -> None:
    """Warm the cache for the autonomous daily-decision log write-ups.

    These back the dashboard's Daily Decision Log: /api/decisions injects summary_zh /
    sold_note_zh / brain_text_zh and per-holding rationale_zh via cached_zh(). Without
    this warm-up the AI's decision write-up stays English even when zh is toggled.
    translate_and_cache() skips already-cached strings, so the daily call only translates
    text from new decisions. Best-effort — never raises.
    """
    try:
        from bot import autonomous
    except Exception:
        return

    texts: list[str] = []
    try:
        for d in autonomous.load_decisions(limit):
            for field in ("summary", "sold_note", "brain_text"):
                v = d.get(field)
                if v and isinstance(v, str):
                    texts.append(v)
            for h in (d.get("holdings") or []):
                r = h.get("rationale")
                if r and isinstance(r, str):
                    texts.append(r)
    except Exception:
        return

    if texts:
        translate_and_cache(texts)


def translate_runs() -> None:
    """Warm the cache for run-log titles + summaries.

    These back the dashboard's Brain Activity ("Full Trace") log: /api/runs injects
    title_zh / summary_zh via cached_zh(), so without this warm-up the AI's run write-up
    stays English even when zh is toggled. Reads the run index via brain.runlog;
    translate_and_cache() skips already-cached strings, so the daily call only translates
    text from new runs. Best-effort — never raises.
    """
    try:
        from brain import runlog
    except Exception:
        return

    texts: list[str] = []
    try:
        for r in runlog.list_runs():
            # title defaults to the run_id (a bare timestamp) when none was given — skip
            # those; they're not prose. summary is the AI's narrative write-up of the run.
            title = r.get("title")
            if title and isinstance(title, str) and title != r.get("run_id"):
                texts.append(title)
            summary = r.get("summary")
            if summary and isinstance(summary, str):
                texts.append(summary)
    except Exception:
        return

    if texts:
        translate_and_cache(texts)
