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
    # The capacity purpose shares the incumbent server and its authfile, so its
    # root-gated lifecycle is proven in this same isolated root fixture: outside
    # it those tests skip, and a skipped install/rollback is not evidence.
    suites = ["tests/test_application_tunnel_entry.py", "tests/test_application_tunnel_control.py",
              "tests/test_application_tunnel_lifecycle.py", "tests/test_os_tunnel_entry.py",
              "tests/test_hermes_primary_application_tunnel.py", "tests/test_application_tunnel_home.py",
              "tests/test_capacity_tunnel_entry.py", "tests/test_capacity_tunnel_control.py"]
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
        required = {"test_home_successor_reuses_existing_unit_credential_and_reverse_journals",
                    "test_home_server_lost_ack_reconciles_without_rewriting",
                    "test_home_restart_lost_ack_uses_original_observation_without_second_command",
                    "test_home_active_ssh_stream_refuses_transition_without_restart_intent",
                    "test_role_successor_preserves_credential_inode_and_original_journals",
                    "test_role_server_lost_ack_reconciles_original_acl_once",
                    "test_role_partial_client_publication_recovers_from_original_v2_intent",
                    "test_role_client_stage_requires_no_server_filesystem",
                    "test_unknown_original_start_never_authorizes_role_successor",
                    "test_real_cli_stage_server_apply_and_reconciliation",
                    "test_server_lost_ack_reconciles_original_committed_grant",
                    "test_loaded_label_without_running_pid_cannot_claim_start",
                    "test_actual_linux_process_image_observation_binds_this_running_python",
                    "test_actual_application_reader_accepts_owned_private_file_without_acl",
                    "test_stage_records_the_capacity_identity_and_a_closed_server_bundle",
                    "test_stage_refuses_a_credential_rotation_on_the_original_operation",
                    "test_apply_server_adds_one_capacity_acl_and_preserves_the_incumbent",
                    "test_apply_server_is_serialized_on_the_incumbent_application_server_lock",
                    "test_apply_client_installs_only_capacity_targets_and_lifecycle_is_proven",
                    "test_start_client_refuses_without_a_proven_server_grant",
                    "test_apply_client_refuses_a_target_that_changed_after_the_stage",
                    "test_rollback_restores_the_incumbent_authfile_and_removes_only_capacity_files",
                    "test_rollback_never_touches_an_application_owned_authfile_entry",
                    "test_rollback_preserves_an_application_grant_added_after_the_capacity_apply",
                    "test_rollback_refuses_when_the_capacity_entry_itself_drifted"}
        observed = {node.get("name") for node in document.iter("testcase")}
        if not required <= observed or totals["tests"] < len(required) or any(
                totals[key] for key in ("failures", "errors", "skipped")):
            raise SystemExit("required positive transport proof missing: " + json.dumps(totals, sort_keys=True))
        print("TRANSPORT_SOURCE_PROOF " + json.dumps(totals, sort_keys=True))
        print("Proves both the application and capacity transport root suites.")
        print("Synthetic fixtures only; no installed grant, daemon, tunnel or provider effect.")


if __name__ == "__main__":
    main()

