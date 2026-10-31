"""Explicit exact-source-bound private-DATA initialization inputs, not execution.

No initializer/helper is run here. The existing owner must qualify approval,
namespace, platform, actual image and execution authority. Peer imports require
an exact qualified private package at the remote bootstrap, never mutable path
search. Old contracts are intentionally unsupported by this new component.
"""
from __future__ import annotations
from collections.abc import Mapping
from contextlib import contextmanager
import hashlib
import os

from .paid_initializer import sealed_snapshot, path as _path
from .paid_initializer_token_data import FrozenHelper, TokenDataRefused, _check_snapshot, _identity

CONTRACT = "paid-host-env-held-fd-token-data.v1"
INPUTS_SCHEMA = "mastermind.paid_nested_data_inputs/v1"
CONTEXT_SCHEMA = "mastermind.paid_effective_context/v1"
LEGACY_SHA256 = "c7fc8be292b3f231317c3cc9e5b64c990a34a495cf0fa095048a37df0379b2f6"
_ORIGINAL = b'export PATH=$HOME/.npm-global/bin:$HOME/.local/bin:/opt/homebrew/bin:$HOME/lanes/venv/bin:$PATH\nexport GLM_SHIM_URL=http://127.0.0.1:4141\n# Bind MiniMax admission to the *real* immutable source commit on Ubuntu.\n# An absent checkout leaves the source gate closed; no fallback or bypass.\n[ -d "$HOME/lanes/authority/mastermind-minimax-4d1f45bf600afc2d264a74852c69887084aa52ff/.git" ] && export MINIMAX_GIT_OBJECT_ROOT="$HOME/lanes/authority/mastermind-minimax-4d1f45bf600afc2d264a74852c69887084aa52ff"\n[ -f "$HOME/lanes/ext/.host_glm_token.sh" ] && . "$HOME/lanes/ext/.host_glm_token.sh"\n'
_LAST = b'[ -f "$HOME/lanes/ext/.host_glm_token.sh" ] && . "$HOME/lanes/ext/.host_glm_token.sh"\n'
_REPLACEMENT = b': # credential helper consumed as private DATA before this new variant\n'
_TRANSFORMED = _ORIGINAL[:-len(_LAST)] + _REPLACEMENT
TRANSFORMED_SHA256 = hashlib.sha256(_TRANSFORMED).hexdigest()


class NestedDataRefused(ValueError):
    def __init__(self):
        super().__init__("paid_nested_data_refused")


def _refuse():
    raise NestedDataRefused() from None


def transform_outer(raw, *, contract):
    """Public source DATA only, never an approval or permission to execute."""
    if (type(contract) is not str or contract != CONTRACT or type(raw) is not bytes
            or raw != _ORIGINAL or hashlib.sha256(raw).hexdigest() != LEGACY_SHA256
            or not raw.endswith(_LAST) or raw.count(_LAST) != 1):
        _refuse()
    return _TRANSFORMED


def bind_effective_context(environment, *, expected_home, expected_glm_config,
                           expected_python, lane_root, contract):
    """Resolve actual selector DATA; retain the incumbent owner image guards.

    No credentials/config contents or ambient os.environ are read. This does
    not prove the selected image's custody, startup or grant: the existing owner
    must still recheck those at its actual execution boundary.
    """
    try:
        if (type(contract) is not str or contract != CONTRACT
                or not isinstance(environment, Mapping)):
            _refuse()
        home = _path(expected_home)
        config = _path(expected_glm_config)
        python = _path(expected_python)
        lane = _path(lane_root)
        if lane != home + "/lanes" or environment.get("HOME") != home:
            _refuse()
        selector = environment.get("GLM_CONFIG")
        if selector is not None and type(selector) is not str:
            _refuse()
        # Exact existing glm_keys._config_path meaning, without a new export.
        actual_config = _path(selector or home + "/.glm/config.json")
        if actual_config != config:
            _refuse()
        inherited = environment.get("PATH", "")
        if type(inherited) is not str or "\0" in inherited:
            _refuse()
        selected = None
        for directory in (lane + "/venv/bin:" + inherited).split(":"):
            candidate = os.path.join(directory, "python3")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                selected = candidate
                break
        # Compare logical selection, never replace it with an expected/real ELF.
        if selected != python:
            _refuse()
        return {"schema_version": CONTEXT_SCHEMA, "home": home,
                "glm_config": actual_config, "python_path": selected}
    except Exception:
        _refuse()


class PreparedNestedInputs:
    __slots__ = ("_helper", "_fd", "_identity", "_closed")

    def __init__(self, helper, fd, *, _seal=None):
        if _seal is not _SEAL:
            _refuse()
        self._helper, self._fd, self._closed = helper, fd, False
        self._identity = _identity(os.fstat(fd))

    def __repr__(self):
        return "<PreparedNestedDataInputs>"

    def __reduce_ex__(self, protocol):
        raise TypeError("private inputs are not serializable") from None

    def check(self):
        try:
            if self._closed:
                _refuse()
            self._helper.check()
            _check_snapshot(self._fd, TRANSFORMED_SHA256, len(_TRANSFORMED), self._identity)
        except (OSError, ValueError, TypeError, AttributeError):
            _refuse()

    @property
    def outer_fd(self):
        self.check()
        return self._fd

    @property
    def witness(self):
        self.check()
        return {"schema_version": INPUTS_SCHEMA, "initialization_contract": CONTRACT,
                "legacy_outer_sha256": LEGACY_SHA256,
                "transformed_outer_sha256": TRANSFORMED_SHA256,
                "helper": self._helper.fingerprint}

    def private_environment(self, base):
        """Initial injection only; use check_environment for later survival."""
        self.check()
        try:
            result = self._helper.private_data.child_environment(base)
        except TokenDataRefused:
            _refuse()
        self.check()
        return result

    def check_environment(self, environment):
        self.check()
        try:
            self._helper.private_data.verify_environment(environment)
        except TokenDataRefused:
            _refuse()
        self.check()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            current = os.fstat(self._fd)
            if (current.st_dev, current.st_ino) != self._identity[:2]:
                _refuse()
            os.close(self._fd)
        except OSError:
            _refuse()
        finally:
            self._fd = -1


_SEAL = object()


@contextmanager
def prepare_nested_inputs(outer, helper, *, contract):
    # Exact typed DATA object, never a callback or caller-asserted approval.
    if type(helper) is not FrozenHelper:
        _refuse()
    transformed = transform_outer(outer, contract=contract)
    fd = None
    try:
        helper.check()
        fd = sealed_snapshot(transformed)
        prepared = PreparedNestedInputs(helper, fd, _seal=_SEAL)
        prepared.check()
    except (OSError, ValueError, TypeError, AttributeError):
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _refuse()
    try:
        yield prepared
    except BaseException:
        try:
            prepared.close()
        except NestedDataRefused:
            pass
        raise
    else:
        try:
            prepared.check()
        finally:
            prepared.close()
