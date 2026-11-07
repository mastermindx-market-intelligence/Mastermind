"""Fixed canonical compiler facade, unissued constructors confer no capability."""
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class InstalledProjectCreationCompiler:
    def __init__(self, *, macro_root):
        self._macro_root = Path(macro_root)
        if not self._macro_root.is_absolute(): raise ValueError("PROJECT_CREATION_COMPILER_UNAVAILABLE")
        self._installed_context_owner = None
        self._installed_context_binding = None
        self._installed_reader_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, key) for key in (
            "_source_root", "_macro_root", "_code_root", "_python", "_expected_source_sha", "_allow_synthetic_fixture"))

    def options(self):
        return self._read(mode="options", code_commit=None, request=None)

    def prepare(self, request):
        return self._read(mode="prepare", code_commit=request.get("expected_commit") if type(request) is dict else None, request=request)

    def restore(self, request, *, code_commit):
        return self._read(mode="restore", code_commit=code_commit, request=request)

    def _read(self, *, mode, code_commit, request):
        from control_plane.installed_project_read_binding import read_installed_project_creation_recipe_binding
        try:
            return read_installed_project_creation_recipe_binding(self, mode=mode, code_commit=code_commit, request=request)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("PROJECT_CREATION_COMPILER_UNAVAILABLE") from None
