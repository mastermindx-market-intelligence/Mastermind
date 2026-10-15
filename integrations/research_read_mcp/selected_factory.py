"""Explicit selected-generation factory inputs; no imports or effects from Macro.

These process-local parameters are supplied by the release owner. Neither wire
arguments, deployment JSON nor an environment flag can activate this path.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .contracts import ContractViolation
from .selected_delivery import GuardedOperation


@dataclass(frozen=True)
class SelectedReadOptions:
    expected_producer_commit: str
    writer_policy: object
    max_age_seconds: int = 3600
    max_reuse_seconds: int = 300
    corpus_byte_budget: int = 32 * 1024 * 1024
    image_admission_bytes: int = 256 * 1024 * 1024
    refresh_interval_seconds: int = 30

    def validate(self):
        if (type(self) is not SelectedReadOptions
                or type(self.expected_producer_commit) is not str
                or re.fullmatch(r"[0-9a-f]{40}", self.expected_producer_commit) is None
                or not callable(self.writer_policy)):
            raise ContractViolation("SOURCE_UNAVAILABLE")
        # Upper bounds are the current deployment proposal, not an RSS promise.
        for value, maximum in ((self.max_age_seconds, 3600),
                               (self.max_reuse_seconds, 300),
                               (self.corpus_byte_budget, 192 * 1024 * 1024),
                               (self.image_admission_bytes, 768 * 1024 * 1024)):
            if type(value) is not int or not 0 < value <= maximum:
                raise ContractViolation("SOURCE_UNAVAILABLE")
        if (type(self.refresh_interval_seconds) is not int
                or not 0 < self.refresh_interval_seconds <= 300):
            raise ContractViolation("SOURCE_UNAVAILABLE")


class SelectedMacroComposition:
    """One provider/service pair; the existing adapter owns async concurrency."""
    def __init__(self, service, context_type, receipt, provider, guarded_type, unavailable_type):
        self.service, self.context_type, self.receipt = service, context_type, receipt
        self._provider = provider
        self._guarded_type, self._unavailable_type = guarded_type, unavailable_type

    def run(self, operation):
        try:
            result = self._provider.run(operation)
        except self._unavailable_type:
            raise ContractViolation("SOURCE_UNAVAILABLE") from None
        if type(result) is not self._guarded_type:
            raise ContractViolation("SOURCE_UNAVAILABLE")
        # Macro and MCP use different field order; bind by name, never position.
        return GuardedOperation(value=result.value,
                                selection_identity=result.selection_identity,
                                delivery_guard=result.delivery_guard)

    def ready(self):
        try:
            result = self.run(lambda: None)
            return result.delivery_guard() is None
        except Exception:
            return False

    def prepare(self):
        """Explicit owner action only; readiness and requests never resweep."""
        try:
            self._provider.prepare()
        except self._unavailable_type:
            raise ContractViolation("SOURCE_UNAVAILABLE") from None


    def refresh(self):
        """Full qualification by the same provider; the lifecycle owns cadence."""
        try:
            self._provider.refresh()
        except self._unavailable_type:
            raise ContractViolation("SOURCE_UNAVAILABLE") from None


def build_selected(runtime, service_module, reader_module, store_module, options, clock):
    """Called only after the immutable importer verifies every owned module."""
    options.validate()
    if not callable(clock):
        raise ContractViolation("SOURCE_UNAVAILABLE")
    provider_type = getattr(reader_module, "QualifiedReadProvider", None)
    if not callable(provider_type) or not callable(getattr(provider_type, "refresh", None)):
        raise ContractViolation("SOURCE_UNAVAILABLE")
    provider = provider_type(
        store_module.build_store(), expected_producer_commit=options.expected_producer_commit,
        clock=clock, writer_policy=options.writer_policy,
        max_age_seconds=options.max_age_seconds, max_reuse_seconds=options.max_reuse_seconds,
        corpus_byte_budget=options.corpus_byte_budget,
        image_admission_bytes=options.image_admission_bytes)
    service = runtime.build_qualified_read_service(
        provider, clock=lambda: datetime.fromtimestamp(clock(), timezone.utc))
    return SelectedMacroComposition(service, service_module.ServerReadContext, {}, provider,
                                    reader_module.GuardedRead, reader_module.SelectedReadUnavailable)
