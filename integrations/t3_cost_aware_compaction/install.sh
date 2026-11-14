#!/bin/sh
set -eu
printf '%s\n' 'ERROR: adaptive compaction installation is held: the shared-settings writer is not qualified.' 'Use compaction.py report mode. Existing installed jobs require separate owner reconciliation; this script does not alter them.' >&2
exit 2
