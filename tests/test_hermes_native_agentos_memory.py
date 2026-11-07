"""Run the native context contract and actual-source lifecycle in protected CI.

The same cases remain usable directly from each integration package. These
imports enroll them in the existing tests-only collection and shard workflow;
they create no alternate runner, workflow or service.
"""
from integrations.hermes_harness.tests.test_native_agentos_context import *  # noqa: F401,F403
from integrations.hermes_runtime.tests.test_native_agentos_memory import *  # noqa: F401,F403
