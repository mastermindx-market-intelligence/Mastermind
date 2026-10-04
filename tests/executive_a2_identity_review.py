"""Frozen review of the A2 public-plist metadata expectation, not new authority.

Reviewed source: d2b45df4f6128feb4fc08d9dd76c350039f404cc.
Function source SHA256: cdd3eee061177e312dd0803a75a625342df8e2b3ce6065e2d9222c0b721db1ec.
The existing owner reads a public root-owned plist with exact mode 0644. It
neither changes permissions nor reads the relay credential. Only that permission
Constant is acknowledged; UID/GID names and all call structure remain scanned.
Any function or literal drift requires a new independent source review.
"""

REVIEWED_PATH = "ops/executive_os/a2_agent_relay_enrollment.py"
REVIEWED_LITERAL_COUNT = 1
REVIEWED_ANCHORS = {
    "w3c_plist_configured": {
        "node_type": "FunctionDef",
        "ast_sha256": "4f7cb9086bcf5b2a69d64009116a3dbc2754d698adcffda44718b7def6ef57c2",
        "sites": (
            (("body", 1, "body", 0, "value", "keywords", 2, "value"), "int", 420, "0o644"),
        ),
    },
}
