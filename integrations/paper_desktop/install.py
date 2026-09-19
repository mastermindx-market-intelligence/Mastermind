"""Stage project-scoped MCP configurations without changing live provider homes.

No downloads, purchases, credential access, permission changes or process restarts.
Existing files are never overwritten. Production Executive profiles remain separate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


PRIVATE_DIR_MODE = 0o700


def configs(python: str, server: str, allow_write: bool):
    args = [server] + (["--allow-write"] if allow_write else [])
    entry = {"command": python, "args": args}
    codex = "[mcp_servers.mastermindPaper]\ncommand = " + json.dumps(python) + "\nargs = " + json.dumps(args) + "\n"
    return {
        "claude-project.mcp.json": json.dumps({"mcpServers": {"mastermindPaper": dict(entry, type="stdio")}}, indent=2) + "\n",
        "cursor.mcp.json": json.dumps({"mcpServers": {"mastermindPaper": entry}}, indent=2) + "\n",
        "codex.config.toml": codex,
        "vscode.mcp.json": json.dumps({"servers": {"mastermindPaper": dict(entry, type="stdio")}}, indent=2) + "\n",
        "opencode.json": json.dumps({"mcp": {"mastermindPaper": {"type": "local", "command": [python] + args, "enabled": True}}}, indent=2) + "\n",
    }


def enrollment_text(workspace: Path) -> str:
    project = json.dumps(str(workspace))
    return (
        "# Paper client enrollment\n\n"
        "The staged client files are inert until each client trusts/approves this workspace.\n"
        "Do not weaken global sandboxing or auto-approve unrelated MCP servers.\n\n"
        "## Codex\n\n"
        "Project-local .codex/config.toml is loaded only for trusted projects. Add this exact\n"
        "workspace entry to the user-level ~/.codex/config.toml after inspecting the workspace:\n\n"
        "    [projects." + project + "]\n"
        "    trust_level = \"trusted\"\n\n"
        "Then run codex mcp list from this workspace. If Codex itself cannot authenticate,\n"
        "run codex login status; a stale stored login is repaired by codex logout followed\n"
        "by an interactive codex login. Authentication is a user/account ceremony, not an\n"
        "MCP bridge permission.\n\n"
        "## Claude Code\n\n"
        "Run claude mcp list from this workspace. A project MCP may show Pending approval;\n"
        "launch interactive claude in this workspace and approve only mastermindPaper.\n\n"
        "Re-run each client MCP list after approval. A listed server proves configuration\n"
        "visibility, not a successful Paper read/edit or Executive worker grant.\n"
    )

def stage(destination: Path, python: str, allow_write=False):
    if not Path(python).is_absolute() or not Path(python).is_file():
        raise ValueError("An existing absolute Python executable is required")
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists: refuse overwrite; inspect the existing installation")
    source = Path(__file__).resolve().parent
    # Only user-reviewed source is staged. No runtime files or provider credentials.
    files = {name: (source / name).read_bytes() for name in ("bridge.py", "mcp_server.py", "requirements-mcp.txt")}
    (destination / "runtime").mkdir(mode=PRIVATE_DIR_MODE, parents=True)
    destination.chmod(PRIVATE_DIR_MODE)
    for name, data in files.items():
        path = destination / "runtime" / name
        path.write_bytes(data)
        path.chmod(0o600)
    config_root = destination / "client-configs"
    config_root.mkdir(mode=PRIVATE_DIR_MODE)
    for name, text in configs(python, str(destination / "runtime" / "mcp_server.py"), allow_write).items():
        (config_root / name).write_text(text)
        (config_root / name).chmod(0o600)
    # These are real project-scoped config paths in a NEW, isolated workspace.
    # No global home or currently running worker is reconfigured.
    workspace = destination / "workspace"
    workspace.mkdir(mode=PRIVATE_DIR_MODE)
    names = {"claude-project.mcp.json": ".mcp.json", "cursor.mcp.json": ".cursor/mcp.json",
             "codex.config.toml": ".codex/config.toml", "vscode.mcp.json": ".vscode/mcp.json",
             "opencode.json": "opencode.json"}
    for template, relative in names.items():
        target = workspace / relative
        target.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        target.write_text((config_root / template).read_text())
        target.chmod(0o600)
    (workspace / "AGENTS.md").write_text(
        "# Paper design workspace\n\n"
        "Use mastermindPaper MCP after current client approval. Inspect and read the catalog first.\n"
        "Only one designer owns the active desktop file; no subagent write fan-out.\n"
        "Snapshot hashes are observations, not revisions or permission. Preserve the intended file.\n"
        "Stop on EFFECT_UNKNOWN and inspect the original edit; never replay blindly.\n"
        "Do not delete, export to arbitrary host paths, purchase, log into accounts, or deploy code.\n"
        "Get a screenshot and JSX after design approval. Implementation/browser proof is separate.\n"
    )
    skill_source = source.parents[1] / "skills" / "paper-design-workflow"
    if skill_source.is_dir():
        import shutil
        skill_target = destination / "skills" / "paper-design-workflow"
        shutil.copytree(skill_source, skill_target)
        for namespace in (".agents", ".claude"):
            link = workspace / namespace / "skills" / "paper-design-workflow"
            link.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
            link.symlink_to("../../../skills/paper-design-workflow", target_is_directory=True)
    enrollment = destination / "ENROLLMENT.md"
    enrollment.write_text(enrollment_text(workspace))
    enrollment.chmod(0o600)
    receipt = {"state": "STAGED_NOT_ENROLLED", "path": str(destination), "allow_write": allow_write,
               "sdk_installed_by_this_script": False, "provider_homes_modified": False,
               "executive_production_armed": False,
               "client_enrollment": {"codex": {"project_trust_required": True, "verify": "codex mcp list"},
                                     "claude": {"project_mcp_approval_required": True, "verify": "claude mcp list"}},
               "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
               "next_action": "Follow ENROLLMENT.md in an authorized client, then inspect Paper; provider login/approval stays a human gate."}
    (destination / "INSTALLATION.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (destination / "INSTALLATION.json").chmod(0o600)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--allow-write", action="store_true")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    if not a.apply:
        print(json.dumps({"state": "DRY_RUN", "destination": str(a.destination),
                          "configs": configs(a.python, str(a.destination / "runtime/mcp_server.py"), a.allow_write)}))
        return 0
    try:
        print(json.dumps(stage(a.destination, a.python, a.allow_write), indent=2))
    except (ValueError, OSError) as exc:
        print(json.dumps({"state": "STAGING_REFUSED", "detail": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
