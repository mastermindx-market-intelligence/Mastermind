"""Read-only installed-distribution list (INSTALL_RUNBOOK T2).

Runs on the VPS from stdin under the service's own interpreter and writes nothing there:

    ssh -i KEY -o BatchMode=yes root@HOST '/opt/mastermind/.venv/bin/python -I -B -' \
        < remote_dists.py > identity/pre/dists.txt

Stdlib only. Reads package metadata (never imports the packages, never runs pip, never
contacts a network) and prints a header comment with the interpreter identity, then one
`name==version` line per distribution visible to that interpreter, sorted case-insensitively.
"""

import importlib.metadata as metadata
import sys


def main():
    print("# executable=%s prefix=%s python=%s" % (sys.executable, sys.prefix, sys.version.split()[0]))
    rows = set()
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata is not None else None
        rows.add("%s==%s" % (name or "<unnamed>", dist.version))
    for row in sorted(rows, key=lambda text: (text.lower(), text)):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
