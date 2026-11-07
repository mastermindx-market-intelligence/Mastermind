"""Fail a pytest-xdist shard that lost a worker or ran fewer tests than it collected.

pytest-xdist 3.8.0 exits 0 with "no tests ran" when a worker dies during
import or collection (``DSession.worker_errordown`` has no crash item to turn
into a failed report, ``--max-worker-restart 0`` only triggers shutdown, and
``session.testscollected`` was already set by the surviving workers so pytest
does not even return NO_TESTS_COLLECTED). A shard whose process exit code is
the only thing the fan-in reads would then pass with zero tests executed.

This plugin registers on the xdist controller only. It records every worker
that went down with an error and counts the test cases that actually
finished; at session end, if a worker died or fewer cases finished than were
collected, it writes one ``CI_XDIST_GUARD`` line and forces a non-zero exit
status. It never turns a failure into a pass or changes collection or ordering.
An explicitly requested serial-child mode additionally writes a small terminal
receipt for the incumbent process runner. Ordinary serial runs are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


CHILD_RECEIPT_NAME = "ci-pytest-completion.json"
CHILD_RECEIPT_SCHEMA = "ci.pytest-child-completion.v1"
MAX_CHILD_RECEIPT_BYTES = 2 ** 12


def item_digest(items) -> str:
    """Bind exact ordered arguments or an explicitly sorted case multiset."""
    return hashlib.sha256(json.dumps(
        list(items), ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()


def _private_directory(path: Path):
    if not path.is_absolute():
        raise ValueError("completion directory must be absolute")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        held, named = os.fstat(fd), path.lstat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_uid)
        if (identity(held) != identity(named) or not stat.S_ISDIR(held.st_mode)
                or stat.S_IMODE(held.st_mode) != stat.S_IRWXU
                or held.st_uid != os.geteuid()):
            raise ValueError("completion directory is not privately owned")
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_child_receipt(path: Path, value: dict) -> None:
    if path.name != CHILD_RECEIPT_NAME:
        raise ValueError("unexpected completion leaf")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("ascii")
    if len(raw) > MAX_CHILD_RECEIPT_BYTES:
        raise ValueError("completion receipt exceeds its bound")
    directory = _private_directory(path.parent)
    output = None
    try:
        output = os.open(CHILD_RECEIPT_NAME,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         stat.S_IRUSR | stat.S_IWUSR, dir_fd=directory)
        if os.write(output, raw) != len(raw):
            raise OSError("incomplete completion receipt write")
        os.fsync(output)
    finally:
        if output is not None:
            os.close(output)
        os.close(directory)


def read_child_receipt(path: Path):
    """Read one small owned regular leaf; never adopt foreign/stale output."""
    if path.name != CHILD_RECEIPT_NAME:
        raise ValueError("unexpected completion leaf")
    directory = _private_directory(path.parent)
    source = None
    try:
        source = os.open(CHILD_RECEIPT_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
        before = os.fstat(source)
        named = os.stat(CHILD_RECEIPT_NAME, dir_fd=directory, follow_symlinks=False)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode,
                                 info.st_uid, info.st_nlink, info.st_size,
                                 info.st_mtime_ns, info.st_ctime_ns)
        if (identity(before) != identity(named)
                or not stat.S_ISREG(before.st_mode)
                or stat.S_IMODE(before.st_mode) != stat.S_IRUSR | stat.S_IWUSR
                or before.st_uid != os.geteuid() or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_CHILD_RECEIPT_BYTES):
            raise ValueError("completion receipt is not an owned bounded file")
        raw = os.read(source, MAX_CHILD_RECEIPT_BYTES + 1)
        if (len(raw) != before.st_size or identity(os.fstat(source)) != identity(before)
                or identity(os.stat(CHILD_RECEIPT_NAME, dir_fd=directory,
                                    follow_symlinks=False)) != identity(before)):
            raise ValueError("completion receipt changed during read")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate completion field")
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=unique_object)
    finally:
        if source is not None:
            os.close(source)
        os.close(directory)


def valid_child_receipt(value, *, pid: int, token: str,
                        assigned_digest: str, returncode: int) -> bool:
    fields = {"schema", "pid", "token", "assigned_modules_sha256", "collected",
              "finished", "collected_sha256", "finished_sha256",
              "collection_completed", "collection_errors", "deselected", "exitstatus"}
    if type(value) is not dict or set(value) != fields:
        return False
    if (value["schema"] != CHILD_RECEIPT_SCHEMA or type(value["pid"]) is not int
            or value["pid"] != pid or value["token"] != token
            or value["assigned_modules_sha256"] != assigned_digest
            or value["collection_completed"] is not True):
        return False
    for field in ("collected", "finished", "collection_errors", "deselected", "exitstatus"):
        if type(value[field]) is not int or not 0 <= value[field] <= 2 ** 20:
            return False
    for field in ("collected_sha256", "finished_sha256"):
        if type(value[field]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[field]) is None:
            return False
    return (0 < value["collected"] == value["finished"]
            and value["collected_sha256"] == value["finished_sha256"]
            and value["collection_errors"] == value["deselected"] == 0
            and value["exitstatus"] == returncode)


class SerialCompletionGuard:
    """Opt-in terminal proof; raw case IDs never leave this process."""
    def __init__(self, config, reporter):
        self.config = config
        self.reporter = reporter
        self.collected = []
        self.finished = []
        self.collection_completed = False
        self.collection_errors = 0
        self.deselected = 0

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]
        self.collection_completed = True

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_runtest_logfinish(self, nodeid, location):
        self.finished.append(nodeid)

    def pytest_sessionfinish(self, session, exitstatus):
        value = dict(schema=CHILD_RECEIPT_SCHEMA, pid=os.getpid(),
                     token=self.config.option.ci_child_token,
                     assigned_modules_sha256=item_digest(self.config.args),
                     collected=len(self.collected), finished=len(self.finished),
                     collected_sha256=item_digest(sorted(self.collected)),
                     finished_sha256=item_digest(sorted(self.finished)),
                     collection_completed=self.collection_completed,
                     collection_errors=self.collection_errors,
                     deselected=self.deselected, exitstatus=int(session.exitstatus))
        try:
            write_child_receipt(Path(self.config.option.ci_child_receipt), value)
        except (OSError, ValueError, TypeError, OverflowError):
            if self.reporter is not None:
                self.reporter.write_line("\nCI_CHILD_GUARD terminal receipt unavailable")
            if not int(session.exitstatus or 0):
                session.exitstatus = 1


def pytest_addoption(parser):
    group = parser.getgroup("ci-child-completion")
    group.addoption("--ci-child-receipt", default=None)
    group.addoption("--ci-child-token", default=None)


class XdistCompletionGuard:
    def __init__(self, reporter) -> None:
        self.reporter = reporter
        self.node_errors: list[tuple[str, str]] = []
        self.finished = 0

    def pytest_testnodedown(self, node, error) -> None:
        if error:
            gateway = getattr(node, "gateway", None)
            self.node_errors.append(
                (str(getattr(gateway, "id", None) or node), str(error))
            )

    def pytest_runtest_logfinish(self, nodeid, location) -> None:
        self.finished += 1

    def problems(self, session) -> list[str]:
        found = []
        for worker, error in self.node_errors:
            found.append(f"worker {worker} went down: {error}")
        collected = int(getattr(session, "testscollected", 0) or 0)
        if self.finished < collected:
            found.append(
                f"finished {self.finished} of {collected} collected test cases"
            )
        return found

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        found = self.problems(session)
        if not found:
            return
        self.reporter.write_line(
            "\nCI_XDIST_GUARD shard incomplete: " + "; ".join(found)
        )
        if not int(session.exitstatus or 0):
            # pytest returns session.exitstatus after this hook; a shard that
            # lost tests is a failed shard, never a quiet pass.
            session.exitstatus = 1


def pytest_sessionstart(session) -> None:
    config = session.config
    receipt = getattr(config.option, "ci_child_receipt", None)
    token = getattr(config.option, "ci_child_token", None)
    if receipt is not None or token is not None:
        if (type(receipt) is not str or type(token) is not str
                or re.fullmatch(r"[0-9a-f]{32}", token) is None
                or hasattr(config, "workerinput")
                or getattr(config.option, "numprocesses", None)):
            raise ValueError("invalid serial child completion request")
        config.pluginmanager.register(
            SerialCompletionGuard(config, config.pluginmanager.getplugin("terminalreporter")),
            "ci-serial-completion-guard",
        )
        return
    if hasattr(config, "workerinput"):
        return  # an xdist worker: the controller sees every relayed event
    if not getattr(config.option, "numprocesses", None):
        return  # serial run: the process exit status already covers it
    reporter = config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        config.pluginmanager.register(
            XdistCompletionGuard(reporter), "ci-xdist-completion-guard"
        )
