"""Frozen reviewed literals for the Fabric release, never runtime authority.

Exact source hashes and token spans only. Each site is a permission, an input
bound or a reviewed primary/secondary identity exclusion. Shell and retained
.py.base are scanned as source too. Any byte drift exposes every site again;
these pins are not learned or refreshed by the tests.
"""

REVIEWED_FILES = {
    # POSIX stat.st_blocks is counted in 512-byte units, not account identity.
    # Exact reviewed preview source/site only; any byte drift re-exposes it.
    'ops/fleet_storage_cleanup/linux_cache_preview.py': {
        'sha256': '1fc025101f08a052223a79f494fa28c489f48a85590bc9b37e8ef1af0ea3796d',
        'sites': ((204, 43, 46, 'int', '512'),),
    },
    # Reviewed application HTTP statuses, permission modes and bounded limits.
    # These exact spans contain no account/principal identity. Byte drift
    # exposes the source to the original guard again.
    'app/main.py': {
        "sha256": '5c4ff5854aca04bb1f7395c2afdcf72ae319ee8fe82041f679d1bf16addcc081',
        "sites": (
            (652, 44, 47, 'int', '400'),
            (689, 44, 47, 'int', '400'),
        ),
    },
    'ops/native_fabric/quota_continuity/candidate/go_shim.py': {'sha256': 'a5af142fda4911f6dbe72896dd37df3b10d24be26fcff57da61a4ad636c4c14e', 'sites': [[469, 66, 69, 'int', '502'], [1689, 32, 37, 'int', '0o700'], [2040, 140, 143, 'int', '900'], [2042, 33, 36, 'int', '900'], [2105, 22, 25, 'int', '429'], [2293, 79, 82, 'int', '500'], [2371, 34, 37, 'int', '400'], [2386, 33, 36, 'int', '500'], [2406, 34, 37, 'int', '502'], [2753, 92, 95, 'int', '400'], [2760, 99, 102, 'int', '503'], [2763, 80, 83, 'int', '409'], [2795, 110, 113, 'int', '503'], [2801, 100, 103, 'int', '409'], [2808, 101, 104, 'int', '409'], [2824, 31, 34, 'int', '409'], [2824, 51, 54, 'int', '503'], [2832, 73, 76, 'int', '409'], [2836, 99, 102, 'int', '503'], [2941, 107, 110, 'int', '503'], [2950, 102, 105, 'int', '400'], [2971, 96, 99, 'int', '429'], [2981, 103, 106, 'int', '503'], [2998, 105, 108, 'int', '503'], [3036, 27, 30, 'int', '503'], [3041, 101, 104, 'int', '502'], [3049, 91, 94, 'int', '401'], [3053, 96, 99, 'int', '400'], [3075, 476, 479, 'int', '512'], [3079, 94, 97, 'int', '400'], [3090, 101, 104, 'int', '409'], [3092, 110, 113, 'int', '503'], [3103, 101, 104, 'int', '409'], [3111, 105, 108, 'int', '409'], [3114, 101, 104, 'int', '409'], [3117, 104, 107, 'int', '400'], [3127, 105, 108, 'int', '409'], [3137, 94, 97, 'int', '400'], [3153, 109, 112, 'int', '400'], [3156, 96, 99, 'int', '400'], [3169, 96, 99, 'int', '429'], [3179, 102, 105, 'int', '503'], [3187, 106, 109, 'int', '429'], [3218, 103, 106, 'int', '503'], [3229, 272, 275, 'int', '502'], [3323, 23, 26, 'int', '400'], [3396, 35, 38, 'int', '429'], [3425, 37, 40, 'int', '404'], [3456, 27, 30, 'int', '400'], [3459, 27, 30, 'int', '400'], [3462, 27, 30, 'int', '400'], [3468, 31, 34, 'int', '400'], [3475, 31, 34, 'int', '429']]},
    'ops/native_fabric/quota_continuity/candidate/native_go_entry.py': {'sha256': '5fc47d9ed40754760e5d6cffbfd00a2cf8bb74cb293387acb1fb0cd875db5878', 'sites': [[1044, 60, 65, 'int', '0o700']]},
    'ops/native_fabric/quota_continuity/source/go_shim.py': {
        "sha256": '4a41548a757f763ed5210df96aff6c7148d25d9e192cd3d849e108e1e917d100',
        "sites": (
            (1035, 32, 37, 'int', '0o700'),
            (1365, 140, 143, 'int', '900'),
            (1367, 33, 36, 'int', '900'),
            (1430, 22, 25, 'int', '429'),
            (1516, 79, 82, 'int', '500'),
            (1594, 34, 37, 'int', '400'),
            (1609, 33, 36, 'int', '500'),
            (1629, 34, 37, 'int', '502'),
            (1872, 23, 26, 'int', '400'),
            (1919, 35, 38, 'int', '429'),
            (1943, 37, 40, 'int', '404'),
            (1974, 27, 30, 'int', '400'),
            (1977, 27, 30, 'int', '400'),
            (1980, 27, 30, 'int', '400'),
            (1986, 31, 34, 'int', '400'),
            (1993, 31, 34, 'int', '429'),
        ),
    },
    # Frozen GLM account-admission evidence: these are elapsed-time bounds,
    # not user identities. Whole-file hashes and exact sites fail closed on
    # any changed meaning, added identity, or modified retained traceback.
    "research/fabric_glm_account_admission_20261014/baseline.quota_remote.py": {
        "sha256": "80ce4151a5d3f05528bc3c5e9af214d510ad9d9f17803c62f01a4c2d818ec5ff",
        "sites": ((22, 10, 13, "int", "600"),),
    },
    "research/fabric_glm_account_admission_20261014/quota_remote.py": {
        "sha256": "a1dab11da10264836e6271955b375b8e6508c23f23d0444c99d96464deb70f2b",
        "sites": ((22, 10, 13, "int", "600"),),
    },
    "research/fabric_glm_account_admission_20261014/BASELINE.xml": {
        "sha256": "538923697693ccd4c5e836de20466cbe2f4d2ae1f0ca189da194a5b0d0d5b64a",
        "sites": ((19, 46, 49, "int", "600"),),
    },
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
    'integrations/session_bridge/bound_launch_capture/runtime/lane_runtime.py': {'sha256': '764d140d598734d3607f697bea911c873d72ede08331308347d45a8f9451a996',
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
 'ops/executive_os/acceptance.py': {'sha256': '2a2956df8847ec625f4a94bac36e494797644e75540ccc5b51bb7162d032ace0',
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
                                    # PR #2151: retained-selection validation adds six lines.
                                    # The same 21 complete tokens and columns remain; only
                                    # this reviewed file digest and line coordinates change.
                                    'sites': ((903, 59, 62, 'int', '454'),
                                              (903, 64, 67, 'int', '455'),
                                              (903, 69, 72, 'int', '456'),
                                              (904, 23, 26, 'int', '450'),
                                              (904, 45, 48, 'int', '450'),
                                              (905, 49, 52, 'int', '400'),
                                              (905, 64, 67, 'int', '500'),
                                              (912, 28, 53, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (920, 39, 64, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (981, 44, 47, 'int', '454'),
                                              (981, 49, 52, 'int', '455'),
                                              (981, 54, 57, 'int', '456'),
                                              (982, 44, 47, 'int', '454'),
                                              (982, 49, 52, 'int', '455'),
                                              (982, 54, 57, 'int', '456'),
                                              (1103, 56, 59, 'int', '400'),
                                              (1103, 85, 88, 'int', '500'),
                                              (1104, 85, 88, 'int', '453'),
                                              (1104, 90, 93, 'int', '454'),
                                              (1104, 95, 98, 'int', '455'),
                                              (1104, 100, 103, 'int', '456'))},
 'ops/executive_os/attended_worker_definition.py': {'sha256': '267ca3fceea48d2c3a1e8a4aaefbf8a90bd595d0c324f1a503826e9604ead92d',
 'sites': ((255, 31, 51, 'str', "'_mastermind_worker'"), (351, 95, 100, 'int', '0o660'))},
 'ops/executive_os/bootstrap-host.sh': {'sha256': 'acb2c16a703b018fe110bf88ff576b60a32b2d029db24a769e58dac3d98daf60',
 'sites': ((784, 21, 43, 'str', '_mastermind_[a-z0-9_]*'),
           (786, 97, 120, 'str', '_mastermind_agent_relay'),
           (792, 89, 92, 'int', '457'))},    # Application claim lifetime cap; this literal is not host identity.
    "ops/native_fabric/quota_continuity/candidate/go_lease_capability.py": {
        "sha256": "c4b7ec997cb73a5fbbcd40868de9f9825e18770a82ba4202b8a6de27c9dbcc86",
        "sites": ((326, 113, 116, "int", "900"),),
    },
}

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

# H4 capacity-bridge and native-writer receipts: the same class of proof record.
# Each entry records the existing Darwin host's observed st_uid/uid in postimage
# ownership metadata; observations, not runtime defaults, service enrollment or
# authorization. Preserve the receipts byte-for-byte. Only these typed integer
# tokens in the three exact files are reviewed; any byte or path drift restores
# the original identity guard for the complete receipt.
REVIEWED_FILES["review_evidence/hermes_h4/capacity-bridge-source-install-20261107.json"] = {
    "sha256": "28cd93c3521d615b85ea70d7cba1330c3aded05a0cb5727a9358bf55657d0b0a",
    "sites": (),
    "utf8_sites": (
        (8, 11, 14, "int", "501"),
        (19, 11, 14, "int", "501"),
    ),
}
REVIEWED_FILES["review_evidence/hermes_h4/combined-20261108/native-preimages.json"] = {
    "sha256": "61348fd1bff786831f9ede279824dc749c9bb38472d42789374e0b5a9d3cc9e4",
    "sites": (),
    "utf8_sites": (
        (39, 18, 21, "int", "501"),
        (52, 18, 21, "int", "501"),
        (65, 18, 21, "int", "501"),
        (78, 18, 21, "int", "501"),
        (91, 18, 21, "int", "501"),
        (104, 18, 21, "int", "501"),
        (121, 18, 21, "int", "501"),
        (134, 18, 21, "int", "501"),
        (147, 18, 21, "int", "501"),
        (160, 18, 21, "int", "501"),
        (173, 18, 21, "int", "501"),
        (186, 18, 21, "int", "501"),
        (199, 18, 21, "int", "501"),
        (212, 18, 21, "int", "501"),
        (229, 18, 21, "int", "501"),
        (242, 18, 21, "int", "501"),
        (263, 18, 21, "int", "501"),
        (276, 18, 21, "int", "501"),
        (289, 18, 21, "int", "501"),
        (302, 18, 21, "int", "501"),
        (319, 18, 21, "int", "501"),
    ),
}
REVIEWED_FILES["review_evidence/hermes_h4/native-writer-delta-20261107.json"] = {
    "sha256": "b378d4f5b7194c8a05d7e52fe412c8db28139f16c8ed18ea4f60cca00b1a9340",
    "sites": (),
    "utf8_sites": (
        (26, 18, 21, "int", "501"),
        (39, 18, 21, "int", "501"),
        (52, 18, 21, "int", "501"),
        (65, 18, 21, "int", "501"),
        (78, 18, 21, "int", "501"),
        (91, 18, 21, "int", "501"),
        (108, 18, 21, "int", "501"),
        (121, 18, 21, "int", "501"),
        (134, 18, 21, "int", "501"),
        (151, 18, 21, "int", "501"),
        (164, 18, 21, "int", "501"),
        (177, 18, 21, "int", "501"),
        (190, 18, 21, "int", "501"),
        (203, 18, 21, "int", "501"),
        (216, 18, 21, "int", "501"),
        (229, 18, 21, "int", "501"),
    ),
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
# PR #1329 accepted-V2 carry: the same complete account-pattern token and
# attended worker UID/GID bounds move with the qualified maintenance source.
# Both owning constructs remain byte-identical; no new identity exemption.
REVIEWED_FILES['ops/executive_os/acceptance_maintenance.py'] = {
    "sha256": 'febdc61cc241058c8b5e896290e62e0acc342ddf08010fbd36a6e24399748f56',
    "sites": ((111, 31, 56, 'str', 'r"_mastermind_[a-z0-9_]+"'), (1861, 46, 49, 'int', '400'), (1861, 66, 69, 'int', '500')),
}


# PR #1813 reviewed migration-evidence helper, carried through PR #1329's
# qualified provenance accessors. The config-namespace function stays exact.
# This exact token is the Root config-directory permission mode, not a UID.
# Source, path, AST location and complete token must all match; scanner unchanged.
REVIEWED_FILES['ops/executive_os/schema_upgrade_evidence.py'] = {
    "sha256": '141f4cbb77d3c3eed130025289b1f2cd06805f67cd4a10d7c2462f2d4d49e122',
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
# 2026-11-09 MMOS composition pin move: commit a751d78cc (PR #2316 WO-05
# admitted child class projection) inserts 106 lines above the three pinned
# comparisons. The three reviewed identity operands are byte-identical and
# shift to 226/416/511. No new identity site is qualified.
REVIEWED_FILES.update({'control_plane/paid_fabric_backend.py': {'sha256': '27a074b96871beb70900c0590d7dd6d99fb1bd318896596da68232ebdaf37bde',
 'sites': ((226, 73, 76, 'int', '501'), (416, 78, 81, 'int', '450'), (511, 83, 86, 'int', '501'))},
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
 'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py': {'sha256': 'd680789e7a184b7b882a57f6cc7b0337b6bebc4e27069ac8263aeffd456c5fed',
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
 'ops/native_fabric/quota_continuity/candidate/paid_host_qualification.py': {'sha256': '2a52ba79e6cd38a42ecbd48919704d2c837c65d042707b37640df78f27b8d0c0', 'sites': ((34, 17, 20, 'int', '501'), (452, 85, 90, 'int', '0o700'))},
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
# Control component composition retains the four original whole Constant
# tokens and their complete identity-owner AST from protected 49c2e1d.
# The two added 0o644 tokens are the closed root-file mode and the matching
# exact-CAS publication mode, both with explicit uid=0 and gid=0. They are
# permissions, not principals; each complete token and enclosing call was
# inspected on these exact source bytes. No generic numeric rule changes.
# Integrated protected finite-retirement source is inspected with the same
# exact studio UID, group and root-file permission AST token contexts; the
# full postimage and all six source sites must remain an exact match.
# Original-transaction recovery keeps these six literal tokens, their enclosing
# owners and calls unchanged. Root re-reviewed the full recovery diff and these
# exact moved spans; no identity/numeric exception or scanner rule is added.
REVIEWED_FILES['ops/executive_os/autonomy_control.py'] = {'sha256': 'e8c812d6bc11a00a00db0fbb0bf4b60ff354c3b4ff9fcce18e3e11cebe45d0b0',
 'sites': ((349, 24, 27, 'int', '501'),
           (7008, 35, 37, 'int', '80'),
           (7009, 50, 55, 'int', '0o755'),
           (7889, 41, 46, 'int', '0o644'),
           (8689, 64, 69, 'int', '0o644'),
           (10104, 41, 46, 'int', '0o644'))}

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
REVIEWED_FILES['ops/native_fabric/quota_continuity/candidate/paid_initializer.py'] = {'sha256': '602893be1fa1ece43862ba889e92af8d8e879cb67f62f16840300b7f21ad2887',
 'sites': ((72, 35, 40, 'int', '0o777'), (220, 30, 35, 'int', '0o777'), (230, 33, 38, 'int', '0o777'))}

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
# Content identity GET registration reviewed6eb650a8; the existing control_room_action AST is exact.
# 2026-11-09 MMOS composition pin move: commit 3838b8b82 (PR #2351 capacity
# fabric OS read) adds one route constant line above the handler; the eight
# reviewed action-refusal operands are byte-identical and shift by one line.
# 2026-11-09 T3 attempt-fleet read pin move (t3/fleet-attempt-read-route):
# the per-attempt route adds one further route-constant line above the
# handler; the same eight reviewed action-refusal operands are byte-identical
# and shift by one more line.
REVIEWED_FILES['integrations/mastermind_workspace_app/app.py'] = {'sha256': 'f7e4e50df2b8945be5dfdb8e5092f4d68dcfe738c75cf39efaa89a1ffb463e95', 'sites': ((928, 71, 74, 'int', '400'), (939, 71, 74, 'int', '403'), (947, 71, 74, 'int', '400'), (953, 79, 82, 'int', '400'), (962, 71, 74, 'int', '400'), (972, 71, 74, 'int', '403'), (977, 76, 79, 'int', '503'), (983, 71, 74, 'int', '403'))}

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
REVIEWED_FILES['app/mastermind_os/src/knowledge/library/project-data-observation.ts'] = {'sha256': 'f2a1bb24330f5afc85c585b4746acc81b218a9e7cc4e675e9ec856cb0955b281', 'sites': ((96, 97, 100, 'int', '512'),)}
REVIEWED_FILES['app/mastermind_os/src/knowledge/library/project-knowledge-port.ts'] = {'sha256': 'e5e379e7e4c985d36452fc82c8ad94ecaa7146ebf4aacc6ae0cd08aea504b336', 'sites': ((51, 64, 67, 'int', '512'),)}
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
# Selected-child capture changes the enclosing source only; the permission
# handler AST and all four HTTP denial token positions remain unchanged.
# 2026-11-09 MMOS composition pin move: commit 3838b8b82 (PR #2351 capacity
# fabric OS read) adds the trusted capacity_fabric_source constructor guard
# four lines above the handler; the four reviewed 403 operands are
# byte-identical and shift by four lines.
# 2026-11-09 T3 attempt-fleet read pin move (t3/fleet-attempt-read-route):
# the trusted t3_attempt_fleet_source constructor guard adds four further
# lines above the handler; the same four reviewed denial operands are
# byte-identical and shift by four more lines.
REVIEWED_FILES['control_plane/workspace_read_service.py'] = {'sha256': '4666348f25299d01df1d57dd1d06d5e656f1dcf9f469e76480cbc69dbb34d2f1', 'sites': ((723, 93, 96, 'int', '403'), (725, 56, 59, 'int', '403'), (732, 46, 49, 'int', '403'), (733, 56, 59, 'int', '403'))}
# S14 reviewed private-directory comparison (Root + independent89cb). This
# single permission check grants no identity or chmod capability. Any path,
# token-coordinate or complete-postimage drift restores ordinary D8 scrutiny.
REVIEWED_FILES['ops/native_fabric/quota_continuity/candidate/post_failure_observation.py'] = {'sha256': '80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337', 'sites': ((294, 79, 84, 'int', '0o700'),)}


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

# Validated source path bounds; no identity/authority. Exact postimage and sites only.
# 2026-11-06 attended source audit: accepted-creation navigation preserves both
# complete bounded-path lines; the optional callback shifts them by three lines.
# The full-source hash and both spans still reject all path/context/byte drift.
# This source audit supplies no native runtime or release approval.
# Accepted S24 composition (4aabd797 custody /578ec12e persistence review):
# only the same two512 path-length bounds move eight lines; no identity or limit change.
REVIEWED_FILES['app/mastermind_os/src/projects/ProjectPlanningJourney.tsx'] = {'sha256': '1bfbec76a4f007d5ab5570eb5080891c896714129d4f0c51d7cfaf56a260b419', 'sites': ((371, 26, 29, 'int', '512'), (487, 57, 60, 'int', '512'))}

# fixed HTTP not-found status. Exact full postimage and literal sites only.
REVIEWED_FILES['integrations/mastermind_executive_app/fresh_conversation_transport.py'] = {'sha256': 'b5fd60efebebc04ea12d1d1976663c74f907dec2f151a2d71a6f442182b5e5b2', 'sites': ((93, 39, 42, 'int', '404'),)}

# fixed HTTP unavailable status. Exact full postimage and literal sites only.
# 2026-11-06 source audit: the fixed planning/execution pair shares the original
# authenticated carrier; these are still only its two HTTP unavailable operands.
REVIEWED_FILES['integrations/mastermind_executive_app/project_planning_transport.py'] = {'sha256': 'e2bf5510be0196546d95530840827727721912a94a0b2368cc8c5a70bfb61442', 'sites': ((55, 45, 48, 'int', '503'), (81, 81, 84, 'int', '503'))}

# Actual source-issued proposal PR number, never a UID or HTTP/permission grant.
REVIEWED_FILES['app/mastermind_os/src/fixtures/knowledge-memory-source.json'] = {'sha256': 'ee715ecbf81efef147491f1cbbea041ba1a62688bd0906b715231156bdacc0e9', 'sites': (), 'utf8_sites': ((1, 36976, 36979, 'int', '403'),)}

# 2026-11-09 MMOS composition (commit 3838b8b82, PR #2351): the two 900-second
# freshness bounds of the Capacity Fabric projection are elapsed-time limits in
# the alias-tainted account/owner context, never UIDs/GIDs or peers — the same
# qualification as the incumbent quota_continuity 900 elapsed-time sites above.
# Exact whole-file hash and whole-token spans only; any drift restores the
# ordinary D8 guard. This pin is a source-drift qualification, not independent
# review or release authority.
REVIEWED_FILES['control_plane/workspace_capacity_fabric.py'] = {'sha256': 'f48347aa98d894368e7e175263427c55f79c066cb3c7dfd7f32ea4253db53892', 'sites': ((234, 66, 69, 'int', '900'), (277, 106, 109, 'int', '900'))}

# 2026-11-09 MMOS composition (commit 3838b8b82, PR #2351): the 900px breakpoint
# of the Capacity Fabric responsive layout is a CSS viewport width in the
# alias-tainted accounts-selector line, never an identity. Exact whole-file
# hash and whole-token span only; any drift restores the ordinary D8 guard.
REVIEWED_FILES['app/mastermind_os/src/resources/capacity-fabric.css'] = {'sha256': 'e75e39ac6eba0344f4a3133d3c875976d342b7db9b69e6010c6d29f0ffc8f1bf', 'sites': ((49, 19, 22, 'int', '900'),)}

# Actual local Programs observation negative-test HTTP statuses, no OS identity.
# 2026-11-07 attended source check: native Hermes composition and exact pending
# auth-timer expiry move these unchanged three operands. Preserve whole-file and
# exact-token qualification; this supplies no runtime or formal release approval.
# Discovery correction plus Company priorities changes only the containing source
# and line positions; these same three fixture HTTP statuses are not principals.
# Content-continuation reviewed6eb650a8 preserves the complete enclosing fixture
# function. Primary/work-entry composition preserves these three complete fixture
# calls. 2026-11-09 MMOS merge pin move: master #2344 primary/work-entry source
# and PR #2351 capacity-fabric OS read (commit 3838b8b82) both insert lines above
# the fixture; the three reviewed 503 operands are byte-identical at their merged
# positions (3812/3817/3821). Only exact existing tokens qualify.
REVIEWED_FILES['app/mastermind_os/src-tauri/src/auth.rs'] = {'sha256': '612e97c934d4407c3b08bdf3c15bf75e8df5a1507d4161435b862896acff4737', 'sites': ((3812, 68, 71, 'int', '503'), (3817, 69, 72, 'int', '503'), (3821, 67, 70, 'int', '503'))}
REVIEWED_FILES['app/mastermind_os/src/fixtures/discovery-correction-owner.json'] = {
    # Inert PR number from the actual temporary-Git test owner, not a UID.
    'sha256': '363eb680b3a7f982e4fedb8496598b7127ed719c2d1c802831e330bc74ab803f',
    'sites': ((163, 18, 21, 'int', '401'),),
}

# Reviewed Session Unicode-scalar input bound, never an OS identity.
REVIEWED_FILES['app/mastermind_os/src-tauri/src/native_session_send.rs'] = {'sha256': 'e290af30b07536060bbeaa26e1c4dab59dd6d10becedfe40ce33f9cc6fac4d2c', 'sites': ((13, 118, 121, 'int', '700'),)}

# BYOK metadata READ re-pin: same eight action literals and unchanged action AST.
# Attended parent source check under the current Chairman waiver; no formal approval claim.

# Prospective evaluation candidate: exact fixed UID/private-mode checks and HTTP
# status constants; no new principal, mode grant or scanner exemption. Inherited
# c2 protected primitives retain their accepted scoped review; changed issuer
# code and these exact postimages require the one consequence review.
REVIEWED_FILES.update({'control_plane/protected_memory_economic_owner.py': {'sha256': '988c7407b08bc005ad608092ffdd90e46a04bc5f3a8254682154f27a63e82130',
                                                      'sites': [[61, 33, 36, 'int', '501'],
                                                                [141, 25, 28, 'int', '450']]},
 'control_plane/protected_memory_evaluation_assignment.py': {'sha256': '58050d8abbcd7dbbc73e00f2374aac39eab00a3852a79cdc51b5025e3e978557',
                                                             'sites': [[442, 82, 85, 'int', '450'],
                                                                       [443, 34, 37, 'int', '450'],
                                                                       [462, 82, 85, 'int', '450'],
                                                                       [462, 108, 111, 'int', '450']]},
 'control_plane/protected_memory_evaluation_execution.py': {'sha256': '45c977d0b73c8fc6632c6775934e0131413504e3b381e70b1f62f1406ceb408e',
                                                            'sites': [[118, 35, 38, 'int', '450'],
                                                                      [118, 61, 64, 'int', '450']]},
 'control_plane/protected_memory_evaluation_source.py': {'sha256': '2194b98269bd10e7f8e3dfac655db1ffe9a7d45af6b67b059904c09193c26aee',
                                                         'sites': [[56, 55, 58, 'int', '450'],
                                                                   [59, 99, 102, 'int', '450'],
                                                                   [96, 81, 84, 'int', '450']]},
 'control_plane/protected_memory_execution.py': {'sha256': '90dee86e669f6606a68da3640aa2964dde75d98fb1d2bd46481cda92ca7c15bf',
                                                 'sites': [[70, 68, 71, 'int', '450'],
                                                           [73, 20, 23, 'int', '450'],
                                                           [73, 55, 60, 'int', '0o700'],
                                                           [248, 36, 39, 'int', '450']]},
 'control_plane/protected_memory_peer.py': {'sha256': '921228bd2ee266da35ace6c4ed445c61475542764d4e2a90456a2e322201e9ca',
                                            'sites': [[46, 20, 23, 'int', '450'],
                                                      [120, 23, 26, 'int', '450']]},
 'control_plane/protected_memory_profile.py': {'sha256': '0c695423e3fa30be313a65727d40de09d5bb37f1a9a4be79aa014744fbcdf24f',
                                               'sites': [[28, 46, 49, 'int', '450'],
                                                         [61, 81, 84, 'int', '450'],
                                                         [79, 81, 84, 'int', '450'],
                                                         [114, 93, 96, 'int', '443'],
                                                         [121, 23, 26, 'int', '450']]},
 'integrations/mastermind_executive_app/coo.py': {'sha256': '0be32b8bdd843c4667d153254c4369ed6921eb9323bea43baf1b77d18be8fd7b',
                                                  'sites': [[198, 75, 78, 'int', '400'],
                                                            [208, 93, 96, 'int', '503'],
                                                            [324, 37, 40, 'int', '400'],
                                                            [334, 54, 57, 'int', '503'],
                                                            [349, 54, 57, 'int', '503'],
                                                            [359, 56, 59, 'int', '503']]},
 'scripts/protected_memory_economic_helper.py': {'sha256': 'b8c2c01b07c1f8dff7d6352fade6142258ef3a8ecc1ec0775869cd21e6aef4c8',
                                                 'sites': [[18, 21, 24, 'int', '501'],
                                                           [40, 58, 61, 'int', '501']]},
 'scripts/protected_memory_model_runner.py': {'sha256': '4a90ff3c92b5cfe6e2c2a73aac3eaeb556e12627924b23f3ae94a5d00eb5a57a',
                                              'sites': [[32, 43, 46, 'int', '450'],
                                                        [76, 21, 24, 'int', '450'],
                                                        [82, 48, 51, 'int', '450']]}})

# C16: fixed observation-only TLS directory; root owner and canonical Control
# group retain the exact private traversal mode. Whole-source and token-bound.
# C21 attended-parent source review combines native composition with the
# accepted archive closure and inert gateway replacement. ensure_directories
# retains its exact AST and whole permission token at the accepted moved site.
REVIEWED_FILES['scripts/enroll_linux_secondary_worker.py'] = {'sha256': '925aa0d0aa6174d29653f189ffcf47c9550a53aaf303387cf6c0e77b3ac7c1a6',
                                                              'sites': ((708, 71, 76, 'int', '0o750'),)}

# Fixed receipt/native-response byte bound in MAX_WIRE_BYTES, not an OS identity.
# One exact multiplication operand; full-source drift restores the ordinary guard.
REVIEWED_FILES["integrations/hermes_runtime/native_session_control.py"] = {
    "sha256": "716b934f77cdc377b769c6cf1cefcfbb199be3e71d885f4624c6e6dc0d93b9c9",
    "sites": ((23, 17, 20, "int", "512"),),
}

# Native EVAL marker v2 retains the original directory permission mode.
# Exact historical root_identity["mode"] comparison, not a selected UID/GID.
# Whole-source drift and any neighboring identity literal restore ordinary D8.
REVIEWED_FILES["integrations/hermes_runtime/native_eval_inputs.py"] = {
    "sha256": "0739341fda7b0faa6d45cbe61a35587055e9da0fc1ccd5b5792e7cfaa95a1ae2",
    "sites": ((96, 61, 66, "int", "0o700"),),
}

# HTTPX 0.28.1 donor same-host HTTPS upgrade: standard HTTPS port only. No principal,
# UID/GID or fleet selection. Full archive/site drift restores ordinary D8.
REVIEWED_FILES["integrations/hermes_runtime/tests/fixtures/transport_observation/httpx___client.py.source"] = {
    "sha256": "c43f941baefe58c91e96d00039e1868fe719d91453026d7db1647194563bff8d",
    "sites": ((73, 42, 45, "int", "443"),),
}

# Fixed Secretary wire-response byte ceiling, not an OS identity. The complete
# NUMBER token is the left operand of MAX_SECRETARY_RESPONSE_BYTES = 512 * 1024.
REVIEWED_FILES["control_plane/remote_worker_transport.py"] = {
    "sha256": "c0d8d30ec2789d56c609c5f245b530c5765a2bb774f647cb7bd8cc2a86b05c31",
    "sites": ((34, 31, 34, "int", "512"),),
}

# C46 native-control composition changes the enclosing source. The byte-ceiling
# declaration, both consumers and the single reviewed operand remain exact.

# The installer exclusively creates the gateway audit parent with this private
# initial mode, under its held trusted root, before qualified final0755 mode.
# Only this new token is reviewed; existing source identities remain visible.
# The authenticated release-record verifier moved this unchanged mode site three lines.
# Whole-file and exact-token drift rejection, including all prior unmasked findings, stays intact.
REVIEWED_FILES['ops/executive_os/install.sh'] = {'sha256': '7c1b7147bf5236c68c043f20ad1bda37872c9fe13050a70374a44e433783324b', 'sites': ((1727, 26, 31, 'int', '0o700'),)}


# Fixed MCP audit leaf ownership and modes in the existing gateway transaction.
REVIEWED_FILES['ops/executive_os/mcp_auth_audit_directories.py'] = {'sha256': 'e40d488bd0c18f6cc422aeb15ce853cba330a8d5c9559cc7a7612b1ce119a3ed', 'sites': ((22, 12, 15, 'int', '458'), (23, 7, 12, 'int', '0o700'), (125, 49, 54, 'int', '0o755'), (128, 60, 65, 'int', '0o755'))}

# Hermes native Fabric: two bounded escalation-reason length limits, not
# principals, account selections, permissions or process identities. Only the
# exact reviewed source postimage and these complete typed numeric AST tokens
# are exempt; any source drift exposes both to the ordinary D8 scanner again.
# This does not confer trusted session grants or Fabric execution authority.
# Pin-move history converged at this merge (origin/master into
# feat/mmos-v1-integration-t3, 2026-11-10). Master #2365 (commit 6696153d3,
# accepted manual-pool enumeration xai, anthropic-oauth, openai-codex) moved
# the same two reason-length tokens by nine lines (48->57, 271->280) with
# unchanged enclosing validation expressions. The trunk moved this pin in its
# 2026-11-09 merge (MERGE_MASTER_20261109); master independently re-pinned in
# #2377/#2386. Both sides carried byte-identical pin value and sites here;
# recomputed against the merged source at this merge — no side was picked.
REVIEWED_FILES["integrations/hermes_attended_fabric/native.py"] = {
    "sha256": "7b6d14ea2e041f98573627925340f00c4b6e6c3cfde5a16e297aa3a52079a0bf",
    "sites": ((57, 65, 68, "int", "500"), (280, 60, 63, "int", "500")),
}

# Hermes primary APPLICATION codec: fixed input-byte and conversation-count
# bounds, never OS accounts, principals, permissions or service selection.
# Attended source self-review under the CEO-Web waiver. Full source hash and
# complete typed tokens remain required; any drift restores the ordinary guard.
REVIEWED_FILES["integrations/hermes_application_fabric/codec.py"] = {
    "sha256": "62005182643a5e6312ca6c2169898839ebc15e49a1aefe6ddaf0f39f75f5de27",
    "sites": ((15, 20, 23, "int", "512"), (141, 63, 66, "int", "512")),
}


# Native Agent OS v2 adds private readback and projects an optional real child.
# Existing enrollment/admission functions and MAX_WIRE_BYTES AST are unchanged;
# the same sole 512 operand remains at (23, 17, 20), with no new identity mask.

# Test-owned frozen source data, merged into this same finite review table.
from tests.test_hermes_workspace_oauth_identity_review import (
    REVIEWED_FILES as HERMES_WORKSPACE_OAUTH_REVIEWED_FILES,
)
REVIEWED_FILES.update(HERMES_WORKSPACE_OAUTH_REVIEWED_FILES)

# Original #852 held subscription principals, source-qualified at exact sites.
# This fixed source evidence grants no installed identity, credential or capacity.
REVIEWED_FILES['ops/executive_os/provider_worker_slots.py'] = {'sha256': '5e22af39347f1a6e762b7716b73506beca5460b05914e9e2d9f1a19d9b7fb42e',
 'sites': ((168, 20, 44, 'str', '"_mastermind_alibaba_01"'),
           (169, 21, 45, 'str', '"_mastermind_alibaba_01"'),
           (170, 19, 22, 'int', '459'),
           (171, 19, 22, 'int', '459'),
           (180, 20, 44, 'str', '"_mastermind_minimax_01"'),
           (181, 21, 45, 'str', '"_mastermind_minimax_01"'),
           (182, 19, 22, 'int', '460'),
           (183, 19, 22, 'int', '460'),
           (288, 12, 36, 'str', '"_mastermind_alibaba_01"'),
           (296, 12, 36, 'str', '"_mastermind_minimax_01"'))}

# Material protected320 context composition: only line locations/file digest
# move for the same six accepted Memory HTTP-status operands; no new mask.
REVIEWED_FILES['integrations/mastermind_executive_app/coo.py'] = {'sha256': '5522cf9369fc4c04e585bd24a32e22fc4690c82f4048c65ed52dbe2467a4ae99',
 'sites': [(245, 75, 78, 'int', '400'),
           (255, 93, 96, 'int', '503'),
           (636, 37, 40, 'int', '400'),
           (657, 54, 57, 'int', '503'),
           (677, 54, 57, 'int', '503'),
           (687, 56, 59, 'int', '503')]}

# Exact synthetic APPLICATION HTTP refusal assertion; not an OS identity.
# Full-source or token-site drift restores the ordinary identity guard.
REVIEWED_FILES[
    "integrations/hermes_application_fabric/qualification/qualify_application_owner.py"
] = {'sha256': '192ff0bf4321f0006cb34ba68dd4d648da3a3825dccc8cd731f220f61e793f32', 'sites': ((367, 37, 40, 'int', '409'),)}

# Original H4 f008 receipts record the existing Darwin host's ownership.
# These are observed identities, not runtime defaults, service enrollment or
# authorization. Preserve the receipts byte-for-byte. Only these fifteen
# typed integer tokens in the two exact files are reviewed; any byte or path
# drift restores the original identity guard for the complete receipt.
REVIEWED_FILES["review_evidence/hermes_h4/profile-mapping-20261107.json"] = {
    "sha256": "6df7896d56bc9b2098914fb945e314369d360f9f87f7d2f5d1d414f796aded53",
    "sites": (),
    "utf8_sites": (
        (20, 20, 23, "int", "501"),
        (47, 20, 23, "int", "501"),
        (70, 20, 23, "int", "501"),
    ),
}
REVIEWED_FILES["review_evidence/hermes_h4/native-preimage-qualification-20261107.json"] = {
    "sha256": "eaa5796f0000713bc83e6fac6962a40b7c367cf311022bf81452334ed83bfdee",
    "sites": (),
    "utf8_sites": (
        (29, 18, 21, "int", "501"),
        (42, 18, 21, "int", "501"),
        (55, 18, 21, "int", "501"),
        (68, 18, 21, "int", "501"),
        (85, 18, 21, "int", "501"),
        (98, 18, 21, "int", "501"),
        (111, 18, 21, "int", "501"),
        (128, 18, 21, "int", "501"),
        (141, 18, 21, "int", "501"),
        (154, 18, 21, "int", "501"),
        (167, 18, 21, "int", "501"),
        (180, 18, 21, "int", "501"),
    ),
}

# Exact HTTPS port excluded by the disposable Chisel fixture.
# This is not a general port exemption or permission to use a live listener.
REVIEWED_FILES[
    "integrations/hermes_application_fabric/qualification/qualify_chisel_protocol.py"
] = {
    "sha256": "66af1f5e2569d6f54d7313787e613cf933a301a36d12ebc2a34b48319a38961f",
    "sites": ((27, 26, 29, "int", "443"),),
}
# H5 + protected Hermes/auth-timer composition retains all three exact Programs
# observation status lines; whole-source hash and absolute line positions repinned.


# H6 retained qualification receipts: exact immutable output tokens only.
# These sites are traceback coordinates, temporary path identifiers, HTTP
# results or negative-test names. They neither create identities nor qualify
# runtime authority. Full-file or token drift restores the unchanged guard.
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/ci-paired-archive.log'] = {'sha256': '80853727ac6201e58ee123d4ab0a31c55b8ede993d0239935bba56c48812f101',
 'sites': ((17, 95, 98, 'int', '469'),
           (18, 89, 92, 'int', '469'),
           (21, 95, 98, 'int', '423'),
           (22, 89, 92, 'int', '423'),
           (116, 275, 278, 'int', '678'),
           (306, 180, 183, 'int', '452'),
           (311, 180, 183, 'int', '452'),
           (316, 180, 183, 'int', '452'),
           (321, 180, 183, 'int', '452'),
           (326, 180, 183, 'int', '452'),
           (331, 180, 183, 'int', '452'),
           (336, 180, 183, 'int', '452'),
           (341, 180, 183, 'int', '452'),
           (346, 180, 183, 'int', '452'),
           (351, 180, 183, 'int', '452'),
           (356, 180, 183, 'int', '452'),
           (361, 180, 183, 'int', '452'),
           (366, 180, 183, 'int', '452'),
           (371, 180, 183, 'int', '452'),
           (376, 180, 183, 'int', '452'),
           (381, 180, 183, 'int', '452'),
           (386, 180, 183, 'int', '452'),
           (391, 180, 183, 'int', '452'),
           (396, 180, 183, 'int', '452'),
           (401, 180, 183, 'int', '452'),
           (406, 180, 183, 'int', '452'),
           (411, 180, 183, 'int', '452'),
           (416, 180, 183, 'int', '452'),
           (421, 180, 183, 'int', '452'),
           (426, 180, 183, 'int', '452'),
           (431, 175, 178, 'int', '529'),
           (436, 175, 178, 'int', '529'),
           (441, 175, 178, 'int', '529'),
           (446, 175, 178, 'int', '529'),
           (451, 175, 178, 'int', '529'))}
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/ci-paired-archive.xml'] = {'sha256': '971791af5f8194d98c104e5590f525e4aa936fa3d57ec8862a4a0bb0bef500d2',
 'sites': ((1, 8804, 8807, 'int', '813'),)}
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/ci-release-preflight.xml'] = {'sha256': 'cae40e77100dfaa74987558327261726962b054cdd8e4a5309cd992a741ff9b1',
 'sites': ((1, 18691, 18694, 'int', '962'), (1, 55399, 55402, 'int', '971'))}
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/current-native-composition.xml'] = {'sha256': '0db10663c221bb632710946751d17df374503b10bb262837f0257e4482f8a0ed',
 'sites': ((1, 103703, 103722, 'str', '_mastermind_account'),
           (1, 103731, 103750, 'str', '_mastermind_account'),
           (1, 104037, 104056, 'str', '_mastermind_account'),
           (1, 104065, 104084, 'str', '_mastermind_account'),
           (1, 104362, 104381, 'str', '_mastermind_account'),
           (1, 104390, 104409, 'str', '_mastermind_account'))}
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/h5-composed-baseline.xml'] = {'sha256': '974a1c7266c19a10ce2be0cc7f56d2aef33c07d1af58ee2471f1f7465c2caa29',
 'sites': ((10, 14, 17, 'int', '403'),
           (10, 34, 37, 'int', '403'),
           (10, 6505, 6521, 'str', '_mastermind_exec'),
           (10, 6702, 6722, 'str', '_mastermind_intruder'),
           (10, 53546, 53565, 'str', '_mastermind_account'),
           (10, 53574, 53593, 'str', '_mastermind_account'),
           (10, 53880, 53899, 'str', '_mastermind_account'),
           (10, 53908, 53927, 'str', '_mastermind_account'),
           (10, 54205, 54224, 'str', '_mastermind_account'),
           (10, 54233, 54252, 'str', '_mastermind_account'),
           (10, 59285, 59307, 'str', '_mastermind_unreviewed'),
           (10, 59546, 59568, 'str', '_mastermind_unreviewed'),
           (10, 64592, 64614, 'str', '_mastermind_unreviewed'),
           (10, 64623, 64645, 'str', '_mastermind_unreviewed'))}
REVIEWED_FILES['review_evidence/fabric_application/h6-recovery-20261107-c2/native-loader-baseline.log'] = {'sha256': '3e21b01c58fdc2a90ad265a0cea6309ec87ac41ffe050200a07baef4a9ac3f93',
 'sites': ((9, 102, 105, 'int', '677'),)}

# Existing disposable shared-relay proof parent; immutable receipt, no runtime grant.
REVIEWED_FILES['review_evidence/fabric_application/shared-relay-source-qualification-20261107.json'] = {
    "sha256": '3629a7a963e9621aa1b190c1b946c6a3d8a1277caaa3ffac6dd129a4c984b5b3',
    "sites": ((296, 26, 29, "int", "501"),),
}

# Retained source qualification records the observed proof parent UID only.
# It grants no runtime identity or enrollment. Exact bytes and the sole complete
# UTF-8 integer token are required; drift restores the ordinary identity guard.
REVIEWED_FILES["review_evidence/fabric_application/shared-relay-source-qualification-20261107.json"] = {
    "sha256": "3629a7a963e9621aa1b190c1b946c6a3d8a1277caaa3ffac6dd129a4c984b5b3",
    "sites": (),
    "utf8_sites": ((296, 26, 29, "int", "501"),),
}

# The sealed verifier ModuleType label is a Python module identity, never an OS
# account, principal or service. This exact source/string site alone is reviewed;
# any full-source or token drift restores the ordinary identity guard.
REVIEWED_FILES["integrations/hermes_application_fabric/source_context.py"] = {'sha256': '887799a569cc04d5e0327e2c2732ee389064929e241c060328dcbecedcab3597', 'sites': ((425, 36, 73, 'str', '"_mastermind_attended_native_sources"'), (444, 42, 78, 'str', '"_mastermind_attended_configuration"'))}

# Exact retained readiness qualification records the observed proof parent UID.
# This grants no runtime identity. Any source, path or token drift exposes it
# to the incumbent guard again; the original receipt is preserved unchanged.
REVIEWED_FILES['review_evidence/fabric_application/protected-hermes-readiness-join-20261107.json'] = {
    "sha256": 'ca3bfdc6cd8a670f1eb54a578bd795a19060ee05b299fa37c30b6fe479838d33',
    "sites": (),
    "utf8_sites": ((61, 13, 16, "int", "501"),),
}

# Installed-consumer qualification maps disposable Control metadata to the
# incumbent Control UID. These two exact fixture operands register no account,
# grant or service; source/token drift restores the ordinary identity guard.
REVIEWED_FILES["integrations/hermes_application_fabric/qualification/qualify_attended_configuration.py"] = {
    "sha256": "96dbbd9572b9323e2f1da20882b2170b21932e119d4768925ca030d50399bf92",
    "sites": ((105, 39, 42, "int", "450"), (132, 27, 30, "int", "450")),
}

# Exact observed native preimage metadata records the proof-host UID only.
# These immutable evidence tokens create no account, runtime default or grant.
# Full-source or token drift restores the ordinary guard.
REVIEWED_FILES['review_evidence/hermes_primary/attended-native-preimages-20-files-20261107.json'] = {
    "sha256": '7b5af848fa6bdc47b178b73fc027a46c34f897e2a9bade655b9dec09af6d1a12',
    "sites": (),
    "utf8_sites": ((39, 18, 21, 'int', '501'), (52, 18, 21, 'int', '501'), (65, 18, 21, 'int', '501'), (78, 18, 21, 'int', '501'), (91, 18, 21, 'int', '501'), (104, 18, 21, 'int', '501'), (121, 18, 21, 'int', '501'), (134, 18, 21, 'int', '501'), (147, 18, 21, 'int', '501'), (160, 18, 21, 'int', '501'), (173, 18, 21, 'int', '501'), (186, 18, 21, 'int', '501'), (199, 18, 21, 'int', '501'), (212, 18, 21, 'int', '501'), (229, 18, 21, 'int', '501'), (242, 18, 21, 'int', '501'), (263, 18, 21, 'int', '501'), (276, 18, 21, 'int', '501'), (289, 18, 21, 'int', '501'), (302, 18, 21, 'int', '501'), (319, 18, 21, 'int', '501')),
}
REVIEWED_FILES["integrations/session_bridge/installed_web_observation.py"] = {
    "sha256": "e7b3c60725b1be5574d39525aefc076aab2c06a8a3fa0fb7b78ecbb905579a22",
    "sites": ((252, 46, 49, "int", "512"),),
}

# Select-option value length bound, not a UID/GID or account identity. Only this
# complete protocol source and typed literal are reviewed; any byte drift restores
# ordinary D8 scrutiny. This grants no browser permission or runtime authority.
REVIEWED_FILES["integrations/chairman_surfaces/web_sol_browser_protocol.py"] = {
    "sha256": "050d0dd2fd682ddc4f39b2e2b6a55b50794bb306c91992ba3c5ffb2a2d86694b",
    "sites": ((128, 72, 75, "int", "512"),),
}

# Content-continuation source union independently qualified at282140ec5,
# original treee9b3984c (review6eb650a8), then primary-purpose and mode fixtures.
# Root re-reviewed the final composition. Only two synthetic600-second
# token lifetimes and six fixed HTTP400/403 response tokens are qualified.
# No principal/UID/callee or arbitrary nearby literal is exempted; changed
# bytes invalidate the whole pin, preserving the generic topology guard.
REVIEWED_FILES['app/mastermind_os/src-tauri/src/auth/authorization_continuation.rs'] = {'sha256': '71b76671de68819ac6ed92a4d705800aed84b9d51cf46f3858f6f974788cb2cb', 'sites': ((542, 58, 61, 'int', '600'), (543, 66, 69, 'int', '600'))}
REVIEWED_FILES['integrations/mastermind_workspace_app/native_authorization_identity.py'] = {'sha256': 'db7f7f1e82de28d99d23f1391d542599180e5ac0daf7b7e689432c73b0c13102', 'sites': ((72, 25, 28, 'int', '400'), (94, 29, 32, 'int', '400'), (100, 25, 28, 'int', '403'), (108, 29, 32, 'int', '400'), (113, 33, 36, 'int', '400'), (119, 29, 32, 'int', '403'))}
# Fixed explicit Memory owner source: closed Control helper dependency paths;
# same private mkdir, turn/CPU/reference/HTTP bounds, incumbent TTL and full
# APPLICATION recipe limits. Source/path/token identity remains exact. The
# Broker/task postimages are the full current-native preserving transplants.
# No identity scanner, runtime grant, timeout or budget rule changes.
REVIEWED_FILES.update({'control_plane/protected_memory_economic_owner.py': {'sha256': '431a4a36f12ebaff25ee681aaf45635a0a6820b7b117bae18aa6b52393e19221',
                                                      'sites': [(74,
                                                                 33,
                                                                 36,
                                                                 'int',
                                                                 '501'),
                                                                (154,
                                                                 25,
                                                                 28,
                                                                 'int',
                                                                 '450')]},
 'ops/native_fabric/provider_plans/memory118/native_owner/artifact_delivery.py': {'sha256': 'ad985dfc615ef2a8788939dcf42e008b1504126a3a23e23e46f82d6c391ad38a',
                                                                                  'sites': ((1397,
                                                                                             28,
                                                                                             33,
                                                                                             'int',
                                                                                             '0o700'),)},
 'ops/native_fabric/provider_plans/memory118/native_owner/fabric_task.py': {'sha256': 'c0f12526bb13cbef6be6b766232e31dc520fffc38e1353923ae97e8ff5c521d1',
                                                                            'sites': ((1031,
                                                                                       51,
                                                                                       54,
                                                                                       'int',
                                                                                       '400'),
                                                                                      (1316,
                                                                                       59,
                                                                                       62,
                                                                                       'int',
                                                                                       '400'),
                                                                                      (1869,
                                                                                       79,
                                                                                       82,
                                                                                       'int',
                                                                                       '400'))},
 'ops/native_fabric/provider_plans/memory118/native_owner/lease_broker.py': {'sha256': '7a713554c24b2fe47186db1332a023d952bdbeb8a83e972976c19dc5bc9769bd',
                                                                             'sites': ((106,
                                                                                        80,
                                                                                        83,
                                                                                        'int',
                                                                                        '512'),
                                                                                       (275,
                                                                                        67,
                                                                                        70,
                                                                                        'int',
                                                                                        '900'),
                                                                                       (475,
                                                                                        87,
                                                                                        90,
                                                                                        'int',
                                                                                        '599'),
                                                                                       (755,
                                                                                        52,
                                                                                        55,
                                                                                        'int',
                                                                                        '900'),
                                                                                       (768,
                                                                                        45,
                                                                                        48,
                                                                                        'int',
                                                                                        '512'))},
 'ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py': {'sha256': 'c4082b778c8829e7e472599c9fbdb4cc0dfba400e6d7afff980bbe89669e4c70',
                                                                                          'sites': ((40,
                                                                                                     21,
                                                                                                     24,
                                                                                                     'int',
                                                                                                     '501'),
                                                                                                    (212,
                                                                                                     78,
                                                                                                     81,
                                                                                                     'int',
                                                                                                     '660'))},
 'ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py': {'sha256': 'eda0fa2df123f94325b4f10b5ac6b92182521f3898ed54a5afacb05047721e3b',
                                                                                 'sites': ((202,
                                                                                            51,
                                                                                            54,
                                                                                            'int',
                                                                                            '599'),
                                                                                           (204,
                                                                                            43,
                                                                                            46,
                                                                                            'int',
                                                                                            '429'))},
 'scripts/protected_memory_economic_helper.py': {'sha256': 'cb49f73b511ca8905b35b4486572ee8304cac21e01b97e3add375298bb312b19',
                                                 'sites': [(18,
                                                            21,
                                                            24,
                                                            'int',
                                                            '501'),
                                                           (40,
                                                            58,
                                                            61,
                                                            'int',
                                                            '501')]}})
# Exact accepted Memory native-owner namespace; same reviewed bytes/sites as
# accepted dc79/55e/b87, no generic path or literal exception.
REVIEWED_FILES['ops/native_fabric/provider_plans/memory118/native_owner/artifact_delivery.py'] = {'sha256': 'ad985dfc615ef2a8788939dcf42e008b1504126a3a23e23e46f82d6c391ad38a', 'sites': ((1397, 28, 33, 'int', '0o700'),)}
REVIEWED_FILES['ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py'] = {'sha256': 'c4082b778c8829e7e472599c9fbdb4cc0dfba400e6d7afff980bbe89669e4c70', 'sites': ((40, 21, 24, 'int', '501'), (212, 78, 81, 'int', '660'))}
REVIEWED_FILES['ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py'] = {'sha256': 'eda0fa2df123f94325b4f10b5ac6b92182521f3898ed54a5afacb05047721e3b', 'sites': ((202, 51, 54, 'int', '599'), (204, 43, 46, 'int', '429'))}

# Exact reviewed helper-buffer bounds (512 KiB), no identity/permission grant.
# Complete source hash plus typed spans; any byte drift restores the guard.
REVIEWED_FILES['ops/native_fabric/support_policy_status/reader.py'] = {'sha256': '463bca4c06fc8cbb07f2e87fce8efac0a4ff2ca1c47db08e32f3b7f17c1b0058', 'sites': ((385, 66, 69, 'int', '512'), (404, 54, 57, 'int', '512'))}

# Passive Paperclip asset document pagination: exact row-count bounds only.
# No identity, permission or runtime topology change; any source drift restores D8.
REVIEWED_FILES["ops/paperclip_fleet/archive_assets.py"] = {'sha256': 'f96b00c2c238139c67f7be03f79d698c3f0d4f3d7f055e1a20661600c07b57af', 'sites': ((459, 53, 56, 'int', '500'), (460, 182, 185, 'int', '500'), (461, 48, 51, 'int', '500'))}
