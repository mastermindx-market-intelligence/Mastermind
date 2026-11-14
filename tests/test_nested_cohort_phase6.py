"""Portable mechanics qualification, not market-data profitability proof."""
import os
from pathlib import Path
import subprocess
import sys


def test_nested_cycle_cohort_research():
    root=Path(__file__).resolve().parents[1]/"research"/"apmem_shadow"/"phase6"
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
    p=subprocess.run([sys.executable,"-m","unittest","discover","-s",".","-p","test_*.py"],cwd=root,env=env,text=True,capture_output=True,timeout=180)
    assert p.returncode==0,p.stdout+p.stderr
    assert "OK" in p.stderr
