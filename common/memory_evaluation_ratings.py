"""Guide-bound annotation grammar/alignment only, never a rating issuer."""
from __future__ import annotations
import hashlib
import json
from common import memory_evaluation_contract as c
from common import memory_native_wire as w
from common.memory_participant_view import selected_descriptors, project_original_result, _json

CORRECT = ('correct', 'incorrect', 'unresolved', 'not_applicable')
VERDICTS = ('supported', 'contradicted', 'unsupported', 'attributed_inference', 'unresolved')

def result_contract(*, adjudication=False):
    """Fixed model-facing grammar; judgments remain the actual actor's text."""
    return dict(schema='mastermind.memory_evaluation_output_contract.v1',
        encoding='one UTF8 canonical JSON object; sorted keys, no whitespace outside strings, no markdown',
        result_schema='mastermind.memory_evaluation_resolution.v1' if adjudication else 'mastermind.memory_evaluation_annotation.v1',
        annotation=dict(fields=['schema','answer_assessment','facets','claims','relevance'],
            answer_assessment=list(CORRECT),facet_fields=['facet_id','assessment','reason'],
            claim_fields=['claim_id','span','verdict','material','critical','source_support','reason'],
            span_fields=['start_byte','end_byte_exclusive','quoted_utf8','span_sha256'],
            span_basis='decoded original answer UTF8 bytes; no normalization',verdict=list(VERDICTS),
            material_and_critical='boolean original reviewer judgments, not citation-derived facts',
            source_support='complete byte-identical descriptors from ONLY original packet source cards',
            supported_or_contradicted='requires at least one exact descriptor; membership is not entailment',
            relevance_fields=['context_id','relevance','facet_ids','reason'],relevance=[0,1,2],
            coverage='every registered required facet and every original source context exactly once'),
        resolution=dict(fields=['schema','resolutions','overall_reason'],item_fields=['item_key','judgment','reason'],
            coverage='every ordered comparison item exactly once; nonempty original reason for every item',
            answer_and_facet_judgment_fields=['assessment'],relevance_judgment_fields=['relevance','facet_ids'],
            span_judgment_fields=['verdict','material','critical','source_support'],
            unmatched_span_additional_field='alignment: resolved or unresolved; preserve both original spans'),
        limitations=['syntax and source membership do not prove truth or expertise','no automatic severity precedence or scientific admission'])

def annotation(raw, packet, result):
    value = w.parse(raw, 65536)
    w.exact(value, 'schema answer_assessment facets claims relevance')
    if value['schema'] != 'mastermind.memory_evaluation_annotation.v1' or value['answer_assessment'] not in CORRECT: c.fail()
    view = project_original_result(packet, result, attempt_id='original-subject')
    answer = view['answer'].encode('utf-8')
    task = _json(packet[:-len(w.SUFFIX)], canonical=True)['task']
    allowed = {w.canonical(d) for d in selected_descriptors(packet)}
    facets = value['facets']
    if type(facets) is not list or [f.get('facet_id') for f in facets] != task['required_facet_ids']: c.fail()
    for f in facets:
        w.exact(f, 'facet_id assessment reason')
        if f['assessment'] not in CORRECT: c.fail()
        c.text(f['reason'])
    if type(value['claims']) is not list or len(value['claims']) > 64: c.fail()
    spans = []
    for claim in value['claims']:
        w.exact(claim, 'claim_id span verdict material critical source_support reason')
        w.token(claim['claim_id']); c.text(claim['reason'])
        if claim['verdict'] not in VERDICTS or type(claim['material']) is not bool or type(claim['critical']) is not bool: c.fail()
        span = claim['span']; w.exact(span, 'start_byte end_byte_exclusive quoted_utf8 span_sha256')
        start, end = span['start_byte'], span['end_byte_exclusive']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(answer): c.fail()
        quoted = answer[start:end]
        if (quoted.decode('utf-8') != span['quoted_utf8'] or hashlib.sha256(quoted).hexdigest() != span['span_sha256']): c.fail()
        spans.append((start, end))
        supports = claim['source_support']
        if type(supports) is not list or len(supports) > 45 or any(w.canonical(d) not in allowed for d in supports): c.fail()
        if claim['verdict'] in ('supported','contradicted') and not supports:c.fail()
        if len({w.canonical(d) for d in supports}) != len(supports): c.fail()
    if len(spans) != len(set(spans)): c.fail()
    rel = value['relevance']; seen = []
    contexts = {d['context_id'] for d in selected_descriptors(packet)}
    if type(rel) is not list or len(rel) > 9: c.fail()
    for item in rel:
        w.exact(item, 'context_id relevance facet_ids reason')
        if item['context_id'] not in contexts or type(item['relevance']) is not int or item['relevance'] not in (0, 1, 2): c.fail()
        if (type(item['facet_ids']) is not list or item['facet_ids'] != sorted(set(item['facet_ids']))
                or not set(item['facet_ids']) <= set(task['required_facet_ids'])): c.fail()
        c.text(item['reason']); seen.append(item['context_id'])
    # Coverage is explicit: no disappearing retrieval item denominator.
    if set(seen) != contexts or len(seen) != len(contexts): c.fail()
    return value

def align(first, second):
    """Facet identity or EXACT UTF8 span identity, never local claim IDs."""
    def items(value):
        result = {'answer': value['answer_assessment']}
        for facet in value['facets']: result['facet:' + facet['facet_id']] = facet
        for claim in value['claims']:
            span = claim['span']
            key = 'span:' + c.digest(span)
            result[key] = {k:v for k,v in claim.items() if k != 'claim_id'}
        for row in value['relevance']: result['relevance:' + row['context_id']] = row
        return result
    left, right = items(first), items(second)
    comparisons = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        # Reasons are judgments too and are retained; an equality is never
        # semantic correctness, and unresolved==unresolved is not agreement.
        unresolved = (a == 'unresolved' or b == 'unresolved'
            or type(a) is dict and any(a.get(k) == 'unresolved' for k in ('assessment', 'verdict'))
            or type(b) is dict and any(b.get(k) == 'unresolved' for k in ('assessment', 'verdict')))
        if a != b or unresolved:
            comparisons.append(dict(item_key=key, state='UNRESOLVED_ALIGNMENT' if a is None or b is None else
                'UNRESOLVED' if unresolved else 'DISAGREEMENT', reviewer_1=a, reviewer_2=b))
    return comparisons

def resolution(raw, comparisons, *, packet):
    value = w.parse(raw, 65536)
    w.exact(value, 'schema resolutions overall_reason')
    if value['schema'] != 'mastermind.memory_evaluation_resolution.v1': c.fail()
    c.text(value['overall_reason'])
    rows = value['resolutions']
    if type(rows) is not list or [r.get('item_key') for r in rows] != [r['item_key'] for r in comparisons]: c.fail()
    allowed={w.canonical(d) for d in selected_descriptors(packet)}
    facets=set(_json(packet[:-len(w.SUFFIX)],canonical=True)['task']['required_facet_ids'])
    for row,item in zip(rows,comparisons):
        w.exact(row, 'item_key judgment reason')
        c.text(row['reason'])
        # Do not force maximum severity, agreement or a scientific disposition.
        if type(row['judgment']) is not dict or not row['judgment']: c.fail()
        key=item['item_key'];judgment=row['judgment']
        if key=='answer' or key.startswith('facet:'):
            if set(judgment)!={'assessment'}:c.fail()
        elif key.startswith('relevance:'):
            if set(judgment)!={'relevance','facet_ids'}:c.fail()
            if type(judgment['facet_ids']) is not list or judgment['facet_ids']!=sorted(set(judgment['facet_ids'])) or not set(judgment['facet_ids'])<=facets:c.fail()
        elif key.startswith('span:'):
            required={'verdict','material','critical','source_support'}
            if item['state']=='UNRESOLVED_ALIGNMENT':required.add('alignment')
            if set(judgment)!=required or type(judgment['source_support']) is not list:c.fail()
            if len(judgment['source_support'])>45 or any(w.canonical(d) not in allowed for d in judgment['source_support']):c.fail()
            if len({w.canonical(d) for d in judgment['source_support']})!=len(judgment['source_support']):c.fail()
            if judgment['verdict'] in ('supported','contradicted') and not judgment['source_support']:c.fail()
        else:c.fail()
        for k, v in row['judgment'].items():
            if k == 'assessment' and v not in CORRECT: c.fail()
            if k == 'verdict' and v not in VERDICTS: c.fail()
            if k in ('material', 'critical') and type(v) is not bool: c.fail()
            if k == 'relevance' and (type(v) is not int or v not in (0,1,2)): c.fail()
            if k == 'alignment' and v not in ('resolved', 'unresolved'): c.fail()
    return value
