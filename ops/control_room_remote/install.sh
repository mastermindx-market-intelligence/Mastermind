#!/usr/bin/env bash
set -euo pipefail
umask 077

SOURCE_REPO=
ACCEPTED_MASTERMIND_COMMIT=
ACCEPTED_MASTERMIND_TREE=
VERIFY_SOURCE_ONLY=0
SERVICE_UID=497
DESTINATION_ROOT=/opt/mastermind-control-room
UNIT_DESTINATION=/etc/systemd/system/mastermind-control-room-remote.service
SERVICE_USER=mastermind-control-room
CADDY_GROUP=caddy

die() {
  printf '%s\n' "$1" >&2
  exit 65
}

while (($#)); do
  case "$1" in
    --source-repo) SOURCE_REPO=${2-}; shift 2 ;;
    --accepted-commit) ACCEPTED_MASTERMIND_COMMIT=${2-}; shift 2 ;;
    --accepted-tree) ACCEPTED_MASTERMIND_TREE=${2-}; shift 2 ;;
    --service-uid) SERVICE_UID=${2-}; shift 2 ;;
    --verify-source-only) VERIFY_SOURCE_ONLY=1; shift ;;
    *) die "unknown_argument" ;;
  esac
done

[[ $SOURCE_REPO == /* ]] || die "source_repo_not_absolute"
[[ $ACCEPTED_MASTERMIND_COMMIT =~ ^[0-9a-f]{40}$ ]] || die "accepted_commit_invalid"
[[ $ACCEPTED_MASTERMIND_TREE =~ ^[0-9a-f]{40}$ ]] || die "accepted_tree_invalid"
[[ $SERVICE_UID =~ ^[1-9][0-9]*$ ]] || die "service_uid_invalid"
[[ -d $SOURCE_REPO && ! -L $SOURCE_REPO ]] || die "source_repo_invalid"

# Keep these identity checks explicit: git status --porcelain, git rev-parse
# HEAD, and git rev-parse HEAD^{tree} must all agree before git archive runs.
SOURCE_STATUS=$(cd "$SOURCE_REPO" && git status --porcelain --untracked-files=all)
[[ -z $SOURCE_STATUS ]] || die "source_repo_dirty"
SOURCE_HEAD=$(cd "$SOURCE_REPO" && git rev-parse HEAD)
SOURCE_TREE=$(cd "$SOURCE_REPO" && git rev-parse 'HEAD^{tree}')
[[ $SOURCE_HEAD == "$ACCEPTED_MASTERMIND_COMMIT" ]] || die "source_commit_mismatch"
[[ $SOURCE_TREE == "$ACCEPTED_MASTERMIND_TREE" ]] || die "source_tree_mismatch"

python3 -I -B - "$SOURCE_REPO" <<'PY' || die "source_member_unsafe"
import os
import stat
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
listed = subprocess.run(
    [
        "git", "-C", os.fspath(root), "ls-files", "-z", "--",
        "app/static/chairman_control", "control_plane",
        "scripts/chairman_control_room_remote.py",
    ],
    check=True,
    capture_output=True,
).stdout.split(b"\0")
if not listed or listed == [b""]:
    raise SystemExit(1)
for encoded in listed:
    if not encoded:
        continue
    relative = encoded.decode("utf-8", errors="strict")
    parts = Path(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise SystemExit(1)
    candidate = root.joinpath(*parts)
    info = candidate.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit(1)
    if info.st_nlink != 1 or info.st_mode & 0o022:
        raise SystemExit(1)
PY

if ((VERIFY_SOURCE_ONLY)); then
  printf 'SOURCE_VERIFIED commit=%s tree=%s\n' \
    "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE"
  exit 0
fi

[[ $(uname -s) == Linux ]] || die "linux_required"
[[ $(id -u) -eq 0 ]] || die "root_required"
[[ $DESTINATION_ROOT == /opt/mastermind-control-room ]] || die "destination_root_invalid"
[[ $UNIT_DESTINATION == /etc/systemd/system/mastermind-control-room-remote.service ]] || die "unit_destination_invalid"

CADDY_RECORD=$(getent group "$CADDY_GROUP" || true)
[[ -n $CADDY_RECORD ]] || die "caddy_group_missing"
CADDY_GID=$(printf '%s' "$CADDY_RECORD" | cut -d: -f3)
[[ $CADDY_GID =~ ^[0-9]+$ ]] || die "caddy_group_invalid"

SERVICE_RECORD=$(getent passwd "$SERVICE_USER" || true)
UID_RECORD=$(getent passwd "$SERVICE_UID" || true)
if [[ -n $SERVICE_RECORD ]]; then
  [[ $(printf '%s' "$SERVICE_RECORD" | cut -d: -f3) == "$SERVICE_UID" ]] \
    || die "service_user_uid_mismatch"
elif [[ -n $UID_RECORD ]]; then
  die "service_uid_occupied"
else
  useradd --system --uid "$SERVICE_UID" --gid "$CADDY_GID" \
    --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if [[ -e $DESTINATION_ROOT || -L $DESTINATION_ROOT ]]; then
  [[ -d $DESTINATION_ROOT && ! -L $DESTINATION_ROOT ]] || die "destination_root_unsafe"
  [[ $(stat -c %u "$DESTINATION_ROOT") == 0 ]] || die "destination_root_foreign_owner"
  (( (8#$(stat -c %a "$DESTINATION_ROOT") & 8#022) == 0 )) \
    || die "destination_root_writable"
else
  install -d -o root -g root -m 0755 "$DESTINATION_ROOT"
fi
install -d -o root -g root -m 0755 "$DESTINATION_ROOT/releases"

if [[ -e $UNIT_DESTINATION || -L $UNIT_DESTINATION ]]; then
  [[ -f $UNIT_DESTINATION && ! -L $UNIT_DESTINATION ]] || die "unit_destination_unsafe"
  [[ $(stat -c %u "$UNIT_DESTINATION") == 0 ]] || die "unit_destination_foreign_owner"
fi

RELEASE_PATH=$DESTINATION_ROOT/releases/$ACCEPTED_MASTERMIND_COMMIT
[[ ! -e $RELEASE_PATH && ! -L $RELEASE_PATH ]] || die "release_already_exists"
STAGING_DIR=$(mktemp -d "$DESTINATION_ROOT/.candidate-${ACCEPTED_MASTERMIND_COMMIT}.XXXXXX")
ARCHIVE_PATH=$DESTINATION_ROOT/.archive-${ACCEPTED_MASTERMIND_COMMIT}.$$.tar
UNIT_STAGE=$DESTINATION_ROOT/.unit-${ACCEPTED_MASTERMIND_COMMIT}.$$
cleanup() {
  rm -f -- "$ARCHIVE_PATH" "$UNIT_STAGE"
  if [[ -n ${STAGING_DIR-} && -d $STAGING_DIR ]]; then
    rm -rf -- "$STAGING_DIR"
  fi
}
trap cleanup EXIT

(cd "$SOURCE_REPO" && git archive "$ACCEPTED_MASTERMIND_COMMIT" \
  app/static/chairman_control control_plane scripts/chairman_control_room_remote.py \
  > "$ARCHIVE_PATH")

python3 -I -B - "$ARCHIVE_PATH" <<'PY' || die "archive_member_unsafe"
import pathlib
import sys
import tarfile

with tarfile.open(sys.argv[1], mode="r:") as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
            raise SystemExit(1)
        if not (member.isdir() or member.isreg()):
            raise SystemExit(1)
PY

tar -xf "$ARCHIVE_PATH" -C "$STAGING_DIR" --no-same-owner --no-same-permissions
find "$STAGING_DIR" -type d -exec chmod 0750 {} +
find "$STAGING_DIR" -type f -exec chmod 0640 {} +
chmod 0750 "$STAGING_DIR/scripts/chairman_control_room_remote.py"

MANIFEST_DIGEST=$(python3 -I -B - "$STAGING_DIR" "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, os.fspath(root))
from control_plane import chairman_control_room_remote as remote

manifest = remote.build_release_manifest(root, commit=sys.argv[2], tree=sys.argv[3])
remote.write_release_manifest(root / "control_room_build.json", manifest)
print(manifest["artifact_digest"])
PY
)

python3 -m venv "$STAGING_DIR/venv"
chmod 0640 "$STAGING_DIR/control_room_build.json"
find "$STAGING_DIR/venv" -type d -exec chmod 0750 {} +
find "$STAGING_DIR/venv" -type f -perm /100 -exec chmod 0750 {} +
find "$STAGING_DIR/venv" -type f ! -perm /100 -exec chmod 0640 {} +
chown -R root:"$CADDY_GROUP" "$STAGING_DIR"
chmod -R go-w "$STAGING_DIR"

CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT
sed "s/@EXPECTED_COMMIT@/$CONTROL_ROOM_EXPECTED_COMMIT/g" \
  "$SOURCE_REPO/ops/control_room_remote/mastermind-control-room-remote.service" \
  > "$UNIT_STAGE"
grep -Fq "Environment=CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT" "$UNIT_STAGE" \
  || die "unit_commit_render_failed"

python3 -I -B - "$STAGING_DIR" "$RELEASE_PATH" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
os.replace(source, destination)
directory_fd = os.open(destination.parent, os.O_RDONLY)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
STAGING_DIR=

install -o root -g root -m 0644 "$UNIT_STAGE" "$UNIT_DESTINATION"
systemctl daemon-reload

python3 -I -B - "$DESTINATION_ROOT" "$ACCEPTED_MASTERMIND_COMMIT" <<'PY'
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
commit = sys.argv[2]
current = root / "current"
next_link = root / "current.next"
if os.path.lexists(next_link):
    raise SystemExit("current_next_exists")
if os.path.lexists(current) and not stat.S_ISLNK(current.lstat().st_mode):
    raise SystemExit("current_not_symlink")
os.symlink(f"releases/{commit}", next_link)
directory_fd = os.open(root, os.O_RDONLY)
try:
    os.fsync(directory_fd)
    os.replace(next_link, current)
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY

printf 'RELEASE_INSTALLED commit=%s tree=%s digest=%s release=%s unit=%s\n' \
  "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE" \
  "$MANIFEST_DIGEST" "$RELEASE_PATH" "$UNIT_DESTINATION"
