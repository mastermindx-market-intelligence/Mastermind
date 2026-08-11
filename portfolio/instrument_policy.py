"""Deterministic instrument identity policy for executable portfolio targets.

The US Brain is a common-stock-only book.  A ticker-shaped string, a quote, or a
signal artifact does not prove that an instrument is a common stock: all of
those surfaces also contain ETFs.  This module therefore distinguishes negative
authority (trusted ETF metadata can reject immediately) from positive authority
(only the canonical per-company ``stockdata`` contract can approve a name).

The policy is intentionally read-only and fail-closed.  Missing or conflicting
metadata returns ``unknown``; callers must not turn that into executable intent.
Regional books and the archived ETF book do not use this policy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

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
