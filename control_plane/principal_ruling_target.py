"""Closed, immutable host selection; no identity, admission or runtime effect."""
from __future__ import annotations

import dataclasses
import re

from common.executive_workspace_contract import _check_work_ref
from control_plane.wake_events import WAKE_ID_RE


@dataclasses.dataclass(frozen=True)
class PrincipalRulingTarget:
    """One original pending obligation selected by the qualified host."""

    work_ref: str
    obligation_id: str
    reasoning_surface: str

    def __post_init__(self):
        if (type(self.work_ref) is not str or not _check_work_ref(self.work_ref)
                or type(self.obligation_id) is not str
                or WAKE_ID_RE.fullmatch(self.obligation_id) is None
                or type(self.reasoning_surface) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", self.reasoning_surface) is None):
            raise ValueError("exact host-owned principal ruling target required")
