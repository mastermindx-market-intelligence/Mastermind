"""Fixed attended DSH reverse; the incumbent Fabric/OS identities are unchanged."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.executive_os import application_tunnel_entry, os_tunnel_entry


def main():
    return application_tunnel_entry._main_for_purpose(os_tunnel_entry.DEEPSEEK_APPLICATION)


if __name__ == "__main__":
    raise SystemExit(main())
