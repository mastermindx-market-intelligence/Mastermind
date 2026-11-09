"""Fixed native-owner wiring proposal; no CLI, permission issuer or activation.

The current native tool bridge does not export NativeMetadataPermissionSource.
The default source therefore refuses before original metadata, intent or carrier
access. A subclass supplied by an authenticated tool host is a trusted-process
integration seam, not an authentication mechanism against Python callers.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
from types import MethodType

import artifact_delivery as delivery
import artifact_reader as artifacts
import original_directory_custody_reader as reader
from current_source_observation import NativeInvocationOwner

HERE = Path(__file__).resolve().parent
DESTINATION = '/Volumes/Mastermind/evidence/mmos-commission-01a15741/fabric-integration-source-01a1a005/prophet-original-plan/metadata-action-v1'
ORIGINAL = Path('/Volumes/Mastermind/evidence/prophet-r6-local-20261008-01a11e89/prophet-end-to-end-resumption-20261012/paper-to-product-20261014/product-reset-20261015')
METADATA = ((ORIGINAL/'plan-review-original-binding.json', reader.ORIGINAL_BINDING_SHA256),
            (ORIGINAL/'plan-review-original-collection-1230/read-request.json', reader.ORIGINAL_REQUEST_SHA256))


class NativeMetadataPermissionSource(NativeInvocationOwner):
    """Required host-side permission export, presently unsupported.

    open_permission must consume an authentic, currently applicable OS/tool
    action permission, not a user-supplied receipt, root label or CURRENT grant.
    The opaque context must bind the exact view, invoking native principal,
    selected source closure and whole host entry. binding() must derive the
    enrolled same SSH account and expected non-root UID from that permission's
    authenticated account binding. No bearer token or raw account is relayed.

    current() must revalidate that SAME context and account without reissuing or
    refreshing a grant. No existing adapter exports these facts; defaults deny.
    A boolean, mapping, nominal type or a test implementation is not that grant.
    """
    def open_permission(self, view, invoking_uid, source_sha256, host_entry_sha256):
        return None

    def current(self, context, view, invoking_uid, source_sha256, host_entry_sha256):
        return False

    def binding(self, context):
        return None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _sources():
    # Fixed executable inputs, read with the incumbent no-follow owned reader.
    names = ('artifact_delivery.py', 'artifact_reader.py', 'artifact_production.py',
             'current_source_observation.py', 'native_runtime_bindings.py',
             'original_directory_custody_reader.py', 'original_directory_custody_owner.py')
    return {name: _sha(delivery.local_file(HERE/name, 262144)) for name in names}


def _entry():
    raw = delivery.local_file(HERE/'hosts.json', 65536)
    registry = artifacts.strict_json(raw)
    entry = registry.get(reader.HOST) if type(registry) is dict else None
    if (type(entry) is not dict or type(entry.get('roles')) is not list
            or 'lanes' not in entry['roles'] or type(entry.get('ssh_alias')) is not str
            or reader.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', entry['ssh_alias']) is None):
        raise reader.Refused('original_directory_registry_unqualified')
    return raw, entry


def owner_factory(permission_source=None):
    """Actual fixed factory composition, unavailable without host permission.

    No caller path/account/UID/resource selector; no read or diagnosis at mount.
    The factory is intentionally not wired to a CLI or to the CURRENT owner.
    """
    if (not isinstance(permission_source, NativeMetadataPermissionSource)
            or type(permission_source) is NativeMetadataPermissionSource):
        raise reader.Refused('native_tool_scoped_permission_export_unavailable')
    for name in ('open_permission', 'current', 'binding'):
        method = getattr(permission_source, name)
        if (type(method) is not MethodType or method.__self__ is not permission_source
                or method.__func__ is getattr(NativeMetadataPermissionSource, name)):
            raise reader.Refused('native_tool_scoped_permission_export_unavailable')
    raw, entry = _entry()
    return _NativeMetadataOwner(permission_source, raw, entry, _sources())


class _NativeMetadataOwner(reader.OriginalDirectoryOwner):
    def __init__(self, permission, registry, entry, sources):
        self._permission = permission
        self._permission_methods = tuple(getattr(permission, name) for name in ('open_permission','current','binding'))
        self._registry = registry
        self._entry = entry
        self._sources = sources
        self._source_sha = _sha(reader.canonical(sources))
        self._entry_sha = _sha(reader.canonical(entry))
        self._context = None
        self._view = None
        self._uid = None
        self._bound = None
        self._chain = None
        self._attempted = False
        self._transporting = False
        self._used_transport = False
        self._metadata_validated = False
        self._intent = None
        self._intent_inode = None

    def _authority_current(self):
        return (self._context is not None and self._view is not None
            and os.getuid() == self._uid
            and tuple(getattr(self._permission, name) for name in ('open_permission','current','binding')) == self._permission_methods
            and self._permission.binding(self._context) == self._bound
            and self._permission.current(self._context, self._view, self._uid,
                                          self._source_sha, self._entry_sha) is True
            and os.getuid() == self._uid
            and tuple(getattr(self._permission, name) for name in ('open_permission','current','binding')) == self._permission_methods)

    def _current(self):
        raw, entry = _entry()
        if (raw != self._registry or entry != self._entry
                or _sources() != self._sources or not self._authority_current()):
            return False
        if self._metadata_validated and not all(
                _sha(delivery.local_file(path, 16384)) == expected for path, expected in METADATA):
            return False
        if self._chain is not None:
            self._chain.verify()
            if delivery.read_local_at(self._chain, 'intent.json', 8192,
                                      expected_inode=self._intent_inode) != self._intent:
                return False
        # Authority/account/current native identity must be LAST, after all
        # potentially blocking source/metadata/intent I/O. Never renew context.
        return self._authority_current()

    def admit_original_directory_metadata(self, view, invoking_uid):
        value = reader.request()
        expected = reader.MetadataActionView(reader.SCHEMA, reader.ACTION,
            reader.validate_request(value), reader.RUN, reader.ROOT, reader.ROOT,
            reader.HOST, value['directory_scope'], reader.production.directory(value['contract']))
        if (self._attempted or type(view) is not reader.MetadataActionView or view != expected
                or invoking_uid != os.getuid() or invoking_uid <= 0):
            return False
        self._attempted = True  # Never re-enter even if acquisition fails.
        self._view, self._uid = view, invoking_uid
        self._context = self._permission.open_permission(view, invoking_uid,
                                                        self._source_sha, self._entry_sha)
        if self._context is None or type(self._context) in (bool, dict, str, bytes):
            return False
        self._bound = self._permission.binding(self._context)
        if (type(self._bound) is not reader.OwnerTransportBinding
                or self._bound.host != reader.HOST
                or self._bound.ssh_alias != self._entry['ssh_alias']
                or type(self._bound.remote_uid) is not int or self._bound.remote_uid <= 0
                or type(self._bound.account_scope_sha256) is not str
                or reader.re.fullmatch('[a-f0-9]{64}', self._bound.account_scope_sha256) is None
                or not self._current()):
            return False
        # Only the two already named ORIGINAL METADATA records; never follow
        # packet/log/support/result references contained in them.
        for path, expected in METADATA:
            if not self._current():
                return False
            raw = delivery.local_file(path, 16384)
            if _sha(raw) != expected:
                return False
        self._metadata_validated = True
        if not self._current():
            return False
        # Same incumbent exclusive evidence owner, distinct diagnosis action.
        # Existing directory/intent (including interrupted) is never adopted.
        self._chain = delivery.reserve_destination(DESTINATION)
        self._chain.verify()
        self._intent = reader.canonical({
            'schema': 'mastermind.original_directory_metadata_intent.v1',
            'action': reader.ACTION, 'request_sha256': view.request_sha256,
            'source_sha256': self._source_sha, 'host_entry_sha256': self._entry_sha,
            'account_scope_sha256': self._bound.account_scope_sha256,
            'remote_uid': self._bound.remote_uid,
            'state': 'EFFECT_UNKNOWN', 'retry_authorized': False})
        self._intent_inode = delivery.write_exclusive(self._chain.fd, 'intent.json', self._intent)
        return self._current()

    def original_directory_metadata_current(self, view, invoking_uid):
        if self._chain is None or view != self._view or invoking_uid != self._uid:
            return False
        self._chain.verify()
        return self._current()

    def original_directory_transport_binding(self, view, invoking_uid):
        return self._bound if view == self._view and invoking_uid == self._uid else None

    def original_directory_metadata_transport(self, binding, value):
        if self._used_transport or binding != self._bound or not self._current():
            raise reader.Refused('original_directory_transport_not_current')
        self._used_transport = True
        self._transporting = True
        try:
            return delivery.transport(binding.ssh_alias, value, original_directory_owner=self)
        finally:
            self._transporting = False


def code_for_registered_transport(alias, value, owner):
    """Fixed carrier branch; direct request JSON/default CURRENT owner denied."""
    if (type(owner) is not _NativeMetadataOwner or not owner._transporting
            or owner._chain is None or alias != owner._bound.ssh_alias
            or not owner.original_directory_metadata_current(owner._view, owner._uid)
            or reader.validate_request(value) != owner._view.request_sha256):
        raise reader.Refused('original_directory_carrier_not_admitted')
    code = _remote_source(owner._sources)
    if not owner.original_directory_metadata_current(owner._view, owner._uid):
        raise reader.Refused('original_directory_admission_withdrawn')
    return code


def _functions(raw, names):
    tree = ast.parse(raw.decode('utf-8'))
    found = {node.name: ast.get_source_segment(raw.decode('utf-8'), node)
             for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    return '\n\n'.join(found[name] for name in names)


def _remote_source(expected_sources):
    # Exact source captured/revalidated by the owner, fixed function census.
    rr = delivery.local_file(HERE/'original_directory_custody_reader.py', 65536)
    ar = delivery.local_file(HERE/'artifact_reader.py', 65536)
    pr = delivery.local_file(HERE/'artifact_production.py', 65536)
    for name, raw in (('original_directory_custody_reader.py', rr),
                      ('artifact_reader.py', ar), ('artifact_production.py', pr)):
        if _sha(raw) != expected_sources[name]:
            raise reader.Refused('original_directory_generated_source_changed')
    imports = 'import hashlib,json,os,pwd,re,stat,sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
    strict = _functions(ar, ('strict_json',))
    production = _functions(pr, ('valid_identity', 'validate_contract'))
    # Validators execute in private namespaces to preserve their original
    # constants; the emitted engine is only the reviewed metadata functions.
    bootstrap = ("artifacts=SimpleNamespace(strict_json=strict_json)\n"
        "p={'__builtins__':__builtins__,'re':re,'reader':SimpleNamespace(MAX_FILES=8,COMPONENT=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\\Z')),"
        "'SCHEMA':'mastermind.fabric_artifact_production.v1','RESERVED_NAMES':{'request.json','receipt.json'},"
        "'IDENT':re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\\Z'),'HEX':re.compile(r'[0-9a-f]{64}\\Z')}\n"
        f"exec({production!r},p)\nproduction=SimpleNamespace(validate_contract=p['validate_contract'])\n")
    constants = {k: getattr(reader, k) for k in ('SCHEMA','ACTION','RUN','ROOT','HOST',
        'ORIGINAL_REQUEST_SHA256','ORIGINAL_BINDING_SHA256','ORIGINAL_REFUSAL_SHA256')}
    functions = _functions(rr, ('Refused','canonical','request','validate_request','_identity','_metadata'))
    main = ("try:\n raw=sys.stdin.buffer.read(16385)\n if len(raw)>16384:raise ValueError()\n"
        " value=strict_json(raw)\n result=_metadata(value)\n packet=canonical(result)\n"
        " if len(packet)>8192:raise ValueError()\n sys.stdout.buffer.write(packet)\n"
        "except (OSError,ValueError,TypeError,KeyError,RecursionError):\n sys.exit(65)\n")
    return imports+'\n'+strict+'\n'+bootstrap+'\nglobals().update('+repr(constants)+')\n'+functions+'\n'+main


def run_fixed_metadata_action(owner=None):
    """Explicit host gesture only; no auto-call, discovery, refresh or retry."""
    if type(owner) is not _NativeMetadataOwner:
        raise reader.Refused('native_tool_scoped_permission_export_unavailable')
    try:
        result = reader.inspect_metadata(reader.request(), owner=owner)
        if not owner.original_directory_metadata_current(owner._view, owner._uid):
            raise reader.Refused('original_directory_admission_withdrawn')
        # A diagnostic response is not a COMPLETE artifact/worker receipt.
        response = reader.canonical(result)
        created = delivery.write_exclusive(owner._chain.fd, 'metadata-response.json', response)
        if not owner.original_directory_metadata_current(owner._view, owner._uid):
            raise reader.Refused('original_directory_admission_withdrawn')
        if delivery.read_local_at(owner._chain, 'metadata-response.json', 8192,
                                   expected_inode=created) != response:
            raise reader.Refused('original_directory_observation_unconfirmed')
        if not owner.original_directory_metadata_current(owner._view, owner._uid):
            raise reader.Refused('original_directory_admission_withdrawn')
        delivery.write_exclusive(owner._chain.fd, 'observed.json', reader.canonical({
            'schema': 'mastermind.original_directory_metadata_observed.v1',
            'request_sha256': owner._view.request_sha256, 'response_sha256': _sha(reader.canonical(result)),
            'state': 'OBSERVED_METADATA_ONLY', 'retry_authorized': False,
            'original_outcome_accepted': False}))
        if not owner.original_directory_metadata_current(owner._view, owner._uid):
            raise reader.Refused('original_directory_admission_withdrawn')
        return result
    except reader.Refused:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise reader.Refused('original_directory_observation_unconfirmed') from None
    finally:
        if owner._chain is not None:
            owner._chain.close()
