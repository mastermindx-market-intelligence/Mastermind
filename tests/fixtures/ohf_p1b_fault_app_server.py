"""Bounded P1B fault wrapper around the frozen P0 App Server double."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from scripts.ohf.fake_app_server import FakeAppServer


class FaultAppServer(FakeAppServer):
    def __init__(self) -> None:
        super().__init__()
        if os.environ.get("OHF_FAKE_SPAWN_DESCENDANT") == "1":
            ready_file = os.environ.get("OHF_FAKE_CHILD_READY_FILE")
            ready_expression = (
                f"pathlib.Path({ready_file!r}).write_text('ready')"
                if ready_file
                else "None"
            )
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib,signal,time; "
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                        f"{ready_expression}; "
                        "time.sleep(600)"
                    ),
                ]
            )
            child_pid_file = os.environ.get("OHF_FAKE_CHILD_PID_FILE")
            if child_pid_file:
                Path(child_pid_file).write_text(str(child.pid), encoding="utf-8")

    def handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if method == "thread/turns/list" and os.environ.get(
            "OHF_FAKE_SECRET_CANDIDATE"
        ):
            thread = self._require_thread(str(params.get("threadId") or ""))
            if thread is None:
                self._error(request_id, "native session reference missing", code=-32004)
                return
            secret = os.environ["OHF_FAKE_SECRET_CANDIDATE"]
            rows = list(thread.get("turns") or [])
            if rows:
                rows[-1] = {
                    **rows[-1],
                    "text": secret,
                    "items": [
                        {
                            "type": "agentMessage",
                            "text": secret,
                            "content": [{"type": "text", "text": secret}],
                        }
                    ],
                }
            self._ok(request_id, {"data": rows, "nextCursor": None})
            return
        if (
            method == "turn/start"
            and os.environ.get("OHF_FAKE_DELAY_COMPLETION") == "1"
        ):
            thread_id = str(params.get("threadId") or "")
            thread = self._require_thread(thread_id)
            if thread is None:
                self._error(request_id, "native session reference missing", code=-32004)
                return
            turn_id = f"turn_delayed_{uuid.uuid4().hex[:8]}"
            thread.setdefault("turns", []).append(
                {"id": turn_id, "text": "interrupted candidate", "items": []}
            )
            self._save()
            self._delayed_turn = (thread_id, turn_id)
            self._ok(
                request_id,
                {
                    "turn": {
                        "id": turn_id,
                        "status": "inProgress",
                        "threadId": thread_id,
                    }
                },
            )
            self._notify("turn/started", {"turn": {"id": turn_id}})
            return
        if (
            method == "turn/interrupt"
            and os.environ.get("OHF_FAKE_DELAY_COMPLETION") == "1"
        ):
            thread_id, turn_id = getattr(self, "_delayed_turn", (None, None))
            if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                self._error(request_id, "native session reference missing", code=-32004)
                return
            self._ok(request_id, {})
            self._notify(
                "turn/completed",
                {
                    "turn": {
                        "id": turn_id,
                        "status": "interrupted",
                        "threadId": thread_id,
                    }
                },
            )
            return
        if method == "turn/start" and os.environ.get("OHF_FAKE_RATE_LIMIT") == "1":
            self._error(request_id, "rate limit exceeded", code=-32029)
            return
        if (
            method == "thread/resume"
            and os.environ.get("OHF_FAKE_RESUME_MISMATCH") == "1"
        ):
            requested_id = str(params.get("threadId") or "")
            if self._require_thread(requested_id) is None:
                self._error(
                    request_id,
                    f"native session reference missing: {requested_id}",
                    code=-32004,
                )
                return
            child_id = f"thr_mismatch_{uuid.uuid4().hex[:8]}"
            child = {
                "id": child_id,
                "session_id": child_id,
                "model": self.model,
                "cwd": str(self.workspace),
                "turns": [],
            }
            self.threads[child_id] = child
            self._save()
            view = self._thread_view(child)
            self._ok(request_id, {"thread": view, "instructionSources": []})
            self._notify("thread/started", {"thread": view})
            return
        super().handle(message)


if __name__ == "__main__":
    raise SystemExit(FaultAppServer().serve())
