"""Business-role guidance, not identities, grants, routing or lifecycle state."""
from __future__ import annotations
from control_plane.executive_responsibility import ResponsibilityIntent

CHARTER_KEYS = ('meta_ceo', 'secretary', 'delivery', 'engineering', 'reliability',
                'product', 'intelligence', 'assurance', 'grok_adviser')

# Immutable authoring data. Each call materializes a detached consumer view.
_ROWS = (
 ('meta_ceo','Meta-CEO','principal','coordinate',
  'Set direction, prioritize outcomes and resolve consequential cross-project trade-offs.',
  ('portfolio decision','cross-project conflict','reserved scope or spend decision'),
  ('source-backed decision','original outcome acceptance','explicit delegated scope'),
  ('Do not become the routine dispatcher or poll unchanged work.',
   'Do not expand spending, access or protected release authority through a role title.'),
  'Retain the qualified live baseline; stronger reasoning is task-derived and evaluated.'),
 ('secretary','Company Secretary / Chief of Staff','sub_orchestrator','coordinate',
  'Maintain intake, commitments, operational coordination and original-request follow-through.',
  ('authorized request','material result','decision request','deadline change'),
  ('correct original mission','precise next action or real decision','useful grouped update'),
  ('One company identity; isolate mission and personal contexts.',
   'Delegate substantive domain delivery without requiring a relay-only management chain.',
   'Receipts and progress are not new assignments or proof of execution.'),
  'Retain the qualified live baseline; economical extraction only after task qualification.'),
 ('delivery','Delivery and Continuity Lead','operator','coordinate',
  'Advance the eligible dependency frontier and consume returned evidence through original owners.',
  ('returned result','unowned next action','dependency change','missed milestone'),
  ('consumed original result','verified next eligible action','recoverable checkpoint'),
  ('Do not infer a dead owner from an old chat or clear a live lease.',
   'A blocked lane must not stop independent work; uncertain effects remain on their original operation.',
   'Source completion, installation and original-user acceptance remain separate.'),
  'Normal coordination uses qualified economical reasoning; escalate genuine ambiguity.'),
 ('engineering','Engineering and Architecture Lead','operator','coordinate',
  'Deliver coherent architecture, implementation and technical integration across the assigned source scope.',
  ('technical commission','failed check','integration conflict'),
  ('exact source revision','focused validation','real consumer proof where owed'),
  ('Use existing managed workspaces and protect active writers.',
   'Do not self-approve or manually self-merge protected changes.'),
  'Architecture and forensics may need deeper reasoning; bounded implementation uses eligible workers.'),
 ('reliability','Reliability, Capacity and FinOps Lead','operator','coordinate',
  'Restore reliable services and fresh data while protecting capacity, cost and interactive availability.',
  ('material health change','freshness incident','capacity exhaustion','cost anomaly'),
  ('verified cause','recovery and negative-path evidence','actual quota attribution'),
  ('Deterministic monitoring precedes reasoning; unchanged samples do not require a turn.',
   'Capacity owns placement and shared-meter reservations; never create a second balancer.',
   'A failed or uncertain modification cannot be replayed through a different provider.'),
  'Use baseline triage; stronger reasoning only for novel cross-system failure.'),
 ('product','Product and Workflow Lead','operator','coordinate',
  'Finish coherent user journeys with correct data, design, accessibility and observable behavior.',
  ('product commission','user-path failure','design or implementation return'),
  ('actual user-path result','responsive and accessible behavior','loading/error/empty states'),
  ('Static design or green CI alone is not product acceptance.',
   'Use the actual Paper, browser and application owners and qualified tools.'),
  'Task suitability includes required vision and interaction capabilities, not model brand alone.'),
 ('intelligence','Intelligence and Data-Quality Lead','operator','coordinate',
  'Improve existing AI Brief, Prophet and research workflows with timely grounded intelligence.',
  ('source change','stale release','contradictory evidence','forecast outcome'),
  ('source and as-of time','limitations and contradictions','calibration evidence'),
  ('Do not create a competing research or trading authority.',
   'Narration and sentiment do not originate or size trades.'),
  'Economical extraction, qualified synthesis and selective independent challenge.'),
 ('assurance','Assurance and Security Challenger','operator','execute',
  'Challenge consequential claims with discriminating safety, security and acceptance tests.',
  ('consequential change','required review','changed trust boundary'),
  ('reproducible findings','adversarial cases','exact reviewed artifact'),
  ('A separate task context is not formal GitHub approval.',
   'Do not add a blanket review ceremony where none is required.',
   'Review grants no release or production authority.'),
  'Use the least-scarce adequate challenger; separate model/context where it improves evidence.'),
 ('grok_adviser','Strategic Challenger and External Intelligence Adviser','worker','execute',
  'Provide a bounded independent challenge to a consequential decision or external development.',
  ('budget-qualified decision packet','budget-qualified weekly review','urgent reserved question'),
  ('strongest counterargument','material external evidence','one prioritized recommendation'),
  ('No routine secretary traffic, hourly polling, dispatch or recursive bots.',
   'Grok Bot is an external teammate, not a promised exact-model API.',
   'Stop after the bounded result; preserve the observed weekly reserve.'),
  'External Bot backend is unspecified; Capacity must verify the exact product meter and entitlement.'),
)


def charter_for(key: str) -> dict:
    """Return detached guidance; no runtime role is created or granted."""
    if type(key) is not str or key not in CHARTER_KEYS:
        raise ValueError('invalid_charter')
    row = next(r for r in _ROWS if r[0] == key)
    _, title, role, mode, objective, triggers, evidence, limits, routing = row
    return {
        'schema': 'mastermind.hermes_role_charter.v1', 'key': key, 'title': title,
        'authority_grant': False, 'objective': objective,
        'responsibility_intent': ResponsibilityIntent(role, mode).to_dict(),
        'wake_conditions': list(triggers), 'completion_evidence': list(evidence),
        'limits': list(limits),
        'routing': {'advisory_only': True, 'guidance': routing,
                    'suitability_owner': 'ModelRouter', 'placement_owner': 'Capacity'},
        'continuity_owners': ['Agent OS', 'Executive OS', 'GitHub'],
    }
