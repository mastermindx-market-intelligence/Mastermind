#!/usr/bin/env python3
"""Mastermind Slack Gateway — one app, many agent identities.

Slack's free plan caps a workspace at 10 installed apps, so "one Slack app per
agent" does not scale. This gateway keeps ONE app as the transport and gives
each agent its own identity in one of two modes:

  user  — the agent has its own Slack member account that authorized the app,
          so we hold that member's xoxp- user token: messages are posted AS
          that account (native name, avatar, profile). No override needed.
  bot   — no member account yet: we post with the shared bot token and pass
          chat:write.customize username + icon_emoji, which Slack renders as a
          per-message display identity.

Agents flip from bot to user mode the moment their token file appears — no code
change, no extra app. That keeps the installation count at 1 while identity
stays per-agent.

One process owns the single Socket Mode socket (concurrent clients on the same
app steal each other's events), routes inbound mentions/DMs/channel messages to
a Hermes profile, dispatches the turn, and answers in-thread under the agent's
own identity.

A loopback HTTP control API lets Mastermind OS (or anything local) send as any
agent and read fleet health.

Secrets live only in 0600 env files and are never printed or passed on argv.

Usage:
  slack_gateway.py run                 # foreground / launchd
  slack_gateway.py status              # registry, identities, tokens, log tail
  slack_gateway.py agents              # compact identity table
  slack_gateway.py route "delivery: x" # dry-run the router
  slack_gateway.py send <agent> <channel_id> "text"
  slack_gateway.py http                # foreground HTTP-only (no socket)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
SECRETS = HOME / ".hermes" / "secrets"
CONF_DIR = HOME / ".hermes" / "slack-fleet"
CONF_PATH = CONF_DIR / "agents.json"
LEGACY_CONF = CONF_DIR / "relay.json"
STATE_PATH = CONF_DIR / "relay-state.json"
LOG_PATH = HOME / ".hermes" / "logs" / "slack-gateway.log"

DEFAULT_CONF = {
    "default_agent": "engineering",
    # one entry per Slack app we drive; "main" is the shared Socket Mode transport.
    # extra entries let an agent own a real bot handle without another receiver.
    "apps": {
        "main": {
            "bot_token_file": "slack-mastermind-executive.env",
            "app_token_file": "slack-mastermind-executive-app.env",
            "bot_user_id": "U0BT71H4FQE",
            "app_id": "A0BTCKA7GSY",
            "socket_mode": True,
        },
    },
    "bot": {
        "token_file": "slack-mastermind-executive.env",
        "app_token_file": "slack-mastermind-executive-app.env",
        "bot_user_id": "U0BT71H4FQE",
    },
    "agents": {
        "engineering": {"profile": "engineering", "display_name": "Engineering Lead (CTO)", "emoji": ":mechanical_arm:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "assurance": {"profile": "assurance", "display_name": "Assurance & Security Lead", "emoji": ":shield:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "delivery": {"profile": "delivery", "display_name": "Delivery Lead (COO)", "emoji": ":rocket:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "intelligence": {"profile": "intelligence", "display_name": "Intelligence & Data Quality Lead", "emoji": ":bar_chart:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "product": {"profile": "product", "display_name": "Product & Design Lead", "emoji": ":art:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "reliability": {"profile": "reliability", "display_name": "Reliability & Capacity Lead", "emoji": ":satellite:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "chief-of-staff": {"profile": "chief-of-staff", "display_name": "Chief of Staff", "emoji": ":clipboard:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "secretary": {"profile": "secretary", "display_name": "Secretary", "emoji": ":memo:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
        "meta-ceo": {"profile": "meta-ceo-uncensored", "display_name": "Meta-CEO", "emoji": ":crown:", "slack_user_id": None, "user_token_file": None, "channels": [], "dm": True},
    },
    "mention_aliases": {
        "engineering": "engineering", "cto": "engineering", "eng": "engineering",
        "assurance": "assurance", "security": "assurance", "audit": "assurance",
        "delivery": "delivery", "coo": "delivery", "release": "delivery",
        "intelligence": "intelligence", "intel": "intelligence", "data": "intelligence",
        "product": "product", "design": "product",
        "reliability": "reliability", "finops": "reliability", "sre": "reliability",
        "chief of staff": "chief-of-staff", "cos": "chief-of-staff",
        "secretary": "secretary",
        "meta-ceo": "meta-ceo", "meta ceo": "meta-ceo", "ceo": "meta-ceo",
    },
    "channels": {},
    "dm_agents": {},
    "allowed_users": [],
    "allow_bots": [],
    "max_dispatches_per_minute": 6,
    "dispatch": {"model": "code-flash", "timeout_s": 420, "placeholder": True, "reply_in_thread": True},
    "http": {"host": "127.0.0.1", "port": 8791, "token_file": "slack-gateway-http.env"},
    "ack_reaction": "eyes",
    "done_reaction": "white_check_mark",
}


# --------------------------------------------------------------- plumbing ----
def log(event: str, **fields) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event}
    for k, v in fields.items():
        rec["msg_ts" if k == "ts" else k] = v
    try:
        with LOG_PATH.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def read_env(name: str) -> dict:
    path = Path(name) if os.path.isabs(name) else SECRETS / name
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def merge(base: dict, over: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load_conf(path: Path | None = None) -> dict:
    target = path or CONF_PATH
    if target.exists():
        try:
            return merge(DEFAULT_CONF, json.loads(target.read_text()))
        except Exception as exc:  # noqa: BLE001
            log("conf_parse_error", error=str(exc))
            return json.loads(json.dumps(DEFAULT_CONF))
    if path is None:
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        source = DEFAULT_CONF
        if LEGACY_CONF.exists():  # migrate the first-generation relay config
            try:
                old = json.loads(LEGACY_CONF.read_text())
                source = merge(DEFAULT_CONF, {
                    "default_agent": old.get("default_profile", DEFAULT_CONF["default_agent"]),
                    "channels": old.get("channels", {}),
                    "dm_agents": old.get("dm_profiles", {}),
                    "mention_aliases": old.get("mention_aliases", {}),
                    "allowed_users": old.get("allowed_users", []),
                    "allow_bots": old.get("allow_bots", []),
                    "dispatch": {
                        "model": old.get("dispatch_model", "code-flash"),
                        "timeout_s": old.get("dispatch_timeout_s", 420),
                        "placeholder": old.get("placeholder", True),
                        "reply_in_thread": old.get("reply_in_thread", True),
                    },
                })
                log("migrated_legacy_conf", source=str(LEGACY_CONF))
            except Exception:
                pass
        CONF_PATH.write_text(json.dumps(source, indent=2))
        os.chmod(CONF_PATH, 0o600)
        return source
    return merge(DEFAULT_CONF, {})


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen": {}, "sessions": {}, "recent": {}}


AUDIT_PATH = CONF_DIR.parent / "logs" / "slack-agent-audit.jsonl"


def audit(conf: dict, **rec) -> None:
    """Append one provenance record per dispatch; Slack's own history is not a store of record."""
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec["team_id"] = (conf.get("apps") or {}).get("main", {}).get("team_id", "T0BRD2AQXQV")
        with AUDIT_PATH.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        os.chmod(AUDIT_PATH, 0o600)
    except Exception as exc:  # noqa: BLE001
        log("audit_failed", error=str(exc)[:200])


def save_state(state: dict) -> None:
    seen = state.get("seen", {})
    if len(seen) > 4000:
        for key in sorted(seen, key=lambda k: seen[k])[: len(seen) - 3000]:
            seen.pop(key, None)
    outbound = state.get("outbound", {})
    if len(outbound) > 4000:
        cutoff = time.time() - 86400
        for k in [k for k, v in outbound.items() if v < cutoff][: 2000]:
            outbound.pop(k, None)
    recent = state.get("recent", {})
    now = time.time()
    for ch in list(recent):
        recent[ch] = [t for t in recent[ch] if now - t < 300]
        if not recent[ch]:
            recent.pop(ch, None)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.chmod(tmp, 0o600)
    tmp.replace(STATE_PATH)


# ------------------------------------------------------------- identities ----
def agent_identity(conf: dict, agent: str) -> dict:
    rec = (conf.get("agents") or {}).get(agent) or {}
    profile = rec.get("profile") or agent
    # On M2 the pre-repair 0600 roster still names the nonexistent "hermes"
    # profile for Meta-CEO. Its chartered native profile is enrolled as
    # "meta-ceo-uncensored". Preserve the existing owner's roster on disk;
    # interpret this one known legacy alias at its consumption boundary.
    if agent == "meta-ceo" and profile == "hermes":
        profile = "meta-ceo-uncensored"
    return {
        "agent": agent,
        "profile": profile,
        "display_name": rec.get("display_name") or agent,
        "emoji": rec.get("emoji") or ":robot_face:",
        "slack_user_id": rec.get("slack_user_id"),
        "user_token_file": rec.get("user_token_file"),
        "channels": rec.get("channels") or [],
        "dm": rec.get("dm", True),
    }


def agent_app(conf: dict, agent: str) -> str:
    """Which transport app this agent posts through ('main' = the shared app)."""
    rec = (conf.get("agents") or {}).get(agent) or {}
    return rec.get("app") or "main"


def identity_mode(conf: dict, agent: str) -> tuple[str, str | None]:
    """Resolution order: own Slack account > own bot app > shared bot + display override."""
    ident = agent_identity(conf, agent)
    tf = ident.get("user_token_file")
    if tf:
        tok = read_env(tf).get("SLACK_USER_TOKEN")
        if tok:
            return "user", tok
    app = agent_app(conf, agent)
    if app != "main" and app in (conf.get("apps") or {}):
        return "app", read_env((conf["apps"][app] or {}).get("bot_token_file", "")).get("SLACK_BOT_TOKEN")
    return "bot", None


class Sender:
    """Posts messages as the right identity, over the shared app."""

    def __init__(self, conf: dict, web_client_factory, bot_token: str):
        self.conf = conf
        self._factory = web_client_factory
        self.bot = web_client_factory(bot_token)
        self._user_clients: dict[str, object] = {}
        self._app_clients: dict[str, object] = {}
        self._lock = threading.Lock()
        self.on_post = None  # set by Fleet: records outbound ts values
        for name, rec in (conf.get("apps") or {}).items():
            if name == "main":
                continue
            tok = read_env((rec or {}).get("bot_token_file", "")).get("SLACK_BOT_TOKEN")
            if tok:
                self._app_clients[name] = web_client_factory(tok)

    def client_for(self, agent: str):
        mode, token = identity_mode(self.conf, agent)
        if mode == "user" and token:
            with self._lock:
                if agent not in self._user_clients:
                    self._user_clients[agent] = self._factory(token)
                return self._user_clients[agent], "user"
        if mode == "app":
            app = agent_app(self.conf, agent)
            client = self._app_clients.get(app)
            if client is not None:
                return client, "app"
            log("app_transport_missing", agent=agent, app=app)
        return self.bot, "bot"

    def post(self, agent: str, channel: str, text: str, thread_ts: str | None = None,
             run_id: str = "") -> str | None:
        client, mode = self.client_for(agent)
        ident = agent_identity(self.conf, agent)
        kwargs = {"channel": channel, "text": text[:39000]}
        # machine-readable provenance: the author stays the shared bot, the run does not
        kwargs["metadata"] = json.dumps({
            "event_type": "hermes_agent_reply",
            "event_payload": {"agent_id": agent, "profile": ident["profile"],
                              "identity_mode": mode, "run_id": run_id or "unset",
                              "schema_version": 1},
        })
        if mode == "bot":
            kwargs["username"] = ident["display_name"]
            kwargs["icon_emoji"] = ident["emoji"]
        if thread_ts and self.conf.get("dispatch", {}).get("reply_in_thread", True):
            kwargs["thread_ts"] = thread_ts
        try:
            resp = client.chat_postMessage(**kwargs)
            if not resp.get("ok"):
                log("post_failed", agent=agent, mode=mode, error=resp.get("error"))
                return None
            ts = resp.get("ts")
            if ts and self.on_post:
                self.on_post(ts)
            return ts
        except Exception as exc:  # noqa: BLE001
            log("post_exception", agent=agent, error=str(exc)[:300])
            return None

    def update(self, agent: str, channel: str, ts: str, text: str) -> bool:
        client, _ = self.client_for(agent)
        try:
            return bool(client.chat_update(channel=channel, ts=ts, text=text[:39000]).get("ok"))
        except Exception as exc:  # noqa: BLE001
            log("update_exception", agent=agent, error=str(exc)[:300])
            return False


# ------------------------------------------------------------------ routing ----
def strip_mentions(text: str) -> str:
    return re.sub(r"<@[A-Z0-9]+>", " ", text or "").strip()


def mentioned_user_ids(text: str) -> list[str]:
    return re.findall(r"<@([A-Z0-9]+)>", text or "")


def routable(conf: dict) -> dict:
    """Agents that may RECEIVE work (send-only identities are excluded)."""
    return {k: v for k, v in (conf.get("agents") or {}).items() if not v.get("send_only")}


def route(conf: dict, *, text: str, channel: str, user: str, is_dm: bool,
          authorizations: list[str] | None = None, binding: str | None = None) -> tuple[str, str]:
    agents = routable(conf)
    # 0) A bound thread follows its last explicitly selected agent. A human
    # can transfer focus by *mentioning this real shared bot* and writing a
    # role selector at the start: <@Relay> engineering: please review.
    # Bare role words or a mention of an unrelated Slack account never steal
    # a thread. Native session IDs are independently keyed per role below.
    if binding and binding in agents:
        own_ids = {conf.get("bot", {}).get("bot_user_id")}
        own_ids.update(rec.get("bot_user_id") for rec in (conf.get("apps") or {}).values())
        own_ids.discard(None)
        if set(mentioned_user_ids(text)) & own_ids:
            addressed_body = strip_mentions(text).strip().lower()
            for alias in sorted((conf.get("mention_aliases") or {}), key=len, reverse=True):
                role = conf["mention_aliases"][alias]
                if role in agents and addressed_body.startswith(alias.lower() + ":"):
                    return role, "explicit-role-switch" if role != binding else "thread-binding"
        return binding, "thread-binding"
    # 1) addressed to an agent that has its own Slack account
    for uid in mentioned_user_ids(text):
        for agent, rec in agents.items():
            if (rec.get("slack_user_id") == uid
                    and rec.get("route_on_mention", True)
                    and identity_mode(conf, agent)[0] == "user"):
                return agent, "mention:account"
    # 2) DM that arrived on an agent's own user token
    if is_dm and authorizations:
        for agent, rec in agents.items():
            if (rec.get("slack_user_id") in authorizations
                    and identity_mode(conf, agent)[0] == "user"):
                return agent, "dm:own-token"
    # 3) dm_agents map (user id -> agent), then channel map
    if user in (conf.get("dm_agents") or {}):
        return conf["dm_agents"][user], "dm-user"
    if channel in (conf.get("channels") or {}):
        return conf["channels"][channel], "channel-map"
    for agent, rec in agents.items():
        if channel in (rec.get("channels") or []):
            return agent, "agent-channel"
    # 4) alias in the text (longest alias first: "chief of staff" beats "cos")
    body = strip_mentions(text).lower()
    for alias in sorted((conf.get("mention_aliases") or {}), key=len, reverse=True):
        if re.search(r"(^|[^a-z0-9])" + re.escape(alias) + r"([^a-z0-9]|$)", body):
            return conf["mention_aliases"][alias], f"alias:{alias}"
    return conf.get("default_agent", "engineering"), "dm-default" if is_dm else "default"


# ----------------------------------------------------------------- dispatch ----
def dispatch(profile: str, prompt: str, session_id: str | None, timeout: int,
             model: str = "") -> tuple[bool, str, str | None]:
    env = dict(os.environ)
    env["HERMES_PROFILE"] = profile
    env.pop("HERMES_HOME", None)
    # Per-turn O_EXCL secure temp files prevent simultaneous roles in this
    # multi-thread gateway from overwriting or reading another role's prompt.
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".prompt-", suffix=".txt",
        dir=CONF_DIR, delete=False,
    ) as prompt_file:
        qfile = Path(prompt_file.name)
        prompt_file.write(prompt)
    # Hermes selects its actual memory/credentials through --profile/HERMES_HOME.
    # HERMES_PROFILE alone is only an agent label and can silently use the
    # default home for every Slack role. Resolve via the native strict CLI.
    cmd = ["hermes", "--profile", profile, "chat", "--query-file", str(qfile), "--oneshot", "-Q"]
    if session_id:
        cmd += ["--resume", session_id]
    if model:
        cmd += ["-m", model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s", None
    finally:
        try:
            qfile.unlink()
        except Exception:
            pass
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    sid = None
    # Hermes -Q emits the exact session-id receipt to stderr, not stdout.
    # Keep stdout strictly as user-facing assistant text; stderr is diagnostic.
    m = re.search(r"(?m)^session_id:\s*([A-Za-z0-9_-]{8,160})\s*$", err)
    if m:
        sid = m.group(1)
    else:
        # Preserve compatibility with older Hermes releases which printed
        # the receipt on stdout. Do not accidentally include it in the reply.
        m = re.search(r"(?m)^session_id:\s*([A-Za-z0-9_-]{8,160})\s*$", out)
        if m:
            sid = m.group(1)
            out = (out[:m.start()] + out[m.end():]).strip()
    if proc.returncode != 0:
        return False, (err or f"hermes exited {proc.returncode}")[-1500:], sid
    return True, out or "(no output)", sid


# ---------------------------------------------------------------- the fleet ----
class Fleet:
    def __init__(self, conf: dict):
        from slack_sdk import WebClient

        self.conf = conf
        self.state = load_state()
        self.lock = threading.Lock()
        # Same-Slack-thread Hermes turns must serialize before reading the
        # resumable native ID; otherwise two workers may both start fresh.
        # This holds only mutual-exclusion state, not another durable queue.
        self._turn_gates: dict[str, tuple[threading.Lock, int]] = {}
        bot = read_env(conf["bot"]["token_file"]).get("SLACK_BOT_TOKEN")
        app = read_env(conf["bot"]["app_token_file"]).get("SLACK_APP_TOKEN")
        if not bot or not app:
            raise SystemExit("missing Slack token files in ~/.hermes/secrets")
        self.bot_token = bot
        self.app_token = app
        self.web = WebClient(token=bot)
        self.sender = Sender(conf, WebClient, bot)
        self.sender.on_post = self._record_outbound
        apps = conf.get("apps") or {}
        if "main" not in apps:            # legacy config: synthesize from "bot"
            apps["main"] = {"bot_token_file": conf["bot"]["token_file"],
                            "app_token_file": conf["bot"]["app_token_file"],
                            "bot_user_id": conf["bot"].get("bot_user_id"), "socket_mode": True}
            conf["apps"] = apps
        self.apps = apps
        self.our_bot_users = {r.get("bot_user_id") for r in apps.values() if r.get("bot_user_id")}
        self.our_bot_users.add(conf["bot"].get("bot_user_id"))
        self.bot_user_id = conf["bot"].get("bot_user_id")

    def _record_outbound(self, ts: str) -> None:
        with self.lock:
            self.state.setdefault("outbound", {})[ts] = time.time()
            save_state(self.state)

    # -- turn handling -------------------------------------------------------
    def say(self, agent: str, channel: str, text: str, thread_ts: str | None = None,
            run_id: str = "") -> str | None:
        return self.sender.post(agent, channel, text, thread_ts, run_id)

    def work(self, event: dict, agent: str, reason: str, authorizations: list[str]) -> None:
        channel = event.get("channel", "")
        root = event.get("thread_ts") or event.get("ts") or ""
        # Slash invocations have no root until the original placeholder is
        # posted; each invocation is independent and does not share a gate.
        key = f"{channel}:{root}" if root else ""
        if not key:
            return self._work_serialized(event, agent, reason, authorizations)
        with self.lock:
            if key in self._turn_gates:
                turn_lock, n = self._turn_gates[key]
                self._turn_gates[key] = (turn_lock, n + 1)
            else:
                turn_lock = threading.Lock()
                self._turn_gates[key] = (turn_lock, 1)
        try:
            with turn_lock:
                # Read the latest session ID only after the previous thread
                # worker has finished and durably saved its receipt.
                return self._work_serialized(event, agent, reason, authorizations)
        finally:
            with self.lock:
                current_lock, n = self._turn_gates[key]
                if current_lock is turn_lock and n == 1:
                    del self._turn_gates[key]
                elif current_lock is turn_lock:
                    self._turn_gates[key] = (turn_lock, n - 1)

    def _work_serialized(self, event: dict, agent: str, reason: str, authorizations: list[str]) -> None:
        conf = self.conf
        dconf = conf.get("dispatch") or {}
        channel = event.get("channel", "")
        ts = event.get("ts", "")
        text = event.get("text", "") or ""
        thread_ts = event.get("thread_ts") or ts or ""
        prompt = strip_mentions(text).strip() or "(empty message)"
        run_id = f"{agent}-{int(time.time())}-{uuid.uuid4().hex[:12]}"
        placeholder = None
        if not thread_ts:  # slash invocation: our own placeholder becomes the thread root
            if dconf.get("placeholder", True):
                placeholder = self.say(agent, channel, ":hourglass_flowing_sand: _working on it…_", None, run_id)
                thread_ts = placeholder or ""
        conv_key = f"{channel}:{thread_ts}"
        # Every independent role has its own native Hermes session for this
        # shared Slack thread. A role switch must never pass Secretary's
        # session ID to Engineering or vice versa. A matching old single-role
        # binding can still resume a legacy (pre-migration) stored session ID.
        session_key = f"{conv_key}:{agent}"
        with self.lock:
            sessions = self.state.get("sessions") or {}
            old_binding = (self.state.get("bindings") or {}).get(conv_key)
            sid = sessions.get(session_key)
            if sid is None and old_binding == agent:
                sid = sessions.get(conv_key)
            if thread_ts:
                self.state.setdefault("bindings", {})[conv_key] = agent
                save_state(self.state)
        log("dispatch", agent=agent, reason=reason, channel=channel, ts=ts, run_id=run_id,
            thread=thread_ts, chars=len(prompt), resume=bool(sid), mode=identity_mode(conf, agent)[0])
        self._react(channel, ts, conf.get("ack_reaction"))
        if thread_ts and dconf.get("placeholder", True) and placeholder is None:
            placeholder = self.say(agent, channel, ":hourglass_flowing_sand: _working on it…_", thread_ts, run_id)
        started = time.time()
        ok, reply, new_sid = dispatch(agent_identity(conf, agent)["profile"], prompt, sid,
                                      int(dconf.get("timeout_s", 420)), str(dconf.get("model") or ""))
        # A failed/ambiguous native turn cannot advance a thread's canonical
        # resume pointer merely because its stderr printed a session ID.
        if ok and new_sid:
            with self.lock:
                self.state.setdefault("sessions", {})[session_key] = new_sid
                save_state(self.state)
        self._unreact(channel, ts, conf.get("ack_reaction"))
        out_ts = None
        if ok:
            if placeholder and self.sender.update(agent, channel, placeholder, reply):
                out_ts = placeholder
            else:
                out_ts = self.say(agent, channel, reply, thread_ts, run_id)
            self._react(channel, ts, conf.get("done_reaction"))
        else:
            msg = f":warning: {agent_identity(conf, agent)['display_name']} could not answer: {reply}"
            if placeholder and self.sender.update(agent, channel, placeholder, msg):
                out_ts = placeholder
            else:
                out_ts = self.say(agent, channel, msg, thread_ts, run_id)
        elapsed = round(time.time() - started, 1)
        audit(conf, agent=agent, profile=agent_identity(conf, agent)["profile"], run_id=run_id,
              requester=event.get("user", ""), channel=channel, root_ts=thread_ts, out_ts=out_ts or "",
              ok=ok, seconds=elapsed, reason=reason, chars=len(reply or ""))
        log("dispatch_done", agent=agent, ok=ok, seconds=elapsed, run_id=run_id)

    def _react(self, channel: str, ts: str, name: str | None) -> None:
        if not name:
            return
        try:
            self.web.reactions_add(channel=channel, timestamp=ts, name=name)
        except Exception:
            pass

    def _unreact(self, channel: str, ts: str, name: str | None) -> None:
        if not name:
            return
        try:
            self.web.reactions_remove(channel=channel, timestamp=ts, name=name)
        except Exception:
            pass

    # -- admission -----------------------------------------------------------
    def admit(self, event: dict, authorizations: list[str]) -> tuple[str, str] | None:
        conf = self.conf
        etype = event.get("type")
        if etype not in ("app_mention", "message"):
            return None
        subtype = event.get("subtype")
        if subtype in ("message_changed", "message_deleted"):
            return None
        if event.get("bot_id"):
            if event["bot_id"] not in (conf.get("allow_bots") or []):
                return None
        user = event.get("user")
        if not user or user in self.our_bot_users:
            return None
        # 1) never answer a message this gateway produced (ts bookkeeping beats
        #    guessing from the author id, which is shared with the human owner)
        with self.lock:
            if event.get("ts") and event["ts"] in (self.state.get("outbound") or {}):
                log("ignored_own_post", ts=event["ts"])
                return None
        # 2) never answer a *routable* agent's own seat. send_only identities (the human
        #    owner) still get answers — their API posts are caught by the check above.
        for name, rec in (conf.get("agents") or {}).items():
            if (rec.get("user_token_file") and rec.get("slack_user_id")
                    and rec["slack_user_id"] == user and not rec.get("send_only")):
                log("ignored_own_agent_message", agent=name, agent_slack_user=user)
                return None
        if etype == "message" and event.get("channel_type") not in ("im", "channel", "group", "mpim"):
            return None
        channel = event.get("channel", "")
        allowed = conf.get("allowed_users") or []
        if allowed and user not in allowed and not event.get("bot_id"):
            log("rejected_user", user=user)
            return None
        is_dm = event.get("channel_type") == "im"
        thread_root = event.get("thread_ts") or event.get("ts") or ""
        with self.lock:
            bound = (self.state.get("bindings") or {}).get(f"{channel}:{thread_root}")
        # Unbound channel events must address this app or an enrolled role,
        # not an unrelated Slack user. A bound thread may follow up without
        # another mention. Explicit channel enrollment retains its route.
        addressed_ids = set(mentioned_user_ids(event.get("text", "")))
        our_addresses = set(self.our_bot_users)
        # A configured external user ID is not our Slack principal. Only a
        # genuinely enrolled user-token identity may receive native @mentions.
        # In particular, Grok Secretary remains an independent external peer.
        our_addresses.update(rec.get("slack_user_id")
                             for name, rec in routable(conf).items()
                             if rec.get("slack_user_id")
                             and identity_mode(conf, name)[0] == "user")
        if (etype == "message" and event.get("channel_type") in ("channel", "group")
                and not bound
                and not (addressed_ids & our_addresses)
                and channel not in (conf.get("channels") or {})
                and not any(channel in (rec.get("channels") or [])
                            for rec in routable(conf).values())):
            return None
        # Admission is pure: do not consume rate capacity before the final
        # source-timestamp deduplication in handle(). Slack commonly sends
        # one logical mention through both app_mention and message events.
        return route(conf, text=event.get("text", ""), channel=channel, user=user,
                     is_dm=is_dm, authorizations=authorizations, binding=bound)

    def slash_agent(self, command: str) -> str | None:
        """'/mx-delivery' -> 'delivery'; explicit conf['slash_agents'] wins if present."""
        explicit = (self.conf.get("slash_agents") or {}).get(command)
        if explicit:
            return explicit
        if not command.startswith("/mx-"):
            return None
        name = command[len("/mx-"):]
        return name if name in (self.conf.get("agents") or {}) else None

    def handle_slash(self, payload: dict) -> None:
        command = payload.get("command", "")
        text = (payload.get("text") or "").strip()
        channel = payload.get("channel_id", "")
        user = payload.get("user_id", "")
        team = payload.get("team_id", "")
        agent = self.slash_agent(command)
        log("slash", command=command, agent=agent, user=user, chars=len(text))
        if not agent:
            log("slash_unknown", command=command)
            return
        expect_team = (self.conf.get("apps") or {}).get("main", {}).get("team_id")
        if expect_team and team and team != expect_team:
            log("slash_wrong_team", team=team)
            return
        allowed = self.conf.get("allowed_users") or []
        if allowed and user not in allowed:
            log("slash_rejected_user", user=user)
            return
        if not channel or not text:
            self.say(agent, channel or "", f":warning: `{command}` needs a request, e.g. `{command} summarise the open PRs`")
            return
        event = {"type": "message", "channel": channel, "ts": "", "thread_ts": "",
                 "text": text, "user": user}
        threading.Thread(target=self.work, args=(event, agent, f"slash:{command}", []), daemon=True).start()

    def handle(self, payload: dict) -> None:
        event = payload.get("event") or {}
        authorizations = [a.get("user_id") for a in (payload.get("authorizations") or []) if a.get("user_id")]
        verdict = self.admit(event, authorizations)
        if not verdict:
            return
        agent, reason = verdict
        key = f"{event.get('channel')}:{event.get('ts')}"
        with self.lock:
            if key in (self.state.get("seen") or {}):
                return
            now = time.time()
            channel = event.get("channel", "")
            recent = self.state.setdefault("recent", {})
            hits = [t for t in (recent.get(channel) or []) if now - t < 60]
            if len(hits) >= int(self.conf.get("max_dispatches_per_minute", 6)):
                log("rate_limited", channel=channel)
                return
            hits.append(now)
            recent[channel] = hits
            self.state.setdefault("seen", {})[key] = now
            save_state(self.state)
        threading.Thread(target=self.work, args=(event, agent, reason, authorizations), daemon=True).start()

    # -- socket --------------------------------------------------------------
    def socket_transports(self) -> list[tuple[str, str, object]]:
        """(app name, app-level token, WebClient) for every app we receive on."""
        from slack_sdk import WebClient

        out = []
        for name, rec in self.apps.items():
            if not (rec or {}).get("socket_mode", True):
                continue
            bot = read_env((rec or {}).get("bot_token_file", "")).get("SLACK_BOT_TOKEN")
            app_tok = read_env((rec or {}).get("app_token_file", "")).get("SLACK_APP_TOKEN")
            if app_tok:
                out.append((name, app_tok, WebClient(token=bot) if bot else self.web))
        if not out:
            out.append(("main", self.app_token, self.web))
        return out

    def run_socket(self) -> None:
        transports = self.socket_transports()
        log("transports", apps=[t[0] for t in transports])
        threads = [threading.Thread(target=self._run_one_socket, args=t, daemon=True)
                   for t in transports]
        for t in threads:
            t.start()
        while True:
            time.sleep(30)
            alive = sum(1 for t in threads if t.is_alive())
            if alive == 0:
                log("all_sockets_dead")
                return

    def _run_one_socket(self, name: str, app_token: str, web) -> None:
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.request import SocketModeRequest
        from slack_sdk.socket_mode.response import SocketModeResponse

        def listener(client, req: SocketModeRequest) -> None:
            client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
            if req.type == "slash_commands":
                try:
                    self.handle_slash(dict(req.payload or {}))
                except Exception as exc:  # noqa: BLE001
                    log("slash_exception", error=str(exc)[:400])
                return
            if req.type != "events_api":
                return
            try:
                payload = dict(req.payload or {})
                payload["_transport_app"] = name
                self.handle(payload)
            except Exception as exc:  # noqa: BLE001
                log("handle_exception", app=name, error=str(exc)[:400])

        client = SocketModeClient(app_token=app_token, web_client=web)
        client.socket_mode_request_listeners.append(listener)
        try:
            client.connect()
            log("socket_connected", app=name)
        except Exception as exc:  # noqa: BLE001
            log("socket_connect_failed", app=name, error=str(exc)[:300])
        while True:
            time.sleep(8)
            if not client.is_connected():
                log("socket_reconnect", app=name)
                try:
                    client.connect()
                except Exception as exc:  # noqa: BLE001
                    log("socket_reconnect_failed", app=name, error=str(exc)[:300])
                    time.sleep(15)


# ------------------------------------------------------------------- HTTP ----
def make_http_server(fleet: Fleet, conf: dict) -> ThreadingHTTPServer:
    hconf = conf.get("http") or {}
    token = read_env(hconf.get("token_file", "slack-gateway-http.env")).get("SLACK_GATEWAY_HTTP_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _auth(self) -> bool:
            if not token:
                return self.client_address[0] in ("127.0.0.1", "::1")
            return self.headers.get("X-Gateway-Token") == token

        def _json(self, code: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):  # silence stderr chatter
            return

        def do_GET(self) -> None:  # noqa: N802
            if not self._auth():
                return self._json(401, {"error": "unauthorized"})
            if self.path.startswith("/health"):
                agents = {}
                for name in (conf.get("agents") or {}):
                    mode, _ = identity_mode(conf, name)
                    agents[name] = {"identity_mode": mode,
                                    "transport": agent_app(conf, name),
                                    "profile": agent_identity(conf, name)["profile"]}
                return self._json(200, {
                    "ok": True,
                    "gateway": "mastermind-slack-gateway",
                    "app": (conf.get("apps") or {}).get("main", {}).get("app_id", "A0BTCKA7GSY"),
                    "transports": {n: {"app_id": (r or {}).get("app_id", ""),
                                       "bot_user_id": (r or {}).get("bot_user_id"),
                                       "socket_mode": (r or {}).get("socket_mode", True)}
                                   for n, r in (conf.get("apps") or {}).items()},
                    "bot_user_id": conf["bot"].get("bot_user_id"),
                    "default_agent": conf.get("default_agent"),
                    "identities": {k: v["identity_mode"] for k, v in agents.items()},
                    "agents": agents,
                    "sessions": len(fleet.state.get("sessions") or {}),
                    "uptime_s": int(time.time() - START),
                })
            if self.path.startswith("/agents"):
                return self._json(200, {"ok": True, "agents": conf.get("agents")})
            return self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._auth():
                return self._json(401, {"error": "unauthorized"})
            if not self.path.startswith("/send"):
                return self._json(404, {"error": "not_found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._json(400, {"error": "bad_json"})
            agent = body.get("agent") or conf.get("default_agent")
            channel = body.get("channel")
            text = body.get("text") or ""
            if not channel or not text:
                return self._json(400, {"error": "channel_and_text_required"})
            if channel.startswith("U"):
                try:
                    channel = fleet.web.conversations_open(users=channel).get("channel", {}).get("id", channel)
                except Exception:
                    pass
            ts = fleet.say(agent, channel, text, body.get("thread_ts"))
            log("http_send", agent=agent, channel=channel, ok=bool(ts))
            return self._json(200 if ts else 502, {"ok": bool(ts), "ts": ts, "agent": agent,
                                                   "identity_mode": identity_mode(conf, agent)[0]})

    server = ThreadingHTTPServer((hconf.get("host", "127.0.0.1"), int(hconf.get("port", 8791))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


START = time.time()


# ------------------------------------------------------------------- CLI ----
def cmd_status() -> int:
    conf = load_conf()
    print(f"conf            : {CONF_PATH}")
    bot = read_env(conf["bot"]["token_file"])
    app = read_env(conf["bot"]["app_token_file"])
    print(f"bot token       : present={bool(bot.get('SLACK_BOT_TOKEN'))} file={conf['bot']['token_file']}")
    print(f"app token       : present={bool(app.get('SLACK_APP_TOKEN'))} file={conf['bot']['app_token_file']}")
    print(f"default agent   : {conf.get('default_agent')}")
    print(f"{'agent':16} {'mode':5} {'slack account':15} {'profile':16} display")
    for name in (conf.get("agents") or {}):
        ident = agent_identity(conf, name)
        mode, _ = identity_mode(conf, name)
        print(f"{name:16} {mode:5} {str(ident['slack_user_id'] or '-'):15} {ident['profile']:16} {ident['display_name']}")
    print(f"channels        : {conf.get('channels')}")
    print(f"dm_agents       : {conf.get('dm_agents')}")
    print(f"allowed users   : {conf.get('allowed_users') or '(anyone in workspace)'}")
    print(f"http            : {conf.get('http')}")
    if LOG_PATH.exists():
        print("recent log      :")
        for line in LOG_PATH.read_text().strip().splitlines()[-4:]:
            print("  " + line[:190])
    return 0


def cmd_enroll(argv: list[str]) -> int:
    """slack_gateway.py enroll <agent>  — read an xoxp- token from stdin (no echo).

    Verifies it with auth.test, writes ~/.hermes/secrets/slack-user-<agent>.env at
    0600, and registers the agent's Slack account in agents.json. The gateway then
    posts as that account natively instead of using the display-name override.
    """
    if len(argv) < 3:
        print("usage: slack_gateway.py enroll <agent>   (token on stdin)", file=sys.stderr)
        return 2
    agent = argv[2]
    token = sys.stdin.readline().strip()
    if not token.startswith("xoxp-"):
        print("refusing: not a user token (xoxp-…)", file=sys.stderr)
        return 2
    from slack_sdk import WebClient
    res = WebClient(token=token).auth_test()
    if not res.get("ok"):
        print(f"slack rejected the token: {res.get('error')}", file=sys.stderr)
        return 4
    uid, uname = res.get("user_id"), res.get("user")
    path = SECRETS / f"slack-user-{agent}.env"
    SECRETS.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"SLACK_USER_TOKEN={token}\n")
    os.chmod(path, 0o600)
    conf = load_conf()
    rec = conf.setdefault("agents", {}).setdefault(agent, {})
    rec["user_token_file"] = path.name
    rec["slack_user_id"] = uid
    rec.setdefault("display_name", agent)
    rec.setdefault("emoji", ":robot_face:")
    rec.setdefault("profile", agent)
    rec.setdefault("channels", [])
    rec.setdefault("dm", True)
    CONF_PATH.write_text(json.dumps(conf, indent=2))
    os.chmod(CONF_PATH, 0o600)
    log("enrolled", agent=agent, slack_user=uname, slack_user_id=uid)
    print(json.dumps({"ok": True, "agent": agent, "slack_user": uname, "slack_user_id": uid,
                      "identity_mode": identity_mode(conf, agent)[0], "token_file": str(path)}))
    return 0


def cmd_verify() -> int:
    """auth.test every agent identity that has a user token."""
    from slack_sdk import WebClient
    conf = load_conf()
    rows = []
    for name in (conf.get("agents") or {}):
        mode, token = identity_mode(conf, name)
        if mode != "user":
            rows.append({"agent": name, "identity_mode": "bot", "ok": True, "slack_user": None})
            continue
        try:
            r = WebClient(token=token).auth_test()
            rows.append({"agent": name, "identity_mode": "user", "ok": bool(r.get("ok")),
                         "slack_user": r.get("user"), "slack_user_id": r.get("user_id")})
        except Exception as exc:  # noqa: BLE001
            rows.append({"agent": name, "identity_mode": "user", "ok": False, "error": str(exc)[:200]})
    print(json.dumps({"ok": all(r.get("ok") for r in rows), "agents": rows}, indent=2))
    return 0 if all(r.get("ok") for r in rows) else 1


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        return cmd_status()
    if cmd == "agents":
        conf = load_conf()
        for name in (conf.get("agents") or {}):
            mode, _ = identity_mode(conf, name)
            print(f"{name:16} {mode}")
        return 0
    if cmd == "enroll":
        return cmd_enroll(argv)
    if cmd == "verify":
        return cmd_verify()
    if cmd == "route":
        conf = load_conf()
        text = argv[2] if len(argv) > 2 else ""
        print(route(conf, text=text, channel=argv[3] if len(argv) > 3 else "", user="", is_dm=False))
        return 0

    conf = load_conf()
    if cmd in ("run", "http", "send"):
        try:
            fleet = Fleet(conf)
        except SystemExit as exc:
            print(f"startup failed: {exc}", file=sys.stderr)
            return 3
        if cmd == "send":
            if len(argv) < 5:
                print("usage: slack_gateway.py send <agent> <channel_id> <text>", file=sys.stderr)
                return 2
            ts = fleet.say(argv[2], argv[3], argv[4])
            print(json.dumps({"ok": bool(ts), "ts": ts, "mode": identity_mode(conf, argv[2])[0]}))
            return 0 if ts else 1
        server = make_http_server(fleet, conf)
        log("gateway_start", http=f"{server.server_address[0]}:{server.server_address[1]}")
        if cmd == "http":
            print(f"http on {server.server_address}")
            try:
                while True:
                    time.sleep(30)
            except KeyboardInterrupt:
                return 0
        try:
            fleet.run_socket()
        except KeyboardInterrupt:
            log("gateway_stop")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
