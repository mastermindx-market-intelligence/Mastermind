"""Pure native-math grey-dot replay with explicit settled-bar observation clocks.

Original source is caller supplied and bound by the snapshot manifest. Only the
listed pure functions and literal constants are executed. No Terminal services,
production emitters, data writers or current worktree imports are invoked.
"""
from __future__ import annotations
import ast
import hashlib
import types
from pathlib import Path
import numpy as np
import pandas as pd

PURE_FUNCTIONS = ('_rma', 'rsi', 'ema', 'rsi_macd', 'stoch_rsi_kd',
                  'crossover', '_3d_groups')


def load_math(source_dir: Path, manifest: dict):
    raw = (source_dir / 'confluence.py').read_bytes()
    raw2 = (source_dir / 'confluence_v2.py').read_bytes()
    for rel, value in [('signal_layer/confluence.py', raw),
                       ('signal_layer/confluence_v2.py', raw2)]:
        if hashlib.sha256(value).hexdigest() != manifest['source_files'][rel]:
            raise ValueError('Native source identity changed: ' + rel)
    tree = ast.parse(raw)
    env = {'np': np, 'pd': pd, '__name__': '_phase5_pure_math'}
    # Literal assignment extraction avoids all module-level executable statements.
    for n in tree.body:
        if isinstance(n, ast.Assign):
            try:
                value = ast.literal_eval(n.value)
            except (ValueError, TypeError):
                continue
            for t in n.targets:
                if isinstance(t, ast.Name):
                    env[t.id] = value
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for name, v in zip(t.elts, value):
                        if isinstance(name, ast.Name): env[name.id] = v
    for name in PURE_FUNCTIONS:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1: raise ValueError('Missing native pure function: ' + name)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<native:' + name + '>', 'exec'), env)
    c = types.SimpleNamespace(**env)
    env2 = {'np': np, 'pd': pd, 'C': c}
    tree2 = ast.parse(raw2)
    for name in ('_known_dates', '_early_dot_mask'):
        nodes = [n for n in tree2.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1: raise ValueError('Missing native mask function: ' + name)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<native:' + name + '>', 'exec'), env2)
    return c, env2['_early_dot_mask']


def frame(close: pd.Series, c, phase: int) -> pd.DataFrame:
    opened, known, values = c._3d_groups(close, phase)
    if len(opened) < 90: return pd.DataFrame()
    x = pd.Series(values, index=opened)
    m, s = c.rsi_macd(x)
    k, d = c.stoch_rsi_kd(x)
    return pd.DataFrame({'macd': m, 'sig': s, 'k': k, 'd': d,
                         'rsi14': c.rsi(x, c.RSI_LEN), 'known_ts': known})


def dots(close: pd.Series, c, native_mask, phase: int = 0):
    if phase not in (0, 1, 2): raise ValueError('Undeclared bar phase')
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError('Invalid observation index')
    if not np.isfinite(close.to_numpy(float)).all() or (close <= 0).any():
        raise ValueError('Unqualified prices')
    sig = frame(close, c, phase)
    out = pd.Series(False, index=close.index)
    if sig.empty: return out, []
    rows = sig.dropna(subset=['macd', 'sig', 'k', 'd', 'rsi14'])
    necessary = c.crossover(rows.k, rows.d) & (rows.d.rolling(c.CONF_W).min() < c.OS)
    records = []
    for label, row in rows.loc[necessary].iterrows():
        known = pd.Timestamp(row.known_ts)
        pos = close.index.get_loc(known)
        # gi % 3 == 0 means this is a completed native 3-session bar.
        if (pos + phase) % 3 != 0: continue
        prefix = close.iloc[:pos + 1]
        observed = frame(prefix, c, phase)
        mask = native_mask(observed, prefix)
        fire = bool(label in mask.index and mask.loc[label])
        if fire:
            out.loc[known] = True
            records.append({'signal_label': str(label.date()),
                            'known_session': str(known.date()), 'bar_phase': phase,
                            'provisional': False, 'research_dataset_anchor': True})
    return out, records
