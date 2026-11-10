# Joint API host records

These records preserve the original first-run assertion failure, its original-operation reconciliation, and the remaining six successful cases. They are diagnostic proof, not runtime configuration. Exact source identities and the eleven distinct accepted cases appear in [the qualification](JOINT_API_QUALIFICATION.md). Each original file's bytes and SHA256 are retained below; the containing Markdown document has its own Git identity. For a file explicitly marked without a terminal newline, the newline before the closing fence is a display delimiter and is omitted when reconstructing the original bytes.

## estate-joint-api-transaction-owner-20261110-c4.log

Original bytes: 5839. SHA256: `546ebda94105e8db532c33b5b892648cc14a1960db1d3243c34c8702df26621d`. Terminal newline: present.

```text
.....F
=================================== FAILURES ===================================
_ test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked] _
  + Exception Group Traceback (most recent call last):
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 332, in test_joint_same_enrollment_help_then_original_unix_requester_lifecycle
  |     asyncio.run(run())
  |     ~~~~~~~~~~~^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 205, in run
  |     return runner.run(main)
  |            ~~~~~~~~~~^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 128, in run
  |     return self._loop.run_until_complete(task)
  |            ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py", line 720, in run_until_complete
  |     return future.result()
  |            ~~~~~~~~~~~~~^^
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 264, in run
  |     async with session(s, companion=True) as (client, http_client):
  |                ~~~~~~~^^^^^^^^^^^^^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 154, in session
  |     async with app._app.router.lifespan_context(app._app):
  |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/server.py", line 2687, in lifespan
  |     async with manager.run():
  |                ~~~~~~~~~~~^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/server/streamable_http_manager.py", line 128, in run
  |     async with anyio.create_task_group() as tg:
  |                ~~~~~~~~~~~~~~~~~~~~~~~^^
  |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_backends/_asyncio.py", line 871, in __aexit__
  |     raise BaseExceptionGroup(
  |         "unhandled errors in a TaskGroup", self._exceptions
  |     ) from None
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Exception Group Traceback (most recent call last):
    |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/server/streamable_http_manager.py", line 133, in run
    |     yield  # Let the application run
    |     ^^^^^
    |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/server.py", line 2688, in lifespan
    |     yield
    |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 157, in session
    |     async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
    |                ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
    |     await self.gen.athrow(value)
    |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 647, in streamable_http_client
    |     async with anyio.create_task_group() as tg:
    |                ~~~~~~~~~~~~~~~~~~~~~~~^^
    |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_backends/_asyncio.py", line 871, in __aexit__
    |     raise BaseExceptionGroup(
    |         "unhandled errors in a TaskGroup", self._exceptions
    |     ) from None
    | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
    +-+---------------- 1 ----------------
      | Traceback (most recent call last):
      |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_core/_tasks.py", line 327, in _run_coro
      |     retval = await self._coro
      |              ^^^^^^^^^^^^^^^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 565, in handle_request_async
      |     await self._handle_post_request(ctx)
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 358, in _handle_post_request
      |     response.raise_for_status()
      |     ~~~~~~~~~~~~~~~~~~~~~~~~~^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/httpx/_models.py", line 829, in raise_for_status
      |     raise HTTPStatusError(message, request=request, response=self)
      | httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'http://127.0.0.1/mcp/coo'
      | For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
      +------------------------------------
=========================== short test summary info ============================
FAILED tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
```

## estate-joint-api-transaction-owner-20261110-c4.receipt.json

Original bytes: 1950. SHA256: `12ffc258968fe415e75d217b6f98d30a4b01fdc7f488d65c9d234ef852e88ed2`. Terminal newline: present.

```json
{
  "after_tree": "5d81a751eb41ee38990c4a0e7e4e626a1d070457",
  "argv": [
    "python3",
    "-B",
    "-m",
    "pytest",
    "-q",
    "-p",
    "anyio.pytest_plugin",
    "tests/test_joint_api_ingress.py",
    "--maxfail=1",
    "--tb=short",
    "--basetemp=/tmp/estate-joint-api-transaction-owner-20261110-c4",
    "--junitxml=/tmp/estate-joint-api-transaction-owner-20261110-c4.xml"
  ],
  "basetemp": "/tmp/estate-joint-api-transaction-owner-20261110-c4",
  "elapsed_seconds": 302.536,
  "junit_sha256": "37eedf79eadb1ef4f1721a6bf1557000177a51b2c5a951a912b2c6da7f828387",
  "log_sha256": "546ebda94105e8db532c33b5b892648cc14a1960db1d3243c34c8702df26621d",
  "pytest_pid": 48990,
  "returncode": 1,
  "source": {
    "control_plane/coo_principal_host.py": "285965b20dd52f8391e3066fdcf9b970086d6217a48769e8b2f8e40baa052f64",
    "control_plane/executive_runtime.py": "363276f69185150e4089fbfe03fcd7121197cc5427a37870169fccf9c59da516",
    "control_plane/executive_service.py": "323374c560f3b85af617d1f334b504adce858141796b785fbb35e8a72426a6fe",
    "control_plane/mission_workspace.py": "61d962771dc9823204d80c5838fc1fe4ae8009b669141db11372a41f9c8ffc20",
    "control_plane/runtime_namespace_custody.py": "0e4255b9ec9ddda5b613b2bf610156b221aa5efadf51702be0d62ad5f3776cf2",
    "control_plane/workspace_read_service.py": "291f290848ab65507c10fbd205cc566fcdcdb5b937b24746a92ef97120aca254",
    "tests/test_joint_api_ingress.py": "7d4f68e24faf65e5ead83056a15c8c4e768c59047a2d5e1f9473c000a90ee2ec",
    "tests/test_joint_api_project_owner.py": "72f45a1090f3533f1d98c832f852c0aa18d65d2ed489663abd7aff5ab9f16d58"
  },
  "source_unchanged": true,
  "suites": [
    {
      "errors": "0",
      "failures": "1",
      "hostname": "m2studio",
      "name": "pytest",
      "skipped": "0",
      "tests": "6",
      "time": "298.570",
      "timestamp": "2026-11-10T06:30:00.212292-07:00"
    }
  ],
  "tree": "5d81a751eb41ee38990c4a0e7e4e626a1d070457"
}
```

## estate-joint-api-transaction-owner-20261110-c4.xml

Original bytes: 6830. SHA256: `37eedf79eadb1ef4f1721a6bf1557000177a51b2c5a951a912b2c6da7f828387`. Terminal newline: absent.

```xml
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="6" time="298.570" timestamp="2026-11-10T06:30:00.212292-07:00" hostname="m2studio"><testcase classname="tests.test_joint_api_ingress" name="test_same_signed_api_principal_discovers_joint_tools_and_qualifies_help[t3]" time="45.775" /><testcase classname="tests.test_joint_api_ingress" name="test_same_signed_api_principal_discovers_joint_tools_and_qualifies_help[paperclip]" time="49.013" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-normal]" time="53.263" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-normal]" time="50.130" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-changed_digest]" time="51.097" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked]" time="45.954"><failure message="HTTPStatusError(&quot;Client error '401 Unauthorized' for url 'http://127.0.0.1/mcp/coo'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401&quot;) [single exception in ExceptionGroup]">+ Exception Group Traceback (most recent call last):
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 332, in test_joint_same_enrollment_help_then_original_unix_requester_lifecycle
  |     asyncio.run(run())
  |     ~~~~~~~~~~~^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 205, in run
  |     return runner.run(main)
  |            ~~~~~~~~~~^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 128, in run
  |     return self._loop.run_until_complete(task)
  |            ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py", line 720, in run_until_complete
  |     return future.result()
  |            ~~~~~~~~~~~~~^^
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 264, in run
  |     async with session(s, companion=True) as (client, http_client):
  |                ~~~~~~~^^^^^^^^^^^^^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 154, in session
  |     async with app._app.router.lifespan_context(app._app):
  |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/server.py", line 2687, in lifespan
  |     async with manager.run():
  |                ~~~~~~~~~~~^^
  |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
  |     await self.gen.athrow(value)
  |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/server/streamable_http_manager.py", line 128, in run
  |     async with anyio.create_task_group() as tg:
  |                ~~~~~~~~~~~~~~~~~~~~~~~^^
  |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_backends/_asyncio.py", line 871, in __aexit__
  |     raise BaseExceptionGroup(
  |         "unhandled errors in a TaskGroup", self._exceptions
  |     ) from None
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Exception Group Traceback (most recent call last):
    |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/server/streamable_http_manager.py", line 133, in run
    |     yield  # Let the application run
    |     ^^^^^
    |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/server.py", line 2688, in lifespan
    |     yield
    |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 157, in session
    |     async with streamable_http_client("http://127.0.0.1/mcp/coo", http_client=http_client) as (read, write, _):
    |                ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 235, in __aexit__
    |     await self.gen.athrow(value)
    |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 647, in streamable_http_client
    |     async with anyio.create_task_group() as tg:
    |                ~~~~~~~~~~~~~~~~~~~~~~~^^
    |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_backends/_asyncio.py", line 871, in __aexit__
    |     raise BaseExceptionGroup(
    |         "unhandled errors in a TaskGroup", self._exceptions
    |     ) from None
    | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
    +-+---------------- 1 ----------------
      | Traceback (most recent call last):
      |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_core/_tasks.py", line 327, in _run_coro
      |     retval = await self._coro
      |              ^^^^^^^^^^^^^^^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 565, in handle_request_async
      |     await self._handle_post_request(ctx)
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 358, in _handle_post_request
      |     response.raise_for_status()
      |     ~~~~~~~~~~~~~~~~~~~~~~~~~^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/httpx/_models.py", line 829, in raise_for_status
      |     raise HTTPStatusError(message, request=request, response=self)
      | httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'http://127.0.0.1/mcp/coo'
      | For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
      +------------------------------------</failure></testcase></testsuite></testsuites>
```

## original-revocation-ack.json

Original bytes: 3517. SHA256: `9d4e9dcea5e866772a9e3b31f42f5862eb49e5e74113f919c9df0ea8fdadfa80`. Terminal newline: present.

```json
{
  "acknowledgments": [],
  "attempts": [
    {
      "attempt_id": "ATT-406839dbf1b14b0a9cd4823b5a3099b5",
      "job_id": "JOB-003",
      "status": "COMPLETED"
    }
  ],
  "child_events": [
    {
      "command_id": "coo-cycle:JOB-001:admit-plan:ATT-5965f37ea09a46fc8384c09d54c6d4dc:member:0",
      "event_id": 29,
      "event_type": "JOB_CREATED"
    },
    {
      "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
      "event_id": 48,
      "event_type": "JOB_CLAIMED"
    },
    {
      "command_id": "c08241873db14653af4cd826763a2c6a",
      "event_id": 49,
      "event_type": "OHF_PROFILE_SEALED"
    },
    {
      "command_id": "ohf-op:complete-61003-start",
      "event_id": 50,
      "event_type": "OPERATOR_OPERATION_INTENT"
    },
    {
      "command_id": "ohf-op:complete-61003-start:applied",
      "event_id": 51,
      "event_type": "OPERATOR_OPERATION_APPLIED"
    },
    {
      "command_id": "8e12eef21b144112aaabe521a60073dd",
      "event_id": 52,
      "event_type": "OHF_ATTESTATION_OBSERVED"
    },
    {
      "command_id": "0e6963c7fdd440608c894cc66049173b",
      "event_id": 53,
      "event_type": "OHF_LAUNCH_DECISION"
    },
    {
      "command_id": "ohf-work-admit:ohf-generation-8ed5b10584224e5e80b6040874b23fb0",
      "event_id": 54,
      "event_type": "ORCHESTRATION_WORK_ADMITTED"
    },
    {
      "command_id": "ohf-op:complete-61003-turn",
      "event_id": 55,
      "event_type": "OPERATOR_OPERATION_INTENT"
    },
    {
      "command_id": "ohf-op:complete-61003-turn:applied",
      "event_id": 56,
      "event_type": "OPERATOR_OPERATION_APPLIED"
    },
    {
      "command_id": "ohf-candidate:ohf-turn-2b46bd8f8a424ff5b0592f047e5519f2",
      "event_id": 57,
      "event_type": "OHF_CANDIDATE_RESULT_RECORDED"
    },
    {
      "command_id": "orchestration-result-seal:ATT-406839dbf1b14b0a9cd4823b5a3099b5",
      "event_id": 58,
      "event_type": "ORCHESTRATION_ROLE_RESULT_SEALED"
    },
    {
      "command_id": "20efa8fe24534055b687dc5a890e8bf8",
      "event_id": 59,
      "event_type": "OHF_RECONCILE_OBSERVED"
    },
    {
      "command_id": "59b63fde938a49aa827ccb5cc97efa9c",
      "event_id": 60,
      "event_type": "OHF_GRACEFUL_STOP"
    },
    {
      "command_id": "eb108e7ee8e14fb586897123cb4fdc09",
      "event_id": 61,
      "event_type": "OHF_EPOCH_ABANDONED"
    },
    {
      "command_id": "07b021da1edb48d6a8ce35930ba54a9b",
      "event_id": 62,
      "event_type": "JOB_COMPLETED"
    },
    {
      "command_id": "terminal-return:ATT-406839dbf1b14b0a9cd4823b5a3099b5:5b0c5ce5755a04b43595a243a17665945b671e6775f1bb2ec7fe909e44810a96:prepared",
      "event_id": 63,
      "event_type": "EXECUTIVE_TERMINAL_RETURN_PREPARED"
    },
    {
      "command_id": "terminal-return:ATT-406839dbf1b14b0a9cd4823b5a3099b5:5b0c5ce5755a04b43595a243a17665945b671e6775f1bb2ec7fe909e44810a96:attempted",
      "event_id": 64,
      "event_type": "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED"
    },
    {
      "command_id": "terminal-return:ATT-406839dbf1b14b0a9cd4823b5a3099b5:5b0c5ce5755a04b43595a243a17665945b671e6775f1bb2ec7fe909e44810a96:applied",
      "event_id": 65,
      "event_type": "EXECUTIVE_TERMINAL_RETURN_APPLIED"
    }
  ],
  "database": "/tmp/estate-joint-api-transaction-owner-20261110-c4/test_joint_same_enrollment_hel3/planning/runtime/data/control_plane/executive.sqlite3",
  "original_command": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
  "schema": "mastermind.joint_api_original_ack_reconciliation.v1"
}
```

## original-revocation-runtime.json

Original bytes: 3758. SHA256: `7ddec641d95f8814b44a2e497e24036368699424cfe51e79541628d04863452c`. Terminal newline: present.

```json
{
  "fixture": "/tmp/estate-joint-api-transaction-owner-20261110-c4/test_joint_same_enrollment_hel3",
  "runtime": [
    {
      "attempts": 3,
      "database": "/tmp/estate-joint-api-transaction-owner-20261110-c4/test_joint_same_enrollment_hel3/planning/runtime/data/control_plane/executive.sqlite3",
      "event_high_water": 65,
      "jobs": [
        {
          "attempt_count": 0,
          "depth": 0,
          "job_id": "JOB-001",
          "parent_job_id": null,
          "root_job_id": "JOB-001",
          "status": "QUEUED"
        },
        {
          "attempt_count": 1,
          "depth": 1,
          "job_id": "JOB-002",
          "parent_job_id": "JOB-001",
          "root_job_id": "JOB-001",
          "status": "COMPLETED"
        },
        {
          "attempt_count": 1,
          "depth": 1,
          "job_id": "JOB-003",
          "parent_job_id": "JOB-001",
          "root_job_id": "JOB-001",
          "status": "COMPLETED"
        },
        {
          "attempt_count": 0,
          "depth": 0,
          "job_id": "JOB-004",
          "parent_job_id": null,
          "root_job_id": "JOB-004",
          "status": "QUEUED"
        },
        {
          "attempt_count": 1,
          "depth": 1,
          "job_id": "JOB-005",
          "parent_job_id": "JOB-004",
          "root_job_id": "JOB-004",
          "status": "RUNNING"
        }
      ],
      "original_claim_and_consumption": [
        {
          "attempt_id": "ATT-406839dbf1b14b0a9cd4823b5a3099b5",
          "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
          "event_id": 48,
          "event_type": "JOB_CLAIMED",
          "job_id": "JOB-003",
          "payload_keys": [
            "attempt_number",
            "authority_policy_hash",
            "capability_policy_digest",
            "capability_policy_version",
            "cycle_command_id",
            "dispatch_job_id",
            "effective_grant_digest",
            "execution_profile_digest",
            "execution_profile_id",
            "fence_generation",
            "lease_expires_at_ms",
            "lease_owner",
            "lease_seconds",
            "orchestration_role",
            "placement_snapshot_digest",
            "preferred_model_aliases",
            "requested_quota_class",
            "requested_worker_id",
            "routing_policy_version",
            "routing_reason_codes",
            "selected_child_requester",
            "selected_model_alias"
          ],
          "requester_family": "coo_api_principal"
        }
      ]
    },
    {
      "attempts": 0,
      "database": "/tmp/estate-joint-api-transaction-owner-20261110-c4/test_joint_same_enrollment_hel3/custody/runtime/data/control_plane/executive.sqlite3",
      "event_high_water": 4,
      "jobs": [],
      "original_claim_and_consumption": []
    }
  ],
  "schema": "mastermind.joint_api_original_revocation_readback.v1",
  "tests": [
    {
      "failed": false,
      "name": "test_same_signed_api_principal_discovers_joint_tools_and_qualifies_help[t3]"
    },
    {
      "failed": false,
      "name": "test_same_signed_api_principal_discovers_joint_tools_and_qualifies_help[paperclip]"
    },
    {
      "failed": false,
      "name": "test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-normal]"
    },
    {
      "failed": false,
      "name": "test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-normal]"
    },
    {
      "failed": false,
      "name": "test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-changed_digest]"
    },
    {
      "failed": true,
      "name": "test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked]"
    }
  ]
}
```

## estate-joint-api-auth-fences-20261110-c4.log

Original bytes: 80. SHA256: `700bc0322b00f8e8db3ce495047983b54ab27ab59ed1fedac05f3aeba47dae24`. Terminal newline: present.

```text
......                                                                   [100%]
```

## estate-joint-api-auth-fences-20261110-c4.receipt.json

Original bytes: 2682. SHA256: `cf2a67eee8aaaf9bfa8bbf0630d500e40a83187fa0c150f1142adeee7b7f477b`. Terminal newline: present.

```json
{
  "after_tree": "39cd9a04485cfce734cca28ec1c599bb2934f71c",
  "argv": [
    "python3",
    "-B",
    "-m",
    "pytest",
    "-q",
    "-p",
    "anyio.pytest_plugin",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked]",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-foreign_root]",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-source_generation]",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-foreign_principal]",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-lost_response]",
    "tests/test_joint_api_ingress.py::test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-concurrent_ack]",
    "--maxfail=1",
    "--tb=short",
    "--basetemp=/tmp/estate-joint-api-auth-fences-20261110-c4",
    "--junitxml=/tmp/estate-joint-api-auth-fences-20261110-c4.xml"
  ],
  "basetemp": "/tmp/estate-joint-api-auth-fences-20261110-c4",
  "elapsed_seconds": 418.42,
  "junit_sha256": "4be3f751ca28233bf367e17262ea45399caaa8b58ffa1b738c09893ba98a3fb8",
  "log_sha256": "700bc0322b00f8e8db3ce495047983b54ab27ab59ed1fedac05f3aeba47dae24",
  "pytest_pid": 27016,
  "returncode": 0,
  "source": {
    "control_plane/coo_principal_host.py": "285965b20dd52f8391e3066fdcf9b970086d6217a48769e8b2f8e40baa052f64",
    "control_plane/executive_runtime.py": "363276f69185150e4089fbfe03fcd7121197cc5427a37870169fccf9c59da516",
    "control_plane/executive_service.py": "323374c560f3b85af617d1f334b504adce858141796b785fbb35e8a72426a6fe",
    "control_plane/mission_workspace.py": "61d962771dc9823204d80c5838fc1fe4ae8009b669141db11372a41f9c8ffc20",
    "control_plane/runtime_namespace_custody.py": "0e4255b9ec9ddda5b613b2bf610156b221aa5efadf51702be0d62ad5f3776cf2",
    "control_plane/workspace_read_service.py": "291f290848ab65507c10fbd205cc566fcdcdb5b937b24746a92ef97120aca254",
    "tests/test_joint_api_ingress.py": "fa5367923ae15aff15019f3799c3b0edfbb5ec0c8dc162a39a33777bc789dc07",
    "tests/test_joint_api_project_owner.py": "72f45a1090f3533f1d98c832f852c0aa18d65d2ed489663abd7aff5ab9f16d58"
  },
  "source_unchanged": true,
  "suites": [
    {
      "errors": "0",
      "failures": "0",
      "hostname": "m2studio",
      "name": "pytest",
      "skipped": "0",
      "tests": "6",
      "time": "411.686",
      "timestamp": "2026-11-10T06:46:25.469713-07:00"
    }
  ],
  "tree": "39cd9a04485cfce734cca28ec1c599bb2934f71c"
}
```

## estate-joint-api-auth-fences-20261110-c4.xml

Original bytes: 1240. SHA256: `4be3f751ca28233bf367e17262ea45399caaa8b58ffa1b738c09893ba98a3fb8`. Terminal newline: absent.

```xml
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="6" time="411.686" timestamp="2026-11-10T06:46:25.469713-07:00" hostname="m2studio"><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-revoked]" time="71.855" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-foreign_root]" time="61.583" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-source_generation]" time="54.626" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-foreign_principal]" time="70.722" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[paperclip-lost_response]" time="56.998" /><testcase classname="tests.test_joint_api_ingress" name="test_joint_same_enrollment_help_then_original_unix_requester_lifecycle[t3-concurrent_ack]" time="90.477" /></testsuite></testsuites>
```
