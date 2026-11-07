"""Read-only descriptor-relative capture for the original private relay.

The child must first qualify its held Page/Document and exact origin. This
module reads no credentials during service startup or public preparation. It
never decrypts, creates, chmods, unlocks, discovers, or logs a vault. The actual
Fernet engine runs in the same owned Node child that performs the DOM write.
"""
from __future__ import annotations

import os
import stat

from .credential_use import parse_credential_grant, CredentialUseRefused

MAX_VAULT_BYTES = 1024 * 1024


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def capture_existing_vault(grant: dict) -> dict[str, str]:
    """Return key/ciphertext ONLY to the private original child, never a tool."""
    selected = parse_credential_grant(grant)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    directory = -1
    try:
        directory = os.open(selected.vault_directory, flags | os.O_DIRECTORY)
        before = os.fstat(directory)
        if (not stat.S_ISDIR(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o700
                or before.st_uid != os.geteuid()
                or (before.st_dev, before.st_ino) != (selected.vault_device, selected.vault_inode)):
            raise CredentialUseRefused()
        captured = {}
        for name, maximum in (("vault.key", 45), ("vault.json.enc", MAX_VAULT_BYTES)):
            descriptor = os.open(name, flags, dir_fd=directory)
            try:
                opened = os.fstat(descriptor)
                if (not stat.S_ISREG(opened.st_mode) or stat.S_IMODE(opened.st_mode) != 0o600
                        or opened.st_uid != os.geteuid() or opened.st_nlink != 1
                        or not 1 <= opened.st_size <= maximum):
                    raise CredentialUseRefused()
                raw = bytearray()
                while len(raw) <= maximum:
                    part = os.read(descriptor, min(65536, maximum + 1 - len(raw)))
                    if not part:
                        break
                    raw.extend(part)
                if (len(raw) > maximum or _identity(os.fstat(descriptor)) != _identity(opened)
                        or _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(opened)):
                    raise CredentialUseRefused()
                captured[name] = bytes(raw).decode("ascii", errors="strict")
                raw[:] = b"\0" * len(raw)
            finally:
                os.close(descriptor)
        after = os.stat(selected.vault_directory, follow_symlinks=False)
        if ((after.st_dev, after.st_ino, after.st_uid, stat.S_IMODE(after.st_mode))
                != (before.st_dev, before.st_ino, before.st_uid, stat.S_IMODE(before.st_mode))):
            raise CredentialUseRefused()
        key = captured["vault.key"].removesuffix("\n")
        ciphertext = captured["vault.json.enc"]
        if len(key) != 44 or not ciphertext:
            raise CredentialUseRefused()
        return {"key": key, "ciphertext": ciphertext}
    except (OSError, UnicodeError, ValueError):
        raise CredentialUseRefused() from None
    finally:
        if directory >= 0:
            os.close(directory)
