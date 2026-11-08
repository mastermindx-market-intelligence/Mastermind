#!/usr/bin/env python3
"""Sealed transform for the manual-only Experiential Labs native picker route.

Child ``explabs-manual-20261103-picker01`` under ``explabs-manual-20261103-root``.
Pure source transform and route contract: nothing here publishes, installs,
selects, launches, leases, spends, or reads credentials.

Target route (exact, case-sensitive model): ``pool=experiential`` and
``model=glm-5.3-uncensored``, manual-only with opt-in. The route is additive
to the sealed incumbent picker and composes with the reviewed Cursor 4.6
overlay (PR #2029) in either application order; automatic routing, pool
promotion, publication, quota, model, registry and ledger authorities are
unchanged and untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Sealed native generations and their exact ``ext/pick.py`` preimages, as
# recorded by the reviewed incumbent qualification (PR #2029). The current
# generation's preimage is byte-identical to the protected in-repo candidate
# snapshot below, so the transform is provable without host access.
SEALED_PREDECESSORS = {
    "9eec6f73903fabfdd6d15bfe6f815f652f0946b5838cef6d40e96ca5b7e7f185":
        "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b",
    "8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a":
        "747a55a50fb1ae579d18ae4decc6e3b077eb4b927a3968b61abaeeeb6292f132",
}
CURRENT_GENERATION = "8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a"

REPO_ROOT = Path(__file__).resolve().parents[3]
PICK = "ext/pick.py"

# Repo snapshot pickers with their sealed digests. ``candidate`` is the exact
# sealed current-generation picker preimage; ``source`` and ``overlay`` are
# the protected lineage fixtures (source digest sealed by
# quota_continuity/rollout/native-preimages.json).
SNAPSHOT_PICKER_SEALS = {
    "candidate": (
        Path("ops/native_fabric/quota_continuity/candidate/pick.py"),
        "747a55a50fb1ae579d18ae4decc6e3b077eb4b927a3968b61abaeeeb6292f132",
    ),
    "source": (
        Path("ops/native_fabric/quota_continuity/source/pick.py"),
        "0f5cbc32504680e09055b77cffdea81adea734388b7b061fcf77d017b7715cb2",
    ),
    "overlay": (
        Path("ops/native_fabric/grok47/overlay/pick.py"),
        "02afff09760a98d593f6bb25c4e6a41e2d7bd4d450d0c668b63c5d4aedf8e0e6",
    ),
}

_EXPERIENTIAL_BLOCK = '''import stat  # experiential manual route: bounded nofollow reads
# --- Experiential Labs manual-only route (explabs-manual-20261103-picker01) ---
# pool=experiential + model=glm-5.3-uncensored is admitted only when the
# caller pins both exactly (the model spelling is case-sensitive) and the
# owner-verified witness file beside pools.yaml currently proves entitlement,
# local gateway health, admitted transport, an authenticated account cap and
# the platform-funded retention/sensitive-data/code consents. The route is
# never scored implicitly: no AUTO path, no failover target, no default
# model, and never a substitution with any Z.AI glm or glm-5.3-flash model.
_EXPERIENTIAL_POOL = "experiential"
_EXPERIENTIAL_MODEL = "glm-5.3-uncensored"
_EXPERIENTIAL_WITNESS_SCHEMA = "mastermind.experiential.manual_route_witnesses.v1"
_EXPERIENTIAL_CONSENT_FIELDS = (
    "retention_opt_in", "sensitive_data_opt_in",
    "proprietary_code_opt_in", "code_exposure_opt_in",
)
_EXPERIENTIAL_ALLOWED_CLASSES = frozenset(("mechanical", "fix_build"))


def _experiential_witnesses():
    """Read owner-verified Experiential route witnesses; fail closed.

    Only the native owner writes this file; callers can never assert
    entitlement, gateway health, transport admission, an authenticated
    account cap or funding consent. Anything unreadable, unknown, stale or
    partially proven returns None so the route stays closed.
    """
    target = os.path.join(HERE, "..", "orch", "fabric",
                          "experiential_witnesses.json")
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 65536:
                return None
            raw = b""
            while len(raw) < info.st_size:
                part = os.read(descriptor, info.st_size - len(raw))
                if not part:
                    return None
                raw += part
        finally:
            os.close(descriptor)
        witness = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(witness, dict):
        return None
    if witness.get("schema") != _EXPERIENTIAL_WITNESS_SCHEMA:
        return None
    if witness.get("pool") != _EXPERIENTIAL_POOL:
        return None
    if witness.get("model") != _EXPERIENTIAL_MODEL:
        return None
    for field in ("entitlement_verified_by_owner", "local_gateway_healthy",
                  "transport_admitted", "cap_authenticated",
                  "provider_retains_data_disclosed", "platform_funded_only"):
        if witness.get(field) is not True:
            return None
    consent = witness.get("consent")
    if not isinstance(consent, dict):
        return None
    for name in _EXPERIENTIAL_CONSENT_FIELDS:
        if consent.get(name) is not True:
            return None
    ttl = witness.get("witness_ttl_minutes")
    if type(ttl) not in (int, float) or not 0 < float(ttl) <= 1440:
        return None
    stamped = witness.get("witnessed_at")
    if not isinstance(stamped, str):
        return None
    try:
        moment = datetime.fromisoformat(stamped.replace("Z", "+00:00"))
    except Exception:
        return None
    if moment.tzinfo is None:
        return None
    age = (datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds()
    if not 0 <= age <= float(ttl) * 60.0:
        return None
    return witness


def _experiential_manual_affinity(task_class: str, doc=None):
    """Manual-only admission decision for the exact pinned Experiential route.

    Automatic routing can never reach this decision: there is no scoring
    entry, no failover target, no default model and no cross-provider
    substitution. Witnesses are re-read on every call so a request-time
    strict recheck observes the same freshness the preview reported.
    """
    if str(task_class or "").strip().lower() not in _EXPERIENTIAL_ALLOWED_CLASSES:
        return False, "experiential manual route only admits mechanical/fix_build"
    if _experiential_witnesses() is None:
        return False, "experiential owner witnesses unavailable or stale"
    return True, "experiential_manual_witnessed"


'''

# Reviewed additive hunks over the sealed incumbent picker. Every hunk must
# occur exactly once in each declared snapshot and its replacement must not
# occur beforehand; order within the list is not significant (regions are
# disjoint) and either composition order with the reviewed Cursor 4.6
# overlay is supported because no anchor overlaps that transform.
HUNKS = (
    ("family_fold_strict_subject", ("candidate", "source", "overlay"),
     '    for fam in _POOL_FAMILIES:\n'
     '        if stem == fam or stem.startswith(fam + "-"):\n'
     '            return fam\n'
     '    return raw\n',
     '    # The Experiential Labs route serves a Z.AI GLM-family model behind\n'
     '    # a distinct program slug. Reviewer-independence law (R33) must\n'
     '    # still treat it as glm family: an uncensored GLM derivative is not\n'
     '    # an independent reviewer of GLM-authored work.\n'
     '    if stem == "experiential":\n'
     '        return "glm"\n'
     '    for fam in _POOL_FAMILIES:\n'
     '        if stem == fam or stem.startswith(fam + "-"):\n'
     '            return fam\n'
     '    return raw\n'),
    ("manual_route_helpers", ("candidate", "source", "overlay"),
     'def _subject_ok(pool: str, task_class: str, subject_pool: Optional[str],\n'
     '                doc: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:\n'
     '    """R33 reviewer-not-author for review/audit/verify picks."""\n',
     _EXPERIENTIAL_BLOCK +
     'def _subject_ok(pool: str, task_class: str, subject_pool: Optional[str],\n'
     '                doc: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:\n'
     '    """R33 reviewer-not-author for review/audit/verify picks."""\n'),
    ("policy_implicit_promotion_guard", ("candidate", "source", "overlay"),
     '    tc = task_class.lower()\n'
     '    p = canonical_pool(pool) or pool\n',
     '    tc = task_class.lower()\n'
     '    p = canonical_pool(pool) or pool\n'
     '    if p == "experiential" and model != _EXPERIENTIAL_MODEL:\n'
     '        # Manual-only route: implicit scoring, escalation ladders and\n'
     '        # any unpinned or differently spelled request are never\n'
     '        # admitted. The exact case-sensitive pin still requires owner\n'
     '        # witnesses and every downstream gate; this only closes implicit\n'
     '        # promotion.\n'
     '        return False, "experiential manual route requires exact glm-5.3-uncensored pin"\n'),
    ("explicit_pin_intercept", ("candidate", "overlay"),
     '    if explicit_model and not native_alias and not grok_pin:\n',
     '    experiential_pin = requested_model == _EXPERIENTIAL_MODEL\n'
     '    if forced == _EXPERIENTIAL_POOL and not experiential_pin:\n'
     '        # The pool itself is manual-only: no default model, no unscoped\n'
     '        # and no case-folded spelling. Exact identity or nothing.\n'
     '        return "NONE reason=experiential pool requires exact glm-5.3-uncensored pin"\n'
     '    if experiential_pin:\n'
     '        if forced != _EXPERIENTIAL_POOL:\n'
     '            return "NONE reason=exact experiential model requires experiential pool"\n'
     '        ok, reason = _experiential_manual_affinity(tc, doc)\n'
     '        if not ok:\n'
     '            return f"NONE reason={reason}"\n'
     '        # Qualified against the sealed current-generation picker. Owner\n'
     '        # witnesses prove availability, never admission: pool policy,\n'
     '        # capability, subject, quality-floor, quota and economic gates\n'
     '        # below all stay binding.\n'
     '    if explicit_model and not native_alias and not grok_pin:\n'),
    ("selection_pinned_identity", ("candidate", "overlay"),
     '    pinned = ((pool == "grok" and model in ("grok-4.6", "grok-4.7"))\n'
     '              or (pool == "cursor" and model == "cursor-grok-4.6-high"))\n',
     '    pinned = ((pool == "grok" and model in ("grok-4.6", "grok-4.7"))\n'
     '              or (pool == "cursor" and model == "cursor-grok-4.6-high")\n'
     '              or (pool == _EXPERIENTIAL_POOL and model == _EXPERIENTIAL_MODEL))\n'),
    ("selection_model_pin_param", ("candidate", "overlay"),
     '        selected_model = (explicit_model or None) if forced in ("glm", "grok") or native_alias else None\n',
     '        selected_model = ((explicit_model or None)\n'
     '                          if forced in ("glm", "grok") or native_alias\n'
     '                          or experiential_pin else None)\n'),
    ("auto_execute_loop_guard", ("candidate", "source", "overlay"),
     '    for token in order:\n'
     '        p = ROUTING_TOKEN_POOLS.get(token, token)\n'
     '        if p == "grok":\n',
     '    for token in order:\n'
     '        p = ROUTING_TOKEN_POOLS.get(token, token)\n'
     '        if p == _EXPERIENTIAL_POOL:\n'
     '            # Manual-only route: never scored implicitly (no pool\n'
     '            # promotion).\n'
     '            continue\n'
     '        if p == "grok":\n'),
    ("auto_scored_loop_guard", ("candidate", "source", "overlay"),
     '        for token in order:\n'
     '            p = ROUTING_TOKEN_POOLS.get(token, token)\n'
     '            if p == "grok":\n',
     '        for token in order:\n'
     '            p = ROUTING_TOKEN_POOLS.get(token, token)\n'
     '            if p == _EXPERIENTIAL_POOL:\n'
     '                # Manual-only route: never scored implicitly.\n'
     '                continue\n'
     '            if p == "grok":\n'),
    ("launch_economic_guard", ("candidate", "source", "overlay"),
     '    if normalized_mode not in {"grok", "cursor", "glm", "glm-codex",\n'
     '                               "go", "go-codex", "qwen", "bailian", "codex-native", "claude-native", "oc-free"}:\n'
     '        return result\n',
     '    if normalized_mode == _EXPERIENTIAL_POOL:\n'
     '        # The manual-only Experiential route is never outside the\n'
     '        # economic guard: only the exact pinned model with current owner\n'
     '        # witnesses passes; every other model on this mode is refused.\n'
     '        if requested_model != _EXPERIENTIAL_MODEL:\n'
     '            result.update(allowed=False,\n'
     '                          reason="experiential_route_requires_exact_pin",\n'
     '                          tier="unknown")\n'
     '            return result\n'
     '        if _experiential_witnesses() is None:\n'
     '            result.update(\n'
     '                allowed=False,\n'
     '                reason="experiential_owner_witnesses_unavailable",\n'
     '                tier=model_tier.CLASS_TIER.get(normalized_task, "unknown"))\n'
     '            return result\n'
     '        result["reason"] = "experiential_manual_witnessed"\n'
     '        result["tier"] = model_tier.CLASS_TIER.get(normalized_task, "unknown")\n'
     '        return result\n'
     '    if normalized_mode not in {"grok", "cursor", "glm", "glm-codex",\n'
     '                               "go", "go-codex", "qwen", "bailian", "codex-native", "claude-native", "oc-free"}:\n'
     '        return result\n'),
)

# Witness contract consumed by the overlaid native picker. Owner-written
# state beside pools.yaml under the existing root-bound orch directory; no
# manifest, binding or authority change. Caller flags can never assert the
# owner-verified fields.
WITNESS_SCHEMA = "mastermind.experiential.manual_route_witnesses.v1"
WITNESS_FILE = "orch/fabric/experiential_witnesses.json"
WITNESS_OWNER_FIELDS = (
    "entitlement_verified_by_owner", "local_gateway_healthy",
    "transport_admitted", "cap_authenticated",
    "provider_retains_data_disclosed", "platform_funded_only",
)
WITNESS_CONSENT_FIELDS = (
    "retention_opt_in",          # --experiential-retention-acknowledged
    "sensitive_data_opt_in",     # --experiential-sensitive-data-opt-in
    "proprietary_code_opt_in",   # --experiential-proprietary-code
    "code_exposure_opt_in",      # --experiential-code-exposure-opt-in
)
WITNESS_TTL_MINUTES = (0, 1440)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot_picker(name: str) -> bytes:
    path, seal = SNAPSHOT_PICKER_SEALS[name]
    raw = (REPO_ROOT / path).read_bytes()
    if sha(raw) != seal:
        raise ValueError("snapshot_picker_seal_drift:" + str(path))
    return raw


def apply_reviewed_hunks(raw: bytes, snapshots: tuple[str, ...] = ("candidate",)) -> bytes:
    """Pure exact-once source transform. No file is mutated in place."""
    text = raw.decode("utf-8")
    for name, targets, old, new in HUNKS:
        if not any(target in snapshots for target in targets):
            continue
        if text.count(old) != 1 or text.count(new) != 0:
            raise ValueError("reviewed_selector_hunk_identity_mismatch:" + name)
        text = text.replace(old, new, 1)
    import ast

    ast.parse(text, filename="qualified-native-experiential-pick.py")
    output = text.encode("utf-8")
    if output == raw:
        raise ValueError("no_candidate_change")
    return output


def patched(raw: bytes, predecessor: str) -> bytes:
    expected = SEALED_PREDECESSORS.get(predecessor)
    if expected is None or sha(raw) != expected:
        raise ValueError("sealed_picker_preimage_changed")
    return apply_reviewed_hunks(raw)


def overlay_witness_fingerprint(witness: dict) -> str:
    """Stable digest of the exact witness document a recheck must observe."""
    canonical = json.dumps(witness, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    return sha(canonical)


def validate_witness_document(witness: dict, *, now_epoch: float | None = None) -> str | None:
    """Repo-side mirror of the overlaid picker's witness gate.

    Returns None when the document fails closed, else the reason the gate
    admits. Used by tests to build fixtures and by the qualification runner
    to lint a draft witness document without touching any host.
    """
    import datetime as _dt

    if not isinstance(witness, dict):
        return None
    if witness.get("schema") != WITNESS_SCHEMA:
        return None
    if witness.get("pool") != "experiential":
        return None
    if witness.get("model") != "glm-5.3-uncensored":
        return None
    for field in WITNESS_OWNER_FIELDS:
        if witness.get(field) is not True:
            return None
    consent = witness.get("consent")
    if not isinstance(consent, dict):
        return None
    for name in WITNESS_CONSENT_FIELDS:
        if consent.get(name) is not True:
            return None
    ttl = witness.get("witness_ttl_minutes")
    if type(ttl) not in (int, float) or not 0 < float(ttl) <= 1440:
        return None
    stamped = witness.get("witnessed_at")
    if not isinstance(stamped, str):
        return None
    try:
        moment = _dt.datetime.fromisoformat(stamped.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    if now_epoch is None:
        now_epoch = _dt.datetime.now(_dt.timezone.utc).timestamp()
    if not 0 <= now_epoch - moment.timestamp() <= float(ttl) * 60.0:
        return None
    return "experiential_manual_witnessed"
