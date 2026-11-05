#!/usr/bin/env python3
"""A bounded remote client for an already admitted Go worker lease.

The existing transport owns provider/host admission, tunnel identity, deadline,
process-group cleanup and lease settlement. This helper grants none of them.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from email.utils import parsedate_to_datetime
from go_remote_capsule import CapsuleError, load_capsule, validate_health


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise CapsuleError('worker capsule refused')


def _json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CapsuleError('worker capsule refused')
            result[key] = value
        return result
    def constant(value):
        raise CapsuleError('worker capsule refused')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise CapsuleError('worker capsule refused')
    return value


def probe(capsule, required_seconds=0):
    # Never honor inherited HTTP proxies or follow a redirect with a bearer.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(capsule['endpoint']+'/worker-health', headers={
        'Authorization': 'Bearer '+capsule['token'],
        'X-MM-Run-Id': capsule['run_id'], 'X-MM-Host': capsule['host'],
        'X-MM-Worker-Model': capsule['model'],
    })
    with opener.open(request, timeout=3) as response:
        if response.status != 200:
            raise CapsuleError('worker capsule refused')
        server_date = parsedate_to_datetime(response.headers['Date'])
        if server_date.tzinfo is None or server_date.utcoffset().total_seconds() != 0:
            raise CapsuleError('worker capsule refused')
        remaining = capsule['expires_at'] - server_date.timestamp()
        if not required_seconds + 5 <= remaining <= 301:
            raise CapsuleError('worker capsule refused')
        raw = response.read(8193)
        if len(raw) > 8192:
            raise CapsuleError('worker capsule refused')
    validate_health(capsule, _json_object(raw))


def configuration(capsule):
    quote = json.dumps
    # Official codex-cli 0.154.0 schema: both provider retry settings accept 0.
    return '\n'.join([
        'model = '+quote(capsule['model']), 'model_provider = "go_worker"',
        'approval_policy = "never"', 'sandbox_mode = "danger-full-access"',
        'cli_auth_credentials_store = "ephemeral"',
        '[agents]', 'enabled = false',
        '[features]', 'multi_agent_v2 = false',
        '[model_providers.go_worker]', 'name = "go_worker"',
        'base_url = '+quote(capsule['endpoint']+'/v1'),
        'env_key = "GO_WORKER_CAPABILITY"', 'wire_api = "responses"',
        'requires_openai_auth = false', 'request_max_retries = 0',
        'stream_max_retries = 0', 'stream_idle_timeout_ms = 120000',
        'env_http_headers = { "X-MM-Run-Id" = "GO_WORKER_RUN", "X-MM-Host" = "GO_WORKER_HOST", "X-MM-Worker-Model" = "GO_WORKER_MODEL" }', '',
    ])


def run(cwd, model, prompt, *, environ=None, codex_binary=None, diagnostics=None):
    # Public stages only. No exception text, paths, environment or capsule bytes.
    observed = diagnostics if diagnostics is not None else {}
    observed.update(phase='preflight', child_returncode=None)
    env = dict(os.environ if environ is None else environ)
    if env.get('LANE_LEASED') != '1':
        raise CapsuleError('worker capsule refused')
    timeout = env.get('REMOTE_SUB_CHILD_TIMEOUT', '')
    if not timeout.isascii() or not timeout.isdigit() or not 1 <= int(timeout) <= 240:
        raise CapsuleError('worker capsule refused')
    expected = {
        'root': env.get('POOL_ORCHESTRATOR_ID'), 'lease_id': env.get('POOL_LEASE_ID'),
        'account': env.get('POOL_ACCOUNT'), 'run_id': env.get('REMOTE_SUB_RUN_ID'),
        'host': env.get('LANE_REMOTE_HOST'), 'model': model,
    }
    path = env.get('GO_REMOTE_CAPABILITY_FILE', '')
    if not Path(path).is_absolute():
        raise CapsuleError('worker capsule refused')
    observed['phase'] = 'capsule_validation'
    capsule = load_capsule(path, expected=expected, now=time.time())
    observed['phase'] = 'local_preflight'
    cwd, prompt = Path(cwd), Path(prompt)
    if not cwd.is_absolute() or not cwd.is_dir() or not prompt.is_absolute() or not prompt.is_file() or prompt.stat().st_size > 1024*1024:
        raise CapsuleError('worker capsule refused')
    binary = codex_binary or shutil.which('codex', path=env.get('PATH'))
    if not binary:
        raise CapsuleError('worker capsule refused')
    observed['phase'] = 'health_probe'
    probe(capsule, int(timeout))
    safe_names = ('HOME','PATH','SHELL','USER','LOGNAME','TMPDIR','LANG','LC_ALL','TZ',
                  'SSL_CERT_FILE','SSL_CERT_DIR','CURL_CA_BUNDLE',
                  'POOL_ORCHESTRATOR_ID','POOL_PARENT_RUN_ID','POOL_TASK_CLASS',
                  'POOL_LEASE_ID','POOL_ACCOUNT','REMOTE_SUB_RUN_ID','LANE_REMOTE_HOST')
    child_env = {name: env[name] for name in safe_names if name in env}
    observed['phase'] = 'temporary_home_enter'
    with tempfile.TemporaryDirectory(prefix='go_worker_home_') as home:
        observed['phase'] = 'temporary_home_configuration'
        config = Path(home)/'config.toml'
        fd = os.open(config, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as stream:stream.write(configuration(capsule))
        child_env.update(CODEX_HOME=home, GO_WORKER_CAPABILITY=capsule['token'],
                         GO_WORKER_RUN=capsule['run_id'], GO_WORKER_HOST=capsule['host'],
                         GO_WORKER_MODEL=capsule['model'])
        # CLI overrides keep project-level settings from changing the admitted
        # provider endpoint, credential source, retry policy or child-agent mode.
        overrides = [
            'agents.enabled=false', 'features.multi_agent_v2=false',
            'model_provider="go_worker"',
            'cli_auth_credentials_store="ephemeral"',
            'model_providers.go_worker.env_http_headers={ "X-MM-Run-Id" = "GO_WORKER_RUN", "X-MM-Host" = "GO_WORKER_HOST", "X-MM-Worker-Model" = "GO_WORKER_MODEL" }',
            'model_providers.go_worker.base_url='+json.dumps(capsule['endpoint']+'/v1'),
            'model_providers.go_worker.env_key="GO_WORKER_CAPABILITY"',
            'model_providers.go_worker.wire_api="responses"',
            'model_providers.go_worker.requires_openai_auth=false',
            'model_providers.go_worker.request_max_retries=0',
            'model_providers.go_worker.stream_max_retries=0',
            'model_providers.go_worker.supports_websockets=false',
        ]
        command = [str(binary),'exec','--ephemeral','--dangerously-bypass-approvals-and-sandbox',
                   '--skip-git-repo-check','-C',str(cwd),'-m',model]
        for value in overrides:command.extend(['-c',value])
        command.append('-')
        observed['phase'] = 'prompt_open'
        with prompt.open('rb') as source:
            observed['phase'] = 'provider_process'
            rc = subprocess.run(command, stdin=source,env=child_env,cwd=cwd,check=False).returncode
            observed['child_returncode'] = rc
            observed['phase'] = 'prompt_close'
        observed['phase'] = 'temporary_home_exit'
    return rc


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print('GO_REMOTE_CLIENT_REFUSED',file=sys.stderr);return 78
    observed = {'phase': 'preflight', 'child_returncode': None}
    try:return run(*args, diagnostics=observed)
    except Exception as exc:
        print('GO_REMOTE_CLIENT_REFUSED',file=sys.stderr)
        # Keep the original fail-closed exit and marker. Completion observations
        # are not settlement, artifact acceptance, authentication or retry rights.
        allowed = {'CapsuleError','OSError','PermissionError','FileNotFoundError',
                   'FileExistsError','TimeoutError','ValueError','TypeError',
                   'RuntimeError','SubprocessError'}
        name = type(exc).__name__
        rc = observed['child_returncode']
        try:
            print('GO_REMOTE_CLIENT_DIAGNOSTIC '+json.dumps({
                'phase': observed['phase'], 'exception_class': name if name in allowed else 'Exception',
                'child_completion_observed': type(rc) is int,
                'child_returncode': rc if type(rc) is int else None,
                'retry_authorized': False,
            },sort_keys=True,separators=(',',':')),file=sys.stderr)
        except Exception:
            # Optional diagnosis must not replace the original refusal result.
            pass
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
