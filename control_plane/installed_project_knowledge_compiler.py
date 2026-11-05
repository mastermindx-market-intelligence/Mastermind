"""Fixed DRAFT recipe facade; issued only by the installed sealed source factory.

No public principal/path/module/command is accepted. The integration service binds
actor, distinct action stamp and retained date before calling this private facade.
Construction alone supplies no binding or permission. Shared lower binding and
collector registration belong to the current installed integration owner.
"""
from __future__ import annotations
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class InstalledProjectKnowledgeCompiler:
    def __init__(self, *, macro_root):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("project_knowledge_recipe_unavailable")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python",
            "_expected_source_sha", "_allow_synthetic_fixture"))

    def compile(self, request, *, actor_ref, permission_binding_digest, decision_date):
        return self._read(mode="prepare", request=request, actor_ref=actor_ref,
            permission_binding_digest=permission_binding_digest, decision_date=decision_date,
            initial_snapshot=None, source_binding=None)

    def restore(self, request, *, actor_ref, permission_binding_digest,
                initial_snapshot, source_binding):
        return self._read(mode="restore", request=request, actor_ref=actor_ref,
            permission_binding_digest=permission_binding_digest,
            decision_date=initial_snapshot.get("decision_date") if type(initial_snapshot) is dict else None,
            initial_snapshot=initial_snapshot, source_binding=source_binding)

    def _read(self, *, mode, request, actor_ref, permission_binding_digest,
              decision_date, initial_snapshot, source_binding):
        from control_plane.installed_project_read_binding import InstalledProjectReadUnavailable
        try:
            from control_plane.installed_project_read_binding import (
                read_installed_project_knowledge_recipe_binding,
            )
            return read_installed_project_knowledge_recipe_binding(self, mode=mode,
                request=request, actor_ref=actor_ref,
                permission_binding_digest=permission_binding_digest,
                decision_date=decision_date, initial_snapshot=initial_snapshot,
                source_binding=source_binding)
        except (ImportError, ValueError, TypeError, AttributeError, InstalledProjectReadUnavailable):
            raise ValueError("project_knowledge_recipe_unavailable") from None
