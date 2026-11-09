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
# Exit: 0 step PASS, 1 ABORT (reason in $PBR_EV/logs/stops.log), 4 deploy still running,
# 5 HOLD (s4a: report to the seat; not a rollback trigger by itself).
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
SEAT_WT=/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/pbr-runtime-rev3-22e74a0f5c56c38e
EV_ROOT=/Volumes/Mastermind/evidence/pbr
RT_REF=origin/claude/ssd-pbr-runtime-85f3de87bc7b8894
RB_PATH=research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/runbook
WT_TOOL=/Users/chriswong/.local/lib/mastermind/worktree-storage/worktree_storage.py
PY=/usr/bin/python3
PY_WT=/opt/homebrew/bin/python3
BASH5=/opt/homebrew/bin/bash
NR_DROPIN=/etc/needrestart/conf.d/99-mastermind-no-autorestart.conf
UU_DPKG_LOG=/var/log/unattended-upgrades/unattended-upgrades-dpkg.log
UU_LOG=/var/log/unattended-upgrades/unattended-upgrades.log
PIN_RB=e7d9a16b3dbe5e9ed085d0de7ece79590046f3b3a363cc41b84b84c93030c68a
PIN_MANIFEST=49b3ca7d8b53074f1b6491eccc6371c8b214c75f86c6b75c6f126a6dcd4852bf
PIN_DISTS=b15841d63d3480ea5b8af68ab2d321f2f65d546fa74365153979e127c32776e0
MECH=(scripts/deploy_code_to_vps.sh scripts/deploy_from_git.sh scripts/refresh_datadog_release_tag.sh
      app/main.py portfolio/forward_evaluation.py app/scheduler.py)
SDK_TRIO="pyproject.toml
requirements/gate-linux-x86_64-py312.lock
requirements/gate-macos-arm64-py312.lock"
# G7b rev 3 (seat ruling D-G7B-1, 2026-11-02): the only non-SDK pyproject drift admitted OLD->SHA is #1899's
# dev-only pytest bound; with no SDK floor the gate locks must keep every pin/extra/hash (comment-only changes).
G7B_DEV_DRIFT='-    "pytest>=8,<10",
+    "pytest>=8,<9.2",'
# G7b rev 3.4 (seat ruling D-G7B-2, 2026-11-03): a requirements file ADDED since OLD (absent at OLD; renames are split
# into delete + add) named <stem>-macos-arm64-py312.{in,lock} directly under requirements/, and not a gate-* file, is
# platform-scoped: the Linux deploy never pip-installs and its rsync drops *.lock. It is admitted and listed in
# gates/G7b.RULING; a modified or deleted pre-existing file, a gate-* name, a subdirectory or any other platform STOPs.
G7B_MAC_ADDED_RE='^requirements/[A-Za-z0-9][A-Za-z0-9._-]*-macos-arm64-py312[.](in|lock)$'
# G7b rev 3.5 (seat ruling D-G7B-3, 2026-11-05): with pyproject.toml unchanged OLD->SHA, a drift set that is a non-empty
# subset of the two gate locks (#1909: header-comment-only regeneration) takes the existing lockbody check alone -
# 0 non-comment lines = equal, any pin/extra/hash/option line = STOP. The #1714 trio path and D-G7B-2 are unchanged.
G7B_GATE_LOCKS="requirements/gate-linux-x86_64-py312.lock
requirements/gate-macos-arm64-py312.lock"
# D-G7B-4 (rev 3.7): exactly this direct declaration, already pinned in BOTH
# OLD gate locks. This is source admission only; T2 stays equal and fresh
# same-venv compatibility is mandatory at s1, immediately before s3, and s4.
G7B_JSONSCHEMA_DRIFT='+    "jsonschema>=4.26,<5",    # validates the existing bot tool roster for Fabric inference'
G7B_JSONSCHEMA_OLD_ENTRIES=$'100644 blob 7f97e053ea7afd287ceec36d33a37faea85283eb\tpyproject.toml
100644 blob d7a925849235a42f088ba359e0308847a9316fcd\trequirements/gate-linux-x86_64-py312.lock
100644 blob 3db3c9bdee75dd0212f24a252a8d002cf6f73992\trequirements/gate-macos-arm64-py312.lock'
G7B_JSONSCHEMA_NEW_ENTRIES=$'100644 blob 622259d33f04d40907075430c5228d6fbba2bae1\tpyproject.toml
100644 blob 87471eec3fe0d41a1655411ec05be5e6519ab584\trequirements/gate-linux-x86_64-py312.lock
100644 blob 53d9429e5f8bdf701f98d798b34fdf79afaf003c\trequirements/gate-macos-arm64-py312.lock'
# G7a rev 3.6 (seat ruling D-G7A-1, 2026-11-06): #1422 (b796d4505) changed portfolio/forward_evaluation.py OLD->SHA in one hunk of
# _current_exposure_metrics (build_snapshot path only), traced inert to every deploy probe and runbook mirror (evidence
# runtime-rev36-build-20261106T0607Z/G7A_forward_evaluation_trace.md). Admitted ONLY as this exact mode+blob pair; any other blob or
# mode, a git read failure, or a change to any other MECH path STOPs.
G7A_FE_PATH=portfolio/forward_evaluation.py
G7A_FE_OLD_ENTRY="100644 blob 46031e40a2510b49cd4d3dce23a5ed05cc759213"
G7A_FE_NEW_ENTRY="100644 blob 13d15e91823d2b46b97dd4057c04d6c8628a29e0"
G7A_PR1422=b796d450505f77a3c9a0716c2c825db9800c27a7
# G7a rev 3.7 / D-G7A-2: one complete, source-adjudicated six-path manifest.
# The three changed paths affect chat/research dispatch, failed daily-mark
# publication and the existing D-G7A-1 hunk. Deploy probes/startup/schedules and
# the three deploy scripts retain their admitted mechanics. This is not a path
# waiver: any missing/foreign mode/blob on either side, or unreadable blob STOPs.
G7A_BUNDLE_PATHS=$'app/main.py\napp/scheduler.py\nportfolio/forward_evaluation.py'
G7A_BUNDLE_OLD_ENTRIES=$'100644 blob fdb22dc1a2650ff57d50a1c9c1cfebcf10521da4\tapp/main.py
100644 blob ec2546731d69289b5af4837a6d1eefe59caf9b37\tapp/scheduler.py
100644 blob 46031e40a2510b49cd4d3dce23a5ed05cc759213\tportfolio/forward_evaluation.py
100755 blob f871e88815e70338a646008dbe77dfcc1727e978\tscripts/deploy_code_to_vps.sh
100755 blob f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9\tscripts/deploy_from_git.sh
100755 blob a7a32713ef1477d1b84398ff24c6b9fda938831e\tscripts/refresh_datadog_release_tag.sh'
G7A_BUNDLE_NEW_ENTRIES=$'100644 blob 6106ff3dd2d55ba4f9eebe0440388fe2e446931c\tapp/main.py
100644 blob 50dca31c852e9abe332bd9e191ff900e6c1fcdb3\tapp/scheduler.py
100644 blob 13d15e91823d2b46b97dd4057c04d6c8628a29e0\tportfolio/forward_evaluation.py
100755 blob f871e88815e70338a646008dbe77dfcc1727e978\tscripts/deploy_code_to_vps.sh
100755 blob f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9\tscripts/deploy_from_git.sh
100755 blob a7a32713ef1477d1b84398ff24c6b9fda938831e\tscripts/refresh_datadog_release_tag.sh'
# G7a rev 3.8 / D-G7A-3: #2175 (7a3c0b78) on top of the D-G7A-2 bundle - same three paths, same OLD manifest, new
# main/scheduler blobs. Fabric portfolio dispatch is selected only by env/config; under the legacy selection the call
# shapes and /health values equal D-G7A-2, and the rev 3.8 rb health checks (backend=waterfall, policy=codex-first)
# refuse a Fabric-selected service. Any other blob or mode on either side STOPs.
G7A_PR2175=7a3c0b78710ffa66140228b6e2af53036c78d63e
G7A_BUNDLE3_NEW_ENTRIES=$'100644 blob ca6886c3ee02e6d58f992e6917be2739ce678ab9\tapp/main.py
100644 blob eb9840ad6086848e0ad3e44bc972fd7e7b67d7fe\tapp/scheduler.py
100644 blob 13d15e91823d2b46b97dd4057c04d6c8628a29e0\tportfolio/forward_evaluation.py
100755 blob f871e88815e70338a646008dbe77dfcc1727e978\tscripts/deploy_code_to_vps.sh
100755 blob f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9\tscripts/deploy_from_git.sh
100755 blob a7a32713ef1477d1b84398ff24c6b9fda938831e\tscripts/refresh_datadog_release_tag.sh'
# G7b rev 3.8 / D-G7B-5: #2228 + #2297 on top of D-G7B-4 - the jsonschema declaration plus the inert hermes plugin
# package-data stanza in pyproject.toml, comment-only gate-lock regeneration, and one ADDED test-only requirements
# file (never pip-installed by the deploy). Admitted only as these exact four-path mode/blob manifests (the .in is
# absent at OLD); T2 stays equal and the D-G7B-4 jsonschema runtime proof is mandatory at s1, prelaunch and s4.
G7B_D5_PATHS=(pyproject.toml requirements/gate-linux-x86_64-py312.lock requirements/gate-macos-arm64-py312.lock
              requirements/hermes-transport-observation-test.in)
G7B_D5_DEP="pyproject.toml
requirements/gate-linux-x86_64-py312.lock
requirements/gate-macos-arm64-py312.lock
requirements/hermes-transport-observation-test.in"
G7B_D5_DRIFT='+    "jsonschema>=4.26,<5",    # validates the existing bot tool roster for Fabric inference
+[tool.setuptools.package-data]
+"integrations.hermes_github_plugin" = ["plugin.yaml"]
+'
G7B_D5_OLD_ENTRIES=$G7B_JSONSCHEMA_OLD_ENTRIES
G7B_D5_NEW_ENTRIES=$'100644 blob 55d202a8847c2ca88f94943e8d1417623adb28bc\tpyproject.toml
100644 blob 41b7b36a0ba8514475c4546003025f2a5324d12b\trequirements/gate-linux-x86_64-py312.lock
100644 blob 3526e8fa0a7c9d8772969a75a5ec52071fa58c84\trequirements/gate-macos-arm64-py312.lock
100644 blob 39170f2e6bb26a824008615ccc93b57e40a6eb51\trequirements/hermes-transport-observation-test.in'
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
# rev 3.2 (seat ruling D-EVT-1): the live run_events.jsonl carries interleaved-write rows that do not parse (10 rows dated
# 2026-10-07..10-16 inside the 20000-line tail on 2026-11-02). Such a row is tolerated only when its leading "ts" prefix parses
# and is strictly before the threshold: the running process's ActiveEnterTimestamp when gates/process_active_enter.txt exists
# (G2 reasons about runs since process start), else 00:00Z two days before DAY. Every other unparsed row still reaches
# events-filter and stops the step, as before. Dropped rows are recorded in logs/unparsed_rows.log.
EVT_PREFILTER='
import sys, re, json, datetime
sys.stdin.reconfigure(errors="surrogateescape"); sys.stdout.reconfigure(errors="surrogateescape")  # rev 3.3: non-UTF-8 bytes pass through unchanged; such a row counts as unparsed
thr = float(sys.argv[1]); log = open(sys.argv[2], "a", errors="backslashreplace"); dropped = kept_bad = 0
pat = re.compile(r"^\{\"ts\":\"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\+00:00\"")  # rev 3.3: the host writes +00:00 only; any other suffix is not a trusted prefix
for line in sys.stdin:
    s = line.strip()
    if not s:
        continue
    try:
        s.encode("utf-8"); json.loads(s)  # UnicodeEncodeError (a surrogate-escaped byte) is a ValueError: the row is unparsed
        sys.stdout.write(line)
        continue
    except ValueError:
        pass
    m = pat.match(s); ts = None
    if m:
        try:
            ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            ts = None
    if ts is not None and ts < thr:
        dropped += 1; log.write("DROPPED ts=%s len=%d head=%s\n" % (m.group(1), len(s), s[:80])); continue
    kept_bad += 1; log.write("KEPT_UNPARSED ts=%s len=%d head=%s\n" % (m.group(1) if m else "?", len(s), s[:80]))
    sys.stdout.write(line)
print(json.dumps({"events_prefilter": {"threshold_epoch": thr, "dropped_before_threshold": dropped, "kept_unparsed": kept_bad}}), file=sys.stderr)
'
events_tail() {  # events_tail <out>: fresh 20000-line run_events tail, extra.flags dropped; unparsed rows before the threshold dropped (D-EVT-1; rev 3.3 hardening)
  local thr
  if [ -s "$EV/gates/process_active_enter.txt" ]; then thr=$(tr -d @ < "$EV/gates/process_active_enter.txt")
  else thr=$(( $(epoch "${DAY}T00:00") - 172800 )); fi
  [[ $thr =~ ^[0-9]+$ ]] || { echo "events_tail: bad threshold '$thr'" >&2; return 1; }
  "${VPS[@]}" "tail -n 20000 $LIVE/governance/run_events.jsonl" | "$PY" -I -B -c "$EVT_PREFILTER" "$thr" "$EV/logs/unparsed_rows.log" | rb events-filter > "$1"
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
    [ -n "${PBR_WAIVE_G2E:-}" ] || stop "G2: open run_started since process start: $(jget "$EV/gates/G1_G2.json" G2_open). Hold and re-run s2 (an open prewarm_marks, every 2 min, clears in ~2 min); a row older than its job's normal duration is a ledger anomaly - only the seat may waive it (PBR_WAIVE_G2E='<ruling ref>'); the cgroup liveness check still applies"
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
# systemd 255 prints NextElapseUSecRealtime as a pretty date even with --timestamp=unix, so the
# gated value is the raw D-Bus property (busctl "t <usec>"); the pretty lines are informational.
nx() { busctl get-property org.freedesktop.systemd1 "/org/freedesktop/systemd1/unit/$1" \
  org.freedesktop.systemd1.Timer NextElapseUSecRealtime 2>/dev/null | sed -n 's/^t \([0-9][0-9]*\)$/\1/p'; }
echo "upgrade_timer_next_usec=$(nx apt_2ddaily_2dupgrade_2etimer)"
echo "apt_timer_next_usec=$(nx apt_2ddaily_2etimer)"
echo "restart_timer_next_usec=$(nx mastermind_2drestart_2etimer)"
echo "upgrade_timer_next_pretty=$(systemctl show apt-daily-upgrade.timer -p NextElapseUSecRealtime --value)"
echo "apt_timer_next_pretty=$(systemctl show apt-daily.timer -p NextElapseUSecRealtime --value)"
echo "restart_timer_next_pretty=$(systemctl show mastermind-restart.timer -p NextElapseUSecRealtime --value)"
exit 0
EOF
  grep -Eqx 'apt_daily=(inactive|failed)' "$f" && grep -Eqx 'apt_daily_upgrade=(inactive|failed)' "$f" \
    && grep -qx 'unattended_upgrade_procs=0' "$f" && grep -qx 'needrestart_procs=0' "$f" \
    && grep -qx 'apt_dpkg_procs=0' "$f" && grep -qx 'lock_holders=no' "$f" \
    || stop "G3: apt/unattended-upgrade/needrestart/dpkg not idle (or lock state unknown) - hold and re-check; see $f"
  local nxt; nxt=$(sed -n 's/^upgrade_timer_next_usec=\([1-9][0-9]\{9,\}\)$/\1/p' "$f")  # 0/empty/garbled = unknown
  [ -n "$nxt" ] && nxt=$((nxt / 1000000))
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

g7_pipe_ok() {  # g7_pipe_ok "${PIPESTATUS[@]}": rc 0 iff stage 1 (git) exited 0 and every later grep stage 0|1 (2 = error). rev 3.6 (r6 MINOR)
  [ "$1" = 0 ] || return 1; shift
  local s; for s in "$@"; do [ "$s" -le 1 ] || return 1; done
  return 0
}

g7a_classify() {  # g7a_classify <wt> <old> <sha>: stdout G7A_MODE (none|D-G7A-1|D-G7A-2|D-G7A-3) rc 0; stderr reason rc 1. git reads only.
  local wt=$1 old=$2 sha=$3 mech oe ne entries metadata file blob mode
  mech=$(git -C "$wt" diff --no-renames --name-only "$old" "$sha" -- "${MECH[@]}") || { echo "G7a: git diff failed - STOP, seat" >&2; return 1; }
  [ -n "$mech" ] || { echo none; return 0; }
  if [ "$mech" = "$G7A_BUNDLE_PATHS" ]; then
    oe=$(git -C "$wt" ls-tree --full-tree "$old" -- "${MECH[@]}") || { echo "G7a: bundle OLD tree read failed - STOP, seat" >&2; return 1; }
    ne=$(git -C "$wt" ls-tree --full-tree "$sha" -- "${MECH[@]}") || { echo "G7a: bundle SHA tree read failed - STOP, seat" >&2; return 1; }
    if [ "$oe" != "$G7A_BUNDLE_OLD_ENTRIES" ]; then
      echo "G7a: three changed paths but OLD is not the complete D-G7A-2/D-G7A-3 mode+blob manifest - STOP, seat" >&2; return 1
    elif [ "$ne" = "$G7A_BUNDLE_NEW_ENTRIES" ]; then mode=D-G7A-2
    elif [ "$ne" = "$G7A_BUNDLE3_NEW_ENTRIES" ]; then mode=D-G7A-3   # rev 3.8: #2175
    else
      echo "G7a: three changed paths are not the complete D-G7A-2 or D-G7A-3 SHA mode+blob manifest - STOP, seat" >&2; return 1
    fi
    for entries in "$oe" "$ne"; do
      while IFS=$'\t' read -r metadata file; do
        blob=${metadata##* }
        git -C "$wt" cat-file -e "$blob^{blob}" || { echo "G7a: $mode blob unavailable ($file) - STOP, seat" >&2; return 1; }
      done <<< "$entries"
    done
    echo "$mode"; return 0
  fi
  [ "$mech" = "$G7A_FE_PATH" ] || { echo "G7a: deploy/runtime mechanics changed since OLD: $(echo $mech) - seat ruling (the runbook's mirrors would be stale)" >&2; return 1; }
  oe=$(git -C "$wt" ls-tree "$old" -- "$G7A_FE_PATH") || { echo "G7a: git ls-tree OLD failed - STOP, seat" >&2; return 1; }
  ne=$(git -C "$wt" ls-tree "$sha" -- "$G7A_FE_PATH") || { echo "G7a: git ls-tree SHA failed - STOP, seat" >&2; return 1; }
  if [ "$oe" != "$G7A_FE_OLD_ENTRY"$'\t'"$G7A_FE_PATH" ] || [ "$ne" != "$G7A_FE_NEW_ENTRY"$'\t'"$G7A_FE_PATH" ]; then
    echo "G7a: $G7A_FE_PATH changed since OLD but not as the D-G7A-1 pair (OLD '$oe' -> SHA '$ne') - STOP, seat" >&2; return 1
  fi
  echo D-G7A-1
}

g7b_mac_added() {  # g7b_mac_added <wt> <old> <sha>: stdout the D-G7B-2 admitted paths, sorted (may be empty); rc 1 = git failed. git reads only.
  local ns; ns=$(git -C "$1" diff --no-renames --name-status --diff-filter=A "$2" "$3" -- requirements/) || return 1
  printf '%s\n' "$ns" | cut -f2- | grep -E "$G7B_MAC_ADDED_RE" | grep -vi '^requirements/gate-' | sort   # rev 3.5 (r5o NIT): case-insensitive gate-* exclusion
  return 0
}

g7b_gate_locks_only() {  # g7b_gate_locks_only <sorted drift list>: rc 0 iff every line is one of G7B_GATE_LOCKS (D-G7B-3); pure bash
  local f g ok
  while IFS= read -r f; do
    ok=1
    while IFS= read -r g; do [ "$f" = "$g" ] && ok=0; done <<< "$G7B_GATE_LOCKS"
    [ "$ok" = 0 ] || return 1
  done <<< "$1"
  return 0
}

g7b_exact_manifest() {  # <wt> <old> <sha> <old entries> <new entries> <path...>: exact complete mode/blob manifests; 0 exact, 1 different, 2 unreadable
  local wt=$1 old=$2 sha=$3 want_old=$4 want_new=$5 oe ne entries metadata file blob
  shift 5
  oe=$(git -C "$wt" ls-tree --full-tree "$old" -- "$@") || return 2
  ne=$(git -C "$wt" ls-tree --full-tree "$sha" -- "$@") || return 2
  [ "$oe" = "$want_old" ] && [ "$ne" = "$want_new" ] || return 1
  for entries in "$oe" "$ne"; do
    while IFS=$'\t' read -r metadata file; do
      blob=${metadata##* }; git -C "$wt" cat-file -e "$blob^{blob}" || return 2
    done <<< "$entries"
  done
}
g7b_jsonschema_pair() {  # D-G7B-4 trio; 0 exact, 1 different, 2 unreadable
  g7b_exact_manifest "$1" "$2" "$3" "$G7B_JSONSCHEMA_OLD_ENTRIES" "$G7B_JSONSCHEMA_NEW_ENTRIES" \
    pyproject.toml requirements/gate-linux-x86_64-py312.lock requirements/gate-macos-arm64-py312.lock
}
g7b_d5_manifest() {  # D-G7B-5 four paths; 0 exact, 1 different, 2 unreadable
  g7b_exact_manifest "$1" "$2" "$3" "$G7B_D5_OLD_ENTRIES" "$G7B_D5_NEW_ENTRIES" "${G7B_D5_PATHS[@]}"
}
g7b_ruled_mode() {  # <wt> <old> <sha>: stdout D-G7B-4|D-G7B-5|legacy rc 0; rc 1 = source unreadable (never legacy). rev 3.8 (r8c MINOR 2)
  local rc=0
  g7b_jsonschema_pair "$1" "$2" "$3" || rc=$?
  [ "$rc" != 2 ] || return 1
  [ "$rc" != 0 ] || { echo D-G7B-4; return 0; }
  rc=0; g7b_d5_manifest "$1" "$2" "$3" || rc=$?
  [ "$rc" != 2 ] || return 1
  [ "$rc" != 0 ] || { echo D-G7B-5; return 0; }
  echo legacy
}

g7b_classify() {  # g7b_classify <wt> <old> <sha>: stdout T2_MODE (equal|floor_pending) rc 0; stderr reason rc 1. git reads only.
  local wt=$1 old=$2 sha=$3 dep mac
  dep=$(git -C "$wt" diff --no-renames --name-only "$old" "$sha" -- pyproject.toml requirements/ | sort) || { echo "G7b: git diff failed" >&2; return 1; }
  mac=$(g7b_mac_added "$wt" "$old" "$sha") || { echo "G7b: git diff failed" >&2; return 1; }
  if [ -n "$mac" ]; then   # rev 3.4 / D-G7B-2: drop the admitted macOS-only additions. rev 3.5 (r5o MINOR): comm must succeed and drop exactly |mac| lines
    local nd nm nr
    nd=$(printf '%s\n' "$dep" | grep -c .); nm=$(printf '%s\n' "$mac" | grep -c .)
    dep=$(comm -23 <(printf '%s\n' "$dep") <(printf '%s\n' "$mac")) || { echo "G7b: comm failed - STOP, seat" >&2; return 1; }
    nr=$(printf '%s\n' "$dep" | grep -c .)
    [ "$((nd - nr))" = "$nm" ] || { echo "G7b: D-G7B-2 admitted list is not a subset of the drift ($nd-$nr != $nm) - STOP, seat" >&2; return 1; }
  fi
  [ -n "$dep" ] || { echo equal; return 0; }
  [ "$dep" = "$SDK_TRIO" ] || [ "$dep" = "$G7B_D5_DEP" ] || g7b_gate_locks_only "$dep" || { echo "G7b: dependency drift beyond the #1714 trio / the D-G7B-3 gate-lock subset / the D-G7B-5 set: $(echo $dep) - STOP, seat" >&2; return 1; }
  # rev 3.5 / D-G7B-3: on a gate-lock-only drift pyproject.toml is unchanged, so plines/sdk/rest are empty and only lockbody decides
  local plines sdk sdk_bad rest lockbody
  plines=$(git -C "$wt" diff --text --no-textconv --no-ext-diff -U0 "$old" "$sha" -- pyproject.toml | grep -E '^[-+]' | grep -vE '^(--- |\+\+\+ )' | grep -vE '^[-+][[:space:]]*#'; g7_pipe_ok "${PIPESTATUS[@]}") \
    || { echo "G7b: pyproject.toml diff failed - STOP, seat" >&2; return 1; }   # rev 3.6 (r6 MINOR): a git failure must not read as an empty diff
  sdk=$(printf '%s\n' "$plines" | grep 'claude-agent-sdk' | grep -v '^$')                 # the floor's -/+ lines
  sdk_bad=$(printf '%s\n' "$sdk" | grep '^+' | grep -vc 'claude-agent-sdk>=0\.2')          # a new floor must stay in the 0.2 series
  rest=$(printf '%s\n' "$plines" | grep -v 'claude-agent-sdk' | grep -v '^$')
  [ "$sdk_bad" = 0 ] || { echo "G7b: the claude-agent-sdk floor is not a >=0.2 floor: $(echo $sdk) - STOP, seat" >&2; return 1; }
  if [ "$dep" = "$G7B_D5_DEP" ] || [ "$rest" = "$G7B_D5_DRIFT" ]; then   # rev 3.8 / D-G7B-5: all four bindings or STOP
    [ "$dep" = "$G7B_D5_DEP" ] && [ "$rest" = "$G7B_D5_DRIFT" ] && [ -z "$sdk" ] && g7b_d5_manifest "$wt" "$old" "$sha" \
      || { echo "G7b: drift is not the exact D-G7B-5 path set, pyproject drift and four-path mode/blob manifests - STOP, seat" >&2; return 1; }
  elif [ "$rest" = "$G7B_JSONSCHEMA_DRIFT" ]; then
    [ "$dep" = "$SDK_TRIO" ] && [ -z "$sdk" ] && g7b_jsonschema_pair "$wt" "$old" "$sha" \
      || { echo "G7b: jsonschema declaration is not the exact D-G7B-4 mode/blob pair - STOP, seat" >&2; return 1; }
  elif [ -n "$rest" ] && [ "$rest" != "$G7B_DEV_DRIFT" ]; then
    echo "G7b: pyproject drift is not the claude-agent-sdk floor / the ruled dev bound (D-G7B-1): $(echo $rest) - STOP, seat" >&2; return 1
  fi
  if [ -n "$sdk" ]; then echo floor_pending; return 0; fi   # #1714 trio: rev-2 semantics, T2 runs in floor_pending mode
  lockbody=$(git -C "$wt" diff --no-renames --text --no-textconv --no-ext-diff -U0 "$old" "$sha" -- requirements/gate-linux-x86_64-py312.lock requirements/gate-macos-arm64-py312.lock | grep -E '^[-+]' | grep -vE '^(--- |\+\+\+ )' | grep -vcE '^[-+][[:space:]]*#'; g7_pipe_ok "${PIPESTATUS[@]}") \
    || { echo "G7b: gate-lock diff failed - STOP, seat" >&2; return 1; }   # rev 3.1: column-0 option lines (-r, --index-url, -e) count as body lines; only the ---/+++ headers are dropped. rev 3.4: the two gate locks only. rev 3.5 (r5o NIT): --text --no-textconv --no-ext-diff. rev 3.6 (r6 MINOR/NIT): pipeline status checked (grep -c exits 1 on a zero count, so not `|| return`); --no-renames
  [ "$lockbody" = 0 ] || { echo "G7b: $lockbody non-comment gate-lock line(s) changed without an SDK floor (pins/extras/hashes) - STOP, seat" >&2; return 1; }
  echo equal
}

# Re-derive the condition from the frozen source at each affected runtime step.
# Missing/copied state must not turn the exact conditional case into legacy equal.
g7b_runtime_mode() {  # rev 3.8: D-G7B-4 or D-G7B-5 from the frozen source; the attempt state must name the same ruling
  local mode
  mode=$(g7b_ruled_mode "$WT" "$OLD" "$SHA") || { echo "G7b: frozen source unreadable" >&2; return 1; }
  if [ "$mode" != legacy ]; then
    [ "${G7B_MODE:-}" = "$mode" ] && [ "$T2_MODE" = equal ] \
      || { echo "G7b: $mode attempt state missing or inconsistent" >&2; return 1; }
  else
    [ "${G7B_MODE:-legacy}" = legacy ] || { echo "G7b: ruling does not match frozen source" >&2; return 1; }
  fi
  echo "$mode"
}

# Fixed library-only read. No application imports, network, package installation
# or portfolio reads/writes. timeout(1) also bounds the remote process if SSH drops.
T2_JSONSCHEMA_PROGRAM='
import copy, importlib.metadata, json, re, subprocess, sys
from jsonschema import Draft202012Validator, FormatChecker
binding = json.loads(sys.argv[1])
assert sys.executable == "/opt/mastermind/.venv/bin/python", "wrong interpreter"
assert importlib.metadata.version("jsonschema") == "4.26.0", "wrong jsonschema version"
unit = subprocess.check_output(["systemctl", "show", "mastermind.service", "-p", "ExecStart", "--value"], text=True, timeout=5)
paths = re.findall(r"(?:^|[ ;{])path=([^ ;}]+)", unit)
assert paths == ["/opt/mastermind/.venv/bin/uvicorn"], "wrong service interpreter"
schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
 "required": ["as_of", "decision_cutoff", "windows", "authority", "member"],
 "properties": {"as_of": {"type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
  "decision_cutoff": {"anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]},
  "windows": {"type": "array", "items": {"enum": [5,20,63]}, "minItems": 3, "maxItems": 3, "uniqueItems": True},
  "authority": {"type": "boolean", "const": False}, "member": {"$ref": "#/$defs/member"}},
 "$defs": {"member": {"type": "object", "required": ["symbol", "value"], "additionalProperties": False,
  "properties": {"symbol": {"type": "string", "pattern": "^[A-Z]{1,5}$"}, "value": {"type": ["number", "null"]}}}}}
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
value = {"as_of": "2026-11-02", "decision_cutoff": None, "windows": [5,20,63], "authority": False, "member": {"symbol": "XLK", "value": None}}
assert validator.is_valid(value), "valid value rejected"
bad = []
for key, replacement in [("as_of", "2026-02-30"), ("windows", [5,5,63]), ("windows", [5,20,99]), ("authority", True), ("member", {"symbol": "bad", "value": "wrong"})]:
 item = copy.deepcopy(value); item[key] = replacement; bad.append(item)
extra = copy.deepcopy(value); extra["unexpected"] = True; bad.append(extra)
assert all(not validator.is_valid(item) for item in bad), "invalid value accepted"
print(json.dumps({"binding": binding, "executable": sys.executable, "service_executable": paths[0], "version": "4.26.0", "valid": True, "invalid_rejected": len(bad)}, sort_keys=True))
'

t2_jsonschema_condition() {  # <pre|prelaunch|post> <fresh dists file> <proof file>
  local mode; mode=$(g7b_runtime_mode) || return 1
  [ "$mode" != legacy ] || return 0
  "$PY" -I -B - "$EV" "$SHA" "$1" "$2" "$3" "${BASH_SOURCE[0]}" "$mode" "$T2_JSONSCHEMA_PROGRAM" "${VPS[@]}" <<'PY'
import datetime, hashlib, json, pathlib, secrets, shlex, subprocess, sys
attempt, target, phase, dists_path, proof_path, driver_path, ruling, program, *ssh = sys.argv[1:]
def sha(data): return hashlib.sha256(data).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
try:
    assert ruling in ("D-G7B-4", "D-G7B-5"), "unknown ruling"
    assert phase in ("pre", "prelaunch", "post"), "unknown phase"
    dists = pathlib.Path(dists_path).read_bytes()
    versions = [line for line in dists.decode("utf-8").splitlines() if line.startswith("jsonschema==")]
    assert versions == ["jsonschema==4.26.0"], "fresh T2 distribution must identify exactly jsonschema==4.26.0"
    identity = {"attempt": str(pathlib.Path(attempt).resolve()), "target": target,
                "probe_sha256": sha(program.encode()), "driver_sha256": sha(pathlib.Path(driver_path).read_bytes())}
    if phase != "pre":
        baseline = json.loads((pathlib.Path(attempt)/"identity/pre/jsonschema.compatibility.json").read_text())
        assert baseline.get("schema") == "pbr-w1-jsonschema-compatibility/v1" and baseline.get("ruling") == ruling, "missing prior condition"
        assert all(baseline.get(k) == v for k,v in identity.items()), "prior proof belongs to a different attempt, target or driver"
        assert baseline.get("phase") == "pre" and baseline.get("distributions_sha256") == sha(dists), "pre/current distribution mismatch"
        assert baseline.get("result", {}).get("valid") is True, "prior compatibility did not pass"
    binding = {**identity, "phase": phase, "distributions_sha256": sha(dists), "nonce": secrets.token_hex(24)}
    request = "timeout --signal=KILL 15s /opt/mastermind/.venv/bin/python -I -B - " + shlex.quote(json.dumps(binding, sort_keys=True))
    started = now()
    result = subprocess.run([*ssh[:-1], "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3", ssh[-1], request],
                            input=program.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
    assert result.returncode == 0, "compatibility read failed rc=" + str(result.returncode)
    assert 0 < len(result.stdout) <= 8192, "invalid compatibility output size"
    observed = json.loads(result.stdout)
    expected = {"binding": binding, "executable": "/opt/mastermind/.venv/bin/python",
                "service_executable": "/opt/mastermind/.venv/bin/uvicorn", "version": "4.26.0", "valid": True, "invalid_rejected": 6}
    assert json.dumps(observed, sort_keys=True) == json.dumps(expected, sort_keys=True), "malformed, stale or incompatible response"
    receipt = {"schema": "pbr-w1-jsonschema-compatibility/v1", "ruling": ruling, **binding,
               "started_at": started, "completed_at": now(), "result": observed}
    out = pathlib.Path(proof_path)
    with out.open("w") as handle: handle.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
except Exception as exc:
    print(ruling + " runtime condition REFUSED: " + str(exc), file=sys.stderr)
    sys.exit(1)
PY
}

t2_jsonschema_prelaunch() {
  local mode; mode=$(g7b_runtime_mode) || stop "G7b runtime state"
  [ "$mode" != legacy ] || return 0
  local I=$EV/identity/prelaunch
  mkdir -p "$I" || stop "T2 prelaunch evidence"
  dists_read "$I/dists.txt" || stop "T2 prelaunch dists read"
  diff "$EV/identity/pre/dists.txt" "$I/dists.txt" > "$I/dists.diff" || stop "T2 prelaunch venv drift; no deploy, no pip"
  t2_jsonschema_condition prelaunch "$I/dists.txt" "$I/jsonschema.compatibility.json" || stop "$mode prelaunch compatibility; no deploy"
}

# ------------------------------------------------------------------ s0: bootstrap + G7 (Mac + git only)
s0() {
  STEP=s0
  [ -z "${PBR_EV:-}" ] || stop "PBR_EV is set; s0 always creates a new evidence dir (unset PBR_EV)"
  env_guard
  [ -n "${OPERATOR_SESSION_ID:-}" ] || stop "set OPERATOR_SESSION_ID to the executing session id (worktree identity)"
  local day=${PBR_DAY:-}
  [ -n "$day" ] || stop "set PBR_DAY=YYYY-MM-DD to the window day (rev 3.1 removed the 2026-10-23 default)"
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
       | "$PY_WT" -E -s -B "$WT_TOOL" create | tail -n 1) || stop "worktree create failed"   # -E -s -B, not -I: Python 3.14 isolated mode implies -P and hides the helper's sibling pool_storage module (rev 3); env/user-site isolation kept (rev 3.1)
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
  local g7a; g7a=$(g7a_classify "$wt" "$OLD" "$sha" 2> "$EV/gates/G7a.reason") || stop "$(cat "$EV/gates/G7a.reason")"   # rev 3.7 / exact D-G7A-1 or D-G7A-2
  rm -f "$EV/gates/G7a.reason"
  if [ "$g7a" = D-G7A-1 ]; then
    printf 'G7a (rev 3.6): %s changed OLD->SHA exactly as the D-G7A-1 pair (OLD %s -> SHA %s; #1422 %s, one hunk of _current_exposure_metrics on the build_snapshot path), traced inert to the deploy probes and the runbook G4/G6 mirrors (evidence runtime-rev36-build-20261106T0607Z/G7A_forward_evaluation_trace.md). Every other MECH path is unchanged OLD->SHA.\n' \
      "$G7A_FE_PATH" "$G7A_FE_OLD_ENTRY" "$G7A_FE_NEW_ENTRY" "${G7A_PR1422:0:9}" > "$EV/gates/G7a.RULING" || stop "G7a ruling record"
  elif [ "$g7a" = D-G7A-2 ]; then
    printf 'G7a (rev 3.7 / D-G7A-2): exact complete six-path bundle at frozen OLD=%s -> SHA=%s.\nChanged paths: app/main.py, app/scheduler.py, portfolio/forward_evaluation.py.\nOLD entries:\n%s\nSHA entries:\n%s\nThe three deployment scripts are unchanged. app/main.py changes chat/research dispatch; _runtime_health, _start_scheduler, health and ready retain their source. app/scheduler.py changes Self-Directed daily-mark failure handling: failed/unavailable marks suppress publication and retain FREEZE event handling; schedule registration/startup/cohort/deploy probes are unchanged. This is an intended later business-job behavior, not an inert release. The forward-evaluation hunk retains D-G7A-1. Source qualification: INSTALL_RUNBOOK.md D-G7A-2; original carrier Mastermind #1693. G7b, G8, Nov9 window, live-idle/WAL/outbox, overnight and marker/authority checks remain required.\n' \
      "$OLD" "$sha" "$G7A_BUNDLE_OLD_ENTRIES" "$G7A_BUNDLE_NEW_ENTRIES" > "$EV/gates/G7a.RULING" || stop "G7a bundle ruling record"
  elif [ "$g7a" = D-G7A-3 ]; then
    printf 'G7a (rev 3.8 / D-G7A-3): exact complete six-path bundle at frozen OLD=%s -> SHA=%s (the D-G7A-2 bundle plus #2175 %s on app/main.py and app/scheduler.py).\nChanged paths: app/main.py, app/scheduler.py, portfolio/forward_evaluation.py.\nOLD entries:\n%s\nSHA entries:\n%s\nThe three deployment scripts and the forward-evaluation blob equal the D-G7A-2 bundle. #2175 adds the Fabric portfolio path, selected only by MM_PROVIDER_APPLICATION_MODE in the service environment or a configured fabric cli_bridge backend; under the legacy selection with no runlog original, caller_kwargs is empty, so the job call shapes and the /health values equal D-G7A-2. app/main.py: the /health handler source changes (a Fabric branch; the legacy branch still reports reasoning_backend=waterfall and reasoning_policy=codex_first_claude_oauth_fallback) and rb health (rev 3.8) refuses any other backend or policy, so a Fabric-selected service STOPs the deploy health gate; manual wait-runs use brain.fabric_chat._observe_thread and end the ledger run on BaseException; manual responses add run_id/fabric_held. app/scheduler.py: fabric_held results map to FREEZE (fabric_effect_unsettled); autonomous/china/hk whole-book retries are skipped when a runlog original exists or Fabric is selected; brain jobs pass caller_kwargs; the overnight watch_us/watch_asia jobs pass the run handle, re-raise a watch failure and record per-book ledger status instead of an unconditional ok; maybe_first_* readiness accepts a runlog original, Fabric availability (Fabric selected) or cli_bridge availability. Schedule registration, startup, cohort and the deploy probes are unchanged. This is an intended later business-job behavior, not an inert release. The forward-evaluation hunk retains D-G7A-1. Source qualification: INSTALL_RUNBOOK.md D-G7A-3; original carriers Mastermind #1693 and #2175. G7b, G8, the window, live-idle/WAL/outbox, overnight and marker/authority checks remain required.\n' \
      "$OLD" "$sha" "${G7A_PR2175:0:9}" "$G7A_BUNDLE_OLD_ENTRIES" "$G7A_BUNDLE3_NEW_ENTRIES" > "$EV/gates/G7a.RULING" || stop "G7a D-G7A-3 ruling record"
  fi
  state G7A_MODE "$g7a"
  local t2; t2=$(g7b_classify "$wt" "$OLD" "$sha" 2> "$EV/gates/G7b.reason") || stop "$(cat "$EV/gates/G7b.reason")"
  rm -f "$EV/gates/G7b.reason"
  git -C "$wt" diff -U0 "$OLD" "$sha" -- pyproject.toml requirements/ > "$EV/identity/dep_drift.diff" || stop "dep drift diff"
  if [ -s "$EV/identity/dep_drift.diff" ]; then
    printf 'G7b (rev 3.8): dependency drift OLD->SHA classified T2_MODE=%s under seat rulings D-G7B-1..D-G7B-5; see identity/dep_drift.diff\n' "$t2" \
      > "$EV/gates/G7b.RULING" || stop "G7b ruling record"
    local mac; mac=$(g7b_mac_added "$wt" "$OLD" "$sha") || stop "G7b admitted list"
    [ -z "$mac" ] || printf 'D-G7B-2 admitted (added since OLD; macOS-arm64 only; the Linux deploy never pip-installs; .lock is rsync-excluded, .in is transferred but unconsumed):\n%s\n' "$mac" \
      >> "$EV/gates/G7b.RULING" || stop "G7b ruling record"
  fi
  state T2_MODE "$t2"
  local g7b
  g7b=$(g7b_ruled_mode "$wt" "$OLD" "$sha") || stop "G7b: frozen source unreadable"   # rev 3.8 (r8c MINOR 2): rc 2 is a STOP, never legacy
  if [ "$g7b" = D-G7B-4 ]; then
    printf 'D-G7B-4: exact pyproject/gate-lock mode+blob pair; only the direct jsonschema>=4.26,<5 declaration is added, both gate-lock bodies unchanged. T2_MODE=equal. RUNTIME CONDITION PENDING: fresh jsonschema==4.26.0 and same-service-interpreter Draft202012Validator/FormatChecker proof required at s1, immediately before s3, and s4. No package/venv change or SDK policy change.\n' >> "$EV/gates/G7b.RULING" || stop "G7b conditional ruling"
  elif [ "$g7b" = D-G7B-5 ]; then
    printf 'D-G7B-5 (rev 3.8; #2228 + #2297): exact four-path mode+blob manifests (pyproject.toml, both gate locks, requirements/hermes-transport-observation-test.in; the .in is absent at OLD). pyproject adds only the direct jsonschema>=4.26,<5 declaration and inert integrations.hermes_github_plugin package-data (plugin.yaml; the deploy never builds or pip-installs the project); both gate-lock bodies change in comments only; the test-only .in is transferred but never consumed. T2_MODE=equal. RUNTIME CONDITION PENDING: fresh jsonschema==4.26.0 and same-service-interpreter Draft202012Validator/FormatChecker proof required at s1, immediately before s3, and s4. No package/venv change or SDK policy change.\n' >> "$EV/gates/G7b.RULING" || stop "G7b conditional ruling"
  fi
  state G7B_MODE "$g7b"
  git -C "$wt" diff --name-status "$OLD" "$sha" > "$EV/identity/old_to_sha.name-status.txt"
  pass G7
  say "s0 PASS: SHA=$sha T2_MODE=$t2 G7A_MODE=$g7a G7B_MODE=$g7b WT=$wt"
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
  t2_jsonschema_condition pre "$I/dists.txt" "$I/jsonschema.compatibility.json" || stop "G7b runtime pre-change compatibility"
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
  t2_jsonschema_prelaunch
  gates_all   # live-idle/maintenance gates remain after the added library read
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
  local P=$EV/captures/post I=$EV/identity/post fail=0 t2_fail=0 t2_why=""
  show_read "$P/systemctl_show.txt" || stop "systemctl show"
  blob_manifest "$I/installed_manifest.jsonl" || stop "T1 manifest read"
  rb t1 --repo "$WT" --sha "$SHA" --manifest "$I/installed_manifest.jsonl" --out "$I" > "$I/t1_verdict.json" || { say "T1 FAIL"; fail=1; }
  grep -q '"marker_claim_matches": true' "$I/t1_verdict.json" || { say "T1 marker does not claim $SHA"; fail=1; }
  dists_read "$I/dists.txt" || stop "T2 dists read"
  if diff "$EV/identity/pre/dists.txt" "$I/dists.txt" > "$I/dists.diff"; then say "T2 PASS (venv unchanged; mode $T2_MODE)"
  else say "T2 FAIL: the venv changed during the deploy (the deploy never touches .venv)"; t2_fail=1; t2_why="venv changed outside the deploy"; fi
  t2_jsonschema_condition post "$I/dists.txt" "$I/jsonschema.compatibility.json" \
    || { say "T2 FAIL: ${G7B_MODE:-G7b} post-install compatibility"; t2_fail=1; t2_why="${t2_why:+$t2_why; }G7b post-install compatibility refused"; }   # rev 3.8 (r8c NIT 1)
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
  [ "$t2_fail" = 0 ] || fail=2   # a later T1/T3/T4 failure must not erase the no-rollback T2 hold
  case $fail in
    0) state INSTALLED "$SHA"; pass PROOF; say "s4 PASS: installed = $SHA (T1 T2 T3 T4 /health app_started + snapshot + marker) - run s4a, then s5" ;;
    2) stop "T2 FAIL - STOP: $t2_why; no rollback without the seat" ;;
    *) stop "post-install proof FAILED (see captures/post, identity/post) - R-b decision table with the seat" ;;
  esac
}

# ------------------------------------------------------------------ s4a: D-ACCT-1 account-load check
# Read-only. A quarantine file in any paper_account data dir, an account_state_invalid run_event /
# journal line since DEPLOY_T0 (any book), or an INVALID classification of an active paper_account
# book is a HOLD (exit 5): report to the seat. It is NOT a rollback trigger by itself.
# Classified: the active paper_account books. self_directed has its own engine (scheduler.py, the
# _MARK_BOOK_IDS note) and is never loaded through paper_account, so AccountStateInvalid cannot arise for it.
BOOKS_PA="autonomous china hk"
s4a() {  # s4a [label]: run after s4 PASS (label post-restart) and after each first-natural-cycle read
  STEP=s4a; load
  [ -f "$EV/gates/PROOF.PASS" ] || stop "run s4 first"
  local label=${1:-post-restart} hold=0 fc=0 b rc st summary=""
  case $label in ''|*[!A-Za-z0-9_.-]*) stop "label must match [A-Za-z0-9_.-]+" ;; esac
  local A=$EV/proof/account_load/$label
  [ -e "$A" ] && stop "$A exists - use a new label"
  mkdir -p "$A/src" || stop "mkdir $A"
  # grep without -q reads to EOF: under pipefail an early exit would SIGPIPE git show (rc 141)
  if git -C "$WT" show "$SHA:portfolio/paper_account.py" 2>/dev/null | grep '^class AccountStateInvalid(' > /dev/null; then fc=1; fi
  say "D-ACCT-1 fail-closed load present in $SHA: $([ "$fc" = 1 ] && echo yes || echo NO)"
  # 1. quarantine census over every paper_account data dir (legacy portfolio/ + portfolios/*/, archived
  #    books included: any load that quarantines leaves its copy beside the original). test/sha256sum/stat only.
  "${VPS[@]}" 'bash -s' > "$A/quarantine_census.txt" <<'EOF' || stop "quarantine census read"
cd /opt/mastermind-live-data || exit 1
k=0
for d in portfolio portfolios/*/; do
  d=${d%/}
  [ -d "$d" ] || continue
  n=0
  for f in "$d"/account.quarantine.*.json "$d"/account_quarantine.jsonl; do
    [ -e "$f" ] || continue
    n=$((n+1)); sha256sum -- "$f"; stat -c '%n size=%s mtime=%Y' -- "$f"
  done
  echo "dir $d quarantine_files=$n"; k=$((k+1))
done
echo "census_done dirs=$k"
EOF
  grep -q '^census_done dirs=' "$A/quarantine_census.txt" || stop "quarantine census incomplete"
  for b in $BOOKS_PA; do
    grep -q "^dir portfolios/$b quarantine_files=" "$A/quarantine_census.txt" || stop "quarantine census has no portfolios/$b"
  done
  grep -q 'quarantine_files=[1-9]' "$A/quarantine_census.txt" && { say "HOLD: quarantine file(s) present - $A/quarantine_census.txt"; hold=1; }
  # 2. run_events since DEPLOY_T0
  events_tail "$A/run_events.tail.jsonl" || stop "run_events read"
  [ -s "$A/run_events.tail.jsonl" ] || stop "run_events tail is empty"
  "$PY" -I -B - "$EV/tools" "$A/run_events.tail.jsonl" "$DEPLOY_T0" > "$A/account_state_invalid_events.jsonl" <<'PYEOF' || stop "run_events scan"
import json, sys
sys.path.insert(0, sys.argv[1])
import pbr_rb
since = float(sys.argv[3])
for line in open(sys.argv[2]):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r.get("kind") != "account_state_invalid":
        continue
    try:
        late = pbr_rb.parse_ts(r.get("ts")) >= since
    except Exception:
        late = True  # an unparseable stamp is never read as "before the deploy"
    if late:
        print(json.dumps({k: r.get(k) for k in ("ts", "book", "status", "severity", "extra")}, sort_keys=True))
PYEOF
  [ -s "$A/account_state_invalid_events.jsonl" ] && { say "HOLD: account_state_invalid run_event(s) since DEPLOY_T0"; hold=1; }
  # 3. journal since DEPLOY_T0 (the logger line); pipefail keeps a journalctl failure visible
  "${VPS[@]}" "set -o pipefail; journalctl -u $SVC --since=@$DEPLOY_T0 --no-pager -o short-iso-precise | { grep -E 'account_state_invalid|AccountStateInvalid' || true; }" \
    > "$A/journal_hits.txt" || stop "journal read"
  [ -s "$A/journal_hits.txt" ] && { say "HOLD: account_state_invalid in the journal since DEPLOY_T0"; hold=1; }
  # 4. classification with SHA's own read-only account_file_status, run on the Mac (no host import,
  #    so the host's .env is never loaded); the account bytes are deleted after classification
  if [ "$fc" = 1 ]; then
    git -C "$WT" archive "$SHA" portfolio/__init__.py portfolio/paper_account.py bot/__init__.py | tar -x -C "$A/src" \
      || stop "classifier extract"
    for b in $BOOKS_PA; do
      "${VPS[@]}" "test -e $LIVE/portfolios/$b/account.json"; rc=$?
      case $rc in
        1) printf '{"path": "%s", "problems": [], "sha256": null, "size": null, "status": "MISSING"}\n' \
             "$LIVE/portfolios/$b/account.json" > "$A/status.$b.json" ;;
        0) ( umask 077; "${VPS[@]}" "cat -- $LIVE/portfolios/$b/account.json" > "$A/src/.acct.$b" ) || stop "account.json read $b"
           "$PY_WT" -I -B - "$A/src" "$A/src/.acct.$b" "$LIVE/portfolios/$b/account.json" > "$A/status.$b.json" <<'PYEOF' \
             || { rm -f "$A/src/.acct.$b"; stop "classifier $b"; }
import json, sys
sys.path.insert(0, sys.argv[1])
from portfolio.paper_account import account_file_status
s = account_file_status(path=sys.argv[2])
s["path"] = sys.argv[3]
print(json.dumps(s, sort_keys=True))
PYEOF
           rm -f "$A/src/.acct.$b" ;;
        *) stop "account.json existence check $b (ssh rc $rc)" ;;
      esac
      st=$(jget "$A/status.$b.json" status | tr -d '"')
      summary="$summary $b=$st"
      [ "$st" = INVALID ] && { say "HOLD: $b account.json classifies INVALID ($(jget "$A/status.$b.json" problems))"; hold=1; }
      [ "$st" = MISSING ] && { say "HOLD: $b account.json is MISSING (an active paper_account book would seed a fresh book)"; hold=1; }
    done
    summary="$summary self_directed=n/a(own-engine)"
  else
    say "classification skipped: $SHA has no account_file_status (D-ACCT-1 not installed)"
  fi
  if [ "$hold" = 0 ]; then
    pass "ACCT_$label"; say "s4a PASS ($label): no quarantine file, no account_state_invalid event/journal line since DEPLOY_T0;${summary:- classification skipped}"
  else
    : > "$EV/gates/ACCT_$label.HOLD"
    say "s4a HOLD ($label): report $A to the seat - not a rollback trigger by itself; the affected book stays halted"
    exit 5
  fi
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

# needrestart proof (§6 #1). needrestart writes nothing to the journal on this host: its "Restarting
# services..." / "Service restarts being deferred:" report lands in the unattended-upgrades dpkg log
# (host local time, required +0000). NRestarts counts only Restart= restarts, so a needrestart
# "systemctl restart" is visible only as pid-1 journal lines and a new ActiveEnterTimestamp/InvocationID.
nr_judge() {  # nr_judge <dir> <cut> <apt_start> <apt_exit> <host_now> <baseline_show> <nr_verify_rc>: verdict JSON; exit 0 PASS, 1 FAIL
  "$PY" -I -B - "$@" <<'PY'
import calendar, json, os, re, sys, time
d, base = sys.argv[1], sys.argv[6]
cut, st, ex, now, nrrc = (int(sys.argv[i]) for i in (2, 3, 4, 5, 7))
TOK = re.compile(r'(^|\s)mastermind\.service(\s|$)')
HEAD = {"Restarting services...": "restart", "Service restarts being deferred:": "deferred",
        "Services to be restarted:": "listed"}
VERB = re.compile(r'\b(Stopping|Stopped|Starting|Started|Deactivated|Main process exited|Scheduled restart|Killing)\b')
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
def ep(day, hms): return calendar.timegm(time.strptime(day + " " + hms, "%Y-%m-%d %H:%M:%S"))
def lines(name): return open(os.path.join(d, name), errors="replace").read().splitlines()
raw = lines(".dpkg_log.raw"); absent = raw[:1] == ["#absent"]
blocks, cur = [], None
for ln in ([] if absent else raw):
    m = re.match(r'^Log started:\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s*$', ln)
    if m:
        cur = {"start": ep(*m.groups()), "end": None, "lines": [ln]}; blocks.append(cur); continue
    if cur is None: continue
    cur["lines"].append(ln)
    m = re.match(r'^Log ended:\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s*$', ln)
    if m: cur["end"] = ep(*m.groups()); cur = None
keep = [b for b in blocks if b["start"] >= cut]
with open(os.path.join(d, "dpkg_needrestart_blocks.txt"), "w") as f:
    for b in keep: f.write("\n".join(b["lines"]) + "\n")
hits = {"restart": [], "deferred": [], "listed": []}; nr_blocks = 0
for b in keep:
    sec = None; ran = False
    for ln in b["lines"]:
        if ln[:1] in (" ", "\t"):
            if sec and TOK.search(ln): hits[sec].append(iso(b["start"]))
        else:
            sec = HEAD.get(ln.strip()); ran = ran or sec is not None or ln.startswith("No services need")
    nr_blocks += ran
iv = [(st - 5, ex + 120)] + [(b["start"] - 5, (b["end"] if b["end"] is not None else now) + 120) for b in keep]
inside = lambda t: any(a <= t <= z for a, z in iv)
pid1 = []
for ln in lines("journal_pid1_unit.txt"):
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\S*\s', ln)
    if m and inside(ep(*m.groups())) and VERB.search(ln): pid1.append(ln[:200])
uu, on = [], False
for ln in lines(".uu_log.raw"):
    m = re.match(r'^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),', ln)
    if m: on = ep(*m.groups()) >= cut
    if on: uu.append(ln)
with open(os.path.join(d, "uu_log.txt"), "w") as f: f.write("\n".join(uu) + ("\n" if uu else ""))
def props(p):
    out = {}
    for ln in open(p, errors="replace"):
        k, _, v = ln.rstrip("\n").partition("="); out[k] = v
    return out
cur_p, base_p = props(os.path.join(d, "systemctl_show.txt")), props(base)
def tsu(v):
    m = re.fullmatch(r'@(\d+)(\.\d+)?', v or ""); return int(m.group(1)) if m else None
def num(v): return int(v) if re.fullmatch(r'\d+', v or "") else None
ae, n_now, n_base = tsu(cur_p.get("ActiveEnterTimestamp")), num(cur_p.get("NRestarts")), num(base_p.get("NRestarts"))
reasons, notes = [], []
for t in hits["restart"]: reasons.append("mastermind.service is in a needrestart restart list (block %s)" % t)
for ln in pid1: reasons.append("pid-1 journal inside an unattended-upgrade run: " + ln)
if ae is None: reasons.append("ActiveEnterTimestamp unreadable now")
elif inside(ae): reasons.append("ActiveEnterTimestamp %s is inside an unattended-upgrade run" % iso(ae))
if n_now is None or n_base is None: reasons.append("NRestarts unreadable (baseline %r, now %r)" % (n_base, n_now))
elif n_now > n_base: reasons.append("NRestarts %d -> %d since the baseline (a Restart= auto-restart) - incident" % (n_base, n_now))
elif n_now < n_base: notes.append("NRestarts %d -> %d: flushed by a manual restart" % (n_base, n_now))
if cur_p.get("ActiveState") != "active": reasons.append("mastermind.service ActiveState=%s now" % cur_p.get("ActiveState"))
if nrrc != 0: reasons.append("the mastermind override is not configured now (nr_verify rc=%d)" % nrrc)
same = cur_p.get("InvocationID") == base_p.get("InvocationID")
if not same and ae is not None: notes.append("InvocationID changed since the baseline; last start %s (expected only from the 08:30Z mastermind-restart.timer)" % iso(ae))
timer = any((z - 30600) // 86400 > (a - 1 - 30600) // 86400 for a, z in iv)
if timer: notes.append("an unattended-upgrade interval spans 08:30Z (mastermind-restart.timer): seat adjudicates any pid-1 line")
v = "FAIL" if reasons else "PROVEN" if hits["deferred"] else "LISTED" if hits["listed"] else "VACUOUS"
print(json.dumps({"check": "needrestart", "verdict": v, "pass": not reasons, "reasons": reasons, "notes": notes,
    "cut": iso(cut), "apt_daily_upgrade": [iso(st), iso(ex)], "dpkg_log_absent": absent,
    "blocks_since_cut": len(keep), "needrestart_blocks": nr_blocks, "restart_hits": hits["restart"],
    "deferred_hits": hits["deferred"], "listed_hits": hits["listed"], "pid1_in_upgrade": pid1,
    "intervals": [[iso(a), iso(z)] for a, z in iv], "nrestarts": [n_base, n_now], "active_enter": iso(ae) if ae else None,
    "invocation_same_as_baseline": same, "nr_verify_rc": nrrc, "overlaps_0830_timer": timer}, indent=1))
sys.exit(0 if not reasons else 1)
PY
}
needrestart_check() {  # needrestart_check [YYYY-MM-DD]: the first unattended upgrade after the window (§6 #1; read-only)
  STEP=needrestart-check; load
  local day=${1:-$DAY} cut base C now tz as st ex nrrc rc v
  [[ $day =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || stop "bad day '$day'"
  [ -f "$EV/gates/NEEDRESTART.PASS" ] || stop "s5 has not passed - there is no override to prove"
  [ ! -e "$EV/needrestart/verify_after_revert.txt" ] || stop "s5 was reverted - there is no override to prove; seat"
  if [ -f "$EV/gates/PROOF_OLD.PASS" ]; then base=$EV/rollback/proof/systemctl_show.txt
  elif [ -f "$EV/gates/PROOF.PASS" ]; then base=$EV/captures/post/systemctl_show.txt
  else stop "no s4/proof-old baseline"; fi
  [ -s "$base" ] || stop "baseline $base is missing"
  cut=$(epoch "${day}T05:40") || stop "bad day '$day'"
  C="$EV/cycles/${day}T0540Z_needrestart"; mkdir -p "$C" || stop "mkdir $C"
  "${VPS[@]}" 'date +"%s %z"' > "$C/host_clock.txt" || stop "host clock read failed"
  read -r now tz < "$C/host_clock.txt"
  [[ ${now:-} =~ ^[0-9]+$ ]] || stop "host clock unreadable"
  [ "${tz:-}" = "+0000" ] || stop "host UTC offset is '${tz:-}', not +0000 - the dpkg log is in local time; seat"
  "${VPS[@]}" "systemctl show apt-daily-upgrade.service --timestamp=unix -p ActiveState -p Result -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p ExecMainStatus" \
    > "$C/apt_upgrade_show.txt" || stop "apt-daily-upgrade read failed"
  as=$(sed -n 's/^ActiveState=//p' "$C/apt_upgrade_show.txt")
  st=$(sed -n 's/^ExecMainStartTimestamp=@\([0-9]*\).*/\1/p' "$C/apt_upgrade_show.txt")
  ex=$(sed -n 's/^ExecMainExitTimestamp=@\([0-9]*\).*/\1/p' "$C/apt_upgrade_show.txt")
  [ -n "$st" ] && [ "$st" -ge "$cut" ] \
    || stop "not yet: apt-daily-upgrade has not started since ${day}T05:40Z (last start: $([ -n "$st" ] && date -u -r "$st" +%FT%TZ || echo none)) - re-run after it finishes (expected ~06:00-06:10Z; latest timer draw 07:00Z)"
  { [ "$as" = inactive ] || [ "$as" = failed ]; } && [ -n "$ex" ] && [ "$ex" -ge "$st" ] \
    || stop "not yet: apt-daily-upgrade is '$as' (started $(date -u -r "$st" +%FT%TZ)) - re-run after it finishes"
  show_read "$C/systemctl_show.txt" || stop "systemctl show"
  nr_verify > "$C/nr_verify_now.txt"; nrrc=$?
  "${VPS[@]}" "test ! -e $UU_DPKG_LOG && echo '#absent' || cat -- $UU_DPKG_LOG" > "$C/.dpkg_log.raw" || stop "dpkg log read failed"
  "${VPS[@]}" "test ! -e $UU_LOG && echo '#absent' || cat -- $UU_LOG" > "$C/.uu_log.raw" || stop "unattended-upgrades log read failed"
  "${VPS[@]}" "bash -s -- $cut" > "$C/journal_needrestart.txt" <<'EOF' || stop "journal read failed"
journalctl --since=@"$1" --no-pager -o short-iso-precise | grep -i needrestart
r=("${PIPESTATUS[@]}"); [ "${r[0]}" -eq 0 ] && [ "${r[1]}" -le 1 ]
EOF
  "${VPS[@]}" "journalctl _PID=1 UNIT=$SVC --since=@$((cut - 300)) --no-pager -o short-iso-precise" > "$C/journal_pid1_unit.txt" \
    || stop "pid-1 journal read failed"
  nr_judge "$C" "$cut" "$st" "$ex" "$now" "$base" "$nrrc" > "$C/verdict.json"; rc=$?
  rm -f -- "$C/.dpkg_log.raw" "$C/.uu_log.raw"
  v=$(jget "$C/verdict.json" verdict 2>/dev/null) || stop "no verdict (judge rc=$rc) - see $C"
  [ "$rc" -eq 0 ] || stop "needrestart-check FAIL: $(jget "$C/verdict.json" reasons) - INCIDENT, report to the seat (s5-revert does not undo a restart); evidence $C"
  case $v in
    '"PROVEN"') say "needrestart-check PASS (PROVEN): needrestart deferred mastermind.service and no unattended-upgrade run since ${day}T05:40Z restarted it - §6 #1 proven" ;;
    '"LISTED"') say "needrestart-check PASS (LISTED): needrestart only listed mastermind.service (list mode) and nothing restarted it - restart-mode override not exercised" ;;
    *) say "needrestart-check PASS (VACUOUS): no needrestart report named mastermind.service since ${day}T05:40Z ($(jget "$C/verdict.json" blocks_since_cut) dpkg blocks) - §6 #1 still unproven; re-run after the next library upgrade" ;;
  esac
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
  [ "$(jget "$R/rb_open_runs.json" G2_no_open_run_since_process_start)" = true ] || stop "R-b precondition: an open run since the deploy: $(jget "$R/rb_open_runs.json" G2_open). Nothing on the host changed yet; an open prewarm_marks clears in ~2 min - re-run rollback-b; anything else - seat"
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

g7b_selftest() {  # helper import + 40 retained, 23 D-G7A-2, 23 D-G7B-4, 13 D-G7A-3 and 23 D-G7B-5 cases; git only, no host contact
  STEP=g7b-selftest
  local root fail=0 n=0 r live
  root=$(mktemp -d) || stop "mktemp"
  G7B_SELFTEST_ROOT=$root; trap 'rm -rf "$G7B_SELFTEST_ROOT"' EXIT   # global: a local is out of scope when the EXIT trap runs under set -u
  _g=(git -c user.name=t -c user.email=t@t -c commit.gpgsign=false)
  _pp() {  # _pp <sdk spec> <pytest spec> <comment-or-empty> <extra dependency line-or-empty> <out>
    printf '[project]\ndependencies = [\n    "claude-agent-sdk>=%s",\n%s]\n[project.optional-dependencies]\ndev = [\n%s    "pytest>=%s",\n]\n' "$1" "$4" "$3" "$2" > "$5"
  }
  _lock() {  # _lock <header sha> <sdk pin> <sdk hash> <pytest pin> <out>
    printf '# pyproject.toml sha256: %s\n# Regenerate: pip-compile --generate-hashes ... pyproject.toml\nclaude-agent-sdk==%s \\\n    --hash=sha256:%s\npytest==%s \\\n    --hash=sha256:p1\n' "$1" "$2" "$3" "$4" > "$5"
  }
  _mk() {  # _mk <name>: repo at the OLD shape, one commit; prints its path
    local d=$root/$1
    mkdir -p "$d/requirements" && "${_g[@]}" -C "$d" init -q || return 1
    _pp 0.1 '8,<10' '' '' "$d/pyproject.toml"
    _lock aaaa 0.1.0 s1 9.1.1 "$d/requirements/gate-linux-x86_64-py312.lock"
    _lock aaaa 0.1.0 s1 9.1.1 "$d/requirements/gate-macos-arm64-py312.lock"
    echo old > "$d/README.md"
    "${_g[@]}" -C "$d" add -A && "${_g[@]}" -C "$d" commit -qm old || return 1
    echo "$d"
  }
  _mac() {  # _mac <repo> <stem>: an AEAD-like macOS-arm64 .in/.lock pair with pins and hashes (D-G7B-2 shape)
    printf '# direct pins\ncryptography==50.0.1\n' > "$1/requirements/$2-macos-arm64-py312.in"
    printf 'cryptography==50.0.1 \\\n    --hash=sha256:c1\ncffi==2.0.0 \\\n    --hash=sha256:c2\n' > "$1/requirements/$2-macos-arm64-py312.lock"
  }
  _base() {  # _base <case>: commit the working change in $r as the new OLD (no classification)
    "${_g[@]}" -C "$r" add -A && "${_g[@]}" -C "$r" commit -qm base || stop "selftest base $1"
  }
  _expect() {  # _expect <case> <repo> <old> <new> <want: equal|floor_pending|none|D-G7A-1|D-G7A-2|D-G7A-3|D-G7B-4|D-G7B-5|legacy|STOP|ANY> [classifier, default g7b_classify]
    n=$((n + 1))
    local got rc; got=$("${6:-g7b_classify}" "$2" "$3" "$4" 2>/dev/null); rc=$?; [ "$rc" -eq 0 ] || got=STOP
    if [ "$got" = "$5" ] || { [ "$5" = ANY ] && [ "$got" != STOP ]; }; then say "g7b-selftest $1: PASS ($got)"
    else say "g7b-selftest $1: FAIL want=$5 got=$got"; fail=1; fi
  }
  _run() {  # _run <case> <want> [classifier]: commit the working change in $r, classify HEAD~1..HEAD
    "${_g[@]}" -C "$r" add -A && "${_g[@]}" -C "$r" commit -qm new || stop "selftest commit $1"
    _expect "$1" "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" "$2" "${3:-}"
  }
  _unread() {  # _unread <repo> <path>: commit the working change, then delete the loose object of <path> at HEAD (git cannot read it)
    "${_g[@]}" -C "$1" add -A && "${_g[@]}" -C "$1" commit -qm new || return 1
    local o; o=$(git -C "$1" rev-parse "HEAD:$2") && [ -f "$1/.git/objects/${o:0:2}/${o:2}" ] && rm -f "$1/.git/objects/${o:0:2}/${o:2}"
  }
  _mka() {  # _mka <name>: repo with forward_evaluation.py = the D-G7A-1 OLD blob plus one other MECH path; prints its path
    local d=$root/$1
    mkdir -p "$d/portfolio" "$d/app" && "${_g[@]}" -C "$d" init -q || return 1
    cp "$fe_a" "$d/$G7A_FE_PATH" && echo main > "$d/app/main.py" && echo old > "$d/README.md" || return 1
    "${_g[@]}" -C "$d" add -A && "${_g[@]}" -C "$d" commit -qm old || return 1
    echo "$d"
  }
  _capture_bundle() {  # _capture_bundle <directory> <fixed manifest>; actual source blobs, fixture bytes only
    local d=$1 entries=$2 metadata file blob file_mode
    while IFS=$'\t' read -r metadata file; do
      blob=${metadata##* }; file_mode=${metadata%% *}
      mkdir -p "$d/$(dirname "$file")" || return 1
      git -C "$SEAT_WT" cat-file blob "$blob" > "$d/$file" || return 1
      case "$file_mode" in
        100644) chmod 644 "$d/$file" || return 1 ;;
        100755) chmod 755 "$d/$file" || return 1 ;;
        *) return 1 ;;
      esac
    done <<< "$entries"
  }
  _mkb() {  # _mkb <name>: an inert repository containing the complete D-G7A-2 OLD manifest
    local d=$root/$1
    mkdir -p "$d" && cp -R "$root/bundle.old/." "$d/" && echo old > "$d/README.md" \
      && "${_g[@]}" -C "$d" init -q && "${_g[@]}" -C "$d" config core.filemode true \
      && "${_g[@]}" -C "$d" add -A && "${_g[@]}" -C "$d" commit -qm old || return 1
    echo "$d"
  }
  _newb() {  # _newb <repo> [source, default bundle.new]: only the three changed paths; stable scripts remain observable invariants
    local file src=${2:-$root/bundle.new}
    while IFS= read -r file; do
      cp "$src/$file" "$1/$file" && chmod 644 "$1/$file" || return 1
    done <<< "$G7A_BUNDLE_PATHS"
  }
  local cmt=$'    # pytest 9.2.0 reds five existing tests at teardown; hold below 9.2\n'
  n=$((n + 1)); if "$PY_WT" -E -s -B "$WT_TOOL" --help > /dev/null 2>&1; then say "g7b-selftest c0_wt_tool: PASS (helper imports under -E -s -B)"; else say "g7b-selftest c0_wt_tool: FAIL ($PY_WT -E -s -B $WT_TOOL --help)"; fail=1; fi
  r=$(_mk c1_unrelated) || stop "mk"; echo new > "$r/README.md"; _run c1_unrelated equal
  r=$(_mk c2_sdk_floor) || stop "mk"; _pp 0.2.120 '8,<10' '' '' "$r/pyproject.toml"
    _lock bbbb 0.2.120 s2 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock bbbb 0.2.120 s2 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c2_sdk_floor floor_pending
  r=$(_mk c3_dev_bound) || stop "mk"; _pp 0.1 '8,<9.2' "$cmt" '' "$r/pyproject.toml"
    _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c3_dev_bound equal
  r=$(_mk c4_dev_bound_lockpin) || stop "mk"; _pp 0.1 '8,<9.2' "$cmt" '' "$r/pyproject.toml"
    _lock cccc 0.1.0 s1 9.2.0 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock cccc 0.1.0 s1 9.2.0 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c4_dev_bound_lockpin STOP
  r=$(_mk c5_other_dep) || stop "mk"; _pp 0.1 '8,<10' '' $'    "requests>=2",\n' "$r/pyproject.toml"
    _lock dddd 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock dddd 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c5_other_dep STOP
  r=$(_mk c6_extra_file) || stop "mk"; echo x > "$r/requirements/extra.txt"; _run c6_extra_file STOP
  r=$(_mk c7_sdk_plus_dev) || stop "mk"; _pp 0.2.120 '8,<9.2' "$cmt" '' "$r/pyproject.toml"
    _lock eeee 0.2.120 s2 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock eeee 0.2.120 s2 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c7_sdk_plus_dev floor_pending
  r=$(_mk c9_sdk_floor_0_3) || stop "mk"; _pp 0.3 '8,<10' '' '' "$r/pyproject.toml"
    _lock ffff 0.3.0 s3 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock ffff 0.3.0 s3 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c9_sdk_floor_0_3 STOP
  r=$(_mk c10_lock_col0_option) || stop "mk"; _pp 0.1 '8,<9.2' "$cmt" '' "$r/pyproject.toml"
    _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    printf -- '--index-url https://example.invalid/simple\n' >> "$r/requirements/gate-linux-x86_64-py312.lock"
    _run c10_lock_col0_option STOP
  # rev 3.4 / D-G7B-2: added macOS-arm64 platform files
  r=$(_mk c11_mac_added) || stop "mk"; _mac "$r" executive-control-aead; _run c11_mac_added equal
  r=$(_mk c12_mac_added_dev_bound) || stop "mk"; _pp 0.1 '8,<9.2' "$cmt" '' "$r/pyproject.toml"
    _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock cccc 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _mac "$r" executive-control-aead; _run c12_mac_added_dev_bound equal
  r=$(_mk c13_mac_added_sdk_floor) || stop "mk"; _pp 0.2.120 '8,<10' '' '' "$r/pyproject.toml"
    _lock bbbb 0.2.120 s2 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock bbbb 0.2.120 s2 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _mac "$r" executive-control-aead; _run c13_mac_added_sdk_floor floor_pending
  r=$(_mk c14_linux_added) || stop "mk"; _lock aaaa 0.1.0 s1 9.1.1 "$r/requirements/extra-linux-x86_64-py312.lock"; _run c14_linux_added STOP
  r=$(_mk c15_gate_named_mac_added) || stop "mk"; _lock aaaa 0.1.0 s1 9.1.1 "$r/requirements/gate-extra-macos-arm64-py312.lock"
    _run c15_gate_named_mac_added STOP
  r=$(_mk c16_mac_modified) || stop "mk"; _mac "$r" ws; _base c16_mac_modified
    printf 'idna==3.10 \\\n    --hash=sha256:c3\n' >> "$r/requirements/ws-macos-arm64-py312.lock"; _run c16_mac_modified STOP
  r=$(_mk c17_mac_deleted) || stop "mk"; _mac "$r" ws; _base c17_mac_deleted
    rm "$r/requirements/ws-macos-arm64-py312.in"; _run c17_mac_deleted STOP
  r=$(_mk c18_renamed_to_mac) || stop "mk"; _lock aaaa 0.1.0 s1 9.1.1 "$r/requirements/extra.txt"; _base c18_renamed_to_mac
    "${_g[@]}" -C "$r" mv requirements/extra.txt requirements/extra-macos-arm64-py312.lock || stop "selftest mv"; _run c18_renamed_to_mac STOP
  r=$(_mk c19_mac_subdir) || stop "mk"; mkdir -p "$r/requirements/sub"; _lock aaaa 0.1.0 s1 9.1.1 "$r/requirements/sub/x-macos-arm64-py312.lock"
    _run c19_mac_subdir STOP
  # rev 3.5 / D-G7B-3: gate-lock-only drift with pyproject.toml unchanged (#1909 shape)
  r=$(_mk c20_locks_header_only) || stop "mk"
    _lock 1909 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock 1909 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c20_locks_header_only equal
  r=$(_mk c21_one_lock_header_only) || stop "mk"; _lock 1909 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"
    _run c21_one_lock_header_only equal
  r=$(_mk c22_lock_pin_pyproject_equal) || stop "mk"
    _lock 1909 0.1.0 s1 9.2.0 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock 1909 0.1.0 s1 9.2.0 "$r/requirements/gate-macos-arm64-py312.lock"
    _run c22_lock_pin_pyproject_equal STOP
  # rev 3.6 (r6 MINOR/NIT): an unreadable blob or a rename-paired gate lock must STOP, never read as an empty diff
  r=$(_mk c23_lock_blob_unreadable) || stop "mk"
    _lock 1909 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock 1909 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _unread "$r" requirements/gate-linux-x86_64-py312.lock || stop "selftest unread c23"
    _expect c23_lock_blob_unreadable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP
  r=$(_mk c24_pyproject_blob_unreadable) || stop "mk"; _pp 0.2.120 '8,<10' '' '' "$r/pyproject.toml"
    _lock bbbb 0.1.0 s1 9.1.1 "$r/requirements/gate-linux-x86_64-py312.lock"; _lock bbbb 0.1.0 s1 9.1.1 "$r/requirements/gate-macos-arm64-py312.lock"
    _unread "$r" pyproject.toml || stop "selftest unread c24"
    _expect c24_pyproject_blob_unreadable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP
  r=$(_mk c25_lock_rename_pair) || stop "mk"; rm "$r/requirements/gate-macos-arm64-py312.lock"; _base c25_lock_rename_pair
    "${_g[@]}" -C "$r" mv requirements/gate-linux-x86_64-py312.lock requirements/gate-macos-arm64-py312.lock || stop "selftest mv"
    _run c25_lock_rename_pair STOP
  live=$(git -C "$SEAT_WT" rev-parse --verify -q origin/master) || stop "SEAT_WT origin/master unreadable"
  _expect "c8_live(OLD..origin/master@${live:0:8})" "$SEAT_WT" "$OLD" "$live" ANY
  # rev 3.6 / D-G7A-1: forward_evaluation.py is admitted only as the exact OLD->SHA mode+blob pair; synthetic repos carry the real blobs
  local fe_a=$root/fe.old fe_b=$root/fe.new
  git -C "$SEAT_WT" cat-file blob "${G7A_FE_OLD_ENTRY##* }" > "$fe_a" && git -C "$SEAT_WT" cat-file blob "${G7A_FE_NEW_ENTRY##* }" > "$fe_b" \
    || stop "selftest: the D-G7A-1 blobs are unreadable in $SEAT_WT"
  r=$(_mka a1_unrelated) || stop "mk"; echo new > "$r/README.md"; _run a1_unrelated none g7a_classify
  r=$(_mka a2_exact_pair) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; _run a2_exact_pair D-G7A-1 g7a_classify
  r=$(_mka a3_exact_pair_plus_unrelated) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; echo new > "$r/README.md"
    _run a3_exact_pair_plus_unrelated D-G7A-1 g7a_classify
  r=$(_mka a4_other_new_blob) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; echo '# x' >> "$r/$G7A_FE_PATH"; _run a4_other_new_blob STOP g7a_classify
  r=$(_mka a5_other_old_blob) || stop "mk"; echo '# x' >> "$r/$G7A_FE_PATH"; _base a5_other_old_blob
    cp "$fe_b" "$r/$G7A_FE_PATH"; _run a5_other_old_blob STOP g7a_classify
  r=$(_mka a6_pair_plus_other_mech) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; echo main2 > "$r/app/main.py"
    _run a6_pair_plus_other_mech STOP g7a_classify
  r=$(_mka a7_other_mech_only) || stop "mk"; echo main2 > "$r/app/main.py"; _run a7_other_mech_only STOP g7a_classify
  r=$(_mka a8_fe_deleted) || stop "mk"; rm "$r/$G7A_FE_PATH"; _run a8_fe_deleted STOP g7a_classify
  r=$(_mka a9_fe_added) || stop "mk"; rm "$r/$G7A_FE_PATH"; _base a9_fe_added
    cp "$fe_b" "$r/$G7A_FE_PATH"; _run a9_fe_added STOP g7a_classify
  r=$(_mka a10_pair_exec_mode) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; chmod +x "$r/$G7A_FE_PATH"
    _run a10_pair_exec_mode STOP g7a_classify
  r=$(_mka a11_reverse_pair) || stop "mk"; cp "$fe_b" "$r/$G7A_FE_PATH"; _base a11_reverse_pair
    cp "$fe_a" "$r/$G7A_FE_PATH"; _run a11_reverse_pair STOP g7a_classify
  r=$(_mka a12_bad_rev) || stop "mk"
    _expect a12_bad_rev "$r" 0000000000000000000000000000000000000001 "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  _expect "a13_live_pr1422(OLD..${G7A_PR1422:0:9})" "$SEAT_WT" "$OLD" "$G7A_PR1422" D-G7A-1 g7a_classify
  _expect "a14_live(OLD..origin/master@${live:0:8})" "$SEAT_WT" "$OLD" "$live" ANY g7a_classify
  # rev 3.7 / D-G7A-2: retain a1-a14 and qualify the complete six-path manifests.
  _capture_bundle "$root/bundle.old" "$G7A_BUNDLE_OLD_ENTRIES" \
    && _capture_bundle "$root/bundle.new" "$G7A_BUNDLE_NEW_ENTRIES" || stop "selftest: D-G7A-2 source blobs unavailable"
  r=$(_mkb b1_exact_bundle) || stop "mk"; _newb "$r" || stop "bundle"; _run b1_exact_bundle D-G7A-2 g7a_classify
  r=$(_mkb b2_bundle_unrelated) || stop "mk"; _newb "$r" || stop "bundle"; echo new > "$r/README.md"
    _run b2_bundle_unrelated D-G7A-2 g7a_classify
  local file tag oid
  while IFS= read -r file; do
    tag=${file##*/}; tag=${tag//./_}
    r=$(_mkb "b3_wrong_old_$tag") || stop "mk"; echo '# unqualified OLD' >> "$r/$file"; _base "b3_wrong_old_$tag"
      _newb "$r" || stop "bundle"; _run "b3_wrong_old_$tag" STOP g7a_classify
    r=$(_mkb "b4_wrong_target_$tag") || stop "mk"; _newb "$r" || stop "bundle"; echo '# unqualified SHA' >> "$r/$file"
      _run "b4_wrong_target_$tag" STOP g7a_classify
  done <<< "$G7A_BUNDLE_PATHS"
  r=$(_mkb b5_old_mode) || stop "mk"; chmod 755 "$r/app/main.py"; _base b5_old_mode
    _newb "$r" || stop "bundle"; _run b5_old_mode STOP g7a_classify
  r=$(_mkb b6_target_mode) || stop "mk"; _newb "$r" || stop "bundle"; chmod 755 "$r/app/main.py"
    _run b6_target_mode STOP g7a_classify
  r=$(_mkb b7_added) || stop "mk"; rm "$r/app/main.py"; _base b7_added
    _newb "$r" || stop "bundle"; _run b7_added STOP g7a_classify
  r=$(_mkb b8_deleted) || stop "mk"; _newb "$r" || stop "bundle"; rm "$r/app/main.py"; _run b8_deleted STOP g7a_classify
  r=$(_mkb b9_reverted) || stop "mk"; _newb "$r" || stop "bundle"; cp "$root/bundle.old/$G7A_FE_PATH" "$r/$G7A_FE_PATH"
    _run b9_reverted STOP g7a_classify
  r=$(_mkb b10_renamed) || stop "mk"; _newb "$r" || stop "bundle"; mv "$r/app/main.py" "$r/app/main-renamed.py"
    _run b10_renamed STOP g7a_classify
  r=$(_mkb b11_reverse) || stop "mk"; _newb "$r" || stop "bundle"; _base b11_reverse
    cp -R "$root/bundle.old/." "$r/" || stop "bundle"; _run b11_reverse STOP g7a_classify
  r=$(_mkb b12_extra_mechanics) || stop "mk"; _newb "$r" || stop "bundle"; echo '# extra' >> "$r/scripts/deploy_code_to_vps.sh"
    _run b12_extra_mechanics STOP g7a_classify
  r=$(_mkb b13_foreign_stable_script) || stop "mk"; echo '# foreign on both sides' >> "$r/scripts/deploy_code_to_vps.sh"; _base b13_foreign_stable_script
    _newb "$r" || stop "bundle"; _run b13_foreign_stable_script STOP g7a_classify
  r=$(_mkb b14_missing_stable_script) || stop "mk"; rm "$r/scripts/deploy_code_to_vps.sh"; _base b14_missing_stable_script
    _newb "$r" || stop "bundle"; _run b14_missing_stable_script STOP g7a_classify
  r=$(_mkb b15_bad_old_rev) || stop "mk"
    _expect b15_bad_old_rev "$r" 0000000000000000000000000000000000000001 "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  r=$(_mkb b16_bad_target_rev) || stop "mk"
    _expect b16_bad_target_rev "$r" "$(git -C "$r" rev-parse HEAD)" 0000000000000000000000000000000000000001 STOP g7a_classify
  r=$(_mkb b17_old_blob_unavailable) || stop "mk"; _newb "$r" || stop "bundle"
    "${_g[@]}" -C "$r" add -A && "${_g[@]}" -C "$r" commit -qm new || stop "selftest commit b17"
    oid=$(git -C "$r" rev-parse HEAD~1:app/main.py) && [ -f "$r/.git/objects/${oid:0:2}/${oid:2}" ] \
      && rm "$r/.git/objects/${oid:0:2}/${oid:2}" || stop "selftest unread b17"
    _expect b17_old_blob_unavailable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  r=$(_mkb b18_target_blob_unavailable) || stop "mk"; _newb "$r" || stop "bundle"; _unread "$r" app/main.py || stop "selftest unread b18"
    _expect b18_target_blob_unavailable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  r=$(_mkb b19_stable_blob_unavailable) || stop "mk"; _newb "$r" || stop "bundle"; _unread "$r" scripts/deploy_code_to_vps.sh || stop "selftest unread b19"
    _expect b19_stable_blob_unavailable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  # rev 3.8 / D-G7A-3: the same OLD manifest and three paths with #2175's main/scheduler blobs; any mix with D-G7A-2 STOPs
  _capture_bundle "$root/bundle3.new" "$G7A_BUNDLE3_NEW_ENTRIES" || stop "selftest: D-G7A-3 source blobs unavailable"
  local b3=$root/bundle3.new
  r=$(_mkb e1_exact_bundle3) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; _run e1_exact_bundle3 D-G7A-3 g7a_classify
  r=$(_mkb e2_bundle3_unrelated) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; echo new > "$r/README.md"
    _run e2_bundle3_unrelated D-G7A-3 g7a_classify
  while IFS= read -r file; do
    tag=${file##*/}; tag=${tag//./_}
    r=$(_mkb "e3_wrong_target_$tag") || stop "mk"; _newb "$r" "$b3" || stop "bundle"; echo '# unqualified SHA' >> "$r/$file"
      _run "e3_wrong_target_$tag" STOP g7a_classify
  done <<< "$G7A_BUNDLE_PATHS"
  r=$(_mkb e4_mixed_main3_sched2) || stop "mk"; _newb "$r" || stop "bundle"; cp "$b3/app/main.py" "$r/app/main.py"
    _run e4_mixed_main3_sched2 STOP g7a_classify
  r=$(_mkb e5_mixed_main2_sched3) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; cp "$root/bundle.new/app/main.py" "$r/app/main.py"
    _run e5_mixed_main2_sched3 STOP g7a_classify
  r=$(_mkb e6_target_mode) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; chmod 755 "$r/app/scheduler.py"; _run e6_target_mode STOP g7a_classify
  r=$(_mkb e7_extra_mechanics) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; echo '# extra' >> "$r/scripts/deploy_from_git.sh"
    _run e7_extra_mechanics STOP g7a_classify
  r=$(_mkb e8_reverse) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; _base e8_reverse
    cp -R "$root/bundle.old/." "$r/" || stop "bundle"; _run e8_reverse STOP g7a_classify
  r=$(_mkb e9_from_bundle2) || stop "mk"; _newb "$r" || stop "bundle"; _base e9_from_bundle2
    _newb "$r" "$b3" || stop "bundle"; _run e9_from_bundle2 STOP g7a_classify
  r=$(_mkb e10_target_blob_unavailable) || stop "mk"; _newb "$r" "$b3" || stop "bundle"; _unread "$r" app/scheduler.py || stop "selftest unread e10"
    _expect e10_target_blob_unavailable "$r" "$(git -C "$r" rev-parse HEAD~1)" "$(git -C "$r" rev-parse HEAD)" STOP g7a_classify
  _expect "a15_live_pr2175(OLD..${G7A_PR2175:0:9})" "$SEAT_WT" "$OLD" "$G7A_PR2175" D-G7A-3 g7a_classify
  rm -rf "$root"
  _capture_bundle "$root/deps.old" "$G7B_JSONSCHEMA_OLD_ENTRIES" \
    && _capture_bundle "$root/deps.new" "$G7B_JSONSCHEMA_NEW_ENTRIES" || stop "selftest: D-G7B-4 source blobs unavailable"
  _mkd() {
    local d=$root/$1
    mkdir -p "$d" && cp -R "$root/deps.old/." "$d/" && echo old > "$d/README.md" \
      && "${_g[@]}" -C "$d" init -q && "${_g[@]}" -C "$d" config core.filemode true \
      && "${_g[@]}" -C "$d" add -A && "${_g[@]}" -C "$d" commit -qm old || return 1
    echo "$d"
  }
  _newd() { cp -R "$root/deps.new/." "$1/"; }
  r=$(_mkd d1_exact) || stop "mk"; _newd "$r" || stop "deps"; _run d1_exact equal
  r=$(_mkd d2_added_mac) || stop "mk"; _newd "$r" || stop "deps"; _mac "$r" extra; _run d2_added_mac equal
  r=$(_mkd d3_unrelated) || stop "mk"; _newd "$r" || stop "deps"; echo new > "$r/README.md"; _run d3_unrelated equal
  local dp di=0
  while IFS= read -r dp; do
    di=$((di + 1))
    r=$(_mkd "d4_wrong_old_$di") || stop "mk"; echo '# different old source' >> "$r/$dp"; _base "d4_$di"; _newd "$r" || stop "deps"; _run "d4_wrong_old_$di" STOP
    r=$(_mkd "d5_wrong_new_$di") || stop "mk"; _newd "$r" || stop "deps"; echo '# different new source' >> "$r/$dp"; _run "d5_wrong_new_$di" STOP
  done <<< "$SDK_TRIO"
  r=$(_mkd d6_old_mode) || stop "mk"; chmod 755 "$r/pyproject.toml"; _base d6; _newd "$r" || stop "deps"; chmod 644 "$r/pyproject.toml"; _run d6_old_mode STOP
  r=$(_mkd d7_new_mode) || stop "mk"; _newd "$r" || stop "deps"; chmod 755 "$r/requirements/gate-linux-x86_64-py312.lock"; _run d7_new_mode STOP
  r=$(_mkd d8_extra_file) || stop "mk"; _newd "$r" || stop "deps"; echo extra > "$r/requirements/extra-linux.txt"; _run d8_extra_file STOP
  r=$(_mkd d9_extra_dependency) || stop "mk"; _newd "$r" || stop "deps"; echo 'unexpected-dependency = "1"' >> "$r/pyproject.toml"; _run d9_extra_dependency STOP
  r=$(_mkd d10_sdk_combination) || stop "mk"; _newd "$r" || stop "deps"; echo 'claude-agent-sdk>=0.2.120' >> "$r/pyproject.toml"; _run d10_sdk_combination STOP
  r=$(_mkd d11_lock_pin) || stop "mk"; _newd "$r" || stop "deps"; echo 'another==1.2.3' >> "$r/requirements/gate-linux-x86_64-py312.lock"; _run d11_lock_pin STOP
  r=$(_mkd d12_lock_option) || stop "mk"; _newd "$r" || stop "deps"; echo '--index-url https://invalid.example' >> "$r/requirements/gate-macos-arm64-py312.lock"; _run d12_lock_option STOP
  r=$(_mkd d13_deleted_pyproject) || stop "mk"; _newd "$r" || stop "deps"; rm "$r/pyproject.toml"; _run d13_deleted_pyproject STOP
  r=$(_mkd d14_renamed_gate) || stop "mk"; _newd "$r" || stop "deps"; mv "$r/requirements/gate-linux-x86_64-py312.lock" "$r/requirements/renamed-macos-arm64-py312.lock"; _run d14_renamed_gate STOP
  r=$(_mkd d15_reverse) || stop "mk"; _newd "$r" || stop "deps"; _base d15
    _expect d15_reverse "$r" HEAD HEAD~1 STOP
  _expect d16_bad_old "$r" missing-old HEAD STOP
  _expect d17_bad_new "$r" HEAD~1 missing-target STOP
  r=$(_mkd d18_old_unreadable) || stop "mk"; _newd "$r" || stop "deps"; _base d18
    oid=$(git -C "$r" rev-parse HEAD~1:pyproject.toml) && rm "$r/.git/objects/${oid:0:2}/${oid:2}" || stop "unread d18"
    _expect d18_old_unreadable "$r" HEAD~1 HEAD STOP
  r=$(_mkd d19_new_unreadable) || stop "mk"; _newd "$r" || stop "deps"; _unread "$r" pyproject.toml || stop "unread d19"
    _expect d19_new_unreadable "$r" HEAD~1 HEAD STOP
  # rev 3.8 / D-G7B-5: the D-G7B-4 OLD trio to the exact four-path manifests (.in added); every neighbour STOPs
  _capture_bundle "$root/deps5.new" "$G7B_D5_NEW_ENTRIES" || stop "selftest: D-G7B-5 source blobs unavailable"
  _newd5() { cp -R "$root/deps5.new/." "$1/"; }
  local d5in=requirements/hermes-transport-observation-test.in
  r=$(_mkd f1_exact) || stop "mk"; _newd5 "$r" || stop "deps"; _run f1_exact equal
  r=$(_mkd f2_unrelated) || stop "mk"; _newd5 "$r" || stop "deps"; echo new > "$r/README.md"; _run f2_unrelated equal
  r=$(_mkd f3_added_mac) || stop "mk"; _newd5 "$r" || stop "deps"; _mac "$r" extra; _run f3_added_mac equal
  di=0
  for dp in "${G7B_D5_PATHS[@]}"; do
    di=$((di + 1))
    r=$(_mkd "f4_wrong_new_$di") || stop "mk"; _newd5 "$r" || stop "deps"; echo '# different new source' >> "$r/$dp"; _run "f4_wrong_new_$di" STOP
  done
  di=0
  while IFS= read -r dp; do
    di=$((di + 1))
    r=$(_mkd "f5_wrong_old_$di") || stop "mk"; echo '# different old source' >> "$r/$dp"; _base "f5_$di"; _newd5 "$r" || stop "deps"; _run "f5_wrong_old_$di" STOP
  done <<< "$SDK_TRIO"
  r=$(_mkd f6_in_present_at_old) || stop "mk"; cp "$root/deps5.new/$d5in" "$r/$d5in" || stop "deps"; _base f6; _newd5 "$r" || stop "deps"
    _run f6_in_present_at_old STOP
  r=$(_mkd f7_missing_in) || stop "mk"; _newd5 "$r" || stop "deps"; rm "$r/$d5in"; _run f7_missing_in STOP
  r=$(_mkd f8_renamed_in) || stop "mk"; _newd5 "$r" || stop "deps"; mv "$r/$d5in" "$r/requirements/hermes-transport-observation-test2.in"; _run f8_renamed_in STOP
  r=$(_mkd f9_no_package_data) || stop "mk"; _newd5 "$r" || stop "deps"; cp "$root/deps.new/pyproject.toml" "$r/pyproject.toml"; _run f9_no_package_data STOP
  r=$(_mkd f10_sdk_line) || stop "mk"; _newd5 "$r" || stop "deps"; echo '    "claude-agent-sdk>=0.2.120",' >> "$r/pyproject.toml"; _run f10_sdk_line STOP
  r=$(_mkd f11_in_exec_mode) || stop "mk"; _newd5 "$r" || stop "deps"; chmod 755 "$r/$d5in"; _run f11_in_exec_mode STOP
  r=$(_mkd f12_reverse) || stop "mk"; _newd5 "$r" || stop "deps"; _base f12
    _expect f12_reverse "$r" HEAD HEAD~1 STOP
  r=$(_mkd f13_in_unreadable) || stop "mk"; _newd5 "$r" || stop "deps"; _unread "$r" "$d5in" || stop "unread f13"
    _expect f13_in_unreadable "$r" HEAD~1 HEAD STOP
  # g7b_ruled_mode: the runtime ruling re-derived from source; unreadable is never legacy
  _expect g1_ruled_d5 "$root/f1_exact" HEAD~1 HEAD D-G7B-5 g7b_ruled_mode
  _expect g2_ruled_d4 "$root/d1_exact" HEAD~1 HEAD D-G7B-4 g7b_ruled_mode
  r=$(_mkd g3_ruled_legacy) || stop "mk"; echo new > "$r/README.md"; _run g3_ruled_legacy legacy g7b_ruled_mode
  _expect g4_ruled_unreadable "$root/f13_in_unreadable" HEAD~1 HEAD STOP g7b_ruled_mode
  _expect "g5_ruled_live(OLD..origin/master@${live:0:8})" "$SEAT_WT" "$OLD" "$live" ANY g7b_ruled_mode
  [ "$fail" = 0 ] || stop "g7b-selftest FAILED"
  [ "$n" = 122 ] || stop "g7b-selftest ran $n cases, expected 122"
  say "g7b-selftest PASS ($n cases)"
}

g7a_check() {  # rev 3.8: s0's G7a on SEAT_WT origin/master as of its last fetch (git only, no host contact); the precheck's mirror of s0 0.5
  STEP=g7a-check
  local live g7a why
  live=$(git -C "$SEAT_WT" rev-parse --verify -q origin/master) || stop "SEAT_WT origin/master unreadable"
  git -C "$SEAT_WT" merge-base --is-ancestor "$OLD" "$live" || stop "G7: OLD $OLD is not an ancestor of origin/master@${live:0:8}"
  why=$(mktemp) || stop "mktemp"
  g7a=$(g7a_classify "$SEAT_WT" "$OLD" "$live" 2> "$why") || { local m; m=$(cat "$why"); rm -f "$why"; stop "origin/master@${live:0:8}: $m"; }
  rm -f "$why"
  say "g7a-check PASS (origin/master@${live:0:8}: G7A_MODE=$g7a)"
}

status() { load; cat "$EV/state.env"; ls "$EV/gates"; tail -n 5 "$EV/logs/stops.log" 2>/dev/null; return 0; }

[[ "${BASH_SOURCE[0]}" == "$0" ]] || return 0   # sourced (fixture tests): define functions only

case "${1:-}" in
  s0) s0 ;;
  s1) s1 ;;
  s2) s2 ;;
  s3) s3 ;;
  s3-result) s3_result ;;
  s4) s4 ;;
  s4a) shift; s4a "$@" ;;
  s5) s5 ;;
  s5-revert) s5_revert ;;
  s6) s6 ;;
  cycle) shift; cycle "$@" ;;
  restart-check) shift; restart_check "$@" ;;
  needrestart-check) shift; needrestart_check "$@" ;;
  proof-old) proof_old ;;
  rollback-b) rollback_b ;;
  rollback-c) rollback_c ;;
  rollback-c-result) rollback_c_result ;;
  status) status ;;
  g7b-selftest) g7b_selftest ;;
  g7a-check) g7a_check ;;
  *) echo "usage: install_w1.sh s0|s1|s2|s3|s3-result|s4|s4a [label]|s5|s5-revert|s6|cycle <job> <HH:MM> [book] [day]|restart-check [HH:MM] [day]|needrestart-check [day]|proof-old|rollback-b|rollback-c|rollback-c-result|status|g7b-selftest|g7a-check" >&2; exit 2 ;;
esac
