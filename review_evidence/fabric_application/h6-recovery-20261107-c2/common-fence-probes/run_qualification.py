"""Run explicit offline probes once and retain complete outcomes."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--label", required=True)
parser.add_argument("--base", type=Path)
parser.add_argument("tests", nargs="+")
args = parser.parse_args()
root = Path(tempfile.mkdtemp(prefix=args.label + "-", dir=args.base)).resolve()
Path("/tmp/" + args.label + "-location.txt").write_text(str(root))
argv = [sys.executable, "-B", "-m", "pytest", "-q", *args.tests,
        "--basetemp", str(root / "fixtures"), "--junitxml", str(root / "result.xml")]
started = time.monotonic()
with (root / "result.log").open("wb") as log:
    result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
cases = []
if (root / "result.xml").exists():
    for case in ET.parse(root / "result.xml").iter("testcase"):
        record = {"name": case.attrib.get("name"), "classname": case.attrib.get("classname"),
                  "failure": case.find("failure") is not None,
                  "error": case.find("error") is not None,
                  "skipped": case.find("skipped") is not None}
        issue = case.find("failure")
        if issue is None:
            issue = case.find("error")
        if issue is not None:
            record["message"] = issue.attrib.get("message", "")
        cases.append(record)
summary = {"root": str(root), "argv": argv, "python": sys.version,
           "rc": result.returncode, "seconds": round(time.monotonic() - started, 3),
           "testcases": len(cases), "failures": sum(c["failure"] for c in cases),
           "errors": sum(c["error"] for c in cases), "skips": sum(c["skipped"] for c in cases),
           "cases": cases,
           "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                     for name in ("result.log", "result.xml") if (root / name).exists()}}
(root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({key: value for key, value in summary.items() if key != "cases"}))
if result.returncode:
    print(json.dumps([{"name": c["name"], "message": c.get("message", "")[:1800]}
                      for c in cases if c["failure"] or c["error"]]))
    if not cases:
        print((root / "result.log").read_text()[-6000:])
raise SystemExit(result.returncode)
