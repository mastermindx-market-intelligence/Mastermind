"""Static pins for existing Company modes and the fixed Fabric HTTP statuses.

Reviewed source: 53dd88f444c37e0cfec18b511a54a332addca1a9.
The listener source was independently reviewed before this static guard repair.
The original three exact 0710 Constants remain acknowledged. The 2026-11-03
catalog composition adds three exact HTTP response Constants in the existing
ingress method. Each method's full AST, owning class, literal values and spelling
remain pinned; all other identity tokens stay visible to the generic D8 guard.
No runtime authority is added.
"""

REVIEWED_PATH = "control_plane/executive_service.py"
REVIEWED_CONTAINER = "ExecutiveControlService"
REVIEWED_LITERAL_COUNT = 6
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
    # Exact catalog/native-status composition. These are only the second
    # operands of workspace_error("access_denied", 403) and
    # workspace_error("source_unavailable", 503), never UIDs or grants.
    # The complete ingress-method AST binds its admission, source selection
    # and release-time permission checks; a change to any of them invalidates
    # all three status sites without changing the historical Company record.
    "_handle_ceo_ingress_connection": {
        "node_type": "AsyncFunctionDef",
        # Existing section-sign/em-dash prose needs an exact full-source pin
        # in addition to the method AST; all three literal lines are ASCII.
        # Qualified Knowledge/Archive READ additions change the enclosing ingress AST.
        # The original CCR branch and listener remain structurally unchanged.
        "source_sha256": 'b82f61a07a8191e5935fbf64dab5cdb1d1238eae309812fa41fbf59f6d04c2aa',
        "ast_sha256": '83aef0bdc6356c12bab0fcce640c7d0a7dcbd91a313a3f99d7ad6d0e1da0997a',
        "sites": ((('body', 3, 'body', 48, 'body', 3, 'orelse', 0, 'body', 2, 'body', 0, 'value', 'args', 1),
  'int',
  403,
  '403'),
 (('body',
   3,
   'body',
   48,
   'body',
   3,
   'orelse',
   0,
   'body',
   2,
   'orelse',
   0,
   'body',
   4,
   'body',
   0,
   'value',
   'args',
   1),
  'int',
  403,
  '403'),
 (('body',
   3,
   'body',
   48,
   'body',
   3,
   'orelse',
   0,
   'body',
   2,
   'orelse',
   0,
   'handlers',
   0,
   'body',
   0,
   'value',
   'args',
   1),
  'int',
  503,
  '503')),
    },
}

# BYOK fixed READ changes the full ingress AST, with existing App/Runtime fences.
# The same three original Fabric HTTP operands are retained at mapped exact sites.
# Parent checked this postimage under the Chairman waiver; no independent approval claim.
# Protected #695 backup composition changes the full source only; the BYOK ingress AST and exact status sites are unchanged.

# Parent reviewed the BYOK + protected Workspace composition at 49c2e1d.
# The exact 136-node Fabric response branch and original three operands are unchanged.
