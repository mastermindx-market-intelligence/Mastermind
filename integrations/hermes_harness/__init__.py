"""Secretary and Meta-CEO harness over the five Hermes work packages.

Importing this package does not start Hermes, register tools, read a secret,
or admit a child. Call ``boot_harness`` for the in-process wiring.
"""

from integrations.hermes_harness.extensions import boot_harness

__all__ = ["boot_harness"]
