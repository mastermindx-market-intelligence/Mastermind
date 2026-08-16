"""OHF-P0 harness laboratory — production-inert capability and recovery probes.

This package must never import Executive OS lifecycle modules, open the
Executive SQLite store, claim workers, or arm live execution.  See
``research/EXECUTIVE_OS_OHF_P0_PROBE_SPEC.md``.
"""

SCHEMA_VERSION = "mastermind.ohf_harness_probe/v1"

__all__ = ["SCHEMA_VERSION"]
