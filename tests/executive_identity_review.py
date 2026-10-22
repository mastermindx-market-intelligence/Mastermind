"""Test-only, source-review-bound literals for the existing installed topology.

Accepted preimage: 5544887bdb3de349eba97910f3d1047c21cc52b0.
Factory SHA256: 2b9c4402a44907c829f8a4ae099fac7c938dd3658325784e1b1d2a748e0cf513.
Independent review: cfd5a5f1909b56f00240a370890f0df0adaceab2f98fada30bc43df47febccaa.
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
from tests.executive_fabric_release_identity_review import REVIEWED_FILES
from tests.executive_incident_identity_review import REVIEWED_FILES as INCIDENT_REVIEWED_FILES

REVIEWED_PATH = "control_plane/executive_installed_peer.py"
REVIEWED_LITERAL_COUNT = 33

# Source-only, fixed-mode review. These are directory chmod/inspection modes,
# not user/group IDs or process identities. Original installed bytes remain
# immutable; any changed source digest or site exposes every literal to D8.
REVIEWED_PRIVATE_MODE_SOURCES = {'integrations/session_bridge/artifact_manifest_framing/artifact_production.base.py': {'anchors': ('            '
                                                                                                   'os.mkdir(self.name, '
                                                                                                   '0o700, '
                                                                                                   'dir_fd=self.tmp)',
                                                                                                   '                    '
                                                                                                   'or s.st_uid != '
                                                                                                   'os.getuid() or '
                                                                                                   'stat.S_IMODE(s.st_mode) '
                                                                                                   '!= 0o700):',
                                                                                                   '                or '
                                                                                                   'current.st_uid != '
                                                                                                   'os.getuid() or '
                                                                                                   'stat.S_IMODE(current.st_mode) '
                                                                                                   '!= 0o700):'),
                                                                                       'sha256': 'c0f17c3e489c83bdb369d6c1ea9adc2757f4732f515cbc76e230fe154a61f67e'},
 'integrations/session_bridge/artifact_manifest_framing/artifact_production.py': {'anchors': ('            '
                                                                                              'os.mkdir(self.name, '
                                                                                              '0o700, dir_fd=self.tmp)',
                                                                                              '                    or '
                                                                                              's.st_uid != os.getuid() '
                                                                                              'or '
                                                                                              'stat.S_IMODE(s.st_mode) '
                                                                                              '!= 0o700):',
                                                                                              '                or '
                                                                                              'current.st_uid != '
                                                                                              'os.getuid() or '
                                                                                              'stat.S_IMODE(current.st_mode) '
                                                                                              '!= 0o700):'),
                                                                                  'sha256': 'e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf'},
 'integrations/session_bridge/artifact_tool_framing/artifact_production.base.py': {'anchors': ('            '
                                                                                               'os.mkdir(self.name, '
                                                                                               '0o700, '
                                                                                               'dir_fd=self.tmp)',
                                                                                               '                    or '
                                                                                               's.st_uid != '
                                                                                               'os.getuid() or '
                                                                                               'stat.S_IMODE(s.st_mode) '
                                                                                               '!= 0o700):',
                                                                                               '                or '
                                                                                               'current.st_uid != '
                                                                                               'os.getuid() or '
                                                                                               'stat.S_IMODE(current.st_mode) '
                                                                                               '!= 0o700):'),
                                                                                   'sha256': 'e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf'},
 'integrations/session_bridge/artifact_tool_framing/artifact_production.py': {'anchors': ('            '
                                                                                          'os.mkdir(self.name, 0o700, '
                                                                                          'dir_fd=self.tmp)',
                                                                                          '                    or '
                                                                                          's.st_uid != os.getuid() or '
                                                                                          'stat.S_IMODE(s.st_mode) != '
                                                                                          '0o700):',
                                                                                          '                or '
                                                                                          'current.st_uid != '
                                                                                          'os.getuid() or '
                                                                                          'stat.S_IMODE(current.st_mode) '
                                                                                          '!= 0o700):'),
                                                                              'sha256': '0be15bd5d3304a65673576fd30386bcc977c02ed8ee28313a4cb1ed454f8c409'},
 'integrations/session_bridge/bound_launch_capture/lane_runtime.py.patch': {'anchors': ('+_OWNED_CAPTURE_DIR_MODE = '
                                                                                        '0o700',),
                                                                            'sha256': '664002d7309779e69cd5f1b3e6a260215f1247526c813824e7e8f5897c8457be'},
 'integrations/session_bridge/prospective_completion/candidate/original_delivery_collector.py': {'anchors': ('        '
                                                                                                             'if (not '
                                                                                                             'stat.S_ISDIR(b.st_mode) '
                                                                                                             'or '
                                                                                                             'a.st_uid '
                                                                                                             '!= '
                                                                                                             'os.getuid() '
                                                                                                             'or '
                                                                                                             'stat.S_IMODE(a.st_mode) '
                                                                                                             '!= 0o700',
                                                                                                             '    '
                                                                                                             'path=completion_path(run);os.mkdir(path,0o700)'),
                                                                                                 'sha256': '30cce4abf8b50473906506452dd70f84cf001f5f4a030dd0c6751df108c2df15'},
 'integrations/session_bridge/prospective_completion/prospective-completion.patch': {'anchors': ('+        if (not '
                                                                                                 'stat.S_ISDIR(b.st_mode) '
                                                                                                 'or a.st_uid != '
                                                                                                 'os.getuid() or '
                                                                                                 'stat.S_IMODE(a.st_mode) '
                                                                                                 '!= 0o700',
                                                                                                 '+    '
                                                                                                 'path=completion_path(run);os.mkdir(path,0o700)'),
                                                                                     'sha256': 'cc2b765a8b3907474a321ffc93986050a2018dfbe1542d2abffdad05f85d1918'}}

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
                         'ast_sha256': '67aa53157af3c6764bf86409cb7801024600cb9f2e973360d8ea5d8b1a2797a0',
                         'sites': ((('body', 3, 'body', 1, 'test', 'comparators', 0), 'int', 450, '450'),
                                   (('body', 3, 'orelse', 1, 'test', 'comparators', 0), 'int', 458, '458'))},
 '_inventory_python_base': {'node_type': 'FunctionDef',
                            'ast_sha256': 'fa4c9c3d13b53e71660a28e26ffd76824c2dd0574a98426cac4676d4a714f3d8',
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
    file_review = REVIEWED_FILES.get(path) or INCIDENT_REVIEWED_FILES.get(path)
    if file_review is not None:
        if hashlib.sha256(source.encode()).hexdigest() != file_review['sha256']:
            return ()
        lines = source.splitlines()
        spans = []
        for line, start, end, kind, spelling in file_review['sites']:
            if (not 1 <= line <= len(lines) or not lines[line-1].isascii()
                    or lines[line-1][start:end] != spelling):
                return ()
            spans.append((line, start, end, kind))
        return tuple(sorted(spans))
    modes = REVIEWED_PRIVATE_MODE_SOURCES.get(path)
    if modes is not None:
        if hashlib.sha256(source.encode()).hexdigest() != modes["sha256"]:
            return ()
        lines = source.splitlines()
        spans = []
        for anchor in modes["anchors"]:
            sites = [i for i, line in enumerate(lines, 1) if line == anchor]
            if len(sites) != 1 or anchor.count("0o700") != 1:
                return ()
            start = anchor.index("0o700")
            spans.append((sites[0], start, start + len("0o700"), "int"))
        return tuple(sorted(spans))
    # Independent scoped review of the fixed ten-minute telemetry age, not a UID.
    # The complete production patch is pinned; a changed or duplicated site is
    # fully visible to D8 again. Never derive this digest from current source.
    if path == "integrations/session_bridge/glm_host_account_pairing/glm-host-account-pairing.patch":
        expected = "55fdbca61880b8834dd33cd22a9263927c8dc36735dfde4d069461ab78dd9b66"
        anchor = "+DEFAULT_MAX_AGE = 600"
        if hashlib.sha256(source.encode()).hexdigest() != expected:
            return ()
        lines = source.splitlines()
        sites = [i for i, line in enumerate(lines, 1) if line == anchor]
        if len(sites) != 1:
            return ()
        start = anchor.index("600")
        return ((sites[0], start, start + 3, "int"),)
    reviewed_container = None
    if path == REVIEWED_PATH:
        reviewed_anchors = REVIEWED_ANCHORS
    elif path == "integrations/research_read_mcp/release_identity.py":
        from tests.research_read_archive_identity_review import (
            REVIEWED_ANCHORS as archive_path_anchors,
        )
        reviewed_anchors = archive_path_anchors
    elif path == "control_plane/executive_service.py":
        from tests.executive_company_identity_review import (
            REVIEWED_ANCHORS as company_anchors, REVIEWED_CONTAINER,
        )
        reviewed_anchors = company_anchors
        reviewed_container = REVIEWED_CONTAINER
    elif path == "control_plane/executive_release_factory.py":
        from tests.executive_release_identity_review import REVIEWED_ANCHORS as release_anchors
        reviewed_anchors = release_anchors
    elif path == "ops/executive_os/release_owner_resident_inputs.py":
        from tests.executive_release_owner_identity_review import (
            REVIEWED_ANCHORS as release_owner_anchors,
        )
        reviewed_anchors = release_owner_anchors
    elif path == "control_plane/executive_release_observation.py":
        from tests.executive_release_observation_identity_review import (
            REVIEWED_ANCHORS as release_observation_anchors,
        )
        reviewed_anchors = release_observation_anchors
    elif path == "ops/executive_os/a2_agent_relay_enrollment.py":
        from tests.executive_a2_identity_review import REVIEWED_ANCHORS as a2_anchors
        reviewed_anchors = a2_anchors
    elif path == "control_plane/finite_initial_registration.py":
        from tests.test_finite_initial_identity_review import REVIEWED_ANCHORS_BY_PATH
        reviewed_anchors = REVIEWED_ANCHORS_BY_PATH[path]
    elif path in {"ops/executive_os/attended_control_staging.py", "control_plane/fabric_attended_registration.py"}:
        from tests.executive_finite_identity_review import REVIEWED_ANCHORS_BY_PATH
        reviewed_anchors = REVIEWED_ANCHORS_BY_PATH[path]
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
    nodes = tree.body
    if reviewed_container is not None:
        containers = [node for node in nodes if _anchor_name(node) == reviewed_container]
        if len(containers) != 1 or not isinstance(containers[0], ast.ClassDef):
            return ()
        nodes = containers[0].body
    anchors = {}
    for node in nodes:
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
