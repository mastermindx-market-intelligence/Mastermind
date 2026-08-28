#!/usr/bin/env bash
set -euo pipefail
umask 077

SOURCE_REPO=
ACCEPTED_MASTERMIND_COMMIT=
ACCEPTED_MASTERMIND_TREE=
VERIFY_SOURCE_ONLY=0
STAGE_RELEASE_ONLY=
VALIDATE_DIRECTORY_ONLY=
VALIDATE_DIRECTORY_UID=
VALIDATE_DIRECTORY_GID=
VALIDATE_DIRECTORY_MODE=
VALIDATE_DIRECTORY_LABEL=
SERVICE_UID=497
DESTINATION_ROOT=/opt/mastermind-control-room
RELEASES_ROOT=$DESTINATION_ROOT/releases
UNIT_DESTINATION=/etc/systemd/system/mastermind-control-room-remote.service
SERVICE_USER=mastermind-control-room
CADDY_GROUP=caddy
SOURCE_ARTIFACT_ROOT=/var/lib/mastermind-control-room-sources
RELEASE_TRACKED_PATHS=(
  app/static/chairman_control/control_room.css
  app/static/chairman_control/control_room.js
  app/static/chairman_control/remote.html
  common/__init__.py
  common/redaction.py
  config/strategic_state.yml
  control_plane/__init__.py
  control_plane/ceo_boot_packet.py
  control_plane/ceo_intent.py
  control_plane/chairman_control_room.py
  control_plane/chairman_control_room_remote.py
  control_plane/codex_worker.py
  control_plane/executive_agent_capabilities.py
  control_plane/executive_ambient_process.py
  control_plane/executive_authority.py
  control_plane/executive_coo_policy.py
  control_plane/executive_inbox.py
  control_plane/executive_orchestration_principal.py
  control_plane/executive_orchestration_result.py
  control_plane/executive_runtime.py
  control_plane/executive_supervisor.py
  control_plane/executive_worker_broker.py
  control_plane/executive_workspace.py
  control_plane/flags.py
  control_plane/operator_harness_contract.py
  control_plane/operator_harness_wire.py
  control_plane/strategic_state.py
  control_plane/surface_bindings.py
  control_plane/worker_adapter.py
  ops/control_room_remote/mastermind-control-room-remote.service
  scripts/__init__.py
  scripts/chairman_control_room_remote.py
  scripts/ohf/__init__.py
  scripts/ohf/redaction.py
)

die() {
  printf '%s\n' "$1" >&2
  exit 65
}

verify_existing_directory() {
  local path=$1
  local expected_uid=$2
  local expected_gid=$3
  local expected_mode=$4
  local label=$5
  local reason
  if ! reason=$(python3 -I -B - "$path" "$expected_uid" "$expected_gid" "$expected_mode" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
info = path.lstat()
if stat.S_ISLNK(info.st_mode):
    print("symlink")
    raise SystemExit(1)
if not stat.S_ISDIR(info.st_mode):
    print("type")
    raise SystemExit(1)
if info.st_uid != int(sys.argv[2]):
    print("owner")
    raise SystemExit(1)
if info.st_gid != int(sys.argv[3]):
    print("group")
    raise SystemExit(1)
if stat.S_IMODE(info.st_mode) != int(sys.argv[4], 8):
    print("mode")
    raise SystemExit(1)
PY
  ); then
    die "${label}_${reason:-unsafe}"
  fi
}

while (($#)); do
  case "$1" in
    --source-repo) SOURCE_REPO=${2-}; shift 2 ;;
    --accepted-commit) ACCEPTED_MASTERMIND_COMMIT=${2-}; shift 2 ;;
    --accepted-tree) ACCEPTED_MASTERMIND_TREE=${2-}; shift 2 ;;
    --service-uid) SERVICE_UID=${2-}; shift 2 ;;
    --verify-source-only) VERIFY_SOURCE_ONLY=1; shift ;;
    --stage-release-only) STAGE_RELEASE_ONLY=${2-}; shift 2 ;;
    --validate-directory-only)
      VALIDATE_DIRECTORY_ONLY=${2-}
      VALIDATE_DIRECTORY_UID=${3-}
      VALIDATE_DIRECTORY_GID=${4-}
      VALIDATE_DIRECTORY_MODE=${5-}
      VALIDATE_DIRECTORY_LABEL=${6-}
      shift 6
      ;;
    *) die "unknown_argument" ;;
  esac
done

if [[ -n $VALIDATE_DIRECTORY_ONLY ]]; then
  [[ $VALIDATE_DIRECTORY_ONLY == /* ]] || die "validate_directory_not_absolute"
  [[ $VALIDATE_DIRECTORY_UID =~ ^[0-9]+$ ]] || die "validate_directory_uid_invalid"
  [[ $VALIDATE_DIRECTORY_GID =~ ^[0-9]+$ ]] || die "validate_directory_gid_invalid"
  [[ $VALIDATE_DIRECTORY_MODE =~ ^0[0-7]{3}$ ]] || die "validate_directory_mode_invalid"
  [[ $VALIDATE_DIRECTORY_LABEL =~ ^[a-z_]+$ ]] || die "validate_directory_label_invalid"
  verify_existing_directory \
    "$VALIDATE_DIRECTORY_ONLY" "$VALIDATE_DIRECTORY_UID" \
    "$VALIDATE_DIRECTORY_GID" "$VALIDATE_DIRECTORY_MODE" \
    "$VALIDATE_DIRECTORY_LABEL"
  printf 'DIRECTORY_VERIFIED path=%s\n' "$VALIDATE_DIRECTORY_ONLY"
  exit 0
fi

[[ $SOURCE_REPO == /* ]] || die "source_repo_not_absolute"
[[ $ACCEPTED_MASTERMIND_COMMIT =~ ^[0-9a-f]{40}$ ]] || die "accepted_commit_invalid"
[[ $ACCEPTED_MASTERMIND_TREE =~ ^[0-9a-f]{40}$ ]] || die "accepted_tree_invalid"
[[ $SERVICE_UID =~ ^[1-9][0-9]*$ ]] || die "service_uid_invalid"
[[ -d $SOURCE_REPO && ! -L $SOURCE_REPO ]] || die "source_repo_invalid"
(( VERIFY_SOURCE_ONLY == 0 || ${#STAGE_RELEASE_ONLY} == 0 )) || die "verification_modes_conflict"

# Keep these identity checks explicit: git status --porcelain, git rev-parse
# HEAD, and git rev-parse HEAD^{tree} must all agree before git archive runs.
SOURCE_STATUS=$(cd "$SOURCE_REPO" && git status --porcelain --untracked-files=all)
[[ -z $SOURCE_STATUS ]] || die "source_repo_dirty"
SOURCE_HEAD=$(cd "$SOURCE_REPO" && git rev-parse HEAD)
SOURCE_TREE=$(cd "$SOURCE_REPO" && git rev-parse 'HEAD^{tree}')
[[ $SOURCE_HEAD == "$ACCEPTED_MASTERMIND_COMMIT" ]] || die "source_commit_mismatch"
[[ $SOURCE_TREE == "$ACCEPTED_MASTERMIND_TREE" ]] || die "source_tree_mismatch"

python3 -I -B - "$SOURCE_REPO" "$ACCEPTED_MASTERMIND_COMMIT" \
  "${RELEASE_TRACKED_PATHS[@]}" <<'PY' || die "source_member_unsafe"
import os
import stat
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
commit = sys.argv[2]
requested = sys.argv[3:]
root_info = root.lstat()
listed = subprocess.run(
    [
        "git", "-C", os.fspath(root), "ls-files", "-z", "--", *requested,
    ],
    check=True,
    capture_output=True,
).stdout.split(b"\0")
if not listed or listed == [b""]:
    raise SystemExit(1)
decoded = [item.decode("utf-8", errors="strict") for item in listed if item]
if len(decoded) != len(set(decoded)) or set(decoded) != set(requested):
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
    if info.st_uid != root_info.st_uid:
        raise SystemExit(1)
    if info.st_nlink != 1 or info.st_mode & 0o022:
        raise SystemExit(1)
    if not hasattr(os, "O_NOFOLLOW"):
        raise SystemExit(1)
    descriptor = os.open(candidate, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise SystemExit(1)
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 16 * 1024 * 1024:
                raise SystemExit(1)
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    accepted = subprocess.run(
        ["git", "-C", os.fspath(root), "show", f"{commit}:{relative}"],
        check=True,
        capture_output=True,
    ).stdout
    if b"".join(chunks) != accepted:
        raise SystemExit(1)
PY

if ((VERIFY_SOURCE_ONLY)); then
  printf 'SOURCE_VERIFIED commit=%s tree=%s\n' \
    "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE"
  exit 0
fi

STAGING_DIR=
ARCHIVE_PATH=
UNIT_STAGE=
cleanup() {
  if [[ -n ${ARCHIVE_PATH-} ]]; then rm -f -- "$ARCHIVE_PATH"; fi
  if [[ -n ${UNIT_STAGE-} ]]; then rm -f -- "$UNIT_STAGE"; fi
  if [[ -n ${STAGING_DIR-} && -d $STAGING_DIR ]]; then
    rm -rf -- "$STAGING_DIR"
  fi
}
trap cleanup EXIT

publish_staging() {
  local source=$1
  local destination=$2
  python3 -I -B - "$source" "$destination" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
if os.path.lexists(destination):
    raise SystemExit("destination_exists")
os.replace(source, destination)
directory_fd = os.open(destination.parent, os.O_RDONLY)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
}

materialize_archive() {
  local staging=$1
  local archive=$2
  (cd "$SOURCE_REPO" && git archive "$ACCEPTED_MASTERMIND_COMMIT" \
    "${RELEASE_TRACKED_PATHS[@]}" > "$archive")

  python3 -I -B - "$archive" <<'PY' || die "archive_member_unsafe"
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

  tar -xf "$archive" -C "$staging" --no-same-owner --no-same-permissions
  find "$staging" -type d -exec chmod 0750 {} +
  find "$staging" -type f -exec chmod 0640 {} +
  chmod 0750 "$staging/scripts/chairman_control_room_remote.py"

  python3 -I -B - "$staging/ops/control_room_remote/mastermind-control-room-remote.service" <<'PY' \
    || die "unit_template_contract_invalid"
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
required_once = (
    "Type=simple",
    "User=mastermind-control-room",
    "Group=caddy",
    "RuntimeDirectory=mastermind-control-room",
    "RuntimeDirectoryMode=0750",
    "UMask=0007",
    "Environment=CONTROL_ROOM_EXPECTED_COMMIT=@EXPECTED_COMMIT@",
    "ExecStart=/usr/bin/python3 -I -B /opt/mastermind-control-room/current/scripts/chairman_control_room_remote.py --repo-root /opt/mastermind-control-room/current --macro-root /opt/macro --expected-commit ${CONTROL_ROOM_EXPECTED_COMMIT} --build-metadata /opt/mastermind-control-room/current/control_room_build.json",
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectSystem=strict",
    "ProtectHome=true",
    "RestrictAddressFamilies=AF_UNIX",
    "ReadWritePaths=/run/mastermind-control-room",
    "Restart=on-failure",
)
lines = text.splitlines()
if any(lines.count(line) != 1 for line in required_once):
    raise SystemExit(1)
if text.count("@EXPECTED_COMMIT@") != 1:
    raise SystemExit(1)
if sum(line.startswith("ExecStart=") for line in lines) != 1:
    raise SystemExit(1)
for forbidden in (
    "AF_INET", "AF_INET6", "EnvironmentFile", "CAP_NET_BIND_SERVICE",
    " --host ", " --port ", " --bind ", " --socket ",
):
    if forbidden in text:
        raise SystemExit(1)
PY

  python3 -I -B - "$staging" "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE" <<'PY'
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
}

if [[ -n $STAGE_RELEASE_ONLY ]]; then
  [[ $STAGE_RELEASE_ONLY == /* ]] || die "stage_destination_not_absolute"
  [[ ! -e $STAGE_RELEASE_ONLY && ! -L $STAGE_RELEASE_ONLY ]] || die "stage_destination_exists"
  STAGE_PARENT=$(dirname "$STAGE_RELEASE_ONLY")
  [[ -d $STAGE_PARENT && ! -L $STAGE_PARENT ]] || die "stage_parent_unsafe"
  python3 -I -B - "$STAGE_PARENT" <<'PY' || die "stage_parent_foreign_owner"
import os
import sys
from pathlib import Path

if Path(sys.argv[1]).lstat().st_uid != os.getuid():
    raise SystemExit(1)
PY
  STAGING_DIR=$(mktemp -d "$STAGE_PARENT/.candidate-${ACCEPTED_MASTERMIND_COMMIT}.XXXXXX")
  ARCHIVE_PATH=$STAGE_PARENT/.archive-${ACCEPTED_MASTERMIND_COMMIT}.$$.tar
  MANIFEST_DIGEST=$(materialize_archive "$STAGING_DIR" "$ARCHIVE_PATH")
  publish_staging "$STAGING_DIR" "$STAGE_RELEASE_ONLY"
  STAGING_DIR=
  printf 'RELEASE_STAGED commit=%s tree=%s digest=%s release=%s\n' \
    "$ACCEPTED_MASTERMIND_COMMIT" "$ACCEPTED_MASTERMIND_TREE" \
    "$MANIFEST_DIGEST" "$STAGE_RELEASE_ONLY"
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
if [[ -e $SOURCE_ARTIFACT_ROOT || -L $SOURCE_ARTIFACT_ROOT ]]; then
  verify_existing_directory "$SOURCE_ARTIFACT_ROOT" 0 "$CADDY_GID" 0750 source_artifact_root
else
  install -d -o root -g "$CADDY_GROUP" -m 0750 "$SOURCE_ARTIFACT_ROOT"
fi

if [[ -e $DESTINATION_ROOT || -L $DESTINATION_ROOT ]]; then
  [[ -d $DESTINATION_ROOT && ! -L $DESTINATION_ROOT ]] || die "destination_root_unsafe"
  [[ $(stat -c %u "$DESTINATION_ROOT") == 0 ]] || die "destination_root_foreign_owner"
  (( (8#$(stat -c %a "$DESTINATION_ROOT") & 8#022) == 0 )) \
    || die "destination_root_writable"
else
  install -d -o root -g root -m 0755 "$DESTINATION_ROOT"
fi
if [[ -e $RELEASES_ROOT || -L $RELEASES_ROOT ]]; then
  verify_existing_directory "$RELEASES_ROOT" 0 0 0755 releases_root
else
  install -d -o root -g root -m 0755 "$RELEASES_ROOT"
fi

if [[ -e $UNIT_DESTINATION || -L $UNIT_DESTINATION ]]; then
  [[ -f $UNIT_DESTINATION && ! -L $UNIT_DESTINATION ]] || die "unit_destination_unsafe"
  [[ $(stat -c %u "$UNIT_DESTINATION") == 0 ]] || die "unit_destination_foreign_owner"
  (( (8#$(stat -c %a "$UNIT_DESTINATION") & 8#022) == 0 )) \
    || die "unit_destination_writable"
fi

RELEASE_PATH=$RELEASES_ROOT/$ACCEPTED_MASTERMIND_COMMIT
[[ ! -e $RELEASE_PATH && ! -L $RELEASE_PATH ]] || die "release_already_exists"
STAGING_DIR=$(mktemp -d "$DESTINATION_ROOT/.candidate-${ACCEPTED_MASTERMIND_COMMIT}.XXXXXX")
ARCHIVE_PATH=$DESTINATION_ROOT/.archive-${ACCEPTED_MASTERMIND_COMMIT}.$$.tar
UNIT_STAGE=$DESTINATION_ROOT/.unit-${ACCEPTED_MASTERMIND_COMMIT}.$$
MANIFEST_DIGEST=$(materialize_archive "$STAGING_DIR" "$ARCHIVE_PATH")

CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT
sed "s/@EXPECTED_COMMIT@/$CONTROL_ROOM_EXPECTED_COMMIT/g" \
  "$STAGING_DIR/ops/control_room_remote/mastermind-control-room-remote.service" \
  > "$UNIT_STAGE"
grep -Fq "Environment=CONTROL_ROOM_EXPECTED_COMMIT=$ACCEPTED_MASTERMIND_COMMIT" "$UNIT_STAGE" \
  || die "unit_commit_render_failed"
if grep -Fq '@EXPECTED_COMMIT@' "$UNIT_STAGE"; then die "unit_placeholder_remained"; fi

chmod 0640 "$STAGING_DIR/control_room_build.json"
chown -R root:"$CADDY_GROUP" "$STAGING_DIR"
chmod -R go-w "$STAGING_DIR"

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

publish_staging "$STAGING_DIR" "$RELEASE_PATH"
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
