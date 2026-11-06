"""Require the actual isolated root transport suites with no skipped proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def main():
    if os.geteuid() != 0 or not sys.platform.startswith("linux"):
        raise SystemExit("the transport proof requires its isolated Linux root fixture")
    root = Path(__file__).resolve().parents[2]
    suites = ["tests/test_application_tunnel_entry.py", "tests/test_application_tunnel_control.py",
              "tests/test_application_tunnel_lifecycle.py", "tests/test_os_tunnel_entry.py"]
    with tempfile.TemporaryDirectory(prefix="application-transport-proof-") as directory:
        report = Path(directory) / "proof.xml"
        result = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-o", "addopts=",
                                 "--noconftest", "-p", "no:cacheprovider", "--tb=short",
                                 "--junitxml=" + str(report), *suites], cwd=root)
        if result.returncode:
            raise SystemExit(result.returncode)
        document = ET.parse(report).getroot()
        totals = {key: sum(int(node.get(key, "0")) for node in document.iter("testsuite"))
                  for key in ("tests", "failures", "errors", "skipped")}
        required = {"test_real_cli_stage_server_apply_and_reconciliation",
                    "test_server_lost_ack_reconciles_original_committed_grant",
                    "test_loaded_label_without_running_pid_cannot_claim_start",
                    "test_actual_linux_process_image_observation_binds_this_running_python",
                    "test_actual_application_reader_accepts_owned_private_file_without_acl"}
        observed = {node.get("name") for node in document.iter("testcase")}
        if not required <= observed or totals["tests"] < len(required) or any(
                totals[key] for key in ("failures", "errors", "skipped")):
            raise SystemExit("required positive transport proof missing: " + json.dumps(totals, sort_keys=True))
        print("APPLICATION_TRANSPORT_SOURCE_PROOF " + json.dumps(totals, sort_keys=True))
        print("Synthetic fixtures only; no installed grant, daemon, tunnel or provider effect.")


if __name__ == "__main__":
    main()
