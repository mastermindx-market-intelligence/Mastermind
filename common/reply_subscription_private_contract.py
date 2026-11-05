"""Neutral event facet on the EXISTING authenticated Executive App peer.

No listener, identity, lifecycle, credential or subscription state is owned here.
"""
from collections.abc import Callable
from dataclasses import dataclass

PRIVATE_SCHEMA = "mastermind.executive_ceo_ingress_reply_events.v1"
RESULT_SCHEMA = "mastermind.executive_ceo_ingress_reply_events_result.v1"
OPERATIONS = ("can_discover", "subscribe", "unsubscribe")
MODIFYING = ("subscribe", "unsubscribe")


def result(operation, *, data=None, code=None):
    return {"schema":RESULT_SCHEMA, "operation":operation, "ok":code is None,
        "data":data if code is None else None, "error":None if code is None else {"code":code}}


@dataclass(frozen=True)
class ReplyEventIngressOwner:
    runtime: object
    validator: Callable
    handler: Callable

    def __post_init__(self):
        if self.runtime is None or not callable(self.validator) or not callable(self.handler):
            raise TypeError("fixed event owner required")

    def validate_frame(self, frame):
        operation = self.validator(frame)
        if type(operation) is not str or operation not in OPERATIONS:
            raise ValueError("invalid event operation")
        return operation

    async def handle_frame(self, frame):
        self.validate_frame(frame)
        return await self.handler(frame)


@dataclass(frozen=True)
class ReplyEventCommitConsumer:
    runtime: object
    handler: Callable

    def __post_init__(self):
        if self.runtime is None or not callable(self.handler):
            raise TypeError("existing Runtime commit consumer required")

    async def handle_committed(self, *, read_ref, message_key, fingerprint):
        return await self.handler(read_ref=read_ref,message_key=message_key,fingerprint=fingerprint)
