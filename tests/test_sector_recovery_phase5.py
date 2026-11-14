"""Hermetic qualification of the independently tested sector-recovery research."""
import os
from pathlib import Path
import subprocess
import sys


def test_sector_recovery_phase5_hermetic_suite():
    directory=Path(__file__).resolve().parents[1]/"research"/"apmem_shadow"/"phase5"
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
    result=subprocess.run([sys.executable,"-m","unittest","discover","-s",".","-p","test_*.py"],
        cwd=directory,env=env,text=True,capture_output=True,timeout=180)
    assert result.returncode==0, result.stdout+result.stderr
    assert "Ran " in result.stderr and "OK" in result.stderr
