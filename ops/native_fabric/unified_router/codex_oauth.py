"""OAuth account handling for credential_pool routes (ChatGPT codex shape).

The unified router composes incumbent capacity owners; it creates no new
credential store. OAuth rows are read live from the Hermes ``credential_pool``
in ``~/.hermes/auth.json`` at request time (the same pattern the Anthropic
OAuth gateway uses). Access tokens are short-lived; refresh tokens are
single-use and rotating, so a refresh always runs inside the incumbent
``auth.json.lock`` with a re-read/merge of exactly one row — if another
writer (Hermes, a sibling gateway) rotated the grant first, its pair is
adopted instead of replaying the consumed token.
"""
from __future__ import annotations

import base64
import fcntl
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


class OAuthPoolError(RuntimeError):
    """Named fail-closed refusal, never permission to change a carrier."""


@dataclass(frozen=True)
class OAuthAccount:
    id: str
    label: str
    access_token: str
    refresh_token: str
    exhausted_until: float = 0.0

    @property
    def exhausted(self) -> bool:
        return self.exhausted_until > time.time()


def _jwt_claim(token: str, claim_path: tuple[str, ...]) -> object | None:
    """One claim from a JWT payload without verifying a signature (local read
    of our own stored token only; never an authentication decision)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    value: object = payload
    for part in claim_path:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def account_id_header(access_token: str) -> dict[str, str]:
    """``ChatGPT-Account-ID`` from the OAuth JWT (canonical codex-rs shape)."""
    claim = _jwt_claim(access_token, ("https://api.openai.com/auth",
                                      "chatgpt_account_id"))
    if isinstance(claim, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", claim):
        return {"ChatGPT-Account-ID": claim}
    return {}


def read_accounts(auth_store: Path, pool: str) -> list[OAuthAccount]:
    """OAuth rows of one credential pool; secret values stay in-process."""
    document = json.loads(auth_store.read_text(encoding="utf-8"))
    entries = (document.get("credential_pool") or {}).get(pool)
    if not isinstance(entries, list):
        raise OAuthPoolError(f"credential_pool.{pool} is not a pool of accounts")
    accounts: list[OAuthAccount] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        access = str(entry.get("access_token") or "")
        refresh = str(entry.get("refresh_token") or "")
        if not access or not refresh:
            continue
        reset = entry.get("last_error_reset_at")
        exhausted_until = float(reset) if isinstance(reset, (int, float)) else 0.0
        if entry.get("last_status") != "exhausted":
            exhausted_until = 0.0
        accounts.append(OAuthAccount(
            id=str(entry.get("id") or entry.get("label") or ""),
            label=str(entry.get("label") or ""),
            access_token=access, refresh_token=refresh,
            exhausted_until=exhausted_until))
    if not accounts:
        raise OAuthPoolError(f"credential_pool.{pool} has no usable OAuth rows")
    return sorted(accounts, key=lambda a: (a.label, a.id))


def bench_row(auth_store: Path, pool: str, account_id: str, *, reset_at: float,
              reason: str) -> None:
    """Record an upstream usage-limit refusal on the incumbent row.

    Mirrors what Hermes itself writes (``last_status``/``last_error_code``/
    ``last_error_reset_at``) so every consumer of the pool sees the same
    bench; the merge is limited to those three fields of exactly one row.
    """
    lock_path = auth_store.parent / "auth.json.lock"
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            document = json.loads(auth_store.read_text(encoding="utf-8"))
            entries = (document.get("credential_pool") or {}).get(pool)
            if isinstance(entries, list):
                for entry in entries:
                    if (isinstance(entry, dict)
                            and str(entry.get("id") or entry.get("label") or "")
                            == account_id):
                        entry["last_status"] = "exhausted"
                        entry["last_error_code"] = 429
                        entry["last_error_reason"] = reason
                        entry["last_error_reset_at"] = reset_at
                        break
                auth_store.write_text(json.dumps(document, indent=2),
                                      encoding="utf-8")
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def refresh_account(auth_store: Path, pool: str, account: OAuthAccount, *,
                    token_url: str, client_id: str,
                    client,
                    timeout_s: float = 20.0) -> OAuthAccount:
    """Spend this row's refresh token; commit the rotated pair under flock.

    The re-read -> endpoint POST -> write-back runs inside the incumbent
    ``auth.json.lock``; a waiter that finds the row already rotated by a peer
    adopts the stored pair instead of replaying the consumed token.
    """
    if not account.refresh_token:
        raise OAuthPoolError("account has no refresh token")
    lock_path = auth_store.parent / "auth.json.lock"
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            document = json.loads(auth_store.read_text(encoding="utf-8"))
            entries = (document.get("credential_pool") or {}).get(pool)
            row = None
            if isinstance(entries, list):
                for entry in entries:
                    if (isinstance(entry, dict)
                            and str(entry.get("id") or entry.get("label") or "")
                            == account.id):
                        row = entry
                        break
            if row is None:
                raise OAuthPoolError("account row vanished from the pool")
            stored_refresh = str(row.get("refresh_token") or "")
            if stored_refresh and stored_refresh != account.refresh_token:
                # Another writer rotated this single-use grant first: adopt.
                return OAuthAccount(account.id, account.label,
                                    str(row.get("access_token") or ""),
                                    stored_refresh, 0.0)
            response = client.post(
                token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Accept": "application/json",
                         "User-Agent": "HermesAgent/fabric-router"},
                data={"grant_type": "refresh_token",
                      "refresh_token": account.refresh_token,
                      "client_id": client_id})
            if response.status_code == 429:
                raise OAuthPoolError("token endpoint rate limited; retry later")
            if response.status_code != 200:
                raise OAuthPoolError(
                    f"token refresh refused ({response.status_code})")
            payload = response.json()
            access = str(payload.get("access_token") or "")
            if not access:
                raise OAuthPoolError("refresh response omitted access_token")
            refresh = str(payload.get("refresh_token") or account.refresh_token)
            row["access_token"] = access
            row["refresh_token"] = refresh
            row["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime())
            row.pop("last_status", None)
            row.pop("last_error_code", None)
            row.pop("last_error_reason", None)
            row.pop("last_error_reset_at", None)
            auth_store.write_text(json.dumps(document, indent=2),
                                  encoding="utf-8")
            return OAuthAccount(account.id, account.label, access, refresh, 0.0)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
