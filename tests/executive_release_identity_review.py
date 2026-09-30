"""Static #1075 root-factory literal pins submitted for independent review.

Existing Control UID/group450 and POSIX512-byte st_blocks units only. No
account, principal, socket topology, realm or authority is added. Full owning
ASTs and literal tokens are pinned; any context drift removes the exception.
The generic D8 scanner and its mutation controls remain authoritative.
These candidate pins require exact-source independent review before merge.
"""
REVIEWED_PATH = 'control_plane/executive_release_factory.py'
REVIEWED_LITERAL_COUNT = 3
REVIEWED_ANCHORS = {'_Reader': {'node_type': 'ClassDef',
             'ast_sha256': '59aa65b283ed49dec83ca29867fee3439b766c826031ca4951aa302012ac626f',
             'sites': ((('body',
                         5,
                         'body',
                         5,
                         'body',
                         19,
                         'orelse',
                         1,
                         'test',
                         'values',
                         3,
                         'left',
                         'right'),
                        'int',
                        512,
                        '512'),)},
 '_resident': {'node_type': 'FunctionDef',
               'ast_sha256': 'd8648e9088618d888b05482c7c68ac98c5828fd7884a2791bc88744b566a99ab',
               'sites': ((('body', 3, 'iter', 'elts', 3, 'elts', 4), 'int', 450, '450'),
                         (('body', 23, 'test', 'values', 2, 'comparators', 0), 'int', 450, '450'))}}
