"""Secretary and Meta-CEO harness over the five Hermes work packages.

Importing this package does not start Hermes, register tools, read a secret,
or admit a child. Call ``boot_harness`` for the in-process wiring.

The package body stays unloaded until ``boot_harness`` is called. Importing
``shadow_gate`` must not pull provider overlays or PyYAML. The secretary
shadow job does not install PyYAML.
"""

from __future__ import annotations

__all__ = ["boot_harness"]


def __getattr__(name: str):
    if name == "boot_harness":
        from integrations.hermes_harness.extensions import boot_harness

        return boot_harness
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
