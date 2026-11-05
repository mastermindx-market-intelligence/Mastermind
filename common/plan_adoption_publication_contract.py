"""Closed final ADOPT postimage facts; dictionaries grant no authority.

Actual original Events and the fixed Git owner must separately prove the
ADOPTION phase/default bytes. Candidate publication is never accepted here.
"""
import re


def _fail():
    raise ValueError("INVALID_PLAN_ADOPTION_PUBLICATION")


def validate_adoption_sources(selection, sources):
    if (type(selection) is not dict or set(selection) != {"action", "request_id", "work_ref"}
            or selection["action"] != "ADOPT_PLAN"
            or type(selection["request_id"]) is not str
            or re.fullmatch(r"mmos-project-adopt-[a-f0-9]{40}", selection["request_id"]) is None
            or type(selection["work_ref"]) is not str
            or re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*", selection["work_ref"]) is None
            or not 2 <= len(selection["work_ref"][3:]) <= 64
            or type(sources) is not list or len(sources) not in (2, 3)):
        _fail()
    ws = "agentos/workstreams/WS-" + selection["work_ref"][3:] + ".md"
    decision = "agentos/decisions/DEC-PLAN-ADOPTION-" + selection["request_id"][-40:].upper() + ".md"
    paths, commits = set(), set()
    for source in sources:
        if (type(source) is not dict or set(source) != {"repository", "commit", "path", "content_sha256"}
                or source["repository"] != "macro" or type(source["commit"]) is not str
                or re.fullmatch(r"[a-f0-9]{40}", source["commit"]) is None
                or type(source["content_sha256"]) is not str
                or re.fullmatch(r"[a-f0-9]{64}", source["content_sha256"]) is None
                or type(source["path"]) is not str or source["path"] in paths):
            _fail()
        path = source["path"]
        if path not in (ws, decision):
            if (re.fullmatch(r"agentos/decisions/DEC-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md", path) is None
                    or not 2 <= len(path[len("agentos/decisions/DEC-"):-3]) <= 128):
                _fail()
        paths.add(path); commits.add(source["commit"])
    if not {ws, decision} <= paths or len(commits) != 1:
        _fail()
    return frozenset(paths)


def validate_adoption_publication(selection, images, sources):
    paths = validate_adoption_sources(selection, sources)
    if type(images) is not list or len(images) != len(sources):
        _fail()
    decision = "agentos/decisions/DEC-PLAN-ADOPTION-" + selection["request_id"][-40:].upper() + ".md"
    planned = {}
    for image in images:
        if (type(image) is not dict or set(image) != {"path", "content_sha256", "expected_preimage_sha256"}
                or type(image["path"]) is not str or image["path"] not in paths or image["path"] in planned
                or type(image["content_sha256"]) is not str
                or re.fullmatch(r"[a-f0-9]{64}", image["content_sha256"]) is None):
            _fail()
        before = image["expected_preimage_sha256"]
        if image["path"] == decision:
            if before is not None: _fail()
        elif type(before) is not str or re.fullmatch(r"[a-f0-9]{64}", before) is None:
            _fail()
        planned[image["path"]] = image["content_sha256"]
    if planned != {source["path"]: source["content_sha256"] for source in sources}:
        _fail()
    return paths
