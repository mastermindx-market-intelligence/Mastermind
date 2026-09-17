# Web-Sol census extension bundle closure

Operation: `web-sol-census-package-closure-20260906-sol-001`
Carrier: Slack `C0BSBM78V1N/1788711726.330709`
Parent: `WS:CHAIRMAN-CONTROL-ROOM`, MAS-198, Mastermind #501
Installer owner: existing #340; model/effort owner: existing #480
Original source baseline: `cd297f1079bf5a44b520697a096096000f64efdd`
Current protected procedure pin at repair: `4fe4d6bc93d9543f77320f68342a10c5af4d4f49`
Skillpack: `mastermind.sol_skillpack.v1`, 1.0.1, bootstrap major 1
State: `BUILT_NOT_PROVEN / SOURCE_ONLY / HOLD_FOR_REVIEW`

## Outcome and boundary

The installer needs the census popup, controller, collector and stylesheet as well
as the original manifest/background/content assets. The existing generated-only
renderer correctly produces three configuration/launcher artifacts. It does not
claim to package static extension source. This additive function makes that next
step explicit without changing that contract or creating another installer.

`render_census_extension_bundle` returns a private `DeploymentBundle`-compatible
complete-bundle subtype containing seven exact source files and three generated
artifacts. Its existing `as_files`,
`plan_deployment`, rollback manifest and `verify_deployment_readback` consumers cover
all ten. Removing or modifying any member makes exact readback fail.

This is a complete **extension plus generated configuration** bundle, not a copy
of every Python runtime dependency. The existing wrapper still references the
admitted immutable repository root; #340 must verify that root and all other
installation, profile, owner, permission, fault and rollback gates independently.
No package staging receipt is installation or provider proof.

## Closed additive API

```python
bundle = render_census_extension_bundle(
    admitted_binding,
    admitted_release,
    source_files=exact_git_source_bytes,
    expected_source_digests=independently_admitted_sha256,
)
plan = plan_deployment(bundle, observed_preimages)
# Only the separately authorized installer may apply this plan.
receipt = verify_deployment_readback(bundle, observed_postimages)
```

The fixed members are `manifest.json`, `background.js`, `content.js`, `census.html`,
`census.css`, `census_core.js`, and `census.js`. Generated `instance_config.js` cannot
be supplied or overwritten through the source map. Extra/missing/path-like names,
mutable/non-byte/empty content, files over 256 KiB, totals over 1 MiB, incomplete or
malformed digest maps, and any digest mismatch produce fixed payload-free errors.

The manifest gate admits only the CENSUS1 MV3 layout, exact native permission and
host lists, fixed background/content/popup references, matching package version,
and the public-key-derived extension origin already owned by the native adapter.
Duplicate JSON members and malformed manifests fail closed. Future legitimate
layout changes require explicit reviewed evolution, not permissive inference.

Expected hashes are integrity inputs, not authorization. Supplying matching hashes
does not authenticate a Git commit, prove source protection, inspect JavaScript
semantics, attest HTML dependencies, authorize installation, or prove live behavior.
The caller must establish source provenance and independent source review before use.
No native wire schema, capability digest, package-version fence or protocol changes.

## Public receipt boundary

The complete bundle preserves source commit, instance, native-host and profile-derived
identity internally because exact binding, artifact destinations, bundle digest,
deployment planning, readback and rollback depend on them. Both public serialization
routes have complete-bundle-only projections:

- `bundle.public_receipt` contains exactly `schema`, `package_version`,
  `protocol_major`, `capability_digest`, `bundle_digest`, and `artifact_digests`.
- `verify_deployment_readback(bundle, current_files)` contains exactly `schema`,
  `ok`, `bundle_digest`, and `artifact_digests` after exact byte verification.

Both projections omit `source_commit`, `instance_id`, `native_host_name` and raw
profile identity while retaining all ten artifact digests. The legacy generated-only
`DeploymentBundle.public_receipt` and five-key readback receipt retain their original
identity-bearing byte/order/behavior contracts. These repairs do not relabel the
readback consumer, silently change legacy consumers, or add another receipt schema or
store.

## Proof and release sequence

1. The unchanged generated-only deployment suite passed before implementation.
2. Commit `690e351f15c42e72048f3df8313340941f005f95` contains the RED tests:
   the complete renderer was absent, and behavior assertions failed as expected.
3. Run `python3 -m pytest -q tests/test_web_sol_extension_bundle.py
   tests/test_web_sol_deployment.py` and the full `tests/test_web_sol*.py` family.
4. Mutation checks must discriminate omitted assets, ignored hashes, incorrect
   digest/modes, relaxed version/permission/origin fences, duplicate JSON and size.
5. Stage actual source assets from immutable #502/current-base Git objects in an
   owned scratch directory. Bind every source blob and SHA-256, use the real bundle
   consumer, read back all files, and simulate create/update/rollback planning.
   The pre-merge renderer and extension pins remain distinct in that receipt.
6. Publish exactly three scoped paths on the child branch in a Draft/HOLD PR;
   obtain independent exact-head review and then separate source release.
7. Only after source protection and existing resource/admission gates clear may
   #340 consume the complete renderer for its real installed proof and rollback.

The package renderer performs no filesystem, process, network, browser, credential,
account, clock, native-message or lifecycle effect. Scratch staging by a test is
explicitly outside the pure function. It is not an alternative privileged installer.
No #502 source path, #340 live target, #480 mode experiment, or #364 capacity owner
is changed. No new workstream, registry, scheduler, memory or retry owner is created.

## Reference evidence

Chrome's manifest key controls extension identity; Chromium derives that ID from
SHA-256 of the decoded public key. These are source-format facts, not a claim about
an installed browser or provider session. Primary references checked 2026-09-06:

- https://developer.chrome.com/docs/extensions/reference/manifest/key
- https://chromium.googlesource.com/chromium/src/+/master/components/crx_file/id_util.h

The existing #340 carrier must retain independent preimage, ownership, native
runtime source-root, installation, fault, resource-release and rollback evidence.
A full extension byte readback alone does not discharge those obligations.

## Executed source evidence, 2026-09-06

- Legacy baseline: 12 deployment tests passed before new source.
- Initial missing-capability tests failed before production implementation; RED
  commit is recorded above. Final focused cases include 71 new packaging tests.
- Final full Web-Sol family: 319 passed, zero failures or skips, across 18 Python
  test modules. This is not the entire repository CI suite.
- Nine in-process isolated-module mutants were caught by existing assertions;
  each original control passed first. A prior subprocess mutation attempt timed
  out at 45 seconds and restored source; it is not counted as a mutant kill.
- The complete legacy deployment source remains an identical byte prefix;
  compile and working-diff whitespace checks passed.
- Actual extension assets from current-base candidate
  `c2ae335e4728bbeb8da742a8d5bf1e33fd4c52d1`, tree
  `1bcb15101cdd947e84a84994928340fe1d29a7ba`, were Git-blob-verified and staged
  through the new renderer in owned scratch directories for two synthetic profile
  bindings. All ten artifacts per binding passed byte and mode readback; altered
  staged CSS was refused, restored and verified. HTML dependencies were complete.
- Renderer SHA-256: `bbd76ad5a8b56683888440443070dbac348e0652c3fe06ab9e7cdeb3e12ed616`.
- Mutation receipt SHA-256: `798e9eb927aac70f04f030f347bdce1287a76d4a8b465b718348e623ddf114db`.
- Staging receipt SHA-256: `582baaeb5b3a66116b41a111381f9009aae13692e90e22e507ee974ff9747216`.

The initial staging attempt stopped before writes because that immutable Git
object was absent locally; its remote identity was verified and the exact object
fetched before the successful test. The tested renderer and extension source pins
are distinct and explicit. No native wrapper ran, no browser launched, and no real
profile, account, installation or provider behavior was exercised by this child.
Independent review, hosted CI, source release and #340 installation remain separate.

## Independent-review repair evidence, 2026-09-06

Independent exact-head review `5126187281` requested changes because the complete
renderer returned `dataclasses.replace(generated, ...)` and therefore inherited the
legacy public receipt, exposing `source_commit`, `instance_id` and
`native_host_name`. The review explicitly required a complete-bundle-only payload-free
projection while preserving the generated-only contract.

TDD repair on the incumbent branch and carrier:

- RED: `test_complete_bundle_public_receipt_exposes_integrity_not_source_or_profile_identity`
  failed on the three extra identity keys. Log SHA-256:
  `99cb9aa3894dd8b3d8c5af152f1afdb3e70420aff382207d7e95300fe6883ed3`.
- GREEN control: the new complete-bundle projection test and unchanged legacy public
  receipt test both passed. Log SHA-256:
  `7d8791a9bb72e65283b3c0e607dd407e50bce3050f811bc7cf9b37f38c330fda`.
- Focused deployment/complete-bundle suite: **84 passed**.
- Full applicable Web-Sol Python family: **320 passed** with a short isolated
  pytest base directory; compile and `git diff --check` passed.
- The #502 Node census fixture is not present on this pre-#502 source branch, so a
  direct Node invocation was inapplicable rather than a test failure. Current-base
  integration after #502 protection must run that fixture separately.

The production change is limited to a private complete-bundle subtype and construction
of that subtype in `render_census_extension_bundle`. Bundle/source/profile identity
still changes the internal `bundle_digest`; all ten artifact digests remain externally
committed. No browser, profile, installer, native wrapper, provider or runtime effect
occurred in this repair.

## Second independent-review repair evidence, 2026-09-06

Independent exact-head review `5126402205` requested changes at
`c2e9f8162f880468aa1b05148a0d22a0ba43f074`: the direct complete-bundle projection
was identity-free, but the documented-public `verify_deployment_readback` consumer
still emitted the derived `instance_id`. Root admitted one local-only correction on
the original source carrier; remote push remained explicitly ungranted.

TDD and local evidence for the second correction:

- RED: `test_complete_bundle_readback_receipt_exposes_integrity_not_identity`
  failed because the readback receipt contained `instance_id`; the exact legacy
  generated-bundle readback control passed. RED log SHA-256:
  `971e99520d3334cd879896bf6ab867963f30e1f718aeb91ee66858c814453919`.
- GREEN: the same two discriminators passed after the minimum subtype-only projection
  change. GREEN log SHA-256:
  `99db33d5c94c6f7da021687c7391181685cc33299c5435b1c861e2db3be3ec87`.
- Focused deployment/complete-bundle suite: **86 collected and passed**; log SHA-256
  `b7dee23c5b0bdea31c1d8ae048f013874efa279f477dccaba3f25c872d457efb`.
- Full applicable Web-Sol Python family: **322 collected and passed** using the fresh
  short pytest base `/tmp/r5`; log SHA-256
  `bfe89c27e132745f82f4f85848e64c38c3d77cebbbad4fa3c4b3e5b33a829428`.
- The first full-family attempt used a longer owned temporary root and produced five
  `socket_path_too_long` failures in unrelated AF_UNIX transport tests. Every failure
  had that exact class; the result is preserved as an environmental qualification,
  not counted as passing evidence. Log SHA-256:
  `2893afb3c6bce211cfc44a214e7cfd7fe17836afe9c98d5210db0851ecea93f8`.
- Python compilation and `git diff --check` passed. The empty diff-check log SHA-256 is
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

The implementation changes only the existing readback function's projection for the
private complete-bundle subtype. Exact readback mismatch refusal executes before the
projection; all ten artifact commitments and private identity-sensitive bundle,
destination, plan and rollback behavior remain unchanged. The ordinary generated-only
bundle still returns its original ordered five keys, including `instance_id`.
No source push, PR metadata, hosted CI, review, browser, profile, native wrapper,
provider, installation, RuntimeBinding or production effect is part of this local
repair evidence.
