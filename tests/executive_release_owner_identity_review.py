"""Static release-owner resident-input literal pins submitted for review.

The three occurrences are the already installed Control UID 450.  They bind
the supplied issuer receipt and installed Control configuration to that exact
principal; they do not add an account, socket, authority, or runtime identity.
Full owning ASTs and literal tokens are pinned.  Any context drift removes the
exception and returns the literals to the generic D8 scanner.

Resident source SHA256:
4c8620b387f6b027100eeb9ad4fd039e147003827f2e6eb990f2a9370deb44b4.
Independent source review report SHA256:
0bb26cc14ca225319e4a6b6658e56b2260a6337f029150e2d78868327d6dc001.
"""

REVIEWED_PATH = "ops/executive_os/release_owner_resident_inputs.py"
REVIEWED_LITERAL_COUNT = 3
REVIEWED_ANCHORS = {
    "validate_issuer_binding_receipt": {
        "node_type": "FunctionDef",
        "ast_sha256": "8f769065e7b55f0f0b48a3a379afb29afbeceb858c8c0979badf79613f9af102",
        "sites": (
            (("args", "kw_defaults", 6), "int", 450, "450"),
            (("body", 11, "test", "values", 0, "comparators", 0), "int", 450, "450"),
        ),
    },
    "compile_installed_evidence": {
        "node_type": "FunctionDef",
        "ast_sha256": "cf2f1232d0019151af181eaa0ee4cac216680e11b3d96fa648213edd323b89ec",
        "sites": (
            (("body", 13, "test", "values", 3, "comparators", 0), "int", 450, "450"),
        ),
    },
}
