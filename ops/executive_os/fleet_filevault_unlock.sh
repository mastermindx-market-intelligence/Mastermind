#!/bin/bash
# Interactive break-glass FileVault preboot unlock for the four enrolled Minis.
#
# This launcher never accepts a password in argv or environment and never reads a
# password from a file/keychain. It permits exactly one interactive SSH password
# attempt after a read-only preflight proves the expected FileVault-preboot
# signature, then reconciles by waiting for normal public-key SSH to return.
set -euo pipefail
umask 077

SSH="/usr/bin/ssh"
NC="/usr/bin/nc"
GREP="/usr/bin/grep"
MKTEMP="/usr/bin/mktemp"
RM="/bin/rm"
SLEEP="/bin/sleep"

if [ "$#" -ne 1 ]; then
  /bin/echo "usage: $0 {mini1|mini2|mini3|mini4}" >&2
  exit 64
fi

case "$1" in
  mini1|mini2|mini3|mini4) HOST="$1" ;;
  *) /bin/echo "unknown enrolled Mini" >&2; exit 65 ;;
esac

ALIAS="mmx-$HOST"
DEBUG_LOG="$($MKTEMP "/private/tmp/mastermind-filevault-preflight.$HOST.XXXXXX")"
cleanup() {
  $RM -f -- "$DEBUG_LOG"
}
trap cleanup EXIT

SSH_COMMON=(
  -o BatchMode=yes
  -o ConnectTimeout=6
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o StrictHostKeyChecking=yes
  -o NumberOfPasswordPrompts=0
)

# A successful key-auth probe means the data volume is already mounted. Never
# solicit a password in that state.
set +e
"$SSH" -v "${SSH_COMMON[@]}" "$ALIAS" /usr/bin/true   >/dev/null 2>"$DEBUG_LOG"
KEY_RC=$?
set -e
if [ "$KEY_RC" -eq 0 ]; then
  /bin/echo "ALREADY_BOOTED host=$HOST"
  exit 0
fi

# Refuse to reinterpret arbitrary SSH key failures as FileVault preboot.
# Apple's preboot SSH path exposes password and keyboard-interactive while the
# ordinary per-user authorized_keys path is unavailable on the locked volume.
$GREP -qi 'Authentications that can continue:.*password' "$DEBUG_LOG"   || { /bin/echo "PREBOOT_NOT_PROVEN host=$HOST code=PASSWORD_AUTH_NOT_ADVERTISED" >&2; exit 65; }
$GREP -qi 'Authentications that can continue:.*keyboard-interactive' "$DEBUG_LOG"   || { /bin/echo "PREBOOT_NOT_PROVEN host=$HOST code=INTERACTIVE_AUTH_NOT_ADVERTISED" >&2; exit 65; }

# On this enrolled Mini fleet, Screen Sharing or ARD reachable while public-key
# SSH fails is not the stranded preboot state this launcher is allowed to act on.
if "$NC" -G 1 -z "$HOST.local" 5900 >/dev/null 2>&1   || "$NC" -G 1 -z "$HOST.local" 3283 >/dev/null 2>&1; then
  /bin/echo "PREBOOT_NOT_PROVEN host=$HOST code=GUI_RECOVERY_REACHABLE" >&2
  exit 65
fi

/bin/echo "FILEVAULT_PREBOOT_CONFIRMED_FOR_INTERACTIVE_UNLOCK host=$HOST"
/bin/echo "Enter the $HOST login password at the SSH prompt. The password is not logged."

if [ ! -t 0 ] || [ ! -t 1 ]; then
  /bin/echo "INTERACTIVE_TTY_REQUIRED host=$HOST" >&2
  exit 66
fi
unset SSH_ASKPASS SSH_ASKPASS_REQUIRE DISPLAY

# Exactly one interactive password attempt. The expected successful preboot
# effect is an SSH disconnect while macOS mounts the data volume. Therefore the
# child's exit code is never treated as success/failure evidence.
set +e
"$SSH" -tt   -o BatchMode=no   -o ConnectTimeout=8   -o PubkeyAuthentication=no   -o PasswordAuthentication=yes   -o KbdInteractiveAuthentication=yes   -o PreferredAuthentications=password,keyboard-interactive   -o NumberOfPasswordPrompts=1   -o StrictHostKeyChecking=yes   "$ALIAS" /usr/bin/true
UNLOCK_SSH_RC=$?
set -e

# Reconcile only. Never replay the password effect. A confirmed return of the
# exact normal key-auth path proves the volume mounted and normal sshd resumed.
for attempt in {1..24}; do
  if "$SSH" "${SSH_COMMON[@]}" "$ALIAS" /usr/bin/true >/dev/null 2>&1; then
    /bin/echo "UNLOCK_CONFIRMED host=$HOST normal_ssh=ready password_ssh_rc=$UNLOCK_SSH_RC"
    exit 0
  fi
  "$SLEEP" 5
done

/bin/echo "UNLOCK_EFFECT_UNKNOWN host=$HOST normal_ssh=not_ready password_ssh_rc=$UNLOCK_SSH_RC" >&2
exit 75
