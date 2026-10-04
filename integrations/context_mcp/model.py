"""Pure identity/refusal model for the Mastermind Context MCP surface."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ContextCaller:
    """Per-request authenticated identity snapshot, not a new grant."""

    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int


class ContextPortRefused(Exception):
    """Closed public refusal returned by the deployment-owned context port."""

    _CODES = frozenset(
        {
            "CONTEXT_REFUSED",
            "CONTEXT_BINDING_CHANGED",
            "CONTEXT_SOURCE_CHANGED",
            "CONTEXT_UNAVAILABLE",
        }
    )

    def __init__(self, code: str = "CONTEXT_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown Context MCP refusal")
        self.code = code
        super().__init__(code)
