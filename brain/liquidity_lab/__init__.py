"""Research-only Global Liquidity Transmission quant substrate.

The package consumes adapter-normalized references to the Macro-owned
``global_liquidity_transmission.v1`` producer.  It deliberately contains no
liquidity-state calculation and exposes no portfolio, sizing, or execution path.
"""

from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    TARGETS,
    ContractError,
    ForwardForecast,
    SourceStateRef,
    TargetSpec,
    build_shock_record,
)
from brain.liquidity_lab.eventization import EventizationPolicy, eventize
from brain.liquidity_lab.ledger import ForwardLedger, ShockRegistry

__all__ = [
    "ContractError",
    "EventizationPolicy",
    "ForwardForecast",
    "ForwardLedger",
    "HORIZONS_BDAYS",
    "ShockRegistry",
    "SourceStateRef",
    "TARGETS",
    "TargetSpec",
    "build_shock_record",
    "eventize",
]
