#!/opt/homebrew/bin/bash
# install_w1.sh - PBR #1693 RUNTIME: W1 release (Option A) driver for INSTALL_RUNBOOK.md.
#
# One subcommand per runbook step. Mac-side only (the deploy key is Mac-held). Every VPS
# contact is a pipe-only ssh READ except: s3 (the repo's own deploy wrapper), s5 (needrestart
# backup + drop-in), s5-revert, rollback-b and rollback-c. State lives in $PBR_EV/state.env so
# each step runs from a fresh shell:
#
#   OPERATOR_SESSION_ID=<id> /opt/homebrew/bin/bash --noprofile --norc install_w1.sh s0
#   PBR_EV=<dir printed by s0> /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" <step>
#
# Exit: 0 step PASS, 1 ABORT (reason in $PBR_EV/logs/stops.log), 4 deploy still running.
set -u -o pipefail
export TZ=UTC LC_ALL=C
umask 022

OLD=ff16c192cc7b932e59c28c4fe30aeaf27bcb7595
HOST=root@146.190.142.17
KEY=/Users/chriswong/.ssh/macro_dashboard_deploy_v2
DPATH=/opt/mastermind
LIVE=/opt/mastermind-live-data
SVC=mastermind.service
HEALTH_URL=http://127.0.0.1:8001/health
SEAT_WT=/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/mastermind-fable-ceo-rebuild-421ce3-1c9d9c6b5d77a525
EV_ROOT=/Volumes/Mastermind/evidence/pbr
RT_REF=origin/claude/ssd-pbr-runtime-85f3de87bc7b8894
RB_PATH=research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/runbook
WT_TOOL=/Users/chriswong/.local/lib/mastermind/worktree-storage/worktree_storage.py
PY=/usr/bin/python3
PY_WT=/opt/homebrew/bin/python3
BASH5=/opt/homebrew/bin/bash
NR_DROPIN=/etc/needrestart/conf.d/99-mastermind-no-autorestart.conf
PIN_RB=536e038bb357e88926edf2613840b5d74431ccfb63c88dbe08a889f3abfa14ac
PIN_MANIFEST=49b3ca7d8b53074f1b6491eccc6371c8b214c75f86c6b75c6f126a6dcd4852bf
PIN_DISTS=b15841d63d3480ea5b8af68ab2d321f2f65d546fa74365153979e127c32776e0
MECH=(scripts/deploy_code_to_vps.sh scripts/deploy_from_git.sh scripts/refresh_datadog_release_tag.sh
      app/main.py portfolio/forward_evaluation.py app/scheduler.py)
SDK_TRIO="pyproject.toml
requirements/gate-linux-x86_64-py312.lock
requirements/gate-macos-arm64-py312.lock"
SHOW_PROPS="-p ActiveState -p SubState -p MainPID -p ActiveEnterTimestamp -p ExecMainStartTimestamp -p NRestarts -p FragmentPath -p DropInPaths -p NeedDaemonReload -p ControlGroup -p Result -p InvocationID"
VPS=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST")

STEP=init
EV=""
now_z() { date -u +%FT%TZ; }
say() {
  printf '%s %s\n' "$(now_z)" "$*"
  if [ -n "$EV" ] && [ -d "$EV/logs" ]; then printf '%s %s %s\n' "$(now_z)" "$STEP" "$*" >> "$EV/logs/runbook.log"; fi
  return 0
}
stop() {
  say "ABORT $STEP: $*"
  if [ -n "$EV" ] && [ -d "$EV/logs" ]; then printf '%s ABORT %s: %s\n' "$(now_z)" "$STEP" "$*" >> "$EV/logs/stops.log"; fi
  exit 1
}
pass()  { : > "$EV/gates/$1.PASS" || stop "cannot write gate marker $1"; say "GATE $1 PASS"; }
state() { printf '%s=%s\n' "$1" "$2" >> "$EV/state.env" || stop "cannot write state $1"; }
rb()    { "$PY" -I -B "$EV/tools/pbr_rb.py" "$@"; }
jget()  { "$PY" -I -B -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get(sys.argv[2])))' "$1" "$2"; }
epoch() { "$PY" -I -B -c 'import calendar,sys,time; print(calendar.timegm(time.strptime(sys.argv[1], "%Y-%m-%dT%H:%M")))' "$1"; }
host_now() { "${VPS[@]}" 'date -u +%s'; }
load() {
  [ -n "${PBR_EV:-}" ] && [ -f "$PBR_EV/state.env" ] || { EV=""; stop "set PBR_EV to the evidence dir printed by s0"; }
  EV=$PBR_EV
  # shellcheck disable=SC1091
  . "$EV/state.env"
  W_OPEN=$(epoch "${DAY}T04:10"); W_LAST_START=$(epoch "${DAY}T05:30")
  W_CLOSE=$(epoch "${DAY}T05:40"); APT_MIN_NEXT=$(epoch "${DAY}T05:55")
}
events_tail() {  # events_tail <out>: fresh 20000-line run_events tail, extra.flags dropped
  "${VPS[@]}" "tail -n 20000 $LIVE/governance/run_events.jsonl" | rb events-filter > "$1"
}
snapshot_list() {  # snapshot_list <out>
  "${VPS[@]}" 'bash -s' > "$1" <<'EOF'
for s in /opt/mastermind/.deploy_prev/snapshot.*; do
  [ -d "$s" ] || continue
  c=0; [ -f "$s/complete" ] && c=1
  if [ -f "$s/deployed_git_sha" ]; then h=$(cat "$s/deployed_git_sha"); else h=absent; fi
  printf '%s complete=%s sha=%s\n' "$s" "$c" "$h"
done
exit 0
EOF
}
marker_read() {  # marker_read <out>: start.json sha256 (or "missing"); never its content
  "${VPS[@]}" 'bash -s' > "$1" <<'EOF'
f=/opt/mastermind-live-data/portfolio_forward_evaluation/start.json
if [ -f "$f" ] && [ ! -L "$f" ]; then sha256sum -- "$f" | awk '{print $1}'; stat -c 'mtime=%Y' -- "$f"
elif [ ! -e "$f" ] && [ ! -L "$f" ]; then echo missing
else echo unreadable; exit 1; fi
EOF
}
unit_hashes() {  # unit_hashes <out>: sha256 of the unit fragment + drop-ins (never their content)
  "${VPS[@]}" "sha256sum -- \$(systemctl show $SVC -p FragmentPath --value) \$(systemctl show $SVC -p DropInPaths --value) | sort -k2" > "$1"
}
blob_manifest() { "${VPS[@]}" "python3 -I -B - $DPATH" < "$EV/tools/remote_blob_manifest.py" > "$1"; }
dists_read()    { "${VPS[@]}" "$DPATH/.venv/bin/python -I -B -" < "$EV/tools/remote_dists.py" > "$1"; }
show_read()     { "${VPS[@]}" "systemctl show $SVC --timestamp=unix $SHOW_PROPS" > "$1"; }
health_read()   { "${VPS[@]}" "curl -fsS -m 6 $HEALTH_URL" > "$1"; }

env_guard() {  # the deploy scripts honour these; the runbook never sets them except R-c's own prefix
  local v
  for v in $(compgen -e); do
    case $v in
      MASTERMIND_VPS_*|MASTERMIND_SERVE_ONLY|MASTERMIND_GIT_REMOTE|MASTERMIND_BASE_BRANCH|MASTERMIND_DEPLOY_*)
        stop "environment override $v is set; the deploy scripts would honour it - unset it and re-run this step";;
    esac
  done
}

# ------------------------------------------------------------------ gates (read-only)
g5_clock() {
  local now; now=$(host_now) || stop "G5: host clock read failed"
  [[ $now =~ ^[0-9]+$ ]] && [ "$now" -ge "$W_OPEN" ] && [ "$now" -lt "$W_LAST_START" ] \
    || stop "G5: host time $(date -u -r "${now:-0}" +%FT%TZ) is outside [${DAY}T04:10Z, ${DAY}T05:30Z) - window rule; do not deploy"
  echo "$now" > "$EV/gates/G5_host_epoch.txt"; pass G5
}
g8_master() {
  local remote; remote=$(git -C "$WT" ls-remote origin refs/heads/master | awk '{print $1}') || stop "G8: ls-remote failed"
  echo "$remote" > "$EV/gates/G8_origin_master.txt"
  [ "$remote" = "$SHA" ] || stop "G8: origin/master moved to $remote (fixed at s0: $SHA); the wrapper would refuse - seat ruling (hold, or restart from s0 with a new evidence dir)"
  pass G8
}
g12_events() {
  local ae; ae=$("${VPS[@]}" "systemctl show $SVC --timestamp=unix -p ActiveEnterTimestamp --value") || stop "G1/G2: systemctl read failed"
  [[ $ae =~ ^@[0-9]+$ ]] || stop "G1/G2: service ActiveEnterTimestamp unreadable ('$ae') - is the service running?"
  echo "$ae" > "$EV/gates/process_active_enter.txt"
  events_tail "$EV/gates/run_events.gates.jsonl" || stop "G1/G2: run_events read failed"
  rb gates --events "$EV/gates/run_events.gates.jsonl" --date "$DAY" --since-process "$ae" > "$EV/gates/G1_G2.json"
  local g1 g2 cov bad runs
  g1=$(jget "$EV/gates/G1_G2.json" G1_watch_us_0220_finished); g2=$(jget "$EV/gates/G1_G2.json" G2_no_open_run_since_process_start)
  cov=$(jget "$EV/gates/G1_G2.json" tail_covers_window); bad=$(jget "$EV/gates/G1_G2.json" unparsed)
  runs=$(jget "$EV/gates/G1_G2.json" G1_runs)
  [ "$cov" = true ] && [ "$bad" = 0 ] || stop "G1/G2: the run_events tail does not cover the window or has unparsed rows - see gates/G1_G2.json; seat"
  if [ "$g1" != true ]; then
    [ -n "${PBR_WAIVE_G1:-}" ] || stop "G1: watch_us_overnight 02:20 has no run_finished (runs: $runs). Hold and re-run s2 every 10 min until 05:30Z. Only the seat may waive (PBR_WAIVE_G1='<ruling ref>')"
    printf 'G1 waived by seat ruling: %s; runs=%s\n' "$PBR_WAIVE_G1" "$runs" > "$EV/gates/G1.WAIVER"
  fi
  if [ "$g2" != true ]; then
    [ -n "${PBR_WAIVE_G2E:-}" ] || stop "G2: open run_started since process start: $(jget "$EV/gates/G1_G2.json" G2_open). Hold and re-run s2; a row older than its job's normal duration is a ledger anomaly - only the seat may waive it (PBR_WAIVE_G2E='<ruling ref>'); the cgroup liveness check still applies"
    printf 'G2 (run_events) waived by seat ruling: %s; open=%s\n' "$PBR_WAIVE_G2E" "$(jget "$EV/gates/G1_G2.json" G2_open)" > "$EV/gates/G2E.WAIVER"
  fi
  pass G1; pass G2E
}
g2_cgroup() {
  "${VPS[@]}" 'bash -s' > "$EV/gates/G2_cgroup.txt" <<'EOF' || stop "G2: cgroup read failed"
cg=$(systemctl show mastermind.service -p ControlGroup --value)
[ -n "$cg" ] && [ -r "/sys/fs/cgroup$cg/cgroup.procs" ] || { echo "cgroup_unreadable"; exit 1; }
while read -r p; do ps -o pid=,etimes=,comm= -p "$p"; done < "/sys/fs/cgroup$cg/cgroup.procs"
exit 0
EOF
  ! grep -Eiq '(claude|node|codex)' "$EV/gates/G2_cgroup.txt" \
    || stop "G2: a reasoning child (claude/node/codex) is running in $SVC - an LLM run is in flight; hold and re-check"
  pass G2
}
g3_apt() {
  local f=$EV/gates/G3_apt.txt
  "${VPS[@]}" 'bash -s' > "$f" <<'EOF' || stop "G3: read failed"
echo "apt_daily=$(systemctl is-active apt-daily.service)"
echo "apt_daily_upgrade=$(systemctl is-active apt-daily-upgrade.service)"
echo "unattended_upgrade_procs=$(pgrep -f '(^|/)unattended-upgrade( |$)' | wc -l)"
echo "needrestart_procs=$(pgrep -f '(^|/)needrestart( |$)' | wc -l)"
echo "apt_dpkg_procs=$(pgrep -f '(^|/)(apt|apt-get|aptitude|dpkg)( |$)' | wc -l)"
if command -v fuser >/dev/null 2>&1; then
  fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1
  rc=$?; if [ "$rc" -eq 0 ]; then echo "lock_holders=yes"; else echo "lock_holders=no"; fi
else
  echo "lock_holders=unknown"
fi
echo "upgrade_timer_next=$(systemctl show apt-daily-upgrade.timer --timestamp=unix -p NextElapseUSecRealtime --value)"
echo "apt_timer_next=$(systemctl show apt-daily.timer --timestamp=unix -p NextElapseUSecRealtime --value)"
echo "restart_timer_next=$(systemctl show mastermind-restart.timer --timestamp=unix -p NextElapseUSecRealtime --value)"
exit 0
EOF
  grep -Eqx 'apt_daily=(inactive|failed)' "$f" && grep -Eqx 'apt_daily_upgrade=(inactive|failed)' "$f" \
    && grep -qx 'unattended_upgrade_procs=0' "$f" && grep -qx 'needrestart_procs=0' "$f" \
    && grep -qx 'apt_dpkg_procs=0' "$f" && grep -qx 'lock_holders=no' "$f" \
    || stop "G3: apt/unattended-upgrade/needrestart/dpkg not idle (or lock state unknown) - hold and re-check; see $f"
  local nxt; nxt=$(sed -n 's/^upgrade_timer_next=@\([0-9][0-9]*\).*/\1/p' "$f")
  [ -n "$nxt" ] && [ "$nxt" -ge "$APT_MIN_NEXT" ] \
    || stop "G3: apt-daily-upgrade next elapse '${nxt:-unknown}' is before ${DAY}T05:55Z or unknown - seat ruling"
  pass G3
}
g4_settlement() {  # g4_settlement <out>: read-only mirror of the deploy script's settlement-state gate
  "${VPS[@]}" 'bash -s' > "$1" 2>&1 <<'EOF'
set -e
for book in autonomous china hk; do
  book_dir=/opt/mastermind-live-data/portfolios/$book
  if [ -e "$book_dir/paper_transaction.json" ]; then printf 'unresolved_wal:%s\n' "$book"; exit 21; fi
  if [ -d "$book_dir/settlement_receipts" ]; then
    if ! receipt_entry=$(find -H "$book_dir/settlement_receipts" -mindepth 1 -maxdepth 1 -name '*.json' -print -quit); then
      printf 'receipt_scan_failed:%s\n' "$book"; exit 23
    fi
    if [ -n "$receipt_entry" ]; then printf 'unfinalized_receipt:%s\n' "$book"; exit 22; fi
  fi
done
printf 'clean\n'
EOF
}
g4_gate() {
  g4_settlement "$EV/gates/G4_settlement.txt"; local rc=$?
  [ "$rc" -eq 0 ] && [ "$(cat "$EV/gates/G4_settlement.txt")" = clean ] \
    || stop "G4: settlement state not clean (rc=$rc: $(head -c 200 "$EV/gates/G4_settlement.txt")) - the deploy would refuse; seat ruling. Never 'repair' live data."
  pass G4
}
g6_forward() {
  "${VPS[@]}" "cd $DPATH && MASTERMIND_FORWARD_EVALUATION_RELEASE_STATE_ROOT=$LIVE python3 -B -m portfolio.forward_evaluation status" \
    > "$EV/gates/G6_forward_status.json" 2> "$EV/gates/G6_forward_status.stderr"
  local rc=$?
  [ "$rc" -eq 0 ] || stop "G6: forward_evaluation status rc=$rc (2 = not_started/unknown_book; other = pending/err). The deploy would init/finalize a cohort marker on the live root - seat ruling"
  marker_read "$EV/gates/G6_marker.txt" || stop "G6: start.json unreadable"
  grep -Eq '^[0-9a-f]{64}$' "$EV/gates/G6_marker.txt" || stop "G6: start.json marker missing while status rc=0 - seat"
  pass G6
}
gates_all() { g5_clock; g8_master; g12_events; g2_cgroup; g3_apt; g4_gate; g6_forward; }

# ------------------------------------------------------------------ s0: bootstrap + G7 (Mac + git only)
s0() {
  STEP=s0
  [ -z "${PBR_EV:-}" ] || stop "PBR_EV is set; s0 always creates a new evidence dir (unset PBR_EV)"
  env_guard
  [ -n "${OPERATOR_SESSION_ID:-}" ] || stop "set OPERATOR_SESSION_ID to the executing session id (worktree identity)"
  local day=${PBR_DAY:-2026-10-23}
  "$PY" -I -B -c 'import datetime,sys; sys.exit(0 if datetime.date.fromisoformat(sys.argv[1]).weekday() < 5 else 1)' "$day" \
    || stop "PBR_DAY=$day is not a Mon-Fri date (W1 is a weekday window)"
  if [ "$day" = 2026-10-23 ]; then
    [ "$(epoch 2026-10-23T04:10)" = 1792728600 ] && [ "$(epoch 2026-10-23T05:30)" = 1792733400 ] \
      || stop "epoch self-check failed"
  fi
  [ -f "$KEY" ] || stop "deploy key missing at $KEY"
  [ -x "$BASH5" ] && [ -x "$PY" ] && [ -x "$PY_WT" ] || stop "missing $BASH5, $PY or $PY_WT"
  command -v rsync >/dev/null && command -v ssh >/dev/null && command -v git >/dev/null || stop "rsync/ssh/git missing"
  # 0.1 fresh worktree at origin/master (external SSD policy helper)
  local name wt
  name="pbr-install-w1-$(date -u +%Y%m%dT%H%M%SZ)"
  wt=$(printf '{"cwd": "%s", "name": "%s", "session_id": "%s"}' "$SEAT_WT" "$name" "$OPERATOR_SESSION_ID" \
       | "$PY_WT" -I -B "$WT_TOOL" create | tail -n 1) || stop "worktree create failed"
  [ -d "$wt" ] || stop "worktree create returned '$wt'"
  local sha remote
  sha=$(git -C "$wt" rev-parse HEAD) || stop "rev-parse"
  remote=$(git -C "$wt" ls-remote origin refs/heads/master | awk '{print $1}') || stop "ls-remote"
  [ "$sha" = "$remote" ] || stop "worktree HEAD $sha != origin/master $remote (master moved during s0); remove $wt and re-run s0"
  [ -z "$(git -C "$wt" status --porcelain)" ] || stop "worktree $wt is not clean"
  # 0.2 evidence dir
  local cid; cid="$(date -u +%Y%m%dT%H%MZ)_${sha:0:8}"
  EV="$EV_ROOT/install-$cid"
  [ ! -e "$EV" ] || { EV=""; stop "evidence dir already exists for $cid"; }
  mkdir -p "$EV"/tools "$EV"/logs "$EV"/captures/pre "$EV"/captures/post "$EV"/gates "$EV"/identity/pre \
           "$EV"/identity/pre_vs_sha "$EV"/identity/post "$EV"/needrestart "$EV"/cycles "$EV"/rollback || stop "mkdir"
  : > "$EV/state.env"
  state CAPTURE_ID "$cid"; state SHA "$sha"; state WT "$wt"; state DAY "$day"
  # 0.3 helpers from the RUNTIME branch, sha256-pinned
  git -C "$SEAT_WT" fetch -q origin "${RT_REF#origin/}" || stop "fetch ${RT_REF#origin/}"
  local f
  for f in pbr_rb.py remote_blob_manifest.py remote_dists.py; do
    git -C "$SEAT_WT" show "$RT_REF:$RB_PATH/$f" > "$EV/tools/$f" || stop "extract $f"
  done
  cp "$0" "$EV/tools/install_w1.sh" || stop "copy driver"
  ( cd "$EV/tools" && shasum -a 256 -c ) > "$EV/logs/pins.txt" 2>&1 <<EOF || stop "helper pin mismatch (logs/pins.txt) - do not proceed; ask RUNTIME"
$PIN_RB  pbr_rb.py
$PIN_MANIFEST  remote_blob_manifest.py
$PIN_DISTS  remote_dists.py
EOF
  shasum -a 256 "$EV/tools/install_w1.sh" >> "$EV/logs/pins.txt"
  # 0.4 tool versions + a local-only flag check of the deploy's rsync invocation
  { echo "bash=$($BASH5 --version | head -n 1)"; echo "rsync=$(command -v rsync) $(rsync --version 2>&1 | head -n 1)"
    echo "ssh=$(ssh -V 2>&1)"; echo "git=$(git --version)"; echo "py=$($PY --version 2>&1)"
    echo "env_bash=$(command -v bash)"; echo "TMPDIR=${TMPDIR:-unset}"; } > "$EV/logs/tools.txt"
  local a b; a=$(mktemp -d) && b=$(mktemp -d) || stop "mktemp"
  echo probe > "$a/probe.txt"
  rsync -azcn --delete --out-format='%n' --exclude='.git' "$a/" "$b/" > "$EV/logs/rsync_flag_check.txt" 2>&1 \
    || stop "local rsync rejects the deploy's flags (logs/rsync_flag_check.txt)"
  rm -f "$a/probe.txt"; rmdir "$a" "$b"
  # 0.5 G7 composition gates
  git -C "$wt" merge-base --is-ancestor "$OLD" "$sha" || stop "G7: OLD $OLD is not an ancestor of $sha"
  local mech; mech=$(git -C "$wt" diff --name-only "$OLD" "$sha" -- "${MECH[@]}")
  [ -z "$mech" ] || stop "G7a: deploy/runtime mechanics changed since OLD: $(echo $mech) - seat ruling (the runbook's mirrors would be stale)"
  local dep t2=equal; dep=$(git -C "$wt" diff --name-only "$OLD" "$sha" -- pyproject.toml requirements/ | sort)
  if [ -n "$dep" ]; then
    [ "$dep" = "$SDK_TRIO" ] || stop "G7b: dependency drift beyond the #1714 trio: $(echo $dep) - STOP, seat"
    local other; other=$(git -C "$wt" diff -U0 "$OLD" "$sha" -- pyproject.toml | grep -E '^[-+][^-+]' | grep -vc 'claude-agent-sdk>=0\.2')
    [ "$other" = 0 ] || stop "G7b: pyproject drift is not only the claude-agent-sdk floor - STOP, seat"
    t2=floor_pending
  fi
  state T2_MODE "$t2"
  git -C "$wt" diff --name-status "$OLD" "$sha" > "$EV/identity/old_to_sha.name-status.txt"
  pass G7
  say "s0 PASS: SHA=$sha T2_MODE=$t2 WT=$wt"
  echo "export PBR_EV=$EV"
}

# ------------------------------------------------------------------ s1: pre-change capture (read-only)
s1() {
  STEP=s1; load
  [ -f "$EV/gates/G7.PASS" ] || stop "s0 has not passed"
  local P=$EV/captures/pre I=$EV/identity/pre b
  "${VPS[@]}" true || stop "ssh to $HOST failed"
  show_read "$P/systemctl_show.txt" || stop "systemctl show"
  grep -qx 'ActiveState=active' "$P/systemctl_show.txt" || stop "service is not active before the change - seat"
  "${VPS[@]}" "systemctl show $SVC -p ExecStart --value | sed -n 's/.*path=\([^ ;]*\).*/\1/p'" > "$P/execstart_path.txt" || stop "ExecStart"
  "${VPS[@]}" "systemctl show $SVC -p EnvironmentFiles --value | awk '{print \$1}'" > "$P/environment_file_names.txt" || stop "EnvironmentFiles"
  unit_hashes "$I/unit_sha256.txt" || stop "T3 unit hashes"
  dists_read "$I/dists.txt" || stop "T2 dists read"
  grep -E '^(claude-agent-sdk|anthropic)==' "$I/dists.txt" > "$I/dists_key.txt" || stop "T2: claude-agent-sdk/anthropic not in the venv"
  blob_manifest "$I/installed_manifest.jsonl" || stop "T1 manifest read"
  rb t1 --repo "$WT" --sha "$OLD" --manifest "$I/installed_manifest.jsonl" --out "$I" > "$I/t1_verdict.json" \
    || stop "T1(pre) vs OLD FAIL - the host is not OLD (identity/pre/identity_manifest.tsv); seat ruling"
  grep -q '"marker_claim_matches": true' "$I/t1_verdict.json" || stop ".deployed_git_sha does not claim OLD - seat"
  rb t1 --repo "$WT" --sha "$SHA" --manifest "$I/installed_manifest.jsonl" --out "$EV/identity/pre_vs_sha" \
    > "$EV/identity/pre_vs_sha/t1_verdict.json"   # expected FAIL: differing+missing = paths the deploy will write
  "${VPS[@]}" 'bash -s' > "$P/book_state.txt" <<'EOF' || stop "book state read"
cd /opt/mastermind-live-data/portfolios || exit 1
for b in autonomous china hk; do
  for f in account.json fills.jsonl decisions.jsonl pending_target.json paper_transaction.json; do
    if [ -e "$b/$f" ]; then sha256sum -- "$b/$f"; stat -c '%n size=%s mtime=%Y' -- "$b/$f"; else echo "absent $b/$f"; fi
  done
  if [ -d "$b/settlement_receipts" ]; then
    echo "receipts $b $(find -H "$b/settlement_receipts" -mindepth 1 -maxdepth 1 -name '*.json' | wc -l)"
  else echo "receipts $b absent"; fi
done
EOF
  marker_read "$P/forward_marker.txt" || stop "start.json read"
  snapshot_list "$P/deploy_prev.txt" || stop ".deploy_prev listing"
  "${VPS[@]}" "df -B1 --output=avail $DPATH | tail -n 1" > "$P/df_avail_bytes.txt" || stop "df"
  [ "$(tr -d ' ' < "$P/df_avail_bytes.txt")" -ge 1073741824 ] || stop "less than 1 GiB free under $DPATH (each deploy adds a full code snapshot)"
  for b in autonomous china hk; do
    "${VPS[@]}" "if [ -f $LIVE/portfolios/$b/pending_target.json ]; then cat $LIVE/portfolios/$b/pending_target.json; else echo '{\"absent\": true}'; fi" \
      > "$P/pending_target.$b.json" || stop "pending_target $b"
    "${VPS[@]}" "tail -n 400 $LIVE/portfolios/$b/decisions.jsonl" | rb decisions --file - --since "@$((W_OPEN - 172800))" \
      > "$P/decisions.$b.trimmed.jsonl" || stop "decisions $b"
  done
  events_tail "$P/run_events.tail.jsonl" || stop "run_events read"
  "${VPS[@]}" "journalctl _PID=1 UNIT=$SVC --since=@$((W_OPEN - 86400)) --no-pager -o short-iso-precise" > "$P/journal_pid1_unit.txt" || stop "journal"
  "${VPS[@]}" "systemctl list-timers --all --no-pager" > "$P/timers.txt" || stop "timers"
  pass PRE
  say "s1 PASS: pre-change capture complete; predicted deploy delta: $(cat "$EV/identity/pre_vs_sha/t1_verdict.json")"
}

# ------------------------------------------------------------------ s2: gate check (read-only, repeatable)
s2() { STEP=s2; load; [ -f "$EV/gates/PRE.PASS" ] || stop "s1 has not passed"; gates_all; say "s2 PASS: all gates clear - run s3 now"; }

# ------------------------------------------------------------------ s3: the deploy (exactly once per evidence dir)
launch_detached() {  # launch_detached <tag> <workdir> <log> <sha> <command...>: survives the caller's shell/tool timeout
  local tag=$1 dir=$2 log=$3 sha=$4; shift 4
  /usr/bin/nohup "$PY" -I -B -c '
import os, sys
try:
    os.setsid()
except OSError:
    pass
os.execv(sys.argv[1], sys.argv[1:])' "$BASH5" --noprofile --norc -c '
tag=$1; dir=$2; log=$3; sha=$4; ev=$5; shift 5
cd "$dir" || exit 97
MASTERMIND_DEPLOY_LOG="$log" "$@" > "$ev/logs/$tag.stdout" 2>&1
rc=$?
printf "%s\n" "$rc" > "$ev/logs/$tag.rc.tmp" && mv -f "$ev/logs/$tag.rc.tmp" "$ev/logs/$tag.rc"' \
    "pbr-w1-$tag" "$tag" "$dir" "$log" "$sha" "$EV" "$@" < /dev/null > "$EV/logs/$tag.nohup" 2>&1 &
  echo $! > "$EV/logs/$tag.pid"
}
s3() {
  STEP=s3; load
  [ ! -e "$EV/logs/deploy.started" ] || stop "a deploy was already started from this evidence dir - exactly once: use s3-result; NEVER re-run s3"
  env_guard
  [ -f "$EV/gates/PRE.PASS" ] && [ -f "$EV/gates/G7.PASS" ] || stop "s0/s1 have not passed"
  gates_all
  local t0; t0=$(host_now) || stop "host clock read"
  [ "$t0" -lt "$W_LAST_START" ] || stop "G5 recheck: past 05:30Z"
  state DEPLOY_T0 "$t0"
  now_z > "$EV/logs/deploy.started"
  launch_detached deploy "$WT" "$EV/logs/deploy.log" "$SHA" ./scripts/deploy_from_git.sh "$SHA"
  say "deploy LAUNCHED pid=$(cat "$EV/logs/deploy.pid") DEPLOY_T0=$t0 sha=$SHA - expect 2-6 min; poll with s3-result; never interrupt"
}
classify() {  # classify <tag> <expected sha> <log>
  local tag=$1 want=$2 L=$3
  if [ ! -f "$EV/logs/$tag.rc" ]; then
    local pid; pid=$(cat "$EV/logs/$tag.pid" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      say "$tag still running (pid $pid); last log line: $(tail -n 1 "$L" 2>/dev/null)"; exit 4
    fi
    stop "$tag process is gone without an rc file - EFFECT UNKNOWN: do not re-run; read $L and decide R-b with the seat"
  fi
  local rc; rc=$(cat "$EV/logs/$tag.rc"); state "${tag^^}_RC" "$rc"
  case $rc in
    0)
      if grep -q "deploy OK: $SVC healthy at commit $want" "$L"; then pass "${tag^^}"; say "$tag OK at $want"; return 0; fi
      grep -q "deploy no-op" "$L" && stop "$tag no-op: host already in sync at $want although T1(pre) said OLD - seat ruling"
      stop "$tag rc 0 without 'deploy OK' - EFFECT UNKNOWN; seat" ;;
    2) stop "$tag refused before any host change (rc 2): $(tail -n 2 "$EV/logs/$tag.stdout" | tr '\n' ' ') - nothing touched" ;;
    1|130|143)
      if ! grep -q "; rolling back" "$L"; then
        stop "$tag failed before the service stop (rc $rc, no rollback needed): $(grep -E 'deploy (failed|refused)' "$L" | tail -n 1) - nothing touched"
      fi
      if grep -q "code rollback verified" "$L"; then
        state ROLLED_BACK R-a
        stop "$tag FAILED; automatic rollback (R-a) VERIFIED: $(grep 'rolling back' "$L" | tail -n 1). Next: proof-old, then the seat"
      fi
      stop "$tag FAILED; automatic rollback INCOMPLETE: $(grep -E 'recovery (incomplete|:)|reconciliation required' "$L" | tail -n 2 | tr '\n' ' ') - use the R-b decision table" ;;
    *) stop "$tag unexpected rc $rc - EFFECT UNKNOWN; seat" ;;
  esac
}
s3_result() { STEP=s3-result; load; [ -f "$EV/logs/deploy.started" ] || stop "no deploy was started"; classify deploy "$SHA" "$EV/logs/deploy.log"; say "s3-result PASS - run s4"; }

# ------------------------------------------------------------------ s4: post-install proof (read-only)
s4() {
  STEP=s4; load
  [ -f "$EV/gates/DEPLOY.PASS" ] || stop "s3-result has not reported deploy OK"
  local P=$EV/captures/post I=$EV/identity/post fail=0
  show_read "$P/systemctl_show.txt" || stop "systemctl show"
  blob_manifest "$I/installed_manifest.jsonl" || stop "T1 manifest read"
  rb t1 --repo "$WT" --sha "$SHA" --manifest "$I/installed_manifest.jsonl" --out "$I" > "$I/t1_verdict.json" || { say "T1 FAIL"; fail=1; }
  grep -q '"marker_claim_matches": true' "$I/t1_verdict.json" || { say "T1 marker does not claim $SHA"; fail=1; }
  dists_read "$I/dists.txt" || stop "T2 dists read"
  if diff "$EV/identity/pre/dists.txt" "$I/dists.txt" > "$I/dists.diff"; then say "T2 PASS (venv unchanged; mode $T2_MODE)"
  else say "T2 FAIL: the venv changed during the deploy (the deploy never touches .venv)"; fail=2; fi
  unit_hashes "$I/unit_sha256.txt" || stop "T3 unit hashes"
  diff <(grep -v '/81-datadog-version.conf$' "$EV/identity/pre/unit_sha256.txt") \
       <(grep -v '/81-datadog-version.conf$' "$I/unit_sha256.txt") > "$I/unit.diff" || { say "T3 FAIL: unit/drop-ins changed"; fail=1; }
  if grep -q '/80-datadog.conf$' "$I/unit_sha256.txt"; then
    local want81; want81=$(printf '[Service]\nEnvironment=DD_VERSION=%s\n' "$SHA" | shasum -a 256 | awk '{print $1}')
    grep -q "^$want81  .*/81-datadog-version.conf\$" "$I/unit_sha256.txt" || { say "T3 FAIL: 81-datadog-version.conf != DD_VERSION=$SHA"; fail=1; }
  fi
  grep -qx 'NeedDaemonReload=no' "$P/systemctl_show.txt" || { say "T3 FAIL: NeedDaemonReload is not 'no'"; fail=1; }
  rb t4 --t1-summary "$I/t1_summary.json" --show "$P/systemctl_show.txt" --not-before "@$DEPLOY_T0" > "$I/t4_verdict.json" || { say "T4 FAIL"; fail=1; }
  health_read "$P/health.json" || { say "health read failed"; fail=1; }
  rb health --body "$P/health.json" --sha "$SHA" > "$P/health_verdict.json" || { say "health FAIL"; fail=1; }
  events_tail "$P/run_events.tail.jsonl" || stop "run_events read"
  rb app-started --events "$P/run_events.tail.jsonl" --sha "$SHA" --since "@$DEPLOY_T0" > "$P/app_started_verdict.json" \
    || { say "app_started FAIL (if app_started_since=0 or preflight is empty, re-run s4 once after 60 s)"; fail=1; }
  grep -q '"quarantine_incident": true' "$P/app_started_verdict.json" && say "INCIDENT: a cutover preflight outcome is 'quarantined' - report to the seat (does not fail the proof)"
  snapshot_list "$P/deploy_prev.txt" || stop ".deploy_prev listing"
  local new; new=$(comm -13 <(awk '{print $1}' "$EV/captures/pre/deploy_prev.txt" | sort) <(awk '{print $1}' "$P/deploy_prev.txt" | sort))
  if [ "$(printf '%s\n' "$new" | grep -c .)" = 1 ] && grep -qx "$new complete=1 sha=$OLD" "$P/deploy_prev.txt"; then
    state SNAP "$new"
  else say "snapshot FAIL: expected one new complete snapshot holding OLD, got: $(echo $new)"; fail=1; fi
  marker_read "$P/forward_marker.txt" || stop "start.json read"
  [ "$(head -n 1 "$EV/captures/pre/forward_marker.txt")" = "$(head -n 1 "$P/forward_marker.txt")" ] || { say "start.json identity changed"; fail=1; }
  "${VPS[@]}" "cd $DPATH && MASTERMIND_FORWARD_EVALUATION_RELEASE_STATE_ROOT=$LIVE python3 -B -m portfolio.forward_evaluation status" \
    > "$P/forward_status.json" 2> "$P/forward_status.stderr" || { say "forward_evaluation status rc != 0 after the deploy"; fail=1; }
  case $fail in
    0) state INSTALLED "$SHA"; pass PROOF; say "s4 PASS: installed = $SHA (T1 T2 T3 T4 /health app_started + snapshot + marker) - run s5" ;;
    2) stop "T2 FAIL - STOP: venv changed outside the deploy; no rollback without the seat" ;;
    *) stop "post-install proof FAILED (see captures/post, identity/post) - R-b decision table with the seat" ;;
  esac
}

# ------------------------------------------------------------------ s5: needrestart release row
nr_verify() {  # exit 0 = a mastermind.service override with value 0 is configured; 3 = none; 4 = config parse error
  "${VPS[@]}" 'perl -' <<'PERL'
our %nrconf; our $LOGPREF = "[pbr-verify]";
do "/etc/needrestart/needrestart.conf";
if ($@) { print "parse_error: $@\n"; exit 4; }
my ($hit, $val);
for my $re (sort keys %{ $nrconf{override_rc} || {} }) {
  next unless "mastermind.service" =~ /$re/;
  ($hit, $val) = ($re, $nrconf{override_rc}{$re});
  last unless $val;
}
printf "restart_mode=%s override=%s value=%s\n", (defined $nrconf{restart} ? $nrconf{restart} : "undef"),
  (defined $hit ? $hit : "none"), (defined $val ? $val : "undef");
exit((defined $hit && !$val) ? 0 : 3);
PERL
}
s5() {
  STEP=s5; load
  [ -f "$EV/gates/PROOF.PASS" ] || [ -f "$EV/gates/PROOF_OLD.PASS" ] || stop "neither s4 nor proof-old has passed"
  local N=$EV/needrestart rc
  "${VPS[@]}" "grep -n 'conf.d' /etc/needrestart/needrestart.conf; ls -la /etc/needrestart/conf.d/; sha256sum /etc/needrestart/needrestart.conf" \
    > "$N/conf_include.txt" 2>&1 || stop "needrestart config read failed"
  grep -q 'conf\.d/\*\.conf' "$N/conf_include.txt" || stop "needrestart.conf has no conf.d/*.conf include loop - a drop-in would be inert; seat"
  nr_verify > "$N/verify_before.txt"; rc=$?
  [ "$rc" -eq 3 ] || stop "verify before change rc=$rc (expect 3 = no mastermind override; 0 = already present; 4 = parse error)"
  "${VPS[@]}" "set -e; B=/root/needrestart.backup.$CAPTURE_ID; [ ! -e \$B ]; cp -a /etc/needrestart \$B; diff -r /etc/needrestart \$B; cd \$B && find . -type f -exec sha256sum {} + | sort -k2" \
    > "$N/backup_sha256.txt" 2>&1 || stop "needrestart backup failed - no change made"
  printf '%s\n' \
    "# PBR #1693 W1 release row (seat-approved 2026-10-22): needrestart must never auto-restart mastermind.service." \
    "# Restarts happen only via the deploy script or mastermind-restart.timer. Revert: rm this file." \
    "# Backup of /etc/needrestart: /root/needrestart.backup.$CAPTURE_ID" \
    '$nrconf{override_rc}{qr(^mastermind(?:\.service)?$)} = 0;' > "$N/99-mastermind-no-autorestart.conf"
  "${VPS[@]}" 'set -e; d=/etc/needrestart/conf.d; f=$d/99-mastermind-no-autorestart.conf; test -d "$d" || exit 1; test ! -L "$d" || exit 1; test ! -e "$f" || exit 1; test ! -L "$f" || exit 1; tmp=$(mktemp "$d/.99-mm.XXXXXX"); cat > "$tmp"; chmod 0644 "$tmp"; mv -f "$tmp" "$f"; sha256sum "$f"' \
    < "$N/99-mastermind-no-autorestart.conf" > "$N/dropin_sha256.txt" 2>&1 \
    || stop "drop-in write failed (a leftover conf.d/.99-mm.* temp is inert: not *.conf) - seat"
  [ "$(awk '{print $1}' "$N/dropin_sha256.txt")" = "$(shasum -a 256 "$N/99-mastermind-no-autorestart.conf" | awk '{print $1}')" ] \
    || stop "drop-in hash mismatch - run s5-revert"
  nr_verify > "$N/verify_after.txt"; rc=$?
  if [ "$rc" -ne 0 ]; then
    "${VPS[@]}" "rm -f -- $NR_DROPIN"; nr_verify > "$N/verify_after_autorevert.txt"
    stop "override not effective after the write (rc=$rc); drop-in removed - seat"
  fi
  pass NEEDRESTART; say "s5 PASS: $(cat "$N/verify_after.txt")"
}
s5_revert() {
  STEP=s5-revert; load
  "${VPS[@]}" "rm -f -- $NR_DROPIN" || stop "remove failed"
  nr_verify > "$EV/needrestart/verify_after_revert.txt"; local rc=$?
  [ "$rc" -eq 3 ] || stop "revert verify rc=$rc (expect 3); backup at /root/needrestart.backup.$CAPTURE_ID"
  say "s5-revert PASS: drop-in removed"
}

# ------------------------------------------------------------------ s6: close (manifest + redaction scan)
s6() {
  STEP=s6; load
  rb close --dir "$EV" > "$EV/logs/close_verdict.json" || stop "close FAIL: redaction hits listed in logs/close_verdict.json - redact before sharing"
  say "s6 PASS: $(cat "$EV/logs/close_verdict.json")"
  ls "$EV/gates"
}

# ------------------------------------------------------------------ s7: cycle observation (read-only)
cycle() {  # cycle <job> <HH:MM> [book] [YYYY-MM-DD]
  STEP=cycle; load
  local job=${1:?job} hhmm=${2:?HH:MM} book=${3:-} day=${4:-$DAY}
  local fire now; fire=$(epoch "${day}T${hhmm}") || stop "bad time"
  now=$(host_now) || stop "host clock"
  [ "$now" -ge $((fire + 2700)) ] || stop "too early: read at or after $(date -u -r $((fire + 2700)) +%FT%TZ) (fire + 45 min)"
  local C; C="$EV/cycles/${day}T${hhmm/:/}Z_${job}${book:+_$book}"
  mkdir -p "$C" || stop "mkdir $C"
  events_tail "$C/run_events.tail.jsonl" || stop "run_events read"
  local args=(--events "$C/run_events.tail.jsonl" --job "$job" --since "@$((fire - 300))")
  [ -n "$book" ] && args+=(--book "$book")
  rb cycle "${args[@]}" > "$C/cycle.json"; local rc=$?
  if [ -n "$book" ]; then
    "${VPS[@]}" "tail -n 50 $LIVE/portfolios/$book/decisions.jsonl" | rb decisions --file - --since "@$((fire - 300))" > "$C/decisions.trimmed.jsonl" \
      || say "decision read failed for $book"
  fi
  health_read "$C/health.json" && rb health --body "$C/health.json" --sha "${INSTALLED:-$SHA}" > "$C/health_verdict.json" \
    || say "WARN: /health does not show ${INSTALLED:-$SHA} - incident"
  "${VPS[@]}" "journalctl _PID=1 UNIT=$SVC --since=@${DEPLOY_T0:-$fire} --no-pager -o short-iso-precise" > "$C/journal_pid1_unit.txt" \
    || say "journal read failed"
  case $job in settle_*) g4_settlement "$C/settlement_state.txt" ;; esac
  say "cycle $job $day $hhmm${book:+ ($book)}: $(jget "$C/cycle.json" disposition_hint)"
  [ "$rc" -eq 0 ] || stop "cycle read incomplete (run_events tail does not reach the fire time) - re-read once; else record incomplete_uncertain with an incident note"
}
restart_check() {  # restart_check [HH:MM] [YYYY-MM-DD]: the 08:30Z mastermind-restart.timer cycle
  STEP=restart-check; load
  local hhmm=${1:-08:30} day=${2:-$DAY} fire now C
  fire=$(epoch "${day}T${hhmm}"); now=$(host_now) || stop "host clock"
  [ "$now" -ge $((fire + 600)) ] || stop "too early: read at or after fire + 10 min"
  C="$EV/cycles/${day}T${hhmm/:/}Z_restart"; mkdir -p "$C" || stop "mkdir"
  events_tail "$C/run_events.tail.jsonl" || stop "run_events read"
  rb app-started --events "$C/run_events.tail.jsonl" --sha "${INSTALLED:-$SHA}" --since "@$((fire - 150))" > "$C/app_started_verdict.json" \
    || stop "restart cycle: app_started with ${INSTALLED:-$SHA} after the timer not proven (see $C) - incident"
  health_read "$C/health.json" || stop "health read"
  rb health --body "$C/health.json" --sha "${INSTALLED:-$SHA}" > "$C/health_verdict.json" || stop "health FAIL after the timer restart - incident"
  say "restart-check PASS: timer restart came back on ${INSTALLED:-$SHA}"
}

# ------------------------------------------------------------------ rollback
proof_old() {  # identity proof of OLD after R-a / R-b / R-c (read-only)
  STEP=proof-old; load
  local R=$EV/rollback fail=0 ae
  mkdir -p "$R/proof" || stop "mkdir"
  show_read "$R/proof/systemctl_show.txt" || stop "systemctl show"
  ae=$(sed -n 's/^ActiveEnterTimestamp=@\([0-9]*\).*/\1/p' "$R/proof/systemctl_show.txt")
  [ -n "$ae" ] || stop "service has no ActiveEnterTimestamp (stopped?) - seat"
  blob_manifest "$R/proof/installed_manifest.jsonl" || stop "manifest"
  rb t1 --repo "$WT" --sha "$OLD" --manifest "$R/proof/installed_manifest.jsonl" --out "$R/proof" > "$R/proof/t1_verdict.json" || { say "T1(OLD) FAIL"; fail=1; }
  grep -q '"marker_claim_matches": true' "$R/proof/t1_verdict.json" || { say "marker does not claim OLD"; fail=1; }
  rb t4 --t1-summary "$R/proof/t1_summary.json" --show "$R/proof/systemctl_show.txt" --not-before "@${DEPLOY_T0:-$ae}" > "$R/proof/t4_verdict.json" || { say "T4 FAIL"; fail=1; }
  health_read "$R/proof/health.json" || { say "health read failed (re-run once after 60 s)"; fail=1; }
  rb health --body "$R/proof/health.json" --sha "$OLD" > "$R/proof/health_verdict.json" || { say "health(OLD) FAIL"; fail=1; }
  events_tail "$R/proof/run_events.tail.jsonl" || stop "run_events"
  rb app-started --events "$R/proof/run_events.tail.jsonl" --sha "$OLD" --since "@$((ae - 1))" > "$R/proof/app_started_verdict.json" || { say "app_started(OLD) FAIL"; fail=1; }
  marker_read "$R/proof/forward_marker.txt" || stop "start.json read"
  [ "$(head -n 1 "$EV/captures/pre/forward_marker.txt")" = "$(head -n 1 "$R/proof/forward_marker.txt")" ] || { say "start.json identity changed - reconciliation required"; fail=1; }
  [ "$fail" -eq 0 ] || stop "rollback proof FAILED (rollback/proof) - seat"
  state INSTALLED "$OLD"; pass PROOF_OLD; say "proof-old PASS: OLD restored and loaded"
}
rollback_b() {  # manual mirror of deploy_code_to_vps.sh rollback_release (seat-approved route)
  STEP=R-b; load
  [ "${PBR_CONFIRM:-}" = R-b ] || stop "R-b changes the host: set PBR_CONFIRM=R-b after the seat's go"
  local R=$EV/rollback snap=${SNAP:-}
  if [ -z "$snap" ]; then
    snapshot_list "$R/deploy_prev.now.txt" || stop "listing"
    snap=$(comm -13 <(awk '{print $1}' "$EV/captures/pre/deploy_prev.txt" | sort) <(awk '{print $1}' "$R/deploy_prev.now.txt" | sort))
    [ "$(printf '%s\n' "$snap" | grep -c .)" = 1 ] || stop "cannot identify exactly one new snapshot: $(echo $snap) - seat"
    grep -qx "$snap complete=1 sha=$OLD" "$R/deploy_prev.now.txt" || stop "snapshot $snap is not complete/OLD - leave as is; seat"
    state SNAP "$snap"
  fi
  [[ $snap =~ ^/opt/mastermind/\.deploy_prev/snapshot\.[A-Za-z0-9]+$ ]] || stop "snapshot path invalid: $snap"
  g4_settlement "$R/rb_settlement.txt"; [ "$(cat "$R/rb_settlement.txt")" = clean ] \
    || stop "R-b precondition: settlement state not clean (new code may have written v2 WAL/receipts) - seat ruling"
  events_tail "$R/rb_events.jsonl" || stop "run_events"
  rb gates --events "$R/rb_events.jsonl" --date "$DAY" --since-process "@${DEPLOY_T0:?}" > "$R/rb_open_runs.json"
  [ "$(jget "$R/rb_open_runs.json" G2_no_open_run_since_process_start)" = true ] || stop "R-b precondition: an open run since the deploy - seat"
  local EXC=(); eval "$(sed -n '/^EXC=(/,/^)/p' "$WT/scripts/deploy_code_to_vps.sh")"
  [ "${#EXC[@]}" -eq 29 ] && [[ " ${EXC[*]} " == *" --exclude=data "* ]] && [[ " ${EXC[*]} " == *" --exclude=.deploy_prev "* ]] \
    || stop "could not parse the deploy script's EXC list (${#EXC[@]} entries)"
  local REMOTE_EXCLUDES; printf -v REMOTE_EXCLUDES ' %q' "${EXC[@]}"
  "${VPS[@]}" "systemctl stop $SVC; systemctl show $SVC -p ActiveState -p MainPID" > "$R/rb_stop.txt" 2>&1
  grep -Eqx 'ActiveState=(inactive|failed)' "$R/rb_stop.txt" && grep -qx 'MainPID=0' "$R/rb_stop.txt" \
    || stop "R-b: service stop unverified - source NOT restored; seat"
  "${VPS[@]}" "set -e
rsync -ac --delete $REMOTE_EXCLUDES '$snap/tree/' '$DPATH/'
difference=\$(rsync -acn --delete --itemize-changes $REMOTE_EXCLUDES '$snap/tree/' '$DPATH/')
[ -z \"\$difference\" ]
if [ -f '$snap/deployed_git_sha' ]; then cp -a '$snap/deployed_git_sha' '$DPATH/.deployed_git_sha'
elif [ -f '$snap/deployed_git_sha.absent' ]; then rm -f '$DPATH/.deployed_git_sha'
else exit 1; fi
if [ -f '$snap/datadog.enabled' ]; then
  tag='/etc/systemd/system/$SVC.d/81-datadog-version.conf'
  if [ -f '$snap/datadog_version' ]; then cp -a '$snap/datadog_version' \"\$tag\"
  elif [ -f '$snap/datadog_version.absent' ]; then rm -f \"\$tag\"
  else exit 1; fi
  systemctl daemon-reload
fi
echo restore_verified" > "$R/rb_restore.txt" 2>&1 \
    || stop "R-b restore FAILED verification - leave the service STOPPED (never boot a mixed tree); seat"
  "${VPS[@]}" "systemctl restart $SVC" > "$R/rb_restart.txt" 2>&1 || stop "R-b restart failed - seat"
  state ROLLED_BACK R-b
  say "R-b restored $snap and restarted; run proof-old after >= 60 s"
}
rollback_c() {  # transactional re-deploy of OLD through deploy_code_to_vps.sh (seat ruling only)
  STEP=R-c; load
  [ -n "${PBR_SEAT_RULING:-}" ] || stop "R-c bypasses the origin/master wrapper rule: it needs a seat ruling reference in PBR_SEAT_RULING"
  [ ! -e "$EV/logs/rc.started" ] || stop "R-c was already started from this evidence dir; use rollback-c-result"
  env_guard
  local st; st=$(mktemp -d "${TMPDIR:-/tmp}/mastermind-deploy.XXXXXX") || stop "mktemp"
  git -C "$WT" archive "$OLD" | tar -xf - -C "$st" || stop "archive OLD"
  [ -x "$st/scripts/deploy_code_to_vps.sh" ] || stop "OLD archive lacks the deploy script"
  echo "$PBR_SEAT_RULING" > "$EV/rollback/rc.ruling"; echo "$st" > "$EV/rollback/rc.stage"
  now_z > "$EV/logs/rc.started"
  MASTERMIND_DEPLOY_SOURCE="$st/" MASTERMIND_DEPLOY_EXPECT_SHA="$OLD" \
    launch_detached rc "$st" "$EV/rollback/rc.deploy.log" "$OLD" "$st/scripts/deploy_code_to_vps.sh"
  say "R-c LAUNCHED (OLD via the transactional script); poll rollback-c-result"
}
rollback_c_result() { STEP=R-c-result; load; classify rc "$OLD" "$EV/rollback/rc.deploy.log"; state ROLLED_BACK R-c; say "R-c OK - run proof-old"; }

status() { load; cat "$EV/state.env"; ls "$EV/gates"; tail -n 5 "$EV/logs/stops.log" 2>/dev/null; return 0; }

[[ "${BASH_SOURCE[0]}" == "$0" ]] || return 0   # sourced (fixture tests): define functions only

case "${1:-}" in
  s0) s0 ;;
  s1) s1 ;;
  s2) s2 ;;
  s3) s3 ;;
  s3-result) s3_result ;;
  s4) s4 ;;
  s5) s5 ;;
  s5-revert) s5_revert ;;
  s6) s6 ;;
  cycle) shift; cycle "$@" ;;
  restart-check) shift; restart_check "$@" ;;
  proof-old) proof_old ;;
  rollback-b) rollback_b ;;
  rollback-c) rollback_c ;;
  rollback-c-result) rollback_c_result ;;
  status) status ;;
  *) echo "usage: install_w1.sh s0|s1|s2|s3|s3-result|s4|s5|s5-revert|s6|cycle <job> <HH:MM> [book] [day]|restart-check [HH:MM] [day]|proof-old|rollback-b|rollback-c|rollback-c-result|status" >&2; exit 2 ;;
esac
