# Deterministic text-only fixture for SCF-GHP1 source tests.
# The runtime test generates a >10,000-line source in memory; this small file
# exists only to reserve a harmless fixture namespace for the later live canary.

CANARY_SCHEMA = "mastermind.github_branch_patch_canary.v1"
CANARY_STATE = "SOURCE_ONLY_PRODUCTION_INERT"
