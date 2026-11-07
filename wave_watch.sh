#!/bin/bash
# Read-only wave watcher. No pushes/merges/edits.
R=mastermindx-market-intelligence/Mastermind
echo "=== CYCLE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "--QUEUE--"
gh api graphql -f query='query{repository(owner:"mastermindx-market-intelligence",name:"Mastermind"){mergeQueue{entries(first:15){nodes{position,state,pullRequest{number}}}}}}' 2>&1
echo ""
echo "--2224--"
gh pr view 2224 --repo $R --json state,mergedAt,autoMergeRequest,mergeStateStatus,mergeCommit 2>&1
echo "--2217--"
gh pr view 2217 --repo $R --json state,mergedAt,autoMergeRequest,mergeStateStatus,mergeCommit 2>&1
echo "--2189--"
gh pr view 2189 --repo $R --json state,mergedAt,mergeCommit 2>&1
echo "--789--"
gh pr view 789 --repo $R --json state,mergedAt,mergeCommit 2>&1
echo "--MASTER--"
git ls-remote https://github.com/mastermindx-market-intelligence/Mastermind.git refs/heads/master
