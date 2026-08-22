"""integrations.chairman_surfaces — Chairman Control Room P0 Wave B.

Zero-message provider navigation adapters: given a validated
``mastermind.surface_bindings.v1`` binding (:mod:`control_plane.
surface_bindings`), focus/open/resume the external surface it points at —
a ChatGPT tab in a named Chrome profile, a Claude Code terminal session, a
Claude desktop conversation, a Cursor agent thread, or a Codex session.

This package never decides lifecycle, attention, ownership, or ranking —
that stays with the canonical sources the Chairman Control Room compositor
(:mod:`control_plane.chairman_control_room`, Wave A) already reads. It is
navigation only, same as the bindings store it consumes.

See ``research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_ARCHITECTURE_AND_
FABLE00_COMMISSION_2026-08-21.md`` §6 (provider locator hierarchy) and §11
rows 6-15 (this wave's commissioned rows).
"""
from __future__ import annotations
