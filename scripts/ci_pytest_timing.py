"""Opt-in CI diagnostics; no collection, ordering, outcome or timeout changes."""
from __future__ import annotations

import json
import os
import pytest

# Frozen diagnostic selectors only, never admission or source authority.
_H1_OWNED = {'tests/test_paid_initializer.py': {'cases': ('test_actual_linux_initializer_exec_and_selector_drift_before_hook',
                                              'test_actual_nested_initializer_private_package_context_and_wire',
                                              'test_actual_pinned_image_exec_matches_normal_isolated_venv_startup',
                                              'test_annotation_boundary_itself_never_renders_unapproved_fields',
                                              'test_bad_closed_input_refuses',
                                              'test_child_diagnostic_decoder_rejects_unbounded_or_private_fields',
                                              'test_child_diagnostic_is_allowlisted_and_preserves_nonzero',
                                              'test_child_output_is_bounded_before_materialization',
                                              'test_closed_commitment_is_detached_expected_input',
                                              'test_completion_notice_has_own_line_with_real_ci_capture',
                                              'test_context_and_identity_mutation_refuses',
                                              'test_different_input_digest_is_not_approval',
                                              'test_fast_preflight_is_supplementary_and_full_ci_fanin_unchanged',
                                              'test_final_observer_primary_and_cleanup_refusals_stay_distinct',
                                              'test_guard_failure_annotation_has_own_line_with_actual_ci_capture',
                                              'test_hook_snapshot_cannot_change_after_approval_even_when_original_changes',
                                              'test_native_initializer_extends_only_exact_preimage_members',
                                              'test_observer_directory_premise_is_exact_and_preserves_unmodeled_writes',
                                              'test_observer_metadata_fixture_is_finite_and_does_not_hide_other_errors',
                                              'test_raw_commitment_refuses',
                                              'test_shell_stdout_cannot_be_a_probe_witness',
                                              'test_unexpected_pipeline_exception_keeps_private_repr_out_of_diagnostics',
                                              'test_untrusted_initializer_environment_refuses'),
                                    'functions': ('_decode_observer_diagnostic',
                                                  '_guard_notice',
                                                  '_inert_bootstrap',
                                                  '_linux_completion',
                                                  '_observer_metadata_fixture',
                                                  '_preserving_stat_view',
                                                  '_system_fixture_failure_metadata',
                                                  '_system_fixture_failure_notice',
                                                  '_system_fixture_launch',
                                                  '_system_fixture_metadata_safe',
                                                  '_system_fixture_public_node',
                                                  'bounded',
                                                  'changed_capture',
                                                  'check_read',
                                                  'checked_pread',
                                                  'checked_read',
                                                  'commitment',
                                                  'counted_child',
                                                  'distribution',
                                                  'fail',
                                                  'guarded',
                                                  'modeled_xattr',
                                                  'owned_fstat',
                                                  'owned_lstat',
                                                  'owned_stat',
                                                  'pairs',
                                                  'root_view',
                                                  'run',
                                                  'selectors',
                                                  'test_actual_linux_initializer_exec_and_selector_drift_before_hook',
                                                  'test_actual_nested_initializer_private_package_context_and_wire',
                                                  'test_actual_pinned_image_exec_matches_normal_isolated_venv_startup',
                                                  'test_annotation_boundary_itself_never_renders_unapproved_fields',
                                                  'test_bad_closed_input_refuses',
                                                  'test_child_diagnostic_decoder_rejects_unbounded_or_private_fields',
                                                  'test_child_diagnostic_is_allowlisted_and_preserves_nonzero',
                                                  'test_child_output_is_bounded_before_materialization',
                                                  'test_closed_commitment_is_detached_expected_input',
                                                  'test_completion_notice_has_own_line_with_real_ci_capture',
                                                  'test_context_and_identity_mutation_refuses',
                                                  'test_different_input_digest_is_not_approval',
                                                  'test_fast_preflight_is_supplementary_and_full_ci_fanin_unchanged',
                                                  'test_final_observer_primary_and_cleanup_refusals_stay_distinct',
                                                  'test_guard_failure_annotation_has_own_line_with_actual_ci_capture',
                                                  'test_hook_snapshot_cannot_change_after_approval_even_when_original_changes',
                                                  'test_native_initializer_extends_only_exact_preimage_members',
                                                  'test_observer_directory_premise_is_exact_and_preserves_unmodeled_writes',
                                                  'test_observer_metadata_fixture_is_finite_and_does_not_hide_other_errors',
                                                  'test_raw_commitment_refuses',
                                                  'test_shell_stdout_cannot_be_a_probe_witness',
                                                  'test_unexpected_pipeline_exception_keeps_private_repr_out_of_diagnostics',
                                                  'test_untrusted_initializer_environment_refuses',
                                                  'traced')},
 'tests/test_paid_initializer_nosite.py': {'cases': ('test_actual_nofollow_link_metadata_recheck_and_unsupported_acl_refusal',
                                                     'test_ignored_node_rejects_unqualified_parent_before_open',
                                                     'test_ignored_node_visible_metadata_is_closed_data_not_errno_absence',
                                                     'test_new_profile_mutated_probe_hash_refuses_canonical_admission',
                                                     'test_no_follow_scanner_never_classifies_target_or_descends_symlinks',
                                                     'test_normal_imports_and_importlib_cannot_execute_marker',
                                                     'test_preamble_missing_real_flags_refuses_before_marker',
                                                     'test_preloaded_module_and_replaced_policy_refuse_without_repair',
                                                     'test_profile_is_explicit_nested_only_and_decode_has_no_policy_side_effect',
                                                     'test_real_new_profile_compiler_early_policy_and_final_utf8_ceiling',
                                                     'test_shared_actual_startup_predicate_rejects_foreign_writable_links_types_count',
                                                     'test_stat_uid_model_preserves_complete_interface_and_linecache'),
                                           'functions': ('_stat_view',
                                                         'child',
                                                         'fstat',
                                                         'guarded_open',
                                                         'listed',
                                                         'named',
                                                         'named_or_invalid',
                                                         'native_list',
                                                         'nested_commitment',
                                                         'opened',
                                                         'root_fstat',
                                                         'root_stat',
                                                         'test_actual_nofollow_link_metadata_recheck_and_unsupported_acl_refusal',
                                                         'test_ignored_node_rejects_unqualified_parent_before_open',
                                                         'test_ignored_node_visible_metadata_is_closed_data_not_errno_absence',
                                                         'test_new_profile_mutated_probe_hash_refuses_canonical_admission',
                                                         'test_no_follow_scanner_never_classifies_target_or_descends_symlinks',
                                                         'test_normal_imports_and_importlib_cannot_execute_marker',
                                                         'test_preamble_missing_real_flags_refuses_before_marker',
                                                         'test_preloaded_module_and_replaced_policy_refuse_without_repair',
                                                         'test_profile_is_explicit_nested_only_and_decode_has_no_policy_side_effect',
                                                         'test_real_new_profile_compiler_early_policy_and_final_utf8_ceiling',
                                                         'test_shared_actual_startup_predicate_rejects_foreign_writable_links_types_count',
                                                         'test_stat_uid_model_preserves_complete_interface_and_linecache',
                                                         'unsupported')},
 'tests/test_paid_initializer_runtime_library.py': {'cases': ('test_actual_two_fixed_links_and_ordinary_library_are_held_and_closed',
                                                              'test_either_link_nonliteral_or_escape_refuses_before_content',
                                                              'test_late_either_link_or_library_change_refuses_and_closes',
                                                              'test_library_hash_refuses_real_byte_change_with_stable_modelled_stat',
                                                              'test_library_target_and_ancestor_guards_remain_closed'),
                                                    'functions': ('acl',
                                                                  'foreign',
                                                                  'library_chain',
                                                                  'owned_fstat',
                                                                  'owned_open',
                                                                  'owned_stat',
                                                                  'read',
                                                                  'stable',
                                                                  'stable_name',
                                                                  'test_actual_two_fixed_links_and_ordinary_library_are_held_and_closed',
                                                                  'test_either_link_nonliteral_or_escape_refuses_before_content',
                                                                  'test_late_either_link_or_library_change_refuses_and_closes',
                                                                  'test_library_hash_refuses_real_byte_change_with_stable_modelled_stat',
                                                                  'test_library_target_and_ancestor_guards_remain_closed')},
 'tests/test_paid_initializer_sysconfig.py': {'cases': ('test_actual_content_hash_refuses_even_with_modelled_stable_metadata',
                                                        'test_actual_exact_link_and_ordinary_target_are_held_without_execution',
                                                        'test_late_namespace_and_content_change_refuse_and_dispose',
                                                        'test_retarget_escape_and_other_relative_shapes_refuse_before_target_read',
                                                        'test_target_chain_custody_mode_and_acl_refuse'),
                                              'functions': ('acl',
                                                            'foreign',
                                                            'library_fixture',
                                                            'owned_fstat',
                                                            'owned_open',
                                                            'owned_stat',
                                                            'read',
                                                            'stable_fstat',
                                                            'stable_stat',
                                                            'test_actual_content_hash_refuses_even_with_modelled_stable_metadata',
                                                            'test_actual_exact_link_and_ordinary_target_are_held_without_execution',
                                                            'test_late_namespace_and_content_change_refuse_and_dispose',
                                                            'test_retarget_escape_and_other_relative_shapes_refuse_before_target_read',
                                                            'test_target_chain_custody_mode_and_acl_refuse')},
 'tests/test_paid_initializer_token_data.py': {'cases': ('TestLinuxFrozenData.test_body_failure_repeatedly_disposes_private_fds',
                                                         'TestLinuxFrozenData.test_denied_mutation_never_rebaselines_snapshot_custody',
                                                         'TestLinuxFrozenData.test_late_origin_change_refuses_and_closes',
                                                         'TestLinuxFrozenData.test_real_seals_custody_private_env_and_cleanup',
                                                         'test_actual_origin_changed_during_copy_refuses',
                                                         'test_actual_origin_multiple_links_refuse',
                                                         'test_actual_posix_origin_read_preserves_offset',
                                                         'test_actual_write_capable_origin_fd_refuses',
                                                         'test_arbitrary_mapping_error_cannot_echo_private_value',
                                                         'test_executable_or_noncanonical_helper_refused',
                                                         'test_expected_fingerprint_inputs_remain_closed',
                                                         'test_origin_mismatch_refuses',
                                                         'test_post_hook_missing_or_changed_token_refuses',
                                                         'test_private_environment_drift_refuses_without_repair',
                                                         'test_private_environment_is_explicit_immutable_and_non_echo',
                                                         'test_private_shape_and_serialization_are_non_echo',
                                                         'test_snapshot_identity_mismatch_refuses_before_seal_use',
                                                         'test_unsupported_platform_has_no_snapshot_fallback'),
                                               'functions': ('__getitem__',
                                                             '__iter__',
                                                             '__len__',
                                                             'changed',
                                                             'origin',
                                                             'test_actual_origin_changed_during_copy_refuses',
                                                             'test_actual_origin_multiple_links_refuse',
                                                             'test_actual_posix_origin_read_preserves_offset',
                                                             'test_actual_write_capable_origin_fd_refuses',
                                                             'test_arbitrary_mapping_error_cannot_echo_private_value',
                                                             'test_body_failure_repeatedly_disposes_private_fds',
                                                             'test_denied_mutation_never_rebaselines_snapshot_custody',
                                                             'test_executable_or_noncanonical_helper_refused',
                                                             'test_expected_fingerprint_inputs_remain_closed',
                                                             'test_late_origin_change_refuses_and_closes',
                                                             'test_origin_mismatch_refuses',
                                                             'test_post_hook_missing_or_changed_token_refuses',
                                                             'test_private_environment_drift_refuses_without_repair',
                                                             'test_private_environment_is_explicit_immutable_and_non_echo',
                                                             'test_private_shape_and_serialization_are_non_echo',
                                                             'test_real_seals_custody_private_env_and_cleanup',
                                                             'test_snapshot_identity_mismatch_refuses_before_seal_use',
                                                             'test_unsupported_platform_has_no_snapshot_fallback')}}



_H1_OWNED['tests/test_paid_provider_entry_linux.py'] = {
    'cases': (
        'test_actual_compiled_c_executor_model_and_original_result',
        'test_compiled_fixture_data_assembles_against_real_wire_and_compilers',
        'test_retained_output_canary_discriminator_uses_owned_fixed_leaves',
        'test_retained_output_symlink_and_original_namespace_swap_refuse',
        'test_unknown_process_settlement_preserves_disposable_namespace',
        'test_executor_timeout_terminates_only_same_identity_once_and_consumes',
        'test_truncated_http_fixture_announces_full_body_then_closes',
        'test_model_cleanup_requires_exact_original_terminal_before_removal',
        'test_executor_identity_retains_actual_popen_pid_and_start_scope',
    ),
    'functions': (
        '_identity', '_fixture_output_namespace', '_fixture_owned_bytes',
        '_assert_fixture_outputs_private', '_fixture_executor_identity',
        '_communicate_fixture_executor', '_fixture_model_settled',
        '_fixture_http_response', '_exclusive_home_fixture', '_source_stage',
        '_request_material', '_publish_support', '_fixture_premodel_diagnostic',
        '_fixture_intermediate_command', '_fixture_intermediate_failure',
        'test_actual_compiled_c_executor_model_and_original_result',
        'test_compiled_fixture_data_assembles_against_real_wire_and_compilers',
        'test_retained_output_canary_discriminator_uses_owned_fixed_leaves',
        'test_retained_output_symlink_and_original_namespace_swap_refuse',
        'test_unknown_process_settlement_preserves_disposable_namespace',
        'test_executor_timeout_terminates_only_same_identity_once_and_consumes',
        'test_truncated_http_fixture_announces_full_body_then_closes',
        'test_model_cleanup_requires_exact_original_terminal_before_removal',
        'test_executor_identity_retains_actual_popen_pid_and_start_scope',
        'observed_stat', 'stat_fixed', 'close_server', '__init__',
        '__getattr__', 'communicate', 'poll', 'terminate', 'log_message', 'do_POST',
    ),
}


# One exact new source test exposed by the composed full-suite failure. This
# adds no dynamic path, traceback text, namespace value or parameter source.
_H1_OWNED['tests/test_paid_executor_held_yaml.py'] = {
    'cases': ('test_root_loader_ast_constants_and_custody_preserved',),
    'functions': ('test_root_loader_ast_constants_and_custody_preserved',),
}


def _h1_failure_metadata(nodeid,phase,*,error=None,crash=None):
    module=nodeid.split('::',1)[0]
    if module not in _H1_OWNED or phase not in ('collect','setup','call','teardown'):return None
    parts=nodeid.split('::')[1:]
    candidate='.'.join(x.split('[',1)[0] for x in parts)
    case=candidate if candidate in _H1_OWNED[module]['cases'] else None
    value=dict(module=module,case=case,function=None,phase=phase,line=None,errno=None)
    expected=os.path.normpath(os.path.join(os.getcwd(),module))
    if error is not None:
        trace=error.__traceback__
        while trace is not None:
            code=trace.tb_frame.f_code
            if (os.path.normpath(os.path.abspath(code.co_filename))==expected
                    and code.co_name in _H1_OWNED[module]['functions']
                    and type(trace.tb_lineno)is int and 0<trace.tb_lineno<=1000000):
                value.update(function=code.co_name,line=trace.tb_lineno)
            trace=trace.tb_next
        if type(error) in (OSError,PermissionError,FileNotFoundError,NotADirectoryError,IsADirectoryError,TimeoutError):
            number=error.errno
            if type(number)is int and 0<=number<=4096:value['errno']=number
    elif crash is not None:
        filename=getattr(crash,'path',None);line=getattr(crash,'lineno',None)
        if (type(filename)is str and os.path.normpath(os.path.abspath(filename))==expected
                and type(line)is int and 0<line<=1000000):value['line']=line
    return value


def _h1_metadata_is_safe(value):
    if type(value)is not dict or set(value)!={'module','case','function','phase','line','errno'}:return False
    module=value['module']
    if type(module)is not str or module not in _H1_OWNED:return False
    if value['case'] is not None and value['case'] not in _H1_OWNED[module]['cases']:return False
    if value['function'] is not None and value['function'] not in _H1_OWNED[module]['functions']:return False
    if value['phase'] not in ('collect','setup','call','teardown'):return False
    return ((value['line'] is None or type(value['line'])is int and 0<value['line']<=1000000)
        and (value['errno'] is None or type(value['errno'])is int and 0<=value['errno']<=4096))


def _module_of(nodeid):
    return nodeid.split("::", 1)[0]


def _worker_key(report):
    # pytest-xdist stamps every report relayed to the controller with the
    # WorkerController that produced it; a serial run has no such attribute.
    node = getattr(report, "node", None)
    if node is None:
        return None
    gateway = getattr(node, "gateway", None)
    return getattr(gateway, "id", None) or id(node)


class ModuleTiming:
    """Per-module CI_MODULE start/summary records.

    Serial runs see modules one after another, so a new module's first test
    closes the previous module. Under pytest-xdist (``--dist loadfile``) the
    controller receives interleaved events from several workers; every module
    still runs on exactly one worker, so a worker's first report for a
    different module closes that worker's previous module, and the session
    end closes whatever is still open. Records are diagnostics only; every
    pytest exit status still governs.
    """

    def __init__(self, reporter, diagnostics=None, *, parallel=False):
        self.reporter = reporter
        self.diagnostics = diagnostics
        self.parallel = bool(parallel)
        self.module = None
        self._open = {}
        self._worker_module = {}

    def _emit(self, event, module, **fields):
        # Pytest's quiet progress dots can leave an unterminated line. Keep
        # each record independently parseable without touching that output.
        self.reporter.write_line("\nCI_MODULE " + json.dumps(
            {"event": event, "module": module, **fields}, sort_keys=True,
        ))
        if self.diagnostics is not None:
            try:self.diagnostics.progress_record(event,module,**fields)
            except Exception:pass

    def _summarize(self, module):
        state = self._open.pop(module, None)
        if state is not None:
            self._emit(
                "summary", module, cases_started=state["cases_started"],
                cases_finished=state["cases_finished"],
                reported_seconds=round(state["reported_seconds"], 6),
            )

    def _h1_failure(self,nodeid,phase,*,error=None,crash=None):
        if self.diagnostics is not None:
            try:
                value=self.diagnostics.failure_record(nodeid,phase,error=error,crash=crash)
                if value is not None:
                    self.reporter.write_line('\n::error title=CI fixed failure metadata::'
                        +json.dumps(value,sort_keys=True,separators=(',',':')))
            except Exception:pass
        try:
            try:value=_h1_failure_metadata(nodeid,phase,error=error,crash=crash)
            except Exception:
                # A diagnostic failure must never replace the original test result.
                # Keep only the independently fixed module/phase, without rendering it.
                module=nodeid.split('::',1)[0]
                value=(dict(module=module,case=None,function=None,phase=phase,line=None,errno=None)
                    if module in _H1_OWNED and phase in ('collect','setup','call','teardown') else None)
            if value is not None and _h1_metadata_is_safe(value):
                self.reporter.write_line('\n::error file='+value['module']
                    +',title=H1 preflight failure metadata::'+json.dumps(value,sort_keys=True,separators=(',',':')))
        except Exception:
            pass  # Best-effort diagnostics cannot replace the original report.

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self,item,call):
        outcome=yield
        report=outcome.get_result()
        try:
            if report.failed:
                error=call.excinfo.value if call.excinfo is not None else None
                self._h1_failure(report.nodeid,report.when,error=error)
        except Exception:
            pass

    def pytest_collectreport(self,report):
        try:
            if report.failed:
                crash=getattr(report.longrepr,'reprcrash',None)
                self._h1_failure(report.nodeid,'collect',crash=crash)
        except Exception:
            pass

    def pytest_runtest_logstart(self, nodeid, location):
        module = _module_of(nodeid)
        if module not in self._open:
            if not self.parallel:
                for previous in list(self._open):
                    self._summarize(previous)
            self._open[module] = {
                "cases_started": 0, "cases_finished": 0, "reported_seconds": 0.0,
            }
            self._emit("start", module)
        self._open[module]["cases_started"] += 1
        self.module = module

    def pytest_runtest_logreport(self, report):
        module = _module_of(report.nodeid)
        state = self._open.get(module)
        if state is not None:
            state["reported_seconds"] += report.duration
        if self.parallel:
            worker = _worker_key(report)
            if worker is not None:
                previous = self._worker_module.get(worker)
                if previous is not None and previous != module:
                    self._summarize(previous)
                self._worker_module[worker] = module
            # Workers do not run this plugin's makereport wrapper for the
            # controller; keep the fixed failure metadata from the relayed
            # report (no live exception object is available here).
            try:
                if report.failed:
                    self._h1_failure(
                        report.nodeid, report.when,
                        crash=getattr(report.longrepr, "reprcrash", None),
                    )
            except Exception:
                pass

    def pytest_runtest_logfinish(self, nodeid, location):
        state = self._open.get(_module_of(nodeid))
        if state is not None:
            state["cases_finished"] += 1

    def pytest_sessionfinish(self, session, exitstatus):
        for module in list(self._open):
            self._summarize(module)



# Explicit serial invocation evidence. This companion bypasses FixedDiagnostics:
# its closed progress schema and the private completion receipt stay unchanged.
_CASE_SCHEMA = "ci.module-case-evidence.v1"
_CASE_MAX_COUNT = 1 << 20
_CASE_MAX_NODE_BYTES = 16 * 1024
_CASE_MAX_PHASE_BYTES = 4 * 1024
_CASE_MAX_TOTAL_BYTES = 64 * 1024 * 1024


def pytest_addoption(parser):
    parser.addoption("--ci-case-evidence", action="store_true", default=False,
                     help="emit bounded case/outcome evidence for this serial invocation")


def _case_evidence_enabled(config):
    option = config.option
    return (
        bool(getattr(option, "ci_case_evidence", False))
        and "--ci-case-evidence" in config.invocation_params.args
        and not hasattr(config, "workerinput")
        and not getattr(option, "numprocesses", None)
        and not getattr(option, "tx", None)
        and getattr(option, "dist", "no") in (None, "no")
    )


class ModuleCaseEvidence:
    """Observe whole-file serial execution without affecting pytest's verdict."""

    def __init__(self, reporter, config):
        from pathlib import Path

        self.reporter = reporter
        # Tests may patch shared serializers or these module constants until
        # fixture teardown. Their call reports arrive before that restoration.
        # Keep this invocation's original serializer and finite bounds; a new
        # observer still receives the configured bounds at its construction.
        self._json_dumps = json.dumps
        self._max_count = _CASE_MAX_COUNT
        self._max_node_bytes = _CASE_MAX_NODE_BYTES
        self._max_phase_bytes = _CASE_MAX_PHASE_BYTES
        self._max_total_bytes = _CASE_MAX_TOTAL_BYTES
        self.states = {}
        self.errors = set()
        self.collection_completed = False
        self.active = None
        self.bytes = 0
        self.overflow = False
        root = Path(config.rootpath)
        for argument in config.args:
            if (type(argument) is not str or "::" in argument
                    or not argument.endswith(".py")):
                self.errors.add("non_file_selection")
                continue
            try:
                path = Path(os.path.abspath(argument)).relative_to(root).as_posix()
            except ValueError:
                self.errors.add("non_file_selection")
                continue
            if len(path.encode("utf-8")) > self._max_node_bytes:
                self.errors.add("selection_overflow")
                continue
            self.states.setdefault(path, dict(
                collected=None, finished=[], deselected=[], collection=[],
                invocations=[], phase_reports=0, errors=set(),
            ))
        if not self.states:
            self.errors.add("empty_selection")

    def _canonical(self, value):
        return self._json_dumps(value, ensure_ascii=True, separators=(",", ":"))

    def _state(self, nodeid):
        try:
            valid = type(nodeid) is str and len(nodeid.encode("utf-8")) <= self._max_node_bytes
        except UnicodeError:
            valid = False
        if not valid:
            self.overflow = True
            self.errors.update({"invalid_nodeid", "evidence_overflow"})
            return None
        state = self.states.get(_module_of(nodeid))
        if state is None:
            self.errors.add("unexpected_module")
        return state

    def _append(self, state, field, value):
        if self.overflow:
            return False
        size = len(self._canonical(value).encode("ascii"))
        if len(state[field]) >= self._max_count or self.bytes + size > self._max_total_bytes:
            self.overflow = True
            self.errors.add("evidence_overflow")
            return False
        state[field].append(value)
        self.bytes += size
        return True

    def pytest_collectreport(self, report):
        try:
            module = _module_of(report.nodeid)
            state = self.states.get(module)
            if state is None:
                if report.failed:
                    self.errors.add("collection_failed")
                return  # Directory/session collectors are not selected whole files.
            outcome = report.outcome
            if outcome not in ("passed", "failed", "skipped"):
                state["errors"].add("invalid_collection_outcome")
                return
            if self._state(report.nodeid) is not None:
                self._append(state, "collection", [report.nodeid, outcome])
            if outcome == "failed":
                state["errors"].add("collection_failed")
        except Exception:
            self.errors.add("observer_error")

    def pytest_deselected(self, items):
        try:
            for item in items:
                state = self._state(item.nodeid)
                if state is not None:
                    self._append(state, "deselected", item.nodeid)
                if self.overflow:
                    break
        except Exception:
            self.errors.add("observer_error")

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session):
        try:
            for state in self.states.values():
                state["collected"] = []
            for item in session.items:
                state = self._state(item.nodeid)
                if state is not None:
                    self._append(state, "collected", item.nodeid)
                if self.overflow:
                    break
            self.collection_completed = True
        except Exception:
            self.errors.add("observer_error")

    def pytest_runtest_logstart(self, nodeid, location):
        try:
            if self.active is not None:
                self.active[1]["errors"].add("unfinished_invocation")
            state = self._state(nodeid)
            self.active = None if state is None else [nodeid, state, []]
        except Exception:
            self.errors.add("observer_error")

    def pytest_runtest_logreport(self, report):
        try:
            state = self._state(report.nodeid)
            if state is None:
                return
            if self.active is None or self.active[0] != report.nodeid:
                state["errors"].add("unmatched_report")
                return
            if report.when not in ("setup", "call", "teardown") or report.outcome not in (
                "passed", "failed", "skipped"
            ):
                state["errors"].add("invalid_phase")
                return
            # Preserve repeated call reports (including subtests), each outcome,
            # and xfail presence. Never retain repr, reasons, durations or locals.
            phase = [report.when, report.outcome, hasattr(report, "wasxfail")]
            phases = self.active[2]
            size = len(self._canonical(phase).encode("ascii"))
            if (size > self._max_phase_bytes or state["phase_reports"] >= self._max_count
                    or self.bytes + size > self._max_total_bytes):
                self.overflow = True
                self.errors.add("evidence_overflow")
                return
            if not self.overflow:
                phases.append(phase)
                state["phase_reports"] += 1
                self.bytes += size
        except Exception:
            self.errors.add("observer_error")

    def pytest_runtest_logfinish(self, nodeid, location):
        try:
            state = self._state(nodeid)
            if state is None:
                return
            self._append(state, "finished", nodeid)
            if self.active is None or self.active[0] != nodeid:
                state["errors"].add("unmatched_finish")
                return
            phases = self.active[2]
            kinds = [phase[0] for phase in phases]
            valid = (
                len(phases) >= 2 and kinds[0] == "setup" and kinds[-1] == "teardown"
                and kinds.count("setup") == kinds.count("teardown") == 1
                and all(kind == "call" for kind in kinds[1:-1])
                and ((phases[0][1] == "passed" and len(phases) >= 3)
                     or (phases[0][1] != "passed" and len(phases) == 2))
            )
            if not valid:
                state["errors"].add("incomplete_phases")
            self._append(state, "invocations", [nodeid, phases])
            self.active = None
        except Exception:
            self.errors.add("observer_error")

    def _row(self, module, state):
        from scripts.ci_xdist_guard import item_digest

        errors = self.errors | state["errors"]
        collection_observed = any(row[0] == module for row in state["collection"])
        collection_complete = (
            self.collection_completed and collection_observed
            and "collection_failed" not in errors and not self.overflow
        )
        collected = (state["collected"] if collection_complete else None)
        finished = state["finished"]
        if not collection_observed:
            errors = errors | {"collection_unobserved"}
        complete = (
            collection_complete and not errors and not state["deselected"]
            and sorted(collected) == sorted(finished)
            and len(state["invocations"]) == len(finished)
        )

        def digest(values):
            if values is None or self.overflow:
                return None
            # Sorting full values preserves multiplicity. Invocation phase lists
            # stay associated, so identical phase bags cannot hide different cases.
            ordered = sorted(values) if all(type(value) is str for value in values) else sorted(
                values, key=self._canonical
            )
            return item_digest(ordered)

        return dict(
            event="case_evidence", schema=_CASE_SCHEMA, module=module, pid=os.getpid(),
            complete=bool(complete), errors=sorted(errors),
            collection_complete=bool(collection_complete),
            collected=None if collected is None or self.overflow else len(collected),
            finished=None if self.overflow else len(finished),
            deselected=None if self.overflow else len(state["deselected"]),
            collection_reports=None if self.overflow else len(state["collection"]),
            case_invocations=None if self.overflow else len(state["invocations"]),
            phase_reports=None if self.overflow else state["phase_reports"],
            collected_sha256=digest(collected), finished_sha256=digest(finished),
            deselected_sha256=digest(state["deselected"]),
            collection_sha256=digest(state["collection"]) if collection_observed else None,
            outcomes_sha256=digest(state["invocations"]),
        )

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if self.active is not None:
            self.active[1]["errors"].add("unfinished_invocation")
        for module, state in self.states.items():
            try:
                row = self._row(module, state)
                self.reporter.write_line("\nCI_MODULE " + self._json_dumps(row, sort_keys=True))
            except Exception:
                # Absence is not a valid evidence row; never replace pytest's exit.
                pass


def pytest_sessionstart(session):
    config = session.config
    if hasattr(config, "workerinput"):
        # pytest-xdist worker: its terminal output is not relayed, and every
        # test event reaches the controller's registration below instead.
        return
    reporter = config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        diagnostics=None
        if os.environ.get('MMX_CI_FIXED_DIAGNOSTICS_DIR'):
            try:
                from pathlib import Path
                from scripts.ci_fixed_diagnostics import PublicCatalog,FixedDiagnostics
                diagnostics=FixedDiagnostics(PublicCatalog(Path(__file__).resolve().parents[1]),
                    os.environ['MMX_CI_FIXED_DIAGNOSTICS_DIR'])
            except Exception:pass
        parallel = bool(getattr(config.option, "numprocesses", None))
        config.pluginmanager.register(
            ModuleTiming(reporter, diagnostics, parallel=parallel), "ci-module-timing"
        )
        if _case_evidence_enabled(config):
            try:
                config.pluginmanager.register(
                    ModuleCaseEvidence(reporter, config), "ci-module-case-evidence"
                )
            except Exception:
                pass  # Missing evidence cannot replace the original pytest verdict.
