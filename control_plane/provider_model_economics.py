"""Production-inert capability and token-economics catalog for routing models.

Quota windows/balances stay with Shared AI Provider Control; suitability stays
with Model Router; lifecycle/claims stay with Executive OS. Subscription burn
here is only a method declaration, never capacity truth.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

CATALOG_SCHEMA = "mastermind.provider_model_economics/v1"
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "provider_model_economics.v1.json"
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BURN_METHODS = {"measured_native_delta", "provider_native_credits", "token_rate_card"}
_AUTHORITY = {"suitability": "model_router", "capacity_and_quota": "shared_ai_provider_control", "lifecycle_and_claim": "executive_os"}
_TOP = {"schema", "catalog_version", "verified_at", "production_armed", "scope", "authority", "sources", "models"}
_MODEL_KEYS = {"provider", "provider_model", "family", "positioning", "context_window_tokens", "max_output_tokens", "model_capabilities", "harness_overlays", "api_rates", "subscription_burn", "source_ids"}
_OVERLAY = {"surface", "capabilities", "effective_context_window_tokens", "source_ids"}
_RATE = {"rate_id", "surface", "currency", "unit", "min_context_tokens", "max_context_tokens", "input", "cached_input", "cache_write", "output", "source_id", "effective_from", "notes"}
_BURN = {"surface", "method", "native_unit", "source_id", "notes"}
_SOURCE = {"url", "verified_at"}


class ModelEconomicsError(ValueError):
    pass


def _closed(value: Any, keys: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ModelEconomicsError(f"{field} has wrong shape")
    return value


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ModelEconomicsError(f"{field} must be a bounded lowercase identifier")
    return value


def _model(value: Any, field: str) -> str:
    if not isinstance(value, str) or _MODEL.fullmatch(value) is None:
        raise ModelEconomicsError(f"{field} must be a bounded provider model token")
    return value


def _int(value: Any, field: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise ModelEconomicsError(f"{field} has invalid integer")
    return value


def _int_or_none(value: Any, field: str) -> int | None:
    return None if value is None else _int(value, field)


def _date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ModelEconomicsError(f"{field} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ModelEconomicsError(f"{field} must be an ISO date") from exc
    return value


def _decimal(value: Any, field: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 32:
        raise ModelEconomicsError(f"{field} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ModelEconomicsError(f"{field} must be a decimal string") from exc
    if not result.is_finite() or result < 0 or result.as_tuple().exponent < -9:
        raise ModelEconomicsError(f"{field} is out of bounds")
    return result


def _ids(value: Any, field: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 64 or (not empty and not value):
        raise ModelEconomicsError(f"{field} must be a bounded identifier list")
    result = tuple(_id(x, field) for x in value)
    if len(result) != len(set(result)):
        raise ModelEconomicsError(f"{field} has duplicates")
    return result


def _sources_exist(ids: tuple[str, ...], sources: Mapping[str, Any], field: str) -> None:
    if set(ids) - set(sources):
        raise ModelEconomicsError(f"{field} references unknown sources")


@dataclasses.dataclass(frozen=True, slots=True)
class HarnessOverlay:
    surface: str
    capabilities: frozenset[str]
    effective_context_window_tokens: int | None


@dataclasses.dataclass(frozen=True, slots=True)
class ApiRateCard:
    rate_id: str
    surface: str
    min_context_tokens: int
    max_context_tokens: int | None
    input_per_million: Decimal
    cached_input_per_million: Decimal | None
    cache_write_per_million: Decimal | None
    output_per_million: Decimal

    def accepts(self, context_tokens: int) -> bool:
        return context_tokens >= self.min_context_tokens and (self.max_context_tokens is None or context_tokens <= self.max_context_tokens)


@dataclasses.dataclass(frozen=True, slots=True)
class SubscriptionBurnRule:
    surface: str
    method: str
    native_unit: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderModelRecord:
    model_key: str
    provider: str
    provider_model: str
    context_window_tokens: int | None
    max_output_tokens: int | None
    model_capabilities: frozenset[str]
    harness_overlays: tuple[HarnessOverlay, ...]
    api_rates: tuple[ApiRateCard, ...]
    subscription_burn: tuple[SubscriptionBurnRule, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderModelCatalog:
    catalog_version: str
    verified_at: str
    models: Mapping[str, ProviderModelRecord]

    def model(self, key: str) -> ProviderModelRecord:
        key = _id(key, "model_key")
        if key not in self.models:
            raise ModelEconomicsError(f"unknown model_key {key!r}")
        return self.models[key]

    def effective_capabilities(self, key: str, *, surface: str | None = None) -> frozenset[str]:
        record = self.model(key)
        result = set(record.model_capabilities)
        if surface is not None:
            surface = _id(surface, "surface")
            result.update(*(o.capabilities for o in record.harness_overlays if o.surface == surface))
        return frozenset(result)

    def effective_context_window(self, key: str, *, surface: str | None = None) -> int | None:
        record = self.model(key)
        if surface is not None:
            surface = _id(surface, "surface")
            for overlay in record.harness_overlays:
                if overlay.surface == surface and overlay.effective_context_window_tokens is not None:
                    return overlay.effective_context_window_tokens
        return record.context_window_tokens

    def subscription_burn_rule(self, key: str, *, surface: str) -> SubscriptionBurnRule:
        surface = _id(surface, "surface")
        rows = [x for x in self.model(key).subscription_burn if x.surface == surface]
        if len(rows) != 1:
            raise ModelEconomicsError(f"model {key!r} has no unique subscription burn rule for {surface!r}")
        return rows[0]

    def api_rate_card(self, key: str, *, surface: str, context_tokens: int | None) -> ApiRateCard:
        surface = _id(surface, "surface")
        rows = [x for x in self.model(key).api_rates if x.surface == surface]
        if not rows:
            raise ModelEconomicsError(f"model {key!r} has no reviewed API rate for {surface!r}")
        if context_tokens is None:
            if len(rows) == 1 and rows[0].min_context_tokens == 0 and rows[0].max_context_tokens is None:
                return rows[0]
            raise ModelEconomicsError("context_tokens is required when pricing is context-banded or bounded")
        context_tokens = _int(context_tokens, "context_tokens", zero=True)
        rows = [x for x in rows if x.accepts(context_tokens)]
        if len(rows) != 1:
            raise ModelEconomicsError(f"no unique reviewed rate for model={key!r} surface={surface!r} context_tokens={context_tokens}")
        return rows[0]

    def estimate_api_cash_usd(self, key: str, *, surface: str, input_tokens: int, cached_input_tokens: int = 0, cache_write_tokens: int = 0, output_tokens: int = 0, context_tokens: int | None = None) -> Decimal:
        card = self.api_rate_card(key, surface=surface, context_tokens=context_tokens)
        amounts = {"input": _int(input_tokens, "input_tokens", zero=True), "cached": _int(cached_input_tokens, "cached_input_tokens", zero=True), "write": _int(cache_write_tokens, "cache_write_tokens", zero=True), "output": _int(output_tokens, "output_tokens", zero=True)}
        prices = {"input": card.input_per_million, "cached": card.cached_input_per_million, "write": card.cache_write_per_million, "output": card.output_per_million}
        total = Decimal(0)
        for name, tokens in amounts.items():
            if tokens:
                if prices[name] is None:
                    raise ModelEconomicsError(f"reviewed rate {card.rate_id!r} has no {name} price")
                total += Decimal(tokens) * prices[name] / Decimal(1_000_000)
        return total


def _parse_overlay(raw: Any, sources: Mapping[str, Any], field: str) -> HarnessOverlay:
    raw = _closed(raw, _OVERLAY, field)
    refs = _ids(raw["source_ids"], field)
    _sources_exist(refs, sources, field)
    return HarnessOverlay(_id(raw["surface"], field), frozenset(_ids(raw["capabilities"], field)), _int_or_none(raw["effective_context_window_tokens"], field))


def _parse_rate(raw: Any, sources: Mapping[str, Any], field: str) -> ApiRateCard:
    raw = _closed(raw, _RATE, field)
    source = _id(raw["source_id"], field)
    _sources_exist((source,), sources, field)
    if raw["currency"] != "USD" or raw["unit"] != "per_million_tokens":
        raise ModelEconomicsError(f"{field} supports USD per_million_tokens only")
    _date(raw["effective_from"], field)
    if not isinstance(raw["notes"], str) or len(raw["notes"]) > 2048:
        raise ModelEconomicsError(f"{field} notes are invalid")
    lo = _int(raw["min_context_tokens"], field, zero=True)
    hi = _int_or_none(raw["max_context_tokens"], field)
    if hi is not None and hi < lo:
        raise ModelEconomicsError(f"{field} context band is inverted")
    return ApiRateCard(_id(raw["rate_id"], field), _id(raw["surface"], field), lo, hi, _decimal(raw["input"], field), _decimal(raw["cached_input"], field, nullable=True), _decimal(raw["cache_write"], field, nullable=True), _decimal(raw["output"], field))


def _parse_burn(raw: Any, sources: Mapping[str, Any], field: str) -> SubscriptionBurnRule:
    raw = _closed(raw, _BURN, field)
    source = _id(raw["source_id"], field)
    _sources_exist((source,), sources, field)
    method = _id(raw["method"], field)
    if method not in _BURN_METHODS:
        raise ModelEconomicsError(f"{field} has unsupported burn method")
    if not isinstance(raw["notes"], str) or len(raw["notes"]) > 2048:
        raise ModelEconomicsError(f"{field} notes are invalid")
    return SubscriptionBurnRule(_id(raw["surface"], field), method, _id(raw["native_unit"], field))


def _parse_model(key: str, raw: Any, sources: Mapping[str, Any]) -> ProviderModelRecord:
    raw = _closed(raw, _MODEL_KEYS, f"models.{key}")
    refs = _ids(raw["source_ids"], key)
    _sources_exist(refs, sources, key)
    overlays = tuple(_parse_overlay(x, sources, key) for x in raw["harness_overlays"])
    rates = tuple(_parse_rate(x, sources, key) for x in raw["api_rates"])
    burns = tuple(_parse_burn(x, sources, key) for x in raw["subscription_burn"])
    if len({x.surface for x in overlays}) != len(overlays) or len({x.surface for x in burns}) != len(burns):
        raise ModelEconomicsError(f"{key} has duplicate surfaces")
    for surface in {x.surface for x in rates}:
        rows = sorted((x for x in rates if x.surface == surface), key=lambda x: x.min_context_tokens)
        for left, right in zip(rows, rows[1:]):
            if left.max_context_tokens is None or right.min_context_tokens <= left.max_context_tokens:
                raise ModelEconomicsError(f"{key} has overlapping price bands")
    return ProviderModelRecord(key, _id(raw["provider"], key), _model(raw["provider_model"], key), _int_or_none(raw["context_window_tokens"], key), _int_or_none(raw["max_output_tokens"], key), frozenset(_ids(raw["model_capabilities"], key)), overlays, rates, burns)


def load_provider_model_catalog(path: Path | str = DEFAULT_CATALOG_PATH) -> ProviderModelCatalog:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelEconomicsError("provider model catalog is unreadable") from exc
    doc = _closed(doc, _TOP, "catalog")
    if doc["schema"] != CATALOG_SCHEMA or doc["production_armed"] is not False or doc["scope"] != "routing_models_only" or doc["authority"] != _AUTHORITY:
        raise ModelEconomicsError("provider model catalog boundary is invalid")
    sources = doc["sources"]
    if not isinstance(sources, Mapping) or not sources:
        raise ModelEconomicsError("sources must be a non-empty object")
    for key, row in sources.items():
        _id(key, "source_id")
        row = _closed(row, _SOURCE, f"source.{key}")
        if not isinstance(row["url"], str) or not row["url"].startswith("https://"):
            raise ModelEconomicsError(f"source.{key} has invalid URL")
        _date(row["verified_at"], f"source.{key}")
    raw_models = doc["models"]
    if not isinstance(raw_models, Mapping) or not raw_models or len(raw_models) > 256:
        raise ModelEconomicsError("models must be a bounded object")
    models = {_id(key, "model_key"): _parse_model(_id(key, "model_key"), value, sources) for key, value in raw_models.items()}
    identities = [(x.provider, x.provider_model) for x in models.values()]
    if len(identities) != len(set(identities)):
        raise ModelEconomicsError("duplicate provider/model identity")
    return ProviderModelCatalog(_id(doc["catalog_version"], "catalog_version"), _date(doc["verified_at"], "verified_at"), models)
