"""Project planning facts from the existing owner's already-qualified capture.

This module performs no I/O, authentication, source discovery, writes or adoption.
Only the installed sealed source owner may compose its output into a READ result.
References supplied in records never cause a path or network fetch here.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re


_MACRO = "mastermindx-market-intelligence/macro"
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_MAX_RESULT_BYTES = 131072 - 4096


class _CapturedRecord:
    def __init__(self, raw):
        self.raw = raw

    def read_text(self, *, encoding):
        if encoding != "utf-8":
            raise ValueError("RECORD_INVALID")
        return self.raw.decode("utf-8")


def _unavailable(reason):
    return {"state": "UNAVAILABLE", "reason": reason}


def project_captured_continuity(*, owner, work_ref, qualified_commits,
                                workstream_capture, decision_captures,
                                proposal_captures, content_captures):
    """Pure join over captures issued by the existing sealed source owner.

    Captures are closed {source, raw_bytes} values. qualified_commits describes
    roots the caller actually captured, not repositories named by a record.
    Content captures may bind a retained older commit in those same roots.
    Neither those ordinary values nor this function issue source-read authority.
    """
    selected = (work_ref if type(work_ref) is str
                and re.fullmatch(r"WS:[A-Z0-9][A-Z0-9-]{0,62}[A-Z0-9]", work_ref) else None)
    result = {"schema": "mastermind.project_plan_continuity.v1", "work_ref": selected,
              "adoption": _unavailable("SOURCE_UNAVAILABLE"),
              "proposals": {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE",
                            "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}}
    try:
        contract = owner._project_plan_contract()
        if (selected is None or not isinstance(qualified_commits, dict) or _MACRO not in qualified_commits
                or any(repo not in {_MACRO, "mastermindx-market-intelligence/Mastermind"}
                       or type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None
                       for repo, commit in qualified_commits.items())
                or not isinstance(decision_captures, list) or len(decision_captures) > 128
                or not isinstance(proposal_captures, list) or len(proposal_captures) > 32
                or not isinstance(content_captures, list) or len(content_captures) > 128):
            return result
        contents = {}
        identities = {}
        total = 0

        def key(ref):
            return tuple(ref[name] for name in ("repository", "path", "commit", "content_sha256"))

        def capture(value, *, current=False):
            nonlocal total
            if not isinstance(value, dict) or set(value) != {"source", "raw_bytes"}:
                raise ValueError("SOURCE_UNAVAILABLE")
            ref = contract.bind_source_ref(value["source"], value["raw_bytes"])
            if ref["repository"] not in qualified_commits:
                raise ValueError("SOURCE_UNAVAILABLE")
            if current and ref["commit"] != qualified_commits[ref["repository"]]:
                raise ValueError("SOURCE_UNAVAILABLE")
            identity = (ref["repository"], ref["path"], ref["commit"])
            old = identities.get(identity)
            if old is not None and old != ref["content_sha256"]:
                raise ValueError("SOURCE_UNAVAILABLE")
            identities[identity] = ref["content_sha256"]
            total += len(value["raw_bytes"])
            if total > _MAX_CAPTURE_BYTES:
                raise ValueError("CONTENT_OVER_BUDGET")
            contents[key(ref)] = value["raw_bytes"]
            return ref, value["raw_bytes"]

        ws_source, ws_raw = capture(workstream_capture, current=True)
        expected_path = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
        if ws_source["repository"] != _MACRO or ws_source["path"] != expected_path:
            return result
        workstream, _ = owner.parse_record(_CapturedRecord(ws_raw))
        if ("WS:" + str(workstream.get("key")) != work_ref
                or any(p.hard for p in owner.check_workstream(workstream, Path(expected_path), None))):
            return result
        records = []
        record_sources = {}
        for value in decision_captures:
            ref, raw = capture(value, current=True)
            rec, _ = owner.parse_record(_CapturedRecord(raw))
            path = "agentos/decisions/DEC-" + str(rec.get("key")) + ".md"
            if ref["repository"] != _MACRO or ref["path"] != path:
                return result
            if rec.get("key") in record_sources:
                return result
            record_sources[rec.get("key")] = ref
            records.append(rec)
        for value in content_captures:
            capture(value)
        artifacts = workstream.get("artifacts") or []
        if not isinstance(artifacts, list) or any(type(item) is not str for item in artifacts):
            raise ValueError("SOURCE_UNAVAILABLE")
        prepared_proposals = []
        for value in proposal_captures:
            ref, _ = capture(value, current=True)
            repository = ref["repository"].rsplit("/", 1)[-1]
            prefix = "mastermind" if repository == "Mastermind" else "macro"
            if (prefix + ":" + ref["path"] not in artifacts
                    and not (repository == "macro" and ref["path"] in artifacts)):
                raise ValueError("SOURCE_UNAVAILABLE")
            prepared_proposals.append(ref)
        try:
            current = owner.select_project_plan_adoption(records, work_ref=work_ref)
        except ValueError:
            result["adoption"] = _unavailable("LINEAGE_INVALID")
            result["proposals"]["reason"] = "LINEAGE_INVALID"
            return result

        def resolved(ref):
            return contents.get(key(ref))

        def parsed_proposal(ref):
            raw = resolved(ref)
            if raw is None:
                raise LookupError("SOURCE_UNAVAILABLE")
            return owner.parse_project_plan_proposal(raw, work_ref=work_ref)

        # A declared proposal association must bind actual captured bytes before
        # it can substantiate the adopted body. Missing evidence is not adoption.
        if current is None:
            result["adoption"] = _unavailable("NOT_DECLARED")
        else:
            metadata = current["adoption"]
            ref = metadata["adopted_source"]
            raw = resolved(ref)
            current_key = current["decision_ref"][4:]
            rec = next(item for item in records if item.get("key") == current_key)
            if (type(rec.get("decided_by")) is not str or not rec["decided_by"].strip()
                    or len(rec["decided_by"]) > 256):
                raise ValueError("RECORD_INVALID")
            decided_at = (rec["decided_at"].isoformat()
                          if type(rec["decided_at"]) is date else rec["decided_at"])
            if type(decided_at) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", decided_at) is None:
                raise ValueError("RECORD_INVALID")
            declaration = {"decision_ref": current["decision_ref"],
                           "decision_source": record_sources[current_key],
                           "adoption": metadata, "decided_by": rec["decided_by"],
                           "decided_at": decided_at}
            reason = None if raw is not None else "SOURCE_UNAVAILABLE"
            proposal_ref = metadata["proposal_source"]
            if proposal_ref is not None:
                try:
                    header, _candidate = parsed_proposal(proposal_ref)
                    if (header["base_adoption"] != metadata["predecessor"]
                            or header["candidate_sha256"] != ref["content_sha256"]):
                        raise ValueError("RECORD_INVALID")
                    if metadata["predecessor"] is not None:
                        previous = next(item for item in records
                                        if "DEC:" + item["key"] == metadata["predecessor"])
                        if header["base_source"] != previous["project_plan_adoption"]["adopted_source"]:
                            raise ValueError("RECORD_INVALID")
                except LookupError:
                    reason = "SOURCE_UNAVAILABLE"
                except (ValueError, StopIteration):
                    reason = "PROPOSAL_MISMATCH"
            if reason:
                result["adoption"] = {**_unavailable(reason), "declared_decision": declaration}
            else:
                result["adoption"] = {"state": "AVAILABLE", **declaration,
                                      "content": raw.decode("utf-8")}

        proposals = []
        seen = set()
        for associated_ref in prepared_proposals:
            ref = associated_ref
            declared_ref = current["adoption"]["proposal_source"] if current else None
            if (declared_ref is not None
                    and all(declared_ref[k] == associated_ref[k] for k in ("repository", "path", "content_sha256"))
                    and resolved(declared_ref) is not None
                    and resolved(declared_ref) == resolved(associated_ref)):
                # Current WS association and retained decision reference can
                # name different commits containing the exact same artifact.
                # Both bodies were actually captured and byte-compared above.
                # Preserve the decision's immutable reference; never infer this
                # association from digest metadata or a timestamp alone.
                ref = declared_ref
            item = {"proposal_source": ref}
            try:
                header, candidate = parsed_proposal(ref)
                if header["proposal_id"] in seen:
                    result["proposals"] = {**_unavailable("RECORD_INVALID"),
                                           "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}
                    return result
                seen.add(header["proposal_id"])
                referenced = current is not None and current["adoption"]["proposal_source"] == ref
                item.update({"state": "RECORDED_PROPOSAL", **header,
                             "adoption_relation": ("CURRENT_DECISION_REFERENCES_PROPOSAL" if referenced
                                                   else "UNASSOCIATED_WITH_CURRENT_DECISION")})
                comparison_base = current
                if referenced:
                    predecessor = current["adoption"]["predecessor"]
                    if predecessor is None:
                        comparison_base = None
                    else:
                        previous = next(row for row in records if "DEC:" + row["key"] == predecessor)
                        comparison_base = {"decision_ref": predecessor,
                                           "adoption": previous["project_plan_adoption"]}
                try:
                    contract.require_proposal_base(header, comparison_base)
                except ValueError:
                    item["comparison"] = _unavailable("STALE_PREDECESSOR")
                else:
                    if current is not None and result["adoption"]["state"] != "AVAILABLE":
                        item["comparison"] = _unavailable(result["adoption"]["reason"])
                    else:
                        from control_plane.project_plan_content import compare_plan_content
                        item["comparison"] = compare_plan_content(
                            base_source=header["base_source"], base_bytes=resolved(header["base_source"]),
                            candidate_sha256=header["candidate_sha256"], candidate_bytes=candidate)
                item["comparison_basis"] = ("RECORDED_PREDECESSOR" if referenced
                                             else "DECLARED_ADOPTION_SOURCE"
                                             if current and result["adoption"]["state"] != "AVAILABLE"
                                             else "ADOPTED_CONTENT" if current else "RECORDED_SOURCE")
            except ValueError:
                item.update(_unavailable("RECORD_INVALID"))
            proposals.append(item)
        result["proposals"] = {"state": "AVAILABLE", "items": proposals,
                               "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_RESULT_BYTES:
            result["adoption"] = _unavailable("CONTENT_OVER_BUDGET")
            result["proposals"] = {**_unavailable("CONTENT_OVER_BUDGET"),
                                   "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}
        return result
    except (ValueError, TypeError, KeyError, AttributeError, ImportError, LookupError, OSError,
            UnicodeError, RecursionError, OverflowError):
        # Public projection returns no source paths, payloads or raw exceptions
        # from a failed capture. Actual authenticated owner controls remain outside.
        result["adoption"] = _unavailable("SOURCE_UNAVAILABLE")
        result["proposals"] = {**_unavailable("SOURCE_UNAVAILABLE"),
                               "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}
        return result
