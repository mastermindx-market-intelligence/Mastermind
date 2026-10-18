"""Small in-memory mutation controls. Never edits source or calls a provider.

A mutation counts as caught only if its named behavioral assertion fails.
Import/runtime errors are NOT scored as caught. This is author testing, not an
independent reviewer or a complete mutation-coverage claim.
"""
from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/native_context/adapter.py"


def load(source: str, label: str):
    name = "_native_context_mutant_" + label
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, str(SOURCE), "exec"), module.__dict__)
    return module


def inputs(module, **edits):
    binding = module.Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, "b" * 40)
    data = {"schema": "context_bundle.v1", "target": {"workstream": "WS:EXAMPLE-CONTEXT"},
            "repo_sha": "a" * 40, "source_records_digest": "sha256:" + "c" * 64,
            "generated_at": "2026-10-09T22:00:00Z", "sections": [], "excluded": [],
            "omitted_due_to_budget": [], "degraded": [], "no_answer_reason": None}
    data.update(edits)
    return binding, json.dumps(data).encode()


def render(module, binding, raw, ok=True):
    return module.render_hook(b'{"hook_event_name":"SessionStart","source":"startup"}',
                              provider="codex", binding=binding, hydrate=True,
                              reader=lambda *_: module.ReaderResult(ok, raw))


def text(response):
    return response["hookSpecificOutput"]["additionalContext"]


def wrong_pin(module):
    binding, raw = inputs(module, repo_sha="d" * 40)
    assert "INVALID_CANONICAL_RESPONSE" in text(render(module, binding, raw))


def wrong_target(module):
    binding, raw = inputs(module, target={"workstream": "WS:WRONG"})
    assert "INVALID_CANONICAL_RESPONSE" in text(render(module, binding, raw))


def overbudget(module):
    binding, raw = inputs(module, sections=["WITHHELD_SENTINEL" * 1500])
    result = text(render(module, binding, raw))
    assert "WITHHELD_SENTINEL" not in result and "NAVIGATION_ONLY_OVER_BUDGET" in result


def failure_payload(module):
    binding, raw = inputs(module)
    assert "READER_UNAVAILABLE" in text(render(module, binding, raw, ok=False))


def duplicate(module):
    binding, raw = inputs(module)
    raw = raw[:-1] + b',"schema":"context_bundle.v1"}'
    assert "INVALID_CANONICAL_RESPONSE" in text(render(module, binding, raw))


def no_controls(module):
    binding, raw = inputs(module)
    assert set(render(module, binding, raw)) == {"hookSpecificOutput"}


def fork_orientation(module):
    out = module.render_hook(b'{"hook_event_name":"SessionStart","source":"fork"}',
                             provider="claude")
    assert "FORK_REQUIRES_REBIND" in text(out)


def codex_output_limit(module):
    fragment = module.hook_fragment(provider="codex", python=Path("/python"),
                                    script=Path("/release/hook.py"))
    assert fragment["hooks"]["SessionStart"][0]["hooks"][0]["additionalContextLimit"] == 0


def reconciliation(module):
    binding, _ = inputs(module)
    out = module.render_hook(b'{"hook_event_name":"SessionStart","source":"startup"}',
                             provider="codex", binding=binding, hydrate=True,
                             reader=lambda *_: module.ReaderResult(False, reason="canonical_read_failed"))
    assert "READER_RECONCILIATION_REQUIRED" in text(out)


MUTATIONS = [
    ("claude-fork", 'if event["source"] == "fork":', 'if False:', fork_orientation),
    ("codex-second-truncation", 'handler["additionalContextLimit"] = 0',
     'handler["additionalContextLimit"] = 2500', codex_output_limit),
    ("reader-reconciliation", '"canonical_read_failed", "canonical_reader_unavailable_reconcile"',
     '"different_reason", "another_reason"', reconciliation),
    ("source-pin", 'if data.get("repo_sha") != binding.expected_macro_sha:', 'if False:', wrong_pin),
    ("workstream-target", 'if type(target) is not dict or target.get("workstream") != "WS:" + binding.workstream:',
     'if False:', wrong_target),
    ("output-budget", 'if _fits(loaded, max_context_bytes):', 'if True:', overbudget),
    ("failed-read", 'if type(result) is not ReaderResult or result.ok is not True:', 'if False:', failure_payload),
    ("duplicate-json", 'if key in result:', 'if False:', duplicate),
    ("hook-authority-fields", 'return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}',
     'return {"permissionDecision": "allow", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}',
     no_controls),
]


def main() -> int:
    raw = SOURCE.read_bytes()
    source = raw.decode()
    original_digest = hashlib.sha256(raw).hexdigest()
    rows = []
    for name, old, new, probe in MUTATIONS:
        if source.count(old) != 1:
            raise RuntimeError("non-exact mutation selector: " + name)
        probe(load(source, name + "_baseline"))
        modified = load(source.replace(old, new, 1), name)
        try:
            probe(modified)
            outcome = "SURVIVED"
        except AssertionError:
            outcome = "CAUGHT_BY_ASSERTION"
        except Exception:
            outcome = "INVALID_MUTATION_RUNTIME_ERROR"
        rows.append({"mutation": name, "baseline": "PASS", "outcome": outcome})
    unchanged = hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original_digest
    result = {"scope": f"{len(MUTATIONS)} selected author-written boundary mutations; no native model calls",
              "source_sha256": original_digest, "source_unchanged": unchanged, "results": rows}
    print(json.dumps(result, indent=2))
    return int(not unchanged or any(r["outcome"] != "CAUGHT_BY_ASSERTION" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
