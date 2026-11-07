#!/usr/bin/env python3
"""Assemble the explicit reviewed native closure locally; never install it.

This review workspace contains exact installed preimages plus proposed source
overlays. The resulting bytes must be committed/reviewed/merged before release.
No directory scan decides what to transport; this fixed list is the inventory.
"""
import argparse
import hashlib
import json
import io
import zipfile
from pathlib import Path

BASE_FILES = frozenset("""
a04_terminal_reconcile.py artifact_delivery.py artifact_production.py artifact_reader.py
bailian_keys.py bootstrap_clis.py codex_usage.py current_failed_artifact_evidence.py
fabric_client_projection.py fabric_cpu_scope.py fabric_host_qualification.py
fabric_operator_client.py fabric_operator_contract.py fabric_operator_diagnostics.py
fabric_operator_issue.py fabric_operator_owner.py fabric_operator_stop.py
fabric_policy_snapshot.py fabric_stop_return.py fabric_task.py glm_bound_claude.py
glm_codex_exec.sh glm_host_account_probe.py glm_host_account_readiness.py
glm_host_account_source.py glm_keys.py glm_remote_capability.py go_codex_exec.sh
go_lease_capability.py go_lease_gateway.py go_remote_capsule.py go_remote_codex.py
go_remote_run.py go_remote_transport.py host_pick.py host_pull.sh host_pull_backend.py
lane_runtime.py lease_broker.py mac_policy_return.py mm_codex_exec.sh mm_feeder_lib.py
model_tier.py native_completion_reconcile.py native_host_review_controller_reconcile.py
native_host_review_delivery.py native_host_review_reconcile.py
native_host_review_source_delivery.py native_host_review_source_reader.py
native_preexec_reconcile.py native_prestart_reconcile.py native_remote.py oc_free_exec.sh
operator_stdout_delivery.py original_delivery_collector.py original_result_delivery.py
original_result_read.py pick.py placement_view.py pool_ledger.py pool_status.py
quota_remote.py qwen_exec.sh remote_sub.sh remote_sub_exec.py remote_sub_helpers.py
run_observation.py run_observation_delivery.py slot.py studio_mcp_projection.sh
sub.sh support_bundle.py host_pull_probe.template yes
""".split())
ADDITIONS = frozenset({"host_pull_daemon.sh", "host_pull_launchd.plist.template", "paid_provider_entry.py", "paid_host_readiness.py", "recovery_artifacts.py", "fabric_continuation.py", "quota_circuit.py",
                      "capacity_preflight.py", "provider_outcome.py", "native_runtime_bindings.py",
                      "paid_controller_channel.py", "paid_glm_model_client.py", "paid_model_owner.py",
                      "linux_process_identity.py", "paid_controller_spawn.py", "paid_incumbent_state.py", "paid_host_qualification.py", "paid_initializer.py", "paid_initializer_token_data.py", "paid_initializer_nested_data.py", "paid_yaml_runtime.py", "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json",
                      "commission_deadline.py", "current_source_observation.py", "native_plain_packet_check.py", "native_plain_packet_reconcile.py",
                      "post_failure_observation.py", "post_failure_observation_delivery.py",
                      "participant_binding.py", "fabric_participant_owner.py",
                      "original_advertised_artifact.py"})
# The retired credential-to-stdout helper is audit evidence only. It must never
# be importable from source/ or selected as a runtime fallback. Its exact bytes
# still have to match the installed preimage before the secure overlay is used.
PREIMAGE_ONLY = {"bailian_keys.py": "bailian_keys.py.preimage"}
# Canonical protected merged Mastermind PR #1691 provides these nine Grok
# Build 4.7 runtime files. They are ALREADY selected in native sequence 16.
# Keep the byte-verified accepted source instead of reintroducing seq-15 files.
# Never derive these names from a runtime scan or mutable published stage.
GROK47_MERGED_SOURCE_DIGESTS = {
    'artifact_delivery.py': '447ab9d65264f46acfe5662d60e38c1f4db97198afc9113c2717109e298db9c3',
    'fabric_operator_client.py': 'fcb79e9dc4b873832e18e1fde16f0ba900374a08d62d0fc8b9b624a40ec1cd17',
    'fabric_operator_contract.py': 'e642e36ef99d2c40b1254975b9ad3cc218fb9ef81c4ce87f3c7b6e7be0808c6a',
    'native_remote.py': '388c412ee5803ac54356275323eba5fb0ee57519a8810490f81fe13977459f9e',
    'pick.py': '02afff09760a98d593f6bb25c4e6a41e2d7bd4d450d0c668b63c5d4aedf8e0e6',
    'remote_sub.sh': '3177b96fd3e7d4bb1ab0b3762bc99e72bc87fa25496736b3dc262cdea401db64',
    'remote_sub_exec.py': '6be6830dcd9c00dc46cf613a610ad0dc574ca13f50aa1cd5fbffb7e65e1649c1',
    'remote_sub_helpers.py': '9b9881aeb574082e1f54b581ce56af98c6257332d64c2fe0f0be8c9455fec94b',
    'sub.sh': '7ceaba75dc4375bb05742b779967ade294afcc969358f610ecdb43041fa2f7d2',
}

# Four exact forward compositions preserve protected Qwen fresh-usage and
# caller UTC narrowing plus canonical provider entry. Qualify their accepted
# Grok bases above as well as the
# closed composed candidate bytes; neither source may silently replace the other.
GROK47_CANDIDATE_COMPOSITION_DIGESTS = {
    'artifact_delivery.py': '6848a4bfa60708a85dcea130d5b0be8f0d56bba0386b27bf3b5fd355d433494d',
    'remote_sub_exec.py': '4a3ec23923b120ccba86570e9cc21bb40b1f7bd29501fa63882e505e3bd1d281',
    'pick.py': '5d37967731337fa6d49a6a119d415c66fcc35802c167b16de7e8a1751f950892',
    'remote_sub.sh': '2ec99c393cfd4022197978a2ed8869c44649efce8eea6a0d66f14767af8a53cc',
    'remote_sub_helpers.py': 'f7d62e9bdfa7388b7f86c0f968a021bf3949141ddcc8515103075ed3a1da2f93',
    'sub.sh': '4956942c77421b9d1015889995ebf0419399ea62c16de608765a0795b5fb551f',
    'native_remote.py': '2beef7dd4de1dab2908970bed48cfd3fdfd99da2d99bc8de72a92d2a1b2418b6',
    'fabric_operator_contract.py': 'e6b32fd1547402c1184f826f74c253f34384cb6e32306e55b84449a892d19b5e',
}

EXTRA_PREIMAGES = {
    "yes": "b4f5e5353392e8ff4adc4158e1064243d0d7241333e9a891e05c1866b421813a",
    "host_pull_probe.template": "10ff206fb7050210e502d03c6916c092b2d82a2b8929d4b54b9cfe5b97bbea72",
    "pool": "95dad5ac680d605200252f7152ecc80b77a767016874028288822a98b2b72c78",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


GO_INSTALLED_PREIMAGE = "4a41548a757f763ed5210df96aff6c7148d25d9e192cd3d849e108e1e917d100"
GO_APPLICATION_DEPENDENCIES = ("lease_broker.py", "go_lease_capability.py", "go_lease_gateway.py")
# Actual102 closure after protected51e9 and application A3 composition: the B dependencies
# are unchanged; remote_sub retains the protected fast-observation and terminal-replay fixes.
GO_BASE_MANIFEST_SHA256 = "395b1af90c815125a92c81c8b72ec61065002f4f9e66ad53618794ec790ce429"
GO_BASE_PICKER_SHA256 = "747a55a50fb1ae579d18ae4decc6e3b077eb4b927a3968b61abaeeeb6292f132"
# The sparse-config data successor is additive to this exact executor.
GO_BASE_EXECUTOR_SHA256 = "9a01a5b7d559e2f86b92f1da9c7f426d6a5b9c4f1e0ca98542ce8a0452bf87c1"
# Protected47dc keeps diagnostic false distinct from unproved cleanup (76).
# Admit only that exact provider outcome delta while retaining actual395b.
GO_BASE_PROVIDER_OUTCOME_SHA256 = "22b5ae9325118327b8b0734514c6f5711e39ae919f0e04426f7fac182895bf24"
GO_PROTECTED_PROVIDER_OUTCOME_SHA256 = "ff909ac6fb0a734ce0ea1aa78c2b04e992c170e5be413c1b7778e6ffd7c7907e"
GO_BASE_DEPENDENCIES = {
    "lease_broker.py": "b785ff1d83c6e2c6b77c8bd349e37a8624c9055e5fce8aa2307c09b8302d12eb",
    "go_lease_capability.py": "4d0f9aa423afc56dd29d955beaaab06a6ed9082ea503bdbea352af6c99a6e4df",
    "go_lease_gateway.py": "a35096dea01297bd872baff021f544bb300e12754839a9e546d655118c94ad21",
}
HTTP_GENERATION_MEMBERS = frozenset({"ext/application_http_transports.py",
    "ext/application_http_realm_projection.py", "ext/application_http_realms.v1.json"})

# Exact same-owner helpers for application selection. These are two existing
# members, not an open-ended allowance for another source/manifest epoch.
GO_SELECTION_SUPPORT_PREIMAGES = {
    "pool_ledger.py": "34be52eca114c32f44538254b3675ce2d0a79dc420ebda2f42702c6be56ad6cc",
    "quota_circuit.py": "0962d638a0a5655a71ea7a6eeb83088ad60af30f4a26e9c5bc47a92c3ab77945",
}
GO_SELECTION_SUPPORT_DIGESTS = {
    "pool_ledger.py": "a9ba8724ad1d6f9a78944cd87f95c1cb70a0832d71612402565111fb04100ef2",
    "quota_circuit.py": "0b1b07b950625abfa5a935c273594156ea6b8f97ac6426820666f55ac498c303",
}


# Protected process-custody and paid eligibility upgrades form one exact
# source-bound cohort in CURRENT, never a mutation of the frozen 102 baseline.
# These are SHA-256 members of the already-reviewed protected master closure.
GO_PROTECTED_CUSTODY_PREIMAGES = {
    "linux_process_identity.py": "e2cbe24d453116c09af8b25bb936a1e00c9e6999014bc5ea5276edb84b8dcca2",
    "paid_host_qualification.py": "e4cb143b13324bd5ce4d96af5396054b3c63e1b82c831edae4516f37e495a1b0",
    "paid_initializer.py": "d203b1363cdc6f926d9542a2ecfb2ec6b24dd1da46c3fd1f527caea232132749",
}
GO_PROTECTED_CUSTODY_DIGESTS = {
    "linux_process_identity.py": "11a0771d7f8fb8c8288303b3d182100341413098c1ee31d12339330dd869e71e",
    "paid_host_qualification.py": "2a52ba79e6cd38a42ecbd48919704d2c837c65d042707b37640df78f27b8d0c0",
    "paid_initializer.py": "602893be1fa1ece43862ba889e92af8d8e879cb67f62f16840300b7f21ad2887",
}

# Exact protected95e diagnostic cohort: three replacements and two additions.
GO_POST_FAILURE_PREIMAGES = {
    "artifact_delivery.py": "447ab9d65264f46acfe5662d60e38c1f4db97198afc9113c2717109e298db9c3",
    "run_observation.py": "0984a7a221e7d79e30e3c0c0a7cb7425e9f762d73f2946df1d28283f36f85809",
    "run_observation_delivery.py": "eba658de92294a833108c83804c2b237ef9be0356bbc0158ff5709755e8bb147"
}
GO_POST_FAILURE_DIGESTS = {
    "artifact_delivery.py": "81749610b8afd7151dbadb4cbcedbef853fc18ad9de9364fd3b2b1d747d535b1",
    "run_observation.py": "cbe4b0b4db3783e44d9cc442ab973996e8b5102c178ab61e172bfd0aae7accfb",
    "run_observation_delivery.py": "c18ab07723b42a8dece4c072256ad161384508f65bac44bbb9781948710f675b"
}
GO_POST_FAILURE_ADDITIONS = {
    "post_failure_observation.py": "2a78630ccaf574da752c77d7b8f821723ccb264b970e2fe38b1976d886ca97a0",
    "post_failure_observation_delivery.py": "0e096d439e71600a20aabd6f29ea94127596ab3c1a4fb31d567194eba145c7f3"
}
# Protected PR #2101 adds historical-receipt metadata to this same pair.
# Retain the earlier exact pair; never admit a mixture of the two generations.
GO_POST_FAILURE_METADATA_ADDITIONS = {
    "post_failure_observation.py": "80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337",
    "post_failure_observation_delivery.py": "81ab6f7f673e53c53b0e0a0cf4f3f1324642e29563f9213170f2a1ae29a0e4fc",
}
# Protected PR #2104 adds a closed delivery-error diagnostic variant.
# Retain both earlier exact cohorts and reject unknown or mixed members.
GO_POST_FAILURE_DIAGNOSTICS_ADDITIONS = {
    "post_failure_observation.py": "80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337",
    "post_failure_observation_delivery.py": "45636d279cd784248942d37c76e5625b2af7824a8f83638f804d56cff2d568e1",
}

# The completed-SSH255 observer and its helper are one protected source cohort.
# Neither half is admitted independently or backdated into the historical102.
GO_COMPLETED_POLL_PREIMAGES = {
    "fabric_task.py": "778f4f3ebf03f5ce93e60081dc8a739ae90fb4cbeb32d01bbcc7b008c813a23b",
    "remote_sub_helpers.py": "3a4efaefd63244e77cee385d83da0bb4e53b86a0e83a183601f2fa80ec4d602b",
}
GO_COMPLETED_POLL_DIGESTS = {
    "fabric_task.py": "baae8bb99ef6ccda1162dd486a10c8e713bcf4e731ba9160c5e9d1d9bdd1e7d8",
    "remote_sub_helpers.py": "f7d62e9bdfa7388b7f86c0f968a021bf3949141ddcc8515103075ed3a1da2f93",
}


# Protected Ubuntu4 qualification changes these three runtime members as one
# cohort. Normalize it before the older completed-poll pair is checked.
GO_UBUNTU4_PREIMAGES = {
    "fabric_host_qualification.py": "1b1b64342c61e90887a6f023dca3e0c75707b57fecaf05227b1a960cb7922899",
    "fabric_task.py": "baae8bb99ef6ccda1162dd486a10c8e713bcf4e731ba9160c5e9d1d9bdd1e7d8",
    "remote_sub.sh": "a1e271170778f992cf07c780234620c22d17f6242581311c414e30dd428ade40",
}
GO_UBUNTU4_DIGESTS = {
    "fabric_host_qualification.py": "f50ef3208efe97c933372eada2e26b8870ba9b9590e33766f991e3416b613aa2",
    "fabric_task.py": "a653f55fb41fc26cd2efd6e18cb4747025bc85e00ad1ebf11898a6c2d12e41cd",
    "remote_sub.sh": "0835b0ff65f36becb4b150dc3c733e015ae9b3b3d27a00091a4ee1c16c4cfb0c",
}


GO_PARTICIPANT_ADDITIONS = {
    "participant_binding.py": "09aafda1390914e283915204459e37900123cd54a3d0f4e9116102f3a8921f56",
    "fabric_participant_owner.py": "1619505962de4c73f415312871cc407777bf6c04ba6d02fb9be62c9d54a5545c",
}
GO_PARTICIPANT_OPERATOR = "90c6eee6bd7f2ca7d36c6b915a4fe2cae42b749d99ec2170fb39f55c5f72c0c7"
GO_PARTICIPANT_OPERATOR_PREIMAGE = "f81b4f053a22ba973b06214f6d06ed2d66e3fc471c781311f074718683cf4675"
GO_BASE_ORIGINAL_COLLECTOR_SHA256 = "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183"
GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256 = "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83"


GO_ORIGINAL_ARTIFACT_ADDITIONS = {
    "original_advertised_artifact.py": "46a06945d0e640794cb52945a5caece440abee6da1c0ba13eaff371d9dc6e3c0",
}
GO_ORIGINAL_ARTIFACT_PREIMAGE = "81749610b8afd7151dbadb4cbcedbef853fc18ad9de9364fd3b2b1d747d535b1"
GO_ORIGINAL_ARTIFACT_DIGEST = "6848a4bfa60708a85dcea130d5b0be8f0d56bba0386b27bf3b5fd355d433494d"

# Exact protected107 process-census successor; prior namespaces retain their bytes.
GO_CENSUS_RUNTIME_PREIMAGE = "61350902dcf90ac65800f81e20acf473092c45738bbbef9b582548777e4e0329"
GO_CENSUS_RUNTIME_DIGEST = "83b516a07d1262f3f10da5e197ea4b0c776fa1f22d7825a62ae3d068c0b7c35d"
# C36 at fe3265a9: exact owned-child exit observation successor, current107 only.
GO_CENSUS_EXIT_RUNTIME_DIGEST = "a2d1ebea4ee948cd9e34fc9268ae3c043297619c81354592369da119df7a595f"

# Exact current107 remote-cwd successor of the protected Ubuntu4 task member.
# The complete Ubuntu4 cohort must still validate after this normalization.
GO_REMOTE_CWD_TASK_DIGEST = "72f6b0d70d4596c1d059cf57504ff7fd39ca6d3464d96e9f9c6c8172b1a69037"
# Closed refusal diagnostics compose on the exact remote-cwd source in raw107.
# Older namespaces and the frozen Ubuntu4/poll generations retain their bytes.
GO_REQUEST_REFUSAL_TASK_DIGEST = "2d66d51376b4bfd9740947988777809ee53c0314d7155ad2bd73c9a9ec44b7e4"

# One complete successor of the captured protected107 WORKER closure. This
# historical view is validation-only: emitted manifests retain the repaired
# bytes. Future APPLICATION or policy cohorts must compose this exact delta,
# not relabel their unrelated parent as this captured generation.
ADMISSION_INTEGRITY_PARENT_MANIFEST_SHA256 = "815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347"
ADMISSION_INTEGRITY_PREIMAGES = {
    "ext/fabric_task.py": GO_REQUEST_REFUSAL_TASK_DIGEST,
    "ext/lane_runtime.py": GO_CENSUS_EXIT_RUNTIME_DIGEST,
}
ADMISSION_INTEGRITY_DIGESTS = {
    "ext/fabric_task.py": "1bdec660216cd3218d46c5740eee7d4f24a74c3f2dc23b61083dfc503c9d1d68",
    "ext/lane_runtime.py": "b0f8c77af1ddd1eab7b1bd5b3188e6a15f79ceac5a80cbdcdb65c9998a2bce6b",
}


# Reviewed current-quiescence read/guard changes only Broker in exact raw107.
# Validate the whole parent; never normalize a mixed or unrelated source set.
QUALIFICATION_QUIESCENCE_PARENT_SHA256 = "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE = "9525c86bcc78dd01a51c103d5f4b3a587b2611c7fdfe863407e1b919a8ac931a"
QUALIFICATION_QUIESCENCE_BROKER_SHA256 = "5dedf63c1c8f2a7c098ca6669d509971e5118a4693f8341d27c2f17f8b0b836a"


def before_qualification_quiescence(manifest):
    if type(manifest) is not dict:
        raise ValueError("qualification quiescence manifest invalid")
    previous = dict(manifest)
    if previous.get("ext/lease_broker.py") != QUALIFICATION_QUIESCENCE_BROKER_SHA256:
        return previous
    previous["ext/lease_broker.py"] = QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE
    if sha((json.dumps(_source_integrity_parent(previous), sort_keys=True, indent=2) + "\n").encode()) != QUALIFICATION_QUIESCENCE_PARENT_SHA256:
        raise ValueError("qualification quiescence parent closure differs")
    return previous


def before_admission_integrity(manifest):
    """Validate one exact forward cohort without mutating caller identity."""
    if type(manifest) is not dict:
        raise ValueError("native admission integrity manifest invalid")
    manifest = before_qualification_quiescence(manifest)
    if not any(manifest.get(name) == digest
               for name, digest in ADMISSION_INTEGRITY_DIGESTS.items()):
        return dict(manifest)
    if any(manifest.get(name) != digest
           for name, digest in ADMISSION_INTEGRITY_DIGESTS.items()):
        raise ValueError("native admission integrity cohort is incomplete or foreign")
    previous = dict(manifest)
    previous.update(ADMISSION_INTEGRITY_PREIMAGES)
    if sha((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) != ADMISSION_INTEGRITY_PARENT_MANIFEST_SHA256:
        raise ValueError("native admission integrity parent closure differs")
    return previous


# The complete host-pull repair composes only on the current protected107
# admission-integrity closure. This inverse is a validation view; emitted
# manifests and staged payloads keep the repaired source identities.
HOST_PULL_INTEGRITY_PARENT_MANIFEST_SHA256 = "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
HOST_PULL_INTEGRITY_PREIMAGES = {
    "ext/host_pull.sh": "b58b4cf4932b801df45d4a70fdd99aaaee800e7e57cc06501aa5c21b20ea8a1c",
    "ext/host_pull_backend.py": "d00ff264dcb1a51b73d1e1f772da22a2130873f517299e8c430f060a8191f248",
    "ext/host_pull_daemon.sh": "826aed96db81ecbfee1b647a1d5e4842414d43961b6daaea5a77606e9e679345",
}
HOST_PULL_INTEGRITY_DIGESTS = {
    "ext/host_pull.sh": "464d9a5522a61311d5e8c2b7495a6297c86300d611903ad56524d4aa2e574e72",
    "ext/host_pull_backend.py": "822226666c479137afe8f357d43032a805066a71a5b90d38f2051b40230c2ae9",
    "ext/host_pull_daemon.sh": "842c12036b7bcd1a7101747a522efa272a893474342d57817fb06ecee3e73f0b",
}


def _source_integrity_parent(manifest):
    """Prove the same complete parent for either or both exact source deltas.

    This private proof view never replaces emitted or captured current bytes.
    Each public inverse still returns only its own declared inverse.
    """
    previous = dict(manifest)
    if previous.get("ext/lease_broker.py") == QUALIFICATION_QUIESCENCE_BROKER_SHA256:
        previous["ext/lease_broker.py"] = QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE
    if any(previous.get(name) == digest
           for name, digest in HOST_PULL_INTEGRITY_DIGESTS.items()):
        if any(previous.get(name) != digest
               for name, digest in HOST_PULL_INTEGRITY_DIGESTS.items()):
            raise ValueError("native host-pull integrity cohort is incomplete or foreign")
        previous.update(HOST_PULL_INTEGRITY_PREIMAGES)
    return previous


def before_host_pull_integrity(manifest):
    """Validate the complete host-pull successor without changing its identity."""
    if type(manifest) is not dict:
        raise ValueError("native host-pull integrity manifest invalid")
    if not any(manifest.get(name) == digest
               for name, digest in HOST_PULL_INTEGRITY_DIGESTS.items()):
        return dict(manifest)
    if any(manifest.get(name) != digest
           for name, digest in HOST_PULL_INTEGRITY_DIGESTS.items()):
        raise ValueError("native host-pull integrity cohort is incomplete or foreign")
    previous = dict(manifest)
    previous.update(HOST_PULL_INTEGRITY_PREIMAGES)
    if sha((json.dumps(_source_integrity_parent(previous), sort_keys=True, indent=2) + "\n").encode()) != HOST_PULL_INTEGRITY_PARENT_MANIFEST_SHA256:
        raise ValueError("native host-pull integrity parent closure differs")
    return previous


# One exact command-scoped advice setting extends the complete accepted72
# closure. This inverse is used only for historical validation, never capture.
SPARSE_INDEX_ADVICE_PARENT_SHA256 = "45a90565e189bca551cb79f579296689aa00674778d3917a6af75a720ff71c18"
SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE = "710115e08673467ce39a0322da2cf718a66e5b95d4a62a9eff94e160f79515db"
SPARSE_INDEX_ADVICE_EXECUTOR_SHA256 = "4a3ec23923b120ccba86570e9cc21bb40b1f7bd29501fa63882e505e3bd1d281"


# Ubuntu4's closed central GLM-Codex qualification has three coupled native
# source deltas. Normalize only this exact cohort to the protected current107
# predecessor when proving existing historical source closure. This cannot
# authorize an arbitrary host, remote provider token, or mixed source release.
UBUNTU4_CENTRAL_GLM_NATIVE_DIGESTS = {
    "ext/fabric_host_qualification.py": "ae443c6dc465733cde78cc823e523b2f00203e1f4bc5dbe166b59a4999aad8ab",
    "ext/fabric_task.py": "85bebdfd19ec5d13124608e74ebe37fd310a0d4d0fb5071a6e8fc4d87463d799",
    "ext/remote_sub.sh": "2ec99c393cfd4022197978a2ed8869c44649efce8eea6a0d66f14767af8a53cc",
}
UBUNTU4_CENTRAL_GLM_NATIVE_PREIMAGES = {
    "ext/fabric_host_qualification.py": "f50ef3208efe97c933372eada2e26b8870ba9b9590e33766f991e3416b613aa2",
    "ext/fabric_task.py": "1bdec660216cd3218d46c5740eee7d4f24a74c3f2dc23b61083dfc503c9d1d68",
    "ext/remote_sub.sh": "0835b0ff65f36becb4b150dc3c733e015ae9b3b3d27a00091a4ee1c16c4cfb0c",
}


def before_ubuntu4_central_glm(manifest):
    if type(manifest) is not dict:
        raise ValueError("Ubuntu4 central GLM source manifest invalid")
    previous = dict(manifest)
    if not any(previous.get(name) == digest
               for name, digest in UBUNTU4_CENTRAL_GLM_NATIVE_DIGESTS.items()):
        return previous
    if any(previous.get(name) != digest
           for name, digest in UBUNTU4_CENTRAL_GLM_NATIVE_DIGESTS.items()):
        raise ValueError("Ubuntu4 central GLM source cohort incomplete or foreign")
    previous.update(UBUNTU4_CENTRAL_GLM_NATIVE_PREIMAGES)
    return previous


def before_sparse_index_advice(manifest):
    if type(manifest) is not dict:
        raise ValueError("native sparse-index advice manifest invalid")
    previous = before_ubuntu4_central_glm(manifest)
    if previous.get("ext/remote_sub_exec.py") != SPARSE_INDEX_ADVICE_EXECUTOR_SHA256:
        return previous
    previous["ext/remote_sub_exec.py"] = SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE
    if sha((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) != SPARSE_INDEX_ADVICE_PARENT_SHA256:
        raise ValueError("native sparse-index advice parent closure differs")
    return previous


def validate_go_base_manifest(manifest, dependency_hashes):
    """Accept exact historical102/prior104/previous106/current107 compositions.

    Both the builder and installer compare A3 with their reviewed source
    component first. The picker successor is independently source-pinned by
    the existing Grok composition owner. Normalize only that exact successor
    (or the unchanged historical picker), plus the two closed same-owner
    support changes, the exact protected diagnostic outcome correction, and
    the complete protected Ubuntu4/poll cohorts within the current diagnostic
    closure, the exact sparse-config executor successor, and the complete
    protected participant cohort in the complete106 namespace. The exact
    advertised-artifact recovery pair extends that closure to107 and is
    projected back to106 before historical validation; it grants no new
    application artifact access.
    The two exact current107 census successors and the exact remote-cwd and
    refusal task successors are normalized without changing any historical namespace
    or the caller manifest. The task successor still requires the complete
    Ubuntu4 and poll cohorts. Every other member/key stays bound to actual395b.
    The closed original-collection successor is accepted only in the complete
    current107 namespace; historical106/104/102 retain the original collector.
    """
    # Bind actual captured bytes independently of the historical parent proof.
    # Both views start from this same exact-dict snapshot; normalization never
    # substitutes predecessor bytes for the source captured by the Go component.
    if type(manifest) is not dict:
        raise ValueError("native admission integrity manifest invalid")
    actual_manifest = dict(manifest)
    manifest = before_admission_integrity(before_host_pull_integrity(before_sparse_index_advice(actual_manifest)))
    expected = {"pool"} | {"ext/" + name for name in BASE_FILES | ADDITIONS}
    previous_expected = expected - {"ext/" + name for name in GO_ORIGINAL_ARTIFACT_ADDITIONS}
    prior_expected = previous_expected - {"ext/" + name for name in GO_PARTICIPANT_ADDITIONS}
    historical_expected = prior_expected - {"ext/" + name for name in GO_POST_FAILURE_ADDITIONS}
    if (type(manifest) is not dict
            or frozenset(manifest) not in (frozenset(expected), frozenset(previous_expected), frozenset(prior_expected),
                                          frozenset(historical_expected))
            or type(dependency_hashes) is not dict
            or set(dependency_hashes) != set(GO_APPLICATION_DEPENDENCIES)):
        raise ValueError("native Go base dependency closure differs")
    normalized = dict(manifest)
    runtime = manifest["ext/lane_runtime.py"]
    if runtime in (GO_CENSUS_RUNTIME_DIGEST, GO_CENSUS_EXIT_RUNTIME_DIGEST):
        if set(manifest) != expected:
            raise ValueError("native Go census cannot relabel historical namespace")
        normalized["ext/lane_runtime.py"] = GO_CENSUS_RUNTIME_PREIMAGE
    elif runtime != GO_CENSUS_RUNTIME_PREIMAGE:
        raise ValueError("native Go census is not the exact protected source")
    if manifest["ext/fabric_task.py"] == GO_REQUEST_REFUSAL_TASK_DIGEST:
        if set(manifest) != expected:
            raise ValueError("native Go refusal task cannot relabel historical namespace")
        normalized["ext/fabric_task.py"] = GO_REMOTE_CWD_TASK_DIGEST
    if normalized["ext/fabric_task.py"] == GO_REMOTE_CWD_TASK_DIGEST:
        if set(manifest) != expected:
            raise ValueError("native Go remote-cwd task cannot relabel historical namespace")
        normalized["ext/fabric_task.py"] = GO_UBUNTU4_DIGESTS["fabric_task.py"]
    if set(manifest) == expected:
        if (any(manifest["ext/" + name] != digest for name, digest in GO_ORIGINAL_ARTIFACT_ADDITIONS.items())
                or manifest["ext/artifact_delivery.py"] != GO_ORIGINAL_ARTIFACT_DIGEST):
            raise ValueError("native Go original-artifact recovery is not one exact protected pair")
        for name in GO_ORIGINAL_ARTIFACT_ADDITIONS:
            del normalized["ext/" + name]
        normalized["ext/artifact_delivery.py"] = GO_ORIGINAL_ARTIFACT_PREIMAGE
    projected_namespace = set(normalized)
    current_diagnostics = projected_namespace != historical_expected
    if projected_namespace == previous_expected:
        if (any(normalized["ext/" + name] != digest for name, digest in GO_PARTICIPANT_ADDITIONS.items())
                or normalized["ext/fabric_operator_owner.py"] != GO_PARTICIPANT_OPERATOR):
            raise ValueError("native Go participant cohort is not the exact protected source")
        for name in GO_PARTICIPANT_ADDITIONS:
            del normalized["ext/" + name]
        normalized["ext/fabric_operator_owner.py"] = GO_PARTICIPANT_OPERATOR_PREIMAGE
    ubuntu4 = {name: normalized["ext/" + name] for name in GO_UBUNTU4_DIGESTS}
    if any(ubuntu4[name] == digest for name, digest in GO_UBUNTU4_DIGESTS.items()):
        if not current_diagnostics or ubuntu4 != GO_UBUNTU4_DIGESTS:
            raise ValueError("native Go Ubuntu4 cohort is not the exact protected source")
        normalized.update({"ext/" + name: digest
                           for name, digest in GO_UBUNTU4_PREIMAGES.items()})
    historical = dict(normalized)
    poll_pair = {name: normalized["ext/" + name] for name in GO_COMPLETED_POLL_PREIMAGES}
    if (poll_pair != GO_COMPLETED_POLL_PREIMAGES
            and not (current_diagnostics and poll_pair == GO_COMPLETED_POLL_DIGESTS)):
        raise ValueError("native Go completed-poll cohort is not the exact protected source")
    historical.update({"ext/" + name: digest
                       for name, digest in GO_COMPLETED_POLL_PREIMAGES.items()})
    for name, original in GO_POST_FAILURE_PREIMAGES.items():
        exact = GO_POST_FAILURE_DIGESTS[name] if current_diagnostics else original
        if normalized["ext/" + name] != exact:
            raise ValueError("native Go post-failure cohort is not the exact protected source")
        historical["ext/" + name] = original
    if current_diagnostics:
        additions = {name: manifest["ext/" + name]
                     for name in GO_POST_FAILURE_ADDITIONS}
        if additions not in (GO_POST_FAILURE_ADDITIONS, GO_POST_FAILURE_METADATA_ADDITIONS,
                             GO_POST_FAILURE_DIAGNOSTICS_ADDITIONS):
            raise ValueError("native Go post-failure additions are not one exact protected cohort")
        for name in GO_POST_FAILURE_ADDITIONS:
            del historical["ext/" + name]
    for name, original in GO_BASE_DEPENDENCIES.items():
        if actual_manifest["ext/" + name] != dependency_hashes[name]:
            raise ValueError("native Go base differs from captured application dependency")
        historical["ext/" + name] = original
    if manifest["ext/pick.py"] not in {
            GO_BASE_PICKER_SHA256, GROK47_CANDIDATE_COMPOSITION_DIGESTS["pick.py"]}:
        raise ValueError("native Go base picker is not the exact composed source")
    historical["ext/pick.py"] = GO_BASE_PICKER_SHA256
    # The new advice epoch was already qualified against its full107 parent.
    # Historical validation still recognizes exactly its original710 endpoint.
    if manifest["ext/remote_sub_exec.py"] not in {
            GO_BASE_EXECUTOR_SHA256, SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE}:
        raise ValueError("native Go executor is not the exact composed source")
    historical["ext/remote_sub_exec.py"] = GO_BASE_EXECUTOR_SHA256
    for name, original in GO_SELECTION_SUPPORT_PREIMAGES.items():
        if manifest["ext/" + name] not in {original, GO_SELECTION_SUPPORT_DIGESTS[name]}:
            raise ValueError("native Go selection support is not the exact composed source")
        historical["ext/" + name] = original
    if manifest["ext/provider_outcome.py"] not in {
            GO_BASE_PROVIDER_OUTCOME_SHA256, GO_PROTECTED_PROVIDER_OUTCOME_SHA256}:
        raise ValueError("native Go provider outcome is not the exact protected source")
    historical["ext/provider_outcome.py"] = GO_BASE_PROVIDER_OUTCOME_SHA256
    collector = manifest["ext/original_delivery_collector.py"]
    if (collector not in {GO_BASE_ORIGINAL_COLLECTOR_SHA256,
                          GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256}
            or (collector == GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256
                and set(manifest) != expected)):
        raise ValueError("native Go original collector is not the exact current source")
    historical["ext/original_delivery_collector.py"] = GO_BASE_ORIGINAL_COLLECTOR_SHA256
    # Preserve exact source hashes and deny partial/mixed custody receipts.
    # The protected/current trio belongs only to the complete current106
    # namespace, never a relabelled historical102 or prior104 closure.
    custody = {name: historical["ext/" + name]
               for name in GO_PROTECTED_CUSTODY_PREIMAGES}
    if custody == GO_PROTECTED_CUSTODY_DIGESTS:
        if projected_namespace != previous_expected:
            raise ValueError("native Go custody cannot relabel historical namespace")
        historical.update({"ext/" + name: digest
                           for name, digest in GO_PROTECTED_CUSTODY_PREIMAGES.items()})
    elif custody != GO_PROTECTED_CUSTODY_PREIMAGES:
        raise ValueError("native Go protected custody cohort changed")
    if sha((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) != GO_BASE_MANIFEST_SHA256:
        raise ValueError("native Go base closure is not the reviewed protected composition")


def application_http_sources(root):
    """Compile immutable metadata from the exact three historical inputs.

    Realm and H preimages are explicitly mapped as AST evidence only. New
    candidate realms must not rewrite the accepted two-driver metadata or
    invalidate its historical input closure. The independently sealed CURRENT
    H is the sole transport code in the flat runtime closure. No preimage is
    imported or staged; no Git history, credential or provider is consulted.
    """
    root = Path(root)
    reader = root / "rollout/application_http_realm_projection.py"
    def read(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("application HTTP source must be an explicit regular file")
        return path.read_bytes()
    reader_raw = read(reader)
    # Execute and seal the SAME captured compiler bytes. A stale/substituted
    # same-path module in a reused builder process is not source evidence.
    compiler = {"__name__": "mastermind_http_projection_compiler", "__file__": str(reader)}
    exec(compile(reader_raw, str(reader), "exec"), compiler)
    evidence = {
        compiler["REALM_SOURCE_PATH"]: root / "source/codex_provider_realm.py.preimage",
        compiler["TRANSPORT_SOURCE_PATH"]: root / "source/application_http_transports.py.preimage",
    }
    inputs = {row["path"]: read(evidence.get(row["path"], root.parents[2] / row["path"]))
        for row in compiler["INPUT_SOURCES"]}
    payload = compiler["compile_projection_bytes"](inputs)
    compiler["validate_projection"](payload, expected_sha256=sha(payload))
    return {"ext/application_http_transports.py":
                (read(root / "candidate/application_http_transports.py"), "candidate/application_http_transports.py"),
            "ext/application_http_realm_projection.py":
                (reader_raw, "rollout/application_http_realm_projection.py"),
            "ext/application_http_realms.v1.json":
                (payload, "generated:rollout/application_http_realm_projection.py")}


def compose_application_http_stage(root, output, manifest, files):
    """Add one closed metadata/reader/transport group to existing Go ingress."""
    if (not {"ext/native_go_entry.py", "ext/go_application_handler.py"}.issubset(manifest)
            or HTTP_GENERATION_MEMBERS & set(manifest)):
        raise ValueError("application HTTP requires one unextended Go composition")
    additions = application_http_sources(root)
    for relative in additions:
        target = Path(output) / "native-code-stage" / relative
        if target.exists() or target.is_symlink():
            raise ValueError("application HTTP stage destination already exists")
    for relative, (raw, source) in additions.items():
        (Path(output) / "native-code-stage" / relative).write_bytes(raw)
        manifest[relative] = sha(raw)
        files[relative] = {"source": source, "sha256": sha(raw),
            "installed_preimage_sha256": None, "bytes": len(raw)}


def stage_external_go_component(root, output, stable_ext, *, staged_manifest=None):
    """One closed external-owner bundle; never installs or changes a generation.

    The original nested handler and state owner remain separate from the flat
    native stage. C's existing generation/installer must explicitly consume and
    qualify this component before any installed path can change.
    """
    root, output = Path(root), Path(output)
    if (not isinstance(stable_ext, str) or not Path(stable_ext).is_absolute()
            or ".." in Path(stable_ext).parts):
        raise ValueError("external Go stable owner path invalid")
    sources = {"source-go_shim.py": root / "source/go_shim.py",
               "go_shim.py": root / "candidate/go_shim.py"}
    raw = {}
    for name, path in sources.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError("external Go source must be an explicit regular file")
        raw[name] = path.read_bytes()
    if sha(raw["source-go_shim.py"]) != GO_INSTALLED_PREIMAGE:
        raise ValueError("external Go installed preimage mismatch")
    dependencies = {}
    for name in GO_APPLICATION_DEPENDENCIES:
        path = root / "candidate" / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("external Go application dependency unavailable")
        data = path.read_bytes()
        dependencies[name] = {"sha256": sha(data), "bytes": len(data), "source": "candidate/" + name}
    staged_dependencies = None
    if staged_manifest is not None:
        staged_dependencies = {}
        for name, dependency in dependencies.items():
            relative = "ext/" + name
            staged = output / "native-code-stage" / relative
            expected = staged_manifest.get(relative)
            if (not isinstance(expected, str) or expected != dependency["sha256"]
                    or staged.is_symlink() or not staged.is_file()
                    or sha(staged.read_bytes()) != expected):
                raise ValueError("external Go dependency differs from captured native stage")
            staged_dependencies[name] = expected
    record = {"schema": "native-external-go-component.v1", "component": "go_application_handler",
        "destination_relative_to_stable_ext": "go_shim/go_shim.py", "stable_ext": stable_ext,
        "installed_preimage_sha256": GO_INSTALLED_PREIMAGE,
        "candidate_sha256": sha(raw["go_shim.py"]), "candidate_bytes": len(raw["go_shim.py"]),
        "candidate_source": "candidate/go_shim.py", "dependencies": dependencies,
        "native_stage_dependencies": staged_dependencies,
        "preimage_source_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6646945527",
        "installation_state": "HELD_REQUIRES_PROTECTED_RELEASE_AND_EXISTING_OWNER_INSTALLATION"}
    bundle = output / "external-go-component"
    if bundle.is_symlink() or bundle.exists() and not bundle.is_dir():
        raise ValueError("external Go bundle directory invalid")
    for name in (*raw, "component.json"):
        path = bundle / name
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError("external Go bundle member invalid")
    bundle.mkdir(parents=True, exist_ok=True)
    for name, data in raw.items():
        (bundle / name).write_bytes(data)
    (bundle / "component.json").write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def compose_go_stage(root, output, manifest, files, component):
    """Join only the captured external B handler and the fixed native entry."""
    root, output = Path(root), Path(output)
    validate_go_base_manifest(manifest,
        {name: row["sha256"] for name, row in component["dependencies"].items()})
    expected = {"ext/" + name: row["sha256"] for name, row in component["dependencies"].items()}
    if (component.get("schema") != "native-external-go-component.v1"
            or component.get("component") != "go_application_handler"
            or component.get("destination_relative_to_stable_ext") != "go_shim/go_shim.py"
            or component.get("installed_preimage_sha256") != GO_INSTALLED_PREIMAGE
            or set(component["dependencies"]) != set(GO_APPLICATION_DEPENDENCIES)
            or component.get("native_stage_dependencies") != {
                name: manifest.get("ext/" + name) for name in GO_APPLICATION_DEPENDENCIES}
            or any(manifest.get(name) != digest for name, digest in expected.items())):
        raise ValueError("native Go component closure differs")
    handler = output / "external-go-component/go_shim.py"
    entry = root / "candidate/native_go_entry.py"
    for path in (handler, entry):
        if path.is_symlink() or not path.is_file():
            raise ValueError("native Go source is not an explicit regular file")
    handler_raw, entry_raw = handler.read_bytes(), entry.read_bytes()
    if (sha(handler_raw) != component["candidate_sha256"]
            or len(handler_raw) != component["candidate_bytes"]):
        raise ValueError("captured native Go handler changed")
    additions = {"ext/go_application_handler.py": (handler_raw, "candidate/go_shim.py"),
                 "ext/native_go_entry.py": (entry_raw, "candidate/native_go_entry.py")}
    if set(additions) & set(manifest):
        raise ValueError("native Go stage was already composed")
    for relative, (raw, source) in additions.items():
        target = output / "native-code-stage" / relative
        if target.exists() or target.is_symlink():
            raise ValueError("native Go stage destination already exists")
        target.write_bytes(raw)
        manifest[relative] = sha(raw)
        files[relative] = {"source": source, "sha256": sha(raw),
            "installed_preimage_sha256": None, "bytes": len(raw)}


def main():
    draft = Path(__file__).resolve().parent
    root = draft.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=draft,
                        help='artifact directory outside immutable released source when deploying')
    parser.add_argument('--include-go-application', action='store_true',
                        help='include the fixed Go entry/handler source pair; does not enroll or start services')
    parser.add_argument('--include-application-http', action='store_true',
                        help='seal fixed HTTP transport metadata; requires Go ingress and grants no application permission')
    args = parser.parse_args()
    if args.include_application_http and not args.include_go_application:
        parser.error('--include-application-http requires --include-go-application')
    output = args.output
    inventory = json.loads((draft / 'native-preimages.json').read_text())
    if (inventory.get('schema') != 'native-code-preimages.v1'
            or set(inventory['files']) != BASE_FILES | {'pool_launcher.sh'}):
        raise ValueError('explicit native preimage inventory differs')
    rows = inventory['files']
    stage = output / "native-code-stage"
    (stage / "ext").mkdir(parents=True, exist_ok=True)
    manifest = {}
    files = {}
    for name in sorted(BASE_FILES | ADDITIONS):
        if name in GROK47_MERGED_SOURCE_DIGESTS:
            source = root.parent / "grok47" / "overlay" / name
            if source.is_symlink() or not source.is_file():
                raise ValueError("accepted Grok 4.7 source digest mismatch: " + name)
            # The staged bytes must be the exact approved source bytes,
            # not a second unverified read after the digest check.
            raw = source.read_bytes()
            if sha(raw) != GROK47_MERGED_SOURCE_DIGESTS[name]:
                raise ValueError("accepted Grok 4.7 source digest mismatch: " + name)
            if name in GROK47_CANDIDATE_COMPOSITION_DIGESTS:
                source = root / "candidate" / name
                if source.is_symlink() or not source.is_file():
                    raise ValueError("accepted Grok forward composition mismatch: " + name)
                raw = source.read_bytes()
                if sha(raw) != GROK47_CANDIDATE_COMPOSITION_DIGESTS[name]:
                    raise ValueError("accepted Grok forward composition mismatch: " + name)
        else:
            choices = (root / "candidate" / name,)
            if name not in PREIMAGE_ONLY:
                choices += (root / "source" / name,)
            source = next((p for p in choices if p.is_file()), None)
            if source is None or source.is_symlink():
                raise ValueError("missing explicit regular code dependency: " + name)
            raw = source.read_bytes()
        preimage = rows.get(name)
        if name in BASE_FILES:
            original = root / "source" / PREIMAGE_ONLY.get(name, name)
            if (not preimage or original.is_symlink()
                    or sha(original.read_bytes()) != preimage):
                raise ValueError("installed preimage mismatch: " + name)
        relative = "ext/" + name
        (stage / relative).write_bytes(raw)
        manifest[relative] = sha(raw)
        source_ref = ("../grok47/overlay/" + name if name in GROK47_MERGED_SOURCE_DIGESTS
                      and name not in GROK47_CANDIDATE_COMPOSITION_DIGESTS
                      else str(source.relative_to(root)))
        files[relative] = {"source": source_ref, "sha256": sha(raw),
                           "installed_preimage_sha256": preimage, "bytes": len(raw)}
    source = root / "candidate/pool_launcher.sh"
    if source.is_symlink() or sha((root/'source/pool_launcher.sh').read_bytes()) != rows['pool_launcher.sh']:
        raise ValueError('installed pool launcher preimage mismatch')
    raw = source.read_bytes()
    (stage / "pool").write_bytes(raw)
    manifest["pool"] = sha(raw)
    files["pool"] = {"source": str(source.relative_to(root)), "sha256": sha(raw),
                     "installed_preimage_sha256": rows['pool_launcher.sh'], "bytes": len(raw)}
    if {p.name for p in (stage / "ext").iterdir()} != BASE_FILES | ADDITIONS:
        raise ValueError("unexpected staged native file")
    pure_yaml = json.loads((root/"candidate/paid_pyyaml_provenance.json").read_bytes())
    pure_archive=(root/"candidate/paid_pyyaml_6_0_3.zip").read_bytes()
    if sha(pure_archive) != pure_yaml["zip_sha256"]:
        raise ValueError("qualified pure YAML archive differs")
    lock=(root.parents[2]/pure_yaml['lock_path']).read_bytes()
    if (sha(lock)!=pure_yaml['lock_sha256'] or pure_yaml['package']!='PyYAML'
            or pure_yaml['version']!='6.0.3'
            or ('PyYAML==6.0.3 --hash=sha256:'+pure_yaml['artifact_sha256']).encode() not in lock):
        raise ValueError('qualified pure YAML lock differs')
    with zipfile.ZipFile(io.BytesIO(pure_archive)) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())) or set(archive.namelist())!=set(pure_yaml['files']):
            raise ValueError('qualified pure YAML closure differs')
        for name,item in pure_yaml['files'].items():
            raw=archive.read(name)
            if (name not in {'LICENSE','METADATA'} and not (name.startswith('yaml/') and name.endswith('.py'))
                    or len(raw)!=item['bytes'] or sha(raw)!=item['sha256']):
                raise ValueError('qualified pure YAML member differs')
    # Qualify the complete repair cohort even when no APPLICATION pair is added.
    before_admission_integrity(before_host_pull_integrity(before_sparse_index_advice(manifest)))
    component = stage_external_go_component(root, output, inventory["stable_ext"], staged_manifest=manifest)
    if args.include_go_application:
        compose_go_stage(root, output, manifest, files, component)
    extra = {"native_go_entry.py", "go_application_handler.py"} if args.include_go_application else set()
    if args.include_application_http:
        compose_application_http_stage(root, output, manifest, files)
        extra |= {Path(name).name for name in HTTP_GENERATION_MEMBERS}
    if {p.name for p in (stage / "ext").iterdir()} != BASE_FILES | ADDITIONS | extra:
        raise ValueError("unexpected composed native file")
    record = {"qualified_pure_yaml": pure_yaml, "schema": "native-code-source-inventory.v1", "native_code_files": len(manifest),
        "baseline_code_files": len(BASE_FILES) + 1, "new_code_files": sorted(ADDITIONS | extra),
        "source_status": "SOURCE_INVENTORY_REQUIRES_PROTECTED_RELEASE_AND_INSTALLATION_EVIDENCE",
        "stable_ext": inventory["stable_ext"], "files": files,
        "excluded_historical_importer": "fabric_operator_recovery.py",
        "excluded_comment_only_edges": [["qwen_exec.sh", "lane2.py"],
            ["qwen_exec.sh", "qwen_review.py"], ["mm_feeder_lib.py", "mm_feeder.sh"]],
        "external_owners": ["System Python/Bash and installed provider CLIs",
            "Original glm_shim/go_shim/lane_bin runtime owners",
            "Original dedicated Claude/Codex profile owners",
            "Original fixed historical evidence/source-validator locations"],
        "deployment_rule": "Modified bytes must come from protected merged source; rebuild after any source change."}
    for name, value in (("native-manifest.json", manifest), ("native-source-inventory.json", record)):
        (output / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"native_files": len(manifest), "total_bytes": sum(v["bytes"] for v in files.values()),
        "manifest_sha256": sha((output / "native-manifest.json").read_bytes()),
        "source_inventory_sha256": sha((output / "native-source-inventory.json").read_bytes())}))


if __name__ == "__main__":
    main()
