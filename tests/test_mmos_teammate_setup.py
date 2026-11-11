"""MMOS lane T2 — setup_teammate file-writing rules."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools",
                                "mmos_teammate"))
import setup_teammate as st  # noqa: E402


def make_home(tmp_path):
    home = tmp_path / "home"
    (home / "userdata").mkdir(parents=True)
    settings_path = home / "userdata" / "settings.json"
    settings_path.write_text(json.dumps({"providerInstances": {
        "capacity_fabric": {"driver": "claudeAgent",
                            "config": {"customModels": {}}}}}))
    os.chmod(settings_path, 0o644)
    charter = tmp_path / "charter.md"
    charter.write_text("# charter\n")
    spec = {"name": "Assurance",
            "t3": {"dev_home": str(home), "dev_root": str(tmp_path / "root"),
                   "t3_bin": "/x/t3", "home_path": str(tmp_path / "th"),
                   "charter_path": str(charter), "instance_id": "assurance"}}
    return spec, settings_path


def test_settings_write_is_atomic_private_and_never_partial(tmp_path,
                                                            monkeypatch):
    # R2a finding 11: the dev server watches settings.json and reloads about
    # 100ms after a change, so the write must be one rename from a staged
    # file that is 0600 from creation — never an in-place truncate. A
    # mid-write failure leaves the original bytes untouched and no staged
    # leftovers; the successful path lands valid JSON at mode 0600.
    spec, settings_path = make_home(tmp_path)
    before = settings_path.read_bytes()
    real_dump = json.dump  # captured before any patching

    def exploding_dump(obj, fh, *args, **kwargs):
        fh.write("{ partial")  # the write dies halfway
        raise RuntimeError("disk full")

    monkeypatch.setattr(st.json, "dump", exploding_dump)
    with pytest.raises(RuntimeError):
        st.ensure_t3_instance(spec)
    assert settings_path.read_bytes() == before  # untouched, not truncated
    assert not [p for p in os.listdir(settings_path.parent)
                if ".new-" in p]  # the failed staging is cleaned up

    monkeypatch.setattr(st.json, "dump", real_dump)
    st.ensure_t3_instance(spec)
    data = json.loads(settings_path.read_text())
    instance = data["providerInstances"]["assurance"]
    assert instance["config"]["homePath"] == st.expand(str(tmp_path / "th"))
    assert "--append-system-prompt-file" in instance["config"]["launchArgs"]
    assert (os.stat(settings_path).st_mode & 0o777) == 0o600
    assert not [p for p in os.listdir(settings_path.parent) if ".new-" in p]
