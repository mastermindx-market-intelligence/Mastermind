"""Current receiver policy over an exact canonical accepted subscription grant."""
from dataclasses import dataclass
import hashlib
import json

from .installed import _principal
from .reply_policy_selection import ReplyPolicySelection, ReplyPolicyDenied
from .runtime_reply_authorization import validate_reply_authorization, policy_fingerprint
from .runtime_reply_subscriptions import RuntimeReplySubscriptionStore
from .web_reply_subscription_owner import SubscriptionConflict, owner_key


def authorization_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RetainedReplyAudience:
    subscription_id: str
    version: str
    authorization_digest: str
    owner_key: str
    request_ref: str
    callback_url_digest: str


class ObservedReplyPolicyDenial(ValueError):
    def __init__(self, audience):
        super().__init__("current subscriber policy denied")
        self.audience = audience


class RuntimeReplyAuthorizationOwner:
    def __init__(self, store, policies, *, clock):
        if (type(store) is not RuntimeReplySubscriptionStore
                or not isinstance(policies, ReplyPolicySelection) or not callable(clock)):
            raise TypeError("canonical subscription and actual receiver policy owners required")
        self.store, self.policies, self.clock = store, policies, clock

    def capture(self, subscription_id):
        snapshot, value = self.store.accepted_authorization(subscription_id)
        record = snapshot.record
        audience = RetainedReplyAudience(subscription_id,snapshot.version,authorization_digest(value),
            record.owner_key,record.request_ref,record.callback_url_digest)
        self.current(audience)
        return audience

    def current(self, audience):
        if type(audience) is not RetainedReplyAudience:
            raise ValueError("canonical accepted audience required")
        snapshot, value = self.store.accepted_authorization(audience.subscription_id,
            expected_version=audience.version)
        record = snapshot.record
        if (authorization_digest(value) != audience.authorization_digest
                or (record.owner_key,record.request_ref,record.callback_url_digest) !=
                   (audience.owner_key,audience.request_ref,audience.callback_url_digest)):
            raise SubscriptionConflict("accepted audience changed")
        source = _principal(value["principal"])
        try:
            policy = self.policies.select(source)
            if policy_fingerprint(policy) != value["source_policy_sha256"]:
                raise ReplyPolicyDenied("validated receiver policy changed")
        except ReplyPolicyDenied:
            raise ObservedReplyPolicyDenial(audience) from None
        projection = validate_reply_authorization(value,policy,now=self.clock())
        if (owner_key(projection) != record.owner_key or value["request_ref"] != record.request_ref
                or value["read_ref"] != record.read_ref or value["expires_at"] != record.expires_at):
            raise ValueError("bounded audience differs from accepted subscription")
        from control_plane.native_continuation import stored_continuation_request, _digest
        event, _ = stored_continuation_request(self.store._runtime,record.read_ref)
        if event.command_id != record.request_ref or _digest(event.to_dict()) != value["request_event_sha256"]:
            raise ValueError("original request provenance changed")
        return projection

    async def revoke_observed(self, denial):
        if type(denial) is not ObservedReplyPolicyDenial:
            raise TypeError("actual observed policy denial required")
        a = denial.audience
        try:
            await self.store.remove(a.subscription_id,a.owner_key,request_ref=a.request_ref,
                callback_url_digest=a.callback_url_digest,expected_version=a.version)
        except SubscriptionConflict:
            return False  # A newer authenticated grant/revoke stays authoritative.
        return True
