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
ADDITIONS = frozenset({"recovery_artifacts.py", "fabric_continuation.py", "quota_circuit.py",
                      "capacity_preflight.py", "provider_outcome.py", "native_runtime_bindings.py",
                      "paid_controller_channel.py", "paid_glm_model_client.py", "paid_model_owner.py",
                      "linux_process_identity.py", "paid_controller_spawn.py", "paid_incumbent_state.py", "paid_host_qualification.py", "paid_initializer.py", "paid_initializer_token_data.py", "paid_initializer_nested_data.py", "paid_yaml_runtime.py", "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json",
                      "commission_deadline.py", "current_source_observation.py", "native_plain_packet_check.py", "native_plain_packet_reconcile.py"})
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

# PR #1797 composes the existing Qwen/Grok-forward picker with a two-hunk
# judgment review-routing repair. The protected Grok overlay digest above is
# unchanged; the source-owned candidate postimage is pinned independently below.
# Former Qwen/Grok-forward candidate pick SHA256: a3c3a9822779e244f4140dc1223c4a2617243ed35c12c0358527d637fc1fc1ee.
# Three exact forward compositions preserve protected Qwen fresh-usage and
# caller UTC narrowing. Qualify their accepted Grok bases above as well as the
# closed composed candidate bytes; neither source may silently replace the other.
GROK47_CANDIDATE_COMPOSITION_DIGESTS = {
    'pick.py': '4008caca8c6a0e2145e7cb90965740ce24445e3300a8e3693d7a96130df236df',
    'remote_sub.sh': '09e000db51b2eca4fadd2e3d1a201f4027b4ea725359d1b42ef4d3baf92fe5d7',
    'remote_sub_helpers.py': '0d5f5c38b60eeef70cc7cefe37ee64bd69d56d3e3bdd32644871279fc0e88556',
}

EXTRA_PREIMAGES = {
    "yes": "b4f5e5353392e8ff4adc4158e1064243d0d7241333e9a891e05c1866b421813a",
    "host_pull_probe.template": "10ff206fb7050210e502d03c6916c092b2d82a2b8929d4b54b9cfe5b97bbea72",
    "pool": "95dad5ac680d605200252f7152ecc80b77a767016874028288822a98b2b72c78",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    draft = Path(__file__).resolve().parent
    root = draft.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=draft,
                        help='artifact directory outside immutable released source when deploying')
    output = parser.parse_args().output
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
    record = {"qualified_pure_yaml": pure_yaml, "schema": "native-code-source-inventory.v1", "native_code_files": len(manifest),
        "baseline_code_files": len(BASE_FILES) + 1, "new_code_files": sorted(ADDITIONS),
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
