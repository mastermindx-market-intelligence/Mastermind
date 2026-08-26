#!/bin/bash
# Prepare the inert, credential-free CF2-H0 capacity source foundation.
set -euo pipefail
umask 077

SCRIPT_DIR="$(/usr/bin/dirname "${BASH_SOURCE[0]}")"
MASTERMIND_SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"
CONTRACT="$SCRIPT_DIR/capacity_source_contract.py"
SLOT_RESOLVER="$SCRIPT_DIR/provider_worker_slots.py"
PYTHON_PROVISIONER="$SCRIPT_DIR/provision-python-runtime.sh"

MACRO_ORIGIN="https://github.com/mastermindx-market-intelligence/macro.git"
MACRO_COMMIT="dcdd939c45b23abce5ba04f95e330ac914a3904b"
MATERIAL_SOURCE_DIGEST="35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"
PYTHON_VERSION="3.12.10"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
PYTHON_BINARY_SHA256="d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
PYYAML_VERSION="6.0.3"
PYYAML_WHEEL="pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"
PYYAML_WHEEL_SHA256="fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0"
SOURCE_CONFIG_SCHEMA="mastermind.executive_capacity_source_config/v1"
HOST_RECEIPT_SCHEMA="mastermind.executive_capacity_host_preparation/v1"

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
SOURCE_PARENT="$SYSTEM_ROOT/capacity-sources/macro"
SOURCE_ROOT="$SOURCE_PARENT/$MACRO_COMMIT"
RUNTIME_PARENT="$SYSTEM_ROOT/capacity-runtimes"
RUNTIME_ROOT="$RUNTIME_PARENT/cf1-pyyaml-6.0.3-cp312-arm64"
GENERATION_ROOT="$SYSTEM_ROOT/capacity-generations"
STAGING_ROOT="$SYSTEM_ROOT/capacity-staging"
ARCHIVE_ROOT="$SYSTEM_ROOT/capacity-archive"
TELEMETRY_ROOT="/var/db/mastermind-executive/capacity-telemetry"
AI_COSTS_STATE_ROOT="$TELEMETRY_ROOT/ai-costs"
CONTROL_USER="_mastermind_exec"
PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")
MATERIAL_PATHS=(
  "config/capability_manifest.yml"
  "config/metabolism_budget.yml"
  "engine/codex_lane/runner.py"
  "engine/codex_provider.py"
  "engine/llm_auth.py"
  "engine/metabolism/budget_gate.py"
  "engine/neuralweb/key_pool.py"
  "engine/provider_capacity.py"
  "engine/provider_health.py"
  "lib/ai_costs.py"
  "scripts/build_provider_capacity.py"
)

EXPECTED_MASTERMIND_SHA=""
OPERATOR_USER=""
MACRO_SOURCE_TRANSPORT=""
WHEEL_SOURCE=""
VERIFY_ONLY="false"

MUTATION_STARTED="false"
INSTALL_COMPLETE="false"
CONFIG_INSTALLED="false"
RECEIPT_INSTALLED="false"
STAGING_SESSION=""
SOURCE_STAGE=""
RUNTIME_STAGE=""
WHEEL_STAGE=""
GENERATION_STAGE=""

usage() {
  /bin/echo "usage: sudo /bin/bash $0 --expected-mastermind-sha SHA [--verify-only | --operator-user NAME --macro-source PATH --pyyaml-wheel PATH]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-mastermind-sha) EXPECTED_MASTERMIND_SHA="${2:-}"; shift 2 ;;
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    --macro-source) MACRO_SOURCE_TRANSPORT="${2:-}"; shift 2 ;;
    --pyyaml-wheel) WHEEL_SOURCE="${2:-}"; shift 2 ;;
    --verify-only) VERIFY_ONLY="true"; shift ;;
    *) usage ;;
  esac
done

refuse() {
  /bin/echo "capacity host preparation refused: $1" >&2
  exit 65
}

case "$EXPECTED_MASTERMIND_SHA" in
  ''|*[!0-9a-f]*) refuse "expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters" ;;
esac
[ "${#EXPECTED_MASTERMIND_SHA}" -eq 40 ] || {
  refuse "expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters"
}
[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "prepare-capacity-host.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "prepare-capacity-host.sh supports macOS only" >&2
  exit 69
}
[ -d "$MASTERMIND_SOURCE_REPO/.git" ] && [ ! -L "$MASTERMIND_SOURCE_REPO/.git" ] || {
  refuse "Mastermind source must be a direct Git checkout"
}
[ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] || refuse "capacity contract is unavailable"
[ -f "$SLOT_RESOLVER" ] && [ ! -L "$SLOT_RESOLVER" ] || refuse "slot resolver is unavailable"
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || refuse "reviewed Python is unavailable"
[ "$(/usr/bin/shasum -a 256 "$PYTHON_BINARY" | /usr/bin/awk '{print $1}')" = "$PYTHON_BINARY_SHA256" ] || {
  refuse "reviewed Python digest differs"
}
[ "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse HEAD)" = "$EXPECTED_MASTERMIND_SHA" ] || {
  refuse "Mastermind source HEAD differs from the explicit merged SHA"
}
[ -z "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" status --porcelain=v1)" ] || {
  refuse "Mastermind source tree is not clean"
}
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_REPO" ! -user root -print -quit)" ] || {
  refuse "source tree contains a non-root-owned object"
}
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_REPO" -perm +022 -print -quit)" ] || {
  refuse "source tree contains a group/other-writable object"
}
"$PYTHON_PROVISIONER" --verify-only >/dev/null || refuse "reviewed Python receipt did not verify"

slot_field() {
  local slot_id="$1"
  local field="$2"
  /usr/bin/python3 -I -S -B "$SLOT_RESOLVER" "$slot_id" "$field"
}

assert_no_acl() {
  local inspected="$1"
  if [ -n "$(/usr/bin/find "$inspected" -exec /usr/bin/stat -f '%Sp' {} \; \
    | /usr/bin/awk '/\+/{found=1} END {if(found) print "ACL"}')" ]; then
    refuse "installed object contains a filesystem ACL"
  fi
}

verify_runtime_tree() {
  local inspected="$1"
  [ -d "$inspected" ] && [ ! -L "$inspected" ] || return 1
  [ -f "$inspected/bin/python3.12" ] && [ -x "$inspected/bin/python3.12" ] \
    && [ ! -L "$inspected/bin/python3.12" ] || return 1
  [ "$(/usr/bin/shasum -a 256 "$inspected/bin/python3.12" | /usr/bin/awk '{print $1}')" = "$PYTHON_BINARY_SHA256" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" ! -user root -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -perm +022 -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -type l -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -type f -links +1 -print -quit)" ] || return 1
  assert_no_acl "$inspected"
  PYTHONNOUSERSITE=1 "$inspected/bin/python3.12" -I -B - "$inspected" "$PYYAML_VERSION" <<'PY'
import hashlib
import importlib.metadata
import pathlib
import site
import sys

import _yaml
import yaml

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
expected_version = sys.argv[2]
if pathlib.Path(sys.prefix).resolve(strict=True) != root:
    raise RuntimeError("capacity Python prefix differs from its runtime")
if pathlib.Path(sys.base_prefix).resolve(strict=True) == root:
    raise RuntimeError("capacity Python did not retain the attested base prefix")
if site.ENABLE_USER_SITE:
    raise RuntimeError("capacity Python user site is enabled")
if yaml.__version__ != expected_version:
    raise RuntimeError("PyYAML version differs")
for module in (yaml, _yaml):
    origin = pathlib.Path(module.__file__).resolve(strict=True)
    if root not in origin.parents:
        raise RuntimeError("PyYAML import origin escapes the capacity runtime")
    if "/Users/" in str(origin):
        raise RuntimeError("PyYAML import origin enters an interactive user tree")
distribution = importlib.metadata.distribution("PyYAML")
record = distribution.locate_file("PyYAML-6.0.3.dist-info/RECORD").resolve(strict=True)
if root not in record.parents:
    raise RuntimeError("PyYAML RECORD escapes the capacity runtime")
print(hashlib.sha256(record.read_bytes()).hexdigest())
PY
}

isolated_git() {
  /usr/bin/env -i \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_TERMINAL_PROMPT=0 GIT_OPTIONAL_LOCKS=0 \
    "$@"
}

verify_source_tree() {
  local inspected="$1"
  local file_path
  [ -d "$inspected" ] && [ ! -L "$inspected" ] || return 1
  [ -d "$inspected/.git" ] && [ ! -L "$inspected/.git" ] || return 1
  [ "$(isolated_git /usr/bin/git -C "$inspected" rev-parse HEAD)" = "$MACRO_COMMIT" ] || return 1
  if isolated_git /usr/bin/git -C "$inspected" symbolic-ref -q HEAD >/dev/null 2>&1; then
    return 1
  fi
  [ -z "$(isolated_git /usr/bin/git -C "$inspected" status --porcelain=v1)" ] || return 1
  [ -z "$(isolated_git /usr/bin/git -C "$inspected" remote)" ] || return 1
  isolated_git /usr/bin/git -C "$inspected" fsck --full --strict --no-progress >/dev/null || return 1
  [ -z "$(isolated_git /usr/bin/git -C "$inspected" ls-files -s \
    | /usr/bin/awk '$1 == "120000" || $1 == "160000" {print; exit}')" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -type l -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" ! -user root -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -perm +022 -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected" -type f -links +1 -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$inspected/.git/hooks" -type f -perm +111 -print -quit 2>/dev/null)" ] || return 1
  [ ! -e "$inspected/.git/objects/info/alternates" ] || return 1
  [ -z "$(isolated_git /usr/bin/git -C "$inspected" config --local --get-all credential.helper 2>/dev/null || true)" ] || return 1
  [ -z "$(isolated_git /usr/bin/git -C "$inspected" for-each-ref refs/replace)" ] || return 1
  assert_no_acl "$inspected"
  for file_path in "${MATERIAL_PATHS[@]}"; do
    [ -f "$inspected/$file_path" ] && [ ! -L "$inspected/$file_path" ] || return 1
  done
}

observe_material_digest() {
  local inspected_source="$1"
  local inspected_runtime="$2"
  local execution_user="${3:-root}"
  local runner=(/usr/bin/env -i)
  if [ "$execution_user" != root ]; then
    runner=(/usr/bin/sudo -u "$execution_user" /usr/bin/env -i)
  fi
  "${runner[@]}" \
    HOME=/var/empty PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$inspected_source" \
    GIT_TERMINAL_PROMPT=0 GIT_OPTIONAL_LOCKS=0 \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    "$inspected_runtime/bin/python3.12" -I -B - "$inspected_source" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
from engine.provider_capacity import material_source_receipt

receipt = material_source_receipt(root)
if not receipt.material_sources_match_commit:
    raise RuntimeError("material sources do not match the accepted commit")
print(receipt.material_source_digest)
PY
}

assert_control_outside_group() {
  local group="$1"
  local gid="$2"
  local membership
  membership="$(/usr/sbin/dseditgroup -o checkmember -m "$CONTROL_USER" "$group" 2>&1 || true)"
  case "$membership" in
    *"is not a member"*) ;;
    *) refuse "control principal is a member of a Personal Pro group" ;;
  esac
  case " $(/usr/bin/id -G "$CONTROL_USER") " in
    *" $gid "*) refuse "control principal resolves a Personal Pro GID" ;;
  esac
}

verify_empty_realms() {
  local slot_id slot_user slot_group slot_uid slot_gid slot_home
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    slot_user="$(slot_field "$slot_id" worker_user)"
    slot_group="$(slot_field "$slot_id" worker_group)"
    slot_uid="$(slot_field "$slot_id" worker_uid)"
    slot_gid="$(slot_field "$slot_id" worker_gid)"
    slot_home="$(slot_field "$slot_id" provider_home)"
    [ "$(/usr/bin/id -u "$slot_user")" = "$slot_uid" ] || refuse "worker UID differs"
    [ "$(/usr/bin/id -g "$slot_user")" = "$slot_gid" ] || refuse "worker GID differs"
    [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$slot_home")" = "$slot_uid:$slot_gid:700" ] || {
      refuse "realm home metadata differs"
    }
    [ -z "$(/usr/bin/find "$slot_home" -mindepth 1 -print -quit)" ] || {
      refuse "realm home contains pre-existing material"
    }
    assert_control_outside_group "$slot_group" "$slot_gid"
    /usr/bin/sudo -u "$CONTROL_USER" /usr/bin/test ! -r "$slot_home" || {
      refuse "control principal can read a Personal Pro home"
    }
    /usr/bin/sudo -u "$CONTROL_USER" /usr/bin/test ! -x "$slot_home" || {
      refuse "control principal can traverse a Personal Pro home"
    }
  done
}

verify_telemetry_boundary() {
  [ "$(/usr/bin/stat -f '%Su:%Sg:%Lp' "$TELEMETRY_ROOT")" = "$CONTROL_USER:$CONTROL_USER:700" ] || return 1
  [ "$(/usr/bin/stat -f '%Su:%Sg:%Lp' "$AI_COSTS_STATE_ROOT")" = "$CONTROL_USER:$CONTROL_USER:700" ] || return 1
  [ -z "$(/usr/bin/find "$TELEMETRY_ROOT" -mindepth 2 -print -quit)" ] || return 1
}

verify_generation() {
  local generation="$1"
  [ -d "$generation" ] && [ ! -L "$generation" ] || return 1
  [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$generation")" = "0:0:555" ] || return 1
  for artifact in components.json source-config.json host-preparation-receipt.json; do
    [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$generation/$artifact")" = "0:0:444:1" ] || return 1
  done
  assert_no_acl "$generation"
  /usr/bin/python3 -I -S -B "$CONTRACT" verify \
    --components "$generation/components.json" \
    --config "$generation/source-config.json" \
    --receipt "$generation/host-preparation-receipt.json" >/dev/null
  /usr/bin/python3 -I -S -B - "$generation" "$EXPECTED_MASTERMIND_SHA" <<'PY'
import json
import pathlib
import sys

generation = pathlib.Path(sys.argv[1]).resolve(strict=True)
expected_mastermind = sys.argv[2]
receipt = json.loads(
    (generation / "host-preparation-receipt.json").read_text(encoding="utf-8")
)
if receipt.get("installed_mastermind_commit") != expected_mastermind:
    raise RuntimeError("generation Mastermind identity differs")
if generation.name != receipt.get("source_config_digest"):
    raise RuntimeError("generation directory does not match the source config digest")
PY
}

verify_installed_host() {
  local observed_material observed_record generations generation_count generation
  verify_source_tree "$SOURCE_ROOT" || refuse "installed Macro source did not verify"
  observed_record="$(verify_runtime_tree "$RUNTIME_ROOT")" || refuse "installed capacity runtime did not verify"
  observed_material="$(observe_material_digest "$SOURCE_ROOT" "$RUNTIME_ROOT" "$CONTROL_USER")" || {
    refuse "installed material receipt did not verify under the control principal"
  }
  [ "$observed_material" = "$MATERIAL_SOURCE_DIGEST" ] || refuse "installed material digest differs"
  verify_empty_realms
  verify_telemetry_boundary || refuse "telemetry absence boundary did not verify"
  generations="$(/usr/bin/find "$GENERATION_ROOT" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null || true)"
  generation_count="$(/bin/echo "$generations" | /usr/bin/awk 'NF {count++} END {print count+0}')"
  [ "$generation_count" -eq 1 ] || refuse "capacity generation inventory is ambiguous"
  generation="$generations"
  verify_generation "$generation" || refuse "installed capacity generation did not verify"
  /bin/echo "PREPARED_NOT_P0_ACCEPTED"
}

if [ "$VERIFY_ONLY" = "true" ]; then
  verify_installed_host
  exit 0
fi

[ -n "$OPERATOR_USER" ] && [ -n "$MACRO_SOURCE_TRANSPORT" ] && [ -n "$WHEEL_SOURCE" ] || usage
/usr/bin/id "$OPERATOR_USER" >/dev/null 2>&1 || refuse "operator account does not exist"
case "$MACRO_SOURCE_TRANSPORT" in /*) ;; *) refuse "Macro source transport path must be absolute" ;; esac
case "$WHEEL_SOURCE" in /*) ;; *) refuse "PyYAML wheel path must be absolute" ;; esac
[ -d "$MACRO_SOURCE_TRANSPORT" ] && [ ! -L "$MACRO_SOURCE_TRANSPORT" ] \
  && [ -d "$MACRO_SOURCE_TRANSPORT/.git" ] && [ ! -L "$MACRO_SOURCE_TRANSPORT/.git" ] \
  || refuse "Macro source transport is not a direct Git checkout"
[ -f "$WHEEL_SOURCE" ] && [ ! -L "$WHEEL_SOURCE" ] || refuse "PyYAML wheel is not a direct file"
[ "$(/usr/bin/basename "$WHEEL_SOURCE")" = "$PYYAML_WHEEL" ] || refuse "PyYAML wheel filename differs"

archive_partial_stage() {
  local disposition="$1"
  local destination
  [ -n "$STAGING_SESSION" ] && [ -d "$STAGING_SESSION" ] || return 0
  /usr/bin/install -d -o root -g wheel -m 0700 "$ARCHIVE_ROOT" || return 0
  destination="$ARCHIVE_ROOT/$disposition-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
  /bin/mv "$STAGING_SESSION" "$destination" 2>/dev/null || true
  STAGING_SESSION=""
}

cleanup() {
  local status="$?"
  if [ "$MUTATION_STARTED" = "true" ]; then
    if [ "$INSTALL_COMPLETE" = "true" ] && [ "$status" -eq 0 ]; then
      archive_partial_stage "completed-transport"
    else
      archive_partial_stage "failed-stage"
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

MUTATION_STARTED="true"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT"
/usr/bin/install -d -o root -g wheel -m 0700 "$STAGING_ROOT"
/usr/bin/install -d -o root -g wheel -m 0700 "$ARCHIVE_ROOT"
STAGING_SESSION="$(/usr/bin/mktemp -d "$STAGING_ROOT/cf2-h0.XXXXXX")"
SOURCE_STAGE="$STAGING_SESSION/source"
RUNTIME_STAGE="$STAGING_SESSION/runtime"
WHEEL_STAGE="$STAGING_SESSION/$PYYAML_WHEEL"
GENERATION_STAGE="$STAGING_SESSION/generation"

/usr/bin/ditto --noqtn "$MACRO_SOURCE_TRANSPORT" "$SOURCE_STAGE"
/usr/bin/ditto --noqtn "$WHEEL_SOURCE" "$WHEEL_STAGE"
OBSERVED_WHEEL_SHA256="$(/usr/bin/shasum -a 256 "$WHEEL_STAGE" | /usr/bin/awk '{print $1}')"
[ "$OBSERVED_WHEEL_SHA256" = "$PYYAML_WHEEL_SHA256" ] || refuse "PyYAML wheel digest differs"

/usr/sbin/chown -R root:wheel "$SOURCE_STAGE"
[ "$(isolated_git /usr/bin/git -C "$SOURCE_STAGE" rev-parse HEAD)" = "$MACRO_COMMIT" ] \
  || refuse "Macro source transport HEAD differs"
[ "$(isolated_git /usr/bin/git -C "$SOURCE_STAGE" remote)" = "origin" ] \
  || refuse "Macro source transport remote inventory differs"
[ "$(isolated_git /usr/bin/git -C "$SOURCE_STAGE" remote get-url origin)" = "$MACRO_ORIGIN" ] \
  || refuse "Macro source transport origin differs"
isolated_git /usr/bin/git -C "$SOURCE_STAGE" remote remove origin
if [ -d "$SOURCE_STAGE/.git/hooks" ]; then
  /usr/bin/find "$SOURCE_STAGE/.git/hooks" -type f -exec /bin/chmod 0444 {} \;
fi
verify_source_tree "$SOURCE_STAGE" || refuse "staged Macro source did not verify"

"$PYTHON_BINARY" -I -S -B -m venv --copies "$RUNTIME_STAGE"
PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null \
  "$RUNTIME_STAGE/bin/python3.12" -I -B -m pip install \
  --isolated --no-index --no-deps --only-binary=:all: --no-compile "$WHEEL_STAGE" >/dev/null

verify_runtime_candidate() {
  verify_runtime_tree "$RUNTIME_STAGE" >/dev/null
}
verify_source_candidate() {
  local candidate_material
  verify_source_tree "$SOURCE_STAGE"
  candidate_material="$(observe_material_digest "$SOURCE_STAGE" "$RUNTIME_STAGE")"
  [ "$candidate_material" = "$MATERIAL_SOURCE_DIGEST" ]
}
verify_runtime_candidate || refuse "staged capacity runtime did not verify"
verify_source_candidate || refuse "staged source material did not verify"

"$SCRIPT_DIR/bootstrap-host.sh" --operator-user "$OPERATOR_USER"
verify_empty_realms
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_USER" -m 0700 "$TELEMETRY_ROOT"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_USER" -m 0700 "$AI_COSTS_STATE_ROOT"
verify_telemetry_boundary || refuse "telemetry absence boundary did not verify"

/usr/bin/find "$SOURCE_STAGE" -type d -exec /bin/chmod 0555 {} \;
/usr/bin/find "$SOURCE_STAGE" -type f -exec /bin/chmod 0444 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type d -exec /bin/chmod 0555 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type f -perm +111 -exec /bin/chmod 0555 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type f ! -perm +111 -exec /bin/chmod 0444 {} \;
/usr/sbin/chown -R root:wheel "$SOURCE_STAGE" "$RUNTIME_STAGE"
verify_runtime_candidate || refuse "hardened capacity runtime did not verify"
verify_source_candidate || refuse "hardened source material did not verify"

/usr/bin/install -d -o root -g wheel -m 0755 "$SOURCE_PARENT"
/usr/bin/install -d -o root -g wheel -m 0755 "$RUNTIME_PARENT"
/usr/bin/install -d -o root -g wheel -m 0755 "$GENERATION_ROOT"
if [ -e "$SOURCE_ROOT" ] || [ -L "$SOURCE_ROOT" ]; then
  verify_source_tree "$SOURCE_ROOT" || refuse "existing versioned Macro source conflicts"
else
  /bin/mv "$SOURCE_STAGE" "$SOURCE_ROOT"
  SOURCE_STAGE=""
fi
if [ -e "$RUNTIME_ROOT" ] || [ -L "$RUNTIME_ROOT" ]; then
  verify_runtime_tree "$RUNTIME_ROOT" >/dev/null || refuse "existing versioned runtime conflicts"
else
  /bin/mv "$RUNTIME_STAGE" "$RUNTIME_ROOT"
  RUNTIME_STAGE=""
fi

verify_source_tree "$SOURCE_ROOT" || refuse "installed Macro source did not verify before receipt"
PYYAML_RECORD_SHA256="$(verify_runtime_tree "$RUNTIME_ROOT")" || refuse "installed runtime did not verify before receipt"
OBSERVED_MATERIAL_DIGEST="$(observe_material_digest "$SOURCE_ROOT" "$RUNTIME_ROOT" "$CONTROL_USER")" || {
  refuse "control-principal material receipt did not verify"
}
[ "$OBSERVED_MATERIAL_DIGEST" = "$MATERIAL_SOURCE_DIGEST" ] || refuse "control-principal material digest differs"

/usr/bin/install -d -o root -g wheel -m 0700 "$GENERATION_STAGE"
RENDERED="$GENERATION_STAGE/rendered.json"
/usr/bin/python3 -I -S -B "$CONTRACT" render \
  --material-source-digest "$OBSERVED_MATERIAL_DIGEST" \
  --pyyaml-record-sha256 "$PYYAML_RECORD_SHA256" \
  --mastermind-commit "$EXPECTED_MASTERMIND_SHA" >"$RENDERED"
/usr/bin/python3 -I -S -B - "$RENDERED" "$GENERATION_STAGE" <<'PY'
import json
import os
import pathlib
import sys

rendered = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
value = json.loads(rendered.read_text(encoding="utf-8"))
for key, filename in (
    ("components", "components.json"),
    ("source_config", "source-config.json"),
    ("host_receipt", "host-preparation-receipt.json"),
):
    payload = json.dumps(
        value[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    path = destination / filename
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
rendered.unlink()
PY
/usr/bin/python3 -I -S -B "$CONTRACT" verify \
  --components "$GENERATION_STAGE/components.json" \
  --config "$GENERATION_STAGE/source-config.json" \
  --receipt "$GENERATION_STAGE/host-preparation-receipt.json" >/dev/null
SOURCE_CONFIG_DIGEST="$(/usr/bin/python3 -I -S -B - "$GENERATION_STAGE/host-preparation-receipt.json" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["source_config_digest"])
PY
)"
GENERATION_TARGET="$GENERATION_ROOT/$SOURCE_CONFIG_DIGEST"
/usr/sbin/chown -R root:wheel "$GENERATION_STAGE"
/bin/chmod 0444 "$GENERATION_STAGE/components.json" "$GENERATION_STAGE/source-config.json" "$GENERATION_STAGE/host-preparation-receipt.json"
/bin/chmod 0555 "$GENERATION_STAGE"
if [ -e "$GENERATION_TARGET" ] || [ -L "$GENERATION_TARGET" ]; then
  verify_generation "$GENERATION_TARGET" || refuse "existing capacity generation conflicts"
else
  CONFIG_INSTALLED="true"
  RECEIPT_INSTALLED="true"
  /bin/mv "$GENERATION_STAGE" "$GENERATION_TARGET"
  GENERATION_STAGE=""
fi

INSTALL_COMPLETE="true"
verify_installed_host
