"""OHF-P1A production-inert Codex minimal-surface spike.

Does not modify the accepted P0 probe.  Does not copy, symlink, read, or print
auth.json.  Live mode requires an already-authenticated dedicated CODEX_HOME.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts.ohf.fixtures import (
    OHF_PROBE_MCP_SERVER,
    OHF_PROBE_MCP_TOOL,
    OHF_PROBE_SKILL_ACK,
    OHF_PROBE_SKILL_NAME,
)
from scripts.ohf.laboratory import (
    AppServerClient,
    JsonRpcError,
    Laboratory,
    REPO_ROOT,
    default_user_codex_home,
    inspect_codex_home,
)
from scripts.ohf.p1a_capability_policy import (
    CLASS_ALLOWED_AMBIENT,
    CLASS_FORBIDDEN,
    CLASS_REQUIRED,
    CLASS_UNCLASSIFIED,
    classify_observed,
    render_minimal_surface_config,
    write_profile_fail_closed,
)
from scripts.ohf.protocol import (
    extra_roots_set_params,
    mcp_server_names,
    mcp_tool_names,
    parse_config_read,
    skill_names,
    skills_list_params,
)
from scripts.ohf.redaction import evidence_contains_secret, redact_evidence, redact_text

CLIENT_INFO = {
    "name": "mastermind_ohf_p1a",
    "title": "Mastermind OHF-P1A minimal-surface spike",
    "version": "0.1.0",
}
P0_AMBIENT_SKILL_BASELINE = (
    "github:gh-address-comments",
    "github:gh-fix-ci",
    "github:github",
    "github:yeet",
    "imagegen",
    "openai-docs",
    "plugin-creator",
    "plugin-management:plugin-management",
    "review-agent",
    "skill-creator",
    "skill-installer",
)
SCHEMA = "mastermind.ohf_p1a_minimal_surface/v1"


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "symlink": path.is_symlink()}
    st = path.stat()
    return {
        "present": True,
        "symlink": path.is_symlink(),
        "inode": st.st_ino,
        "mtime": int(st.st_mtime),
        "size": st.st_size,
        "mode": stat.S_IMODE(st.st_mode),
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes()) if path.is_file() else ""


def _try(client: AppServerClient, method: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any] | None:
    try:
        return client.request(method, params, timeout=timeout)
    except JsonRpcError as exc:
        return {"_error": redact_text(str(exc))}


def _initialize(client: AppServerClient) -> dict[str, Any]:
    result = client.request(
        "initialize",
        {"clientInfo": CLIENT_INFO, "capabilities": {"experimentalApi": True}},
    )
    client.notify("initialized", {})
    return result


def _bounded_turn(client: AppServerClient, thread_id: str, text: str) -> dict[str, Any]:
    result = client.request(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [{"type": "text", "text": text}],
            "cwd": str(Path(client.cwd)),
            "approvalPolicy": "never",
        },
        timeout=60.0,
    )
    try:
        completed = client.wait_notification("turn/completed", timeout=60.0)
    except JsonRpcError:
        completed = {}
    return {"result": result, "completed": completed}


def _argv(lab: Laboratory) -> list[str]:
    if lab.backend == "live":
        exe = shutil.which("codex")
        if not exe:
            raise FileNotFoundError("codex CLI is not installed")
        return [
            exe,
            "app-server",
            "-c",
            "features.apps=false",
            "-c",
            "skills.bundled.enabled=false",
        ]
    return [sys.executable, "-m", "scripts.ohf.fake_app_server"]


def _write_minimal_config(lab: Laboratory) -> str:
    python = shutil.which("python3") or shutil.which("python") or "python3"
    text = render_minimal_surface_config(
        model=lab.requested_model,
        mcp_command=python,
        mcp_args=["-m", "scripts.ohf.fixtures.ohf_probe_mcp"],
        mcp_cwd=str(REPO_ROOT),
    )
    lab.config_path.write_text(text, encoding="utf-8")
    if lab.backend == "live":
        dest = lab.live_codex_home() / "config.toml"
        dest.write_text(text, encoding="utf-8")
    return text


def run_minimal_surface(
    lab: Laboratory,
    *,
    original_config_bytes: bytes | None = None,
) -> dict[str, Any]:
    default_home = default_user_codex_home()
    default_auth_before = _file_meta(default_home / "auth.json")
    dedicated_auth_before = (
        _file_meta(lab.live_codex_home() / "auth.json") if lab.backend == "live" else {}
    )
    backup_bytes = original_config_bytes
    backup_hash = _sha256_bytes(backup_bytes) if backup_bytes is not None else ""
    dedicated_config: Path | None = None
    if lab.backend == "live":
        dedicated_config = lab.live_codex_home() / "config.toml"

    evidence: dict[str, Any] = {
        "schema_version": SCHEMA,
        "backend": lab.backend,
        "codex_version": "codex-cli 0.147.0",
        "apps_disable_setting": "features.apps=false",
        "bundled_skills_disable_setting": "skills.bundled.enabled=false",
        "auth_isolation": {
            "codex_home_used": str(lab.live_codex_home()) if lab.backend == "live" else str(lab.codex_home),
            "auth_json_copied": False,
            "auth_json_symlinked": False,
            "implicit_default_home_fallback": False,
            "dedicated_home_authenticated_independently": lab.backend == "live",
        },
        "config_backup": {
            "original_sha256": backup_hash,
            "restored_sha256": "",
            "restore_matched": False,
        },
        "notes": [],
        "skills": {},
        "mcp": {},
        "thread": {},
        "config_attestation": {},
        "classification": {},
        "launch_decision_write_profile": "",
    }

    def note(text: str) -> None:
        evidence["notes"].append(redact_text(text))

    client: AppServerClient | None = None
    try:
        config_text = _write_minimal_config(lab)
        evidence["config_sha256"] = _sha256_bytes(config_text.encode("utf-8"))
        client = AppServerClient(_argv(lab), env=lab.env(), cwd=lab.workspace)
        client.start()
        init = _initialize(client)
        evidence["initialize_ok"] = bool(init)
        skill_root = str(lab.workspace / ".agents" / "skills")
        _try(client, "skills/extraRoots/set", extra_roots_set_params([skill_root]))
        started = _try(client, "thread/start", {"cwd": str(lab.workspace)})
        thread_id = ""
        if isinstance(started, dict):
            thread = started.get("thread") or {}
            thread_id = str(thread.get("id") or "")
            if started.get("_error"):
                note(f"thread/start -> {started['_error']}")
        evidence["thread"]["start_id"] = thread_id
        evidence["thread"]["start_ok"] = bool(thread_id)

        skills = _try(
            client,
            "skills/list",
            skills_list_params(str(lab.workspace), [skill_root]),
        )
        if skills and skills.get("_error"):
            note(f"skills/list -> {skills['_error']}")
            discovered_skills: list[str] = []
        else:
            discovered_skills = skill_names(skills)
        evidence["skills"]["observed"] = discovered_skills
        evidence["skills"]["fixture_discovered"] = OHF_PROBE_SKILL_NAME in discovered_skills
        evidence["skills"]["p0_ambient_still_present"] = sorted(
            name for name in discovered_skills if name in P0_AMBIENT_SKILL_BASELINE or name.startswith("openai-templates:") or name.startswith("github:")
        )
        evidence["skills"]["bundled_disappeared"] = not evidence["skills"]["p0_ambient_still_present"]

        invoked_ok = False
        if thread_id and evidence["skills"]["fixture_discovered"]:
            turn = _bounded_turn(
                client,
                thread_id,
                f"$ohf-probe Reply with exactly {OHF_PROBE_SKILL_ACK}",
            )
            blob = redact_text(json.dumps(turn, sort_keys=True))
            invoked_ok = OHF_PROBE_SKILL_ACK in blob
        evidence["skills"]["fixture_invoked"] = invoked_ok
        evidence["thread"]["turn_ok"] = invoked_ok or bool(thread_id)

        mcp_status = _try(client, "mcpServerStatus/list", {})
        if mcp_status and mcp_status.get("_error"):
            note(f"mcpServerStatus/list -> {mcp_status['_error']}")
            mcp_names: list[str] = []
            tool_names: list[str] = []
        else:
            mcp_names = mcp_server_names(mcp_status)
            tool_names = mcp_tool_names(mcp_status)
        evidence["mcp"]["servers"] = mcp_names
        evidence["mcp"]["tools"] = tool_names
        evidence["mcp"]["codex_apps_present"] = "codex_apps" in mcp_names
        evidence["mcp"]["fixture_server_visible"] = OHF_PROBE_MCP_SERVER in mcp_names
        evidence["mcp"]["fixture_tool_visible"] = OHF_PROBE_MCP_TOOL in tool_names
        invoked = None
        if thread_id:
            invoked = _try(
                client,
                "mcpServer/tool/call",
                {
                    "threadId": thread_id,
                    "server": OHF_PROBE_MCP_SERVER,
                    "tool": OHF_PROBE_MCP_TOOL,
                    "arguments": {"text": "ping"},
                },
            )
            if invoked and invoked.get("_error"):
                note(f"mcpServer/tool/call -> {invoked['_error']}")
        invoked_text = redact_text(str(invoked or ""))
        evidence["mcp"]["fixture_callable"] = "echo:ping" in invoked_text

        resumed = {}
        if thread_id:
            client.terminate()
            client = AppServerClient(_argv(lab), env=lab.env(), cwd=lab.workspace)
            client.start()
            _initialize(client)
            resumed = _try(client, "thread/resume", {"threadId": thread_id}) or {}
            if resumed.get("_error"):
                note(f"thread/resume -> {resumed['_error']}")
        resume_thread = ""
        if isinstance(resumed, dict):
            resume_thread = str((resumed.get("thread") or {}).get("id") or "")
        evidence["thread"]["resume_id"] = resume_thread
        evidence["thread"]["resume_ok"] = bool(resume_thread) and resume_thread == thread_id

        config_read = _try(client, "config/read", {})
        parsed = parse_config_read(config_read if not (config_read or {}).get("_error") else {})
        features = parsed.get("features") if isinstance(parsed.get("features"), dict) else {}
        skills_cfg = parsed.get("skills") if isinstance(parsed.get("skills"), dict) else {}
        bundled = skills_cfg.get("bundled") if isinstance(skills_cfg.get("bundled"), dict) else {}
        evidence["config_attestation"] = {
            "config_read_ok": bool(parsed),
            "features_apps": features.get("apps"),
            "skills_bundled_enabled": bundled.get("enabled"),
            "sandbox_mode": parsed.get("sandbox_mode") or parsed.get("sandboxMode"),
            "approval_policy": parsed.get("approval_policy") or parsed.get("approvalPolicy"),
            "model": parsed.get("model"),
        }

        residual_skills = [
            name for name in discovered_skills if name != OHF_PROBE_SKILL_NAME
        ]
        residual_mcp = [name for name in mcp_names if name != OHF_PROBE_MCP_SERVER]
        skill_class = classify_observed(
            discovered_skills,
            required=[OHF_PROBE_SKILL_NAME],
            allowed_ambient=[],
            forbidden=[],
        )
        mcp_class = classify_observed(
            mcp_names,
            required=[OHF_PROBE_MCP_SERVER],
            allowed_ambient=[],
            forbidden=["codex_apps"] if "codex_apps" in mcp_names else [],
        )
        # Residual ambient after reduction is unclassified until a version baseline is accepted.
        if residual_skills:
            skill_class[CLASS_UNCLASSIFIED] = sorted(
                set(skill_class[CLASS_UNCLASSIFIED]) | set(residual_skills)
            )
            skill_class[CLASS_ALLOWED_AMBIENT] = []
        evidence["classification"] = {"skills": skill_class, "mcp": mcp_class}
        evidence["residual_surface"] = {
            "unexpected_skills": residual_skills,
            "unexpected_mcp": residual_mcp,
            "unexpected_tools": [name for name in tool_names if name != OHF_PROBE_MCP_TOOL],
        }
        evidence["launch_decision_write_profile"] = write_profile_fail_closed(
            {
                CLASS_REQUIRED: skill_class[CLASS_REQUIRED] + mcp_class[CLASS_REQUIRED],
                CLASS_FORBIDDEN: skill_class[CLASS_FORBIDDEN] + mcp_class[CLASS_FORBIDDEN],
                CLASS_UNCLASSIFIED: skill_class[CLASS_UNCLASSIFIED] + mcp_class[CLASS_UNCLASSIFIED],
                "missing_required": skill_class["missing_required"] + mcp_class["missing_required"],
            }
        )
    finally:
        if client is not None:
            client.close()
        if lab.backend == "live" and dedicated_config is not None:
            if backup_bytes is not None:
                dedicated_config.write_bytes(backup_bytes)
            elif dedicated_config.is_file():
                dedicated_config.unlink()
            restored = _sha256_file(dedicated_config) if dedicated_config.is_file() else ""
            evidence["config_backup"]["restored_sha256"] = restored
            evidence["config_backup"]["restore_matched"] = restored == backup_hash

    evidence["auth_isolation"]["default_auth_unchanged"] = (
        _file_meta(default_home / "auth.json") == default_auth_before
    )
    if lab.backend == "live":
        evidence["auth_isolation"]["dedicated_auth_unchanged"] = (
            _file_meta(lab.live_codex_home() / "auth.json") == dedicated_auth_before
        )
        evidence["live_home"] = inspect_codex_home(lab.live_codex_home())
        evidence["live_home"].pop("path", None)
        evidence["live_home"]["path_is_default"] = lab.live_codex_home() == default_home
    return redact_evidence(evidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OHF-P1A Codex minimal-surface spike")
    parser.add_argument("--backend", choices=("fake", "live"), default="fake")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--codex-home", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--workdir", default="")
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args(argv)
    backend = "live" if args.live else args.backend
    dedicated = Path(args.codex_home).expanduser() if args.codex_home else None
    if backend == "live" and dedicated is None:
        print("P1A live spike requires --codex-home", file=sys.stderr)
        return 2
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="ohf-p1a-"))
    original_config: bytes | None = None
    dedicated_config: Path | None = None
    if backend == "live":
        assert dedicated is not None
        dedicated_config = Path(dedicated).expanduser().resolve() / "config.toml"
        if dedicated_config.is_file():
            original_config = dedicated_config.read_bytes()
    evidence: dict | None = None
    try:
        lab = Laboratory(
            root=workdir,
            backend=backend,
            requested_model=args.model,
            dedicated_codex_home=dedicated,
        )
        evidence = run_minimal_surface(lab, original_config_bytes=original_config)
    finally:
        if dedicated_config is not None and original_config is not None:
            dedicated_config.write_bytes(original_config)
    if evidence is None:
        return 2
    if evidence_contains_secret(evidence):
        print("P1A: refusing to write evidence that still contains secret-shaped values", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir) if args.out_dir else workdir / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "minimal_surface.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
