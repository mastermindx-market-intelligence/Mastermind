#!/usr/bin/env python3
"""Command-line entry to the mmos_computer_use server.

One subcommand per tool action. Builds the SAME context as the MCP server
(same runtime pin, deny list, lease, presence, pacer, adapter, vision
client) and dispatches through the same handle_tool_call, so every gate,
refusal and receipt is identical; only the transport differs.

Output: exactly one receipt JSON on stdout (same shape the MCP tool
returns). Exit codes: 0 a receipt was produced (read its status field —
refusals are receipts, not process errors); 1 startup refused (config,
pin, deny-list load); 2 usage error. Never retry a nonzero-exit or
uncertain-status action; the receipt is the whole answer.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import server  # noqa: E402  (same directory; the MCP server module)

INT_KEYS = {"window_id", "x", "y", "ttl_seconds", "amount"}
BOOL_KEYS = {"ocr", "allow_foreground"}
STR_KEYS = {"app", "title", "element_ref", "text", "chord", "direction",
            "question", "owner", "keep_path"}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mmos_computer_use",
        description="CLI front to the mmos_computer_use server "
                    "(same gates and receipts as the MCP tool).")
    sub = parser.add_subparsers(dest="action", metavar="<action>")

    # Per-action flags mirror TOOL_SCHEMA in server.py.
    flags = {
        "app": (["--app"], {"help": "application name"}),
        "window_id": (["--window-id"], {"type": int, "help": "window id"}),
        "title": (["--title"], {"help": "slice_front title substring"}),
        "element_ref": (["--element-ref"], {"help": "AX element id or label"}),
        "text": (["--text"], {"help": "text for set_text / slice_paste"}),
        "chord": (["--chord"], {"help": "single keyboard chord"}),
        "direction": (["--direction"], {"choices": ["up", "down", "left",
                                                    "right"]}),
        "amount": (["--amount"], {"type": int, "help": "scroll amount 1-50"}),
        "x": (["--x"], {"type": int}),
        "y": (["--y"], {"type": int}),
        "ocr": (["--ocr"], {"action": "store_true",
                            "help": "capture: include OCR text"}),
        "keep_path": (["--keep-path"], {"help": "capture: PNG path (scratch)"}),
        "question": (["--question"], {"help": "vision_ask question"}),
        "element_hints": (["--element-hint"], {"action": "append",
                                               "dest": "element_hints"}),
        "owner": (["--owner"], {"help": "lease owner id"}),
        "ttl_seconds": (["--ttl-seconds"], {"type": int}),
        "allow_foreground": (["--allow-foreground"], {"action": "store_true"}),
    }
    per_action = {
        "apps": [],
        "windows": ["app"],
        "inspect": ["window_id"],
        "capture": ["window_id", "ocr", "keep_path"],
        "press": ["window_id", "element_ref"],
        "set_text": ["window_id", "element_ref", "text"],
        "keys": ["window_id", "chord"],
        "scroll": ["window_id", "direction", "amount"],
        "pointer_click": ["window_id", "element_ref", "x", "y"],
        "slice_front": ["app", "window_id", "title"],
        "slice_click": ["window_id", "element_ref", "x", "y"],
        "slice_paste": ["window_id", "text", "element_ref"],
        "slice_send": ["window_id", "element_ref"],
        "slice_look": ["window_id"],
        "vision_ask": ["window_id", "question", "element_hints"],
        "lease_acquire": ["owner", "ttl_seconds"],
        "lease_release": ["owner"],
        "lease_status": [],
        "presence": [],
    }
    for action, keys in per_action.items():
        # Import order note: server.ACTIONS is the source of truth.
        subparser = sub.add_parser(action, help=action)
        for key in keys:
            names, kwargs = flags[key]
            subparser.add_argument(*names, **kwargs)
    return parser


def main(argv=None, ctx=None):
    parser = build_parser()
    args_ns = parser.parse_args(argv)
    if not args_ns.action:
        parser.print_usage(sys.stderr)
        sys.stderr.write("cli: an action is required\n")
        return 2
    arguments = {"action": args_ns.action}
    for key in INT_KEYS | BOOL_KEYS | STR_KEYS | {"element_hints"}:
        value = getattr(args_ns, key, None)
        if value is not None:
            arguments[key] = value
    if ctx is None:
        try:
            ctx = server.build_context()
        except server.RefuseError as error:
            sys.stderr.write("cli: startup refused: %s\n" % error)
            return 1
    result = server.handle_tool_call(ctx, arguments)
    texts = [c.get("text", "") for c in result.get("content", [])
             if c.get("type") == "text"]
    sys.stdout.write((texts[0] if texts else
                      json.dumps({"status": "INTERNAL",
                                  "cause": "empty result"})) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
