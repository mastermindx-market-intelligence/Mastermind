"""Read the existing OMH router; never infer entitlement, placement or execution."""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from .adapter import ProposalError, bounded_plain
from .json_input import decode_plain_json
from .__main__ import _read_file

_TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}')


class RecommendationError(ValueError):
    """Closed errors expose no source text, paths, provider config or prompts."""
    REASONS = {'INVALID_RECOMMENDATION_REQUEST','OMH_BACKEND_UNAVAILABLE',
               'OMH_OVERRIDE_INVALID','OMH_CATEGORY_UNKNOWN','OMH_OUTPUT_INVALID'}
    def __init__(self, reason: str):
        if reason not in self.REASONS:raise ValueError('unknown recommendation error')
        self.reason=reason
        super().__init__(reason)


def installed_backend():
    """Use the installed package itself; no model API, installer or auth reader."""
    try:
        from omh.plugin_bundle.omh.hermes_delegation import (
            mixture_chain_overrides_path, parse_mixture_chain_overrides, chains_with_overrides,
        )
        from omh.routing.recommend import recommend_skills
        return SimpleNamespace(
            mixture_chain_overrides_path=mixture_chain_overrides_path,
            parse_mixture_chain_overrides=parse_mixture_chain_overrides,
            chains_with_overrides=chains_with_overrides,recommend_skills=recommend_skills,
            version=importlib.metadata.version('oh-my-hermes'))
    except (ImportError,importlib.metadata.PackageNotFoundError):
        raise RecommendationError('OMH_BACKEND_UNAVAILABLE') from None


def read_chain_file(path: Path) -> bytes | None:
    """Read one explicit regular routing file; absence alone permits defaults."""
    try:
        return _read_file(str(path))
    except FileNotFoundError:
        return None
    except (OSError,ProposalError,ValueError):
        raise RecommendationError('OMH_OVERRIDE_INVALID') from None


def _token(value: Any, *, empty=False) -> str:
    if type(value) is not str or (not value and not empty) or (value and _TOKEN.fullmatch(value) is None):
        raise RecommendationError('OMH_OUTPUT_INVALID')
    return value


def recommend(message: str, category: str, *, omh_home: Path, backend=None) -> dict[str,Any]:
    """Return detached advisory candidates and a small existing-skill shortlist.

    The explicit OMH home belongs to the host/CLI operator, never tool arguments.
    Do not call effective_mixture_category_chains: its entitlement shaping reads
    provider/auth metadata and is not an admission proof. Capacity owns eligibility.
    """
    if (type(message) is not str or not 1<=len(message)<=4000 or message!=message.strip()
            or any(ord(c)<32 and c not in '\n\r\t' for c in message)
            or type(category) is not str or _TOKEN.fullmatch(category) is None):
        raise RecommendationError('INVALID_RECOMMENDATION_REQUEST')
    try:message_bytes=message.encode('utf-8')
    except UnicodeEncodeError:raise RecommendationError('INVALID_RECOMMENDATION_REQUEST') from None
    home=Path(omh_home)
    if not home.is_absolute():raise RecommendationError('INVALID_RECOMMENDATION_REQUEST')
    owner=backend if backend is not None else installed_backend()
    try:
        path=owner.mixture_chain_overrides_path(home)
        # A package update must not redirect this adapter to an auth/memory file.
        if path != home/'routing/model-chains.json':raise RecommendationError('OMH_BACKEND_UNAVAILABLE')
        raw=read_chain_file(path)
        overrides={}
        if raw is not None:
            try:
                document=decode_plain_json(raw)
                overrides,status=owner.parse_mixture_chain_overrides(document)
            except (ProposalError,ValueError,KeyError,TypeError):
                raise RecommendationError('OMH_OVERRIDE_INVALID') from None
            if status!='applied':raise RecommendationError('OMH_OVERRIDE_INVALID')
        chains=owner.chains_with_overrides(overrides)
        if type(chains) is not dict or category not in chains:
            raise RecommendationError('OMH_CATEGORY_UNKNOWN')
        chain=chains[category]
        if type(chain) not in (tuple,list) or not 1<=len(chain)<=16:
            raise RecommendationError('OMH_OUTPUT_INVALID')
        candidates=[]
        for entry in chain:
            if type(entry) not in (tuple,list) or len(entry)!=2:raise RecommendationError('OMH_OUTPUT_INVALID')
            candidates.append(dict(model_alias=_token(entry[0]),reasoning_effort=_token(entry[1],empty=True)))
        rows=owner.recommend_skills(message,limit=3)
        if type(rows) is not list or len(rows)>3:raise RecommendationError('OMH_OUTPUT_INVALID')
        skills=[]
        for row in rows:
            if type(row) is not dict:raise RecommendationError('OMH_OUTPUT_INVALID')
            # In particular do not return suggested_prompt or handoff commands.
            skills.append({key:_token(row.get(key,''),empty=key!='skill')
                           for key in ('skill','category','phase')})
        result=dict(schema='mastermind.hermes_omh.recommendation/v1',
                    state='RECOMMENDED_NOT_ADMITTED',admitted=False,dispatched=False,
                    availability='NOT_OBSERVED',selected_model=None,category=category,
                    origin='configured_override' if category in overrides else 'upstream_default',
                    model_candidates=candidates,skills=skills,
                    request_sha256=hashlib.sha256(message_bytes).hexdigest(),
                    omh_version=_token(owner.version),
                    chain_source_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
                    execution_owner='Mastermind Executive and Capacity/Fabric',
                    memory_owner='Existing selected OMH provider and scoped Agent OS integration')
        bounded_plain(result)
        return result
    except RecommendationError:
        raise
    except Exception:
        # Existing upstream software is a failure boundary, not a default route.
        raise RecommendationError('OMH_BACKEND_UNAVAILABLE') from None
