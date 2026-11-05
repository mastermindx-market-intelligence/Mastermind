from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest


_CLOSED_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONSAFEPATH": "1",
}


@pytest.fixture(scope="session")
def private_python_executable(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Build the private interpreter required by production command attestation."""

    environment = tmp_path_factory.mktemp("workbench-command-python") / "runtime"
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-m",
            "venv",
            "--copies",
            "--without-pip",
            str(environment),
        ],
        check=True,
        cwd="/",
        env=_CLOSED_ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    executable = environment / "bin" / "python"
    os.chmod(executable, 0o500)
    observed = os.lstat(executable)
    assert stat.S_ISREG(observed.st_mode)
    assert observed.st_uid == os.geteuid()
    assert observed.st_nlink == 1
    assert stat.S_IMODE(observed.st_mode) == 0o500
    assert 0 < observed.st_size <= 64 * 1024 * 1024
    probe = subprocess.run(
        [
            str(executable),
            "-I",
            "-S",
            "-c",
            "import os,sys;assert os.path.samefile(sys.executable,sys.argv[1])",
            str(executable),
        ],
        check=False,
        cwd="/",
        env=_CLOSED_ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert probe.returncode == 0, probe.stderr.decode("utf-8", errors="replace")
    return str(executable)
