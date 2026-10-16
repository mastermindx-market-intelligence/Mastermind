"""Local observation reader for the existing picker/broker; no transport or grant."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
MAX_BYTES = 1024 * 1024


def owned_bytes(path, *, maximum=MAX_BYTES):
    """Bounded stable file + immediate-directory custody, never authentication."""
    path = Path(path)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    dfd = os.open(path.parent, flags | os.O_DIRECTORY)
    try:
        directory = os.fstat(dfd)
        if directory.st_uid != os.geteuid() or directory.st_mode & 0o022:
            raise ValueError('observation directory custody')
        fd = os.open(path.name, flags, dir_fd=dfd)
        try:
            before = os.fstat(fd)
            def identity(st):
                return (st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_size,
                        st.st_mtime_ns, st.st_ctime_ns)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_mode & 0o022 or before.st_size > maximum):
                raise ValueError('observation file custody')
            data = bytearray()
            while len(data) <= maximum:
                chunk = os.read(fd, min(65536, maximum + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if (len(data) > maximum or identity(before) != identity(os.fstat(fd))
                    or identity(before) != identity(os.stat(path.name, dir_fd=dfd, follow_symlinks=False))):
                raise ValueError('observation file changed')
            current = os.stat(path.parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (directory.st_dev, directory.st_ino):
                raise ValueError('observation directory changed')
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def filter_observed_accounts(accounts, *, host, model, now, preferred=None,
                             hosts_path=None, state_dir=None, validator_path=None, mode="glm"):
    """Intersect existing candidates only. Failure never grants/falls back."""
    from glm_host_account_readiness import filter_glm_host_accounts, filter_bailian_host_accounts
    if mode not in ("glm", "qwen"):
        return [], "host_account_mode_invalid"
    validator_name = "glm_keys.py" if mode == "glm" else "bailian_keys.py"
    if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', host):
        return [], 'glm_host_account_source_invalid'
    try:
        registry = json.loads(owned_bytes(hosts_path or HERE/'hosts.json'))
        entry = registry[host]
        if not isinstance(entry, dict) or not isinstance(entry.get('ssh_alias'), str) or not entry.get('ssh_alias'):
            raise ValueError('host transport missing')
        # Re-check the current existing admission policy, not just a prior
        # positive observation: a new hold must take effect before a lease.
        from host_pick import MODE_TOOLS
        roles = entry.get('roles', [])
        modes = entry.get('allowed_modes')
        held = entry.get('qualification_only_modes', [])
        valid_modes = lambda xs: (isinstance(xs, list)
            and all(isinstance(x, str) and x in MODE_TOOLS for x in xs)
            and len(xs) == len(set(xs)))
        if (not isinstance(roles, list) or 'lanes' not in roles
                or not ((modes is None and mode == 'glm')
                        or valid_modes(modes) and mode in modes)
                or not valid_modes(held) or mode in held):
            return [], 'host_account_mode_not_admitted'
        document = json.loads(owned_bytes(Path(state_dir or HERE/'state/hosts')/(host+'.json')))
        digest = hashlib.sha256(owned_bytes(validator_path or HERE/validator_name)).hexdigest()
        predicate = filter_glm_host_accounts if mode == "glm" else filter_bailian_host_accounts
        return predicate(accounts, document, host=host,
            transport_alias=entry['ssh_alias'], mode=mode, model=model, candidate_model=model,
            validator_sha256=digest, now=now, preferred=preferred, source_verified=True)
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return [], 'glm_host_account_source_unavailable'
