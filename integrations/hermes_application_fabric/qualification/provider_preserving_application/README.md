# Provider-preserving APPLICATION source join

This is a tested, exact-source contribution to the existing APPLICATION owner.
It combines the completed public provider guards and worker picker from selected
native sequence 37 with current APPLICATION source and the previously published
expected-latency extension. It does not select a native generation or enroll an
account. The original release owner must finish the remaining source overlaps,
closed manifest/component qualification and existing C3/bridge transition.

## Exact input and output

The APPLICATION preimage is `51b4abe1f68b58b2c41f9aa45aceaf2ab45670f3`.
The observed provider release is sequence 37, generation
`9c557397a9fbbcb88fa300b20063d6982c82fe5e768da951c74fa14a298d27b4`.
Its declared 116-member map matches protected provider profile blob
`ef808289fd862a586b1a82d5a1c57a5a862039df`.
[Original runtime metadata observation](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2175#issuecomment-6711529944).
Those observations do not replace the installer's complete byte/currentness checks.

`application-provider-latency.patch` applies to the exact four current owner
preimages and adds two disjoint tests. Full old/new Git blobs and SHA-256 hashes
are in `source-contract.json`. A clean isolated preimage passed `git apply --check`,
application and every postimage/unchanged-input comparison.

| Existing owner path | Current preimage | Combined postimage |
| --- | --- | --- |
| candidate/lease_broker.py | d8577c6ee5cc9bd3e7fc22905530f4755b860ae0 | 95f0974bebe0b02d3c01c3c5aa5e9eaa050856bd |
| candidate/pick.py | d17447c3c9f472b061733e36fa49a7f8d7e34ee5 | b645a6130f61c79635af798998f057ceb2fde220 |
| candidate/go_lease_gateway.py | e21b6d6a4e4230fce5f55d90820c6391d4b79324 | 9ba7f2c3e13c26c203bf9fd2e957de96dbf8bd0e |
| candidate/go_shim.py | 066d87cd23275204fb6d30af45ac03db1d4dbb4f | 36e91dca30c4788d1acd769272735475db64be39 |

The table paths are beneath `ops/native_fabric/quota_continuity/`.
The combined patch already includes the earlier latency proposal
`bccdbeaafd5535f399b3c1c60ed6dee897ce31924f648d883009de3b61e16010`.
**Apply one combined proposal; do not also apply that older patch.**
If an incumbent changes a preimage, reconcile that source first.

## Preservation and behavior

The two published provider picker stages apply in order to the current
APPLICATION picker and reproduce the complete selected-37 picker byte-for-byte
before adding latency. The later latency composition preserves its `hard_filter`,
`_plan_active_directory`, `_plan_auto_pick` and `format_pick` syntax trees.
The initial BytePlus/Experiential mode registration is retained.

The provider Broker contribution changes only `Broker._base_account_cap` before
latency is added. It preserves explicit enablement, bounded operator concurrency,
BytePlus subscription uniqueness and provider hard-stop policy, and Experiential's
single registered physical owner. The existing quota-circuit wrapper remains.
All other APPLICATION Broker methods, including physical occupancy across models,
original request recovery and settlement, are unchanged in that provider join.

Worker provider support does not grant APPLICATION authority. BytePlus and
Experiential remain outside the existing closed APPLICATION pool scope. The first
Hermes conversation still needs an eligible existing APPLICATION recipe/account.
Unknown provider allowance is never converted to zero or invented capacity.

The composed latency extension keeps the earlier qualified contract: trusted
bounded purpose; exact served model and complete physical-account cohort; fresh
owner evidence bound to the actual loaded Go transport; eligibility and cost
order before a unique-fastest tie resolution. Strict model/pool intent stays
strict. New dispatches recheck the binding; existing pending, terminal and
uncertain requests retain their original owner. Timeout and 429 create no replay
permission. Other latency-required transports remain unknown until their owner
supplies a qualified producer.

## Executed qualification

The final exact-source composition passed **152 cases, zero failures/errors/skips**:

- Seven direct provider/APPLICATION join cases, with the real Broker and real
  provider enrollment predicates. They cover duplicate subscription headroom,
  stale exhausted windows, explicit limits, Experiential physical-owner binding,
  worker/APPLICATION authority separation and strict worker routing refusal.
- Twenty-eight latency cases plus 117 existing APPLICATION picker, admission,
  Gateway and handler cases. Existing concurrent cross-model/shared-worker-cap
  and original-effect recovery tests remain unchanged.

The duplicate-subscription and Experiential owner cases both fail against the
unmodified APPLICATION preimage and pass against this composition. The proof
retains those two expected baseline failures. Log hashes, Python version and
source identities are in `qualification.json` and `source-contract.json`.

The tests use inert data and the incumbent ephemeral loopback provider fixture.
No installed source, provider credential, live provider call, grant issuance or
native selection was used. The full provider AUTO stage test remains with its
owner because it reconstructs/imports the held controller/source cohort; these
results do not claim that full release qualification.

## Existing-owner integration

Consume the exact patch into the current APPLICATION composition and preserve
all nine selected provider dependencies. In particular, the existing profile
maps `control_plane/experiential_plan_policy.py` to the flat runtime module
`ext/experiential_plan_policy.py`; retain that mapping. The policy helpers are
unchanged, not new copies or registries.

Finish the remaining selected-source overlaps through their active owners, then
qualify the complete explicit native manifest, source inventory and existing
Go/HTTP component metadata. Keep the current installer/publisher transaction,
consumer/bridge checks and full expected-CURRENT comparison. A standalone
107/109/112 stage is not a replacement for the selected provider cohort.

The original operation then owns release, existing Secretary role/service
enrollment and account qualification. The final owed proof remains authenticated
Hermes primary reasoning, one harmless native tool and continuation, actual
provider/model/account/lease attribution, usage and financial enforcement, and
original-request recovery without duplicate effects.
