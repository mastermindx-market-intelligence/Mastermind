from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "prepare-capacity-host.sh"


def test_root_inline_json_parsers_use_isolated_python() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    unsafe = [
        line.strip()
        for line in source.splitlines()
        if "/usr/bin/python3 -c" in line and "json.load(sys.stdin)" in line
    ]
    isolated = [
        line.strip()
        for line in source.splitlines()
        if "/usr/bin/python3 -I -S -B -c" in line and "json.load(sys.stdin)" in line
    ]

    assert unsafe == []
    assert len(isolated) == 4


def test_isolated_inline_python_does_not_import_hostile_cwd_json(tmp_path: Path) -> None:
    marker = tmp_path / "imported"
    (tmp_path / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    vulnerable = subprocess.run(
        ["/usr/bin/python3", "-c", "import json"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert vulnerable.returncode == 0
    assert marker.exists()

    marker.unlink()
    isolated = subprocess.run(
        ["/usr/bin/python3", "-I", "-S", "-B", "-c", "import json"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert isolated.returncode == 0
    assert not marker.exists()
