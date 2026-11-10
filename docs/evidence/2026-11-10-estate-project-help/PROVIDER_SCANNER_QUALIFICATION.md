# Provider scanner glob-head optimization — source qualification

## Exact failure and scope

Repository `mastermindx-market-intelligence/Mastermind`, base `95762fc3700598a7be1a12b8c6c1995753071eed`; CI run `42796811883`, attempt 1, shard 4 job `129774519618`. The original case `test_r12_scanner_stays_fast_on_the_f1_f2_shapes[=(x) ]` scanned a 262,144-character input in 3.039100052 seconds against its existing 3-second cap. The CI excerpt is retained. This measurement alone does not prove a flaky test or superlinear growth.

Only `_r7_glob_head_names_wrapper` gains a necessary-condition fast path: if none of its actual recognized raw glob characters occur, return the same false result without tokenizing. No input cap, test threshold, watchdog, tokenizer, other scope reader, structural authorization predicate or command execution path changes. The original 333-KiB provider-policy test file remains byte-identical.

## Source proof for the necessary condition

`_R6Word.has_glob` accepts only `kind == "lit"` segments containing a character from the existing `_R6_GLOB_CHARS`. In the actual `_r6_lex_unbounded` call graph, literal segments are built from unchanged raw literal runs, unchanged raw characters, or the literal dollar sign supplied by `_r6_dollar`. `_R6Word.add`/`_flush` only concatenate those literal pieces; concatenation cannot manufacture a missing character. Single/double quotes, escapes, ANSI quotes, locale forms, parameter/arithmetic and command substitution use other segment kinds. Locale forwarding does not convert those pieces to literal segments. Malformed lexing already produces false in this particular helper. Therefore absence in raw input implies absence in every original unquoted literal segment and the original helper would return false.

This shortcut applies only to that glob-head reading. The remaining readers still inspect the command and can recognize encoded, quoted, computed or continuation-spliced wrapper names. The new test explicitly verifies those cases remain in scope.

## Decision and performance qualification

`scanner-affected.log`: **104 passed, 1 dependency deprecation warning, 17.62s**. The actual existing F1/F2 escape detection, armed structural refusal, scanner-disabled security negatives, all fourteen original F1/F2 timing shapes, and original glob/parts matcher comparison pass with their unchanged budgets. The new tests add thirty-seven absent-raw-glob lexical cases, nine positive raw-glob heads and five non-glob encoded wrapper spellings.

```sh
PYTHONPATH=/workspace/scratch/dfef37b7f33a/estate-return-qualification/.qualification-deps:.:tests python -m pytest --noconftest -c /dev/null tests/test_provider_orchestrator_glob_fast_path.py tests/test_provider_orchestrator_policy.py -k 'glob_fast_path or r12_f1_f2_scanner_fixes_name_each_escape or r12_escapes_are_refused_armed_by_structure_alone or r12_structural_table_every_escape_row_denies_without_the_scanner or r12_scanner_is_not_consulted_for_construct_bearing_commands or r12_scanner_stays_fast_on_the_f1_f2_shapes or r7_glob_and_parts_matchers' -q -x --tb=short
```

`scanner_probe.py` loads the exact original guard from its recorded preimage as a separate module and compares both the helper and complete `r6_names_wrapper` decisions against the candidate. It does not execute shell text. All **223** representative lexical comparisons match, including all eighteen original F1/F2 escape rows. Of those, 111 cases have no raw recognized glob and every actual original lexer result satisfies the necessary condition; twelve cases are original recognized glob heads. Hex/octal/Unicode ANSI forms, quoting, escaping, continuation, prefixes, substitution, and malformed constructs are included. Both pre-edit and post-edit comparison logs are retained.

The serial probe uses three samples per source per size, wall and CPU clocks, after the test workers completed. Medians for repeated `=(x) `:

| Input characters | Original wall seconds | Candidate wall seconds |
| --- | ---: | ---: |
| 32,768 | 0.1542 | 0.0601 |
| 65,536 | 0.4430 | 0.1179 |
| 131,072 | 0.7816 | 0.2531 |
| 262,144 | 1.9408 | 0.5112 |

The full samples are in `scanner-serial-comparison.log`. This is local relative evidence, not a guarantee of CI scheduling or a declaration that the entire scanner has been asymptotically proved. The unchanged three-second case passes locally; no CI rerun was initiated.

To reproduce the probe, place the full exact source snapshot under `source/`, the guard preimage under `preimages/ops/executive_os/provider_orchestrator_guard.py`, and the retained script next to those directories; run with the same dependency path and `python scanner_probe.py --timing`. The evidence directory retains the original script bytes; its default paths describe that qualification layout.

## Integrity and boundary

The two-file full-index patch was checked/applied to exact base preimages using `git apply --check --index` followed by `git apply --index`. Every replay byte matches its manifest postimage; staged whitespace check passes. The original guard blob is `5cb9470dee6d61cfda12bffb6d7aebbf3d394ef6`; the original provider-policy test blob stays `37ecdae9bb1065fbb109ee9c41afe632934b6095`.

Reviewable source only. No installed/provider/worker execution, credentials, authorization grants, runtime services, GitHub publication or workflow rerun occurred. The selected original owner security suites were exercised; the full 1,295-case provider-policy module and production CI remain separate from this bounded qualification.
