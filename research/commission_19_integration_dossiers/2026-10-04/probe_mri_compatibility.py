#!/usr/bin/env python3
"""C17 E01 synthetic source-compatibility probe; no network and no repo writes."""
import argparse
import ast
import hashlib
import json
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

READER_SHA256 = "8757c8728b9ca566d2303853da69572c74a7ace61e1d810d66cbbb2f837581ae"
PRODUCER_SHA256 = "5f3448c442481592940b314e6db4ce4b9994edc4b1c9d4446445bc81ee3ef0ec"


def checked_text(path: Path, expected: str) -> str:
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise SystemExit(f"REFUSED_ALTERED_SOURCE {path}: expected={expected} actual={actual}")
    return content.decode("utf-8")


def one_function(module: ast.Module, name: str) -> ast.FunctionDef:
    found = [n for n in ast.walk(module) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise SystemExit(f"REFUSED_FUNCTION_CARDINALITY {name}: {len(found)}")
    return found[0]


def literal_constant(module: ast.Module, name: str) -> str:
    found = [n.value for n in module.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    if len(found) != 1:
        raise SystemExit(f"REFUSED_CONSTANT_CARDINALITY {name}: {len(found)}")
    value = ast.literal_eval(found[0])
    if not isinstance(value, str):
        raise SystemExit(f"REFUSED_NONSTRING_CONSTANT {name}")
    return value


def latest_assignment(module: ast.Module) -> ast.Assign:
    build = one_function(module, "build")
    found = [n for n in ast.walk(build) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "latest" for t in n.targets)]
    if len(found) != 1:
        raise SystemExit(f"REFUSED_LATEST_ASSIGNMENT_CARDINALITY {len(found)}")
    return found[0]


def assemble_latest(assign: ast.Assign) -> dict:
    # Only names read by the exact dict assignment receive synthetic values.
    synthetic = {
        "asof_utc": "synthetic-2026-10-04T00:00:00Z",
        "coherent_target_refit_status": "synthetic_withheld",
        "coherent_current_projection_n": 0,
        "scoreboard": {"by_release": {"cpi_headline": {"n": 0}, "cpi_core": {"n": 0}}},
        "last_scored_all_forward": None,
        "upcoming_block": [{"release_type": "cpi_headline", "surprise_skew": {"sigma_scale_pp": 0.31}}],
        "last_scored": None,
        "capture_health": {"synthetic": True},
        "_OFFICIAL_ACTUALS_RELPATH": "data/release_forecast/official_actuals.jsonl",
        "sum": sum,
        "int": int,
    }
    exact = ast.Module(body=[assign], type_ignores=[])
    exec(compile(ast.fix_missing_locations(exact), "producer_latest_assignment", "exec"), synthetic)
    result = synthetic["latest"]
    if not isinstance(result, dict):
        raise SystemExit("REFUSED_LATEST_NOT_DICT")
    return result


@contextmanager
def synthetic_config(root: Path):
    previous = sys.modules.get("lib")
    lib = types.ModuleType("lib")
    lib.config = types.SimpleNamespace(ROOT=root)
    sys.modules["lib"] = lib
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("lib", None)
        else:
            sys.modules["lib"] = previous


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", type=Path, required=True)
    parser.add_argument("--producer", type=Path, required=True)
    args = parser.parse_args()
    reader_text = checked_text(args.reader, READER_SHA256)
    producer_text = checked_text(args.producer, PRODUCER_SHA256)
    reader_module = ast.parse(reader_text, filename=str(args.reader))
    producer_module = ast.parse(producer_text, filename=str(args.producer))
    reader_node = one_function(reader_module, "_read_mri_surprise_dispersion")
    emitted_relative_path = literal_constant(producer_module, "_SITE_RELPATH")
    emitted = assemble_latest(latest_assignment(producer_module))
    reader_exact = ast.Module(body=[reader_node], type_ignores=[])
    reader_namespace: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="c17-e01-local-") as tmp:
        root = Path(tmp)
        with synthetic_config(root):
            exec(compile(ast.fix_missing_locations(reader_exact), str(args.reader), "exec"), reader_namespace)
            reader = reader_namespace["_read_mri_surprise_dispersion"]
            out = root / emitted_relative_path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(emitted), encoding="utf-8")
            path_result = reader("cpi")
            expected = root / "site/release_forecast/latest.json"
            expected.parent.mkdir(parents=True, exist_ok=True)
            expected.write_text(json.dumps(emitted), encoding="utf-8")
            shape_result = reader("cpi")
            positive_shape = {
                "schema": "release_forecast.v2", "asof": "synthetic-2026-10-04T00:00:00Z",
                "CPI": {"surprise_skew": {"sigma_scale_pp": 0.31}, "prediction_spread_sigma": 1.2,
                        "expectation_read": {"tag": "aligned"}},
            }
            expected.write_text(json.dumps(positive_shape), encoding="utf-8")
            positive = reader("cpi")
    expected_positive = {
        "release_type": "cpi", "sigma_surprise": 0.31, "pred_spread_sigma": 1.2,
        "expectation_read": {"tag": "aligned"}, "asof": "synthetic-2026-10-04T00:00:00Z", "available": True,
    }
    assertions = {
        "path_lookup_returns_none": path_result is None,
        "producer_shape_returns_none": shape_result is None,
        "positive_control_exact": positive == expected_positive,
    }
    print(json.dumps({
        "classification": "assembly_only_synthetic_proof",
        "macro_source_revision": "9201f1602bfe47e05a63d61802fbed6f7f55a19d",
        "source": {"reader_sha256": READER_SHA256, "producer_sha256": PRODUCER_SHA256,
                   "reader_function_ast_sha256": hashlib.sha256(ast.dump(reader_node, include_attributes=False).encode()).hexdigest(),
                   "producer_site_relpath": emitted_relative_path},
        "results": {"path_lookup": path_result, "producer_shape": shape_result, "positive_control": positive},
        "assertions": assertions, "passed": all(assertions.values()),
        "scope": "Source files were read after hash verification. No module top-level or full producer executed; all upstream values and files were synthetic temporary inputs. No real/runtime data was read or changed.",
    }, indent=2, sort_keys=True))
    if not all(assertions.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
