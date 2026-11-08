# Current116 maintenance guard source overlay

This optional source profile starts from the complete sequence-37 generation
`9c557397a9fbbcb88fa300b20063d6982c82fe5e768da951c74fa14a298d27b4`.
It preserves all 116 payload names and changes three payloads: `ext/lease_broker.py`
adds the two previously reviewed static qualification/maintenance guard methods;
`ext/pick.py` applies the fixed-parent remote-placement patch from component
`7b1ba72f1a7159ea04278e7901f4cdd4ffc2304f`. It excludes exactly the two local-only
plan pools from remote validation while preserving ordinary remote eligibility
and the separate AUTO class/consent rules. `ext/remote_sub_exec.py` carries the previously reviewed command-scoped sparse
Git warning suppression while retaining every current APPLICATION definition and
strict stderr/config/read-only guard. The other 113 payloads stay exact.
Every incumbent Broker method, application-native recipe/invocation/recovery and
release check, module global and CLI remains unchanged. The ordinary provider-plan
profile and its default composition remain unchanged. Both patches use the same
repository-owned source root; callers cannot supply a profile or patch path.

The source provenance is the protected provider-plan chain: first profile
`7bc8a208d5cf867fcc269d9c049d53e52445347b` applied six patches over sequence 35,
including Broker `42d45e5c…` to `a841230c…`. The current profile at
`2541a68e9240ca3fb5c1fda7b68e1df8984c973b` inherited that Broker and applied four
AUTO patches over sequence 36. Its complete output manifest matches sequence 37.
The historical Broker patch is correctly absent from the current four-patch set.
`provenance.json` binds the exact method ASTs to reviewed source C43. Hashes prove
source correspondence; they do not establish live publisher custody or authority.

Run the existing source composer with the closed profile choice:

```sh
python3 ops/native_fabric/provider_plans/compose.py \
  --profile current116-maintenance-guard --base <verified-public-source-base> \
  --output <new-source-stage>
```

Composition checks the exact predecessor and all regular code payloads. It does
not copy runtime links or inspect their targets, construct Broker, read a database
or lock, inspect policy, publish an artifact, or select code. The committed inert
test reconstructs the actual current116 from the existing source fixture and
production default composer, then checks the new composition and actual picker traversal with inert owner
observations, without executing Broker or guard methods. Accepted guard behavior/review remains separate evidence.

The incumbent `native_generation.py` remains the only publication/CAS-selection
owner. Root must reconcile the actual current generation and live writers before
any separately authorized adoption. A newer selected cohort requires a new exact
source composition; this profile cannot roll it back. After qualified adoption,
fixed ORCH repair and policy qualification remain separate authorized effects;
no failed Fabric operation is retried by composing or selecting this source.
