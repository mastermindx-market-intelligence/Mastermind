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
             'ast_sha256': 'c231d737b4f5f9be13d48364a9762108ae9f0d8ad3a01313af534acbd00cedc4',
             'sites': ((('body',
                         6,
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
               'ast_sha256': '64c54eeb8ff5bcea770411652100afdc84e5d3bf31736f2d0e352af2734981c2',
               'sites': ((('body', 3, 'iter', 'elts', 3, 'elts', 4),
                          'int',
                          450,
                          '450'),
                         (('body', 23, 'test', 'values', 2, 'comparators', 0),
                          'int',
                          450,
                          '450'))}}
