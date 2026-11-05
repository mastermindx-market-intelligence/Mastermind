"""Frozen reviewed literals for the Fabric release, never runtime authority.

Exact source hashes and token spans only. Each site is a permission, an input
bound or a reviewed primary/secondary identity exclusion. Shell and retained
.py.base are scanned as source too. Any byte drift exposes every site again;
these pins are not learned or refreshed by the tests.
"""

REVIEWED_FILES = {
    # R2 AEAD source candidate: the existing Control UID remains fixed at this
    # single exact site. Independent source acceptance remains a release gate;
    # these static test pins do not establish it or grant a new identity.
    "ops/executive_os/control_aead_profile.py": {
        "sha256": "08595b2ecf5b4d5841a85532062e01cd560ae1afe4af3adfe4c7e6eaf22eb2b0",
        "sites": ((277, 124, 127, "int", "450"),),
    },
    # Existing ten-minute telemetry age, not a UID. Full reviewed source and
    # exact token only; drift exposes the source to ordinary D8 again.
    "research/fabric_bailian_host_eligibility_20261015/candidate/glm_host_account_readiness.py": {
        "sha256": "b8921960e7e46a472b536895b5a6491096627d1c8fd58ea0baf283ff34accc07",
        "sites": ((31, 18, 21, "int", "600"),),
    },
    'integrations/session_bridge/bound_launch_capture/runtime/lane_runtime.py': {'sha256': 'cfb18bd9381fae4af1d13a257a8fa5986d903571f64b2aa5dc900439759e9b91',
                                                                              'sites': ((1277,
                                                                                         50,
                                                                                         55,
                                                                                         'int',
                                                                                         '0o770'),
                                                                                        (1277,
                                                                                         75,
                                                                                         80,
                                                                                         'int',
                                                                                         '0o750'),
                                                                                        (2868,
                                                                                         58,
                                                                                         61,
                                                                                         'int',
                                                                                         '500'))},
 'integrations/session_bridge/original_validator_compat/artifact_delivery.py.base': {'sha256': '7c86494e58707d7d8f5f9d72e11e2eb84055caad6a14727ada27a6b0d5e1a1a6',
                                                                                     'sites': ((922,
                                                                                                28,
                                                                                                33,
                                                                                                'int',
                                                                                                '0o700'),)},
 'integrations/session_bridge/original_validator_compat/artifact_production.c0f17c3e.before.py': {'sha256': 'c0f17c3e489c83bdb369d6c1ea9adc2757f4732f515cbc76e230fe154a61f67e',
                                                                                                  'sites': ((145,
                                                                                                             77,
                                                                                                             82,
                                                                                                             'int',
                                                                                                             '0o700'),
                                                                                                            (166,
                                                                                                             85,
                                                                                                             90,
                                                                                                             'int',
                                                                                                             '0o700'))},
 'integrations/session_bridge/original_validator_compat/artifact_production.py': {'sha256': 'e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf',
                                                                                  'sites': ((146,
                                                                                             77,
                                                                                             82,
                                                                                             'int',
                                                                                             '0o700'),
                                                                                            (167,
                                                                                             85,
                                                                                             90,
                                                                                             'int',
                                                                                             '0o700'))},
 'ops/executive_os/acceptance.py': {'sha256': '7a99d1029197cbb877cb968f0f9cbcb3abc257fb10d75406a20f8da884069b94',
                                    # Re-pinned for argv redaction + newline flattening in the
                                    # failure artifact: _redact_failure_text extracted from
                                    # _redact_failure_stream, argv_text now redacted and
                                    # newline-flattened; the same 21 reviewed principal/UID
                                    # literals stay at their exact line/column positions; no new literal added.
                                    # Re-pinned 2026-10-19 for the byte-bounded, line-preserving
                                    # failure-artifact repair (A1 byte bound on
                                    # _redact_failure_stream, A2 control chars + line prefix,
                                    # assert -> raise on _build_failure_payload): the 21 reviewed
                                    # principal/UID literals shifted by +3 lines from the new
                                    # _FAILURE_CONTROL_CHARS_RE definition; no new literal added.
                                    # Re-pinned 2026-10-19 (PR 1637 hardening): write-once _write_bytes; sites unchanged.
                                    # PR2010 phase timing: Root-reviewed postimage; the same
                                    # 21 whole-token sites and enclosing function ASTs are
                                    # unchanged, shifted +10 lines. Full-file drift still refuses.
                                    'sites': ((897, 59, 62, 'int', '454'),
                                              (897, 64, 67, 'int', '455'),
                                              (897, 69, 72, 'int', '456'),
                                              (898, 23, 26, 'int', '450'),
                                              (898, 45, 48, 'int', '450'),
                                              (899, 49, 52, 'int', '400'),
                                              (899, 64, 67, 'int', '500'),
                                              (906, 28, 53, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (914, 39, 64, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (975, 44, 47, 'int', '454'),
                                              (975, 49, 52, 'int', '455'),
                                              (975, 54, 57, 'int', '456'),
                                              (976, 44, 47, 'int', '454'),
                                              (976, 49, 52, 'int', '455'),
                                              (976, 54, 57, 'int', '456'),
                                              (1097, 56, 59, 'int', '400'),
                                              (1097, 85, 88, 'int', '500'),
                                              (1098, 85, 88, 'int', '453'),
                                              (1098, 90, 93, 'int', '454'),
                                              (1098, 95, 98, 'int', '455'),
                                              (1098, 100, 103, 'int', '456'))},
 'ops/executive_os/attended_worker_definition.py': {'sha256': '267ca3fceea48d2c3a1e8a4aaefbf8a90bd595d0c324f1a503826e9604ead92d',
 'sites': ((255, 31, 51, 'str', "'_mastermind_worker'"), (351, 95, 100, 'int', '0o660'))},
 'ops/executive_os/bootstrap-host.sh': {'sha256': '805279ecceb16965ded44f94ab62aa882090accf45edf8a2e7ab86487bca04ce',
                                        'sites': ((776, 21, 43, 'str', '_mastermind_[a-z0-9_]*'),
                                                  (778, 97, 120, 'str', '_mastermind_agent_relay'),
                                                  (784, 89, 92, 'int', '457'))}}

# Candidate-only fixed finite publisher principal/mode postimage for independent
# review: SHA and precise sites are frozen, not computed at runtime. This does
# not authorize publication, merge, release or Capacity admission.
REVIEWED_FILES['ops/executive_os/finite_definition_publication.py'] = {'sha256': 'ffb49518bee8610e2314fecba2eb860c0d4f13c186457b77c15468339cc987e6',
 'sites': ((124, 54, 59, 'int', '0o700'),
 (124, 61, 66, 'int', '0o755'),
 (151, 45, 50, 'int', '0o755'),
 (169, 53, 58, 'int', '0o444'),
 (203, 29, 34, 'int', '0o700'),
 (209, 28, 33, 'int', '0o700'),
 (212, 88, 93, 'int', '0o700'),
 (265, 71, 76, 'int', '0o700'),
 (274, 28, 33, 'int', '0o755'),
 (282, 75, 80, 'int', '0o755'),
 (294, 60, 65, 'int', '0o700'),
 (353, 25, 30, 'int', '0o444'),
 (361, 39, 44, 'int', '0o440'),
 (361, 59, 62, 'int', '470'),
 (373, 55, 76, 'str', '"_mastermind_minimax"'),
 (374, 25, 46, 'str', '"_mastermind_minimax"'),
 (374, 59, 62, 'int', '470'),
 (374, 75, 78, 'int', '470'),
 (375, 24, 27, 'int', '450'),
 (560, 24, 45, 'str', '"_mastermind_minimax"'),
 (561, 25, 46, 'str', '"_mastermind_minimax"'),
 (563, 12, 15, 'int', '470'),
 (563, 17, 20, 'int', '470'),
 (563, 22, 25, 'int', '470'),
 (565, 29, 32, 'int', '470'),
 (566, 83, 86, 'int', '470'),
 (567, 66, 69, 'int', '470'),
 (567, 71, 74, 'int', '470'),
 (567, 76, 81, 'int', '0o700'),
 (579, 76, 81, 'int', '0o555'))}

# Exact finite lifecycle successor postimage. The production delta changes only
# socket ACL observation/currentness; the same 37 reviewed principal/mode literals
# remain fixed. Any other byte or token movement exposes the complete source to D8.
REVIEWED_FILES['ops/executive_os/finite_service_lifecycle.py'] = {'sha256': '17d247d0917f79e1b7e382df98f7515b76a26481e5561e58904ef4a2fc61d4da',
 'sites': ((297, 36, 39, 'int', '470'),
           (297, 65, 68, 'int', '450'),
           (300, 74, 77, 'int', '470'),
           (300, 79, 82, 'int', '470'),
           (300, 84, 87, 'int', '470'),
           (300, 89, 92, 'int', '470'),
           (312, 22, 25, 'int', '470'),
           (364, 28, 49, 'str', "'_mastermind_minimax'"),
           (365, 29, 50, 'str', "'_mastermind_minimax'"),
           (368, 84, 87, 'int', '470'),
           (368, 89, 92, 'int', '470'),
           (368, 94, 97, 'int', '470'),
           (370, 45, 48, 'int', '470'),
           (370, 54, 57, 'int', '470'),
           (386, 68, 71, 'int', '470'),
           (396, 55, 76, 'str', "'_mastermind_minimax'"),
           (396, 91, 112, 'str', "'_mastermind_minimax'"),
           (397, 23, 26, 'int', '470'),
           (397, 39, 42, 'int', '470'),
           (397, 56, 59, 'int', '450'),
           (414, 105, 108, 'int', '470'),
           (414, 110, 113, 'int', '470'),
           (414, 115, 120, 'int', '0o700'),
           (477, 32, 35, 'int', '470'),
           (488, 57, 75, 'str', "'_mastermind_exec'"),
           (499, 51, 54, 'int', '470'),
           (503, 37, 40, 'int', '470'),
           (503, 59, 62, 'int', '470'),
           (504, 60, 63, 'int', '470'),
           (521, 28, 31, 'int', '470'),
           (569, 66, 69, 'int', '450'),
           (569, 71, 74, 'int', '450'),
           (569, 76, 79, 'int', '450'),
           (569, 81, 84, 'int', '450'),
           (574, 97, 100, 'int', '450'),
           (574, 102, 107, 'int', '0o660'),
           (624, 28, 31, 'int', '450'))}

# Exact accepted R2 HTTP response statuses, not process identities.
# Source83f2 is unchanged; full source hash and all token spans are required.
# Drift, another path, a changed literal or a new UID restores ordinary D8.
REVIEWED_FILES['integrations/mastermind_executive_app/principal_dialogue.py'] = {'sha256': '9403d9ae5f44c3f07ef5f6d4a80b0e30883a9267d6a41e987b5c76f6ef3b64cd',
 'sites': ((95, 45, 48, 'int', '500'),
           (104, 41, 44, 'int', '500'),
           (109, 40, 43, 'int', '400'),
           (115, 41, 44, 'int', '500'))}

REVIEWED_FILES['integrations/mastermind_executive_app/principal_ruling_http.py'] = {'sha256': '1bf02f595c09c9bfde890425ac767cf1160d688b41d5c1ea5020f9b4f3890600',
 'sites': ((45, 120, 123, 'int', '404'),
           (51, 28, 31, 'int', '401'),
           (75, 77, 80, 'int', '413'),
           (80, 28, 31, 'int', '400'))}

REVIEWED_FILES['app/mastermind_os/src/product-acceptance/owner-observation.ts'] = {
    'sha256': 'a914fa318b2a96d4d9d01ee5f378becac222e3750725de99416dff6b463a257a',
    'sites': ((34, 132, 135, 'int', '512'),),
}

# Retained producer: existing private-directory permissions, not native UIDs.
# Runtime bytes and both comparisons are unchanged; exact source and sites only.
REVIEWED_FILES["integrations/session_bridge/r2_plain_review_scopes/candidate/artifact_production.py"] = {
    "sha256": "0be15bd5d3304a65673576fd30386bcc977c02ed8ee28313a4cb1ed454f8c409",
    "sites": ((149, 77, 82, "int", "0o700"), (170, 85, 90, "int", "0o700")),
}

# Scoped independent native-finite-capacity-owner-review-01a12a08-v1 PASS
# on 4c24b21bcc96ea2215e7c3bbc9782b59b9ff46ed approves only the unchanged
# two renderer and 37 lifecycle literal sites above; no new identity exemption.

# Scoped SourceOS initial-reference review, 2026-10-16: fixed predecessor
# validation only. Any changed byte or token restores the generic D8 guard.
REVIEWED_FILES['ops/executive_os/finite_reference_assignment.py'] = {'sha256': '7d2cc97ab91900804f2755b5f11edbd40fa3cca36b6d973ba3e87c5e9a55dc4a', 'sites': ((103, 49, 70, 'str', "'_mastermind_minimax'"), (104, 26, 29, 'int', '470'), (104, 45, 48, 'int', '470'), (104, 65, 68, 'int', '450'), (105, 27, 30, 'int', '450'))}

# Native Root scoped review EC-1 closed: exact fixed directory/HOME permission
# sites only, not principal identity; every changed byte invalidates this pin.
REVIEWED_FILES['ops/executive_os/finite_enrollment_completion.py'] = {'sha256': 'c49496b13380aa2b1d61cd12454ea21a89fc7b34a8de5c16b9ecb25da9afa3b4', 'sites': ((174, 111, 116, 'int', '0o755'), (228, 95, 100, 'int', '0o700'), (289, 26, 31, 'int', '0o700'))}

# --- Native-fabric-quota-continuity release review, 2026-10-18 ---------------
# Exact source bytes and token sites only. Every site is a permission mode, an
# HTTPS .ts.net validator port, an HTTP-status sentinel in a non-importable
# preimage docstring, a grant-lifetime seconds bound, or the existing ten-
# minute observation age already reviewed at the historical research path.
# No process identity literal is exposed; any changed byte or token restores
# the generic D8 scanner to every site below.
# ---------------------------------------------------------------------------

# R2-retained private-directory permission checks. Ownership remains os.getuid();
# the two stat.S_IMODE comparisons against 0o700 are not native UIDs.
# Same bytes/sites already reviewed at the R2 retained path above.
REVIEWED_FILES['ops/native_fabric/quota_continuity/source/artifact_production.py'] = {
    "sha256": "0be15bd5d3304a65673576fd30386bcc977c02ed8ee28313a4cb1ed454f8c409",
    "sites": ((149, 77, 82, "int", "0o700"), (170, 85, 90, "int", "0o700")),
}

# Non-importable preimage suffix; the line-oriented scanner still reads the
# docstring's exact standalone 429. Drift re-exposes the standalone token.
REVIEWED_FILES['ops/native_fabric/quota_continuity/source/bailian_keys.py.preimage'] = {
    "sha256": "435dad2bcde27384c4c47edaea5afdf7f248d10229558193414b105664a9759c",
    "sites": ((540, 66, 69, "int", "429"),),
}

# Studio fabric HTTPS .ts.net validator: only the absent-or-443 explicit
# port is admitted; the canonicalizer preserves an already accepted
# explicit :443 suffix. No credential, query, fragment, or path deviation.
REVIEWED_FILES['ops/native_fabric/quota_continuity/source/fabric_client_projection.py'] = {
    "sha256": "39a138f88f6a3e4fb9b60f4365620ca05903e9f15783f95495627a54a13402e6",
    "sites": ((72, 30, 33, "int", "443"), (83, 15, 18, "int", "443")),
}

# Remaining grant lifetime / start-window seconds bound (660s); not a process
# identity literal.
REVIEWED_FILES['ops/native_fabric/quota_continuity/source/fabric_operator_owner.py'] = {
    "sha256": "a9d5adfa90d081b460a6ad751a705add7ca0387e66266d9cea37eb99c8c09d04",
    "sites": ((242, 81, 84, "int", "660"), (389, 85, 88, "int", "660")),
}

# Existing ten-minute telemetry observation age. Same bytes/sites already
# reviewed at the historical research path below.
REVIEWED_FILES['ops/native_fabric/quota_continuity/source/glm_host_account_readiness.py'] = {
    "sha256": "b8921960e7e46a472b536895b5a6491096627d1c8fd58ea0baf283ff34accc07",
    "sites": ((31, 18, 21, "int", "600"),),
}

# Pre-Job acceptance-maintenance consumer, 2026-10-18 (PR 1609 Repair 3). The
# eight-key protected-group-membership.json validator mirrors the contract the
# acceptance producer (ops/executive_os/acceptance.py, reviewed above at the
# same account regex and 400 <= id < 500 bounds) already writes: it only
# CHECKS a retained receipt's shape. It registers no account, assigns no uid or
# gid and grants nothing. Exact full-file bytes and the three token sites only;
# any changed byte exposes every site to the generic D8 scanner again.
# Re-pinned for the historical-only legacy six-key admission (no new literal; the same three
# tokens moved with the added constant and helper), and again for the comment/docstring
# wording that names the single historical site and the strict candidate re-check.
# Re-pinned for the supersede_preproof_v1 admission: the same three tokens moved
# with the added SCHEMA_PREPROOF constant, preproof_evidence helper, and the
# shared-key canary exception in _validate_superseded_link. No new identity
# literal; the count stays 3 and the existing producer's literal contract is
# unchanged.
# Re-pinned by CRROOM-INT for the F1 citation repair (line numbers in the
# _PREPROOF_RECEIPT_KEYS comments were replaced by qualified producer names);
# token sites are unchanged in kind, spelling, and count.
# Re-pinned for PR 1637 hardening (preproof file recheck, optional lstat, AWAITING_CANARY); sites unchanged.
# Re-pinned for the explicit unstarted PREPROOF successor mode; same three
# guarded literal tokens, unchanged scanner and no new identity exemption.
# Installed-preparation continuation 027be0c0 / source-risk review b29273a0;
# Macro-epoch composition f48d7421 / source-risk review bd9bba4b:
# same three complete runtime tokens and unchanged original top-level ASTs;
# only the reviewed digest and shifted lines change. No new identity exemption.
REVIEWED_FILES['ops/executive_os/acceptance_maintenance.py'] = {
    "sha256": 'f53e9401d28f1053d67a59d375f7380b86271f87278080f7dd972f3d8ff6f7f9',
    "sites": ((104, 31, 56, 'str', 'r"_mastermind_[a-z0-9_]+"'), (1825, 46, 49, 'int', '400'), (1825, 66, 69, 'int', '500')),
}


# PR #1813: unchanged independently reviewed migration-evidence helper 8c7f1584.
# This exact token is the Root config-directory permission mode, not a UID.
# Source, path, AST location and complete token must all match; scanner unchanged.
REVIEWED_FILES['ops/executive_os/schema_upgrade_evidence.py'] = {
    "sha256": '1f316e19da3b2d4f362b64928c7ede1aee0b28301a71990455c138589d9cc402',
    "sites": ((347, 46, 51, 'int', '0o755'),),
}


# PR #1794 source-risk review 5a342984: exact paid source bytes and
# literal sites (including two precise docstring account-name examples). No
# caller identity, permission or runtime admission is granted; any source/token
# drift exposes these sites to the unchanged guard again.
# 2026-11-03 native-status composition: the original three identity comparisons
# are unchanged; the extra startup module names shift the last two sites by five
# lines. Previous source SHA d7fcc70d413c5445ee38c21dc1e19b584da12e2afb3eab02fcd39e9241f469ad.
# No new identity site is qualified; any source drift restores the ordinary guard.
REVIEWED_FILES.update({'control_plane/paid_fabric_backend.py': {'sha256': '936701c295116b786dc36d018357dfe0217c7cee37c4b11c2b14223c59c4a664',
 'sites': ((120, 73, 76, 'int', '501'), (310, 78, 81, 'int', '450'), (405, 83, 86, 'int', '501'))},
 'control_plane/paid_fabric_wire.py': {'sha256': '6c9c16eaa48fa7f5ac7cbd4eaa113b619a5bb1e3d65ef69ab55c6f0d839fc9c6',
 'sites': ((98, 35, 38, 'int', '501'),)},
 'control_plane/paid_model_execution_principal.py': {'sha256': 'a20a4115599d93cb8a9c5397a84a58624f9cd24bb5ee00e219add653f832e79c',
                                                     'sites': ((63, 18, 21, 'int', '512'),)},
 'control_plane/paid_model_terminal_evidence.py': {'sha256': '81eade4a8dc6739508d94292df5430a3bf6d0da016194990a2057ace6ced98ac',
                                                   'sites': ((838, 24, 29, 'int', '0o777'),)},
 'control_plane/paid_quiesce_transport.py': {'sha256': 'ce1ce7afcd1f26d9202e2e7376159218e80052c0a36c6e99868d56707befce27',
                                             'sites': ((162, 128, 131, 'int', '450'),
                                                       (162, 132, 137, 'int', '0o660'),
                                                       (183, 34, 37, 'int', '501'))},
 'control_plane/worker_execution_contract.py': {'sha256': '07621e74ea343f2c0ad320a8f019e55365b14b1ad988e5d1145ba1d7c2344da2',
                                                'sites': ((60, 33, 36, 'int', '512'),)},
 'ops/executive_os/canonical_paid_actions.py': {'sha256': 'f12ddfb1365d3bdfd5a3bc4b90b9d21aac17e02e797dbad489b21acf211e282c',
 'sites': ((56, 71, 74, 'int', '501'),)},
 'ops/executive_os/canonical_paid_definition.py': {'sha256': 'a2009ce6c555d7de9bd6a9497871a33f1edb7d2bffe19f38ffbf91790f64349f',
                                                   'sites': ((17, 45, 57, 'str', '_mastermind_'),
                                                             (91, 18, 21, 'int', '501'),
                                                             (158, 49, 54, 'int', '0o755'),
                                                             (164,
                                                              4,
                                                              24,
                                                              'str',
                                                              "'_mastermind_worker'"),
                                                             (164,
                                                              26,
                                                              47,
                                                              'str',
                                                              "'_mastermind_minimax'"),
                                                             (166, 32, 46, 'str', "'_mastermind_'"),
                                                             (252, 13, 25, 'str', '_mastermind_'),
                                                             (335, 58, 63, 'int', '0o660'),
                                                             (745, 54, 59, 'int', '0o700'),
                                                             (745, 61, 66, 'int', '0o755'),
                                                             (772, 45, 50, 'int', '0o755'),
                                                             (825, 29, 34, 'int', '0o700'),
                                                             (831, 28, 33, 'int', '0o700'),
                                                             (834, 88, 93, 'int', '0o700'),
                                                             (887, 71, 76, 'int', '0o700'),
                                                             (896, 28, 33, 'int', '0o755'),
                                                             (904, 75, 80, 'int', '0o755'),
                                                             (916, 60, 65, 'int', '0o700'))},
 'ops/executive_os/canonical_paid_lifecycle.py': {'sha256': '94be5849ac3b87d3ba1eeec382529869b72fd9a1e4e2b920db09e49f753b0236',
                                                  'sites': ((56, 13, 16, 'int', '501'),
                                                            (57, 14, 17, 'int', '450'),
                                                            (458, 53, 58, 'int', '0o660'),
                                                            (546, 48, 53, 'int', '0o660'),
                                                            (752, 53, 58, 'int', '0o755'),
                                                            (790, 84, 89, 'int', '0o755'))},
 'ops/executive_os/canonical_paid_qualification.py': {'sha256': '9fe50017d44b9b9863ad08d2d85ea22c301f6975b7e91421379948dce7d7e1f4',
 'sites': ((162, 48, 53, 'int', '0o755'),
           (613, 21, 26, 'int', '0o700'),
           (631, 74, 79, 'int', '0o700'),
           (643, 25, 30, 'int', '0o700'),
           (653, 22, 27, 'int', '0o755'),
           (661, 82, 87, 'int', '0o755'))},
 'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py': {'sha256': '93267de79c92231f853fc16e03f939e8d52d3322d19a828a568ffcb5d7a7f867',
                                                                'sites': ((1280,
                                                                           46,
                                                                           49,
                                                                           'int',
                                                                           '503'),
                                                                          (1288,
                                                                           42,
                                                                           45,
                                                                           'int',
                                                                           '401'),
                                                                          (1338,
                                                                           38,
                                                                           41,
                                                                           'int',
                                                                           '502'),
                                                                          (1446,
                                                                           20,
                                                                           23,
                                                                           'int',
                                                                           '401'),
                                                                          (1491,
                                                                           24,
                                                                           27,
                                                                           'int',
                                                                           '401'),
                                                                          (1521,
                                                                           24,
                                                                           27,
                                                                           'int',
                                                                           '401'),
                                                                          (1693,
                                                                           39,
                                                                           42,
                                                                           'int',
                                                                           '502'),
                                                                          (1697,
                                                                           34,
                                                                           37,
                                                                           'int',
                                                                           '502'),
                                                                          (1699,
                                                                           32,
                                                                           35,
                                                                           'int',
                                                                           '502'))},
 'ops/native_fabric/paid_canonical_glm/source/glm_shim.py': {'sha256': '020b9ef9c59260d07980a23f2ac277d4e4d7350ff81e010d071fd733cc05b1fc',
                                                             'sites': ((1217, 46, 49, 'int', '503'),
                                                                       (1225, 42, 45, 'int', '401'),
                                                                       (1275, 38, 41, 'int', '502'),
                                                                       (1375, 20, 23, 'int', '401'),
                                                                       (1420, 24, 27, 'int', '401'),
                                                                       (1450, 24, 27, 'int', '401'),
                                                                       (1578, 39, 42, 'int', '502'),
                                                                       (1582, 34, 37, 'int', '502'),
                                                                       (1584,
                                                                        32,
                                                                        35,
                                                                        'int',
                                                                        '502'))},
 'ops/native_fabric/quota_continuity/candidate/paid_host_qualification.py': {'sha256': 'e4cb143b13324bd5ce4d96af5396054b3c63e1b82c831edae4516f37e495a1b0', 'sites': ((34, 17, 20, 'int', '501'), (452, 85, 90, 'int', '0o700'))},
 'ops/native_fabric/quota_continuity/candidate/paid_model_owner.py': {'sha256': '75bbacb052dcb9374245854e2e6b8681fa369e034000689df0d4f752bd1b6e3b',
 'sites': ((147, 32, 37, 'int', '0o700'), (230, 68, 73, 'int', '0o700'))},
 'scripts/executive_paid_fabric_shim.py': {'sha256': 'e80b95a09ce31153e7bff2ea7b85dd1eb8d8850d4d6029ec27250cd8f13228f1',
                                           'sites': ((43, 81, 84, 'int', '450'),)}})

# Gateway fixed Studio UID, incumbent config/plist mode, and the normal
# installer's exact /Library/Application Support 0:80:0755 ancestor.
# Exact source and Constant-token sites are frozen for the final changed-risk
# review; this does not authorize publication, runtime admission or release.
# No generic numeric exception is added: source/path/site drift exposes all
# literals again through the existing D8 scanner.
# Finite-workstream template derivation changes only _gateway_templates.
# The same four whole Constant tokens, relative AST paths and complete
# enclosing identity owners remain unchanged; later lines shift by one.
REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = {
    'sha256': '93cb7727512d1922461272e8d0b4a2557fa39d51d9a88e18597401f1731ea83a',
    'sites': ((335, 24, 27, 'int', '501'),
              (6556, 35, 37, 'int', '80'),
              (6557, 50, 55, 'int', '0o755'),
              (7094, 41, 46, 'int', '0o644')),
}

# The same closed Studio reader's fixed observed UID. Frozen corrected helper
# bytes are subject to the integrated G1-G3 review, not an activation grant.
REVIEWED_FILES['ops/executive_os/os_gateway_studio_reader.py'] = {
    'sha256': 'eabe51db9bb94dc3589b8d05a7f4bbe42799d179d8c8d26e6be534a68612c0ee',
    'sites': ((60, 21, 24, 'int', '501'),),
}


# Fixed pre-census ancestor permission modes; not account UIDs. Only the
# exact reviewed source, AST Constant and complete token qualify.
REVIEWED_FILES['control_plane/executive_backup.py'] = {
    'sha256': '058965ae78b61f072ba3720f877bac7b54538a6e06f296db7135217cf05721cd',
    'sites': ((3505, 39, 44, 'int', '0o711'), (3507, 43, 48, 'int', '0o700'), (3509, 39, 44, 'int', '0o755')),
}

# Input-mode bounds and exact ignored Linux symlink mode, never target authority.
REVIEWED_FILES['ops/native_fabric/quota_continuity/candidate/paid_initializer.py'] = {'sha256': 'd203b1363cdc6f926d9542a2ecfb2ec6b24dd1da46c3fd1f527caea232132749',
 'sites': ((71, 35, 40, 'int', '0o777'), (216, 30, 35, 'int', '0o777'), (226, 33, 38, 'int', '0o777'))}

# Exact reviewed recurring-readiness principal checks; no runtime admission.
REVIEWED_FILES['ops/native_fabric/quota_continuity/candidate/paid_host_readiness.py'] = {'sha256': '115bad457d738af088ec4eed79ff56f56b0f154e56521e0093839daf087b9a66',
 'sites': ((454, 95, 98, 'int', '501'),
           (456, 72, 75, 'int', '501'),
           (807, 26, 29, 'int', '501'),
           (811, 63, 66, 'int', '501'),
           (857, 57, 60, 'int', '501'))}
# #1515 source-pin alignment candidate on unchanged app.py blob.
# Eight exact action refusal statuses manually inspected; independent current-
# head re-review remains required before protected release. These are HTTP response statuses,
# not account/UID/GID values. Any changed byte/site restores ordinary D8.
REVIEWED_FILES['control_plane/workspace_control_room_actions.py'] = {
    'sha256': 'ff72b9f6d5165cd07bc41052fc322da84e02eef2e3041f58e7569de4f37bfb50',
    'sites': ((135, 58, 61, 'int', '409'),),
}
# Current-base composition keeps the original action-handler AST unchanged.
# These eight sites retain the same exact HTTP status literals.
# 2026-11-03 catalog composition adds fixed metadata GETs before that handler;
# its AST is still identical and all eight sites move by 58 lines. Previous
# source SHA de6f82cd7861cd79d90bc058c2753f5912a20e47c4ff992201962d8abdc78f31.
# Journal source-only read composition: exact unchanged action-handler AST and
# original eight complete literal tokens; new GET registration is reviewed separately.
# Composed READ source: original eight whole action tokens and action AST unchanged.
REVIEWED_FILES['integrations/mastermind_workspace_app/app.py'] = {'sha256': 'ed6e016eb9f65121baff9e9e41d5a7aa98c9edf20765d5b34224f4518e5bd5dd', 'sites': ((923, 71, 74, 'int', '400'), (934, 71, 74, 'int', '403'), (942, 71, 74, 'int', '400'), (948, 79, 82, 'int', '400'), (957, 71, 74, 'int', '400'), (967, 71, 74, 'int', '403'), (972, 76, 79, 'int', '503'), (978, 71, 74, 'int', '403'))}

# Source-only stateless H1 packet: fixed outer byte length/permission mode and
# native transport UID. Exact file hash, AST Constants and whole tokens only.
REVIEWED_FILES['tools/admin_inputs/h1_input_wrapper.py'] = {
    'sha256': '726544463fa6c4058512a558f70e5d0c585f9742594d20363f873b0b2d0fb8e7',
    'sites': ((244, 76, 79, 'int', '587'), (244, 107, 112, 'int', '0o755'), (257, 124, 127, 'int', '501')),
}

# Same independently reviewed initialize UA string-length cap as a057927b;
# full W3 composition/source review2fcbe954 preserves that exact Constant.
# Bind the reviewed W3 postimage, including retained-input evidence, only.
# This is not a UID exemption or a scanner/defaults change.
REVIEWED_FILES['control_plane/codex_operator_adapter.py'] = {
    'sha256': 'f6b94b81eec07354bf74ae6d589e76b43255604006b11cf7a7712a02fe513379',
    'sites': ((190, 46, 49, 'int', '512'),),
}

# Frozen Portfolio mmtask source restored as reviewable data (P7.T5).
# These are text display bounds, never UIDs. The payload's 500 Constant follows
# an em dash, so its strictly opt-in site uses Python UTF-8 byte columns and
# complete typed-Constant qualification. All legacy ASCII records are unchanged.
REVIEWED_FILES['integrations/session_bridge/mmtask_restore/payload/mmtask'] = {
    'sha256': '711ba4f46c80e518d99167877738db9e92182b78bf7b4e3052bcfee79316d54a',
    'sites': ((659, 93, 96, 'int', '400'),),
    'utf8_sites': ((214, 135, 138, 'int', '500'),),
}
REVIEWED_FILES['integrations/session_bridge/mmtask_restore/preimage/mmtask'] = {
    'sha256': '9567ecad658e50b149a14f4c0cd0c7b42d15ad546b0508e2153619f14d0eb336',
    'sites': ((556, 93, 96, 'int', '400'),),
}

# Exact unchanged JSON traversal node budget, never an OS identity or grant.
# Any changed source byte/site returns this numeric token to the ordinary D8 guard.
REVIEWED_FILES['app/mastermind_os/src/admission/project-admission-command-port.ts'] = {'sha256': 'bc14696fce184ce0d186431f044a79d93c61ca07b8c4eaf718e4ed19b3af2571', 'sites': ((37, 87, 90, 'int', '400'),)}

# Exact reviewed archive catalogue cardinality bound; never a host UID or grant.
REVIEWED_FILES['app/mastermind_os/src/projects/archive/project-archive-continuation.ts'] = {'sha256': '22dc5ee85b1ca02464e20cd77b52cdc6cc9ea5e8f19161cf78f81e734934d84d', 'sites': ((29, 78, 81, 'int', '500'),)}

# Exact Knowledge path/generation bounds and inert synthetic PR fixture numbers.
# These are not OS identities; full-source drift exposes every token again.
REVIEWED_FILES['app/mastermind_os/src/knowledge/library/project-data-observation.ts'] = {'sha256': '8255d63192da282f52f0f81e2963aa6ff3084e5065d60e8516d483fab3122b79', 'sites': ((91, 97, 100, 'int', '512'),)}
REVIEWED_FILES['app/mastermind_os/src/knowledge/library/project-knowledge-port.ts'] = {'sha256': '9a41d0f5bafef2ab8168509aaf3ff7e37369b619230c2c380bedb2b586d7eaf2', 'sites': ((46, 64, 67, 'int', '512'),)}
REVIEWED_FILES['app/mastermind_os/src/fixtures/knowledge-data-observation-owner.json'] = {'sha256': 'd12878bdff07fcdb6bfa05ba2c1694c7600416c7407a9e84e87e20dcc116f118', 'sites': ((119, 16, 19, 'int', '401'),)}
REVIEWED_FILES['app/mastermind_os/src/fixtures/knowledge-write-owner.json'] = {'sha256': 'cb6d4c43fc821993f664a9bc75ccf3f38d76bbaff58e36363c6e700b7e3b6856', 'sites': ((97, 22, 25, 'int', '401'), (413, 22, 25, 'int', '402'))}

# PR1917 source review5761933327 at63d184218e8d6a2b7da48f98045a2e67f504f5aa:
# default HTTPS port in the exact parsed-origin condition, not a UID/GID.
# Existing full-file SHA + token-span verification binds this one Constant;
# any source/path/context drift restores the ordinary D8 scanner. This does
# not change the URL/port policy or the separate reviewed Squid ACL exception.
REVIEWED_FILES['integrations/hermes_secretary/tab_sweep.py'] = {
    'sha256': '12d2c8f059f941eb908cc9d7ec3651763f8102832e05435118ce8e1385d5fd46',
    'sites': ((19, 77, 80, 'int', '443'),),
}

# NEXT accepted source: callback input bound / existing HTTP permission denial,
# never an OS identity. Exact whole-source hash and token sites only.
REVIEWED_FILES['app/mastermind_os/src-tauri/src/terminal_session_core.rs'] = {'sha256': '4d97af924ce072ee6135e21101871fbae75ddcdaaf61989482f4781b112fd133', 'sites': ((731, 49, 52, 'int', '512'),)}

# NEXT accepted source: callback input bound / existing HTTP permission denial,
# never an OS identity. Exact whole-source hash and token sites only.
# BYOK/Instructions composition preserves the complete permission handler AST;
# only its enclosing source and four HTTP denial token positions change.
REVIEWED_FILES['control_plane/workspace_read_service.py'] = {'sha256': 'de69741a1be8c3e980815a284c277da04843f16f34ce303141d482ff7ec64a66', 'sites': ((711, 93, 96, 'int', '403'), (713, 56, 59, 'int', '403'), (720, 46, 49, 'int', '403'), (721, 56, 59, 'int', '403'))}
# S14 reviewed private-directory comparison (Root + independent89cb). This
# single permission check grants no identity or chmod capability. Any path,
# token-coordinate or complete-postimage drift restores ordinary D8 scrutiny.
REVIEWED_FILES['ops/native_fabric/quota_continuity/candidate/post_failure_observation.py'] = {
    'sha256': '80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337',
    'sites': ((294, 79, 84, 'int', '0o700'),),
}


# PR1890 attended parent classification under the current Chairman source waiver:
# two CSS dimensions and five graph coordinates, never identities or grants.
# Each complete token is on an ASCII physical line. Exact final HTML bytes and
# seven spans only; every source/context/path change restores ordinary D8.
# This pin is not independent/formal review or a CodeQL finding disposition.
REVIEWED_FILES['research/competitive_intelligence/x_engagement/2026-10-30/account_network_interactive.html'] = {
    'sha256': '62492c23f2d6a21d389268e51823f6b2f130e2e47a64f17bcfc38e886e9cc3d8',
    'sites': (
        (8, 77, 80, 'int', '680'),
        (37, 17, 20, 'int', '900'),
        (70, 45, 48, 'int', '495'),
        (70, 51, 54, 'int', '535'),
        (72, 45, 48, 'int', '720'),
        (74, 10, 13, 'int', '922'),
        (79, 56, 59, 'int', '800'),
    ),
}

# BYOK metadata READ re-pin: same eight action literals and unchanged action AST.
# Attended parent source check under the current Chairman waiver; no formal approval claim.
