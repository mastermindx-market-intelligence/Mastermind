"""Explicit source-authored profile selection for goal-only project drafts.

The sealed owner supplies this captured catalogue. Neither this pure builder
nor a selected profile grants source publication or Runtime execution.
"""
from __future__ import annotations

import copy
import re

from integrations.mastermind_workspace_app.project_proposal_request import (
    REQUEST_SCHEMA, build_proposal_request, profile_digest)

CATALOGUE_SCHEMA = 'mastermind.workspace_project_authoring_profiles.v1'
SELECTION_SCHEMA = 'mastermind.project_profile_selection.v1'


def validate_profiles(catalogue):
    if (type(catalogue) is not dict or set(catalogue) != {'schema','profiles'}
            or catalogue['schema'] != CATALOGUE_SCHEMA or type(catalogue['profiles']) is not list
            or not 1 <= len(catalogue['profiles']) <= 8):
        raise ValueError('invalid_profiles')
    seen=set()
    for entry in catalogue['profiles']:
        if (type(entry) is not dict or set(entry) != {'id','label','summary','profile'}
                or type(entry['id']) is not str or re.fullmatch(r'[a-z][a-z0-9-]{1,63}',entry['id']) is None
                or entry['id'] in seen):
            raise ValueError('invalid_profiles')
        seen.add(entry['id'])
        for field in ('label','summary'):
            values=entry[field]
            if (type(values) is not dict or set(values) != {'en','zhCN'}
                    or any(type(text) is not str or not text.strip() or len(text.encode('utf-8'))>1000 for text in values.values())):
                raise ValueError('invalid_profiles')
        profile_digest(entry['profile'])
    return copy.deepcopy(catalogue)


def profile_choices(catalogue):
    """Literal captured facts for Options; no automatic selected profile."""
    choices=[]
    for entry in validate_profiles(catalogue)['profiles']:
        p=entry['profile']
        choices.append({'id':entry['id'],'label':entry['label'],'summary':entry['summary'],
            'revision':profile_digest(p),'owner':p['owner'],'program':p['program'],'repos':p['repos'],
            'classification':p['class'],'blastRadius':p['blast_radius'],'ambiguity':p['ambiguity']})
    return choices


def build_profiled_proposal_request(request, *, principal, captured_catalogue):
    """Resolve only an explicit profile at its exact authored revision."""
    keys={'schema','request_id','goal','expected_macro_sha','profile_id','profile_sha256'}
    if (type(request) is not dict or set(request)!=keys or request['schema']!=SELECTION_SCHEMA
            or type(request['profile_id']) is not str
            or type(request['request_id']) is not str
            or re.fullmatch(r'mmos-project-create-[0-9a-f]{40}',request['request_id']) is None):
        raise ValueError('invalid_profile_selection')
    entries=validate_profiles(captured_catalogue)['profiles']
    found=[entry for entry in entries if entry['id']==request['profile_id']]
    if len(found)!=1:
        raise ValueError('invalid_profile_selection')
    # Revision checks and literal goal handling stay with the existing builder.
    return build_proposal_request({key:request[key] for key in keys-{'profile_id','schema'}} | {'schema':REQUEST_SCHEMA},
                                  principal=principal,authored_profile=found[0]['profile'])
