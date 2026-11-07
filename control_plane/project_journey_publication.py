"""Closed CREATE/PLAN path law for the existing actual-Event read proof.

This validates DATA only. The caller must already have re-read the genuine
SourceOperationEvents original/terminal receipt under its current READ guard.
It neither issues a proof nor substitutes for the actual Git ancestry and
current postimage checks performed by CanonicalProjectDataMode.
"""
from __future__ import annotations

import re


def validate_project_journey_publication(lookup, images, sources):
    """Return the exact qualified path set, or refuse; no generic allowance."""
    def fail():
        raise ValueError("PROJECT_JOURNEY_PUBLICATION_INVALID")

    budget = [128]
    def plain(value, depth=0):
        budget[0] -= 1
        if budget[0] < 0 or depth > 4:
            fail()
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                fail()
            for child in value.values():
                plain(child, depth + 1)
        elif type(value) is list:
            for child in value:
                plain(child, depth + 1)
        elif value is not None and type(value) not in (str, int, bool):
            fail()
    for value in (lookup, images, sources):
        plain(value)

    if (type(lookup) is not dict
            or set(lookup) != {"schema", "action", "request_id", "work_ref"}
            or lookup["schema"] != "mastermind.workspace_source_operation_lookup.v1"):
        fail()
    action, request_id, work_ref = (lookup[key] for key in ("action", "request_id", "work_ref"))
    prefixes = {"publish_project_proposal": "mmos-project-create-",
                "publish_project_plan_proposal": "mmos-project-plan-proposal-"}
    if (type(action) is not str or action not in prefixes
            or type(request_id) is not str
            or re.fullmatch(re.escape(prefixes[action]) + r"[a-f0-9]{40}", request_id) is None
            or type(work_ref) is not str
            or re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*", work_ref) is None
            or not 5 <= len(work_ref) <= 67):
        fail()
    ws = "agentos/workstreams/WS-" + work_ref[3:] + ".md"
    proposal = "research/project-plans/PLAN-" + work_ref[3:] + "-" + request_id[-40:] + ".md"
    expected = {ws} if action == "publish_project_proposal" else {ws, proposal}
    if (type(images) is not list or type(sources) is not list
            or len(images) != len(expected) or len(sources) != len(expected)):
        fail()
    image_map, source_map, commits = {}, {}, set()
    for image in images:
        if (type(image) is not dict
                or set(image) != {"path", "content_sha256", "expected_preimage_sha256"}
                or type(image["path"]) is not str or image["path"] not in expected
                or image["path"] in image_map
                or type(image["content_sha256"]) is not str
                or re.fullmatch(r"[a-f0-9]{64}", image["content_sha256"]) is None):
            fail()
        before = image["expected_preimage_sha256"]
        if action == "publish_project_proposal" or image["path"] == proposal:
            if before is not None:
                fail()
        elif type(before) is not str or re.fullmatch(r"[a-f0-9]{64}", before) is None:
            fail()
        image_map[image["path"]] = image["content_sha256"]
    for source in sources:
        if (type(source) is not dict
                or set(source) != {"repository", "commit", "path", "content_sha256"}
                or source["repository"] != "macro"
                or type(source["commit"]) is not str
                or re.fullmatch(r"[a-f0-9]{40}", source["commit"]) is None
                or type(source["path"]) is not str or source["path"] not in expected
                or source["path"] in source_map
                or type(source["content_sha256"]) is not str
                or re.fullmatch(r"[a-f0-9]{64}", source["content_sha256"]) is None):
            fail()
        source_map[source["path"]] = source["content_sha256"]
        commits.add(source["commit"])
    if image_map != source_map or set(image_map) != expected or len(commits) != 1:
        fail()
    return frozenset(expected)
