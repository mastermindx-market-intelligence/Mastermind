"""Canonical paid GLM private bridge profile: inert definition source only.

Render, verify and publish one default-disabled canonical-paid definition
through the incumbent Executive root installer lifecycle. This module starts
no listener or process, writes no credential or provider state, arms nothing,
admits no Capacity worker and touches no Runtime row, receipt or service. It
reuses the existing Capacity identity DATA shape and the original
Control publication qualification and the original root
publication IO; the finite profile, socket and admission stay untouched. An
interrupted write is EFFECT_UNKNOWN and must be reconciled, never replayed or
cleaned up.

The bridge principal is never invented and never caller-selected: the root
render resolves the actual operating-system record for the one fixed bridge
UID through the real pwd/grp owners, requires a coherent reverse username
lookup and the actual primary group, and refuses unavailable identities,
reserved Control identities and any finite ``_mastermind_*`` reuse. The same
actual qualification re-runs inside the locked re-render and the postimage
check. Candidate verification stays a pure closed-wire consistency check and
never pretends to authenticate a principal.

The disabled launchd body freezes the exact parent startup contract: the
signed Executive Python with -I -S -B, the release-qualified fixed shim
entrypoint and the fixed root config input that the parent-owned shim
constructor privately consumes together with the adopted CanonicalPaidFabric
descriptor and the real fixed controller context. No backend, descriptor or
controller context is implemented, read or started here.

The closed external source map binds the fixed release entrypoint, all three
selected-release candidate files and the closed overlay to the actual
installed release: both the original manifest document and the actual
release_manifest.verify return must carry exactly one matching regular-file
entry (path, type, size, digest, root owner, safe modes) per fixed path, and
the descriptor-read actual bytes must equal the supplied preimages. The
original raw preimages are read directly from their fixed release source/
paths and must match their immutable parent pins. Qualification runs before
any stage or publication and repeats in the locked render and postimage.
Binding source digests is not Capacity admission and not startup proof.

Publication support here covers a DISABLED definition only. No existing
authoritative producer in this source mints a paid GLM Capacity join, so a
published profile is explicitly NOT an admitted Capacity worker; the parent's
current source must later compose the real join. Nothing in these bytes
creates a grant, an admission or a runtime proof.
"""
from __future__ import annotations

from contextlib import ExitStack
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import secrets
import stat

from ops.executive_os import autonomy_control as owner
from ops.executive_os.capacity_broker_topology import (
    CONTROL_GID,
    CONTROL_UID,
    PYTHON_BINARY,
)
from control_plane.executive_capacity_join import (
    CapacityJoin,
    CapacityJoinError,
    PROVIDER_CAPACITY_SCHEMA,
)
from control_plane.executive_fabric_composition import (
    CONFIG_SCHEMA_VERSION as BINDINGS_SCHEMA_VERSION,
    _document,
)
from control_plane.executive_host_pressure import HOST_REF_RE

CONFIG_SCHEMA = 'mastermind.executive_paid_fabric_bridge_config/v1'
OVERLAY_SCHEMA = 'mastermind.executive_paid_fabric_overlay/v1'
PROFILE_SCHEMA = 'mastermind.executive_paid_fabric_profile/v1'
ADAPTER_ID = 'canonical-paid-fabric'
PROFILE_ID = ADAPTER_ID
WORKER_ID = 'glm-paid-01'
PAID_LABEL = 'com.mastermind.executive.fabric.' + WORKER_ID
PAID_DEFINITION_DIRNAME = 'fabric-' + WORKER_ID
PAID_SOCKET_PATH = '/var/run/mastermind-executive/fabric-' + WORKER_ID + '.sock'
PAID_LAUNCHD_SOCKET_NAME = 'CanonicalPaidFabric'
# The one fixed actual bridge UID. No GID, group name or username is invented
# here: every other principal fact is derived from the actual UID record at
# render time, so there is deliberately no synthetic bridge GID constant.
PAID_BRIDGE_UID = 501
PAID_PROVIDER = 'glm'
PAID_MODELS = frozenset({'glm-5.3', 'glm-5.3-flash'})
# The existing controller endpoint the same shim process already owns; the
# adopted launchd FD is private and is never a second public endpoint.
PAID_HTTP_ENDPOINT = 'http://127.0.0.1:4141'
EXECUTABLE_PYTHON = str(PYTHON_BINARY)
SHIM_MODULE = 'scripts/executive_paid_fabric_shim.py'
PAID_CONFIG_ARGUMENT = '--config'
# Frozen root config input for the parent-owned shim constructor. The shim
# privately consumes this config together with the actual CanonicalPaidFabric
# AF_UNIX descriptor and the real fixed controller context; none of those are
# implemented, read or started here.
PAID_BRIDGE_CONFIG_PATH = str(Path(owner.CONFIG_ROOT) / PAID_DEFINITION_DIRNAME
                              / 'bridge.json')
PAID_RUNTIME_ROOT = '/private/var/db/mastermind-executive'
PAID_WORKSPACE_ROOT = PAID_RUNTIME_ROOT + '/workers/' + WORKER_ID + '/jobs/workspaces'
PAID_RUN_ROOT = PAID_RUNTIME_ROOT + '/workers/' + WORKER_ID + '/jobs/runs'
DESTINATION = Path(owner.CONFIG_ROOT) / PAID_DEFINITION_DIRNAME
FILES = frozenset({'profile.json', 'bridge.json', 'bindings.json', PAID_LABEL + '.plist'})
# Closed external source map: the fixed release entrypoint, all three
# selected-release candidate files and the closed overlay. The relative
# release paths below are owner constants; a caller can never select a path,
# module or executable.
EXTERNAL_SOURCES = frozenset({'shim', 'overlay', 'candidate_glm_shim',
                              'candidate_glm_lease_gateway',
                              'candidate_glm_lease_capability'})
PAID_CANONICAL_GLM_PREFIX = 'ops/native_fabric/paid_canonical_glm'
CANDIDATE_GLM_SHIM = PAID_CANONICAL_GLM_PREFIX + '/candidate/glm_shim.py'
CANDIDATE_GLM_LEASE_GATEWAY = PAID_CANONICAL_GLM_PREFIX + '/candidate/glm_lease_gateway.py'
CANDIDATE_GLM_LEASE_CAPABILITY = (
    PAID_CANONICAL_GLM_PREFIX + '/candidate/glm_lease_capability.py')
BOUND_SOURCE_PATHS = {
    'shim': SHIM_MODULE,
    'candidate_glm_shim': CANDIDATE_GLM_SHIM,
    'candidate_glm_lease_gateway': CANDIDATE_GLM_LEASE_GATEWAY,
    'candidate_glm_lease_capability': CANDIDATE_GLM_LEASE_CAPABILITY,
}
# Original raw preimages are read directly from their fixed release source/
# paths and must match these immutable parent-owned pins exactly. They are
# never caller input and are never re-frozen from an older worker hash; the
# candidate digests above stay parent-owned and move with the selected
# release. A future producer fails closed until a genuinely installed release
# agrees with these pins.
RAW_GLM_SHIM = PAID_CANONICAL_GLM_PREFIX + '/source/glm_shim.py'
RAW_GLM_LEASE_GATEWAY = PAID_CANONICAL_GLM_PREFIX + '/source/glm_lease_gateway.py'
RAW_GLM_LEASE_CAPABILITY = PAID_CANONICAL_GLM_PREFIX + '/source/glm_lease_capability.py'
RAW_SOURCE_PINS = {
    RAW_GLM_SHIM: ('020b9ef9c59260d07980a23f2ac277d4e4d7350ff81e010d071fd733cc05b1fc',
                   65508),
    RAW_GLM_LEASE_GATEWAY: (
        '7fd2b64925cb7d7ea83dd37e3802ddab9d004e775bb4ed04e5da04a51dc5ed00', 5843),
    RAW_GLM_LEASE_CAPABILITY: (
        'e80070971fdce507c5314e05b5be67abd0f9cd4603ae6a6b1072e666f3e0a5b7', 9781),
}
RELEASE_SOURCE_PATHS = frozenset(BOUND_SOURCE_PATHS.values()) | frozenset(RAW_SOURCE_PINS)
MAX_FILE_BYTES = 32_768
# Source preimages are bounded far above the artifact/document bound because
# the original shim and candidate sources exceed it; nothing is truncated.
MAX_SOURCE_FILE_BYTES = 131_072
MAX_SOURCE_TOTAL_BYTES = 1_048_576
# Root-selected installed inputs only; never an arbitrary caller path.
_RELEASES_ROOT = Path(owner.SYSTEM_ROOT) / 'releases'
_MANIFEST_NAME = '.executive-release-manifest.json'
# Installed release source files are root:wheel and never group/other
# writable; the incumbent installer only clears the group/other write bits on
# the staged tree, so the read-only file modes it actually produces are safe.
_RELEASE_SOURCE_MODES = frozenset({0o444, 0o644, 0o755})
_COMMIT_RE = re.compile(r'[0-9a-f]{40}')
_DIGEST_RE = re.compile(r'[0-9a-f]{64}')
_TOKEN_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
_PRINCIPAL_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9._-]{0,63}')
_RESERVED_PRINCIPALS = frozenset({
    '_mastermind_worker', '_mastermind_minimax', owner.CONTROL_USER,
})
_RESERVED_PRINCIPAL_PREFIXES = ('_mastermind_',)
_DISARMED_CONTROL_KEYS = (
    'ceo_submit_armed', 'coo_autonomy_armed', 'coo_operator_harness_armed',
    'fabric_bridge_armed', 'coo_foreground_only',
)
_PAID_CONFIG_FIELDS = frozenset({
    'schema_version', 'adapter_id', 'bridge_uid', 'control_uid',
    'launchd_socket_name', 'socket_path', 'workspace_root', 'run_root',
    'max_request_bytes', 'max_response_bytes', 'request_timeout_seconds',
    'validation_commands',
})
# The parent overlay omits principal claims entirely: bridge user, group and
# GID are derived from the actual UID record by the root renderer and only
# then sealed into the profile.
_PAID_OVERLAY_FIELDS = frozenset({
    'schema_version', 'adapter_id', 'provider', 'model', 'http_endpoint',
    'execution_profile_sha256', 'permission_profile_sha256',
})
_PAID_PROFILE_FIELDS = frozenset({
    'schema_version', 'profile_id', 'label', 'worker_id', 'bridge_uid',
    'bridge_gid', 'bridge_group', 'bridge_user', 'control_uid', 'control_gid',
    'launchd_socket_name', 'socket_path', 'provider', 'model', 'http_endpoint',
    'host_ref', 'release_commit', 'release_tree', 'release_manifest_sha256',
    'entrypoint', 'source_digests', 'execution_profile_sha256',
    'permission_profile_sha256', 'workspace_root', 'run_root', 'bridge_home',
    'expected_remote_binary', 'remote_worker_identity',
    'capacity_capability_id', 'bridge_armed', 'capacity_admitted',
})


class CanonicalPaidPublicationRefused(ValueError):
    """Closed, secret-free refusal before any canonical effect."""


class CanonicalPaidPublicationEffectUnknown(RuntimeError):
    """A write interval ended uncertainly; reconcile, never replay."""


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _commit(value) -> str:
    if type(value) is not str or _COMMIT_RE.fullmatch(value) is None:
        raise CanonicalPaidPublicationRefused('exact protected release identity required')
    return value


def _digest(value) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise CanonicalPaidPublicationRefused('exact source digest required')
    return value


def _require_ordinary_principal_name(value, kind: str) -> str:
    """One bounded, non-reserved, non-finite principal/group name."""
    if type(value) is not str or _PRINCIPAL_NAME_RE.fullmatch(value) is None:
        raise CanonicalPaidPublicationRefused(
            'canonical-paid ' + kind + ' is not a bounded principal name')
    if value in _RESERVED_PRINCIPALS or value.startswith(_RESERVED_PRINCIPAL_PREFIXES):
        raise CanonicalPaidPublicationRefused(
            'canonical-paid ' + kind + ' reuses a reserved or finite identity')
    return value


def _require_bridge_home(value) -> str:
    # Non-secret pwd metadata only; never read or create a credential/home path.
    if (type(value) is not str or not value or len(value) > 4096
            or not Path(value).is_absolute() or '..' in Path(value).parts
            or any(ord(char) < 32 for char in value)):
        raise CanonicalPaidPublicationRefused('actual bridge home is invalid')
    return value


def _qualify_bridge_principal() -> dict[str, object]:
    """Resolve the actual non-secret principal behind the fixed bridge UID.

    The root render consults the real pwd/grp owners only; no caller supplies
    or overrides a username, group or GID. Availability, fixed-UID agreement
    and two-way username coherence, the actual primary group and two-way
    group coherence are all required. Reserved Control identities and any
    finite ``_mastermind_*`` reuse are refused. The returned facts are
    ordinary authenticated NSS metadata, not a credential and never an
    admission; the pure candidate verifier never re-runs this lookup.
    """
    try:
        record = pwd.getpwuid(PAID_BRIDGE_UID)
    except (KeyError, OSError) as exc:
        raise CanonicalPaidPublicationRefused(
            'actual bridge principal for the fixed UID is unavailable') from exc
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('bridge principal lookup failed') from exc
    user = record.pw_name
    primary_gid = record.pw_gid
    if (type(user) is not str or type(primary_gid) is not int
            or record.pw_uid != PAID_BRIDGE_UID):
        raise CanonicalPaidPublicationRefused(
            'actual bridge principal record differs from the fixed UID')
    _require_ordinary_principal_name(user, 'bridge user')
    try:
        reverse = pwd.getpwnam(user)
    except (KeyError, OSError) as exc:
        raise CanonicalPaidPublicationRefused(
            'bridge username does not resolve to an actual record') from exc
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('bridge principal lookup failed') from exc
    if (type(reverse.pw_name) is not str or reverse.pw_name != user
            or type(reverse.pw_uid) is not int or reverse.pw_uid != PAID_BRIDGE_UID
            or type(reverse.pw_gid) is not int or reverse.pw_gid != primary_gid):
        raise CanonicalPaidPublicationRefused(
            'bridge username is not coherent with the fixed UID')
    home = _require_bridge_home(getattr(record, 'pw_dir', None))
    if getattr(reverse, 'pw_dir', None) != home:
        raise CanonicalPaidPublicationRefused('bridge home lookup is incoherent')
    if primary_gid == CONTROL_GID or primary_gid == 0:
        raise CanonicalPaidPublicationRefused(
            'bridge primary group must not reuse Control or root')
    try:
        group_record = grp.getgrgid(primary_gid)
    except (KeyError, OSError) as exc:
        raise CanonicalPaidPublicationRefused(
            'actual bridge primary group is unavailable') from exc
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('bridge principal lookup failed') from exc
    group = group_record.gr_name
    if (type(group) is not str or type(group_record.gr_gid) is not int
            or group_record.gr_gid != primary_gid):
        raise CanonicalPaidPublicationRefused(
            'actual bridge primary group record differs from its GID')
    _require_ordinary_principal_name(group, 'bridge group')
    try:
        reverse_group = grp.getgrnam(group)
    except (KeyError, OSError) as exc:
        raise CanonicalPaidPublicationRefused(
            'bridge group name does not resolve to an actual record') from exc
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('bridge principal lookup failed') from exc
    if (type(reverse_group.gr_name) is not str or reverse_group.gr_name != group
            or type(reverse_group.gr_gid) is not int
            or reverse_group.gr_gid != primary_gid):
        raise CanonicalPaidPublicationRefused(
            'bridge group is not coherent with the primary GID')
    return {'bridge_uid': PAID_BRIDGE_UID, 'bridge_gid': primary_gid,
            'bridge_user': user, 'bridge_group': group, 'bridge_home': home}


def _expected_plist(profile: dict) -> dict:
    """The one launchd body its sealed profile may bind; Disabled, never RunAtLoad."""
    release = str(_RELEASES_ROOT / profile['release_commit'])
    return {
        'Label': PAID_LABEL,
        'ProgramArguments': [EXECUTABLE_PYTHON, '-I', '-S', '-B',
                             str(Path(release) / SHIM_MODULE),
                             PAID_CONFIG_ARGUMENT, PAID_BRIDGE_CONFIG_PATH],
        'WorkingDirectory': release,
        'UserName': profile['bridge_user'],
        'GroupName': profile['bridge_group'],
        'InitGroups': False,
        'EnvironmentVariables': {'HOME': profile['bridge_home'],
                                 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                                 'LANG': 'C', 'LC_ALL': 'C'},
        'Sockets': {PAID_LAUNCHD_SOCKET_NAME: {
            'SockFamily': 'Unix', 'SockType': 'stream', 'SockPassive': True,
            'SockPathName': PAID_SOCKET_PATH, 'SockPathOwner': 0,
            'SockPathGroup': CONTROL_GID, 'SockPathMode': 0o660}},
        'RunAtLoad': False, 'KeepAlive': False, 'Disabled': True, 'Umask': 0o077,
    }


def _validate_paid_bridge_document(value) -> None:
    """Private strict paid structure; the parent broker later extends support."""
    if type(value) is not dict or set(value) != _PAID_CONFIG_FIELDS:
        raise CanonicalPaidPublicationRefused('paid bridge config differs from its closed schema')
    if value['schema_version'] != CONFIG_SCHEMA or value['adapter_id'] != ADAPTER_ID:
        raise CanonicalPaidPublicationRefused('paid bridge config schema/adapter is fixed')
    if (type(value['bridge_uid']) is not int or value['bridge_uid'] != PAID_BRIDGE_UID
            or value['bridge_uid'] == CONTROL_UID
            or type(value['control_uid']) is not int or value['control_uid'] != CONTROL_UID):
        raise CanonicalPaidPublicationRefused('paid bridge/control principal is fixed')
    if (value['launchd_socket_name'] != PAID_LAUNCHD_SOCKET_NAME
            or value['socket_path'] != PAID_SOCKET_PATH):
        raise CanonicalPaidPublicationRefused('paid bridge route is fixed')
    if value['workspace_root'] != PAID_WORKSPACE_ROOT or value['run_root'] != PAID_RUN_ROOT:
        raise CanonicalPaidPublicationRefused('paid bridge roots are fixed')
    for key, expected in (('max_request_bytes', 1048576), ('max_response_bytes', 4194304)):
        if type(value[key]) is not int or value[key] != expected:
            raise CanonicalPaidPublicationRefused('paid bridge frame ceiling is fixed')
    if type(value['request_timeout_seconds']) not in (int, float) or value['request_timeout_seconds'] != 3600:
        raise CanonicalPaidPublicationRefused('paid bridge timeout is fixed')
    if value['validation_commands'] != []:
        raise CanonicalPaidPublicationRefused('paid bridge ships without a validation allowlist')


def _validated_overlay(value) -> dict:
    if type(value) is not dict or set(value) != _PAID_OVERLAY_FIELDS:
        raise CanonicalPaidPublicationRefused('paid overlay differs from its closed schema')
    if value['schema_version'] != OVERLAY_SCHEMA or value['adapter_id'] != ADAPTER_ID:
        raise CanonicalPaidPublicationRefused('paid overlay identity differs')
    if value['provider'] != PAID_PROVIDER or value['model'] not in PAID_MODELS:
        raise CanonicalPaidPublicationRefused('unsupported paid provider or model')
    if value['http_endpoint'] != PAID_HTTP_ENDPOINT:
        raise CanonicalPaidPublicationRefused('paid overlay endpoint is the existing controller only')
    for key in ('execution_profile_sha256', 'permission_profile_sha256'):
        _digest(value[key])
    return value


def _validate_paid_profile_document(value) -> None:
    if type(value) is not dict or set(value) != _PAID_PROFILE_FIELDS:
        raise CanonicalPaidPublicationRefused('canonical-paid profile differs from its closed schema')
    pins = {
        'schema_version': PROFILE_SCHEMA, 'profile_id': PROFILE_ID, 'label': PAID_LABEL,
        'worker_id': WORKER_ID, 'bridge_uid': PAID_BRIDGE_UID,
        'control_uid': CONTROL_UID, 'control_gid': CONTROL_GID,
        'launchd_socket_name': PAID_LAUNCHD_SOCKET_NAME, 'socket_path': PAID_SOCKET_PATH,
        'provider': PAID_PROVIDER, 'http_endpoint': PAID_HTTP_ENDPOINT,
        'workspace_root': PAID_WORKSPACE_ROOT, 'run_root': PAID_RUN_ROOT,
    }
    if any(value.get(key) != expected for key, expected in pins.items()):
        raise CanonicalPaidPublicationRefused('canonical-paid profile pin differs')
    for key in ('bridge_uid', 'bridge_gid', 'control_uid', 'control_gid'):
        if type(value[key]) is not int:
            raise CanonicalPaidPublicationRefused('canonical-paid principal is not an exact integer')
    # Only the UID is fixed. The GID and both names are the derived actual
    # principal facts sealed at render; the wire check bounds them and refuses
    # reserved or finite reuse without pretending to re-authenticate anyone.
    if value['bridge_gid'] <= 0 or value['bridge_gid'] == CONTROL_GID:
        raise CanonicalPaidPublicationRefused(
            'canonical-paid primary group is not an ordinary derived GID')
    if value['bridge_armed'] is not False or value['capacity_admitted'] is not False:
        raise CanonicalPaidPublicationRefused('canonical-paid definition must stay disarmed and unadmitted')
    if (type(value['model']) is not str or value['model'] not in PAID_MODELS):
        raise CanonicalPaidPublicationRefused('canonical-paid profile identity is unsupported')
    _require_ordinary_principal_name(value['bridge_user'], 'bridge user')
    _require_ordinary_principal_name(value['bridge_group'], 'bridge group')
    _require_bridge_home(value['bridge_home'])
    if value['expected_remote_binary'] is not None or value['remote_worker_identity'] is not None:
        raise CanonicalPaidPublicationRefused('remote execution identity is unavailable; definition stays unselected')
    if type(value['host_ref']) is not str or HOST_REF_RE.fullmatch(value['host_ref']) is None:
        raise CanonicalPaidPublicationRefused('canonical-paid profile host differs from its owner')
    _commit(value['release_commit'])
    _commit(value['release_tree'])
    _digest(value['release_manifest_sha256'])
    for key in ('execution_profile_sha256', 'permission_profile_sha256'):
        _digest(value[key])
    entrypoint = value['entrypoint']
    if (type(entrypoint) is not dict or set(entrypoint) != {'python', 'shim_module'}
            or entrypoint['python'] != EXECUTABLE_PYTHON
            or entrypoint['shim_module'] != SHIM_MODULE):
        raise CanonicalPaidPublicationRefused('canonical-paid entrypoint is fixed and non-dynamic')
    digests = value['source_digests']
    if (type(digests) is not dict or set(digests) != set(EXTERNAL_SOURCES)
            or any(type(item) is not str or _DIGEST_RE.fullmatch(item) is None
                   for item in digests.values())):
        raise CanonicalPaidPublicationRefused('canonical-paid external source digests are incomplete')
    if type(value['capacity_capability_id']) is not str or _TOKEN_RE.fullmatch(value['capacity_capability_id']) is None:
        raise CanonicalPaidPublicationRefused('exact Capacity identity required')


def _require_qualified_prior(prior, expected_release_sha: str) -> None:
    """The installed disarmed prior binds this exact release; no caller state."""
    control = getattr(prior, 'control', None)
    worker = getattr(prior, 'worker', None)
    if type(control) is not dict or type(worker) is not dict:
        raise CanonicalPaidPublicationRefused('qualified installed prior required')
    if (control.get('proof_base_sha') != expected_release_sha
            or any(control.get(key, False) is not False for key in _DISARMED_CONTROL_KEYS)
            or worker.get('operator_harness_armed') is not False):
        raise CanonicalPaidPublicationRefused('Control and primary Worker must remain disarmed')
    runtime_root = control.get('runtime_root')
    if type(runtime_root) is not str or not runtime_root or not Path(runtime_root).is_absolute():
        raise CanonicalPaidPublicationRefused('installed runtime root is required')
    if (type(worker.get('control_uid')) is not int or worker['control_uid'] != CONTROL_UID
            or type(worker.get('worker_uid')) is not int or worker['worker_uid'] == PAID_BRIDGE_UID
            or type(worker.get('worker_id')) is not str or worker['worker_id'] == WORKER_ID
            or type(worker.get('worker_user')) is not str):
        raise CanonicalPaidPublicationRefused('canonical-paid cannot reuse an installed principal')


def _require_external_sources(external_sources) -> dict:
    if (type(external_sources) is not dict or set(external_sources) != set(EXTERNAL_SOURCES)
            or any(type(value) is not bytes
                   or not 1 <= len(value) <= MAX_SOURCE_FILE_BYTES
                   for value in external_sources.values())):
        raise CanonicalPaidPublicationRefused('complete exact nonsecret external source preimages required')
    sources = dict(external_sources)
    if sum(len(value) for value in sources.values()) > MAX_SOURCE_TOTAL_BYTES:
        raise CanonicalPaidPublicationRefused('bounded external source package exceeded')
    for name in sorted(BOUND_SOURCE_PATHS):
        try:
            compile(sources[name].decode('utf-8', errors='strict'),
                    BOUND_SOURCE_PATHS[name], 'exec')
        except (UnicodeError, ValueError, SyntaxError, RecursionError):
            raise CanonicalPaidPublicationRefused(
                'root-selected release source is incomplete: ' + name) from None
    try:
        _validated_overlay(_document(sources['overlay']))
    except CanonicalPaidPublicationRefused:
        raise
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('paid overlay preimage is not bounded strict JSON') from exc
    return sources


def _manifest_entry(entries, relative_path: str) -> dict:
    """The one exact unique regular-file entry for a fixed release path."""
    if type(entries) is not list:
        raise CanonicalPaidPublicationRefused('installed release manifest entries differ')
    matches = [value for value in entries
               if type(value) is dict and value.get('path') == relative_path]
    if len(matches) != 1:
        raise CanonicalPaidPublicationRefused(
            'installed release manifest lacks one exact entry for ' + relative_path)
    entry = matches[0]
    if (entry.get('type') != 'file'
            or type(entry.get('size')) is not int
            or not 1 <= entry['size'] <= MAX_SOURCE_FILE_BYTES
            or type(entry.get('sha256')) is not str
            or _DIGEST_RE.fullmatch(entry['sha256']) is None
            or type(entry.get('uid')) is not int or entry['uid'] != 0
            or type(entry.get('gid')) is not int or entry['gid'] != 0
            or type(entry.get('mode')) is not int
            or entry['mode'] not in _RELEASE_SOURCE_MODES):
        raise CanonicalPaidPublicationRefused(
            'installed release source entry is not a bounded root-owned regular file: '
            + relative_path)
    return entry


def _require_installed_release_sources(expected_release_sha: str, manifest: dict,
                                       sources: dict) -> None:
    """Prove the fixed source map against the actual installed release.

    The original manifest document and the actual release_manifest.verify
    return must both carry exactly one matching regular-file entry (path,
    type, size, digest, root owner, safe modes) for every fixed path; the two
    entries must agree; and the descriptor-read actual bytes must equal the
    supplied preimages exactly. The original raw preimages are validated
    directly from their fixed release source/ paths against their immutable
    parent pins. Any absent, duplicate, different, symlinked, mutable or
    foreign entry, or an incomplete map, refuses before any stage or
    publication; the locked re-render and the postimage check repeat all of
    it. Source digests bind bytes only; this is not Capacity admission.
    """
    from ops.executive_os.release_manifest import verify
    release_root = _RELEASES_ROOT / expected_release_sha
    try:
        verified = verify(release_root, expected_release_sha, manifest['tree_sha'])
        if type(verified) is not dict:
            raise CanonicalPaidPublicationRefused('installed release verification is unavailable')
        verified_entries = verified.get('entries')
        original_entries = manifest.get('entries')
        for name, relative_path in sorted(BOUND_SOURCE_PATHS.items()):
            original = _manifest_entry(original_entries, relative_path)
            observed = _manifest_entry(verified_entries, relative_path)
            if original != observed:
                raise CanonicalPaidPublicationRefused(
                    'installed release source entry differs from its original manifest: '
                    + relative_path)
            raw, _info = owner._read_root_file(release_root / relative_path,
                                               modes=_RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
            if (len(raw) != observed['size'] or sha256(raw) != observed['sha256']
                    or raw != sources[name]):
                raise CanonicalPaidPublicationRefused(
                    'installed release source bytes differ from the exact supplied '
                    'preimage: ' + relative_path)
        for relative_path, (digest, size) in sorted(RAW_SOURCE_PINS.items()):
            original = _manifest_entry(original_entries, relative_path)
            observed = _manifest_entry(verified_entries, relative_path)
            if original != observed:
                raise CanonicalPaidPublicationRefused(
                    'original paid source entry differs from its original manifest: '
                    + relative_path)
            raw, _info = owner._read_root_file(release_root / relative_path,
                                               modes=_RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
            if (len(raw) != size or sha256(raw) != digest
                    or len(raw) != observed['size'] or sha256(raw) != observed['sha256']):
                raise CanonicalPaidPublicationRefused(
                    'original paid source preimage differs from its immutable parent '
                    'pin: ' + relative_path)
        total = sum(len(value) for value in sources.values())
        total += sum(size for _digest, size in RAW_SOURCE_PINS.values())
        if total > MAX_SOURCE_TOTAL_BYTES:
            raise CanonicalPaidPublicationRefused('bounded paid source package exceeded')
    except CanonicalPaidPublicationRefused:
        raise
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('installed release source is unavailable') from exc


def verify_candidate(artifacts: dict) -> dict[str, str]:
    """Verify inert identities before any exclusive filesystem publication.

    This is a pure closed-wire check: it validates the four sealed artifacts,
    the empty unselected binding document and the existing Capacity identity
    data shape and the exact disabled launchd body, including the sealed
    derived principal fields as data. It performs no pwd/grp lookup and never
    authenticates a principal, grants source acceptance, admission or
    enrollment.
    """
    if (type(artifacts) is not dict or set(artifacts) != FILES
            or any(type(value) is not bytes or not 1 <= len(value) <= MAX_FILE_BYTES
                   for value in artifacts.values())):
        raise CanonicalPaidPublicationRefused('four bounded exact source artifacts required')
    try:
        profile_bytes = artifacts['profile.json']
        profile = _document(profile_bytes)
        _validate_paid_profile_document(profile)
        bridge_document = _document(artifacts['bridge.json'])
        _validate_paid_bridge_document(bridge_document)
        # The legacy closed broker schema must keep refusing the paid document.
        from control_plane.executive_fabric_bridge_broker import BridgeConfig, BridgeProtocolError
        try:
            BridgeConfig.from_document(bridge_document)
        except BridgeProtocolError:
            pass
        else:
            raise CanonicalPaidPublicationRefused('legacy bridge schema accepted the paid document')
        # An inert definition is not a physical route. Legacy _bindings must
        # keep refusing this empty document; the paid runtime owner separately
        # qualifies actual remote executable/principal proof before selection.
        bindings = _document(artifacts['bindings.json'])
        if bindings != {'schema_version': BINDINGS_SCHEMA_VERSION, 'bindings': []}:
            raise CanonicalPaidPublicationRefused('remote binding is unavailable; definition must remain empty and unselected')
        CapacityJoin(profile['host_ref'], profile['capacity_capability_id'],
                     PROVIDER_CAPACITY_SCHEMA, sha256(profile_bytes))
        plist = plistlib.loads(artifacts[PAID_LABEL + '.plist'])
        if plist != _expected_plist(profile):
            raise CanonicalPaidPublicationRefused('launchd body differs from its sealed profile')
        if (plist.get('Label') != PAID_LABEL or plist.get('Disabled') is not True
                or plist.get('RunAtLoad') is not False):
            raise CanonicalPaidPublicationRefused('canonical-paid definition must ship disabled')
    except CanonicalPaidPublicationRefused:
        raise
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('canonical-paid definition validation refused') from exc
    return {name: sha256(artifacts[name]) for name in sorted(FILES)}


def render_definition(prior, expected_release_sha: str, *, host_ref: str,
                      capacity_capability_id: str, external_sources: dict) -> dict[str, bytes]:
    """Render the exact inert four-artifact paid definition; nothing is written.

    The caller supplies the qualified installed prior, the exact protected
    release identity, the complete nonsecret external source preimages and
    the pinned Capacity identity. The actual bridge principal is resolved
    from the real pwd/grp records for the one fixed UID, and the closed
    source map is proven against the actual installed release manifest,
    release verification and descriptor reads. Installed release bytes are
    read through the original root file owner only; the sealed profile binds
    their digests and never copies or edits the installed shim.
    """
    _commit(expected_release_sha)
    if os.geteuid() != 0:
        raise CanonicalPaidPublicationRefused('sealed root source identity required')
    if type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None:
        raise CanonicalPaidPublicationRefused('pinned physical host identity required')
    if (type(capacity_capability_id) is not str
            or _TOKEN_RE.fullmatch(capacity_capability_id) is None):
        raise CanonicalPaidPublicationRefused('pinned Capacity identity required')
    _require_qualified_prior(prior, expected_release_sha)
    sources = _require_external_sources(external_sources)
    try:
        manifest_bytes, _info = owner._read_root_file(
            _RELEASES_ROOT / expected_release_sha / _MANIFEST_NAME,
            modes=frozenset({0o444}), uid=0, gid=0)
        manifest = _document(manifest_bytes)
    except CanonicalPaidPublicationRefused:
        raise
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('installed release manifest is unavailable') from exc
    tree = manifest.get('tree_sha') if type(manifest) is dict else None
    if manifest.get('commit_sha') != expected_release_sha:
        raise CanonicalPaidPublicationRefused('installed release manifest differs')
    _commit(tree)
    from ops.executive_os.release_manifest import verify
    try:
        verify(_RELEASES_ROOT / expected_release_sha, expected_release_sha, tree)
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('installed release tree differs') from exc
    _require_installed_release_sources(expected_release_sha, manifest, sources)
    principal = _qualify_bridge_principal()
    overlay = _validated_overlay(_document(sources['overlay']))
    profile = {
        'schema_version': PROFILE_SCHEMA,
        'profile_id': PROFILE_ID,
        'label': PAID_LABEL,
        'worker_id': WORKER_ID,
        'bridge_uid': PAID_BRIDGE_UID,
        'bridge_gid': principal['bridge_gid'],
        'bridge_group': principal['bridge_group'],
        'bridge_user': principal['bridge_user'],
        'bridge_home': principal['bridge_home'],
        'expected_remote_binary': None,
        'remote_worker_identity': None,
        'control_uid': CONTROL_UID,
        'control_gid': CONTROL_GID,
        'launchd_socket_name': PAID_LAUNCHD_SOCKET_NAME,
        'socket_path': PAID_SOCKET_PATH,
        'provider': PAID_PROVIDER,
        'model': overlay['model'],
        'http_endpoint': PAID_HTTP_ENDPOINT,
        'host_ref': host_ref,
        'release_commit': expected_release_sha,
        'release_tree': tree,
        'release_manifest_sha256': sha256(manifest_bytes),
        'entrypoint': {'python': EXECUTABLE_PYTHON, 'shim_module': SHIM_MODULE},
        'source_digests': {name: sha256(sources[name]) for name in sorted(EXTERNAL_SOURCES)},
        'execution_profile_sha256': overlay['execution_profile_sha256'],
        'permission_profile_sha256': overlay['permission_profile_sha256'],
        'workspace_root': PAID_WORKSPACE_ROOT,
        'run_root': PAID_RUN_ROOT,
        'capacity_capability_id': capacity_capability_id,
        'bridge_armed': False,
        'capacity_admitted': False,
    }
    profile_bytes = _json(profile)
    bindings_bytes = _json({'schema_version': BINDINGS_SCHEMA_VERSION, 'bindings': []})
    # Existing Capacity owner validates the complete join/source digest wire.
    try:
        CapacityJoin(host_ref, capacity_capability_id, PROVIDER_CAPACITY_SCHEMA,
                     sha256(profile_bytes))
    except CapacityJoinError as exc:
        raise CanonicalPaidPublicationRefused('Capacity identity is not admissible evidence') from exc
    bridge_document = {
        'schema_version': CONFIG_SCHEMA,
        'adapter_id': ADAPTER_ID,
        'bridge_uid': PAID_BRIDGE_UID,
        'control_uid': CONTROL_UID,
        'launchd_socket_name': PAID_LAUNCHD_SOCKET_NAME,
        'socket_path': PAID_SOCKET_PATH,
        'workspace_root': PAID_WORKSPACE_ROOT,
        'run_root': PAID_RUN_ROOT,
        'max_request_bytes': 1048576,
        'max_response_bytes': 4194304,
        'request_timeout_seconds': 3600,
        'validation_commands': [],
    }
    artifacts = {'profile.json': profile_bytes,
                 'bridge.json': _json(bridge_document),
                 'bindings.json': bindings_bytes,
                 PAID_LABEL + '.plist': plistlib.dumps(
                     _expected_plist(profile), fmt=plistlib.FMT_XML, sort_keys=True)}
    verify_candidate(artifacts)
    return artifacts


def _object_at(parent_fd: int, name: str):
    """Observe one name without following symlinks, including proved absence."""
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _same_inode(info, held) -> bool:
    return (info is not None and stat.S_ISDIR(info.st_mode)
            and (info.st_dev, info.st_ino) == (held.st_dev, held.st_ino))


def _discard_definitely_private(parent_fd: int, stage_fd: int, stage_name: str,
                                canonical_name: str, uid: int, gid: int) -> bool:
    """Remove only this caller's provably unpublished staging inode.

    The incumbent config-directory lock remains held by our caller. Never
    touch the canonical target or unfamiliar content; a failed cleanup leaves
    the original uncertain stage for inspection.
    """
    try:
        held = os.fstat(stage_fd)
        staged = _object_at(parent_fd, stage_name)
        canonical = _object_at(parent_fd, canonical_name)
        if (not _same_inode(staged, held) or _same_inode(canonical, held)
                or held.st_uid != uid or held.st_gid != gid
                or stat.S_IMODE(held.st_mode) not in {0o700, 0o755}):
            return False
        names = os.listdir(stage_fd)
        if set(names) - FILES:
            return False
        for name in names:
            file_info = _object_at(stage_fd, name)
            if (file_info is None or not stat.S_ISREG(file_info.st_mode)
                    or file_info.st_uid != uid or file_info.st_gid != gid
                    or file_info.st_nlink != 1):
                return False
        for name in sorted(names):
            os.unlink(name, dir_fd=stage_fd)
        os.rmdir(stage_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except OSError:
        return False


def _trusted_control_root(lock_fd: int) -> os.stat_result:
    """Reprove trust on the original CONFIG_ROOT lock descriptor itself."""
    from control_plane.fs_security import has_macos_acl

    held, visible = os.fstat(lock_fd), Path(owner.CONFIG_ROOT).lstat()
    if (not stat.S_ISDIR(held.st_mode)
            or held.st_uid != 0 or held.st_gid != 0
            or stat.S_IMODE(held.st_mode) != 0o755
            or (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)
            or has_macos_acl(Path(owner.CONFIG_ROOT), expected_identity=visible,
                             descriptor=lock_fd)):
        raise CanonicalPaidPublicationRefused('incumbent Control config root is untrusted')
    return held


def _require_definition_absent(parent_fd: int, name: str) -> None:
    if _object_at(parent_fd, name) is not None:
        raise CanonicalPaidPublicationRefused('canonical-paid definition already exists, inspect original')
    prefix = '.' + name + '.'
    if any(value.startswith(prefix) and value.endswith('.stage')
           for value in os.listdir(parent_fd)):
        raise CanonicalPaidPublicationRefused('prior canonical-paid private stage requires reconciliation')


def _write_exclusive(directory: Path, artifacts: dict[str, bytes], *,
                     uid: int, gid: int, mode: int = 0o444,
                     parent_fd: int | None = None) -> dict[str, str]:
    """Build privately, then publish one verified directory atomically.

    Called only after the original Control config directory mutex has been
    acquired by the root owner. It never replaces an existing name, emulates
    exclusive rename, or repairs an uncertain canonical write.
    """
    if type(artifacts) is not dict:
        raise CanonicalPaidPublicationRefused('exact immutable source bundle required')
    sealed = dict(artifacts)  # private snapshot; member bytes are immutable
    expected = verify_candidate(sealed)
    from control_plane.fs_security import has_macos_acl
    from ops.executive_os.capacity_host_artifacts import _rename_exclusive
    owns_parent_fd = parent_fd is None
    if owns_parent_fd:
        parent_fd = os.open(directory.parent,
                            os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0))
    if not isinstance(parent_fd, int):
        raise CanonicalPaidPublicationRefused('original locked parent is unavailable')
    stage_fd = -1
    stage_name = ('.' + directory.name + '.' + str(os.getpid()) + '.'
                  + secrets.token_hex(8) + '.stage')
    stage_created = False
    try:
        # In production, parent_fd IS the trusted CONFIG_ROOT lock FD. Never
        # open a second path after the owner has already qualified it.
        held_parent, visible_parent = os.fstat(parent_fd), directory.parent.lstat()
        if (not _same_inode(visible_parent, held_parent)
                or (held_parent.st_uid, held_parent.st_gid,
                    stat.S_IMODE(held_parent.st_mode))
                != (visible_parent.st_uid, visible_parent.st_gid,
                    stat.S_IMODE(visible_parent.st_mode))):
            raise CanonicalPaidPublicationRefused('original locked parent directory moved')
        _require_definition_absent(parent_fd, directory.name)
        os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        stage_created = True
        stage_fd = os.open(stage_name,
                           os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0),
                           dir_fd=parent_fd)
        os.fchown(stage_fd, uid, gid)
        os.fchmod(stage_fd, 0o700)
        held = os.fstat(stage_fd)
        if (not _same_inode(_object_at(parent_fd, stage_name), held)
                or (held.st_uid, held.st_gid, stat.S_IMODE(held.st_mode)) != (uid, gid, 0o700)):
            raise CanonicalPaidPublicationEffectUnknown('private definition inode changed')
        for name in sorted(FILES):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, 'O_NOFOLLOW', 0), mode, dir_fd=stage_fd)
            try:
                pending = memoryview(sealed[name])
                while pending:
                    count = os.write(descriptor, pending)
                    if count <= 0:
                        raise OSError('short artifact write')
                    pending = pending[count:]
                os.fchown(descriptor, uid, gid)
                os.fchmod(descriptor, mode)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        # Observe every file's bytes and ACL on the same open descriptor; the
        # canonical name remains absent until after this succeeds.
        hashes = {}
        for name in sorted(FILES):
            name_path = directory.parent / stage_name / name
            descriptor = os.open(name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
                                 dir_fd=stage_fd)
            try:
                info, listed = os.fstat(descriptor), _object_at(stage_fd, name)
                if (listed is None or not stat.S_ISREG(info.st_mode)
                        or (info.st_dev, info.st_ino) != (listed.st_dev, listed.st_ino)
                        or info.st_uid != uid or info.st_gid != gid or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != mode
                        or has_macos_acl(name_path, expected_identity=listed,
                                         descriptor=descriptor)):
                    raise CanonicalPaidPublicationEffectUnknown('private artifact identity or ACL differs')
                chunks, count = [], 0
                while True:
                    part = os.read(descriptor, min(8192, MAX_FILE_BYTES + 1 - count))
                    if not part:
                        break
                    count += len(part)
                    if count > MAX_FILE_BYTES:
                        raise CanonicalPaidPublicationEffectUnknown('private artifact exceeds bound')
                    chunks.append(part)
                observed = b''.join(chunks)
                if observed != sealed[name]:
                    raise CanonicalPaidPublicationEffectUnknown('private artifact bytes differ')
                hashes[name] = sha256(observed)
            finally:
                os.close(descriptor)
        if hashes != expected or set(os.listdir(stage_fd)) != FILES:
            raise CanonicalPaidPublicationEffectUnknown('private bundle postimage differs')
        staged = _object_at(parent_fd, stage_name)
        held = os.fstat(stage_fd)
        if (not _same_inode(staged, held) or held.st_uid != uid
                or held.st_gid != gid or stat.S_IMODE(held.st_mode) != 0o700
                or has_macos_acl(directory.parent / stage_name, expected_identity=staged,
                                 descriptor=stage_fd)):
            raise CanonicalPaidPublicationEffectUnknown('private directory identity or ACL differs')
        os.fsync(stage_fd)
        # The paid bridge's non-root principal must be able to traverse the
        # directory and read the root-owned 0444 definitions at startup. Those
        # nonsecret modes are required by its exact installed reader and the
        # separately reviewed root-owned lifecycle source.
        os.fchmod(stage_fd, 0o755)
        os.fsync(stage_fd)
        if _object_at(parent_fd, directory.name) is not None:
            raise CanonicalPaidPublicationRefused('canonical-paid definition appeared')
        _rename_exclusive(parent_fd, stage_name, parent_fd, directory.name)
        os.fsync(parent_fd)
        actual = _object_at(parent_fd, directory.name)
        if (not _same_inode(actual, held) or actual.st_uid != uid
                or actual.st_gid != gid or stat.S_IMODE(actual.st_mode) != 0o755
                or _object_at(parent_fd, stage_name) is not None):
            raise CanonicalPaidPublicationEffectUnknown('published exact inode unconfirmed')
        return hashes
    except Exception as exc:
        # An FD-limit failure after mkdir but before opening the private stage
        # cannot have issued the canonical rename. Prove the target absent,
        # then remove only this exact still-empty stage.
        if stage_created and stage_fd < 0:
            try:
                staged = _object_at(parent_fd, stage_name)
                if (staged is not None and stat.S_ISDIR(staged.st_mode)
                        and stat.S_IMODE(staged.st_mode) == 0o700
                        and _object_at(parent_fd, directory.name) is None):
                    os.rmdir(stage_name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                    raise CanonicalPaidPublicationRefused(
                        'original empty private stage removed before publication') from exc
            except OSError:
                pass
        if stage_created and stage_fd >= 0 and _discard_definitely_private(
                parent_fd, stage_fd, stage_name, directory.name, uid, gid):
            raise CanonicalPaidPublicationRefused(
                'canonical-paid private stage refused without canonical publication') from exc
        if not stage_created:
            if isinstance(exc, CanonicalPaidPublicationRefused):
                raise
            raise CanonicalPaidPublicationRefused(
                'canonical-paid prepublication qualification refused') from exc
        raise CanonicalPaidPublicationEffectUnknown(
            'original canonical-paid directory publication effect unconfirmed') from exc
    finally:
        # Final close errors must not mask APPLIED or EFFECT_UNKNOWN.
        if stage_fd >= 0:
            try:
                os.close(stage_fd)
            except OSError:
                pass
        if owns_parent_fd:
            try:
                os.close(parent_fd)
            except OSError:
                pass


def _require_publication_inputs(expected_release_sha, expected_control_sha256) -> None:
    if (os.geteuid() != 0
            or type(expected_release_sha) is not str
            or _COMMIT_RE.fullmatch(expected_release_sha) is None
            or type(expected_control_sha256) is not str
            or _DIGEST_RE.fullmatch(expected_control_sha256) is None):
        raise CanonicalPaidPublicationRefused('exact root release and Control preimage required')


def _require_join_matches_sealed(artifacts: dict, capacity_join: CapacityJoin) -> None:
    """Revalidate one supplied join through the existing owner, identity only."""
    if type(capacity_join) is not CapacityJoin:
        raise CanonicalPaidPublicationRefused(
            'existing Capacity identity join is required; no caller boolean is permission')
    try:
        revalidated = CapacityJoin(capacity_join.host_ref, capacity_join.capacity_capability_id,
                                   PROVIDER_CAPACITY_SCHEMA, capacity_join.worker_source_config_digest)
    except CapacityJoinError as exc:
        raise CanonicalPaidPublicationRefused('Capacity identity is not admissible evidence') from exc
    if revalidated != capacity_join:
        raise CanonicalPaidPublicationRefused('Capacity identity join differs from its owner')
    profile = _document(artifacts['profile.json'])
    if (capacity_join.host_ref != profile['host_ref']
            or capacity_join.capacity_capability_id != profile['capacity_capability_id']
            or capacity_join.worker_source_config_digest != sha256(artifacts['profile.json'])):
        raise CanonicalPaidPublicationRefused('Capacity join differs from the sealed paid profile')


def _publish_selected_definition(expected_release_sha, expected_control_sha256,
                                 prepare_locked) -> dict[str, object]:
    """The original locked publication interval under one held CONFIG_ROOT FD."""
    _require_publication_inputs(expected_release_sha, expected_control_sha256)
    host = owner.ProductionCeoSubmitHost()
    lock_fd = -1
    effect_possible = False
    try:
        with ExitStack() as custody:
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host._config_root_safe()
            lock_fd = os.open(owner.CONFIG_ROOT,
                              os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0))
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CanonicalPaidPublicationRefused(
                    'incumbent Control publication mutex occupied') from exc
            _trusted_control_root(lock_fd)
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host.require_services_already_stopped()
            host.require_service_uids_quiescent()
            prior = host.load_unarmed_configs(expected_release_sha)
            host.require_runtime_quiescent(prior)
            if (prior.control_sha256 != expected_control_sha256
                    or any(prior.control.get(key, False) is not False
                           for key in _DISARMED_CONTROL_KEYS)
                    or prior.worker.get('operator_harness_armed') is not False):
                raise CanonicalPaidPublicationRefused('Control and primary Worker must remain disarmed')
            if Path(DESTINATION).parent != Path(owner.CONFIG_ROOT):
                raise CanonicalPaidPublicationRefused('incumbent Capacity/config binding differs')
            sealed, recheck = prepare_locked(prior, lock_fd, custody)
            hashes = verify_candidate(sealed)
            _trusted_control_root(lock_fd)
            effect_possible = True
            try:
                hashes_published = _write_exclusive(DESTINATION, sealed, uid=0, gid=0,
                                                    parent_fd=lock_fd)
            except CanonicalPaidPublicationRefused:
                # Only this incumbent writer can prove its stage never became
                # canonical and that its own private cleanup completed.
                effect_possible = False
                raise
            if hashes_published != hashes:
                raise CanonicalPaidPublicationEffectUnknown('published disk digest differs')
            host.require_exact_install(expected_release_sha)
            host.require_transaction_absent()
            host.require_services_already_stopped()
            host.require_service_uids_quiescent()
            current = host.load_unarmed_configs(expected_release_sha)
            host.require_runtime_quiescent(current)
            host._config_root_safe()
            _trusted_control_root(lock_fd)
            if (current.control_sha256 != prior.control_sha256
                    or current.worker_sha256 != prior.worker_sha256):
                raise CanonicalPaidPublicationEffectUnknown('original config/Capacity postimage changed')
            recheck(current)
            return {'state': 'STAGED_DISARMED_DEFINITION', 'release': expected_release_sha,
                    'control_preimage_sha256': expected_control_sha256,
                    'artifacts': hashes_published, 'effect': 'APPLIED',
                    'admitted_worker': False, 'capacity_admitted': False,
                    'service_started': False}
    except CanonicalPaidPublicationRefused as exc:
        if effect_possible:
            raise CanonicalPaidPublicationEffectUnknown(
                'original canonical-paid publication effect unconfirmed') from exc
        raise
    except CanonicalPaidPublicationEffectUnknown:
        raise
    except Exception as exc:
        if effect_possible:
            raise CanonicalPaidPublicationEffectUnknown(
                'original canonical-paid publication effect unconfirmed') from exc
        raise CanonicalPaidPublicationRefused('original Control/Capacity qualification refused') from exc
    finally:
        if lock_fd >= 0:
            try:
                os.close(lock_fd)
            except OSError:
                pass


def publish_definition(expected_release_sha: str, expected_control_sha256: str,
                       artifacts: dict[str, bytes], *, capacity_join: CapacityJoin,
                       external_sources: dict) -> dict[str, object]:
    """Single root-owner entry for source-derived, *disabled* publication.

    The prior-owner checks are intentionally repeated under the CONFIG_ROOT
    lock. The supplied Capacity join is an existing-owner identity value that
    is revalidated inside the locked interval; no boolean, seal or metadata
    here issues admission. The actual principal and the whole fixed source
    map are re-qualified in the preflight render, the locked re-render and
    the postimage check against the real pwd/grp owners and the real
    installed release. An interrupted interval is EFFECT_UNKNOWN and is never
    republished; residue of an uncertain attempt is left for inspection.
    """
    _require_publication_inputs(expected_release_sha, expected_control_sha256)
    if type(artifacts) is not dict:
        raise CanonicalPaidPublicationRefused('exact source bundle required')
    sealed = dict(artifacts)
    verify_candidate(sealed)
    sources = _require_external_sources(external_sources)
    _require_join_matches_sealed(sealed, capacity_join)
    try:
        host = owner.ProductionCeoSubmitHost()
        host.require_exact_install(expected_release_sha)
        host.require_transaction_absent()
        host.require_services_already_stopped()
        host.require_service_uids_quiescent()
        prior = host.load_unarmed_configs(expected_release_sha)
        host.require_runtime_quiescent(prior)
        if prior.control_sha256 != expected_control_sha256:
            raise CanonicalPaidPublicationRefused('Control source preimage changed')
        rendered = render_definition(prior, expected_release_sha,
                                     host_ref=capacity_join.host_ref,
                                     capacity_capability_id=capacity_join.capacity_capability_id,
                                     external_sources=sources)
        if rendered != sealed:
            raise CanonicalPaidPublicationRefused('source-rendered canonical-paid definition differs')
    except CanonicalPaidPublicationRefused:
        raise
    except Exception as exc:
        raise CanonicalPaidPublicationRefused('original root/Capacity source preflight refused') from exc

    def prepare_locked(prior, lock_fd, custody):
        _require_definition_absent(lock_fd, Path(DESTINATION).name)
        _require_join_matches_sealed(sealed, capacity_join)

        def reproduce(current):
            return render_definition(current, expected_release_sha,
                                     host_ref=capacity_join.host_ref,
                                     capacity_capability_id=capacity_join.capacity_capability_id,
                                     external_sources=sources)

        if reproduce(prior) != sealed:
            raise CanonicalPaidPublicationRefused('source-rendered canonical-paid definition differs')

        def recheck(current):
            _require_join_matches_sealed(sealed, capacity_join)
            if reproduce(current) != sealed:
                raise CanonicalPaidPublicationRefused('source-rendered canonical-paid definition differs')

        return sealed, recheck

    return _publish_selected_definition(expected_release_sha, expected_control_sha256,
                                        prepare_locked)
