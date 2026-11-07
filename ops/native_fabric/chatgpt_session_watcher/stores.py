"""Local watcher memory: session registry, owed-returns ledger, lessons, metrics, run receipts.

Files are JSON. Writes are atomic. Secret-shaped strings are redacted before they hit disk.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from playbook import LESSON_SEED
from policy import redact_obj

REGISTRY_SCHEMA = "mastermind.chatgpt_session_registry.v1"
LEDGER_SCHEMA = "mastermind.chatgpt_owed_returns.v1"
LESSONS_SCHEMA = "mastermind.chatgpt_watcher_lessons.v1"
METRICS_SCHEMA = "mastermind.chatgpt_watcher_metrics.v1"
RUN_SCHEMA = "mastermind.fabric_task_status.v1"


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(redact_obj(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sessions_from(doc) -> list[dict]:
    if isinstance(doc, list):
        return [dict(row) for row in doc if isinstance(row, dict)]
    if not isinstance(doc, dict):
        raise ValueError("registry document must be a list or object")
    for key in ("sessions", "entries", "sample"):
        rows = doc.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    raise ValueError("registry document has no sessions")


def ledger_rows_from(doc) -> list[dict]:
    if isinstance(doc, list):
        return [dict(row) for row in doc if isinstance(row, dict)]
    if not isinstance(doc, dict):
        raise ValueError("ledger document must be a list or object")
    for key in ("entries", "returns", "sample"):
        rows = doc.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    raise ValueError("ledger document has no entries")


class RegistryStore:
    def __init__(self, path: Path):
        self.path = path
        self.sessions: list[dict] = []
        self.meta: dict = {}
        self.load()

    def load(self) -> None:
        doc = _read(self.path)
        if doc is None:
            self.sessions = []
            self.meta = {}
            return
        self.sessions = sessions_from(doc)
        self.meta = dict(doc.get("meta") or {}) if isinstance(doc, dict) else {}

    def save(self) -> None:
        atomic_write(self.path, {
            "schema": REGISTRY_SCHEMA,
            "sessions": self.sessions,
            "meta": self.meta,
        })

    def get(self, chat_id: str | None) -> dict | None:
        if not chat_id:
            return None
        for row in self.sessions:
            if row.get("chat_id") == chat_id:
                return row
        return None

    def upsert_seen(self, row: dict) -> dict:
        chat_id = row.get("chat_id")
        current = self.get(chat_id) if chat_id else None
        if current is None:
            current = {
                "chat_id": chat_id,
                "status": "seen_sidebar",
                "replaces": None,
                "replaced_by": None,
                "do_not_steer": False,
            }
            self.sessions.append(current)
        for key, value in row.items():
            if value is not None and key not in {"status", "replaced_by", "do_not_steer"}:
                current[key] = value
        return current


class LedgerStore:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[dict] = []
        self.load()

    def load(self) -> None:
        doc = _read(self.path)
        self.entries = ledger_rows_from(doc) if doc is not None else []

    def save(self) -> None:
        atomic_write(self.path, {"schema": LEDGER_SCHEMA, "entries": self.entries})

    def open_returns(self) -> list[dict]:
        return [row for row in self.entries if str(row.get("state") or "") not in {"consumed", "cancelled"}]

    def upsert(self, entry: dict) -> None:
        task = entry.get("task")
        for index, row in enumerate(self.entries):
            if task and row.get("task") == task:
                self.entries[index] = {**row, **entry}
                return
        self.entries.append(dict(entry))


class LessonsStore:
    def __init__(self, path: Path):
        self.path = path
        self.lessons: list[dict] = []
        self.load()

    def load(self) -> None:
        doc = _read(self.path)
        if isinstance(doc, dict) and isinstance(doc.get("lessons"), list):
            self.lessons = list(doc["lessons"])
        else:
            self.lessons = []

    def ensure_seed(self) -> None:
        ids = {row.get("id") for row in self.lessons}
        for seed in LESSON_SEED:
            if seed["id"] not in ids:
                self.lessons.append(dict(seed))

    def save(self) -> None:
        atomic_write(self.path, {"schema": LESSONS_SCHEMA, "lessons": self.lessons})

    def all(self) -> list[dict]:
        return list(self.lessons)

    def retired_tactics(self) -> set[str]:
        return {row["tactic"] for row in self.lessons if row.get("retire_tactic") and row.get("tactic")}

    def append_failure(self, *, symptom: str, tactic: str, chat_id: str | None) -> None:
        lesson_id = f"fail-{symptom}-{tactic}"
        if any(row.get("id") == lesson_id for row in self.lessons):
            return
        self.lessons.append({
            "id": lesson_id,
            "symptom": symptom,
            "tactic": tactic,
            "chat_id": chat_id,
            "fix": "unresolved",
            "source": "cycle",
        })

    def append_lesson(self, lesson: dict) -> None:
        if any(row.get("id") == lesson.get("id") for row in self.lessons):
            return
        self.lessons.append(dict(lesson))


class MetricsStore:
    def __init__(self, path: Path):
        self.path = path
        self.tactics: dict[str, dict[str, int]] = {}
        self.accounts: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        doc = _read(self.path)
        if isinstance(doc, dict):
            self.tactics = dict(doc.get("tactics") or {})
            self.accounts = dict(doc.get("accounts") or {})

    def save(self) -> None:
        atomic_write(self.path, {
            "schema": METRICS_SCHEMA,
            "tactics": self.tactics,
            "accounts": self.accounts,
        })

    def record(self, tactic: str, success: bool) -> None:
        row = self.tactics.setdefault(tactic, {"attempts": 0, "successes": 0})
        row["attempts"] = int(row.get("attempts") or 0) + 1
        if success:
            row["successes"] = int(row.get("successes") or 0) + 1

    def prefer(self, default: str, options: list[str], minimum: int = 3) -> str:
        best = default
        best_rate = -1.0
        for name in options:
            row = self.tactics.get(name) or {}
            attempts = int(row.get("attempts") or 0)
            if attempts < minimum:
                continue
            rate = int(row.get("successes") or 0) / attempts
            if rate > best_rate:
                best, best_rate = name, rate
        return best


class RunStore:
    def __init__(self, root: Path):
        self.root = root / "runs"

    def _path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", run_id):
            raise ValueError("invalid run id")
        return self.root / f"{run_id}.json"

    def read(self, run_id: str) -> dict:
        path = self._path(run_id)
        if not path.exists():
            return {
                "schema": RUN_SCHEMA,
                "run_id": run_id,
                "root_id": None,
                "state": "NOT_FOUND",
                "result_available": False,
                "accepted": None,
                "worker_kind": "chatgpt_web_session_watcher",
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, run_id: str, payload: dict) -> None:
        atomic_write(self._path(run_id), payload)


class WatcherStores:
    def __init__(self, root: Path):
        self.root = root
        self.registry = RegistryStore(root / "registry.json")
        self.ledger = LedgerStore(root / "owed_returns.json")
        self.lessons = LessonsStore(root / "lessons.json")
        self.metrics = MetricsStore(root / "metrics.json")
        self.runs = RunStore(root)

    def save(self) -> None:
        self.registry.save()
        self.ledger.save()
        self.lessons.save()
        self.metrics.save()
