#!/bin/sh
set -eu

repo="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
target="${MASTERMIND_WORKSPACE_CLI_INSTALL:-$HOME/.local/bin/mmx-workspace}"
mkdir -p "$(dirname "$target")"

cat > "$target" <<EOF
#!/bin/sh
set -eu
export MASTERMIND_SOURCE_REPO='$repo'
if [ -n "\${MASTERMIND_PYTHON:-}" ]; then
  exec "\$MASTERMIND_PYTHON" '$repo/scripts/mastermind_workspace.py' "\$@"
elif [ -x /opt/homebrew/bin/python3 ]; then
  exec /opt/homebrew/bin/python3 '$repo/scripts/mastermind_workspace.py' "\$@"
else
  exec python3 '$repo/scripts/mastermind_workspace.py' "\$@"
fi
EOF
chmod 0755 "$target"
printf '%s\n' "$target"
