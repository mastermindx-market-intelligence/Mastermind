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

Every act/slice/vision subcommand needs BOTH --owner and the --lease-nonce
returned by `lease_acquire`: the lease is single-holder and each
acquisition has its own nonce (SERVER_VERSION 0.3.0). Missing or wrong
nonce is a typed LEASE_NONCE_INVALID receipt, not a transport error.

Environment (M2 hardening; BCU R2 item 2):
  MMOS_CU_PRESENCE_MIN_IDLE / MMOS_CU_PACING_SECONDS — like the
    runtime.json keys and any constructor argument — may only make the
    gates STRICTER than their 180 s defaults; outside the test harness
    every looser value refuses at startup (the defaults are the
    production floors), and no value may go below the absolute 1 s floor.
  MMOS_CU_STATE_DIR / MMOS_CU_DENY / MMOS_CU_RUNTIME may only point
    INSIDE this tool's own folder (tools/mmos_computer_use/ or a subdir);
    anything outside refuses at startup.
  MMOS_CU_TEST_MODE=1 is the explicit test-only escape that permits
    sub-default thresholds and out-of-layer paths. Since BCU R2 item 2 it
    is honored ONLY inside the unit-test harness process (pytest loaded
    in-process): the env marker alone, which any session could export,
    never unlocks the layer. Never set it in production.
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
            "question", "owner", "lease_nonce"}


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
        "question": (["--question"], {"help": "vision_ask question"}),
        "element_hints": (["--element-hint"], {"action": "append",
                                               "dest": "element_hints"}),
        "owner": (["--owner"], {"help": "lease owner id"}),
        "lease_nonce": (["--lease-nonce"],
                        {"help": "nonce from lease_acquire (required on acts)"}),
        "ttl_seconds": (["--ttl-seconds"], {"type": int}),
        "allow_foreground": (["--allow-foreground"], {"action": "store_true"}),
    }
    per_action = {
        "apps": [],
        "windows": ["app"],
        "inspect": ["window_id"],
        "capture": ["window_id", "ocr"],
        # Every act/slice/vision action carries the lease owner AND the
        # acquisition nonce (M5): both are required by the server gate.
        "press": ["window_id", "element_ref", "owner", "lease_nonce",
                  "allow_foreground"],
        "set_text": ["window_id", "element_ref", "text", "owner",
                     "lease_nonce"],
        "keys": ["window_id", "chord", "owner", "lease_nonce",
                 "allow_foreground"],
        "scroll": ["window_id", "direction", "amount", "owner",
                   "lease_nonce", "allow_foreground"],
        "pointer_click": ["window_id", "element_ref", "x", "y", "owner",
                          "lease_nonce"],
        "slice_front": ["app", "window_id", "title", "owner",
                        "lease_nonce"],
        "slice_click": ["window_id", "element_ref", "x", "y", "owner",
                        "lease_nonce"],
        "slice_paste": ["window_id", "text", "element_ref", "owner",
                        "lease_nonce", "allow_foreground"],
        "slice_send": ["window_id", "element_ref", "owner", "lease_nonce"],
        "slice_look": ["window_id", "question", "owner", "lease_nonce"],
        "vision_ask": ["window_id", "question", "element_hints", "owner",
                       "lease_nonce"],
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
