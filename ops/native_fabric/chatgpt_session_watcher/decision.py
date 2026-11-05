"""Choose one action from the playbook rules, the registry, and tactic metrics.

The model is not consulted here. Reply text is rendered later and checked by policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from policy import (
    TARGET_ACTIVE_MAX,
    Account,
    card_choice,
    cooloff_active,
    is_chris_own,
    is_flovia,
    is_held,
    next_numbered_title,
    other_account,
)
from states import classify


@dataclass
class Decision:
    profile: str
    action: str
    tactic: str
    symptom: str
    chat_id: str | None = None
    title: str | None = None
    reply_kind: str | None = None
    context_sentence: str | None = None
    card_choice: str | None = None
    hold_reason: str | None = None
    successor_title: str | None = None
    mode_target: str | None = None
    old_chat_id: str | None = None

    def public(self) -> dict:
        payload = asdict(self)
        payload.pop("context_sentence", None)
        return {key: value for key, value in payload.items() if value is not None}


def _base(account: Account, obs: dict, symptom: str, action: str, tactic: str, **kwargs) -> Decision:
    return Decision(
        profile=account.profile,
        chat_id=obs.get("chat_id"),
        title=obs.get("title"),
        action=action,
        tactic=tactic,
        symptom=symptom,
        **kwargs,
    )


def decide(
    obs: dict,
    entry: dict | None,
    account: Account,
    *,
    now: datetime,
    active: int,
    pro_count: int,
    throttled: bool,
    recovery_allowed: bool,
    archive_ids: set[str],
    metrics,
    context_sentence: str | None = None,
    limit_retry_allowed: bool = False,
) -> Decision:
    symptom = classify(obs)
    mode = str(obs.get("mode") or (entry or {}).get("mode") or "")
    if is_flovia(entry, obs):
        return _base(account, obs, symptom, "hold", "never_touch", hold_reason="flovia_or_personal")
    held = is_held(entry)
    if held:
        return _base(account, obs, symptom, "hold", held, hold_reason=held)
    badge = str(obs.get("account_badge") or "")
    if other_account(badge, account):
        return _base(account, obs, "wrong_account", "hold", "wrong_account", hold_reason="wrong_account")
    if symptom == "free_plan":
        return _base(account, obs, symptom, "hold", "plan_lapsed", hold_reason="plan_lapsed")
    if symptom == "out_of_credits":
        return _base(account, obs, symptom, "hold", "report_credits", hold_reason="out_of_credits")
    if obs.get("debugging_banner"):
        return _base(account, obs, symptom, "hold", "debugging_banner", hold_reason="debugging_banner")

    if is_chris_own(entry):
        return _chris_own(account, obs, entry, symptom, mode, now)

    if symptom == "hit_limit":
        if limit_retry_allowed:
            return _base(account, obs, symptom, "retry", "limit_retry_once")
        return _base(account, obs, symptom, "hold", "account_limit", hold_reason="hit_limit")

    chat_id = str(obs.get("chat_id") or "")
    if chat_id and chat_id in archive_ids:
        return _base(account, obs, "duplicate_chain", "archive", "archive_duplicate")

    if (entry or {}).get("replaced_by") and str((entry or {}).get("status") or "") not in {"archived", "superseded"}:
        return _base(account, obs, symptom, "archive", "archive_superseded")

    if obs.get("finished") and str((entry or {}).get("status") or "") not in {"archived", "superseded"}:
        return _base(account, obs, symptom, "archive", "archive_finished")

    if symptom == "permission_card":
        choice, reason = card_choice(obs)
        if choice == "hold":
            return _base(account, obs, symptom, "hold", reason, hold_reason=reason)
        return _base(account, obs, symptom, "approve_card", reason, card_choice=choice)

    if symptom == "running":
        tactic = "never_send_running_pro" if mode == "Pro" else "leave_running"
        return _base(account, obs, symptom, "hold", tactic, hold_reason="running")

    if symptom == "connection_interrupted":
        return _base(
            account, obs, symptom, "stop_and_resume", "stop_and_resume",
            reply_kind="interrupted", context_sentence=context_sentence, mode_target=mode or "Pro",
        )

    if symptom == "thinking_failed":
        if mode == "Extra High":
            return _base(account, obs, symptom, "paste_send", "eh_reprompt", reply_kind="continue", mode_target="Extra High")
        return _base(
            account, obs, symptom, "switch_extra_high", "thinking_failed_extra_high",
            reply_kind="thinking_failed", mode_target="Extra High",
        )

    if symptom == "error_in_message_stream":
        tactic = metrics.prefer("resume_continue", ["resume_continue", "retry"])
        if tactic == "retry":
            return _base(account, obs, symptom, "retry", "retry")
        return _base(
            account, obs, symptom, "paste_send", "resume_continue",
            reply_kind="continue", context_sentence=context_sentence, mode_target=mode or "Pro",
        )

    if symptom == "message_delivery_timed_out":
        return _base(account, obs, symptom, "retry", "delivery_retry")

    if symptom == "could_not_load":
        if throttled and not recovery_allowed:
            return _base(account, obs, symptom, "hold", "throttle", hold_reason="throttle")
        if not recovery_allowed:
            return _base(account, obs, symptom, "hold", "recovery_budget", hold_reason="recovery_budget")
        target = "Extra High" if account.surface == "multilogin" and pro_count >= 5 else "Pro"
        if account.tier == "business":
            target = "Extra High"
        return _base(
            account, obs, symptom, "recover", "numbered_successor",
            reply_kind="recover", successor_title=next_numbered_title(str(obs.get("title") or "")),
            mode_target=target, old_chat_id=obs.get("chat_id"),
        )

    if symptom == "maximum_length":
        if (entry or {}).get("handoff_requested"):
            target = "Extra High" if account.tier == "business" or pro_count >= 5 else "Pro"
            return _base(
                account, obs, symptom, "recover", "recover_after_handoff",
                reply_kind="recover", successor_title=next_numbered_title(str(obs.get("title") or "")),
                mode_target=target, old_chat_id=obs.get("chat_id"),
            )
        return _base(account, obs, symptom, "request_handoff", "max_length_handoff", reply_kind="handoff", mode_target="Extra High")

    if symptom == "page_unresponsive":
        if int(obs.get("unresponsive_streak") or 0) >= 3:
            return _base(account, obs, symptom, "hold", "unresponsive_escalation", hold_reason="page_unresponsive")
        return _base(account, obs, symptom, "wait_page", "wait_not_exit")

    if symptom in {"crashed", "inactive_tab"}:
        return _base(account, obs, symptom, "reload_tab", symptom)

    if obs.get("write_blocked"):
        return _base(
            account, obs, "write_tool_blocked", "switch_extra_high", "write_blocked_handoff",
            reply_kind="write_blocked", mode_target="Extra High",
        )

    if symptom == "idle":
        if mode == "Extra High":
            return _base(
                account, obs, symptom, "paste_send", "eh_reprompt",
                reply_kind="continue", context_sentence=context_sentence, mode_target="Extra High",
            )
        if cooloff_active(entry, now, "Pro"):
            return _base(account, obs, symptom, "hold", "pro_cooloff", hold_reason="pro_cooloff")
        if active >= TARGET_ACTIVE_MAX:
            return _base(account, obs, symptom, "hold", "at_active_cap", hold_reason="at_active_cap")
        return _base(
            account, obs, symptom, "paste_send", "pro_continue",
            reply_kind="continue", context_sentence=context_sentence, mode_target="Pro",
        )

    return _base(account, obs, symptom, "hold", "no_rule", hold_reason="no_rule")


def _chris_own(account: Account, obs: dict, entry: dict | None, symptom: str, mode: str, now: datetime) -> Decision:
    if symptom == "permission_card":
        choice, reason = card_choice(obs)
        if choice == "hold":
            return _base(account, obs, symptom, "hold", reason, hold_reason=reason)
        return _base(account, obs, symptom, "approve_card", "chris_own_card", card_choice=choice)
    if symptom in {"message_delivery_timed_out", "error_in_message_stream"}:
        return _base(account, obs, symptom, "retry", "chris_own_retry")
    if symptom == "running":
        return _base(account, obs, symptom, "hold", "never_send_running_pro", hold_reason="running")
    if symptom == "connection_interrupted":
        return _base(account, obs, symptom, "stop_and_resume", "chris_own_unblock", reply_kind="bare", mode_target=mode or "Pro")
    if symptom == "idle":
        if mode != "Extra High" and cooloff_active(entry, now, "Pro"):
            return _base(account, obs, symptom, "hold", "pro_cooloff", hold_reason="pro_cooloff")
        return _base(account, obs, symptom, "paste_send", "chris_own_continue", reply_kind="bare", mode_target=mode or "Pro")
    return _base(account, obs, symptom, "hold", "chris_own_report", hold_reason="chris_own")


def idle_fill(account: Account, *, pro_count: int) -> Decision:
    target = "Extra High"
    if account.tier == "personal_pro" and account.surface == "multilogin" and pro_count >= 5:
        target = "Extra High"
    return Decision(
        profile=account.profile,
        action="idle_fill",
        tactic="dot_ask",
        symptom="idle_account",
        title="MastermindX",
        reply_kind="dot",
        mode_target=target,
    )
