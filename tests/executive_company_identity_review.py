"""Static review pins for the Company listener's existing parent-directory mode.

Reviewed source: 53dd88f444c37e0cfec18b511a54a332addca1a9.
The listener source was independently reviewed before this static guard repair.
Only the three exact 0710 Constants are acknowledged. The method's full AST,
owning class, literal values and spelling remain pinned; all other identity
tokens stay visible to the generic D8 guard. No runtime authority is added.
"""

REVIEWED_PATH = "control_plane/executive_service.py"
REVIEWED_CONTAINER = "ExecutiveControlService"
REVIEWED_LITERAL_COUNT = 3
REVIEWED_ANCHORS = {
    "_bind_company_consultation_server": {
        "node_type": "AsyncFunctionDef",
        "ast_sha256": "01c585ea0efc7e2ba1a09f68ceac6962a74d72e572c10343af4dcf1fdf930236",
        "sites": (
            (("body", 7, "body", 2, "value", "keywords", 0, "value"), "int", 456, "0o710"),
            (("body", 7, "body", 5, "body", 1, "value", "args", 0), "int", 456, "0o710"),
            (("body", 7, "body", 6, "test", "values", 1, "comparators", 0), "int", 456, "0o710"),
        ),
    },
}
