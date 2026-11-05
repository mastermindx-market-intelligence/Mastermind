"""Fail-closed refusal. The code is safe to print; it never carries a secret."""
from __future__ import annotations


class RuntimeRefusal(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def refusal(issues: set[str]) -> RuntimeRefusal:
    return RuntimeRefusal(",".join(sorted(issues)))
