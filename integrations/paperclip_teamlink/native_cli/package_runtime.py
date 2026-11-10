"""Stage a relocatable native CLI bundle from an already verified T3 build.

Copies installed, lockfile-resolved runtime externals and their dependency graph.
All dependency symlinks point inside the artifact, never into a live worktree.
No package scripts, credentials, server configuration or T3 app files are touched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

PREFIXES = ('@cursor/sdk', 'playwright-core', 'node-pty', 'ffi-rs', '@yuuang/',
            '@ff-labs/', 'transcribe-cpp', '@transcribe-cpp/', 'koffi', '@koromix/',
            '@napi-rs/keyring', '@clerk/electron-passkeys', 'node-gyp-build',
            'node-addon-api', 'bufferutil', 'utf-8-validate')
EXACT = {'@bufbuild/protobuf', '@connectrpc/connect', '@connectrpc/connect-node',
         '@connectrpc/connect-web', '@statsig/js-client', '@statsig/client-core',
         'zod', 'undici', '@fastify/busboy'}


def resolve_package(name, origin):
    for directory in (origin, *origin.parents):
        candidate = directory / 'node_modules' / name
        if (candidate / 'package.json').is_file():
            return candidate.resolve()
    return None


def package(source, built, output):
    if output.exists():
        raise ValueError('output must be a fresh directory')
    if not (built / 'bin.mjs').is_file():
        raise ValueError('verified CLI bundle missing')
    output.mkdir(parents=True)
    for path in built.iterdir():
        if path.is_file() and path.suffix != '.map':
            shutil.copy2(path, output / path.name)
    modules = output / 'node_modules'
    modules.mkdir()
    copied, metadata = {}, []

    def copy_package(origin):
        origin = origin.resolve()
        if origin in copied:
            return copied[origin]
        raw = (origin / 'package.json').read_bytes()
        info = json.loads(raw)
        identity = hashlib.sha256(str(origin).encode() + raw).hexdigest()[:16]
        destination = output / '.runtime-store' / identity
        copied[origin] = destination
        shutil.copytree(origin, destination, symlinks=False,
                        ignore=shutil.ignore_patterns('node_modules', '.git'))
        metadata.append({'name': info['name'], 'version': info.get('version'),
                         'packageJsonSha256': hashlib.sha256(raw).hexdigest(), 'directory': str(destination.relative_to(output))})
        optional = info.get('optionalDependencies', {})
        peers = info.get('peerDependencies', {})
        dependencies = {**peers, **info.get('dependencies', {}), **optional}
        for name in sorted(dependencies):
            resolved = resolve_package(name, origin)
            if resolved is None:
                if name in optional or name in peers:
                    continue
                raise ValueError(f'installed dependency missing: {info["name"]} -> {name}')
            staged = copy_package(resolved)
            link = destination / 'node_modules' / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(os.path.relpath(staged, link.parent), target_is_directory=True)
        return destination

    dependencies = json.loads((source / 'apps/server/package.json').read_text())['dependencies']
    # Match the upstream cli-external-packages.ts selection at the pinned commit.
    roots = [name for name in dependencies if name in EXACT or name.startswith(PREFIXES)]
    for name in sorted(roots):
        origin = resolve_package(name, source / 'apps/server')
        if origin is None:
            raise ValueError(f'installed external missing: {name}')
        target = copy_package(origin)
        link = modules / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
    for path in output.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(output.resolve()):
            raise ValueError('external artifact symlink')
    shutil.copy2(source / 'LICENSE', output / 'LICENSE.t3')
    manifest = {'upstreamCommit': '0770446869d247a8b28c27d7ed93f47f8ff0c1e4',
                'patchSha256': '6ce1853635819631d35353c5e6c2f4596931d3d57493d396d82e5b50901ccb0c',
                'packages': sorted(metadata, key=lambda x: (x['name'], x.get('version') or ''))}
    (output / 'runtime-provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'runtimePackages': len(metadata), 'externalRoots': roots, 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--built', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.source.resolve(), args.built.resolve(), args.output.absolute())))
