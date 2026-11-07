"""Operation-specific project selection; shared Workspace v3 stays unchanged.

A rootless selection names a canonical authored project. An optional explicit
root additionally requires retained membership and immutable creation proof in
the authenticated owner. Neither shape grants an action or creates a root.
"""
from common import executive_workspace_contract as workspace
from common.workspace_project_plan_contract import validate_selection as project_selection
import re

_COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def selection(value, *, command=False):
    if type(value) is not dict:
        raise ValueError("invalid_input")
    base = {"work_ref", "command_id"} if command else {"work_ref"}
    if set(value) not in (base, base | {"root_job_id"}):
        raise ValueError("invalid_input")
    try:
        project_selection({"work_ref": value["work_ref"]})
    except ValueError:
        raise ValueError("invalid_input") from None
    if "root_job_id" in value:
        workspace.v3_selection({"work_ref": value["work_ref"], "root_job_id": value["root_job_id"]})
    if command and (type(value["command_id"]) is not str or _COMMAND.fullmatch(value["command_id"]) is None):
        raise ValueError("invalid_input")
    return dict(value)
