"""Closed-contract helpers for the held Code Intelligence experiment bundle.

Submodules are intentionally not imported here.  The hosted workflow invokes
``hosted_runner`` with ``python -m``; eager re-exports would preload that module
and contaminate the sealed command's receipt stream with a runtime warning.
"""

__all__: list[str] = []
