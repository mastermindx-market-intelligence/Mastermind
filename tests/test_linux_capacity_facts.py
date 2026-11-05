"""Offline fixtures only: no host inspection, stress, reservation or service work."""
from dataclasses import replace
import ast
from pathlib import Path
import pytest
from ops.executive_os import linux_capacity_facts as f

G = 1 << 30
BOOT = '11111111-2222-3333-4444-555555555555'

def read(text):
    return f.Read(text.encode('ascii'))

def stat(counters, count=24):
    row = ' '.join(map(str, counters))
    return read('cpu '+row+'\n'+''.join(f'cpu{i} '+row+'\n' for i in range(count)))

def inputs():
    return {
      'meminfo': read(f'MemTotal: {64*G//1024} kB\nMemAvailable: {32*G//1024} kB\nSwapTotal: {8*G//1024} kB\nSwapFree: {6*G//1024} kB\n'),
      'stat_before': stat([100, 20, 50, 800, 10, 5, 5, 10, 10, 2]),
      'stat_after': stat([140, 20, 70, 830, 15, 5, 5, 15, 20, 2]),
      'vmstat_before': read('pswpin 100\npswpout 200\n'),
      'vmstat_after': read('pswpin 110\npswpout 220\n'),
      'pressure_cpu': read('some avg10=12.34 avg60=5.00 avg300=1.00 total=123450\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n'),
      'pressure_memory': read('some avg10=2.00 avg60=1.00 avg300=0.50 total=10000\nfull avg10=1.00 avg60=0.50 avg300=0.25 total=5000\n'),
      'pressure_io': read('some avg10=4.00 avg60=2.00 avg300=1.00 total=20000\nfull avg10=2.00 avg60=1.00 avg300=0.50 total=10000\n'),
    }

def scope():
    # The parent includes sibling CI/inference use, not just this leaf's use.
    parent = f.CgroupLevel(1, read('150000 100000\n'), read(str(8*G)+'\n'), read(str(7*G)+'\n'))
    leaf = f.CgroupLevel(2, read('200000 100000\n'), read(str(4*G)+'\n'), read(str(2*G)+'\n'))
    return f.CgroupScope((parent, leaf), read('0-23\n'), read('0-23\n'), True)

def window():
    return f.Window(BOOT, BOOT, 1000, 2000, 100000, 100100, 5000)

def disk():
    return f.Disk((8, 1, 50), (8, 1, 50), (8, 1, 50), 10000, 5000, 4096, True)

def observe(**kw):
    args = dict(scope=scope(), window=window(), disk=disk())
    reads = kw.pop('reads', inputs())
    args.update(kw)
    return f.observe(reads, **args)

def null(metric, reason):
    assert metric.value is None
    assert metric.null_reason is reason

def error(fn, reason):
    with pytest.raises(f.ObservationError) as exc:
        fn()
    assert exc.value.reason is reason

def test_first_gap_parent_pressure_not_host_or_leaf_capacity():
    facts = observe()
    assert facts['host_usable_memory_bytes'].value == 64*G
    assert facts['host_available_memory_estimate_bytes'].value == 32*G
    assert facts['host_logical_cpu_count'].value == 24
    assert facts['effective_cpu_capacity_millicores'].value == 1500
    assert facts['effective_memory_headroom_estimate_bytes'].value == G
    # A port that uses the host's 32GiB or subtracts leaf use from the parent
    # limit would report 32GiB or 6GiB, instead of the actual 1GiB estimate.
    assert facts['effective_memory_headroom_estimate_bytes'].value not in (32*G, 6*G)

def test_cpu_busy_excludes_idle_iowait_and_does_not_double_count_guest():
    assert observe()['host_cpu_busy_milli_pct'].value == 65000

def test_native_psi_windows_and_swap_page_units_remain_explicit():
    facts = observe()
    assert facts['cpu_some_avg10'].value == 12340
    assert facts['cpu_some_avg60'].value == 5000
    assert facts['cpu_some_total'].value == 123450
    assert facts['pswpin_pages_delta'].value == 10
    assert facts['pswpout_pages_delta'].value == 20
    assert facts['host_swap_used_bytes'].value == 2*G
    null(facts['host_cpu_full_pressure'], f.Reason.NOT_APPLICABLE)

def test_no_darwin_metrics_are_fabricated():
    facts = observe()
    null(facts['darwin_vm_counters'], f.Reason.NOT_APPLICABLE)
    null(facts['darwin_fseventsd'], f.Reason.NOT_APPLICABLE)
    assert 'physical_memory_bytes' not in facts  # MemTotal is usable, not installed RAM.

def test_affinity_and_cpuset_intersection_limits_cpu():
    s = replace(scope(), cpuset_effective=read('4-8\n'), affinity=read('8-12\n'))
    assert observe(scope=s)['effective_cpu_capacity_millicores'].value == 1000

def test_unlimited_is_distinct_from_unavailable_and_still_counts_ancestors():
    s = scope()
    s = replace(s, levels=(s.levels[0], replace(s.levels[1], cpu_max=read('max 100000\n'), memory_max=read('max\n'))))
    assert observe(scope=s)['effective_cpu_capacity_millicores'].value == 1500
    assert observe(scope=s)['effective_memory_headroom_estimate_bytes'].value == G
    s = replace(s, levels=(replace(s.levels[0], cpu_max=f.Read(None), memory_max=f.Read(None)), s.levels[1]))
    null(observe(scope=s)['effective_cpu_capacity_millicores'], f.Reason.MISSING)
    null(observe(scope=s)['effective_memory_headroom_estimate_bytes'], f.Reason.MISSING)

def test_measured_zero_headroom_is_not_unknown():
    s = scope(); s = replace(s, levels=(replace(s.levels[0], memory_current=read(str(9*G)+'\n')), s.levels[1]))
    assert observe(scope=s)['effective_memory_headroom_estimate_bytes'] == f.Metric(0)

def test_no_swap_is_known_zero_only_when_both_counters_are_observed():
    r = inputs(); r['meminfo'] = read('MemTotal: 1000 kB\nMemAvailable: 500 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n')
    assert observe(reads=r)['host_swap_used_bytes'] == f.Metric(0)
    r['meminfo'] = read('MemTotal: 1000 kB\nMemAvailable: 500 kB\nSwapTotal: 0 kB\n')
    null(observe(reads=r)['host_swap_used_bytes'], f.Reason.MISSING)

@pytest.mark.parametrize('reason', [f.Reason.MISSING, f.Reason.PERMISSION_DENIED, f.Reason.TIMEOUT, f.Reason.NOT_SUPPORTED])
def test_unavailable_meminfo_never_becomes_zero(reason):
    r=inputs();r['meminfo']=f.Read(None,reason)
    facts=observe(reads=r)
    for name in ['host_usable_memory_bytes','host_available_memory_estimate_bytes','effective_memory_headroom_estimate_bytes']:
        null(facts[name], reason)

@pytest.mark.parametrize('raw,reason', [
    (b'MemTotal: 1 MB\n',f.Reason.MALFORMED),
    (b'MemTotal: -1 kB\n',f.Reason.MALFORMED),
    (b'MemTotal: 1 kB\nMemTotal: 1 kB\n',f.Reason.MALFORMED),
    (b'MemTotal: 1 kB\nMemAvailable: 2 kB\n',f.Reason.MALFORMED),
    (b'MemTotal: 1 kB\nSwapTotal: 0 kB\nSwapFree: 1 kB\n',f.Reason.MALFORMED),
    (b'MemTotal: 9223372036854775807 kB\n',f.Reason.OVERFLOW),
    (b'MemTotal: 999999999999999999999 kB\n',f.Reason.OVERFLOW),
    (b'MemTotal: 1 kB',f.Reason.MALFORMED),
    (b'MemTotal: 1 kB\x00\n',f.Reason.MALFORMED),
    (b'MemTotal: \xff kB\n',f.Reason.MALFORMED),
    (b'\n',f.Reason.MALFORMED),
])
def test_malformed_memory_refusal(raw,reason):
    r=inputs();r['meminfo']=f.Read(raw)
    null(observe(reads=r)['host_usable_memory_bytes'],reason)

@pytest.mark.parametrize('change,reason',[
    ({'elapsed_ms':251},f.Reason.TIMEOUT),
    ({'data':b'x'*(f.MAX_READ_BYTES+1)},f.Reason.OVERFLOW),
    ({'before':(1,2),'after':(1,3)},f.Reason.SOURCE_MOVED),
    ({'elapsed_ms':True},f.Reason.MALFORMED),
    ({'data':'not bytes'},f.Reason.MALFORMED),
    ({'data':b'1\n','failure':f.Reason.MISSING},f.Reason.MALFORMED),
])
def test_read_receipts_fail_closed(change,reason):
    args=dict(data=b'1\n');args.update(change)
    error(lambda:f.Read(**args).text(),reason)

@pytest.mark.parametrize('changes,reason',[
    ({'boot_after':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},f.Reason.BOOT_DRIFT),
    ({'boot_after':'hostname-is-not-boot'},f.Reason.MALFORMED),
    ({'now_ms':99999},f.Reason.FUTURE),
    ({'now_ms':104500},f.Reason.STALE), # end alone is fresh; earliest start is not
    ({'monotonic_end_ms':1000},f.Reason.WINDOW_INVALID),
    ({'monotonic_end_ms':6001},f.Reason.WINDOW_INVALID),
    ({'source_after':2},f.Reason.SOURCE_MOVED),
    ({'now_ms':True},f.Reason.MALFORMED),
])
def test_sample_window_whole_record_refusals(changes,reason):
    error(lambda:observe(window=replace(window(),**changes)),reason)

@pytest.mark.parametrize('changes,reason',[
    ({'complete_ancestry':False},f.Reason.SCOPE_UNQUALIFIED),
    ({'version':1},f.Reason.NOT_SUPPORTED),
    ({'membership_after':2},f.Reason.SOURCE_MOVED),
    ({'limits_after':2},f.Reason.SOURCE_MOVED),
    ({'levels':()},f.Reason.SCOPE_UNQUALIFIED),
])
def test_cgroup_scope_refusal(changes,reason):
    facts=observe(scope=replace(scope(),**changes))
    null(facts['effective_cpu_capacity_millicores'],reason)
    null(facts['effective_memory_headroom_estimate_bytes'],reason)

@pytest.mark.parametrize('text', ['0-3,2\n','3-1\n','4096\n','0,,1\n','-1\n','\n'])
def test_bad_cpuset(text):
    null(observe(scope=replace(scope(),affinity=read(text)))['effective_cpu_capacity_millicores'],f.Reason.MALFORMED)

def test_empty_cpu_intersection_refuses():
    null(observe(scope=replace(scope(),affinity=read('100\n')))['effective_cpu_capacity_millicores'],f.Reason.SCOPE_UNQUALIFIED)

@pytest.mark.parametrize('text,reason',[
    ('1 0\n',f.Reason.MALFORMED),('max\n',f.Reason.MALFORMED),
    ('9223372036854775807 100000\n',f.Reason.OVERFLOW),
    ('-1 100000\n',f.Reason.MALFORMED),('0 100000\n',f.Reason.MALFORMED),
])
def test_quota_format_and_overflow(text,reason):
    s=scope();s=replace(s,levels=(replace(s.levels[0],cpu_max=read(text)),s.levels[1]))
    null(observe(scope=s)['effective_cpu_capacity_millicores'],reason)

def test_missing_required_memavailable_has_typed_reason():
    r=inputs();r['meminfo']=read('MemTotal: 1000 kB\n')
    null(observe(reads=r)['effective_memory_headroom_estimate_bytes'],f.Reason.MISSING)

def test_missing_proc_stat_does_not_show_idle():
    r=inputs();del r['stat_before']
    null(observe(reads=r)['host_cpu_busy_milli_pct'],f.Reason.MISSING)

def test_no_cpu_delta_does_not_show_idle():
    r=inputs();r['stat_after']=r['stat_before']
    null(observe(reads=r)['host_cpu_busy_milli_pct'],f.Reason.NO_COUNTER_DELTA)

def test_iowait_regression_is_unknown_not_clamped():
    r=inputs();r['stat_after']=stat([140,20,70,830,9,5,5,15,20,2])
    null(observe(reads=r)['host_cpu_busy_milli_pct'],f.Reason.COUNTER_REGRESSION)

def test_hotplug_invalidates_cpu_capacity_and_usage():
    r=inputs();r['stat_after']=stat([140,20,70,830,15,5,5,15,20,2],23)
    facts=observe(reads=r)
    null(facts['host_cpu_busy_milli_pct'],f.Reason.SOURCE_MOVED)
    null(facts['effective_cpu_capacity_millicores'],f.Reason.SOURCE_MOVED)

@pytest.mark.parametrize('text,reason', [
    ('some avg10=101.00 avg60=0.00 avg300=0.00 total=1\n',f.Reason.MALFORMED),
    ('some avg10=0.00 avg10=0.00 avg300=0.00 total=1\n',f.Reason.MALFORMED),
    ('some avg10=0 avg60=0.00 avg300=0.00 total=1\n',f.Reason.MALFORMED),
    ('some avg10=0.00 avg60=0.00 avg300=0.00 total=1\n',f.Reason.MISSING),
])
def test_bad_or_missing_memory_psi(text,reason):
    r=inputs();r['pressure_memory']=read(text)
    null(observe(reads=r)['memory_some_avg10'],reason)

def test_psi_permission_restriction_is_unknown():
    r=inputs();r['pressure_cpu']=f.Read(None,f.Reason.PERMISSION_DENIED)
    null(observe(reads=r)['cpu_some_avg10'],f.Reason.PERMISSION_DENIED)

def test_swap_counter_regression_refuses():
    r=inputs();r['vmstat_after']=read('pswpin 90\npswpout 220\n')
    null(observe(reads=r)['pswpin_pages_delta'],f.Reason.COUNTER_REGRESSION)

@pytest.mark.parametrize('changes,reason',[
    ({'before':(8,2,50)},f.Reason.MOUNT_MISMATCH),
    ({'after':(8,1,51)},f.Reason.SOURCE_MOVED),
    ({'qualified_local_mount':False},f.Reason.SCOPE_UNQUALIFIED),
    ({'bavail':10001},f.Reason.MALFORMED),
    ({'bavail':-1},f.Reason.MALFORMED),
    ({'frsize':0},f.Reason.MALFORMED),
    ({'blocks':f.I64,'frsize':4096},f.Reason.OVERFLOW),
])
def test_disk_mount_and_usable_bytes_refusals(changes,reason):
    null(observe(disk=replace(disk(),**changes))['disk_usable_bytes'],reason)

def test_usable_disk_is_bavail_not_total_or_root_free():
    assert observe()['disk_usable_bytes'].value == 5000*4096

def test_caller_cannot_add_host_identity_or_paths():
    for key in ('host_ref','/proc/self/environ','worker_id','reserve'):
        r=inputs();r[key]=read('1\n')
        error(lambda:observe(reads=r),f.Reason.MALFORMED)

def test_module_has_no_effectful_runtime_imports():
    tree=ast.parse(Path(f.__file__).read_text())
    imports=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imports.update(x.name.split('.')[0] for x in n.names)
        if isinstance(n,ast.ImportFrom):imports.add(n.module.split('.')[0])
    assert imports <= {'__future__','dataclasses','enum','re','typing'}

@pytest.mark.parametrize('args', [(None,None),(1,f.Reason.MISSING),(True,None),(-1,None)])
def test_metric_null_contract(args):
    error(lambda:f.Metric(*args),f.Reason.MALFORMED)
