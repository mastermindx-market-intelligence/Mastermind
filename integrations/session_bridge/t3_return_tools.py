"""Original-run return linking over the incumbent authenticated Session Bridge.

Linking creates only the existing Runtime return reference. It never launches a
T3 thread, chooses a provider, subscribes a callback, acknowledges a result or
expands account access. The separately authenticated event subscription remains
ChatGPT's native MCP Events operation, not a model-authored callback URL.
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping

from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.executive_mcp.schemas import GatewayError, ToolSpec
from .schemas import BridgeError
from .t3_native_client import Unavailable, Conflict
from .t3_reply_events import (_run, _identity, REQUEST_PREFIX, READ_PREFIX,
    is_t3_request_ref, T3ReturnEffectUnknown)
from .web_reply_subscription_owner import owner_key

LINK = 'session_t3_return_link'
STATUS = 'session_t3_return_status'
NAMES = (LINK, STATUS)
SCHEMA = 'mastermind.t3_return_control.v1'
_ID = {'type': 'string', 'minLength': 1, 'maxLength': 256}
_SCOPE = {'type': 'object', 'additionalProperties': False,
    'required': ['connection_id', 'environment_id', 'project_id', 'capacity_provider_id'],
    'properties': {**{key: _ID for key in ('connection_id', 'environment_id', 'project_id')},
                   'capacity_provider_id': {'const': 'capacity_fabric'}}}
_RUN = {'type': 'object', 'additionalProperties': False,
    'required': ['thread', 'run_id', 'request_id', 'delivery', 'message_id'],
    'properties': {'thread': {'type': 'object', 'additionalProperties': False,
        'required': ['scope', 'thread_id'], 'properties': {'scope': _SCOPE, 'thread_id': _ID}},
        'run_id': _ID, 'request_id': _ID,
        'delivery': {'enum': ['launched', 'queued', 'started', 'steered', 'restarted']},
        'message_id': {'anyOf': [_ID, {'type': 'null'}]}}}


def validate_return_arguments(name, arguments):
    if type(arguments) is not dict:
        raise ValueError('Closed original-return arguments required')
    if name == LINK:
        if set(arguments) not in ({'run'}, {'run', 'ttl_seconds'}):
            raise ValueError('Exact observed native Run receipt required')
        run = _run(arguments['run'])
        ttl = arguments.get('ttl_seconds', 3600)
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise ValueError('Bounded original-return lifetime required')
        return {'run': dataclasses.asdict(run), 'ttl_seconds': ttl}
    if name == STATUS and set(arguments) == {'request_ref'} and is_t3_request_ref(arguments['request_ref']):
        return dict(arguments)
    raise ValueError('Exact original native request reference required')


def validate_observer(value):
    if type(value) is not dict:
        raise ValueError('Closed original observer status required')
    if set(value) == {'state'} and value['state'] in {'NOT_SELECTED', 'NOT_STARTED'}:
        return value
    fields = {'state', 'code', 'observations', 'transport', 'maximum_wait_ms',
              'minimum_observation_interval_seconds', 'automatic_reconnect', 'native_inference_started'}
    states = {'NOT_STARTED', 'STARTING', 'RESOLVING_ORIGINAL_SUBSCRIBER', 'WAITING_NATIVE',
              'CONSUMING_ORIGINAL_OBSERVATION', 'WAITING_NATIVE_INTERVAL', 'STOPPED', 'UNAVAILABLE', 'EFFECT_UNKNOWN'}
    codes = {None, 'NO_CURRENT_ORIGINAL_SUBSCRIBER', 'ORIGINAL_RETURN_BOUNDARY_REACHED',
             'ORIGINAL_RETURN_COMMIT_UNCERTAIN', 'OWNED_OBSERVER_CANCELLED', 'ORIGINAL_NATIVE_RETURN_UNAVAILABLE'}
    if (set(value) != fields or value['state'] not in states or value['code'] not in codes
            or type(value['observations']) is not int or not 0 <= value['observations'] < 2**53
            or value['transport'] != 'native_exact_run_wait'
            or type(value['maximum_wait_ms']) is not int or not 1 <= value['maximum_wait_ms'] <= 30000
            or type(value['minimum_observation_interval_seconds']) not in (int, float)
            or not 0 < value['minimum_observation_interval_seconds'] <= 30
            or value['automatic_reconnect'] is not False or value['native_inference_started'] is not False):
        raise ValueError('Original observer returned unqualified fields')
    return value


def original_references(principal, run):
    ident = _identity(owner_key(principal), run)
    return {'request_ref': REQUEST_PREFIX + ident, 'read_ref': READ_PREFIX + ident}


class RuntimeT3ReturnControl:
    def __init__(self, host):
        from .installed_reply_events import RuntimeReplyEventHost
        if type(host) is not RuntimeReplyEventHost or host.returns.t3_replies is None:
            raise TypeError('Existing Runtime reply-event host and native source required')
        self.host, self.source = host, host.returns.t3_replies

    async def __call__(self, principal, name, arguments):
        args = validate_return_arguments(name, arguments)
        try:
            if not self.host.enabled:
                raise Unavailable('Original native return owner is not selected')
            self.host.policies.select(principal)
            if name == LINK:
                from integrations.mastermind_executive_app.gateway import SUBMIT_SCOPE
                if SUBMIT_SCOPE not in principal.scopes:
                    raise BridgeError('scope_refused', 'Original-return linking requires the existing submit scope')
                binding = await self.source.bind(principal, _run(args['run']), ttl_seconds=args['ttl_seconds'])
                return {'schema': SCHEMA, 'operation': name, 'binding': binding,
                        'monitor_selected': self.host.t3_monitor is not None,
                        'native_inference_started': False, 'parent_consumed': False}
            grant = await self.source.resolve(principal, args['request_ref'])
            observation = {'state': 'NOT_SELECTED'}
            if self.host.t3_monitor is not None:
                from .t3_reply_monitor import _key
                projection, _, _, run = self.source._binding(principal, args['request_ref'])
                observer = self.host.t3_monitor.observers.get(_key(projection, run))
                observation = {'state': 'NOT_STARTED'} if observer is None else observer.status()
            return {'schema': SCHEMA, 'operation': name, 'request_ref': grant.request_ref,
                    'read_ref': grant.read_ref, 'expires_at': grant.expires_at,
                    'access_current': grant.access_current, 'observer': observation,
                    'native_inference_started': False, 'parent_consumed': False}
        except T3ReturnEffectUnknown:
            raise BridgeError('effect_unknown', 'Reconcile the exact original return reference; do not relaunch or relink') from None
        except (Unavailable, Conflict):
            raise BridgeError('reply_unavailable', 'Original native return access is unavailable') from None


class T3ReturnTools:
    def __init__(self, client):
        from .installed import InstalledSessionBridgeClient
        if type(client) is not InstalledSessionBridgeClient:
            raise TypeError('Same installed authenticated Session Bridge client required')
        self.client = client

    @staticmethod
    def specs():
        return (
            ToolSpec(name=LINK, description='Link one exact observed T3 Run receipt to the authenticated original account. Creates a return reference only: no native launch, callback subscription, provider change or acceptance. Preserve the returned request_ref for MCP Events and read_ref for canonical reads. Never repeat an uncertain link or relaunch its worker.',
                input_schema={'type': 'object', 'additionalProperties': False, 'required': ['run'],
                    'properties': {'run': _RUN, 'ttl_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 86400}}},
                output_description=SCHEMA, read_only=False),
            ToolSpec(name=STATUS, description='Read one exact original T3 return binding and its native-observer readiness. Subscription, active observation, callback delivery, parent consumption and acceptance are distinct. No worker, callback, retry or subscription is started.',
                input_schema={'type': 'object', 'additionalProperties': False, 'required': ['request_ref'],
                    'properties': {'request_ref': {'type': 'string', 'pattern': '^t3-request-[0-9a-f]{64}$'}}},
                output_description=SCHEMA, read_only=True),
        )

    @staticmethod
    def validate(name, arguments):
        try: return validate_return_arguments(name, arguments)
        except (ValueError, TypeError, KeyError):
            raise GatewayError('invalid_input', 'Exact original T3 return arguments required') from None

    @staticmethod
    def error(name, code, message=None, original=None):
        safe = code if code in {'invalid_input', 'effect_unknown', 'reply_unavailable', 'scope_refused', 'not_found'} else 'backend_unavailable'
        return {'schema': SCHEMA, 'operation': name, 'ok': False, 'data': None,
                'error': {'code': safe, 'message': 'Original T3 return operation unavailable; preserve its original reference'},
                'original': original, 'retry_allowed': False, 'parent_consumed': False}

    async def handle(self, principal, name, arguments):
        args = self.validate(name, arguments)
        projection = principal_projection(principal)
        original = (original_references(projection, _run(args['run'])) if name == LINK else
                    {'request_ref': args['request_ref'], 'read_ref': READ_PREFIX + args['request_ref'][len(REQUEST_PREFIX):]})
        try:
            value = await self.client.return_control(principal, name, args)
            if (type(value) is not dict or value.get('schema') != SCHEMA or value.get('operation') != name
                    or value.get('native_inference_started') is not False or value.get('parent_consumed') is not False):
                raise ValueError('Unqualified native return receipt')
            if name == LINK:
                if set(value) != {'schema', 'operation', 'binding', 'monitor_selected', 'native_inference_started', 'parent_consumed'}:
                    raise ValueError('Unexpected return binding fields')
                bound = value['binding']
                if (type(bound) is not dict or set(bound) != {'request_ref', 'read_ref', 'expires_at', 'request_event_sha256', 'native_execution', 'subscription', 'parent_consumed'}
                        or bound.get('request_ref') != original['request_ref'] or bound.get('read_ref') != original['read_ref']
                        or bound.get('native_execution') != 'NOT_CREATED' or bound.get('subscription') != 'NOT_CREATED'
                        or bound.get('parent_consumed') is not False or type(value['monitor_selected']) is not bool
                        or type(bound.get('expires_at')) is not int
                        or re.fullmatch('[0-9a-f]{64}', str(bound.get('request_event_sha256'))) is None):
                    raise ValueError('Original return binding mismatch')
            else:
                if (set(value) != {'schema', 'operation', 'request_ref', 'read_ref', 'expires_at', 'access_current', 'observer', 'native_inference_started', 'parent_consumed'}
                        or value['request_ref'] != original['request_ref'] or value['read_ref'] != original['read_ref']
                        or type(value['expires_at']) is not int or value['access_current'] is not True
                        or type(value['observer']) is not dict or len(value['observer']) > 12):
                    raise ValueError('Original return status mismatch')
                validate_observer(value['observer'])
            if len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode()) > 8192:
                raise ValueError('Return receipt exceeds budget')
            return {'schema': SCHEMA, 'operation': name, 'ok': True, 'data': value,
                    'error': None, 'original': original, 'retry_allowed': False, 'parent_consumed': False}
        except BridgeError as exc:
            return self.error(name, exc.code, original=original)
        except Exception:
            return self.error(name, 'effect_unknown' if name == LINK else 'reply_unavailable', original=original)

    def extend_host_configuration(self, configuration: Mapping):
        import mcp.types as mt
        tools, names = configuration['profile_tools'], configuration.get('direct_tool_names', ())
        submits = configuration.get('direct_submit_names', ())
        prior_validate, prior_handler = configuration['profile_validator'], configuration.get('direct_handler')
        prior_error = configuration.get('direct_error_factory')
        if (configuration.get('release_profile', False) is not False
                or any(name in names or any(tool.name == name for tool in tools) for name in NAMES)
                or type(tools) is not tuple or type(names) is not tuple or type(submits) is not tuple):
            raise ValueError('Original authenticated profile is incompatible with T3 return tools')
        additions = tuple(mt.Tool(name=spec.name, description=spec.description, inputSchema=spec.input_schema,
            annotations=mt.ToolAnnotations(**{**spec.annotations, 'idempotentHint': spec.read_only,
                                              'openWorldHint': True})) for spec in self.specs())
        def validate(name, args):
            return self.validate(name, args) if name in NAMES else prior_validate(name, args)
        async def handle(principal, name, args):
            if name in NAMES: return await self.handle(principal, name, args)
            if name not in names or prior_handler is None: raise GatewayError('not_found', 'Unknown direct tool')
            return await prior_handler(principal, name, args)
        def error(name, code, message):
            if name in NAMES: return self.error(name, code, message)
            if name not in names or prior_error is None: raise GatewayError('not_found', 'Unknown direct tool')
            return prior_error(name, code, message)
        return dict(configuration, profile_tools=tools + additions, profile_validator=validate,
            direct_tool_names=names + NAMES, direct_submit_names=submits + (LINK,),
            direct_handler=handle, direct_error_factory=error)
