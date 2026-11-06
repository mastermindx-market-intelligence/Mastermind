"""Fixed Git-object acquisition inside the incumbent sealed Macro READ bracket.

No record can choose a host, filesystem root or network fetch. Only regular
Markdown blobs in this already-qualified captured Macro root are resolved.
Other repository references stay unavailable until an existing owner captures
and qualifies that repository too. No publication or adoption occurs here.
"""
from __future__ import annotations

import hashlib
import re
import types

from control_plane.project_plan_continuity import project_captured_continuity

_MACRO = "mastermindx-market-intelligence/macro"
_HELPER = "scripts/agentos_project_plan_contract.py"
_ROW = re.compile(rb"100644 blob ([0-9a-f]{40}) +([0-9]+)\t([^\x00\r\n]+)\x00")
_MAX_INVENTORY = 4096
_MAX_DECISION_BYTES = 16 * 1024 * 1024


def _missing(work_ref):
    return {"schema": "mastermind.project_plan_continuity.v1", "work_ref": work_ref,
            "adoption": {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"},
            "proposals": {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE",
                          "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}}


def capture_plan_continuity(*, owner, git, work_ref, macro_sha,
                            workstream_source, workstream_bytes, executable_macro_sha=None,
                            _data_closure=None):
    """Use the parent's bounded Git runner and existing cumulative deadline."""
    if _data_closure is not None:
        _data_closure.update(state='CAPTURED',captures=[])
    def retain(kind,capture):
        if _data_closure is not None:
            source=capture['source']
            _data_closure['captures'].append(dict(kind=kind,path=source['path'],
                commit=source['commit'] if kind=='ANCHORED_CONTENT' else 'CURRENT_DATA',
                content_sha256=source['content_sha256'],mode='100644'))
    def missing(*,fixed=False):
        if _data_closure is not None:
            _data_closure['state']='FIXED_READER_UNAVAILABLE' if fixed else 'FAILED'
        return _missing(work_ref)
    code_sha = macro_sha if executable_macro_sha is None else executable_macro_sha
    if not callable(getattr(owner, "select_project_plan_adoption", None)):
        return missing(fixed=True)  # Older configured reader, identical at both refs.
    try:
        membership = git("ls-tree", "-z", code_sha, "--", _HELPER)
        if re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(_HELPER) + "\x00", membership) is None:
            return missing(fixed=True)
        helper_text = git("show", code_sha + ":" + _HELPER, limit=1048576)
        helper = types.ModuleType("_captured_agentos_plan_content_contract")
        helper.__file__ = "scripts/agentos_project_plan_contract.py"
        exec(compile(helper_text, helper.__file__, "exec"), helper.__dict__)
        # The actual owner loader is bound to immutable Git bytes, never an
        # ambient module or mutable sibling in another checkout.
        owner._project_plan_contract = lambda: helper

        def rows(commit, paths, *, maximum_bytes):
            raw = git("--literal-pathspecs", "ls-tree", "-r", "-l", "-z", commit, "--", *paths,
                      limit=1048576).encode("utf-8")
            parsed = []
            position = 0
            total = 0
            while position < len(raw):
                match = _ROW.match(raw, position)
                if match is None:
                    raise ValueError("SOURCE_UNAVAILABLE")
                oid, length, path = match.groups()
                size = int(length)
                if not 1 <= size <= 262144:
                    raise ValueError("SOURCE_UNAVAILABLE")
                total += size
                if total > maximum_bytes or len(parsed) >= _MAX_INVENTORY:
                    raise ValueError("SOURCE_UNAVAILABLE")
                parsed.append((oid.decode("ascii"), size, path.decode("utf-8")))
                position = match.end()
            return parsed

        def batch(commit, members, *, maximum_bytes):
            if not members:
                return []
            stdin = "".join(oid + "\n" for oid, _, _ in members).encode("ascii")
            raw = git("cat-file", "--batch", input_bytes=stdin,
                      limit=maximum_bytes + len(members) * 100).encode("utf-8")
            captures = []
            position = 0
            for oid, size, path in members:
                header = (oid + " blob " + str(size) + "\n").encode("ascii")
                if raw[position:position + len(header)] != header:
                    raise ValueError("SOURCE_UNAVAILABLE")
                position += len(header)
                body = raw[position:position + size]
                position += size
                if len(body) != size or raw[position:position + 1] != b"\n":
                    raise ValueError("SOURCE_UNAVAILABLE")
                position += 1
                if hashlib.sha1(b"blob " + str(size).encode() + b"\0" + body).hexdigest() != oid:
                    raise ValueError("SOURCE_UNAVAILABLE")
                captures.append({"source": {"repository": _MACRO, "path": path, "commit": commit,
                                             "content_sha256": hashlib.sha256(body).hexdigest()},
                                 "raw_bytes": body})
            if position != len(raw):
                raise ValueError("SOURCE_UNAVAILABLE")
            return captures

        class Record:
            def __init__(self, raw):
                self.raw = raw
            def read_text(self, *, encoding):
                if encoding != "utf-8":
                    raise ValueError("SOURCE_UNAVAILABLE")
                return self.raw.decode("utf-8")

        all_decisions = batch(macro_sha, rows(macro_sha, ["agentos/decisions/"],
            maximum_bytes=_MAX_DECISION_BYTES), maximum_bytes=_MAX_DECISION_BYTES)
        decisions = []
        parsed_records = []
        for capture in all_decisions:
            record, _ = owner.parse_record(Record(capture["raw_bytes"]))
            if "project_plan_adoption" not in record:
                continue
            metadata = record["project_plan_adoption"]
            affects = record.get("affects")
            if not isinstance(metadata, dict) or not isinstance(affects, list):
                raise ValueError("SOURCE_UNAVAILABLE")
            if metadata.get("work_ref") != work_ref and work_ref not in affects:
                continue
            decisions.append(capture)
            retain('ADOPTION_DECISION',capture)
            parsed_records.append(record)
        if len(decisions) > 128:
            return missing()
        try:
            current = owner.select_project_plan_adoption(parsed_records, work_ref=work_ref)
        except ValueError:
            return project_captured_continuity(owner=owner, work_ref=work_ref,
                qualified_commits={_MACRO: macro_sha},
                workstream_capture={"source": workstream_source, "raw_bytes": workstream_bytes},
                decision_captures=decisions, proposal_captures=[], content_captures=[])

        ws, _ = owner.parse_record(Record(workstream_bytes))
        artifacts = ws.get("artifacts") or []
        if type(artifacts) is not list:
            raise ValueError("SOURCE_UNAVAILABLE")
        paths = []
        for entry in artifacts:
            if type(entry) is not str:
                raise ValueError("SOURCE_UNAVAILABLE")
            path = entry[6:] if entry.startswith("macro:") else entry
            if ":" in path or not path.endswith(".md"):
                continue  # No automatic cross-repository or URL source authority.
            # Validate the path grammar as data only; the placeholder hash is
            # never emitted as a captured source or a byte-correspondence claim.
            helper.validate_source_ref({"repository": _MACRO, "path": path,
                                        "commit": macro_sha, "content_sha256": "0" * 64})
            if path not in paths:
                paths.append(path)
        if len(paths) > 64:
            return missing()
        artifacts_captured = batch(macro_sha, rows(macro_sha, paths, maximum_bytes=8 * 1024 * 1024),
                                   maximum_bytes=8 * 1024 * 1024) if paths else []
        proposals = []
        for capture in artifacts_captured:
            retain('SELECTED_ARTIFACT',capture)
            try:
                header, _ = owner.parse_record(Record(capture["raw_bytes"]))
            except ValueError:
                continue  # Ordinary Markdown is not a typed proposal declaration.
            if header.get("schema") == "agentos.project_plan_proposal.v1":
                proposals.append(capture)
        if len(proposals) > 32:
            return missing()

        contents = []
        captured_keys = set()
        total_content = 0

        def resolve(ref):
            nonlocal total_content
            ref = helper.validate_source_ref(ref)
            if ref["repository"] != _MACRO:
                return  # Preserved as unresolved; no inferred Mastermind seal.
            identity = tuple(ref[k] for k in ("repository", "path", "commit", "content_sha256"))
            if identity in captured_keys:
                return
            captured_keys.add(identity)
            commit = ref["commit"]
            from control_plane.agentos_project_plan import ProjectPlanSourceUnavailable
            try:
                if commit != macro_sha:
                    git("merge-base", "--is-ancestor", commit, macro_sha, limit=4096)
                members = rows(commit, [ref["path"]], maximum_bytes=262144)
            except ProjectPlanSourceUnavailable:
                return  # Unresolved reference; retain the actual owner declaration.
            if len(members) != 1 or members[0][2] != ref["path"]:
                return
            captured = batch(commit, members, maximum_bytes=262144)[0]
            if captured["source"] != ref:
                raise ValueError("SOURCE_UNAVAILABLE")
            total_content += len(captured["raw_bytes"])
            if total_content > 2 * 1024 * 1024:
                raise ValueError("SOURCE_UNAVAILABLE")
            contents.append(captured)
            retain('ANCHORED_CONTENT',captured)

        if current:
            resolve(current["adoption"]["adopted_source"])
            if current["adoption"]["proposal_source"] is not None:
                resolve(current["adoption"]["proposal_source"])
        for capture in proposals:
            try:
                header, _ = owner.parse_project_plan_proposal(capture["raw_bytes"], work_ref=work_ref)
            except ValueError:
                continue
            resolve(header["base_source"])
        return project_captured_continuity(owner=owner, work_ref=work_ref,
            qualified_commits={_MACRO: macro_sha},
            workstream_capture={"source": workstream_source, "raw_bytes": workstream_bytes},
            decision_captures=decisions, proposal_captures=proposals, content_captures=contents)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, SyntaxError,
            UnicodeError, OverflowError, RecursionError):
        return missing()
