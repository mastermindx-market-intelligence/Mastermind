"""Preserve protected launch refusals when composing the independently evolved parser.

Only pure guard calls with fixture-issued receipts are made; command strings are
never executed. The original protected corpus remains unmodified. These checks
preserve its unsafe-command refusal outcomes without requiring obsolete private
helpers or identical diagnostic prose. Deliberately tighter r13 safe-form scope
is covered and documented by the existing integration tests, not relaxed here.
"""
from __future__ import annotations

import pytest

from ops.executive_os import provider_orchestrator_guard as guard
from tests.test_provider_orchestrator_policy import (
    _binding, _emitted, _guard_launch, _install, _payload,
    mastermind_scope, shared_placement,
)

PROTECTED_SOURCE = "81c08810fbacad1391a0dde32893e18fc5207272"
PROTECTED_TEST_SHA256 = "2909c18f27c963e46e0edba44a5ea74899a707b6e6f3ce33ea500b5c40ad585d"

# Exact literal inputs from the source-linked r5-r10 negative regression rows.
PROTECTED_REFUSALS = [('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:py-Sc',
  'python3 -Sc \'import os; os.system("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:py-Bc',
  'python3 -Bc \'import os; os.system("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:py-Ic',
  'python3 -Ic \'import os; os.system("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:py-uc',
  'python3 -uc \'import os; os.system("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:perl-we',
  'perl -we \'exec("pool","run","grok","a","/tmp","grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:perl-E',
  'perl -E \'exec "pool run grok a /tmp grok-4.6"\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:node-p',
  'node -p \'require("child_process").execSync("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:node-eval',
  'node --eval \'require("child_process").execSync("pool run grok a /tmp grok-4.6")\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:ruby-ne',
  'ruby -ne \'exec "pool run grok a /tmp grok-4.6"\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:php-nr',
  'php -nr \'system("pool run grok a /tmp grok-4.6");\''),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:heredoc-dash',
  'python3 - <<\'EOF\'\nimport os\nos.system("pool run grok a /tmp grok-4.6")\nEOF'),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:heredoc-bare',
  'python3 <<\'EOF\'\nimport os\nos.system("pool run grok a /tmp grok-4.6")\nEOF'),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:pipe-stdin',
  'echo \'import os; os.system("pool run grok a /tmp grok-4.6")\' | python3'),
 ('test_r5_b1_every_interpreter_is_refused_with_a_wrapper_name:interpreter-slot-script',
  'python3 /opt/mastermind/ext/slot.py grok -- run'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:function-twice',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f(){ pool run glm a '
  '/tmp glm-5.3; }; f; f'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:function-keyword',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code function f { pool '
  'run glm a /tmp glm-5.3; }; f'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:brace-for',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code for i in 1 2; { '
  'pool run glm a /tmp glm-5.3; }'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:brace-arith-for',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code for ((i=0;i<2;i++)) '
  '{ pool run glm a /tmp glm-5.3; }'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:trap',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code trap 'pool run glm "
  "a /tmp glm-5.3' USR1; kill -USR1 $$"),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:watch',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code watch -n 60 pool '
  'run glm a /tmp glm-5.3'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:timeout-foreground',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code timeout '
  '--foreground 600 pool run glm a /tmp glm-5.3'),
 ('test_r5_ma_function_brace_trap_and_repeater_launches_are_refused:awk-brace-program',
  'awk \'BEGIN{system("pool run grok a /tmp grok-4.6")}\''),
 ('test_r5_mb_eval_source_dot_inside_a_nested_shell_is_unobservable:nested-eval-concat',
  'X=\'export POOL_ORCH\' Y=\'ESTRATOR_ID=root-other\' bash -c \'eval "$X$Y"; pool run glm a /tmp glm-5.3\''),
 ('test_r5_mb_eval_source_dot_inside_a_nested_shell_is_unobservable:nested-eval',
  'bash -c \'eval "$X"; pool run glm a /tmp glm-5.3\''),
 ('test_r5_mb_eval_source_dot_inside_a_nested_shell_is_unobservable:nested-dot',
  "sh -c '. ./env.sh; pool run glm a /tmp glm-5.3'"),
 ('test_r5_mb_eval_source_dot_inside_a_nested_shell_is_unobservable:nested-source',
  "bash -c 'source ./env.sh; pool run glm a /tmp glm-5.3'"),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-pool-star',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool* run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-poo-star',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code poo* run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-poo-class',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code poo[l] run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-leading-star',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code *ool run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-sub-question',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code su?.sh grok'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-faithful-pool-star',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool* run glm a '
  '/tmp glm-5.3'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-second-launch',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp '
  'glm-5.3 ; poo* run grok a /tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:brace-expansion-head',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code po{o,}l run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-argument-with-wrapper-token',
  'sudo POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool* run grok '
  'a /tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-quoted-literal-star',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code "pool"* run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-inner-class',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code po[o]l run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_glob_expanded_command_words_are_refused:glob-bare-head',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code * run grok a /tmp '
  'grok-4.6'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:paren-function-twice',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f() ( pool run glm '
  'a /tmp glm-5.3 ); f; f'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:paren-function-recursive',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f() ( pool run glm '
  'a /tmp glm-5.3; f ); f'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:paren-function-keyword',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code function f () ( '
  'pool run glm a /tmp glm-5.3 ); f'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:paren-function-spaced',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f () ( pool run glm '
  'a /tmp glm-5.3 ); f'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:while-condition',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code while pool run glm '
  'a /tmp glm-5.3; do :; done'),
 ('test_r6_ma2_paren_function_bodies_and_loop_conditions_are_refused:until-condition',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code until pool run glm '
  'a /tmp glm-5.3; do :; done'),
 ('test_r6_b2_wrapper_glob_suffixes_are_refused:glob-pool-question',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool? run grok a '
  '/tmp grok-4.6'),
 ('test_r6_b2_wrapper_glob_suffixes_are_refused:glob-sub-sh-question',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code sub.sh? grok a /tmp '
  'grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:env-class-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code env poo[l] run grok '
  'a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:sudo-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code sudo poo? run grok '
  'a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:sudo-user-arg-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code sudo -u root poo[l] '
  'run grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:nice-adjust-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code nice -n 5 poo? run '
  'grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:exec-brace',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code exec po{o,}l run '
  'grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:usr-bin-env-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code /usr/bin/env poo? '
  'run grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:command-builtin-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code command poo[l] run '
  'grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:nohup-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code nohup poo? run grok '
  'a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:time-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code time poo? run grok '
  'a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:env-unset-arg-glob',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code env -u '
  'POOL_TASK_CLASS poo[l] run grok a /tmp grok-4.6'),
 ('test_r6_b2_expanded_wrapper_behind_transparent_runner_is_refused:xargs-pipe-glob',
  "printf '%s\\n' a b | xargs -n 1 poo? run grok a /tmp grok-4.6"),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:timeout', 'timeout 5 poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:watch', 'watch poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:watch-interval',
  'watch -n 0.2 ./poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:strace',
  'strace -o /dev/null poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:setsid', 'setsid poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:stdbuf', 'stdbuf -o0 poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:arch', 'arch -x86_64 poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:script',
  'script -q /dev/null poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_unlisted_runner_payloads_are_refused:nohup-timeout-chain',
  'nohup timeout 5 poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:faketime', 'faketime 5s poo* run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:vrfy', 'vrfy --mode x poo* run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:unbuffer', 'unbuffer poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:valgrind', 'valgrind -q poo? run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:chroot', 'chroot / poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:zzz', 'zzz --flag=1 poo* run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:attached-value',
  'faketime --when=po* poo* run grok a /tmp grok-4.6'),
 ('test_r7_posture_refuses_never_enumerated_runners:program-string-glob',
  'R -e \'system("poo* run grok x /tmp grok-4.6")\''),
 ('test_r7_b1_attached_value_flags_do_not_swallow_the_payload:sudo-user-eq',
  'sudo --user=root poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_b1_attached_value_flags_do_not_swallow_the_payload:env-unset-eq',
  'env --unset=FOO poo[l] run grok a /tmp grok-4.6'),
 ('test_r7_b1_attached_value_flags_do_not_swallow_the_payload:nice-adjust-eq',
  'nice --adjustment=5 poo* run grok a /tmp grok-4.6'),
 ('test_r7_b1_attached_value_flags_do_not_swallow_the_payload:xargs-max-eq',
  'xargs --max-args=2 poo* </dev/null'),
 ('test_r7_b1_shell_program_payloads_are_refused:bash-c', "bash -c 'poo* run grok x /tmp grok-4.6'"),
 ('test_r7_b1_shell_program_payloads_are_refused:sh-c', "sh -c 'poo* run grok x /tmp grok-4.6'"),
 ('test_r7_b1_shell_program_payloads_are_refused:ssh', "ssh h 'poo* run grok x /tmp grok-4.6'"),
 ('test_r7_m1_do_done_pair_in_a_loop_condition_is_refused:while-do-done-pair',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code while echo do echo '
  'done; pool run glm a /tmp glm-5.3; do :; done'),
 ('test_r7_m1_do_done_pair_in_a_loop_condition_is_refused:until-do-done-pair',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code until echo do echo '
  'done; pool run glm a /tmp glm-5.3; do :; done'),
 ('test_r7_m1_do_done_pair_in_a_loop_condition_is_refused:while-bare-do',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code while echo do; pool '
  'run glm a /tmp glm-5.3; do :; done'),
 ('test_r7_m1_do_done_pair_in_a_loop_condition_is_refused:while-grep-do',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code while grep -q do '
  'notes.txt; pool run glm a /tmp glm-5.3; do :; done'),
 ('test_r7_m1_do_done_pair_in_a_loop_condition_is_refused:while-quoted-do',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code while [ "$x" = "do" '
  ']; pool run glm a /tmp glm-5.3; do :; done'),
 ('test_r7_m1_paren_body_edge_spans_are_refused:next-line',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f()\n'
  '( pool run glm a /tmp glm-5.3 )\n'
  'f\n'
  'f'),
 ('test_r7_m1_paren_body_edge_spans_are_refused:behind-comment',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f() # c\n'
  '( pool run glm a /tmp glm-5.3 ); f; f'),
 ('test_r7_m1_paren_body_edge_spans_are_refused:quoted-close-paren',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code f() ( echo ")"; '
  'pool run glm a /tmp glm-5.3 ); f; f'),
 ('test_r7_m2_trap_program_concatenations_are_refused:backslash-concat',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code trap 'echo "
  "hi'\\;'pool run glm a /tmp glm-5.3' USR1; kill -USR1 4242"),
 ('test_r7_m2_trap_program_concatenations_are_refused:quote-splice',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code trap 'echo "
  "'\\''hi'\\''; pool run glm a /tmp glm-5.3 ' USR1; kill -USR1 4242"),
 ('test_r7_m2_trap_program_concatenations_are_refused:double-quote-concat',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code trap "echo hi""; '
  'pool run glm a /tmp glm-5.3" USR1; kill -USR1 4242'),
 ('test_r7_m2_trap_program_concatenations_are_refused:dash-dash',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code trap -- 'echo hi; "
  "pool run glm a /tmp glm-5.3' USR1; kill -USR1 4242"),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:R-system',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code R -e \'system("pool '
  'run grok x /tmp grok-4.6")\''),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:R-paste0',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code R -e '
  '\'system(paste0("po","ol run grok x"))\'; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:R-file',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code R --file '
  'tools/snip.R; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:sqlite3-read',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code sqlite3 db '.read "
  'e.sql\'; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:jshell',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code jshell -s '
  'tools/snip.jsh; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unlisted_interpreters_beside_a_launch_are_refused:java-jar',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code java -jar '
  'tools/App.jar; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unrecognized_heads_beside_a_launch_are_refused:groovy',
  "POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code groovy -e 'println "
  '1\'; pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unrecognized_heads_beside_a_launch_are_refused:make',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code make -f x.mk; pool '
  'run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unrecognized_heads_beside_a_launch_are_refused:octave',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code octave --eval 1; '
  'pool run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m3_unrecognized_heads_beside_a_launch_are_refused:renamed-wrapper',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code ln -s '
  '/usr/local/bin/pool p && ./p run glm a /tmp glm-5.3'),
 ('test_r7_m3_unrecognized_heads_beside_a_launch_are_refused:unknown-tool',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code zzz --mode x; pool '
  'run glm "bounded task" /tmp glm-5.3'),
 ('test_r7_m1_extglob_words_are_refused:plus-extglob', "po+(o)l run grok 'x' /tmp grok-4.6"),
 ('test_r7_m1_extglob_words_are_refused:question-extglob', "po?(o)l run grok 'x' /tmp grok-4.6"),
 ('test_r7_m1_extglob_words_are_refused:at-extglob', "su@(b).sh grok 'x'"),
 ('test_r8_br61_process_substitution_glob_payloads_are_refused:cat-procsub',
  "cat <(poo* run grok 'x' /tmp grok-4.6)"),
 ('test_r8_br61_process_substitution_glob_payloads_are_refused:diff-procsub',
  "diff <(poo* run grok 'x' /tmp grok-4.6) /dev/null"),
 ('test_r8_br61_process_substitution_glob_payloads_are_refused:write-procsub',
  "echo x > >(poo* run grok 'x' /tmp grok-4.6)"),
 ('test_r8_br61_process_substitution_glob_payloads_are_refused:extglob-procsub', "cat <(su?.sh grok 'x')"),
 ('test_r8_br61_process_substitution_glob_payloads_are_refused:command-sub',
  "cat $(poo* run grok 'x' /tmp grok-4.6)"),
 ('test_r8_br61_process_substitution_beside_faithful_launch_is_refused:beside-faithful',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp '
  'glm-5.3 && cat <(poo* run grok x /tmp grok-4.6)'),
 ('test_r8_br61_process_substitution_beside_faithful_launch_is_refused:write-beside-faithful',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp '
  'glm-5.3; echo x > >(poo* run grok x /tmp grok-4.6)'),
 ('test_r8_br61_process_substitution_beside_faithful_launch_is_refused:stdin-beside-faithful',
  'POOL_ORCHESTRATOR_ID=root-orch-1 POOL_PARENT_RUN_ID=hermes-run-7 POOL_TASK_CLASS=code pool run glm a /tmp '
  'glm-5.3 < <(poo* run grok x /tmp grok-4.6)'),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:if',
  "if poo* run grok 'x' /tmp grok-4.6; then :; fi"),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:while',
  "while poo* run grok 'x' /tmp grok-4.6; do :; done"),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:until',
  "until poo* run grok 'x' /tmp grok-4.6; do :; done"),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:negation', "! poo* run grok 'x' /tmp grok-4.6"),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:elif',
  "if :; then :; elif poo* run grok 'x' /tmp grok-4.6; then :; fi"),
 ('test_r8_br62_keyword_condition_glob_heads_are_refused:time-glob', "time poo? run grok 'x' /tmp grok-4.6"),
 ('test_r9_br71_backtick_payloads_are_refused:cat-head', "cat `poo* run grok 'x' /tmp grok-4.6`"),
 ('test_r9_br71_backtick_payloads_are_refused:echo-head', "echo `poo* run grok 'x' /tmp grok-4.6`"),
 ('test_r9_br71_backtick_payloads_are_refused:procsub-nested', 'cat <(echo `poo* run grok x`)'),
 ('test_r9_br71_backtick_payloads_are_refused:while-multiplexed',
  'while cat `poo* run grok x` >/dev/null; do :; done'),
 ('test_r9_br71_backtick_payloads_are_refused:class-glob', 'cat `poo[l] run grok x`'),
 ('test_r10_br81_glued_backtick_closer_output_reparse_is_refused:glob-closer', '`echo poo*`'),
 ('test_r10_br81_glued_backtick_closer_output_reparse_is_refused:qmark-closer', '`echo su?.sh`'),
 ('test_r10_br81_glued_backtick_closer_output_reparse_is_refused:brace-closer', '`echo po{o,}l`')]


@pytest.mark.parametrize("case_name,command", PROTECTED_REFUSALS,
                         ids=[name for name, _ in PROTECTED_REFUSALS])
def test_protected_unsafe_shape_stays_refused(shared_placement, tmp_path, monkeypatch,
                                            capsys, case_name, command):
    _install(monkeypatch, tmp_path, _binding())
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    result = _emitted(capsys)
    reason = result["permissionDecisionReason"]
    assert result["permissionDecision"] == "deny", case_name
    assert reason.startswith("Mastermind shared-placement guard:"), case_name
    assert "missing binding" not in reason and "not owner-authenticated" not in reason


@pytest.mark.parametrize("command", [
    "python /opt/x/slot.py glm -- run",
    "python3 /opt/x/slot.py glm -- run",
    "python3.12 /opt/x/slot.py glm -- run",
    "/usr/bin/python3 /opt/x/slot.py glm -- run",
    "env python3 /opt/x/slot.py glm -- run",
    "exec python3 /opt/x/slot.py glm -- run",
    "bash -c 'python3 /opt/x/slot.py glm -- run'",
    "python3 '/opt/x/slot.py' glm -- run",
])
def test_protected_interpreter_hosted_wrapper_refusal_is_not_lost(
        shared_placement, tmp_path, monkeypatch, capsys, command):
    _install(monkeypatch, tmp_path, _binding())
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    with pytest.raises(SystemExit):
        _guard_launch(shared_placement, command)
    result = _emitted(capsys)
    assert result["permissionDecision"] == "deny"
    assert "unobservable launch" in result["permissionDecisionReason"]
    assert "R6_INTERPRETER_WRAPPER" in result["permissionDecisionReason"]


def test_unarmed_interpreter_wrapper_keeps_existing_identity_checks(
        mastermind_scope, monkeypatch, capsys):
    for name in ("MASTERMIND_SHARED_PLACEMENT", "POOL_EXECUTION_BINDING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POOL_ORCHESTRATOR_ID", "root-orch-1")
    monkeypatch.setenv("POOL_PARENT_RUN_ID", "hermes-run-7")
    monkeypatch.setenv("POOL_TASK_CLASS", "code")
    command = "python3 /opt/x/slot.py glm -- run"
    guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert capsys.readouterr().out == ""
    monkeypatch.delenv("POOL_PARENT_RUN_ID")
    with pytest.raises(SystemExit):
        guard.guard_bash(_payload(mastermind_scope, command), {"command": command})
    assert "Fabric root-budget guard" in _emitted(capsys)["permissionDecisionReason"]
