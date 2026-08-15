"""Network-facing integrations, isolated from the sealed Executive runtime.

Packages under ``integrations/`` may depend on third-party SDKs.  ``control_plane``
and ``common`` must never import from here — that is what keeps the Executive
control service importable under its pinned, root-owned Python runtime with no
third-party package installed.
"""
from __future__ import annotations
