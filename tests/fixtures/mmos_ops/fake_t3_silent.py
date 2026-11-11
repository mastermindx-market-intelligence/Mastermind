#!/usr/bin/env python3
"""A `server` that never answers: binds nothing, prints nothing, exits non-zero.

Used to force install's never-answered path (truthful one-line failure + the
label really unloaded) without waiting on a real slow boot.
"""
import sys

sys.exit(1)
