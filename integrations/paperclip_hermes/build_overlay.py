#!/usr/bin/env python3
"""Render the reviewed generic Hermes extension against an explicit source tree.

Writes only to a distinct output directory. Each modification is constrained to
one known function/anchor; unknown or already patched input is refused. The
manifest records the exact preimage needed by a later native release operation.
This builder does not install, start, restart, or select any runtime.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


class Overlay:
    def __init__(self, source):
        self.source = Path(source).resolve()
        self.before, self.files = {}, {}

    def read(self, rel):
        if rel not in self.files:
            self.before[rel] = (self.source / rel).read_bytes()
            self.files[rel] = self.before[rel].decode()
        return self.files[rel]

    def replace(self, rel, old, new):
        text = self.read(rel)
        if text.count(old) != 1:
            raise ValueError(f'overlay_anchor_mismatch:{rel}:{old[:70]!r}')
        self.files[rel] = text.replace(old, new, 1)

    def function(self, rel, name, old, new):
        text = self.read(rel)
        nodes = [n for n in ast.walk(ast.parse(text))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        if len(nodes) > 1:
            lines = text.splitlines(keepends=True)
            nodes = [n for n in nodes if ''.join(lines[n.lineno - 1:n.end_lineno]).count(old) == 1]
        if len(nodes) != 1:
            raise ValueError(f'overlay_function_mismatch:{rel}:{name}')
        node = nodes[0]
        lines = text.splitlines(keepends=True)
        body = ''.join(lines[node.lineno - 1:node.end_lineno])
        if body.count(old) != 1:
            raise ValueError(f'overlay_function_anchor_mismatch:{rel}:{name}:{old[:70]!r}')
        self.files[rel] = ''.join(lines[:node.lineno - 1]) + body.replace(old, new, 1) + ''.join(lines[node.end_lineno:])

    def import_line(self, rel, statement):
        text = self.read(rel)
        if statement in text:
            raise ValueError(f'overlay_import_already_present:{rel}')
        nodes = ast.parse(text).body
        after = 0
        for node in nodes:
            if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)) or (isinstance(node, ast.ImportFrom)
                                                             and node.module == '__future__'):
                after = node.end_lineno
            else:
                break
        lines = text.splitlines(keepends=True)
        self.files[rel] = ''.join(lines[:after]) + '\n' + statement + '\n' + ''.join(lines[after:])

    def decorator(self, rel, name, decorator):
        self.replace(rel, f'def {name}(', f'@{decorator}\ndef {name}(')

    def render(self, output):
        output = Path(output).resolve()
        if output == self.source or self.source in output.parents:
            raise ValueError('overlay_output_must_be_outside_source')
        overlay = Path(__file__).parent / 'core_overlay'
        for path in sorted(overlay.rglob('*.py')):
            rel = path.relative_to(overlay).as_posix()
            if (self.source / rel).exists():
                raise ValueError(f'overlay_new_file_exists:{rel}')
            self.files[rel] = path.read_text()
        manifest = {}
        for rel, text in sorted(self.files.items()):
            ast.parse(text, filename=rel)
            destination = output / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text)
            manifest[rel] = {
                'before_sha256': hashlib.sha256(self.before[rel]).hexdigest() if rel in self.before else None,
                'after_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        (output / 'overlay-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        return manifest


def plugin_and_client(o):
    o.replace('hermes_cli/plugins_capability_ctx.py', '    # -- capability probing', '''    def register_launch_credentials(self, binding_id: str, declaration: dict | None = None):
        """Declare exact finite-launch credential destinations; values stay in the caller."""
        from hermes_cli.plugins_launch_credentials import register
        return register(self, binding_id, declaration)

    # -- capability probing''')
    o.import_line('hermes_cli/plugins_manifest.py',
                  'from agent.launch_credential_binding import manifest_bindings')
    o.replace('hermes_cli/plugins_manifest.py',
              '"requires_auth", "oauth", "config_keys",',
              '"requires_auth", "oauth", "config_keys", "launch_credentials",')
    o.replace('hermes_cli/plugins_manifest.py',
              '    config_keys: list[str] = field(default_factory=list)',
              '''    config_keys: list[str] = field(default_factory=list)
    # Private values never appear here; startup reads this metadata before importing plugins.
    launch_credentials: dict[str, dict[str, Any]] = field(default_factory=dict)''')
    o.function('hermes_cli/plugins_manifest.py', 'parse_manifest_file',
               '            provides_tools=data.get("provides_tools", []),',
               '''            provides_tools=data.get("provides_tools", []),
            launch_credentials=manifest_bindings(data.get("launch_credentials")),''')
    o.function('hermes_cli/plugin_host.py', '_env',
               '        env = self._base_context.run(served_profile_child_env, target_home=self._home, inherit_credentials=True)',
               '''        from hermes_cli.plugins_launch_credentials import launch_secret_names, strip_child_credentials
        from tools.environments.local import hermes_subprocess_env
        names = launch_secret_names()
        base = hermes_subprocess_env(inherit_credentials=True,
                                    base_env=strip_child_credentials(os.environ, names))
        env = self._base_context.run(served_profile_child_env, base=base,
                                     target_home=self._home, inherit_credentials=True)''')
    o.function('hermes_cli/plugin_host.py', '_env',
               '        return env', '        return strip_child_credentials(env, names)')
    o.function('hermes_cli/gateway_chat.py', 'client_env_policy',
               'def client_env_policy(parameters)', 'def client_env_policy(parameters, capabilities=())')
    o.function('hermes_cli/gateway_chat.py', 'client_env_policy',
               '    return {"client_env": shell_client_env()} if "client_env" in parameters else {}',
               '''    from hermes_cli.plugins_launch_credentials import launch_parameters
    result = {"client_env": shell_client_env()} if "client_env" in parameters else {}
    result.update(launch_parameters(parameters, capabilities))
    return result''')
    o.function('hermes_cli/gateway_chat.py', 'run_gateway_chat',
               'policy.update(client_env_policy(parameters))',
               'policy.update(client_env_policy(parameters, description.get("capabilities", ())))')
    o.function('hermes_cli/gateway_chat.py', 'run_gateway_chat',
               '    async with connect_gateway() as client:',
               '''    from hermes_cli.plugins_launch_credentials import verify_fresh_launch
    verify_fresh_launch(any((wants_latest(args), getattr(args, "resume", None), continue_title(args))))
    async with connect_gateway() as client:''')
    o.function('hermes_cli/gateway_chat.py', '_resume',
               '    key = getattr(args, "api_key", None)',
               '''    from hermes_cli.plugins_launch_credentials import refuse_launch_resume
    refuse_launch_resume()
    key = getattr(args, "api_key", None)''')
    o.function('hermes_cli/gateway_session_store.py', '__init__',
               '        self._create_parameters = None',
               '        self._create_parameters = None\n        self._create_capabilities = ()')
    o.function('hermes_cli/gateway_session_store.py', '__init__',
               '        self.connection = connection or GatewayConnection.shared()',
               '''        from hermes_cli.plugins_launch_credentials import verify_required_binding
        verify_required_binding()
        self.connection = connection or GatewayConnection.shared()''')
    o.function('hermes_cli/gateway_session_store.py', 'client_env',
               '            self._create_parameters = list((contract or {}).get("parameters") or [])',
               '''            self._create_parameters = list((contract or {}).get("parameters") or [])
            self._create_capabilities = list((described or {}).get("capabilities") or [])''')
    o.function('hermes_cli/gateway_session_store.py', 'client_env',
               'return client_env_policy(self._create_parameters)',
               'return client_env_policy(self._create_parameters, self._create_capabilities)')
    o.function('hermes_cli/gateway_session_store.py', 'attach',
               '        if session_id in self.snapshots:',
               '''        from hermes_cli.plugins_launch_credentials import refuse_launch_resume
        refuse_launch_resume()
        if session_id in self.snapshots:''')
    o.function('hermes_cli/gateway_runtime_start.py', 'spawn_unmanaged_gateway',
               '    env = served_profile_child_env(base=dict(os.environ), target_home=home, inherit_credentials=True)',
               '''    from hermes_cli.plugins_launch_credentials import launch_secret_names, strip_child_credentials
    names = launch_secret_names()
    env = served_profile_child_env(base=strip_child_credentials(os.environ, names),
                                   target_home=home, inherit_credentials=True)''')
    o.function('hermes_cli/gateway_runtime_start.py', 'spawn_unmanaged_gateway',
               '    remaining(deadline)\n    logs = home / "logs"',
               '''    env = strip_child_credentials(env, names)
    remaining(deadline)
    logs = home / "logs"''')


def creation_and_lifecycle(o):
    o.replace('tui_gateway/contracts/canonical_sessions.py',
              '    client_env: dict[str, str] | None = None',
              '''    client_env: dict[str, str] | None = None
    # Private finite credentials; consumed before policy/receipts and never echoed.
    launch_credentials_v1: dict[str, JsonValue] | None = None''')
    o.replace('gateway/session_policy.py', "'run_budget', 'verbose', 'row_cwd', 'client_env'})",
              "'run_budget', 'verbose', 'row_cwd', 'client_env', 'launch_credentials_v1'})")
    o.function('gateway/session_policy.py', 'build_policy',
               '    unknown = sorted(set(params) - CREATE_FIELDS)',
               '''    if 'launch_credentials_v1' in params:
        _refuse('launch_credentials_v1', 'requires the local creation owner')
    unknown = sorted(set(params) - CREATE_FIELDS)''')
    o.function('gateway/session_controls.py', 'describe',
               "'acp-session-mcp-v1', 'clarify-batch-v1'",
               "'acp-session-mcp-v1', 'clarify-batch-v1', 'finite-launch-credentials-v1'")
    o.function('gateway/session_local.py', 'stage_local_session',
               '    private_secrets = dict(trusted_secrets or {})',
               '''    from gateway.session_launch_credentials import (
        prepare_creation, public_policy, assert_existing, stage_publication,
    )
    prepared_credentials = prepare_creation(authority, actor, params, client_local=client_local)
    params = {key: value for key, value in params.items() if key != 'launch_credentials_v1'}
    private_secrets = dict(trusted_secrets or {})''')
    o.function('gateway/session_local.py', 'stage_local_session',
               "    request_id = params.get('request_id', uuid.uuid4().hex)",
               "    policy = public_policy(authority, policy, prepared_credentials)\n    request_id = params.get('request_id', uuid.uuid4().hex)")
    o.function('gateway/session_local.py', 'stage_local_session',
               "        original = restore_policy(saved['policy'])",
               "        original = restore_policy(saved['policy'])\n        assert_existing(authority, sid, original, prepared_credentials)")
    o.function('gateway/session_local.py', 'stage_local_session',
               '    return staged', '    return stage_publication(staged, authority, prepared_credentials)')
    o.import_line('hermes_state_local.py', 'from gateway.session_launch_credentials import finish_publication')
    o.decorator('hermes_state_local.py', 'commit_local_session', 'finish_publication')
    o.function('gateway/session_finite.py', 'execute_finite_admission',
               "    with finite_turn_scope(row['payload'].get('finite', False), row['payload'].get('unattended') is True),",
               "    from gateway.session_launch_credentials import admission_scope\n    with admission_scope(authority, ref, row), \\\n            finite_turn_scope(row['payload'].get('finite', False), row['payload'].get('unattended') is True),")
    o.function('gateway/session_controls.py', 'cancel',
               "        if row is not None:\n            await self.interrupt(ref, {'execution_generation': row['generation']})",
               "        if row is not None:\n            await self.interrupt(ref, {'execution_generation': row['generation']})\n        else:\n            from gateway.session_launch_credentials import release_unclaimed\n            release_unclaimed(self.authority, ref.session_id)")
    o.function('gateway/session_policy.py', 'release_launch_secrets',
               '    kept = _secret_refs(authority, retired)',
               '''    from gateway.session_launch_credentials import release
    release(authority, retired)
    kept = _secret_refs(authority, retired)''')


def tools_and_redaction(o):
    o.import_line('model_tools.py',
                  'from agent.launch_credential_binding import guard_tool_call, redact as _redact_launch')
    o.decorator('model_tools.py', 'handle_function_call', 'guard_tool_call')
    o.function('model_tools.py', '_execute_tool',
               'return dispatch_connector_call(function_name, next_args, ids.tool_call_id, ids.turn_id, ids.task_id)',
               'return _redact_launch(dispatch_connector_call(function_name, next_args, ids.tool_call_id, ids.turn_id, ids.task_id))')
    o.function('model_tools.py', '_execute_tool',
               'return registry.dispatch(function_name, next_args, **dispatch_kwargs)',
               'return _redact_launch(registry.dispatch(function_name, next_args, **dispatch_kwargs))')
    o.function('model_tools.py', '_execute_tool',
               '''        return run_tool_execution_middleware(function_name, function_args, _dispatch, original_args=original_args,
                                             **ids.hook_kwargs())''',
               '''        return _redact_launch(run_tool_execution_middleware(
            function_name, function_args, _dispatch, original_args=_redact_launch(original_args), **ids.hook_kwargs()))''')
    o.function('model_tools.py', '_emit_post_tool_call_hook',
               '    if _post_tool_call_hook_suppressed.get():',
               '''    function_args, result = _redact_launch(function_args), _redact_launch(result)
    error_message, middleware_trace = _redact_launch(error_message), _redact_launch(middleware_trace)
    if _post_tool_call_hook_suppressed.get():''')
    o.function('model_tools.py', '_apply_transform_tool_result_hook',
               '    try:\n        from hermes_cli.lifecycle',
               '    function_args, result = _redact_launch(function_args), _redact_launch(result)\n    try:\n        from hermes_cli.lifecycle')
    o.function('model_tools.py', '_apply_transform_tool_result_hook',
               'return next((r for r in hook_results if isinstance(r, str)), result)',
               'return _redact_launch(next((r for r in hook_results if isinstance(r, str)), result))')
    o.function('agent/tool_executor.py', '_commit_tool_result',
               '    function_name, function_args, tool_call_id, effective_task_id = ref.name, ref.args, ref.call_id, ref.task_id',
               '''    from agent.launch_credential_binding import redact as _redact_launch
    function_result = _redact_launch(function_result)
    function_name, function_args, tool_call_id, effective_task_id = ref.name, _redact_launch(ref.args), ref.call_id, ref.task_id''')
    o.function('agent/tool_executor.py', '_commit_tool_result',
               '    persisted_result = function_result',
               '    function_result = _redact_launch(function_result)\n    persisted_result = function_result')
    o.function('agent/tool_executor.py', '_commit_tool_result',
               '    messages.append(tool_message)',
               '    tool_message = _redact_launch(tool_message)\n    messages.append(tool_message)')
    o.function('tools/environments/local.py', '_make_run_env',
               '    return run_env',
               '''    # Only a finite, validated synchronous tool dispatch can supply these values.
    from agent.launch_credential_binding import tool_environment
    run_env.update(tool_environment())
    return run_env''')
    o.function('tools/environments/base.py', '_snapshot_excluded_passthrough_names',
               '        if not self._profile_scoped_passthrough:\n            return ()',
               '''        from agent.launch_credential_binding import snapshot_exclusion_names
        self._snapshot_passthrough_names.update(snapshot_exclusion_names())
        if not self._profile_scoped_passthrough:
            return tuple(sorted(self._snapshot_passthrough_names))''')
    o.function('agent/redact.py', 'redact_sensitive_text',
               '    text = redact_registered_vault_values(text)',
               '''    from agent.launch_credential_binding import redact as redact_launch
    text = redact_launch(text)
    text = redact_registered_vault_values(text)''')
    o.function('hermes_logging.py', '_install_session_record_factory',
               '        return record',
               '''        from agent.launch_credential_binding import sanitize_log_record
        return sanitize_log_record(record)''')
    o.function('hermes_logging.py', 'prepare',
               '        return copy.copy(record)',
               '''        from agent.launch_credential_binding import sanitize_log_record
        return sanitize_log_record(copy.copy(record))''')


def validation_errors(o):
    # A malformed private field can fail before any value-bound redactor exists.
    o.replace('tui_gateway/contracts/registry.py', 'def _report(kind: str, name: str, exc: ValidationError) -> None:',
              '''def _input_free_errors(exc):
    return exc.errors(include_input=False, include_context=False, include_url=False)


def _public_error_location(contract, error):
    # Top-level declared names only; never echo private map keys or caller values.
    loc = error.get("loc", ())
    first = loc[0] if loc else None
    return first if isinstance(first, str) and first in contract.params.model_fields else "params"


def _report(kind: str, name: str, exc: ValidationError) -> None:''')
    o.function('tui_gateway/contracts/registry.py', '_report',
               '''    if STRICT:
        raise ContractViolation(f"{kind} {name!r} violates its contract: {exc}") from exc
    logger.error("%s %r violates its wire contract: %s", kind, name, exc)''',
               '''    # Error types are Pydantic codes. Input, messages and exception chains remain private.
    codes = sorted({str(error.get("type", "validation_error")) for error in _input_free_errors(exc)})
    message = f"{kind} {name!r} violates its contract: {', '.join(codes)}"
    if STRICT:
        raise ContractViolation(message) from None
    logger.error("%s", message)''')
    for name in ('validate_params', 'canonical_param_problems'):
        o.function('tui_gateway/contracts/registry.py', name, 'exc.errors()', '_input_free_errors(exc)')
    o.function('tui_gateway/contracts/registry.py', 'validate_params',
               'loc = ".".join(str(p) for p in err.get("loc", ())) or "params"',
               'loc = _public_error_location(contract, err)')
    o.function('tui_gateway/contracts/registry.py', 'validate_params',
               "{err.get('msg')}", 'unknown field')
    o.function('tui_gateway/contracts/registry.py', 'canonical_param_problems',
               '".".join(str(p) for p in err.get("loc", ())) or "params"',
               '_public_error_location(contract, err)')
    o.function('tui_gateway/ws.py', '_dispatch_one',
               '            _log.exception("ws dispatch crash peer=%s id=%s method=%s", peer, req_id, req_method)',
               '''            private = (isinstance(req, dict) and isinstance(req.get("params"), dict)
                       and "launch_credentials_v1" in req["params"])
            if private:
                _log.error("ws private launch dispatch failed")
            else:
                _log.exception("ws dispatch crash peer=%s id=%s method=%s", peer, req_id, req_method)''')
    o.replace('tui_gateway/ws.py',
              '                _log.warning("ws parse error peer=%s index=%d error=%s payload=%r", peer, messages, exc, line[:_WS_LOG_PAYLOAD_PREVIEW])',
              '                _log.warning("ws parse error peer=%s index=%d position=%d length=%d", peer, messages, exc.pos, len(line))')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    overlay = Overlay(args.source)
    plugin_and_client(overlay)
    creation_and_lifecycle(overlay)
    tools_and_redaction(overlay)
    validation_errors(overlay)
    manifest = overlay.render(args.output)
    print(json.dumps({'files': len(manifest), 'output': str(Path(args.output).resolve()), 'runtime_changed': False}))


if __name__ == '__main__':
    main()
