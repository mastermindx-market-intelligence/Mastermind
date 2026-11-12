"""Bounded Paper Desktop client. No credentials, listener, queue or retry owner.

The CLI is dependency-free (Python 3.9+); the MCP projection uses the official SDK.
Paper itself owns documents. Executive/approved interactive clients own authorization.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any

VERSION = "0.1.8"
ENDPOINT = "http://127.0.0.1:29979/mcp"
MAX_BYTES = 16 * 1024 * 1024
MAX_REQUEST = 1 << 19
PRIVATE_DIR_MODE = 0o700
DESKTOP_LOCK_WAIT_SECONDS = 30.0
DESKTOP_LOCK_POLL_SECONDS = 0.05
SUPPORTED_SERVER = ("paper-desktop", None)
SUPPORTED_CATALOG_SHA256 = "1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db"
# Retain historic full-catalog hashes as provenance and as the private
# exact-pin test seam. Production admission now checks reviewed *individual*
# tool input contracts, rather than comparing the entire vendor catalog.
# The observed 0.5.18 41-tool catalog remains in the immutable test fixture;
# four new resource commands are still blocked by the tool-name allowlists.
PAPER_RICH_TEXT_CATALOG_SHA256 = "16e6b93f0c51a1574ba8acee4df732052898707a04731d3817530971a88fdefd"
# Paper Desktop 0.5.16 on M1 is a *distinct*, independently observed
# 37-tool full catalog. Exactly six existing descriptors differ from the
# 1b9aff baseline; no tool name was added or removed, and HTML is required.
# Source: tests/fixtures/paper_desktop/955e92_full_catalog.json.
PAPER_M1_RICH_TEXT_CATALOG_SHA256 = "955e92cd0477027dcc5fe666810e49393f42f453c1c362e64cd0f3b3ab9f10cf"
REVIEWED_CATALOG_SHA256_ALTERNATES = frozenset({
    "f3483e001d4f07f5a49144ca52a4f9e14ba046e35546dda05d6cd37c9d2b4728",
    PAPER_RICH_TEXT_CATALOG_SHA256,
    PAPER_M1_RICH_TEXT_CATALOG_SHA256,
})
READ_TOOLS = frozenset({
    "get_basic_info", "get_selection", "get_node_info", "get_children",
    "get_tree_summary", "get_screenshot", "get_jsx", "get_computed_styles",
    "get_fill_image", "get_font_family_info", "get_guide",
    "find_nodes", "get_tokens", "list_comment_threads", "get_comment_thread",
    "list_comment_thread_authors", "list_resources",
})
EDIT_TOOLS = frozenset({
    "create_artboard", "write_html", "set_text_content", "rename_nodes",
    "duplicate_nodes", "move_nodes", "update_styles", "finish_working_on_nodes",
    "create_page", "create_tokens", "set_tokens", "set_comment_thread_status",
    "arrange_pages", "update_pages",
})
FILE_MANAGE_TOOLS = frozenset({"create_file", "rename_resource"})

# Version-independent tool capability contract. Reviewed references come from
# accepted full catalogs or exact observed tool descriptors retained in fixtures.
# Admission tests each current tool *independently*. Presentation strings and
# unrelated vendor tools never disable a usable tool. The shapes and safety annotations
# remain source-reviewed. Do not turn this into a trust-all version fallback.
REVIEWED_TOOL_CONTRACTS = {'arrange_pages': [{'annotations': {'destructiveHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'},
                                                   'order': {'items': {'anyOf': [{'type': 'string'},
                                                                                 {'additionalProperties': False,
                                                                                  'properties': {'type': {'const': 'divider',
                                                                                                          'type': 'string'}},
                                                                                  'required': ['type'],
                                                                                  'type': 'object'}]},
                                                             'type': 'array'},
                                                   'removeDividerIds': {'items': {'type': 'string'},
                                                                        'type': 'array'}},
                                    'required': ['fileId', 'order'],
                                    'type': 'object'}}],
 'create_artboard': [{'annotations': {'destructiveHint': True},
                      'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                      'additionalProperties': False,
                                      'properties': {'fileId': {'type': 'string'},
                                                     'name': {'type': 'string'},
                                                     'pageId': {'type': 'string'},
                                                     'styles': {'additionalProperties': {'anyOf': [{'type': 'string'},
                                                                                                   {'type': 'number'}]},
                                                                'properties': {'height': {'type': 'string'},
                                                                               'width': {'type': 'string'}},
                                                                'required': ['height', 'width'],
                                                                'type': 'object'}},
                                      'required': ['fileId', 'name', 'styles'],
                                      'type': 'object'}}],
 'create_file': [{'annotations': {'destructiveHint': True},
                  'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                  'additionalProperties': False,
                                  'properties': {'cloneFileId': {'type': 'string'},
                                                 'name': {'type': 'string'},
                                                 'parentId': {'type': 'string'}},
                                  'type': 'object'}},
                 {'annotations': {'destructiveHint': True},
                  'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                  'additionalProperties': False,
                                  'properties': {'cloneFileId': {'type': 'string'},
                                                 'name': {'type': 'string'}},
                                  'type': 'object'}}],
 'create_page': [{'annotations': {'destructiveHint': True},
                  'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                  'additionalProperties': False,
                                  'properties': {'fileId': {'type': 'string'},
                                                 'icon': {'enum': ['arrow',
                                                                   'bar-chart',
                                                                   'blueprint',
                                                                   'check',
                                                                   'cross',
                                                                   'design',
                                                                   'images',
                                                                   'info',
                                                                   'line-chart',
                                                                   'padlock',
                                                                   'paper',
                                                                   'pie-chart',
                                                                   'presentation',
                                                                   'question',
                                                                   'swatches',
                                                                   'table',
                                                                   'vector'],
                                                          'type': 'string'},
                                                 'name': {'type': 'string'}},
                                  'required': ['fileId'],
                                  'type': 'object'}}],
 'create_tokens': [{'annotations': {'destructiveHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'},
                                                   'tokens': {'items': {'additionalProperties': False,
                                                                        'properties': {'description': {'maxLength': 1024,
                                                                                                       'type': 'string'},
                                                                                       'name': {'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                                                'type': 'string'},
                                                                                       'type': {'enum': ['breakpoint',
                                                                                                         'color',
                                                                                                         'container',
                                                                                                         'fontFamily',
                                                                                                         'fontSize',
                                                                                                         'fontWeight',
                                                                                                         'letterSpacing',
                                                                                                         'lineHeight',
                                                                                                         'opacity',
                                                                                                         'radius',
                                                                                                         'spacing'],
                                                                                                'type': 'string'},
                                                                                       'value': {'anyOf': [{'type': 'string'},
                                                                                                           {'type': 'number'}]}},
                                                                        'required': ['name',
                                                                                     'type',
                                                                                     'value'],
                                                                        'type': 'object'},
                                                              'minItems': 1,
                                                              'type': 'array'}},
                                    'required': ['fileId', 'tokens'],
                                    'type': 'object'}}],
 'duplicate_nodes': [{'annotations': {'destructiveHint': True},
                      'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                      'additionalProperties': False,
                                      'properties': {'fileId': {'type': 'string'},
                                                     'nodes': {'items': {'additionalProperties': False,
                                                                         'properties': {'id': {'type': 'string'},
                                                                                        'parentId': {'type': 'string'}},
                                                                         'required': ['id'],
                                                                         'type': 'object'},
                                                               'type': 'array'}},
                                      'required': ['fileId', 'nodes'],
                                      'type': 'object'}}],
 'find_nodes': [{'annotations': {'readOnlyHint': True},
                 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                 'additionalProperties': False,
                                 'properties': {'fileId': {'type': 'string'},
                                                'filters': {'items': {'additionalProperties': False,
                                                                      'properties': {'styleName': {'type': 'string'},
                                                                                     'styleValue': {'type': 'string'}},
                                                                      'type': 'object'},
                                                            'minItems': 1,
                                                            'type': 'array'},
                                                'nodeId': {'type': 'string'},
                                                'pageId': {'type': 'string'},
                                                'textValue': {'type': 'string'}},
                                 'required': ['fileId'],
                                 'type': 'object'}}],
 'finish_working_on_nodes': [{'annotations': {'readOnlyHint': True},
                              'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                              'additionalProperties': False,
                                              'properties': {'fileId': {'type': 'string'},
                                                             'nodeIds': {'items': {'type': 'string'},
                                                                         'type': 'array'}},
                                              'required': ['fileId'],
                                              'type': 'object'}}],
 'get_basic_info': [{'annotations': {'readOnlyHint': True},
                     'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                     'additionalProperties': False,
                                     'properties': {'fileId': {'type': 'string'},
                                                    'pageId': {'type': 'string'}},
                                     'type': 'object'}}],
 'get_children': [{'annotations': {'readOnlyHint': True},
                   'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                   'additionalProperties': False,
                                   'properties': {'fileId': {'type': 'string'},
                                                  'nodeId': {'type': 'string'}},
                                   'required': ['fileId', 'nodeId'],
                                   'type': 'object'}}],
 'get_comment_thread': [{'annotations': {'readOnlyHint': True},
                         'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                         'additionalProperties': False,
                                         'properties': {'commentThreadId': {'minLength': 1,
                                                                            'type': 'string'},
                                                        'fileId': {'type': 'string'}},
                                         'required': ['commentThreadId', 'fileId'],
                                         'type': 'object'}}],
 'get_computed_styles': [{'annotations': {'readOnlyHint': True},
                          'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                          'additionalProperties': False,
                                          'properties': {'fileId': {'type': 'string'},
                                                         'nodeIds': {'items': {'type': 'string'},
                                                                     'type': 'array'}},
                                          'required': ['fileId', 'nodeIds'],
                                          'type': 'object'}}],
 'get_fill_image': [{'annotations': {'readOnlyHint': True},
                     'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                     'additionalProperties': False,
                                     'properties': {'fileId': {'type': 'string'},
                                                    'nodeId': {'type': 'string'}},
                                     'required': ['fileId', 'nodeId'],
                                     'type': 'object'}}],
 'get_font_family_info': [{'annotations': {'readOnlyHint': True},
                           'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                           'additionalProperties': False,
                                           'properties': {'familyNames': {'items': {'type': 'string'},
                                                                          'type': 'array'},
                                                          'fileId': {'type': 'string'}},
                                           'required': ['familyNames', 'fileId'],
                                           'type': 'object'}}],
 'get_guide': [{'annotations': {'readOnlyHint': True},
                'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                'additionalProperties': False,
                                'properties': {'topic': {'type': 'string'}},
                                'required': ['topic'],
                                'type': 'object'}}],
 'get_jsx': [{'annotations': {'readOnlyHint': True},
              'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                              'additionalProperties': False,
                              'properties': {'fileId': {'type': 'string'},
                                             'format': {'enum': ['inline-styles', 'tailwind'],
                                                        'type': 'string'},
                                             'includeNodeIds': {'type': 'boolean'},
                                             'includeRootPositioning': {'type': 'boolean'},
                                             'nodeId': {'type': 'string'}},
                              'required': ['fileId', 'nodeId'],
                              'type': 'object'}}],
 'get_node_info': [{'annotations': {'readOnlyHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'},
                                                   'nodeId': {'type': 'string'}},
                                    'required': ['fileId', 'nodeId'],
                                    'type': 'object'}}],
 'get_screenshot': [{'annotations': {'readOnlyHint': True},
                     'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                     'additionalProperties': False,
                                     'properties': {'fileId': {'type': 'string'},
                                                    'nodeId': {'type': 'string'},
                                                    'scale': {'type': 'number'}},
                                     'required': ['fileId', 'nodeId'],
                                     'type': 'object'}}],
 'get_selection': [{'annotations': {'readOnlyHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'}},
                                    'type': 'object'}}],
 'get_tokens': [{'annotations': {'readOnlyHint': True},
                 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                 'additionalProperties': False,
                                 'properties': {'fileId': {'type': 'string'},
                                                'format': {'enum': ['css', 'json', 'tailwind'],
                                                           'type': 'string'},
                                                'namePattern': {'type': 'string'},
                                                'types': {'items': {'enum': ['breakpoint',
                                                                             'color',
                                                                             'container',
                                                                             'fontFamily',
                                                                             'fontSize',
                                                                             'fontWeight',
                                                                             'letterSpacing',
                                                                             'lineHeight',
                                                                             'opacity',
                                                                             'radius',
                                                                             'spacing'],
                                                                    'type': 'string'},
                                                          'type': 'array'}},
                                 'required': ['fileId'],
                                 'type': 'object'}}],
 'get_tree_summary': [{'annotations': {'readOnlyHint': True},
                       'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                       'additionalProperties': False,
                                       'properties': {'depth': {'type': 'number'},
                                                      'fileId': {'type': 'string'},
                                                      'nodeId': {'type': 'string'}},
                                       'required': ['fileId', 'nodeId'],
                                       'type': 'object'}}],
 'list_comment_thread_authors': [{'annotations': {'readOnlyHint': True},
                                  'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                                  'additionalProperties': False,
                                                  'properties': {'fileId': {'type': 'string'},
                                                                 'pageId': {'type': 'string'}},
                                                  'required': ['fileId'],
                                                  'type': 'object'}}],
 'list_comment_threads': [{'annotations': {'readOnlyHint': True},
                           'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                           'additionalProperties': False,
                                           'properties': {'currentPageOnly': {'type': 'boolean'},
                                                          'fileId': {'type': 'string'},
                                                          'limit': {'maximum': 200,
                                                                    'minimum': 1,
                                                                    'type': 'integer'},
                                                          'nodeId': {'type': 'string'},
                                                          'offset': {'maximum': 9007199254740991,
                                                                     'minimum': 0,
                                                                     'type': 'integer'},
                                                          'pageId': {'type': 'string'},
                                                          'participantUserId': {'type': 'string'},
                                                          'previewLength': {'maximum': 1000,
                                                                            'minimum': 20,
                                                                            'type': 'integer'},
                                                          'search': {'type': 'string'},
                                                          'searchScope': {'enum': ['all-messages',
                                                                                   'first-message'],
                                                                          'type': 'string'},
                                                          'sortDirection': {'enum': ['asc', 'desc'],
                                                                            'type': 'string'},
                                                          'sortField': {'enum': ['createdAt',
                                                                                 'page',
                                                                                 'updatedAt'],
                                                                        'type': 'string'},
                                                          'status': {'enum': ['all', 'open', 'resolved'],
                                                                     'type': 'string'},
                                                          'threadAuthorUserId': {'type': 'string'}},
                                           'required': ['fileId'],
                                           'type': 'object'}}],
 'list_resources': [{'annotations': {'readOnlyHint': True},
                     'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                     'additionalProperties': False,
                                     'properties': {'includeArchived': {'type': 'boolean'},
                                                    'limit': {'maximum': 200,
                                                              'minimum': 1,
                                                              'type': 'integer'},
                                                    'parentId': {'type': 'string'}},
                                     'type': 'object'}},
                    {'annotations': {'readOnlyHint': True},
                     'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                     'additionalProperties': False,
                                     'properties': {'limit': {'maximum': 200,
                                                              'minimum': 1,
                                                              'type': 'integer'}},
                                     'type': 'object'}}],
 'move_nodes': [{'annotations': {'destructiveHint': True},
                 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                 'additionalProperties': False,
                                 'properties': {'fileId': {'type': 'string'},
                                                'moves': {'items': {'anyOf': [{'additionalProperties': False,
                                                                               'properties': {'before': {'type': 'string'},
                                                                                              'nodeId': {'type': 'string'}},
                                                                               'required': ['before',
                                                                                            'nodeId'],
                                                                               'type': 'object'},
                                                                              {'additionalProperties': False,
                                                                               'properties': {'after': {'type': 'string'},
                                                                                              'nodeId': {'type': 'string'}},
                                                                               'required': ['after',
                                                                                            'nodeId'],
                                                                               'type': 'object'},
                                                                              {'additionalProperties': False,
                                                                               'properties': {'index': {'maximum': 9007199254740991,
                                                                                                        'minimum': 0,
                                                                                                        'type': 'integer'},
                                                                                              'nodeId': {'type': 'string'},
                                                                                              'parentId': {'type': 'string'}},
                                                                               'required': ['nodeId',
                                                                                            'parentId'],
                                                                               'type': 'object'}]},
                                                          'minItems': 1,
                                                          'type': 'array'}},
                                 'required': ['fileId', 'moves'],
                                 'type': 'object'}}],
 'rename_nodes': [{'annotations': {'destructiveHint': True},
                   'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                   'additionalProperties': False,
                                   'properties': {'fileId': {'type': 'string'},
                                                  'updates': {'items': {'additionalProperties': False,
                                                                        'properties': {'name': {'type': 'string'},
                                                                                       'nodeId': {'type': 'string'}},
                                                                        'required': ['name', 'nodeId'],
                                                                        'type': 'object'},
                                                              'type': 'array'}},
                                   'required': ['fileId', 'updates'],
                                   'type': 'object'}}],
 'rename_resource': [{'annotations': {'destructiveHint': True},
                      'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                      'additionalProperties': False,
                                      'properties': {'name': {'type': 'string'},
                                                     'resourceId': {'type': 'string'}},
                                      'required': ['name', 'resourceId'],
                                      'type': 'object'}}],
 'set_comment_thread_status': [{'annotations': {'destructiveHint': True},
                                'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                                'additionalProperties': False,
                                                'properties': {'commentThreadId': {'minLength': 1,
                                                                                   'type': 'string'},
                                                               'fileId': {'type': 'string'},
                                                               'status': {'enum': ['open', 'resolved'],
                                                                          'type': 'string'}},
                                                'required': ['commentThreadId', 'fileId', 'status'],
                                                'type': 'object'}}],
 'set_text_content': [{'annotations': {'destructiveHint': True},
                       'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                       'additionalProperties': False,
                                       'properties': {'fileId': {'type': 'string'},
                                                      'updates': {'items': {'additionalProperties': False,
                                                                            'properties': {'html': {'type': 'string'},
                                                                                           'nodeId': {'type': 'string'}},
                                                                            'required': ['html', 'nodeId'],
                                                                            'type': 'object'},
                                                                  'type': 'array'}},
                                       'required': ['fileId', 'updates'],
                                       'type': 'object'}},
                      {'annotations': {'destructiveHint': True},
                       'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                       'additionalProperties': False,
                                       'properties': {'fileId': {'type': 'string'},
                                                      'updates': {'items': {'additionalProperties': False,
                                                                            'properties': {'nodeId': {'type': 'string'},
                                                                                           'textContent': {'type': 'string'}},
                                                                            'required': ['nodeId',
                                                                                         'textContent'],
                                                                            'type': 'object'},
                                                                  'type': 'array'}},
                                       'required': ['fileId', 'updates'],
                                       'type': 'object'}}],
 'set_tokens': [{'annotations': {'destructiveHint': True},
                 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                 'additionalProperties': False,
                                 'properties': {'fileId': {'type': 'string'},
                                                'tokens': {'items': {'additionalProperties': False,
                                                                     'properties': {'delete': {'type': 'boolean'},
                                                                                    'description': {'maxLength': 1024,
                                                                                                    'type': 'string'},
                                                                                    'name': {'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                                             'type': 'string'},
                                                                                    'newName': {'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                                                'type': 'string'},
                                                                                    'value': {'anyOf': [{'type': 'string'},
                                                                                                        {'type': 'number'}]}},
                                                                     'required': ['name'],
                                                                     'type': 'object'},
                                                           'minItems': 1,
                                                           'type': 'array'}},
                                 'required': ['fileId', 'tokens'],
                                 'type': 'object'}}],
 'update_pages': [{'annotations': {'destructiveHint': True},
                   'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                   'additionalProperties': False,
                                   'properties': {'fileId': {'type': 'string'},
                                                  'updates': {'items': {'additionalProperties': False,
                                                                        'properties': {'icon': {'anyOf': [{'enum': ['arrow',
                                                                                                                    'bar-chart',
                                                                                                                    'blueprint',
                                                                                                                    'check',
                                                                                                                    'cross',
                                                                                                                    'design',
                                                                                                                    'images',
                                                                                                                    'info',
                                                                                                                    'line-chart',
                                                                                                                    'padlock',
                                                                                                                    'paper',
                                                                                                                    'pie-chart',
                                                                                                                    'presentation',
                                                                                                                    'question',
                                                                                                                    'swatches',
                                                                                                                    'table',
                                                                                                                    'vector'],
                                                                                                           'type': 'string'},
                                                                                                          {'type': 'null'}]},
                                                                                       'name': {'type': 'string'},
                                                                                       'pageId': {'type': 'string'}},
                                                                        'required': ['pageId'],
                                                                        'type': 'object'},
                                                              'type': 'array'}},
                                   'required': ['fileId', 'updates'],
                                   'type': 'object'}}],
 # The second style profile is the exact f200 tool-only descriptor fixture;
 # primitive-union equivalence is not generalized to other tools or schemas.
 'update_styles': [{'annotations': {'destructiveHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'},
                                                   'updates': {'items': {'additionalProperties': False,
                                                                         'properties': {'nodeIds': {'items': {'type': 'string'},
                                                                                                    'type': 'array'},
                                                                                        'styles': {'additionalProperties': {'anyOf': [{'type': 'string'},
                                                                                                                                      {'type': 'number'}]},
                                                                                                   'propertyNames': {'type': 'string'},
                                                                                                   'type': 'object'}},
                                                                         'required': ['nodeIds', 'styles'],
                                                                         'type': 'object'},
                                                               'type': 'array'}},
                                    'required': ['fileId', 'updates'],
                                    'type': 'object'}},
                   {'annotations': {'destructiveHint': True},
                    'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                    'additionalProperties': False,
                                    'properties': {'fileId': {'type': 'string'},
                                                   'updates': {'items': {'additionalProperties': False,
                                                                         'properties': {'nodeIds': {'items': {'type': 'string'},
                                                                                                    'type': 'array'},
                                                                                        'styles': {'additionalProperties': {'type': ['string', 'number']},
                                                                                                   'propertyNames': {'type': 'string'},
                                                                                                   'type': 'object'}},
                                                                         'required': ['nodeIds', 'styles'],
                                                                         'type': 'object'},
                                                               'type': 'array'}},
                                    'required': ['fileId', 'updates'],
                                    'type': 'object'}}],
 'write_html': [{'annotations': {'destructiveHint': True},
                 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                 'additionalProperties': False,
                                 'properties': {'fileId': {'type': 'string'},
                                                'html': {'type': 'string'},
                                                'mode': {'enum': ['insert-children', 'replace'],
                                                         'type': 'string'},
                                                'targetNodeId': {'type': 'string'}},
                                 'required': ['fileId', 'html', 'mode', 'targetNodeId'],
                                 'type': 'object'}}]}

# Exact f200 (Paper 0.5.18) descriptors retained in
# tests/fixtures/paper_desktop/f200eaf_artboard_token_descriptors.json. The native
# catalog spells string|number as a type array; this admits those exact shapes only.
# Primitive-union equivalence is not generalized to other tools or schemas.
REVIEWED_TOOL_CONTRACTS['create_artboard'].append(
{'annotations': {'destructiveHint': True},
 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                 'additionalProperties': False,
                 'properties': {'fileId': {'description': 'The file ID that the tool should '
                                                          'operate on.',
                                           'type': 'string'},
                                'name': {'description': 'Name for the artboard (shown in the layer '
                                                        'tree).',
                                         'type': 'string'},
                                'pageId': {'description': 'The page ID that the tool should '
                                                          'operate on. When omitted the active '
                                                          'page will be used. The active page can '
                                                          'change between tool calls, prefer '
                                                          'passing explicit page IDs.',
                                           'type': 'string'},
                                'styles': {'additionalProperties': {'type': ['string', 'number']},
                                           'description': 'CSS styles for the artboard as a JSON '
                                                          'object. Use camelCase property names.\n'
                                                          'width and height are required — use '
                                                          'whole pixel values.\n'
                                                          'When positioning an artboard make sure '
                                                          'to give 80px of space between artboards '
                                                          'to avoid overlaps.\n'
                                                          'Example: {"display": "flex", '
                                                          '"flexDirection": "column", "width": '
                                                          '"1440px", "height": "900px", '
                                                          '"backgroundColor": "#f5f5f5", '
                                                          '"padding": "20px"}',
                                           'properties': {'height': {'description': 'Height of the '
                                                                                    'artboard as a '
                                                                                    'whole pixel '
                                                                                    'value (e.g. '
                                                                                    '"900px").',
                                                                     'type': 'string'},
                                                          'width': {'description': 'Width of the '
                                                                                   'artboard as a '
                                                                                   'whole pixel '
                                                                                   'value (e.g. '
                                                                                   '"1440px").',
                                                                    'type': 'string'}},
                                           'required': ['width', 'height'],
                                           'type': 'object'}},
                 'required': ['name', 'styles', 'fileId'],
                 'type': 'object'}})
REVIEWED_TOOL_CONTRACTS['create_tokens'].append(
{'annotations': {'destructiveHint': True},
 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                 'additionalProperties': False,
                 'properties': {'fileId': {'description': 'The file ID that the tool should '
                                                          'operate on.',
                                           'type': 'string'},
                                'tokens': {'description': 'Design tokens to create. Each entry '
                                                          'creates a new design token; duplicate '
                                                          'names are allowed but discouraged.',
                                           'items': {'additionalProperties': False,
                                                     'properties': {'description': {'description': 'Optional '
                                                                                                   'human-readable '
                                                                                                   'description '
                                                                                                   'of '
                                                                                                   'what '
                                                                                                   'the '
                                                                                                   'design '
                                                                                                   'token '
                                                                                                   'is '
                                                                                                   'for '
                                                                                                   'and '
                                                                                                   'how '
                                                                                                   'it '
                                                                                                   'should '
                                                                                                   'be '
                                                                                                   'used. '
                                                                                                   'Max '
                                                                                                   '1024 '
                                                                                                   'characters.',
                                                                                    'maxLength': 1024,
                                                                                    'type': 'string'},
                                                                    'name': {'description': 'CSS '
                                                                                            'custom '
                                                                                            'property '
                                                                                            'name. '
                                                                                            'E.g. '
                                                                                            '"--color-primary".',
                                                                             'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                             'type': 'string'},
                                                                    'type': {'description': 'Design '
                                                                                            'token '
                                                                                            'type/category.',
                                                                             'enum': ['breakpoint',
                                                                                      'color',
                                                                                      'container',
                                                                                      'fontFamily',
                                                                                      'fontSize',
                                                                                      'fontWeight',
                                                                                      'letterSpacing',
                                                                                      'lineHeight',
                                                                                      'opacity',
                                                                                      'radius',
                                                                                      'spacing'],
                                                                             'type': 'string'},
                                                                    'value': {'description': 'Design '
                                                                                             'token '
                                                                                             'value. '
                                                                                             'For '
                                                                                             'colors, '
                                                                                             'use '
                                                                                             'a '
                                                                                             'CSS '
                                                                                             'color '
                                                                                             'string '
                                                                                             'like '
                                                                                             '"#ff0000" '
                                                                                             'or '
                                                                                             '"oklch(...)". '
                                                                                             'For '
                                                                                             'sizes '
                                                                                             '(spacing, '
                                                                                             'radius, '
                                                                                             'fontSize, '
                                                                                             'container, '
                                                                                             'breakpoint), '
                                                                                             'use '
                                                                                             'a px '
                                                                                             'string '
                                                                                             'like '
                                                                                             '"8px". '
                                                                                             'For '
                                                                                             'fontWeight, '
                                                                                             'use '
                                                                                             'a '
                                                                                             'number '
                                                                                             '(e.g. '
                                                                                             '400). '
                                                                                             'For '
                                                                                             'lineHeight/letterSpacing, '
                                                                                             'use '
                                                                                             'a '
                                                                                             'string '
                                                                                             '("1.5px") '
                                                                                             'or '
                                                                                             'number. '
                                                                                             'For '
                                                                                             'opacity, '
                                                                                             'use '
                                                                                             'a '
                                                                                             '0–1 '
                                                                                             'number '
                                                                                             '(e.g. '
                                                                                             '0.5) '
                                                                                             'or a '
                                                                                             'percent '
                                                                                             'string '
                                                                                             '(e.g. '
                                                                                             '"50%"). '
                                                                                             'To '
                                                                                             'alias '
                                                                                             'another '
                                                                                             'design '
                                                                                             'token, '
                                                                                             'use '
                                                                                             'a '
                                                                                             'CSS '
                                                                                             'variable '
                                                                                             'reference '
                                                                                             'like '
                                                                                             '"var(--color-red)".',
                                                                              'type': ['string',
                                                                                       'number']}},
                                                     'required': ['type', 'name', 'value'],
                                                     'type': 'object'},
                                           'minItems': 1,
                                           'type': 'array'}},
                 'required': ['tokens', 'fileId'],
                 'type': 'object'}})
REVIEWED_TOOL_CONTRACTS['set_tokens'].append(
{'annotations': {'destructiveHint': True},
 'inputSchema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                 'additionalProperties': False,
                 'properties': {'fileId': {'description': 'The file ID that the tool should '
                                                          'operate on.',
                                           'type': 'string'},
                                'tokens': {'description': 'Design tokens to update or delete, '
                                                          'applied sequentially.',
                                           'items': {'additionalProperties': False,
                                                     'properties': {'delete': {'description': 'Optional. '
                                                                                              'If '
                                                                                              'true, '
                                                                                              'deletes '
                                                                                              'the '
                                                                                              'design '
                                                                                              'token '
                                                                                              'entirely.',
                                                                               'type': 'boolean'},
                                                                    'description': {'description': 'Optional '
                                                                                                   'human-readable '
                                                                                                   'description '
                                                                                                   'of '
                                                                                                   'what '
                                                                                                   'the '
                                                                                                   'design '
                                                                                                   'token '
                                                                                                   'is '
                                                                                                   'for '
                                                                                                   'and '
                                                                                                   'how '
                                                                                                   'it '
                                                                                                   'should '
                                                                                                   'be '
                                                                                                   'used. '
                                                                                                   'Max '
                                                                                                   '1024 '
                                                                                                   'characters. '
                                                                                                   'Pass '
                                                                                                   'an '
                                                                                                   'empty '
                                                                                                   'string '
                                                                                                   'to '
                                                                                                   'clear.',
                                                                                    'maxLength': 1024,
                                                                                    'type': 'string'},
                                                                    'name': {'description': 'Target '
                                                                                            'design '
                                                                                            'token '
                                                                                            'by '
                                                                                            'its '
                                                                                            'full '
                                                                                            'CSS '
                                                                                            'custom '
                                                                                            'property '
                                                                                            'name '
                                                                                            '(e.g. '
                                                                                            '"--color-primary").',
                                                                             'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                             'type': 'string'},
                                                                    'newName': {'description': 'Optional. '
                                                                                               'Rename '
                                                                                               'the '
                                                                                               'design '
                                                                                               'token. '
                                                                                               'Provide '
                                                                                               'the '
                                                                                               'full '
                                                                                               'CSS '
                                                                                               'custom '
                                                                                               'property '
                                                                                               'name '
                                                                                               '(e.g. '
                                                                                               '"--color-primary-strong").',
                                                                                'pattern': '^--[a-zA-Z0-9_-]+$',
                                                                                'type': 'string'},
                                                                    'value': {'description': 'Optional. '
                                                                                             'New '
                                                                                             'value.',
                                                                              'type': ['string',
                                                                                       'number']}},
                                                     'required': ['name'],
                                                     'type': 'object'},
                                           'minItems': 1,
                                           'type': 'array'}},
                 'required': ['tokens', 'fileId'],
                 'type': 'object'}})

SCHEMA_PRESENTATION_KEYS = frozenset({"description", "title", "examples", "$comment"})


def semantic_schema(value, *, _named_fields=False):
    """Normalize schema prose while preserving legitimate input property names.

    The key 'description' is presentation metadata in a schema node but is an
    actual user-data field inside a 'properties' dictionary. Never discard
    those named fields (including names like 'title' and '$comment').
    Also preserve '$schema': it identifies JSON-Schema draft semantics, not
    harmless presentation text.
    """
    if isinstance(value, dict):
        normalized = {
            key: semantic_schema(item, _named_fields=(
                key in {"properties", "patternProperties", "$defs", "definitions"}))
            for key, item in value.items()
            if _named_fields or key not in SCHEMA_PRESENTATION_KEYS
        }
        if not _named_fields:
            # Ordering is not part of JSON Schema required/enum semantics.
            for key in ("required", "enum"):
                if isinstance(normalized.get(key), list):
                    normalized[key] = sorted(normalized[key], key=lambda item: encode(item))
        return normalized
    if isinstance(value, list):
        return [semantic_schema(item) for item in value]
    return value


def _same_reviewed_json(left, right):
    """JSON values are type-sensitive: safety true is not numeric 1.

    Python dict equality aliases bool and int; canonical JSON bytes do not.
    Invalid/nonserializable vendor inputs fail closed, never match a review.
    """
    try:
        return encode(left) == encode(right)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False


def compatible_tool_contract(tool_name, descriptor):
    """Return reviewed profile and safe extra root-field names, or None.

    A vendor may add optional top-level inputs, but we will NOT forward those
    unreviewed inputs. Required inputs, nested shape, defaults, semantics-
    bearing annotations and the original fields must stay reviewed.
    """
    if not isinstance(descriptor, dict) or descriptor.get("name") != tool_name:
        return None
    schema = descriptor.get("inputSchema")
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        return None
    actual = semantic_schema(schema)
    annotations = semantic_schema(descriptor.get("annotations", {}))
    if not isinstance(annotations, dict):
        return None
    for reviewed in REVIEWED_TOOL_CONTRACTS.get(tool_name, ()):
        if not _same_reviewed_json(annotations, reviewed["annotations"]):
            continue
        known = semantic_schema(reviewed["inputSchema"])
        if _same_reviewed_json(actual, known):
            return {"profile": reviewed, "optional_new_inputs": []}
        new_fields = set(actual.get("properties", {})) - set(known.get("properties", {}))
        if not new_fields or not isinstance(actual.get("required", []), list):
            continue
        if any(key in actual.get("required", []) for key in new_fields):
            continue
        if any(not isinstance(actual["properties"][key], dict)
               or "default" in actual["properties"][key] for key in new_fields):
            continue
        restricted = dict(actual, properties={
            key: value for key, value in actual["properties"].items() if key not in new_fields})
        if _same_reviewed_json(restricted, known):
            return {"profile": reviewed, "optional_new_inputs": sorted(new_fields)}
    return None


def scoped_tool_compatibility(catalog):
    """Read-only classification of each approved operation for this vendor run."""
    if not isinstance(catalog, dict):
        return {}
    return {name: compatible_tool_contract(name, catalog.get(name))
            for name in sorted(READ_TOOLS | EDIT_TOOLS | FILE_MANAGE_TOOLS)}


PAPER_FILE_ID_RE = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
# Native export, node deletion and undocumented page deletion remain unavailable.
# File management is a separate explicitly guarded write action, not a hidden read.


class Refusal(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(code)


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def load_json(value: str | bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise Refusal("DUPLICATE_JSON_KEY")
            result[key] = item
        return result
    try:
        return json.loads(value, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refusal("INVALID_JSON") from exc


def private_dir(path: Path) -> Path:
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")
    return path


def state_root() -> Path:
    # Fixed per OS principal, not per workspace, so separate clients share the mutex.
    return private_dir(Path.home() / ".local" / "state" / "mastermind-paper")


@contextlib.contextmanager
def desktop_lock(root: Path | None = None, *, wait_seconds: float | None = None):
    """Serialize one host's Paper calls while absorbing ordinary session overlap.

    Waiting is only for the local OS lock before any upstream call is sent. It is
    not an effect retry, queue, lease, or exactly-once mechanism. A bounded
    timeout still fails closed with DESKTOP_BUSY and no Paper call dispatched.
    """
    root = private_dir(root) if root else state_root()
    fd = os.open(root / "desktop.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Refusal("UNSAFE_LOCK_FILE")
        limit = DESKTOP_LOCK_WAIT_SECONDS if wait_seconds is None else max(0.0, float(wait_seconds))
        deadline = time.monotonic() + limit
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise Refusal(
                        "DESKTOP_BUSY",
                        f"Another bridge call held this desktop for more than {limit:g}s; no Paper call sent.",
                    ) from exc
                time.sleep(min(DESKTOP_LOCK_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
        yield
    finally:
        os.close(fd)


class PaperClient:
    """Fixed loopback transport; handles JSON and bounded SSE, never follows redirects.

    No proxy environment, cookies, caller URL, automatic retries or event reconnection.
    Tests inject a transport; production cannot select another host or port.
    """
    def __init__(self, timeout: float = 20.0):
        self.timeout = max(1.0, min(float(timeout), 60.0))
        self.session_id = None
        self.protocol = None
        self.counter = 0
        self.server = None

    def rpc(self, method: str, params: dict | None = None, *, notification=False) -> dict:
        self.counter += 1
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            request["id"] = self.counter
        body = encode(request)
        if len(body) > MAX_REQUEST:
            raise Refusal("REQUEST_TOO_LARGE")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        connection = http.client.HTTPConnection("127.0.0.1", 29979, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        try:
            connection.request("POST", "/mcp", body=body, headers=headers)
            response = connection.getresponse()
            if response.status != 200 and not (notification and response.status == 202):
                code = {401: "UPSTREAM_AUTH_REQUIRED", 403: "UPSTREAM_FORBIDDEN", 429: "UPSTREAM_RATE_LIMITED"}.get(response.status, "UPSTREAM_HTTP_ERROR")
                raise Refusal(code, "HTTP %d; no redirect or retry performed." % response.status)
            session_id = response.getheader("Mcp-Session-Id")
            if session_id:
                if not re.fullmatch(r"[\x21-\x7e]{1,256}", session_id):
                    raise Refusal("INVALID_SESSION_HEADER")
                if self.session_id and session_id != self.session_id:
                    raise Refusal("SESSION_CHANGED")
                self.session_id = session_id
            if notification:
                return {}
            content_type = response.getheader("Content-Type", "").split(";")[0].strip()
            if content_type == "text/event-stream":
                payload = self._sse(response, request["id"], deadline)
            elif content_type == "application/json":
                raw = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise Refusal("RESPONSE_DEADLINE")
                    chunk = response.read1(min(65536, MAX_BYTES - len(raw) + 1))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise Refusal("RESPONSE_TOO_LARGE")
                payload = load_json(bytes(raw))
            else:
                raise Refusal("UNSUPPORTED_CONTENT_TYPE")
            if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != request["id"]:
                raise Refusal("INVALID_RPC_RESPONSE")
            if "error" in payload:
                raise Refusal("UPSTREAM_RPC_ERROR", "Inspect Paper; upstream error text is not authority.")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise Refusal("INVALID_RPC_RESULT")
            return result
        except (OSError, http.client.HTTPException) as exc:
            raise Refusal("UPSTREAM_UNAVAILABLE", "Paper must be running with a file open. Login state is unknown.") from exc
        finally:
            connection.close()

    def _sse(self, response, request_id, deadline):
        size, parts, buffer = 0, [], b""
        while time.monotonic() < deadline:
            chunk = response.read1(min(65536, MAX_BYTES - size + 1))
            size += len(chunk)
            if size > MAX_BYTES:
                raise Refusal("RESPONSE_TOO_LARGE")
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip() == b"":
                    if parts:
                        item = load_json(b"\n".join(parts))
                        parts = []
                        if isinstance(item, dict) and item.get("id") == request_id:
                            return item
                elif line.startswith(b"data:"):
                    parts.append(line[5:].lstrip(b" ").rstrip(b"\r"))
        raise Refusal("INCOMPLETE_SSE_RESPONSE")

    def initialize(self):
        result = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "mastermind-paper", "version": VERSION}})
        self.protocol = result.get("protocolVersion")
        if self.protocol not in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}:
            raise Refusal("UNSUPPORTED_PROTOCOL")
        self.server = result.get("serverInfo")
        self.rpc("notifications/initialized", notification=True)
        return result

    def catalog(self):
        tools, cursor, seen = [], None, set()
        for _ in range(8):
            page = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            chunk = page.get("tools")
            if not isinstance(chunk, list):
                raise Refusal("INVALID_CATALOG")
            tools.extend(chunk)
            if len(tools) > 128:
                raise Refusal("CATALOG_TOO_LARGE")
            cursor = page.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen:
                raise Refusal("CATALOG_CURSOR_INVALID")
            seen.add(cursor)
        else:
            raise Refusal("CATALOG_TOO_LARGE")
        result = {}
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or tool["name"] in result:
                raise Refusal("INVALID_CATALOG")
            result[tool["name"]] = tool
        return result

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})


def _basic_candidates(result):
    values = []
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        values.append(structured)
    for block in result.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            value = load_json(block.get("text", ""))
        except Refusal:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _stable_file(value):
    file_id = value.get("fileId") or value.get("documentId")
    file_name = value.get("fileName")
    nested = value.get("file")
    if not file_id and isinstance(nested, dict):
        file_id = nested.get("id")
        if not file_name:
            file_name = nested.get("name")
    if isinstance(file_id, str) and file_id:
        return file_id, file_name if isinstance(file_name, str) and file_name else None
    return None


def basic_object(result):
    if result.get("isError"):
        raise Refusal("DOCUMENT_UNAVAILABLE")
    values = _basic_candidates(result)
    if not values:
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info must return a JSON object; do not guess fields.")
    stable = [item for item in (_stable_file(value) for value in values) if item]
    file_ids = {item[0] for item in stable}
    if len(file_ids) > 1:
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting file identities.")
    file_id = next(iter(file_ids), None)
    details = [value for value in values
               if isinstance(value.get("fileName"), str) and value.get("fileName")
               and isinstance(value.get("pageName"), str) and value.get("pageName")
               and isinstance(value.get("artboards"), list)]
    if details:
        names = {value["fileName"] for value in details}
        pages = {(value.get("pageId"), value["pageName"]) for value in details}
        detail_variants = {encode(value) for value in details}
        if len(names) != 1 or len(pages) != 1 or len(detail_variants) != 1:
            raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting document detail.")
        info = dict(details[0])
        stable_names = {name for _, name in stable if name}
        if stable_names and (len(stable_names) != 1 or info["fileName"] not in stable_names):
            raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "File header and document detail disagree.")
        if file_id:
            info["fileId"] = file_id
        hashes = [value.get("contentHash") for value in values if isinstance(value.get("contentHash"), dict)]
        if hashes:
            encoded = {encode(value) for value in hashes}
            if len(encoded) != 1:
                raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned conflicting content hashes.")
            info["contentHash"] = hashes[0]
        return info
    if file_id:
        info = dict(values[0])
        info["fileId"] = file_id
        if stable[0][1] and not info.get("fileName"):
            info["fileName"] = stable[0][1]
        return info
    raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED", "get_basic_info returned no supported document identity.")


def document_identity(info):
    file_id = info.get("fileId") or info.get("documentId")
    nested = info.get("file")
    if not file_id and isinstance(nested, dict):
        file_id = nested.get("id")
    if isinstance(file_id, str) and file_id:
        return {"kind": "file-id", "id": file_id}
    name, page, boards = info.get("fileName"), info.get("pageName"), info.get("artboards")
    if not isinstance(name, str) or not name or not isinstance(page, str) or not isinstance(boards, list):
        raise Refusal("DOCUMENT_SCHEMA_UNVERIFIED")
    ids = sorted(b["id"] for b in boards if isinstance(b, dict) and isinstance(b.get("id"), str) and b["id"])
    if not ids:
        raise Refusal("DOCUMENT_ANCHOR_REQUIRED", "Create one starter artboard in the intended Paper file, then inspect again.")
    return {"kind": "artboard-anchor", "file": name, "page": page, "anchor": ids[0]}


def validate_execution_binding(value):
    """Validate installed provenance, never caller permission or a host registry.

    The host ref must come from the existing fleet owner at deployment. This
    function validates its shape, not physical-host attestation. Legacy unbound
    runtimes retain their original snapshot contract.
    """
    if value is None:
        return None
    fields = {"schema", "host_ref", "service_ref", "runtime_revision", "bridge_sha256"}
    if type(value) is not dict or set(value) != fields:
        raise Refusal("EXECUTION_BINDING_INVALID")
    if value.get("schema") != "mastermind.paper_execution_binding.v1":
        raise Refusal("EXECUTION_BINDING_INVALID")
    for key, pattern in (("host_ref", r"host-[0-9a-f]{64}"),
                         ("service_ref", r"[0-9a-f]{64}"),
                         ("runtime_revision", r"[0-9a-f]{40}"),
                         ("bridge_sha256", r"[0-9a-f]{64}")):
        if type(value[key]) is not str or not re.fullmatch(pattern, value[key]):
            raise Refusal("EXECUTION_BINDING_INVALID")
    return dict(value)


def snapshot(client, file_id: str | None = None, *, execution_binding=None):
    execution_binding = validate_execution_binding(execution_binding)
    if file_id is not None and (not isinstance(file_id, str) or not file_id):
        raise Refusal("FILE_ID_REQUIRED")
    arguments = {} if file_id is None else {"fileId": file_id}
    info = basic_object(client.call("get_basic_info", arguments))
    try:
        identity = document_identity(info)
        bind_error = None
    except Refusal as exc:
        identity, bind_error = None, exc.code
    if identity is not None and identity.get("kind") != "file-id":
        bind_error = "FILE_ID_REQUIRED"
    if file_id is not None and (identity is None or identity.get("kind") != "file-id"
                                or identity.get("id") != file_id):
        raise Refusal("FILE_ID_MISMATCH", "Paper target read did not return the requested file.")
    guarded_info = info if execution_binding is None else {
        "document": info, "execution_binding": execution_binding}
    result = {"basic_info": info, "identity": identity, "snapshot_sha256": digest(guarded_info),
              "write_binding_ready": identity is not None and identity.get("kind") == "file-id",
              "binding_error": bind_error}
    if execution_binding is not None:
        result["execution_binding"] = execution_binding
    return result


def same_document(identity, info):
    if identity["kind"] == "file-id":
        try:
            current = document_identity(info)
        except Refusal:
            return False
        return current.get("kind") == "file-id" and current.get("id") == identity["id"]
    return (info.get("fileName") == identity["file"] and info.get("pageName") == identity["page"]
            and any(isinstance(b, dict) and b.get("id") == identity["anchor"] for b in info.get("artboards", [])))

def schema_receipt(client, catalog, *, server_pin=SUPPORTED_SERVER,
                   catalog_pin=SUPPORTED_CATALOG_SHA256):
    server = client.server if isinstance(client.server, dict) else {}
    actual = {"server_name": server.get("name"), "server_version": server.get("version"),
              "catalog_sha256": digest(catalog)}
    expected_name = server_pin[0] if server_pin else None
    expected_version = server_pin[1] if server_pin and len(server_pin) > 1 else None
    server_name_ok = expected_name is None or actual["server_name"] == expected_name
    server_version_ok = expected_version is None or actual["server_version"] == expected_version

    known_full = (actual["catalog_sha256"] == SUPPORTED_CATALOG_SHA256
                  or actual["catalog_sha256"] in REVIEWED_CATALOG_SHA256_ALTERNATES)
    # The test-only explicit pin stays exact and never inherits tolerant mode.
    # Production always uses the default value and still checks every tool.
    custom_pin = catalog_pin != SUPPORTED_CATALOG_SHA256
    pin_ok = (not custom_pin or catalog_pin is None
              or actual["catalog_sha256"] == catalog_pin)
    classified = scoped_tool_compatibility(catalog)
    # Preserve the existing exact-catalog test seam: passing a non-default
    # digest still requires a byte-for-byte catalog match, never loose matching.
    # No MCP or CLI input can select this internal-only _catalog_pin parameter.
    critical_ok = ((pin_ok and "get_basic_info" in catalog) if custom_pin
                   else classified.get("get_basic_info") is not None)
    if custom_pin:
        eligible = sorted(name for name in EDIT_TOOLS | FILE_MANAGE_TOOLS
                          if name in catalog and pin_ok)
    else:
        eligible = sorted(name for name in EDIT_TOOLS | FILE_MANAGE_TOOLS
                          if classified.get(name) is not None)
    incompatible = sorted(name for name in EDIT_TOOLS | FILE_MANAGE_TOOLS
                          if name not in eligible)
    unrestricted = [name for name, profile in classified.items()
                    if profile and profile["optional_new_inputs"]]
    ok = bool(server_name_ok and server_version_ok and pin_ok and critical_ok and eligible)
    return {**actual, "accepted_for_write": ok,
            "expected_server": [expected_name, expected_version] if server_pin else None,
            "server_name_compatible": server_name_ok,
            "server_version_compatible": server_version_ok,
            "server_version_policy": "EXACT" if expected_version is not None else "OBSERVED_NOT_PINNED",
            "catalog_compatible": bool(pin_ok and critical_ok and eligible),
            "catalog_policy": "TOOL_SCOPED_CONTRACT_V1" if not custom_pin else "EXACT_CUSTOM_PIN",
            "full_catalog_known": known_full,
            "expected_catalog_sha256": catalog_pin,
            "additional_reviewed_catalog_sha256": sorted(REVIEWED_CATALOG_SHA256_ALTERNATES)
                if not custom_pin else [],
            "snapshot_tool_compatible": critical_ok,
            "compatible_write_tools": eligible if ok else [],
            "incompatible_write_tools": incompatible,
            "optional_vendor_inputs_ignored": unrestricted}



def qualify_call_arguments(tool, arguments, catalog, *, action, custom_exact_pin):
    """Validate one requested call against its current reviewed tool profile."""
    if tool not in catalog:
        raise Refusal("TOOL_NOT_AVAILABLE")
    if custom_exact_pin:
        return
    qualified = compatible_tool_contract(tool, catalog[tool])
    if qualified is None:
        raise Refusal("TOOL_SCHEMA_CHANGED",
                      "Only this tool is unavailable; other compatible Paper operations remain active.")
    # Benign optional vendor extensions remain unusable by bridge callers.
    known_inputs = set(qualified["profile"]["inputSchema"].get("properties", {}))
    upstream_keys = set(arguments) - ({"sourceFileId"} if action == "file_manage" else set())
    if upstream_keys - known_inputs:
        raise Refusal("UNREVIEWED_TOOL_ARGUMENTS")
    if action in {"edit", "file_manage"} and tool == "set_text_content":
        # Both text formats are reviewed; use the profile for this exact call.
        fields = qualified["profile"]["inputSchema"]["properties"]["updates"]["items"]["properties"]
        item_key = "html" if "html" in fields else "textContent"
        updates = arguments.get("updates")
        if not isinstance(updates, list) or not updates or any(
            not isinstance(item, dict)
            or set(item) != {"nodeId", item_key}
            or not isinstance(item["nodeId"], str) or not item["nodeId"]
            or not isinstance(item[item_key], str)
            for item in updates
        ):
            raise Refusal("PAPER_RICH_TEXT_SCHEMA_REQUIRED"
                          if item_key == "html" else "PAPER_LEGACY_TEXT_SCHEMA_REQUIRED")


def execute(action: str, *, tool: str | None = None, arguments: dict | None = None,
            expected_snapshot: str | None = None, operation_id: str | None = None,
            allow_write=False, client=None, lock_root=None, execution_binding=None,
            _server_pin=SUPPORTED_SERVER, _catalog_pin=SUPPORTED_CATALOG_SHA256):
    """One serialized operation. Snapshot hash is a drift guard, NOT authorization.

    Local edits outside this adapter can race; no transaction/isolation claim is made.
    No persistent duplicate/retry ledger is introduced. Caller owns effect reconciliation.
    """
    execution_binding = validate_execution_binding(execution_binding)
    if action not in {"status", "catalog", "read", "edit", "file_manage"}:
        raise Refusal("UNKNOWN_ACTION")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict) or len(encode(arguments)) > MAX_REQUEST - 1024:
        raise Refusal("INVALID_ARGUMENTS")
    # Keep the already-published paper_edit surface usable for new, strictly
    # guarded file operations; an additional native MCP tool is optional.
    if action == "edit" and tool in FILE_MANAGE_TOOLS:
        action = "file_manage"
    editing = action in {"edit", "file_manage"}
    if editing:
        if not allow_write:
            raise Refusal("WRITE_DISABLED")
        if tool not in (FILE_MANAGE_TOOLS if action == "file_manage" else EDIT_TOOLS):
            raise Refusal("TOOL_NOT_ALLOWED")
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", operation_id):
            raise Refusal("OPERATION_ID_REQUIRED")
        if not isinstance(expected_snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_snapshot):
            raise Refusal("SNAPSHOT_REQUIRED")
    elif action == "read" and tool not in READ_TOOLS:
        raise Refusal("TOOL_NOT_ALLOWED")
    client = client or PaperClient()
    with desktop_lock(lock_root):
        client.initialize()
        if action == "status":
            # Status calls get_basic_info implicitly. Qualify its live read
            # annotations/input schema *before* any Paper tool is dispatched.
            # A private exact-pin unit fixture retains its historical seam;
            # MCP/CLI callers cannot override the default production pin.
            status_catalog = client.catalog()
            status_schema = schema_receipt(
                client, status_catalog, server_pin=_server_pin, catalog_pin=_catalog_pin)
            if _catalog_pin == SUPPORTED_CATALOG_SHA256:
                if (not status_schema["server_name_compatible"]
                        or not status_schema["server_version_compatible"]
                        or not status_schema["snapshot_tool_compatible"]):
                    raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
            return {"state": "CONNECTED", "server": client.server, "endpoint": ENDPOINT,
                    "document": snapshot(client, execution_binding=execution_binding),
                    "write_schema": status_schema,
                    "quota_remaining": None, "plan": "UNKNOWN"}
        catalog = client.catalog()
        schema = schema_receipt(client, catalog, server_pin=_server_pin, catalog_pin=_catalog_pin)
        if action == "catalog":
            return {"server": client.server, "tools": [
                        dict(catalog[n], bridge_access=(
                            ("read" if compatible_tool_contract(n, catalog[n]) is not None
                             else "read_held_schema") if n in READ_TOOLS else
                            "edit" if n in schema["compatible_write_tools"] else "edit_held_schema"))
                        for n in sorted(catalog) if n in READ_TOOLS | EDIT_TOOLS | FILE_MANAGE_TOOLS],
                    "blocked_tools": sorted(set(catalog) - READ_TOOLS - EDIT_TOOLS - FILE_MANAGE_TOOLS),
                    "catalog_sha256": schema["catalog_sha256"], "write_schema": schema}
        if editing and not schema["accepted_for_write"]:
            raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED",
                          "Paper identity, critical snapshot schema, or requested full-catalog pin is incompatible.")
        # Explicit non-default exact pin remains a private test seam. Normal
        # callers cannot select it and always use the tool-scoped contracts.
        custom_exact_pin = (_catalog_pin != SUPPORTED_CATALOG_SHA256
                            and (_catalog_pin is None or schema["catalog_sha256"] == _catalog_pin))
        if action == "read" and not custom_exact_pin:
            # An explicit guarded read also invokes the snapshot getter.
            # Refuse altered/unsafe implicit getter contracts before either
            # the guard read or the requested tool can reach Paper.
            if (not schema["server_name_compatible"]
                    or not schema["server_version_compatible"]
                    or (expected_snapshot is not None
                        and not schema["snapshot_tool_compatible"])):
                raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
        qualify_call_arguments(tool, arguments, catalog, action=action,
                               custom_exact_pin=custom_exact_pin)
        if action == "file_manage":
            if tool == "create_file":
                supplied_file = arguments.get("cloneFileId") or arguments.get("sourceFileId")
                if set(arguments) - {"cloneFileId", "sourceFileId", "name"}:
                    raise Refusal("INVALID_ARGUMENTS")
                if arguments.get("cloneFileId") and arguments.get("sourceFileId"):
                    raise Refusal("INVALID_ARGUMENTS")
                if not supplied_file:
                    raise Refusal("INVALID_ARGUMENTS")
            else:
                supplied_file = arguments.get("resourceId")
                if set(arguments) != {"resourceId", "name"}:
                    raise Refusal("INVALID_ARGUMENTS")
            if not isinstance(supplied_file, str) or not PAPER_FILE_ID_RE.fullmatch(supplied_file):
                raise Refusal("FILE_ID_REQUIRED", "An exact existing source file ID is required.")
        else:
            supplied_file = arguments.get("fileId")
        if editing and (not isinstance(supplied_file, str) or not supplied_file):
            raise Refusal("FILE_ID_REQUIRED", "Pass the exact inspected Paper file ID for every edit.")
        # A guarded background-file read must inspect that same explicit target,
        # not the unrelated user-active document. Host scope remains out of band.
        before = (snapshot(client, supplied_file, execution_binding=execution_binding)
                  if editing or expected_snapshot else None)
        if before and before["snapshot_sha256"] != expected_snapshot:
            raise Refusal("DOCUMENT_CHANGED", "Read the exact target file before deciding on a new edit.")
        if editing and not before["write_binding_ready"]:
            raise Refusal(before["binding_error"] or "DOCUMENT_BINDING_REQUIRED")
        if editing and supplied_file != before["identity"]["id"]:
            raise Refusal("FILE_ID_MISMATCH", "Edit target does not match the inspected Paper file.")
        if action == "file_manage" and (not isinstance(arguments.get("name"), str)
                                       or not 1 <= len(arguments["name"].strip()) <= 500):
            raise Refusal("FILE_NAME_REQUIRED")
        if editing and tool == "set_tokens":
            updates = arguments.get("tokens")
            if isinstance(updates, list) and any(isinstance(item, dict) and item.get("delete") is True for item in updates):
                raise Refusal("TOKEN_DELETE_NOT_ALLOWED", "Delete tokens only through an explicitly reviewed destructive workflow.")
        if before is not None and not custom_exact_pin:
            # The guard getter is itself a vendor RPC. Requalify after it so
            # material mid-operation drift cannot dispatch an obsolete call.
            # This is pre-dispatch: refusal must not claim EFFECT_UNKNOWN.
            catalog = client.catalog()
            schema = schema_receipt(client, catalog, server_pin=_server_pin,
                                    catalog_pin=_catalog_pin)
            if (not schema["server_name_compatible"]
                    or not schema["server_version_compatible"]
                    or not schema["snapshot_tool_compatible"]
                    or (editing and not schema["accepted_for_write"])):
                raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
            qualify_call_arguments(tool, arguments, catalog, action=action,
                                   custom_exact_pin=False)
        # Paper validates its current input schema. A dispatched tool error may be partial.
        try:
            upstream_arguments = dict(arguments)
            if action == "file_manage":
                upstream_arguments.pop("sourceFileId", None)
            result = client.call(tool, upstream_arguments)
        except Exception as exc:
            if editing:
                return {"state": "EFFECT_UNKNOWN", "operation_id": operation_id, "tool": tool,
                        "before": before, "retry_allowed": False, "reason": "RESPONSE_NOT_OBSERVED"}
            raise
        if not editing:
            observed = {"state": "TOOL_ERROR" if result.get("isError") else "OBSERVED", "result": result}
            if tool == "get_basic_info" and supplied_file is not None and not result.get("isError"):
                # Bootstrap through the existing read schema when Paper has no
                # default active-file context. Never infer a target from a name.
                if not same_document({"kind": "file-id", "id": supplied_file}, basic_object(result)):
                    raise Refusal("FILE_ID_MISMATCH", "Paper target read did not return the requested file.")
                # A page-specific result cannot mint the file-only snapshot
                # used by edits. We must read the file-only getter again, but
                # only after requalifying its *current* schema/annotations.
                # The first getter may itself have changed the live catalog.
                # No unreviewed second getter may reach the vendor.
                if not custom_exact_pin:
                    live_snapshot_schema = schema_receipt(
                        client, client.catalog(), server_pin=_server_pin,
                        catalog_pin=_catalog_pin)
                    if (not live_snapshot_schema["server_name_compatible"]
                            or not live_snapshot_schema["server_version_compatible"]
                            or not live_snapshot_schema["snapshot_tool_compatible"]):
                        raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
                observed["document"] = snapshot(client, supplied_file, execution_binding=execution_binding)
                observed["write_schema"] = schema
            return observed
        if result.get("isError"):
            return {"state": "EFFECT_UNKNOWN", "operation_id": operation_id, "tool": tool,
                    "result": result, "before": before, "retry_allowed": False, "reason": "UPSTREAM_TOOL_ERROR_MAY_BE_PARTIAL"}
        try:
            # A write has already been dispatched. A newly unqualified getter
            # is not a safe verification path: retain EFFECT_UNKNOWN/no replay.
            if not custom_exact_pin:
                after_schema = schema_receipt(client, client.catalog(), server_pin=_server_pin,
                                              catalog_pin=_catalog_pin)
                if (not after_schema["server_name_compatible"]
                        or not after_schema["server_version_compatible"]
                        or not after_schema["snapshot_tool_compatible"]):
                    raise Refusal("UPSTREAM_SCHEMA_UNREVIEWED")
            after = snapshot(client, supplied_file, execution_binding=execution_binding)
            matched = same_document(before["identity"], after["basic_info"])
            if action == "file_manage" and tool == "rename_resource":
                matched = matched and after["basic_info"].get("fileName") == arguments["name"].strip()
        except Exception:
            after, matched = None, False
        return {"state": ("RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION" if tool == "create_file" and action == "file_manage" and matched
                          else "APPLIED_RESPONSE_OBSERVED" if matched else "EFFECT_UNKNOWN"),
                "operation_id": operation_id, "tool": tool, "result": result,
                "before": before, "after": after, "retry_allowed": False,
                "production_acceptance": False}


def save_artifacts(value: dict, directory: Path):
    """Save only returned PNG/JPEG images and JSON; no server-selected host paths."""
    directory = private_dir(directory)
    copied = json.loads(json.dumps(value))
    paths = []
    result = copied.get("result", {})
    for block in result.get("content", []):
        if block.get("type") != "image":
            continue
        suffix = {"image/png": "png", "image/jpeg": "jpg"}.get(block.get("mimeType"))
        if not suffix:
            raise Refusal("UNSUPPORTED_IMAGE_TYPE")
        try:
            raw = base64.b64decode(block["data"], validate=True)
        except (KeyError, ValueError) as exc:
            raise Refusal("INVALID_IMAGE") from exc
        if len(raw) > MAX_BYTES or not (raw.startswith(b"\x89PNG\r\n\x1a\n") if suffix == "png" else raw.startswith(b"\xff\xd8\xff")):
            raise Refusal("INVALID_IMAGE")
        name = hashlib.sha256(raw).hexdigest() + "." + suffix
        target = directory / name
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise Refusal("ARTIFACT_EXISTS", "Reuse the existing artifact; never overwrite it.")
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        block.pop("data")
        block["artifact_path"] = str(target)
        paths.append(str(target))
    copied["artifact_paths"] = paths
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "catalog", "read", "edit", "file_manage"])
    parser.add_argument("--tool")
    parser.add_argument("--arguments", default="{}", help="JSON object; @file reads a bounded local JSON file")
    parser.add_argument("--expected-snapshot")
    parser.add_argument("--operation-id")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    try:
        raw = args.arguments
        if raw.startswith("@"):
            with open(raw[1:], "rb") as stream:
                raw = stream.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise Refusal("REQUEST_TOO_LARGE")
        result = execute(args.action, tool=args.tool, arguments=load_json(raw),
                         expected_snapshot=args.expected_snapshot, operation_id=args.operation_id,
                         allow_write=args.allow_write)
        if args.artifact_dir:
            result = save_artifacts(result, args.artifact_dir)
        print(json.dumps(result, indent=2))
        return 2 if result.get("state") in {"EFFECT_UNKNOWN", "TOOL_ERROR"} else 0
    except Refusal as exc:
        print(json.dumps({"state": exc.code, "detail": exc.detail, "retry_allowed": False}))
        return 2
    except Exception:
        print(json.dumps({"state": "LOCAL_FAILURE", "retry_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

