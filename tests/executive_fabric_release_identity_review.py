"""Frozen reviewed literals for the Fabric release, never runtime authority.

Exact source hashes and token spans only. Each site is a permission, an input
bound or a reviewed primary/secondary identity exclusion. Shell and retained
.py.base are scanned as source too. Any byte drift exposes every site again;
these pins are not learned or refreshed by the tests.
"""

REVIEWED_FILES = {
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
 'ops/executive_os/acceptance.py': {'sha256': '6bb540de6bafd49b08ae0eb085c5e9dd6ddd67e9c9de92549850f6809d09672b',
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
                                    'sites': ((887, 59, 62, 'int', '454'),
                                              (887, 64, 67, 'int', '455'),
                                              (887, 69, 72, 'int', '456'),
                                              (888, 23, 26, 'int', '450'),
                                              (888, 45, 48, 'int', '450'),
                                              (889, 49, 52, 'int', '400'),
                                              (889, 64, 67, 'int', '500'),
                                              (896, 28, 53, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (904, 39, 64, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (965, 44, 47, 'int', '454'),
                                              (965, 49, 52, 'int', '455'),
                                              (965, 54, 57, 'int', '456'),
                                              (966, 44, 47, 'int', '454'),
                                              (966, 49, 52, 'int', '455'),
                                              (966, 54, 57, 'int', '456'),
                                              (1087, 56, 59, 'int', '400'),
                                              (1087, 85, 88, 'int', '500'),
                                              (1088, 85, 88, 'int', '453'),
                                              (1088, 90, 93, 'int', '454'),
                                              (1088, 95, 98, 'int', '455'),
                                              (1088, 100, 103, 'int', '456'))},
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
REVIEWED_FILES['ops/executive_os/acceptance_maintenance.py'] = {
    "sha256": "3c45fc1c851576e5260f4544c3329915b4b3ce0efdaadf8d3ad002546acd4bc6",
    "sites": ((73, 31, 56, "str", 'r"_mastermind_[a-z0-9_]+"'),
              (903, 46, 49, "int", "400"),
              (903, 66, 69, "int", "500")),
}


# PR #1794 source-risk review 5a342984: exact paid source bytes and
# literal sites (including two precise docstring account-name examples). No
# caller identity, permission or runtime admission is granted; any source/token
# drift exposes these sites to the unchanged guard again.
REVIEWED_FILES.update({'control_plane/paid_fabric_backend.py': {'sha256': '049fe372eb5c3e292524957ba6b57d79cc5a9326e2563207cb1daa283a69f475',
                                          'sites': ((120, 73, 76, 'int', '501'),
                                                    (303, 78, 81, 'int', '450'),
                                                    (398, 83, 86, 'int', '501'))},
 'control_plane/paid_fabric_wire.py': {'sha256': '5315eb7578cf49c0c405d7d7ae3b52d6ad3056c47f9d8f440008297b52e3004c',
                                       'sites': ((56, 35, 38, 'int', '501'),)},
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
 'ops/executive_os/canonical_paid_actions.py': {'sha256': '957b4a04432ca5ebbb954f4fa76ab74e4d383f233a58449ffc3cf6c1294212c9',
                                                'sites': ((56, 71, 74, 'int', '501'),)},
 'ops/executive_os/canonical_paid_definition.py': {'sha256': '47103c495dcd6cc8393c55d066286d7dbc732be95762b592ed2780815be384e1',
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
                                                             (747, 54, 59, 'int', '0o700'),
                                                             (747, 61, 66, 'int', '0o755'),
                                                             (774, 45, 50, 'int', '0o755'),
                                                             (827, 29, 34, 'int', '0o700'),
                                                             (833, 28, 33, 'int', '0o700'),
                                                             (836, 88, 93, 'int', '0o700'),
                                                             (889, 71, 76, 'int', '0o700'),
                                                             (898, 28, 33, 'int', '0o755'),
                                                             (906, 75, 80, 'int', '0o755'),
                                                             (918, 60, 65, 'int', '0o700'))},
 'ops/executive_os/canonical_paid_lifecycle.py': {'sha256': '94be5849ac3b87d3ba1eeec382529869b72fd9a1e4e2b920db09e49f753b0236',
                                                  'sites': ((56, 13, 16, 'int', '501'),
                                                            (57, 14, 17, 'int', '450'),
                                                            (458, 53, 58, 'int', '0o660'),
                                                            (546, 48, 53, 'int', '0o660'),
                                                            (752, 53, 58, 'int', '0o755'),
                                                            (790, 84, 89, 'int', '0o755'))},
 'ops/executive_os/canonical_paid_qualification.py': {'sha256': 'c228bea84a56466f4c7694535f5de5acce005e45fc9207780162bec7067c77e2',
                                                      'sites': ((161, 48, 53, 'int', '0o755'),
                                                                (612, 22, 27, 'int', '0o700'),
                                                                (617, 22, 27, 'int', '0o755'),
                                                                (626, 82, 87, 'int', '0o755'))},
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
 'ops/native_fabric/quota_continuity/candidate/paid_host_qualification.py': {'sha256': 'd2f5be14f345cf00b4bd4357d705713a24e373a7d1675229aab6202f0d500cad',
                                                                             'sites': ((34,
                                                                                        17,
                                                                                        20,
                                                                                        'int',
                                                                                        '501'),
                                                                                       (382,
                                                                                        85,
                                                                                        90,
                                                                                        'int',
                                                                                        '0o700'))},
 'ops/native_fabric/quota_continuity/candidate/paid_model_owner.py': {'sha256': 'a0bc9df6070ab23e555df5432ea0ca1b5dd859f8366b6656630e241588de216c',
                                                                      'sites': ((138,
                                                                                 32,
                                                                                 37,
                                                                                 'int',
                                                                                 '0o700'),
                                                                                (220,
                                                                                 68,
                                                                                 73,
                                                                                 'int',
                                                                                 '0o700'))},
 'scripts/executive_paid_fabric_shim.py': {'sha256': 'e80b95a09ce31153e7bff2ea7b85dd1eb8d8850d4d6029ec27250cd8f13228f1',
                                           'sites': ((43, 81, 84, 'int', '450'),)}})

# Gateway fixed Studio UID, incumbent config/plist mode, and the normal
# installer's exact /Library/Application Support 0:80:0755 ancestor.
# Exact source and Constant-token sites are frozen for the final changed-risk
# review; this does not authorize publication, runtime admission or release.
# No generic numeric exception is added: source/path/site drift exposes all
# literals again through the existing D8 scanner.
REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = {
    'sha256': 'e0ffcafab71d4531465004ae35f34e7b69b22d77a1f65b3ff5a6d27e064c1687',
    'sites': ((335, 24, 27, 'int', '501'),
              (6476, 35, 37, 'int', '80'),
              (6477, 50, 55, 'int', '0o755'),
              (7014, 41, 46, 'int', '0o644')),
}

# The same closed Studio reader's fixed observed UID. Frozen corrected helper
# bytes are subject to the integrated G1-G3 review, not an activation grant.
REVIEWED_FILES['ops/executive_os/os_gateway_studio_reader.py'] = {
    'sha256': 'aea09940df9475c571002309fa70eae88d19d2b2034b9f1a4700a3e86619534d',
    'sites': ((55, 21, 24, 'int', '501'),),
}
