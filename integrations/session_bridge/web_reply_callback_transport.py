"""One-shot, owner-invoked outbound HTTPS for signed MCP Events callbacks.

No subscription store, callback registry, provider dispatch, retry owner, poller
or credential selector. A current authorized subscription owner invokes this
synchronous effect only on an owned I/O lane after validating current access
and canonical original-request identity. It must reconcile the same operation
if request/response delivery becomes ambiguous: retry is never automatic.

The callback hostname is the authenticated subscription URL; DNS is resolved
per attempt; ALL addresses must be public. Connect to one already checked IP
and use original hostname for TLS SNI, certificate validation and HTTP Host.
No system proxy, redirect following or alternate-address fallback is allowed.

Injections are test seams and never caller-selectable MCP arguments. A real
owner MUST control the resolver, connector, signed packet and transaction.
"""
from __future__ import annotations

import inspect

import base64
import binascii
import dataclasses
import http.client
import json
import ipaddress
import socket
import ssl
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlsplit

from .web_reply_delivery import (
    PreparedReplyWebhook, _EVENT, _SUB, _NONCE,
    _VERIFICATION_ID, _validated_event, classify_reply_webhook_response,
)
from .web_reply_event_rpc import _callback_url


class CallbackDestinationRefused(ValueError):
    """No callback request issued because the destination was unsafe or absent."""


class CallbackEffectUnknown(RuntimeError):
    """The original one-shot callback may have been received; never blind-retry."""


@dataclasses.dataclass(frozen=True, slots=True)
class CallbackHTTPReceipt:
    """Observed HTTP response only, NOT model work or original-parent consumption."""
    status_code: int
    response_body: bytes = dataclasses.field(repr=False)
    response_truncated: bool


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Pin TCP to validated public IP while keeping TLS/Host at original DNS name."""

    def __init__(self, hostname: str, port: int, pinned_ip: str, timeout: int = 7):
        _public_ip(pinned_ip)
        if (type(hostname) is not str or not hostname or type(port) is not int
                or not 1 <= port <= 65535 or type(timeout) is not int
                or not 1 <= timeout <= 10):
            raise CallbackDestinationRefused("invalid TLS peer binding")
        super().__init__(hostname,port,context=ssl.create_default_context(),timeout=timeout)
        self._pinned_ip=pinned_ip

    def connect(self) -> None:
        if self._tunnel_host:
            raise CallbackDestinationRefused("callback proxy tunneling is forbidden")
        # This exact validated IP is dialed, never DNS-resolved again by
        # HTTPConnection or chosen from local/private fallback candidates.
        raw = socket.create_connection((self._pinned_ip,self.port),self.timeout)
        try:
            self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _public_ip(value: Any) -> str:
    if type(value) is not str:
        raise CallbackDestinationRefused("invalid DNS address")
    try:
        ip=ipaddress.ip_address(value)
    except ValueError:
        raise CallbackDestinationRefused("invalid DNS address") from None
    translated = (isinstance(ip, ipaddress.IPv6Address) and (
        ip.ipv4_mapped is not None or ip.sixtofour is not None
        or ip.teredo is not None
        or ip in ipaddress.IPv6Network("64:ff9b::/96")
        or ip in ipaddress.IPv6Network("64:ff9b:1::/48")
    ))
    if not ip.is_global or translated:
        # NAT64 can embed private IPv4 endpoints in a globally routed IPv6
        # address. Never grant public-host permission based on is_global alone.
        raise CallbackDestinationRefused("callback DNS address is not public")
    return str(ip)


def _allowed_addresses(resolved: Any,port: int) -> tuple[str,...]:
    if (type(resolved) not in (list,tuple) or not 1 <= len(resolved) <= 16):
        raise CallbackDestinationRefused("callback DNS set missing or over bound")
    addresses=[]
    for entry in resolved:
        if (type(entry) not in (tuple,list) or len(entry)!=5
                or entry[0] not in (socket.AF_INET,socket.AF_INET6)
                or entry[1] != socket.SOCK_STREAM
                or entry[2] not in (0,socket.IPPROTO_TCP)
                or type(entry[4]) not in (tuple,list)
                or len(entry[4]) < 2 or type(entry[4][1]) is not int
                or entry[4][1] != port):
            raise CallbackDestinationRefused("untrusted callback DNS record")
        if entry[0] == socket.AF_INET6:
            if (len(entry[4])!=4 or entry[4][3] != 0):
                raise CallbackDestinationRefused("scoped IPv6 callback forbidden")
        elif len(entry[4]) != 2:
            raise CallbackDestinationRefused("invalid IPv4 callback record")
        addresses.append(_public_ip(entry[4][0]))
    return tuple(addresses)


def _signed_request_headers(packet: PreparedReplyWebhook, host: str,
                            port: int) -> dict[str,str]:
    if (type(packet) is not PreparedReplyWebhook or type(packet.body) is not bytes
            or not 0 < len(packet.body) <= 8192):
        raise CallbackDestinationRefused("untrusted signed callback payload")
    fixed={"Content-Type","webhook-id","webhook-timestamp",
           "webhook-signature","X-MCP-Subscription-Id"}
    source=packet.headers
    if (not hasattr(source,"items") or set(source)!=fixed
            or any(type(k) is not str or type(v) is not str
                   or any(ord(c) < 32 or ord(c)==127 for c in v)
                   or not v or len(v)>2048 for k,v in source.items())
            or source["Content-Type"] != "application/json"
            or _SUB.fullmatch(source["X-MCP-Subscription-Id"]) is None):
        raise CallbackDestinationRefused("invalid signed callback header")
    try:
        stamp=source["webhook-timestamp"]
        if (not stamp.isascii() or not stamp.isdecimal()
                or str(int(stamp)) != stamp or not 0 < int(stamp) <= 4102444800):
            raise ValueError
        signatures=source["webhook-signature"].split(" ")
        if not 1 <= len(signatures) <= 2 or len(set(signatures)) != len(signatures):
            raise ValueError
        for signature in signatures:
            version,separator,raw=signature.partition(",")
            if version != "v1" or separator != ",":
                raise ValueError
            digest=base64.b64decode(raw,validate=True)
            if len(digest) != 32 or base64.b64encode(digest).decode("ascii") != raw:
                raise ValueError
        def unique_object(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise ValueError("duplicate webhook field")
                result[key]=value
            return result
        parsed=json.loads(packet.body,object_pairs_hook=unique_object)
        if type(parsed) is not dict:
            raise ValueError
        if parsed.get("type") == "verification":
            if (set(parsed) != {"type","challenge"}
                    or type(parsed["challenge"]) is not str
                    or _NONCE.fullmatch(parsed["challenge"]) is None
                    or _VERIFICATION_ID.fullmatch(source["webhook-id"]) is None):
                raise ValueError
            expected=json.dumps(parsed,sort_keys=True,separators=(",",":"),
                                ensure_ascii=True).encode("ascii")
        else:
            data=parsed.get("data")
            if (type(data) is not dict or type(data.get("request_ref")) is not str
                    or _EVENT.fullmatch(source["webhook-id"]) is None
                    or parsed.get("eventId") != source["webhook-id"]):
                raise ValueError
            expected=_validated_event(parsed,data["request_ref"])
        if expected != packet.body:
            raise ValueError
    except (ValueError,TypeError,UnicodeError,binascii.Error):
        # Structural integrity is NOT cryptographic HMAC verification. The
        # trusted existing signer still owns key authorization and signing.
        raise CallbackDestinationRefused("inconsistent signed webhook packet") from None
    return {**dict(source),"Host":host if port==http.client.HTTPS_PORT else f"{host}:{port}"}


def send_once(callback_url: str, packet: PreparedReplyWebhook, *,
              resolver: Callable[...,Sequence[Any]] | None=None,
              connector: Callable[...,Any] | None=None,
              timeout_s: int=7, before_request: Callable[[],PreparedReplyWebhook] | None=None) -> CallbackHTTPReceipt:
    """One pinned HTTPS POST, never follow redirects, retry or claim consumption.

    All checks that can refuse a callback precede socket creation. An error
    after attempting the request is EFFECT_UNKNOWN even if an owner-provided
    transport chooses a ValueError exception type. No exception payload or
    response body is logged or added to privileged model context.
    """
    if (type(timeout_s) is not int or not 1<=timeout_s<=10
            or (resolver is not None and not callable(resolver))
            or (connector is not None and not callable(connector))
            or (before_request is not None and (not callable(before_request) or inspect.iscoroutinefunction(before_request)))):
        raise CallbackDestinationRefused("invalid bounded callback dependencies")
    try:
        safe=_callback_url(callback_url)
        parsed=urlsplit(safe)
        host=parsed.hostname
        port=parsed.port or http.client.HTTPS_PORT
        path=parsed.path or "/"
        if parsed.query:
            path+="?"+parsed.query
        headers=_signed_request_headers(packet,host,port)
        answers=(resolver or socket.getaddrinfo)(host,port,type=socket.SOCK_STREAM)
        addresses=_allowed_addresses(answers,port)
    except (OSError,TypeError,ValueError,UnicodeError):
        raise CallbackDestinationRefused("callback destination unavailable") from None
    if before_request is not None:
        refreshed = before_request()
        if type(refreshed) is not PreparedReplyWebhook or refreshed.body != packet.body:
            raise CallbackDestinationRefused("owner fence changed callback event")
        headers = _signed_request_headers(refreshed,host,port)
    # First address only. Do not retry alternate addresses after failed send.
    conn=None
    try:
        conn=(connector or PinnedHTTPSConnection)(host,port,addresses[0],timeout_s)
        conn.request("POST",path,packet.body,headers=headers)
        response=conn.getresponse()
        code=response.status
        if type(code) is not int or not 100<=code<600:
            raise ValueError("invalid callback status")
        body=response.read(513)
        if type(body) is not bytes:
            raise ValueError("invalid callback response body")
        return CallbackHTTPReceipt(code,body,len(body)>512)
    except BaseException as exc:
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):
            raise
        raise CallbackEffectUnknown("original callback outcome unknown") from None
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass


__all__=["CallbackDestinationRefused","CallbackEffectUnknown",
         "CallbackHTTPReceipt","PinnedHTTPSConnection","send_once"]
