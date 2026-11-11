"""H2 emitted quota readers through the actual sealed native entry.

Only disposable original-owner fixtures are published/selected. Inspection and
cache-only observation may not read provider credentials or contact a provider.
"""
import builtins
import importlib
from pathlib import Path
import socket
import sqlite3
import sys
from types import ModuleType
from unittest import mock

import pytest

from test_go_native_stage import published, loaded_entry
from test_quota_reset_native_stage import stages
from test_provider_application_transition import combined_builds


@pytest.fixture(scope="module", params=("application", "http", "quota_application", "quota_http"))
def native_stage(request, stages, combined_builds):
    source = combined_builds if request.param.startswith("quota_") else stages
    return getattr(source, request.param)


def test_emitted_quota_readers_keep_original_owners_and_repeatable_inspection(published, monkeypatch):
    private = published.root / "private-provider-config.json"
    private.write_text('{"api_key":"fixture-unused-secret"}')
    monkeypatch.setenv("GLM_CONFIG", str(private))
    monkeypatch.setenv("MINIMAX_CONFIG", str(private))
    original_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, Path)):
            assert Path(file) not in {private, published.profile}, "inspection read provider credential"
        return original_open(file, *args, **kwargs)

    with loaded_entry(published) as entry, \
            mock.patch.object(builtins, "open", side_effect=guarded_open), \
            mock.patch.object(sqlite3, "connect", side_effect=AssertionError("inspection opened database")), \
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("inspection contacted provider")), \
            mock.patch.object(socket.socket, "bind", side_effect=AssertionError("inspection started service")):
        startup = entry.inspect(verified_root=published.release, verified_metadata=published.meta)
        assert published.meta["files"]["ext/quota_remote.py"] == \
            "91c89d4197d791a078e804db9c591c4cddc197f1e35f54f46fba95fe7b27a9a5"
        remote = importlib.import_module("quota_remote")
        keys = importlib.import_module("glm_keys")
        assert Path(remote.__file__) == published.release / "ext/quota_remote.py"
        assert Path(keys.__file__) == published.release / "ext/glm_keys.py"
        assert Path(remote.CACHE_PATH) == published.ext / "quota_cache.json"
        # The real H2 read view sees the original empty cache as unqualified;
        # it cannot refresh, invent a grant, or create a replacement cache.
        view = remote.cached_glm_account_view("account-a", binding=None, now_ts=1800000000.0)
        assert view["quota_ready"] is False
        assert not (published.ext / "quota_cache.json").exists()
        again = entry.inspect(verified_root=published.release, verified_metadata=published.meta)
        assert again.handler is startup.handler
        assert entry._LOADED_MODULES["quota_remote"][0] is remote
        assert entry._LOADED_MODULES["glm_keys"][0] is keys


@pytest.mark.parametrize("name", ("quota_remote", "glm_keys"))
def test_foreign_quota_reader_cannot_join_the_sealed_native_namespace(published, name):
    with loaded_entry(published) as entry:
        foreign = ModuleType(name)
        foreign.__file__ = str(published.release / "ext" / (name + ".py"))
        sys.modules[name] = foreign
        with pytest.raises(ValueError, match="module conflict"):
            entry.inspect(verified_root=published.release, verified_metadata=published.meta)
