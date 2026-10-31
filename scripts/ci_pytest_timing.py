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


class ModuleTiming:
    def __init__(self, reporter):
        self.reporter = reporter
        self.module = None
        self.cases_started = 0
        self.cases_finished = 0
        self.reported_seconds = 0.0

    def _emit(self, event, **fields):
        # Pytest's quiet progress dots can leave an unterminated line. Keep
        # each record independently parseable without touching that output.
        self.reporter.write_line("\nCI_MODULE " + json.dumps(
            {"event": event, "module": self.module, **fields}, sort_keys=True,
        ))

    def _summarize(self):
        if self.module is not None:
            self._emit(
                "summary", cases_started=self.cases_started,
                cases_finished=self.cases_finished,
                reported_seconds=round(self.reported_seconds, 6),
            )

    def _h1_failure(self,nodeid,phase,*,error=None,crash=None):
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
        module = nodeid.split("::", 1)[0]
        if module != self.module:
            self._summarize()
            self.module = module
            self.cases_started = self.cases_finished = 0
            self.reported_seconds = 0.0
            self._emit("start")
        self.cases_started += 1

    def pytest_runtest_logreport(self, report):
        if report.nodeid.split("::", 1)[0] == self.module:
            self.reported_seconds += report.duration

    def pytest_runtest_logfinish(self, nodeid, location):
        if nodeid.split("::", 1)[0] == self.module:
            self.cases_finished += 1

    def pytest_sessionfinish(self, session, exitstatus):
        self._summarize()


def pytest_sessionstart(session):
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        session.config.pluginmanager.register(ModuleTiming(reporter), "ci-module-timing")
