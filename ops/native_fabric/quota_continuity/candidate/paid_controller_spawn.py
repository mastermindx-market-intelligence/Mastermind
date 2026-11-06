"""Fixed private FD placement before exec of the incumbent controller.

No authority is serialized here. The sole shim owner retains it and validates
its actual spawned Bash process at the post-acquire exchange.
"""
import os
from pathlib import Path
import sys


def main(args):
    if len(args) < 2 or not args[0].isdigit():
        raise ValueError('paid_controller_spawn_refused')
    fd = int(args[0])
    if fd < 3:
        raise ValueError('paid_controller_spawn_refused')
    script = Path(__file__).with_name('remote_sub.sh')
    if Path(args[1]) != script or script.is_symlink():
        raise ValueError('paid_controller_spawn_refused')
    if fd != 9:
        os.dup2(fd, 9, inheritable=True)
        os.close(fd)
    else:
        os.set_inheritable(9, True)
    os.execve('/bin/bash', ['/bin/bash', str(script), *args[2:]], os.environ)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception:
        print('CANONICAL_PAID_CONTROLLER_START_REFUSED', file=sys.stderr)
        raise SystemExit(78)
