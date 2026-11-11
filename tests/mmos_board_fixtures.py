"""Board answers built from sanitized captures of the real server.

Each capture below came from an HTTP GET against the installed board
(loopback, 2026-11-11): free text replaced by placeholders, ids kept, no
credentials anywhere. Tests in this lane build the fake board's rows from
THESE shapes, so the code under test reads only fields the server actually
serves. The board never serves ``blockedByIssueIds`` on a GET — relations
arrive as ``blockedBy`` summaries — and comment rows carry
``authorAgentId`` (there is no nested ``author`` object and no ``authorId``).

Endpoints captured (all GET, one file each in ``mmos_board_fixtures/``):

===========================  ==================================================
file                         endpoint
===========================  ==================================================
issues_list.json             GET /api/companies/:cid/issues
issue_by_id.json             GET /api/issues/:id
parent_2ad0bf92….json        GET /api/issues/:id (a parent, blockedBy served)
parent_7897297c….json        GET /api/issues/:id (a parent, blockedBy served)
child_MAS-13.json            GET /api/issues/:id (an ask child)
child_MAS-8.json             GET /api/issues/:id (an ask child)
children_query.json          GET /api/companies/:cid/issues?parentId=:id
comments.json                GET /api/issues/:id/comments
parent_comments.json         GET /api/issues/:id/comments (a parent)
child_comments.json          GET /api/issues/:id/comments (a child)
interactions.json            GET /api/issues/:id/interactions
parent_interactions.json     GET /api/issues/:id/interactions (resolved row)
inbox_lite.json              GET /api/agents/:id/inbox (agent-scoped, 401 body)
agents_list.json             GET /api/companies/:cid/agents (400 body)
agent_by_id.json             GET /api/agents/:id
===========================  ==================================================
"""
import copy
import json
import os

_DIR = os.path.join(os.path.dirname(__file__), "mmos_board_fixtures")


def _load(name):
    with open(os.path.join(_DIR, name + ".json")) as fh:
        return json.load(fh)


ISSUE = _load("issue_by_id")
PARENT = _load("parent_2ad0bf92-e025-46bb-b315-dc7d0f99f693")
CHILD = _load("child_MAS-13")
_COMMENT = (_load("child_comments") or _load("comments"))[0]
_INTERACTION = _load("parent_interactions")[0]

_BLOCKED_BY_KEYS = ("activeRecoveryAction", "assigneeAgentId",
                    "assigneeUserId", "id", "identifier", "priority",
                    "scheduledRetry", "status", "title")


def served_issue(**over):
    """A row shaped exactly like GET /api/issues/:id serves it."""
    row = copy.deepcopy(ISSUE)
    row.update(over)
    return row


def served_parent(**over):
    row = copy.deepcopy(PARENT)
    row.update(over)
    return row


def served_child(**over):
    row = copy.deepcopy(CHILD)
    row.update(over)
    return row


def blocked_by(*rows):
    """A served blockedBy summary list — one summary per blocker row.

    The server projects exactly the _BLOCKED_BY_KEYS fields of each blocker
    issue; nothing else about the blocker reaches the parent's GET.
    """
    out = []
    for row in rows:
        summary = {key: row.get(key) for key in _BLOCKED_BY_KEYS}
        out.append(summary)
    return out


def served_comment(body, author_type="agent", author_agent_id=None, **over):
    """A comment row shaped like GET /api/issues/:id/comments serves them."""
    row = copy.deepcopy(_COMMENT)
    row.update({"body": body, "authorType": author_type,
                "authorAgentId": author_agent_id,
                "authorUserId": None})
    row.update(over)
    return row


def served_interaction(kind="request_confirmation", status="pending",
                       idem="", result=None, **over):
    row = copy.deepcopy(_INTERACTION)
    row["kind"] = kind
    row["status"] = status
    if idem:
        row["idempotencyKey"] = idem
    row["result"] = result
    row.update(over)
    return row
