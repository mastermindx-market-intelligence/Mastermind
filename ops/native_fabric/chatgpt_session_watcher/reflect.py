"""Periodic reflection. Proposes playbook and template edits. Does not modify policy."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from minimax_client import MinimaxUnavailable
from stores import WatcherStores

_BANNER = (
    "Core policy, prompt templates, and decision rules change only through a reviewed pull request. "
    "This file is a proposal, not an applied edit."
)


def reflect(stores: WatcherStores, proposal_dir: Path, *, client=None, escalation=None, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    proposal_dir.mkdir(parents=True, exist_ok=True)
    # Refuse to write into the source tree's policy module, wherever this runs.
    resolved = proposal_dir.resolve()
    source = Path(__file__).resolve().parent
    if resolved == source or source in resolved.parents and resolved.name != "proposals":
        # State directories are fine. The package directory itself is not, except
        # an explicit proposals folder created by a test under tmp.
        if _is_source_tree(resolved):
            raise RuntimeError("reflection_refuses_source_edits")
    used = "rules"
    suggestion = _deterministic(stores)
    if client is not None:
        try:
            suggestion = client.complete([
                {"role": "system", "content": "Propose watcher tactic changes as prose. Do not emit a patch that edits policy.py."},
                {"role": "user", "content": suggestion},
            ])
            used = "minimax"
        except MinimaxUnavailable:
            if escalation is not None:
                suggestion = escalation.complete([
                    {"role": "user", "content": suggestion},
                ])
                used = "escalation"
    body = "\n".join([
        "# Watcher reflection proposal",
        "",
        _BANNER,
        "",
        f"Reasoning: {used}.",
        "",
        "## Suggested tactic notes",
        "",
        suggestion.strip(),
        "",
        "Do not apply this file in place. Open a reviewed PR if a core rule should change.",
        "",
    ])
    path = proposal_dir / f"playbook_update_{now.strftime('%Y%m%dT%H%M%SZ')}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _is_source_tree(path: Path) -> bool:
    return (path / "policy.py").exists() or path.name == "chatgpt_session_watcher" and (path / "cli.py").exists()


def _deterministic(stores: WatcherStores) -> str:
    lines = []
    for name, row in sorted(stores.metrics.tactics.items()):
        attempts = int(row.get("attempts") or 0)
        successes = int(row.get("successes") or 0)
        if attempts < 3:
            lines.append(f"- {name}: {successes}/{attempts} attempts, keep the playbook default until there are 3 samples.")
            continue
        rate = successes / attempts
        if rate < 0.34:
            lines.append(f"- {name}: {successes}/{attempts} succeeded. Prefer a different tactic. Retiring it needs a reviewed PR.")
        elif rate > 0.66:
            lines.append(f"- {name}: {successes}/{attempts} succeeded. Prefer this tactic when the symptom matches.")
        else:
            lines.append(f"- {name}: {successes}/{attempts} succeeded. No change.")
    unresolved = [row for row in stores.lessons.lessons if row.get("fix") == "unresolved"]
    for row in unresolved:
        lines.append(
            f"- New failure {row.get('symptom')} via {row.get('tactic')} is in the lessons store. "
            "Add a fix only through a reviewed PR."
        )
    if not lines:
        lines.append("- No tactic has a recorded outcome yet.")
    return "\n".join(lines)
