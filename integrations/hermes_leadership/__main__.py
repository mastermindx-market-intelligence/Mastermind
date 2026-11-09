"""Bounded offline policy inspection. Never a live authentication/admission CLI."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import sys
from integrations.secretary_team_access.client import _strict_json
from .budget import evaluate_adviser_budget
from .charters import charter_for

MAX_INPUT_BYTES = 65536


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, 'invalid_arguments\n')


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument('command', choices=('charter', 'budget'))
    parser.add_argument('subject', nargs='?')
    args = parser.parse_args(argv)
    if args.command == 'charter':
        try:
            result = charter_for(args.subject)
        except ValueError:
            parser.error('invalid_subject')
    else:
        if args.subject is not None:
            parser.error('unexpected_subject')
        try:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                raise ValueError('input_over_budget')
            envelope = _strict_json(raw)
            if type(envelope) is not dict or set(envelope) != {'snapshot', 'request', 'now'}:
                raise ValueError('invalid_envelope')
            stamp = envelope['now']
            if type(stamp) is not str or len(stamp) > 40:
                raise ValueError('invalid_time')
            now = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError('timezone_required')
            result = evaluate_adviser_budget(envelope['snapshot'], envelope['request'], now=now)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, OSError):
            sys.stderr.write('invalid_input\n')
            return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False,
                               separators=(',', ':')) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
