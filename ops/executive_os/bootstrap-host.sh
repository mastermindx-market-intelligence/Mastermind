#!/bin/bash
# One-time, root-only macOS account and filesystem bootstrap for Executive OS.
# This script never installs code, copies credentials, starts services, or
# removes existing data. Re-running it verifies the established identities.
set -euo pipefail
umask 077

SCRIPT_DIR="$(/usr/bin/dirname "${BASH_SOURCE[0]}")"
SYSTEM_PYTHON="/usr/bin/python3"
PROVIDER_SLOT_RESOLVER="$SCRIPT_DIR/provider_worker_slots.py"
PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")
CONTROL_USER="_mastermind_exec"
CONTROL_GROUP="_mastermind_exec"
WORKER_USER="_mastermind_worker"
WORKER_GROUP="_mastermind_worker"
OPS_GROUP="_mastermind_ops"
CONTROL_UID="450"
CONTROL_GID="450"
WORKER_UID="451"
WORKER_GID="451"
OPS_GID="453"
OPERATOR_USER=""
SECONDARY_WORKER_ID=""
SECONDARY_WORKER_USER=""
SECONDARY_WORKER_GROUP=""
SECONDARY_WORKER_UID=""
SECONDARY_WORKER_GID=""
SECONDARY_MODE=false
ORDINARY_OPTIONS=false
SEEN_OPTIONS=" "

# --- BEGIN native ACL guard ---
# Use the Apple OS runtime before trusting the candidate /Library Python.
# Its Ruby/Fiddle loader stays inside the OS System framework; no user gems,
# RUBYOPT, RUBYLIB, DYLD environment, candidate interpreter or CLI selector.
require_native_no_acl() {
  /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C /usr/bin/ruby \
    --disable-gems --disable=rubyopt - "$@" <<'MASTERMIND_NATIVE_ACL_RUBY'
# frozen_string_literal: true
# native_acl.rb -- Darwin native extended-ACL bootstrap guard (Ruby 2.6, Fiddle).
#
# Contract: exit 0  == every inspected inode certified free of a native ACL.
#           exit 65 == bounded refusal (ACL present -- even an empty allocated
#           ACL --, unsupported inode type, missing path, identity drift,
#           traversal error, unavailable native API/runtime, usage error).
# There is no fallback and no success text: any condition that cannot be
# positively certified refuses. Missing OS runtime/API refuses; it never
# degrades to POSIX-mode heuristics. This helper never mutates anything
# (no delete/chmod/chown, no content or credential reads) and invokes no
# external commands.
#
# CLI:  ruby --disable-gems --disable=rubyopt - <one|tree> <abs-path>...
# "one"  inspects each given path exactly, the object itself (a symlink is
#        inspected as the link, never its target).
# "tree" inspects each named directory recursively without following
#        symlinks; every inode including symlink entries is inspected.
#
# Identity checking is sampled (lstat before/after each native query) and is
# valid only under a trusted owner; it is not atomic malicious-root
# containment.

module NativeAcl
  EXIT_OK = 0
  EXIT_REFUSE = 65

  # Refusal reasons are a fixed bounded symbol set; the CLI prints only the
  # generic prefix plus the symbol, never paths, errnos or payloads.
  class Refusal < StandardError
    attr_reader :reason
    def initialize(reason)
      @reason = reason
      super("refusal")
    end
  end

  # --- pure argument policy -------------------------------------------------
  class PathPolicy
    MODES = %w[one tree].freeze

    # -> [mode, [paths]]; raises Refusal(:usage) on anything else.
    def self.parse(argv)
      args = Array(argv)
      mode = args.shift
      raise Refusal, :usage unless MODES.include?(mode)
      raise Refusal, :usage if args.empty?
      args.each do |p|
        raise Refusal, :usage unless p.is_a?(String)
        raise Refusal, :usage if p.include?("\0")
        raise Refusal, :usage unless p.start_with?("/")
      end
      [mode, args]
    end
  end

  # --- pure identity tuple --------------------------------------------------
  # mtime/ctime compared exactly; atime deliberately excluded per contract.
  class Identity
    FIELDS = %i[dev ino mode uid gid nlink size mtime ctime].freeze

    def self.capture(stat)
      FIELDS.map { |f| stat.__send__(f) }
    end

    def self.same?(a, b)
      capture(a) == capture(b)
    end
  end

  # --- filesystem collaborators (real implementations; tests inject fakes) --
  class RealLstat
    def lstat(path) # no-follow
      File.lstat(path)
    rescue Errno::ENOENT
      raise Refusal, :missing
    rescue SystemCallError
      raise Refusal, :lstat_error
    end
  end

  class RealEntries
    def children(dir) # names only; sorted for determinism; never follows
      out = []
      Dir.open(dir) { |d| d.each_child { |n| out << n } }
      out.sort
    rescue SystemCallError
      raise Refusal, :traverse_error
    end
  end

  # --- native ABI (isolated; resolves lazily, refuses when unavailable) -----
  class NativeResolver
    ACL_TYPE_EXTENDED = 0x100
    RUBY_FRAMEWORK_PREFIX = "/System/Library/Frameworks/Ruby.framework/".freeze

    # -> :absent (NULL + ENOENT only) or an allocated pointer object.
    # Any allocated ACL, even an empty one, is returned as present.
    def get_link(path)
      ensure_functions!
      reset_last_error!
      ptr = @get_link_fn.call(path, ACL_TYPE_EXTENDED)
      # An allocated ACL must reach the single free attempt without any
      # dependency on errno (which is relevant only to a NULL result).
      return ptr unless ptr.null?
      return :absent if read_last_error == enoent
      raise Refusal, :acl_error
    end

    # int acl_free(void*). Called at most once per allocated pointer; the
    # caller (AclProbe) never retries, even if this raises.
    def acl_free(ptr)
      ensure_functions!
      @free_fn.call(ptr)
    end

    private

    def enoent
      Errno::ENOENT::Errno
    end

    def reset_last_error!
      raise Refusal, :runtime unless Fiddle.respond_to?(:last_error=) &&
                                     Fiddle.respond_to?(:last_error)
      Fiddle.send(:last_error=, 0)
    end

    def read_last_error
      raise Refusal, :runtime unless Fiddle.respond_to?(:last_error)
      value = Fiddle.last_error
      raise Refusal, :runtime unless value.is_a?(Integer)
      value
    end

    def ensure_functions!
      return if @get_link_fn
      load_fiddle!
      handle = default_handle
      get_link_fn = Fiddle::Function.new(
        symbol!(handle, "acl_get_link_np"),
        [Fiddle::TYPE_VOIDP, Fiddle::TYPE_INT],
        Fiddle::TYPE_VOIDP
      )
      free_fn = Fiddle::Function.new(
        symbol!(handle, "acl_free"),
        [Fiddle::TYPE_VOIDP],
        Fiddle::TYPE_INT
      )
      @get_link_fn, @free_fn = get_link_fn, free_fn
    end

    def load_fiddle!
      $LOAD_PATH.replace(
        $LOAD_PATH.select do |p|
          p.respond_to?(:start_with?) && p.start_with?(RUBY_FRAMEWORK_PREFIX)
        end
      )
      require "fiddle"
      raise Refusal, :runtime unless defined?(Fiddle::Function) &&
                                     defined?(Fiddle::TYPE_VOIDP)
    rescue Refusal
      raise
    rescue StandardError, LoadError
      raise Refusal, :runtime
    end

    def default_handle
      Fiddle::Handle::DEFAULT
    rescue StandardError
      begin
        Fiddle.dlopen(nil)
      rescue StandardError
        raise Refusal, :runtime
      end
    end

    def symbol!(handle, name)
      handle[name]
    rescue StandardError
      raise Refusal, :runtime
    end
  end

  # --- allocation-safe probe: free exactly once, never retried --------------
  # The allocated pointer stays a local; the single acl_free attempt happens
  # before any other fallible work, so every refusal path (including a throw
  # out of acl_free itself) leaves exactly one free attempt and no leak from
  # our side and no double free.
  class AclProbe
    def initialize(resolver)
      @resolver = resolver
    end

    def query(path)
      ptr = @resolver.get_link(path)
      return :absent if ptr.equal?(:absent)
      raise Refusal, :acl_error if ptr.nil? || !ptr.respond_to?(:null?)
      raise Refusal, :acl_error if ptr.null?
      rc = begin
        @resolver.acl_free(ptr)
      rescue Refusal
        raise
      rescue Exception
        raise Refusal, :acl_free_error
      end
      raise Refusal, :acl_free_error unless rc.is_a?(Integer) && rc.zero?
      raise Refusal, :acl_present
    end
  end

  # --- inspection core ------------------------------------------------------
  class Inspector
    def initialize(lstat:, probe:, entries:)
      @lstat = lstat
      @probe = probe
      @entries = entries
    end

    def run(mode, paths)
      paths.each { |p| mode == "one" ? inspect_one(p) : inspect_tree(p) }
      :ok
    end

    private

    def inspect_one(path)
      before = take_lstat(path)
      classify!(before)
      @probe.query(path)
      after = take_lstat(path)
      identity!(before, after)
    end

    def inspect_tree(root)
      st = take_lstat(root)
      raise Refusal, :not_directory unless st.directory?
      walk_dir(root, st)
    end

    def walk_dir(dir, expected)
      before = take_lstat(dir)
      raise Refusal, :not_directory unless before.directory?
      identity!(expected, before)
      @probe.query(dir)
      @entries.children(dir).each do |name|
        child = File.join(dir, name)
        cst = take_lstat(child) # no-follow; missing entry refuses, never skips
        classify!(cst)
        if cst.directory?
          walk_dir(child, cst)
        else
          @probe.query(child)
          identity!(cst, take_lstat(child))
        end
      end
      identity!(before, take_lstat(dir))
    end

    def take_lstat(path)
      @lstat.lstat(path)
    end

    def classify!(st)
      return if st.file? || st.directory? || st.symlink?
      raise Refusal, :unsupported
    end

    def identity!(a, b)
      raise Refusal, :identity unless Identity.same?(a, b)
    end
  end

  # --- CLI entry ------------------------------------------------------------
  class Runner
    attr_reader :last_reason

    def initialize(lstat: nil, resolver: nil, entries: nil)
      # Collaborator kwargs exist for the test harness only; the CLI passes
      # nothing, so the real native library and filesystem are always used.
      @lstat = lstat
      @resolver = resolver
      @entries = entries
      @last_reason = nil
    end

    def run(argv)
      mode, paths = PathPolicy.parse(argv)
      inspector = Inspector.new(
        lstat: @lstat || RealLstat.new,
        probe: AclProbe.new(@resolver || NativeResolver.new),
        entries: @entries || RealEntries.new
      )
      inspector.run(mode, paths)
      EXIT_OK
    rescue Refusal => e
      @last_reason = e.reason
      report(e.reason)
      EXIT_REFUSE
    rescue StandardError
      @last_reason = :error
      report(:error)
      EXIT_REFUSE
    end

    private

    def report(reason)
      $stderr.puts("native_acl: refused (#{reason.to_s[0, 40]})")
    end
  end
end

# Main fires only for real CLI invocations (stdin script or executed file),
# never when the definitions are loaded by the test harness.
if $PROGRAM_NAME == "-" || __FILE__ == $PROGRAM_NAME
  exit(NativeAcl::Runner.new.run(ARGV))
end
MASTERMIND_NATIVE_ACL_RUBY
}
# --- END native ACL guard ---

slot_field() {
  local slot_id="$1"
  local field="$2"
  "$SYSTEM_PYTHON" -I -S -B "$PROVIDER_SLOT_RESOLVER" "$slot_id" "$field"
}

usage() {
  /bin/echo "usage: $0 --operator-user NAME [--control-uid N] [--worker-uid N] [--ops-gid N]" >&2
  /bin/echo "secondary-only: $0 --secondary-worker-id ID --secondary-worker-user NAME --secondary-worker-group NAME --secondary-worker-uid N --secondary-worker-gid N" >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] && [ -n "$2" ] || usage
  case "$SEEN_OPTIONS" in *" $1 "*) usage ;; esac
  SEEN_OPTIONS="$SEEN_OPTIONS$1 "
  case "$1" in
    --secondary-worker-id) SECONDARY_MODE=true; SECONDARY_WORKER_ID="$2"; shift 2 ;;
    --secondary-worker-user) SECONDARY_MODE=true; SECONDARY_WORKER_USER="$2"; shift 2 ;;
    --secondary-worker-group) SECONDARY_MODE=true; SECONDARY_WORKER_GROUP="$2"; shift 2 ;;
    --secondary-worker-uid) SECONDARY_MODE=true; SECONDARY_WORKER_UID="$2"; shift 2 ;;
    --secondary-worker-gid) SECONDARY_MODE=true; SECONDARY_WORKER_GID="$2"; shift 2 ;;
    --operator-user) ORDINARY_OPTIONS=true; OPERATOR_USER="${2:-}"; shift 2 ;;
    --control-uid) ORDINARY_OPTIONS=true; CONTROL_UID="${2:-}"; CONTROL_GID="${2:-}"; shift 2 ;;
    --worker-uid) ORDINARY_OPTIONS=true; WORKER_UID="${2:-}"; WORKER_GID="${2:-}"; shift 2 ;;
    --ops-gid) ORDINARY_OPTIONS=true; OPS_GID="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "bootstrap-host.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "bootstrap-host.sh supports macOS only" >&2
  exit 69
}
[ -x "$SYSTEM_PYTHON" ] || {
  /bin/echo "system Python is unavailable for worker-slot resolution" >&2
  exit 69
}
[ -f "$PROVIDER_SLOT_RESOLVER" ] && [ ! -L "$PROVIDER_SLOT_RESOLVER" ] || {
  /bin/echo "reviewed provider worker-slot resolver is unavailable" >&2
  exit 69
}
if [ "$SECONDARY_MODE" = true ]; then
  [ "$ORDINARY_OPTIONS" = false ] || usage
else
[ -n "$OPERATOR_USER" ] || usage
case "$OPERATOR_USER" in
  [A-Za-z_]* ) ;;
  *) /bin/echo "operator account name is invalid" >&2; exit 65 ;;
esac
case "$OPERATOR_USER" in *[!A-Za-z0-9_.-]*) /bin/echo "operator account name is invalid" >&2; exit 65 ;; esac
/usr/bin/id "$OPERATOR_USER" >/dev/null 2>&1 || {
  /bin/echo "operator user does not exist: $OPERATOR_USER" >&2
  exit 65
}
OPERATOR_UID="$(/usr/bin/id -u "$OPERATOR_USER")"
fi

for numeric in "$CONTROL_UID" "$WORKER_UID" "$OPS_GID"; do
  case "$numeric" in
    ''|*[!0-9]*) /bin/echo "UID/GID values must be decimal integers" >&2; exit 65 ;;
  esac
  [ "$numeric" -ge 400 ] && [ "$numeric" -lt 500 ] || {
    /bin/echo "service UID/GID values must be in the reviewed 400-499 range" >&2
    exit 65
  }
done
[ "$CONTROL_UID" -ne "$WORKER_UID" ] || {
  /bin/echo "control and worker UIDs must be distinct" >&2
  exit 65
}

read_attribute() {
  local record="$1"
  local attribute="$2"
  LC_ALL=C LANG=C /usr/bin/dscl . -read "$record" "$attribute" 2>/dev/null \
    | /usr/bin/awk -v attribute="$attribute" '
        NR == 1 {
          standard=attribute ":"
          native="dsAttrTypeNative:" attribute ":"
          if (index($0, standard) == 1) {
            value=substr($0, length(standard) + 1)
          } else if (index($0, native) == 1) {
            value=substr($0, length(native) + 1)
          } else {
            malformed=1
            next
          }
          sub(/^[[:space:]]*/, "", value)
          next
        }
        {value=value " " $0}
        END {
          if (NR == 0 || malformed) exit 65
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
          print value
        }
      '
}

valid_uuid() {
  /bin/echo "$1" | /usr/bin/grep -Eq \
    '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
}

sorted_words() {
  /bin/echo "$1" \
    | /usr/bin/awk '{for (field_number=1; field_number<=NF; field_number++) print $field_number}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

assert_reviewed_authentication_authority() {
  local name="$1"
  local authority authority_err authority_error authority_out authority_status
  authority_out="$(/usr/bin/mktemp /private/tmp/mastermind-authority.stdout.XXXXXX)"
  authority_err="$(/usr/bin/mktemp /private/tmp/mastermind-authority.stderr.XXXXXX)"
  if LC_ALL=C LANG=C /usr/bin/dscl . -read "/Users/$name" AuthenticationAuthority \
    >"$authority_out" 2>"$authority_err"; then
    authority_status=0
  else
    authority_status=$?
  fi
  authority="$(/bin/cat "$authority_out")"
  authority_error="$(/bin/cat "$authority_err")"
  /bin/rm -f -- "$authority_out" "$authority_err"
  [ "$authority_status" -eq 0 ] || {
    /bin/echo "could not inspect the authentication authority for $name" >&2
    exit 65
  }
  case "$authority|$authority_error" in
    '|No such key: AuthenticationAuthority') authority='' ;;
    'AuthenticationAuthority: ;DisabledUser;|') authority=';DisabledUser;' ;;
    *)
      /bin/echo "service account $name has an unreadable authentication authority" >&2
      exit 65
      ;;
  esac
  case "$authority" in
    ''|';DisabledUser;') ;;
    *)
      /bin/echo "service account $name has an unreviewed authentication authority" >&2
      exit 65
      ;;
  esac
}

authentication_state() {
  local name="$1"
  local disabled_expected observed probe status unsupported_expected
  probe="$(/usr/bin/uuidgen)"
  if observed="$(LC_ALL=C LANG=C /usr/bin/dscl . -authonly "$name" "$probe" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  disabled_expected='<dscl_cmd> DS Error: -14167 (eDSAuthAccountDisabled)
Authentication for node /Local/Default failed. (-14167, eDSAuthAccountDisabled)'
  unsupported_expected='<dscl_cmd> DS Error: -14091 (eDSAuthMethodNotSupported)
Authentication for node /Local/Default failed. (-14091, eDSAuthMethodNotSupported)'
  if [ "$status" -eq 87 ] && [ "$observed" = "$disabled_expected" ]; then
    /bin/echo disabled
    return
  fi
  if [ "$status" -eq 11 ] && [ "$observed" = "$unsupported_expected" ]; then
    /bin/echo needs_disable
    return
  fi
  /bin/echo "service account $name has an unreviewed authentication state" >&2
  return 65
}

assert_authentication_disabled() {
  local name="$1"
  local state
  assert_reviewed_authentication_authority "$name"
  state="$(authentication_state "$name")" || {
    /bin/echo "could not inspect authentication for service account $name" >&2
    exit 65
  }
  [ "$state" = disabled ] || {
    /bin/echo "service account $name is not authentication-disabled" >&2
    exit 65
  }
}

sleep_for_authentication_propagation() {
  /bin/sleep 1
}

wait_for_authentication_disabled() {
  local name="$1"
  local attempt state
  for attempt in 1 2 3 4 5; do
    assert_reviewed_authentication_authority "$name"
    state="$(authentication_state "$name")" || exit 65
    if [ "$state" = disabled ]; then
      return
    fi
    [ "$state" = needs_disable ] || {
      /bin/echo "service account $name entered an unreviewed authentication state" >&2
      exit 65
    }
    if [ "$attempt" -lt 5 ]; then
      sleep_for_authentication_propagation
    fi
  done
  /bin/echo "service account $name did not reach authentication-disabled state" >&2
  exit 65
}

ensure_authentication_disabled() {
  local name="$1"
  local state
  assert_reviewed_authentication_authority "$name"
  state="$(authentication_state "$name")" || exit 65
  if [ "$state" = needs_disable ]; then
    LC_ALL=C LANG=C /usr/bin/pwpolicy -n /Local/Default -u "$name" -disableuser \
      >/dev/null 2>&1 || {
      /bin/echo "could not disable authentication for service account $name" >&2
      exit 65
    }
  fi
  wait_for_authentication_disabled "$name"
}

ensure_numeric_unused() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  local expected_name="$4"
  local owners
  owners="$(numeric_owners "$record_type" "$attribute" "$numeric")"
  if [ -n "$owners" ] && [ "$owners" != "$expected_name" ]; then
    /bin/echo "$attribute $numeric has a non-exact owner set: $owners" >&2
    exit 65
  fi
}

numeric_owners() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  /usr/bin/dscl . -list "/$record_type" "$attribute" \
    | /usr/bin/awk -v numeric="$numeric" '$NF == numeric {print $1}' \
    | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
}

assert_numeric_owner() {
  local record_type="$1"
  local attribute="$2"
  local numeric="$3"
  local expected_name="$4"
  local owners
  owners="$(numeric_owners "$record_type" "$attribute" "$numeric")"
  [ "$owners" = "$expected_name" ] || {
    /bin/echo "$record_type $attribute $numeric owner set is not exactly $expected_name: $owners" >&2
    exit 65
  }
}

ensure_group() {
  local name="$1"
  local gid="$2"
  local verify_only="${3:-false}"
  ensure_numeric_unused Groups PrimaryGroupID "$gid" "$name"
  if /usr/bin/dscl . -read "/Groups/$name" >/dev/null 2>&1; then
    [ "$(read_attribute "/Groups/$name" PrimaryGroupID)" = "$gid" ] || {
      /bin/echo "existing group $name has the wrong GID" >&2
      exit 65
    }
    [ "$(read_attribute "/Groups/$name" RealName)" = "$name service group" ] || {
      /bin/echo "existing group $name has the wrong reviewed identity" >&2
      exit 65
    }
    valid_uuid "$(read_attribute "/Groups/$name" GeneratedUID)" || {
      /bin/echo "existing group $name has no valid GeneratedUID" >&2
      exit 65
    }
    return
  fi
  [ "$verify_only" != true ] || return 0
  /usr/bin/dscl . -create "/Groups/$name"
  /usr/bin/dscl . -create "/Groups/$name" PrimaryGroupID "$gid"
  /usr/bin/dscl . -create "/Groups/$name" RealName "$name service group"
  /usr/bin/dscl . -create "/Groups/$name" GeneratedUID "$(/usr/bin/uuidgen)"
}

ensure_user() {
  local name="$1"
  local uid="$2"
  local gid="$3"
  local home="$4"
  local verify_only="${5:-false}"
  ensure_numeric_unused Users UniqueID "$uid" "$name"
  if /usr/bin/dscl . -read "/Users/$name" >/dev/null 2>&1; then
    [ "$(read_attribute "/Users/$name" UniqueID)" = "$uid" ] || {
      /bin/echo "existing user $name has the wrong UID" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" PrimaryGroupID)" = "$gid" ] || {
      /bin/echo "existing user $name has the wrong primary GID" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" RealName)" = "$name service account" ] || {
      /bin/echo "existing user $name has the wrong reviewed identity" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" NFSHomeDirectory)" = "$home" ] || {
      /bin/echo "existing user $name has the wrong home" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" UserShell)" = "/usr/bin/false" ] || {
      /bin/echo "existing user $name does not have the disabled shell" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" IsHidden)" = "1" ] || {
      /bin/echo "existing user $name is not hidden" >&2
      exit 65
    }
    [ "$(read_attribute "/Users/$name" Password)" = "*" ] || {
      /bin/echo "existing user $name does not have a disabled password" >&2
      exit 65
    }
    valid_uuid "$(read_attribute "/Users/$name" GeneratedUID)" || {
      /bin/echo "existing user $name has no valid GeneratedUID" >&2
      exit 65
    }
    if [ "$verify_only" = true ]; then
      assert_reviewed_authentication_authority "$name"
      local observed_auth
      observed_auth="$(authentication_state "$name")" || exit 65
      case "$observed_auth" in disabled|needs_disable) ;; *) exit 65 ;; esac
    else
      ensure_authentication_disabled "$name"
    fi
    return
  fi
  [ "$verify_only" != true ] || return 0
  /usr/bin/dscl . -create "/Users/$name"
  /usr/bin/dscl . -create "/Users/$name" UniqueID "$uid"
  /usr/bin/dscl . -create "/Users/$name" PrimaryGroupID "$gid"
  /usr/bin/dscl . -create "/Users/$name" RealName "$name service account"
  /usr/bin/dscl . -create "/Users/$name" NFSHomeDirectory "$home"
  /usr/bin/dscl . -create "/Users/$name" UserShell /usr/bin/false
  /usr/bin/dscl . -create "/Users/$name" IsHidden 1
  /usr/bin/dscl . -create "/Users/$name" Password '*'
  valid_uuid "$(read_attribute "/Users/$name" GeneratedUID)" || {
    /bin/echo "new user $name has no valid auto-generated GeneratedUID" >&2
    exit 65
  }
  ensure_authentication_disabled "$name"
}

assert_exact_members() {
  local group="$1"
  local gid="$2"
  local expected_primary="$3"
  local expected_named="$4"
  local primary named uuid_members expected_uuids nested member member_uuid
  primary="$(
    /usr/bin/dscl . -list /Users PrimaryGroupID \
      | /usr/bin/awk -v gid="$gid" '$NF == gid {print $1}' \
      | /usr/bin/sort -u | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/[[:space:]]*$//'
  )"
  [ "$primary" = "$(sorted_words "$expected_primary")" ] || {
    /bin/echo "group $group contains an unreviewed primary-GID user" >&2
    exit 65
  }
  named="$(read_attribute "/Groups/$group" GroupMembership 2>/dev/null || true)"
  named="$(sorted_words "$named")"
  [ "$named" = "$(sorted_words "$expected_named")" ] || {
    /bin/echo "group $group contains unreviewed members" >&2
    exit 65
  }
  expected_uuids=""
  for member in $expected_named; do
    member_uuid="$(read_attribute "/Users/$member" GeneratedUID)"
    valid_uuid "$member_uuid" || {
      /bin/echo "reviewed member $member has no valid GeneratedUID" >&2
      exit 65
    }
    expected_uuids="$expected_uuids $member_uuid"
  done
  uuid_members="$(read_attribute "/Groups/$group" GroupMembers 2>/dev/null || true)"
  uuid_members="$(sorted_words "$(/bin/echo "$uuid_members" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  expected_uuids="$(sorted_words "$(/bin/echo "$expected_uuids" | /usr/bin/tr '[:lower:]' '[:upper:]')")"
  [ "$uuid_members" = "$expected_uuids" ] || {
    /bin/echo "group $group contains UUID-only or stale members" >&2
    exit 65
  }
  nested="$(read_attribute "/Groups/$group" NestedGroups 2>/dev/null || true)"
  if [ -n "$(sorted_words "$nested")" ]; then
    /bin/echo "group $group contains unreviewed nested groups" >&2
    exit 65
  fi
}


# SECONDARY_WORKER_FUNCTIONS_BEGIN
secondary_refuse() {
  /bin/echo "secondary worker bootstrap refused: $1" >&2
  exit 65
}

validate_secondary_worker() {
  local value reserved slot_id field
  [ -n "$SECONDARY_WORKER_ID" ] && [ "${#SECONDARY_WORKER_ID}" -le 64 ] || secondary_refuse "worker id"
  case "$SECONDARY_WORKER_ID" in [a-z]*) ;; *) secondary_refuse "worker id" ;; esac
  case "$SECONDARY_WORKER_ID" in *[!a-z0-9-]*) secondary_refuse "worker id" ;; esac
  for value in "$SECONDARY_WORKER_USER" "$SECONDARY_WORKER_GROUP"; do
    [ "${#value}" -le 31 ] || secondary_refuse "service name"
    case "$value" in _mastermind_[a-z0-9_]*) ;; *) secondary_refuse "service name" ;; esac
    case "$value" in *[!a-z0-9_]*) secondary_refuse "service name" ;; esac
    for reserved in "$CONTROL_USER" "$CONTROL_GROUP" "$WORKER_USER" "$WORKER_GROUP" "$OPS_GROUP" _mastermind_agent_relay; do
      [ "$value" != "$reserved" ] || secondary_refuse "reserved service name"
    done
  done
  for value in "$SECONDARY_WORKER_UID" "$SECONDARY_WORKER_GID"; do
    case "$value" in 4[0-9][0-9]) ;; *) secondary_refuse "service id" ;; esac
    for reserved in "$CONTROL_UID" "$CONTROL_GID" "$WORKER_UID" "$WORKER_GID" "$OPS_GID" 457; do
      [ "$value" != "$reserved" ] || secondary_refuse "reserved service id"
    done
  done
  [ "$SECONDARY_WORKER_ID" != codex-01 ] || secondary_refuse "reserved worker id"
  for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
    [ "$SECONDARY_WORKER_ID" != "$slot_id" ] || secondary_refuse "reserved worker id"
    for field in worker_user worker_group; do
      reserved="$(slot_field "$slot_id" "$field")" || secondary_refuse "slot identity unavailable"
      [ -n "$reserved" ] || secondary_refuse "slot identity empty"
      [ "$SECONDARY_WORKER_USER" != "$reserved" ] && [ "$SECONDARY_WORKER_GROUP" != "$reserved" ] || secondary_refuse "reserved slot name"
    done
    for field in worker_uid worker_gid; do
      reserved="$(slot_field "$slot_id" "$field")" || secondary_refuse "slot identity unavailable"
      case "$reserved" in 4[0-9][0-9]) ;; *) secondary_refuse "slot identity invalid" ;; esac
      [ "$SECONDARY_WORKER_UID" != "$reserved" ] && [ "$SECONDARY_WORKER_GID" != "$reserved" ] || secondary_refuse "reserved slot id"
    done
  done
}

secondary_record_exists() {
  local records
  records="$(/usr/bin/dscl . -list "/$1")" || secondary_refuse "directory enumeration failed"
  /usr/bin/printf '%s\n' "$records" | /usr/bin/grep -Fxq -- "$2"
}

require_secondary_directory() {
  local path="$1" expected="$2" allow_missing="${3:-false}"
  [ ! -L "$path" ] || secondary_refuse "directory is a symlink"
  if [ ! -e "$path" ]; then
    [ "$allow_missing" = true ] || secondary_refuse "required parent missing"
    return
  fi
  [ -d "$path" ] || secondary_refuse "directory has wrong type"
  [ "$(/usr/bin/stat -f '%u:%g:%Lp' "$path")" = "$expected" ] || secondary_refuse "directory metadata mismatch"
  require_native_no_acl one "$path" || secondary_refuse "directory ACL or native observation failure"
}

ensure_secondary_directory() {
  local path="$1" owner="$2" group="$3" mode="$4" expected="$5"
  require_secondary_directory "$path" "$expected" true
  if [ ! -e "$path" ]; then
    /bin/mkdir -m "$mode" -- "$path"
    /usr/sbin/chown "$owner:$group" "$path"
  fi
  require_secondary_directory "$path" "$expected"
}

bootstrap_secondary_worker() {
  validate_secondary_worker
  local canonical_runtime path primary="" named=""
  canonical_runtime="$(cd -P /var/db/mastermind-executive && /bin/pwd -P)" || secondary_refuse "runtime root unavailable"
  [ "$canonical_runtime" = /private/var/db/mastermind-executive ] || secondary_refuse "runtime root mismatch"
  local worker_root="$canonical_runtime/workers/$SECONDARY_WORKER_ID"
  local provider_home="$worker_root/provider-home"
  local state_root="$worker_root/state"
  local active_root="$worker_root/active"
  local jobs_root="$worker_root/jobs"
  local workspace_root="$jobs_root/workspaces"
  local run_root="$jobs_root/runs"
  local jobs_metadata="$CONTROL_UID:$SECONDARY_WORKER_GID:710"
  local worker_metadata="$SECONDARY_WORKER_UID:$SECONDARY_WORKER_GID:700"
  for path in /private /private/var /private/var/db; do
    require_secondary_directory "$path" '0:0:755'
  done
  require_secondary_directory "$canonical_runtime" '0:0:711'
  require_secondary_directory "$canonical_runtime/workers" '0:0:711'
  require_secondary_directory "$worker_root" '0:0:711' true
  for path in "$provider_home" "$state_root" "$active_root"; do
    require_secondary_directory "$path" "$worker_metadata" true
  done
  for path in "$jobs_root" "$workspace_root" "$run_root"; do
    require_secondary_directory "$path" "$jobs_metadata" true
  done
  # Verify the existing Control principal completely before extending its groups.
  secondary_record_exists Users "$CONTROL_USER" || secondary_refuse "Control user absent"
  secondary_record_exists Groups "$CONTROL_GROUP" || secondary_refuse "Control group absent"
  /usr/bin/dscl . -read "/Users/$CONTROL_USER" >/dev/null || secondary_refuse "Control user unreadable"
  /usr/bin/dscl . -read "/Groups/$CONTROL_GROUP" >/dev/null || secondary_refuse "Control group unreadable"
  assert_numeric_owner Users UniqueID "$CONTROL_UID" "$CONTROL_USER"
  assert_numeric_owner Groups PrimaryGroupID "$CONTROL_GID" "$CONTROL_GROUP"
  ensure_group "$CONTROL_GROUP" "$CONTROL_GID" true
  ensure_user "$CONTROL_USER" "$CONTROL_UID" "$CONTROL_GID" "$CONTROL_HOME" true
  assert_authentication_disabled "$CONTROL_USER"
  assert_exact_members "$CONTROL_GROUP" "$CONTROL_GID" "$CONTROL_USER" ""
  # Verify every existing identity before any create/disable/directory effect.
  if secondary_record_exists Users "$SECONDARY_WORKER_USER"; then
    /usr/bin/dscl . -read "/Users/$SECONDARY_WORKER_USER" >/dev/null || secondary_refuse "user unreadable"
    primary="$SECONDARY_WORKER_USER"
  fi
  # Primary-GID users can exist even if no group record has been created.
  local primary_owners
  primary_owners="$(numeric_owners Users PrimaryGroupID "$SECONDARY_WORKER_GID")" || secondary_refuse "primary-GID census failed"
  [ "$primary_owners" = "$primary" ] || secondary_refuse "unreviewed selected primary-GID user"
  if secondary_record_exists Groups "$SECONDARY_WORKER_GROUP"; then
    /usr/bin/dscl . -read "/Groups/$SECONDARY_WORKER_GROUP" >/dev/null || secondary_refuse "group unreadable"
    named="$(sorted_words "$(read_attribute "/Groups/$SECONDARY_WORKER_GROUP" GroupMembership 2>/dev/null || true)")"
    case "$named" in ""|"$CONTROL_USER") ;; *) secondary_refuse "unreviewed secondary group members" ;; esac
    assert_exact_members "$SECONDARY_WORKER_GROUP" "$SECONDARY_WORKER_GID" "$primary" "$named"
  fi
  ensure_group "$SECONDARY_WORKER_GROUP" "$SECONDARY_WORKER_GID" true
  ensure_user "$SECONDARY_WORKER_USER" "$SECONDARY_WORKER_UID" "$SECONDARY_WORKER_GID" "$provider_home" true
  ensure_group "$SECONDARY_WORKER_GROUP" "$SECONDARY_WORKER_GID"
  ensure_user "$SECONDARY_WORKER_USER" "$SECONDARY_WORKER_UID" "$SECONDARY_WORKER_GID" "$provider_home"
  assert_numeric_owner Users UniqueID "$SECONDARY_WORKER_UID" "$SECONDARY_WORKER_USER"
  assert_numeric_owner Groups PrimaryGroupID "$SECONDARY_WORKER_GID" "$SECONDARY_WORKER_GROUP"
  if [ "$named" != "$CONTROL_USER" ]; then
    /usr/sbin/dseditgroup -o edit -a "$CONTROL_USER" -t user "$SECONDARY_WORKER_GROUP"
  fi
  assert_exact_members "$SECONDARY_WORKER_GROUP" "$SECONDARY_WORKER_GID" "$SECONDARY_WORKER_USER" "$CONTROL_USER"
  ensure_secondary_directory "$worker_root" 0 0 0711 '0:0:711'
  for path in "$provider_home" "$state_root" "$active_root"; do
    ensure_secondary_directory "$path" "$SECONDARY_WORKER_UID" "$SECONDARY_WORKER_GID" 0700 "$worker_metadata"
  done
  for path in "$jobs_root" "$workspace_root" "$run_root"; do
    ensure_secondary_directory "$path" "$CONTROL_UID" "$SECONDARY_WORKER_GID" 0710 "$jobs_metadata"
  done
  /bin/echo "secondary worker bootstrap complete: $SECONDARY_WORKER_ID uid=$SECONDARY_WORKER_UID gid=$SECONDARY_WORKER_GID home=$provider_home"
}
# SECONDARY_WORKER_FUNCTIONS_END

SYSTEM_ROOT="/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT="/var/db/mastermind-executive"
CONTROL_HOME="$RUNTIME_ROOT/control/home"
PROVIDER_HOME="$RUNTIME_ROOT/workers/codex-01/provider-home"

if [ "$SECONDARY_MODE" = true ]; then
  bootstrap_secondary_worker
  exit 0
fi

ensure_numeric_unused Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"
ensure_group "$CONTROL_GROUP" "$CONTROL_GID"
ensure_group "$WORKER_GROUP" "$WORKER_GID"
ensure_group "$OPS_GROUP" "$OPS_GID"
ensure_user "$CONTROL_USER" "$CONTROL_UID" "$CONTROL_GID" "$CONTROL_HOME"
ensure_user "$WORKER_USER" "$WORKER_UID" "$WORKER_GID" "$PROVIDER_HOME"
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_user="$(slot_field "$slot_id" worker_user)"
  slot_group="$(slot_field "$slot_id" worker_group)"
  slot_uid="$(slot_field "$slot_id" worker_uid)"
  slot_gid="$(slot_field "$slot_id" worker_gid)"
  slot_home="$(slot_field "$slot_id" provider_home)"
  ensure_group "$slot_group" "$slot_gid"
  ensure_user "$slot_user" "$slot_uid" "$slot_gid" "$slot_home"
done

# Control may inspect worker-created run artifacts through the worker primary
# group. The worker broker receives only its exact reviewed macOS directory
# group vector and rejects control/operator or unknown supplementary groups.
/usr/sbin/dseditgroup -o edit -a "$CONTROL_USER" -t user "$WORKER_GROUP"
/usr/sbin/dseditgroup -o edit -a "$OPERATOR_USER" -t user "$OPS_GROUP"

/usr/sbin/dseditgroup -o checkmember -m "$CONTROL_USER" "$WORKER_GROUP" \
  | /usr/bin/grep -q 'yes' || {
    /bin/echo "control user is not a member of the worker artifact group" >&2
    exit 65
  }
/usr/sbin/dseditgroup -o checkmember -m "$OPERATOR_USER" "$OPS_GROUP" \
  | /usr/bin/grep -q 'yes' || {
    /bin/echo "operator user is not a member of the Executive ops group" >&2
    exit 65
  }


assert_exact_members "$CONTROL_GROUP" "$CONTROL_GID" "$CONTROL_USER" ""
assert_exact_members "$WORKER_GROUP" "$WORKER_GID" "$WORKER_USER" "$CONTROL_USER"
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_user="$(slot_field "$slot_id" worker_user)"
  slot_group="$(slot_field "$slot_id" worker_group)"
  slot_uid="$(slot_field "$slot_id" worker_uid)"
  slot_gid="$(slot_field "$slot_id" worker_gid)"
  assert_exact_members "$slot_group" "$slot_gid" "$slot_user" ""
  assert_numeric_owner Users UniqueID "$slot_uid" "$slot_user"
  assert_numeric_owner Groups PrimaryGroupID "$slot_gid" "$slot_group"
done
assert_exact_members "$OPS_GROUP" "$OPS_GID" "" "$OPERATOR_USER"
assert_numeric_owner Users UniqueID "$CONTROL_UID" "$CONTROL_USER"
assert_numeric_owner Users UniqueID "$WORKER_UID" "$WORKER_USER"
assert_numeric_owner Users UniqueID "$OPERATOR_UID" "$OPERATOR_USER"
assert_numeric_owner Groups PrimaryGroupID "$CONTROL_GID" "$CONTROL_GROUP"
assert_numeric_owner Groups PrimaryGroupID "$WORKER_GID" "$WORKER_GROUP"
assert_numeric_owner Groups PrimaryGroupID "$OPS_GID" "$OPS_GROUP"

/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/bin"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/config"
/usr/bin/install -d -o root -g wheel -m 0755 "$SYSTEM_ROOT/releases"

/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/control"
for directory in home db policy admin-checkout launch-receipts backups canaries; do
  /usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/control/$directory"
done
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs"
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs/workspaces"
/usr/bin/install -d -o "$CONTROL_USER" -g "$WORKER_GROUP" -m 0710 "$RUNTIME_ROOT/jobs/runs"
/usr/bin/install -d -o root -g wheel -m 0711 "$RUNTIME_ROOT/workers"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$RUNTIME_ROOT/workers/codex-01"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$PROVIDER_HOME"
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 "$RUNTIME_ROOT/workers/codex-01/state"
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_user="$(slot_field "$slot_id" worker_user)"
  slot_group="$(slot_field "$slot_id" worker_group)"
  slot_home="$(slot_field "$slot_id" provider_home)"
  slot_root="${slot_home%/provider-home}"
  [ "$slot_root" != "$slot_home" ] || {
    /bin/echo "provider home for $slot_id is outside the reviewed slot shape" >&2
    exit 65
  }
  /usr/bin/install -d -o "$slot_user" -g "$slot_group" -m 0700 "$slot_root"
  /usr/bin/install -d -o "$slot_user" -g "$slot_group" -m 0700 "$slot_home"
  /usr/bin/install -d -o "$slot_user" -g "$slot_group" -m 0700 "$slot_root/state"
done

# Explicit forbidden fixtures for the real secret-canary proof. Values are
# generated later by the acceptance command and never by this bootstrap.
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures/other-worker-home"
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 "$RUNTIME_ROOT/canary-fixtures/production-like"

/usr/bin/install -d -o root -g wheel -m 0755 /var/run/mastermind-executive
/usr/bin/install -d -o root -g wheel -m 0755 /var/log/mastermind-executive
/usr/bin/install -d -o "$CONTROL_USER" -g "$CONTROL_GROUP" -m 0700 /var/log/mastermind-executive/control
/usr/bin/install -d -o "$WORKER_USER" -g "$WORKER_GROUP" -m 0700 /var/log/mastermind-executive/worker
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_user="$(slot_field "$slot_id" worker_user)"
  slot_group="$(slot_field "$slot_id" worker_group)"
  /usr/bin/install -d -o "$slot_user" -g "$slot_group" -m 0700 \
    "/var/log/mastermind-executive/workers/$slot_id"
done

for protected_path in \
  "$SYSTEM_ROOT" "$SYSTEM_ROOT/bin" "$SYSTEM_ROOT/config" "$SYSTEM_ROOT/releases" \
  "$RUNTIME_ROOT" "$RUNTIME_ROOT/control" "$RUNTIME_ROOT/jobs" \
  "$RUNTIME_ROOT/jobs/workspaces" "$RUNTIME_ROOT/jobs/runs" \
  "$RUNTIME_ROOT/workers" "$RUNTIME_ROOT/workers/codex-01" "$PROVIDER_HOME" \
  /var/run/mastermind-executive /var/log/mastermind-executive; do
  require_native_no_acl one "$protected_path" || {
    /bin/echo "unexpected or unreadable filesystem ACL on $protected_path" >&2; exit 65
  }
done
for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do
  slot_home="$(slot_field "$slot_id" provider_home)"
  slot_root="${slot_home%/provider-home}"
  for protected_path in "$slot_root" "$slot_home" "$slot_root/state" \
    "/var/log/mastermind-executive/workers/$slot_id"; do
    require_native_no_acl one "$protected_path" || {
      /bin/echo "unexpected or unreadable filesystem ACL on $protected_path" >&2; exit 65
    }
  done
done

/bin/echo "host bootstrap complete"
/bin/echo "next: run install.sh, then provision each reviewed worker slot independently"
