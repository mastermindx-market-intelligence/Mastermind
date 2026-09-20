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

# Select the workspace root once, while an authorized host installer owns the
# decision. The installed launcher pins this value so a shell caller cannot
# redirect the canonical route through MASTERMIND_AGENT_WORKSPACE_ROOT.
workspace_root="$HOME/.mastermind/agent-workspaces"
workspace_mount=""
if [ -d /Volumes/Mastermind ]; then
  observed_mount="$(/bin/df -P /Volumes/Mastermind 2>/dev/null | /usr/bin/awk 'END {print $6}')"
  if [ "$observed_mount" = "/Volumes/Mastermind" ]; then
    workspace_root="/Volumes/Mastermind/agent-workspaces"
    workspace_mount="/Volumes/Mastermind"
  fi
fi

target="${MASTERMIND_WORKSPACE_CLI_INSTALL:-$HOME/.local/bin/mmx-workspace}"
payload_root="${MASTERMIND_WORKSPACE_CLI_PAYLOAD_ROOT:-$HOME/.local/share/mastermind/workspace-cli/$release_sha}"
mkdir -p "$(dirname "$target")" "$payload_root/scripts" "$payload_root/control_plane"
cp "$repo/scripts/mastermind_workspace.py" "$payload_root/scripts/mastermind_workspace.py"
cp "$repo/control_plane/executive_workspace.py" "$payload_root/control_plane/executive_workspace.py"
cp "$repo/control_plane/__init__.py" "$payload_root/control_plane/__init__.py"
chmod 0755 "$payload_root/scripts/mastermind_workspace.py"
chmod 0644 "$payload_root/control_plane/executive_workspace.py" "$payload_root/control_plane/__init__.py"

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
