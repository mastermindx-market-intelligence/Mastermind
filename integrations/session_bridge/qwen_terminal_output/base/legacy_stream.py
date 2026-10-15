"""Exact pure stream functions from the installed baseline; no account code."""
import json
import os
import sys
from typing import IO, Optional, Dict, Any, List


def _item_text(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    kind = item.get("type") or ""
    if kind == "agent_message":
        return (item.get("text") or "").rstrip() + ("\n" if item.get("text") else "")
    if kind == "error":
        msg = item.get("message") or item.get("text") or ""
        return f"[error] {msg}\n" if msg else ""
    if kind == "command_execution":
        cmd = item.get("command") or ""
        out = item.get("aggregated_output") or ""
        rc = item.get("exit_code")
        bits = [f"$ {cmd}".rstrip()]
        if out:
            bits.append(out.rstrip())
        if rc is not None:
            bits.append(f"(exit {rc})")
        return "\n".join(bits) + "\n"
    if kind == "reasoning":
        return ""
    text = item.get("text") or item.get("message") or ""
    return (text.rstrip() + "\n") if text else ""


def stream_jsonl(in_f: IO[str], out_f: IO[str], thread_path: str, raw_path: Optional[str] = None) -> Optional[str]:
    """Filter Codex --json JSONL to plain text. Persist thread/session id."""
    thread_id = None
    raw_fh = open(raw_path, "w", encoding="utf-8") if raw_path else None
    try:
        for line in in_f:
            if raw_fh is not None:
                raw_fh.write(line)
                raw_fh.flush()
            s = line.strip()
            if not s:
                continue
            try:
                ev = json.loads(s)
            except json.JSONDecodeError:
                out_f.write(line)
                out_f.flush()
                continue
            if not isinstance(ev, dict):
                continue
            et = ev.get("type") or ""
            tid = ev.get("thread_id") or ev.get("session_id")
            if isinstance(tid, str) and tid:
                thread_id = tid
                if thread_path:
                    tmp = thread_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as tf:
                        tf.write(tid + "\n")
                    os.replace(tmp, thread_path)
            if et == "thread.started":
                continue
            if et in ("error", "turn.failed"):
                err = ev.get("error") if isinstance(ev.get("error"), dict) else {}
                msg = ev.get("message") or (err or {}).get("message") or ev.get("error") or ""
                if isinstance(msg, dict):
                    msg = msg.get("message") or json.dumps(msg)
                if msg:
                    out_f.write(str(msg).rstrip() + "\n")
                    out_f.flush()
                continue
            if et == "item.completed":
                text = _item_text(ev.get("item") or {})
                if text:
                    out_f.write(text)
                    if not text.endswith("\n"):
                        out_f.write("\n")
                    out_f.flush()
                continue
            payload = ev.get("payload")
            if isinstance(payload, dict):
                sid = payload.get("session_id") or payload.get("id")
                if isinstance(sid, str) and sid and et == "session_meta":
                    thread_id = sid
                    if thread_path:
                        tmp = thread_path + ".tmp"
                        with open(tmp, "w", encoding="utf-8") as tf:
                            tf.write(sid + "\n")
                        os.replace(tmp, thread_path)
                ptype = payload.get("type")
                if ptype == "agent_message":
                    msg = payload.get("message") or payload.get("text") or ""
                    if msg:
                        out_f.write(str(msg).rstrip() + "\n")
                        out_f.flush()
    finally:
        if raw_fh is not None:
            raw_fh.close()
    return thread_id


def cmd_stream(argv: List[str]) -> int:
    """Internal: filter Codex JSONL on stdin. argv: <thread-file> [raw-file]."""
    if not argv:
        _die("usage: stream <thread-file> [raw-file]", 2)
    thread_path = argv[0]
    raw_path = argv[1] if len(argv) > 1 else None
    stream_jsonl(sys.stdin, sys.stdout, thread_path, raw_path)
    return 0
