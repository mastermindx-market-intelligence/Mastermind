"""Compatibility facade for the durable Executive OS runtime.

Phase 1A callers import this module.  Phase 1B moved lifecycle authority to the
dedicated SQLite implementation without changing those registry entry points.
No legacy JSON snapshot is read or imported.
"""

from control_plane.executive_runtime import *  # noqa: F401,F403
from control_plane.executive_runtime import __all__
