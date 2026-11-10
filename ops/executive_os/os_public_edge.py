"""Inert, closed-route public OS edge staging; never installs or reloads Caddy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from integrations.mastermind_executive_app.os_assets import os_asset_mimes

HOST = "mcp.mastermind-x.com"
# Historical profiles are exact transition inputs, never caller-defined routes.
LEGACY_POST_ROUTES = ("/os/executive/context", "/os/executive/submit", "/os/executive/status")
SESSION_READ_POST_ROUTES = (
    "/os/executive/session/context", "/os/executive/session/reply",
    "/os/executive/session/references",
)
CONTROL_ROOM_ACTION_ROUTES = (
    "/workspace/control-room/open", "/workspace/control-room/bind",
    "/workspace/control-room/unbind", "/workspace/control-room/refresh-builds",
)
READER_POST_ROUTES = LEGACY_POST_ROUTES + SESSION_READ_POST_ROUTES
CONTROL_ROOM_POST_ROUTES = LEGACY_POST_ROUTES + CONTROL_ROOM_ACTION_ROUTES
# Keep the historical reader profile exact. Qualified Session SEND is a separate
# final-profile addition below; this does not change generic submit authority.
POST_ROUTES = READER_POST_ROUTES + CONTROL_ROOM_ACTION_ROUTES
LEGACY_GET_ROUTES = (
    "/os/", "/os/auth/callback", "/workspace/programs/current",
    "/workspace/work/current", "/workspace/mission/current",
    "/workspace/mission/v3/current", "/workspace/result/current",
    "/workspace/window/current",
)
CONTROL_ROOM_LEGACY_GET_ROUTES = LEGACY_GET_ROUTES + (
    "/workspace/plan/current", "/workspace/operator/activity/current",
)
READER_GET_ROUTES = CONTROL_ROOM_LEGACY_GET_ROUTES + (
    "/workspace/result-references/current",
)
CONTROL_ROOM_READ_ROUTES = (
    "/workspace/control-room/state/current",
    "/workspace/control-room/discover/current",
    "/workspace/mission/v4/current",
)
CONTROL_ROOM_GET_ROUTES = CONTROL_ROOM_LEGACY_GET_ROUTES + CONTROL_ROOM_READ_ROUTES
COMPOSED_GET_ROUTES = READER_GET_ROUTES + CONTROL_ROOM_READ_ROUTES
FABRIC_READ_ROUTES = ("/workspace/fabric/catalog/current", "/workspace/fabric/status/current")
PRE_PROJECT_PLAN_GET_ROUTES = COMPOSED_GET_ROUTES + FABRIC_READ_ROUTES
PRE_PROJECT_JOURNAL_GET_ROUTES = PRE_PROJECT_PLAN_GET_ROUTES + ("/workspace/project-plan/current",)
PRE_AUTONOMY_GET_ROUTES = PRE_PROJECT_JOURNAL_GET_ROUTES + ("/workspace/project-journal/current",)
PRE_PROJECT_SESSION_GET_ROUTES = PRE_AUTONOMY_GET_ROUTES + ("/workspace/autonomy/current",)
PRE_DIRECTION_GET_ROUTES = PRE_PROJECT_SESSION_GET_ROUTES + ("/workspace/project-session/current",)
PRE_PROJECT_ADMISSION_GET_ROUTES = PRE_DIRECTION_GET_ROUTES + ("/workspace/resources/capacity/current", "/workspace/project-direction/current")
PRE_PROJECT_ADMISSION_POST_ROUTES = POST_ROUTES
PROJECT_ADMISSION_GET_ROUTES = ("/workspace/project-admission/current", "/workspace/project-admission/operation")
PROJECT_ADMISSION_POST_ROUTES = ("/workspace/project-admission/pause", "/workspace/project-admission/resume")
PRE_ARCHIVE_GET_ROUTES = PRE_PROJECT_ADMISSION_GET_ROUTES + PROJECT_ADMISSION_GET_ROUTES
PRE_PROJECT_KNOWLEDGE_GET_ROUTES = PRE_ARCHIVE_GET_ROUTES + ("/workspace/projects/archive/current",)
PROJECT_KNOWLEDGE_GET_ROUTES = ("/workspace/project-knowledge/current", "/workspace/project-memory/current", "/workspace/project-source/current")
GET_ROUTES = PRE_PROJECT_KNOWLEDGE_GET_ROUTES + PROJECT_KNOWLEDGE_GET_ROUTES
POST_ROUTES = PRE_PROJECT_ADMISSION_POST_ROUTES + PROJECT_ADMISSION_POST_ROUTES
PRE_SOURCE_CONTEXT_GET_ROUTES = GET_ROUTES
SOURCE_CONTEXT_GET_ROUTES = PRE_SOURCE_CONTEXT_GET_ROUTES + ("/workspace/source-operation/context",)
SOURCE_OPERATION_GET_ROUTE = ("/workspace/source-operation/operation",)
GET_ROUTES = SOURCE_CONTEXT_GET_ROUTES + SOURCE_OPERATION_GET_ROUTE
# Dedicated source-operation command POSTs. Source commands are separately
# granted downstream; these edge paths confer no authority of their own and
# stay out of POST_ROUTES so the legacy branch matcher is never widened.
SOURCE_POST_ROUTES = (
    "/workspace/source-operation/prepare", "/workspace/source-operation/submit",
    "/workspace/source-operation/reconcile", "/workspace/source-operation/advance",
)
# The legacy Executive/session/CCR branches and POST /mcp keep exactly 64000
# bytes; only the dedicated source branch admits the larger legitimate
# 32KiB UTF-8 text uploads with JSON escaping.
SOURCE_MAX_BODY = 98304
# Accepted project controls extend the current exact source-operation profile.
# Keep each predecessor's complete GET/POST pair; route presence grants nothing.
PRE_PROJECT_INSTRUCTIONS_GET_ROUTES = GET_ROUTES
PRE_INSTRUCTION_ADMISSION_GET_ROUTES = PRE_PROJECT_INSTRUCTIONS_GET_ROUTES + ("/workspace/project-instructions/current",)
PRE_INSTRUCTION_ADMISSION_POST_ROUTES = POST_ROUTES
PRE_PROJECT_ACCESS_GET_ROUTES = PRE_INSTRUCTION_ADMISSION_GET_ROUTES + (
    "/workspace/instruction-admission/current", "/workspace/instruction-admission/operation")
GET_ROUTES = PRE_PROJECT_ACCESS_GET_ROUTES + ("/workspace/project-access/current",)
POST_ROUTES = PRE_INSTRUCTION_ADMISSION_POST_ROUTES + ("/workspace/instruction-admission/pause",)

# The qualified first release is a complete exact predecessor of this cut.
PRE_MISSION_RESULT_GET_ROUTES = GET_ROUTES
PRE_MISSION_RESULT_POST_ROUTES = POST_ROUTES
MISSION_RESULT_GET_ROUTES = PRE_MISSION_RESULT_GET_ROUTES + ("/workspace/mission-result/current",)

PRE_JOURNEY_GET_ROUTES = GET_ROUTES
PRE_JOURNEY_POST_ROUTES = POST_ROUTES
GET_ROUTES = PRE_JOURNEY_GET_ROUTES + ("/workspace/source-operation/options",)
PROJECT_PLANNING_POST_ROUTES = tuple("/os/executive/project-planning/"+name for name in ("submit","status","result","consume"))
POST_ROUTES = PRE_JOURNEY_POST_ROUTES + PROJECT_PLANNING_POST_ROUTES
PRE_PLAN_PROPOSAL_GET_ROUTES = GET_ROUTES
PRE_PLAN_PROPOSAL_POST_ROUTES = POST_ROUTES
PROJECT_PLANNING_POST_ROUTES += ("/os/executive/project-planning/prepare_proposal",)
POST_ROUTES = PRE_PLAN_PROPOSAL_POST_ROUTES + ("/os/executive/project-planning/prepare_proposal",)
PRE_CONVERSATION_READ_GET_ROUTES = GET_ROUTES
PRE_CONVERSATION_READ_POST_ROUTES = POST_ROUTES
PROJECT_CONVERSATION_READ_POST_ROUTES = (
    "/os/executive/session/history-context", "/os/executive/session/conversations",
    "/os/executive/session/conversation-read", "/os/executive/session/fresh-conversations",
    "/os/executive/session/fresh-conversation-read",
)
FRESH_CONVERSATION_POST_ROUTES = (
    "/os/executive/conversation/preview", "/os/executive/conversation/create",
    "/os/executive/conversation/status", "/os/executive/conversation/read",
    "/os/executive/conversation/consume", "/os/executive/conversation/turn",
    "/os/executive/conversation/turn/status", "/os/executive/conversation/turn/read",
    "/os/executive/conversation/consume/status", "/os/executive/conversation/turn/preview",
)
GET_ROUTES = PRE_CONVERSATION_READ_GET_ROUTES + ("/workspace/resources/host-observation/current",)
POST_ROUTES = PRE_CONVERSATION_READ_POST_ROUTES + PROJECT_CONVERSATION_READ_POST_ROUTES + FRESH_CONVERSATION_POST_ROUTES

PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES = GET_ROUTES
PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES = POST_ROUTES
GET_ROUTES = PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES + ("/workspace/mission-result/current",)

# Fixed zero-selector privacy identity read; preserve the complete predecessor.
PRE_NATIVE_DRAFT_GET_ROUTES = GET_ROUTES
PRE_NATIVE_DRAFT_POST_ROUTES = POST_ROUTES
GET_ROUTES = PRE_NATIVE_DRAFT_GET_ROUTES + ("/workspace/native-draft-identity/current",)

# One separately qualified existing-session write, with its complete incumbent
# profile retained. Authentication, target and original-key authority remain
# with the existing Session owner; generic submit is unchanged.
PRE_NATIVE_SESSION_SEND_GET_ROUTES = GET_ROUTES
PRE_NATIVE_SESSION_SEND_POST_ROUTES = POST_ROUTES
POST_ROUTES = PRE_NATIVE_SESSION_SEND_POST_ROUTES + ("/os/executive/session/send",)

# Protected f1950e9f: fixed secret-free role metadata READ, with no enrollment
# or provider operation. Preserve its complete native-SEND predecessor.
PRE_BYOK_ROLES_GET_ROUTES = GET_ROUTES
PRE_BYOK_ROLES_POST_ROUTES = POST_ROUTES
BYOK_READ_ROUTES = ("/workspace/byok/roles/current",)
GET_ROUTES = PRE_BYOK_ROLES_GET_ROUTES + BYOK_READ_ROUTES

# Project team launch and retained results extend the qualified parent profile.
# Their existing downstream Executive/Workspace owners still authorize each call.
PRE_PROJECT_EXECUTION_GET_ROUTES = GET_ROUTES
PRE_PROJECT_EXECUTION_POST_ROUTES = POST_ROUTES
PROJECT_EXECUTION_POST_ROUTES = tuple("/os/executive/project-execution/" + name
    for name in ("preview", "submit", "status")) + (
    "/os/executive/session/project-executions", "/os/executive/session/project-execution-read")
# The published project-only source at 2cf4c5e6 predates native SEND and BYOK.
# Retain that exact complete pair, not arbitrary mixtures of the three groups.
PROJECT_EXECUTION_PRE_MERGE_GET_ROUTES = PRE_NATIVE_SESSION_SEND_GET_ROUTES
PROJECT_EXECUTION_PRE_MERGE_POST_ROUTES = PRE_NATIVE_SESSION_SEND_POST_ROUTES + PROJECT_EXECUTION_POST_ROUTES
POST_ROUTES = PRE_PROJECT_EXECUTION_POST_ROUTES + PROJECT_EXECUTION_POST_ROUTES

# Native result, consumption and governed correction retain their existing
# authenticated backend owners. Preserve the complete current predecessor;
# these three paths extend only the normal bounded POST branch.
PRE_DIRECT_NATIVE_GET_ROUTES = GET_ROUTES
PRE_DIRECT_NATIVE_POST_ROUTES = POST_ROUTES
DIRECT_NATIVE_POST_ROUTES = (
    "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
    "/os/executive/direct-native/correction",
)
POST_ROUTES = PRE_DIRECT_NATIVE_POST_ROUTES + DIRECT_NATIVE_POST_ROUTES
PRE_COMPANY_PRIORITIES_POST_ROUTES = POST_ROUTES
POST_ROUTES += ("/os/executive/company-priorities",)

# Two fixed metadata-only READs use the existing per-resource auth owners.
# Preserve both exact predecessor profiles; partial mixes remain refused.
PRE_AUTHORIZATION_IDENTITY_GET_ROUTES = GET_ROUTES
AUTHORIZATION_IDENTITY_GET_ROUTES = (
    "/workspace/native-authorization-identity/acquisition/current",
    "/workspace/native-authorization-identity/content/current",
)
GET_ROUTES = PRE_AUTHORIZATION_IDENTITY_GET_ROUTES + AUTHORIZATION_IDENTITY_GET_ROUTES

# Preserve exactly the profiles admitted by the predecessor contracts.
# Both publication phases emit GET_ROUTES/POST_ROUTES; arbitrary mixtures,
# partial upgrades, wildcards and extra paths cannot become transition inputs.
# The source-context profile is the installed predecessor of GET_ROUTES and
# remains an exact legacy transition input.
TRANSITION_ROUTE_PROFILES = (
    (LEGACY_GET_ROUTES, LEGACY_POST_ROUTES),
    (LEGACY_GET_ROUTES, READER_POST_ROUTES),
    (READER_GET_ROUTES, LEGACY_POST_ROUTES),
    (READER_GET_ROUTES, READER_POST_ROUTES),
    (CONTROL_ROOM_LEGACY_GET_ROUTES, LEGACY_POST_ROUTES),
    (CONTROL_ROOM_GET_ROUTES, CONTROL_ROOM_POST_ROUTES),
    (COMPOSED_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_PLAN_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_JOURNAL_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_AUTONOMY_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_SESSION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_DIRECTION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_ADMISSION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (PRE_ARCHIVE_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_KNOWLEDGE_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_SOURCE_CONTEXT_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (SOURCE_CONTEXT_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_INSTRUCTIONS_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_INSTRUCTION_ADMISSION_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_PROJECT_ACCESS_GET_ROUTES, PRE_JOURNEY_POST_ROUTES),
    (PRE_JOURNEY_GET_ROUTES, PRE_JOURNEY_POST_ROUTES),
    (MISSION_RESULT_GET_ROUTES, PRE_MISSION_RESULT_POST_ROUTES),
    (PRE_PLAN_PROPOSAL_GET_ROUTES, PRE_PLAN_PROPOSAL_POST_ROUTES),
    (PRE_CONVERSATION_READ_GET_ROUTES, PRE_CONVERSATION_READ_POST_ROUTES),
    (PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES, PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES),
    (PRE_NATIVE_DRAFT_GET_ROUTES, PRE_NATIVE_DRAFT_POST_ROUTES),
    (PRE_NATIVE_SESSION_SEND_GET_ROUTES, PRE_NATIVE_SESSION_SEND_POST_ROUTES),
    (PRE_BYOK_ROLES_GET_ROUTES, PRE_BYOK_ROLES_POST_ROUTES),
    (PRE_PROJECT_EXECUTION_GET_ROUTES, PRE_PROJECT_EXECUTION_POST_ROUTES),
    (PROJECT_EXECUTION_PRE_MERGE_GET_ROUTES, PROJECT_EXECUTION_PRE_MERGE_POST_ROUTES),
    (PRE_DIRECT_NATIVE_GET_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES),
    (PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, PRE_COMPANY_PRIORITIES_POST_ROUTES),
    (PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, POST_ROUTES),
    (GET_ROUTES, POST_ROUTES),
)

# Retain the published reader-profile names for existing callers.
INCUMBENT_GET_ROUTES = READER_GET_ROUTES
INCUMBENT_POST_ROUTES = READER_POST_ROUTES
# Public MCP entrypoint (#1656). Two dedicated branches, kept out of GET_ROUTES
# so a previously installed 3-branch config stays plannable: the RFC 9728
# protected-resource metadata document and the Streamable HTTP POST. The /mcp
# branch presents a loopback Host because the gateway's SDK transport fence
# admits only loopback hosts; Caddy still performs no authentication.
MCP_METADATA_ROUTE = "/.well-known/oauth-protected-resource/mcp"
MCP_ROUTES = ("/mcp",)
# One exact COO route pair (#2120). The COO metadata document is a distinct
# RFC 9728 protected resource at its own fixed path, and the COO transport is a
# distinct query-free Streamable HTTP POST. Both extend the same two existing
# exact method branches: the metadata branch keeps the public Host and the
# transport branch keeps the gateway's loopback Host and its 64000-byte cap.
# The public edge serves the paths only; the receiving owner still has to
# publish the real COO resource/issuer/scopes at the metadata path and to keep
# rejecting the public CEO audience there. Nothing here asserts enrollment.
MCP_COO_METADATA_ROUTE = "/.well-known/oauth-protected-resource/mcp/coo"
MCP_COO_ROUTE = "/mcp/coo"
# The two coherent public-MCP profiles. The CEO-only pair is the exact legacy
# transition input; the complete CEO+COO pair is what the renderer emits.
MCP_METADATA_ROUTES = (MCP_METADATA_ROUTE,)
COMPLETE_MCP_METADATA_ROUTES = MCP_METADATA_ROUTES + (MCP_COO_METADATA_ROUTE,)
COMPLETE_MCP_ROUTES = MCP_ROUTES + (MCP_COO_ROUTE,)
MCP_MAX_BODY = 64000
_TEMPLATE = Path(__file__).with_name("os_public_edge.caddy.template")


def asset_routes(manifest: object) -> tuple[str, ...]:
    if (type(manifest) is not dict or set(manifest) != {"schema", "files"}
            or manifest["schema"] != "mastermind.os_assets.v1"
            or type(manifest["files"]) is not list):
        raise ValueError("OS edge manifest refused")
    files = manifest["files"]
    if any(type(item) is not dict or set(item) != {"path", "byte_count", "sha256", "mime"}
           or type(item["path"]) is not str for item in files):
        raise ValueError("OS edge manifest entry refused")
    # One owner of the 3/9-file topology, exact names and MIME types. In
    # particular, no arbitrary path can become executable Caddy syntax.
    mimes = os_asset_mimes([item["path"] for item in files])
    for item in files:
        if (type(item["byte_count"]) is not int or not 0 < item["byte_count"] <= 4 * 1024 * 1024
                or type(item["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or item["mime"] != mimes[item["path"]]):
            raise ValueError("OS edge manifest metadata refused")
    return tuple(sorted("/os/" if item["path"] == "index.html" else "/os/" + item["path"] for item in files))


def render(manifest: object, relay_port: int) -> str:
    if type(relay_port) is not int or not 49152 <= relay_port <= 50200:
        raise ValueError("OS edge relay port refused")
    routes = asset_routes(manifest)
    template = _TEMPLATE.read_text(encoding="utf-8")
    # The fixed GET matcher must list exactly GET_ROUTES in order, so a route
    # admitted in metadata but missing from the template cannot pass render
    # (the previously missing source-operation context read is corrected here).
    # The two public-MCP matchers are checked as complete intended path lists,
    # not as placeholder counts: the metadata list and the transport list must
    # each appear exactly once, in full, so a template that still carries only
    # the CEO-only pair, or that widens either list, cannot be rendered.
    if (template.count("__ASSET_PATHS__") != 1
            or template.count("__RELAY_PORT__") != 5
            or template.count("path " + " ".join(GET_ROUTES) + " __ASSET_PATHS__\n") != 1
            or template.count("path " + " ".join(POST_ROUTES) + "\n") != 1
            or template.count("path " + " ".join(SOURCE_POST_ROUTES) + "\n") != 1
            or template.count("path " + " ".join(COMPLETE_MCP_METADATA_ROUTES) + "\n") != 1
            or template.count("path " + " ".join(COMPLETE_MCP_ROUTES) + "\n") != 1
            or template.count("max_size 98304") != 1
            or template.count("max_size 64KB") != 2):
        raise ValueError("OS edge template differs")
    return template.replace("__ASSET_PATHS__", " ".join(routes)).replace("__RELAY_PORT__", str(relay_port))


def stage(*, manifest: object, relay_port: int, output: Path) -> dict:
    content = render(manifest, relay_port).encode("utf-8")
    parent = output.parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022 or parent.resolve() != parent:
        raise ValueError("OS edge output directory refused")
    # Exclusive creation preserves any existing artifact, including dangling
    # symlinks. No replace/reload is part of this inert staging capability.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # A failed write stays visible for reconciliation; never silently
        # delete an artifact after an uncertain filesystem effect.
        raise
    return {
        "schema": "mastermind.os_public_edge.stage.v1",
        "sha256": hashlib.sha256(content).hexdigest(),
        "relay_port": relay_port,
        "routes": {"get": sorted(set(GET_ROUTES) | set(asset_routes(manifest))),
                   "post": list(POST_ROUTES),
                   "source_post": list(SOURCE_POST_ROUTES)},
        "mcp": {"get": list(COMPLETE_MCP_METADATA_ROUTES),
                "post": list(COMPLETE_MCP_ROUTES)},
        "installed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--relay-port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from ops.executive_os.executive_mcp_entry import build_os_asset_manifest
    actual = build_os_asset_manifest(args.source)
    supplied = json.loads((args.source / "app/mastermind_os/dist/asset-manifest.json").read_bytes())
    if supplied != actual:
        raise ValueError("OS edge source manifest differs from built bytes")
    print(json.dumps(stage(manifest=actual, relay_port=args.relay_port, output=args.out), sort_keys=True))


if __name__ == "__main__":
    main()
