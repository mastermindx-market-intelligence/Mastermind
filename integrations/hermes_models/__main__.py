"""Render Hermes provider overlays. Credential values are refused on argv."""

from __future__ import annotations

import sys

from integrations.hermes_models.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
