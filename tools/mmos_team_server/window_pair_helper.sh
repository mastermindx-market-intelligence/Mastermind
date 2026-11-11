#!/bin/sh
# window_pair_helper.sh — mint one fresh one-time pairing URL for a
# Mastermind OS window (lane T8, PROGRAM_PLAN_V4).
#
# The window runs this helper with no arguments and reads the URL from the
# pipe. It reuses `t3 pair` exactly: the token is minted by opening the
# server home's auth database, so the only authority that works here is being
# the macOS user who owns that home (file ownership). Nothing is admitted
# over loopback TCP or a request header, and there is no second auth path.
#
# Secret rules: the pairing URL (with its one-time token) is written to
# stdout for the window only — never argv, never a log, never evidence.
# t3's own stderr is discarded unread so no child diagnostic can carry a
# secret into the caller.
#
# Defaults target the installed team server (127.0.0.1:3780). A dev server
# overrides with WINDOW_PAIR_T3_BIN / WINDOW_PAIR_T3_HOME. The window clears
# the environment when it runs this helper from the fixed config, so those
# variables only reach a helper that is run directly (a wrapper script named
# in the config is the supported way to aim the window at a dev server; see
# open_team_window.sh and the runbook).
set -eu

T3_BIN="${WINDOW_PAIR_T3_BIN:-$HOME/.mastermind/t3-team-server/bin/t3}"
T3_HOME="${WINDOW_PAIR_T3_HOME:-$HOME/.mastermind/t3-team/home}"

if [ ! -x "$T3_BIN" ]; then
  echo "window_pair_helper: t3 command is not executable: $(basename "$T3_BIN")" >&2
  exit 1
fi
if [ ! -d "$T3_HOME" ]; then
  echo "window_pair_helper: t3 home directory not found" >&2
  exit 1
fi

# --base-dir is passed explicitly because `t3 pair` otherwise prefers a
# linked-worktree state dir over T3CODE_HOME when the caller sits inside one
# (this repo's checkout is a T3 worktree); the flag makes minting
# deterministic from any working directory. --ttl keeps the one-time token
# short-lived (the window consumes it within seconds); --label marks the
# connection in the server's list. stderr of the minting command is dropped
# so only the URL line ever leaves this script.
#
# Panel repair C: the minting command's own exit status must become this
# script's exit status. The output is captured first (under `set -eu` a
# failing command substitution fails the assignment, and nothing is printed
# on that path), and only a successful mint's output is filtered to the one
# URL line — a pipeline would otherwise mask the failure with sed's exit
# status and the window would read an empty "success" from a dead server.
pair_output=$(T3CODE_HOME="$T3_HOME" "$T3_BIN" pair --base-dir "$T3_HOME" --ttl 2m --label 'Mastermind OS window' 2>/dev/null)
printf '%s\n' "$pair_output" | sed -n 's/^Pairing URL: //p' | head -n 1
