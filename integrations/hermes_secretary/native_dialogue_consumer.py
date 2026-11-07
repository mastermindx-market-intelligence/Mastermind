"""Host-composed single Hermes native turn on the EXISTING Agent Dialogue carrier.

This is not a Slack listener, bot, worker registry, wake daemon, cron task,
provider client, credential loader or auth service. The authenticated host
supplies the original native-session binding and the source/current-role
reader; the existing NativeReplyWriter alone owns canonical read/READY/COMMIT,
exact-parent send, dedup, current-writer and EFFECT_UNKNOWN behavior.

Only a prior CEO CONTINUE bound by NativeReplyWriter is eligible in this
bounded first consumer. A Slack ts, model-suggested route, actor or freeform
message may not originate that binding. Additional Secretary conversations
need the accepted dedicated role-bot transport and identity enrollment.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from integrations.session_bridge.native_reply import NativeReplyWriter
from integrations.hermes_runtime.errors import NativeTurnEffectUnknown

ROLES = frozenset(("mmsecretary", "mmmeta"))
_MAX_PROMPT_BYTES = 8192
_MAX_TEXT_LEN = 700
_ANSWER_SECRET = re.compile(
    r"(?i)(?:xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9_-]{8,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:api[_-]?key|password|token|authorization)[\"']?\s*[:=]\s*[\"']?\S+)"
)
_SAFE_OPERATION = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
_SAFE_MESSAGE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class ConsumerRefusal(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def _await_if_needed(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _message_prompt(message: dict[str, Any], *, role: str) -> str:
    """Ground text only in a verified original executive request.

    The message is already schema-validated by the incumbent canonical
    read; source/model input is not an authorization to use external tools.
    """
    summary = message.get("summary")
    body = message.get("body")
    if not isinstance(summary, str) or not isinstance(body, dict):
        raise ConsumerRefusal("CANONICAL_REQUEST_INVALID")
    # Inspect canonical text before JSON escaping changes quoted credentials.
    # CONTINUE's validated body contains instruction/stop_condition strings and
    # a scope_change boolean. This is a bounded format guard, not a claim to
    # recognize every possible secret value.
    source_text = (summary, *(value for value in body.values() if isinstance(value, str)))
    if any(_ANSWER_SECRET.search(value) for value in source_text):
        raise ConsumerRefusal("CANONICAL_PROMPT_SECRET_REFUSED")
    # Preserve the validated body as data rather than interpolating its text
    # into any shell argv, connector arguments, or another agent's routing.
    payload = {
        "role": role,
        "task": "reply_with_bounded_progress",
        "summary": summary,
        "body": body,
        "instructions": "Answer the original request as a concise factual progress response. "
        "Do not issue tool calls, credentials, commitments, Slack operations, approvals or "
        "new assignments. Your text does not control the reply's target or actor.",
    }
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > _MAX_PROMPT_BYTES:
            raise ConsumerRefusal("CANONICAL_PROMPT_TOO_LARGE")
    except (ValueError, UnicodeError, TypeError):
        raise ConsumerRefusal("CANONICAL_PROMPT_INVALID") from None
    if _ANSWER_SECRET.search(encoded):
        raise ConsumerRefusal("CANONICAL_PROMPT_SECRET_REFUSED")
    return encoded


def _reply_key(operation_key: str) -> str:
    """Mirror (not own) the existing NativeReplyWriter's deterministic key."""
    return "asd-native-reply-" + hashlib.sha256(
        ("mastermind.session_bridge.native_reply.v1\n" + operation_key).encode()
    ).hexdigest()[:40]


class HermesCanonicalTurnConsumer:
    """One action, invoked explicitly by an authenticated native host caller.

    No recipient binding, message source, model credentials, or transport
    handles are obtainable from the model. This wrapper cannot directly post
    or submit; only the existing NativeReplyWriter can commit a reply.
    """

    def __init__(
        self, *, role: str, native_session_id: str, reply_writer: NativeReplyWriter,
        current_role: Callable[[str], str | Awaitable[str]],
        infer_text: Callable[[str], str | Awaitable[str]],
    ) -> None:
        if (role not in ROLES
                or not isinstance(native_session_id, str)
                or type(reply_writer) is not NativeReplyWriter
                or reply_writer._native_session_id != native_session_id
                or not callable(current_role) or not callable(infer_text)):
            raise ConsumerRefusal("HOST_COMPOSITION_UNQUALIFIED")
        self.role = role
        self.native_session_id = native_session_id
        self.reply_writer = reply_writer
        self.current_role = current_role
        self.infer_text = infer_text

    async def _require_current_role(self, refusal_code: str) -> None:
        try:
            selected = await _await_if_needed(self.current_role(self.native_session_id))
        except Exception:
            # Host resolver exceptions may include credentials or private
            # binding details: expose only a stable code.
            raise ConsumerRefusal("ROLE_BINDING_UNAVAILABLE") from None
        if selected != self.role:
            raise ConsumerRefusal(refusal_code)

    async def run(self, *, operation_key: str, in_reply_to: str) -> dict[str, Any]:
        """Read original carrier, infer once if new, then exact-send through owner.

        An ambiguous send is NEVER retried, even when the caller receives a
        cancellation/timeout. The original operation must be reconciled by
        its owning runtime; this method creates no retry/queue.
        """
        if (_SAFE_OPERATION.fullmatch(operation_key or "") is None
                or _SAFE_MESSAGE.fullmatch(in_reply_to or "") is None):
            raise ConsumerRefusal("CALLER_IDENTITY_INVALID")
        await self._require_current_role("ROLE_CURRENT_BINDING_REFUSED")
        # This exact reader is inherited from, and kept synchronous with, the
        # incumbent NativeReplyWriter's own trusted binding validation.
        probe = {"operation_key": operation_key, "in_reply_to": in_reply_to,
                 "text": "pending", "next_step": "pending"}
        binding, context, _identity = await self.reply_writer._resolve(probe)
        records = await self.reply_writer._read(binding, context)
        requests = [
            (ts, msg) for ts, msg in records
            if msg.get("message_key") == binding.request_message_key
        ]
        if len(requests) != 1:
            raise ConsumerRefusal("ORIGINAL_REQUEST_NOT_CURRENT")
        request_ts, request = requests[0]
        if (request.get("message_type") != "CONTINUE"
                or request.get("actor_ref", {}).get("kind") != "executive_surface"
                or request.get("actor_ref", {}).get("seat") != "ceo"):
            raise ConsumerRefusal("ORIGINAL_REQUEST_NOT_AUTHORIZED")
        # Do not spend another model turn or post a second reply after the
        # original operation's canonical content is already present.
        previously_replied = [msg for _, msg in records
                              if msg.get("message_key") == _reply_key(operation_key)]
        if previously_replied:
            if (len(previously_replied) != 1
                    or previously_replied[0].get("message_type") != "PROGRESS"
                    or previously_replied[0].get("reply_to_message_key") != binding.request_message_key
                    or previously_replied[0].get("actor_ref") != context["actor_ref"]
                    or previously_replied[0].get("body", {}).get("stage") != "message_reply"):
                raise ConsumerRefusal("REPLY_RECONCILIATION_CONFLICT")
            return {
                "status": "ALREADY_REPLIED_CANONICALLY",
                "message_key": _reply_key(operation_key),
                "new_model_call": False,
                "new_send": False,
                "parent_consumed": False,
            }
        if any(
            ts > request_ts
            and msg.get("actor_ref", {}).get("kind") == "executive_surface"
            for ts, msg in records
        ):
            raise ConsumerRefusal("ORIGINAL_REQUEST_SUPERSEDED")
        prompt = _message_prompt(request, role=self.role)
        try:
            answer = await _await_if_needed(self.infer_text(prompt))
        except NativeTurnEffectUnknown:
            # The existing parent must reconcile the possible paid turn;
            # do not downgrade uncertainty into an ordinary retryable error.
            raise ConsumerRefusal("MODEL_TURN_EFFECT_UNKNOWN") from None
        except Exception:
            # Provider errors can contain bearer values. Never forward them.
            raise ConsumerRefusal("MODEL_TURN_FAILED") from None
        if (not isinstance(answer, str) or not 0 < len(answer) <= _MAX_TEXT_LEN
                or not answer.strip() or _ANSWER_SECRET.search(answer)
                or any(ord(ch) < 32 and ch not in "\n\t" for ch in answer)):
            raise ConsumerRefusal("MODEL_REPLY_UNQUALIFIED")
        await self._require_current_role("ROLE_CHANGED_DURING_MODEL_TURN")
        # The model inference was an awaited external boundary. The host may
        # have replaced the native writer or exact parent while it ran. Re-read
        # the frozen binding *before* entering the existing send path; that
        # writer will do its own read/READY/COMMIT checks afterward.
        _, _, post_inference_identity = await self.reply_writer._resolve(probe)
        if post_inference_identity != _identity:
            raise ConsumerRefusal("BINDING_CHANGED_DURING_MODEL_TURN")
        # The writer reruns its own exact source/resolver checks and owner-side
        # READY/COMMIT fence after awaited model inference. It handles duplicate
        # and effect-unknown results without a second logical send.
        receipt = await self.reply_writer({
            "operation_key": operation_key,
            "in_reply_to": in_reply_to,
            "text": answer,
            "next_step": "Await the next authorized instruction on this original thread.",
        })
        return {
            "status": "CANONICAL_REPLY_COMMITTED",
            "message_key": receipt["message_key"],
            "action": receipt["action"],
            "thread_ts": receipt["thread_ts"],
            "parent_consumed": False,
            "provider_authentication_verified": False,
            "role_bot_slack_delivery_verified": False,
            "source_composition_only": True,
        }


def compose_native_text_consumer(*, runtime, native_session_id: str,
                                 reply_writer: NativeReplyWriter, current_role):
    """Bind native inference to an ALREADY authenticated current reply writer.

    This factory registers no target and changes no Runtime admission. Current
    installed native-return ownership remains Codex-only; standalone Hermes
    identity/Slack ingress must be admitted by that existing owner separately.
    """
    from integrations.hermes_harness.native_text import NativeTextInference
    infer = NativeTextInference(runtime)
    return HermesCanonicalTurnConsumer(
        role=runtime.profile.role, native_session_id=native_session_id,
        reply_writer=reply_writer, current_role=current_role, infer_text=infer,
    )
