"""Default-off installed composition; consumes explicitly provisioned host inputs.

Never creates a key, grant, directory, file, listener, vault or enrollment. Key
custody remains with the existing Executive control storage owner and installer.
"""
import os
from pathlib import Path
import re
import stat
import time

from .installed_reply_events import RuntimeReplyEventHost
from .reply_policy_selection import InstalledReplyPolicySelection
from .runtime_reply_subscriptions import ExecutiveReplyCipher
from .runtime_return import RuntimeSessionReturn
from .runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector


def validate_reply_event_host_config(value):
    if value is None: return None
    if type(value) is not dict or type(value.get("armed")) is not bool:
        raise ValueError("reply event host configuration unavailable")
    if value["armed"] is False:
        if set(value) != {"armed"}: raise ValueError("disarmed event host accepts no custody inputs")
        return None
    if set(value) != {"armed","mcp_config_path","storage_key_path","storage_key_id"}:
        raise ValueError("explicit receiver and storage custody inputs required")
    for key in ("mcp_config_path","storage_key_path"):
        if type(value[key]) is not str or not Path(value[key]).is_absolute() or os.path.normpath(value[key]) != value[key]:
            raise ValueError("explicit absolute host custody path required")
    if type(value["storage_key_id"]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}",value["storage_key_id"]) is None:
        raise ValueError("storage key identity unavailable")
    return dict(value)


def _provisioned_cipher(path, key_id, *, control_uid):
    from ops.executive_os.executive_mcp_entry import require_sealed_path
    if type(control_uid) is not int or control_uid <= 0 or os.geteuid() != control_uid:
        raise ValueError("existing Executive control identity required")
    path = Path(path)
    require_sealed_path(path.parent, directory=True)
    from control_plane.fs_security import has_macos_acl
    for parent in (path.parent,*path.parent.parents):
        if has_macos_acl(parent,expected_identity=parent.lstat()):
            raise ValueError("Executive key parent ACL custody unavailable")
    fd = os.open(path,os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (before.st_uid != control_uid or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != 32):
            raise ValueError("provisioned Executive key custody unavailable")
        if has_macos_acl(path,expected_identity=before,descriptor=fd):
            raise ValueError("Executive key ACL custody unavailable")
        key = os.read(fd,33)
        after = os.fstat(fd)
        if (len(key) != 32 or (before.st_dev,before.st_ino,before.st_uid,before.st_gid,before.st_mode,before.st_ctime_ns,before.st_mtime_ns,before.st_size) !=
                (after.st_dev,after.st_ino,after.st_uid,after.st_gid,after.st_mode,after.st_ctime_ns,after.st_mtime_ns,after.st_size)
                or has_macos_acl(path,expected_identity=after,descriptor=fd)):
            raise ValueError("provisioned Executive key changed")
        return ExecutiveReplyCipher(key_id,key)
    finally:
        os.close(fd)


def build_installed_reply_event_host(runtime, value, *, release_sha, peer_uid,
                                     dialogue_socket_path, native_owner_configured, control_uid=None, service_call=None):
    config = validate_reply_event_host_config(value)
    if config is None: return None  # No policy/key I/O on incumbent path.
    policies = InstalledReplyPolicySelection(config["mcp_config_path"],release_sha=release_sha,peer_uid=peer_uid)
    cipher = _provisioned_cipher(config["storage_key_path"],config["storage_key_id"],control_uid=control_uid)
    fabric = RuntimeFabricTargetProjector(runtime)
    codex = RuntimeCodexTargetProjector(fabric,owner_configured=native_owner_configured)
    kwargs = {} if service_call is None else {"service_call":service_call}
    returns = RuntimeSessionReturn(runtime,fabric=fabric,codex=codex,socket_path=Path(dialogue_socket_path),**kwargs)
    return RuntimeReplyEventHost(returns,cipher,policies,clock=lambda:int(time.time()),enabled=True)
