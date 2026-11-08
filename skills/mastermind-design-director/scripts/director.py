#!/usr/bin/env python3
"""Portable, offline design-document helpers; no dispatch, credentials or task store.

The existing Hermes skills/terminal tools invoke this CLI. GitHub/Agent OS retain
the documents; Paper supplies observations; runtime owners retain every effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REFERENCES = 5
APPROVAL_CLASSES = {"chairman_approved", "owner_accepted", "ai_curated", "unknown", "superseded", "rejected"}
REVIEW_DIMENSIONS = (
    "sophistication", "composition", "typography", "spacing", "distinctiveness",
    "system_consistency", "workflow", "data_readability", "accessibility",
    "responsive", "feasibility", "assignment_completeness",
)
RATINGS = {"strong", "adequate", "needs_work", "not_observed"}


class DesignError(ValueError):
    """Invalid document or unproven prerequisite; never permission to retry an effect."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DesignError(message)


def text(value: Any, name: str, limit: int = 12000) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name}: nonempty text required")
    require(len(value) <= limit and "\x00" not in value, f"{name}: invalid length or NUL")
    return value


def strings(value: Any, name: str, *, minimum: int = 0) -> list[str]:
    require(isinstance(value, list) and minimum <= len(value) <= 100, f"{name}: bounded list required")
    for item in value:
        text(item, name)
    require(len(value) == len(set(value)), f"{name}: duplicate items")
    return value


def obj(value: Any, name: str) -> dict:
    require(isinstance(value, dict), f"{name}: object required")
    return value


def timestamp(value: Any, name: str) -> datetime:
    text(value, name, 64)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesignError(f"{name}: ISO timestamp required") from exc
    require(result.tzinfo is not None, f"{name}: timezone required")
    require(result <= datetime.now(timezone.utc), f"{name}: future timestamps are not observations")
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path) -> Any:
    require(path.stat().st_size <= MAX_JSON_BYTES, "JSON document exceeds 2 MiB")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DesignError("Invalid UTF-8 JSON") from exc


def schema(value: Any, kind: str) -> dict:
    value = obj(value, kind)
    require(value.get("schema") == f"mastermind.design.{kind}.v1", f"Wrong {kind} schema")
    return value


def assignment(value: Any) -> dict:
    a = schema(value, "assignment")
    timestamp(a.get("issued_at"), "assignment.issued_at")
    for key in ("operation_id", "assignment_id", "source_ref", "product", "persona", "objective",
                "user_question", "useful_next_step", "shell_ref", "token_ref"):
        text(a.get(key), key)
    paper = obj(a.get("paper"), "paper")
    text(paper.get("file_id"), "paper.file_id", 128)
    text(paper.get("page_id"), "paper.page_id", 128)
    strings(paper.get("scope_node_ids", []), "paper.scope_node_ids")
    require(type(paper.get("allow_new_artboards")) is bool, "allow_new_artboards: boolean required")
    require(paper["scope_node_ids"] or paper["allow_new_artboards"], "No authorized Paper target")
    for key in ("preserve", "states", "viewports", "acceptance", "constraints", "non_goals"):
        strings(a.get(key), key, minimum=1 if key in {"preserve", "states", "viewports", "acceptance"} else 0)
    strings(a.get("reference_ids", []), "reference_ids")
    if "data_and_interactions" in a:
        text(a["data_and_interactions"], "data_and_interactions")
    if a.get("session_ref") is not None:
        text(a["session_ref"], "session_ref")
    require(a.get("effect_state", "none") in {"none", "known", "unknown"}, "Invalid effect_state")
    return a


def local_artifact(root: Path, relative: Any) -> Path:
    text(relative, "artifact path", 1024)
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "Artifact path must stay inside evidence root")
    root = root.resolve()
    candidate = root / rel
    for part in (candidate, *candidate.parents):
        if part == root:
            break
        require(not part.is_symlink(), "Symlink evidence is not accepted")
    require(candidate.resolve().is_relative_to(root), "Artifact escapes evidence root")
    require(candidate.is_file(), f"Evidence file missing: {relative}")
    return candidate


def screenshot(e: Any, root: Path) -> dict:
    e = obj(e, "screenshot")
    for key in ("file_id", "page_id", "node_id", "path", "sha256", "source_ref"):
        text(e.get(key), f"screenshot.{key}")
    require(re.fullmatch(r"[0-9a-f]{64}", e["sha256"]) is not None, "Invalid screenshot digest")
    timestamp(e.get("observed_at"), "screenshot.observed_at")
    path = local_artifact(root, e["path"])
    require(path.stat().st_size <= MAX_IMAGE_BYTES, "Screenshot exceeds 8 MiB")
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"), "Evidence must be PNG or JPEG")
    require(hashlib.sha256(data).hexdigest() == e["sha256"], "Screenshot bytes changed")
    try:
        from PIL import Image
    except ImportError as exc:
        raise DesignError("Pillow image decoder is required; use the existing qualified runtime") from exc
    try:
        with Image.open(io.BytesIO(data)) as im:
            require(im.format in {"PNG", "JPEG"}, "Unsupported image encoding")
            require(0 < im.width * im.height <= 40000000, "Screenshot pixel budget exceeded")
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            im.load()
    except DesignError:
        raise
    except Exception as exc:
        raise DesignError("Screenshot is not a decodable complete image") from exc
    return e


def corpus(value: Any, root: Path, *, verify_images: bool = True) -> dict:
    c = schema(value, "corpus")
    require(isinstance(c.get("references"), list) and len(c["references"]) <= 500, "Invalid corpus")
    ids = set()
    for item in c["references"]:
        r = obj(item, "reference")
        rid = text(r.get("id"), "reference.id", 128)
        require(rid not in ids, "Duplicate reference ID")
        ids.add(rid)
        for key in ("title", "product", "source_ref", "why_it_works"):
            text(r.get(key), f"reference.{key}")
        for key in ("tags", "principles", "limitations", "reuse_contexts"):
            strings(r.get(key), f"reference.{key}")
        approval = obj(r.get("approval"), "approval")
        require(approval.get("classification") in APPROVAL_CLASSES, "Invalid approval classification")
        if approval["classification"] in {"chairman_approved", "owner_accepted"}:
            for key in ("actor", "source_ref", "scope"):
                text(approval.get(key), f"approval.{key}")
            timestamp(approval.get("recorded_at"), "approval.recorded_at")
        # Approval is a cited classification, never conferred by this validator.
        if verify_images:
            screenshot(r.get("screenshot"), root)
    return c


def retrieve(c: dict, query: str, *, product: str | None = None, limit: int = 3,
             approved_only: bool = False) -> list[dict]:
    require(type(limit) is int and 1 <= limit <= MAX_REFERENCES, "Reference limit must be 1–5")
    terms = set(re.findall(r"\w+", query.casefold()))
    require(bool(terms), "A reference query is required")
    ranked = []
    for r in c["references"]:
        cls = r["approval"]["classification"]
        if cls in {"rejected", "superseded"} or (approved_only and cls not in {"chairman_approved", "owner_accepted"}):
            continue
        hay = " ".join([r["title"], r["product"], *r["tags"], *r["reuse_contexts"]]).casefold()
        overlap = len(terms.intersection(re.findall(r"\w+", hay)))
        same_product = bool(product and r["product"].casefold() == product.casefold())
        if not overlap and not same_product:
            continue
        score = overlap * 3 + (5 if same_product else 0) + (1 if cls in {"chairman_approved", "owner_accepted"} else 0)
        ranked.append((score, r["id"], r))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in ranked[:limit]]


def bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None specified."


def brief(a: dict, c: dict) -> str:
    a = assignment(a)
    require(a.get("effect_state", "none") != "unknown", "Reconcile the original effect before preparing a new dispatch")
    known = {r["id"]: r for r in c["references"]}
    wanted = a.get("reference_ids", [])
    require(all(i in known for i in wanted), "Requested reference ID is absent")
    refs = [known[i] for i in wanted] if wanted else retrieve(c, a["objective"], product=a["product"])
    require(len(refs) <= MAX_REFERENCES, "Brief exceeds five references")
    require(all(r["approval"]["classification"] not in {"rejected", "superseded"} for r in refs), "Negative examples cannot be positive brief references")
    selected = "\n".join(
        f"- **{r['title']}** [{r['approval']['classification']}] — {r['source_ref']}\n"
        f"  Study: {r['why_it_works']}\n  Limits: {'; '.join(r['limitations'])}\n"
        f"  Screenshot: {r['screenshot']['path']} (sha256 {r['screenshot']['sha256']})"
        for r in refs) or "No qualified matching visual examples. Do not invent approval or visual evidence."
    parts = [
        f"# Astra Pro design brief — {a['product']}",
        f"Operation: {a['operation_id']}\nAssignment: {a['assignment_id']}\nAssignment SHA-256: {digest(a)}\nSource: {a['source_ref']}",
        f"## The experience\n\n{a['objective']}\n\nFor {a['persona']}. At first glance, answer: **{a['user_question']}**\nUseful next step: {a['useful_next_step']}",
        f"## Product context\n\nShell: {a['shell_ref']}\nTokens/components: {a['token_ref']}\nPreserve:\n\n{bullet(a['preserve'])}",
        f"## Exact Paper scope\n\nFile: `{a['paper']['file_id']}`; page: `{a['paper']['page_id']}`. Existing nodes: {', '.join(a['paper']['scope_node_ids']) or 'none'}. New artboards allowed: {a['paper']['allow_new_artboards']}. Inspect these targets and live writers before editing.",
        f"## Selected visual references\n\n{selected}",
        "## Creative direction\n\nYou are the creative principal. Choose a compelling composition and expressive hierarchy within the product's actual visual grammar. Use examples for judgment, not a fixed layout. Explain one meaningful tradeoff. Avoid decorative colored container edges, generic card repetition and false live data. Keep real analytical depth available through purposeful disclosure.",
        f"## States and responsive behavior\n\n{bullet(a['states'])}\n\nViewports:\n{bullet(a['viewports'])}",
        f"## Data and interactions\n\n{a.get('data_and_interactions', 'Recover actual data contracts and interactions from the source; report missing facts. Never invent signals, approval or execution authority.')}",
        f"## Constraints\n\n{bullet(a['constraints'])}\n\nNon-goals:\n{bullet(a['non_goals'])}",
        f"## Acceptance and return\n\n{bullet(a['acceptance'])}\n\nInspect actual screenshots after changes. Return `mastermind.design.completion.v1` with this operation/assignment, account alias, session reference, exact Paper IDs, changed screens, screenshots, decisions, states, gaps, checks, limitations and exact continuation. A send receipt is not START and a screenshot is not implemented software.",
        f"Continue original session: {a.get('session_ref') or 'Not yet bound; use the supported attended dispatch route.'}\nNever scrape ChatGPT, share credentials, rotate accounts to evade a quota, or retry a missing completion."
    ]
    result = "\n\n".join(parts) + "\n"
    require(len(result) <= 28000, "Brief exceeds 28000 characters; narrow context without dropping acceptance")
    return result


def completion(a: dict, value: Any, evidence_root: Path) -> dict:
    a = assignment(a)
    r = schema(value, "completion")
    for key in ("operation_id", "assignment_id"):
        require(r.get(key) == a[key], f"Completion {key} does not match assignment")
    require(r.get("assignment_sha256") == digest(a), "Completion is for a different assignment revision")
    for key in ("session_ref", "account_alias", "summary", "continuation"):
        text(r.get(key), key)
    if a.get("session_ref"):
        require(r["session_ref"] == a["session_ref"], "Completion changed original session")
    require(r.get("status") in {"complete", "partial", "blocked"}, "Invalid completion status")
    reported_at = timestamp(r.get("reported_at"), "reported_at")
    issued_at = timestamp(a["issued_at"], "issued_at")
    require(reported_at >= issued_at, "Completion predates assignment")
    for key in ("decisions", "interactions", "gaps", "limitations", "checks"):
        strings(r.get(key), key)
    screens = r.get("screens")
    require(isinstance(screens, list) and 0 <= len(screens) <= 100, "Invalid screens")
    if r["status"] == "complete":
        require(bool(screens) and not r["gaps"], "Complete requires screens and no functional gaps")
    seen = set()
    for s in screens:
        obj(s, "screen")
        for key in ("node_id", "name", "change"):
            text(s.get(key), f"screen.{key}")
        require(s["node_id"] not in seen, "Duplicate screen")
        seen.add(s["node_id"])
        require(s.get("file_id") == a["paper"]["file_id"], "Wrong Paper file")
        require(s.get("page_id") == a["paper"]["page_id"], "Wrong Paper page")
        require(s["change"] in {"created", "changed", "unchanged", "removed"}, "Invalid screen change")
        if s["change"] == "created":
            require(a["paper"]["allow_new_artboards"], "New artboard not authorized by scope")
        else:
            require(s["node_id"] in a["paper"]["scope_node_ids"], "Screen outside existing-node scope")
        if s["change"] != "removed":
            e = screenshot(s.get("screenshot"), evidence_root)
            require(all(e[key] == s[key] for key in ("file_id", "page_id", "node_id")), "Screenshot target mismatch")
            require(issued_at <= timestamp(e["observed_at"], "observed_at") <= reported_at,
                    "Screenshot observation is outside assignment/completion interval")
    coverage = obj(r.get("coverage"), "coverage")
    require(set(coverage) == {"preserve", "states", "viewports", "acceptance"}, "All assignment coverage groups required")
    evidence_digests = {s["screenshot"]["sha256"] for s in screens if s["change"] != "removed"}
    for group in coverage:
        rows = coverage[group]
        require(isinstance(rows, list) and len(rows) == len(a[group]), f"Incomplete {group} coverage")
        require(all(isinstance(row, dict) for row in rows), "Invalid coverage row")
        require([row.get("requirement") for row in rows] == a[group], f"Changed or reordered {group} requirements")
        for row in rows:
            require(row.get("status") in {"observed", "missing"}, "Invalid coverage status")
            text(row.get("evidence"), "coverage.evidence")
            cited = strings(row.get("screenshot_sha256"), "coverage.screenshot_sha256")
            require(set(cited) <= evidence_digests, "Coverage cites unknown screenshot")
            if row["status"] == "observed":
                require(bool(cited), "Observed coverage requires actual image evidence")
            if r["status"] == "complete":
                require(row["status"] == "observed", "Complete return has missing assignment coverage")
    return {"schema": "mastermind.design.validation.v1", "assignment_id": a["assignment_id"],
            "completion_sha256": digest(r), "document_valid": True,
            "design_accepted": False, "production_proven": False,
            "meaning": "Document identity and local evidence bytes checked; verify current Paper and review substance."}


def critique(a: dict, r: dict, value: Any, evidence_root: Path) -> dict:
    checked = completion(a, r, evidence_root)
    q = schema(value, "critique")
    require(q.get("completion_sha256") == checked["completion_sha256"], "Critique is for a different completion")
    for key in ("reviewer", "evidence_ref"):
        text(q.get(key), key)
    require(timestamp(q.get("observed_at"), "critique.observed_at") >= timestamp(r["reported_at"], "reported_at"),
            "Critique predates completion")
    dimensions = obj(q.get("dimensions"), "dimensions")
    require(set(dimensions) == set(REVIEW_DIMENSIONS), "All twelve review dimensions are required")
    for name, d in dimensions.items():
        obj(d, name)
        require(d.get("rating") in RATINGS, f"Invalid rating: {name}")
        text(d.get("evidence"), f"{name}.evidence")
    viewed = strings(q.get("viewed_screenshot_sha256"), "viewed_screenshot_sha256", minimum=1)
    actual = {s["screenshot"]["sha256"] for s in r["screens"] if s["change"] != "removed"}
    require(set(viewed) <= actual, "Critique cites unknown screenshot")
    issues = q.get("issues")
    require(isinstance(issues, list) and len(issues) <= 30, "Invalid critique issues")
    for issue in issues:
        obj(issue, "issue")
        require(issue.get("priority") in {"blocking", "material", "polish"}, "Invalid issue priority")
        require(issue.get("dimension") in REVIEW_DIMENSIONS, "Invalid issue dimension")
        for key in ("finding", "evidence", "requested_change"):
            text(issue.get(key), f"issue.{key}")
    # This recommendation cannot change a task, accept a design or authorize a send.
    missing = sorted(actual - set(viewed))
    essential_unobserved = any(d["rating"] == "not_observed" for d in dimensions.values())
    new_scope_unverified = [s["node_id"] for s in r["screens"]
                            if s["change"] == "created" and s["node_id"] not in a["paper"]["scope_node_ids"]]
    if a.get("effect_state") == "unknown":
        action = "reconcile_original_effect"
    elif r["status"] != "complete" or r["gaps"] or missing or essential_unobserved or new_scope_unverified:
        action = "gather_missing_evidence"
    elif any(i["priority"] in {"blocking", "material"} for i in issues):
        action = "targeted_revision"
    elif any(d["rating"] == "needs_work" for d in dimensions.values()):
        action = "targeted_revision"
    else:
        action = "candidate_for_design_acceptance"
    return {"schema": "mastermind.design.recommendation.v1", "action": action,
            "completion_sha256": checked["completion_sha256"], "critique_sha256": digest(q),
            "unviewed_screenshots": missing, "not_observed": [k for k,v in dimensions.items() if v["rating"] == "not_observed"],
            "new_scope_requires_canonical_verification": new_scope_unverified,
            "issues": issues, "design_accepted": False, "production_proven": False}


def continuation(a: dict, r: dict, q: dict, evidence_root: Path) -> str:
    result = critique(a, r, q, evidence_root)
    require(a.get("effect_state", "none") != "unknown", "Reconcile original effect before any continuation")
    require(result["action"] != "candidate_for_design_acceptance", "No material revision is justified")
    changes = [i["requested_change"] for i in result["issues"] if i["priority"] != "polish"]
    if result["unviewed_screenshots"]:
        changes.append("Inspect and report the missing screenshot evidence before altering the design.")
    if result["new_scope_requires_canonical_verification"]:
        changes.append("Verify the original creation receipt and amend exact target scope with the canonical owner before candidacy; do not repeat creation.")
    if not changes:
        changes.extend(f"{name}: {d['evidence']}" for name,d in q["dimensions"].items()
                       if d["rating"] in {"needs_work", "not_observed"})
        changes.extend(r["gaps"])
        if not changes:
            changes.append("Resolve the documented incomplete evidence; preserve accepted structure.")
    return (f"# Continue the original design\n\nOperation: {a['operation_id']}\nAssignment: {a['assignment_id']}\n"
            f"Session: {r['session_ref']}\nPaper: {a['paper']['file_id']} / {a['paper']['page_id']}\n"
            f"Prior completion: {digest(r)}\nCritique: {digest(q)} ({q['evidence_ref']})\n\nPreserve:\n{bullet(a['preserve'])}\n\nChange only:\n{bullet(changes)}\n\n"
            "Re-read original targets and known overlapping writers. Return the same completion contract with new screenshot evidence. "
            "Do not recreate the original assignment, resend an uncertain action or repeat accepted work.\n\n"
            f"## Original assignment, unchanged\n\n```json\n{json.dumps(a, ensure_ascii=False, indent=2)}\n```\n")


def handoff(a: dict, r: dict, q: dict, spec: Any, evidence_root: Path) -> str:
    decision = critique(a, r, q, evidence_root)
    require(decision["action"] == "candidate_for_design_acceptance", "Design still needs evidence or revision")
    s = schema(spec, "handoff")
    require(s.get("completion_sha256") == digest(r), "Handoff refers to another completion")
    for key in ("decision_ref", "decision_actor", "implementation_repo", "target_paths", "component_mapping",
                "tokens", "interactions", "data_contracts", "responsive", "accessibility", "verification", "known_gaps"):
        text(s.get(key), f"handoff.{key}")
    sections = [("Implementation", s["implementation_repo"] + "\n" + s["target_paths"]),
                ("Components",s["component_mapping"]),("Tokens",s["tokens"]),
                ("Interactions and states",s["interactions"]),("Data contracts",s["data_contracts"]),
                ("Responsive behavior",s["responsive"]),("Accessibility",s["accessibility"]),
                ("Verification",s["verification"]),("Known gaps",s["known_gaps"])]
    return (f"# Engineering handoff — {a['product']}\n\nOperation: {a['operation_id']}\nAssignment: {a['assignment_id']}\n"
            f"Design decision: {s['decision_ref']} (actor: {s['decision_actor']}; verify with its canonical owner).\n"
            f"Completion: {digest(r)}\nPaper: {a['paper']['file_id']} / {a['paper']['page_id']}\n\n"
            + "\n\n".join(f"## {title}\n\n{body}" for title,body in sections)
            + f"\n\n## Original requirements\n\n```json\n{json.dumps(a, ensure_ascii=False, indent=2)}\n```"
            + "\n\nDesign handoff does not prove implementation, installation or production acceptance.\n")


def status_advice(a: dict, receipt: Any, now: datetime) -> dict:
    assignment(a)
    r = schema(receipt, "observation")
    require(r.get("operation_id") == a["operation_id"] and r.get("assignment_id") == a["assignment_id"], "Observation targets another assignment")
    text(r.get("source_ref"), "observation.source_ref")
    state = r.get("state")
    require(state in {"prepared", "delivered", "started", "running", "completed", "failed", "effect_unknown"}, "Unknown observed state")
    observed = timestamp(r.get("observed_at"), "observation.observed_at")
    require(now.tzinfo is not None and observed <= now, "Observation clock is invalid or in future")
    age = (now - observed).total_seconds() / 60
    if state == "effect_unknown" or a.get("effect_state") == "unknown":
        action = "reconcile_original_effect"
    elif state == "completed":
        action = "verify_completion_and_live_paper"
    elif state == "failed":
        action = "diagnose_original_failure"
    elif state == "prepared":
        action = "attended_dispatch_if_eligible"
    elif age >= 90:
        action = "reconcile_with_existing_owner_no_resubmit"
    elif age >= 45:
        action = "read_official_status_or_canonical_return"
    else:
        action = "await_existing_return"
    return {"schema":"mastermind.design.status_advice.v1", "observed_state":state,
            "worker_start_reported":state in {"started","running","completed"}, "action":action,
            "automatic_resubmit":False,"scheduler_created":False,"source_ref":r["source_ref"]}


def notification(a: dict, r: dict, evidence_root: Path, *, channel: str, thread: str, canonical_ref: str) -> dict:
    completion(a, r, evidence_root)
    for key,value in (("channel",channel),("thread",thread),("canonical_ref",canonical_ref)):
        text(value,key,2000)
    return {"schema":"mastermind.design.notification_draft.v1", "channel":channel,"thread_ts":thread,
            "text":f"Design return: {a['assignment_id']} ({r['status']}). Review original Paper evidence: {canonical_ref}",
            "completion_sha256":digest(r),"sent":False,"design_accepted":False,
            "instruction":"Use the existing authorized Slack action once; preserve returned message ID. Missing receipt requires same-carrier reconciliation."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate-corpus","retrieve","brief","validate-completion","critique","continue","handoff","status","notification"])
    parser.add_argument("--corpus",type=Path,default=SKILL_ROOT/"references"/"corpus.json")
    parser.add_argument("--evidence-root",type=Path,default=SKILL_ROOT)
    parser.add_argument("--assignment",type=Path)
    parser.add_argument("--completion",type=Path)
    parser.add_argument("--critique",type=Path)
    parser.add_argument("--spec",type=Path)
    parser.add_argument("--observation",type=Path)
    parser.add_argument("--query",default="")
    parser.add_argument("--product")
    parser.add_argument("--limit",type=int,default=3)
    parser.add_argument("--approved-only",action="store_true")
    parser.add_argument("--now")
    parser.add_argument("--channel")
    parser.add_argument("--thread")
    parser.add_argument("--canonical-ref")
    args=parser.parse_args(argv)
    def document(name: str) -> dict:
        path=getattr(args,name)
        require(path is not None,f"--{name} is required")
        return read_json(path)
    try:
        if args.command in {"validate-corpus","retrieve","brief"}:
            c=corpus(read_json(args.corpus),SKILL_ROOT if args.corpus==SKILL_ROOT/"references"/"corpus.json" else args.evidence_root)
            if args.command=="validate-corpus":
                result={"valid":True,"references":len(c["references"]),"approval_conferred":False}
            elif args.command=="retrieve":
                result=retrieve(c,args.query,product=args.product,limit=args.limit,approved_only=args.approved_only)
            else:
                result=brief(document("assignment"),c)
        elif args.command=="status":
            result=status_advice(document("assignment"),document("observation"),timestamp(args.now,"now") if args.now else datetime.now(timezone.utc))
        else:
            a=document("assignment"); r=document("completion")
            if args.command=="validate-completion": result=completion(a,r,args.evidence_root)
            elif args.command=="notification": result=notification(a,r,args.evidence_root,channel=args.channel,thread=args.thread,canonical_ref=args.canonical_ref)
            else:
                q=document("critique")
                if args.command=="critique": result=critique(a,r,q,args.evidence_root)
                elif args.command=="continue": result=continuation(a,r,q,args.evidence_root)
                else: result=handoff(a,r,q,document("spec"),args.evidence_root)
        print(result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (DesignError,OSError) as exc:
        print(json.dumps({"error":str(exc),"effect":"none","retry_authorized":False}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
