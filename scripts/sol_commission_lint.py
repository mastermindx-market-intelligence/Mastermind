"""Deterministic Continuation Delta commission linter.

Validates a Sol commission manifest (``mastermind.sol_commission.v1``) against
the replay-prevention invariants of docs/sol_skills/CONTINUATION_DELTA_CONTRACT.md:
completed/superseded/rejected work must never re-enter executable scope, open
work must never go dark, revalidation requires a named invalidating event, and
binding ``do_not_redo`` state must be reconciled — never silently dropped.

Boundaries (constitutional — do not "improve" these away):
- The tool validates a DERIVATION ARTIFACT only. It authorizes nothing,
  dispatches nothing, and owns no lifecycle, queue, or completion ledger.
- Zero network. Inputs are the manifest file and an optional local Agent OS
  context bundle; nothing else is read.
- Deterministic: identical inputs produce byte-identical reports.
- Executable surface is ONLY ``execution.ordered`` / ``execution.parallel``.
  Everything else in a commission document is evidence/context; treating
  descriptive history as executable would recreate the incident in reverse
  (over-hardening — see contract §Case K).
- Semantic completeness cannot be proven here: the linter checks the author's
  DECLARED reconciliation, and (with a bundle) exact-statement coverage.
  Renaming/laundering an obligation ID is a documented blind spot owned by
  DNR reconciliation plus Skillpack pressure testing.

Usage:
    python3 scripts/sol_commission_lint.py path/to/handoff.md
    python3 scripts/sol_commission_lint.py path/to/handoff.md \
        --agentos-context path/to/context_bundle.json [--json]

Exit codes: 0 = no hard findings; 1 = hard findings; 2 = unusable invocation.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

import yaml

SCHEMA = "mastermind.sol_commission.v1"
MODES = ("NEW_WAVE", "CONTINUATION_DELTA")

DISPOSITIONS = (
    "DONE",
    "OPEN",
    "NEW",
    "BLOCKED",
    "SUPERSEDED",
    "REJECTED",
    "REVALIDATE_REQUIRED",
)
EXEC_ELIGIBLE = {"OPEN", "NEW", "REVALIDATE_REQUIRED"}
NEVER_EXECUTABLE = {"DONE", "SUPERSEDED", "REJECTED"}
HELD_ALWAYS = {"BLOCKED"}
DNR_DISPOSITIONS = ("HONORED", "REFUTED")

REOPEN_FINDING_BY_DISPOSITION = {
    "DONE": "HANDOFF_REPLAY_COLLISION",
    "SUPERSEDED": "SUPERSEDED_WORK_REOPENED",
    "REJECTED": "REJECTED_WORK_REOPENED",
}

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_OBSERVED_SHA = re.compile(r"^(blob:)?[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
# Exact deferred_to token grammar: WS: followed by a non-empty UPPER-KEBAB key.
# Grammar + non-self are the whole deterministic floor; true existence and
# independence of the named workstream are owned by Agent OS reconciliation
# plus behavioral pressure testing (see contract §Known deterministic blind spots).
_WS_TOKEN = re.compile(r"^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$")

HARD = "hard"
WARNING = "warning"


@dataclasses.dataclass(frozen=True)
class Finding:
    name: str
    severity: str
    detail: str


class _Lint:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def hard(self, name: str, detail: str) -> None:
        self.findings.append(Finding(name, HARD, detail))

    def warn(self, name: str, detail: str) -> None:
        self.findings.append(Finding(name, WARNING, detail))


def _normalize_statement(text: str) -> str:
    """Coverage matching is exact after normalization: casefold + collapsed
    whitespace + stripped leading/trailing space and trailing periods. Nothing
    fuzzier — fuzzy matching would fake semantic completeness."""
    collapsed = re.sub(r"\s+", " ", str(text)).strip()
    return collapsed.rstrip(".").casefold()


def _extract_manifest_text(path: Path) -> str | None:
    """A .yml/.yaml file is the manifest whole; in a .md commission document
    the manifest is the first fenced ```yaml block whose mapping carries the
    commission schema id."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yml", ".yaml"}:
        return text
    blocks: list[str] = []
    buf: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if buf is None and stripped.startswith("```yaml"):
            buf = []
            continue
        if buf is not None and stripped.startswith("```"):
            blocks.append("\n".join(buf))
            buf = None
            continue
        if buf is not None:
            buf.append(line)
    for block in blocks:
        if "mastermind.sol_commission.v1" in block:
            return block
    return blocks[0] if blocks else None


def _load_context_bundle(path: Path, lint: _Lint) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        lint.hard("MALFORMED_MANIFEST", f"context bundle unreadable: {exc}")
        return []
    statements = data.get("do_not_redo", [])
    if isinstance(statements, dict):
        flat: list[str] = []
        for group in statements.values():
            if isinstance(group, list):
                flat.extend(str(s) for s in group)
        return flat
    if isinstance(statements, list):
        return [str(s) for s in statements]
    lint.hard("MALFORMED_MANIFEST", "context bundle do_not_redo is neither list nor mapping")
    return []


def lint_file(path: Path | str, context_path: Path | str | None = None) -> list[Finding]:
    """Lint one commission manifest; returns deterministically ordered findings."""
    lint = _Lint()
    path = Path(path)

    raw = _extract_manifest_text(path)
    if raw is None:
        lint.hard("MALFORMED_MANIFEST", "no fenced yaml manifest block found")
        return _finalize(lint)
    try:
        manifest = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        lint.hard("MALFORMED_MANIFEST", f"yaml parse failure: {exc}")
        return _finalize(lint)
    if not isinstance(manifest, dict):
        lint.hard("MALFORMED_MANIFEST", "manifest is not a mapping")
        return _finalize(lint)

    if manifest.get("schema") != SCHEMA:
        lint.hard("MALFORMED_MANIFEST", f"schema must be {SCHEMA}, got {manifest.get('schema')!r}")
    mode = manifest.get("handoff_mode")
    if mode not in MODES:
        lint.hard("MALFORMED_MANIFEST", f"handoff_mode must be one of {MODES}, got {mode!r}")
        mode = None

    obligations = _check_obligations(manifest, lint)
    _check_identity(manifest, mode, lint)
    _check_sources(manifest, mode, lint)
    _check_execution(manifest, mode, obligations, lint)
    _check_dnr(manifest, obligations, lint)

    if context_path is not None:
        bundle = _load_context_bundle(Path(context_path), lint)
        _check_dnr_coverage(manifest, bundle, lint)
    else:
        lint.warn(
            "DNR_COVERAGE_UNPROVEN",
            "no --agentos-context bundle supplied; only the author's declared "
            "do_not_redo reconciliation was validated",
        )

    return _finalize(lint)


def _finalize(lint: _Lint) -> list[Finding]:
    order = {HARD: 0, WARNING: 1}
    return sorted(lint.findings, key=lambda f: (order[f.severity], f.name, f.detail))


def _check_identity(manifest: dict, mode: str | None, lint: _Lint) -> None:
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        lint.hard("MALFORMED_MANIFEST", "identity block missing or not a mapping")
        return

    program_or_workstream = identity.get("program_or_workstream")
    if not (isinstance(program_or_workstream, str) and program_or_workstream.strip()):
        lint.hard(
            "MALFORMED_MANIFEST",
            f"identity.program_or_workstream must be a non-empty organizational identity, got {program_or_workstream!r}",
        )

    repository = identity.get("repository")
    if not (isinstance(repository, str) and _REPOSITORY.fullmatch(repository)):
        lint.hard(
            "MALFORMED_MANIFEST",
            f"identity.repository must use exact owner/repo shape, got {repository!r}",
        )

    skillpack_sha = identity.get("skillpack_sha")
    if not (isinstance(skillpack_sha, str) and _SHA40.fullmatch(skillpack_sha)):
        lint.hard(
            "MALFORMED_MANIFEST",
            f"identity.skillpack_sha must be an exact 40-hex Skillpack commit SHA, got {skillpack_sha!r}",
        )

    carrier = identity.get("carrier")
    if not isinstance(carrier, dict):
        lint.hard("MALFORMED_MANIFEST", "identity.carrier missing or not a mapping")
        return
    pickup = carrier.get("pickup_sha")
    if mode == "CONTINUATION_DELTA":
        carrier_type = carrier.get("type")
        branch = carrier.get("branch")
        if carrier_type not in {"pull_request", "branch"}:
            lint.hard(
                "UNBOUND_CONTINUATION",
                f"CONTINUATION_DELTA carrier.type must be 'pull_request' or 'branch', got {carrier_type!r}",
            )
        if not (isinstance(branch, str) and branch.strip()):
            lint.hard(
                "UNBOUND_CONTINUATION",
                f"CONTINUATION_DELTA carrier.branch must be non-empty, got {branch!r}",
            )
        if carrier_type == "pull_request":
            carrier_id = carrier.get("id")
            if not (
                isinstance(carrier_id, int)
                and not isinstance(carrier_id, bool)
                and carrier_id > 0
            ):
                lint.hard(
                    "UNBOUND_CONTINUATION",
                    f"CONTINUATION_DELTA pull_request carrier.id must be a positive integer, got {carrier_id!r}",
                )
        if not (isinstance(pickup, str) and _SHA40.fullmatch(pickup)):
            lint.hard(
                "UNBOUND_CONTINUATION",
                f"CONTINUATION_DELTA requires an exact 40-hex carrier pickup_sha, got {pickup!r}",
            )
    if mode == "NEW_WAVE" and carrier.get("type") == "pull_request" and carrier.get("id"):
        lint.warn(
            "NEW_WAVE_WITH_EXISTING_CARRIER",
            f"NEW_WAVE declared but carrier is existing pull_request #{carrier.get('id')} — "
            "possibly the wrong handoff mode",
        )


def _source_ok(entry: object, require_status_present: bool) -> tuple[bool, str]:
    """A source is reconciled when it carries path + a well-formed observed_sha,
    OR explicitly declares status: unavailable (with a reason) / status: absent.
    Returns (reconciled, malformed_detail)."""
    if not isinstance(entry, dict):
        return False, ""
    status = entry.get("status")
    if status in {"unavailable", "absent"}:
        if status == "unavailable" and not str(entry.get("reason", "")).strip():
            return False, "status: unavailable requires a reason"
        return True, ""
    observed = entry.get("observed_sha")
    if observed is not None and not (
        isinstance(observed, str) and _OBSERVED_SHA.fullmatch(observed)
    ):
        return False, (
            f"observed_sha must be 40-hex or blob:<40-hex>, got {observed!r}"
        )
    has_identity = bool(entry.get("path")) and observed is not None
    if require_status_present and status not in {None, "present"}:
        return False, f"unknown source status {status!r}"
    return has_identity, ""


def _check_sources(manifest: dict, mode: str | None, lint: _Lint) -> None:
    if mode != "CONTINUATION_DELTA":
        return
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        lint.hard(
            "ORGANIZATIONAL_STATE_NOT_RECONCILED",
            "CONTINUATION_DELTA carries no sources block",
        )
        return
    for key in ("agentos_workstream", "latest_handoff"):
        entry = sources.get(key)
        if entry is None:
            lint.hard(
                "ORGANIZATIONAL_STATE_NOT_RECONCILED",
                f"sources.{key} absent and not declared status: unavailable/absent — "
                "the organizational state was not considered",
            )
            continue
        reconciled, malformed = _source_ok(entry, require_status_present=True)
        if malformed:
            lint.hard("MALFORMED_MANIFEST", f"sources.{key}: {malformed}")
        elif not reconciled:
            lint.hard(
                "ORGANIZATIONAL_STATE_NOT_RECONCILED",
                f"sources.{key} lacks path+observed_sha and is not declared unavailable/absent",
            )
    github = sources.get("github")
    if not isinstance(github, dict):
        lint.hard(
            "ORGANIZATIONAL_STATE_NOT_RECONCILED",
            "sources.github absent — carrier/default-branch state was not pinned",
        )
    else:
        for key in ("default_branch_sha", "carrier_head_sha"):
            value = github.get(key)
            if not (isinstance(value, str) and _SHA40.fullmatch(value)):
                lint.hard(
                    "MALFORMED_MANIFEST",
                    f"sources.github.{key} must be 40-hex, got {value!r}",
                )
        identity = manifest.get("identity") or {}
        carrier = identity.get("carrier") if isinstance(identity, dict) else None
        pickup = carrier.get("pickup_sha") if isinstance(carrier, dict) else None
        carrier_head = github.get("carrier_head_sha")
        if (
            isinstance(pickup, str)
            and _SHA40.fullmatch(pickup)
            and isinstance(carrier_head, str)
            and _SHA40.fullmatch(carrier_head)
            and pickup != carrier_head
        ):
            lint.hard(
                "CARRIER_HEAD_MISMATCH",
                f"identity.carrier.pickup_sha {pickup} does not match "
                f"sources.github.carrier_head_sha {carrier_head} — continuation grounding is inconsistent",
            )
    # Best-effort staleness hint (documented as best-effort in the contract):
    # only fires when the author supplied both structured fields.
    workstream = sources.get("agentos_workstream")
    carrier = (manifest.get("identity") or {}).get("carrier") or {}
    if isinstance(workstream, dict) and isinstance(carrier, dict):
        recorded = workstream.get("recorded_next_wave")
        completed = carrier.get("completed_waves")
        if recorded and isinstance(completed, list) and recorded in completed:
            lint.warn(
                "POSSIBLE_STALE_ORG_STATE",
                f"workstream records next wave {recorded!r} but the carrier lists it "
                "completed — organizational state may lag implementation truth",
            )


def _check_obligations(manifest: dict, lint: _Lint) -> dict[str, dict]:
    obligations = manifest.get("obligations")
    result: dict[str, dict] = {}
    if obligations is None:
        lint.hard("MALFORMED_MANIFEST", "obligations block missing")
        return result
    if not isinstance(obligations, list):
        lint.hard("MALFORMED_MANIFEST", "obligations is not a list")
        return result
    seen: dict[str, str] = {}
    for ob in obligations:
        if not isinstance(ob, dict) or not ob.get("id") or not ob.get("statement"):
            lint.hard("MALFORMED_MANIFEST", f"obligation lacks id/statement: {ob!r}")
            continue
        oid = str(ob["id"])
        disposition = ob.get("disposition")
        if disposition not in DISPOSITIONS:
            lint.hard(
                "MALFORMED_MANIFEST",
                f"obligation {oid}: unknown disposition {disposition!r}",
            )
            continue
        if oid in seen:
            lint.hard(
                "OBLIGATION_STATE_COLLISION",
                f"obligation {oid} declared more than once "
                f"({seen[oid]} vs {disposition})",
            )
            continue
        seen[oid] = disposition
        result[oid] = ob
        if disposition == "REVALIDATE_REQUIRED":
            prior = ob.get("prior_evidence")
            invalidated = ob.get("invalidated_by")
            if not (isinstance(prior, list) and any(str(x).strip() for x in prior)) or not (
                isinstance(invalidated, list) and any(str(x).strip() for x in invalidated)
            ):
                lint.hard(
                    "UNJUSTIFIED_REVALIDATION",
                    f"obligation {oid}: REVALIDATE_REQUIRED needs both prior_evidence "
                    "and a concrete invalidated_by event",
                )
    return result


def _check_execution(
    manifest: dict, mode: str | None, obligations: dict[str, dict], lint: _Lint
) -> None:
    execution = manifest.get("execution")
    if not isinstance(execution, dict):
        lint.hard("MALFORMED_MANIFEST", "execution block missing or not a mapping")
        return
    surfaces = {}
    for key in ("ordered", "parallel", "held"):
        value = execution.get(key, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            lint.hard("MALFORMED_MANIFEST", f"execution.{key} is not a list")
            value = []
        surfaces[key] = [str(x) for x in value]

    executable = surfaces["ordered"] + surfaces["parallel"]

    # One ID, one placement — anywhere across the three surfaces. Duplication
    # inside a list and cross-list placement are equally contradictions.
    all_placements = surfaces["ordered"] + surfaces["parallel"] + surfaces["held"]
    for oid in sorted({x for x in all_placements if all_placements.count(x) > 1}):
        locations = [key for key in ("ordered", "parallel", "held") for x in surfaces[key] if x == oid]
        lint.hard(
            "EXECUTION_SURFACE_COLLISION",
            f"obligation {oid} appears {len(locations)} times across execution surfaces "
            f"({', '.join(locations)}) — one ID, one placement",
        )

    for key in ("ordered", "parallel", "held"):
        for oid in surfaces[key]:
            if oid not in obligations:
                lint.hard(
                    "UNDECLARED_EXECUTION",
                    f"execution.{key} references {oid} which is not declared in obligations",
                )

    for oid in executable:
        ob = obligations.get(oid)
        if ob is None:
            continue
        disposition = ob["disposition"]
        if disposition in NEVER_EXECUTABLE:
            lint.hard(
                REOPEN_FINDING_BY_DISPOSITION[disposition],
                f"obligation {oid} ({disposition}) appears in executable scope",
            )
        elif disposition not in EXEC_ELIGIBLE:
            lint.hard(
                "EXECUTION_DISPOSITION_ILLEGAL",
                f"obligation {oid} ({disposition}) is not execution-eligible "
                f"(only {sorted(EXEC_ELIGIBLE)} may be executed)",
            )

    for oid in surfaces["held"]:
        ob = obligations.get(oid)
        if ob is None:
            continue
        disposition = ob["disposition"]
        if disposition in NEVER_EXECUTABLE:
            lint.hard(
                "HELD_DISPOSITION_ILLEGAL",
                f"obligation {oid} ({disposition}) is settled work — holding it is "
                "meaningless and hides the settled state",
            )
        elif disposition in EXEC_ELIGIBLE and not str(ob.get("hold_reason", "")).strip():
            lint.hard(
                "HELD_DISPOSITION_ILLEGAL",
                f"obligation {oid} ({disposition}) may be held only with an explicit hold_reason",
            )

    own_workstream = str((manifest.get("identity") or {}).get("program_or_workstream") or "").strip()
    placed = set(surfaces["ordered"]) | set(surfaces["parallel"]) | set(surfaces["held"])
    for oid, ob in obligations.items():
        if ob["disposition"] in EXEC_ELIGIBLE and oid not in placed:
            deferred = str(ob.get("deferred_to", "")).strip()
            if _WS_TOKEN.fullmatch(deferred) and deferred != own_workstream:
                # Deterministic floor only: exact WS:<KEY> grammar and not this
                # commission's own workstream. Existence/independence of the
                # target is NOT proven here.
                continue
            lint.hard(
                "DARK_OPEN_WORK",
                f"obligation {oid} ({ob['disposition']}) is neither executable, held, nor "
                "validly deferred_to an independent workstream (exact WS:<KEY> token, not "
                "this commission's own workstream)",
            )

    if mode == "CONTINUATION_DELTA" and not executable:
        lint.hard(
            "NOTHING_TO_COMMISSION",
            "no executable work remains — emit a NOTHING_TO_COMMISSION report to the "
            "Chairman instead of dispatching a continuation commission",
        )


def _check_dnr(manifest: dict, obligations: dict[str, dict], lint: _Lint) -> None:
    entries = manifest.get("do_not_redo_reconciliation")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        lint.hard("MALFORMED_MANIFEST", "do_not_redo_reconciliation is not a list")
        return
    # One normalized binding statement, exactly one reconciliation entry.
    # HONORED + REFUTED duplicates would otherwise both "cover" the statement
    # while contradicting each other (coverage collapses to set membership).
    seen_statements: dict[str, int] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("statement"):
            norm = _normalize_statement(entry["statement"])
            seen_statements[norm] = seen_statements.get(norm, 0) + 1
    for norm, count in sorted(seen_statements.items()):
        if count > 1:
            lint.hard(
                "DNR_STATE_COLLISION",
                f"do_not_redo statement reconciled {count} times (normalized: {norm!r}) — "
                "one binding statement takes exactly one disposition",
            )
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("statement"):
            lint.hard("MALFORMED_MANIFEST", f"do_not_redo entry lacks statement: {entry!r}")
            continue
        disposition = entry.get("disposition")
        if disposition not in DNR_DISPOSITIONS:
            lint.hard(
                "MALFORMED_MANIFEST",
                f"do_not_redo entry disposition must be one of {DNR_DISPOSITIONS}, "
                f"got {disposition!r}",
            )
            continue
        reopens = entry.get("reopens") or []
        refuted_by = entry.get("refuted_by")
        has_refutation = isinstance(refuted_by, list) and any(
            str(x).strip() for x in refuted_by
        )
        if disposition == "REFUTED" and not has_refutation:
            lint.hard(
                "DNR_REOPEN_WITHOUT_REFUTATION",
                f"do_not_redo entry {entry.get('statement')!r} is REFUTED without "
                "concrete refuted_by evidence",
            )
        if reopens and not (disposition == "REFUTED" and has_refutation):
            lint.hard(
                "DNR_REOPEN_WITHOUT_REFUTATION",
                f"do_not_redo entry {entry.get('statement')!r} maps {sorted(map(str, reopens))} "
                "back toward execution without disposition: REFUTED + refuted_by evidence",
            )


def _check_dnr_coverage(manifest: dict, bundle_statements: list[str], lint: _Lint) -> None:
    entries = manifest.get("do_not_redo_reconciliation")
    declared = set()
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("statement"):
                declared.add(_normalize_statement(entry["statement"]))
    for statement in bundle_statements:
        if _normalize_statement(statement) not in declared:
            lint.hard(
                "DNR_COVERAGE_MISSING",
                f"binding do_not_redo statement not reconciled: {statement!r}",
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", help="commission manifest (.md with fenced yaml, or .yml)")
    parser.add_argument(
        "--agentos-context",
        default=None,
        help="optional Agent OS context bundle JSON for do_not_redo coverage cross-check",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    context_path = Path(args.agentos_context) if args.agentos_context else None
    if context_path is not None and not context_path.is_file():
        print(f"ERROR: context bundle not found: {context_path}", file=sys.stderr)
        return 2

    findings = lint_file(manifest_path, context_path=context_path)
    hard_count = sum(1 for f in findings if f.severity == HARD)

    if args.as_json:
        print(
            json.dumps(
                {
                    "manifest": str(manifest_path),
                    "hard_count": hard_count,
                    "findings": [dataclasses.asdict(f) for f in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for f in findings:
            print(f"{f.severity.upper():7s} {f.name}: {f.detail}")
        print(
            f"{'REFUSE' if hard_count else 'PASS'}: {hard_count} hard finding(s), "
            f"{len(findings) - hard_count} warning(s) — validation only; this tool "
            "authorizes nothing"
        )
    return 1 if hard_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
