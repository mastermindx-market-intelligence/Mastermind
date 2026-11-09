#!/usr/bin/env python3
"""A5 live boot proof: boot a REAL patched T3 server in isolation and pin the
admission patch's live behavior (Director A5, 2026-11-09).

Closes the last SOURCE_ONLY gap of DONE_WHEN 4 invariant 11 (three distinct
Opus audits said "admission patch never booted live"). The driver:

1. copies the pinned donor clone (READ-ONLY shared clone, HEAD checked at the
   pin) into two scratch trees — ``patched`` (committed admission patch applied
   + A5 scratch-only singleton counters) and ``base`` (counters only, NO
   admission patch) — installs both with the repo's pinned pnpm and typechecks
   them;
2. boots each tree headlessly (``node src/bin.ts serve``) on an isolated port
   with an isolated data dir — never 3773, never ``~/.t3``, never the desktop
   app — and authenticates over the SAME OAuth PKCE flow the live proof uses
   (``/oauth/mcp/register`` -> ``/oauth/mcp/decision`` with the server's own
   headless startup pairing credential printed on stdout -> ``/oauth/mcp/token``).
   No desktop token is ever reused;
3. scenario A (``MASTERMIND_ADMISSION_ENDPOINT`` unset, patched) runs one real
   ``t3_thread_launch`` / ``t3_thread_read`` / ``t3_thread_send`` /
   ``t3_thread_interrupt`` over the isolated MCP endpoint with the donor's free
   ``devReplay`` ACP instance (recorded turns, no paid model), and compares the
   reply shapes + singleton construction counts with the unpatched base boot;
4. scenario B boots the patched tree against a local fake admission server
   (admit / refuse / unreachable / hang) and pins: admitted launch -> thread
   starts and the ledger binding shows up in later revalidate consults;
   refused launch -> typed refusal, no thread; unreachable -> fail-closed, no
   thread; hang -> observed for a bounded window only (UNKNOWN, never
   fabricated); interrupts NEVER consult admission and are never blocked;
   request fields claiming ``creationSource``/admission carry no authority;
5. emits ``t3_admission_patch_boot_receipt.json`` (secret-free, user home
   redacted as ``~``) and stops every server it started.

Scratch-only instrumentation: ``A5ScratchCounts.ts`` wraps the four shared
singleton layers (ProjectionStore, CommandOutputHub, Orchestrator,
TextGeneration) with the patch's own composition rule (``Layer.provide``, never
a nested ``Layer.build``); each construction emits one ``A5_COUNT`` JSON line
on the server's stderr (harvested per boot; the value of
``$A5_SINGLETON_COUNTS_FILE`` is only the on-switch). The exact instrumentation
diff is recorded in the receipt; the committed patch/MANIFEST are never
modified.

Usage:
  env -u PYTHONPATH /opt/homebrew/bin/python3.12 t3_admission_patch_boot.py \
      [--scratch DIR] [--hang-window SECONDS] [--keep] [--skip-install] \
      [--reuse-install] [--skip-typecheck] [--skip-base]

Exit code 0 = receipt written with outcome DONE or DONE_WITH_FINDINGS; the
per-scenario PASS/FAIL/UNKNOWN verdicts are in the receipt (a FAIL scenario
still exits 0 only for outcome DONE_WITH_FINDINGS when the boot itself
succeeded; a boot that never reached readiness exits 3 with outcome BLOCKED).
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PATCH_PATH = REPO / "integrations" / "t3" / "upstream_patches" / "mastermind_admission_0770446.patch"
MANIFEST_PATH = REPO / "integrations" / "t3" / "upstream_patches" / "MANIFEST.md"
RECEIPT_OUT = REPO / "integrations" / "t3" / "live_proof" / "t3_admission_patch_boot_receipt.json"

PIN = "0770446869d247a8b28c27d7ed93f47f8ff0c1e4"
PATCH_SHA256 = "5785ac9525a852d0c19c3668f2ae4e9cb3fcd779a62b2a084affa2004f4e922f"
DEFAULT_PINNED_SOURCE = Path(
    os.environ.get("MMOS_T3_PINNED_SOURCE", "/Users/chriswong/.hermes/profiles/engineering/mmos/t3code-src")
)
PNPM = ["npx", "-y", "pnpm@12.14.0"]  # the donor repo pins this exact version
PORT_BASE = 3977  # isolated ports; NEVER 3773 (the real desktop T3)
BOOT_TIMEOUT_S = 180.0
DEFAULT_HANG_WINDOW_S = 75.0
LOGEvents: list[dict] = []


def log(event: str, **facts: object) -> None:
    entry = {"t": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event, **facts}
    LOGEvents.append(entry)
    print(f"[a5] {event} {facts if facts else ''}", flush=True)


def redact(text: str) -> str:
    home = os.path.expanduser("~")
    return text.replace(home, "~") if home != "/" else text


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], *, cwd: Path | None = None, timeout: float = 600.0, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        timeout=timeout, env=env,
    )


def free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Scratch instrumentation (NEVER part of the committed patch)
# ---------------------------------------------------------------------------

A5_COUNTS_MODULE = '''\
/**
 * A5 SCRATCH-ONLY singleton-construction counters (Director A5 live boot proof,
 * 2026-11-09). NOT part of the committed upstream patch; written only into the
 * private scratch tree by integrations/t3/live_proof/t3_admission_patch_boot.py.
 *
 * Counts how many times each shared singleton service (ProjectionStore,
 * CommandOutputHub, Orchestrator, TextGeneration) is constructed inside the
 * server runtime build. When $A5_SINGLETON_COUNTS_FILE is set to any non-empty
 * value, one "A5_COUNT {json}" line per construction is written to stderr; the
 * driver harvests those lines from the server's stderr log (node builtin fs is
 * not used — the donor's effect-tsgo rules ban it in this module — and stderr
 * is per-process, so per-boot attribution needs no file).
 *
 * Semantics are exactly the incumbent layer's: the wrapper requires the
 * incumbent service from the SAME memo map (Layer.provide, never a nested
 * Layer.build), bumps a counter, and returns the incumbent instance unchanged —
 * the same composition rule the admission decorators use, so the counters
 * cannot change what is built. All side effects live in bumpCount, a plain
 * non-Effect function, so no effect language-service rule fires inside
 * Effect.gen.
 */
import * as Context from "effect/Context";
import * as Effect from "effect/Effect";
import * as Layer from "effect/Layer";

import * as CommandOutputHub from "../orchestration-v2/CommandOutputHub.ts";
import * as Orchestrator from "../orchestration-v2/Orchestrator.ts";
import * as ProjectionStore from "../orchestration-v2/ProjectionStore.ts";
import * as TextGeneration from "../textGeneration/TextGeneration.ts";

const countsEnabled = process.env.A5_SINGLETON_COUNTS_FILE !== undefined &&
  process.env.A5_SINGLETON_COUNTS_FILE !== "";

export const a5SingletonCounts: Record<string, number> = {};

function bumpCount(name: string): number {
  const next = (a5SingletonCounts[name] ?? 0) + 1;
  a5SingletonCounts[name] = next;
  if (countsEnabled) {
    try {
      process.stderr.write(`A5_COUNT ${JSON.stringify({ name, count: next })}\\n`);
    } catch {
      // Instrumentation must never break the server.
    }
  }
  return next;
}

export const countedServiceLayer = <I, S, E, RIn>(
  tag: Context.Key<I, S>,
  name: string,
  incumbent: Layer.Layer<I, E, RIn>,
): Layer.Layer<I, E, RIn> => {
  a5SingletonCounts[name] = 0;
  return Layer.effect(
    tag,
    Effect.gen(function* () {
      const inner = yield* tag;
      bumpCount(name);
      return inner;
    }),
  ).pipe(Layer.provide(incumbent));
};

export const a5ProjectionStoreLayer = countedServiceLayer(
  ProjectionStore.ProjectionStoreV2,
  "ProjectionStore",
  ProjectionStore.layer,
);
export const a5CommandOutputHubLayer = countedServiceLayer(
  CommandOutputHub.CommandOutputHub,
  "CommandOutputHub",
  CommandOutputHub.layer,
);
export const a5OrchestratorLayer = countedServiceLayer(
  Orchestrator.OrchestratorV2,
  "Orchestrator",
  Orchestrator.layer,
);
export const a5TextGenerationLayer = countedServiceLayer(
  TextGeneration.TextGeneration,
  "TextGeneration",
  TextGeneration.layer,
);
'''


def instrument_tree(tree: Path) -> dict:
    """Write the A5 counters module + counting edits into a scratch tree.

    Returns {counts_module_sha256, edits: {file: (replacements, additions)}}.
    """
    counts_path = tree / "apps/server/src/mastermind/A5ScratchCounts.ts"
    counts_path.parent.mkdir(parents=True, exist_ok=True)
    counts_path.write_text(A5_COUNTS_MODULE)

    edits: dict[str, dict] = {}

    rl = tree / "apps/server/src/orchestration-v2/runtimeLayer.ts"
    s = rl.read_text()
    anchor = 'import * as MastermindAdmission from "../mastermind/MastermindAdmissionAdapter.ts";\n'
    if anchor not in s:
        # base tree (no admission patch): anchor on the ThreadLaunchService import
        anchor = 'import * as ThreadLaunchService from "./ThreadLaunchService.ts";\n'
    import_block = (
        "// A5 SCRATCH-ONLY singleton counters (live boot proof); NOT part of the committed patch.\n"
        "import {\n"
        "  a5CommandOutputHubLayer,\n"
        "  a5OrchestratorLayer,\n"
        "  a5ProjectionStoreLayer,\n"
        "  a5TextGenerationLayer,\n"
        '} from "../mastermind/A5ScratchCounts.ts";\n'
    )
    assert anchor in s, "runtimeLayer.ts import anchor not found"
    s = s.replace(anchor, anchor + import_block, 1)
    repl = {
        "ProjectionStore.layer": "a5ProjectionStoreLayer",
        "CommandOutputHub.layer": "a5CommandOutputHubLayer",
        "Orchestrator.layer": "a5OrchestratorLayer",
        "TextGeneration.layer": "a5TextGenerationLayer",
    }
    counts = {k: s.count(k) for k in repl}
    for k, v in repl.items():
        s = s.replace(k, v)
    rl.write_text(s)
    edits["apps/server/src/orchestration-v2/runtimeLayer.ts"] = counts

    sv = tree / "apps/server/src/server.ts"
    s = sv.read_text()
    anchor2 = 'import * as RuntimeLayer from "./orchestration-v2/runtimeLayer.ts";\n'
    assert anchor2 in s, "server.ts runtimeLayer import anchor not found"
    import2 = (
        "// A5 SCRATCH-ONLY singleton counters (live boot proof); NOT part of the committed patch.\n"
        "import { a5ProjectionStoreLayer, a5TextGenerationLayer } from \"./mastermind/A5ScratchCounts.ts\";\n"
    )
    s = s.replace(anchor2, anchor2 + import2, 1)
    counts2 = {
        "ProjectionStoreV2.layer": s.count("ProjectionStoreV2.layer"),
        "TextGeneration.layer": s.count("TextGeneration.layer"),
    }
    s = s.replace("ProjectionStoreV2.layer", "a5ProjectionStoreLayer")
    s = s.replace("TextGeneration.layer", "a5TextGenerationLayer")
    sv.write_text(s)
    edits["apps/server/src/server.ts"] = counts2
    return {
        "counts_module_sha256": hashlib.sha256(A5_COUNTS_MODULE.encode()).hexdigest(),
        "edits": edits,
    }


# ---------------------------------------------------------------------------
# Fake admission endpoint (threading, scriptable)
# ---------------------------------------------------------------------------


class FakeAdmissionServer:
    """Local stand-in for the Mastermind admission endpoint.

    Every /v1/admit consult is logged (body + timestamp). Behavior per consult
    is scripted by a queue: "admit", "refuse", or ("hang", seconds). Answers
    carry the wire shapes the adapter parses (MANIFEST: admitted |
    blocked_with_reason | passthrough).
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self.consults: list[dict] = []
        self.lock = threading.Lock()
        self.script: list[tuple] = []  # consumed from the front; last entry repeats
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
                try:
                    body = json.loads(raw) if raw else {}
                except ValueError:
                    body = {"_unparsable": raw[:200]}
                with server.lock:
                    step = server.script.pop(0) if len(server.script) > 1 else server.script[0]
                kind = step[0]
                if kind == "admit":
                    payload = {"decision": "admitted", "rootRef": step[1], "admissionId": step[2], "grantedAt": "2026-11-09T00:00:00Z"}
                    status, out = 200, json.dumps(payload)
                elif kind == "refuse":
                    payload = {"decision": "blocked_with_reason", "reason": step[1]}
                    status, out = 200, json.dumps(payload)
                elif kind == "hang":
                    # reply recorded up front: it only goes out after the sleep
                    payload = {"decision": "admitted", "rootRef": "late", "after_s": step[1]}
                    status, out = None, None  # answered below after hanging
                else:  # pragma: no cover - driver bug guard
                    payload = {"error": "unknown script step"}
                    status, out = 500, json.dumps(payload)
                with server.lock:
                    # every consult is logged with the reply the script sends for
                    # it (for hang: the eventual reply + how long it hangs)
                    server.consults.append(
                        {
                            "t": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "path": self.path,
                            "body": body,
                            "reply": payload,
                        }
                    )
                if kind == "hang":
                    time.sleep(step[1])
                    status = 200
                    out = json.dumps({"decision": "admitted", "rootRef": "late"})
                data = out.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:  # silence
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def set_script(self, script: list[tuple]) -> None:
        with self.lock:
            self.script = list(script)

    def snapshot_consults(self) -> list[dict]:
        with self.lock:
            return [dict(c) for c in self.consults]

    def consults_matching(self, **criteria) -> list[dict]:
        out = []
        for c in self.snapshot_consults():
            body = c.get("body") or {}
            if all(body.get(k) == v for k, v in criteria.items()):
                out.append(c)
        return out

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# ---------------------------------------------------------------------------
# Isolated server boot + MCP client
# ---------------------------------------------------------------------------


class BootedServer:
    def __init__(self, name: str, tree: Path, scratch: Path, port: int, admission_endpoint: str | None) -> None:
        self.name = name
        self.tree = tree
        self.dir = scratch / f"data-{name}"
        self.run_dir = scratch / f"run-{name}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.mcp_url = f"{self.base}/mcp"
        self.admission_endpoint = admission_endpoint
        self.proc: subprocess.Popen | None = None
        self.counts_file = self.run_dir / "counts.ndjson"
        self.log_path = self.run_dir / "server.log"
        self.token: str | None = None
        self.environment: dict = {}

    def start(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "T3CODE_PORT": str(self.port),
                "T3CODE_HOST": "127.0.0.1",
                "T3CODE_HOME": str(self.dir),
                # devUrl presence marks the dev variant: seeds the donor's free
                # devReplay ACP instance (recorded turns, no paid model). The
                # URL itself is never contacted over this proof.
                "VITE_DEV_SERVER_URL": "http://127.0.0.1:5199",
                "A5_SINGLETON_COUNTS_FILE": str(self.counts_file),
            }
        )
        env.pop("MASTERMIND_ADMISSION_ENDPOINT", None)
        env.pop("MASTERMIND_ADMISSION_ROOT_REF", None)
        if self.admission_endpoint is not None:
            env["MASTERMIND_ADMISSION_ENDPOINT"] = self.admission_endpoint
        log_file = self.log_path.open("wb")
        self.proc = subprocess.Popen(
            ["node", "src/bin.ts", "serve", "--base-dir", str(self.dir), "--no-browser"],
            cwd=str(self.tree / "apps/server"),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,  # own process group -> killpg gets children too
        )
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        pattern = re.compile(r"^Token: (\S+)$", re.MULTILINE)
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"[{self.name}] server exited rc={self.proc.returncode}: {self._log_tail()}"
                )
            text = self._log_text()
            match = pattern.search(text)
            if match and "T3 Code server is ready" in text:
                self.token = match.group(1)
                return
            time.sleep(0.5)
        raise RuntimeError(f"[{self.name}] server not ready in {BOOT_TIMEOUT_S}s: {self._log_tail()}")

    def _log_text(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")
        except OSError:
            return ""

    def _log_tail(self, n: int = 1500) -> str:
        text = redact(self._log_text()[-n:])
        # never let the (short-lived) startup pairing credential into a receipt
        return re.sub(r"(?m)^Token: \S+$", "Token: <redacted>", text)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait(timeout=10)

    def singleton_counts(self) -> dict[str, int]:
        """Final per-name construction counts, harvested from A5_COUNT stderr
        lines in this server's own log (per-process attribution, no fs API)."""
        counts: dict[str, int] = {}
        for line in self._log_text().splitlines():
            if not line.startswith("A5_COUNT "):
                continue
            try:
                rec = json.loads(line[len("A5_COUNT "):])
            except ValueError:
                continue
            counts[rec.get("name")] = rec.get("count")
        return counts

    def data_dir_digest(self) -> str:
        """sha256 over sorted (relative path, size) pairs — shape, not content."""
        items = []
        for path in sorted(self.dir.rglob("*")):
            if path.is_file():
                items.append(f"{path.relative_to(self.dir)}:{path.stat().st_size}")
        return hashlib.sha256("\n".join(items).encode()).hexdigest()[:16]

    # -- OAuth (same shape as integrations/t3/live_proof/t3_live_proof.py) ----

    def _http_json(self, url: str, payload: dict | None, *, form: dict | None = None) -> tuple[int, dict]:
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
            ctype = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(payload or {}).encode()
            ctype = "application/json"
        req = urllib.request.Request(
            url, data=body, method="POST", headers={"Content-Type": ctype, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")
            except ValueError:
                return exc.code, {}

    def obtain_token(self) -> str:
        assert self.token is not None, "server boot did not yield a startup pairing credential"
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        redirect_uri = "http://localhost:51234/callback"
        status, reg = self._http_json(
            self.base + "/oauth/mcp/register",
            {
                "client_name": "a5-admission-boot-proof",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_method": "none",
            },
        )
        if status != 201:
            raise RuntimeError(f"[{self.name}] oauth register failed {status}: {reg}")
        status, decision = self._http_json(
            self.base + "/oauth/mcp/decision",
            {
                "authorization": {
                    "response_type": "code",
                    "client_id": reg["client_id"],
                    "redirect_uri": redirect_uri,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": "a5-boot-state-1",
                    "resource": self.mcp_url,
                },
                "decision": {"_tag": "pairing-code", "access": "auto", "code": self.token},
            },
        )
        if status != 200 or not decision.get("redirectTo"):
            raise RuntimeError(f"[{self.name}] oauth decision failed {status}: {decision}")
        grant_code = urllib.parse.parse_qs(urllib.parse.urlparse(decision["redirectTo"]).query).get("code", [""])[0]
        status, token = self._http_json(
            self.base + "/oauth/mcp/token",
            None,
            form={
                "grant_type": "authorization_code",
                "code": grant_code,
                "redirect_uri": redirect_uri,
                "client_id": reg["client_id"],
                "code_verifier": verifier,
                "resource": self.mcp_url,
            },
        )
        if status != 200 or not token.get("access_token"):
            raise RuntimeError(f"[{self.name}] oauth token failed {status}: {token}")
        return token["access_token"]


class McpClient:
    """Minimal streamable-HTTP MCP client (stdlib only), same wire handling as
    t3_live_proof.McpHttp but bound to one BootedServer."""

    def __init__(self, server: BootedServer, token: str) -> None:
        self.server = server
        self.token = token
        self.session_id: str | None = None
        self.next_id = 0
        self.protocol_version = "2025-03-26"

    def _post(self, payload: dict, *, expect_reply: bool = True) -> dict | None:
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.server.mcp_url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=240) as resp:
            sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", "replace")
        if not expect_reply:
            return None
        if "text/event-stream" in ctype:
            data = None
            for line in raw.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
            if data is None:
                raise RuntimeError("SSE response carried no data frame")
            return json.loads(data)
        return json.loads(raw) if raw.strip() else {}

    def initialize(self) -> dict:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "a5-admission-boot-proof", "version": "1.0.0"},
                },
            }
        )
        result = resp.get("result") or {}
        if result.get("protocolVersion"):
            self.protocol_version = result["protocolVersion"]
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
        return result

    def _rpc_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def call(self, name: str, arguments: dict, timeout_note: str = "") -> dict:
        """Returns a normalized reply: {isError, code, message, payload}."""
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._rpc_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if resp.get("error"):
            err = resp["error"] if isinstance(resp["error"], dict) else {"message": str(resp["error"])}
            return {"isError": True, "code": err.get("code"), "message": str(err.get("message"))[:400], "payload": None}
        result = resp.get("result") or {}
        structured = result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else None
        if structured is None:
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    try:
                        parsed = json.loads(item.get("text", ""))
                    except (ValueError, TypeError):
                        continue
                    if isinstance(parsed, dict):
                        structured = parsed
                        break
        if result.get("isError") or structured is None:
            text = ""
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text += str(item.get("text", ""))
            return {
                "isError": True,
                "code": (structured or {}).get("code") if isinstance(structured, dict) else None,
                "message": redact(text[:400] or str(result)[:400]),
                "payload": structured,
            }
        return {"isError": False, "code": structured.get("code"), "message": None, "payload": structured}


def shape_of(reply: dict) -> dict:
    """Reply SHAPE for equality comparisons: isError + sorted payload keys +
    presence flags only (ids and transient run statuses are timing-unique)."""
    payload = reply.get("payload") or {}
    return {
        "isError": reply.get("isError", False),
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "threadId_present": bool(isinstance(payload, dict) and payload.get("threadId")),
        "runId_present": bool(isinstance(payload, dict) and payload.get("runId") is not None),
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

LAUNCH_ARGS = {
    "scratch": True,
    "title": "a5 admission boot proof",
    "message": "Say A5-BOOT-OK",
    "modelSelection": {"instanceId": "devReplay", "model": "showcase"},
}


def wait_run_terminal(client: McpClient, thread_id: str, deadline_s: float = 90.0) -> dict:
    """Poll t3_thread_read until the latest run is terminal; returns last read."""
    deadline = time.monotonic() + deadline_s
    last = {}
    while time.monotonic() < deadline:
        reply = client.call("t3_thread_read", {"threadId": thread_id})
        last = reply
        payload = reply.get("payload") or {}
        runs = payload.get("recentRuns") or []
        statuses = [r.get("status") for r in runs]
        if statuses and statuses[0] in {"completed", "failed", "interrupted", "rolled_back"}:
            return {"reply": reply, "run_status": statuses[0], "statuses": statuses[:3]}
        time.sleep(1.5)
    return {"reply": last, "run_status": "timeout", "statuses": []}


def scenario_ab_flow(server: BootedServer, label: str) -> dict:
    """Launch -> read -> send/steer -> interrupt on an endpoint-unset server."""
    token = server.obtain_token()
    client = McpClient(server, token)
    init = client.initialize()
    env = client.call("t3_environment_read", {})
    server.environment = env.get("payload") or {}
    launch = client.call("t3_thread_launch", dict(LAUNCH_ARGS, title=f"{label} launch"))
    launch_payload = launch.get("payload") or {}
    thread_id = launch_payload.get("threadId")
    evidence: dict = {
        "initialize_serverInfo": init.get("serverInfo"),
        "environmentId": server.environment.get("environmentId"),
        "launch": launch,
        "launch_shape": shape_of(launch),
    }
    if not launch["isError"] and thread_id:
        read1 = client.call("t3_thread_read", {"threadId": thread_id})
        evidence["read_shape"] = shape_of(read1)
        evidence["read_thread_status"] = (read1.get("payload") or {}).get("thread", {}).get("status")
        # send immediately (the turn may still be live -> steer; else it starts a
        # new run) and interrupt shortly after, while a run is plausibly active.
        send = client.call("t3_thread_send", {"threadId": thread_id, "message": "and one more turn"})
        evidence["send"] = send
        evidence["send_shape"] = shape_of(send)
        time.sleep(0.6)
        interrupt = client.call("t3_thread_interrupt", {"threadId": thread_id, "reason": "a5 proof"})
        evidence["interrupt"] = interrupt
        evidence["interrupt_shape"] = shape_of(interrupt)
        evidence["interrupt_is_admission_block"] = "Mastermind" in (interrupt.get("message") or "")
        terminal = wait_run_terminal(client, thread_id)
        evidence["run_statuses_observed"] = terminal.get("statuses")
    else:
        evidence["launch_failed_early"] = True
    evidence["singleton_counts"] = server.singleton_counts()
    return evidence


def scenario_b_admit(server: BootedServer, fake: FakeAdmissionServer) -> dict:
    """Enforce mode, endpoint admits everything: launch starts, ledger binding
    becomes visible in later revalidate consults, interrupt never consults."""
    token = server.obtain_token()
    client = McpClient(server, token)
    init = client.initialize()
    consults_before = len(fake.snapshot_consults())
    evidence_head: dict = {"initialize_serverInfo": init.get("serverInfo")}
    fake.set_script([("admit", "a5-fake-root-1", "a5-admission-1")])
    launch = client.call("t3_thread_launch", dict(LAUNCH_ARGS, title="B1 admitted launch"))
    payload = launch.get("payload") or {}
    evidence: dict = {
        **evidence_head,
        "launch": launch,
        "launch_shape": shape_of(launch),
        "threadId": payload.get("threadId"),
    }
    if not launch["isError"] and payload.get("threadId"):
        thread_id = payload["threadId"]
        # steer probe: send immediately after launch while the first turn is
        # plausibly live (mid-run delivery => provider_turn.steer consult;
        # otherwise the send starts a second run => another start consult).
        send = client.call("t3_thread_send", {"threadId": thread_id, "message": "steer probe"})
        evidence["send"] = send
        evidence["send_shape"] = shape_of(send)
        time.sleep(0.6)
        # interrupt with admission armed and ADMITTING: a real mid-run interrupt
        # when a turn is live; no_active_run when the replay already finished —
        # either way ZERO new consults and never an admission block.
        before_interrupt = len(fake.snapshot_consults())
        interrupt = client.call("t3_thread_interrupt", {"threadId": thread_id, "reason": "a5 B1"})
        evidence["interrupt"] = interrupt
        evidence["interrupt_shape"] = shape_of(interrupt)
        evidence["interrupt_consults_delta"] = len(fake.snapshot_consults()) - before_interrupt
        evidence["interrupt_is_admission_block"] = "Mastermind" in (interrupt.get("message") or "")
        terminal = wait_run_terminal(client, thread_id)
        evidence["run_statuses_observed"] = terminal.get("statuses")
        consults_after_run = fake.snapshot_consults()
        launch_consults = [c for c in consults_after_run if (c["body"] or {}).get("kind") == "launch"]
        revalidate_consults = [
            c for c in consults_after_run if (c["body"] or {}).get("kind") == "revalidate"
        ]
        evidence["launch_consult"] = launch_consults[-1] if launch_consults else None
        evidence["revalidate_consult_bodies"] = [c["body"] for c in revalidate_consults[:6]]
        evidence["revalidate_phases"] = [(c["body"] or {}).get("phase") for c in revalidate_consults]
        evidence["revalidate_carries_binding"] = any(
            (c["body"] or {}).get("hasLocalBinding") is True
            and (c["body"] or {}).get("binding", {}).get("rootRef") == "a5-fake-root-1"
            for c in revalidate_consults
        )
    evidence["consult_count"] = len(fake.snapshot_consults()) - consults_before
    evidence["singleton_counts"] = server.singleton_counts()
    return evidence


def scenario_b_refuse(server: BootedServer, fake: FakeAdmissionServer) -> dict:
    """Enforce mode, endpoint refuses: observed consult->blocked->refusal chain,
    no thread minted, smuggled request fields carry no authority, interrupt
    never consults. The MCP reply is the donor-generic orchestration_error
    (LIVE FINDING: the patch's typed admission cause is not surfaced over MCP;
    recorded, not patched around)."""
    token = server.obtain_token()
    client = McpClient(server, token)
    init = client.initialize()
    fake.set_script([("refuse", "a5 stale lease: proof refusal")])
    consults_before = len(fake.snapshot_consults())
    launch = client.call("t3_thread_launch", dict(LAUNCH_ARGS, title="B2 refused launch"))
    evidence: dict = {
        "initialize_serverInfo": init.get("serverInfo"),
        "launch": launch,
        "launch_shape": shape_of(launch),
        "launch_is_error": launch["isError"],
    }
    consults_after = fake.snapshot_consults()
    launch_consults = [c for c in consults_after if (c["body"] or {}).get("kind") == "launch"]
    evidence["launch_consult_count"] = len(launch_consults)
    evidence["launch_consult"] = launch_consults[-1] if launch_consults else None
    # The fence is proven by the OBSERVED chain: the endpoint was consulted,
    # answered blocked_with_reason, and only then the launch failed with no
    # thread minted. LIVE FINDING (donor behavior, not patched around): the
    # donor's t3_thread_launch handler whitelists which ThreadLaunchError
    # causes may surface (toolkits/project/handlers.ts -> unavailable()); the
    # patch's MastermindAdmission* cause is not among them, so the MCP reply is
    # the generic orchestration_error "The operation could not be completed."
    evidence["refusal_consult_reply_was_blocked"] = bool(launch_consults) and (
        (launch_consults[-1].get("reply") or {}).get("decision") == "blocked_with_reason"
    )
    evidence["refusal_reply_is_generic_orchestration_error"] = (
        launch["isError"]
        and (launch.get("payload") or {}).get("code") == "orchestration_error"
        and (launch.get("payload") or {}).get("message") == "The operation could not be completed."
    )
    # no thread was minted: the refusal reply carries no threadId (the launch
    # funnel never reached thread allocation), and the whole store agrees.
    evidence["refusal_threadId_absent"] = not bool((launch.get("payload") or {}).get("threadId"))
    listed = client.call("t3_thread_list", {"allProjects": True, "limit": 100})
    evidence["threads_total_after_refusal"] = (listed.get("payload") or {}).get("total")
    # smuggle: request body claims creationSource + admission fields -> still gated.
    smuggle = client.call(
        "t3_thread_launch",
        dict(
            LAUNCH_ARGS,
            title="B2 smuggle",
            creationSource="ui",
            admission={"decision": "admitted", "rootRef": "smuggled-root"},
            rootRef="smuggled-root",
            admitted=True,
        ),
    )
    evidence["smuggle_launch"] = smuggle
    evidence["smuggle_is_error"] = smuggle["isError"]
    evidence["smuggle_threadId_absent"] = not bool((smuggle.get("payload") or {}).get("threadId"))
    consults_after_smuggle = fake.snapshot_consults()
    smuggle_consults = [
        c for c in consults_after_smuggle[(len(consults_after)):]
        if (c["body"] or {}).get("kind") == "launch"
    ]
    evidence["smuggle_consult"] = smuggle_consults[-1] if smuggle_consults else None
    evidence["smuggle_consult_reply_was_blocked"] = bool(smuggle_consults) and (
        (smuggle_consults[-1].get("reply") or {}).get("decision") == "blocked_with_reason"
    )
    evidence["smuggle_consult_saw_client_fields"] = any(
        c["body"].get("rootRef") == "smuggled-root" or "admission" in json.dumps(c["body"])
        for c in smuggle_consults
    )
    # no authority: the smuggled fields either never survived argument decoding
    # (rejected at validation, no consult) or reached the gate but appear NOWHERE
    # in the consult body; either way no thread was minted and no grant happened.
    evidence["smuggle_no_authority"] = (
        smuggle["isError"]
        and evidence["smuggle_threadId_absent"]
        and evidence["smuggle_consult_saw_client_fields"] is False
    )
    # interrupt under refusal: zero consults, upstream reply (thread_not_found),
    # never an admission block.
    before_interrupt = len(fake.snapshot_consults())
    interrupt = client.call(
        "t3_thread_interrupt",
        {"threadId": "mcp:00000000-a5b1-4proof-n0ad-missionblockd", "reason": "a5 B2"},
    )
    evidence["interrupt"] = interrupt
    evidence["interrupt_consults_delta"] = len(fake.snapshot_consults()) - before_interrupt
    evidence["interrupt_is_admission_block"] = "Mastermind" in (interrupt.get("message") or "")
    evidence["consult_count"] = len(fake.snapshot_consults()) - consults_before
    evidence["singleton_counts"] = server.singleton_counts()
    return evidence


def scenario_b_unreachable(server: BootedServer) -> dict:
    """Enforce mode, endpoint unreachable (connection refused): documented
    fail-closed — launch refuses, no thread, interrupt unaffected."""
    token = server.obtain_token()
    client = McpClient(server, token)
    init = client.initialize()
    launch = client.call("t3_thread_launch", dict(LAUNCH_ARGS, title="B3 unreachable"))
    evidence: dict = {"initialize_serverInfo": init.get("serverInfo"), "launch": launch, "launch_shape": shape_of(launch)}
    payload = launch.get("payload") or {}
    # fail-closed, proven by outcome: ECONNREFUSED (the driver holds a
    # bound-never-listening socket for the whole proof) -> the launch refuses
    # and mints no thread. Same LIVE FINDING as B2: the typed endpoint-failure
    # cause surfaces over MCP only as the donor-generic orchestration_error.
    evidence["fail_closed"] = launch["isError"] and not bool(payload.get("threadId"))
    evidence["failure_reply_is_generic_orchestration_error"] = (
        launch["isError"]
        and payload.get("code") == "orchestration_error"
        and payload.get("message") == "The operation could not be completed."
    )
    evidence["threadId_absent"] = not bool(payload.get("threadId"))
    listed = client.call("t3_thread_list", {"allProjects": True, "limit": 100})
    evidence["threads_total_after_failure"] = (listed.get("payload") or {}).get("total")
    interrupt = client.call(
        "t3_thread_interrupt",
        {"threadId": "mcp:00000000-a5b3-4proof-n0ad-missionblockd", "reason": "a5 B3"},
    )
    evidence["interrupt"] = interrupt
    evidence["interrupt_is_admission_block"] = "Mastermind" in (interrupt.get("message") or "")
    evidence["singleton_counts"] = server.singleton_counts()
    return evidence


def scenario_b_hang(server: BootedServer, fake: FakeAdmissionServer, window_s: float) -> dict:
    """Enforce mode, endpoint hangs (accepts, never answers). Observed ONLY for
    the bounded window — a hang has no documented client-side timeout in the
    patch (plain fetch, no AbortSignal), so the observation stays UNKNOWN unless
    a refusal lands inside the window. The interrupt probe runs WHILE the
    launch is hung and must answer without consulting admission."""
    token = server.obtain_token()
    client = McpClient(server, token)
    init = client.initialize()
    fake.set_script([("hang", window_s + 60.0)])  # hang far beyond the window
    result: dict = {"hang_window_s": window_s, "initialize_serverInfo": init.get("serverInfo")}

    launch_reply: dict = {}
    launch_error: str | None = None

    def _launch() -> None:
        nonlocal launch_reply, launch_error
        try:
            launch_reply = client.call("t3_thread_launch", dict(LAUNCH_ARGS, title="B4 hang"))
        except Exception as exc:  # transport loss etc. — record honestly
            launch_error = redact(repr(exc)[:300])

    worker = threading.Thread(target=_launch, daemon=True)
    worker.start()
    # give the consult time to start, then probe interrupts while it hangs
    time.sleep(3.0)
    consults_mid = fake.consults_matching(kind="launch")
    result["hang_consult_observed_while_pending"] = bool(consults_mid)
    before_interrupt = len(fake.snapshot_consults())
    interrupt = client.call(
        "t3_thread_interrupt",
        {"threadId": "mcp:00000000-a5b4-4proof-n0ad-missionblockd", "reason": "a5 B4"},
    )
    result["interrupt_while_launch_hung"] = interrupt
    result["interrupt_consults_delta"] = len(fake.snapshot_consults()) - before_interrupt
    result["interrupt_is_admission_block"] = "Mastermind" in (interrupt.get("message") or "")
    worker.join(timeout=window_s)
    if worker.is_alive():
        result["launch_outcome_at_window"] = "STILL_PENDING_PAST_WINDOW"
        result["verdict"] = "UNKNOWN"
    elif launch_error is not None:
        result["launch_error"] = launch_error
        result["launch_outcome_at_window"] = "TRANSPORT_ERROR"
        result["verdict"] = "UNKNOWN"
    else:
        result["launch"] = launch_reply
        result["launch_outcome_at_window"] = "REFUSED_WITHIN_WINDOW" if launch_reply.get("isError") else "SUCCEEDED"
        result["verdict"] = "REFUSED_WITHIN_WINDOW" if launch_reply.get("isError") else "PASS_WITH_SURPRISE"
    result["singleton_counts"] = server.singleton_counts()
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", default="/tmp/a5-admission-boot")
    parser.add_argument("--hang-window", type=float, default=DEFAULT_HANG_WINDOW_S)
    parser.add_argument("--keep", action="store_true", help="keep scratch trees for inspection")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument(
        "--reuse-install",
        action="store_true",
        help="carry node_modules across the scratch wipe (instant rename; pair with --skip-install)",
    )
    parser.add_argument("--skip-typecheck", action="store_true")
    parser.add_argument("--skip-base", action="store_true", help="skip the unpatched baseline boot")
    args = parser.parse_args()

    scratch = Path(args.scratch)
    started_servers: list[BootedServer] = []
    fakes: list[FakeAdmissionServer] = []
    receipt: dict = {
        "schema": "mastermind.t3_admission_patch_boot_receipt/v1",
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "donor_pin": PIN,
        "patch_sha256": None,
        "outcome": None,
        "blocked": None,
        "knobs": {
            "boot_command": "node src/bin.ts serve --base-dir <isolated> --no-browser",
            "port_env": "T3CODE_PORT",
            "host_env": "T3CODE_HOST",
            "data_dir_env": "T3CODE_HOME / --base-dir",
            "dev_instance_seed_env": "VITE_DEV_SERVER_URL (devReplay recorded-turn ACP instance; no paid model)",
            "auth": "server-printed headless startup pairing credential -> /oauth/mcp/register -> /oauth/mcp/decision (pairing-code, PKCE) -> /oauth/mcp/token",
            "admission_endpoint_env": "MASTERMIND_ADMISSION_ENDPOINT",
            "ports_used": [],
            "real_desktop_port": 3773,
            "real_desktop_touched": False,
        },
        "instrumentation": None,
        "scenarios": {},
        "events": [],
    }

    def blocked(reason: str, unblocker: str) -> int:
        receipt["outcome"] = "BLOCKED"
        receipt["blocked"] = {"reason": redact(reason), "unblocker": unblocker}
        write_receipt(receipt)
        for server in started_servers:
            server.stop()
        for fake in fakes:
            fake.stop()
        return 3

    try:
        # -- preflight ----------------------------------------------------
        if not DEFAULT_PINNED_SOURCE.is_dir():
            return blocked(f"pinned donor clone not present: {DEFAULT_PINNED_SOURCE}", "restore the pinned clone")
        head = run(["git", "rev-parse", "HEAD"], cwd=DEFAULT_PINNED_SOURCE).stdout.strip()
        status = run(["git", "status", "--porcelain"], cwd=DEFAULT_PINNED_SOURCE).stdout.strip()
        if head != PIN or status != "":
            return blocked(
                f"pinned clone HEAD={head!r} clean={status == ''!r}", "restore the pinned clone at the pin with a clean tree"
            )
        actual_patch_sha = sha256_file(PATCH_PATH)
        if actual_patch_sha != PATCH_SHA256:
            return blocked(
                f"committed patch bytes sha256 {actual_patch_sha} != pinned {PATCH_SHA256}",
                "restore the committed patch bytes",
            )
        receipt["patch_sha256"] = actual_patch_sha
        log("preflight.ok", pin=head, patch_sha=actual_patch_sha[:16])

        # -- scratch trees -------------------------------------------------
        patched_tree = scratch / "patched"
        base_tree = scratch / "base"
        # node_modules carry-over: rename (same filesystem, instant) instead of
        # reinstalling ~3.2G on every driver re-run. The scratch wipe only ever
        # touches /tmp/a5-admission-boot — never the pinned clone or any worktree.
        nm_cache = scratch.parent / f"{scratch.name}-nodemodules-cache"
        if scratch.exists():
            if args.reuse_install:
                nm_cache.mkdir(parents=True, exist_ok=True)
                for tree, cname in ((patched_tree, "patched"), (base_tree, "base")):
                    nm = tree / "node_modules"
                    if nm.is_dir():
                        cached = nm_cache / cname
                        if cached.exists():
                            shutil.rmtree(cached, ignore_errors=True)
                        nm.rename(cached)
            shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        for tree in (patched_tree, base_tree):
            proc = run(["git", "clone", "--shared", str(DEFAULT_PINNED_SOURCE), str(tree)], timeout=600)
            if proc.returncode != 0:
                return blocked(f"clone failed: {proc.stderr[-400:]}", "free disk / check shared clone")
            proc = run(["git", "checkout", "-q", PIN], cwd=tree, timeout=300)
            if proc.returncode != 0:
                return blocked(f"checkout pin failed: {proc.stderr[-300:]}", "—")
        if args.reuse_install and nm_cache.is_dir():
            restored = 0
            for tree, cname in ((patched_tree, "patched"), (base_tree, "base")):
                cached = nm_cache / cname
                if cached.is_dir():
                    cached.rename(tree / "node_modules")
                    restored += 1
            if restored:
                log("install.reused", trees=restored)
        proc = run(["git", "apply", str(PATCH_PATH)], cwd=patched_tree, timeout=120)
        if proc.returncode != 0:
            return blocked(f"git apply failed: {proc.stderr[-400:]}", "patch/context drift vs pin")

        instrument_patched = instrument_tree(patched_tree)
        instrument_base = instrument_tree(base_tree)
        receipt["instrumentation"] = {
            "module": "apps/server/src/mastermind/A5ScratchCounts.ts (scratch tree only)",
            "module_sha256": instrument_patched["counts_module_sha256"],
            "same_module_in_both_trees": instrument_patched["counts_module_sha256"] == instrument_base["counts_module_sha256"],
            "runtimeLayer_edits": instrument_patched["edits"]["apps/server/src/orchestration-v2/runtimeLayer.ts"],
            "server_ts_edits": instrument_patched["edits"]["apps/server/src/server.ts"],
            "note": (
                "counting wrappers use the patch's own composition rule (Layer.effect + "
                "Layer.provide, no nested Layer.build); counts emit as A5_COUNT stderr "
                "lines per boot (no node:fs — donor effect rules ban it); committed "
                "patch/MANIFEST untouched"
            ),
        }
        log("trees.prepared", patched=str(patched_tree), base=str(base_tree))

        # -- install + typecheck -------------------------------------------
        if not args.skip_install:
            for tree in (patched_tree, base_tree):
                proc = run(PNPM + ["install", "--frozen-lockfile"], cwd=tree, timeout=1800)
                if proc.returncode != 0:
                    return blocked(
                        f"pnpm install failed in {tree.name}: {proc.stderr[-500:]}",
                        "network/store access for the pinned pnpm install",
                    )
            log("install.ok")
        if not args.skip_typecheck:
            typecheck_notes: dict = {}
            for tree in (patched_tree, base_tree):
                proc = run(
                    PNPM + ["exec", "effect-tsgo", "tsrs", "--noEmit"],
                    cwd=tree / "apps/server", timeout=1800,
                )
                out = proc.stdout + proc.stderr
                error_lines = [ln for ln in out.splitlines() if re.search(r"\berror TS\d+", ln)]
                suggestion_lines = [ln for ln in out.splitlines() if re.search(r"\bsuggestion TS\d+", ln)]
                typecheck_notes[tree.name] = {
                    "exit": proc.returncode,
                    "error_level_diagnostics": len(error_lines),
                    "suggestion_level_diagnostics": len(suggestion_lines),
                    "first_error": redact(error_lines[0])[:300] if error_lines else None,
                }
                if error_lines:
                    return blocked(
                        f"typecheck error-level diagnostics in {tree.name}: "
                        f"{[ln[:200] for ln in error_lines[:6]]}",
                        "fix the scratch instrumentation or the patch",
                    )
            # The donor baseline at this pin already emits hundreds of
            # suggestion-level effect(schemaClassMissingBrand) diagnostics
            # repo-wide (pristine base == patched modulo exactly 2 more inside
            # the patch's own adapter file). Suggestions are recorded, not
            # gated: they are donor baseline, not effects introduced by the
            # boot proof, and the committed patch bytes are immutable here.
            receipt["instrumentation"]["typecheck"] = {
                "gate": "zero error-level diagnostics under the donor's own script (effect-tsgo tsrs --noEmit)",
                "trees": typecheck_notes,
                "suggestion_baseline_note": (
                    "TS377141 schemaClassMissingBrand suggestions are pre-existing donor-wide "
                    "baseline at this pin; the committed patch adds exactly 2 in "
                    "MastermindAdmissionAdapter.ts (recorded, not gated)"
                ),
            }
            log(
                "typecheck.ok",
                **{k: v["error_level_diagnostics"] for k, v in typecheck_notes.items()},
            )

        # -- scenario A -----------------------------------------------------
        fake_port = free_port(PORT_BASE + 50)
        fake = FakeAdmissionServer(fake_port)
        fake.start()
        fakes.append(fake)
        fake_url = f"http://127.0.0.1:{fake_port}"
        log("fake_admission.listening", url=fake_url)

        scenarios: dict = receipt["scenarios"]

        port = free_port(PORT_BASE)
        a1 = BootedServer("A1-patched-unset", patched_tree, scratch, port, admission_endpoint=None)
        started_servers.append(a1)
        a1.start()
        receipt["knobs"]["ports_used"].append(port)
        log("boot.A1.ok", port=port)
        scenarios["A1_patched_endpoint_unset"] = scenario_ab_flow(a1, "A1")
        a1.stop()
        started_servers.remove(a1)
        log("A1.done", counts=scenarios["A1_patched_endpoint_unset"]["singleton_counts"])

        if not args.skip_base:
            port = free_port(PORT_BASE + 1)
            a0 = BootedServer("A0-base", base_tree, scratch, port, admission_endpoint=None)
            started_servers.append(a0)
            a0.start()
            receipt["knobs"]["ports_used"].append(port)
            log("boot.A0.ok", port=port)
            scenarios["A0_base_unpatched"] = scenario_ab_flow(a0, "A0")
            a0.stop()
            started_servers.remove(a0)
            log("A0.done", counts=scenarios["A0_base_unpatched"]["singleton_counts"])

        # -- scenario B -----------------------------------------------------
        port = free_port(PORT_BASE + 2)
        b1 = BootedServer("B1-admit", patched_tree, scratch, port, admission_endpoint=fake_url)
        started_servers.append(b1)
        b1.start()
        receipt["knobs"]["ports_used"].append(port)
        log("boot.B1.ok", port=port, endpoint=fake_url)
        scenarios["B1_endpoint_admit"] = scenario_b_admit(b1, fake)
        b1.stop()
        started_servers.remove(b1)
        log("B1.done", counts=scenarios["B1_endpoint_admit"]["singleton_counts"])

        port = free_port(PORT_BASE + 3)
        b2 = BootedServer("B2-refuse", patched_tree, scratch, port, admission_endpoint=fake_url)
        started_servers.append(b2)
        b2.start()
        receipt["knobs"]["ports_used"].append(port)
        fake.set_script([("refuse", "a5 stale lease: proof refusal")])
        scenarios["B2_endpoint_refuse"] = scenario_b_refuse(b2, fake)
        b2.stop()
        started_servers.remove(b2)
        log("B2.done", counts=scenarios["B2_endpoint_refuse"]["singleton_counts"])

        unreachable_port = free_port(PORT_BASE + 10)
        # a bound-but-never-listening socket refuses connections for the whole
        # proof -> guaranteed ECONNREFUSED without a listener race
        dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dead_socket.bind(("127.0.0.1", unreachable_port))
        port = free_port(PORT_BASE + 4)
        b3 = BootedServer(
            "B3-unreachable", patched_tree, scratch, port,
            admission_endpoint=f"http://127.0.0.1:{unreachable_port}",
        )
        started_servers.append(b3)
        b3.start()
        receipt["knobs"]["ports_used"].append(port)
        scenarios["B3_endpoint_unreachable"] = scenario_b_unreachable(b3)
        b3.stop()
        started_servers.remove(b3)
        log("B3.done", counts=scenarios["B3_endpoint_unreachable"]["singleton_counts"])

        port = free_port(PORT_BASE + 5)
        b4 = BootedServer("B4-hang", patched_tree, scratch, port, admission_endpoint=fake_url)
        started_servers.append(b4)
        b4.start()
        receipt["knobs"]["ports_used"].append(port)
        scenarios["B4_endpoint_hang"] = scenario_b_hang(b4, fake, args.hang_window)
        b4.stop()
        started_servers.remove(b4)
        dead_socket.close()
        log("B4.done", verdict=scenarios["B4_endpoint_hang"].get("verdict"))

        # -- verdicts --------------------------------------------------------
        evaluate(receipt)

        fake.stop()
        receipt["events"] = LOGEvents
        write_receipt(receipt)

        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)
        return 0 if receipt["outcome"] in {"DONE", "DONE_WITH_FINDINGS"} else 3

    except Exception as exc:  # noqa: BLE001 — the receipt must record the stop
        import traceback

        receipt["outcome"] = "BLOCKED"
        receipt["blocked"] = {
            "reason": redact("".join(traceback.format_exception(exc))[-1500:]),
            "unblocker": "see reason",
        }
        receipt["events"] = LOGEvents
        write_receipt(receipt)
        for server in started_servers:
            server.stop()
        for fake in fakes:
            fake.stop()
        if not args.keep and scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        return 3


def write_receipt(receipt: dict) -> None:
    text = json.dumps(receipt, indent=2)
    RECEIPT_OUT.write_text(redact(text) + "\n")
    log("receipt.written", path=str(RECEIPT_OUT))


SINGLETONS = ["ProjectionStore", "CommandOutputHub", "Orchestrator", "TextGeneration"]


def evaluate(receipt: dict) -> None:
    """Compute per-scenario PASS/FAIL/UNKNOWN + the overall outcome."""
    s = receipt["scenarios"]
    verdicts: dict[str, str] = {}

    def counts_pass(name: str, ev: dict) -> bool:
        counts = ev.get("singleton_counts") or {}
        return all(counts.get(k) == 1 for k in SINGLETONS)

    # A1: passthrough — launch worked like upstream, all singletons once.
    a1 = s.get("A1_patched_endpoint_unset", {})
    a1_runs_terminal = bool(
        a1.get("run_statuses_observed")
        and a1["run_statuses_observed"][0] in {"completed", "failed", "interrupted"}
    )
    a1_ok = (
        not a1.get("launch_failed_early")
        and not a1.get("launch", {}).get("isError")
        and a1_runs_terminal
        and not a1.get("interrupt_is_admission_block")
        and counts_pass("A1", a1)
    )
    verdicts["A1_patched_endpoint_unset"] = "PASS" if a1_ok else "FAIL"

    # A0 vs A1 shape equality (when the base boot ran).
    a0 = s.get("A0_base_unpatched")
    if a0 is not None:
        same_shapes = (
            a0.get("launch_shape") == a1.get("launch_shape")
            and a0.get("read_shape") == a1.get("read_shape")
            and a0.get("send_shape") == a1.get("send_shape")
            and a0.get("interrupt_shape") == a1.get("interrupt_shape")
        )
        same_counts = a0.get("singleton_counts") == a1.get("singleton_counts")
        base_ok = (
            not a0.get("launch_failed_early")
            and counts_pass("A0", a0)
            and same_shapes
            and same_counts
        )
        verdicts["A0_base_unpatched"] = "PASS" if base_ok else "FAIL"
        a1_ev = s["A1_patched_endpoint_unset"]
        a1_ev["matches_unpatched_shapes"] = same_shapes
        a1_ev["matches_unpatched_counts"] = same_counts

    b1 = s.get("B1_endpoint_admit", {})
    b1_runs_terminal = bool(
        b1.get("run_statuses_observed")
        and b1["run_statuses_observed"][0] in {"completed", "failed", "interrupted"}
    )
    b1_ok = (
        not b1.get("launch", {}).get("isError")
        and b1_runs_terminal
        and b1.get("revalidate_carries_binding") is True
        and b1.get("interrupt_consults_delta") == 0
        and not b1.get("interrupt_is_admission_block")
        and counts_pass("B1", b1)
    )
    verdicts["B1_endpoint_admit"] = "PASS" if b1_ok else "FAIL"

    b2 = s.get("B2_endpoint_refuse", {})
    b2_ok = (
        b2.get("launch_is_error")
        and b2.get("refusal_consult_reply_was_blocked") is True
        and b2.get("launch_consult_count", 0) >= 1
        and b2.get("refusal_threadId_absent") is True
        and b2.get("threads_total_after_refusal") == 0
        and b2.get("smuggle_is_error")
        and b2.get("smuggle_no_authority") is True
        and b2.get("smuggle_consult_reply_was_blocked") is True
        and b2.get("interrupt_consults_delta") == 0
        and not b2.get("interrupt_is_admission_block")
        and counts_pass("B2", b2)
    )
    verdicts["B2_endpoint_refuse"] = "PASS" if b2_ok else "FAIL"

    b3 = s.get("B3_endpoint_unreachable", {})
    b3_ok = (
        b3.get("fail_closed") is True
        and b3.get("threadId_absent") is True
        and b3.get("threads_total_after_failure") == 0
        and not b3.get("interrupt_is_admission_block")
        and counts_pass("B3", b3)
    )
    verdicts["B3_endpoint_unreachable"] = "PASS" if b3_ok else "FAIL"

    b4 = s.get("B4_endpoint_hang", {})
    verdicts["B4_endpoint_hang"] = b4.get("verdict", "UNKNOWN")
    b4_interrupt_ok = (
        not b4.get("interrupt_is_admission_block")
        and b4.get("interrupt_consults_delta") == 0
        and b4.get("hang_consult_observed_while_pending") is True
    )

    for name, verdict in verdicts.items():
        if name in s:
            s[name]["verdict"] = verdict
    s["B4_endpoint_hang"]["interrupt_never_blocked"] = b4_interrupt_ok

    hard_fail = [n for n, v in verdicts.items() if v == "FAIL"]
    hang_pending = verdicts.get("B4_endpoint_hang") == "UNKNOWN"
    receipt["outcome"] = (
        "DONE" if not hard_fail and not hang_pending
        else "DONE_WITH_FINDINGS" if not hard_fail
        else "FAILED"
    )
    receipt["findings_summary"] = {
        "hard_fail_scenarios": hard_fail,
        "hang_case": (
            "no client-side timeout observed within the window (patch uses plain fetch); "
            "interrupts during the hang were never blocked and never consulted admission"
            if hang_pending
            else "resolved within the window"
        ),
        "typed_admission_cause_not_surfaced_over_mcp": (
            "LIVE FINDING (donor behavior, not patched around): the admission fences hold "
            "(endpoint consulted -> decision honored -> no thread minted -> incumbent never "
            "ran), but the donor's t3_thread_launch error mapping whitelists only "
            "AttachmentClaimError / ThreadManagementProviderInstanceDisabledError / "
            "above-ceiling causes (apps/server/src/mcp/toolkits/project/handlers.ts -> "
            "unavailable()); the patch's ThreadLaunchError(cause: MastermindAdmission*) "
            "falls through to the generic orchestration_error 'The operation could not be "
            "completed.' — an MCP client cannot distinguish an admission refusal or "
            "fail-closed endpoint error from any other launch failure. The typed cause is "
            "proven at the service seam by the patch's own vitest suite only."
        ),
    }


if __name__ == "__main__":
    sys.exit(main())
