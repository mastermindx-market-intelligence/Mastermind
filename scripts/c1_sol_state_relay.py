"""Production entrypoint for the outbound-only C1 SOL_STATE Relay."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# Production launch is intentionally ``python -I -S -B``.  Under isolated
# mode the script/repository directory is not an ambient import path, so bind
# exactly this immutable release root before importing first-party packages.
_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from integrations.slack_executive.c1_cycle import C1RelayService  # noqa: E402
from integrations.slack_executive.c1_runtime import (  # noqa: E402
    assert_relay_principal,
    load_config,
    read_token_file,
    verify_slack_identity,
)
from integrations.slack_executive.executive_state_reader import (  # noqa: E402
    CeoIngressStateReader,
)
from integrations.slack_executive.slack_web_api import (  # noqa: E402
    SlackWebApiStateClient,
)
from integrations.slack_executive.sol_state import SolStatePublisher  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mastermind C1 SOL_STATE Relay")
    parser.add_argument("--config", required=True)
    return parser


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def serve(config_path: str | Path) -> None:
    assert_relay_principal()
    config = load_config(config_path)
    token = read_token_file(config.slack_token_file)
    await verify_slack_identity(
        token=token,
        expected_workspace_id=config.slack_workspace_id,
        expected_bot_user_id=config.slack_bot_user_id,
    )

    reader = CeoIngressStateReader(socket_path=config.executive_socket)
    slack = SlackWebApiStateClient(
        token=token,
        bot_user_id=config.slack_bot_user_id,
    )
    publisher = SolStatePublisher(
        slack,
        channel_id=config.slack_channel_id,
        bot_user_id=config.slack_bot_user_id,
        history_limit=100,
        max_executive_age_seconds=config.max_executive_age_seconds,
        relay_version=config.relay_version,
    )
    service = C1RelayService(
        reader=reader,
        publisher=publisher,
        heartbeat_seconds=config.heartbeat_seconds,
        max_executive_age_seconds=config.max_executive_age_seconds,
        relay_version=config.relay_version,
    )

    try:
        await service.recover()
        await service.poll_once(checked_at=_utc_now())
        while True:
            await asyncio.sleep(config.poll_seconds)
            await service.poll_once(checked_at=_utc_now())
    finally:
        await slack.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(serve(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
