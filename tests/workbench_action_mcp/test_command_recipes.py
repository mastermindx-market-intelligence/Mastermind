"""Real-process contract tests for the two closed Workbench canary recipes."""

import ast
import hashlib
import os
import subprocess
import sys
import tempfile
import time

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RECIPE_DIR = os.path.join(REPO_ROOT, "integrations", "workbench_action_mcp", "recipes")
CANARY_CHECKSUM = os.path.join(RECIPE_DIR, "canary_checksum.py")
CANARY_REFUSE = os.path.join(RECIPE_DIR, "canary_refuse.py")
PYTHON = os.path.realpath(sys.executable)
CLOSED_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONSAFEPATH": "1"}
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
HELLO_SHA256 = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
CHECKSUM_REFUSAL = b"checksum-refused\n"
VALIDATION_REFUSAL = b"validation-refused\n"

CHECKSUM_SEQUENCE = [
    "line=01", "line=02", "line=03", "line=04", "line=05", "line=06",
    "line=07", "line=08", "line=09", "line=10", "line=11", "line=12",
    "line=13", "line=14", "line=15", "line=16", "line=17", "line=18",
    "line=19", "line=20", "line=21", "line=22", "line=23", "line=24",
    "line=25", "line=26", "line=27", "line=28", "line=29", "line=30",
    "line=31", "line=32", "line=33", "line=34",
]
REFUSAL_SEQUENCE = CHECKSUM_SEQUENCE[:-1]


def _expected_checksum_output(label, digest):
    lines = [
        "WORKBENCH_CANARY_CHECKSUM v1",
        "recipe=canary_checksum",
        f"path={label}",
        f"expected_sha256={digest}",
        f"actual_sha256={digest}",
        "result=MATCH",
        *CHECKSUM_SEQUENCE,
    ]
    assert len(lines) == 40
    return ("\n".join(lines) + "\n").encode("utf-8")


def _expected_refusal_output(label, digest):
    lines = [
        "WORKBENCH_CANARY_REFUSAL v1",
        "recipe=canary_refuse",
        f"path={label}",
        f"expected_sha256={digest}",
        f"actual_sha256={digest}",
        "result=REFUSED",
        "reason=deliberate_validation_refusal",
        *REFUSAL_SEQUENCE,
    ]
    assert len(lines) == 40
    return ("\n".join(lines) + "\n").encode("utf-8")


def _spawn(
    script, fd_arg, expected_sha256, label, pass_fd=None, *, root_path=None,
    root_device=None, root_inode=None,
):
    root_fd = os.open(
        root_path or os.getcwd(), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    )
    root_stat = os.fstat(root_fd)
    pass_fds = (root_fd,) if pass_fd is None else (pass_fd, root_fd)
    try:
        return subprocess.Popen(
            [
                PYTHON, "-I", "-S", script, str(fd_arg), str(root_fd),
                str(root_stat.st_dev if root_device is None else root_device),
                str(root_stat.st_ino if root_inode is None else root_inode),
                expected_sha256, label,
            ],
            env=CLOSED_ENV,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=pass_fds,
            close_fds=True,
            cwd="/",
        )
    finally:
        os.close(root_fd)


def _finish(proc, barrier=b"\x01", require_blocked=False, timeout=5.0):
    try:
        if require_blocked:
            time.sleep(0.1)
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=1.0)
                pytest.fail(
                    "recipe exited before the launch barrier: "
                    f"rc={proc.returncode}, stdout={stdout!r}, stderr={stderr!r}"
                )
        try:
            stdout, stderr = proc.communicate(input=barrier, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=1.0)
            pytest.fail(f"recipe timed out: stdout={stdout!r}, stderr={stderr!r}")
        return stdout, stderr, proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=1.0)


def _invoke(
    script, fd_arg, expected_sha256, label, *, pass_fd=None,
    barrier=b"\x01", require_blocked=False, **spawn_options,
):
    proc = _spawn(
        script, fd_arg, expected_sha256, label,
        pass_fd=pass_fd, **spawn_options,
    )
    return _finish(proc, barrier=barrier, require_blocked=require_blocked)


def _invoke_raw_args(script, args):
    proc = subprocess.Popen(
        [PYTHON, "-I", "-S", script, *args],
        env=CLOSED_ENV,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(),
        close_fds=True,
    )
    return _finish(proc)


def _make_file(content):
    fixture = tempfile.NamedTemporaryFile(delete=False)
    try:
        fixture.write(content)
        fixture.flush()
        return fixture.name
    finally:
        fixture.close()


def _read_file(path):
    with open(path, "rb") as handle:
        return handle.read()


def _assert_fixed_refusal(result, diagnostic):
    stdout, stderr, returncode = result
    assert returncode == 125
    assert stdout == b""
    assert stderr == diagnostic


def test_recipe_source_has_exact_imports_and_no_escape_apis():
    """An added import or escape API would widen the trusted recipe surface."""
    prohibited_names = {"open", "exec", "eval", "compile", "__import__"}
    prohibited_os_calls = {
        "open", "popen", "system", "fork", "forkpty", "posix_spawn",
        "posix_spawnp", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv",
        "spawnve", "spawnvp", "spawnvpe", "execl", "execle", "execlp",
        "execlpe", "execv", "execve", "execvp", "execvpe",
    }
    for recipe in (CANARY_CHECKSUM, CANARY_REFUSE):
        with open(recipe, "r", encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read(), filename=recipe)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in prohibited_names
                elif (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    assert node.func.attr not in prohibited_os_calls
        assert imported == {"hashlib", "os", "stat", "sys"}


def test_recipe_inventory_contains_only_two_recipes_and_empty_init():
    """Adding another executable recipe would bypass the fixed two-recipe review."""
    assert sorted(name for name in os.listdir(RECIPE_DIR) if name.endswith(".py")) == [
        "__init__.py", "canary_checksum.py", "canary_refuse.py",
    ]
    with open(os.path.join(RECIPE_DIR, "__init__.py"), "rb") as init_file:
        assert init_file.read() == b""


def test_checksum_valid_file_waits_then_emits_exact_match_output():
    """A checksum recipe that skips the barrier or changes its output is rejected."""
    path = _make_file(b"hello world")
    try:
        before = _read_file(path)
        with open(path, "rb") as input_file:
            result = _invoke(
                CANARY_CHECKSUM, input_file.fileno(), HELLO_SHA256, "fixture.bin",
                pass_fd=input_file.fileno(), require_blocked=True,
            )
        assert result == (
            _expected_checksum_output("fixture.bin", HELLO_SHA256),
            b"checksum-ok\n", 0,
        )
        assert _read_file(path) == before
    finally:
        os.unlink(path)


def test_recipe_enters_selected_descriptor_cwd_and_rejects_wrong_root_identity(tmp_path):
    """A harmless launch cwd cannot substitute for the host-selected root fd."""
    path = _make_file(b"hello world")
    selected_root = tmp_path / "selected-root"
    selected_root.mkdir()
    try:
        with open(path, "rb") as input_file:
            result = _invoke(
                CANARY_CHECKSUM,
                input_file.fileno(),
                HELLO_SHA256,
                "fixture.bin",
                pass_fd=input_file.fileno(),
                root_path=selected_root,
                require_blocked=True,
            )
        assert result == (
            _expected_checksum_output("fixture.bin", HELLO_SHA256),
            b"checksum-ok\n",
            0,
        )
        with open(path, "rb") as input_file:
            root_stat = selected_root.stat()
            result = _invoke(
                CANARY_CHECKSUM,
                input_file.fileno(),
                HELLO_SHA256,
                "fixture.bin",
                pass_fd=input_file.fileno(),
                root_path=selected_root,
                root_inode=root_stat.st_ino + 1,
                require_blocked=True,
            )
        _assert_fixed_refusal(result, CHECKSUM_REFUSAL)
    finally:
        os.unlink(path)


def test_checksum_reads_full_maximum_file_from_offset_zero():
    """A single read or inherited-offset read cannot silently hash a suffix."""
    content = b"x" * 65536
    digest = hashlib.sha256(content).hexdigest()
    path = _make_file(content)
    try:
        with open(path, "rb") as input_file:
            input_file.seek(4096)
            result = _invoke(
                CANARY_CHECKSUM, input_file.fileno(), digest, "maximum.bin",
                pass_fd=input_file.fileno(), require_blocked=True,
            )
        assert result == (
            _expected_checksum_output("maximum.bin", digest), b"checksum-ok\n", 0,
        )
        assert _read_file(path) == content
    finally:
        os.unlink(path)


@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_hash_mismatch_is_fixed_refusal(script, diagnostic):
    """A mismatch must never become checksum success or deliberate exit 7."""
    path = _make_file(b"hello world")
    try:
        before = _read_file(path)
        with open(path, "rb") as input_file:
            result = _invoke(
                script, input_file.fileno(), EMPTY_SHA256, "fixture.bin",
                pass_fd=input_file.fileno(), require_blocked=True,
            )
        _assert_fixed_refusal(result, diagnostic)
        assert _read_file(path) == before
    finally:
        os.unlink(path)


@pytest.mark.parametrize("label", [
    "", ".", "..", "a/b", "a\\b", "a\nb", "snowman-\u2603", "a" * 129,
])
@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_invalid_labels_refuse_without_reflection(script, diagnostic, label):
    """Unsafe and non-ASCII labels must produce only a fixed diagnostic."""
    result = _invoke(script, "3", EMPTY_SHA256, label)
    _assert_fixed_refusal(result, diagnostic)
    if label:
        assert label.encode("utf-8") not in result[1]


@pytest.mark.parametrize("bad_hash", [
    "abc", "A" * 64, "+" + "a" * 63, " " + "a" * 63,
])
@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_invalid_hashes_refuse_without_normalization(script, diagnostic, bad_hash):
    """Only exactly 64 lowercase hexadecimal characters are accepted."""
    _assert_fixed_refusal(_invoke(script, "3", bad_hash, "fixture.bin"), diagnostic)


@pytest.mark.parametrize("args", [
    [],
    ["3", "4", "1", "2", EMPTY_SHA256],
    ["3", "4", "1", "2", EMPTY_SHA256, "fixture.bin", "extra"],
])
@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_invalid_argument_count_is_fixed_refusal(script, diagnostic, args):
    """Missing or surplus arguments must not reach descriptor processing."""
    _assert_fixed_refusal(_invoke_raw_args(script, args), diagnostic)


@pytest.mark.parametrize("bad_fd", ["2", "+3", " 3", "three", "\u0663"])
@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_invalid_fd_syntax_refuses_without_traceback(script, diagnostic, bad_fd):
    """Only an ASCII decimal descriptor at least three is accepted."""
    _assert_fixed_refusal(_invoke(script, bad_fd, EMPTY_SHA256, "fixture.bin"), diagnostic)


@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
@pytest.mark.parametrize("fd_arg", ["999999", "9" * 100])
def test_closed_or_out_of_range_fd_refuses_without_traceback(script, diagnostic, fd_arg):
    """An unavailable or OS-out-of-range descriptor must stay sanitized."""
    _assert_fixed_refusal(
        _invoke(script, fd_arg, EMPTY_SHA256, "fixture.bin"), diagnostic,
    )


@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_non_regular_descriptor_refuses(script, diagnostic):
    """A pipe cannot be substituted for the approved regular input file."""
    read_fd, write_fd = os.pipe()
    try:
        result = _invoke(
            script, read_fd, EMPTY_SHA256, "fixture.bin",
            pass_fd=read_fd, require_blocked=True,
        )
        _assert_fixed_refusal(result, diagnostic)
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_multiple_link_file_refuses_without_modification(script, diagnostic):
    """An input with more than one hard link violates the identity contract."""
    path = _make_file(b"hello world")
    linked_path = path + ".link"
    os.link(path, linked_path)
    try:
        before = _read_file(path)
        with open(path, "rb") as input_file:
            result = _invoke(
                script, input_file.fileno(), HELLO_SHA256, "fixture.bin",
                pass_fd=input_file.fileno(), require_blocked=True,
            )
        _assert_fixed_refusal(result, diagnostic)
        assert _read_file(path) == before
    finally:
        os.unlink(linked_path)
        os.unlink(path)


@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_oversized_file_refuses_without_modification(script, diagnostic):
    """A 65,537-byte file must not be read as an approved bounded input."""
    content = b"x" * 65537
    path = _make_file(content)
    try:
        with open(path, "rb") as input_file:
            result = _invoke(
                script, input_file.fileno(), hashlib.sha256(content).hexdigest(),
                "oversized.bin", pass_fd=input_file.fileno(), require_blocked=True,
            )
        _assert_fixed_refusal(result, diagnostic)
        assert _read_file(path) == content
    finally:
        os.unlink(path)


@pytest.mark.parametrize("barrier", [b"", b"\x00"])
@pytest.mark.parametrize("script,diagnostic", [
    (CANARY_CHECKSUM, CHECKSUM_REFUSAL),
    (CANARY_REFUSE, VALIDATION_REFUSAL),
])
def test_missing_or_wrong_barrier_refuses(script, diagnostic, barrier):
    """EOF and any launch byte other than one are fixed refusals."""
    path = _make_file(b"hello world")
    try:
        before = _read_file(path)
        with open(path, "rb") as input_file:
            result = _invoke(
                script, input_file.fileno(), HELLO_SHA256, "fixture.bin",
                pass_fd=input_file.fileno(), barrier=barrier, require_blocked=True,
            )
        _assert_fixed_refusal(result, diagnostic)
        assert _read_file(path) == before
    finally:
        os.unlink(path)


def test_refusal_recipe_valid_file_emits_exact_deliberate_refusal():
    """Only a fully valid refusal invocation earns exit 7 and the 40-line record."""
    path = _make_file(b"hello world")
    try:
        before = _read_file(path)
        with open(path, "rb") as input_file:
            result = _invoke(
                CANARY_REFUSE, input_file.fileno(), HELLO_SHA256, "fixture.bin",
                pass_fd=input_file.fileno(), require_blocked=True,
            )
        assert result == (
            _expected_refusal_output("fixture.bin", HELLO_SHA256),
            b"validation-refused\n", 7,
        )
        assert _read_file(path) == before
    finally:
        os.unlink(path)
