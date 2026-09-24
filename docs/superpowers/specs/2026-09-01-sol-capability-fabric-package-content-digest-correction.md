# Sol Capability Fabric — Package Content Digest Correction

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Operation:** `mastermind-sol-capability-fabric-package-generation-f0-20260901-sol-001`  
**Carrier:** `sol/scf-package-generation-f0-20260901`  
**Protected source basis:** `187490f3d5676adf7a249d69afacedd00b3efcec`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / DIGEST CORRECTION`

This correction supplements and, for the package-content digest only, supersedes:

`docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md`

## Finding

The original specification listed package-content digest:

```text
a82a274a82ed84c6e82a1c34b67c1f2f0a70cc465c26d0fcf64f648ac295cf16
```

That value does not equal the specification's declared canonical projection over the exact seven
ordered file rows.

The declared projection is:

```json
{
  "schema_version": "mastermind.capability_package_content/v1",
  "files": [
    {
      "relative_path": "<package-relative POSIX path>",
      "sha256": "<64-lower-hex>",
      "byte_length": 1,
      "executable": false
    }
  ]
}
```

encoded as:

```python
json.dumps(
    projection,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

Using the exact protected seven-file inventory and lexical row order, the correct SHA-256 is:

```text
a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306
```

## Unchanged facts

The exact file paths, byte lengths, per-file SHA-256 values, executable flags, repository, source
commit, package tree, package root and generation are unchanged.

The four effective Skill closure digests are also unchanged because they were already calculated
with the declared `mastermind.effective_skill_closure/v1` projection:

```text
escalate-decision  ca621a8cc034bf607460d81085c8d466000e38d0f4b6afa8245001374d6cc2ad
finish-operation   3e689aeaa2b1579781832a854d7256c6ad8ee2ef55521b45f3af8dbe9660675e
receive-commission d7953504035c797b30f434f1fdc72e864a7074179abffe7c247f1afc9c0a162c
return-progress    510be1ed3036f0bc1ed5f709875792ca042c350198a48e1128b4ce8ae46a6552
```

## Implementation law

SCF-PKG1 implementation and fixtures must use the corrected package-content digest
`a9781411...a71306` and must recompute it from the real protected files during tests. They must not
accept either value merely because it appears in a document.

This correction changes no package byte, registry policy, profile, route, host receipt, provider
configuration or production state.
