# GLM account quota admission repair

An actual paid Fabric task on Ubuntu1 returned HTTP429 Weekly/Monthly Limit Exhausted while two other GLM accounts retained weekly capacity. The global GLM meter selected the provider, but the existing lease broker did not intersect its candidate accounts with per-account quota data. Its account capacity and host credential readiness checks could therefore admit an exhausted account.

This correction adds `cached_glm_account_parked` to the incumbent quota reader and intersects the existing `Broker.account_cap` decision with it. It reads only the existing quota cache and narrows admission for fresh authoritative observations at the incumbent 95 percent park threshold. Stale, malformed, future, unknown and reset-expired observations preserve the prior decision. Explicit account requests still refuse instead of silently changing identity. Network calls, credentials, quota refresh, source policy, root budgets, active leases and worker lifecycle remain with their existing owners.

The original failed task `fabric-ci-read-contract-tests-01a11e90-v1` returned 836 bytes, SHA256 `f093973d104ca97e1e46b57581ca1ae8ba06003f5d87b6772c110e687e8e1147`, and remains NOT_ACCEPTED. No replay or mid-run transfer is supplied. This admission correction applies to future admitted requests. Generic terminal-error classification remains narrower than an account-bound quota settlement receipt.

## Reproduce without production effects

The adjacent source files are frozen candidates and baselines, not another installed dispatcher. The tests use temporary quota files and SQLite, forbid provider/credential/cache-refresh calls, and do not import installed source.

```sh
python3 -m pytest -q research/fabric_glm_account_admission_20261014/test_account_quota.py
BROKER_SOURCE=baseline.lease_broker.py python3 -m pytest -q research/fabric_glm_account_admission_20261014/test_account_quota.py
```

Candidate:24 PASS. Old broker:3 FAIL,21 PASS (exhausted candidate exclusion, spare-account selection and explicit exhausted-account refusal). Another51 existing quota/broker/account checks passed against the candidates; retained XML and hashes identify those checks. The normal affected production installation requires exact-preimage verification and review. This package does not install itself, change a live lease, clear a refusal, or establish authenticated native RuntimeBinding/Wake.

## Local adoption

SourceOS independently approved the exact candidates in SOURCE_REVIEW.json. The existing Fabric owner installed the helper before its broker consumer at2026-10-14T17:30:47Z with exact-preimage comparison, backups, file and directory synchronization, unchanged owner/mode and postimage readback. Four fresh installed-module checks passed against an isolated retained-quota fixture. INSTALL_RECEIPT.json and INSTALLED_FRESH_LOAD.json bind the bytes. This is local adoption, not protected branch landing, a real new worker result or authenticated native Runtime acceptance. The old failed run is unchanged.
