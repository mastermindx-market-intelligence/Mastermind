"""Fixed Knowledge facades issued by the existing installed collector only."""
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class ProjectKnowledgeSourceUnavailable(ValueError):
    pass


class _Reader:
    def __init__(self, *, macro_root):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute():
            raise ValueError("knowledge source must be absolute")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, field) for field in (
            "_source_root", "_macro_root", "_code_root", "_python",
            "_expected_source_sha", "_allow_synthetic_fixture"))


class AgentOsProjectKnowledgeCatalogueReader(_Reader):
    def read(self, *, work_ref):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_binding)
        try:
            return read_installed_project_binding(self, kind="project_knowledge_catalogue", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise ProjectKnowledgeSourceUnavailable("SOURCE_UNAVAILABLE") from None


class AgentOsProjectKnowledgeMemoryReader(_Reader):
    def read(self, *, work_ref):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_binding)
        try:
            return read_installed_project_binding(self, kind="project_knowledge_memory", work_ref=work_ref)
        except InstalledProjectReadUnavailable:
            raise ProjectKnowledgeSourceUnavailable("SOURCE_UNAVAILABLE") from None


class AgentOsProjectKnowledgeSourceReader(_Reader):
    def read(self, *, work_ref, source_ref, expected_revision):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_knowledge_source_binding)
        try:
            return read_installed_project_knowledge_source_binding(self, work_ref=work_ref,
                source_ref=source_ref, expected_revision=expected_revision)
        except InstalledProjectReadUnavailable:
            raise ProjectKnowledgeSourceUnavailable("SOURCE_UNAVAILABLE") from None


class AgentOsProjectDiscoverySourceReader(_Reader):
    def read(self, *, work_ref, discovery_ref, expected_source_commit):
        from control_plane.installed_project_read_binding import (
            InstalledProjectReadUnavailable, read_installed_project_discovery_source_binding)
        try:
            return read_installed_project_discovery_source_binding(self, work_ref=work_ref,
                discovery_ref=discovery_ref, expected_source_commit=expected_source_commit)
        except InstalledProjectReadUnavailable:
            raise ProjectKnowledgeSourceUnavailable("SOURCE_UNAVAILABLE") from None
