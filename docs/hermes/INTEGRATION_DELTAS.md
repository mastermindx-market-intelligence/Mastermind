# Integration deltas inside the reviewed packages

Commit `288c59a2` is the integration commit that edited these four trees after their reviewed heads. Later commits on this branch are listed after the tables. The harness glue is `integrations/hermes_harness/`, `docs/hermes/DEPLOY_UBUNTU1.md`, and `.github/workflows/hermes-harness.yml`. None of the rows below are that glue.

Reviewed heads:

| Package | PR | Reviewed head |
| --- | --- | --- |
| `integrations/hermes_runtime/` | #1874 | `88be7581` |
| `integrations/hermes_models/` | #1872 | `9bb815f2` |
| `integrations/hermes_steward/` | #1869 | `59daf821` |
| `integrations/hermes_delegate/` | #1871 | `35277633` |

Revert rule for this follow-up: drop a change that is not needed to integrate the packages and that has no covering test. Every row below has a covering test, so none were reverted. They remain fence changes on this branch.

## Runtime, relative to `88be7581`

| File | Reason | Kind | Test |
| --- | --- | --- | --- |
| `integrations/hermes_runtime/install.py` | Refuse a secrets path that resolves inside the state directory (`SECRETS_INSIDE_STATE_DIR`). | fence | `InstallLifecycleTests.test_secrets_file_inside_the_state_directory_is_refused` |
| `integrations/hermes_runtime/secrets.py` | Classify a short placeholder as `SECRETS_TOKEN_PLACEHOLDER` before the length check. | fence | `InstallLifecycleTests.test_placeholder_and_short_tokens_are_refused` |
| `integrations/hermes_runtime/systemd_unit.py` | Drop `AF_INET6` from `RestrictAddressFamilies`. Loopback stays `127.0.0.1`. | fence | `InstallLifecycleTests.test_rollback_then_uninstall_leaves_nothing` (`_assert_unit_has_no_secret`) |
| `integrations/hermes_runtime/tests/test_install_lifecycle.py` | Cover the three fences above, plus an existing unit-path escape (`UNIT_PATH_ESCAPES`) and a `0700` secrets file. | fence | The new methods in that file: `test_secrets_file_inside_the_state_directory_is_refused`, `test_unit_path_outside_the_user_dir_is_refused`, `test_placeholder_and_short_tokens_are_refused` |
| `integrations/hermes_runtime/tests/test_registry.py` | Cover the existing collision and child-env fences. No production change. | fence | `RegistryTests.test_every_refused_toolset_collides_as_an_extension`, `RegistryTests.test_registered_child_secret_names_are_forwarded_and_the_gateway_token_is_not` |

## Models, relative to `9bb815f2`

| File | Reason | Kind | Test |
| --- | --- | --- | --- |
| `integrations/hermes_models/contract.py` | `chain_for` raises when `provider_id` is outside the role, including a known catalog provider. Cursor stays last on the unpinned chain. | fence | `ContractTests.test_chairman_role_mapping` |
| `integrations/hermes_models/credentials.py` | Refuse a credential file with `st_nlink != 1`. Raise `JSONDecodeError` with `from None` so the parser exception is not chained. | fence | `SecretTests.test_symlink_hardlink_loose_mode_and_bad_json_do_not_leak` |
| `integrations/hermes_models/tests/test_contract.py` | Cover the outside-role pin refusal. | fence | `ContractTests.test_chairman_role_mapping` |
| `integrations/hermes_models/tests/test_secrets.py` | Cover symlink, hard link, mode `0700`, and bad JSON. | fence | `SecretTests.test_symlink_hardlink_loose_mode_and_bad_json_do_not_leak` |

## Steward, relative to `59daf821`

| File | Reason | Kind | Test |
| --- | --- | --- | --- |
| `integrations/hermes_steward/client.py` | Optional clock is read on every `read`. A non-ASCII bearer and a bearer over 16KiB are rejected. Compact JWT shape stays on the injected verifier. | fence | `ClientTests.test_clock_advances_between_reads`, `ClientTests.test_non_ascii_and_oversized_bearers_are_rejected` |
| `integrations/hermes_steward/tests/test_client.py` | Cover the clock and the bearer checks. | fence | Those two methods |

## Delegate, relative to `35277633`

No production file changed.

| File | Reason | Kind | Test |
| --- | --- | --- | --- |
| `integrations/hermes_delegate/tests/test_delegate.py` | Cover existing refusal paths: uppercase digest, `live_submit` before admission, a submit with no `replay_of`, a secret-shaped objective that is not stored, and an admitted child whose carrier is unbound. | fence | `DelegateEdgePaths.test_uppercase_sha_is_refused`, `test_live_submit_policy_is_refused_before_admission`, `test_absent_replay_of_submits_a_new_child`, `test_secret_shaped_objective_is_not_stored`, `test_admitted_unbound_carrier_latches_unknown` |

## Later runtime edits

These are not part of `288c59a2`. They load each agent's Slack id.

| File | Reason | Kind | Test |
| --- | --- | --- | --- |
| `integrations/hermes_runtime/systemd_unit.py` | `EnvironmentFile=` is that unit's 0600 secrets path, so the unit process receives `HERMES_SLACK_BOT_USER_ID`. The unit text still has no secret bytes. | glue | `InstallLifecycleTests._assert_unit_has_no_secret` |
| `integrations/hermes_runtime/secrets.py` | The Hermes child receives `HERMES_SLACK_BOT_USER_ID` from the secrets file and does not receive the bot token or the gateway token. | glue | `RegistryTests.test_registered_child_secret_names_are_forwarded_and_the_gateway_token_is_not` |
