"""Include physical-root transport and custody qualification in hosted CI."""

from pathlib import Path
import sys

_rollout = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/rollout"
_before = list(sys.path)
try:
    sys.path.insert(0, str(_rollout))
    from ops.native_fabric.quota_continuity.rollout.test_remote_lane_root import PhysicalRootCase
finally:
    sys.path[:] = _before
