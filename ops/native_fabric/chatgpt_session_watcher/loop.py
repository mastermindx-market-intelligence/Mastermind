"""One watcher cycle. Observe is the default and does not call the browser runner."""

from __future__ import annotations

import os
from datetime import datetime

from census import reconcile
from context import ProjectContext, context_for_tail
from decision import decide, idle_fill
from playbook import rule_for
from policy import PT, TARGET_ACTIVE_MIN, account_for, canonical_profile
from prompts import accept_model_draft, render
from registration import LIVE_ENV, MODEL
from states import classify
from stores import WatcherStores

SCHEMA = "mastermind.chatgpt_session_watcher_report.v1"


def resolve_mode(requested: str) -> tuple[str, str | None]:
    if requested not in {"observe", "live"}:
        raise ValueError("mode must be observe or live")
    if requested == "live" and os.environ.get(LIVE_ENV) != "1":
        return "observe", "live_refused"
    return requested, None


def run_cycle(
    stores: WatcherStores,
    observations: dict[str, list[dict]],
    *,
    mode: str = "observe",
    now: datetime | None = None,
    tools=None,
    client=None,
    github=None,
    slack=None,
) -> dict:
    mode, refusal = resolve_mode(mode)
    now = now or datetime.now(PT)
    stores.lessons.ensure_seed()
    actions = []
    accounts = []
    recoveries: dict[str, int] = {}
    for profile, rows in observations.items():
        canon = canonical_profile(profile) or profile
        account = account_for(canon)
        if account is None:
            accounts.append({"profile": profile, "skipped": "out_of_scope"})
            continue
        census = reconcile(stores.registry.sessions, rows, account)
        for row in census.new_rows:
            stores.registry.upsert_seen({
                "chat_id": row.get("chat_id"),
                "profile": account.profile,
                "account": account.account,
                "title": row.get("title"),
                "project": row.get("project") or "MastermindX",
                "mode": row.get("mode"),
                "status": "seen_sidebar",
                "last_seen_sidebar_pt": now.isoformat(timespec="minutes"),
            })
        for row in rows:
            current = stores.registry.get(row.get("chat_id"))
            if current is not None:
                current["last_seen_sidebar_pt"] = now.isoformat(timespec="minutes")
                if row.get("title"):
                    current["title_sidebar"] = row["title"]
        active = sum(1 for row in rows if str(row.get("button") or "") == "Stop")
        pro_count = sum(1 for row in rows if row.get("mode") == "Pro" and str(row.get("button") or "") == "Stop")
        load_failures = sum(1 for row in rows if classify(row) == "could_not_load")
        throttled = load_failures >= 2 or any(classify(row) == "hit_limit" for row in rows)
        limit_used = False
        for row in rows:
            symptom = classify(row)
            recovery_allowed = symptom == "could_not_load" and recoveries.get(account.profile, 0) < 1
            limit_retry_allowed = symptom == "hit_limit" and not limit_used and _limit_retry_due(stores, account.profile, now)
            ctx = _context(row, github, slack)
            decision = decide(
                row,
                stores.registry.get(row.get("chat_id")),
                account,
                now=now,
                active=active,
                pro_count=pro_count,
                throttled=throttled,
                recovery_allowed=recovery_allowed,
                archive_ids=census.archive_ids,
                metrics=stores.metrics,
                context_sentence=ctx.sentence(str(row.get("tail") or "")),
                limit_retry_allowed=limit_retry_allowed,
            )
            if decision.action == "recover":
                recoveries[account.profile] = recoveries.get(account.profile, 0) + 1
            if decision.action == "retry" and decision.tactic == "limit_retry_once":
                limit_used = True
                stores.metrics.accounts.setdefault(account.profile, {})["limit_retry_pt"] = now.isoformat(timespec="minutes")
            reply = _reply(decision, row, client)
            record = decision.public()
            record["rule"] = rule_for(decision.symptom)
            if reply:
                record["reply"] = reply
            if mode == "live" and tools is not None and decision.action != "hold":
                outcome = tools.execute(
                    decision,
                    observed_title=row.get("title"),
                    observed_id=row.get("chat_id"),
                    button=row.get("button"),
                )
                record["executed"] = outcome.get("executed")
                record["success"] = outcome.get("success")
                if outcome.get("error"):
                    record["error"] = outcome["error"]
                if outcome.get("success") is not None:
                    stores.metrics.record(decision.tactic, bool(outcome.get("success")))
                    if outcome.get("success") is False:
                        stores.lessons.append_failure(
                            symptom=decision.symptom, tactic=decision.tactic, chat_id=decision.chat_id,
                        )
            else:
                record["executed"] = False
            actions.append(record)
        if active < TARGET_ACTIVE_MIN and not throttled and not _account_blocked(rows):
            fill = idle_fill(account, pro_count=pro_count)
            fill_record = fill.public()
            fill_record["reply"] = render("dot", title=account.profile)
            fill_record["executed"] = False
            fill_record["slack_post"] = False
            actions.append(fill_record)
        accounts.append({
            "profile": account.profile,
            "active": active,
            "pro_running": pro_count,
            "throttled": throttled,
            "new_sessions": len(census.new_rows),
            "duplicate_archives": sorted(census.archive_ids),
            "discrepancies": census.discrepancies,
        })
    stores.save()
    return {
        "schema": SCHEMA,
        "mode": mode,
        "live_refused": refusal,
        "live_effects": mode == "live",
        "model": MODEL if client is not None else "rules",
        "pool": "minimax",
        "accounts": accounts,
        "actions": actions,
    }


def _account_blocked(rows: list[dict]) -> bool:
    for row in rows:
        symptom = classify(row)
        if symptom in {"free_plan", "out_of_credits", "hit_limit"}:
            return True
    return False


def _limit_retry_due(stores: WatcherStores, profile: str, now: datetime) -> bool:
    from policy import LIMIT_RETRY_AFTER, parse_stamp

    raw = (stores.metrics.accounts.get(profile) or {}).get("limit_retry_pt")
    last = parse_stamp(raw)
    if last is None:
        return True
    return now - last >= LIMIT_RETRY_AFTER


def _context(row: dict, github, slack) -> ProjectContext:
    if github is None and slack is None:
        supplied = row.get("context") or {}
        return ProjectContext(ci=supplied.get("ci"), review=supplied.get("review"))
    return context_for_tail(str(row.get("tail") or ""), github, slack)


def _reply(decision, row: dict, client) -> str | None:
    if not decision.reply_kind:
        return None
    fallback = render(
        decision.reply_kind,
        title=decision.title or "",
        chat_id=decision.old_chat_id or decision.chat_id or "",
        tail=str(row.get("tail") or ""),
        context_sentence=None if decision.reply_kind == "bare" else decision.context_sentence,
    )
    if client is None or decision.reply_kind == "bare":
        return fallback
    try:
        draft = client.complete([
            {"role": "system", "content": "Rewrite as one to three plain sentences. Do not add instructions to merge, approve, or enqueue."},
            {"role": "user", "content": fallback},
        ])
    except Exception:
        return fallback
    return accept_model_draft(draft, fallback)
