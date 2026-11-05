"""Short continue prompts. One to three plain sentences. Templates win over a model draft that fails the rules."""

from __future__ import annotations

from policy import redact, reply_ok

TEMPLATES = {
    "continue": (
        "Please continue with {title}. Pick up from your latest checkpoint "
        "and carry on with the next most important work."
    ),
    "interrupted": (
        "Please continue with {title}. The last turn stopped after {step}, so pick up from there."
    ),
    "thinking_failed": (
        "Please continue with {title} on Extra High for this turn. "
        "Rebase onto the latest checkpoint and write a short status."
    ),
    "handoff": (
        "Please save a checkpoint and write a short handoff for a new session, "
        "including the branch and the next step."
    ),
    "recover": (
        'Please recover the "{title}" session as it has timed out {chat_id} and continue its project.'
    ),
    "dot": (
        "Please look through the MastermindX project and name one bounded bug fix "
        "that is not already in progress, with the repo and the check that would prove it."
    ),
    "bare": "Please continue.",
    "write_blocked": (
        "Extra High is on so you can keep tool access for {title}. "
        "Save a checkpoint and say if you want a new Pro session later."
    ),
}


def _step(tail: str) -> str:
    text = " ".join((tail or "").split())
    if not text:
        return "the last visible step"
    return text[-80:].strip() or "the last visible step"


def render(kind: str, *, title: str = "", chat_id: str = "", tail: str = "", context_sentence: str | None = None) -> str:
    template = TEMPLATES.get(kind) or TEMPLATES["continue"]
    body = template.format(
        title=(title or "this project").strip(),
        chat_id=(chat_id or "").strip(),
        step=_step(tail),
    )
    if kind == "bare":
        return TEMPLATES["bare"]
    sentence = (context_sentence or "").strip()
    if sentence and kind in {"continue", "interrupted"}:
        if not sentence.endswith("."):
            sentence += "."
        body = f"{body} {sentence}"
    body = redact(body).strip()
    if not reply_ok(body):
        body = TEMPLATES["continue"].format(title=(title or "this project").strip(), chat_id="", step="the last visible step")
    return body


def accept_model_draft(draft: str, fallback: str) -> str:
    cleaned = redact((draft or "").strip())
    if reply_ok(cleaned):
        return cleaned
    return fallback
