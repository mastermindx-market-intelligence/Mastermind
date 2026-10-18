#!/usr/bin/env python3
"""Assemble the explicit reviewed native closure locally; never install it.

This review workspace contains exact installed preimages plus proposed source
overlays. The resulting bytes must be committed/reviewed/merged before release.
No directory scan decides what to transport; this fixed list is the inventory.
"""
import argparse
import hashlib
import json
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
                      "commission_deadline.py"})
# The retired credential-to-stdout helper is audit evidence only. It must never
# be importable from source/ or selected as a runtime fallback. Its exact bytes
# still have to match the installed preimage before the secure overlay is used.
PREIMAGE_ONLY = {"bailian_keys.py": "bailian_keys.py.preimage"}
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
        choices = (root / "candidate" / name,)
        if name not in PREIMAGE_ONLY:
            choices += (root / "source" / name,)
        source = next((p for p in choices if p.is_file()), None)
        if source is None or source.is_symlink():
            raise ValueError("missing explicit regular code dependency: " + name)
        preimage = rows.get(name)
        if name in BASE_FILES:
            original = root / "source" / PREIMAGE_ONLY.get(name, name)
            if (not preimage or original.is_symlink()
                    or sha(original.read_bytes()) != preimage):
                raise ValueError("installed preimage mismatch: " + name)
        raw = source.read_bytes()
        relative = "ext/" + name
        (stage / relative).write_bytes(raw)
        manifest[relative] = sha(raw)
        files[relative] = {"source": str(source.relative_to(root)), "sha256": sha(raw),
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
    record = {"schema": "native-code-source-inventory.v1", "native_code_files": len(manifest),
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
