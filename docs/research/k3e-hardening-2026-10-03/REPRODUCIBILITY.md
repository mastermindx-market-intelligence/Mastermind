# Independent frozen-source audit — reproducibility and limits

This audit executed an independently authored, outcome-blind inspection script on two exact-revision SRC-A1 parquet files. It did not run a collector, request fresh provider data, inspect prices/financial outcomes, fit a model, or rerun the complete #8312 candidate test suite.

## Frozen inputs

Repository: `mastermindx-market-intelligence/macro`.
Commit: `ff420e6841a2468e4b718340cff240abbef114f1`.

| Native path | Bytes | SHA-256 |
|---|---:|---|
| `data/revisions/expectation_observations.parquet` | 37,020,102 | `3db55f485c01bd307f1419ff04f392ae5f1994d2e7d8071b977abe9bbb562b93` |
| `data/revisions/expectation_attempts.parquet` | 1,169,700 | `05507a186772eb0de0cfcc2e21714091dca4247cbf0957aaf0c51a3324db691e` |

Use the existing source owner's permitted access path to obtain these exact files. Save them in an isolated analysis directory as `observations.parquet` and `attempts.parquet`. Do not edit or overwrite canonical source files. Verify the hashes before interpreting results. Do not request new provider collections or alter cadence to reproduce this snapshot check.

## Reproduction

Save the code below as `independent_snapshot_audit.py` beside the two input files. It requires Python, pandas and pyarrow; those dependencies were already present in the audit environment. No dependency installation was performed. Use an existing approved environment rather than changing the production dependency set. The executed environment used Python 3.14; exact pandas/pyarrow package versions were not separately captured, so byte-for-byte environment reproducibility is not claimed.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 independent_snapshot_audit.py
```

The script prints an initial inspection and then a `FINAL_EXTENDED_RECEIPT`; the saved `INDEPENDENT_SNAPSHOT_CHECKS.json` contains the final extended result. The checked-in JSON is copied from the actual successful execution, not regenerated from narrative estimates. The inspection reports observations rather than asserting that every possible source invariant passes.

### Exact inspection script executed

```python
"""Outcome-blind independent SRC-A1 snapshot checks. No source mutation or provider request."""
from pathlib import Path
import json, hashlib
import pandas as pd
import pyarrow.parquet as pq
import pyarrow.compute as pc
root = Path(__file__).parent
obs_path, att_path = root / 'observations.parquet', root / 'attempts.parquet'
t, a = pq.read_table(obs_path), pq.read_table(att_path)
d, ad = t.to_pandas(types_mapper=pd.ArrowDtype), a.to_pandas(types_mapper=pd.ArrowDtype)
result = {'scope': 'outcome_blind_frozen_snapshot_not_release_acceptance', 'input_commit': 'ff420e6841a2468e4b718340cff240abbef114f1'}
result['inputs'] = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (obs_path, att_path)}
result['observations'] = len(d)
result['attempts'] = len(ad)
result['observation_columns'] = len(d.columns)
result['attempt_columns'] = len(ad.columns)
result['unique_observation_ids'] = d.observation_id.nunique()
result['unique_attempt_ids'] = ad.attempt_id.nunique()
result['ticker_symbols'] = d.ticker_compat.nunique()
result['observation_sessions'] = d.collection_session_id.nunique()
result['attempt_sessions'] = ad.collection_session_id.nunique()
result['finite_values'] = pc.sum(pc.fill_null(pc.is_finite(t['value']), False)).as_py()
result['true_null_values'] = t['value'].null_count
result['ieee_nan_values'] = pc.sum(pc.fill_null(pc.is_nan(t['value']), False)).as_py()
result['null_counts'] = {c: t[c].null_count for c in ('issuer_ref','security_ref','unit','currency','basis','source_effective_at','source_published_at','period_end')}
result['rights_counts'] = {str(k): int(v) for k,v in d.rights_class.value_counts(dropna=False).items()}
result['correction_counts'] = {str(k): int(v) for k,v in d.correction_state.value_counts(dropna=False).items()}
result['observation_types'] = {str(k): int(v) for k,v in d.observation_type.value_counts(dropna=False).items()}
result['system_clock_range'] = {'min': d.system_observed_at.min(), 'max': d.system_observed_at.max()}
result['missing_attempt_links'] = int((~d.attempt_id.isin(ad.attempt_id)).sum())
counts = d.groupby('attempt_id').size()
result['attempt_count_mismatches'] = int((ad.set_index('attempt_id').observation_count != counts.reindex(ad.attempt_id).fillna(0)).sum())
prior = d.set_index('observation_id')
sup = d[d.supersedes_observation_id.notna()]
result['supersedes_links'] = len(sup)
result['orphan_supersedes_links'] = int((~sup.supersedes_observation_id.isin(d.observation_id)).sum())
result['witness_checks'] = {}
witnesses = {
 'UVV_unchanged': ('c5c2253a5769bd7fb2dd268c8e290f0c72bc87ee2b3cce9d80e2fd794cb61dee','45d1afc59ef4e656020bc25f4ae443469a4a0c113af77e163c47db0fed7e481a','unchanged'),
 'V_supersedes': ('690d52abb866840f961aeafb0ee74703f27854bb14e865c42620e71bfe859f6e','9ab91c4676e7a0f3c7f4edea54d71c0e4067260670936c6f00b704acaf44fd0f','supersedes'),
 'KBH_rollover': ('75a1f0b16a9f133e001a51e7bc6b73ec77bb5d6f561ce87a1a431f144a3e789d','81070408146974ab4003c09fcc08a862ecccb2c87059fd3a54843b5a8a2054ba','original'),
 'JBGS_partial': ('e60711b5a87398e76a813bf8578ed0eb86815ddd6766f93f17018d243380875b','0cb2901aa2bd4c2b4252fa7ce4f567bf6b09520423929e1aeb12f7500c5ee135','missing'),
}
for label, (old_id,new_id,expected) in witnesses.items():
 old,new=prior.loc[old_id],prior.loc[new_id]
 row={'both_retained': True, 'later_system_clock': bool(new.system_observed_at > old.system_observed_at), 'new_correction_state': str(new.correction_state), 'expected_correction_state': expected, 'supersedes_exact_prior': False if pd.isna(new.supersedes_observation_id) else bool(new.supersedes_observation_id == old_id), 'new_value_missing': bool(pd.isna(new.value)), 'same_anchor': None if pd.isna(old.period_end) or pd.isna(new.period_end) else bool(old.period_end == new.period_end)}
 result['witness_checks'][label]=row
result['limitations']=['No source/publication-clock or rights attestation','No independent event sample or predictive outcome evaluated','Snapshot retention is not historical cross-commit immutability proof','Full scheduled producer/CI receipts were reviewed as source documents, not independently rerun','No identity or economic-basis inference']
text=json.dumps(result,indent=2,sort_keys=True,default=lambda x: int(x) if hasattr(x,'item') else str(x))+'\n'
(root/'INDEPENDENT_SNAPSHOT_CHECKS.json').write_text(text)
print(text)
# Additional checks distinguish populated estimates from reserved null slots.
result['finite_by_observation_type'] = {str(kind): int(frame.value.notna().sum()) for kind,frame in d.groupby('observation_type')}
keys = ['attempt_id','metric','horizon_label_raw']
coverage = d[d.observation_type == 'covering_analyst_count'][keys+['value']].rename(columns={'value':'coverage_value'})
joined = d.merge(coverage,on=keys,how='left',validate='many_to_one')
defect = (joined.observation_type != 'covering_analyst_count') & joined.value.notna() & (joined.coverage_value.isna() | (joined.coverage_value <= 0))
result['present_measurements_without_positive_coverage'] = int(defect.sum())
result['defect_capture_dates'] = {str(k): int(v) for k,v in joined.loc[defect,'system_observed_at'].str.slice(0,10).value_counts().items()}
result['finite_less_empty_coverage_defects'] = int(result['finite_values'] - defect.sum())
for label,(old_id,new_id,expected) in witnesses.items():
 old,new=prior.loc[old_id],prior.loc[new_id]
 result['witness_checks'][label]['same_nonmissing_value'] = None if pd.isna(old.value) or pd.isna(new.value) else bool(old.value == new.value)
 result['witness_checks'][label]['same_metric_horizon'] = bool(old.metric == new.metric and old.horizon_label_raw == new.horizon_label_raw)
 result['witness_checks'][label]['different_sessions'] = bool(old.collection_session_id != new.collection_session_id)
text=json.dumps(result,indent=2,sort_keys=True,default=str)+'\n'
(root/'INDEPENDENT_SNAPSHOT_CHECKS.json').write_text(text)
print('FINAL_EXTENDED_RECEIPT\n'+text)
```

## What was independently established

The successful execution and its final output were inspected. It recomputes native counts/IDs/columns, finite versus Arrow-null values, missing metadata, rights labels, correction counts, source-type availability, receipt-count linkage, supersession membership and the four selected natural witnesses in the frozen snapshot. It separately identifies all-null median slots and present non-count measurements lacking positive coverage. See the actual JSON for each field and witness.

## What was not established

A frozen snapshot does not by itself prove historical field immutability across all commits, truthful public-availability clocks or unforgeable producer attribution. The candidate's full producer/job, historical-retention, operating and mutation-test records were treated as attributed source evidence, not independently rerun in this audit. No rights, canonical economic identity, units/currency/accounting basis, forecast calibration, independent issuer-event sample, predictive effect, trading performance or current production-consumer acceptance follows from these checks.

The 27 historical empty-coverage measurement defects remain in raw data. Excluding them from eligible comparisons is not a source rewrite. Missing metadata and all-null median values remain missing; this procedure does not fill them.
