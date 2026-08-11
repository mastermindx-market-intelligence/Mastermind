"""Deterministic instrument identity policy for executable portfolio targets.

Every active AI portfolio is a single-name-equity book.  A ticker-shaped string,
a quote, or a signal artifact does not prove that an instrument is an eligible
stock: those surfaces also contain ETFs, funds, indices, warrants, and other
pooled products.  Positive authority is market-specific and local:

* US Brain — the canonical per-company ``stockdata`` contract.
* CN Brain — exact membership in Macro's validated A-share stock heatmap.
* HK Brain — exact membership in Macro's validated official HSCI universe or
  its validated Hong Kong stock heatmap.

The policy is read-only and fail-closed.  Missing, malformed, or conflicting
metadata returns ``unknown``; callers must not turn that into executable intent.
The archived ETF book and the user's self-directed book remain outside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

POLICY_NAME = "single_name_equity_only"
POLICY_VERSION = "single_name_equity.v1"

# Negative authority only.  The retired ETF book has a deliberately narrow
# allocation universe; these additional well-known funds close obvious gaps in
# that historical allowlist.  Absence from either set never authenticates a
# common stock.
_ADDITIONAL_KNOWN_ETFS = frozenset(
    {
        "ARKK",
        "ARKG",
        "ARKF",
        "ARKQ",
        "ARKW",
        "BITO",
        "IBIT",
        "FBTC",
        "GBTC",
        "SOXX",
        "VOO",
        "VEA",
        "VWO",
        "EFA",
        "EEM",
        "HYG",
        "LQD",
        "TIP",
        "VNQ",
    }
)

_EXPLICIT_ETF_LABEL = re.compile(
    r"\bETF\b|exchange[- ]traded",
    re.IGNORECASE,
)
_CORPORATE_LEGAL_SUFFIX = re.compile(
    r"(?:^|[\s,])(?:"
    r"inc(?:orporated)?|corp(?:oration)?|ltd|limited|plc|"
    r"l\.?\s*p\.?|s\.?\s*a\.?|s\.?\s*e\.?|n\.?\s*v\.?|a\.?\s*g\.?|"
    r"llc|co(?:mpany)?|group|holdings?|bancorp"
    r")\.?$",
    re.IGNORECASE,
)
_COMMON_SECURITY_TYPES = frozenset(
    {
        "common stock",
        "common_stock",
        "ordinary shares",
        "ordinary_share",
        "equity",
        "stock",
    }
)
_NON_COMMON_SECURITY_TYPES = frozenset(
    {
        "etf",
        "exchange traded fund",
        "exchange-traded fund",
        "fund",
        "mutual fund",
        "closed end fund",
        "closed-end fund",
        "index",
        "future",
        "option",
        "warrant",
        "preferred stock",
        "preferred_stock",
        "bond",
        "crypto",
        "cryptocurrency",
    }
)
_US_COMPANY_EXCHANGES = frozenset(
    {"NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE MKT"}
)

_CHINA_STOCK_SYMBOL = re.compile(
    r"(?:(?:600|601|603|605|688|689)\d{3}\.SS|"
    r"(?:000|001|002|003|300|301|302)\d{3}\.SZ)"
)
_CHINA_TICKER = re.compile(r"\d{6}\.(?:SS|SZ)")
_HK_STOCK_SYMBOL = re.compile(r"\d{4}\.HK")

# Reviewed negative authority for representative/high-liquidity regional funds.
# This list is intentionally not the positive universe: an unlisted ETF still
# fails closed because it cannot appear in either trusted stock master.  These
# rows additionally authorize deterministic removal if inherited inventory is
# ever discovered.
_KNOWN_CHINA_ETFS = frozenset(
    {
        "159919.SZ",  # Harvest CSI 300 ETF
        "510050.SS",  # ChinaAMC SSE 50 ETF
        "510300.SS",  # Huatai-PineBridge CSI 300 ETF
        "510500.SS",  # China Southern CSI 500 ETF
        "512100.SS",  # China Southern CSI 1000 ETF
    }
)
_KNOWN_HK_ETFS = frozenset(
    {
        "2800.HK",  # Tracker Fund of Hong Kong
        "2822.HK",  # CSOP FTSE China A50 ETF
        "2823.HK",  # iShares FTSE A50 China Index ETF
        "2828.HK",  # Hang Seng China Enterprises Index ETF
        "3033.HK",  # CSOP Hang Seng TECH Index ETF
        "3067.HK",  # iShares Hang Seng TECH ETF
        "3088.HK",  # ChinaAMC Hang Seng TECH Index ETF
    }
)
_KNOWN_REGIONAL_INDICES = frozenset({"000300.SS", "000001.SS", "399001.SZ", "^HSI"})


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _read_macro_json(relative: str) -> dict[str, Any] | None:
    """Read one canonical Macro artifact without importing the reasoning layer."""
    for surface in ("site", "data"):
        path = _ROOT / "vendor" / "macro" / surface / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _explicit_identity_labels(payload: dict[str, Any] | None) -> str:
    """Return identity-bearing labels, excluding weak sector taxonomy.

    Macro's ``sector``/``factors.sector`` fields are analytical routing labels,
    not security-master attributes.  In particular, live company snapshots can
    carry ``ETF / macro`` there.  Those fields may make an identity ambiguous,
    but must never authenticate an ETF and thereby authorize a forced sale.
    """
    if not isinstance(payload, dict):
        return ""
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    profile = (
        payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    )
    return " ".join(
        _clean_text(value)
        for value in (
            payload.get("name"),
            payload.get("long_name"),
            payload.get("security_name"),
            payload.get("security_type"),
            payload.get("asset_type"),
            payload.get("instrument_type"),
            payload.get("quote_type"),
            meta.get("en"),
            meta.get("zh"),
            meta.get("security_type"),
            profile.get("name"),
            profile.get("security_type"),
        )
        if value not in (None, "")
    )


def _weak_taxonomy_labels(payload: dict[str, Any] | None) -> str:
    """Return analytical classifications which have no identity authority."""
    if not isinstance(payload, dict):
        return ""
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    factors = (
        payload.get("factors")
        if isinstance(payload.get("factors"), dict)
        else {}
    )
    return " ".join(
        _clean_text(value)
        for value in (
            payload.get("sector"),
            meta.get("grp"),
            factors.get("sector"),
        )
        if value not in (None, "")
    )


def _security_type(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    profile = (
        payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    )
    for value in (
        payload.get("security_type"),
        payload.get("asset_type"),
        payload.get("instrument_type"),
        payload.get("quote_type"),
        meta.get("security_type"),
        profile.get("security_type"),
    ):
        normalized = _clean_text(value, 100).lower()
        if normalized:
            return normalized
    return ""


def _canonical_company_profile(stockdata: dict[str, Any]) -> bool:
    """Whether the canonical snapshot carries narrow operating-company evidence.

    Some legitimate issuers use their ticker as the display name (for example RH)
    and omit ``security_type``.  A recognized US company exchange plus an SEC SIC
    description is still positive company evidence; an entity-style prefix in the
    canonical profile description covers names such as ``AGCO Corporation``.  ETF
    listings normally have neither, and all explicit negative identity checks run
    before this function is consulted.
    """
    profile = (
        stockdata.get("profile")
        if isinstance(stockdata.get("profile"), dict)
        else {}
    )
    exchange = _clean_text(profile.get("exchange"), 100).upper()
    sic_description = _clean_text(profile.get("sic_description"), 300)
    if exchange in _US_COMPANY_EXCHANGES and sic_description:
        return True

    description = _clean_text(profile.get("description"), 1000)
    prefix, marker, _ = description.partition(" is ")
    return bool(marker and _CORPORATE_LEGAL_SUFFIX.search(prefix.strip()))


def classify_us_instrument(ticker: Any) -> dict[str, Any]:
    """Return the trusted identity of a prospective US executable instrument.

    ``kind == 'common_stock'`` is the only executable positive result.  ETF
    observations are verified negative results; everything else remains unknown
    or invalid and must fail closed at the account boundary.
    """
    symbol = str(ticker or "").upper().strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
        return {
            "ticker": symbol,
            "kind": "invalid",
            "status": "invalid_ticker_syntax",
            "verified": False,
        }
    if symbol.endswith((".HK", ".SS", ".SZ")):
        return {
            "ticker": symbol,
            "kind": "invalid",
            "status": "non_us_venue",
            "verified": True,
        }

    try:
        from portfolio import etf_universe

        if (
            etf_universe.is_etf(symbol)
            or etf_universe.name_of(symbol)
            or symbol in _ADDITIONAL_KNOWN_ETFS
        ):
            return {
                "ticker": symbol,
                "kind": "etf",
                "status": "trusted_etf_metadata",
                "verified": True,
            }
    except (AttributeError, ImportError, OSError, TypeError, ValueError):
        # The canonical company contract below is still required for approval.
        # A broken negative lookup therefore cannot fail open.
        if symbol in _ADDITIONAL_KNOWN_ETFS:
            return {
                "ticker": symbol,
                "kind": "etf",
                "status": "trusted_etf_metadata",
                "verified": True,
            }

    stockdata = _read_macro_json(f"stockdata/{symbol}.json")
    stockbrief = _read_macro_json(f"stockbrief/{symbol}.json")
    gex = _read_macro_json(f"gex/{symbol}.json")
    for payload in (stockdata, stockbrief, gex):
        # Generic issuer-name terms such as "Fund" or "Investment Trust" are
        # not ETF authority: Federal Realty Investment Trust (FRT) is an
        # ordinary listed company.  Conversely, analytical sector taxonomy is
        # not ETF authority either: genuine stocks can be routed through
        # ``ETF / macro``.  Only an explicit identity label may supplement the
        # trusted local ETF universe as verified negative authority.
        if _EXPLICIT_ETF_LABEL.search(_explicit_identity_labels(payload)):
            return {
                "ticker": symbol,
                "kind": "etf",
                "status": "trusted_macro_etf_metadata",
                "verified": True,
            }

    if not isinstance(stockdata, dict) or not stockdata:
        return {
            "ticker": symbol,
            "kind": "unknown",
            "status": "missing_canonical_stockdata",
            "verified": False,
        }

    contract_ticker = _clean_text(stockdata.get("ticker"), 32).upper()
    if contract_ticker != symbol:
        return {
            "ticker": symbol,
            "kind": "unknown",
            "status": "stockdata_ticker_mismatch",
            "verified": False,
        }

    security_type = _security_type(stockdata)
    if security_type in _NON_COMMON_SECURITY_TYPES:
        return {
            "ticker": symbol,
            "kind": "non_common_instrument",
            "status": "stockdata_non_common_security_type",
            "verified": True,
        }
    if security_type and security_type not in _COMMON_SECURITY_TYPES:
        return {
            "ticker": symbol,
            "kind": "unknown",
            "status": "stockdata_unrecognized_security_type",
            "verified": False,
        }

    name = _clean_text(stockdata.get("name"), 300)
    sector = _clean_text(stockdata.get("sector"), 200)
    if not sector:
        factors = (
            stockdata.get("factors")
            if isinstance(stockdata.get("factors"), dict)
            else {}
        )
        sector = _clean_text(factors.get("sector"), 200)
    weak_etf_taxonomy = any(
        _EXPLICIT_ETF_LABEL.search(_weak_taxonomy_labels(payload))
        for payload in (stockdata, stockbrief, gex)
    )

    # A canonical company name must be more informative than a ticker echo.
    # Weak/misassigned taxonomy requires stronger positive evidence than an
    # arbitrary long name: either an explicit common-stock security type or a
    # conservative public-company legal suffix.  This admits observed company
    # shapes such as Energy Transfer LP and GSK plc without turning an off-list
    # fund name such as "iShares Core S&P Mid-Cap" into a common stock.
    company_name = bool(name and name.upper() != symbol)
    if security_type in _COMMON_SECURITY_TYPES and name:
        return {
            "ticker": symbol,
            "kind": "common_stock",
            "status": "trusted_stockdata_security_type.v1",
            "verified": True,
        }
    if weak_etf_taxonomy:
        if company_name and _CORPORATE_LEGAL_SUFFIX.search(name):
            return {
                "ticker": symbol,
                "kind": "common_stock",
                "status": "trusted_company_stockdata.v1",
                "verified": True,
            }
        return {
            "ticker": symbol,
            "kind": "unknown",
            "status": "weak_etf_taxonomy_not_identity_authority",
            "verified": False,
        }
    if name and _canonical_company_profile(stockdata):
        return {
            "ticker": symbol,
            "kind": "common_stock",
            "status": "trusted_company_profile.v1",
            "verified": True,
        }
    if company_name and sector:
        return {
            "ticker": symbol,
            "kind": "common_stock",
            "status": "trusted_company_stockdata.v1",
            "verified": True,
        }
    return {
        "ticker": symbol,
        "kind": "unknown",
        "status": "stockdata_missing_common_stock_classification",
        "verified": False,
    }


def executable_common_stock_error(ticker: str) -> str | None:
    """Return ``None`` only for a positively verified US common stock."""
    identity = classify_us_instrument(ticker)
    if identity.get("kind") == "common_stock" and identity.get("verified") is True:
        return None
    return f"non_common_stock:{ticker}:{identity.get('status') or 'unverified_identity'}"


def _validated_stock_heatmap(portfolio_id: str) -> tuple[dict[str, dict[str, Any]], str]:
    """Return an exact trusted regional stock map or an explicit invalid status.

    A single malformed row taints the authority artifact.  Silently filtering a
    bad nested row could manufacture positive identity from an incomplete map.
    """
    contracts = {
        "china": ("marketdata/china_heatmap.json", "china", "chinastockdata"),
        "hk": ("marketdata/hk_heatmap.json", "hk", "hkstockdata"),
    }
    if portfolio_id not in contracts:
        return {}, "unsupported_regional_book"
    relative, market, stockdata_dir = contracts[portfolio_id]
    payload = _read_macro_json(relative)
    if not isinstance(payload, dict):
        return {}, "missing_regional_stock_heatmap"
    tiles = payload.get("tiles")
    n_tiles = payload.get("n_tiles")
    if (
        payload.get("market") != market
        or payload.get("map_type") != "stocks"
        or payload.get("stockdata_dir") != stockdata_dir
        or not isinstance(tiles, list)
        or isinstance(n_tiles, bool)
        or not isinstance(n_tiles, int)
        or n_tiles <= 0
        or n_tiles != len(tiles)
    ):
        return {}, "invalid_regional_stock_heatmap_contract"

    rows: dict[str, dict[str, Any]] = {}
    pattern = _CHINA_TICKER if portfolio_id == "china" else _HK_STOCK_SYMBOL
    for raw in tiles:
        if not isinstance(raw, dict):
            return {}, "invalid_regional_stock_heatmap_rows"
        ticker = raw.get("t") or raw.get("ticker")
        if (
            not isinstance(ticker, str)
            or ticker != ticker.upper().strip()
            or pattern.fullmatch(ticker) is None
            or ticker in rows
        ):
            return {}, "invalid_regional_stock_heatmap_rows"
        if not any(
            isinstance(raw.get(field), str) and raw.get(field).strip()
            for field in ("name", "name_zh", "security_name")
        ):
            return {}, "invalid_regional_stock_heatmap_rows"
        rows[ticker] = raw
    return rows, "trusted_regional_stock_heatmap.v1"


def _validated_hk_official_universe() -> tuple[set[str], str]:
    """Return the official HSCI constituent universe when its provenance is intact."""
    payload = _read_macro_json("hk_stocks_ext/_universe.json")
    if not isinstance(payload, dict):
        return set(), "missing_hk_official_stock_universe"
    tickers = payload.get("tickers")
    count = payload.get("n")
    source = _clean_text(payload.get("source"), 500)
    if (
        not isinstance(tickers, list)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count <= 0
        or count != len(tickers)
        or not source.startswith("https://www.hsi.com.hk/")
    ):
        return set(), "invalid_hk_official_stock_universe_contract"
    normalized: list[str] = []
    for ticker in tickers:
        if (
            not isinstance(ticker, str)
            or ticker != ticker.upper().strip()
            or _HK_STOCK_SYMBOL.fullmatch(ticker) is None
        ):
            return set(), "invalid_hk_official_stock_universe_rows"
        normalized.append(ticker)
    if len(set(normalized)) != len(normalized):
        return set(), "invalid_hk_official_stock_universe_rows"
    return set(normalized), "trusted_hsci_constituent_universe.v1"


def _regional_row_identity(
    portfolio_id: str,
    symbol: str,
    row: dict[str, Any] | None,
    *,
    source_status: str,
) -> dict[str, Any]:
    """Turn one positively matched regional stock-master row into identity."""
    if isinstance(row, dict):
        security_type = _security_type(row)
        if security_type in _NON_COMMON_SECURITY_TYPES:
            kind = "etf" if security_type in {
                "etf",
                "exchange traded fund",
                "exchange-traded fund",
            } else "non_common_instrument"
            return {
                "ticker": symbol,
                "kind": kind,
                "status": "regional_master_non_common_security_type",
                "verified": True,
                "liquidation_authorized": True,
            }
        if _EXPLICIT_ETF_LABEL.search(_explicit_identity_labels(row)):
            return {
                "ticker": symbol,
                "kind": "etf",
                "status": "trusted_regional_etf_metadata",
                "verified": True,
                "liquidation_authorized": True,
            }
    return {
        "ticker": symbol,
        "kind": "common_stock",
        "status": source_status,
        "verified": True,
        "market": portfolio_id,
    }


def _classify_regional_instrument(portfolio_id: str, ticker: Any) -> dict[str, Any]:
    symbol = str(ticker or "").upper().strip()
    expected = _CHINA_TICKER if portfolio_id == "china" else _HK_STOCK_SYMBOL
    if symbol in _KNOWN_REGIONAL_INDICES:
        return {
            "ticker": symbol,
            "kind": "index",
            "status": "regional_benchmark_index",
            "verified": True,
            "liquidation_authorized": True,
        }
    if expected.fullmatch(symbol) is None:
        # Asset identity and venue eligibility are deliberately separate.  A
        # legacy HK company in the CN account is still a stock (so omission can
        # preserve it until an evidenced exit), but executable_equity_error()
        # rejects it for the wrong book and proposed holdings are venue-gated.
        if portfolio_id == "china" and _HK_STOCK_SYMBOL.fullmatch(symbol):
            return _classify_regional_instrument("hk", symbol)
        if portfolio_id == "hk" and _CHINA_TICKER.fullmatch(symbol):
            return _classify_regional_instrument("china", symbol)
        return {
            "ticker": symbol,
            "kind": "invalid",
            "status": f"non_{portfolio_id}_venue_or_ticker_syntax",
            "verified": False,
        }
    if symbol in (_KNOWN_CHINA_ETFS if portfolio_id == "china" else _KNOWN_HK_ETFS):
        return {
            "ticker": symbol,
            "kind": "etf",
            "status": "reviewed_regional_etf_registry.v1",
            "verified": True,
            "liquidation_authorized": True,
        }
    if portfolio_id == "china" and _CHINA_STOCK_SYMBOL.fullmatch(symbol) is None:
        # Same-suffix fund/bond/index namespaces are not company-share authority.
        # Unknown codes fail closed but do not authorize a guessed liquidation.
        return {
            "ticker": symbol,
            "kind": "unknown",
            "status": "not_a_recognized_a_share_stock_code",
            "verified": False,
        }

    heatmap, heatmap_status = _validated_stock_heatmap(portfolio_id)
    row = heatmap.get(symbol)
    if row is not None:
        return _regional_row_identity(
            portfolio_id,
            symbol,
            row,
            source_status=heatmap_status,
        )

    if portfolio_id == "hk":
        official, official_status = _validated_hk_official_universe()
        if symbol in official:
            return _regional_row_identity(
                portfolio_id,
                symbol,
                None,
                source_status=official_status,
            )
        if heatmap_status.startswith("trusted_") or official_status.startswith("trusted_"):
            status = "not_in_trusted_regional_stock_master"
        else:
            status = f"{heatmap_status};{official_status}"
    else:
        status = (
            "not_in_trusted_regional_stock_master"
            if heatmap_status.startswith("trusted_")
            else heatmap_status
        )
    return {
        "ticker": symbol,
        "kind": "unknown",
        "status": status,
        "verified": False,
    }


def classify_instrument(portfolio_id: str, ticker: Any) -> dict[str, Any]:
    """Classify an instrument against the registry-owned policy for one book."""
    from portfolio import registry

    try:
        policy = registry.asset_policy(portfolio_id)
    except ValueError:
        symbol = str(ticker or "").upper().strip()
        return {
            "ticker": symbol,
            "kind": "invalid",
            "status": "unknown_portfolio",
            "verified": False,
        }
    if policy != POLICY_NAME:
        return {
            "ticker": str(ticker or "").upper().strip(),
            "kind": "not_applicable",
            "status": "asset_policy_not_enforced",
            "verified": False,
        }
    if portfolio_id == "autonomous":
        return classify_us_instrument(ticker)
    if portfolio_id in {"china", "hk"}:
        return _classify_regional_instrument(portfolio_id, ticker)
    return {
        "ticker": str(ticker or "").upper().strip(),
        "kind": "unknown",
        "status": "unsupported_single_name_equity_book",
        "verified": False,
    }


def liquidation_authorized(identity: dict[str, Any] | None) -> bool:
    """Whether exact positive evidence permits a deterministic compliance exit."""
    if not isinstance(identity, dict) or identity.get("verified") is not True:
        return False
    if identity.get("liquidation_authorized") is True:
        return True
    # Compatibility for the US classifier, whose exact return dictionaries are
    # kept stable for existing callers and audit fixtures.
    return identity.get("kind") in {"etf", "non_common_instrument", "index", "warrant"}


def executable_equity_error(portfolio_id: str, ticker: str) -> str | None:
    """Return ``None`` only when this book may hold the instrument positively."""
    from portfolio import registry

    if not registry.requires_single_name_equity(portfolio_id):
        return None
    if portfolio_id == "autonomous":
        return executable_common_stock_error(ticker)
    identity = classify_instrument(portfolio_id, ticker)
    if (
        identity.get("kind") == "common_stock"
        and identity.get("verified") is True
        and identity.get("market") == portfolio_id
    ):
        return None
    if identity.get("kind") == "common_stock" and identity.get("verified") is True:
        identity = {**identity, "status": "single_name_equity_wrong_market"}
    symbol = str(ticker or "").upper().strip()
    return (
        f"non_single_name_equity:{symbol}:"
        f"{identity.get('status') or 'unverified_identity'}"
    )
