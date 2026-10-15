"""Opt-in CI diagnostics; no collection, ordering, outcome or timeout changes."""
from __future__ import annotations

import json


class ModuleTiming:
    def __init__(self, reporter):
        self.reporter = reporter
        self.module = None
        self.cases_started = 0
        self.cases_finished = 0
        self.reported_seconds = 0.0

    def _emit(self, event, **fields):
        # Pytest's quiet progress dots can leave an unterminated line. Keep
        # each record independently parseable without touching that output.
        self.reporter.write_line("\nCI_MODULE " + json.dumps(
            {"event": event, "module": self.module, **fields}, sort_keys=True,
        ))

    def _summarize(self):
        if self.module is not None:
            self._emit(
                "summary", cases_started=self.cases_started,
                cases_finished=self.cases_finished,
                reported_seconds=round(self.reported_seconds, 6),
            )

    def pytest_runtest_logstart(self, nodeid, location):
        module = nodeid.split("::", 1)[0]
        if module != self.module:
            self._summarize()
            self.module = module
            self.cases_started = self.cases_finished = 0
            self.reported_seconds = 0.0
            self._emit("start")
        self.cases_started += 1

    def pytest_runtest_logreport(self, report):
        if report.nodeid.split("::", 1)[0] == self.module:
            self.reported_seconds += report.duration

    def pytest_runtest_logfinish(self, nodeid, location):
        if nodeid.split("::", 1)[0] == self.module:
            self.cases_finished += 1

    def pytest_sessionfinish(self, session, exitstatus):
        self._summarize()


def pytest_sessionstart(session):
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        session.config.pluginmanager.register(ModuleTiming(reporter), "ci-module-timing")
