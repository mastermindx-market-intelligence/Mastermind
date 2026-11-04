"""Credential-free complete-turn projection used by the Qwen run wrapper."""
import json
import os
import sys
from typing import IO, Optional


def stream_final_jsonl(in_f: IO[str], out_f: IO[str], thread_path: str,
                       raw_path: str) -> Optional[str]:
    """One completed Codex exec turn, projected to its last assistant message.

    The raw stream remains available to the existing diagnostic/limit scanner.
    Tool output and progress are never a final response, even when they contain
    terminal-looking text. No partial response is published on framing failure.
    This projection does not accept the worker's answer or truncate its content.
    """
    thread_id = None
    last_text = None
    completed = False
    failed = False
    started = False
    with open(raw_path, "w", encoding="utf-8") as raw:
        for line in in_f:
            raw.write(line)
            raw.flush()
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                failed = True
                continue
            if not isinstance(ev, dict):
                failed = True
                continue
            kind = ev.get("type")
            if kind == "thread.started":
                tid = ev.get("thread_id")
                if (not isinstance(tid, str) or not tid.strip()
                        or thread_id is not None or completed):
                    failed = True
                    continue
                thread_id = tid
                with open(thread_path + ".tmp", "w", encoding="utf-8") as target:
                    target.write(tid + "\n")
                os.replace(thread_path + ".tmp", thread_path)
            elif kind == "turn.started":
                if started or completed:
                    failed = True
                started = True
            elif kind in ("error", "turn.failed"):
                failed = True
            elif kind == "item.completed":
                item = ev.get("item")
                if not isinstance(item, dict):
                    failed = True
                    continue
                if item.get("type") == "agent_message":
                    text = item.get("text")
                    if not isinstance(text, str) or completed:
                        failed = True
                    elif item.get("phase") != "commentary":
                        last_text = text
            elif kind == "turn.completed":
                if completed:
                    failed = True
                completed = True
    if failed or not completed or not thread_id or not last_text:
        raise ValueError("QWEN_FINAL_RESPONSE_UNCONFIRMED")
    out_f.write(last_text)
    if not last_text.endswith("\n"):
        out_f.write("\n")
    out_f.flush()
    return thread_id


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("QWEN_FINAL_RESPONSE_ARGUMENTS_INVALID", file=sys.stderr)
        return 77
    try:
        stream_final_jsonl(sys.stdin, sys.stdout, argv[0], argv[1])
    except (ValueError, OSError, UnicodeError):
        print("QWEN_FINAL_RESPONSE_UNCONFIRMED", file=sys.stderr)
        return 77
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
