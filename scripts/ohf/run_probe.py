"""CLI for the production-inert OHF-P0 harness laboratory.

Default backend is the in-repo fake App Server so CI never launches Codex,
never spends quota, and never touches Executive OS state.  Pass ``--live``
only on an operator workstation that already has an independently
authenticated dedicated Codex home.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from scripts.ohf.codex_app_server_probe import run_codex_app_server_probe
from scripts.ohf.laboratory import Laboratory, REPO_ROOT
from scripts.ohf.probe_schema import validate_probe, write_evidence
from scripts.ohf.redaction import evidence_contains_secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OHF-P0 Codex App Server probe")
    parser.add_argument("--backend", choices=("fake", "live"), default="fake")
    parser.add_argument("--live", action="store_true", help="alias for --backend live")
    parser.add_argument(
        "--codex-home",
        default="",
        help="Already-authenticated dedicated Codex home. Required for --live. Never ~/.codex.",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Directory for probe.json and probe.md (default: research/evidence/ohf_p0/<id>)",
    )
    parser.add_argument("--workdir", default="", help="Isolated laboratory root")
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args(argv)
    backend = "live" if args.live else args.backend
    dedicated = Path(args.codex_home).expanduser() if args.codex_home else None
    if backend == "live" and dedicated is None:
        print(
            "OHF-P0 live mode requires --codex-home pointing at a dedicated, "
            "already-authenticated Codex home.\n"
            "Prepare it with:\n"
            "  CODEX_HOME=/path/to/dedicated/home codex login\n"
            "Then:\n"
            "  python -m scripts.ohf.run_probe --live "
            "--codex-home /path/to/dedicated/home --out-dir /tmp/ohf-p0-live",
            file=sys.stderr,
        )
        return 2

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="ohf-p0-"))
    try:
        lab = Laboratory(
            root=workdir,
            backend=backend,
            requested_model=args.model,
            dedicated_codex_home=dedicated,
        )
    except RuntimeError as exc:
        print(f"OHF-P0: {exc}", file=sys.stderr)
        return 2
    probe = run_codex_app_server_probe(lab)
    defects = validate_probe(probe)
    if evidence_contains_secret(probe):
        print("OHF-P0: refusing to write evidence that still contains secret-shaped values", file=sys.stderr)
        return 2
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else REPO_ROOT / "research" / "evidence" / "ohf_p0" / lab.probe_id
    )
    json_path, md_path = write_evidence(probe, out_dir)
    print(json_path)
    print(md_path)
    if defects:
        print("schema defects: " + ", ".join(defects), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
