#!/usr/bin/env python3
"""Read-only qualification of pinned M2 Fabric generation and a 4.7 overlay.

Publication and selection occur exclusively in a fresh temporary fake owner,
never in the provided installed store. No provider, broker, or worker is started.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import os
import subprocess
import sys
import tempfile

ORIGINAL_REVIEWED_BASE = '0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f'
# Protected master PR #1730 accepted an unrelated native release. We must
# preserve its three installed files rather than publish a stale seq14 closure.
BASE = '3a1bbcf121e9ec63ffba7a035ca67a380736608023ad3d74c2f0a67325255178'
OVERLAYS = frozenset({
    'ext/artifact_delivery.py', 'ext/fabric_operator_client.py',
    'ext/fabric_operator_contract.py', 'ext/native_remote.py',
    'ext/pick.py', 'ext/remote_sub.sh', 'ext/sub.sh',
    'ext/remote_sub_exec.py', 'ext/remote_sub_helpers.py',
})
HERE = Path(__file__).resolve().parent
GEN = HERE.parent / 'quota_continuity/rollout/native_generation.py'
spec = importlib.util.spec_from_file_location('qualified_native_generation', GEN)
generation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generation)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def verify_incumbent_grok_policy(store: Path) -> dict:
    """Fail closed if the installed signed policy overrides our 4.7 source default.

    No policy file is modified. A later native-generation selection must
    repeat this same read and compare the observed policy digest.
    """
    store = store.resolve(strict=True)
    path = store.parent / "orch" / "fabric" / "pools.yaml"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
        raise ValueError("grok47_incumbent_policy_unavailable")
    try:
        import yaml
        raw = path.read_bytes()
        doc = yaml.safe_load(raw)
    except Exception as exc:
        raise ValueError("grok47_incumbent_policy_unreadable") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("pools"), dict):
        raise ValueError("grok47_incumbent_policy_invalid")
    grok = doc["pools"].get("grok")
    if not isinstance(grok, dict):
        raise ValueError("grok47_incumbent_grok_pool_missing")
    configured = grok.get("default_model")
    if configured not in (None, "", "grok-4.7"):
        # Never silently bypass a critical routing-policy snapshot with an
        # unreviewed new source default. Route owner must reconcile this first.
        raise ValueError("grok47_policy_default_conflict")
    return {"sha256": sha(raw), "configured_default": configured,
            "effective_default": "grok-4.7"}


def verified_rebase_changes(previous: dict, selected: dict) -> list[str]:
    """Prove no reviewed overlay preimage changed in the accepted predecessor.

    Every non-overlay change is inherited from the selected sealed generation.
    An overlap requires original-owner review, never blind overlay replacement.
    """
    old_files = previous.get("files") or {}
    new_files = selected.get("files") or {}
    if set(old_files) != set(new_files):
        raise ValueError("native_rebase_release_closure_changed")
    for rel in OVERLAYS:
        if old_files[rel] != new_files[rel]:
            raise ValueError("native_rebase_reviewed_overlay_preimage_changed")
    return sorted(rel for rel in new_files if old_files[rel] != new_files[rel])


def qualify(store: Path, release_stage: Path | None = None):
    store = store.resolve(strict=True)
    before = (store/'CURRENT.json').read_bytes()
    selected = generation.current(store)
    if selected is None or selected['generation'] != BASE:
        raise ValueError('selected native generation differs from pinned source')
    policy = verify_incumbent_grok_policy(store)
    base_root, original = generation.verify(store, BASE)
    _, previous = generation.verify(store, ORIGINAL_REVIEWED_BASE)
    inherited_changes = verified_rebase_changes(previous, original)
    overlay_names = {'ext/'+p.name for p in (HERE/'overlay').iterdir() if p.is_file()}
    if overlay_names != OVERLAYS:
        raise ValueError('overlay file set is not reviewed')
    if release_stage is not None:
        release_stage = release_stage.absolute()
        # This task can prepare source under the approved workspaces root only.
        if (release_stage.parent.resolve(strict=True) != HERE.parents[3].resolve(strict=True)
                or release_stage.exists() or release_stage.is_symlink()):
            raise ValueError('release stage must be a fresh sibling workspace path')
    with tempfile.TemporaryDirectory(prefix='grok47-native-qualification-') as temp:
        temp = Path(temp).resolve(strict=True)
        source, stable_ext = temp/'source', temp/'fake-owner'/'ext'
        (source/'ext').mkdir(parents=True)
        stable_ext.mkdir(parents=True)
        new_hashes = {}
        changed = []
        for rel, original_sha in original['files'].items():
            old = (base_root/rel).read_bytes()
            if sha(old) != original_sha:
                raise ValueError('source preimage hash mismatch '+rel)
            raw = (HERE/'overlay'/Path(rel).name).read_bytes() if rel in OVERLAYS else old
            if rel in OVERLAYS:
                if raw == old:
                    raise ValueError('overlay did not change '+rel)
                changed.append(rel)
            target = source/rel
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(raw)
            new_hashes[rel] = sha(raw)
        manifest = temp/'manifest.json'
        manifest.write_text(json.dumps(new_hashes, sort_keys=True))
        # Exercise a REAL incumbent -> successor CAS transition, not only a
        # first selection into an empty fake store.  Both generations are
        # published into an isolated scratch owner, never the live M2 pointer.
        previous_source = temp/'previous-source'
        for rel in original['files']:
            target = previous_source/rel
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes((base_root/rel).read_bytes())
        prior = generation.publish(previous_source, stable_ext, original['files'])
        scratch_store = stable_ext.parent/'native-code-releases'
        prior_pointer = generation.select(scratch_store, prior.name, None)
        if prior_pointer['sequence'] != 1:
            raise ValueError('isolated prior selection mismatch')
        issued = generation.publish(source, stable_ext, new_hashes)
        root, qualified = generation.verify(scratch_store, issued.name)
        if root != issued or qualified['files'] != new_hashes:
            raise ValueError('qualification manifest mismatch')
        pointed = generation.select(scratch_store, issued.name, prior.name)
        if (pointed['generation'] != issued.name or pointed['sequence'] != 2
                or pointed['previous'] != prior.name):
            raise ValueError('isolated CAS transition mismatch')
        try:
            generation.select(scratch_store, prior.name, prior.name)
        except ValueError as exc:
            if 'compare-and-swap refused' not in str(exc):
                raise
        else:
            raise ValueError('stale original-source CAS unexpectedly accepted')
        if generation.current(scratch_store) != pointed:
            raise ValueError('stale CAS affected qualified selection')
        # Real import from the complete 85-file published clone. No worker start.
        code = ("import native_remote, remote_sub_exec; "
                "cmd=native_remote.command('grok','grok-4.7','offline-probe','/tmp',validated=True); "
                "assert cmd[cmd.index('-m')+1]=='grok-4.7'; "
                "assert native_remote.MODELS['grok']=={'grok-4.6','grok-4.7'}; "
                "print('NATIVE_IMPORT_GROK47_PASS')")
        probe = subprocess.run([sys.executable,'-c',code], cwd=temp, timeout=10,
            env={'PATH':os.environ.get('PATH',''),
                 'PYTHONPATH':str(root/'ext'), 'PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True, text=True)
        if probe.returncode != 0 or probe.stdout.strip() != 'NATIVE_IMPORT_GROK47_PASS':
            raise ValueError('isolated native import failed: '+probe.stderr[-700:])
        result = {'state':'QUALIFIED_ISOLATED_ONLY', 'base_generation':BASE,
                  'original_reviewed_base':ORIGINAL_REVIEWED_BASE,
                  'inherited_accepted_release_changes':inherited_changes,
                  'offline_executor_import_verified':True,
                  'files_verified':len(new_hashes), 'overlaid_files':changed,
                  'code_manifest_sha256':sha(generation.canonical(new_hashes)),
                  'isolated_publish_verified':True,
                  'isolated_select_verified':True,
                  'isolated_stale_cas_refused':True,
                  'incumbent_grok_policy':policy}
        if release_stage is not None:
            # Stage reviewed bytes only. The installed publisher and pointer are untouched.
            pending = Path(tempfile.mkdtemp(prefix='.grok47-pending-', dir=release_stage.parent))
            try:
                shutil.copytree(source, pending/'source')
                shutil.copy2(manifest, pending/'manifest.json')
                (pending/'qualification.json').write_text(json.dumps(result, sort_keys=True)+'\n')
                for rel, wanted in new_hashes.items():
                    if sha((pending/'source'/rel).read_bytes()) != wanted:
                        raise ValueError('copied staged file digest mismatch '+rel)
                os.rename(pending, release_stage)
            finally:
                if pending.exists():
                    shutil.rmtree(pending)
            result['release_stage'] = str(release_stage)
    if (store/'CURRENT.json').read_bytes() != before:
        raise ValueError('live selection changed during qualification')
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-store', type=Path, required=True)
    parser.add_argument('--release-stage', type=Path, default=None,
                        help='optional fresh sibling workspace for owner-run publication')
    parser.add_argument('--policy-preflight-only', action='store_true',
                        help='read only the incumbent Grok model-default policy')
    args=parser.parse_args()
    if args.policy_preflight_only:
        if args.release_stage is not None:
            parser.error('--policy-preflight-only cannot stage source')
        print(json.dumps(verify_incumbent_grok_policy(args.installed_store), sort_keys=True))
    else:
        print(json.dumps(qualify(args.installed_store, args.release_stage), sort_keys=True))
