"""Static pins for existing Company modes and the fixed Fabric HTTP statuses.

Reviewed source: 53dd88f444c37e0cfec18b511a54a332addca1a9.
The listener source was independently reviewed before this static guard repair.
The original three exact 0710 Constants remain acknowledged. The 2026-11-03
catalog composition adds three exact HTTP response Constants in the existing
ingress method. Each method's full AST, owning class, literal values and spelling
remain pinned; all other identity tokens stay visible to the generic D8 guard.
No runtime authority is added.

2026-11-09 T3 attempt-fleet read pin move (t3/fleet-attempt-read-route): the
per-attempt frame admission adds one import and one elif branch inside the
existing ingress method. The same three reviewed ingress denial operands are
byte-identical; their AST site paths shift at one index (body 59 to
60) and the method/whole-file digests move with the postimage. The
Company-consultation method and its permission-mode literals are untouched.
"""

REVIEWED_PATH = "control_plane/executive_service.py"
REVIEWED_CONTAINER = "ExecutiveControlService"
REVIEWED_LITERAL_COUNT = 6
REVIEWED_ANCHORS = {'_bind_company_consultation_server': {'node_type': 'AsyncFunctionDef',
                                       'ast_sha256': '01c585ea0efc7e2ba1a09f68ceac6962a74d72e572c10343af4dcf1fdf930236',
                                       'sites': ((('body',
                                                   7,
                                                   'body',
                                                   2,
                                                   'value',
                                                   'keywords',
                                                   0,
                                                   'value'),
                                                  'int',
                                                  456,
                                                  '0o710'),
                                                 (('body',
                                                   7,
                                                   'body',
                                                   5,
                                                   'body',
                                                   1,
                                                   'value',
                                                   'args',
                                                   0),
                                                  'int',
                                                  456,
                                                  '0o710'),
                                                 (('body',
                                                   7,
                                                   'body',
                                                   6,
                                                   'test',
                                                   'values',
                                                   1,
                                                   'comparators',
                                                   0),
                                                  'int',
                                                  456,
                                                  '0o710'))},
 '_handle_ceo_ingress_connection': {'node_type': 'AsyncFunctionDef',
                                    'source_sha256': 'af0a97de9bfc503db756626d0eacf65876848473cfb2230d8fbe478c9bb5c1cc',
                                    'ast_sha256': '8ba83fc94d6ccbfe11eec5ed1b477a28e0ec92bd199f34c4123eb5be6803d912',
                                    'sites': ((('body',
                                                3,
                                                'body',
                                                60,
                                                'body',
                                                3,
                                                'orelse',
                                                0,
                                                'body',
                                                2,
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
                                                60,
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
                                                60,
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
                                               '503'))}}

# BYOK fixed READ changes the full ingress AST, with existing App/Runtime fences.
# The same three original Fabric HTTP operands are retained at mapped exact sites.
# Parent checked this postimage under the Chairman waiver; no independent approval claim.
# Protected #695 backup composition changes the full source only; the BYOK ingress AST and exact status sites are unchanged.

# Parent reviewed the BYOK + protected Workspace composition at 49c2e1d.
# The exact 136-node Fabric response branch and original three operands are unchanged.

# 2026-11-06 composed-source audit: qualified project execution/planning and
# bounded project conversation/Fresh READ coexist with protected BYOK and host
# observation. The whole Company listener AST and exact 136-node protected
# Fabric response branch are unchanged; only the enclosing ingress composition
# and mapped sites change. These fixed pins are a new source-drift qualification,
# not inherited native SEND approval or installation/release authority.

# Parent C17 dispatch composition retains the protected821 ingress AST and exact operands.

# Authenticated Agent OS context adds one 47-line read branch after the existing
# catalog branch. Removing that exact insertion reproduces the previous source
# bytes; the Company method, all three catalog operands and their AST paths are
# unchanged. The new whole-source/method pins qualify that bounded composition.

# Current-context composition extends that same App-peer branch with an
# independently authenticated Workspace projection and the original canonical
# DATA binding. Parent inspected the bounded diff and checked the complete
# Company method plus each original Fabric operand/path against protected
# source. Only whole-source/enclosing-method pins change; no new literal site
# or scanner exemption is added. This is source review, not host acceptance.
# H5 joins protected779fc3be: exact Company listener and Fabric response subtree
# remain AST-identical; only the composed full-source and ingress pins change.

# H6 joins current552 and H5 at exact source. The complete original Fabric
# response subtree and Company listener AST are unchanged; only enclosing
# source/method identity and mapped positions are requalified.
# Discovery correction extends the original authenticated App-peer branch.
# The Company method and all three Fabric error operands, including their
# complete AST paths and token spans, remain unchanged. Only the exact whole
# source and enclosing ingress-method digests change for this composition.

# 2026-11-09 MMOS composition pin move: the integration branch (capacity
# fabric frame branch + WO-13 selected_child_admit action, composed via
# commits merged under feat/mmos-v1-integration) extends the ingress method
# before the catalog branch. The three reviewed Fabric response operands,
# their reasons and their complete AST shape below the catalog block are
# unchanged; only the enclosing whole-source and ingress-method digests and
# the mapped statement index (body 58 -> 59) move. No new literal site is
# qualified.
