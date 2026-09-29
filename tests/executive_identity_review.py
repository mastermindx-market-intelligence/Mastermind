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

REVIEWED_PATH = "control_plane/executive_installed_peer.py"
REVIEWED_LITERAL_COUNT = 33
REVIEWED_ANCHORS = {'_LAUNCHD_ROLES': {'node_type': 'Assign',
                    'ast_sha256': 'd39da759d56fc748cf8a26ea18323d56542f0ac1fd2f7a30f321a37a3b6a93f0',
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
                      'ast_sha256': 'd724eeb306ba8fb27449c3e4268a29edc55920d936cc163e400dcf7e398d5de3',
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
                        'ast_sha256': 'c1ee469b6a858ed6dde6fbff737c895641532d835c4b7db0e0de89cf06761254',
                        'sites': ((('body', 4, 'value', 'keywords', 2, 'value'), 'int', 420, '0o644'),)},
 '_verify_control_projection': {'node_type': 'FunctionDef',
                                'ast_sha256': '0fa6d3cab2505182be5702325f19434989c8df1603c6d9ec88dce26fb273d69e',
                                'sites': ((('body', 2, 'value', 'keywords', 3, 'value'), 'int', 450, '450'),
                                          (('body', 5, 'test', 'comparators', 0), 'int', 450, '450'))},
 '_verify_role_config': {'node_type': 'FunctionDef',
                         'ast_sha256': '7bf72f6613d54840245aa682e5097bd0bc73e83ae88b1df42d3b39b7b97d805c',
                         'sites': ((('body', 3, 'body', 1, 'test', 'comparators', 0), 'int', 450, '450'),
                                   (('body', 3, 'orelse', 1, 'test', 'comparators', 0), 'int', 458, '458'))},
 '_inventory_python_base': {'node_type': 'FunctionDef',
                            'ast_sha256': '302a0806ca41a7ff3a8042330a9200a887a86a04c516f3a7fecbdc702861a135',
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
                            'ast_sha256': '07a6dd1b1b1a20e7718dd4dfaf2001130f11ce24c54c4f5741c099de23fd7eb9',
                            'sites': ((('body', 3, 'body', 0, 'value', 'keywords', 2, 'value'),
                                       'int',
                                       493,
                                       '0o755'),)},
 '_recheck_python_runtime': {'node_type': 'FunctionDef',
                             'ast_sha256': '75b75f2b561df45a58e276351c0fe334d5e4743cd3dcdedcf2a3fbd46ec172da',
                             'sites': ((('body', 3, 'body', 0, 'value', 'keywords', 2, 'value'),
                                        'int',
                                        493,
                                        '0o755'),)}}


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
    if path != REVIEWED_PATH or type(source) is not str:
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
    for name, expected in REVIEWED_ANCHORS.items():
        candidates = anchors.get(name, ())
        if len(candidates) != 1:
            continue
        node = candidates[0]
        if type(node).__name__ != expected["node_type"]:
            continue
        if not all(line.isascii() for line in lines[node.lineno - 1:node.end_lineno]):
            continue
        digest = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
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
