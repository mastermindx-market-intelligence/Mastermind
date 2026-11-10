#!/bin/sh
# attack_team_server.sh — T6 security attacks against tools/mmos_team_server.
#
# Run by a later driver (not by the author). Exactly one result line per attempt:
#   ATTEMPT n <name>: DEFEAT|HELD|BYPASS — <one-line evidence>
# Evidence is counts/sizes/sha256 prefixes only; secret VALUES are never printed
# or stored. Final line: ATTACK SUMMARY: <n> DEFEAT, <n> HELD, <n> BYPASS.
# Exit 0 iff no attempt is BYPASS (DEFEAT and HELD are both acceptable).
#
# Attempts: (a)=1 credential-hunt, (b)=2 non-loopback-reach,
#           (c)=3 hostile-install, (d)=4 two-servers-one-home,
#           (e)=5 crash-loop-disk-fill.
#
# The live dev servers (com.mastermind.t3-team-dev on 3805, ...-dev2 on 3806)
# are OBSERVED only — never stopped, booted out, or modified.
set -u
umask 077

REPO_DIR=$(cd "$(dirname "$0")/../.." && pwd -P)
TEAM="$REPO_DIR/tools/mmos_team_server/team_server.sh"
RUNNER="$REPO_DIR/tools/mmos_team_server/server_runner.sh"

DEV_LABEL="com.mastermind.t3-team-dev"
DEV_ROOT="$HOME/.mastermind/mmos-dev/t3-team"
DEV_ROOT_B="$HOME/.mastermind/mmos-dev/t3-team-b"
DEV_PLIST="$HOME/Library/LaunchAgents/$DEV_LABEL.plist"
EVIDENCE_DIR="$HOME/.mastermind/mmos_evidence/t6-20261110"
T3_HOME="$HOME/.t3"

N_DEFEAT=0; N_HELD=0; N_BYPASS=0
result() { # n name verdict evidence
  case "$3" in
    DEFEAT) N_DEFEAT=$((N_DEFEAT + 1)) ;;
    HELD)   N_HELD=$((N_HELD + 1)) ;;
    BYPASS) N_BYPASS=$((N_BYPASS + 1)) ;;
  esac
  printf 'ATTEMPT %s %s: %s — %s\n' "$1" "$2" "$3" "$4"
}
note() { printf '  [d] %s\n' "$1"; }

TMP_PARENT=$(mktemp -d "${TMPDIR:-/tmp}/t6-attack.XXXXXX")
SFX="attack$$"
HOSTILE_LABEL="com.mastermind.t3-attack-hostile-$SFX"
COLLIDE_LABEL="com.mastermind.t3-attack-collision-$SFX"
FILL_LABEL="com.mastermind.t3-attack-diskfill-$SFX"
LA_DIR="$TMP_PARENT/LaunchAgents"     # temp plist dir for all OUR installs
LOCK_ROOT="$TMP_PARENT/lock-root"
FILL_ROOT="$TMP_PARENT/fill-root"
FILL_LOADED=0

# macOS has no `timeout`; bounded execution via perl alarm.
with_alarm() { perl -e 'alarm shift; exec @ARGV' "$@"; }

cleanup() {
  _rc=$?
  # Boot out ONLY attack labels (never the live dev labels), then remove only
  # plists/roots this script created.
  launchctl bootout "gui/$(id -u)/$HOSTILE_LABEL" >/dev/null 2>&1
  launchctl bootout "gui/$(id -u)/$COLLIDE_LABEL" >/dev/null 2>&1
  if [ "$FILL_LOADED" -eq 1 ]; then
    TEAM_SERVER_LAUNCHAGENTS_DIR="$LA_DIR" \
      "$TEAM" uninstall --root "$FILL_ROOT" --label "$FILL_LABEL" >/dev/null 2>&1
  fi
  launchctl bootout "gui/$(id -u)/$FILL_LABEL" >/dev/null 2>&1
  rm -f "$HOME/Library/LaunchAgents/$HOSTILE_LABEL.plist" \
        "$HOME/Library/LaunchAgents/$COLLIDE_LABEL.plist" 2>/dev/null
  rm -rf "$TMP_PARENT"
  exit "$_rc"
}
trap cleanup EXIT INT TERM HUP

# =====================================================================
# (a) Attempt 1 — credential hunt
# =====================================================================
# Counts lines matching secret-shaped patterns. Raw matched text never leaves
# count_hits; only the integer count (and a sha256 of the scanned content) is
# recorded per site.
count_hits() {
  grep -Eic -e 'Bearer[[:space:]]+[A-Za-z0-9._/-]{12,}' \
    -e 'sk-[A-Za-z0-9_-]{16,}' \
    -e '(^|:)token=[A-Za-z0-9._/-]{8,}' \
    -e 'ANTHROPIC_AUTH_TOKEN=[^[:space:]@]{1,}' \
    -e 'sk-ant-[A-Za-z0-9_-]{8,}' 2>/dev/null
}
# sum_site <label>  (content on stdin via file redirect or heredoc — never a
# pipeline, so the variable assignments stay in this shell)
plist_cnt=0; log_cnt=0; ps_cnt=0; gui_cnt=0; ev_cnt=0
plist_sha=absent; log_sha=absent; ps_sha=absent
sum_site() {
  _lab="$1"
  _data=$(cat)
  [ -n "$_data" ] || return 0
  _c=$(printf '%s\n' "$_data" | count_hits)
  _s=$(printf '%s\n' "$_data" | shasum -a 256 | cut -c1-12)
  eval "${_lab}_cnt=\$_c"
  eval "${_lab}_sha=\$_s"
}

a1() {
  ev_files=0
  [ -f "$DEV_PLIST" ] && sum_site plist < "$DEV_PLIST"
  [ -f "$DEV_ROOT/run/server.log" ] && sum_site log < "$DEV_ROOT/run/server.log"

  # By-design secret files: access.txt (pairing URL) and fabric.env (route
  # keys), both required mode 0600. Record modes only, never contents.
  acc_mode=absent; env_mode=absent
  for r in "$DEV_ROOT" "$DEV_ROOT_B"; do
    [ -f "$r/run/access.txt" ] && acc_mode=$(stat -f '%Lp' "$r/run/access.txt")
    [ -f "$r/fabric.env" ] && env_mode=$(stat -f '%Lp' "$r/fabric.env")
  done

  # ps eww of the 3805 server process. Its env legitimately carries
  # ANTHROPIC_* from the 0600 fabric.env (by design).
  pid=$(launchctl print "gui/$(id -u)/$DEV_LABEL" 2>/dev/null \
        | sed -n 's/^[[:space:]]*pid = \([0-9][0-9]*\).*/\1/p' | head -1)
  if [ -n "$pid" ]; then
    ps_data=$(ps eww "$pid" 2>/dev/null)
    sum_site ps <<EOF
$ps_data
EOF
  fi

  # launchd's GUI-session "inherited environment" block: set session-wide via
  # `launchctl setenv`, outside this tool. If a key appears there but NOT in
  # the server process env, that is HELD (explained), not a tool bypass.
  gui_data=$(launchctl print "gui/$(id -u)/$DEV_LABEL" 2>/dev/null \
             | sed -n '/inherited environment/,/}/p')
  sum_site gui <<EOF
$gui_data
EOF
  gui_only=0
  [ "$gui_cnt" -gt 0 ] && [ "$ps_cnt" -eq 0 ] && gui_only=1

  if [ -d "$EVIDENCE_DIR" ]; then
    for f in "$EVIDENCE_DIR"/*.json; do
      [ -f "$f" ] || continue
      ev_files=$((ev_files + 1))
      _c=$(count_hits < "$f")
      ev_cnt=$((ev_cnt + _c))
    done
  fi
  lines=0
  [ -f "$DEV_ROOT/run/server.log" ] && lines=$(wc -l < "$DEV_ROOT/run/server.log" | tr -d ' ')
  log_mode=$(stat -f '%Lp' "$DEV_ROOT/run/server.log" 2>/dev/null || echo absent)

  # BYPASS: a secret readable somewhere it should not be — the plist, the
  # evidence JSONs, or a world/group-readable server.log.
  leak=0
  [ "$plist_cnt" -gt 0 ] && leak=1
  [ "$ev_cnt" -gt 0 ] && leak=1
  if [ "$log_cnt" -gt 0 ]; then
    case "$log_mode" in 600|400) : ;; *) leak=1 ;; esac
  fi

  if [ "$leak" -eq 1 ]; then
    result 1 credential-hunt BYPASS \
      "secret outside 0600 files: plist_hits=$plist_cnt evidence_hits=$ev_cnt($ev_files files) log_hits=$log_cnt(mode=$log_mode,sha=$log_sha)"
  elif [ "$gui_only" -eq 1 ]; then
    result 1 credential-hunt HELD \
      "gui-session inherited-env has $gui_cnt matches absent from server env (session-wide launchctl setenv, outside this tool); plist=$plist_cnt log=$log_cnt ps=$ps_cnt evidence=$ev_cnt/$ev_files"
  elif [ "$plist_cnt" -eq 0 ] && [ "$log_cnt" -eq 0 ] && [ "$ps_cnt" -eq 0 ] && [ "$ev_cnt" -eq 0 ]; then
    result 1 credential-hunt DEFEAT \
      "0 secrets in plist/log($lines lines,mode=$log_mode)/ps/evidence($ev_files files); access.txt=$acc_mode fabric.env=$env_mode; hashes plist=$plist_sha log=$log_sha"
  else
    result 1 credential-hunt HELD \
      "secrets only in by-design sites: log_hits=$log_cnt(mode=$log_mode,sha=$log_sha) ps_env_hits=$ps_cnt(sha=$ps_sha) gui_session_hits=$gui_cnt; access.txt=$acc_mode fabric.env=$env_mode; plist=$plist_cnt evidence=$ev_cnt/$ev_files"
  fi
}

# =====================================================================
# (b) Attempt 2 — non-loopback reach against 3805/3806
# =====================================================================
a2() {
  addrs=""
  for ip in $(ifconfig 2>/dev/null | awk '/^[[:space:]]*inet /{print $2}' | grep -v '^127\.'); do
    addrs="$addrs $ip"
  done
  # Tailnet address, if a utun with an inet is present.
  tail_ip=$(ifconfig 2>/dev/null | awk '/^utun[0-9]+:/{f=1} f&&/^[[:space:]]*inet /{print $2; exit}')
  case " $addrs " in
    *" $tail_ip "*) : ;;
    *) [ -n "$tail_ip" ] && addrs="$addrs $tail_ip" ;;
  esac
  n_addr=0; reachable=0; attempts=0
  for a in $addrs; do
    n_addr=$((n_addr + 1))
    for p in 3805 3806; do
      attempts=$((attempts + 1))
      code=$(curl -s --noproxy '*' --connect-timeout 3 --max-time 5 \
               -o /dev/null -w '%{http_code}' "http://$a:$p/" 2>/dev/null || echo 000)
      if [ "$code" != "000" ]; then
        reachable=$((reachable + 1))
      elif perl -MIO::Socket::INET -e \
           '$s=IO::Socket::INET->new(PeerAddr=>$ARGV[0],PeerPort=>$ARGV[1],Proto=>"tcp",Timeout=>3);exit($s?0:1)' \
           "$a" "$p" 2>/dev/null; then
        reachable=$((reachable + 1))   # TCP accepts even though HTTP failed
      fi
    done
  done
  addr_list=$(echo $addrs | tr ' ' ',')
  if [ "$reachable" -gt 0 ]; then
    result 2 non-loopback-reach BYPASS \
      "$reachable/$attempts connects accepted via $n_addr non-loopback addr(s) [$addr_list]"
  else
    result 2 non-loopback-reach DEFEAT \
      "0/$attempts reachable via $n_addr non-loopback addr(s) [$addr_list] (HTTP+raw TCP both refused/unreachable)"
  fi
}

# =====================================================================
# (c) Attempt 3 — hostile install targets must all be refused
# =====================================================================
a3() {
  # Narrow integrity probe (driver patch: the author's full `ls -laR` hash both
  # over-reads ~/.t3 and false-positives when the Chairman's live app writes
  # its own userdata during the run). Probe ONLY what this tool would create
  # inside a hostile root: its artifact set, the real bin dir listing, and
  # top-level entries newer than the marker. Read-only; no file contents.
  MARKER="$TMP_PARENT/t3-marker"; : > "$MARKER"; sleep 1
  probe() {
    _r="$1"
    for p in run bin config scratch-project claude-home home fabric.env; do
      [ -e "$_r/$p" ] && echo "exists:$_r/$p"
    done
    [ -d "$_r/bin" ] && ls -la "$_r/bin" 2>/dev/null
    find "$_r" -maxdepth 1 -newer "$MARKER" 2>/dev/null
  }
  snap() { probe "$T3_HOME"; probe "$T3_HOME/team"; }
  before=$(snap)
  refused=0; total=0
  hostile() { # root port
    total=$((total + 1))
    out=$("$TEAM" install --root "$1" --port "$2" --label "$HOSTILE_LABEL" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -Eq 'refus|reserved|resolves|inside'; then
      refused=$((refused + 1))
    else
      note "hostile root=$1 port=$2 UNEXPECTED rc=$rc"
    fi
  }
  hostile "$T3_HOME" 3811                      # root IS ~/.t3
  hostile "$T3_HOME/team" 3811                 # root inside ~/.t3
  link="$TMP_PARENT/t3-link"
  ln -sfn "$T3_HOME" "$link"
  hostile "$link/team" 3811                    # symlink resolving into ~/.t3
  hostile "$TMP_PARENT/port3773-root" 3773     # reserved port (benign root)
  hostile "$TMP_PARENT/port3774-root" 3774     # reserved port (benign root)
  after=$(snap)

  if [ "$before" != "$after" ]; then
    result 3 hostile-install BYPASS \
      "$refused/$total refused; ~/.t3 probe CHANGED — something was written inside ~/.t3"
  elif [ "$refused" -ne "$total" ]; then
    result 3 hostile-install BYPASS \
      "$refused/$total refused nonzero+message (expected 5/5); ~/.t3 probe unchanged"
  else
    result 3 hostile-install DEFEAT \
      "$refused/$total refused nonzero+message; ~/.t3 probe unchanged (artifacts+bin+top-level)"
  fi
}

# =====================================================================
# (d) Attempt 4 — two servers on one home
# =====================================================================
a4() {
  # Part 1 (live, observational): with the real dev server holding
  # $DEV_ROOT/run/home.lock, a second runner on that root must exit 42 BEFORE
  # any execve of the server binary. Only attempted when the dev server is
  # verifiably running; otherwise skipped (safety + not-applicable).
  rc1=skipped
  dev_pid=$(launchctl print "gui/$(id -u)/$DEV_LABEL" 2>/dev/null \
            | sed -n 's/^[[:space:]]*pid = \([0-9][0-9]*\).*/\1/p' | head -1)
  dev_http=$(curl -s --noproxy '*' --connect-timeout 2 --max-time 4 \
               -o /dev/null -w '%{http_code}' "http://127.0.0.1:3805/" 2>/dev/null || echo 000)
  if [ -n "$dev_pid" ] && [ "$dev_http" != "000" ]; then
    out1=$("$RUNNER" "$DEV_ROOT" 2>&1)
    rc1=$?
  fi

  # Part 2 (deterministic flock test in a TEMP root): winner holds the lock
  # for 5s via a fake server-bin; loser must exit 42 with the REFUSED line.
  mkdir -p "$LOCK_ROOT/run" "$LOCK_ROOT/config" "$LOCK_ROOT/scratch-project" \
           "$LOCK_ROOT/fakebin"
  printf 'DUMMY=1\n' > "$LOCK_ROOT/fabric.env"
  chmod 600 "$LOCK_ROOT/fabric.env"
  printf '3911\n' > "$LOCK_ROOT/run/port"
  cat > "$LOCK_ROOT/fakebin/hold" <<'EOF'
#!/bin/sh
sleep 5
exit 1
EOF
  chmod 755 "$LOCK_ROOT/fakebin/hold"
  printf '%s\n' "$LOCK_ROOT/fakebin/hold" > "$LOCK_ROOT/config/server-bin"
  lr="$TMP_PARENT/lock-run"; mkdir -p "$lr"
  "$RUNNER" "$LOCK_ROOT" > "$lr/r1.out" 2>&1 &
  p1=$!
  "$RUNNER" "$LOCK_ROOT" > "$lr/r2.out" 2>&1 &
  p2=$!
  wait "$p1"; rca=$?
  wait "$p2"; rcb=$?
  refused_line=0
  grep -q 'REFUSED another server already holds the lock' "$lr/r1.out" "$lr/r2.out" 2>/dev/null \
    && refused_line=1
  flock_ok=0
  { [ "$rca" = 42 ] || [ "$rcb" = 42 ]; } && [ "$refused_line" -eq 1 ] && flock_ok=1

  # Part 3: one-label-per-root — install on the LIVE dev root with a
  # DIFFERENT label must be refused, and must never load that label.
  out3=$(TEAM_SERVER_LAUNCHAGENTS_DIR="$LA_DIR" \
         "$TEAM" install --root "$DEV_ROOT" --port 3812 --label "$COLLIDE_LABEL" 2>&1)
  rc3=$?
  # NOTE: the guard scans the plist dir for ANY plist naming this root's
  # runner. Our own temp LA_DIR does not contain the dev plist, so also probe
  # against the real LaunchAgents dir (read-only scan on refusal).
  out4=$("$TEAM" install --root "$DEV_ROOT" --port 3812 --label "$COLLIDE_LABEL" 2>&1)
  rc4=$?
  msg4=0; printf '%s' "$out4" | grep -q 'one label per root' && msg4=1
  if launchctl print "gui/$(id -u)/$COLLIDE_LABEL" >/dev/null 2>&1; then
    result 4 two-servers-one-home BYPASS \
      "second-label install on live dev root LOADED $COLLIDE_LABEL (cleaned up in trap)"
    return
  fi

  live_ok="n/a"
  if [ "$rc1" != "skipped" ]; then
    [ "$rc1" = 42 ] && live_ok=1 || live_ok=0
  fi
  if [ "$flock_ok" -eq 1 ] && [ "$rc4" -ne 0 ] && [ "$msg4" -eq 1 ] && [ "$live_ok" != "0" ]; then
    result 4 two-servers-one-home DEFEAT \
      "live 2nd-runner rc=$rc1 (dev Http=$dev_http); temp pair rc=$rca/$rcb +REFUSED line; 2nd-label install rc=$rc4 msg='one label per root' (tempdir rc=$rc3)"
  else
    result 4 two-servers-one-home BYPASS \
      "live rc=$rc1 flock_ok=$flock_ok(rca=$rca rcb=$rcb line=$refused_line) 2nd-label rc=$rc4 msg=$msg4"
  fi
}

# =====================================================================
# (e) Attempt 5 — crash-loop disk fill (launchd KeepAlive, ~60s)
# =====================================================================
a5() {
  mkdir -p "$LA_DIR" "$FILL_ROOT/run" "$FILL_ROOT/config" \
           "$FILL_ROOT/scratch-project" "$FILL_ROOT/fakebin"
  printf 'DUMMY=1\n' > "$FILL_ROOT/fabric.env"
  chmod 600 "$FILL_ROOT/fabric.env"
  # Fake server: prints ~2KB per run then exits 1 -> KeepAlive crash loop.
  cat > "$FILL_ROOT/fakebin/crashy" <<'EOF'
#!/bin/sh
awk 'BEGIN{s="";for(i=0;i<2048;i++)s=s "x"; print s}'
exit 1
EOF
  chmod 755 "$FILL_ROOT/fakebin/crashy"
  port=$(with_alarm 10 perl -MIO::Socket::INET -e \
    '$s=IO::Socket::INET->new(LocalAddr=>"127.0.0.1",LocalPort=>0,Proto=>"tcp",Listen=>1,ReuseAddr=>1);printf "%d",$s->sockport')
  out=$(TEAM_SERVER_LAUNCHAGENTS_DIR="$LA_DIR" TEAM_SERVER_LOG_CAP=32768 \
        "$TEAM" install --root "$FILL_ROOT" --port "$port" \
        --label "$FILL_LABEL" --server-bin "$FILL_ROOT/fakebin/crashy" 2>&1)
  rc=$?
  if [ "$rc" -eq 0 ]; then
    result 5 crash-loop-disk-fill BYPASS \
      "install unexpectedly succeeded with always-crashing server-bin (rc=0 port=$port)"
    return
  fi
  # install dies after its HTTP wait + bootout but LEAVES the plist. Re-load it
  # from an empty env to sustain the KeepAlive+ThrottleInterval loop for ~60s.
  note "install rc=$rc as designed; sustaining launchd crash loop for 60s"
  env -i /bin/launchctl bootstrap "gui/$(id -u)" "$LA_DIR/$FILL_LABEL.plist" 2>/dev/null
  FILL_LOADED=1
  # Seed the log over the cap once to exercise the runner's start-of-run
  # truncation (cap=32768 here).
  awk 'BEGIN{s="";for(i=0;i<65536;i++)s=s "y"; print s}' > "$FILL_ROOT/run/server.log"
  sleep 60
  sz=$(stat -f%z "$FILL_ROOT/run/server.log" 2>/dev/null || echo 0)
  runs=$(grep -c 'exit 1' /dev/null 2>/dev/null || echo 0)  # placeholder; log line count below
  log_lines=$(wc -l < "$FILL_ROOT/run/server.log" 2>/dev/null | tr -d ' ')
  # uninstall (bootout + rm plist) and verify the label is gone
  TEAM_SERVER_LAUNCHAGENTS_DIR="$LA_DIR" "$TEAM" uninstall \
    --root "$FILL_ROOT" --label "$FILL_LABEL" >/dev/null 2>&1
  launchctl bootout "gui/$(id -u)/$FILL_LABEL" >/dev/null 2>&1
  FILL_LOADED=0
  rm -f "$LA_DIR/$FILL_LABEL.plist"
  gone=1
  launchctl print "gui/$(id -u)/$FILL_LABEL" >/dev/null 2>&1 && gone=0

  bounded=1
  [ "$sz" -lt 5242880 ] || bounded=0
  if [ "$gone" -eq 0 ]; then
    result 5 crash-loop-disk-fill BYPASS \
      "temp label still loaded after uninstall+bootout; log=${sz}B"
  elif [ "$bounded" -eq 0 ]; then
    result 5 crash-loop-disk-fill BYPASS \
      "log grew to ${sz}B in ~60s (>=5MB): crash-loop disk-fill NOT bounded"
  else
    result 5 crash-loop-disk-fill HELD \
      "log=${sz}B/60s (~$((sz * 1))B/min, ${log_lines} banner lines) after seeding 65537B > cap=32768; start-of-run truncate + throttle=10s bounds growth <<5MB/min; label gone=yes"
  fi
}

a1
a2
a3
a4
a5
printf 'ATTACK SUMMARY: %d DEFEAT, %d HELD, %d BYPASS\n' "$N_DEFEAT" "$N_HELD" "$N_BYPASS"
[ "$N_BYPASS" -eq 0 ]
