"""Frozen reviewed literals for the Fabric release, never runtime authority.

Exact source hashes and token spans only. Each site is a permission, an input
bound or a reviewed primary/secondary identity exclusion. Shell and retained
.py.base are scanned as source too. Any byte drift exposes every site again;
these pins are not learned or refreshed by the tests.
"""

REVIEWED_FILES = {'integrations/session_bridge/bound_launch_capture/runtime/lane_runtime.py': {'sha256': 'cfb18bd9381fae4af1d13a257a8fa5986d903571f64b2aa5dc900439759e9b91',
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
 'ops/executive_os/acceptance.py': {'sha256': '54cbcfa7379efec31ec909256603ef04e9658b0d9cfb2b584470b4e6bcf8de35',
                                    'sites': ((842, 59, 62, 'int', '454'),
                                              (842, 64, 67, 'int', '455'),
                                              (842, 69, 72, 'int', '456'),
                                              (843, 23, 26, 'int', '450'),
                                              (843, 45, 48, 'int', '450'),
                                              (844, 49, 52, 'int', '400'),
                                              (844, 64, 67, 'int', '500'),
                                              (851, 28, 53, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (859, 39, 64, 'str', 'r"_mastermind_[a-z0-9_]+"'),
                                              (920, 44, 47, 'int', '454'),
                                              (920, 49, 52, 'int', '455'),
                                              (920, 54, 57, 'int', '456'),
                                              (921, 44, 47, 'int', '454'),
                                              (921, 49, 52, 'int', '455'),
                                              (921, 54, 57, 'int', '456'),
                                              (1042, 56, 59, 'int', '400'),
                                              (1042, 85, 88, 'int', '500'),
                                              (1043, 85, 88, 'int', '453'),
                                              (1043, 90, 93, 'int', '454'),
                                              (1043, 95, 98, 'int', '455'),
                                              (1043, 100, 103, 'int', '456'))},
 'ops/executive_os/attended_worker_definition.py': {'sha256': '494c24eebd25dce82568bbb9069ffb1be4ecdc8c038e5d0e6abc7990ef29570b',
                                                    'sites': ((241, 31, 51, 'str', "'_mastermind_worker'"),
                                                              (329, 95, 100, 'int', '0o660'))},
 'ops/executive_os/bootstrap-host.sh': {'sha256': '805279ecceb16965ded44f94ab62aa882090accf45edf8a2e7ab86487bca04ce',
                                        'sites': ((776, 21, 43, 'str', '_mastermind_[a-z0-9_]*'),
                                                  (778, 97, 120, 'str', '_mastermind_agent_relay'),
                                                  (784, 89, 92, 'int', '457'))}}

# Exact finite lifecycle successor postimage. The production delta changes only
# socket ACL observation/currentness; the same 37 reviewed principal/mode literals
# remain fixed. Any other byte or token movement exposes the complete source to D8.
REVIEWED_FILES['ops/executive_os/finite_service_lifecycle.py'] = {'sha256': '115f02b6dbbf1046d7cfd8d7b1b6e8cd528e29887172a89332efb5ab8ce3fc5f',
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
           (413, 105, 108, 'int', '470'),
           (413, 110, 113, 'int', '470'),
           (413, 115, 120, 'int', '0o700'),
           (476, 32, 35, 'int', '470'),
           (487, 57, 75, 'str', "'_mastermind_exec'"),
           (498, 51, 54, 'int', '470'),
           (502, 37, 40, 'int', '470'),
           (502, 59, 62, 'int', '470'),
           (503, 60, 63, 'int', '470'),
           (520, 28, 31, 'int', '470'),
           (568, 66, 69, 'int', '450'),
           (568, 71, 74, 'int', '450'),
           (568, 76, 79, 'int', '450'),
           (568, 81, 84, 'int', '450'),
           (573, 97, 100, 'int', '450'),
           (573, 102, 107, 'int', '0o660'),
           (623, 28, 31, 'int', '450'))}

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


# Exact #1515 Control Room action/HTTP status review at source12c83.
# Independent diagnosis: PR1515 issuecomment6251590011; full source and fixed
# token positions verified before publication. These are HTTP response statuses,
# not account/UID/GID values. Any changed byte/site restores ordinary D8.
REVIEWED_FILES['control_plane/workspace_control_room_actions.py'] = {
    'sha256': 'ff72b9f6d5165cd07bc41052fc322da84e02eef2e3041f58e7569de4f37bfb50',
    'sites': ((135, 58, 61, 'int', '409'),),
}
REVIEWED_FILES['integrations/mastermind_workspace_app/app.py'] = {
    'sha256': '2835c7b2c96b63e38f0d5d3c04e4c8dd69585053ab6bea2a9e98fa49dee591c2',
    'sites': (
        (750, 71, 74, 'int', '400'),
        (761, 71, 74, 'int', '403'),
        (769, 71, 74, 'int', '400'),
        (775, 79, 82, 'int', '400'),
        (784, 71, 74, 'int', '400'),
        (794, 71, 74, 'int', '403'),
        (799, 76, 79, 'int', '503'),
        (805, 71, 74, 'int', '403'),
    ),
}
