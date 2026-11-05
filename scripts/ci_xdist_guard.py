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
status. It never turns a failure into a pass, never changes collection,
ordering or outcomes, and does nothing in a serial run.
"""
from __future__ import annotations


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
    if hasattr(config, "workerinput"):
        return  # an xdist worker: the controller sees every relayed event
    if not getattr(config.option, "numprocesses", None):
        return  # serial run: the process exit status already covers it
    reporter = config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        config.pluginmanager.register(
            XdistCompletionGuard(reporter), "ci-xdist-completion-guard"
        )
