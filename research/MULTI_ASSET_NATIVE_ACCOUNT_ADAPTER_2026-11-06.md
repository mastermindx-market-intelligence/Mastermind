# Multi-asset scenario context: native-account integration increment

Parent: Grey Deer / MAS-258; Macro #10795; Terminal #1323. This continues the Chairman's global protection, destination-context and re-entry implementation. It extends merged Mastermind #2124 (02820a29852d6554f0f595c23cfce04b2032e69a); its merged branch is not reused.

Operation: `multiasset-book-context-20261106-sol`, source base/procedure pin `32a354c3dd77751e206a80b2abc4e497efdbe5e6`, compatible Skillpack 1.0.1/bootstrap 1. The initially unqualified workspace-acquisition return was reconciled by the same operation's installed owner status and publisher: correct branch, exact base, clean/recoverable. No allocation replay or carrier substitution occurred.

## Capability delivered at source

`portfolio.global_scenario_account.compare_account` consumes a caller-supplied, explicitly receipted **native paper-account state**, uses the existing `portfolio.paper_account.valuation(..., state=...)`, then feeds weights into the existing `portfolio.global_scenario_context.compare`. A caller can compare its specified hold, cash, partial-rotation or staged-return what-ifs without replacing the account/NAV, identity policy or scenario owner.

The adapter never calls account load/create/save/mark/rebalance paths. It has no API endpoint, scheduler, collector, quote fetch, portfolio store, order or notification writer. Existing instrument classification reads its original local metadata; current classification is not historical point-in-time identity evidence. No live account or customer session was accessed in this implementation.

## Exact boundaries

- Exact registry identity and active single-name-equity policy are required. Unknown IDs never fall back to another book. Current supported managed books are autonomous/USD, china/CNY and hk/HKD **separately**. Unsupported/self-directed/archived mandates are reported unavailable, not silently expanded.
- The supplied snapshot binds book ID, canonical account-content SHA-256, source revision, valuation session, known-at and valid-until. Mandate binds the same book/currency, revision, validity and explicit concentration/turnover/cash limits. These fields are caller declarations, not authentication: the eventual existing account service must establish their origin and caller access before invocation.
- Native account validation and explicit nonnegative shares/cash prevent missing or leveraged positions from becoming an ordinary fully funded book. Actual held shares and actual explicit cash produce weights; target-book `latest.json`, missing-row subtraction, average cost and static FX are not substitutes.
- Every held input price requires finite positive value, matching source price, same book currency/session, source/revision, unadjusted-close basis, explicit close qualification and valid source clocks. Native carried/unattested/unpriced valuation results are rejected rather than upgraded to qualified NAV.
- Each instrument is classified through the existing native identity owner. A descriptor saying QUALIFIED cannot approve an ETF or unknown security. Risk groupings require an explicit source reference but remain caller-supplied attribution, not independently authenticated issuer look-through or statistical independence.
- Different-currency instruments are unavailable in this adapter; no approximate CNY/HKD FX fallback is used. Global currency and cross-book optimization remain a later separately evidenced consumer.
- Every scenario has a matching explicit future period beginning at the request's as-of instant. Cash return, scenario returns and one-way fee/spread-crossing/impact costs are explicit assumptions. There are no probabilities, expected-return forecasts, chosen weights, recommendations or automatic actions.
- Correction of account, price evidence, mandate, identity or grouping changes the resulting book identity. Input mutation is prohibited. The outward result does not expose raw shares, account bytes or prices; it retains the existing hypothetical comparison and relevant coverage/basis.

## All-cash defect reproduced and fixed

The merged generic core rejected an explicitly empty instrument universe, preventing comparison of a valid all-cash account. The new native test failed first. Its small correction distinguishes `universe is None` (missing/malformed) from an explicit empty universe. Existing weight checks still reject nonzero positions without metadata. An all-cash book can now compare explicit cash assumptions with zero turnover without inventing a fund, ticker or FX quote.

## Executed verification

- New adapter suite: **45 passed**, command `python3 -m pytest -q -o addopts='' tests/test_global_scenario_account.py --disable-warnings`, exit 0, 1.48 seconds.
- Prior combined regression invocation after the all-cash fix passed all six selected modules with exit 0: new adapter, existing global scenario core, paper-account NAV qualification, registry security, firm shadow allocator and historical shadow books. Five extra adapter cases were then added and passed in the 45-case final adapter run. Final collection across the six files contains 198 tests; this collection count is not represented as one new execution receipt.
- `python3 -m py_compile portfolio/global_scenario_account.py portfolio/global_scenario_context.py` and `git diff --check` passed.
- Tests wrap the **real** native valuation function and assert it receives an explicit copied account. Load/create/save/mark/rebalance paths raise if called. Positive instrument metadata in the fixtures is synthetic; the ETF-negative case runs the actual native ETF classifier. All account values are synthetic and no market/backtest efficacy is claimed.
- Source-proximate PR smoke and full protected merge-group CI remain owned by the unchanged existing workflow. No test selection, guard, branch rule, routing permission or data source was changed.

## Remaining acceptance

Reviewable source, not a deployed portfolio feature. A real account service must supply authenticated snapshot/mandate/price provenance and maintain tenant isolation; a real authorized account-to-consumer/UI path, runtime install and prospective net-utility comparison are still owed. The currently legal managed-book asset universe is not broadened by this function. Cross-asset mandates, foreign-currency conversion, validated forecasting, options/flow pressure, re-entry qualification and any capital-policy activation remain distinct work under the original mission.
