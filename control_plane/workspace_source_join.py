"""Installed source join feeding the existing Chairman Control Room refresh.

:func:`build_workspace_composer` is the trusted-parent glue named by the
frozen join contract.  It pre-acquires every canonical source input through
the real installed collectors and the service Runtime's bounded read
observation, then hands exactly those inputs to the existing pure
``compose_control_room``.  It opens no Runtime path, walks no registry
cursor, reads no C2/W3C provider, and never falls back to the legacy gather.
A failed configured composition stays failed; it is never quietly replaced.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

#: Exact installed artifact byte bound required by the frozen contract.
INSTALLED_BYTE_BUDGET = 2 * 1024 * 1024

#: Fixed owner bounds; these are stated by the contract, not discovered.
DISCOVERY_MAX_ROOTS = 64
MAX_ELIGIBLE_COMMANDS = 17
MAX_SELECTED_ROOTS = 17
ROOT_MAX_JOBS = 17
ROOT_MAX_ATTEMPTS_PER_JOB = 20
ROOT_MAX_ATTEMPTS_TOTAL = 340


def _read_installed_document(reader: Callable[..., Any], macro_root: str | None):
    """The installed acquisition requires the canonical bounded reader API."""
    return reader(macro_root, installed_byte_budget=INSTALLED_BYTE_BUDGET)


def _eligible_commands(runtime: Any, roots: Sequence[Any]) -> dict[str, str]:
    """Distinct creation-Event commands reachable by durable routing alone.

    Each job is offered to the existing ``_bounded_provenance`` validator with
    a strictly local recorder that returns ``None``.  The recorder is only
    reached after the durable orchestration-provenance validation passes, and
    because it is supplied the validator never touches ``runtime.events``.
    No Event is read and no point budget is spent here.
    """
    from control_plane.fabric_job_view import _bounded_provenance

    commands: dict[str, str] = {}
    for job in roots:
        def record(command_id: str, _job=job) -> None:
            if command_id in commands and commands[command_id] != _job.job_id:
                raise ValueError("creation command has conflicting root identities")
            commands[command_id] = _job.job_id
            return None

        _bounded_provenance(runtime, job, creation_event_reader=record)
    return commands


def _same_receipt(receipt: Any) -> bool:
    return (type(receipt) is dict
            and set(receipt) == {"schema", "state", "source_identity", "before", "after"}
            and receipt.get("schema") == "mastermind.runtime_read_observation.v1"
            and receipt.get("state") == "SAME"
            and type(receipt.get("source_identity")) is str and bool(receipt["source_identity"])
            and type(receipt.get("before")) is int and receipt["before"] >= 0
            and type(receipt.get("after")) is int and receipt["before"] == receipt["after"])


def _root_evidence(runtime: Any, root_job_id: str):
    """One bounded root observation: snapshot, provenance, finalized receipt.

    Raises when root identity, typed caps, truncation flags or the finalized
    receipt refuse the evidence.  Truncated or conflicted evidence is never
    returned and never retained as a resolved root.
    """
    from control_plane.fabric_job_view import _bounded_provenance

    with runtime.observe_bounded_read() as read:
        snapshot = read.read_job_root_bounded(root_job_id)
        jobs, attempts = list(snapshot.jobs), list(snapshot.attempts)
        if (snapshot.root_job_id != root_job_id or not jobs
                or jobs[0].job_id != root_job_id
                or len(jobs) > ROOT_MAX_JOBS
                or len(attempts) > ROOT_MAX_ATTEMPTS_TOTAL
                or bool(snapshot.jobs_truncated)
                or tuple(snapshot.attempts_truncated_job_ids)):
            raise ValueError("bounded Runtime root snapshot truncated or invalid")
        ids = {job.job_id for job in jobs}
        if len(ids) != len(jobs) or any(job.root_job_id != root_job_id for job in jobs):
            raise ValueError("bounded Runtime root snapshot membership invalid")
        per_job: dict[str, list[Any]] = {}
        for attempt in attempts:
            if attempt.job_id not in ids:
                raise ValueError("bounded Runtime Attempt membership invalid")
            per_job.setdefault(attempt.job_id, []).append(attempt)
        if any(len(rows) > ROOT_MAX_ATTEMPTS_PER_JOB for rows in per_job.values()):
            raise ValueError("bounded Runtime Attempt budget invalid")
        origins = read.classify_root_origins_bounded()
        if len(origins) != 1 or origins[0].job_id != root_job_id:
            raise ValueError("bounded root origin membership invalid")
        root_origin = origins[0]
        provenance_by_job: dict[str, Mapping[str, Any] | None] = {}
        for job in jobs:
            provenance, _warning = _bounded_provenance(
                runtime, job, creation_event_reader=read.get_creation_event_by_command_id)
            if job.job_id == root_job_id and root_origin.kind == "LEGACY_CEO":
                provenance = root_origin.provenance
            provenance_by_job[job.job_id] = provenance
    # The finalized receipt exists only after the observation context closed.
    receipt = read.receipt.to_dict()
    if not _same_receipt(receipt):
        raise ValueError("bounded Runtime root observation is not SAME")
    return jobs, attempts, provenance_by_job, receipt


def _bounded_runtime_inputs(runtime: Any) -> tuple[
        list[dict[str, Any]] | None, list[Any] | None, list[Any] | None,
        dict[str, Mapping[str, Any] | None], list[str], bool]:
    """Complete finite root mapping plus bounded Inbox slices, never global counts.

    Discovery and each root have separate finalized observation receipts. The
    root details must agree with discovery's exact root/provenance postimages.
    Every root receives bounded creation-origin classification. Only a
    positively proven non-CEO root is excluded; unsupported origins still
    invalidate the complete mapping. Legacy CEO candidates preserve ambiguity.
    No global SAME is minted.
    """
    from control_plane.fabric_job_view import _bounded_provenance

    def unavailable(reason, observed=False):
        return None, None, None, {}, ["executive_runtime: " + reason], observed
    observed = False
    try:
        with runtime.observe_bounded_read() as read:
            discovery = read.discover_job_roots_bounded()
            if (type(discovery.truncated) is not bool or discovery.truncated
                    or len(discovery.roots) > DISCOVERY_MAX_ROOTS):
                raise ValueError("root discovery truncated or invalid")
            commands = _eligible_commands(runtime, discovery.roots)
            if len(commands) > MAX_ELIGIBLE_COMMANDS:
                raise ValueError("eligible creation Event point budget exceeded")
            if len({job.job_id for job in discovery.roots}) != len(discovery.roots):
                raise ValueError("duplicate roots prevent complete mapping")
            origins = read.classify_root_origins_bounded()
            if ({origin.job_id for origin in origins} != {job.job_id for job in discovery.roots}
                    or len(origins) != len(discovery.roots)):
                raise ValueError("root origin mapping is incomplete")
            by_id = {origin.job_id: origin for origin in origins}
            selected = [origin for origin in origins if origin.kind != "NON_CEO"]
            if len(selected) > MAX_SELECTED_ROOTS:
                raise ValueError("selected root detail budget exceeded")
            roots = {}
            for job in discovery.roots:
                origin = by_id[job.job_id]
                if origin.kind == "NON_CEO":
                    if origin.provenance is not None:
                        raise ValueError("non-CEO root carries conflicting provenance")
                    continue
                if origin.kind == "STRICT_V2_CEO":
                    provenance, warning = _bounded_provenance(
                        runtime, job, creation_event_reader=read.get_creation_event_by_command_id)
                    if warning is not None or provenance != origin.provenance:
                        raise ValueError("strict root origin provenance changed")
                elif origin.kind == "LEGACY_CEO":
                    provenance = origin.provenance
                else:
                    raise ValueError("root origin unresolved")
                if (not isinstance(provenance, Mapping)
                        or not isinstance(provenance.get("workstream"), str)
                        or not provenance["workstream"]):
                    raise ValueError("root creation provenance or workstream unavailable")
                roots[job.job_id] = (job.to_dict(), dict(provenance))
        if not _same_receipt(read.receipt.to_dict()):
            raise ValueError("root discovery observation is not SAME")
        observed = True
        rows, jobs, attempts, provenance_by_job = [], [], [], {}
        for root_job_id in sorted(roots):
            root_jobs, root_attempts, root_provenance, _receipt = _root_evidence(runtime, root_job_id)
            root = root_jobs[0]
            original_job, original_provenance = roots[root_job_id]
            if root.to_dict() != original_job or root_provenance.get(root_job_id) != original_provenance:
                raise ValueError("root or creation provenance changed after discovery")
            rows.append({"job_id": root.job_id,
                         "status": getattr(root.status, "value", None) or str(root.status),
                         "workstream": original_provenance["workstream"],
                         "root_job_id": root.root_job_id})
            jobs.extend(root_jobs)
            attempts.extend(root_attempts)
            provenance_by_job.update(root_provenance)
        return rows, jobs, attempts, provenance_by_job, [], True
    except Exception as exc:
        return unavailable(f"bounded root mapping unavailable: {type(exc).__name__}: {exc}", observed)


def build_workspace_composer(
    *,
    packet_collector: Any,
    repo_root: Path | str,
    macro_root: Path | str | None,
    bounded_runtime: Callable[[], Any],
    bindings_path: Path | str | None,
    timeout: float = 240.0,
) -> Callable[..., dict[str, Any]]:
    """Return the installed ``compose_inputs`` callback for ServerConfig.

    ``packet_collector`` is the existing
    ``integrations.executive_mcp.installed.InstalledBootPacketCollector``
    supplied by the trusted parent.  ``bounded_runtime`` is a zero-argument
    closed callback returning the actual service custody readonly Runtime
    facade; it is invoked late, at composition time, never while this inert
    factory is being constructed.  A ``None`` ``bindings_path`` yields an
    explicit unavailable binding — the default HOME location is never
    expanded.  The returned callable raises on failed collection; the
    chairman seam turns that failure into explicit unavailable source inputs
    and never falls back to the legacy gather. An explicitly supplied detached
    ``active_builds_snapshot`` replaces only the active-builds artifact read;
    omission alone retains that bounded reader. An unavailable supplied value
    reaches the canonical compositor without an artifact substitution.
    """
    from control_plane import chairman_control_room as ccr
    from control_plane import executive_inbox
    from control_plane.surface_bindings import load_bindings

    repo = Path(repo_root)
    macro = None if macro_root is None else os.fspath(macro_root)

    def compose_inputs(
        generated_at: str, *, active_builds_snapshot: Any = ccr._ACTIVE_BUILDS_SNAPSHOT_OMITTED,
    ) -> dict[str, Any]:
        packet = packet_collector(
            repo_root=repo, macro_root_flag=macro, now=generated_at, timeout=timeout)
        if active_builds_snapshot is ccr._ACTIVE_BUILDS_SNAPSHOT_OMITTED:
            active_builds, builds_error = _read_installed_document(
                ccr._read_active_builds, macro)
        else:
            active_builds, builds_error = active_builds_snapshot, None
        agent_os_state, state_error = _read_installed_document(
            ccr._read_agent_os_state, macro)
        if bindings_path is None:
            bindings = None
            binding_problems: tuple[str, ...] = (
                "workspace surface bindings unavailable: no explicit installed path",)
        else:
            bindings, problems = load_bindings(Path(bindings_path))
            binding_problems = tuple(problems)

        try:
            runtime = bounded_runtime()
            (runtime_jobs, projection_jobs, projection_attempts, provenance_by_job,
             runtime_notes, observed) = _bounded_runtime_inputs(runtime)
        except Exception as exc:  # custody absent: runtime evidence stays unavailable
            runtime_jobs = projection_jobs = projection_attempts = None
            provenance_by_job = {}
            runtime_notes = [
                f"executive_runtime: custody facade unavailable: {exc.__class__.__name__}"]
            observed = False

        notes = list(runtime_notes)
        if builds_error is not None:
            notes.append(f"active_builds: {builds_error}")
        if state_error is not None:
            notes.append(f"agent_os_state: {state_error}")

        mm = packet.get("mastermind") if isinstance(packet, Mapping) else None
        mastermind_grounding = {
            "root": os.fspath(repo),
            "sha": mm.get("sha") if isinstance(mm, Mapping) else None,
            "branch": mm.get("branch") if isinstance(mm, Mapping) else None,
        }
        runtime_grounding = {"path": None, "present": True if observed else None}

        projection = executive_inbox.project_runtime_inputs(
            jobs=projection_jobs, attempts=projection_attempts, workers=None,
            provenance_by_job=provenance_by_job, completeness="bounded",
            now=executive_inbox.parse_now(generated_at))
        inbox = executive_inbox.compose_inbox(
            runtime_projection=projection, boot_packet=packet,
            mastermind_grounding=mastermind_grounding,
            runtime_grounding=runtime_grounding,
            generated_at=generated_at, degraded=tuple(notes))
        return ccr.compose_control_room(
            inbox=inbox, boot_packet=packet, active_builds=active_builds,
            agent_os_state=agent_os_state, runtime_jobs=runtime_jobs,
            bindings=bindings, binding_problems=binding_problems,
            generated_at=generated_at)

    return compose_inputs
