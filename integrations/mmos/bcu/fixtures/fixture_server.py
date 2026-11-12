#!/usr/bin/env python3
"""BCU loopback fixture server (stdlib only).

Serves this script's directory over HTTP bound to 127.0.0.1 only — never a
wildcard interface. Used for browser-harness proofs against fixture.html.

Usage:
    python3 fixture_server.py [--port 8763]     # --port 0 picks an ephemeral port

Programmatic use:
    server = bcu_fixture_server.make_server(port=0)
    ...  # server.server_address[1] is the chosen port
    server.shutdown()
"""
import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8763
BIND_HOST = "127.0.0.1"


class _LoggingHandler(SimpleHTTPRequestHandler):
    """Same serving behavior, with request logs on stdout."""

    def log_message(self, fmt, *args):
        sys.stdout.write("BCU_FIXTURE %s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


def make_server(port=DEFAULT_PORT, directory=None):
    """Build (not run) the fixture server. Returns a ThreadingHTTPServer."""
    serve_dir = str(Path(directory) if directory else Path(__file__).resolve().parent)
    handler = partial(_LoggingHandler, directory=serve_dir)
    return ThreadingHTTPServer((BIND_HOST, port), handler)


def serve(port=DEFAULT_PORT, directory=None):
    """Build and serve_forever; prints the fixture URL first."""
    server = make_server(port=port, directory=directory)
    url = "http://%s:%d/fixture.html" % (server.server_address[0], server.server_address[1])
    print("BCU_FIXTURE_SERVING " + url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Serve the BCU fixture page on loopback")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="TCP port to bind on 127.0.0.1 (0 = ephemeral)")
    args = parser.parse_args()
    sys.exit(serve(port=args.port))


if __name__ == "__main__":
    main()
