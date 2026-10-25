"""Installed native-host entry; source root is fixed by its reviewed launcher."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.mastermind_browser_link.native_bridge import main

if __name__ == "__main__":
    raise SystemExit(main())
