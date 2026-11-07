"""Encoded tactics from the operator playbook, plus the lesson seed read on every cycle.

The full playbook lives in knowledge/operator_playbook.md. These records are the
rules the decision loop applies. A reflection pass may propose edits; it does
not rewrite this module.
"""

from __future__ import annotations

from pathlib import Path

KNOWLEDGE = Path(__file__).resolve().parent / "knowledge" / "operator_playbook.md"

# symptom -> the operative rule, kept short so a prompt can cite it.
RULES = {
    "connection_interrupted": "Press Stop, wait until the send button is back, then send one short continue. Do not send while Stop is showing.",
    "error_in_message_stream": "First send a short continue. If that already failed, Retry once. Repeated failure means a handoff, not another marathon prompt.",
    "thinking_failed": "Switch that Pro turn to Extra High, ask for a rebase and a short status, then return to Pro on a later turn.",
    "permission_card": "GitHub writes get Allow once after See details matches. Other cards get Allow for this conversation. Always allow is acceptable on non-write cards. Never press Escape.",
    "could_not_load": "Recover with one numbered successor that names the old conversation id. Do not open the chat URL. Two or more failures mark the account throttled for new fills.",
    "message_delivery_timed_out": "Click Retry once. If the composer is empty and Stop never appears, send the short continue again.",
    "maximum_length": "Ask for a checkpoint and a short handoff. Then start the next numbered chat and archive the old one once the successor is working.",
    "hit_limit": "Stop nudges on that account. Retry one chat after about an hour. If the sidebar says Free, the plan lapsed: tell Chris and do not Retry.",
    "free_plan": "A Free badge means the plan lapsed. Do not Retry, nudge, or launch. Report it.",
    "out_of_credits": "Report the workspace credit banner. Never click auto-reload or paid credits.",
    "page_unresponsive": "Click Wait, never Exit Page. After repeated dialogs, leave the profile for a later run.",
    "crashed": "Reload the existing ChatGPT tab. Do not navigate to a chat URL.",
    "inactive_tab": "Reload the discarded tab in place.",
    "running": "A Stop button means the turn is live. Never send to a running Pro chat.",
    "idle": "Extra High is reprompted when the turn ends. Pro waits about 30 minutes. Keep the reply to one to three sentences.",
    "write_tool_blocked": "Switch the chat to Extra High and ask for a checkpoint. Do not keep spending Pro turns on a blocked writer.",
}

LESSON_SEED = (
    {"id": "escape-denies", "symptom": "permission_card", "fix": "Never press Escape on a card; Escape denies it. Close See details with the dialog X.", "source": "playbook"},
    {"id": "one-tab", "symptom": "census", "fix": "One ChatGPT tab per profile. Move only through the sidebar or Search chats, never by opening a chat URL.", "source": "playbook"},
    {"id": "paste-not-type", "symptom": "send", "fix": "Paste. Never speed-type a prompt.", "source": "playbook"},
    {"id": "running-pro", "symptom": "running", "fix": "Never send to a running Pro chat.", "source": "policy"},
    {"id": "verify-title", "symptom": "send", "fix": "Read the chat title and conversation id immediately before every send and abort on a mismatch.", "source": "playbook"},
    {"id": "github-allow-once", "symptom": "permission_card", "fix": "GitHub write cards get Allow once only after See details matches the tool name.", "source": "policy"},
    {"id": "allow-conversation", "symptom": "permission_card", "fix": "Other cards get Allow for this conversation. Always allow is acceptable there.", "source": "policy"},
    {"id": "do-not-steer", "symptom": "hold", "fix": "Registry do_not_steer, HOLD, and leave_alone are holds. Do not nudge them.", "source": "policy"},
    {"id": "chris-own", "symptom": "chris_own", "fix": "Chris's own chats get only a card, a Retry, or a bare continue.", "source": "policy"},
    {"id": "flovia", "symptom": "hold", "fix": "The Flovia chat and personal chats are never touched.", "source": "policy"},
    {"id": "no-merge", "symptom": "permission_card", "fix": "Never merge, approve, label, enqueue, mark Ready, or self-review.", "source": "policy"},
    {"id": "no-passwords", "symptom": "login", "fix": "Never type an admin or Passwords unlock password, and never click paid credits or auto-reload.", "source": "policy"},
    {"id": "short-continue", "symptom": "idle", "fix": "Continue prompts are one to three plain sentences. No marathon prompts.", "source": "playbook"},
    {"id": "no-secrets", "symptom": "report", "fix": "Never print secrets. On m2, never use pgrep -f/-a or a full ps command line.", "source": "policy"},
    {"id": "pro-cooloff", "symptom": "idle", "fix": "About 30 minutes of cool-off per Pro chat. Extra High is reprompted at turn end.", "source": "playbook"},
    {"id": "pro-cap", "symptom": "census", "fix": "At most about 4-5 Pro chats per Multilogin profile. Target about 7-11 active chats per account, mostly Extra High.", "source": "playbook"},
    {"id": "expand-see-more", "symptom": "census", "fix": "Expand the MastermindX project, press See more, and use Search chats for buried chats.", "source": "playbook"},
    {"id": "duplicate-chain", "symptom": "census", "fix": "Archive a duplicate in a project chain once the numbered successor is working.", "source": "playbook"},
    {"id": "idle-fill", "symptom": "idle", "fix": "An idle account under the active target gets one bounded Extra High ask. Do not post it to Slack from this worker.", "source": "playbook"},
    {"id": "focus-idle", "symptom": "peekaboo", "fix": "Peekaboo and other focus-taking clicks wait for a real idle gap and re-check the window title.", "source": "playbook"},
)


def load_playbook_text() -> str:
    return KNOWLEDGE.read_text(encoding="utf-8")


def rule_for(symptom: str) -> str:
    return RULES.get(symptom, "")
