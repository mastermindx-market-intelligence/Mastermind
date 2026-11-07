#!/usr/bin/env python3
"""Build the frozen provider-free DSH/ACP fixture in an isolated macOS evidence root.

No network, installation, Executive Job, provider request, or source carrier write.
Requires already-installed *frozen* public donor dependencies and independently
verified contributor R4 / grant artifact / Node 22.22.0 inputs.
The resulting supply must still pass qualify_dsh_governed_worker.py.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
DONOR_SHA = "4878cdabd87d4041bdaff61d04c966883b9fd07a"
DONOR_LOCK = "081d9f8641590187c359477a5ee01efe99e0f216d19b8ac946d50cc710cdfb8b"
PROFILE_SHA = "c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c"
R4_SHA = "243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f"
NODE_SHA = "913b144fdb40638b1acef7974ab3c33fbd527cc0974cb5da467ab1e6ac51b4d4"
# Exact installed pnpm content closure for the frozen donor/lock on darwin-arm64.
PNPM_TREE_SHA = "bc046d6eee33feed3fa4782ec38761937a875b8230f36a0645d306fd5bed0b86"
PROFILE_SOURCE = "4159c403cf63bac8bd18138fa232911589afe06f"
SOURCES = REPO / "experiments/harness_convergence/dsh_worker"
SERVER = REPO / "experiments/harness_convergence/dispatch_binding/stdio-fixture-server.mjs"

CATALOG_SOURCE = """import {Client} from '@modelcontextprotocol/client'
import {StdioClientTransport} from '@modelcontextprotocol/client/stdio'
import {readFileSync,writeFileSync} from 'node:fs'
import {resolve,dirname} from 'node:path'
import assert from 'node:assert/strict'
const [root,node] = process.argv.slice(2)
assert.ok(root?.startsWith('/') && node?.startsWith('/'))
const input=resolve(root,'fixture-input')
const config={
  transport:'stdio',serverName:'granted',command:node,
  args:[resolve(root,'stdio-fixture-server.mjs'),input,'normal'],
  cwd:input,
  env:{HOME:resolve(input,'home'),PATH:dirname(node)+':/usr/bin:/bin',TMPDIR:input},
  toolCallTimeoutMs:3000,failOnStartupError:true,reconnect:{enabled:false},
}
const client=new Client({name:'mmx-governed-catalog-observer',version:'1.0.0'}, {capabilities:{}})
try {
 const transport=new StdioClientTransport({command:config.command,args:config.args,cwd:config.cwd,env:config.env})
 await client.connect(transport)
 const catalog=await client.listTools()
 const info=client.getServerVersion()
 assert.equal(info?.name,'mmx-stdio-fixture')
 assert.equal(info?.version,'1')
 assert.deepEqual(catalog.tools.map(t=>t.name).sort(),['read_file','search_files','write_file'])
 for (const [name,data] of [
   ['observed-tool-catalog.json',{serverInfo:info,tools:catalog.tools}],
   ['fixture-config.json',config],
 ]) writeFileSync(resolve(root,name),JSON.stringify(data,null,2)+'\\n',{flag:'wx',mode:0o600})
 console.log('EXACT_CATALOG',info.name,info.version,catalog.tools.length)
} finally {await client.close()}
"""


class Refused(Exception):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha(path) != expected:
        raise Refused(f"{label}: immutable input unavailable or digest mismatch")


def owned_out(destination: Path, protected: tuple[Path, ...]) -> Path:
    if not destination.is_absolute() or destination == Path("/") or destination.exists():
        raise Refused("fresh absolute output directory required")
    root = destination.resolve(strict=False)
    for other in (*protected, REPO):
        bound = other.resolve(strict=True)
        if root == bound or root.is_relative_to(bound) or bound.is_relative_to(root):
            raise Refused("output overlaps source or pinned input")
    return root


def run(args: list[str], *, cwd: Path, env: dict[str, str],
        log: Path, timeout: int = 120, stdin: str | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, input=stdin,
                            capture_output=True, check=False, timeout=timeout)
    log.write_text(result.stdout + "\n" + result.stderr)
    if result.returncode:
        raise Refused(f"{Path(args[0]).name} failed rc={result.returncode}; inspect {log}")
    return result.stdout


def put(path: Path, data: str) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(data)


def require_read_search_projection(
    projection: dict, config: dict, catalog: dict,
) -> None:
    """Validate the exact observed, disarmed grant rather than just its size.

    This is an independent boundary after the typed projection helper returns:
    two arbitrary tools (including write_file) must not qualify as read/search.
    """
    if not isinstance(projection, dict) or projection.get("schema") != (
        "mastermind.dsh_mcp_tool_projection.v1"
    ) or projection.get("production_armed") is not False:
        raise Refused("MCP projection must be typed and disarmed")
    if projection.get("required") is not True or projection.get("approvalMode") != "approve":
        raise Refused("MCP projection approval/required contract mismatch")
    if projection.get("serverInfo") != catalog.get("serverInfo"):
        raise Refused("MCP projection server identity differs from observed stdio server")
    if projection.get("target") != {
        "transport": "stdio",
        "serverName": config.get("serverName"),
        "command": config.get("command"),
        "args": config.get("args"),
    }:
        raise Refused("MCP projection command/server binding mismatch")
    source = projection.get("source")
    if not isinstance(source, dict) or source.get("capability_id") != (
        "fixture.dsh.read"
    ) or source.get("profile_id") != "fixture.dsh.projection":
        raise Refused("MCP projection must use the exact synthetic read grant")
    tools = projection.get("tools")
    if not isinstance(tools, list) or len(tools) != 2:
        raise Refused("MCP projection must contain exactly two tools")
    observed = catalog.get("tools")
    if not isinstance(observed, list):
        raise Refused("MCP observed stdio tool catalog is invalid")
    allowed = {"read_file", "search_files"}
    selected = {t.get("name"): t for t in observed if isinstance(t, dict)
                and t.get("name") in allowed}
    if set(selected) != allowed or {t.get("name") for t in tools
                                    if isinstance(t, dict)} != allowed:
        raise Refused("MCP projection includes an ungranted or missing tool")
    for tool in tools:
        if not isinstance(tool, dict):
            raise Refused("MCP projection tool must be typed")
        observed_tool = selected[tool["name"]]
        expected = {
            "name": tool["name"],
            "inputSchema": observed_tool.get("inputSchema"),
            "outputSchema": observed_tool.get("outputSchema"),
            "annotations": observed_tool.get("annotations"),
            "execution": observed_tool.get("execution"),
        }
        if tool != expected:
            raise Refused("MCP projection full tool row differs from observed stdio catalog")


def load_qualifier():
    """Load the independent frozen-input verifier from this exact source checkout."""
    qualifier_file = REPO / "scripts/qualify_dsh_governed_worker.py"
    spec = importlib.util.spec_from_file_location("dsh_governed_qualifier", qualifier_file)
    if spec is None or spec.loader is None:
        raise Refused("independent governed supply verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_dependency_closure(module, donor: Path) -> None:
    """Reject altered ignored pnpm bytes before executing any installed dependency."""
    if (module.EXPECTED_PNPM_TREE_SHA != PNPM_TREE_SHA
            or module.EXPECTED_DONOR_LOCK_SHA != DONOR_LOCK):
        raise Refused("preparer and qualifier dependency pins disagree")
    try:
        actual = module.materialized_dependency_digest(donor)
    except module.QualificationRefused as exc:
        raise Refused("materialized dependency tree cannot be independently verified") from exc
    if actual != PNPM_TREE_SHA:
        raise Refused("materialized dependencies mismatch immutable donor lock closure")


def safe_donor_git(donor: Path, *args: str) -> str:
    """Security-gate Git with no inherited Git/provider environment and a timeout."""
    environment = {
        "PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1",
    }
    command = [
        "/usr/bin/git", "--no-optional-locks", "-C", str(donor),
        "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *args,
    ]
    try:
        result = subprocess.run(
            command, text=True, capture_output=True, check=True,
            env=environment, timeout=20,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise Refused("frozen donor git provenance preflight refused") from exc
    return result.stdout.strip()


def build(args: argparse.Namespace) -> int:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise Refused("frozen Node binary requires macOS arm64")
    donor = Path(args.donor).resolve(strict=True)
    patch = Path(args.r4_patch).resolve(strict=True)
    profile = Path(args.profile).resolve(strict=True)
    node = Path(args.node).resolve(strict=True)
    require_sha(patch, R4_SHA, "contributor R4")
    require_sha(profile, PROFILE_SHA, "compiled grant profile")
    require_sha(node, NODE_SHA, "Node 22.22.0 darwin-arm64")
    require_sha(donor / "pnpm-lock.yaml", DONOR_LOCK, "donor lock")
    if safe_donor_git(donor, "rev-parse", "HEAD") != DONOR_SHA:
        raise Refused("donor source SHA does not match the frozen fixture")
    if safe_donor_git(donor, "status", "--porcelain"):
        raise Refused("donor checkout must be unmodified before cloning")
    if not (donor / "node_modules/.pnpm/node_modules/esbuild").exists():
        raise Refused("frozen donor dependencies missing; no automatic installation")
    module = load_qualifier()
    require_dependency_closure(module, donor)
    output = owned_out(Path(args.output), (donor, patch, profile, node))
    output.mkdir(mode=0o700, parents=True)
    logdir = output / "logs"
    logdir.mkdir(mode=0o700)
    home = output / "fixture-input/home"
    home.mkdir(parents=True, mode=0o700)
    clean_env = {
        "PATH": "/usr/bin:/bin", "HOME": str(home),
        "TMPDIR": str(output), "PYTHONDONTWRITEBYTECODE": "1",
    }
    copy = run(["/bin/cp", "-cR", str(donor), str(output / "donor")],
               cwd=output, env=clean_env, log=logdir / "clone.log", timeout=240)
    del copy
    snapshot = output / "donor"
    # A copy made after the first proof must not substitute ignored build code.
    require_dependency_closure(module, snapshot)
    git = ["/usr/bin/git", "-C", str(snapshot)]
    run(git + ["apply", "--check", str(patch)], cwd=output, env=clean_env,
        log=logdir / "patch-check.log")
    run(git + ["apply", str(patch)], cwd=output, env=clean_env,
        log=logdir / "patch-apply.log")
    (output / "runtime/build").mkdir(parents=True)
    (output / "runtime/package.json").write_text('{"type":"module"}\n')
    (output / "node_modules").symlink_to(snapshot / "node_modules/.pnpm/node_modules",
                                          target_is_directory=True)
    for src, name in (
        (patch, "governed-acp-mount.patch"),
        (profile, "profile1060.mjs"),
        (SERVER, "stdio-fixture-server.mjs"),
    ):
        (output / name).write_bytes(src.read_bytes())
    nonce = "governed-" + R4_SHA[:12] + "-" + DONOR_SHA[:12]
    fixture = output / "fixture-input"
    put(fixture / "fixture.json", json.dumps(
        {"kind": "mmx-synthetic-stdio-test", "nonce": nonce}, sort_keys=True) + "\n")
    put(fixture / "memo.txt", f"Research fixture\nneedle {nonce}\n")
    put(fixture / "signals.txt", f"alpha\nbeta\nneedle {nonce}\n")
    put(fixture / "events.jsonl", "")
    put(output / "inspect-tool-catalog.mjs", CATALOG_SOURCE)

    node_exec = str(node)
    tsc = sorted(snapshot.glob("node_modules/.pnpm/typescript@*/node_modules/typescript/bin/tsc"))
    if len(tsc) != 1:
        raise Refused("exact installed donor TypeScript dependency not found")
    run([node_exec, str(tsc[0]), "-p", "packages/acp/acp/tsconfig.json", "--pretty", "false"],
        cwd=snapshot, env=clean_env, log=logdir / "acp-typecheck.log")
    # Rebuild the patched donor ACP JS; do not change the read-only origin.
    compiled_js = """
const root=process.argv[2]
const esbuild=require(root+'/node_modules/.pnpm/node_modules/esbuild')
esbuild.buildSync({entryPoints:[root+'/packages/acp/acp/src/index.ts'],
  outfile:root+'/packages/acp/acp/lib/index.js',bundle:true,packages:'external',
  platform:'node',format:'esm',target:'node22',
  tsconfig:root+'/tsconfig.base.json',legalComments:'none'})
"""
    put(output / "build-patched-acp.cjs", compiled_js)
    run([node_exec, str(output / "build-patched-acp.cjs"), str(snapshot)],
        cwd=output, env=clean_env, log=logdir / "acp-js-build.log")
    if "createGovernedAcpPlugin" not in (
        snapshot / "packages/acp/acp/lib/index.js").read_text():
        raise Refused("patched ACP plugin export absent")

    run([node_exec, str(output / "inspect-tool-catalog.mjs"), str(output), node_exec],
        cwd=output, env=clean_env, log=logdir / "mcp-catalog.log", timeout=30)
    config = json.loads((output / "fixture-config.json").read_text())
    snapshot_tools = json.loads((output / "observed-tool-catalog.json").read_text())
    request = {
        "fixture": "synthetic-dsh-grant-canary",
        "config": config, "snapshot": snapshot_tools,
    }
    put(output / "projection-request.json",
        json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n")
    projection_env = {**clean_env, "PYTHONPATH": str(REPO)}
    project = run([sys.executable,
                   str(REPO / "tests/fixtures/dsh_mcp_grant_projection.py")],
                  cwd=REPO, env=projection_env,
                  log=logdir / "canonical-projection.log",
                  stdin=(output / "projection-request.json").read_text())
    projection = json.loads(project)
    require_read_search_projection(projection, config, snapshot_tools)
    put(output / "projection.json", json.dumps(projection, sort_keys=True,
                                                 separators=(",", ":")) + "\n")
    files = [
        "runtime/package.json", "profile1060.mjs", "projection.json",
        "fixture-config.json", "stdio-fixture-server.mjs",
        "governed-acp-mount.patch", "observed-tool-catalog.json",
        "projection-request.json", "donor/pnpm-lock.yaml",
        "donor/packages/acp/acp/lib/index.js", "donor/tsconfig.base.json",
        "inspect-tool-catalog.mjs",
    ]
    manifest = {
        "schema": "mastermind.dsh_governed_acp_fixed_supply.v1",
        "donor": DONOR_SHA, "profile_head": PROFILE_SOURCE,
        "r4_patch": R4_SHA, "profile_artifact": PROFILE_SHA,
        "node": node_exec, "node_sha256": NODE_SHA,
        "donor_lock_sha256": DONOR_LOCK,
        "materialized_pnpm_sha256": PNPM_TREE_SHA,
        "files": {name: sha(output / name) for name in files},
        "fixture_input": {
            name: sha(fixture / name) for name in
            ("fixture.json", "memo.txt", "signals.txt")
        },
        "fixture_sources": {},
    }
    put(output / "supply-manifest.json", json.dumps(
        manifest, sort_keys=True, indent=2) + "\n")
    run([node_exec, str(SOURCES / "build_governed_fixture.cjs"),
         str(output), str(snapshot / "node_modules/.pnpm/node_modules/esbuild")],
        cwd=REPO, env=clean_env, log=logdir / "governed-bundle.log")
    # The independent qualifier re-attests this exact byte closure after bundling.
    module.verify_supply(output)
    receipt = {
        "schema": "mastermind.dsh_governed_supply_prepared.v1",
        "status": "SUPPLY_PINNED_NOT_YET_TESTED",
        "manifest_sha256": sha(output / "supply-manifest.json"),
        "bundle_sha256": sha(output / "runtime/build/governed_acp_fixture.mjs"),
        "profile_sha256": PROFILE_SHA, "r4_sha256": R4_SHA,
        "node_sha256": NODE_SHA, "provider_calls": 0, "installed": False,
    }
    put(output / "preparation-receipt.json", json.dumps(receipt, sort_keys=True,
                                                         indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", required=True)
    parser.add_argument("--r4-patch", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", required=True)
    try:
        return build(parser.parse_args())
    except (Refused, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "SUPPLY_NOT_QUALIFIED",
                          "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
