# Sequence-38 remote placement correction

An ordinary `audit` / `C1_ROUTINE_BOUNDED` preview currently enumerates BytePlus
and Experiential as remote-host modes. They belong to the existing separate local
plan path; the remote placement owner rejects `byteplus` with `ValueError`. The
picker masks that exception as `host prerequisite unavailable (ValueError)` and
discards otherwise eligible remote routes.

This closed source profile applies the already protected
`patches/pick_remote_plan_modes.forward.patch` to the complete selected
sequence-38 generation
`296e522f5f236d764aa4ad1b9fa677d7eea32e6bdfe2fc97c0755c06a857908f`.
Exactly `ext/pick.py` changes from `37c8809c...` to `f6f62ba5...`; the other
115 payloads remain byte-identical. The profile retains the newer provider-plan
source from sequence 38. It cannot adopt the older sequence-37 maintenance profile.

The default provider-plan profile, historical maintenance profile, local-plan
AUTO/consent/admission path, remote eligibility rules, Broker, policy, accounts,
runtime state bindings, launcher and entrypoints remain under their existing owners.
No arbitrary profile/patch path, provider override or new retry path is added.

## Source qualification

The new composition test reconstructs sequence 37 from the existing sealed public
fixture, runs the actual default composer to obtain sequence 38, then applies this
one-member successor. It checks all 116 hashes, every other picker definition,
the exact ordinary audit preview before and after, local-only mode refusal, and
changed/missing/symlink/wrong-generation inputs. Existing router and AUTO tests
remain the behavioral regression owners. All runtime observations in these tests
are inert fixtures; they do not prove provider availability or worker launch.

```sh
python3 -m pytest -q tests/test_current116_remote_placement_composition.py \
  tests/test_provider_plan_remote_mode_boundary.py tests/test_provider_plan_auto_routing.py
```

## Existing publication path

After protected source acceptance, compose from the exact verified live release
into a fresh owned stage outside the live kit and release store:

```sh
python3 ops/native_fabric/provider_plans/compose.py \
  --profile current116-remote-placement --base VERIFIED_SEQUENCE38 \
  --output NEW_PRIVATE_STAGE
```

The incumbent sealed `native_generation.py` publisher owns publication, verification,
its nonblocking publication lock and exact-current-generation CAS selection. Preserve
its existing interpreter, bridge, state bindings and old immutable generations. A
changed current pointer or competing publisher requires reconciliation; do not simply
substitute a different expected generation. Read back the selected release before
running a fresh read-only preview. No launcher or maintenance-guard upgrade is needed
for this same-schema, same-membership code successor.

This correction was identified while qualifying the Hermes Design Director in
[PR #2275](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2275).
The original audit `hermes-design-director-20261108-c1-01-visual-audit-01` remains
refused before launch; publication and selection do not authorize replay. A preview
or a fixed routing decision is not proof of admitted execution, model vision,
result delivery or design acceptance.
