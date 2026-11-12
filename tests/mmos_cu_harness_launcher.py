#!/usr/bin/env python3
"""TEST-ONLY harness launcher for the mmos_computer_use round-trip test.

BCU-MICRO (R3-M2) class rule: the shipped entry point of a restraining
layer takes NO argument that chooses its rules, its binary or its state —
tools/mmos_computer_use/server.py main() accepts no path argument at all.
The subprocess round-trip test still needs scratch paths, so it starts the
server through THIS file, which injects them via serve()'s keyword
parameters (constructor injection — an in-process path no MCP registration
line can reach).

This launcher is NOT part of the installed set (see the README
Registration section in tools/mmos_computer_use/); it exists only for
tests/test_mmos_bcu_computer_use.py (TestMcpFraming).

Usage:
    python3 tests/mmos_cu_harness_launcher.py \
        --runtime <runtime.json> [--state-dir <dir>] [--deny <deny.json>]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.join(os.path.dirname(HERE), "tools", "mmos_computer_use")
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import server  # noqa: E402  (same-repo module under test)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mmos_cu_harness_launcher",
        description="TEST-ONLY launcher: serve() with keyword-injected "
                    "scratch paths (not part of the installed set).")
    parser.add_argument("--state-dir", default=None,
                        help="scratch lease/pacing state folder")
    parser.add_argument("--runtime", default=None,
                        help="scratch runtime descriptor path")
    parser.add_argument("--deny", default=None,
                        help="scratch deny-list path")
    args = parser.parse_args(argv)
    return server.serve(state_dir=args.state_dir, runtime_path=args.runtime,
                        deny_path=args.deny)


if __name__ == "__main__":
    sys.exit(main())
