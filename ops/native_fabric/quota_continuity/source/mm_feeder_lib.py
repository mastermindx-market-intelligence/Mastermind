#!/usr/bin/env python3
"""Helpers for mm_feeder.sh. Paths and labels arrive via argv (W3-REVIEW F11).
Never reads or prints API keys.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from typing import List, Optional, Tuple


def marker_matches_label(text: str, label: str) -> bool:
    """True if lane2 marker JSON label or key equals *label* (W3-REVIEW F1)."""
    raw = (text or "").strip()
    if not raw or not label:
        return False
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return raw == label
    if not isinstance(obj, dict):
        return False
    return obj.get("label") == label or obj.get("key") == label


def is_label_active(active_dir: str, label: str) -> bool:
    """A label is running if any active/ marker's JSON label or key matches."""
    if not label:
        return False
    if not os.path.isdir(active_dir):
        return False
    try:
        names = os.listdir(active_dir)
    except OSError:
        return False
    for name in names:
        if name.startswith("."):
            continue
        path = os.path.join(active_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if marker_matches_label(text, label):
            return True
    return False


def parse_grant_now(plan_text: str, pool: str = "minimax") -> int:
    """Parse `POOL=<pool> grant_now=N` from lease_broker plan output (F3/F8)."""
    want = f"POOL={pool} "
    for line in (plan_text or "").splitlines():
        line = line.strip()
        if not line.startswith(want):
            continue
        for tok in line.split():
            if tok.startswith("grant_now="):
                try:
                    return max(0, int(tok.split("=", 1)[1]))
                except ValueError:
                    return 0
    return 0


def _pool_cap(pool: str) -> int:
    """Delegate pool admission to the existing slot owner."""
    import slot

    return int(slot._pool_cap(pool))


def split_idle_task(task_line: str) -> Tuple[str, str]:
    """Split mm_idle_tasks.txt on the first pipe (W3-REVIEW F5)."""
    line = task_line or ""
    if "|" not in line:
        return line.strip(), ""
    idx, prompt = line.split("|", 1)
    return idx, prompt


def any_pending_remote_queue(paths: List[str]) -> bool:
    """Fail closed for useful-idle when any existing real host queue has work."""
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                if any(line.strip() for line in fh):
                    return True
        except FileNotFoundError:
            continue
        except OSError:
            # An unreadable real queue is not evidence that it is empty.
            return True
    return False


def backlog_pop(path: str) -> str:
    """Pop the first backlog line; write the rest with no leftover newline file (F6)."""
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    lines = raw.splitlines()
    if not lines:
        with open(path, "w", encoding="utf-8") as fh:
            pass
        return ""
    first, rest = lines[0], lines[1:]
    with open(path, "w", encoding="utf-8") as fh:
        if rest:
            fh.write("\n".join(rest) + "\n")
    return first


def backlog_requeue(path: str, line: str) -> None:
    """Append a popped line with printf semantics (F4)."""
    if not line:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def consume_relaunch_queue(queue_path: str, lock_path: str) -> List[str]:
    """ONE consumer protocol for RELAUNCH_QUEUE.txt (F2).

    Exclusive flock, unique first-token labels, truncate, return labels.
    Shepherd and feeder both call this; neither may read the file without it.
    """
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)) or ".", exist_ok=True)
    # Touch both so the lock exists even when the queue does not yet.
    open(lock_path, "a").close()
    if not os.path.exists(queue_path):
        open(queue_path, "a").close()
    with open(lock_path, "a+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            try:
                with open(queue_path, encoding="utf-8") as qf:
                    raw_lines = qf.read().splitlines()
            except FileNotFoundError:
                raw_lines = []
            seen: List[str] = []
            for raw in raw_lines:
                token = raw.strip().split()[0] if raw.strip() else ""
                if token and token not in seen:
                    seen.append(token)
            with open(queue_path, "w", encoding="utf-8") as qf:
                pass
            return seen
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def return_relaunch_labels(queue_path: str, lock_path: str, labels: List[str]) -> None:
    """Append leftover labels under the same flock as consume (F2)."""
    cleaned = [str(x).strip() for x in labels if str(x).strip()]
    if not cleaned:
        return
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)) or ".", exist_ok=True)
    open(lock_path, "a").close()
    if not os.path.exists(queue_path):
        open(queue_path, "a").close()
    with open(lock_path, "a+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            with open(queue_path, "a", encoding="utf-8") as qf:
                for lab in cleaned:
                    qf.write(lab + "\n")
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def singleton_exec(lock_path: str, argv: List[str]) -> None:
    """Hold an exclusive flock then exec argv (W3-REVIEW F10). Replaces pidfile TOCTOU."""
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)) or ".", exist_ok=True)
    fd = open(lock_path, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.stderr.write("REFUSE: mm_feeder already running\n")
        sys.exit(1)
    fd.seek(0)
    fd.truncate()
    fd.write("%s\n" % os.getpid())
    fd.flush()
    flags = fcntl.fcntl(fd.fileno(), fcntl.F_GETFD)
    fcntl.fcntl(fd.fileno(), fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)
    os.set_inheritable(fd.fileno(), True)
    os.execv(argv[0], argv)


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        sys.stderr.write(
            "usage: mm_feeder_lib.py "
            "is_label_active|grant_now|backlog_pop|backlog_requeue|"
            "consume_relaunch|return_relaunch|split_idle|remote_queue_pending|singleton_exec ...\n"
        )
        return 2
    cmd = argv[1]
    if cmd == "is_label_active":
        if len(argv) < 4:
            return 2
        return 0 if is_label_active(argv[2], argv[3]) else 1
    if cmd == "grant_now":
        pool = argv[2] if len(argv) > 2 else "minimax"
        if _pool_cap(pool) == 0:
            print(0)
            return 0
        print(parse_grant_now(sys.stdin.read(), pool))
        return 0
    if cmd == "backlog_pop":
        if len(argv) < 3:
            return 2
        line = backlog_pop(argv[2])
        if line:
            sys.stdout.write(line)
        return 0
    if cmd == "backlog_requeue":
        if len(argv) < 4:
            return 2
        backlog_requeue(argv[2], argv[3])
        return 0
    if cmd == "consume_relaunch":
        if len(argv) < 4:
            return 2
        for lab in consume_relaunch_queue(argv[2], argv[3]):
            print(lab)
        return 0
    if cmd == "return_relaunch":
        if len(argv) < 4:
            return 2
        return_relaunch_labels(argv[2], argv[3], argv[4:])
        return 0
    if cmd == "split_idle":
        if len(argv) < 3:
            return 2
        idx, prompt = split_idle_task(argv[2])
        sys.stdout.write(idx + "\n" + prompt)
        return 0
    if cmd == "remote_queue_pending":
        if len(argv) < 3:
            return 1
        return 0 if any_pending_remote_queue(argv[2:]) else 1
    if cmd == "singleton_exec":
        if len(argv) < 4:
            return 2
        singleton_exec(argv[2], argv[3:])
        return 0
    sys.stderr.write("unknown cmd %s\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(_main())
