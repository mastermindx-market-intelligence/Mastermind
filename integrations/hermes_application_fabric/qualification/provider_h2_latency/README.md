# Latency routing after the existing provider and H2 quota layers

This is the latency-only successor for the existing APPLICATION owner. It is qualified on the original owner's actual emitted provider/H2 HTTP stage, whose runtime inputs were retained when #2175 adopted d0c5431. It adds no provider account, credential, broker, routing service, quota ledger or installer.

The previous combined provider/latency patch remains historical. Do not apply it, or the older standalone latency patch, to this emitted cohort: the provider and H2 layers are already present.

## Exact composition boundary

Parent source: `0a6d33bfa3280e397c1c3d32a8a6bbcae014c17c`, retained by original `d0c543124b47372becd8ee632a1c29b32ffc3ef0`.

The source owner produced the HTTP stage with manifest `5da35ef46dc2a89449132c5043d4dd66cd30f020f3865ce2ad9cf3e8930d0479` and inventory `ce030bcc70b725f0e4f2eb6b3159954416f12fa2205e5cb20ad16173d3fccac9`. This qualifier verifies those metadata documents and only its 26 explicitly listed public dependencies. It does not read held native/J source, execute the release builder, or claim a complete 121-file byte verification.

`application-h2-latency.patch` has SHA256 `dd4f53955a43db64ca19c077e1a8e2d7692d3b1ae4e1b0aa6d1f879d7cbc4463`. Its 36 hunks target four **emitted** paths:

| Emitted path | Exact parent SHA256 | Qualified result SHA256 |
| --- | --- | --- |
| `ext/lease_broker.py` | `3a210b259681460ec1e8ded91c45f84f6807e6ba4da1704b1ce587693d6531ed` | `b0b7b99bebddfe89ad828d8b6ab625d8ba5b0c2a72472e5f17c946829413be5e` |
| `ext/pick.py` | `a61e4bd966cb3ce94cb00c262170453840edea02c4eb4d42b1521d097476a1dc` | `cac81aea3e9391378e89e8c76286aa6ce4c0a787dfcd6c2e3f1977dd687a13de` |
| `ext/go_lease_gateway.py` | `adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949` | `ac49c893c39cd9c8b1337dc0a5df19276cf1b3ddb530ced97e39de650c41e704` |
| `ext/go_application_handler.py` | `1cab35bdf7ee8fce5f12237035556a9ab4314299c5d7b71c0f44df320fe0dab7` | `e51ef79dc0c2319ec264ab3f93865e3b012c8d360bc5af2cea97aa8b69fa2dd9` |

The application handler is exposed as `candidate/go_shim.py` only inside the existing test fixture layout. Its production name and incumbent external Go component remain authoritative. Raw repository candidate files have different composition meaning even where an old preimage happens to match.

Every postimage reverses to its exact effective parent. Broker `_base_account_cap` and `_try_acquire_in_transaction`, picker `hard_filter` and `_eligible_host_routes`, and every other non-latency function retain their ASTs. H2 claim binding, configuration generation, recovery evidence and physical quota ownership remain unchanged.

## Routing behavior

A host-authorized purpose may add `max_expected_latency_ms`. It is an expected completion estimate for one bounded model request, including supplied conversation/tool history; it is not time to first token or a deadline for the whole agent/tool conversation.

The existing grant owner may attach a closed `latency_qualification` annotation. It binds the entire permitted account cohort, selected/served model identity, actual transport instance/configuration, provider configuration, source profile, task class/complexity, capabilities, request bytes, output tokens and freshness. The annotation grants no accounts or capacity and is excluded from the underlying permission digest, so refreshing performance evidence does not revoke unrelated open turns.

The existing picker first preserves policy eligibility, capability checks, model/pool restrictions, physical account headroom and incumbent economic rank/default behavior. Qualified latency can constrain eligibility and resolve equal-ranked model alternatives. Unknown, stale, mismatched or over-envelope estimates are never treated as zero. Equal-source ambiguity still refuses. A strict host model/pool selection cannot fall back to a faster unauthorized route.

The actual transport supplies its binding; an HTTP model caller cannot supply authority or performance evidence. The Go owner exposes its bounded binding only through its existing authenticated status. Pools without qualified facts remain ineligible for a strict latency requirement. This does not infer a non-Go performance producer from worker support.

The new bound is rechecked at selection, admission and each intentional step. Original pending/unknown/terminal recovery precedes current freshness checks. Changes after dispatch intent retain uncertain effects and never cause reselection or replay. Reader cancellation does not release a provider lease.

## Executed qualification

The committed `qualify.py` was executed against the frozen emitted inputs: **266 cases passed**, zero failures, errors, skips or unexpected effect attempts. See `qualification.json` and the complete `tests.log`.

| Existing or new coverage | Cases |
| --- | ---: |
| Original APPLICATION admission, picker, Go composition, selection and handler | 117 |
| Original AUTO request, cross-pool AUTO and registered pool selection/composition | 97 |
| Existing latency contract | 28 |
| Existing provider preservation | 7 |
| Existing H2 recovery on actual emitted files | 16 |
| New latency versus shared physical account occupancy | 1 |

The new interaction proves that fresh fast-model evidence cannot admit a second model while a real WORKER lease holds the same physical account's only slot. Refusal leaves the original lease and quota rows unchanged, creates no APPLICATION turn/request and sends nothing. Only original worker release permits one new APPLICATION admission. The separate H2 cases preserve one claimant across aliases and models, hard holds, refresh ordering and settlement.

Only numeric-loopback fixture servers are used. The real Broker/SQLite, selector, admission, handler, original source validators and H2 owner logic execute. No production credentials, live provider requests, enrollment, release selection or installed state are used.

The source contract freezes all public stage files, original fixtures and shared realm/protocol owners. Existing 28-case latency and seven-case provider fixtures are extracted unchanged from the earlier owner's combined patch; its runtime hunks are never replayed. The H2 fixture overrides only its existing `runtime_sources()` seam to use final emitted files.

## Reproduce through the current owner

Run with an existing owner-built stage and source checkout carrying the exact pinned fixtures:

```sh
python3 -B integrations/hermes_application_fabric/qualification/provider_h2_latency/qualify.py \
  --stage-root /path/to/existing-owner-http-stage \
  --source-root /path/to/qualified-source \
  --output-dir /tmp/hermes-provider-h2-latency-proof
```

The output directory must be new. The command materializes only a disposable test tree, verifies exact inputs and inverse composition, and runs the frozen 266-case inventory. It refuses drift and performs no install.

Initial development harness failures are retained in `development-observations.json`: an overbroad home guard affected library loading/relative cleanup, and the first expanded run lacked public realm/protocol and lane-runtime fixture dependencies. The completed qualifier contains those exact dependencies and passed the full suite in a single execution. No runtime source repair was needed for those harness failures.

## Original-owner integration action

Consume this exact latency-only delta **after** the provider and H2 layers in the existing APPLICATION builder/component contract. Recompute the incumbent emitted source manifest, inventory, external Go component and inverse plans together, preserving the selected provider family and both installer guards. Do not install these files by hand or substitute this qualifier for the owner builder.

The new performance annotation must be published by the existing grant/provider owner using real, bounded measurements and the actual transport binding. This package issues no performance fact, entitlement or funding authority.

The original #2175 carrier retains release and activation custody. The existing consumer/session/account operation must still prove the authenticated primary turn, an actually offered native tool and continuation, real provider/selected+served model/physical account/lease/usage/budget settlement, and original-request recovery. **Live acceptance remains open.**
