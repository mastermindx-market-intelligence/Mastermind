"""Read-only operator inspector for already-materialized Portfolio V3 evidence.

Run from the source workspace: python -m scripts.portfolio_decision_snapshot status
This partial S0 release intentionally has no compose, capture, path or root option.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot as snapshots
from portfolio.decision_snapshot_contracts import SECTION_IDS


class _InvalidArguments(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Do not echo unknown paths, identities or arbitrary input into JSON logs.
        raise _InvalidArguments('invalid inspector arguments')


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'show'):
        command = commands.add_parser(name)
        command.add_argument('--book', choices=('autonomous',), default='autonomous')
        command.add_argument('--limit', type=int, default=20)
        if name == 'show':
            command.add_argument('--snapshot-id', default=None)
            command.add_argument('--section', choices=SECTION_IDS, default=None)
            command.add_argument('--offset', type=int, default=0)
    return parser


def _emit(value: dict) -> None:
    sys.stdout.write(canonical_json_bytes(value).decode('ascii') + '\n')


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = snapshots.read_projection(
            args.book,
            snapshot_id=getattr(args, 'snapshot_id', None),
            section_id=getattr(args, 'section', None),
            offset=getattr(args, 'offset', 0),
            limit=args.limit,
        )
    except (_InvalidArguments, snapshots.SnapshotInvalidRequest):
        _emit({'error': 'INVALID_REQUEST', 'read_only': True})
        return 2
    except snapshots.SnapshotNotFound:
        _emit({'error': 'SNAPSHOT_NOT_FOUND', 'read_only': True})
        return 3
    except snapshots.SnapshotCorrupt:
        _emit({'error': 'SNAPSHOT_CORRUPT', 'read_only': True})
        return 4
    except snapshots.DecisionSnapshotError:
        _emit({'error': 'SNAPSHOT_UNAVAILABLE', 'read_only': True})
        return 5
    _emit(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
