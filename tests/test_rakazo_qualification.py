"""CI entry for the pinned Rakazo HC-P1B.T1 qualification."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "integrations" / "rakazo_qualification"
RAKAZO_PIN = "c5e66e010ee3f3166d2ad216f928a75a0b9a2218"


def test_rakazo_hc_p1b_qualification_observes_pinned_source() -> None:
    completed = subprocess.run(
        ["npm", "test"],
        cwd=QUALIFICATION,
        check=False,
        text=True,
        capture_output=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"rakazo qualification exited {completed.returncode}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    assert RAKAZO_PIN in completed.stdout
    assert "tampered donor source is rejected before import" in completed.stdout
    assert "NOT_RUN" in completed.stdout
