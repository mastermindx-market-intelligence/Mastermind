"""Test-only exact pins for the two reviewed direct-native sources.

Accepted preimages, independently reviewed before this static guard repair
(root reviewed exact H7ef2597e0, review 989fd839):
  control_plane/direct_native_correction.py
    sha256 e1ca2333e98ed5931cb01f8cbd3770b0240a18c7bdee358b2baea3efd88ed678
  integrations/mastermind_executive_app/direct_native.py
    sha256 f1b433eaeeb7e80743aefbf7e956d579033ba4cb743227952f26030c065969e0

Each record acknowledges one exact Constant token of the already-reviewed
source: the fixed 0o700 sealed run/workspace boundary mode comparison in
``validate_terminal`` and the fixed 503 status operand of the correction
unknown-receipt builder inside ``dispatch_direct_correction``. The complete
postimage digest, the whole anchor AST and the exact value and spelling are
pinned together; any change to the file, the anchor or the literal returns
the token to the generic D8 guard. Identifiers such as ``uid`` and
``control_uid`` stay visible; tests never learn replacement pins from source.
No runtime authority is added.
"""

REVIEWED_ANCHORS_BY_PATH = {
    "control_plane/direct_native_correction.py": {
        "validate_terminal": {
            "node_type": "FunctionDef",
            "source_sha256": "e1ca2333e98ed5931cb01f8cbd3770b0240a18c7bdee358b2baea3efd88ed678",
            "ast_sha256": "59cb5788ba3016db53024bdca0e38bbbc62d7d0c87254f09e8d35a9f5381264b",
            "sites": (
                (("body", 30, "body", 5, "test", "values", 4, "comparators", 0),
                 "int", 448, "0o700"),
            ),
        },
    },
    "integrations/mastermind_executive_app/direct_native.py": {
        "dispatch_direct_correction": {
            "node_type": "AsyncFunctionDef",
            "source_sha256": "f1b433eaeeb7e80743aefbf7e956d579033ba4cb743227952f26030c065969e0",
            "ast_sha256": "0d6eb1e9a0840886322d27ba599bc556ec650851c09227f5883fd905032e1bc4",
            "sites": (
                (("body", 6, "body", 0, "value", "keywords", 0, "value", "orelse"),
                 "int", 503, "503"),
            ),
        },
    },
}
