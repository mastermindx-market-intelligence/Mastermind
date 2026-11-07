"""Exact remote helper closures, historical aliases and paid-entry separation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

from test_current_selection_reader import ROOT, S, load

M = load("h6_remote_owner_mapper", ROOT / "ext/paid_model_owner.py")
P = load("h6_remote_paid_entry", ROOT / "ext/paid_provider_entry.py")
OLD = load("h6_remote_old_support", ROOT.parent / "pre-fence/ext/support_bundle.py")
# Publication uses this existing policy owner, with its actual parser and lock.
load("fabric_policy_snapshot", ROOT / "ext/fabric_policy_snapshot.py")

FAMILIES = {
    "plain": S.COMMON_SOURCE_FILES,
    "plain-physical": S.COMMON_PHYSICAL_ROOT_SOURCE_FILES,
    "paid": S.COMMON_PAID_SOURCE_FILES,
    "paid-physical": S.COMMON_PAID_PHYSICAL_ROOT_SOURCE_FILES,
}

def build_release(tmp_path, family, *, historical=False):
    base = Path(tempfile.mkdtemp(prefix="remote-source-", dir=tmp_path)).resolve()
    stable = base / "lanes/ext"
    for name in ("active", "lanes", "broker", "slots", "state"):
        (stable / name).mkdir(parents=True, mode=0o700)
    (stable.parent / "orch/fabric").mkdir(parents=True, mode=0o700)
    (stable.parent / "support-releases").mkdir(mode=0o700)
    source = base / "source"
    source.mkdir(mode=0o700)
    policy = json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}}).encode()
    (source / "pools.yaml").write_bytes(policy)
    S.ensure_policy(source / "pools.yaml", stable, hashlib.sha256(policy).hexdigest())
    (stable / "quota_cache.json").write_text("{}\n")
    names = OLD.PAID_INITIALIZED_SOURCE_FILES if historical else FAMILIES[family]
    source_root = ROOT.parent / "pre-fence/ext" if historical else ROOT / "ext"
    for name in names:
        if name != "pools.yaml":
            shutil.copyfile(source_root / name, source / name)
    manifest = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}
    here = S.publish(source, stable, manifest)
    environment = {"REMOTE_SUB_LANES": str(stable.parent), "SUPPORT_DIGEST": here.parent.name}
    return dict(base=base, stable=stable, source=source, manifest=manifest,
                here=here, environment=environment)

@pytest.mark.parametrize("family", FAMILIES)
def test_each_available_successor_maps_exact_physical_owner(tmp_path, family):
    f = build_release(tmp_path, family)
    assert M.canonical_state_ext(f["here"], f["environment"]) == f["stable"]
    expected = S._release_metadata(f["manifest"], f["here"].parent.name, f["stable"])
    S._verify_release(f["here"].parent, expected)
    assert set(expected["links"]) == ({"ext/" + name for name in S._EXT_SYMLINKS | {"quota_cache.json"}}
                                      | set(S._ROOT_SYMLINKS))
    assert (f["here"] / "quota_cache.json").is_symlink()
    assert os.readlink(f["here"] / "quota_cache.json") == str(f["stable"] / "quota_cache.json")
    assert json.loads((f["stable"] / "quota_cache.json").read_text()) == {}

def test_historical_paid_bytes_and_aliases_still_verify(tmp_path):
    f = build_release(tmp_path, "paid", historical=True)
    assert M.canonical_state_ext(f["here"], f["environment"]) == f["stable"]
    assert not os.path.lexists(f["here"] / "quota_cache.json")
    expected_old = OLD._release_metadata(f["manifest"], f["here"].parent.name, f["stable"])
    assert S._release_metadata(f["manifest"], f["here"].parent.name, f["stable"]) == expected_old
    S._verify_release(f["here"].parent, expected_old)
    OLD._verify_release(f["here"].parent, expected_old)
    assert S._EXT_SYMLINKS == OLD._EXT_SYMLINKS
    assert S.SOURCE_GENERATIONS[6:] == OLD.SOURCE_GENERATIONS

@pytest.mark.parametrize("family", ["plain", "plain-physical"])
def test_valid_plain_custody_does_not_pass_paid_source_gate(tmp_path, family):
    f = build_release(tmp_path, family)
    assert M.canonical_state_ext(f["here"], f["environment"]) == f["stable"]
    with pytest.raises(P.ProviderEntryRefused):
        with P._SupportSources(f["here"], f["manifest"]):
            pytest.fail("plain custody became a paid entry")

@pytest.mark.parametrize("family", ["paid", "paid-physical"])
def test_paid_held_byte_loader_delivers_helper_mapper_and_quota_owner(tmp_path, family):
    f = build_release(tmp_path, family)
    # A cold finite process keeps the actual held-source namespace guard active.
    code = r'''
import importlib.util,json,os,sys
from pathlib import Path
here=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("h6_paid_entry",here/"paid_provider_entry.py")
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
meta=json.loads((here.parent/"RELEASE.json").read_text())
os.environ["REMOTE_SUB_LANES"]=str(here.parent.parent.parent)
os.environ["SUPPORT_DIGEST"]=here.parent.name
with entry._SupportSources(here,meta["files"]) as owner:
    with entry._support_imports(owner):
        import support_bundle,quota_remote
        from paid_model_owner import canonical_state_ext
        import yaml
        stable=canonical_state_ext(here,os.environ)
        with support_bundle.source_admission_scope(here) as (physical,held):
            assert physical==stable
            held()
        assert quota_remote.CACHE_PATH==str(stable/"quota_cache.json")
        def update(cache):
            cache["fixture_remote_publications"]=cache.get("fixture_remote_publications",0)+1
            return True,cache["fixture_remote_publications"]
        result=quota_remote._update_cache(str(stable/"quota_cache.json"),update)
        print(json.dumps({"publications":result,"yaml":yaml.__version__,"owner":str(stable)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(f["here"])],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"publications": 1, "yaml": "6.0.3",
                                       "owner": str(f["stable"])}
    assert json.loads((f["stable"] / "quota_cache.json").read_text())["fixture_remote_publications"] == 1

@pytest.mark.parametrize("change", ["quota-alias", "file-hash", "extra-file", "missing-member"])
def test_successor_custody_refuses_alias_or_membership_drift(tmp_path, change):
    f = build_release(tmp_path, "plain")
    here = f["here"]
    here.chmod(0o755)
    if change == "quota-alias":
        (here / "quota_cache.json").unlink()
        (here / "quota_cache.json").symlink_to(f["base"] / "foreign-cache.json")
    elif change == "file-hash":
        path = here / "support_bundle.py"
        path.chmod(0o755)
        with path.open("ab") as handle:
            handle.write(b"\n# changed helper\n")
        path.chmod(0o555)
    elif change == "extra-file":
        (here / "extra.py").write_text("pass\n")
        (here / "extra.py").chmod(0o555)
    else:
        (here / "go_lease_capability.py").unlink()
    here.chmod(0o555)
    with pytest.raises(ValueError, match="paid_support_owner_refused"):
        M.canonical_state_ext(here, f["environment"])

def test_real_shell_producer_equals_each_named_current_closure():
    shell = (ROOT / "ext/remote_sub.sh").read_text()
    base = re.search(r"^SUPPORT_FILES=\((.*?)\n\)", shell, re.M | re.S)
    assert base is not None
    base_names = base.group(1).split()
    assert len(base_names) == len(set(base_names))
    assert frozenset(base_names) == S.COMMON_SOURCE_FILES
    paid = re.search(r'CANONICAL_PAID_ACTIVE" -eq 0 \] \|\| SUPPORT_FILES\+=\(([^\n]*)\)', shell)
    assert paid is not None
    paid_names = base_names + paid.group(1).split()
    assert len(paid_names) == len(set(paid_names))
    assert frozenset(paid_names) == S.COMMON_PAID_SOURCE_FILES == P.SUPPORT_FILES
    assert S.COMMON_PHYSICAL_ROOT_SOURCE_FILES == S.COMMON_SOURCE_FILES | {"artifact_delivery.py"}
    assert S.COMMON_PAID_PHYSICAL_ROOT_SOURCE_FILES == P.SUPPORT_FILES | {"artifact_delivery.py"}
    upload = next(line for line in shell.splitlines() if "commission_run support-upload" in line)
    assert '"$HERE/support_bundle.py"' not in upload
    assert subprocess.run(["/bin/bash", "-n", str(ROOT / "ext/remote_sub.sh")],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0

def test_application_successor_stays_closed_without_completed_owner(tmp_path):
    assert S.COMMON_APPLICATION_SOURCE_FILES == S.COMMON_SOURCE_FILES | {"application_native_owner.py"}
    assert S.COMMON_APPLICATION_PHYSICAL_ROOT_SOURCE_FILES == (
        S.COMMON_APPLICATION_SOURCE_FILES | {"artifact_delivery.py"})
    assert not (ROOT / "ext/application_native_owner.py").exists()
    f = build_release(tmp_path, "plain")
    proposed = dict(f["manifest"], **{"application_native_owner.py": "0" * 64})
    with pytest.raises(FileNotFoundError):
        S.publish(f["source"], f["stable"], proposed)
    assert not (f["here"] / "application_native_owner.py").exists()
    # Source membership is not a paid grant, even for a hypothetical complete
    # APPLICATION member set; no placeholder owner file is constructed.
    with pytest.raises(P.ProviderEntryRefused):
        with P._SupportSources(f["here"], proposed):
            pytest.fail("APPLICATION membership became a paid grant")
