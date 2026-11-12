"""GBL-5 R2 (ruling 19b): ONE append performed by a SEPARATE process.

The two-process seq law needs real processes: each child builds its OWN
``PaperclipAskClient`` from a JSON config on argv (fixture facts only —
base URL, ids, the key file PATH, the ask id and a harmless fixture event;
no secret value ever rides argv) and performs exactly one
``append_ask_event``.  The parent test asserts on the stored comments.

Not collected by pytest (name lacks the ``test_`` prefix).
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from integrations.gbl.paperclip_client import PaperclipAskClient  # noqa: E402


def main() -> int:
    cfg = json.loads(sys.argv[1])
    client = PaperclipAskClient(
        cfg["base_url"], cfg["company_id"], cfg["agent_id"],
        hmac_key_path=cfg["hmac_key_path"], timeout_seconds=10.0)
    try:
        client.append_ask_event(cfg["ask_id"], cfg["event"])
    except Exception as exc:                    # reported, never retried
        print(json.dumps({"ok": False,
                          "code": str(getattr(exc, "code", type(exc).__name__))}),
              flush=True)
        return 1
    print(json.dumps({"ok": True}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
