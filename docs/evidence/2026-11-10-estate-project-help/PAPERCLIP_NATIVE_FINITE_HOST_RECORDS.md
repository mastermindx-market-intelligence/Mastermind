# Ordinary finite Hermes: retained original records

These records support the separate finite native qualification. No model provider, installed enrollment, native issue-origin attestation or parent acceptance is claimed. Raw bodies are UTF-8. Each original byte count, SHA256 and terminal-newline fact is retained; a display newline before the closing fence is not part of an original body when terminal_newline=false.

## host-receipt.json

Original bytes: 15966. SHA256: `9975b1bb6b22bb0c18e59f1fa54a10dce6e7b02a2ee1f1caffee90752a06a14f`. terminal_newline=true.

````json
{
  "after_tree": "2b791e5ca7d35446dde1837fa95b399901bd59ce",
  "argv": [
    "python3",
    "-B",
    "-m",
    "pytest",
    "-q",
    "-p",
    "anyio.pytest_plugin",
    "tests/test_paperclip_hermes_api_transport.py",
    "--maxfail=1",
    "--tb=short",
    "--basetemp=/tmp/estate-paperclip-finite-native-discovery-20261110-c4",
    "--junitxml=/tmp/estate-paperclip-finite-native-discovery-20261110-c4.xml"
  ],
  "basetemp": "/tmp/estate-paperclip-finite-native-discovery-20261110-c4",
  "elapsed_seconds": 48.727,
  "junit_sha256": "7001a677da4e829883d8e7168c68559defe1c119253a04ded8f281ad23e6435c",
  "log_sha256": "99db33d5c94c6f7da021687c7391181685cc33299c5435b1c861e2db3be3ec87",
  "native_dependency_fact_sha256": "b29cf28250a1045859e9982af2371bb8797e3aa7f58fe10ab0eef42f8c63a790",
  "native_dependency_fact_unchanged": true,
  "native_patch_installed": false,
  "native_patched_source": {
    "tests/tools/test_tool_search_deferred_schema.py": "1befb7516c76eb1b59ef78c61b15113703ddeaea82712a6a5011b6218d38f4ee",
    "tools/tool_search.py": "bcaf4ed695a5493fdda421f7c969db5a6fd9cf06d8ad92a8cb546c3326f52866"
  },
  "native_patched_source_unchanged": true,
  "native_private_candidate": "/tmp/estate-hermes-native-deferred-schema-ba4ddf9-20261110-c4",
  "native_source": {
    "all_git_blobs_verified": true,
    "archive_format_reconciliations": [
      {
        "archive_blob": "16efe8e095743e4abb2499a1f79bc2941cc2048c",
        "exact_git_blob": "e58ed04c91a3e61d1dac481a8642f6ded946d056",
        "path": "activate.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "f46796efe74769c5f781f2a7b4d0e6fbf5be464e",
        "exact_git_blob": "cc15dc791a016a7494fc3209a43a856268bd996f",
        "path": "apps/desktop/scripts/update-relaunch-waiter.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "75e3fb720c9704bf85ddfb852279892d51d95109",
        "exact_git_blob": "fc486d119cbb6946c9824f89709acdad8b406aa6",
        "path": "apps/desktop/scripts/verify-signed-payloads.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "8f2584db8e0bc8b00b6af3c0aa636fb2415bf1f2",
        "exact_git_blob": "0f3cd764561c60c7205dd35b2ae984607263fe11",
        "path": "evals/update_streaming/watchdog.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "0de81d1634dc7370f2ee7da83013e99053d5e65d",
        "exact_git_blob": "65dd6d8b6c999f8323f94df4bfec679b599708ec",
        "path": "optional-skills/software-development/ast-grep/install.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "4cdf94ed51bebe56339ea04f0756b8349269d093",
        "exact_git_blob": "b051d1ce04ee92cae34d5ece0247de3fa7bb6fe6",
        "path": "optional-skills/software-development/ast-grep/tests/smoke.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "bb33bf20139f0250d3ec1441865601632cb65168",
        "exact_git_blob": "4f6f656fed3836602644c2f2c9c305e2afb3c4c2",
        "path": "scripts/build-bundle.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "bf54bcee7966f7c142cf1fa41c63b5f6c1316370",
        "exact_git_blob": "35c5c171937ce54260a6eb2176c3d4096d317682",
        "path": "scripts/build/windows-deps.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "82cfdc2c70d82c45885c65bce3e2a8b41a5bbe86",
        "exact_git_blob": "5a4bca802e78ccbf1fb441e3db2a129e01b3e38d",
        "path": "scripts/ci/warm_powershell_module_cache.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "431752edf25319e07562c64b4ff5abd7dd4b8661",
        "exact_git_blob": "7b9647873d96278e95f233429d80bff6a269d327",
        "path": "scripts/desktop-update.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "df527495691dde7620fc6cb8d493ad50335ea67f",
        "exact_git_blob": "3ee01affb08fb77d48f527900ff903bbf6e5ae17",
        "path": "scripts/desktop-update/marker-claim.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "95f4b19c44751df36a06a0c7441cf2688b2df0e1",
        "exact_git_blob": "27478317490d18a56e62975f002cf6d18bd0805c",
        "path": "scripts/desktop-update/marker.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "cefc517bbc3234159d64b38f45fd6c01e243d60d",
        "exact_git_blob": "8b6c8260068b6322b3f0e8403516f4d5596ec1c8",
        "path": "scripts/desktop-update/runtime.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "2f57121cd82643d27b8a58386941b54e712882a5",
        "exact_git_blob": "85b5fdedde76652e4476861b99559fa8792d5d36",
        "path": "scripts/desktop-update/update-job.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "2f896e3b52a090b1e90e3567f1d45974e26922d5",
        "exact_git_blob": "8ace25578f616f072f1b4f9b690dd8c7e7d42ab9",
        "path": "scripts/desktop-update/windows.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "b4f55505ad8498d9738d7bb074f177f44debfbee",
        "exact_git_blob": "c0552ec8b9d2fbdc7127ec384c221b683d1e733a",
        "path": "scripts/install.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "caff36d89c4b1213382a769e8640d749bde034cf",
        "exact_git_blob": "997738df80bf39f0ebcf589fc3d1dbac22161e0c",
        "path": "scripts/tests/test-install-ps1-longpath.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "69dbe3273660730a8680b6dce43b35d7f028ddc7",
        "exact_git_blob": "c6f4ca32fef1b99ec23afc960050058ab0021c39",
        "path": "scripts/tests/test-install-ps1-node-compatibility.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "2a22704d4d7a214828f2c7455218928a321ab82c",
        "exact_git_blob": "fdfa2e596a58ef9f1cae24b9b88073087bb50e79",
        "path": "scripts/tests/test-install-ps1-store-guard.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "f4b64c274cffbc17a386265d7df5a6ef5b6cc761",
        "exact_git_blob": "80d7bbf0d1109995263f44404284f64d05734169",
        "path": "scripts/tests/test-install-ps1-utf8.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "542703f53ed2bccd2bb45c879279455c074867bd",
        "exact_git_blob": "7c193027c500dae552797cf917422d7cd9ba73e4",
        "path": "scripts/update-test/hermes-update-rehearsal.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "3529fb2491827f1a18d89601724cf862adfab7e1",
        "exact_git_blob": "d875454651b4c42669ed53b2a712d9d00e4b07f1",
        "path": "scripts/update-test/smoke-test.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "26a583b3fbc70506d40db8c6ccfd2697c8874898",
        "exact_git_blob": "b328a7e1e8da4fde3418114158632a4c1fdad3cc",
        "path": "scripts/windows-build-deps.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "929674f02363018d791d01bf9eea816e3f8e75c9",
        "exact_git_blob": "b3e229dfd98352dae375e2a67ca804d902b128d7",
        "path": "scripts/windows_e2e_harness.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "4371c15b7404edaebbb890990da93e3e0446ec7c",
        "exact_git_blob": "8bb0b64be88019bfdcb9c1871029f7afc354bc9d",
        "path": "setup-hermes.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "c94bdd8b8d3953f12f2975d10d215aebbcf1fd46",
        "exact_git_blob": "2b899ad40e9b8e5d7201ccd3ed47b72fe19ee2a6",
        "path": "tests/install/e2e-assets/desktop-smoke-windows.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "6d3570e7e5df6642cf8bd608702d483e313af6a2",
        "exact_git_blob": "a49e9ac4a505228b771dd38a81e9946b9ab2f36c",
        "path": "tests/install/e2e-assets/record-start.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "c344277c3a47ef490ccf9caade4ad86c57adb43f",
        "exact_git_blob": "594b3a417bf16f46e462d75b38cefb54af3b9fcb",
        "path": "tests/install/e2e-assets/record-stop.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "d82c8a01dcbbd3f74bf65b5d8aa656b09f234420",
        "exact_git_blob": "ff4c7994fd9bb522a7e5e3699cec18349a78211b",
        "path": "tests/install/e2e-assets/source-build-env.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "45ee78dd3ff9566bca94651833c93647573186dd",
        "exact_git_blob": "706bbeca01133095cd8bd5c4ffa2f66ada9005c8",
        "path": "tests/install/e2e-assets/source-driver.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "de870c732523bf24bdc0c15bb0b94281182ac237",
        "exact_git_blob": "cc9acc878055e6ceb9cbffdf0bf55688d810427d",
        "path": "tests/install/e2e-assets/ts-prefix.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "3a3045db1014b7909665ff8fd0f0f3dc20e12d76",
        "exact_git_blob": "45d2904b9c3506226c599067bb5f3c30271146a3",
        "path": "tests/install/e2e-assets/windows-bundle-metadata.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "ec512753ffe846b896b88d5d21a53579422559f8",
        "exact_git_blob": "e1d9d67ec97268eea5b023769d9bb716e2e45b1b",
        "path": "tests/install/e2e-assets/windows-bundle-metadata.test.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "16f07fdca49782b91edb5891fde1513db2473736",
        "exact_git_blob": "544d5f562e463d63a2a61150fade9793deec6e2b",
        "path": "tests/install/e2e-assets/windows-bundle-plugin-smoke.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "f27fc8ff3f96169548d5715c90f28630b1d29bda",
        "exact_git_blob": "20b6c66a7c4585c9c400ae434cea1aacc861ce09",
        "path": "tests/install/e2e-assets/windows-bundled-drive-update.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "49095a962c2dceb8841a3d505e0d7760ff88a0dd",
        "exact_git_blob": "83018e32cadf49afe3c523cf87654d812bd4ce1e",
        "path": "tests/install/e2e-assets/windows-bundled-processes.test.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "3a2c55e5b0bc258c5fbc376eafaf3497ba37b1c0",
        "exact_git_blob": "26cdb812eee107c777cfec0bba3e158d33c0bf5b",
        "path": "tests/install/windows-bundle-smoke.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "f7afc13211e1245a64cf3b1fe20bbdcbda7eebbf",
        "exact_git_blob": "307c57efa69a7800f830879c65ab51a028139136",
        "path": "tests/install/windows-bundled-e2e.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      },
      {
        "archive_blob": "cdb7941defc1e27aeebb83d4e1e7eb973553d650",
        "exact_git_blob": "39702f8cbb570dbdff6184584c6161bef51c4cb9",
        "path": "tests/install/windows-e2e.ps1",
        "reason": "Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes"
      }
    ],
    "archive_sha256": "7cf9cadd02b5421a54ffcdefa4b930f8829a7f291fd511e6d66d2aec4ca7d076",
    "bytes": 243122150,
    "elapsed_seconds": 11.746,
    "files": 22553,
    "ref": "ba4ddf9945a213ede9dda016602a86591ed634f9",
    "schema": "mastermind.native_source_snapshot.v1",
    "source": "/tmp/estate-hermes-native-source-ba4ddf9-20261110-c4",
    "tree": "cd69b1c914e644149423b98211d18789e1161eff"
  },
  "pytest_pid": 85128,
  "returncode": 0,
  "source": {
    "control_plane/coo_principal_host.py": "5469b4d1f4b88393a781bbf387efd23f4183c6f504defd6e2a7ec5c2cc99ac24",
    "control_plane/executive_runtime.py": "363276f69185150e4089fbfe03fcd7121197cc5427a37870169fccf9c59da516",
    "control_plane/executive_service.py": "b2191c2a96de45ee2ff7dc5cd4e55d6bc9163a6d9b110c45725b8de7d8851016",
    "control_plane/mission_workspace.py": "61d962771dc9823204d80c5838fc1fe4ae8009b669141db11372a41f9c8ffc20",
    "control_plane/runtime_namespace_custody.py": "0e4255b9ec9ddda5b613b2bf610156b221aa5efadf51702be0d62ad5f3776cf2",
    "control_plane/workspace_read_service.py": "291f290848ab65507c10fbd205cc566fcdcdb5b937b24746a92ef97120aca254",
    "tests/paperclip_hermes_native_client.py": "7e92d1e619ad47aa7be76b54c2e0658ddfd24ba1588d16698e40bbfdc065cd8c",
    "tests/test_joint_api_ingress.py": "fa5367923ae15aff15019f3799c3b0edfbb5ec0c8dc162a39a33777bc789dc07",
    "tests/test_joint_api_project_owner.py": "72f45a1090f3533f1d98c832f852c0aa18d65d2ed489663abd7aff5ab9f16d58",
    "tests/test_paperclip_hermes_api_transport.py": "cc9f85a25ab863ed7c960c0ee5d5238101610be80e9770716e48e819336ad947"
  },
  "source_unchanged": true,
  "suites": [
    {
      "errors": "0",
      "failures": "0",
      "hostname": "m2studio",
      "name": "pytest",
      "skipped": "0",
      "tests": "2",
      "time": "46.043",
      "timestamp": "2026-11-10T08:23:46.303739-07:00"
    }
  ],
  "tree": "2b791e5ca7d35446dde1837fa95b399901bd59ce"
}
````

## host-junit.xml

Original bytes: 604. SHA256: `7001a677da4e829883d8e7168c68559defe1c119253a04ded8f281ad23e6435c`. terminal_newline=false.

````xml
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="46.043" timestamp="2026-11-10T08:23:46.303739-07:00" hostname="m2studio"><testcase classname="tests.test_paperclip_hermes_api_transport" name="test_finite_native_hermes_requester_uses_original_http_and_unix_owners[normal-paperclip]" time="24.698" /><testcase classname="tests.test_paperclip_hermes_api_transport" name="test_finite_native_hermes_requester_uses_original_http_and_unix_owners[lost_response-paperclip]" time="19.717" /></testsuite></testsuites>
````

## host-output.log

Original bytes: 80. SHA256: `99db33d5c94c6f7da021687c7391181685cc33299c5435b1c861e2db3be3ec87`. terminal_newline=true.

````text
..                                                                       [100%]
````

## lazy-module-smoke-original.json

Original bytes: 667. SHA256: `fc891889b2483d52ccc9b845b47060cc10842694d2693057e32c62d33588c705`. terminal_newline=true.

````json
{
  "returncode": 0,
  "output": "{\"claim_or_ack_authority_proved\": false, \"described_tools\": [\"mcp_estate_schema_preflight_executive_project_help\", \"mcp_estate_schema_preflight_mmx_delegate\"], \"invalid_schema_refused\": true, \"model_tools\": [\"tool_search\", \"tool_describe\", \"tool_call\"], \"native_source\": \"ba4ddf9945a213ede9dda016602a86591ed634f9\", \"network_or_provider_invoked\": false, \"normal_bridge_inert_dispatches\": 1, \"outside_session_refused\": true}\nLAZY_NATIVE_MODULE_CLOSURE_PROVED_BEFORE_MCP_EFFECT\n",
  "network_or_provider_invoked": false,
  "native_source": "/tmp/estate-hermes-native-deferred-schema-ba4ddf9-20261110-c4"
}
````

## normal/native-return.json

Original bytes: 10581. SHA256: `bf5f0b6b6d7bdbc12946fb6047566369565ef30bbdb392336eb3581ce5361e65`. terminal_newline=true.

````json
{
  "acknowledgment": {
    "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
    "attempt_number": 1,
    "attempt_status": "COMPLETED",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": "COMPLETED",
    "live_submit": true,
    "operation_key": "exec-job-003",
    "orchestration_role": "work",
    "reason": null,
    "requester_return": {
      "acceptance": "not_accepted",
      "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "consumption": {
        "acknowledged_at_ms": 1794324251652,
        "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
        "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
        "family": "coo_api_principal",
        "job_id": "JOB-003",
        "parent_job_id": "JOB-001",
        "requester_binding_digest": "f8c1bcb445540a350d41c766d4b719592a8e7577780116e86157b136f053571b",
        "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
        "root_job_id": "JOB-001",
        "schema_version": "mastermind.coo_selected_child_requester_consumption/v1",
        "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
        "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
      },
      "family": "coo_api_principal",
      "job_id": "JOB-003",
      "parent_consumed": false,
      "parent_job_id": "JOB-001",
      "requester_binding_digest": "f8c1bcb445540a350d41c766d4b719592a8e7577780116e86157b136f053571b",
      "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
      "root_job_id": "JOB-001",
      "schema_version": "mastermind.coo_selected_child_requester_return/v1",
      "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
      "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
    },
    "result_capsule": {
      "artifact_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "effective_grant_digest": "2e2283341737dc2c731a2574959d6d64295a817b1bcfa6a4f58f440be5953030",
      "job_id": "JOB-003",
      "next_actions": [],
      "parent_consumed": false,
      "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
      "role": "work",
      "root_job_id": "JOB-001",
      "schema": "mastermind.executive_selected_child_result/v1",
      "summary": "bounded typed fixture result",
      "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
      "validation_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    },
    "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
    "result_status": "RESULT",
    "role": "work",
    "root_job_id": "JOB-001",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "session_ref": "asd-session-exec-job-003",
    "state": "COMPLETED",
    "target_digest": "3944e759a4a7243339de48ad585c4eec3ac7fb5693b1ea8e43f0e2e96d768301",
    "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082"
  },
  "described_tools": [
    "mcp__mastermindExecutiveCoo__executive_project_help",
    "mcp__mastermindExecutiveCoo__mmx_delegate"
  ],
  "disabled_toolsets": [
    "onboarding",
    "catalog",
    "clarify"
  ],
  "dispatch": "model_tools.handle_function_call(tool_call; default guards and middleware)",
  "enabled_toolsets": [
    "mastermindExecutiveCoo"
  ],
  "entry": "ensure_mcp_discovery_before_agent_build(single_query=True)",
  "explicit_calls": [
    {
      "action": null,
      "tool": "mcp__mastermindExecutiveCoo__executive_project_help"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_submit",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "acknowledge_result",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    }
  ],
  "final": {
    "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
    "attempt_number": 1,
    "attempt_status": "COMPLETED",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": "COMPLETED",
    "live_submit": true,
    "operation_key": "exec-job-003",
    "orchestration_role": "work",
    "reason": null,
    "requester_return": {
      "acceptance": "not_accepted",
      "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "consumption": {
        "acknowledged_at_ms": 1794324251652,
        "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
        "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
        "family": "coo_api_principal",
        "job_id": "JOB-003",
        "parent_job_id": "JOB-001",
        "requester_binding_digest": "f8c1bcb445540a350d41c766d4b719592a8e7577780116e86157b136f053571b",
        "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
        "root_job_id": "JOB-001",
        "schema_version": "mastermind.coo_selected_child_requester_consumption/v1",
        "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
        "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
      },
      "family": "coo_api_principal",
      "job_id": "JOB-003",
      "parent_consumed": false,
      "parent_job_id": "JOB-001",
      "requester_binding_digest": "f8c1bcb445540a350d41c766d4b719592a8e7577780116e86157b136f053571b",
      "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
      "root_job_id": "JOB-001",
      "schema_version": "mastermind.coo_selected_child_requester_return/v1",
      "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
      "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
    },
    "result_capsule": {
      "artifact_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "effective_grant_digest": "2e2283341737dc2c731a2574959d6d64295a817b1bcfa6a4f58f440be5953030",
      "job_id": "JOB-003",
      "next_actions": [],
      "parent_consumed": false,
      "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
      "role": "work",
      "root_job_id": "JOB-001",
      "schema": "mastermind.executive_selected_child_result/v1",
      "summary": "bounded typed fixture result",
      "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
      "validation_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    },
    "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
    "result_status": "RESULT",
    "role": "work",
    "root_job_id": "JOB-001",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "session_ref": "asd-session-exec-job-003",
    "state": "COMPLETED",
    "target_digest": "3944e759a4a7243339de48ad585c4eec3ac7fb5693b1ea8e43f0e2e96d768301",
    "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082"
  },
  "missing_workspace_refused": true,
  "model_visible_tools": [
    "tool_search",
    "tool_describe",
    "tool_call"
  ],
  "native_httpx": "2.15.1",
  "native_origin_attested": false,
  "native_ref": "ba4ddf9945a213ede9dda016602a86591ed634f9",
  "native_schema_source_patch": {
    "base_sha256": "87e06c029304dae1ff1f592fa97f238165a04f1406cbdab68a2e3a0c3fd489a5",
    "installed": false,
    "path": "tools/tool_search.py",
    "post_sha256": "bcaf4ed695a5493fdda421f7c969db5a6fd9cf06d8ad92a8cb546c3326f52866"
  },
  "native_sdk": "2.3.0",
  "native_tool_timeout": 300.0,
  "original_native_owner_closed": true,
  "registered_tools": [
    "mcp__mastermindExecutiveCoo__executive_mandate",
    "mcp__mastermindExecutiveCoo__executive_state",
    "mcp__mastermindExecutiveCoo__executive_inbox",
    "mcp__mastermindExecutiveCoo__executive_fabric",
    "mcp__mastermindExecutiveCoo__submit_principal_intent",
    "mcp__mastermindExecutiveCoo__principal_intent_status",
    "mcp__mastermindExecutiveCoo__mmx_delegate",
    "mcp__mastermindExecutiveCoo__executive_agentos_current_context",
    "mcp__mastermindExecutiveCoo__executive_project_help"
  ],
  "reviewed_descriptor": {
    "acceptance": "not_accepted",
    "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "consumption": null,
    "family": "coo_api_principal",
    "job_id": "JOB-003",
    "parent_consumed": false,
    "parent_job_id": "JOB-001",
    "requester_binding_digest": "f8c1bcb445540a350d41c766d4b719592a8e7577780116e86157b136f053571b",
    "result_envelope_digest": "c4a213de931e7e40ddd2295db21c82d822e539edbc6c0b6405f43112b32fa90b",
    "root_job_id": "JOB-001",
    "schema_version": "mastermind.coo_selected_child_requester_return/v1",
    "terminal_evidence_digest": "4e5358e2e04a251d4b419921bb65893554bd4f285eb76eb55c68ddb8f97d7082",
    "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
  },
  "sibling_profile_refused": true,
  "submit": {
    "attempt_id": "ATT-262b27cf44a649218e74be342a4ee8fc",
    "attempt_number": 1,
    "attempt_status": "CLAIMED",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": "RUNNING",
    "live_submit": true,
    "orchestration_role": "work",
    "reason": null,
    "root_job_id": "JOB-001",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "state": "ACTIVE",
    "target_digest": "3944e759a4a7243339de48ad585c4eec3ac7fb5693b1ea8e43f0e2e96d768301"
  },
  "toolset_selection": "hermes_cli.tools_config._get_platform_tools + session_disabled_toolsets(oneshot=True)"
}
````

## normal/native-http-receipt.json

Original bytes: 2653. SHA256: `fc34622ae863db0705e7bc787aa9826c2da41fde801f3ad6db5aa6aa4b86e50e`. terminal_newline=true.

````json
{
  "calls": [
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "initialize",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "notifications/initialized",
      "path": "/mcp/coo",
      "response_status": 202,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/list",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "executive_project_help",
      "workspace_companion": false
    },
    {
      "action": "selected_child_submit",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "acknowledge_result",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    }
  ],
  "native_origin_attested": false,
  "native_returncode": 0
}
````

## normal/native-wire-evidence.json

Original bytes: 3720. SHA256: `4bb3123a5e49743087a2cd45e3a3b20432a8b2ff73ca152db0796d4764818594`. terminal_newline=true.

````json
{
  "app_mcp_sdk": "1.28.1",
  "calls": [
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "initialize",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "notifications/initialized",
      "path": "/mcp/coo",
      "response_status": 202,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/list",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "executive_project_help",
      "workspace_companion": false
    },
    {
      "action": "selected_child_submit",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "acknowledge_result",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "27deb6557746d3e941099b8b8257c6c9b7a4cba253354f7727a69528bd56c46f",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    }
  ],
  "claim": {
    "capability_profile_digest": "0e4ceedc7e9fdd4a298216ef0451ebdae8a699f5bfbbe7a9c95893af1c4e54fb",
    "context": {
      "authority_generation_digest": "e1423ac277c44820265e886e2145b7882c32dc2e2e605dd6ba8c0260639d30b6",
      "mission_authority_ref": "authority:coo-test",
      "principal_binding_digest": "00331e020e1941361228e53c7caf69b92bed10e07b1e59c3ee7934be59736458",
      "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
    },
    "family": "coo_api_principal",
    "schema_version": "mastermind.coo_selected_child_requester/v1",
    "selection": {
      "attempt_ordinal": 1,
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "expected_current_attempt_id": null,
      "job_id": "JOB-003",
      "parent_job_id": "JOB-001",
      "plan_attempt_id": "ATT-88b59aa646a943d9b9caa73cbdab3f00",
      "plan_digest": "9d78e6992cfae255bee4e3bef12bc7edc5568c21fc1b7e28a0a66b7a8c892e45",
      "plan_step_id": "STEP-0",
      "repair_round": 0,
      "root_job_id": "JOB-001"
    }
  },
  "native_mcp_sdk": "2.3.0",
  "native_origin_attested": false
}
````

## normal/native-output.log

Original bytes: 148. SHA256: `c43e7ca1dee4fdea3a64c2170bcb9551ebf460a9f5ed32d02feffe64ed33507f`. terminal_newline=true.

````text
{"native_ref": "ba4ddf9945a213ede9dda016602a86591ed634f9", "native_sdk": "2.3.0", "acknowledgment_state": "COMPLETED", "native_owner_closed": true}
````

## lost-response/native-return.json

Original bytes: 7625. SHA256: `f3a4beaacb657f763f142e78789f3ad6c870ae242712edee92bc1967969426ef`. terminal_newline=true.

````json
{
  "acknowledgment": {
    "attempt_id": null,
    "attempt_status": null,
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": null,
    "live_submit": null,
    "reason": "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "state": "EFFECT_UNKNOWN",
    "target_digest": "c2cefbf23d3ff6a5d38083df0d83d007004a838f597bb063e4cae8042d0cb356"
  },
  "described_tools": [
    "mcp__mastermindExecutiveCoo__executive_project_help",
    "mcp__mastermindExecutiveCoo__mmx_delegate"
  ],
  "disabled_toolsets": [
    "onboarding",
    "catalog",
    "clarify"
  ],
  "dispatch": "model_tools.handle_function_call(tool_call; default guards and middleware)",
  "enabled_toolsets": [
    "mastermindExecutiveCoo"
  ],
  "entry": "ensure_mcp_discovery_before_agent_build(single_query=True)",
  "explicit_calls": [
    {
      "action": null,
      "tool": "mcp__mastermindExecutiveCoo__executive_project_help"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_submit",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "acknowledge_result",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    },
    {
      "action": "selected_child_status",
      "tool": "mcp__mastermindExecutiveCoo__mmx_delegate"
    }
  ],
  "final": {
    "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
    "attempt_number": 1,
    "attempt_status": "COMPLETED",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": "COMPLETED",
    "live_submit": true,
    "operation_key": "exec-job-003",
    "orchestration_role": "work",
    "reason": null,
    "requester_return": {
      "acceptance": "not_accepted",
      "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "consumption": {
        "acknowledged_at_ms": 1794324271365,
        "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
        "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
        "family": "coo_api_principal",
        "job_id": "JOB-003",
        "parent_job_id": "JOB-001",
        "requester_binding_digest": "c204f0569fd75c83d2f8788a4c32974349e41708ac56f56ca78a0e83f08b5e19",
        "result_envelope_digest": "44fbf74d1ee3d3cacbcbcb5c4146c0aea75bc0a999af99051404e503fee844a8",
        "root_job_id": "JOB-001",
        "schema_version": "mastermind.coo_selected_child_requester_consumption/v1",
        "terminal_evidence_digest": "54b60ce3d94cdd36b27eaf7c667cb5b6911e42adeb350ae3b8fe0178b3c69477",
        "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
      },
      "family": "coo_api_principal",
      "job_id": "JOB-003",
      "parent_consumed": false,
      "parent_job_id": "JOB-001",
      "requester_binding_digest": "c204f0569fd75c83d2f8788a4c32974349e41708ac56f56ca78a0e83f08b5e19",
      "result_envelope_digest": "44fbf74d1ee3d3cacbcbcb5c4146c0aea75bc0a999af99051404e503fee844a8",
      "root_job_id": "JOB-001",
      "schema_version": "mastermind.coo_selected_child_requester_return/v1",
      "terminal_evidence_digest": "54b60ce3d94cdd36b27eaf7c667cb5b6911e42adeb350ae3b8fe0178b3c69477",
      "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
    },
    "result_capsule": {
      "artifact_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "effective_grant_digest": "2e2283341737dc2c731a2574959d6d64295a817b1bcfa6a4f58f440be5953030",
      "job_id": "JOB-003",
      "next_actions": [],
      "parent_consumed": false,
      "result_envelope_digest": "44fbf74d1ee3d3cacbcbcb5c4146c0aea75bc0a999af99051404e503fee844a8",
      "role": "work",
      "root_job_id": "JOB-001",
      "schema": "mastermind.executive_selected_child_result/v1",
      "summary": "bounded typed fixture result",
      "terminal_evidence_digest": "54b60ce3d94cdd36b27eaf7c667cb5b6911e42adeb350ae3b8fe0178b3c69477",
      "validation_receipt_digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    },
    "result_envelope_digest": "44fbf74d1ee3d3cacbcbcb5c4146c0aea75bc0a999af99051404e503fee844a8",
    "result_status": "RESULT",
    "role": "work",
    "root_job_id": "JOB-001",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "session_ref": "asd-session-exec-job-003",
    "state": "COMPLETED",
    "target_digest": "c2cefbf23d3ff6a5d38083df0d83d007004a838f597bb063e4cae8042d0cb356",
    "terminal_evidence_digest": "54b60ce3d94cdd36b27eaf7c667cb5b6911e42adeb350ae3b8fe0178b3c69477"
  },
  "missing_workspace_refused": true,
  "model_visible_tools": [
    "tool_search",
    "tool_describe",
    "tool_call"
  ],
  "native_httpx": "2.15.1",
  "native_origin_attested": false,
  "native_ref": "ba4ddf9945a213ede9dda016602a86591ed634f9",
  "native_schema_source_patch": {
    "base_sha256": "87e06c029304dae1ff1f592fa97f238165a04f1406cbdab68a2e3a0c3fd489a5",
    "installed": false,
    "path": "tools/tool_search.py",
    "post_sha256": "bcaf4ed695a5493fdda421f7c969db5a6fd9cf06d8ad92a8cb546c3326f52866"
  },
  "native_sdk": "2.3.0",
  "native_tool_timeout": 300.0,
  "original_native_owner_closed": true,
  "registered_tools": [
    "mcp__mastermindExecutiveCoo__executive_mandate",
    "mcp__mastermindExecutiveCoo__executive_state",
    "mcp__mastermindExecutiveCoo__executive_inbox",
    "mcp__mastermindExecutiveCoo__executive_fabric",
    "mcp__mastermindExecutiveCoo__submit_principal_intent",
    "mcp__mastermindExecutiveCoo__principal_intent_status",
    "mcp__mastermindExecutiveCoo__mmx_delegate",
    "mcp__mastermindExecutiveCoo__executive_agentos_current_context",
    "mcp__mastermindExecutiveCoo__executive_project_help"
  ],
  "reviewed_descriptor": {
    "acceptance": "not_accepted",
    "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "consumption": null,
    "family": "coo_api_principal",
    "job_id": "JOB-003",
    "parent_consumed": false,
    "parent_job_id": "JOB-001",
    "requester_binding_digest": "c204f0569fd75c83d2f8788a4c32974349e41708ac56f56ca78a0e83f08b5e19",
    "result_envelope_digest": "44fbf74d1ee3d3cacbcbcb5c4146c0aea75bc0a999af99051404e503fee844a8",
    "root_job_id": "JOB-001",
    "schema_version": "mastermind.coo_selected_child_requester_return/v1",
    "terminal_evidence_digest": "54b60ce3d94cdd36b27eaf7c667cb5b6911e42adeb350ae3b8fe0178b3c69477",
    "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
  },
  "sibling_profile_refused": true,
  "submit": {
    "attempt_id": "ATT-19bb2bcad07a4482a6b0ae83a95a8d3a",
    "attempt_number": 1,
    "attempt_status": "CLAIMED",
    "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
    "job_id": "JOB-003",
    "job_status": "RUNNING",
    "live_submit": true,
    "orchestration_role": "work",
    "reason": null,
    "root_job_id": "JOB-001",
    "schema": "mastermind.hermes_delegate.selected_child/v1",
    "state": "ACTIVE",
    "target_digest": "c2cefbf23d3ff6a5d38083df0d83d007004a838f597bb063e4cae8042d0cb356"
  },
  "toolset_selection": "hermes_cli.tools_config._get_platform_tools + session_disabled_toolsets(oneshot=True)"
}
````

## lost-response/native-http-receipt.json

Original bytes: 2653. SHA256: `e60924f5228980ba9c93ea028c147f511ebf3ec8b03a8c22db42cc8e932761b1`. terminal_newline=true.

````json
{
  "calls": [
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "initialize",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "notifications/initialized",
      "path": "/mcp/coo",
      "response_status": 202,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/list",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "executive_project_help",
      "workspace_companion": false
    },
    {
      "action": "selected_child_submit",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "acknowledge_result",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    }
  ],
  "native_origin_attested": false,
  "native_returncode": 0
}
````

## lost-response/native-wire-evidence.json

Original bytes: 3720. SHA256: `fb140d5e141686a9faf6981d74c9d02be47ad0ba6edabc32916dc6dff7e3729e`. terminal_newline=true.

````json
{
  "app_mcp_sdk": "1.28.1",
  "calls": [
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "initialize",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "notifications/initialized",
      "path": "/mcp/coo",
      "response_status": 202,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/list",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": null,
      "workspace_companion": false
    },
    {
      "action": null,
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "executive_project_help",
      "workspace_companion": false
    },
    {
      "action": "selected_child_submit",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "acknowledge_result",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    },
    {
      "action": "selected_child_status",
      "authorization_sha256": "1d16785c572ebbca3a2b94580e14ae809be5b47adc6e1ef7ef26dea64ebff425",
      "http_method": "POST",
      "method": "tools/call",
      "path": "/mcp/coo",
      "response_status": 200,
      "tool": "mmx_delegate",
      "workspace_companion": false
    }
  ],
  "claim": {
    "capability_profile_digest": "0e4ceedc7e9fdd4a298216ef0451ebdae8a699f5bfbbe7a9c95893af1c4e54fb",
    "context": {
      "authority_generation_digest": "ebd058cc9d0120c47d7287606b8474bc1bba13fc63be9e3a1ed1ba5ea4b717f2",
      "mission_authority_ref": "authority:coo-test",
      "principal_binding_digest": "00331e020e1941361228e53c7caf69b92bed10e07b1e59c3ee7934be59736458",
      "work_ref": "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412"
    },
    "family": "coo_api_principal",
    "schema_version": "mastermind.coo_selected_child_requester/v1",
    "selection": {
      "attempt_ordinal": 1,
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "expected_current_attempt_id": null,
      "job_id": "JOB-003",
      "parent_job_id": "JOB-001",
      "plan_attempt_id": "ATT-54a5b7148b08431e88cac89288bcf5a9",
      "plan_digest": "dc491613b30458c9f445226501c6b66d98e30d10f1855f1a4980c2f2fbe6dad1",
      "plan_step_id": "STEP-0",
      "repair_round": 0,
      "root_job_id": "JOB-001"
    }
  },
  "native_mcp_sdk": "2.3.0",
  "native_origin_attested": false
}
````

## lost-response/native-output.log

Original bytes: 153. SHA256: `f29316167ab5a230c0af8f1d983420a81566b13ac9e0513e2671831badee5651`. terminal_newline=true.

````text
{"native_ref": "ba4ddf9945a213ede9dda016602a86591ed634f9", "native_sdk": "2.3.0", "acknowledgment_state": "EFFECT_UNKNOWN", "native_owner_closed": true}
````

## native-repository-identity.json

Original bytes: 573. SHA256: `05b66bad65c0468dc00c3c77628855dfaebce663a4a710152f9dbf03bf39b7b6`. terminal_newline=true.

````json
{
  "content": [
    {
      "text": "[Reading 2 new lines (total: 2 lines)]\n\n{\"head\": \"ba4ddf9945a213ede9dda016602a86591ed634f9\", \"origin\": {\"host\": \"github.com\", \"repository_path\": \"/NousResearch/hermes-agent.git\"}, \"repository\": \"/Users/chriswong/.hermes/hermes-agent\", \"requested_commit\": \"ba4ddf9945a213ede9dda016602a86591ed634f9\", \"requested_tree\": \"cd69b1c914e644149423b98211d18789e1161eff\"}\n\n\u2705 Process completed with exit code 0 (runtime: 0.43s)",
      "type": "text"
    }
  ],
  "isError": false,
  "structuredContent": null
}
````

## prior-failures/estate-paperclip-api-native-bridge-host-proof/original-operation-reconciliation.json

Original bytes: 1669. SHA256: `e9847164febccb50423aacd99c84a774a3d3548f47d16fb8610ab410fa7b3394`. terminal_newline=true.

````json
{
  "content": [
    {
      "text": "[Reading 2 new lines (total: 2 lines)]\n\n{\"command\": \"coo-cycle:JOB-001:dispatch:JOB-003:attempt:1\", \"http_path\": \"/tmp/estate-paperclip-finite-native-bridge-20261110-c4/test_finite_native_hermes_requ0/native-http-receipt.json\", \"http_receipt\": {\"calls\": [{\"action\": null, \"authorization_sha256\": \"71dba05fce6ac4a84dd4b5dbfbd3ee110d65fa03c91c24bfe79f212d5beec624\", \"http_method\": \"POST\", \"method\": \"initialize\", \"path\": \"/mcp/coo\", \"response_status\": 200, \"tool\": null, \"workspace_companion\": false}, {\"action\": null, \"authorization_sha256\": \"71dba05fce6ac4a84dd4b5dbfbd3ee110d65fa03c91c24bfe79f212d5beec624\", \"http_method\": \"POST\", \"method\": \"notifications/initialized\", \"path\": \"/mcp/coo\", \"response_status\": 202, \"tool\": null, \"workspace_companion\": false}, {\"action\": null, \"authorization_sha256\": \"71dba05fce6ac4a84dd4b5dbfbd3ee110d65fa03c91c24bfe79f212d5beec624\", \"http_method\": \"POST\", \"method\": \"tools/list\", \"path\": \"/mcp/coo\", \"response_status\": 200, \"tool\": null, \"workspace_companion\": false}], \"native_origin_attested\": false, \"native_returncode\": 1}, \"http_sha256\": \"50d04c8026a5792fb6782bb1eddeca1d29b78ca5cf4e8bdf2fb42e219106cffd\", \"requester_ack_events\": 0, \"selected_command_events\": 0, \"selected_job\": {\"attempt_count\": 0, \"current_attempt_id\": null, \"job_id\": \"JOB-003\", \"parent_job_id\": \"JOB-001\", \"root_job_id\": \"JOB-001\", \"status\": \"QUEUED\"}}\n\n\u2705 Process completed with exit code 0 (runtime: 0.12s)",
      "type": "text"
    }
  ],
  "isError": false,
  "structuredContent": null
}
````

## prior-failures/estate-paperclip-api-native-bridge-host-proof/original-process-output.json

Original bytes: 18697. SHA256: `24e8ba790a3e1b85f89246a312bb506e6ddefdcf14142ef356c32bd49c0978e2`. terminal_newline=true.

````json
{
  "content": [
    {
      "text": "[Reading 34 new lines (total: 34 lines)]\n\n{\"phase\": \"START\", \"tree\": \"07d13cef3a3a272770ca48481c78a906e9342b53\", \"argv\": [\"python3\", \"-B\", \"-m\", \"pytest\", \"-q\", \"-p\", \"anyio.pytest_plugin\", \"tests/test_paperclip_hermes_api_transport.py\", \"--maxfail=1\", \"--tb=short\", \"--basetemp=/tmp/estate-paperclip-finite-native-bridge-20261110-c4\", \"--junitxml=/tmp/estate-paperclip-finite-native-bridge-20261110-c4.xml\"], \"basetemp\": \"/tmp/estate-paperclip-finite-native-bridge-20261110-c4\", \"source\": {\"control_plane/executive_runtime.py\": \"363276f69185150e4089fbfe03fcd7121197cc5427a37870169fccf9c59da516\", \"control_plane/mission_workspace.py\": \"61d962771dc9823204d80c5838fc1fe4ae8009b669141db11372a41f9c8ffc20\", \"control_plane/workspace_read_service.py\": \"291f290848ab65507c10fbd205cc566fcdcdb5b937b24746a92ef97120aca254\", \"control_plane/runtime_namespace_custody.py\": \"0e4255b9ec9ddda5b613b2bf610156b221aa5efadf51702be0d62ad5f3776cf2\", \"control_plane/coo_principal_host.py\": \"5469b4d1f4b88393a781bbf387efd23f4183c6f504defd6e2a7ec5c2cc99ac24\", \"control_plane/executive_service.py\": \"b2191c2a96de45ee2ff7dc5cd4e55d6bc9163a6d9b110c45725b8de7d8851016\", \"tests/test_joint_api_ingress.py\": \"fa5367923ae15aff15019f3799c3b0edfbb5ec0c8dc162a39a33777bc789dc07\", \"tests/test_joint_api_project_owner.py\": \"72f45a1090f3533f1d98c832f852c0aa18d65d2ed489663abd7aff5ab9f16d58\", \"tests/paperclip_hermes_native_client.py\": \"891e75812ea7aa1284e39ce1a50e3ac05a7ff579a50616269c9c2cda664f10fe\", \"tests/test_paperclip_hermes_api_transport.py\": \"cc9f85a25ab863ed7c960c0ee5d5238101610be80e9770716e48e819336ad947\"}}\n{\"pytest_pid\": 66102}\nF\n=================================== FAILURES ===================================\n_ test_finite_native_hermes_requester_uses_original_http_and_unix_owners[normal-paperclip] _\ntests/test_paperclip_hermes_api_transport.py:213: in test_finite_native_hermes_requester_uses_original_http_and_unix_owners\n    asyncio.run(run())\n/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py:205: in run\n    return runner.run(main)\n           ^^^^^^^^^^^^^^^^\n/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py:128: in run\n    return self._loop.run_until_complete(task)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py:720: in run_until_complete\n    return future.result()\n           ^^^^^^^^^^^^^^^\ntests/test_paperclip_hermes_api_transport.py:183: in run\n    assert process.returncode == 0, output.decode(errors=\"replace\")[-10000:]\nE   AssertionError: Traceback (most recent call last):\nE       File \"/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/paperclip_hermes_native_client.py\", line 219, in <module>\nE         main()\nE         ~~~~^^\nE       File \"/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/paperclip_hermes_native_client.py\", line 114, in main\nE         assert module is not None and Path(module.__file__).resolve() == source / relative, relative\nE                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nE     AssertionError: tools/tool_search.py\nE     \nE   assert 1 == 0\nE    +  where 1 = <Process 67996>.returncode\n=========================== short test summary info ============================\nFAILED tests/test_paperclip_hermes_api_transport.py::test_finite_native_hermes_requester_uses_original_http_and_unix_owners[normal-paperclip]\n!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!\n{\"after_tree\": \"07d13cef3a3a272770ca48481c78a906e9342b53\", \"argv\": [\"python3\", \"-B\", \"-m\", \"pytest\", \"-q\", \"-p\", \"anyio.pytest_plugin\", \"tests/test_paperclip_hermes_api_transport.py\", \"--maxfail=1\", \"--tb=short\", \"--basetemp=/tmp/estate-paperclip-finite-native-bridge-20261110-c4\", \"--junitxml=/tmp/estate-paperclip-finite-native-bridge-20261110-c4.xml\"], \"basetemp\": \"/tmp/estate-paperclip-finite-native-bridge-20261110-c4\", \"elapsed_seconds\": 31.214, \"junit_sha256\": \"6aa2f457d29e2a001d93304008df761fe0c623784e20d4cf9fa5addb944f4b60\", \"log_sha256\": \"5c6e1b1fc55e4585d2c9f133790a343f997918cc9428a9bdfdfa902ea271ced5\", \"native_dependency_fact_sha256\": \"b29cf28250a1045859e9982af2371bb8797e3aa7f58fe10ab0eef42f8c63a790\", \"native_dependency_fact_unchanged\": true, \"native_patch_installed\": false, \"native_patched_source\": {\"tests/tools/test_tool_search_deferred_schema.py\": \"1befb7516c76eb1b59ef78c61b15113703ddeaea82712a6a5011b6218d38f4ee\", \"tools/tool_search.py\": \"bcaf4ed695a5493fdda421f7c969db5a6fd9cf06d8ad92a8cb546c3326f52866\"}, \"native_patched_source_unchanged\": true, \"native_private_candidate\": \"/tmp/estate-hermes-native-deferred-schema-ba4ddf9-20261110-c4\", \"native_source\": {\"all_git_blobs_verified\": true, \"archive_format_reconciliations\": [{\"archive_blob\": \"16efe8e095743e4abb2499a1f79bc2941cc2048c\", \"exact_git_blob\": \"e58ed04c91a3e61d1dac481a8642f6ded946d056\", \"path\": \"activate.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"f46796efe74769c5f781f2a7b4d0e6fbf5be464e\", \"exact_git_blob\": \"cc15dc791a016a7494fc3209a43a856268bd996f\", \"path\": \"apps/desktop/scripts/update-relaunch-waiter.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"75e3fb720c9704bf85ddfb852279892d51d95109\", \"exact_git_blob\": \"fc486d119cbb6946c9824f89709acdad8b406aa6\", \"path\": \"apps/desktop/scripts/verify-signed-payloads.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"8f2584db8e0bc8b00b6af3c0aa636fb2415bf1f2\", \"exact_git_blob\": \"0f3cd764561c60c7205dd35b2ae984607263fe11\", \"path\": \"evals/update_streaming/watchdog.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"0de81d1634dc7370f2ee7da83013e99053d5e65d\", \"exact_git_blob\": \"65dd6d8b6c999f8323f94df4bfec679b599708ec\", \"path\": \"optional-skills/software-development/ast-grep/install.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"4cdf94ed51bebe56339ea04f0756b8349269d093\", \"exact_git_blob\": \"b051d1ce04ee92cae34d5ece0247de3fa7bb6fe6\", \"path\": \"optional-skills/software-development/ast-grep/tests/smoke.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"bb33bf20139f0250d3ec1441865601632cb65168\", \"exact_git_blob\": \"4f6f656fed3836602644c2f2c9c305e2afb3c4c2\", \"path\": \"scripts/build-bundle.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"bf54bcee7966f7c142cf1fa41c63b5f6c1316370\", \"exact_git_blob\": \"35c5c171937ce54260a6eb2176c3d4096d317682\", \"path\": \"scripts/build/windows-deps.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"82cfdc2c70d82c45885c65bce3e2a8b41a5bbe86\", \"exact_git_blob\": \"5a4bca802e78ccbf1fb441e3db2a129e01b3e38d\", \"path\": \"scripts/ci/warm_powershell_module_cache.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"431752edf25319e07562c64b4ff5abd7dd4b8661\", \"exact_git_blob\": \"7b9647873d96278e95f233429d80bff6a269d327\", \"path\": \"scripts/desktop-update.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"df527495691dde7620fc6cb8d493ad50335ea67f\", \"exact_git_blob\": \"3ee01affb08fb77d48f527900ff903bbf6e5ae17\", \"path\": \"scripts/desktop-update/marker-claim.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"95f4b19c44751df36a06a0c7441cf2688b2df0e1\", \"exact_git_blob\": \"27478317490d18a56e62975f002cf6d18bd0805c\", \"path\": \"scripts/desktop-update/marker.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"cefc517bbc3234159d64b38f45fd6c01e243d60d\", \"exact_git_blob\": \"8b6c8260068b6322b3f0e8403516f4d5596ec1c8\", \"path\": \"scripts/desktop-update/runtime.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"2f57121cd82643d27b8a58386941b54e712882a5\", \"exact_git_blob\": \"85b5fdedde76652e4476861b99559fa8792d5d36\", \"path\": \"scripts/desktop-update/update-job.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"2f896e3b52a090b1e90e3567f1d45974e26922d5\", \"exact_git_blob\": \"8ace25578f616f072f1b4f9b690dd8c7e7d42ab9\", \"path\": \"scripts/desktop-update/windows.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"b4f55505ad8498d9738d7bb074f177f44debfbee\", \"exact_git_blob\": \"c0552ec8b9d2fbdc7127ec384c221b683d1e733a\", \"path\": \"scripts/install.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"caff36d89c4b1213382a769e8640d749bde034cf\", \"exact_git_blob\": \"997738df80bf39f0ebcf589fc3d1dbac22161e0c\", \"path\": \"scripts/tests/test-install-ps1-longpath.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"69dbe3273660730a8680b6dce43b35d7f028ddc7\", \"exact_git_blob\": \"c6f4ca32fef1b99ec23afc960050058ab0021c39\", \"path\": \"scripts/tests/test-install-ps1-node-compatibility.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"2a22704d4d7a214828f2c7455218928a321ab82c\", \"exact_git_blob\": \"fdfa2e596a58ef9f1cae24b9b88073087bb50e79\", \"path\": \"scripts/tests/test-install-ps1-store-guard.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"f4b64c274cffbc17a386265d7df5a6ef5b6cc761\", \"exact_git_blob\": \"80d7bbf0d1109995263f44404284f64d05734169\", \"path\": \"scripts/tests/test-install-ps1-utf8.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"542703f53ed2bccd2bb45c879279455c074867bd\", \"exact_git_blob\": \"7c193027c500dae552797cf917422d7cd9ba73e4\", \"path\": \"scripts/update-test/hermes-update-rehearsal.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"3529fb2491827f1a18d89601724cf862adfab7e1\", \"exact_git_blob\": \"d875454651b4c42669ed53b2a712d9d00e4b07f1\", \"path\": \"scripts/update-test/smoke-test.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"26a583b3fbc70506d40db8c6ccfd2697c8874898\", \"exact_git_blob\": \"b328a7e1e8da4fde3418114158632a4c1fdad3cc\", \"path\": \"scripts/windows-build-deps.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"929674f02363018d791d01bf9eea816e3f8e75c9\", \"exact_git_blob\": \"b3e229dfd98352dae375e2a67ca804d902b128d7\", \"path\": \"scripts/windows_e2e_harness.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"4371c15b7404edaebbb890990da93e3e0446ec7c\", \"exact_git_blob\": \"8bb0b64be88019bfdcb9c1871029f7afc354bc9d\", \"path\": \"setup-hermes.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"c94bdd8b8d3953f12f2975d10d215aebbcf1fd46\", \"exact_git_blob\": \"2b899ad40e9b8e5d7201ccd3ed47b72fe19ee2a6\", \"path\": \"tests/install/e2e-assets/desktop-smoke-windows.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"6d3570e7e5df6642cf8bd608702d483e313af6a2\", \"exact_git_blob\": \"a49e9ac4a505228b771dd38a81e9946b9ab2f36c\", \"path\": \"tests/install/e2e-assets/record-start.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"c344277c3a47ef490ccf9caade4ad86c57adb43f\", \"exact_git_blob\": \"594b3a417bf16f46e462d75b38cefb54af3b9fcb\", \"path\": \"tests/install/e2e-assets/record-stop.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"d82c8a01dcbbd3f74bf65b5d8aa656b09f234420\", \"exact_git_blob\": \"ff4c7994fd9bb522a7e5e3699cec18349a78211b\", \"path\": \"tests/install/e2e-assets/source-build-env.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"45ee78dd3ff9566bca94651833c93647573186dd\", \"exact_git_blob\": \"706bbeca01133095cd8bd5c4ffa2f66ada9005c8\", \"path\": \"tests/install/e2e-assets/source-driver.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"de870c732523bf24bdc0c15bb0b94281182ac237\", \"exact_git_blob\": \"cc9acc878055e6ceb9cbffdf0bf55688d810427d\", \"path\": \"tests/install/e2e-assets/ts-prefix.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"3a3045db1014b7909665ff8fd0f0f3dc20e12d76\", \"exact_git_blob\": \"45d2904b9c3506226c599067bb5f3c30271146a3\", \"path\": \"tests/install/e2e-assets/windows-bundle-metadata.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"ec512753ffe846b896b88d5d21a53579422559f8\", \"exact_git_blob\": \"e1d9d67ec97268eea5b023769d9bb716e2e45b1b\", \"path\": \"tests/install/e2e-assets/windows-bundle-metadata.test.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"16f07fdca49782b91edb5891fde1513db2473736\", \"exact_git_blob\": \"544d5f562e463d63a2a61150fade9793deec6e2b\", \"path\": \"tests/install/e2e-assets/windows-bundle-plugin-smoke.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"f27fc8ff3f96169548d5715c90f28630b1d29bda\", \"exact_git_blob\": \"20b6c66a7c4585c9c400ae434cea1aacc861ce09\", \"path\": \"tests/install/e2e-assets/windows-bundled-drive-update.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"49095a962c2dceb8841a3d505e0d7760ff88a0dd\", \"exact_git_blob\": \"83018e32cadf49afe3c523cf87654d812bd4ce1e\", \"path\": \"tests/install/e2e-assets/windows-bundled-processes.test.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"3a2c55e5b0bc258c5fbc376eafaf3497ba37b1c0\", \"exact_git_blob\": \"26cdb812eee107c777cfec0bba3e158d33c0bf5b\", \"path\": \"tests/install/windows-bundle-smoke.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"f7afc13211e1245a64cf3b1fe20bbdcbda7eebbf\", \"exact_git_blob\": \"307c57efa69a7800f830879c65ab51a028139136\", \"path\": \"tests/install/windows-bundled-e2e.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}, {\"archive_blob\": \"cdb7941defc1e27aeebb83d4e1e7eb973553d650\", \"exact_git_blob\": \"39702f8cbb570dbdff6184584c6161bef51c4cb9\", \"path\": \"tests/install/windows-e2e.ps1\", \"reason\": \"Git archive applied declared PowerShell CRLF conversion; restored exact pinned blob bytes\"}], \"archive_sha256\": \"7cf9cadd02b5421a54ffcdefa4b930f8829a7f291fd511e6d66d2aec4ca7d076\", \"bytes\": 243122150, \"elapsed_seconds\": 11.746, \"files\": 22553, \"ref\": \"ba4ddf9945a213ede9dda016602a86591ed634f9\", \"schema\": \"mastermind.native_source_snapshot.v1\", \"source\": \"/tmp/estate-hermes-native-source-ba4ddf9-20261110-c4\", \"tree\": \"cd69b1c914e644149423b98211d18789e1161eff\"}, \"pytest_pid\": 66102, \"returncode\": 1, \"source\": {\"control_plane/coo_principal_host.py\": \"5469b4d1f4b88393a781bbf387efd23f4183c6f504defd6e2a7ec5c2cc99ac24\", \"control_plane/executive_runtime.py\": \"363276f69185150e4089fbfe03fcd7121197cc5427a37870169fccf9c59da516\", \"control_plane/executive_service.py\": \"b2191c2a96de45ee2ff7dc5cd4e55d6bc9163a6d9b110c45725b8de7d8851016\", \"control_plane/mission_workspace.py\": \"61d962771dc9823204d80c5838fc1fe4ae8009b669141db11372a41f9c8ffc20\", \"control_plane/runtime_namespace_custody.py\": \"0e4255b9ec9ddda5b613b2bf610156b221aa5efadf51702be0d62ad5f3776cf2\", \"control_plane/workspace_read_service.py\": \"291f290848ab65507c10fbd205cc566fcdcdb5b937b24746a92ef97120aca254\", \"tests/paperclip_hermes_native_client.py\": \"891e75812ea7aa1284e39ce1a50e3ac05a7ff579a50616269c9c2cda664f10fe\", \"tests/test_joint_api_ingress.py\": \"fa5367923ae15aff15019f3799c3b0edfbb5ec0c8dc162a39a33777bc789dc07\", \"tests/test_joint_api_project_owner.py\": \"72f45a1090f3533f1d98c832f852c0aa18d65d2ed489663abd7aff5ab9f16d58\", \"tests/test_paperclip_hermes_api_transport.py\": \"cc9f85a25ab863ed7c960c0ee5d5238101610be80e9770716e48e819336ad947\"}, \"source_unchanged\": true, \"suites\": [{\"errors\": \"0\", \"failures\": \"1\", \"hostname\": \"m2studio\", \"name\": \"pytest\", \"skipped\": \"0\", \"tests\": \"1\", \"time\": \"27.397\", \"timestamp\": \"2026-11-10T08:17:10.425352-07:00\"}], \"tree\": \"07d13cef3a3a272770ca48481c78a906e9342b53\"}\n\n\u2705 Process completed with exit code 1 (runtime: 32.92s)",
      "type": "text"
    }
  ],
  "isError": false,
  "structuredContent": null
}
````
