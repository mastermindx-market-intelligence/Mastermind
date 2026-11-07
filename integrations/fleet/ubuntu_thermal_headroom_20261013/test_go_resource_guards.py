import argparse
import math
import shlex
from pathlib import Path
from types import SimpleNamespace
import pytest
import go_remote_run as g

def valid_scope():
    return dict(root="root-1", lease_id="lease-1", account="C2",
                run_id="rs_test", host="ubuntu2", model="deepseek-v4.1-flash")

def test_go_worker_receives_both_thermal_and_disk_without_shell_injection():
    spec={**valid_scope(),"remote_support":"/fixture/support","child_timeout":60}
    command=g.worker_command(spec,"/home/test","/home/test/wt","/home/test/cap",12,.25,
                             min_free_mem_gb=8,max_cpu_tctl_c=85,min_free_disk_gb=165)
    argv=shlex.split(command.split("; exec ",1)[1])
    assert "LANE_MIN_FREE_MEM_GB=8" in argv
    assert "LANE_MAX_CPU_TCTL_C=85" in argv
    assert "LANE_MIN_FREE_DISK_GB=165" in argv
    assert "LANE_MAX_LOAD_RATIO=0.25" in argv
    assert argv[-2]=="/home/test/wt"
    assert "--min-free-disk-gb" not in argv

@pytest.mark.parametrize("name,value",[
    ("min_free_disk_gb",-1),
    ("min_free_disk_gb",float("nan")),
    ("min_free_disk_gb",3000),
    ("min_free_mem_gb",-1),
    ("min_free_mem_gb",float("inf")),
    ("max_cpu_tctl_c",20),
    ("max_cpu_tctl_c",101),
    ("max_cpu_tctl_c",float("nan")),
])
def test_go_invalid_physical_limits_refused_before_any_transport(tmp_path,name,value,monkeypatch):
    # Zero proxy/ssh work may happen for these invalid bounds.
    spec=valid_scope()
    a=SimpleNamespace(**spec,ssh_alias="ubuntu2",cwd="~",child_timeout=20,
       max_active=12,load_ratio=.25,support_digest="a"*64,
       out=str(tmp_path/"out"),receipt=str(tmp_path/"receipt"),
       min_free_disk_gb=165,min_free_mem_gb=8,max_cpu_tctl_c=85)
    setattr(a,name,value)
    monkeypatch.setattr(g, "gateway_identity", lambda: (_ for _ in ()).throw(AssertionError("transport used")))
    with pytest.raises(Exception) as e:g.run(a)
    assert "transport used" not in str(e.value)
    assert not (tmp_path/"receipt").exists()

def test_go_legacy_worker_argument_signature_remains_callable():
    s={**valid_scope(),"remote_support":"/fixture/support","child_timeout":20}
    command=g.worker_command(s,"/home/test","/cwd","/cap",1,.5)
    argv=shlex.split(command.split("; exec ",1)[1])
    assert "LANE_MIN_FREE_DISK_GB=0" in argv
    assert "LANE_MAX_CPU_TCTL_C=0" in argv
    assert "LANE_MIN_FREE_MEM_GB=0" in argv

def test_remote_launcher_passes_canonical_host_registry_ceilings():
    script=(Path(g.__file__).resolve().parent/"remote_sub.sh").read_text()
    assert script.count("--min-free-mem-gb \"$MIN_FREE_MEM_GB\"") == 1
    assert script.count("--max-cpu-tctl-c \"$MAX_CPU_TCTL_C\"") == 1
    assert script.count("--min-free-disk-gb \"$MIN_FREE_DISK_GB\"") == 1
