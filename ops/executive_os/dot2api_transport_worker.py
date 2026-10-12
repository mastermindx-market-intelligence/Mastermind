#!/usr/bin/env python3
"""One local transport carrier for one Executive Attempt -> one Dot2API task.

The process submits exactly once, writes the exact provider task identity before
polling, and never stores the credential. Executive OS remains retry authority.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from integrations.dot2api.client import (
    Dot2ApiClient,
    Dot2ApiClientError,
    Dot2ApiEffectUnknown,
)


def _read(path: Path) -> dict:
    raw = path.read_bytes()
    if not raw or len(raw) > 128 * 1024:
        raise ValueError("DOT2API_INPUT_SIZE_INVALID")
    value = json.loads(raw.decode("utf-8", errors="strict"))
    if type(value) is not dict:
        raise ValueError("DOT2API_INPUT_INVALID")
    return value


def _atomic(path: Path, value: dict) -> None:
    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    if len(raw) > 1024 * 1024:
        raise ValueError("DOT2API_OUTPUT_SIZE_INVALID")
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    provider_path = Path(args.provider)
    result_path = Path(args.result)
    config = _read(input_path)
    required = {
        "base_url",
        "queue",
        "idempotency_key",
        "messages",
        "ttl_seconds",
        "max_attempts",
        "poll_seconds",
        "poll_deadline_seconds",
    }
    if set(config) != required:
        raise ValueError("DOT2API_INPUT_FIELDS_INVALID")
    poll_seconds = config["poll_seconds"]
    poll_deadline_seconds = config["poll_deadline_seconds"]
    if (
        type(poll_seconds) not in (int, float)
        or not 0.05 <= float(poll_seconds) <= 30.0
        or type(poll_deadline_seconds) not in (int, float)
        or not 0.2 <= float(poll_deadline_seconds) <= 2_592_000.0
    ):
        raise ValueError("DOT2API_POLL_BOUNDS_INVALID")

    token = os.environ.get("MMX_DOT2API_TOKEN")
    client = Dot2ApiClient(
        config["base_url"],
        token_loader=lambda: token or "",
        timeout_seconds=15.0,
    )

    try:
        task = client.submit_chat_task(
            queue=config["queue"],
            idempotency_key=config["idempotency_key"],
            messages=config["messages"],
            ttl_seconds=config["ttl_seconds"],
            max_attempts=config["max_attempts"],
        )
    except Dot2ApiEffectUnknown as exc:
        _atomic(
            provider_path,
            {
                "schema": "mastermind.dot2api.provider_binding/v1",
                "ok": False,
                "effect": "EFFECT_UNKNOWN",
                "code": exc.code,
            },
        )
        return 75
    except Dot2ApiClientError as exc:
        _atomic(
            provider_path,
            {
                "schema": "mastermind.dot2api.provider_binding/v1",
                "ok": False,
                "effect": exc.effect,
                "code": exc.code,
                "status": exc.status,
            },
        )
        return 76

    _atomic(
        provider_path,
        {
            "schema": "mastermind.dot2api.provider_binding/v1",
            "ok": True,
            "effect": "CONFIRMED",
            "task_id": task.id,
            "status": task.status,
            "revision": task.revision,
        },
    )
    print(
        json.dumps(
            {"event": "dot2api_task_bound", "task_id": task.id},
            sort_keys=True,
        ),
        flush=True,
    )

    deadline = time.monotonic() + float(poll_deadline_seconds)
    while not task.terminal:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                json.dumps(
                    {"event": "dot2api_poll_deadline", "task_id": task.id},
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
            return 74
        time.sleep(min(float(poll_seconds), remaining))
        try:
            task = client.get_task(task.id)
        except Dot2ApiClientError as exc:
            print(
                json.dumps(
                    {"event": "dot2api_read_unavailable", "code": exc.code},
                    sort_keys=True,
                ),
                flush=True,
            )
            continue

    _atomic(
        result_path,
        {
            "schema": "mastermind.dot2api.transport_result/v1",
            "task_id": task.id,
            "status": task.status,
            "result": task.result,
            "error": task.error,
            "attempts": task.attempts,
            "max_attempts": task.max_attempts,
            "revision": task.revision,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "expires_at": task.expires_at,
        },
    )
    print(
        json.dumps(
            {
                "event": "dot2api_task_terminal",
                "task_id": task.id,
                "status": task.status,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if task.status == "completed" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"event": "dot2api_transport_refused", "error": type(exc).__name__}
            ),
            file=sys.stderr,
        )
        raise SystemExit(64)
