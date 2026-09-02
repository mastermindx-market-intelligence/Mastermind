"""Fixture corpora are data for the C0 experiment, never tests to collect.

Without this, the repository's full suite would try to import corpus files that
are deliberately incomplete (they carry a planted diagnostic) and are meant to
be read by a language server, not executed by pytest.
"""

from __future__ import annotations


def pytest_ignore_collect(collection_path, config):  # noqa: ARG001
    return True
