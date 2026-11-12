"""Fail-closed refusal. The code is safe to print; it never carries a secret."""
from __future__ import annotations


class RuntimeRefusal(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def refusal(issues: set[str]) -> RuntimeRefusal:
    return RuntimeRefusal(",".join(sorted(issues)))


class NativeTurnEffectUnknown(RuntimeRefusal):
    """A native provider turn may have occurred; its owner must reconcile it.

    This exception does not create a lifecycle, retry grant, or local ledger.
    """
    def __init__(self):
        super().__init__("NATIVE_TEXT_EFFECT_UNKNOWN")
