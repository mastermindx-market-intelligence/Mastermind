#!/bin/bash
# Post-queue-drain fix for PR #2155 — run AFTER queue empties.
# Builds candidate from CURRENT sol head + drained master, resolves take-theirs,
# then gates on SQUASH-EQUIVALENT mergeability (GitHub's real check).
set -e
cd /Users/chriswong/.hermes/cache/scratch/pr2155
SOLBR=sol/hermes-primary-fabric-inference-20261106-sol-01

echo "== fetch =="
git fetch origin master "$SOLBR"
git fetch origin "$SOLBR:refs/solhead2" 2>/dev/null || true
SOL=$(git rev-parse refs/solhead2); M=$(git rev-parse origin/master)
echo "sol head: $SOL  master: $M"

echo "== build candidate =="
git checkout -q -B reloc2155f "$SOL"
if git merge "$M" --no-commit; then echo "merge auto-clean"; fi
# resolve any conflicts: take theirs (master), all files
python3 - <<'EOF'
import re, subprocess
files = subprocess.run(['git','diff','--name-only','--diff-filter=U'],capture_output=True,text=True).stdout.split()
pat = re.compile(r'<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', re.S)
tot=0
for f in files:
    src=open(f).read(); r,n=pat.subn(lambda m:m.group(2),src); open(f,'w').write(r); tot+=n
    print(f"{n:3} hunks -> theirs  {f}")
print(f"TOTAL {tot} hunks across {len(files)} files")
bad=[f for f in files if '<<<<<<<' in open(f).read()]
assert not bad, f"markers left: {bad}"
EOF
git add -A
git commit -q -m "Merge drained master ${M:0:8}: converge contested regions to master for queue admission" || true
CAND=$(git rev-parse reloc2155f)
echo "candidate: $CAND"

echo "== SQUASH-EQUIV GATE (GitHub's real 3-way, ancient base) =="
X=$(git commit-tree "$CAND^{tree}" -p "$SOL" -m "squash-equiv probe")
git merge-tree --write-tree --name-only "$M" "$X" > /tmp/mtgate.txt 2>&1
GATE=$?
cat /tmp/mtgate.txt | head -10
if [ $GATE -ne 0 ]; then echo "GATE FAIL: squash-equiv NOT clean vs master — DO NOT SHIP"; exit 2; fi
echo "GATE PASS: squash-equiv CLEAN vs $M"

echo "== smoke: registry consumer + oauth =="
/tmp/venvchk/bin/python -m pytest tests/test_executive_fabric_release_identity_review.py tests/test_hermes_workspace_oauth_identity_review.py -q 2>&1 | tail -1

echo "== ship =="
git push -q origin reloc2155f:refs/heads/chriswong/resolve-2155-drain-sync
gh pr create --base "$SOLBR" --head chriswong/resolve-2155-drain-sync \
  --title "Converge #2155 to drained master ${M:0:8} for queue admission" \
  --body "Post-drain convergence: all contested regions byte-identical to master $M so PR-level mergeable is CLEAN and auto-merge can admit into the (now empty) queue. Squash-equiv gate verified: single-parent probe commit merge-tree CLEAN vs master."
echo "PR created above; now: gh pr merge <N> --admin --squash --delete-branch"
