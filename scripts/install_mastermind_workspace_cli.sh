#!/bin/sh
set -eu

repo="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
release_sha="$(git -C "$repo" rev-parse HEAD)"
common_dir="$(git -C "$repo" rev-parse --git-common-dir)"
case "$common_dir" in
  /*) common_abs="$common_dir" ;;
  *) common_abs="$repo/$common_dir" ;;
esac
common_abs="$(cd "$(dirname "$common_abs")" && pwd -P)/$(basename "$common_abs")"
if [ "$(basename "$common_abs")" != ".git" ]; then
  echo "unsupported non-worktree Git common directory: $common_abs" >&2
  exit 2
fi
source_repo="$(dirname "$common_abs")"

# Select the workspace root once through the canonical workspace route.
# This is installer policy only: it does not reserve storage or perform Runtime
# admission. An enrolled host policy remains pinned even while its mount is
# unavailable, so the installed launcher refuses fallback later.
if [ -x /opt/homebrew/bin/python3 ]; then
  profile_python=/opt/homebrew/bin/python3
else
  profile_python=python3
fi
profile_output="$("$profile_python" - "$repo/scripts/mastermind_workspace.py" "$HOME" <<'PY'
import importlib.util
import sys
from pathlib import Path

script = Path(sys.argv[1])
home = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("mastermind_workspace_install_profile", script)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load workspace installation profile")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
profile = module.installation_storage_profile(home)
for key in ("root", "mount_point", "policy_path"):
    value = profile[key]
    if "\n" in value or "\r" in value:
        raise SystemExit("workspace installation profile contains a newline")
    print(value)
PY
)"
workspace_root="$(printf '%s\n' "$profile_output" | /usr/bin/sed -n '1p')"
workspace_mount="$(printf '%s\n' "$profile_output" | /usr/bin/sed -n '2p')"
storage_policy="$(printf '%s\n' "$profile_output" | /usr/bin/sed -n '3p')"
if [ -z "$workspace_root" ]; then
  echo "workspace installation profile did not return a root" >&2
  exit 2
fi

target="${MASTERMIND_WORKSPACE_CLI_INSTALL:-$HOME/.local/bin/mmx-workspace}"
payload_root="${MASTERMIND_WORKSPACE_CLI_PAYLOAD_ROOT:-$HOME/.local/share/mastermind/workspace-cli/$release_sha}"
mkdir -p "$(dirname "$target")" "$payload_root/scripts" "$payload_root/control_plane" "$payload_root/common"
cp "$repo/scripts/mastermind_workspace.py" "$payload_root/scripts/mastermind_workspace.py"
cp "$repo/control_plane/executive_workspace.py" "$payload_root/control_plane/executive_workspace.py"
cp "$repo/control_plane/__init__.py" "$payload_root/control_plane/__init__.py"
cp "$repo/common/commission_ref.py" "$payload_root/common/commission_ref.py"
cp "$repo/common/__init__.py" "$payload_root/common/__init__.py"
chmod 0755 "$payload_root/scripts/mastermind_workspace.py"
chmod 0644 "$payload_root/control_plane/executive_workspace.py" "$payload_root/control_plane/__init__.py" \
  "$payload_root/common/commission_ref.py" "$payload_root/common/__init__.py"

wrapper_tmp="$target.tmp.$$"
cat > "$wrapper_tmp" <<EOF
#!/bin/sh
set -eu
workspace_mount='$workspace_mount'
if [ -n "\$workspace_mount" ]; then
  observed_mount="\$(/bin/df -P "\$workspace_mount" 2>/dev/null | /usr/bin/awk 'END {print \$6}')"
  if [ "\$observed_mount" != "\$workspace_mount" ]; then
    echo "Mastermind workspace volume is not mounted at \$workspace_mount; refusing fallback" >&2
    exit 66
  fi
fi
export MASTERMIND_SOURCE_REPO='$source_repo'
export MASTERMIND_AGENT_WORKSPACE_ROOT='$workspace_root'
export MASTERMIND_WORKSPACE_STORAGE_POLICY='$storage_policy'
if [ -n "\${MASTERMIND_PYTHON:-}" ]; then
  exec "\$MASTERMIND_PYTHON" '$payload_root/scripts/mastermind_workspace.py' "\$@"
elif [ -x /opt/homebrew/bin/python3 ]; then
  exec /opt/homebrew/bin/python3 '$payload_root/scripts/mastermind_workspace.py' "\$@"
else
  exec python3 '$payload_root/scripts/mastermind_workspace.py' "\$@"
fi
EOF
chmod 0755 "$wrapper_tmp"
mv "$wrapper_tmp" "$target"
printf '%s\n' "$target"
