"""Delivery only for an original ordinary Fabric artifact producer.

No launch, lease, retry, controller takeover, ledger or acceptance effects.
The original root commissions recovery. Native environment/packet fields are
caller correlation and retained evidence, never authentication or a new grant.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

import artifact_delivery as delivery
import artifact_reader as reader
import artifact_production as production

DirectoryChain = delivery.DirectoryChain
HERE = Path(__file__).resolve().parent
SCHEMA = 'mastermind.original_delivery_read.v1'
PLAIN_SCHEMA = 'mastermind.original_plain_result_contract.v1'
PLAIN_SCOPES = {'fabric-manifest-framing-review-01a11e90-v1': {'root': '01a11e90-4b5d-7f53-b966-8aaaad38701f',
                                                'parent': '01a11e90-4b5d-7f53-b966-8aaaad38701f',
                                                'host': 'mb',
                                                'packet_path': '/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/fabric-start-publication-20261012-fb76f8a5c8c5e179/integrations/session_bridge/artifact_manifest_framing/REVIEW_PACKET.txt',
                                                'packet_sha256': 'e7fb39a83f6e7456fe976c83f88f95602e2164bb00acfdf36f7aaade7e272f88',
                                                'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114',
                                                'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/fabric-manifest-framing-review-01a11e90-v1-collection-v1'},
 'mm-os-incident-custody-direct-review-20261013-01a104e6': {'root': '01a104e6-58f8-76d3-8d99-1302a1cca072',
                                                            'parent': '01a104e6-58f8-76d3-8d99-1302a1cca072',
                                                            'host': 'ubuntu1',
                                                            'packet_path': '/Volumes/Mastermind/evidence/mastermind-os-noir-product-convergence-20261003-astra-001/production-continuation-20261010/issuer-custody-repair-20261013/direct-preventive-review-packet.md',
                                                            'packet_sha256': 'dc3bfd8aaf0358c160c7290def2b3d3c6ef45893e1042620346e8ee7070d588c',
                                                            'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114',
                                                            'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/mm-os-incident-custody-direct-review-20261013-01a104e6-collection-v1'},
 'rf-archive-order-review-01a1333c-v1': {'root': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                         'parent': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                         'host': 'mb',
                                         'mode': 'qwen',
                                         'requested_model': 'qwen3.8-max',
                                         'packet_path': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/runtime-release/physical-qualification/archive-order-repair-v1/ARCHIVE_ORDER_REVIEW_PACKET.txt',
                                         'packet_sha256': '30fb451ed25f680d0dddebfeca1a38abb1b923a031af564758f6b820a456a854',
                                         'support_digest': '8cf4ee40a6b81a2cae2b23e51affb55595292541b8f3e3fcf0627216b31d9ed5',
                                         'source_pins': {'log': 'e765bb98af7a421ddf4c170e03672eef4363ef5d3bc32ab721e634c6734cd33c',
                                                         'support': 'edc233071cb0d6a800dfba97e1a2a904a0a4ec54554ba473ac551611e8182fdd'},
                                         'destination': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/retained-returns/rf-archive-order-review-01a1333c-v1-collection-v1'},
 'rf-mountinfo-review-01a1333c-v1': {'root': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                     'parent': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                     'host': 'ubuntu1',
                                     'mode': 'qwen',
                                     'requested_model': 'qwen3.8-max',
                                     'packet_path': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/containment-acceptance/workloads/MOUNTINFO_INDEPENDENT_REVIEW_PACKET_V1.txt',
                                     'packet_sha256': 'd10873588448ba479ffca205e928239290f5d6e9348994d9d1acdd4897e63728',
                                     'support_digest': '69e494d29888c63cfee97ce19f7ed6afb7cf24a145ee9dc019e737e853f81a9b',
                                     'source_pins': {'log': 'a45d165e074694c10d59dbd4729759c607eb05d09d369e6a977d545c989f2193',
                                                     'support': 'ff2d51c0a2b95a96ef2543b8e1d53d88e7706c6398f1b1fcbc09b44270f310fe'},
                                     'destination': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/retained-returns/rf-mountinfo-review-01a1333c-v1-collection-v1'}}

# Exact native construction/dispatch witnesses are in SCOPES.json and PROVENANCE.json.
PLAIN_SCOPES.update({'r2-events-composition-review-20261015-01a13315': {'root': '01a13315-332b-7102-b7c8-0c7fc01fa92c',
                                                    'parent': '01a13315-332b-7102-b7c8-0c7fc01fa92c',
                                                    'host': 'ubuntu3',
                                                    'mode': 'qwen',
                                                    'requested_model': 'qwen3.8-max',
                                                    'packet_path': '/Volumes/Mastermind/evidence/meta-ceo-r2-20261012-01a13315/1362-composition-review-packet.md',
                                                    'packet_sha256': '9289b43965dca0d11a8e38f8a112124b0bf990515bf4dc717d4e22bd38647f7a',
                                                    'support_digest': 'df14b5db0788c7417b48d253b92a331aa147e6c80573a47ad998e561d7421740',
                                                    'source_pins': {'log': '8e76307669db6493c7eb0a54f51ba29fd71445d2fd84edddb67daa1510935747',
                                                                    'support': 'c2e4d3faf5bb1c821565988a602bdbaa7384400d79c9dfc951b017e39f72ada0'},
                                                    'lease_witness': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/r2-events-composition-review-20261015-01a13315.lease.KQ8T0E',
                                                                      'sha256': 'e6f0b1d171e1453897f16c274f44fa21dc7c5503a4f7a05de34008a7877c093c'},
                                                    'destination': '/Volumes/Mastermind/evidence/meta-ceo-r2-20261012-01a13315/retained-returns/r2-events-composition-review-20261015-01a13315-collection-v1'},
 'r2-events-aead-current-review-20261015-01a13315': {'root': '01a13315-332b-7102-b7c8-0c7fc01fa92c',
                                                     'parent': '01a13315-332b-7102-b7c8-0c7fc01fa92c',
                                                     'host': 'mb',
                                                     'mode': 'qwen',
                                                     'requested_model': 'qwen3.8-max',
                                                     'packet_path': '/Volumes/Mastermind/evidence/meta-ceo-r2-20261012-01a13315/1362-aead-review-packet.md',
                                                     'packet_sha256': 'ec671493af948e49d8e4ceca5d91c64b8084e31c525be0bf948a51d455fc8c56',
                                                     'support_digest': '5fc2034ca5e4b16a8d30a802beb5fa5c4697c44a0a2e10aa09d56f57ec722f62',
                                                     'source_pins': {'log': 'c485b8578f3f1071e7279fe36a5a1602bb7a012d40ef61cb2dcc4fffd0448c71',
                                                                     'support': '12750ade68e8b53b142e816eae58fa3633ec9a8f0410ae2d006e3cad5b0f930d'},
                                                     'lease_witness': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/r2-events-aead-current-review-20261015-01a13315.lease.VDxqSz',
                                                                       'sha256': 'cde62d8f07e38b9583362717fbc0e63d0b0f383e1e89fda8ccdec00038735fa1'},
                                                     'destination': '/Volumes/Mastermind/evidence/meta-ceo-r2-20261012-01a13315/retained-returns/r2-events-aead-current-review-20261015-01a13315-collection-v1'}})
# One original Vault plaintext review; see PROVENANCE.json. No lifecycle mutation.
PLAIN_SCOPES.update({'rv-original-tail-risk-review-01a13301-r1': {'destination': '/Volumes/Mastermind/evidence/research-vault-completion-20261012-01a13301/retained-returns/rv-original-tail-risk-review-01a13301-r1-collection-v1',
                                              'host': 'ubuntu0',
                                              'lease_witness': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/rv-original-tail-risk-review-01a13301-r1.lease.qyAasS',
                                                                'sha256': '1828f9ddabff24ba3871a43aa062da4e589acc2db542db95cbe7680c61a93c17'},
                                              'mode': 'qwen',
                                              'packet_path': '/Volumes/Mastermind/evidence/research-vault-completion-20261012-01a13301/runtime-composition/original-parent-continuation/risk-review-packet.txt',
                                              'packet_sha256': 'ed6b0c62d2d86b0cb9c292df2ed9db931354cc7bf31409c61ae155070e2d7133',
                                              'parent': '01a13301-995f-7631-8cee-d675d7de5671',
                                              'requested_model': 'qwen3.8-max',
                                              'root': '01a13301-995f-7631-8cee-d675d7de5671',
                                              'source_pins': {'log': '62e5fadda6398d0c33ffc5e531cefc1b672fb7ad8237140fff54c032edfa89a1',
                                                              'support': 'fe7b408aef29aa851ff0710e25bc50cc51002342c369afac0d04c15395b962d2'},
                                              'support_digest': '8172955c737b6f55f83aaebcdea5c22566f06a14320bd3fd967054da0fd6c51c'}})
# Original Market Memory review: verified dispatch and immutable source witnesses.
# See rollout/market_memory_l0_original_scope.json; this adds no lifecycle effect.
PLAIN_SCOPES.update({'mm-l0-price-metadata-review-20261015-01a1333c-v1': {'destination': '/Volumes/Mastermind/evidence/market-memory-20261012-01a1333c/retained-returns/mm-l0-price-metadata-review-20261015-01a1333c-v1-collection-v1',
                                                      'host': 'ubuntu1',
                                                      'lease_witness': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/mm-l0-price-metadata-review-20261015-01a1333c-v1.lease.kPZhMS',
                                                                        'sha256': '70ba6a698a49d7401611ef5ab5cf6f2f64f10355329d6593f38a76b3d3f5887b'},
                                                      'mode': 'qwen',
                                                      'packet_path': '/Volumes/Mastermind/evidence/market-memory-20261012-01a1333c/integration/L0_PRICE_METADATA_REVIEW_PACKET.txt',
                                                      'packet_sha256': 'baf0b1e363b85a22796086029202e6b2e8330d21f4caa6b78a02d40c2916d197',
                                                      'parent': '01a1333c-a475-7052-95a8-72c623fb12e1',
                                                      'requested_model': 'qwen3.8-max',
                                                      'root': '01a1333c-a475-7052-95a8-72c623fb12e1',
                                                      'source_pins': {'log': 'b1a89114c36ed8133306a4c654e0995ae2799d9bc77fcf64a24d0d7698c3b954',
                                                                      'support': 'fe7b408aef29aa851ff0710e25bc50cc51002342c369afac0d04c15395b962d2'},
                                                      'support_digest': '8172955c737b6f55f83aaebcdea5c22566f06a14320bd3fd967054da0fd6c51c'}})
BINDING_SCHEMA = 'mastermind.original_delivery_binding.v1'
PLAIN_BINDING_SCHEMA = 'mastermind.fabric_plain_launch_binding.v1'
RECEIPT_SCHEMA = 'mastermind.original_delivery_receipt.v1'
MAX_STDOUT = 8 * 1024 * 1024
MAX_RESPONSE = 14 * 1024 * 1024
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')


class OriginalDeliveryRefused(ValueError):
    """Sanitized original read refusal; never an invitation to retry."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def reject_failure_envelope(row, request, schema):
    if type(row) is not dict or row.get('state') != 'UNAVAILABLE':
        return
    allowed = {'read_request_invalid','read_contract_invalid','directory_owner_or_mode',
        'directory_chain_changed','original_file_owner_mode_type_or_size',
        'original_file_changed','original_rc_invalid','original_artifact_unavailable',
        'filesystem_refused'}
    if (set(row) != {'schema','request_sha256','state','files','artifacts','reason'}
            or row['schema'] != schema or row['request_sha256'] != sha(canonical(request))
            or row['files'] != {} or row['artifacts'] != []
            or type(row['reason']) is not str or row['reason'] not in allowed):
        raise ValueError('collection_failure_envelope_invalid')
    raise OriginalDeliveryRefused(row['reason'])


def canonical(value):
    return reader.canonical(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require_caller(root):
    # Actual invoking root must be independently verified by its original
    # owner. This check prevents an accidental child/new-root substitution; it
    # does not turn mutable environment labels into authenticated authority.
    if (not IDENT.fullmatch(root) or os.environ.get('CODEX_THREAD_ID') != root
            or os.environ.get('POOL_ORCHESTRATOR_ID', root) != root):
        raise ValueError('original_native_root_required')


def verify_plain_lease_witness(run_id, plain):
    # A local unchanged witness only. Never return its value, touch the lease,
    # infer its settlement, or transmit it to the retained-result reader.
    if plain is None or 'lease_witness' not in plain:
        return
    witness = plain['lease_witness']
    if (type(witness) is not dict or set(witness) != {'path', 'sha256'}
            or type(witness['path']) is not str or type(witness['sha256']) is not str
            or not HEX.fullmatch(witness['sha256'])):
        raise ValueError('plain_original_lease_witness_invalid')
    path = Path(witness['path'])
    if (path.parent != delivery.owner_path(HERE/'state/remote_sub', HERE)
            or not re.fullmatch(re.escape(run_id) + r'\.lease\.[A-Za-z0-9_]+', path.name)):
        raise ValueError('plain_original_lease_witness_invalid')
    if sha(delivery.local_file(path, 4096)) != witness['sha256']:
        raise ValueError('plain_original_lease_witness_changed')


# Retained controller control-plane events. Every one of them must appear
# exactly once, in exactly this order, for a NEW plain run to qualify.
TRACKED_EVENT_NAMES = ('RUN_RESERVED', 'LEASE_OK', 'SUPPORT_VERSION_READY',
                       'TRANSPORT_VERIFIED', 'LAUNCH_BINDING', 'LAUNCH_ATTEMPT',
                       'LAUNCH')
PLAIN_TRANSPORT_FIELDS = {'packet_sha256', 'support_digest', 'policy_sha256',
                          'files', 'lease_id', 'account',
                          'acquire_response_sha256', 'phase', 'verified_at'}
FORBIDDEN_LOG_MARKERS = ('REFUSED', 'FAILED', 'EFFECT_UNKNOWN', 'UNPROVEN',
                         'LEASE_PRESERVED')


def tracked_control_events(events):
    """Classify retained log events by tracked name, preserving file order."""
    tracked=[]
    for event in events:
        for name in TRACKED_EVENT_NAMES:
            if event.startswith(name+' '):
                tracked.append((name,event)); break
    return tracked


def validate_plain_transport(record):
    """Strict bounded shape and cross-binding of the transport receipt view."""
    transport=record.get('transport') if type(record) is dict else None
    if (type(transport) is not dict or set(transport)!=PLAIN_TRANSPORT_FIELDS
            or transport['packet_sha256']!=record['packet_sha256']
            or transport['support_digest']!=record['support_digest']
            or transport['lease_id']!=record['lease_id']
            or transport['account']!=record['account']
            or transport['acquire_response_sha256']!=record['acquire_response_sha256']
            or transport['phase']!='PRE_LAUNCH'
            or type(transport['policy_sha256']) is not str or not HEX.fullmatch(transport['policy_sha256'])
            or type(transport['verified_at']) is not str
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z',transport['verified_at'])
            or type(transport['files']) is not dict or not 1<=len(transport['files'])<=256
            or any(type(n) is not str or not n or Path(n).name!=n
                   or type(v) is not str or not HEX.fullmatch(v)
                   for n,v in transport['files'].items())):
        raise ValueError('plain_launch_binding_invalid')
    return transport


def retained_plain_binding(events, value, source):
    """Qualify one NEW ordinary plain run only from its retained record.

    Exactly one LAUNCH_BINDING line in this same producer log — written by the
    original controller before the worker started — is the only source of the
    plain contract. Labels, the binding file and PLAIN_SCOPES never mint one,
    and a missing or duplicated record leaves the run unqualified (fail closed).

    The record must carry the actual prelaunch transport verification (exact
    packet/support/acquire readback), and the retained log must be the complete
    strict sequence RUN_RESERVED → LEASE_OK → SUPPORT_VERSION_READY →
    TRANSPORT_VERIFIED → LAUNCH_BINDING → LAUNCH → LAUNCH_ATTEMPT attempt=1,
    each exactly once in that order with no foreign, moved, duplicate or failed
    event. A crash cut before the acquire, after an unconfirmed transfer, or
    after a confirmed transfer but before the fsynced binding leave a log that
    cannot qualify the run. Later controller/lease uncertainty does not undo
    this original evidence or settle lifecycle state. The acquire observation is validated by
    reconstructing the exact acquired bytes from the record itself; a current
    broker row would be mutable, post-hoc state and is never consulted.
    """
    log_text=source['log'].decode('utf-8')
    if not log_text.endswith('\n'):
        raise ValueError('plain_launch_binding_log_truncated')
    launch_index=next((i for i,event in enumerate(events) if event.startswith('LAUNCH ')),len(events))
    if any(marker in event for event in events[:launch_index]
           for marker in FORBIDDEN_LOG_MARKERS):
        raise ValueError('plain_launch_binding_forbidden_event')
    records=[e[len('LAUNCH_BINDING '):] for e in events if e.startswith('LAUNCH_BINDING ')]
    if len(records)!=1:
        # A pure crash cut before the confirmed transfer leaves the run simply
        # unqualified. But a log that already shows a verified transfer or a
        # launch while the single retained record is missing, moved or
        # duplicated is a broken evidence sequence, never a qualification.
        if len(records)>1 or any(name in ('TRANSPORT_VERIFIED','LAUNCH_BINDING',
                                          'LAUNCH','LAUNCH_ATTEMPT')
                                 for name,_ in tracked_control_events(events)):
            raise ValueError('plain_launch_binding_event_sequence_invalid')
        return None
    record=reader.strict_json(records[0].encode('utf-8'))
    fields={'schema','run_id','root','parent','host','mode','requested_model','pool',
            'lease_id','account','packet_sha256','support_digest',
            'acquire_response_sha256','source','phase','transport'}
    if (type(record) is not dict or set(record)!=fields
            or record['schema']!=PLAIN_BINDING_SCHEMA
            or record['source']!='controller_original_acquire_return'
            or record['phase']!='PRE_LAUNCH'
            or any(record[k]!=value[k] for k in ('run_id','root','parent','host','mode','requested_model'))
            or record['mode'] not in production.ORDINARY_MODES
            or record['pool']!={'glm':'glm','qwen':'bailian'}[record['mode']]
            or value['artifact_names']!=[]
            or any(type(record[k]) is not str or not IDENT.fullmatch(record[k])
                   for k in ('run_id','root','parent','host','requested_model','lease_id','account'))
            or any(type(record[k]) is not str or not HEX.fullmatch(record[k])
                   for k in ('packet_sha256','support_digest','acquire_response_sha256'))):
        raise ValueError('plain_launch_binding_invalid')
    transport=validate_plain_transport(record)
    if record['packet_sha256']!=sha(source['packet']):
        raise ValueError('plain_launch_binding_packet_mismatch')
    reconstructed=(f'LEASE={record["lease_id"]} ACCOUNT={record["account"]}'.encode('ascii'),
                   f'LEASE={record["lease_id"]} ACCOUNT={record["account"]}\n'.encode('ascii'))
    if record['acquire_response_sha256'] not in {sha(raw) for raw in reconstructed}:
        raise ValueError('plain_launch_binding_acquire_unverified')
    expected=[
        'RUN_RESERVED explicit=1',
        'LEASE_OK pool='+record['pool'],
        'SUPPORT_VERSION_READY digest='+record['support_digest']
            +' policy='+transport['policy_sha256'],
        'TRANSPORT_VERIFIED packet='+record['packet_sha256']
            +' support='+record['support_digest']
            +' policy='+transport['policy_sha256']
            +' lease='+record['lease_id']
            +' account='+record['account']
            +' acquire='+record['acquire_response_sha256'],
        'LAUNCH_BINDING '+records[0],
        f"LAUNCH stdout=lanes_{record['run_id']}.stdout"
            +f" rc_file=ext/lanes_{record['run_id']}.rc cwd=~",
        'LAUNCH_ATTEMPT attempt=1',
    ]
    if [event for _name,event in tracked_control_events(events)]!=expected:
        raise ValueError('plain_launch_binding_event_sequence_invalid')
    record['binding_sha256']=sha(records[0].encode('utf-8'))
    return record


def load_binding(path, *, run_id, root, parent):
    require_caller(root)
    raw = delivery.local_file(Path(path), 65536)
    value = reader.strict_json(raw)
    fields = {'schema','run_id','root','parent','host','mode','requested_model',
              'cwd','artifact_names','sources'}
    if (type(value) is not dict or set(value) != fields or value['schema'] != BINDING_SCHEMA
            or any(value[k] != v for k,v in {'run_id':run_id,'root':root,'parent':parent}.items())
            or any(type(value[k]) is not str or not IDENT.fullmatch(value[k])
                   for k in ('run_id','root','parent','host','requested_model'))
            or value['mode'] not in production.ORDINARY_MODES | {'minimax'} or value['cwd'] != '~'
            or type(value['sources']) is not dict or set(value['sources']) != {'packet','log','support'}):
        raise ValueError('original_binding_invalid')
    plain = PLAIN_SCOPES.get(run_id)
    verify_plain_lease_witness(run_id, plain)
    if (value['mode'] == 'minimax' or plain is not None) and (plain is None
            or value['mode'] != plain.get('mode', 'minimax') or value['artifact_names'] != []
            or value['requested_model'] != plain.get('requested_model', 'MiniMax-M3')
            or any(value[k] != plain[k] for k in ('root','parent','host'))):
        raise ValueError('plain_original_scope_unqualified')
    source = {}
    for name, item in value['sources'].items():
        if (type(item) is not dict or set(item) != {'path','sha256'}
                or type(item['sha256']) is not str or not HEX.fullmatch(item['sha256'])):
            raise ValueError('original_source_pin_invalid')
        p = Path(item['path'])
        if name == 'packet' and plain is not None:
            allowed_path = str(p) == plain['packet_path'] and item['sha256'] == plain['packet_sha256']
        else:
            allowed_path = (delivery.owner_path(p, HERE).parent ==
                            delivery.owner_path(HERE/'state/remote_sub', HERE) and
                ((name == 'packet' and (p.name == run_id + '.request.packet'
                                        or re.fullmatch(re.escape(run_id)+r'\.packet\.[A-Za-z0-9_]+',p.name))) or
                 (name != 'packet' and p.name == run_id + ('.log' if name=='log' else '.support.json'))))
        if not allowed_path:
            raise ValueError('original_source_path_invalid')
        data = delivery.local_file(p, 2 * 1024 * 1024)
        if (plain is not None and name in plain.get('source_pins', {})
                and item['sha256'] != plain['source_pins'][name]):
            raise ValueError('plain_original_source_pin_changed')
        if sha(data) != item['sha256']:
            raise ValueError('original_source_changed')
        source[name] = data
    manifest = reader.strict_json(source['support'])
    if (type(manifest) is not dict or not manifest
            or any(type(k) is not str or type(v) is not str or not HEX.fullmatch(v)
                   for k,v in manifest.items())):
        raise ValueError('original_support_mismatch')
    original_validator = None
    if plain is None or plain.get('mode') == 'qwen':
        original_validator = delivery.original_validator_context(manifest)
    validator = original_validator if original_validator is not None else production
    contract = validator.parse_packet(source['packet'].decode('utf-8'))
    if contract is not None and plain is None and re.fullmatch(
            re.escape(run_id)+r'\.packet\.[A-Za-z0-9_]+',
            Path(value['sources']['packet']['path']).name) is None:
        # Existing artifact runs keep their exact <run>.packet.* retention
        # naming; the plain <run>.request.packet name never qualifies one.
        raise ValueError('original_source_path_invalid')
    if plain is not None:
        if contract is not None:
            raise ValueError('plain_original_artifact_contract_conflict')
        contract = dict(schema=PLAIN_SCHEMA, run_id=run_id, root=root, parent=parent,
            names=[], packet_sha256=plain['packet_sha256'], support_digest=plain['support_digest'])
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(run_id)
              + r' host=' + re.escape(value['host']) + r'\] (.*)')
    events=[]
    for line in source['log'].decode('utf-8').splitlines():
        match = re.fullmatch(prefix,line)
        if match: events.append(match[1])
        elif '[remote_sub id=' in line: raise ValueError('original_log_scope_mismatch')
    plain_binding = None
    if contract is None:
        # Old plaintext packets have no producer-bound root/parent/digest.
        # Do not manufacture that missing provenance from this new binding: a
        # future ordinary plain run qualifies only through the controller's
        # retained prelaunch record in this same producer log.
        plain_binding = retained_plain_binding(events, value, source)
        if plain_binding is None:
            raise ValueError('original_producer_contract_unavailable')
        if Path(value['sources']['packet']['path']).name != run_id + '.request.packet':
            # A NEW plain run qualifies only through its retained original
            # <run>.request.packet; artifact-style pin names never carry one.
            raise ValueError('plain_launch_binding_source_pin_invalid')
        contract = dict(schema=PLAIN_SCHEMA, run_id=run_id, root=root, parent=parent,
            names=[], packet_sha256=plain_binding['packet_sha256'],
            support_digest=plain_binding['support_digest'],
            binding_sha256=plain_binding['binding_sha256'],
            acquire_response_sha256=plain_binding['acquire_response_sha256'])
    if (any(contract[k] != value[k] for k in ('run_id','root','parent'))
            or contract['names'] != value['artifact_names']):
        raise ValueError('original_packet_scope_mismatch')
    if sha(canonical({'schema':'remote-support-code.v1','files':manifest})) != contract['support_digest']:
        raise ValueError('original_support_mismatch')
    # Ordinary runs use the explicitly bound, full-hash-qualified validator.
    # Preserve the incumbent plaintext scope's installed-source check unchanged.
    if plain is not None and plain.get('mode', 'minimax') == 'minimax':
        for name in ('artifact_production.py','artifact_reader.py'):
            if manifest.get(name) != sha(delivery.local_file(HERE/name, 128*1024)):
                raise ValueError('original_producer_validator_changed')
    if plain is not None and any(e.startswith('LAUNCH_BINDING ') for e in events):
        # Historical scopes keep their exact evidence set; a retained prelaunch
        # binding never qualifies older missing evidence.
        raise ValueError('plain_launch_binding_unexpected')
    launches=[e for e in events if e.startswith('LAUNCH ')]
    support=[e for e in events if e.startswith('SUPPORT_VERSION_READY ')]
    if (launches != [f'LAUNCH stdout=lanes_{run_id}.stdout rc_file=ext/lanes_{run_id}.rc cwd=~']
            or [e for e in events if e.startswith('LAUNCH_ATTEMPT ')] != ['LAUNCH_ATTEMPT attempt=1']
            or len(support)!=1 or not re.fullmatch('SUPPORT_VERSION_READY digest='+contract['support_digest']+r' policy=[a-f0-9]{64}',support[0])
            or [e for e in events if e.startswith('LEASE_OK ')] != ['LEASE_OK pool='+{'glm':'glm','qwen':'bailian','minimax':'minimax'}[value['mode']]]):
        raise ValueError('original_launch_evidence_unqualified')
    delivery.assert_capsule_family(run_id)
    registry_raw=delivery.local_file(HERE/'hosts.json')
    registry=reader.strict_json(registry_raw)
    host=registry.get(value['host']) if type(registry) is dict else None
    if (type(host) is not dict or value['mode'] not in host.get('allowed_modes',[])
            or type(host.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',host['ssh_alias'])):
        raise ValueError('original_host_registry_unavailable')
    return value, raw, source, contract, host['ssh_alias'], registry_raw, original_validator, plain_binding


def remote_read(request, *, home=None):
    """Fixed read-only paths. home is an inert-test seam, never in the request."""
    if (type(request) is not dict or set(request) != {'schema','run_id','root','parent','host','contract'}
            or request['schema'] != SCHEMA
            or any(type(request[k]) is not str or not IDENT.fullmatch(request[k])
                   for k in ('run_id','root','parent','host'))):
        raise ValueError('read_request_invalid')
    contract=request['contract']
    plain = contract.get('schema') == PLAIN_SCHEMA if type(contract) is dict else False
    if request['run_id'] in PLAIN_SCOPES and not plain:
        raise ValueError('read_contract_invalid')
    if plain:
        expected = PLAIN_SCOPES.get(rid := request['run_id'])
        if expected is not None:
            if (any(request[k] != expected[k] for k in ('root','parent','host'))
                    or contract != dict(schema=PLAIN_SCHEMA, run_id=rid, root=expected['root'],
                        parent=expected['parent'], names=[], packet_sha256=expected['packet_sha256'],
                        support_digest=expected['support_digest'])):
                raise ValueError('read_contract_invalid')
        else:
            # New producer-bound plain group. The remote reader never consults
            # a local scope table: it re-verifies the contract's own scope, the
            # transported packet digest below, and that the contract is bound
            # to a retained prelaunch binding digest and to the host's actual
            # published support generation.
            if (set(contract) != {'schema','run_id','root','parent','names','packet_sha256',
                                  'support_digest','binding_sha256','acquire_response_sha256'}
                    or any(contract[k] != request[k] for k in ('run_id','root','parent'))
                    or contract['names'] != []
                    or any(type(contract[k]) is not str or not HEX.fullmatch(contract[k])
                           for k in ('packet_sha256','support_digest','binding_sha256',
                                     'acquire_response_sha256'))):
                raise ValueError('read_contract_invalid')
    # Local original source qualification validates the full contract. Recheck
    # path-bearing fields here before deriving exact artifact names remotely.
    if not plain and (type(contract) is not dict or set(contract) != {'schema','run_id','root','parent','names','body_sha256','support_digest'}
            or contract['schema'] != 'mastermind.fabric_artifact_production.v1'
            or any(contract[k]!=request[k] for k in ('run_id','root','parent'))
            or type(contract['names']) is not list or not 1<=len(contract['names'])<=8
            or len(set(contract['names']))!=len(contract['names'])
            or any(type(n) is not str or not reader.COMPONENT.fullmatch(n) or n in {'request.json','receipt.json'} for n in contract['names'])
            or any(type(contract[k]) is not str or not HEX.fullmatch(contract[k]) for k in ('body_sha256','support_digest'))):
        raise ValueError('read_contract_invalid')
    root=Path(home if home is not None else pwd.getpwuid(os.geteuid()).pw_dir)
    rid=request['run_id']; held=[]
    def read(chain,name,limit):
        chain.verify()
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        held.append((chain,name,fd,None))
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_nlink!=1 or before.st_mode&0o022 or not 0<before.st_size<=limit):
            raise ValueError('original_file_owner_mode_type_or_size')
        data=b''
        while len(data)<=limit:
            part=os.read(fd,min(65536,limit+1-len(data)))
            if not part:break
            data+=part
        ident=reader.identity(before)
        held[-1]=(chain,name,fd,ident)
        if len(data)!=before.st_size:raise ValueError('original_file_changed')
        return {'bytes':len(data),'sha256':sha(data),'data_base64':base64.b64encode(data).decode()}
    def verify():
        for chain,name,fd,ident in held:
            chain.verify()
            if ident is None or ident!=reader.identity(os.fstat(fd)) or ident!=reader.identity(os.stat(name,dir_fd=chain.fd,follow_symlinks=False)):
                raise ValueError('original_file_changed')
    result={'schema':SCHEMA,'request_sha256':sha(canonical(request)),'state':'PENDING','files':{},'artifacts':[]}
    packet_dir = None
    release_chains = []
    try:
        if plain:
            packet_dir = DirectoryChain(root/'lanes/tmp')
            packet = read(packet_dir, rid+'.txt', 2*1024*1024)
            if packet['sha256'] != contract['packet_sha256']:
                raise ValueError('read_contract_invalid')
            if type(contract.get('binding_sha256')) is str:
                # Verify the contract's support generation against the host's
                # published release directory; a plain contract never qualifies
                # a run whose support version was never published. The full
                # published generation is checked — RELEASE.json must carry the
                # contract's exact digest and every published code file must
                # still hash to its manifest entry — not just a nonempty
                # remote_sub_exec file.
                try:
                    release_base=DirectoryChain(root/'lanes/support-releases'
                                                /contract['support_digest'])
                    release_ext=DirectoryChain(root/'lanes/support-releases'
                                               /contract['support_digest']/'ext')
                except (FileNotFoundError,NotADirectoryError):
                    raise ValueError('read_contract_invalid')
                release_chains.extend((release_base,release_ext))
                try:
                    release_raw=read(release_base,'RELEASE.json',65536)
                except FileNotFoundError:
                    release_base.verify();raise ValueError('read_contract_invalid')
                release_meta=reader.strict_json(base64.b64decode(
                    release_raw['data_base64'],validate=True))
                files=release_meta.get('files') if type(release_meta) is dict else None
                if (type(files) is not dict or not 1<=len(files)<=256
                        or release_meta.get('digest')!=contract['support_digest']
                        or sha(canonical({'schema':'remote-support-code.v1','files':files}))!=contract['support_digest']
                        or any(type(n) is not str or not n or Path(n).name!=n
                               or type(v) is not str or not HEX.fullmatch(v)
                               for n,v in files.items())):
                    raise ValueError('read_contract_invalid')
                for name,want in files.items():
                    release_ext.verify()
                    support_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=release_ext.fd)
                    held.append((release_ext,name,support_fd,None))
                    info=os.fstat(support_fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                            or info.st_nlink!=1 or info.st_mode&0o022
                            or not 0<info.st_size<=2*1024*1024):
                        raise ValueError('read_contract_invalid')
                    code=b''
                    while len(code)<=2*1024*1024:
                        part=os.read(support_fd,min(65536,2*1024*1024+1-len(code)))
                        if not part:break
                        code+=part
                    held[-1]=(release_ext,name,support_fd,reader.identity(info))
                    if len(code)!=info.st_size or sha(code)!=want:
                        raise ValueError('read_contract_invalid')
                release_ext.verify()
            verify()
        with DirectoryChain(root/'lanes/ext') as ext:
            try: rc=read(ext,'lanes_'+rid+'.rc',32)
            except FileNotFoundError:
                ext.verify();return result
            rcraw=base64.b64decode(rc['data_base64'],validate=True)
            if not re.fullmatch(rb'(0|[1-9][0-9]{0,2})\n?',rcraw) or int(rcraw)>255:
                raise ValueError('original_rc_invalid')
            result['files']['rc']=rc
            if int(rcraw)!=0:
                verify();result['state']='NONZERO';return result
            with DirectoryChain(root/'lanes/ext/lanes') as lanes:
                result['files']['process']=read(lanes,rid+'.process.jsonl',65536)
                result['files']['stdout']=read(ext,'lanes_'+rid+'.stdout',MAX_STDOUT)
                scope={k:request[k] for k in ('root','parent','run_id')}
                directory='/tmp/fabric-'+sha(canonical(scope))[:40]
                remaining=reader.MAX_TOTAL
                for name in contract['names']:
                    item=reader.read_one(directory+'/'+name,remaining)
                    if item.get('status')!='RETRIEVED':raise ValueError('original_artifact_unavailable')
                    remaining-=item['bytes'];result['artifacts'].append(item)
                verify();result['state']='READ';return result
    finally:
        for _chain,_name,fd,_ident in reversed(held):os.close(fd)
        for _chain in release_chains:_chain.close()
        if packet_dir is not None:packet_dir.close()


def remote_envelope(request):
    try:
        return remote_read(request)
    except (OSError, ValueError, TypeError, KeyError) as error:
        reason = str(error) if isinstance(error, ValueError) else 'filesystem_refused'
        allowed = {'read_request_invalid','read_contract_invalid','directory_owner_or_mode',
            'directory_chain_changed','original_file_owner_mode_type_or_size',
            'original_file_changed','original_rc_invalid','original_artifact_unavailable'}
        return {'schema':SCHEMA,'request_sha256':sha(canonical(request)),
            'state':'UNAVAILABLE','files':{},'artifacts':[],
            'reason':reason if reason in allowed else 'filesystem_refused'}


def code_for_request(request):
    # Fixed reviewed code, not caller-selected commands/paths/imports. The same
    # incumbent bounded SSH reader transports it; no remote write or probe.
    source=delivery.local_file(HERE/'artifact_reader.py',65536).decode()
    code='import base64, hashlib, json, os, pwd, re, stat, sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
    code+="_reader_ns={'__name__':'fixed_original_artifact_reader'}\nexec("+repr(source)+",_reader_ns)\nreader=SimpleNamespace(**_reader_ns)\n"
    remote_scopes = {key: {field: scope[field] for field in (
        'root', 'parent', 'host', 'packet_sha256', 'support_digest')}
        for key, scope in PLAIN_SCOPES.items()}
    code+='PLAIN_SCHEMA='+repr(PLAIN_SCHEMA)+'\nPLAIN_SCOPES='+repr(remote_scopes)+'\n'
    code+='SCHEMA='+repr(SCHEMA)+'\nMAX_STDOUT='+str(MAX_STDOUT)+'\nIDENT=re.compile('+repr(IDENT.pattern)+')\nHEX=re.compile('+repr(HEX.pattern)+')\n'
    code+=delivery.remote_directory_chain_source()+'\n'+inspect.getsource(canonical)+'\n'+inspect.getsource(sha)+'\n'+inspect.getsource(remote_read)+'\n'+inspect.getsource(remote_envelope)
    code+="\ntry:\n raw=sys.stdin.buffer.read(65537)\n if len(raw)>65536:raise ValueError('request_limit')\n request=reader.strict_json(raw)\n result=remote_envelope(request)\n sys.stdout.buffer.write(canonical(result))\nexcept (OSError,ValueError,TypeError,KeyError):\n raise SystemExit(76)\n"
    return code


def validate_response(raw,request,mode,*,original_validator=None):
    if len(raw)>MAX_RESPONSE:raise ValueError('collection_response_limit')
    row=reader.strict_json(raw)
    reject_failure_envelope(row, request, SCHEMA)
    if (type(row) is not dict or set(row)!={'schema','request_sha256','state','files','artifacts'}
            or row['schema']!=SCHEMA or row['request_sha256']!=sha(canonical(request))
            or type(row['files']) is not dict or type(row['artifacts']) is not list):
        raise ValueError('collection_response_invalid')
    if row['state']=='PENDING' and row['files']=={} and row['artifacts']==[]:
        return None
    if row['state']!='READ' or set(row['files'])!={'rc','process','stdout'}:
        raise ValueError('original_terminal_delivery_unqualified')
    blobs={}
    for name,limit in [('rc',32),('process',65536),('stdout',MAX_STDOUT)]:
        item=row['files'][name]
        if type(item) is not dict or set(item)!={'bytes','sha256','data_base64'}:
            raise ValueError('collection_file_invalid')
        data=base64.b64decode(item['data_base64'],validate=True)
        if type(item['bytes']) is not int or not 0<len(data)<=limit or len(data)!=item['bytes'] or sha(data)!=item['sha256']:
            raise ValueError('collection_file_integrity')
        blobs[name]=data
    if blobs['rc'] not in (b'0',b'0\n'):raise ValueError('collection_rc_mismatch')
    if request['contract'].get('schema') == PLAIN_SCHEMA:
        contract=request['contract']
        bound=type(contract) is dict and type(contract.get('binding_sha256')) is str
        plain=None if bound else PLAIN_SCOPES.get(request['run_id'])
        if ((plain is None and not bound) or row['artifacts']
                or (plain is not None and mode != plain.get('mode', 'minimax'))
                or (bound and mode not in production.ORDINARY_MODES)):
            raise ValueError('plain_artifact_conflict')
        delivery.validate_capsule_process(blobs['process'],blobs['stdout'],request['run_id'])
        process=reader.strict_json(blobs['process'])
        if process.get('stdout_sha256') != sha(blobs['stdout']) or 'artifact_production' in process:
            raise ValueError('plain_capture_digest_mismatch')
        return blobs,[],None
    manifest=delivery.validate_ordinary_producer(request,blobs['stdout'],blobs['process'],
        original_validator=original_validator)
    validator=original_validator if original_validator is not None else production
    process=reader.strict_json(blobs['process'])
    if (process['artifact_production']['contract']!=request['contract']
            or process['artifact_production']['mode']!=mode):raise ValueError('original_completion_scope_mismatch')
    artrequest={'schema':reader.SCHEMA,**{k:request[k] for k in ('root','parent','run_id','host')},
                'stdout_sha256':sha(blobs['stdout']),'paths':validator.paths(request['contract'])}
    artresponse={'schema':reader.SCHEMA,'request_sha256':sha(canonical(artrequest)),'files':row['artifacts']}
    artifacts=delivery.validate_response(canonical(artresponse),artrequest)
    if len(artifacts)!=len(manifest['files']):raise ValueError('original_artifact_count')
    for (meta,data), advertised in zip(artifacts,manifest['files']):
        if data is None or any(meta[k]!=advertised[k] for k in ('path','bytes','sha256')):
            raise ValueError('original_artifact_manifest_mismatch')
    return blobs,artifacts,manifest


class LocalBindingRefused(ValueError):
    """A local-only validation failure before destination reservation/transport."""


def collect(path,*,run_id,root,parent,destination):
    try:
        value,binding_raw,source,contract,alias,registry,original_validator,plain_binding=load_binding(path,run_id=run_id,root=root,parent=parent)
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
        raise LocalBindingRefused(str(error)) from error
    if run_id in PLAIN_SCOPES and str(destination)!=PLAIN_SCOPES[run_id]['destination']:
        raise ValueError('plain_original_destination_changed')
    request={'schema':SCHEMA,**{k:value[k] for k in ('run_id','root','parent','host')},'contract':contract}
    # Reserve before transport. Existing path refuses, so a crashed publication
    # cannot silently repeat the remote observation using that destination.
    with delivery.reserve_destination(destination) as chain:
        delivery.write_exclusive(chain.fd,'read-request.json',canonical(request))
        try:
            response=delivery.transport(alias,request)
        except (OSError,ValueError) as error:
            allowed={'transport_timeout','transport_output_limit','transport_unavailable'}
            reason=str(error) if str(error) in allowed else 'transport_refused'
            delivery.write_exclusive(chain.fd,'transport-failure.json',canonical(
                {'state':'UNAVAILABLE','reason':reason,'retry_authorized':False}))
            raise
        if len(response)>MAX_RESPONSE:raise ValueError('collection_response_limit')
        # Retain the exact untrusted response even when qualification refuses.
        # These new evidence files are never copied over an original run file.
        for index,offset in enumerate(range(0,len(response),reader.MAX_FILE)):
            delivery.write_exclusive(chain.fd,f'read-response.{index:03d}',response[offset:offset+reader.MAX_FILE])
        verified=validate_response(response,request,value['mode'],original_validator=original_validator)
        def verify_source():
            current=load_binding(path,run_id=run_id,root=root,parent=parent)
            if (current[1:4]!=(binding_raw,source,contract) or current[5]!=registry
                    or current[7]!=plain_binding):
                raise ValueError('original_source_changed_during_collection')
        verify_source()
        receipt={'schema':RECEIPT_SCHEMA,**{k:value[k] for k in ('run_id','root','parent','host','mode')},
            'binding_sha256':sha(binding_raw),'request_sha256':sha(canonical(request)),
            'response_sha256':sha(response),'state':'PENDING' if verified is None else 'COMPLETE',
            'delivery_verified':verified is not None,'worker_terminal_proof':verified is not None,
            'lease_settlement':'UNKNOWN','controller_state':'UNKNOWN','acceptance':'NOT_RECORDED',
            'original_operation_mutated':False,'files':[],'stdout_chunks':[], 'artifacts':[]}
        if run_id in PLAIN_SCOPES:
            receipt['plain_provenance']={
                'scope':'retained_packet_and_process_capture_at_collection',
                'producer_root_authenticated':False,
                'producer_packet_consumption_attested':False,
                'served_model_and_historical_physical_host_authenticated':False}
        if plain_binding is not None:
            # New producer-bound plain group: retain the controller's prelaunch
            # record and the exact digests it bound. Honest flags only — this is
            # retained correlation evidence, never authentication or acceptance.
            receipt['requested_model']=value['requested_model']
            receipt['plain_launch_binding']=plain_binding
            receipt['plain_provenance']={
                'scope':'retained_prelaunch_binding_and_remote_packet_capture',
                'binding_sha256':plain_binding['binding_sha256'],
                'packet_sha256':plain_binding['packet_sha256'],
                'support_digest':plain_binding['support_digest'],
                'acquire_response_sha256':plain_binding['acquire_response_sha256'],
                'producer_root_authenticated':False,
                'producer_packet_consumption_attested':False,
                'served_model_and_historical_physical_host_authenticated':False}
        def save(name,data):
            delivery.write_exclusive(chain.fd,name,data)
            receipt['files'].append({'local_name':name,'bytes':len(data),'sha256':sha(data)})
        save('binding.json',binding_raw)
        if verified is not None:
            blobs,artifacts,manifest=verified
            for index,offset in enumerate(range(0,len(blobs['stdout']),reader.MAX_FILE)):
                name=f'stdout.{index:03d}';save(name,blobs['stdout'][offset:offset+reader.MAX_FILE]);receipt['stdout_chunks'].append(name)
            receipt['stdout_sha256']=sha(blobs['stdout']);receipt['stdout_bytes']=len(blobs['stdout'])
            save('process.json',blobs['process']);save('returncode.txt',blobs['rc'])
            for index,(meta,data) in enumerate(artifacts):
                name=f'artifact.{index:02d}';save(name,data)
                receipt['artifacts'].append({**meta,'local_name':name})
            receipt['artifact_manifest']=manifest
        delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=verify_source)
        # publish_receipt invalidates its own created inode on a failed guard.
        if receipt['state']=='UNAVAILABLE':raise ValueError('collection_publication_unconfirmed')
        return receipt


def read_collection(path,*,expected_sha256,run_id,root,parent):
    require_caller(root)
    plain = PLAIN_SCOPES.get(run_id)
    if plain is not None and (str(path) != str(Path(plain['destination'])/'receipt.json')
            or root != plain['root'] or parent != plain['parent']):
        raise ValueError('plain_collection_scope_mismatch')
    verify_plain_lease_witness(run_id, plain)
    raw=delivery.local_file(Path(path),65536)
    if sha(raw)!=expected_sha256:raise ValueError('collection_receipt_changed')
    receipt=reader.strict_json(raw)
    if (receipt.get('schema')!=RECEIPT_SCHEMA or receipt.get('state')!='COMPLETE'
            or receipt.get('delivery_verified') is not True or receipt.get('worker_terminal_proof') is not True
            or any(receipt.get(k)!=v for k,v in {'root':root,'parent':parent,'run_id':run_id}.items())
            or receipt.get('original_operation_mutated') is not False):
        raise ValueError('collection_not_verified')
    chunks=receipt['stdout_chunks']
    if (not isinstance(chunks,list) or not 1<=len(chunks)<=32
            or chunks!=[f'stdout.{i:03d}' for i in range(len(chunks))]):raise ValueError('collection_chunks_invalid')
    record=receipt.get('plain_launch_binding') if type(receipt.get('plain_launch_binding')) is dict else None
    plain_shape=(plain is None and record is not None
                 and receipt.get('artifacts')==[] and receipt.get('artifact_manifest') is None)
    if plain_shape:
        # New producer-bound plain group. Scope comes from the receipt's
        # retained record plus the caller's verified root/parent; no local
        # PLAIN_SCOPES entry is consulted.
        if (record.get('schema')!=PLAIN_BINDING_SCHEMA
                or record.get('source')!='controller_original_acquire_return'
                or record.get('phase')!='PRE_LAUNCH'
                or any(record.get(k)!=v for k,v in {
                    'run_id':run_id,'root':root,'parent':parent,
                    'host':receipt.get('host'),'mode':receipt.get('mode'),
                    'requested_model':receipt.get('requested_model')}.items())
                or record.get('mode') not in production.ORDINARY_MODES
                or record.get('pool')!={'glm':'glm','qwen':'bailian'}[record['mode']]
                or any(type(record.get(k)) is not str or not IDENT.fullmatch(record[k])
                       for k in ('run_id','root','parent','host','requested_model','lease_id','account'))
                or any(type(record.get(k)) is not str or not HEX.fullmatch(record[k])
                       for k in ('packet_sha256','support_digest','acquire_response_sha256'))
                or type(record.get('binding_sha256')) is not str
                or not HEX.fullmatch(record['binding_sha256'])):
            raise ValueError('plain_collection_binding_invalid')
        # The retained record must still carry the exact prelaunch transport
        # verification bound to the same packet/support/acquire observation.
        validate_plain_transport(record)
        provenance=receipt.get('plain_provenance')
        if (type(provenance) is not dict
                or set(provenance)!={'scope','binding_sha256','packet_sha256','support_digest',
                                     'acquire_response_sha256','producer_root_authenticated',
                                     'producer_packet_consumption_attested',
                                     'served_model_and_historical_physical_host_authenticated'}
                or provenance['scope']!='retained_prelaunch_binding_and_remote_packet_capture'
                or provenance['binding_sha256']!=record['binding_sha256']
                or provenance['packet_sha256']!=record['packet_sha256']
                or provenance['support_digest']!=record['support_digest']
                or provenance['acquire_response_sha256']!=record['acquire_response_sha256']
                or provenance['producer_root_authenticated'] is not False
                or provenance['producer_packet_consumption_attested'] is not False
                or provenance['served_model_and_historical_physical_host_authenticated'] is not False):
            raise ValueError('plain_collection_provenance_invalid')
    if plain is not None or plain_shape:
        files=receipt.get('files')
        names=['binding.json',*chunks,'process.json','returncode.txt']
        expected_host=plain['host'] if plain is not None else record['host']
        expected_mode=plain.get('mode', 'minimax') if plain is not None else record['mode']
        if (receipt.get('host')!=expected_host or receipt.get('mode')!=expected_mode
                or receipt.get('artifacts')!=[] or receipt.get('artifact_manifest') is not None
                or type(files) is not list or len(files)!=len(names)
                or any(type(item) is not dict or set(item)!={'local_name','bytes','sha256'}
                    or item['local_name']!=name or type(item['bytes']) is not int
                    or not 0<item['bytes']<=reader.MAX_FILE or type(item['sha256']) is not str
                    or not HEX.fullmatch(item['sha256']) for item,name in zip(files,names))):
            raise ValueError('plain_collection_files_or_scope_invalid')
    with delivery.DirectoryChain(Path(path).parent) as chain:
        delivery.verify_delivered(chain,receipt['files'])
        if plain is not None or plain_shape:
            binding_raw=delivery.read_local_at(chain,'binding.json',65536)
            binding=reader.strict_json(binding_raw)
            if plain is not None:
                expected={'schema':BINDING_SCHEMA,'run_id':run_id,'root':root,'parent':parent,
                    'host':plain['host'],'mode':plain.get('mode', 'minimax'),
                    'requested_model':plain.get('requested_model', 'MiniMax-M3'),
                    'cwd':'~','artifact_names':[]}
                packet_pin={'path':plain['packet_path'],'sha256':plain['packet_sha256']}
                exact_packet_pin=True
            else:
                expected={'schema':BINDING_SCHEMA,'run_id':run_id,'root':root,'parent':parent,
                    'host':record['host'],'mode':record['mode'],
                    'requested_model':record['requested_model'],
                    'cwd':'~','artifact_names':[]}
                packet_pin={'sha256':record['packet_sha256']}
                exact_packet_pin=False
            if (sha(binding_raw)!=receipt.get('binding_sha256') or type(binding) is not dict
                    or any(binding.get(k)!=v for k,v in expected.items())
                    or type(binding.get('sources')) is not dict
                    or not isinstance(binding['sources'].get('packet'),dict)
                    or binding['sources']['packet'].get('sha256')!=packet_pin['sha256']
                    or (exact_packet_pin and binding['sources']['packet']!=packet_pin)):
                raise ValueError('plain_collection_binding_invalid')
            if plain_shape:
                # Close the loop against the retained producer log: the
                # receipt's record must still match the one retained prelaunch
                # record pinned by this binding's log source.
                log_source=binding['sources'].get('log')
                if (type(log_source) is not dict or set(log_source)!={'path','sha256'}
                        or type(log_source['sha256']) is not str or not HEX.fullmatch(log_source['sha256'])
                        or delivery.owner_path(Path(log_source['path']), HERE) !=
                           delivery.owner_path(HERE/'state/remote_sub'/(run_id+'.log'), HERE)):
                    raise ValueError('plain_collection_source_pin_changed')
                log_raw=delivery.local_file(Path(log_source['path']), 2*1024*1024)
                if sha(log_raw)!=log_source['sha256']:
                    raise ValueError('plain_collection_source_pin_changed')
                retained_prefix=(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
                                 + re.escape(run_id) + r' host=' + re.escape(record['host'])
                                 + r'\] LAUNCH_BINDING (.*)')
                retained=[m.group(1) for m in (re.fullmatch(retained_prefix,line)
                          for line in log_raw.decode('utf-8').splitlines()) if m]
                if (len(retained)!=1
                        or sha(retained[0].encode('utf-8'))!=record['binding_sha256']
                        or dict(reader.strict_json(retained[0].encode('utf-8')),
                                binding_sha256=record['binding_sha256'])!=record):
                    raise ValueError('plain_collection_binding_invalid')
            for name, digest in (plain or {}).get('source_pins', {}).items():
                filename = run_id + ('.log' if name == 'log' else '.support.json')
                source = binding['sources'].get(name)
                if (type(source) is not dict or set(source) != {'path', 'sha256'}
                        or type(source['path']) is not str or source['sha256'] != digest
                        or delivery.owner_path(Path(source['path']), HERE) !=
                           delivery.owner_path(HERE/'state/remote_sub'/filename, HERE)):
                    raise ValueError('plain_collection_source_pin_changed')
        stdout=b''.join(delivery.read_local_at(chain,name,reader.MAX_FILE) for name in chunks)
        if len(stdout)!=receipt['stdout_bytes'] or sha(stdout)!=receipt['stdout_sha256']:
            raise ValueError('collection_stdout_integrity')
        chain.verify();return stdout


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    for name in ('root','parent'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--binding');parser.add_argument('--destination')
    parser.add_argument('--collection');parser.add_argument('--receipt-sha256')
    args=parser.parse_args(argv)
    try:
        if args.collection:
            if args.binding or args.destination or not args.receipt_sha256:raise ValueError('collection_arguments')
            sys.stdout.buffer.write(read_collection(args.collection,expected_sha256=args.receipt_sha256,
                run_id=args.run_id,root=args.root,parent=args.parent));return 0
        if not args.binding or not args.destination or args.receipt_sha256:raise ValueError('collection_arguments')
        receipt=collect(args.binding,run_id=args.run_id,root=args.root,parent=args.parent,destination=args.destination)
        print(canonical(receipt).decode());return 0 if receipt['state']=='COMPLETE' else 76
    except LocalBindingRefused as error:
        allowed={'directory_owner_or_mode','directory_chain_changed','directory_path_invalid',
                 'original_native_root_required'}
        reason=str(error) if str(error) in allowed else 'original_binding_unconfirmed'
        print(canonical({'state':'REFUSED','reason':reason,
            'failure_phase':'original_local_binding','remote_read_started':False,
            'destination_reserved':False,'retry_authorized':False,
            'worker_terminal_proof':False,'delivery_verified':False}).decode())
        return 75
    except OriginalDeliveryRefused as error:
        print(canonical({'state':'REFUSED','reason':error.reason,
            'failure_phase':'original_remote_read','retry_authorized':False,
            'worker_terminal_proof':False,'delivery_verified':False}).decode())
        return 75
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        print('{"state":"REFUSED","reason":"original_delivery_unconfirmed","retry_authorized":false}')
        return 75



# ---------------------------------------------------------------------------
# Candidate overlay: collected-source quality qualification (collector side).
#
# A small bounded helper that composes the existing owners only — the exact
# owned receipt bytes, read_collection, load_binding with the retained
# packet/log/support sources through the incumbent producer validator, and the
# retained read-request/read-response chunks revalidated through
# validate_response over a held DirectoryChain. Ordinary producer-
# authenticated glm/qwen artifact contracts only: plain scopes, plain
# retained-launch bindings and historical exception scopes are refused.
#
# RETAINED DESCRIPTORS: retained_collection_quality composes the incumbent
# DirectoryChain/read_local_at strict nofollow owner mechanics into one
# context manager that keeps every directory chain AND every actual input
# regular file descriptor open through qualification AND publication. Held:
# the collection receipt, every retained collection file (request, binding
# copy, response chunks, stdout chunks, process capture, returncode, every
# artifact), the source binding file, the original packet/log/support sources,
# and the owned closed adjudication file. reverify() re-proves identity,
# mode, ownership and exact content — not just a path — before and after the
# sidecar link: replacing a file with identical bytes still refuses (inode
# identity), substituting a symlink or another path refuses (O_NOFOLLOW open
# plus name/identity comparison), and in-place mutation refuses (re-read
# digest). The owner's own sidecar write in the same state directory is not a
# change: directory chains are revalidated by held edge identity, never by
# directory mtime. Existing IO owners do all reading — there is no second
# general reader, no scan, and no runtime IO reader — and every descriptor
# and chain is closed on every path.
#
# The original-caller guard runs BEFORE any input read or write: the
# CODEX_THREAD_ID label must agree with the independently caller-asserted
# original root of the ORIGINAL invocation; POOL_ORCHESTRATOR_ID and
# POOL_PARENT_RUN_ID are optional correlation labels that are refused on any
# mismatch when present but never required when absent — the legitimate
# native shell carries POOL_ORCHESTRATOR_ID unset. Child, vanished-parent,
# foreign and current-coordinator label substitutions are refused. The labels
# stay correlation, never authentication: no native or tool grant is consulted
# or created here, external native/tool original-root scope remains the
# authority, and this helper issues no acceptance, release, settlement or
# retry right.
# ---------------------------------------------------------------------------

QUALITY_SUBJECT_SCHEMA = 'mastermind.collection_quality_subject.v1'
QUALITY_ADJUDICATION_SCHEMA = 'mastermind.collection_quality_adjudication.v1'
QUALITY_MAX_ADJUDICATION = 65536
QUALITY_MAX_REASON = 512
QUALITY_MAX_EVIDENCE = 128
QUALITY_VERDICTS = ('PASS', 'FAIL', 'PARTIAL')
QUALITY_BY_ROLES = ('deterministic', 'reviewer')
QUALITY_CHUNK_BOUND = 64
QUALITY_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
QUALITY_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/()+'-]{0,511}\Z")
QUALITY_SHORT_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/()+'-]{0,127}\Z")


def quality_caller_guard(root, parent):
    """Original-caller agreement guard. Runs before any input read or write."""
    if (type(root) is not str or type(parent) is not str
            or not IDENT.fullmatch(root) or not IDENT.fullmatch(parent)):
        raise OriginalDeliveryRefused('quality_caller_scope_invalid')
    if os.environ.get('CODEX_THREAD_ID') != root:
        # A child thread, a vanished parent label, or a foreign operation.
        raise OriginalDeliveryRefused('quality_caller_not_original_root')
    coordinator = os.environ.get('POOL_ORCHESTRATOR_ID')
    if coordinator is not None and coordinator != root:
        # A present coordinator label must not substitute the original root;
        # the legitimate native shell carries this label unset.
        raise OriginalDeliveryRefused('quality_caller_coordinator_label_mismatch')
    labelled = os.environ.get('POOL_PARENT_RUN_ID')
    if labelled is not None and labelled != parent:
        raise OriginalDeliveryRefused('quality_caller_parent_label_mismatch')


class _QualifiedCollection:
    """One qualified collection with every input descriptor held open.

    Entry performs the caller guard and the full bounded qualification through
    the existing owners, then keeps every directory chain and input regular
    file descriptor open so reverify() can re-prove identity, mode, ownership
    and exact content around the sidecar owner's publication. close() closes
    every descriptor and chain on every path.
    """

    def __init__(self, binding_path, *, collection_receipt, expected_sha256,
                 run_id, root, parent, adjudication_path=None):
        self._chains = []
        self._held = []
        self._names = set()
        self.subject = None
        self.adjudication_raw = None
        try:
            self._qualify(binding_path, collection_receipt=collection_receipt,
                          expected_sha256=expected_sha256, run_id=run_id,
                          root=root, parent=parent,
                          adjudication_path=adjudication_path)
        except OriginalDeliveryRefused:
            self.close()
            raise
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            # Every failure is a typed refusal; a raw filesystem or parse
            # error never escapes qualification.
            self.close()
            raise OriginalDeliveryRefused('quality_collection_unqualified') from error
        except BaseException:
            self.close()
            raise

    # ---- retained descriptor mechanics ------------------------------------

    def _chain(self, path):
        chain = delivery.DirectoryChain(Path(path))
        self._chains.append(chain)
        return chain

    def _retain(self, chain, name, limit, expected=None):
        """Hold the actual regular descriptor BEFORE the owner read.

        The descriptor is opened and fully qualified first, then the incumbent
        owner read runs, and the held descriptor's full identity (device,
        inode, size, times, mode, owner, link count) is compared against the
        visible directory entry both before and after those bytes. A same-bytes
        replacement inside that interval can never satisfy both snapshots, so
        the replaced inode is refused instead of qualifying it. The existing
        read_local_at owner stays the only byte reader; its own errors keep
        this call site's specific refusal mapping. The qualified descriptor is
        retained through publication and revalidated by revalidate().
        """
        key = (id(chain), name)
        if key in self._names:
            return None
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
        try:
            held = os.fstat(fd)
            before = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
            identity = reader.identity(held)
            if (identity != reader.identity(before)
                    or not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                    or held.st_mode & 0o022):
                raise OriginalDeliveryRefused('quality_retained_source_changed')
            raw = delivery.read_local_at(chain, name, limit)
            after = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
            if (identity != reader.identity(os.fstat(fd))
                    or identity != reader.identity(after)
                    or len(raw) != held.st_size):
                raise OriginalDeliveryRefused('quality_retained_source_changed')
        except OriginalDeliveryRefused:
            os.close(fd)
            raise
        except BaseException:
            # Owner-read errors keep their caller's specific refusal mapping;
            # only the descriptor this call opened is released here.
            os.close(fd)
            raise
        if expected is not None and sha(raw) != expected:
            os.close(fd)
            raise OriginalDeliveryRefused('quality_retained_source_changed')
        self._names.add(key)
        self._held.append((chain, name, fd, identity,
                           stat.S_IMODE(held.st_mode), sha(raw), limit))
        return raw

    def revalidate(self):
        """Re-prove every retained input: identity, mode, ownership, content."""
        for chain, name, fd, identity, mode, digest, limit in self._held:
            chain.verify()
            info = os.fstat(fd)
            if (reader.identity(info) != identity
                    or stat.S_IMODE(info.st_mode) != mode
                    or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()):
                raise ValueError('qualified_collection_changed')
            if reader.identity(info) != reader.identity(
                    os.stat(name, dir_fd=chain.fd, follow_symlinks=False)):
                # A same-bytes replacement at the same path still refuses.
                raise ValueError('qualified_collection_changed')
            data = b''
            while len(data) <= limit:
                chunk = os.pread(fd, min(65536, limit + 1 - len(data)), len(data))
                if not chunk:
                    break
                data += chunk
            if len(data) != info.st_size or sha(data) != digest:
                raise ValueError('qualified_collection_changed')
        return True

    def reverify(self):
        """Revalidation around publication; the subject is unchanged by proof."""
        self.revalidate()
        return self.subject

    def close(self):
        for _chain, _name, fd, *_rest in reversed(self._held):
            try:
                os.close(fd)
            except OSError:
                pass
        self._held.clear()
        self._names.clear()
        for chain in reversed(self._chains):
            chain.close()
        self._chains.clear()

    # ---- qualification over the existing owners ---------------------------

    def _qualify(self, binding_path, *, collection_receipt, expected_sha256,
                 run_id, root, parent, adjudication_path):
        quality_caller_guard(root, parent)
        if (not isinstance(binding_path, (str, Path))
                or not isinstance(collection_receipt, (str, Path))
                or not IDENT.fullmatch(run_id) or run_id in PLAIN_SCOPES
                or type(expected_sha256) is not str or not HEX.fullmatch(expected_sha256)):
            raise OriginalDeliveryRefused('quality_subject_unqualified')
        receipt_path = Path(collection_receipt)
        binding_file = Path(binding_path)
        # Exact owned receipt bytes first, retained on a held descriptor.
        try:
            receipt_chain = self._chain(receipt_path.parent)
            receipt_raw = self._retain(receipt_chain, receipt_path.name, 65536)
        except OriginalDeliveryRefused:
            raise
        except (OSError, ValueError) as error:
            raise OriginalDeliveryRefused('quality_receipt_unreadable') from error
        if receipt_raw is None or sha(receipt_raw) != expected_sha256:
            raise OriginalDeliveryRefused('quality_receipt_digest_mismatch')
        # Existing readback owner: receipt scope, state, delivered files, stdout.
        try:
            stdout = read_collection(receipt_path, expected_sha256=expected_sha256,
                                     run_id=run_id, root=root, parent=parent)
        except OriginalDeliveryRefused:
            raise
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            raise OriginalDeliveryRefused('quality_collection_readback_unqualified') from error
        # Incumbent binding owner: exact original packet/log/support sources,
        # producer contract and the full-hash-qualified incumbent validator.
        try:
            value, binding_raw, source, contract, alias, registry, original_validator, plain_binding = load_binding(
                binding_file, run_id=run_id, root=root, parent=parent)
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            raise OriginalDeliveryRefused('quality_binding_unqualified') from error
        if (plain_binding is not None or contract is None
                or contract.get('schema') != production.SCHEMA
                or value['mode'] not in production.ORDINARY_MODES):
            raise OriginalDeliveryRefused('quality_plain_or_historical_scope_unqualified')
        receipt = reader.strict_json(receipt_raw)
        if receipt.get('host') != value['host'] or receipt.get('mode') != value['mode']:
            raise OriginalDeliveryRefused('quality_receipt_scope_mismatch')
        request = {'schema': SCHEMA,
                   **{k: value[k] for k in ('run_id', 'root', 'parent', 'host')},
                   'contract': contract}
        request_bytes = canonical(request)
        if sha(request_bytes) != receipt.get('request_sha256'):
            raise OriginalDeliveryRefused('quality_request_digest_mismatch')
        # Retain the binding file and every original source on held descriptors.
        binding_chain = self._chain(binding_file.parent)
        self._retain(binding_chain, binding_file.name, 65536, expected=sha(binding_raw))
        sources_chain = self._chain(Path(value['sources']['log']['path']).parent)
        for name in ('packet', 'log', 'support'):
            item = value['sources'][name]
            self._retain(sources_chain, Path(item['path']).name, 2 * 1024 * 1024,
                         expected=item['sha256'])
        # Retained collection evidence by exact name: retained request, the
        # collection's own binding copy, and every retained response chunk.
        if delivery.read_local_at(receipt_chain, 'read-request.json', 65536) != request_bytes:
            raise OriginalDeliveryRefused('quality_retained_request_mismatch')
        self._retain(receipt_chain, 'read-request.json', 65536,
                     expected=sha(request_bytes))
        if delivery.read_local_at(receipt_chain, 'binding.json', 65536) != binding_raw:
            raise OriginalDeliveryRefused('quality_retained_binding_mismatch')
        self._retain(receipt_chain, 'binding.json', 65536, expected=sha(binding_raw))
        response = b''
        for index in range(QUALITY_CHUNK_BOUND):
            name = f'read-response.{index:03d}'
            try:
                part = delivery.read_local_at(receipt_chain, name, reader.MAX_FILE)
            except FileNotFoundError:
                break
            response += part
            self._retain(receipt_chain, name, reader.MAX_FILE)
        if not response:
            raise OriginalDeliveryRefused('quality_collection_response_absent')
        if len(response) > MAX_RESPONSE:
            raise OriginalDeliveryRefused('quality_collection_response_limit')
        if sha(response) != receipt.get('response_sha256'):
            raise OriginalDeliveryRefused('quality_retained_response_mismatch')
        verified = validate_response(response, request, value['mode'],
                                     original_validator=original_validator)
        if verified is None:
            raise OriginalDeliveryRefused('quality_collection_not_terminal')
        blobs, artifacts, manifest = verified
        if (blobs['stdout'] != stdout
                or sha(blobs['stdout']) != receipt.get('stdout_sha256')
                or len(blobs['stdout']) != receipt.get('stdout_bytes')):
            raise OriginalDeliveryRefused('quality_stdout_mismatch')
        files = receipt.get('files')
        if type(files) is not list or not files:
            raise OriginalDeliveryRefused('quality_collection_files_mismatch')
        files_by_name = {item.get('local_name'): item for item in files}
        if (sha(blobs['process']) != (files_by_name.get('process.json') or {}).get('sha256')
                or sha(blobs['rc']) != (files_by_name.get('returncode.txt') or {}).get('sha256')):
            raise OriginalDeliveryRefused('quality_process_mismatch')
        expected_artifacts = [{**meta, 'local_name': f'artifact.{index:02d}'}
                              for index, (meta, _data) in enumerate(artifacts)]
        if receipt.get('artifacts') != expected_artifacts:
            raise OriginalDeliveryRefused('quality_artifact_receipt_mismatch')
        expected_names = (['binding.json', *receipt['stdout_chunks'], 'process.json',
                           'returncode.txt']
                          + [f'artifact.{index:02d}' for index in range(len(artifacts))])
        if [item.get('local_name') for item in files] != expected_names:
            raise OriginalDeliveryRefused('quality_collection_files_mismatch')
        for item in files:
            self._retain(receipt_chain, item['local_name'], reader.MAX_FILE,
                         expected=item['sha256'])
        subject = {
            'schema': QUALITY_SUBJECT_SCHEMA,
            'run_id': run_id, 'root': root, 'parent': parent,
            'host': value['host'], 'mode': value['mode'],
            'requested_model': value['requested_model'],
            'destination': str(receipt_path.parent),
            'receipt_name': receipt_path.name,
            'receipt_sha256': expected_sha256,
            'binding_sha256': sha(binding_raw),
            'request_sha256': sha(request_bytes),
            'response_sha256': sha(response),
            'packet_sha256': sha(source['packet']),
            'body_sha256': contract['body_sha256'],
            'support_digest': contract['support_digest'],
            'artifact_names': list(contract['names']),
            'stdout': {'sha256': sha(blobs['stdout']), 'bytes': len(blobs['stdout']),
                       'chunks': len(receipt['stdout_chunks'])},
            'process_sha256': sha(blobs['process']),
            'returncode': 0,
            'files': [dict(item) for item in files],
            'artifacts': [{k: item[k] for k in ('path', 'bytes', 'sha256', 'local_name')}
                          for item in receipt['artifacts']],
            'artifact_manifest_sha256': sha(canonical(manifest)),
            'collection_files_sha256': sha(canonical(files)),
        }
        if adjudication_path is not None:
            # The owned closed adjudication is read once here and retained on
            # its own descriptor, so the exact bytes the owner attests stay
            # provable through publication.
            adjudication_file = Path(adjudication_path)
            adjudication_chain = self._chain(adjudication_file.parent)
            self.adjudication_raw = self._retain(
                adjudication_chain, adjudication_file.name, QUALITY_MAX_ADJUDICATION)
            if self.adjudication_raw is None:
                raise OriginalDeliveryRefused('quality_adjudication_invalid')
        self.subject = subject


class retained_collection_quality:
    """Context manager: qualify one retained collection, hold every input.

    Composes the existing owners into one bounded qualification whose held
    directory chains and input file descriptors survive the whole publication
    window, so the sidecar owner revalidates the ACTUAL retained source — not
    a re-read by path — before and after the link. Exit closes every
    descriptor and chain on every path; nothing here mutates the original
    operation, runs the worker, settles a lease, or adjudicates acceptance.
    """

    def __init__(self, binding_path, *, collection_receipt, expected_sha256,
                 run_id, root, parent, adjudication_path=None):
        self._args = (binding_path, collection_receipt, expected_sha256,
                      run_id, root, parent, adjudication_path)
        self._qualified = None

    def __enter__(self):
        binding_path, collection_receipt, expected_sha256, run_id, root, parent, \
            adjudication_path = self._args
        self._qualified = _QualifiedCollection(
            binding_path, collection_receipt=collection_receipt,
            expected_sha256=expected_sha256, run_id=run_id, root=root,
            parent=parent, adjudication_path=adjudication_path)
        return self._qualified

    def __exit__(self, *_):
        if self._qualified is not None:
            self._qualified.close()
            self._qualified = None
        return False


def quality_adjudication(raw, *, subject):
    """Validate one CLOSED explicit adjudication against a qualified subject.

    The adjudication binds the receipt digest, the stdout digest and length,
    every retained collection file, and every artifact digest/length/name,
    plus verdict, role, reason and evidence. A success boolean is never
    sufficient; any omitted, extra or changed binding refuses.
    """
    if (not isinstance(raw, (bytes, bytearray))
            or not 0 < len(raw) <= QUALITY_MAX_ADJUDICATION
            or type(subject) is not dict
            or subject.get('schema') != QUALITY_SUBJECT_SCHEMA):
        raise OriginalDeliveryRefused('quality_adjudication_invalid')
    try:
        row = reader.strict_json(bytes(raw))
    except (ValueError, TypeError, RecursionError) as error:
        raise OriginalDeliveryRefused('quality_adjudication_invalid') from error
    fields = {'schema', 'run_id', 'root', 'parent', 'verdict', 'by', 'reason',
              'evidence', 'receipt_sha256', 'stdout_sha256', 'stdout_bytes',
              'files', 'artifacts'}
    if (type(row) is not dict or set(row) != fields
            or row['schema'] != QUALITY_ADJUDICATION_SCHEMA
            or any(row.get(k) != subject[k] for k in ('run_id', 'root', 'parent'))
            or row['verdict'] not in QUALITY_VERDICTS
            or row['by'] not in QUALITY_BY_ROLES
            or type(row['reason']) is not str
            or QUALITY_TEXT.fullmatch(row['reason']) is None
            or len(row['reason']) > QUALITY_MAX_REASON
            or type(row['evidence']) is not str
            or QUALITY_SHORT_TEXT.fullmatch(row['evidence']) is None
            or len(row['evidence']) > QUALITY_MAX_EVIDENCE
            or row['receipt_sha256'] != subject['receipt_sha256']
            or row['stdout_sha256'] != subject['stdout']['sha256']
            or row['stdout_bytes'] != subject['stdout']['bytes']
            or row['files'] != subject['files']
            or row['artifacts'] != subject['artifacts']):
        raise OriginalDeliveryRefused('quality_adjudication_incomplete')
    return {'verdict': row['verdict'], 'by': row['by'], 'reason': row['reason'],
            'evidence': row['evidence'], 'adjudication_sha256': sha(bytes(raw))}



if __name__=='__main__':raise SystemExit(main())
