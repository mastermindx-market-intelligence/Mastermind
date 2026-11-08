"""Finite DSH operations through the incumbent application transport owner."""
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.executive_os import application_tunnel_control as control


def main(argv=None):
    return control.main(argv, paths=control.Paths.deepseek())


if __name__ == "__main__":
    try:
        control.require(sys.flags.isolated and sys.dont_write_bytecode,
                        "isolated no-bytecode invocation required")
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, control.install_source_policy.InstallSourcePolicyError,
            subprocess.SubprocessError) as exc:
        sys.stderr.write(control._redact("DeepSeek transport refused: %s" % exc) + "\n")
        raise SystemExit(65)
