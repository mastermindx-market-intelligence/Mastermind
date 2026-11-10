"""Compose PR #2285's adapter with Hermes' existing per-profile plugin owner.

This is an in-process, host-only seam, not an authentication boundary against
arbitrary Python running as the host. The enrolled host must already own the
authenticated session resolver, source grants and sealed key custodian. This
module never reads a key, issues a token at load time, or retains a session map.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from integrations.github_review_app_token import (
    AUTHORING_PERMISSIONS, GitHubAppInstallationTokens,
)
from integrations.hermes_github_native import (
    HostHermesGitHubBinding, NativeToolRegistrationError, _current, register_native_tool,
)
from integrations.hermes_harness.native_tool_registration import _loading_mode_refusal

PLUGIN_NAME = "mmx_github"
# One reviewed manager slot attribute, named in the host-port precedent of
# ``integrations/hermes_harness/native_executive_consumer.py``
# (``CONSUMER_SLOT_ATTRIBUTE``). It is a Python attribute, not an account or
# service identity, so it never carries the identity-name prefix the release
# identity guard reserves for principals.
GITHUB_APP_HOST_SLOT_ATTRIBUTE = "_mmx_github_app_host"


class GitHubPluginHost:
    """One retained registration carrier on the actual native PluginManager.

    The host retains clients in its EXISTING session owner. Every resolution checks
    the same issuer, actor, profile and session grant; no client is created or cached
    here. A failed registration retains its original exception/context for host
    reconciliation. There is deliberately no automatic retry or replacement.
    """

    def __init__(self, manager: Any, *, binding: HostHermesGitHubBinding,
                 issuer: GitHubAppInstallationTokens, app_bot_login: str,
                 package_path: Path):
        self._manager = manager
        self._scope = manager.scope_key
        self._binding = binding
        self._issuer = issuer
        self._actor = app_bot_login
        self._package = package_path
        self._lock = RLock()
        self.registration = None
        self.registration_context = None
        self.registration_error = None
        self.cleanup_error = None
        self.unload_handle = None
        self.registration_attempted = False
        self._closed = False
        self._native_binding = HostHermesGitHubBinding(
            profile_id=binding.profile_id,
            resolve_client=self._resolve,
            currentness_guard=self.is_current,
        )

    def is_current(self) -> bool:
        return (not self._closed
                and getattr(self._manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE, None) is self
                and self._manager.scope_key == self._scope
                and self._binding.is_current())

    def _resolve(self, session_id: str):
        if not self.is_current():
            return None
        client = self._binding.resolve(session_id)
        if client is None:
            return None
        grant = client.binding
        # Identity checks keep a different App/actor from borrowing this slot.
        # HostGitHubSession already checks repo/install/authoring permissions.
        if (grant.token_source is not self._issuer
                or grant.app_bot_login != self._actor
                or grant.token_source._permissions != AUTHORING_PERMISSIONS):
            return None
        if not _current(grant.currentness_guard):
            return None
        return client if self.is_current() else None

    def close(self) -> None:
        """Release a known lease, retaining any uncertain original carrier."""
        from registration_lifecycle import replacement_coordinator
        from tools.registry import registry

        with self._lock:
            self._closed = True
            if (self.registration_error is not None or self.cleanup_error is not None
                    or self.registration_attempted and self.registration is None):
                return
            with replacement_coordinator.transaction():
                if self.registration is not None:
                    try:
                        self.registration.dispose()
                        if registry.snapshot_registration("mmx_github", scope=self._scope) is self.registration.entry:
                            raise NativeToolRegistrationError("GITHUB_PLUGIN_UNLOAD_UNVERIFIED")
                    except Exception as error:
                        self.cleanup_error = error
                        raise NativeToolRegistrationError("GITHUB_PLUGIN_UNLOAD_EFFECT_UNKNOWN") from None
                # A stale unload callback must never remove a later host binding.
                if getattr(self._manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE, None) is self:
                    delattr(self._manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE)


def bind_native_host(manager: Any, *, binding: HostHermesGitHubBinding,
                     issuer: GitHubAppInstallationTokens, app_bot_login: str,
                     package_path: Path) -> GitHubPluginHost:
    """Bind before native discovery; never load plugins or probe credentials.

    Use the installed get_plugin_manager(), the exact installed plugin directory,
    and the host's retained authoring issuer (whose private_key_source stays in the
    sealed custodian). This call registers no tool and performs no network I/O.
    """
    from hermes_cli.plugins import PluginManager
    from registration_lifecycle import replacement_coordinator

    if (type(manager) is not PluginManager
            or type(manager.scope_key) is not str or not manager.scope_key):
        raise NativeToolRegistrationError("GITHUB_PLUGIN_MANAGER_INVALID")
    if (not isinstance(binding, HostHermesGitHubBinding) or not binding.is_current()
            or not isinstance(issuer, GitHubAppInstallationTokens)
            or issuer._permissions != AUTHORING_PERMISSIONS
            or type(app_bot_login) is not str or not app_bot_login.endswith("[bot]")):
        raise NativeToolRegistrationError("GITHUB_PLUGIN_HOST_INVALID")
    path = Path(package_path)
    if (not path.is_absolute() or path.is_symlink()
            or not (path / "__init__.py").is_file()
            or not (path / "plugin.yaml").is_file()):
        raise NativeToolRegistrationError("GITHUB_PLUGIN_PACKAGE_INVALID")
    path = path.resolve()
    with replacement_coordinator.transaction():
        existing = getattr(manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE, None)
        if existing is not None:
            if (type(existing) is GitHubPluginHost
                    and existing._manager is manager
                    and existing._binding is binding and existing._issuer is issuer
                    and existing._actor == app_bot_login and existing._package == path
                    and existing.is_current()):
                return existing
            raise NativeToolRegistrationError("GITHUB_PLUGIN_HOST_ALREADY_BOUND")
        slot = GitHubPluginHost(manager, binding=binding, issuer=issuer,
                                app_bot_login=app_bot_login, package_path=path)
        setattr(manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE, slot)
        return slot


def register_from_host(ctx: Any, *, package_path: Path):
    """Called only by the single-argument directory-plugin entry point."""
    from hermes_cli.plugins import PluginContext

    if type(ctx) is not PluginContext:
        raise NativeToolRegistrationError("GITHUB_PLUGIN_CONTEXT_INVALID")
    slot = getattr(ctx._manager, GITHUB_APP_HOST_SLOT_ATTRIBUTE, None)
    if slot is None:
        return None  # ordinary unbound discovery is inert
    if type(slot) is not GitHubPluginHost or slot._manager is not ctx._manager:
        raise NativeToolRegistrationError("GITHUB_PLUGIN_HOST_INVALID")
    with slot._lock:
        manifest = ctx.manifest
        if (not slot.is_current() or ctx.profile_name != slot._binding.profile_id
                or manifest.name != PLUGIN_NAME or ctx.plugin_id != PLUGIN_NAME
                or manifest.source != "user"
                or Path(manifest.path).resolve() != slot._package
                or Path(package_path).resolve() != slot._package):
            raise NativeToolRegistrationError("GITHUB_PLUGIN_OWNER_MISMATCH")
        refusal = _loading_mode_refusal(ctx)
        if refusal:
            raise NativeToolRegistrationError(refusal)
        if slot.registration_attempted:
            raise NativeToolRegistrationError("GITHUB_PLUGIN_ORIGINAL_REGISTRATION_RETAINED")
        slot.registration_attempted = True
        slot.registration_context = ctx
        try:
            slot.registration = register_native_tool(
                ctx, slot._native_binding, profile_id=slot._binding.profile_id,
            )
            slot.unload_handle = ctx.on_unload(slot.close)
            if slot.unload_handle is None:
                raise NativeToolRegistrationError("GITHUB_PLUGIN_UNLOAD_HOOK_UNVERIFIED")
        except Exception as error:
            slot.registration_error = error
            raise
        return slot.registration
