#!/bin/bash
# Install and prove the inert, credential-free CF2-H0 source and broker topology.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && /bin/pwd)"
MASTERMIND_SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && /bin/pwd -P)"
CONTRACT="$SCRIPT_DIR/capacity_source_contract.py"
ARTIFACTS="$SCRIPT_DIR/capacity_host_artifacts.py"
TOPOLOGY="$SCRIPT_DIR/capacity_broker_topology.py"
SLOT_RESOLVER="$SCRIPT_DIR/provider_worker_slots.py"
PYTHON_PROVISIONER="$SCRIPT_DIR/provision-python-runtime.sh"

MACRO_COMMIT="dcdd939c45b23abce5ba04f95e330ac914a3904b"
MATERIAL_SOURCE_DIGEST="35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"
PYTHON_BINARY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
PYTHON_BINARY_SHA256="d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
PYYAML_VERSION="6.0.3"
PYYAML_WHEEL="pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"
PYYAML_WHEEL_SHA256="fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0"
PYYAML_RECORD_SHA256="715146d21711444bc73c3137d18cffb6e38ace40e8998c5a9dfa69bd7dc46e3e"
RUNTIME_TREE_SHA256="79e1e4dc67c0fbefc266fcf2c27b98a7e0aeff5048e015fae11b20115ee864ee"
CODEX_VERSION="0.147.0"
CODEX_SHA256="19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
SOURCE_PARENT="$SYSTEM_ROOT/capacity-sources/macro"
SOURCE_ROOT="$SOURCE_PARENT/$MACRO_COMMIT"
RUNTIME_PARENT="$SYSTEM_ROOT/capacity-runtimes"
RUNTIME_ROOT="$RUNTIME_PARENT/cf1-pyyaml-6.0.3-cp312-arm64"
RELEASE_PARENT="$SYSTEM_ROOT/releases"
GENERATION_ROOT="$SYSTEM_ROOT/capacity-generations"
STAGING_ROOT="$SYSTEM_ROOT/capacity-staging"
ARCHIVE_ROOT="$SYSTEM_ROOT/capacity-archive"
LOCK_ROOT="$SYSTEM_ROOT/locks"
LOCK_FILE="$LOCK_ROOT/cf2-h0.lock"
TELEMETRY_ROOT="/var/db/mastermind-provider-control"
INSTALLED_CODEX="$SYSTEM_ROOT/bin/codex-$CODEX_VERSION"
CONTROL_USER="_mastermind_exec"
CONTROL_UID="450"
CONTROL_GID="450"
WORKER_TEMPLATE="com.mastermind.executive.worker.codex.plist.template"
WORKER_TEMPLATE_SOURCE="$SCRIPT_DIR/$WORKER_TEMPLATE"
BOOTSTRAP_SOURCE="$SCRIPT_DIR/bootstrap-host.sh"
RELEASE_MANIFEST_SOURCE="$SCRIPT_DIR/release_manifest.py"
PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")
H0_LABELS=(
  "com.mastermind.executive.worker.codex-pro-01"
  "com.mastermind.executive.worker.codex-pro-02"
  "com.mastermind.executive.worker.codex-pro-03"
)
LEGACY_LABELS=("com.mastermind.executive.control" "com.mastermind.executive.worker.codex")
LEGACY_FILES=(
  "$SYSTEM_ROOT/config/control.json"
  "$SYSTEM_ROOT/config/worker-codex.json"
  "/Library/LaunchDaemons/com.mastermind.executive.control.plist"
  "/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"
)
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
MACRO_TRANSPORT=""
MACRO_TRANSPORT_SHA256=""
WHEEL_SOURCE=""
VERIFY_ONLY="false"
MUTATION_STARTED="false"
COMMITTED="false"
STAGING_SESSION=""
GENERATION_CANDIDATE=""
FAILURE_ARCHIVE=""
ROLLBACK_INDEX=0
NEW_VERSIONED_PATHS=()
NEW_TOPOLOGY_PATHS=()
LEGACY_DIGESTS=()
RECOVERY_TARGETS=()

usage() {
  /bin/echo "usage: sudo /bin/bash $0 --expected-mastermind-sha SHA [--verify-only | --operator-user NAME --macro-transport FILE --macro-transport-sha256 SHA256 --pyyaml-wheel FILE]" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-mastermind-sha) EXPECTED_MASTERMIND_SHA="${2:-}"; shift 2 ;;
    --operator-user) OPERATOR_USER="${2:-}"; shift 2 ;;
    --macro-transport) MACRO_TRANSPORT="${2:-}"; shift 2 ;;
    --macro-transport-sha256) MACRO_TRANSPORT_SHA256="${2:-}"; shift 2 ;;
    --pyyaml-wheel) WHEEL_SOURCE="${2:-}"; shift 2 ;;
    --verify-only) VERIFY_ONLY="true"; shift ;;
    *) usage ;;
  esac
done

refuse() {
  /bin/echo "capacity host preparation refused: $1" >&2
  exit 65
}

assert_no_acl() {
  local inspected="$1"
  if [ -n "$(/usr/bin/find "$inspected" -exec /usr/bin/stat -f '%Sp' {} \; | /usr/bin/awk '/\+/{print "ACL"; exit}')" ]; then
    refuse "installed object contains a filesystem ACL"
  fi
}

assert_no_unapproved_xattrs() {
  local inspected="$1"
  /usr/bin/python3 -I -S -B "$ARTIFACTS" verify-approved-xattrs --path "$inspected" >/dev/null \
    || refuse "installed object contains an unapproved extended attribute"
}

case "$EXPECTED_MASTERMIND_SHA" in
  ''|*[!0-9a-f]*) refuse "expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters" ;;
esac
[ "${#EXPECTED_MASTERMIND_SHA}" -eq 40 ] || refuse "expected Mastermind SHA must contain exactly 40 lowercase hexadecimal characters"
[ "$(/usr/bin/id -u)" -eq 0 ] || { /bin/echo "prepare-capacity-host.sh must run as root" >&2; exit 77; }
[ "$(/usr/bin/uname -s)" = "Darwin" ] || { /bin/echo "prepare-capacity-host.sh supports macOS only" >&2; exit 69; }
[ -d "$MASTERMIND_SOURCE_REPO/.git" ] && [ ! -L "$MASTERMIND_SOURCE_REPO/.git" ] || refuse "Mastermind source must be a direct Git checkout"
for required in \
  "$CONTRACT" "$ARTIFACTS" "$TOPOLOGY" "$SLOT_RESOLVER" "$PYTHON_PROVISIONER" \
  "$BOOTSTRAP_SOURCE" "$RELEASE_MANIFEST_SOURCE" "$WORKER_TEMPLATE_SOURCE"; do
  [ -f "$required" ] && [ ! -L "$required" ] || refuse "reviewed H0 source is unavailable"
done
[ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || refuse "reviewed Python is unavailable"
[ "$(/usr/bin/shasum -a 256 "$PYTHON_BINARY" | /usr/bin/awk '{print $1}')" = "$PYTHON_BINARY_SHA256" ] || refuse "reviewed Python digest differs"
[ "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse HEAD)" = "$EXPECTED_MASTERMIND_SHA" ] || refuse "Mastermind source HEAD differs from the explicit merged SHA"
[ -z "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" status --porcelain=v1 --untracked-files=all)" ] || refuse "Mastermind source tree is not clean"
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_REPO" ! -user root -print -quit)" ] || refuse "Mastermind source contains a non-root-owned object"
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_REPO" -perm +022 -print -quit)" ] || refuse "Mastermind source contains a group/other-writable object"
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_REPO" -type f -links +1 -print -quit)" ] || refuse "Mastermind source contains a hard-linked file"
MASTERMIND_SOURCE_PARENT="$(cd "$MASTERMIND_SOURCE_REPO/.." && /bin/pwd -P)"
[ "$(/usr/bin/stat -f '%u:%g' "$MASTERMIND_SOURCE_PARENT")" = "0:0" ] || refuse "Mastermind source parent must be root:wheel"
[ -z "$(/usr/bin/find "$MASTERMIND_SOURCE_PARENT" -maxdepth 0 -perm +022 -print -quit)" ] || refuse "Mastermind source parent is group/other writable"
assert_no_acl "$MASTERMIND_SOURCE_PARENT"
assert_no_unapproved_xattrs "$MASTERMIND_SOURCE_PARENT"
assert_no_acl "$MASTERMIND_SOURCE_REPO"
assert_no_unapproved_xattrs "$MASTERMIND_SOURCE_REPO"
"$PYTHON_PROVISIONER" --verify-only >/dev/null || refuse "reviewed Python receipt did not verify"

slot_field() {
  /usr/bin/python3 -I -S -B "$SLOT_RESOLVER" "$1" "$2"
}

path_digest_or_absent() {
  local path="$1"
  if [ -f "$path" ] && [ ! -L "$path" ]; then
    {
      /usr/bin/stat -f '%u:%g:%Lp:%l' "$path"
      /usr/bin/shasum -a 256 "$path" | /usr/bin/awk '{print $1}'
    } | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
  elif [ ! -e "$path" ] && [ ! -L "$path" ]; then
    /bin/echo absent
  else
    /bin/echo ambiguous
  fi
}

capture_legacy_digests() {
  local path
  LEGACY_DIGESTS=()
  for path in "${LEGACY_FILES[@]}"; do LEGACY_DIGESTS+=("$(path_digest_or_absent "$path")"); done
}

verify_legacy_files_unchanged() {
  local index path
  for index in "${!LEGACY_FILES[@]}"; do
    path="${LEGACY_FILES[$index]}"
    [ "$(path_digest_or_absent "$path")" = "${LEGACY_DIGESTS[$index]}" ] || return 1
  done
}

current_legacy_state_digest() {
  local path label disabled loaded
  {
    for path in "${LEGACY_FILES[@]}"; do
      /bin/echo "$path=$(path_digest_or_absent "$path")"
    done
    for label in "${LEGACY_LABELS[@]}"; do
      disabled=false; loaded=false
      if /bin/launchctl print-disabled system 2>/dev/null | /usr/bin/grep -Fq '"'"$label"'" => true'; then disabled=true; fi
      if /bin/launchctl print "system/$label" >/dev/null 2>&1; then loaded=true; fi
      /bin/echo "$label:disabled=$disabled:loaded=$loaded"
    done
  } | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
}

verify_materialized_source() {
  local root="$1" path
  local arguments=()
  for path in "${MATERIAL_PATHS[@]}"; do arguments+=(--material-path "$path"); done
  [ -d "$root/.git" ] && [ ! -L "$root/.git" ] || return 1
  /usr/bin/python3 -I -S -B "$ARTIFACTS" verify-materialized-source \
    --source-root "$root" --manifest "$root/.git/cf2-h0-transport-manifest.json" \
    --commit "$MACRO_COMMIT" "${arguments[@]}" >/dev/null || return 1
  [ -z "$(/usr/bin/find "$root" ! -user root -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -perm +022 -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -type l -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -type f -links +1 -print -quit)" ] || return 1
  assert_no_acl "$root"
  assert_no_unapproved_xattrs "$root"
}

verify_runtime_tree() {
  local root="$1" evidence record_digest tree_digest
  [ -d "$root" ] && [ ! -L "$root" ] || return 1
  [ -f "$root/bin/python3.12" ] && [ -x "$root/bin/python3.12" ] && [ ! -L "$root/bin/python3.12" ] || return 1
  [ "$(/usr/bin/shasum -a 256 "$root/bin/python3.12" | /usr/bin/awk '{print $1}')" = "$PYTHON_BINARY_SHA256" ] || return 1
  [ -z "$(/usr/bin/find "$root" ! -user root -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" ! -group wheel -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -perm +022 -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -type l -print -quit)" ] || return 1
  [ -z "$(/usr/bin/find "$root" -type f -links +1 -print -quit)" ] || return 1
  [ ! -e "$root/bin/pip" ] && [ ! -e "$root/bin/pip3" ] || return 1
  assert_no_acl "$root"
  assert_no_unapproved_xattrs "$root"
  PYTHONNOUSERSITE=1 "$root/bin/python3.12" -I -B - "$root" "$PYYAML_VERSION" <<'PY' >/dev/null
import pathlib, site, sys
import _yaml, yaml
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
if pathlib.Path(sys.prefix).resolve(strict=True) != root or site.ENABLE_USER_SITE:
    raise RuntimeError("runtime isolation differs")
if yaml.__version__ != sys.argv[2]:
    raise RuntimeError("PyYAML version differs")
for module in (yaml, _yaml):
    if root not in pathlib.Path(module.__file__).resolve(strict=True).parents:
        raise RuntimeError("PyYAML import escapes the runtime")
PY
  evidence="$(/usr/bin/python3 -I -S -B "$ARTIFACTS" verify-runtime-tree --runtime-root "$root")" || return 1
  record_digest="$(/bin/echo "$evidence" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["pyyaml_record_sha256"])')" || return 1
  tree_digest="$(/bin/echo "$evidence" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["runtime_tree_sha256"])')" || return 1
  [ "$record_digest" = "$PYYAML_RECORD_SHA256" ] || return 1
  [ "$tree_digest" = "$RUNTIME_TREE_SHA256" ] || return 1
  /bin/echo "$evidence"
}

verify_telemetry_boundary() {
  local root="${1:-$TELEMETRY_ROOT}" expected observed_inventory expected_inventory
  [ -d "$root" ] && [ ! -L "$root" ] || return 1
  for expected in "$root" "$root/data" "$root/data/ai_costs" "$root/data/metabolism"; do
    [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$expected")" = "0:0:555" ] || return 1
  done
  observed_inventory="$(/usr/bin/find "$root" -mindepth 1 -type d -print | /usr/bin/sort)"
  expected_inventory="$(/bin/printf '%s\n' "$root/data" "$root/data/ai_costs" "$root/data/metabolism" | /usr/bin/sort)"
  [ "$observed_inventory" = "$expected_inventory" ] || return 1
  [ -z "$(/usr/bin/find "$root" ! -type d -print -quit)" ] || return 1
  assert_no_acl "$root"
  assert_no_unapproved_xattrs "$root"
}

label_disabled_unloaded() {
  local label="$1"
  /bin/launchctl print-disabled system 2>/dev/null | /usr/bin/grep -Fq '"'"$label"'" => true' || return 1
  if /bin/launchctl print "system/$label" >/dev/null 2>&1; then return 1; fi
}

assert_control_isolated() {
  local slot_id slot_group slot_gid slot_home membership
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    slot_group="$(slot_field "$slot_id" worker_group)"
    slot_gid="$(slot_field "$slot_id" worker_gid)"
    slot_home="$(slot_field "$slot_id" provider_home)"
    membership="$(/usr/sbin/dseditgroup -o checkmember -m "$CONTROL_USER" "$slot_group" 2>&1 || true)"
    case "$membership" in *"is not a member"*) ;; *) refuse "control principal is a member of a Personal Pro group" ;; esac
    case " $(/usr/bin/id -G "$CONTROL_USER") " in *" $slot_gid "*) refuse "control principal resolves a Personal Pro GID" ;; esac
    /usr/bin/sudo -u "$CONTROL_USER" /bin/test ! -r "$slot_home" || refuse "control principal can read a Personal Pro home"
    /usr/bin/sudo -u "$CONTROL_USER" /bin/test ! -x "$slot_home" || refuse "control principal can traverse a Personal Pro home"
  done
}

verify_release() {
  local release="$RELEASE_PARENT/$EXPECTED_MASTERMIND_SHA"
  [ -d "$release" ] && [ ! -L "$release" ] || return 1
  "$PYTHON_BINARY" -I -S -B "$release/ops/executive_os/release_manifest.py" verify \
    --root "$release" --commit-sha "$EXPECTED_MASTERMIND_SHA" \
    --tree-sha "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse "$EXPECTED_MASTERMIND_SHA^{tree}")" >/dev/null
}

verify_topology() {
  local topology_file="$1"
  local slot_id slot_user slot_gid config attestation plist socket_path release
  release="$RELEASE_PARENT/$EXPECTED_MASTERMIND_SHA"
  [ -f "$topology_file" ] && [ ! -L "$topology_file" ] || return 1
  /usr/bin/python3 -I -S -B - "$topology_file" "$(current_legacy_state_digest)" <<'PY' || return 1
import hashlib, json, pathlib, sys
topology = json.loads(pathlib.Path(sys.argv[1]).read_text())
if topology.get("legacy_phase1c_state_digest") != sys.argv[2]:
    raise RuntimeError("legacy state digest differs")
rows = topology.get("brokers")
if not isinstance(rows, list) or len(rows) != 3:
    raise RuntimeError("broker inventory differs")
for row in rows:
    for path_key, digest_key in (
        ("config_path", "config_sha256"),
        ("attestation_path", "attestation_sha256"),
        ("plist_path", "plist_sha256"),
    ):
        path = pathlib.Path(row[path_key])
        if hashlib.sha256(path.read_bytes()).hexdigest() != row[digest_key]:
            raise RuntimeError("installed topology artifact digest differs")
PY
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    slot_user="$(slot_field "$slot_id" worker_user)"
    slot_gid="$(slot_field "$slot_id" worker_gid)"
    config="$SYSTEM_ROOT/config/worker-$slot_id.json"
    attestation="$SYSTEM_ROOT/codex-attestation-$CODEX_VERSION-$slot_id.json"
    plist="/Library/LaunchDaemons/com.mastermind.executive.worker.$slot_id.plist"
    socket_path="/var/run/mastermind-executive/worker-$slot_id.sock"
    [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$config")" = "0:$slot_gid:440:1" ] || return 1
    [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$attestation")" = "0:$slot_gid:440:1" ] || return 1
    [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$plist")" = "0:0:644:1" ] || return 1
    assert_no_acl "$config"; assert_no_acl "$attestation"; assert_no_acl "$plist"
    assert_no_unapproved_xattrs "$config"; assert_no_unapproved_xattrs "$attestation"; assert_no_unapproved_xattrs "$plist"
    /usr/bin/plutil -lint "$plist" >/dev/null || return 1
    [ ! -e "$socket_path" ] && [ ! -L "$socket_path" ] || return 1
    label_disabled_unloaded "com.mastermind.executive.worker.$slot_id" || return 1
    /usr/bin/sudo -u "$CONTROL_USER" /bin/test ! -r "$config" || return 1
    /usr/bin/sudo -u "$slot_user" /usr/bin/env -i \
      HOME="$(slot_field "$slot_id" provider_home)" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
      LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      "$PYTHON_BINARY" -I -S -B "$release/scripts/executive_os_phase1c_worker.py" \
      check-config --config "$config" >/dev/null || return 1
  done
  assert_control_isolated
}

verify_generation() {
  local generation="$1" mode="${2:-installed}" expected_inventory observed artifact
  [ -d "$generation" ] && [ ! -L "$generation" ] || return 1
  [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$generation")" = "0:0:555" ] || return 1
  expected_inventory="$(/bin/printf '%s\n' broker-topology.json components.json host-preparation-receipt.json rollback-contract.json rollback-drill-receipt.json source-config.json | /usr/bin/sort)"
  observed="$(/usr/bin/find "$generation" -mindepth 1 -maxdepth 1 -type f -print | while IFS= read -r artifact; do /usr/bin/basename "$artifact"; done | /usr/bin/sort)"
  [ "$observed" = "$expected_inventory" ] || return 1
  [ -z "$(/usr/bin/find "$generation" -mindepth 1 -maxdepth 1 ! -type f -print -quit)" ] || return 1
  for artifact in broker-topology.json components.json host-preparation-receipt.json rollback-contract.json rollback-drill-receipt.json source-config.json; do
    [ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$generation/$artifact")" = "0:0:444:1" ] || return 1
  done
  assert_no_acl "$generation"
  assert_no_unapproved_xattrs "$generation"
  /usr/bin/python3 -I -S -B "$CONTRACT" verify \
    --components "$generation/components.json" --config "$generation/source-config.json" \
    --receipt "$generation/host-preparation-receipt.json" >/dev/null || return 1
  /usr/bin/python3 -I -S -B - "$generation" "$EXPECTED_MASTERMIND_SHA" "$mode" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
receipt = json.loads((root / "host-preparation-receipt.json").read_text())
if receipt["preparer_source_commit"] != sys.argv[2]:
    raise RuntimeError("generation identity differs")
if sys.argv[3] == "installed" and root.name != receipt["source_config_digest"]:
    raise RuntimeError("installed generation name differs")
if hashlib.sha256((root / "broker-topology.json").read_bytes()).hexdigest() != receipt["broker_topology_digest"]:
    raise RuntimeError("topology digest differs")
if hashlib.sha256((root / "rollback-contract.json").read_bytes()).hexdigest() != receipt["rollback_contract_digest"]:
    raise RuntimeError("rollback contract digest differs")
if hashlib.sha256((root / "rollback-drill-receipt.json").read_bytes()).hexdigest() != receipt["rollback_drill_receipt_digest"]:
    raise RuntimeError("rollback drill receipt digest differs")
drill_path = root / "rollback-drill-receipt.json"
drill = json.loads(drill_path.read_text())
if set(drill) != {
    "archive_root", "artifacts", "broker_topology_digest", "credential_state",
    "moved_artifact_count", "outcome", "preserved_state", "rollback_contract_digest",
    "schema_version", "service_state", "socket_state",
} or drill["outcome"] != "SHRINK_ONLY_ROLLBACK_PASS" or drill["moved_artifact_count"] != 9:
    raise RuntimeError("rollback drill receipt fields differ")
archive = pathlib.Path(drill["archive_root"])
expected_archive_parent = pathlib.Path("/Library/Application Support/MastermindExecutive/capacity-archive")
if archive.parent != expected_archive_parent or not archive.name.startswith("rollback-drill-"):
    raise RuntimeError("rollback drill archive identity differs")
original = archive / "rollback-receipt.json"
if original.is_symlink() or not original.is_file() or original.read_bytes() != drill_path.read_bytes():
    raise RuntimeError("durable rollback drill receipt differs")
artifacts = drill["artifacts"]
if not isinstance(artifacts, list) or len(artifacts) != 9:
    raise RuntimeError("rollback drill artifact inventory differs")
for artifact in artifacts:
    if not isinstance(artifact, dict) or set(artifact) != {"name", "sha256"}:
        raise RuntimeError("rollback drill artifact row differs")
    path = archive / artifact["name"]
    if path.parent != archive or path.is_symlink() or not path.is_file():
        raise RuntimeError("rollback drill artifact is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
        raise RuntimeError("rollback drill artifact digest differs")
PY
}

verify_installed_host() {
  local generations generation_count generation label
  verify_materialized_source "$SOURCE_ROOT" || refuse "installed Macro source did not verify"
  verify_runtime_tree "$RUNTIME_ROOT" >/dev/null || refuse "installed capacity runtime did not verify"
  verify_telemetry_boundary || refuse "canonical telemetry absence boundary did not verify"
  verify_release || refuse "installed Mastermind release did not verify"
  capture_legacy_digests
  verify_legacy_files_unchanged || refuse "legacy Executive files changed during verification"
  for label in "${LEGACY_LABELS[@]}"; do label_disabled_unloaded "$label" || refuse "legacy Executive service is not disabled and unloaded"; done
  generations="$(/usr/bin/find "$GENERATION_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -print 2>/dev/null || true)"
  generation_count="$(/bin/echo "$generations" | /usr/bin/awk 'NF {count++} END {print count+0}')"
  [ "$generation_count" -eq 1 ] || refuse "capacity generation inventory is ambiguous"
  generation="$generations"
  verify_generation "$generation" || refuse "capacity generation did not verify"
  verify_topology "$generation/broker-topology.json" || refuse "installed inert broker topology did not verify"
  /bin/echo "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
}

if [ "$VERIFY_ONLY" = "true" ]; then
  verify_installed_host
  exit 0
fi

[ -n "$OPERATOR_USER" ] && [ -n "$MACRO_TRANSPORT" ] && [ -n "$MACRO_TRANSPORT_SHA256" ] && [ -n "$WHEEL_SOURCE" ] || usage
/usr/bin/id "$OPERATOR_USER" >/dev/null 2>&1 || refuse "operator account does not exist"
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"
case "$MACRO_TRANSPORT_SHA256" in ''|*[!0-9a-f]*) refuse "Macro transport SHA-256 must contain exactly 64 lowercase hexadecimal characters" ;; esac
[ "${#MACRO_TRANSPORT_SHA256}" -eq 64 ] || refuse "Macro transport SHA-256 must contain exactly 64 lowercase hexadecimal characters"
case "$MACRO_TRANSPORT" in /*) ;; *) refuse "Macro transport path must be absolute" ;; esac
case "$WHEEL_SOURCE" in /*) ;; *) refuse "PyYAML wheel path must be absolute" ;; esac
[ -f "$MACRO_TRANSPORT" ] && [ ! -L "$MACRO_TRANSPORT" ] && [ "$(/usr/bin/stat -f '%l' "$MACRO_TRANSPORT")" -eq 1 ] || refuse "Macro transport must be one direct single-link file"
[ -f "$WHEEL_SOURCE" ] && [ ! -L "$WHEEL_SOURCE" ] && [ "$(/usr/bin/stat -f '%l' "$WHEEL_SOURCE")" -eq 1 ] || refuse "PyYAML wheel must be one direct single-link file"
[ "$(/usr/bin/stat -f '%u' "$MACRO_TRANSPORT")" = "$OPERATOR_UID" ] || refuse "Macro transport must be owned by the named operator"
[ "$(/usr/bin/stat -f '%u' "$WHEEL_SOURCE")" = "$OPERATOR_UID" ] || refuse "PyYAML wheel must be owned by the named operator"
[ -z "$(/usr/bin/find "$MACRO_TRANSPORT" -perm +022 -print -quit)" ] || refuse "Macro transport must not be group/other writable"
[ -z "$(/usr/bin/find "$WHEEL_SOURCE" -perm +022 -print -quit)" ] || refuse "PyYAML wheel must not be group/other writable"
[ "$(/usr/bin/basename "$WHEEL_SOURCE")" = "$PYYAML_WHEEL" ] || refuse "PyYAML wheel filename differs"
CREATE_TELEMETRY_ROOT="false"
if [ -e "$TELEMETRY_ROOT" ] || [ -L "$TELEMETRY_ROOT" ]; then
  verify_telemetry_boundary || refuse "pre-existing Provider Control telemetry root is not the exact canonical absence boundary"
else
  CREATE_TELEMETRY_ROOT="true"
fi
capture_legacy_digests
for label in "${LEGACY_LABELS[@]}"; do label_disabled_unloaded "$label" || refuse "legacy Executive services must already be disabled and unloaded"; done
if [ -d "$GENERATION_ROOT" ] && [ ! -L "$GENERATION_ROOT" ]; then
  ACCEPTED_GENERATION_COUNT="$(/usr/bin/find "$GENERATION_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -print | /usr/bin/awk 'NF {count++} END {print count+0}')"
else
  [ ! -e "$GENERATION_ROOT" ] && [ ! -L "$GENERATION_ROOT" ] || refuse "capacity generation root is ambiguous"
  ACCEPTED_GENERATION_COUNT=0
fi
[ "$ACCEPTED_GENERATION_COUNT" -eq 0 ] || refuse "an accepted H0 generation already exists; use --verify-only"

archive_path() {
  local source="$1" disposition="$2" destination
  [ -e "$source" ] || [ -L "$source" ] || return 0
  /usr/bin/install -d -o root -g wheel -m 0700 "$FAILURE_ARCHIVE"
  destination="$FAILURE_ARCHIVE/$disposition-$(/usr/bin/uuidgen)-$(/usr/bin/basename "$source")"
  /bin/mv "$source" "$destination"
}

validate_recovery_target() {
  local path="$1"
  [ -e "$path" ] && [ ! -L "$path" ] || refuse "interrupted H0 recovery target is ambiguous"
  [ -f "$path" ] || [ -d "$path" ] || refuse "interrupted H0 recovery target has an unsupported type"
  [ -z "$(/usr/bin/find "$path" ! -user root -print -quit)" ] || refuse "interrupted H0 recovery target is not root-owned"
  [ -z "$(/usr/bin/find "$path" -perm +022 -print -quit)" ] || refuse "interrupted H0 recovery target is group/other writable"
  [ -z "$(/usr/bin/find "$path" -type l -print -quit)" ] || refuse "interrupted H0 recovery target contains a symlink"
  [ -z "$(/usr/bin/find "$path" -type f -links +1 -print -quit)" ] || refuse "interrupted H0 recovery target contains a hard-linked file"
  assert_no_acl "$path"
  assert_no_unapproved_xattrs "$path"
}

collect_interrupted_h0_targets() {
  local slot_id path pattern temporary
  RECOVERY_TARGETS=()
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    for path in \
      "$SYSTEM_ROOT/config/worker-$slot_id.json" \
      "$SYSTEM_ROOT/codex-attestation-$CODEX_VERSION-$slot_id.json" \
      "/Library/LaunchDaemons/com.mastermind.executive.worker.$slot_id.plist"; do
      if [ -e "$path" ] || [ -L "$path" ]; then
        validate_recovery_target "$path"
        RECOVERY_TARGETS+=("$path")
      fi
    done
    for path in \
      "$SYSTEM_ROOT/config" \
      "$SYSTEM_ROOT" \
      "/Library/LaunchDaemons"; do
      [ -d "$path" ] && [ ! -L "$path" ] || continue
      case "$path" in
        "$SYSTEM_ROOT/config") pattern="worker-$slot_id.json.*.tmp" ;;
        "$SYSTEM_ROOT") pattern="codex-attestation-$CODEX_VERSION-$slot_id.json.*.tmp" ;;
        *) pattern="com.mastermind.executive.worker.$slot_id.plist.*.tmp" ;;
      esac
      while IFS= read -r temporary; do
        [ -n "$temporary" ] || continue
        validate_recovery_target "$temporary"
        RECOVERY_TARGETS+=("$temporary")
      done < <(/usr/bin/find "$path" -mindepth 1 -maxdepth 1 -name "$pattern" -print)
    done
    path="/var/run/mastermind-executive/worker-$slot_id.sock"
    [ ! -e "$path" ] && [ ! -L "$path" ] || refuse "interrupted H0 state contains a socket-path object"
  done
  if [ -d "$GENERATION_ROOT" ] && [ ! -L "$GENERATION_ROOT" ]; then
    while IFS= read -r path; do
      [ -n "$path" ] || continue
      validate_recovery_target "$path"
      RECOVERY_TARGETS+=("$path")
    done < <(/usr/bin/find "$GENERATION_ROOT" -mindepth 1 -maxdepth 1 -name '.candidate-*' -print)
  fi
  if [ -d "$STAGING_ROOT" ] && [ ! -L "$STAGING_ROOT" ]; then
    while IFS= read -r path; do
      [ -n "$path" ] || continue
      validate_recovery_target "$path"
      RECOVERY_TARGETS+=("$path")
    done < <(/usr/bin/find "$STAGING_ROOT" -mindepth 1 -maxdepth 1 -name 'cf2-h0.*' -print)
  fi
}

ensure_h0_recovery_posture() {
  local label slot_id
  for label in "${H0_LABELS[@]}"; do
    /bin/launchctl disable "system/$label"
    /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
    label_disabled_unloaded "$label" || refuse "interrupted H0 label could not be made disabled and unloaded"
  done
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    [ ! -e "/var/run/mastermind-executive/worker-$slot_id.sock" ] && [ ! -L "/var/run/mastermind-executive/worker-$slot_id.sock" ] \
      || refuse "interrupted H0 recovery found a socket-path object"
  done
}

reconcile_recovery_archives() {
  local archive observed
  PENDING_RECOVERY_INTENT_ARCHIVE=""
  [ -d "$ARCHIVE_ROOT" ] && [ ! -L "$ARCHIVE_ROOT" ] || return 0
  while IFS= read -r archive; do
    [ -n "$archive" ] || continue
    validate_recovery_target "$archive"
    if [ -f "$archive/recovery-intent.json" ] && [ ! -L "$archive/recovery-intent.json" ]; then
      ensure_h0_recovery_posture
      /usr/bin/python3 -I -S -B "$ARTIFACTS" resume-recovery-archive \
        --archive "$archive" --expected-uid 0 >/dev/null \
        || refuse "interrupted H0 recovery archive could not be reconciled"
      ensure_h0_recovery_posture
    elif [ -f "$archive/.recovery-intent.json.candidate" ] && [ ! -L "$archive/.recovery-intent.json.candidate" ]; then
      [ -z "$PENDING_RECOVERY_INTENT_ARCHIVE" ] || refuse "multiple interrupted H0 intent publications require adjudication"
      observed="$(/usr/bin/find "$archive" -mindepth 1 -maxdepth 1 -print)"
      [ "$observed" = "$archive/.recovery-intent.json.candidate" ] \
        || refuse "interrupted H0 intent archive inventory differs"
      PENDING_RECOVERY_INTENT_ARCHIVE="$archive"
    else
      [ -z "$(/usr/bin/find "$archive" -mindepth 1 -maxdepth 1 -print -quit)" ] \
        || refuse "unrecognized interrupted H0 recovery archive"
    fi
  done < <(/usr/bin/find "$ARCHIVE_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'recovered-*' -print)
}

recover_interrupted_h0() {
  local path recovery_archive
  local arguments=()
  if [ "${#RECOVERY_TARGETS[@]}" -eq 0 ]; then
    [ -z "$PENDING_RECOVERY_INTENT_ARCHIVE" ] || refuse "interrupted H0 intent has no matching partial targets"
    return 0
  fi
  ensure_h0_recovery_posture
  if [ -n "$PENDING_RECOVERY_INTENT_ARCHIVE" ]; then
    recovery_archive="$PENDING_RECOVERY_INTENT_ARCHIVE"
  else
    recovery_archive="$ARCHIVE_ROOT/recovered-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
    /usr/bin/install -d -o root -g wheel -m 0700 "$recovery_archive"
  fi
  for path in "${RECOVERY_TARGETS[@]}"; do
    arguments+=(--source "$path")
  done
  /usr/bin/python3 -I -S -B "$ARTIFACTS" create-recovery-intent \
    --archive "$recovery_archive" --expected-uid 0 "${arguments[@]}" >/dev/null \
    || refuse "interrupted H0 recovery intent could not be committed"
  /usr/bin/python3 -I -S -B "$ARTIFACTS" resume-recovery-archive \
    --archive "$recovery_archive" --expected-uid 0 >/dev/null \
    || refuse "interrupted H0 partial state could not be recovered"
  ensure_h0_recovery_posture
  RECOVERY_TARGETS=()
  PENDING_RECOVERY_INTENT_ARCHIVE=""
}

cleanup() {
  local status="$?" path label
  if [ "$MUTATION_STARTED" = "true" ] && [ "$COMMITTED" != "true" ]; then
    for label in "${H0_LABELS[@]}"; do
      /bin/launchctl disable "system/$label" >/dev/null 2>&1 || true
      /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
    done
    for path in "${NEW_TOPOLOGY_PATHS[@]}"; do archive_path "$path" failed-topology || true; done
    [ -z "$GENERATION_CANDIDATE" ] || archive_path "$GENERATION_CANDIDATE" failed-generation || true
    for path in "${NEW_VERSIONED_PATHS[@]}"; do archive_path "$path" failed-versioned || true; done
    [ -z "$STAGING_SESSION" ] || archive_path "$STAGING_SESSION" failed-stage || true
  fi
  exit "$status"
}
trap cleanup EXIT

/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT"
/usr/bin/install -d -o root -g wheel -m 0700 "$STAGING_ROOT" "$ARCHIVE_ROOT" "$LOCK_ROOT"
if ! /usr/bin/shlock -f "$LOCK_FILE" -p "$$"; then
  /bin/echo "capacity host preparation refused: another H0 preparation owns the host lock" >&2
  exit 75
fi
MUTATION_STARTED="true"
reconcile_recovery_archives
collect_interrupted_h0_targets
recover_interrupted_h0
STAGING_SESSION="$(/usr/bin/mktemp -d "$STAGING_ROOT/cf2-h0.XXXXXX")"
FAILURE_ARCHIVE="$ARCHIVE_ROOT/failed-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
TRANSPORT_STAGE="$STAGING_SESSION/macro-transport.zip"
WHEEL_STAGE="$STAGING_SESSION/$PYYAML_WHEEL"
SOURCE_STAGE="$STAGING_SESSION/source"
RUNTIME_STAGE="$STAGING_SESSION/runtime"
TOPOLOGY_STAGE="$STAGING_SESSION/topology"
GENERATION_STAGE="$STAGING_SESSION/generation"
TELEMETRY_STAGE="$STAGING_SESSION/provider-control-telemetry"

/usr/bin/python3 -I -S -B "$ARTIFACTS" copy-closed-input \
  --source "$MACRO_TRANSPORT" --destination "$TRANSPORT_STAGE" \
  --operator-uid "$OPERATOR_UID" --expected-sha256 "$MACRO_TRANSPORT_SHA256" >/dev/null \
  || refuse "Macro transport changed across the privilege boundary"
/usr/bin/python3 -I -S -B "$ARTIFACTS" copy-closed-input \
  --source "$WHEEL_SOURCE" --destination "$WHEEL_STAGE" \
  --operator-uid "$OPERATOR_UID" --expected-sha256 "$PYYAML_WHEEL_SHA256" >/dev/null \
  || refuse "PyYAML wheel changed across the privilege boundary"
assert_no_acl "$TRANSPORT_STAGE"; assert_no_acl "$WHEEL_STAGE"
assert_no_unapproved_xattrs "$TRANSPORT_STAGE"; assert_no_unapproved_xattrs "$WHEEL_STAGE"
[ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$TRANSPORT_STAGE")" = "0:0:400:1" ] || refuse "closed Macro transport metadata differs"
[ "$(/usr/bin/stat -f '%u:%g:%Lp:%l' "$WHEEL_STAGE")" = "0:0:400:1" ] || refuse "closed PyYAML wheel metadata differs"
[ "$(/usr/bin/shasum -a 256 "$TRANSPORT_STAGE" | /usr/bin/awk '{print $1}')" = "$MACRO_TRANSPORT_SHA256" ] || refuse "Macro transport digest differs"
[ "$(/usr/bin/shasum -a 256 "$WHEEL_STAGE" | /usr/bin/awk '{print $1}')" = "$PYYAML_WHEEL_SHA256" ] || refuse "PyYAML wheel digest differs"

MATERIAL_ARGUMENTS=()
for path in "${MATERIAL_PATHS[@]}"; do MATERIAL_ARGUMENTS+=(--material-path "$path"); done
/usr/bin/python3 -I -S -B "$ARTIFACTS" materialize-source-transport \
  --archive "$TRANSPORT_STAGE" --destination "$SOURCE_STAGE" --commit "$MACRO_COMMIT" \
  "${MATERIAL_ARGUMENTS[@]}" >/dev/null || refuse "Macro object transport did not materialize"
verify_materialized_source "$SOURCE_STAGE" || refuse "staged Macro source did not verify"

"$PYTHON_BINARY" -I -S -B -m venv --copies --without-pip "$RUNTIME_STAGE"
[ -z "$(/usr/bin/find "$RUNTIME_STAGE" -type l -print -quit)" ] || refuse "capacity runtime contains a symlink"
/usr/bin/install -d -o root -g wheel -m 0700 "$STAGING_SESSION/runtime-pruned"
EXPECTED_RUNTIME_BIN_INVENTORY="$(/bin/printf '%s\n' Activate.ps1 activate activate.csh activate.fish python python3 python3.12 | /usr/bin/sort)"
OBSERVED_RUNTIME_BIN_INVENTORY="$(/usr/bin/find "$RUNTIME_STAGE/bin" -mindepth 1 -maxdepth 1 -type f -print | while IFS= read -r path; do /usr/bin/basename "$path"; done | /usr/bin/sort)"
[ "$OBSERVED_RUNTIME_BIN_INVENTORY" = "$EXPECTED_RUNTIME_BIN_INVENTORY" ] || refuse "fresh runtime executable inventory differs"
for path in \
  "$RUNTIME_STAGE/bin/Activate.ps1" "$RUNTIME_STAGE/bin/activate" \
  "$RUNTIME_STAGE/bin/activate.csh" "$RUNTIME_STAGE/bin/activate.fish" \
  "$RUNTIME_STAGE/bin/python" "$RUNTIME_STAGE/bin/python3"; do
  [ -f "$path" ] && [ ! -L "$path" ] || refuse "fresh runtime pruning target differs"
  /bin/mv "$path" "$STAGING_SESSION/runtime-pruned/$(/usr/bin/basename "$path")"
done
[ -d "$RUNTIME_STAGE/include/python3.12" ] && [ -z "$(/usr/bin/find "$RUNTIME_STAGE/include/python3.12" -mindepth 1 -print -quit)" ] || refuse "fresh runtime include inventory differs"
/bin/rmdir "$RUNTIME_STAGE/include/python3.12"
[ -d "$RUNTIME_STAGE/include" ] && [ -z "$(/usr/bin/find "$RUNTIME_STAGE/include" -mindepth 1 -print -quit)" ] || refuse "fresh runtime include root differs"
/bin/rmdir "$RUNTIME_STAGE/include"
/usr/bin/python3 -I -S -B - "$RUNTIME_STAGE/pyvenv.cfg" "$RUNTIME_ROOT" <<'PY'
import pathlib, sys
pathlib.Path(sys.argv[1]).write_text(
    "home = /Library/Frameworks/Python.framework/Versions/3.12/bin\n"
    "include-system-site-packages = false\nversion = 3.12.10\n"
    "executable = /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12\n"
    f"command = /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv --copies --without-pip {sys.argv[2]}\n",
    encoding="utf-8",
)
PY
/usr/bin/python3 -I -S -B "$ARTIFACTS" extract-pyyaml-wheel --wheel "$WHEEL_STAGE" --runtime-root "$RUNTIME_STAGE" >/dev/null || refuse "pinned PyYAML wheel extraction refused"
/usr/bin/find "$SOURCE_STAGE" -type d -exec /bin/chmod 0555 {} \;
/usr/bin/find "$SOURCE_STAGE" -type f -exec /bin/chmod 0444 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type d -exec /bin/chmod 0555 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type f -perm +111 -exec /bin/chmod 0555 {} \;
/usr/bin/find "$RUNTIME_STAGE" -type f ! -perm +111 -exec /bin/chmod 0444 {} \;
/bin/chmod 0555 "$RUNTIME_STAGE/lib/python3.12/site-packages/yaml/_yaml.cpython-312-darwin.so"
/usr/sbin/chown -R root:wheel "$SOURCE_STAGE" "$RUNTIME_STAGE"
verify_materialized_source "$SOURCE_STAGE" || refuse "hardened Macro source did not verify"
RUNTIME_EVIDENCE="$(verify_runtime_tree "$RUNTIME_STAGE")" || refuse "hardened capacity runtime did not verify"

"$SCRIPT_DIR/bootstrap-host.sh" --operator-user "$OPERATOR_USER"
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_home="$(slot_field "$slot_id" provider_home)"
  [ -z "$(/usr/bin/find "$slot_home" -mindepth 1 -print -quit)" ] || refuse "Personal Pro realm was not empty before H0 topology installation"
done
assert_control_isolated

if [ "$CREATE_TELEMETRY_ROOT" = "true" ]; then
  /usr/bin/install -d -o root -g wheel -m 0755 "$TELEMETRY_STAGE" "$TELEMETRY_STAGE/data" "$TELEMETRY_STAGE/data/ai_costs" "$TELEMETRY_STAGE/data/metabolism"
  /bin/chmod 0555 "$TELEMETRY_STAGE" "$TELEMETRY_STAGE/data" "$TELEMETRY_STAGE/data/ai_costs" "$TELEMETRY_STAGE/data/metabolism"
  verify_telemetry_boundary "$TELEMETRY_STAGE" || refuse "staged Provider Control telemetry boundary did not verify"
  /bin/mv "$TELEMETRY_STAGE" "$TELEMETRY_ROOT"
  NEW_VERSIONED_PATHS+=("$TELEMETRY_ROOT")
fi
verify_telemetry_boundary || refuse "canonical empty Provider Control telemetry root did not verify"

/usr/bin/install -d -o root -g wheel -m 0755 "$SOURCE_PARENT" "$RUNTIME_PARENT" "$RELEASE_PARENT" "$GENERATION_ROOT"
if [ -e "$SOURCE_ROOT" ]; then verify_materialized_source "$SOURCE_ROOT" || refuse "existing versioned Macro source conflicts"; else /bin/mv "$SOURCE_STAGE" "$SOURCE_ROOT"; NEW_VERSIONED_PATHS+=("$SOURCE_ROOT"); fi
if [ -e "$RUNTIME_ROOT" ]; then verify_runtime_tree "$RUNTIME_ROOT" >/dev/null || refuse "existing versioned capacity runtime conflicts"; else /bin/mv "$RUNTIME_STAGE" "$RUNTIME_ROOT"; NEW_VERSIONED_PATHS+=("$RUNTIME_ROOT"); fi

RELEASE_ROOT="$RELEASE_PARENT/$EXPECTED_MASTERMIND_SHA"
if [ -e "$RELEASE_ROOT" ]; then
  verify_release || refuse "existing Mastermind release conflicts"
else
  RELEASE_STAGE="$STAGING_SESSION/release"
  /usr/bin/install -d -o root -g wheel -m 0755 "$RELEASE_STAGE"
  /usr/bin/git -C "$MASTERMIND_SOURCE_REPO" archive --format=tar "$EXPECTED_MASTERMIND_SHA" | /usr/bin/tar -xf - -C "$RELEASE_STAGE"
  /usr/sbin/chown -R root:wheel "$RELEASE_STAGE"; /bin/chmod -R go-w "$RELEASE_STAGE"; /bin/chmod 0755 "$RELEASE_STAGE"
  "$PYTHON_BINARY" -I -S -B "$RELEASE_STAGE/ops/executive_os/release_manifest.py" create \
    --root "$RELEASE_STAGE" --commit-sha "$EXPECTED_MASTERMIND_SHA" \
    --tree-sha "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse "$EXPECTED_MASTERMIND_SHA^{tree}")"
  /usr/sbin/chown root:wheel "$RELEASE_STAGE/.executive-release-manifest.json"
  "$PYTHON_BINARY" -I -S -B "$RELEASE_STAGE/ops/executive_os/release_manifest.py" verify \
    --root "$RELEASE_STAGE" --commit-sha "$EXPECTED_MASTERMIND_SHA" \
    --tree-sha "$(/usr/bin/git -C "$MASTERMIND_SOURCE_REPO" rev-parse "$EXPECTED_MASTERMIND_SHA^{tree}")" >/dev/null
  /bin/mv "$RELEASE_STAGE" "$RELEASE_ROOT"; NEW_VERSIONED_PATHS+=("$RELEASE_ROOT")
fi
verify_release || refuse "installed Mastermind release did not verify"

[ -x "$INSTALLED_CODEX" ] && [ ! -L "$INSTALLED_CODEX" ] || refuse "exact installed Codex binary is unavailable"
/usr/bin/codesign --verify --strict "$INSTALLED_CODEX" >/dev/null 2>&1 || refuse "installed Codex signature is invalid"
[ "$(/usr/bin/codesign -dv --verbose=4 "$INSTALLED_CODEX" 2>&1 | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2}')" = "2DC432GLL2" ] || refuse "installed Codex signer differs"
[ "$("$INSTALLED_CODEX" --version 2>/dev/null | /usr/bin/awk '$1 == "codex-cli" {print $2}')" = "$CODEX_VERSION" ] || refuse "installed Codex version differs"
[ "$(/usr/bin/shasum -a 256 "$INSTALLED_CODEX" | /usr/bin/awk '{print $1}')" = "$CODEX_SHA256" ] || refuse "installed Codex digest differs"

ATTESTATION_STAGE="$STAGING_SESSION/codex-attestation.json"
"$PYTHON_BINARY" -I -S -B - "$ATTESTATION_STAGE" "$INSTALLED_CODEX" "$CODEX_VERSION" "$CODEX_SHA256" <<'PY'
import json, os, pathlib, stat, sys
from datetime import datetime, timezone
destination, binary_path, version, sha256 = sys.argv[1:]
path = pathlib.Path(binary_path)
fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
try: info = os.fstat(fd)
finally: os.close(fd)
value = {"schema_version": "mastermind.executive_codex_attestation/v1", "path": str(path), "version": version,
         "team_identifier": "2DC432GLL2", "sha256": sha256,
         "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "identity": {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
                      "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
                      "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}}
pathlib.Path(destination).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
PY
ATTESTATION_SHA256="$(/usr/bin/shasum -a 256 "$ATTESTATION_STAGE" | /usr/bin/awk '{print $1}')"

GIDS_JSON="$STAGING_SESSION/supplementary-gids.json"
/usr/bin/python3 -I -S -B - "$SLOT_RESOLVER" "$GIDS_JSON" <<'PY'
import json, pathlib, subprocess, sys
resolver, destination = sys.argv[1:]
rows = {}
for slot_id in ("codex-pro-01", "codex-pro-02", "codex-pro-03"):
    user = subprocess.check_output(["/usr/bin/python3", "-I", "-S", "-B", resolver, slot_id, "worker_user"], text=True).strip()
    primary = int(subprocess.check_output(["/usr/bin/python3", "-I", "-S", "-B", resolver, slot_id, "worker_gid"], text=True).strip())
    gids = sorted({int(value) for value in subprocess.check_output(["/usr/bin/id", "-G", user], text=True).split()} - {primary})
    if set(gids) not in ({12, 61, 100}, {12, 61, 100, 396}): raise RuntimeError("unreviewed worker ambient groups")
    rows[slot_id] = gids
pathlib.Path(destination).write_text(json.dumps(rows, sort_keys=True, separators=(",", ":")))
PY
LEGACY_STATE_DIGEST="$(current_legacy_state_digest)"
/usr/bin/python3 -I -S -B "$TOPOLOGY" --release-root "$RELEASE_ROOT" \
  --template "$RELEASE_ROOT/ops/executive_os/$WORKER_TEMPLATE" \
  --attestation-sha256 "$ATTESTATION_SHA256" --supplementary-gids-json "$GIDS_JSON" \
  --legacy-state-digest "$LEGACY_STATE_DIGEST" \
  --destination "$TOPOLOGY_STAGE" >/dev/null || refuse "inert broker topology render refused"

for label in "${H0_LABELS[@]}"; do
  /bin/launchctl disable "system/$label"
  /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
  label_disabled_unloaded "$label" || refuse "H0 label did not remain disabled and unloaded"
done

install_topology_artifacts() {
  local slot_id slot_group config_target attestation_target plist_target temporary
  NEW_TOPOLOGY_PATHS=()
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    slot_group="$(slot_field "$slot_id" worker_group)"
    config_target="$SYSTEM_ROOT/config/worker-$slot_id.json"
    attestation_target="$SYSTEM_ROOT/codex-attestation-$CODEX_VERSION-$slot_id.json"
    plist_target="/Library/LaunchDaemons/com.mastermind.executive.worker.$slot_id.plist"
    /usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/config"
    temporary="$config_target.$(/usr/bin/uuidgen).tmp"; /usr/bin/install -o root -g "$slot_group" -m 0440 "$TOPOLOGY_STAGE/worker-$slot_id.json" "$temporary"; /bin/mv "$temporary" "$config_target"; NEW_TOPOLOGY_PATHS+=("$config_target")
    temporary="$attestation_target.$(/usr/bin/uuidgen).tmp"; /usr/bin/install -o root -g "$slot_group" -m 0440 "$ATTESTATION_STAGE" "$temporary"; /bin/mv "$temporary" "$attestation_target"; NEW_TOPOLOGY_PATHS+=("$attestation_target")
    temporary="$plist_target.$(/usr/bin/uuidgen).tmp"; /usr/bin/install -o root -g wheel -m 0644 "$TOPOLOGY_STAGE/com.mastermind.executive.worker.$slot_id.plist" "$temporary"; /bin/mv "$temporary" "$plist_target"; NEW_TOPOLOGY_PATHS+=("$plist_target")
  done
}

install_topology_artifacts
verify_topology "$TOPOLOGY_STAGE/broker-topology.json" || refuse "first inert topology install did not verify"
verify_legacy_files_unchanged || refuse "legacy Executive files changed during H0 installation"

ROLLBACK_DRILL_ROOT="$ARCHIVE_ROOT/rollback-drill-$(/bin/date -u +%Y%m%dT%H%M%SZ)-$(/usr/bin/uuidgen)"
/usr/bin/install -d -o root -g wheel -m 0700 "$ROLLBACK_DRILL_ROOT"
for path in "${NEW_TOPOLOGY_PATHS[@]}"; do ROLLBACK_INDEX=$((ROLLBACK_INDEX + 1)); /bin/mv "$path" "$ROLLBACK_DRILL_ROOT/$ROLLBACK_INDEX-$(/usr/bin/basename "$path")"; done
NEW_TOPOLOGY_PATHS=()
[ "$ROLLBACK_INDEX" -eq 9 ] || refuse "rollback drill moved artifact count differs"
[ "$(/usr/bin/find "$ROLLBACK_DRILL_ROOT" -mindepth 1 -maxdepth 1 -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" -eq 9 ] || refuse "rollback drill archive inventory differs"
for label in "${H0_LABELS[@]}"; do label_disabled_unloaded "$label" || refuse "rollback drill changed disabled service state"; done
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do [ ! -e "/var/run/mastermind-executive/worker-$slot_id.sock" ] || refuse "rollback drill left a socket node"; done
ROLLBACK_DRILL_RECEIPT="$ROLLBACK_DRILL_ROOT/rollback-receipt.json"
/usr/bin/python3 -I -S -B - "$TOPOLOGY_STAGE/broker-topology.json" "$TOPOLOGY_STAGE/rollback-contract.json" "$ROLLBACK_DRILL_ROOT" "$ROLLBACK_DRILL_RECEIPT" <<'PY'
import hashlib, json, pathlib, sys
topology, contract, archive, destination = map(pathlib.Path, sys.argv[1:])
artifacts = [
    {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for path in sorted(archive.iterdir())
    if path.is_file() and not path.is_symlink()
]
if len(artifacts) != 9:
    raise RuntimeError("rollback drill artifact inventory differs")
value = {"schema_version": "mastermind.executive_capacity_h0_rollback_receipt/v1", "outcome": "SHRINK_ONLY_ROLLBACK_PASS",
         "broker_topology_digest": hashlib.sha256(topology.read_bytes()).hexdigest(),
         "rollback_contract_digest": hashlib.sha256(contract.read_bytes()).hexdigest(), "moved_artifact_count": 9,
         "archive_root": str(archive), "artifacts": artifacts,
         "service_state": "labels_disabled_unloaded", "socket_state": "nodes_absent", "credential_state": "not_read_or_changed",
         "preserved_state": ["service_principals", "provider_homes", "credentials", "immutable_releases", "capacity_source_release", "capacity_runtime", "provider_control_telemetry", "legacy_phase1c_artifacts"]}
destination.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
PY
/usr/sbin/chown root:wheel "$ROLLBACK_DRILL_RECEIPT"; /bin/chmod 0400 "$ROLLBACK_DRILL_RECEIPT"
ROLLBACK_DRILL_DIGEST="$(/usr/bin/shasum -a 256 "$ROLLBACK_DRILL_RECEIPT" | /usr/bin/awk '{print $1}')"

install_topology_artifacts
verify_topology "$TOPOLOGY_STAGE/broker-topology.json" || refuse "reinstalled inert topology did not verify after rollback drill"
verify_legacy_files_unchanged || refuse "legacy Executive files changed during rollback drill"

RUNTIME_RECORD_DIGEST="$(/bin/echo "$RUNTIME_EVIDENCE" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["pyyaml_record_sha256"])')"
RUNTIME_TREE_DIGEST="$(/bin/echo "$RUNTIME_EVIDENCE" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["runtime_tree_sha256"])')"
TOPOLOGY_DIGEST="$(/usr/bin/shasum -a 256 "$TOPOLOGY_STAGE/broker-topology.json" | /usr/bin/awk '{print $1}')"
ROLLBACK_CONTRACT_DIGEST="$(/usr/bin/shasum -a 256 "$TOPOLOGY_STAGE/rollback-contract.json" | /usr/bin/awk '{print $1}')"

/usr/bin/install -d -o root -g wheel -m 0700 "$GENERATION_STAGE"
RENDERED="$GENERATION_STAGE/rendered.json"
/usr/bin/python3 -I -S -B "$CONTRACT" render --material-source-digest "$MATERIAL_SOURCE_DIGEST" \
  --pyyaml-record-sha256 "$RUNTIME_RECORD_DIGEST" --runtime-tree-sha256 "$RUNTIME_TREE_DIGEST" \
  --mastermind-commit "$EXPECTED_MASTERMIND_SHA" --broker-topology-digest "$TOPOLOGY_DIGEST" \
  --rollback-contract-digest "$ROLLBACK_CONTRACT_DIGEST" --rollback-drill-receipt-digest "$ROLLBACK_DRILL_DIGEST" >"$RENDERED"
/usr/bin/python3 -I -S -B - "$RENDERED" "$GENERATION_STAGE" "$TOPOLOGY_STAGE" "$ROLLBACK_DRILL_RECEIPT" <<'PY'
import json, os, pathlib, sys
rendered, destination, topology, rollback_receipt = map(pathlib.Path, sys.argv[1:]); value = json.loads(rendered.read_text())
payloads = {"components.json": json.dumps(value["components"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            "source-config.json": json.dumps(value["source_config"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            "host-preparation-receipt.json": json.dumps(value["host_receipt"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            "broker-topology.json": (topology / "broker-topology.json").read_bytes(),
            "rollback-contract.json": (topology / "rollback-contract.json").read_bytes(),
            "rollback-drill-receipt.json": rollback_receipt.read_bytes()}
for name, payload in payloads.items():
    fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try: os.write(fd, payload); os.fsync(fd)
    finally: os.close(fd)
rendered.unlink()
PY
/usr/sbin/chown -R root:wheel "$GENERATION_STAGE"; /bin/chmod 0444 "$GENERATION_STAGE"/*.json; /bin/chmod 0555 "$GENERATION_STAGE"
SOURCE_CONFIG_DIGEST="$(/usr/bin/python3 -I -S -B - "$GENERATION_STAGE/host-preparation-receipt.json" <<'PY'
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["source_config_digest"])
PY
)"
verify_generation "$GENERATION_STAGE" candidate || refuse "candidate H0 generation did not verify"
verify_materialized_source "$SOURCE_ROOT" || refuse "installed source changed before commit"
verify_runtime_tree "$RUNTIME_ROOT" >/dev/null || refuse "installed runtime changed before commit"
verify_telemetry_boundary || refuse "telemetry boundary changed before commit"
verify_release || refuse "release changed before commit"
verify_topology "$TOPOLOGY_STAGE/broker-topology.json" || refuse "topology changed before commit"
verify_legacy_files_unchanged || refuse "legacy Executive files changed before commit"
for label in "${LEGACY_LABELS[@]}"; do label_disabled_unloaded "$label" || refuse "legacy service state changed before commit"; done

GENERATION_TARGET="$GENERATION_ROOT/$SOURCE_CONFIG_DIGEST"
[ ! -e "$GENERATION_TARGET" ] && [ ! -L "$GENERATION_TARGET" ] || refuse "capacity generation target already exists"
GENERATION_CANDIDATE="$GENERATION_ROOT/.candidate-$SOURCE_CONFIG_DIGEST-$(/usr/bin/uuidgen)"
/bin/mv "$GENERATION_STAGE" "$GENERATION_CANDIDATE"
archive_path "$STAGING_SESSION" completed-stage
STAGING_SESSION=""
verify_generation "$GENERATION_CANDIDATE" candidate || refuse "moved H0 generation candidate did not verify"
/bin/mv "$GENERATION_CANDIDATE" "$GENERATION_TARGET"
GENERATION_CANDIDATE=""
COMMITTED="true"
/bin/echo "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"
/bin/echo "next: rerun independent CF2-P0; OAuth, routing, worker execution, and CF2-I remain held"
