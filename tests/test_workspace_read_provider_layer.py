"""Focused layer tests for the installed read-provider source binding.

Inert by construction: disposable stub owners only, no Runtime, no store, no
network/provider/account call and no repository write. The retained installed
fixture stays the owner of the real composition; these tests own the layering
and exact-recognition negatives for the new nominal source binding.
"""
import ast
import copy
from pathlib import Path

import pytest

from common.executive_workspace_contract import RESOURCE, SCOPE
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA, load_resource_policy, subject_digest,
)
from control_plane import workspace_read_provider_binding as layer
from control_plane.workspace_read_provider_binding import (
    _ATTRIBUTE, _KEY, _SOURCE_ATTRIBUTE, _Provider, _ReaderLease, _SourceBinding,
    bind_installed_read_provider, installed_read_provider,
    installed_read_source_binding, _issue_installed_read_source,
)
from integrations.mastermind_workspace_app import installed_read_provider_binding as helper

REPO = Path(__file__).resolve().parents[1]


def _policy():
    issuer = 'https://issuer.example.invalid'
    return load_resource_policy(dict(
        schema=AUTH_POLICY_SCHEMA, policy_id='workspace-read-layer',
        resource=RESOURCE,
        resource_metadata_url=RESOURCE + '/.well-known/oauth-protected-resource',
        issuer=issuer, authorization_servers=[issuer],
        jwks_uri=issuer + '/.well-known/jwks.json', required_scopes=[SCOPE],
        allowed_subject_digests=[subject_digest(issuer=issuer, subject='inert-chairman')],
        allowed_algorithms=['RS256'], clock_skew_seconds=30,
        max_token_lifetime_seconds=900, jwks_cache_ttl_seconds=300,
        unknown_kid_refresh_cooldown_seconds=30, fetch_failure_backoff_seconds=5))


def _integration_imports(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return [name for name in found if name.split('.')[0] == 'integrations']


def test_changed_core_has_no_integrations_imports():
    tree = ast.parse((REPO / 'control_plane/workspace_read_provider_binding.py').read_text())
    assert _integration_imports(tree) == []


def test_helper_imports_core_and_lives_under_integrations():
    path = Path(helper.__file__)
    assert path.relative_to(REPO).parts[:1] == ('integrations',)
    tree = ast.parse(path.read_text())
    sources = [node.module for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module]
    assert 'control_plane.workspace_read_provider_binding' in sources


def test_installed_constructor_is_the_only_issuer():
    source = (REPO / 'integrations/mastermind_workspace_app/installed_source_operations.py').read_text()
    tree = ast.parse(source)
    init = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'InstalledWorkspaceSourceOperations':
            init = next(item for item in node.body
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__')
    assert init is not None
    calls = [node for node in ast.walk(init) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'install_installed_read_source']
    assert len(calls) == 1 and [arg.id for arg in calls[0].args] == ['self']


class StubStore:
    pass


class StubRuntime:
    def __init__(self):
        self.store = StubStore()


class StubOwnerBinding:
    fingerprint = 'f' * 64


class StubPermissions:
    def __init__(self, policy):
        self.policy = policy
        self._load_bindings = lambda: None
        self._now = lambda: None


class StubCollector:
    def __init__(self):
        self._source_root = 'source-root'
        self._macro_root = 'macro-root'
        self._code_root = 'code-root'
        self._python = 'python'
        self._runner = lambda *args, **kwargs: None
        self._expected_source_sha = 's' * 40
        self._allow_synthetic_fixture = True
        self.read_project_plan = lambda **kwargs: None
        self.read_project_discovery = lambda **kwargs: None
        self.read_project_discovery_source = lambda **kwargs: None
        self.read_project_knowledge_catalogue = lambda **kwargs: None
        self.read_project_knowledge_memory = lambda **kwargs: None
        self.read_project_knowledge_source = lambda **kwargs: None
        self.canonical_project_data_scope = lambda **kwargs: None
        self.canonical_project_compilation_scope = lambda **kwargs: None
        self._collect_packet = lambda **kwargs: None
        self._capture_canonical_code = lambda **kwargs: None
        self._bind_canonical_code_capture = lambda **kwargs: None


class StubIdentity:
    def __init__(self):
        self.binding = StubOwnerBinding()
        self._path = 'identity-path'
        self._expected = ('expected',)
        self._selection = {'work_ref': 'WS:inert'}
        self.qualify = lambda binding: True
        self._configuration_calls = []

    def _configuration(self):
        self._configuration_calls.append(True)


class StubSource:
    def __init__(self, policy):
        self._collector = StubCollector()
        self._git = StubIdentity()
        self._permissions = StubPermissions(policy)
        self._runtime_guard = lambda runtime: True
        self._compiler = object()
        self._journey = object()

    def read_bindings(self, runtime):
        return runtime

    def canonical_data_owner(self, runtime):
        return runtime


def _stub_factory():
    armed = {'mode': 'inert'}
    runtime_identity = {'runtime': 'inert'}

    def provide(runtime):
        return (armed, runtime_identity, runtime)

    return provide


def _stub_source(monkeypatch):
    """A disposable source the installed-type gates accept for this test."""
    from integrations.mastermind_workspace_app import installed_source_operations as iso
    from integrations.mastermind_workspace_app import project_git_identity as pgi
    from integrations.mastermind_workspace_app import source_operation_context as soc
    from integrations.executive_mcp import installed as exec_installed
    monkeypatch.setattr(iso, 'InstalledWorkspaceSourceOperations', StubSource)
    monkeypatch.setattr(pgi, 'InstalledProjectGitIdentity', StubIdentity)
    monkeypatch.setattr(exec_installed, 'InstalledBootPacketCollector', StubCollector)
    monkeypatch.setattr(soc, 'WorkspaceSourceOperationContextFactory', StubPermissions)
    source = StubSource(_policy())
    helper.install_installed_read_source(source)
    return source


def _installed_stub(monkeypatch):
    """Full nominal composition over disposable stub owners, real capture."""
    source = _stub_source(monkeypatch)
    provide = _stub_factory()
    monkeypatch.setattr(layer, '_fixed_factory_code', lambda: provide.__code__)
    provide = bind_installed_read_provider(provide, source.read_bindings)
    return source, provide, source._permissions.policy


def test_issuer_validates_function_types_and_live_qualifier():
    source = StubSource(_policy())
    ok = dict(qualifier=lambda value: True, capture=lambda *args, **kwargs: None,
              read_function=StubSource.read_bindings,
              owner_function=StubSource.canonical_data_owner,
              guard_function=source._runtime_guard)
    binding = _issue_installed_read_source(source, **ok)
    assert type(binding) is _SourceBinding and binding.key is _KEY
    assert binding.lifetime.issuer is binding and binding.source is source
    assert binding.read_function is StubSource.read_bindings
    assert binding.qualifier.__code__ is binding.qualifier_code
    assert binding.capture.__code__ is binding.capture_code
    with pytest.raises(ValueError):
        _issue_installed_read_source(source, **dict(ok, qualifier='not callable'))
    with pytest.raises(ValueError):
        _issue_installed_read_source(source, **dict(ok, qualifier=lambda value: False))
    with pytest.raises(ValueError):
        _issue_installed_read_source(source, **dict(ok, capture=None))
    with pytest.raises(ValueError):
        _issue_installed_read_source(None, **ok)
    with pytest.raises(ValueError):
        _issue_installed_read_source(source, **dict(ok, read_function='read'))


def test_recognition_demands_the_exact_nominal_binding(monkeypatch):
    source = _stub_source(monkeypatch)
    binding = installed_read_source_binding(source.read_bindings)
    assert type(binding) is _SourceBinding and binding.source is source
    assert installed_read_source_binding(lambda runtime: None) is None
    assert installed_read_source_binding(None) is None
    foreign = StubSource(_policy())
    assert installed_read_source_binding(foreign.read_bindings) is None
    forged = StubSource(_policy())
    setattr(forged, _SOURCE_ATTRIBUTE, object())
    with pytest.raises(ValueError):
        installed_read_source_binding(forged.read_bindings)
    copied = StubSource(_policy())
    setattr(copied, _SOURCE_ATTRIBUTE, copy.copy(binding))
    with pytest.raises(ValueError):
        installed_read_source_binding(copied.read_bindings)
    crossed = StubSource(_policy())
    setattr(crossed, _SOURCE_ATTRIBUTE, binding)
    with pytest.raises(ValueError):
        installed_read_source_binding(crossed.read_bindings)


def test_bind_tags_only_the_fixed_installed_factory(monkeypatch):
    source = _stub_source(monkeypatch)
    provide = _stub_factory()
    monkeypatch.setattr(layer, '_fixed_factory_code', lambda: provide.__code__)

    def arbitrary(runtime):
        raise AssertionError('arbitrary callback ran')

    with pytest.raises(ValueError):
        bind_installed_read_provider(arbitrary, source.read_bindings)
    assert installed_read_provider(arbitrary) is None
    assert not hasattr(arbitrary, _ATTRIBUTE)
    foreign = StubSource(_policy())
    assert bind_installed_read_provider(provide, foreign.read_bindings) is provide
    assert not hasattr(provide, _ATTRIBUTE)
    assert bind_installed_read_provider(provide, source.read_bindings) is provide
    assert type(installed_read_provider(provide)) is _Provider
    with pytest.raises(ValueError):
        bind_installed_read_provider(provide, source.canonical_data_owner)


def test_provider_context_rejects_provider_and_binding_drift(monkeypatch):
    source, provide, policy = _installed_stub(monkeypatch)
    runtime = StubRuntime()
    provider = installed_read_provider(provide)
    first = provider.context(runtime)
    assert first[1][5] == 's' * 40
    assert source._git._configuration_calls == [True]
    with pytest.raises(ValueError):
        provider.context(runtime, expected=(first[0], first[1][:-1]))
    setattr(provide, _ATTRIBUTE, copy.copy(provider))
    with pytest.raises(ValueError):
        provider.context(runtime)
    setattr(provide, _ATTRIBUTE, provider)
    object.__delattr__(provide, _ATTRIBUTE)
    with pytest.raises(ValueError):
        provider.context(runtime)
    setattr(provide, _ATTRIBUTE, object.__new__(_ReaderLease))
    with pytest.raises(ValueError):
        provider.context(runtime)
    shifted = object.__new__(_Provider)
    for slot in _Provider.__slots__:
        object.__setattr__(shifted, slot, getattr(provider, slot))
    object.__setattr__(shifted, 'closure', ())
    setattr(provide, _ATTRIBUTE, shifted)
    with pytest.raises(ValueError):
        provider.context(runtime)
    setattr(provide, _ATTRIBUTE, provider)
    drift = provide.__closure__[0].cell_contents
    drift['changed'] = True
    with pytest.raises(ValueError):
        provider.context(runtime, expected=first)
    del drift['changed']
    assert provider.context(runtime, expected=first) == first


def test_capture_refuses_every_source_outside_the_installed_type(monkeypatch):
    runtime = StubRuntime()
    with pytest.raises(ValueError):
        helper.install_installed_read_source(object())
    with pytest.raises(ValueError):
        helper.install_installed_read_source(StubSource(_policy()))
    source = StubSource(_policy())
    provide = _stub_factory()
    monkeypatch.setattr(layer, '_fixed_factory_code', lambda: provide.__code__)
    assert bind_installed_read_provider(provide, source.read_bindings) is provide
    assert not hasattr(provide, _ATTRIBUTE)
    setattr(source, _SOURCE_ATTRIBUTE, _issue_installed_read_source(
        source, qualifier=lambda value: True, capture=helper._capture,
        read_function=StubSource.read_bindings,
        owner_function=StubSource.canonical_data_owner,
        guard_function=source._runtime_guard))
    tagged = bind_installed_read_provider(_stub_factory(), source.read_bindings)
    provider = installed_read_provider(tagged)
    with pytest.raises(ValueError):
        provider.context(runtime)


def test_capture_negatives_for_source_method_code_and_literals(monkeypatch):
    source, provide, policy = _installed_stub(monkeypatch)
    provider = installed_read_provider(provide)
    runtime = StubRuntime()
    before = provider.context(runtime)
    guard_calls = []
    original_guard = source._runtime_guard
    source._runtime_guard = lambda runtime: guard_calls.append(True) or True
    with pytest.raises(ValueError):
        provider.context(runtime, expected=before)
    assert not guard_calls and source._git._configuration_calls == [True]
    source._runtime_guard = lambda runtime: False
    with pytest.raises(ValueError):
        provider.context(runtime)
    source._runtime_guard = original_guard
    original_method = StubSource.read_bindings
    monkeypatch.setattr(StubSource, 'read_bindings', lambda self, runtime: None)
    with pytest.raises(ValueError):
        provider.context(runtime)
    monkeypatch.setattr(StubSource, 'read_bindings', original_method)
    source.read_bindings = lambda runtime: None
    with pytest.raises(ValueError):
        provider.context(runtime, expected=before)
    del source.__dict__['read_bindings']
    assert provider.context(runtime, expected=before) == before
    source._collector._expected_source_sha = '0' * 40
    with pytest.raises(ValueError):
        provider.context(runtime, expected=before)
    source._collector._expected_source_sha = 's' * 40
    original_owner = StubSource.canonical_data_owner
    monkeypatch.setattr(StubSource, 'canonical_data_owner', lambda self, runtime: None)
    with pytest.raises(ValueError):
        provider.context(runtime)
    monkeypatch.setattr(StubSource, 'canonical_data_owner', original_owner)
    assert source._git._configuration_calls == [True, True]


def test_nominal_source_binding_is_recognition_data_only(monkeypatch):
    source = _stub_source(monkeypatch)
    binding = installed_read_source_binding(source.read_bindings)
    assert binding.qualifier is helper._qualify
    assert binding.capture is helper._capture
    assert binding.read_function is StubSource.read_bindings
    assert binding.owner_function is StubSource.canonical_data_owner
    assert binding.guard_function is source._runtime_guard
    assert set(_SourceBinding.__slots__) == {
        'key', 'source', 'qualifier', 'qualifier_code', 'capture', 'capture_code',
        'read_function', 'owner_function', 'guard_function', 'lifetime'}


def test_foreign_source_descriptor_property_never_executes():
    calls = []
    class ForeignSource:
        def read_bindings(self, runtime):
            raise AssertionError('foreign source entered')
        @property
        def _installed_workspace_read_source(self):
            calls.append(True)
            raise AssertionError('foreign property entered during recognition')
    with pytest.raises(ValueError):
        installed_read_source_binding(ForeignSource().read_bindings)
    assert calls == []
