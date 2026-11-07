"""Request-owned content Readers selected by the incumbent A1 authenticator."""
from dataclasses import replace
from urllib.parse import urlsplit

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA, AuthAuditEvent, AuthError, AuthErrorCode,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_content_contract import load_content_profiles
from integrations.mastermind_steward_app.installed import (
    LiveWindowProfilesConfig, _select_profile_for_principal,
    construct_installed_live_window,
)
from integrations.mastermind_steward_app.live_window import CONTENT_SCOPE, live_window_reader


def live_window_reader_with_profiles(config, *, steward_resource, reserved_paths):
    if type(config) is not LiveWindowProfilesConfig:
        raise TypeError('LiveWindowProfilesConfig required')
    policy = validate_resource_policy(config.content_policy)
    if not isinstance(config.authenticator, JwtAuthenticator):
        raise TypeError('incumbent JwtAuthenticator required')
    if validate_resource_policy(config.authenticator.policy) != policy:
        raise ValueError('content policy mismatch')
    if policy.required_scopes != (CONTENT_SCOPE,):
        raise ValueError('separate accepted content scope required')
    if not callable(config.profile_loader) or not callable(config.now):
        raise TypeError('existing configuration loader and clock required')
    if not callable(getattr(config.audit_sink, 'emit', None)):
        raise TypeError('existing audit sink required')
    steward = urlsplit(steward_resource)
    content = urlsplit(policy.resource)
    if (steward.scheme != 'https' or not steward.netloc
            or content.netloc != steward.netloc
            or config.allowed_origin != f'{steward.scheme}://{steward.netloc}'):
        raise ValueError('same existing host required')
    if content.path.rstrip('/') in {path.rstrip('/') for path in reserved_paths}:
        raise ValueError('reserved application path')
    load_content_profiles(config.profile_loader())
    return _ProfileReader(config, policy, steward_resource, tuple(reserved_paths)), content.path.encode('ascii')


class _ProfileReader:
    def __init__(self, config, policy, steward_resource, reserved_paths):
        self.config = config
        self.policy = policy
        self.steward_resource = steward_resource
        self.reserved_paths = reserved_paths

    async def __call__(self, scope, receive, send):
        config = self.config
        code = AuthErrorCode.SCOPE_REFUSED.value
        try:
            headers = [value for key, value in scope.get('headers', ())
                       if key.lower() == b'authorization']
            if len(headers) != 1:
                raise ValueError('authentication required')
            instant = config.now()
            if type(instant) is not int or validate_resource_policy(config.authenticator.policy) != self.policy:
                raise ValueError('authentication refused')
            principal = await config.authenticator.verify_authorization_header(
                headers[0].decode('ascii'), now=instant,
            )
            profile = _select_profile_for_principal(config, principal)
            if profile is None:
                raise ValueError('access denied')
            window = construct_installed_live_window(
                profile=profile, authenticator=config.authenticator,
                content_policy=self.policy, audit_sink=config.audit_sink,
                ceo_ingress_socket_path=config.ceo_ingress_socket_path,
                now=config.now, allowed_origin=config.allowed_origin,
            )
            # This closure belongs to this request and retains one frozen profile.
            # Both the App installation and the control owner's current access
            # must continue to agree before and after every awaited access check.
            async def current_access(verified, source_ref):
                if _select_profile_for_principal(config, verified) != profile:
                    return None
                stamp = await window.current_access(verified, source_ref)
                if _select_profile_for_principal(config, verified) != profile:
                    return None
                return stamp

            reader, _ = live_window_reader(
                replace(window, current_access=current_access),
                steward_resource=self.steward_resource,
                reserved_paths=self.reserved_paths,
            )
        except AuthError as exc:
            code = exc.code.value
        except Exception:
            pass
        else:
            # The accepted Reader authenticates again, owns HTTP guards and
            # audit, checks access before/after reading, and releases the bytes.
            await reader(scope, receive, send)
            return
        try:
            config.audit_sink.emit(AuthAuditEvent(
                schema=AUTH_AUDIT_SCHEMA, policy_id=self.policy.policy_id,
                code=code, accepted=False,
            ))
        except Exception:
            pass
        await send({'type': 'http.response.start', 'status': 401, 'headers': [
            (b'content-type', b'application/json'), (b'cache-control', b'no-store'),
        ]})
        await send({'type': 'http.response.body', 'body': b'{"error":"authentication_required"}'})
