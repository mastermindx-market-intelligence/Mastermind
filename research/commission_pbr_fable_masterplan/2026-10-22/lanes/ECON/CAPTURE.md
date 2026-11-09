# ECON capture — live paper ledger, 2026-10-22T07:31:19Z

Owner: `pbr-econ` (ECON domain, W1/W2) · program #1693 · read-only pull, nothing written on the VPS, no bot code run.

- Raw evidence (not committed): `/Volumes/Mastermind/evidence/pbr/econ-capture-20261022T073119Z/` on the M2 Studio SSD
  (`live-data/` tar of the paths below, `VPS_LISTINGS.txt` full-iso `ls -la` of every captured dir + installed blob ids).
- `MANIFEST.json` (this dir): sha256, size, mtime, host path, in-service path and label for all 412 captured files.

## Where the live ledger actually is (frontier correction)

| | path |
|---|---|
| host root (what the capture read) | `/opt/mastermind-live-data` |
| in-service root (what the bot sees) | `/opt/mastermind/data` — `mastermind.service` drop-in `authoritative.conf`: `BindPaths=/opt/mastermind-live-data:/opt/mastermind/data` |
| `/opt/mastermind/data` from a plain ssh shell | stale July legacy rsync target — **not** the live ledger |
| US book | `portfolios/autonomous/` (`registry.data_dir("autonomous")`) |
| CN / HK books | `portfolios/china/`, `portfolios/hk/` |
| `portfolio/` | archived legacy *flagship* store (last write 2026-08-10) — **not** the US book |

FABLE_START_HERE §1 said "Autonomous book = legacy default storage `data/portfolio/`"; the registry and the live listing
show the US book is `data/portfolios/autonomous`. The legacy store's fills/NAV do not match the audit fingerprints
(182 / 40 rows, no prefix relation).

## Fingerprint agreement with the 2026-10-21 audit

| book | file | audit sha256 (prefix) | captured | status |
|---|---|---|---|---|
| US | `portfolios/autonomous/fills.jsonl` | 778f2846 | 778f2846 | MATCH |
| US | `portfolios/autonomous/nav_history.jsonl` | a61e03ce | a61e03ce | MATCH |
| CN | `portfolios/china/fills.jsonl` | ed5f35b9 | ed5f35b9 | MATCH |
| CN | `portfolios/china/nav_history.jsonl` | c137d2f1 | c137d2f1 | MATCH |
| HK | `portfolios/hk/fills.jsonl` | e37be161 | e37be161 | MATCH |
| HK | `portfolios/hk/nav_history.jsonl` | 509b7e1a | 509b7e1a | MATCH |

No rows appended since the audit.

## Installed code identity (VPS, `git hash-object` of the deployed tree, read-only)

| file | installed blob | equals |
|---|---|---|
| `portfolio/paper_account.py` | ee795ccb | `43f83e068^` (pre-#1614) |
| `bot/settle.py` | abfe4b92 | `43f83e068^` (pre-#1614) |
| `portfolio/price_evidence.py` | absent | — (#1614 not installed) |
| `portfolio/marks.py` | 2c747d16 | origin/master |
| `brain/benchmark_ledger.py` | 64f92ea9 | origin/master |
| `portfolio/registry.py` | f5eb632d | origin/master |

`.deployed_git_sha` = ff16c192c (#1682); #1614 (43f83e068) is not an ancestor. Service MainPID 876885 started
2026-10-22T06:02:15Z. Merged ≠ installed: #1614's selected-price receipt context is not running in production.

## Replay baseline (fills replayed from an empty account; reproduces the audit)

| book | fills | quantity diffs (account − replay) | oversells | cash | net fill cash | non-trade cash residual | NAV = cash + Σ shares × current_price |
|---|---|---|---|---|---|---|---|
| US | 96 (06-21 → 10-09) | none | none | 702,685.19 | −306,529.32 | **+9,214.51** | 1,003,521.98 (10-22) ✓ |
| CN | 112 (06-22 → 10-12) | none | none | 389,318.94 | −616,463.68 | **+5,782.62** | 944,849.17 (10-21) ✓ |
| HK | 96 (06-21 → 10-12) | 6 symbols | 4 rows | 375,562.69 | −629,677.87 | **+5,240.56** | 1,004,800.23 (10-21) ✓ |

HK diffs: 0700.HK +0.807253 · 0981.HK −49.600212 · 1024.HK +12.276828 · 1929.HK +43.202567 · 3988.HK +72.563412 ·
3993.HK −23.503222. Oversells: row 26 (06-29 1024.HK), row 32 (07-01 1929.HK), row 63 (08-03 3988.HK), row 78
(08-07 1024.HK). Residual = cash − starting_nav − net fill cash. Bridges: `HK_BRIDGE.md`, `CASH_BRIDGE.md` (W1 lanes).
