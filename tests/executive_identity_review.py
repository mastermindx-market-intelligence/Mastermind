"""Test-only, source-review-bound literals for the existing installed topology.

Accepted preimage: 6f42a0db7fcb35b39dc6cd666945c552f6791720.
Factory SHA256: 6e38fa8c82bdc2457e8e13e34e97806da4d4f283c7b2dd381c3ebc40ce0fe3fb.
Independent review: 30f715b2e7bb81f549e20fff5d74eb6514ab35262b7993a7a7771fc31d96d15a.
These STATIC pins acknowledge existing accounts, UIDs, socket groups/modes,
permission modes and the 512 MiB inventory bound, not new runtime authority.
A source change requires review; tests never learn replacement pins from source.
Only exact reviewed Constant tokens are suppressed; identifiers and alias/call
structure remain visible to the generic D8 scanner.
"""
from __future__ import annotations

import ast
import hashlib
import inspect

REVIEWED_PATH = "control_plane/executive_installed_peer.py"
REVIEWED_LITERAL_COUNT = 33
REVIEWED_ANCHORS = {'_LAUNCHD_ROLES': {'node_type': 'Assign',
                    'ast_sha256': 'caa7c22754197370bf93733aec4cbcb1bc12ee23ef8cc30898be5327cfe8e49c',
                    'sites': ((('value', 'values', 0, 'keywords', 3, 'value'),
                               'str',
                               '_mastermind_exec',
                               '"_mastermind_exec"'),
                              (('value', 'values', 0, 'keywords', 4, 'value'),
                               'str',
                               '_mastermind_exec',
                               '"_mastermind_exec"'),
                              (('value', 'values', 1, 'keywords', 3, 'value'),
                               'str',
                               '_mastermind_executive_mcp',
                               '"_mastermind_executive_mcp"'),
                              (('value', 'values', 1, 'keywords', 4, 'value'),
                               'str',
                               '_mastermind_executive_mcp',
                               '"_mastermind_executive_mcp"'))},
 '_ROLE_TOPOLOGIES': {'node_type': 'Assign',
                      'ast_sha256': 'db8c0d3a78c34ed573cc43ecfd2e28fe02218611db9078902f853547d8a89634',
                      'sites': ((('value', 'values', 0, 'keywords', 1, 'value'), 'int', 450, '450'),
                                (('value', 'values', 0, 'keywords', 2, 'value'),
                                 'str',
                                 '_mastermind_exec',
                                 '"_mastermind_exec"'),
                                (('value', 'values', 0, 'keywords', 3, 'value'),
                                 'str',
                                 '_mastermind_exec',
                                 '"_mastermind_exec"'),
                                (('value', 'values', 0, 'keywords', 5, 'value'), 'int', 450, '450'),
                                (('value', 'values', 1, 'keywords', 1, 'value'), 'int', 458, '458'),
                                (('value', 'values', 1, 'keywords', 2, 'value'),
                                 'str',
                                 '_mastermind_executive_mcp',
                                 '"_mastermind_executive_mcp"'),
                                (('value', 'values', 1, 'keywords', 3, 'value'),
                                 'str',
                                 '_mastermind_executive_mcp',
                                 '"_mastermind_executive_mcp"'),
                                (('value', 'values', 1, 'keywords', 6, 'value'), 'int', 420, '0o644'))},
 '_CONTROL_SOCKETS': {'node_type': 'Assign',
                      'ast_sha256': 'fa97adba5165438e10aaf5794d046f62e600af06cf4fc01a45ee4a299cac733a',
                      'sites': ((('value', 'values', 0, 'values', 1), 'int', 452, '452'),
                                (('value', 'values', 0, 'values', 2), 'int', 432, '432'),
                                (('value', 'values', 0, 'values', 4), 'int', 450, '450'),
                                (('value', 'values', 1, 'values', 1), 'int', 457, '457'),
                                (('value', 'values', 1, 'values', 2), 'int', 432, '432'),
                                (('value', 'values', 1, 'values', 4), 'int', 450, '450'),
                                (('value', 'values', 2, 'values', 1), 'int', 453, '453'),
                                (('value', 'values', 2, 'values', 2), 'int', 432, '432'),
                                (('value', 'values', 2, 'values', 4), 'int', 450, '450'))},
 '_EXPECTED_PLIST_PROFILES': {'node_type': 'Assign',
                              'ast_sha256': 'e41cd5c4c0f544b374adaa6e342bc90e97f5657c09b0c6765aa1ff6f24a9ea43',
                              'sites': ((('value', 'values', 0, 'values', 3),
                                         'str',
                                         '_mastermind_exec',
                                         '"_mastermind_exec"'),
                                        (('value', 'values', 0, 'values', 15),
                                         'str',
                                         '_mastermind_exec',
                                         '"_mastermind_exec"'),
                                        (('value', 'values', 1, 'values', 1),
                                         'str',
                                         '_mastermind_executive_mcp',
                                         '"_mastermind_executive_mcp"'),
                                        (('value', 'values', 1, 'values', 11),
                                         'str',
                                         '_mastermind_executive_mcp',
                                         '"_mastermind_executive_mcp"'))},
 '_verify_role_plist': {'node_type': 'FunctionDef',
                        'ast_sha256': 'b6ae4e618fbd7a678ff7cc558882de291e9420c75661613f1b1d270fba4cebf3',
                        'sites': ((('body', 4, 'value', 'keywords', 2, 'value'), 'int', 420, '0o644'),)},
 '_verify_control_projection': {'node_type': 'FunctionDef',
                                'ast_sha256': '3a834919a6a967ef9bb612b9d57502cbe524b8052639b583cb703f0934310b52',
                                'sites': ((('body', 2, 'value', 'keywords', 3, 'value'), 'int', 450, '450'),
                                          (('body', 5, 'test', 'comparators', 0), 'int', 450, '450'))},
 '_verify_role_config': {'node_type': 'FunctionDef',
                         'ast_sha256': 'c46afa84416318a536109f713e764d00db497560cb2a7340898391613410e1e6',
                         'sites': ((('body', 3, 'body', 1, 'test', 'comparators', 0), 'int', 450, '450'),
                                   (('body', 3, 'orelse', 1, 'test', 'comparators', 0), 'int', 458, '458'))},
 '_inventory_python_base': {'node_type': 'FunctionDef',
                            'ast_sha256': '596652feb54da86955aedf19d7d4e313205963daaf3d0f2f272c2e0a5269a1b1',
                            'sites': ((('body',
                                        5,
                                        'body',
                                        5,
                                        'body',
                                        0,
                                        'orelse',
                                        0,
                                        'orelse',
                                        0,
                                        'body',
                                        2,
                                        'test',
                                        'comparators',
                                        0,
                                        'left',
                                        'left'),
                                       'int',
                                       512,
                                       '512'),)},
 '_verify_python_runtime': {'node_type': 'FunctionDef',
                            'ast_sha256': '0675122e35792a7b805fdaef8ebddeba9c55f528fa8b9eaf5d1d22d85e0d59a2',
                            'sites': ((('body', 3, 'body', 0, 'value', 'keywords', 2, 'value'),
                                       'int',
                                       493,
                                       '0o755'),)},
 '_recheck_python_runtime': {'node_type': 'FunctionDef',
                             'ast_sha256': '0ebe50cb8368f4e79e9fd9ce7fea0bfc86eba264a434a5958c52956174f2359b',
                             'sites': ((('body', 3, 'body', 0, 'value', 'keywords', 2, 'value'),
                                        'int',
                                        493,
                                        '0o755'),)}}


def _reviewed_ast_dump(node):
    """Pin full AST structure across Python 3.12 and 3.13+ dump defaults.

    Python 3.13 added show_empty and 3.14 omits empty list fields by default.
    Empty fields stay explicit in this review digest; no source is normalized
    away and the literal pins still come only from the frozen reviewed preimage.
    """
    options = {"include_attributes": False}
    if "show_empty" in inspect.signature(ast.dump).parameters:
        options["show_empty"] = True
    return ast.dump(node, **options)


def _anchor_name(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _relative_node(node, path):
    for step in path:
        node = node[step] if type(step) is int else getattr(node, step)
    return node


def reviewed_literal_spans(path: str, source: str):
    """Return qualified single-line literal spans, or no suppression on drift.

    AST columns are byte offsets. Qualifying only ASCII anchor lines makes them
    exact character offsets too, including any prefix or trailing statement.
    Duplicate anchors of another AST type remain duplicates, never aliases.
    """
    if type(source) is not str:
        return ()
    if path == REVIEWED_PATH:
        reviewed_anchors = REVIEWED_ANCHORS
    elif path == "control_plane/executive_release_factory.py":
        from tests.executive_release_identity_review import REVIEWED_ANCHORS as release_anchors
        reviewed_anchors = release_anchors
    else:
        return ()
    # str.splitlines recognizes these separators, while Python source/AST
    # coordinates do not. Never project across incompatible line models.
    if any(separator in source for separator in "\v\f\x1c\x1d\x1e\x85\u2028\u2029"):
        return ()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return ()
    lines = source.splitlines(keepends=True)
    anchors = {}
    for node in tree.body:
        name = _anchor_name(node)
        if name is not None:
            anchors.setdefault(name, []).append(node)
    spans = []
    for name, expected in reviewed_anchors.items():
        candidates = anchors.get(name, ())
        if len(candidates) != 1:
            continue
        node = candidates[0]
        if type(node).__name__ != expected["node_type"]:
            continue
        if not all(line.isascii() for line in lines[node.lineno - 1:node.end_lineno]):
            continue
        digest = hashlib.sha256(_reviewed_ast_dump(node).encode()).hexdigest()
        if digest != expected["ast_sha256"]:
            continue
        qualified = []
        for relative_path, value_type, value, spelling in expected["sites"]:
            try:
                literal = _relative_node(node, relative_path)
            except (AttributeError, IndexError, KeyError, TypeError):
                qualified = []
                break
            if (not isinstance(literal, ast.Constant)
                    or type(literal.value).__name__ != value_type or literal.value != value
                    or literal.lineno != literal.end_lineno
                    or ast.get_source_segment(source, literal) != spelling
                    or lines[literal.lineno - 1][literal.col_offset:literal.end_col_offset] != spelling):
                qualified = []
                break
            qualified.append((literal.lineno, literal.col_offset, literal.end_col_offset, value_type))
        if len(qualified) == len(expected["sites"]):
            spans.extend(qualified)
    return tuple(sorted(spans))


def mask_reviewed_identity_literals(path: str, source: str) -> str:
    """Neutralize only qualified literal tokens while retaining all other bytes."""
    lines = source.splitlines(keepends=True)
    for line, start, end, value_type in reversed(reviewed_literal_spans(path, source)):
        token = '""' if value_type == "str" else "0"
        replacement = token + " " * (end - start - len(token))
        lines[line - 1] = lines[line - 1][:start] + replacement + lines[line - 1][end:]
    return "".join(lines)
