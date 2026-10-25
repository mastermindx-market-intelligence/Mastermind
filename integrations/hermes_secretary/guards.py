"""Standing rules from the 2026-10-25 secretary snapshot, as fail-closed guards.

These checks do not post, merge, approve, scrape, or submit Fabric work.
A passing check is permission to record a shadow decision, not to act.
"""

from __future__ import annotations

import re
from typing import Callable


class GuardRefusal(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_SECRET = re.compile(
    r"(xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9]|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:api[_-]?key|password|token)\s*[:=]\s*\S+)"
)
_TOOL = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_VERDICT = re.compile(r"(?m)^VERDICT:\s+(\S+)")
_SWITCH_ORDER = (
    "ChatGPT1",
    "ChatGPT2",
    "ChatGPT2 Business",
    "ChrisWong6031",
    "ChatGPT3",
)
_PACKET = ("parent", "root", "task_class", "complexity", "cwd", "task_text")


class StandingRules:
    def __init__(self, *, shadow_mode: bool = True, voice_rooms: tuple[str, ...] | None = None) -> None:
        from roster import authorized_post_room_ids

        self.shadow_mode = shadow_mode
        self.voice_rooms = (
            authorized_post_room_ids() if voice_rooms is None else tuple(voice_rooms)
        )
        self.hold = False
        self._refusals: dict[str, str] = {}
        self._fabric: dict[str, str] = {}

    def refusal_text(self, chat_id: str) -> str | None:
        return self._refusals.get(chat_id)

    def fabric_state(self, run_id: str) -> str | None:
        return self._fabric.get(run_id)

    def consider(self, action: str, **ctx: object) -> None:
        handler = _ACTIONS.get(action)
        if handler is None:
            raise GuardRefusal("UNKNOWN_ACTION")
        if self.hold and action not in {"chris_wait", "release_wait", "act_during_wait"}:
            raise GuardRefusal("CHRIS_WAIT")
        handler(self, ctx)


def _chris_wait(rules: StandingRules, _ctx: dict) -> None:
    rules.hold = True


def _release_wait(rules: StandingRules, ctx: dict) -> None:
    if ctx.get("authority") != "chris":
        raise GuardRefusal("CHRIS_WAIT")
    rules.hold = False


def _act_during_wait(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("CHRIS_WAIT")


def _github_approve(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("NEVER_APPROVE")


def _github_merge(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("NEVER_MERGE")


def _self_approve(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("NEVER_SELF_APPROVE")


def _approval_card(_rules: StandingRules, ctx: dict) -> None:
    tool = ctx.get("tool")
    choice = ctx.get("choice")
    if not isinstance(tool, str) or _TOOL.fullmatch(tool) is None:
        raise GuardRefusal("APPROVAL_SCOPE")
    if choice != f"Allow {tool} for this conversation":
        raise GuardRefusal("APPROVAL_SCOPE")


def _composer_input(_rules: StandingRules, ctx: dict) -> None:
    if ctx.get("method") != "paste":
        raise GuardRefusal("PASTE_ONLY")


def _message_chat(rules: StandingRules, ctx: dict) -> None:
    status = ctx.get("status")
    if status == "chris_own":
        raise GuardRefusal("CHRIS_OWN")
    if status == "do_not_steer":
        raise GuardRefusal("DO_NOT_STEER")
    if ctx.get("refusal_text") or (
        isinstance(ctx.get("chat_id"), str) and ctx["chat_id"] in rules._refusals
    ):
        raise GuardRefusal("REFUSAL_VERBATIM")
    if ctx.get("state") == "running" and ctx.get("tier") == "pro":
        raise GuardRefusal("RUNNING_PRO")
    if ctx.get("state") == "running":
        raise GuardRefusal("RUNNING_CHAT")
    if ctx.get("waiting_on") in {"ci", "review"}:
        raise GuardRefusal("WAITING_EXTERNAL")
    age = ctx.get("last_nudge_age_min")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age < 30:
        raise GuardRefusal("NUDGE_COOLDOWN")
    if ctx.get("input_method", "paste") != "paste":
        raise GuardRefusal("PASTE_ONLY")


def _record_refusal(rules: StandingRules, ctx: dict) -> None:
    chat_id = ctx.get("chat_id")
    text = ctx.get("text")
    if not isinstance(chat_id, str) or not isinstance(text, str) or text == "":
        raise GuardRefusal("REFUSAL_VERBATIM")
    existing = rules._refusals.get(chat_id)
    if existing is not None and existing != text:
        raise GuardRefusal("REFUSAL_VERBATIM")
    rules._refusals[chat_id] = text


def _replay_refusal(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("REFUSAL_VERBATIM")


def _rewrite_refusal(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("REFUSAL_VERBATIM")


def _retry_refusal(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("REFUSAL_VERBATIM")


def _packet_complete(ctx: dict) -> bool:
    return all(isinstance(ctx.get(key), str) and ctx.get(key) for key in _PACKET)


def _fabric_submit(rules: StandingRules, ctx: dict) -> None:
    run_id = ctx.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise GuardRefusal("FABRIC_ONCE")
    if run_id in rules._fabric:
        raise GuardRefusal("FABRIC_ONCE")
    if not _packet_complete(ctx):
        raise GuardRefusal("PACKET_INCOMPLETE")
    rules._fabric[run_id] = "submitted"


def _fabric_retry(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("FABRIC_ONCE")


def _fabric_uncertain(rules: StandingRules, ctx: dict) -> None:
    run_id = ctx.get("run_id")
    if not isinstance(run_id, str) or run_id not in rules._fabric:
        raise GuardRefusal("FABRIC_UNKNOWN_RUN")
    rules._fabric[run_id] = "uncertain"


def _fabric_status(rules: StandingRules, ctx: dict) -> None:
    run_id = ctx.get("run_id")
    if not isinstance(run_id, str) or run_id not in rules._fabric:
        raise GuardRefusal("FABRIC_UNKNOWN_RUN")


def _scrape(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("NO_SCRAPE")


def _backend_api(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("NO_BACKEND_API")


def _post_secret(_rules: StandingRules, ctx: dict) -> None:
    text = ctx.get("text")
    if isinstance(text, str) and _SECRET.search(text):
        raise GuardRefusal("NO_SECRETS")
    raise GuardRefusal("NO_SECRETS")


def _send_email(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("DRAFT_ONLY")


def _draft_email(_rules: StandingRules, _ctx: dict) -> None:
    return None


def _preauthorized_thread(rules: StandingRules, ctx: dict) -> bool:
    from roster import authorized_reply_kinds

    channel = ctx.get("channel")
    thread_ts = ctx.get("thread_ts")
    kind = ctx.get("kind")
    if len(rules.voice_rooms) != 2 or channel not in rules.voice_rooms:
        return False
    if not isinstance(thread_ts, str) or thread_ts == "":
        return False
    if not isinstance(kind, str) or kind.upper() not in authorized_reply_kinds():
        return False
    return True


def _slack_as_chris(rules: StandingRules, ctx: dict) -> None:
    if not _preauthorized_thread(rules, ctx):
        raise GuardRefusal("DRAFT_ONLY")
    if rules.shadow_mode:
        raise GuardRefusal("SHADOW_NO_POST")


def _slack_post(rules: StandingRules, ctx: dict) -> None:
    if rules.shadow_mode:
        raise GuardRefusal("SHADOW_NO_POST")
    if _preauthorized_thread(rules, ctx):
        return None
    raise GuardRefusal("DRAFT_ONLY")


def _switch_account(_rules: StandingRules, ctx: dict) -> None:
    name = ctx.get("name")
    if name == "ChatGPT4" or name not in _SWITCH_ORDER:
        raise GuardRefusal("NEVER_CHATGPT4")
    if str(ctx.get("status")) == "401":
        raise GuardRefusal("NEVER_401")


def _open_new_tab(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("ONE_TAB")


def _open_by_url(_rules: StandingRules, _ctx: dict) -> None:
    raise GuardRefusal("ONE_TAB")


def _comment_review(_rules: StandingRules, ctx: dict) -> None:
    body = ctx.get("body")
    if not isinstance(body, str):
        raise GuardRefusal("VERDICT_REQUIRED")
    found = _VERDICT.search(body)
    if found is None:
        raise GuardRefusal("VERDICT_REQUIRED")
    verdict = found.group(1).upper()
    if verdict in {"MERGE", "MERGED"}:
        raise GuardRefusal("NEVER_MERGE")
    if verdict in {"APPROVE", "APPROVED", "LGTM"}:
        raise GuardRefusal("NEVER_APPROVE")


_ACTIONS: dict[str, Callable[[StandingRules, dict], None]] = {
    "chris_wait": _chris_wait,
    "release_wait": _release_wait,
    "act_during_wait": _act_during_wait,
    "github_approve": _github_approve,
    "github_merge": _github_merge,
    "self_approve": _self_approve,
    "approval_card": _approval_card,
    "composer_input": _composer_input,
    "message_chat": _message_chat,
    "record_refusal": _record_refusal,
    "replay_refusal": _replay_refusal,
    "rewrite_refusal": _rewrite_refusal,
    "retry_refusal": _retry_refusal,
    "fabric_submit": _fabric_submit,
    "fabric_retry": _fabric_retry,
    "fabric_uncertain": _fabric_uncertain,
    "fabric_status": _fabric_status,
    "scrape_cookies": _scrape,
    "backend_api": _backend_api,
    "post_secret": _post_secret,
    "send_email": _send_email,
    "draft_email": _draft_email,
    "slack_as_chris": _slack_as_chris,
    "slack_post": _slack_post,
    "switch_account": _switch_account,
    "open_chat_new_tab": _open_new_tab,
    "open_chat_by_url": _open_by_url,
    "comment_review": _comment_review,
}
