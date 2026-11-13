"""Run a frozen, read-only-input research experiment; writes a NEW output directory.

python -m research.apmem_shadow --prices QQQ.parquet --options QQQ_gex.parquet --output /path/new-run
No automatic data collection, market action, scheduler, or live integration.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import io
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

from .consumer import SourceObservation, ModelObservation, shadow_context
from .evaluation import daily_frame, evaluate, write_json


def read_input(path: Path) -> tuple[pd.DataFrame, dict]:
    # Read once, then hash and parse those SAME bytes. Source files are never modified.
    with path.open("rb") as stream:
        body = stream.read(32*1024*1024+1)
    if len(body) > 32*1024*1024:
        raise ValueError("input exceeds the bounded 32-MiB research file limit")
    seen = datetime.now(timezone.utc).isoformat()
    if path.suffix.lower() == '.parquet':
        frame = pd.read_parquet(io.BytesIO(body))
    elif path.suffix.lower() == '.csv':
        frame = pd.read_csv(io.BytesIO(body))
    else:
        raise ValueError("use an explicitly supplied .csv or .parquet file")
    frame = daily_frame(frame)
    if frame.empty:
        raise ValueError("input contains no economic sessions")
    return frame, {"file_name": path.name, "sha256": hashlib.sha256(body).hexdigest(),
                   "bytes": len(body), "read_observed_at": seen,
                   "rows": len(frame), "first_session": str(frame.index[0].date()),
                   "last_session": str(frame.index[-1].date()),
                   "historical_first_available_at": None,
                   "publication_clock_verified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices', required=True, type=Path)
    parser.add_argument('--options', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--instrument', default='QQQ')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Z][A-Z0-9._-]{0,15}', args.instrument):
        parser.error('invalid instrument identifier')
    if args.output.exists():
        parser.error('output directory already exists; retained evidence is never overwritten')
    started = datetime.now(timezone.utc)
    try:
        prices, pmeta = read_input(args.prices)
        options, ometa = read_input(args.options)
        args.output.mkdir(parents=True, exist_ok=False)
        manifest = {"schema": "mastermind.apmem_input_receipt.v1", "instrument": args.instrument,
                    "instrument_binding": "caller_declared_existing_source_contract",
                    "started_at": started.isoformat(), "prices": pmeta, "options": ometa,
                    "source_files": {}, "environment": {},
                    "mode": "retrospective_reconstruction_not_prospective"}
        for file in sorted(Path(__file__).parent.glob('*.py')):
            manifest['source_files'][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
        for package in ('numpy', 'pandas', 'scipy', 'pyarrow'):
            try: manifest['environment'][package] = version(package)
            except PackageNotFoundError: manifest['environment'][package] = None
        write_json(args.output/'source_manifest.json', manifest)
        outputs = []
        primary = None
        for retention in (.05, .94):
            result, rows = evaluate(prices, options, retention=retention)
            result['instrument'] = args.instrument
            result['input_sha256'] = [pmeta['sha256'], ometa['sha256']]
            result['generated_at'] = datetime.now(timezone.utc).isoformat()
            tag = str(retention).replace('.', '_')
            write_json(args.output/f'evaluation_{tag}.json', result)
            rows.to_csv(args.output/f'predictions_{tag}.csv', index_label='date')
            outputs.append(result)
            if retention == .05: primary = (result, rows)
        completed = datetime.now(timezone.utc)
        result, rows = primary
        last_forecast = rows.forecast_next_daily_variance.iloc[-1]
        # A date-only source cannot honestly provide an observed-through timestamp.
        # Keep the missing clocks missing, rather than inventing historical 16:00s.
        psource = SourceObservation(args.instrument, prices.index[-1].date(), None,
            datetime.fromisoformat(pmeta['read_observed_at']), pmeta['sha256'],
            'supplied_price_snapshot', 'raw_ohlc')
        osource = SourceObservation(args.instrument, options.index[-1].date(), None,
            datetime.fromisoformat(ometa['read_observed_at']), ometa['sha256'],
            'supplied_reconstructed_options_snapshot', 'gex_bn_iv_annual_decimal', True)
        fit = ModelObservation(args.instrument, None, completed, (pmeta['sha256'],),
            'apmem-original-frozen-v1-lambda005',
            float(last_forecast) if np.isfinite(last_forecast) else None)
        context = shadow_context(instrument=args.instrument, decision_at=completed,
            price=psource, options=osource, fit=fit,
            expected_options_session=prices.index[-2].date())
        write_json(args.output/'shadow_context.json', context)
        manifest['completed_at'] = completed.isoformat()
        manifest['output_sha256'] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(args.output.iterdir()) if f.name != 'source_manifest.json'}
        write_json(args.output/'source_manifest.json', manifest)
        summary = {"status": "RESEARCH_EVALUATED_NOT_PROMOTED", "output": str(args.output),
                   "source_manifest_sha256": hashlib.sha256((args.output/'source_manifest.json').read_bytes()).hexdigest(),
                   "source_rows": {"prices": len(prices), "options": len(options)},
                   "consumer": context,
                   "experiments": [{"retention": x['preprocessing']['retention'],
                     "forecast_metrics": x['forecast_metrics'],
                     "event_summaries": {k:{a:b for a,b in v.items() if a!='event_indices'}
                                          for k,v in x['event_summaries'].items()},
                     "fits_attempted": len(x['fits']),
                     "fits_succeeded": sum(f['success'] for f in x['fits']),
                     "comparison_start": x['comparison_start'],
                     "paired_eligible_decisions": x['paired_eligible_decisions'],
                     "strategies": [{k:v for k,v in z.items() if k!='trades'} |
                                    {"episodes":len(z['trades']),"censored_episodes":sum(t['censored'] for t in z['trades'])}
                                    for z in x['strategies']]} for x in outputs]}
        write_json(args.output/'summary.json', summary)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('experiments','consumer')}, allow_nan=False))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(json.dumps({"status": "INPUT_OR_EXECUTION_FAILED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
