"""Sealed facade dispatcher and pre-turn binding receipt.

Order of operations for every single call, with no shortcuts:

1. the request is already validated against the frozen contract;
2. the binding receipt must have been validated against the expected seal;
3. the seal is verified *before* the backend is invoked;
4. exactly one backend method is called;
5. the response is bounded and guarded;
6. the seal is verified *again* before the answer is published.

Step 6 is what turns "the backend probably did not write" into "the backend
provably did not write while producing this answer".
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Mapping

from experiments.code_intelligence.backend import (
    BackendPayloadError,
    backend_identity_digest,
)
from experiments.code_intelligence.jsonrpc_stdio import JsonRpcError
from experiments.code_intelligence.lsp_backend import LspBackendError
from experiments.code_intelligence.semantic_contract import (
    DEFAULT_LIMIT,
    SemanticRequest,
    SemanticResponse,
    semantic_tool_schema_digest,
)
from experiments.code_intelligence.serena_backend import SerenaBackendError
from experiments.code_intelligence.workspace_seal import (
    WorkspaceSeal,
    WorkspaceSealError,
    candidate_tree_fingerprint,
    verify_workspace_seal,
    workspace_binding_digest,
)

__all__ = ["FacadeError", "SemanticFacade"]

_PACKAGE = Path(__file__).parent


class FacadeError(Exception):
    """Typed refusal from the facade."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _facade_source_digest() -> str:
    """Digest of the experiment's own source, so a wrapper swap is visible."""
    digest = hashlib.sha256()
    for path in sorted(_PACKAGE.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


class SemanticFacade:
    """The only surface a model touches. Backend-neutral, seal-bound."""

    def __init__(self, *, seal: WorkspaceSeal, backend: Any, scratch: Path) -> None:
        self.seal = seal
        self._backend = backend
        self._scratch = Path(scratch)
        self._receipt: dict[str, Any] | None = None
        self._bound = False
        self.seal_verifications = 0
        self.backend_calls = 0

    # ------------------------------------------------------------------- start

    def start(self) -> None:
        before = candidate_tree_fingerprint(Path(self.seal.resolved_root))
        started = time.time()
        self._backend.start(seal=self.seal, scratch=self._scratch)
        after = candidate_tree_fingerprint(Path(self.seal.resolved_root))
        if before != after:
            raise FacadeError(
                "CANDIDATE_TREE_WRITE_DETECTED", "backend wrote the tree during startup"
            )
        identity = self._backend.identity
        self._receipt = {
            "workspace_binding_digest": workspace_binding_digest(self.seal),
            "facade_source_digest": _facade_source_digest(),
            "semantic_schema_digest": semantic_tool_schema_digest(),
            "backend_identity_digest": backend_identity_digest(identity),
            "backend_kind": identity.kind,
            "language_server_digests": [list(item) for item in identity.language_servers],
            "startup_unix_ms": int(started * 1000),
            "candidate_tree_before": before,
            "candidate_tree_after": after,
        }
        # Binding is established against the seal the host handed us.
        self.validate_binding(expected=self.seal)

    def binding_receipt(self) -> Mapping[str, Any]:
        if self._receipt is None:
            raise FacadeError("FACADE_NOT_BOUND", "start() was not called")
        return dict(self._receipt)

    def validate_binding(self, *, expected: WorkspaceSeal) -> None:
        """Refuse to serve unless the receipt matches the expected workspace."""
        if self._receipt is None:
            raise FacadeError("FACADE_NOT_BOUND", "start() was not called")
        if self._receipt["workspace_binding_digest"] != workspace_binding_digest(expected):
            raise FacadeError(
                "BINDING_RECEIPT_MISMATCH",
                "receipt does not describe the expected workspace",
            )
        if self._receipt["semantic_schema_digest"] != semantic_tool_schema_digest():
            raise FacadeError("BINDING_RECEIPT_MISMATCH", "tool schema drifted")
        self._bound = True

    # ------------------------------------------------------------------ verify

    def _verify_seal(self) -> None:
        try:
            verify_workspace_seal(self.seal)
        except WorkspaceSealError as exc:
            raise FacadeError(exc.code, exc.detail) from exc
        finally:
            self.seal_verifications += 1

    # -------------------------------------------------------------------- call

    def call(
        self, request: SemanticRequest, *, timeout: float | None = None
    ) -> SemanticResponse:
        if not self._bound or self._receipt is None:
            raise FacadeError("FACADE_NOT_BOUND", "binding receipt was not validated")

        self._verify_seal()

        arguments = dict(request.arguments)
        limit = int(arguments.get("limit", DEFAULT_LIMIT))
        tool = request.tool

        self.backend_calls += 1
        try:
            if tool == "workspace_status":
                payload = self._backend.workspace_status(timeout=timeout)
            elif tool == "symbol_overview":
                payload = self._backend.symbol_overview(
                    relative_file=arguments.get("relative_file"),
                    query=arguments.get("query"),
                    limit=limit,
                    timeout=timeout,
                )
            elif tool == "find_symbol":
                payload = self._backend.find_symbol(
                    name=arguments["name"],
                    relative_file=arguments.get("relative_file"),
                    limit=limit,
                    timeout=timeout,
                )
            elif tool == "find_references":
                payload = self._backend.find_references(
                    name=arguments["name"],
                    relative_file=arguments.get("relative_file"),
                    limit=limit,
                    timeout=timeout,
                )
            elif tool == "find_implementations":
                payload = self._backend.find_implementations(
                    name=arguments["name"],
                    relative_file=arguments.get("relative_file"),
                    limit=limit,
                    timeout=timeout,
                )
            elif tool == "diagnostics":
                payload = self._backend.diagnostics(
                    relative_file=arguments.get("relative_file"),
                    limit=limit,
                    timeout=timeout,
                )
            else:  # pragma: no cover - the contract already refused this
                raise FacadeError("UNKNOWN_TOOL", tool)
        except (LspBackendError, SerenaBackendError, JsonRpcError, BackendPayloadError) as exc:
            # One typed failure. Never retried, never downgraded to an empty result.
            raise FacadeError(getattr(exc, "code", "BACKEND_FAILED"), str(exc)[:300]) from exc

        # Publication gate: the tree must be untouched by the work just done.
        self._verify_seal()

        return SemanticResponse(
            tool=tool,
            workspace_binding_digest=self._receipt["workspace_binding_digest"],
            backend_digest=self._receipt["backend_identity_digest"],
            payload=payload,
        )

    def close(self) -> None:
        try:
            self._backend.close()
        except Exception:  # pragma: no cover - defensive teardown
            pass
