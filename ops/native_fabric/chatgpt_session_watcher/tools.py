"""Browser tool plans. Observe mode records the plan. Live mode runs the gwcap hooks.

Focus-taking clicks (peekaboo) are gated on real user-idle time and the window title.
AppleScript and JXA hooks do not take focus. Sends are paste, never typed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from decision import Decision
from policy import PolicyRefusal, assert_safe_argv, human_is_active, redact

HOOK_NAMES = {
    "census": "census.js",
    "expand": "expand.js",
    "read": "vmain.js",
    "send_extra_high": "jsend.sh",
    "navigate": "jnav.sh",
    "search": "vt.sh",
}

FOREGROUND_ACTIONS = frozenset({"wait_page"})
PASTE_ACTIONS = frozenset({"paste_send", "request_handoff", "idle_fill"})


class ToolError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _hooks_dir() -> Path:
    return Path(__file__).resolve().parent / "hooks" / "gwcap"


class BrowserTools:
    def __init__(self, *, mode: str = "observe", hooks: Path | None = None, idle_seconds=None, seconds_since_own_input=None, runner=None):
        self.mode = mode
        self.hooks = hooks or _hooks_dir()
        self.idle_seconds = idle_seconds or (lambda: 60.0)
        self.seconds_since_own_input = seconds_since_own_input or (lambda: None)
        self._runner = runner
        self.planned: list[dict] = []

    def census_plan(self, profile: str) -> list[str]:
        """Sidebar census only: expand, See more, read rows, search buried chats. No URLs."""
        return ["expand_project", "see_more", "read_sidebar", "search_buried", profile]

    def plan(self, decision: Decision, *, observed_title: str | None = None, observed_id: str | None = None, button: str | None = None) -> list[list[str]]:
        if decision.action in {"hold", "archive"} and decision.action == "hold":
            return []
        argv_sets: list[list[str]] = []
        if decision.action == "approve_card":
            argv_sets.append(self._allow_argv(decision))
        elif decision.action == "retry":
            argv_sets.append(["hook", "retry.js", decision.profile, decision.chat_id or ""])
        elif decision.action == "wait_page":
            argv_sets.append(["peekaboo", "click", "Wait", "--window-title", observed_title or decision.title or ""])
        elif decision.action == "reload_tab":
            argv_sets.append(["hook", "reload_tab", decision.profile])
        elif decision.action == "archive":
            argv_sets.append(["hook", "archive.js", decision.profile, decision.chat_id or ""])
        elif decision.action == "stop_and_resume":
            argv_sets.append(["hook", "stop.js", decision.profile, decision.title or ""])
            if button != "Stop":
                argv_sets.append(self._send_argv(decision))
        elif decision.action in PASTE_ACTIONS or decision.action == "switch_extra_high":
            if decision.action == "switch_extra_high":
                argv_sets.append(["hook", "effort.js", decision.profile, "Extra High"])
            argv_sets.append(self._send_argv(decision))
        elif decision.action == "recover":
            argv_sets.append(["hook", "project_home", decision.profile])
            argv_sets.append(self._send_argv(decision))
        for argv in argv_sets:
            assert_safe_argv(argv)
        if decision.action in PASTE_ACTIONS or decision.action in {"stop_and_resume", "recover", "switch_extra_high"}:
            self._require_identity(decision, observed_title, observed_id, button)
        return argv_sets

    def _require_identity(self, decision: Decision, observed_title: str | None, observed_id: str | None, button: str | None) -> None:
        if observed_title is not None and decision.title and observed_title != decision.title:
            raise ToolError("title_mismatch")
        if observed_id is not None and decision.chat_id and observed_id != decision.chat_id:
            raise ToolError("id_mismatch")
        # Stop first. The paste is a second call after the button is no longer Stop.
        if decision.action == "stop_and_resume" and button == "Stop":
            return
        if decision.mode_target == "Pro" and button == "Stop" and decision.action in PASTE_ACTIONS:
            raise ToolError("running_pro")

    def _send_argv(self, decision: Decision) -> list[str]:
        if decision.mode_target == "Extra High":
            script = "jsend.sh"
        else:
            script = "send_keep_pro.js"
        return ["hook", script, decision.profile, decision.title or "", "paste"]

    def _allow_argv(self, decision: Decision) -> list[str]:
        label = {
            "allow_once": "Allow once",
            "allow_conversation": "Allow for this conversation",
            "always_allow": "Always allow",
            "deny": "Deny",
            "see_details": "See details",
        }.get(decision.card_choice or "", "")
        if not label:
            raise ToolError("card_choice")
        return ["hook", "allow_card.js", decision.profile, decision.title or "", label]

    def execute(self, decision: Decision, *, observed_title: str | None = None, observed_id: str | None = None, button: str | None = None) -> dict:
        try:
            argvs = self.plan(decision, observed_title=observed_title, observed_id=observed_id, button=button)
        except (ToolError, PolicyRefusal) as exc:
            result = {"executed": False, "success": False, "error": exc.code, "action": decision.action}
            self.planned.append(result)
            return result
        if decision.action in FOREGROUND_ACTIONS and human_is_active(self.idle_seconds(), self.seconds_since_own_input()):
            result = {"executed": False, "success": False, "error": "user_active", "action": decision.action}
            self.planned.append(result)
            return result
        if self.mode != "live":
            result = {"executed": False, "success": None, "planned": argvs, "action": decision.action}
            self.planned.append(result)
            return result
        outputs = []
        for argv in argvs:
            if self._runner is None:
                raise ToolError("no_runner")
            completed = self._runner(argv)
            outputs.append(redact(completed if isinstance(completed, str) else str(completed)))
        result = {"executed": True, "success": True, "output": outputs, "action": decision.action}
        self.planned.append(result)
        return result


def default_runner(argv: list[str]) -> str:
    assert_safe_argv(argv)
    completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=30)
    return redact(completed.stdout)
