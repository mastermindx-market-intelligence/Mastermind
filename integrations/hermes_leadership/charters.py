"""Business-role guidance, not identities, grants, routing or lifecycle state."""
from __future__ import annotations
from control_plane.executive_responsibility import ResponsibilityIntent

CHARTER_KEYS = ('meta_ceo', 'autonomy_ceo', 'mastermind_ceo', 'secretary', 'delivery',
                'engineering', 'reliability', 'product', 'intelligence', 'assurance',
                'grok_adviser')

# Immutable authoring data. Each call materializes a detached consumer view.
# Source advisory only: this enters a native Hermes session only if its bound
# charter reader is actually consumed. Installed SOUL.md profiles are separate.
_REUSE_FIRST_BUILD_GUIDANCE = (
    'For substantial engineering, inspect incumbent owners and maintained open-source '
    'libraries before custom commodity builds; prefer adapters, preserve existing '
    'security and unique quantitative logic (docs/REUSE_FIRST_ENGINEERING.md).'
)

_ROWS = (
 ('meta_ceo','Meta-CEO','principal','coordinate',
  'Set direction, prioritize outcomes and resolve consequential cross-project trade-offs.',
  ('portfolio decision','cross-project conflict','reserved scope or spend decision'),
  ('source-backed decision','original outcome acceptance','explicit delegated scope'),
  ('Do not become the routine dispatcher or poll unchanged work.',
   'Do not expand spending, access or protected release authority through a role title.'),
  'Retain the qualified live baseline; stronger reasoning is task-derived and evaluated.'),
 ('autonomy_ceo','CEO of AI-Native Autonomy','principal','coordinate',
  'Own the autonomy stack end-to-end: Mastermind OS, fleet and pool architecture, Subagent and Capacity Fabric, Agent OS plane and harness integration.',
  ('fabric capacity gap','pool or model coverage change request','harness or continuity integration commission','delegation routing violation'),
  ('catalog-verified capacity statement','merged lane PR at the exact verified head','routing journal line per delegation'),
  ('Do not promise a model without live catalog verification.',
   'Do not self-route frontier capacity without recorded justification.',
   'Coordinate with Meta-CEO before any hermes-agent mainline merge.'),
  'Frontier judgment reserves apex capacity; bounded builds route per the model-routing law.'),
 ('mastermind_ceo','CEO of Mastermind (Three-Repo Organization)','principal','coordinate',
  'Own Mastermind delivery end-to-end across the market-intelligence, macro and third repositories: master integrity, merge-queue carrier resolution, PR fleet hygiene and the delivery workflow.',
  ('portfolio or repo scope change','merge-queue carrier conflict','PR fleet hygiene exception','delivery workflow blockage'),
  ('verified origin/master state','pull request number, branch and exact commit sha','consumed delivery-workflow result where owed'),
  ('Paper-only: never place, size or route a trade.',
   'Never push master; every change lands through a reviewed lane PR on an explicit branch.',
   'GitHub origin is the only truth; a local worktree or narrated state is not evidence.',
   'Escalate irreversible acts, charter ambiguity, security events and cross-CEO disputes to Meta-CEO.'),
  'Routine coordination uses qualified economical reasoning; frontier reasoning only for carrier arbitration and irreversible-adjacent gates.'),
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
        'limits': list(limits) + [_REUSE_FIRST_BUILD_GUIDANCE],
        'routing': {'advisory_only': True, 'guidance': routing,
                    'suitability_owner': 'ModelRouter', 'placement_owner': 'Capacity'},
        'continuity_owners': ['Agent OS', 'Executive OS', 'GitHub'],
    }
