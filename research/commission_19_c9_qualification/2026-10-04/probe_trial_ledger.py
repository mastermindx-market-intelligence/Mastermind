"""Reproduce C9 accounting failures against one hash-pinned owner module.

This is research evidence, not an alternate ledger or an evaluation adapter.
It imports only the supplied, verified stdlib-only module and uses temporary
synthetic files. It never uses the module's default production ledger path.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import tempfile
from pathlib import Path


SOURCE = {
    "repository": "mastermindx-market-intelligence/macro",
    "commit": "9201f1602bfe47e05a63d61802fbed6f7f55a19d",
    "path": "engine/trial_ledger.py",
    "git_blob": "eb364fe9fa53f46d0455e194d3e3ccdbb5732778",
    "sha256": "7b99683c9aee822df138d35b8294318e3316c3b6a8b5a80934614141a15413f7",
}


def probe(source_path: Path) -> dict:
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if digest != SOURCE["sha256"]:
        raise ValueError("source digest mismatch; recensus before executing")
    spec = importlib.util.spec_from_file_location("c19_pinned_trial_ledger", source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    with tempfile.TemporaryDirectory(prefix="c19-synthetic-ledger-") as directory:
        root = Path(directory)
        for kind in ("trial", "declared_budget"):
            parent = root / kind
            parent.write_text("synthetic I/O obstruction", encoding="utf-8")
            ledger_path = parent / "synthetic.jsonl"
            ledger = module.TrialLedger(path=ledger_path, family="c19_synthetic")

            def append():
                if kind == "trial":
                    return ledger.log_trial({"synthetic_case": 1})
                return ledger.log_declared_budget(7, reason="synthetic fixture")

            def count(instance):
                return instance.literal_n() if kind == "trial" else instance.declared_budget()

            first_error = None
            try:
                append()
            except OSError as error:
                first_error = type(error).__name__
            before_repair = count(ledger)
            parent.unlink()
            parent.mkdir()
            retry_result = append()
            after_retry = count(ledger)
            persisted = ledger_path.exists()
            restarted = module.TrialLedger(path=ledger_path, family="c19_synthetic")
            restarted_count = count(restarted)
            positive_path = root / (kind + "_positive.jsonl")
            positive = module.TrialLedger(path=positive_path, family="c19_synthetic")
            if kind == "trial":
                positive_return = positive.log_trial({"synthetic_case": 1})
            else:
                positive_return = positive.log_declared_budget(7, reason="synthetic fixture")
            positive_reload = module.TrialLedger(path=positive_path, family="c19_synthetic")
            positive_count = count(positive_reload)
            reproduced = (
                first_error == "FileExistsError"
                and before_repair > 0
                and retry_result is False
                and after_retry > 0
                and not persisted
                and restarted_count == 0
                and positive_return is True
                and positive_count == (1 if kind == "trial" else 7)
            )
            results.append({
                "case": kind,
                "count_method": "literal_n" if kind == "trial" else "declared_budget",
                "initial_error": first_error,
                "memory_count_after_failed_append": before_repair,
                "retry_return_after_io_repair": retry_result,
                "memory_count_after_retry": after_retry,
                "durable_file_exists": persisted,
                "restarted_count": restarted_count,
                "positive_append_return": positive_return,
                "positive_restarted_count": positive_count,
                "accounting_divergence_reproduced": reproduced,
            })
    return {
        "kind": "research_only_owner_module_synthetic_probe",
        "source": SOURCE,
        "python": platform.python_version(),
        "market_data_used": False,
        "holdout_opened": False,
        "production_ledger_used": False,
        "scope": "failed append and same-instance retry; not concurrency or crash proof",
        "results": results,
        "qualification": "BLOCKED_DURABLE_ACCOUNTING" if all(
            result["accounting_divergence_reproduced"] for result in results
        ) else "REVIEW_REQUIRED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_module", type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.owner_module), indent=2, sort_keys=True))
