# Original joint API diagnostic exchange

This diagnostic report preserves the first failed fixture exchange. It is historical evidence, not an executable source file or current qualification claim. The reserved-source refusal and subsequent original-operation reconciliation remain part of the delivery record.

Original log SHA256: `a9dd9c7240618455f86c7d41fc8c882eaa06123ee7f22781454e62b9f5db6828` (23557 bytes). The original bytes follow verbatim.

```text
[Reading 211 lines from line 8 (total: 219 lines, 0 remaining)]

Thread 0x000000016ef13000 [asyncio_0] (most recent call first):
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/selectors.py", line 548 in select
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/control_plane/ceo_boot_packet.py", line 232 in bounded_subprocess_runner
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_project_discovery_installed_plan.py", line 82 in runner
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/installed.py", line 1715 in observe
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/installed.py", line 1770 in _clean_git_snapshot
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_project_owner.py", line 128 in captured_source
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_project_discovery_installed_plan.py", line 69 in capture
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/executive_mcp/installed.py", line 2471 in _capture_canonical_code
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/mastermind_workspace_app/canonical_project_data.py", line 94 in view
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/integrations/mastermind_workspace_app/canonical_project_data.py", line 148 in read_plan
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/control_plane/installed_canonical_project_data_binding.py", line 60 in read_installed_project_data
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/control_plane/workspace_read_service.py", line 745 in _read_project_plan
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/control_plane/coo_project_help_read.py", line 158 in capture_project_help_authority
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/concurrent/futures/thread.py", line 73 in run
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/concurrent/futures/thread.py", line 86 in run
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/concurrent/futures/thread.py", line 119 in _worker
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/threading.py", line 1024 in run
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/threading.py", line 1082 in _bootstrap_inner
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/threading.py", line 1044 in _bootstrap

Thread 0x00000001fa195e80 (most recent call first):
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/selectors.py", line 548 in select
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py", line 2019 in _run_once
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py", line 678 in run_forever
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/base_events.py", line 707 in run_until_complete
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 128 in run
  File "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/asyncio/runners.py", line 205 in run
  File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 332 in test_joint_same_enrollment_help_then_original_unix_requester_lifecycle
  File "/tmp/test_joint_service_original_exchange_20261110_c4.py", line 112 in test_new_disposable_original_exchange
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/python.py", line 167 in pytest_pyfunc_call
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/python.py", line 1707 in runtest
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 184 in pytest_runtest_call
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 250 in <lambda>
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 361 in from_call
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 249 in call_and_report
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 139 in runtestprotocol
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/runner.py", line 118 in pytest_runtest_protocol
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/main.py", line 408 in pytest_runtestloop
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/main.py", line 384 in _main
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/main.py", line 330 in wrap_session
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/main.py", line 377 in pytest_cmdline_main
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_callers.py", line 121 in _multicall
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_manager.py", line 120 in _hookexec
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pluggy/_hooks.py", line 512 in __call__
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/config/__init__.py", line 229 in _main
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/_pytest/config/__init__.py", line 253 in _console_main
  File "/Users/chriswong/Library/Python/3.14/lib/python/site-packages/pytest/__main__.py", line 9 in <module>
  File "<frozen runpy>", line 88 in _run_code
  File "<frozen runpy>", line 203 in _run_module_as_main
JOINT_DIAGNOSTIC {"action": "selected_child_submit", "read_timeout": 10.0, "schema": "mastermind.ceo_ingress.selected_child.v1", "stage": "private.send.begin"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03685199981555343, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.04214324988424778, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.030095583060756326, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "selected_child_status.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.023782957810908556, "reason": "EXECUTIVE_SELECTED_CHILD_NOT_CLAIMED", "stage": "selected_child_status.return", "state": "NOT_CLAIMED"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.02021262515336275, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.030643833801150322, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "guard_dialogue.begin"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.031797792064026, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03655516682192683, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"elapsed": 0.0803970000706613, "stage": "guard_dialogue.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.026053749956190586, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03394208289682865, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "dispatch_selected_child.begin"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03817679104395211, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.043139582965523005, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "guard_dialogue.begin"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03855604212731123, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03589962515980005, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"elapsed": 0.08136541699059308, "stage": "guard_dialogue.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03165379189886153, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.027059667045250535, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"detail": "PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID", "elapsed": 0.38953349995426834, "exception": "StateConflict", "stage": "dispatch_selected_child.raise"}
JOINT_DIAGNOSTIC {"stage": "mission.begin"}
JOINT_DIAGNOSTIC {"elapsed": 0.03214541682973504, "read_state": {"reason_codes": [], "state": "CURRENT", "usable_sections": ["program", "mission", "review", "execution", "principal", "transport", "children"]}, "root_job_id": null, "schema": "mastermind.mission_workspace.v3", "stage": "mission.return"}
JOINT_DIAGNOSTIC {"action": "selected_child_submit", "detail": "", "elapsed": 0.899494166020304, "error": null, "ok": true, "result_reason": "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN", "result_state": "EFFECT_UNKNOWN", "schema": "mastermind.ceo_ingress.selected_child.v1", "stage": "private.send.return", "transport": "sent_ok"}
JOINT_DIAGNOSTIC {"attempt_count": 0, "command_event_type": null, "current_attempt_id": null, "job_status": "QUEUED", "stage": "original.final_read"}
FAILED

=================================== FAILURES ===================================
__________________ test_new_disposable_original_exchange[t3] ___________________
  + Exception Group Traceback (most recent call last):
  |   File "/tmp/test_joint_service_original_exchange_20261110_c4.py", line 112, in test_new_disposable_original_exchange
  |     original_case(joint_signed, tmp_path, monkeypatch, "normal")
  |     ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
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
      | Exception Group Traceback (most recent call last):
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/client/streamable_http.py", line 670, in streamable_http_client
      |     yield (
      |     ...<3 lines>...
      |     )
      |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 158, in session
      |     async with ClientSession(read, write) as client:
      |                ~~~~~~~~~~~~~^^^^^^^^^^^^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/mcp/shared/session.py", line 238, in __aexit__
      |     return await self._task_group.__aexit__(exc_type, exc_val, exc_tb)
      |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      |   File "/tmp/estate-graph-qa-python-20261110-c4/anyio/_backends/_asyncio.py", line 871, in __aexit__
      |     raise BaseExceptionGroup(
      |         "unhandled errors in a TaskGroup", self._exceptions
      |     ) from None
      | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
      +-+---------------- 1 ----------------
        | Traceback (most recent call last):
        |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 160, in session
        |     yield client, http_client
        |   File "/Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_joint_api_ingress.py", line 285, in run
        |     assert submitted["state"] in {"ACTIVE", "COMPLETED"}, submitted
        | AssertionError: {'attempt_id': None, 'attempt_status': None, 'command_id': 'coo-cycle:JOB-001:dispatch:JOB-003:attempt:1', 'job_id': 'JOB-003', ...}
        | assert 'EFFECT_UNKNOWN' in {'COMPLETED', 'ACTIVE'}
        +------------------------------------
=============================== warnings summary ===============================
tests/test_mastermind_executive_app_asgi.py:39
  /Volumes/Mastermind/agent-workspaces/web/estate-graph-composition-20261109-c4/tests/test_mastermind_executive_app_asgi.py:39: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
--- generated xml file: /tmp/estate-joint-service-diagnostic-20261110-c4.xml ---
============================== slowest durations ===============================
40.51s setup    test_joint_service_original_exchange_20261110_c4.py::test_new_disposable_original_exchange[t3]
24.75s call     test_joint_service_original_exchange_20261110_c4.py::test_new_disposable_original_exchange[t3]
0.01s teardown test_joint_service_original_exchange_20261110_c4.py::test_new_disposable_original_exchange[t3]
=========================== short test summary info ============================
FAILED ../../../../../tmp/test_joint_service_original_exchange_20261110_c4.py::test_new_disposable_original_exchange[t3] - AssertionError("{'attempt_id': None, 'attempt_status': None, 'command_id': 'coo-cycle:JOB-001:dispatch:JOB-003:attempt:1', 'job_id': 'JOB-003', ...}\nassert 'EFFECT_UNKNOWN' in {'COMPLETED', 'ACTIVE'}") [single exception in ExceptionGroup]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
=================== 1 failed, 1 warning in 88.59s (0:01:28) ====================
{"tree": "aa36de9b34fe48737cc4082ea707047c7bf231df", "exit_code": 1, "elapsed_seconds": 90.316, "report": "/tmp/estate-joint-service-diagnostic-20261110-c4.xml", "report_sha256": "bde93ae82da3fd732d914dcac62f28d0b4646c312033d2f0ecbefb0ebb37c245", "suites": [{"name": "pytest", "errors": "0", "failures": "1", "skipped": "0", "tests": "1", "time": "88.582", "timestamp": "2026-11-10T05:14:45.684208-07:00", "hostname": "m2studio"}]}

✅ Process completed with exit code 1 (runtime: 94.59s)
```
