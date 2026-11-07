"""Cold native enrollment qualification; setup is confined to a marked fixture home.

The native PM selection is real. The worker installation record and execution
engine are explicit fixtures. No worker/provider is dispatched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AUDITED_CHECKER = r"""
import json, os, runpy, sys
blocked = []
def audit(event, args):
    write = event == "open" and (
        (isinstance(args[1], str) and any(x in args[1] for x in "wax+"))
        or (isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
    mutation = event in {
        "os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.chmod", "os.chown",
        "os.truncate", "os.utime", "os.symlink", "os.link", "subprocess.Popen",
        "os.system", "os.posix_spawn", "os.fork", "os.exec", "socket.connect",
        "socket.connect_ex", "socket.getaddrinfo",
    }
    if write or mutation:
        blocked.append(event)
        raise RuntimeError("observational checker attempted an effect")
sys.addaudithook(audit)
sys.argv = sys.argv[1:]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as exc:
    code = exc.code or 0
if blocked:
    print(json.dumps({"blocked_events": blocked}), file=sys.stderr)
    raise SystemExit(3)
raise SystemExit(code)
"""

NODE_CHECKER = r"""
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const [backend, encoded] = process.argv.slice(2);
const api = await import(pathToFileURL(backend).href);
const config = JSON.parse(encoded);
let engineCalls = 0;
const engine = {async callTool(request) {
  engineCalls++;
  if (engineCalls !== 1 || request.name !== 'start_process') throw new Error('unexpected fixture call');
  const body = 'request status result accept';
  const payload = JSON.stringify({
    exit_code: 0, stdout_base64: Buffer.from(body).toString('base64'),
    stdout_bytes: Buffer.byteLength(body),
    stdout_sha256: createHash('sha256').update(body).digest('hex'),
  });
  return {content:[{type:'text',text:'Process started with PID 123 (shell: /bin/zsh)\nInitial output:\n'+payload+'\nMMX_FABRIC_EXIT=0\n'}]};
}};
const facade = api.createFabricFacade(engine, {
  adapterPath:'/fixture/no-execution/fabric_task.py', hermesNative:config,
});
const response = await facade.call('fabric_capabilities', {});
const value = response.structuredContent ?? JSON.parse(response.content[0].text);
if (value.error || engineCalls !== 1) throw new Error('capability fixture failed');
console.log(JSON.stringify({authorized:value.hermes_native_origin?.enabled === true, engine_calls:engineCalls}));
"""


def snapshot(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if path.is_symlink():
            value = os.readlink(path)
        elif path.is_file():
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            value = None
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_size if path.is_file() else None,
            info.st_mtime_ns, value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--fixture-home", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    args = parser.parse_args()
    source, owner = args.native_source.resolve(), args.fixture_home.resolve()
    marker = json.loads((owner / ".observational-qualification-home.json").read_text())
    if marker != {"schema": "hermes.observational_fixture.v1", "native_source": str(source)}:
        raise ValueError("explicit fixture ownership is required")
    repo = Path(__file__).resolve().parents[3]
    package = Path(__file__).resolve().parents[1]
    backend = repo / "integrations/studio_direct_mcp/fabric-backend.mjs"
    profiles = owner / "profiles"
    profiles.mkdir(exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="fabric-observation-", dir=profiles))
    managed = home / "managed-policy"
    managed.mkdir()
    os.environ.update(HERMES_HOME=str(owner), HERMES_MANAGED_DIR=str(managed),
                      HERMES_CONFIG_BACKEND="file")
    sys.path.insert(0, str(source))
    sys.path.insert(1, str(repo))
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        from pm.environments import committed_venv, site_packages, runtime_facts_path
        environment = committed_venv(source)
        if environment is None:
            raise ValueError("the native PM must prepare the private dependency selection first")
        import site
        site.addsitedir(str(site_packages(environment)))
        from integrations.hermes_attended_fabric.native_evidence import (
            RUNTIME_FILES, PLUGIN_SOURCE, ENROLLMENT_SCHEMA, package_fingerprint)
        from hermes_cli.config import load_config
        installed = home / "plugins/mastermind-fabric-worker"
        installed.mkdir(parents=True)
        for name in RUNTIME_FILES:
            shutil.copy2(package / name, installed / name)
        revision = "f" * 40
        (installed.parent / ".install-metadata.json").write_text(json.dumps({
            "mastermind-fabric-worker": {"source": PLUGIN_SOURCE, "revision": revision, "pinned": True}}))
        digest = package_fingerprint(installed)
        document = {"plugins": {"enabled": ["mastermind-fabric-worker"], "entries": {
            "mastermind-fabric-worker": {
                "mcp_allowlist": ["mastermind-fabric-exec"],
                "native_origin": {"schema": ENROLLMENT_SCHEMA, "enabled": True,
                                  "namespace": "observational-qualification"}}}}}
        config_path = home / "config.yaml"
        good = json.dumps(document)
        config_path.write_text(good)
        load_config()  # setup only: create a real native last-known-good backup
        if not (home / "backups/config").is_dir():
            raise AssertionError("native backup precondition missing")
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        checker = installed / "enrollment_check.py"
        selection = {"home": str(home), "source": str(source), "python": str(python),
                     "revision": revision, "packageSha256": digest}
        child_env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
                     "HERMES_HOME": str(owner), "HERMES_MANAGED_DIR": str(managed),
                     "HERMES_CONFIG_BACKEND": "file"}
        results = []
        def check(label, authorized, *, node=False, extra_env=None):
            environment_values = {**child_env, **(extra_env or {})}
            before = snapshot(home)
            if node:
                command = [str(args.node), "--input-type=module", "-e", NODE_CHECKER,
                           "/fixture/observational-driver.mjs", str(backend), json.dumps(selection)]
                data = None
            else:
                command = [str(python), "-I", "-B", "-c", AUDITED_CHECKER,
                           str(checker), str(source), str(home), revision, digest]
                data = json.dumps({"action": "fabric_capabilities", "arguments": {}})
            result = subprocess.run(command, input=data, capture_output=True, text=True,
                                    env=environment_values, cwd=home, timeout=20)
            if result.returncode != 0:
                raise AssertionError((label, result.returncode, result.stdout, result.stderr))
            response = json.loads(result.stdout)
            if response.get("authorized") is not authorized or snapshot(home) != before:
                raise AssertionError((label, response))
            results.append({"case": label, "authorized": authorized, "files_unchanged": True,
                            "effect_audit": not node, "actual_backend": node})

        check("cold_current_enrollment", True)
        check("actual_backend_current_enrollment", True, node=True)
        config_path.write_text("plugins: [unterminated")
        check("malformed_current_with_real_good_backup", False)
        config_path.write_text(good)
        managed_config = managed / "config.yaml"
        managed_config.write_text('plugins:\n  disabled: [mastermind-fabric-worker]\n')
        check("managed_disable", False)
        check("actual_backend_preserves_managed_selector", False, node=True)
        managed_config.write_text("plugins: [unterminated")
        check("malformed_managed_policy", False)
        managed_config.write_text(json.dumps({"plugins": {"disabled": ["$" + "{BLOCKED_PLUGIN}"]}}))
        check("unresolved_managed_permission", False)
        managed_config.unlink()
        managed_config.symlink_to(managed / "absent-policy")
        check("dangling_managed_policy", False)
        managed_config.unlink()
        for field in ("enabled", "disabled", "mcp_allowlist"):
            changed = json.loads(good)
            if field == "mcp_allowlist":
                changed["plugins"]["entries"]["mastermind-fabric-worker"][field] = "prefix-mastermind-fabric-exec-suffix"
            else:
                changed["plugins"][field] = "prefix-mastermind-fabric-worker-suffix"
            config_path.write_text(json.dumps(changed))
            check("scalar_permission_" + field, False)
        config_path.write_text(good)
        check("remote_process_backend", False, extra_env={"HERMES_CONFIG_BACKEND": "remote"})
        check("actual_backend_preserves_backend_selector", False, node=True,
              extra_env={"HERMES_CONFIG_BACKEND": "remote"})
        deployment = owner / ".env"
        if deployment.exists() or deployment.is_symlink():
            raise ValueError("fixture deployment file unexpectedly exists")
        deployment.write_text("HERMES_CONFIG_BACKEND=remote\n")
        try:
            check("deployment_dotenv_backend", False)
            check("actual_backend_preserves_deployment_home", False, node=True)
        finally:
            deployment.unlink()
        deployment.symlink_to(owner / "absent-env")
        try:
            check("dangling_deployment_dotenv", False)
        finally:
            deployment.unlink()
        check("current_enrollment_after_fixture_changes", True)
        receipt = {
            "schema": "mastermind.hermes_observational_qualification.v1",
            "native_source": str(source), "dependency_environment": str(environment),
            "dependency_facts_sha256": hashlib.sha256(runtime_facts_path(source).read_bytes()).hexdigest(),
            "fixture_home": str(home), "package_sha256": digest,
            "native_pm_selection_real": True, "worker_installation_record_fixture": True,
            "execution_engine_fixture": True, "live_worker_start": False,
            "cases": results, "passed": len(results),
        }
        (home / "qualification-receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print(json.dumps(receipt, sort_keys=True))
    finally:
        reset_hermes_home_override(token)


if __name__ == "__main__":
    main()
