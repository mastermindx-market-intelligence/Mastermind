"""Real process-group signal checks with synthetic helpers; no provider access."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

EXT = Path(__file__).resolve().parents[1]

KEYS = '''import json,os,sys
from pathlib import Path
cmd=sys.argv[1]
row=[cmd]
if cmd=='release': row.append(Path(os.environ['SETTLED']).exists())
with Path(os.environ['EVENTS']).open('a') as f:f.write(json.dumps(row)+'\\n')
if cmd=='pick': print('FixtureAccount')
elif cmd=='env': print("export BAILIAN_API_KEY='SYNTHETIC_FIXTURE_ONLY'")
elif cmd=='model': print(sys.argv[2])
elif cmd=='stream':
 data=sys.stdin.read();Path(sys.argv[2]).write_text('fixture-thread');Path(sys.argv[3]).write_text(data);print(data)
elif cmd in ('next_usable_in','seconds_until_offpeak'): print(0)
'''

CODEX = '''import os,signal,time
from pathlib import Path
stopping=False
def stop(signum,frame):
 global stopping
 stopping=True
for value in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(value,stop)
Path(os.environ['READY']).write_text(str(os.getpid()))
while not stopping:time.sleep(.005)
# Remain alive through a repeated group signal, then settle cleanly. Even this
# zero child exit must never overwrite the wrapper's terminal signal status.
time.sleep(.2)
Path(os.environ['SETTLED']).write_text('settled')
'''


@pytest.mark.parametrize('stop_signal,expected', [
    (signal.SIGTERM, 143), (signal.SIGINT, 130), (signal.SIGHUP, 129),
])
@pytest.mark.parametrize('repeat', [False, True])
def test_signal_is_terminal_after_child_settlement(tmp_path, stop_signal, expected, repeat):
    ext = tmp_path / 'ext'
    ext.mkdir()
    shutil.copy2(EXT / 'qwen_exec.sh', ext / 'qwen_exec.sh')
    # This test owns signal terminality, not Studio MCP projection. Supply the
    # projection owner's no-override success shape so the real wrapper reaches
    # the offline child without contacting an external surface.
    projection = ext / 'studio_mcp_projection.sh'
    projection.write_text('#!/bin/sh\nexit 0\n')
    projection.chmod(0o700)
    (ext / 'bailian_keys.py').write_text(KEYS)
    (ext / 'pool_ledger.py').write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['LEDGER']).write_text('unexpected post-signal ledger')\n"
    )
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'python3').symlink_to(sys.executable)
    cli = binary / 'codex'
    cli.write_text(f'#!{sys.executable}\n' + CODEX)
    cli.chmod(0o700)
    prompt = tmp_path / 'prompt'
    prompt.write_text('offline signal fixture')
    ready, settled = tmp_path / 'ready', tmp_path / 'settled'
    events, ledger = tmp_path / 'events', tmp_path / 'ledger'
    conf = tmp_path / 'lanes/codex_bailian/config.toml'
    conf.parent.mkdir(parents=True)
    conf.write_text('model = "qwen3.8-flash"\n')
    conf.chmod(0o600)
    env = {
        'PATH': str(binary) + ':/usr/bin:/bin', 'HOME': str(tmp_path),
        'TMPDIR': str(tmp_path), 'READY': str(ready), 'SETTLED': str(settled),
        'EVENTS': str(events), 'LEDGER': str(ledger),
        'QWEN_EXEC_SLOTTED': '1', 'LANE_LEASED': '1',
        'POOL_ACCOUNT': 'FixtureAccount', 'POOL_LEASE_ID': '',
        'QWEN_EXEC_KEY_WAIT': '0',
    }
    proc = subprocess.Popen(
        ['/bin/bash', str(ext / 'qwen_exec.sh'), str(tmp_path),
         'qwen3.8-flash', str(prompt)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 4
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists(), 'offline child failed to start'
        child_pid = int(ready.read_text())
        os.killpg(proc.pid, stop_signal)
        if repeat:
            time.sleep(.04)
            os.killpg(proc.pid, stop_signal)
        out, err = proc.communicate(timeout=4)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=4)
    assert proc.returncode == expected, err
    assert 'SYNTHETIC_FIXTURE_ONLY' not in out + err
    assert 'done key=' not in err
    assert 'No such file or directory' not in err
    assert 'failover' not in err
    assert settled.exists()
    assert not ledger.exists()
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert sum(row[0] == 'pick' for row in rows) == 1
    assert [row for row in rows if row[0] == 'release'] == [['release', True]]
    assert not any(row[0] in ('cooldown', 'next_usable_in') for row in rows)
    assert not (tmp_path / f'qwen_exec.{proc.pid}').exists()
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
