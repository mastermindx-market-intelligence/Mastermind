# Research package verification and reproducibility

Date: **2026-10-04**. This is evidence for the [research package](README.md), not qualification of a production gauntlet or a claim that repository-wide tests passed.

## 1. Core document verification actually performed

An independent read-side script fetched the seven newly authored research blobs from GitHub's Git API and checked their bytes without executing repository code or reading market datasets. It completed with exit code **0** and the following results:

- Exact seven-file core allowlist matched; every entry was a regular UTF-8 text blob.
- Each blob's Git object SHA-1 was recomputed from its bytes and matched the returned immutable identity.
- The masterplan contained every top-level required section **A through L**, once and in order.
- **86 relative Markdown file/anchor links** were checked; **zero broken internal links** were found.
- No session-local `filecite`/search/view citation tokens were present in the Markdown files.
- Synthetic receipt JSON parsed, contained exactly three counterexamples, explicitly denied market-data/holdout/production effects, and matched the original receipt's SHA-256.

Verified core repository tree: `fc9f642e450a71ffd30ac43e50bb3e4615d7cf70`. Core package subtree: `d822b5039f5bd8ecb747a079c2f45c75e6500a9a`. This verification addendum is intentionally outside its own core hash manifest, avoiding a self-referential checksum. Final publication adds this eighth file; its Git object identity and the research-only commit diff are checked separately at publication.

| Core artifact | Bytes | SHA-256 |
|---|---:|---|
| `AUDIT_AND_RECENSUS.md` | 23,096 | `b266f47cc67cf99ec97a3a1e852138a13da235d8f76bade23eaeb015695049a7` |
| `IMPLEMENTATION_COMMISSION_P0A.md` | 16,611 | `9c5a30f6a2fd819161916628e9530c89ca51a59f7ad5c7e945d38da42e28b2e3` |
| `MASTERPLAN.md` | 50,439 | `f81f72a1480de42b3f8631904999d456f3d6966c667c249af94ad5118485776d` |
| `README.md` | 7,448 | `a064e1a7b2be36ff1bd9c13be22121835aafa3e6b4fe92750e33f70fbff5f66c` |
| `SOURCE_REGISTER.md` | 19,549 | `9bc5cb5a7fcad4572410a3a31d7d8ccdc53050291b0bfa3f264b1da98567f7d6` |
| `SYNTHETIC_AUDIT_RECEIPT.json` | 2,164 | `78683607d648fe4511c2dcb1976e550958419af2329e86da048a6dde3817e8bc` |
| `VALIDATION_PROTOCOL.md` | 35,615 | `124c1eb9be256bce0110f2c21f8d64be9cc361c541cf9850d580a05cce71d414` |

These structural checks do not prove every scientific judgment or external URL's future availability. Primary source verification and reasoning are separately documented in the [source register](SOURCE_REGISTER.md).

## 2. Fresh synthetic rerun

All three original expression-level counterexamples were rerun in the conversation sandbox and reproduced the recorded values. This was not a production module import, market backtest, repository test suite, or repair.

The first verification attempt omitted the source's initial `ret = close.pct_change().fillna(0)` setup and failed the numeric comparison for the appended-price case. The exact source was reread, that omitted setup was restored in the verification harness, and all recorded values reproduced. **No expected result, source implementation, or original receipt was changed.** The setup is made explicit below so the receipt is reproducible without relying on an implicit preprocessing convention.

| Case | Reproduced result | Interpretation |
|---|---|---|
| SYN-01 | Early sigma `0.011489841990803452` becomes `0.44432536067754225` after a future suffix | Full-sample warm-up median violates prefix invariance |
| SYN-02 | Source standalone drawdown `0.0`; initial-capital-inclusive result `-0.19999999999999996` | Initial wealth is absent from the source expression's running peak |
| SYN-03 | Duplicate-column pseudo-inverse diagonal approximately `0.25, 0.25` | Not conventional VIF under perfect collinearity |

### Reproduction from the receipt

Run only in an isolated research environment with NumPy and pandas. The script reads the synthetic JSON in this directory; it does not access repository data, source stores, trading state, networks or holdouts.

```python
import json
from pathlib import Path
import numpy as np
import pandas as pd

receipt = json.loads(Path('SYNTHETIC_AUDIT_RECEIPT.json').read_text())
a, b, c = receipt['results']

def source_sigma(prices):
    # Preserve the actual source setup, including the first return's zero fill.
    ret = pd.Series(prices).pct_change().fillna(0)
    sigma = ret.rolling(a['vol_window']).std()
    return sigma.fillna(sigma.median()).fillna(0.0)

before = source_sigma(a['prefix_prices']).iloc[1]
after = source_sigma(a['prefix_prices'] + a['appended_prices']).iloc[1]
assert np.isclose(before, a['prefix_sigma_at_index_1'])
assert np.isclose(after, a['extended_sigma_at_same_index_1'])
assert not np.isclose(before, after)

eq = np.cumprod(1 + np.asarray(b['returns'], dtype=float))
source_mdd = np.min(eq / np.maximum.accumulate(eq) - 1)
with_initial_capital = np.r_[1.0, eq]
full_mdd = np.min(with_initial_capital /
                  np.maximum.accumulate(with_initial_capital) - 1)
assert np.isclose(source_mdd, b['source_result'])
assert np.isclose(full_mdd, b['initial_capital_inclusive_result'])

z = np.arange(c['rows'], dtype=float)
correlation = np.corrcoef(np.c_[z, z], rowvar=False)
diagonal = np.diag(np.linalg.pinv(correlation))
assert np.allclose(diagonal, c['source_result'])
print('PASS: three synthetic counterexamples reproduced; no source repair')
```

## 3. Scope and remaining proof

The eight-file delivery contains only research Markdown and synthetic/verification evidence. Publication verification checks its commit diff against the recorded publication base. No merge, installation, production release, live source promotion, portfolio mutation, procurement or empirical market-value claim is part of this delivery.

Future P0A tests in the handoff are **requirements**, not tests reported as run. Existing RC/SPA research comments and Trend C1's prior results remain source-reported evidence, not reproduced market results from this audit. Actual runtime/data/rights/Snapshot qualification and future prospective evidence remain the explicit gates for later owners.
