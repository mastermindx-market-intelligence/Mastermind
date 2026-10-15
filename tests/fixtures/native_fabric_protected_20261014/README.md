# Complete source fixtures for protected broker composition

These are unchanged Git blobs from existing source owners. They are test inputs,
never installable broker/module replacements and never current host observations.

Protected owner: Mastermind #1391, merge `e1cacf9eb310cbdf25a3a22defedb7b086c6c179`.

| Local test input | Original repository path | Git blob |
|---|---|---|
| lease_broker.py.txt | integrations/session_bridge/native_broker_admission/fixtures/lease_broker.base.py | 855495a15615787c3c80f9045e6637839ee47384 |
| native_broker_admission.py.txt | integrations/session_bridge/native_broker_admission/native_broker_admission.py | 15f2e97095d1fc3dafd968576f57505f2b0fb22b |
| native_admission.patch | integrations/session_bridge/native_broker_admission/lease_broker.py.patch | 62eb6da5e556e0de9a5e222be9cf5d4806c681aa |

Neighboring source candidate #1365 at `4c27a8d3a4dab635b5301e3f8fda84576b711b9f`:
`glm_expiry.patch` is unchanged blob `41bcc1a26871def1b1f8ec7994178c897b9608c2` from
`ops/native_fabric/patches/lease_broker_glm_expiry_preference_20261013.patch`.
It is not a protected or installed expiry release; preserve that owner's review.

The test verifies all four SHA256s, applies the accepted native patch and checks
its known postimage before adding routing candidates. The native helper remains
byte-identical. Only temporary SQLite and synthetic account configuration are
used. No live host, provider, credential, quota or native lease is contacted.

The original native fixture/preparation and host-inspection holds are unchanged.
This complete-source composition is a new repository integration check, not a
retry of those denied actions or a relabeling of the original 49-pass/one-failure
suite. Host/current-source, external broker override and launcher installation
compatibility remain separate proof obligations.
