"""Mastermind operational utilities and the explicitly installed Macro library.

Mastermind can import this package before bot bootstraps the pinned Macro root.
Admit that one installed scripts directory so its native generation and freshness
owners remain importable. Mastermind modules retain precedence. No ambient path
discovery, module replacement, source copy or alternate runtime owner is involved.
"""
from pathlib import Path as _Path

_macro_scripts = str(_Path(__file__).resolve().parent.parent / "vendor" / "macro" / "scripts")
if _macro_scripts not in __path__:
    __path__.append(_macro_scripts)
del _Path, _macro_scripts
