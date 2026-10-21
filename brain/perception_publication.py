"""Publish the existing risk contracts from one immutable, market-wide capture.

The existing macro-refresh job is the sole lifecycle owner. This module never
pulls a repository, runs a portfolio, computes a model, or reads book state.
Market View latest is the only commit point; immutable companion copies stay in
the existing two artifact directories. A failed or incomplete capture preserves
the last complete publication.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any

from brain import market_view as mv
from brain import decision_context as dc

_ROOT = Path(__file__).resolve().parent.parent
_MACRO_ROOT = _ROOT / "vendor" / "macro"
_DOCTRINE_PATH = _ROOT / "config" / "doctrine.yml"
_SOURCE_PATHS = {
    "regime": ("data/regime/latest.json", True),
    "cycles": ("site/sectordata/sector_cycles.json", True),
    "rrg": ("site/marketdata/subsector_rotation.json", False),
    "group_flow": ("site/basketdata/flow.json", False),
}
_EXCLUDED = (
    "distribution_tells", "regime_nowcast", "rotation_tensor",
    "anticipation", "neural_web", "liquidity_transmission", "budget_ref",
)
_CONTRACT = "market_wide_perception.v1"
_MAX_SOURCE_BYTES = 16 * 1024 * 1024


class PublicationRefused(ValueError):
    """The existing complete publication remains authoritative."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clock(now: datetime | None) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise PublicationRefused("assessment_clock_naive")
    return value.astimezone(timezone.utc)


def _capture_clock(value: Any, *, checked_at: datetime) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError("capture clock must be an ISO timestamp")
        clock = _clock(datetime.fromisoformat(value))
        if clock > checked_at:
            raise ValueError("capture follows assessment")
        return clock
    except (TypeError, ValueError) as exc:
        raise PublicationRefused("capture_clock_invalid") from exc


def _stable_evidence(value: Any) -> Any:
    """Publication/transport clocks are not a new source observation.

    Own market dates, source health, known-at evidence and corrections remain.
    A required-voter check separately prevents an advisory/metadata change from
    legitimizing a positive consensus formed by evidence erosion.
    """
    if isinstance(value, dict):
        return {k: _stable_evidence(v) for k, v in value.items()
                if k not in {"built_at", "generated_at", "updated_at", "captured_at", "checked_at"}}
    if isinstance(value, list):
        return [_stable_evidence(v) for v in value]
    return value


def _source_identity(sources: dict[str, Any]) -> str:
    return _sha(_json_bytes({
        "contract": _CONTRACT,
        "sources": _stable_evidence(sources),
        "excluded": list(_EXCLUDED),
    }))


def _git(repo: Path, *args: str) -> bytes:
    # Read-only Git object operations; no fetch/reset/status, credentials or hooks.
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
         "-c", "safe.directory=" + str(repo), "-C", str(repo), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False,
    )
    if result.returncode:
        raise PublicationRefused("upstream_git_read_failed")
    return result.stdout


def capture_sources(*, now: datetime | None = None) -> dict[str, Any]:
    """Capture the declared source set at one Git revision, without refreshing it.

    Working bytes must equal the captured commit, including absence. This rejects
    partial checkout, uncommitted replacement and upstream movement. Optional
    advisory contracts may be absent; required regime/cycles may not.
    """
    checked_at = _clock(now)
    repo = _MACRO_ROOT.resolve(strict=True)
    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise PublicationRefused("upstream_revision_invalid")
    sources: dict[str, Any] = {}
    manifest: dict[str, Any] = {}
    for name, (relative, required) in _SOURCE_PATHS.items():
        tree = _git(repo, "ls-tree", head, "--", relative).decode().strip()
        path = repo / relative
        if not tree:
            if required or path.exists():
                raise PublicationRefused("source_missing_or_untracked:" + name)
            sources[name] = None
            manifest[name] = {"path": relative, "status": "absent", "required": False}
            continue
        fields = tree.split()
        if len(fields) < 4 or fields[0] not in {"100644", "100755"} or fields[1] != "blob":
            raise PublicationRefused("source_not_regular_blob:" + name)
        blob = fields[2]
        size = int(_git(repo, "cat-file", "-s", blob))
        if size <= 0 or size > _MAX_SOURCE_BYTES or path.is_symlink():
            raise PublicationRefused("source_size_or_link_invalid:" + name)
        payload = _git(repo, "cat-file", "blob", blob)
        if path.read_bytes() != payload:
            raise PublicationRefused("working_source_not_at_revision:" + name)
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise PublicationRefused("source_not_object:" + name)
        _json_bytes(value)  # rejects non-finite numeric payloads
        sources[name] = value
        manifest[name] = {
            "path": relative, "status": "present", "required": required,
            "git_blob": blob, "sha256": _sha(payload), "bytes": len(payload),
        }
    if _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip() != head:
        raise PublicationRefused("upstream_revision_changed_during_capture")
    # Verify selected live files again; immutable objects above remain the inputs.
    for name, row in manifest.items():
        path = repo / row["path"]
        if row["status"] == "absent":
            if path.exists():
                raise PublicationRefused("source_appeared_during_capture:" + name)
        elif path.is_symlink() or _sha(path.read_bytes()) != row["sha256"]:
            raise PublicationRefused("source_changed_during_capture:" + name)
    return {
        "contract": _CONTRACT, "source_revision": head,
        "captured_at": checked_at.isoformat(), "sources": sources,
        "source_manifest": manifest, "source_identity": _source_identity(sources),
        "excluded": list(_EXCLUDED),
    }


def _read_previous() -> tuple[dict[str, Any] | None, bytes | None]:
    if not mv._LATEST_PATH.exists():
        return None, None
    payload = mv._LATEST_PATH.read_bytes()
    previous = json.loads(payload)
    if (not isinstance(previous, dict) or previous.get("schema_version") != "market_view.v1"
            or previous.get("region") != "us" or type(previous.get("seq")) is not int
            or previous["seq"] < 0):
        raise PublicationRefused("previous_publication_invalid")
    return previous, payload


def _immutable_write(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.is_symlink():
            raise PublicationRefused("immutable_publication_collision")
        with path.open("rb") as handle:
            if handle.read() != payload:
                raise PublicationRefused("immutable_publication_collision")
            # Complete visible bytes may be an orphan from a failed file sync.
            os.fsync(handle.fileno())
    if path.read_bytes() != payload:
        raise PublicationRefused("immutable_publication_readback_failed")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_durable_directory(path: Path) -> None:
    """Persist every ancestor link before publishing an object beneath it.

    Existing links are synchronized too: they may have been created during an
    interrupted preparation, or concurrently before its durability reply.
    """
    path.mkdir(parents=True, exist_ok=True)
    for parent in reversed(path.parents):
        _sync_directory(parent)


def _atomic_replace(path: Path, payload: bytes) -> None:
    """Commit one complete file. The caller distinguishes pre/post-commit failure."""
    fd, name = tempfile.mkstemp(prefix=".perception-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish_capture(capture: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Publish an already captured source set; called only by the existing owner.

    No date-only history is overwritten. Orphan immutable copies from an
    interrupted preparation are never selected by readers or by sequence scans.
    """
    checked_at = _clock(now)
    sources = capture.get("sources")
    if (capture.get("contract") != _CONTRACT or not isinstance(sources, dict)
            or set(sources) != set(_SOURCE_PATHS)
            or capture.get("source_identity") != _source_identity(sources)
            or capture.get("excluded") != list(_EXCLUDED)):
        raise PublicationRefused("captured_source_contract_invalid")
    captured_clock = _capture_clock(capture.get("captured_at"), checked_at=checked_at)
    _ensure_durable_directory(mv._ARTIFACT_DIR)
    _ensure_durable_directory(dc._ARTIFACT_DIR)
    with (mv._ARTIFACT_DIR / ".publication.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous, previous_bytes = _read_previous()
        seq = (previous["seq"] if previous is not None else 0) + 1
        doctrine_before = _DOCTRINE_PATH.read_bytes()
        view = mv.captured_view(copy.deepcopy(sources), now=checked_at,
                                prev_view=previous, seq=seq)
        if _DOCTRINE_PATH.read_bytes() != doctrine_before:
            raise PublicationRefused("doctrine_changed_during_assembly")
        if mv._freshness(view.get("asof"), now=checked_at)["stale"]:
            raise PublicationRefused("regime_market_date_ineligible")
        for name in ("risk_radar", "mtf_signals", "cycles"):
            row = view["planes"][name]
            if (row.get("status") != "validated" or row.get("direction") not in
                    {"risk_on", "risk_off", "neutral"}
                    or (row.get("freshness") or {}).get("stale") is not False
                    or (row.get("raw") or {}).get("present") is False):
                raise PublicationRefused("required_voter_ineligible:" + name)
        if view["net_posture_tilt"]["n_validated"] != 3:
            raise PublicationRefused("required_voter_set_incomplete")
        previous_meta = (previous or {}).get("publication") or {}
        previous_clock = None
        if previous_meta.get("contract") == _CONTRACT:
            previous_clock = _capture_clock(previous_meta.get("captured_at"), checked_at=checked_at)
        if previous_meta.get("source_identity") == capture["source_identity"]:
            previous_typed = dc.for_publication(previous)
            if (previous_meta.get("contract") != _CONTRACT or not previous_typed
                    or not dc.governor_membership_consistent(previous_typed)):
                raise PublicationRefused("existing_committed_pair_invalid")
            _sync_directory(dc._ARTIFACT_DIR)
            _sync_directory(mv._ARTIFACT_DIR)
            return {"status": "unchanged", "seq": previous["seq"],
                    "publication_id": previous_meta.get("publication_id")}
        if previous_clock is not None and captured_clock <= previous_clock:
            raise PublicationRefused("capture_precedes_committed_observation")
        identity = _sha(_json_bytes({
            "contract": _CONTRACT, "source_identity": capture["source_identity"],
            "seq": seq, "built_at": view["built_at"],
        }))
        common = {
            "contract": _CONTRACT, "publication_id": identity,
            "source_identity": capture["source_identity"],
            "source_revision": capture.get("source_revision"),
            "captured_at": capture.get("captured_at"),
            "prepared_at": checked_at.isoformat(),
            "source_manifest": copy.deepcopy(capture.get("source_manifest") or {}),
            "excluded": list(_EXCLUDED), "doctrine_sha256": _sha(doctrine_before),
            "previous_publication_id": previous_meta.get("publication_id"),
            "authority_note": (
                "Market-wide descriptive publication; no book-specific distribution, "
                "new cohort, numerical policy, recovery release or portfolio execution."
            ),
        }
        # Derive the typed companion from the exact canonical view ordering that
        # readers will load. Sorting JSON keys must not change signal-list order
        # between preparation and the strict stored-pair equivalence check.
        view = json.loads(_json_bytes(view))
        typed = dc.assemble(sources["regime"], view, neural_web={}, region="us",
                            seq=seq, built_at=view["built_at"])
        if not dc.governor_membership_consistent(typed):
            raise PublicationRefused("typed_governor_membership_inconsistent")
        typed["publication"] = copy.deepcopy(common)
        typed_bytes = _json_bytes(typed)
        typed_hash = _sha(typed_bytes)
        typed_name = f"{seq:012d}-{typed_hash}.json"
        view["publication"] = {
            **common, "decision_context": {"file": typed_name, "sha256": typed_hash},
        }
        view_bytes = _json_bytes(view)
        view_hash = _sha(view_bytes)
        view_name = f"{seq:012d}-{view_hash}.json"
        _immutable_write(dc._ARTIFACT_DIR / typed_name, typed_bytes)
        _immutable_write(mv._ARTIFACT_DIR / view_name, view_bytes)
        if not dc.for_publication(view):
            raise PublicationRefused("prepared_pair_readback_failed")
        # Referenced immutable entries must be durable before the commit point.
        _sync_directory(dc._ARTIFACT_DIR)
        _sync_directory(mv._ARTIFACT_DIR)
        current_bytes = mv._LATEST_PATH.read_bytes() if mv._LATEST_PATH.is_file() else None
        if current_bytes != previous_bytes:
            raise PublicationRefused("publication_changed_before_commit")
        # Only this rename commits the new current generation. A lost readback or
        # durability acknowledgement after possible mutation is never NO_EFFECT.
        try:
            _atomic_replace(mv._LATEST_PATH, view_bytes)
            if mv._LATEST_PATH.read_bytes() != view_bytes or not dc.for_publication(view):
                raise OSError("committed pair readback failed")
            _sync_directory(mv._ARTIFACT_DIR)
        except Exception as exc:
            try:
                observed = mv._LATEST_PATH.read_bytes() if mv._LATEST_PATH.is_file() else None
            except OSError:
                observed = object()
            if observed == previous_bytes:
                raise PublicationRefused("commit_failed_before_publication") from exc
            return {"status": "effect_unknown", "seq": seq,
                    "reason": "commit_reply_or_durability_unverified",
                    "publication_id": identity}
        # Compatibility only. All current typed consumers follow the committed reference.
        compatibility = "written"
        try:
            _atomic_replace(dc._LATEST_PATH, typed_bytes)
        except Exception:
            compatibility = "failed"
        return {"status": "published", "seq": seq, "publication_id": identity,
                "artifact_sha256": view_hash, "compatibility_copy": compatibility}


def publish_after_refresh(info: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Distinguish owned refresh failure from external freshness-only operation."""
    if not isinstance(info, dict) or info.get("refresh_mode") not in {"owned", "external"}:
        return {"status": "refused", "reason": "refresh_ownership_unknown"}
    if info["refresh_mode"] == "owned" and (
            info.get("refresh_succeeded") is not True
            or not isinstance(info.get("refreshed_to"), str) or not info["refreshed_to"]):
        return {"status": "refused", "reason": "owned_refresh_failed"}
    try:
        clock = _clock(now)
        capture = capture_sources(now=clock)
        return publish_capture(capture, now=clock)
    except Exception as exc:
        return {"status": "refused",
                "reason": str(exc) if isinstance(exc, PublicationRefused)
                else "capture_or_publication_failed:" + type(exc).__name__}
