# APMEM/options shadow research

Original research implementation, not a clone of the creator's private signal generator. **No live trading, sizing, ranking, alert, or production Prophet integration is enabled.** The completed primary experiment does not qualify the original QQQ directional candidate for promotion. See [RESULTS.md](RESULTS.md).

## What is implemented

`model.py` implements a positive asymmetric powered variance recurrence, training-only scaled QML fitting, and rolling chronological forecasts. `evaluation.py` provides fixed volatility/options/price ablations, common input eligibility, next-open long/cash execution, realistic delay/cost variants, and stronger variance-forecast controls. `consumer.py` rejects missing, stale, future, mismatched and unknown-clock inputs and never grants market-action authority. `creator_replay.py` audits the creator's published states using independently sourced opening prices; it cannot reconstruct his generator. `diagnostics.py` exports derived results and labels its block-bootstrap intervals as post-evaluation, pointwise diagnostics.

All work is offline against explicitly supplied input snapshots. No service, collector, scheduler, extra memory store, provider connection, secret or production setting is created.

## Run from a source checkout

The research directory is intentionally not part of the installed production package. From repository root, install the existing `dev` or `apmem-research` extra in an isolated environment, then run:

```sh
python -m unittest discover -s tests -p 'test_apmem*.py' -v
python -m research.apmem_shadow --prices /approved/QQQ_raw.parquet --options /approved/QQQ_gex.parquet --instrument QQQ --output /new/research-run
```

Inputs may be Parquet or CSV with a `date` index/column. Prices require positive, consistent raw `open,high,low,close` values on unique increasing economic session dates. Options require `net_gex_bn,iv30` aligned by economic session. IV is annualized decimal, not percent. The caller binds the instrument to its approved source; this CLI does not authenticate a ticker or data-vendor entitlement from a filename. Corporate-action and source-clock provenance remain the caller's responsibility. Do not pass adjusted opens as executable raw fills.

Output paths must be new. Reads are bounded to 32 MiB/file. The source manifest hashes the exact bytes parsed, source code and outputs, with actual capture/runtime dates. Missing publication and bar clocks remain unknown. The supplied historical archives therefore produce an honest `ABSTAIN` consumer result, not fabricated retrospective availability.

After running the fixed QQQ, SPY and IWM inputs into `results_QQQ`, `results_SPY`, and `results_IWM` below one research root, the optional export command is:

```sh
python -m research.apmem_shadow.diagnostics /research/root /new/derived-export
```

That export also expects the acquisition/source receipts and the separately produced creator-output replay under that root. It is tailored to this documented investigation, not a generic data downloader. No raw vendor records belong in this public repository.

## Qualification and limits

[PROTOCOL.md](PROTOCOL.md) and [PROTOCOL_ADDENDUM.md](PROTOCOL_ADDENDUM.md) were committed before this experiment's first actual-data fit. The original screenshot and past market history were already known: these are retrospective chronological tests, not prospective validation or an untouched strategy-selection holdout. The two correction parameters, all five directional ablations, both fill delays and both costs are retained; no winner is silently substituted.

The three price panels run 2010-01-04 through 2026-11-12. Reconstructed options begin in 2017 and end 2026-11-05. The shared directional comparison starts 2017-02-02. Results exclude distributions, tax and financing and use open-mark, not intraday, drawdown. The actual empirical runtime used NumPy 2.4.6, pandas 3.0.3, SciPy 1.18.0 and PyArrow 24.0.0; the separate principal/test environment used SciPy 1.17.0. Exact source hashes agree; numerical reproducibility across different package versions is not asserted.

No research performance automatically enables ranking, sizing, trading, live alerts or production integration. Any future version must retain provenance, declare changed rules, and obtain a genuinely new evaluation rather than recycle this inspected history as a holdout.
