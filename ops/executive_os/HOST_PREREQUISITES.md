# Executive OS macOS host prerequisites

The installer deliberately has no ambient Python fallback. Before installation,
an administrator must provision a dedicated Python 3.12 runtime and pass both
its executable and runtime root explicitly. The accepted runtime must:

- be signed by the explicitly supplied TeamIdentifier and pass
  `codesign --verify --deep --strict`;
- contain the executable below the supplied runtime root;
- be entirely root-owned, non-symlinked at both entry paths, free of filesystem
  ACLs, and not writable by group or other; any internal runtime symlink must
  resolve back inside the pinned runtime root;
- run with `-I -S -B` and provide the standard-library modules checked by
  `install.sh`; no site-packages or PyYAML dependency is used.

A Homebrew, Conda, or user-owned Python tree does not meet this boundary. The
installer does not copy or re-sign an ambient runtime because that would turn a
mutable, pre-check object into production execution authority.

After running `bootstrap-host.sh` and provisioning the dedicated worker
`auth.json`, install with explicit immutable inputs:

```sh
/bin/bash ops/executive_os/install.sh \
  --source-repo /absolute/path/to/clean/Mastermind \
  --expected-sha 0123456789abcdef0123456789abcdef01234567 \
  --operator-user operator_account \
  --python-runtime-root '/Library/Application Support/MastermindExecutive/python/3.12' \
  --python-binary '/Library/Application Support/MastermindExecutive/python/3.12/bin/python3.12' \
  --python-team-identifier REVIEWED_TEAM_IDENTIFIER
```

Installation leaves both LaunchDaemons disabled and stopped. The printed
`acceptance.sh` command performs the first start, per-PID canary quarantine,
worker-principal live probe, SIGHUP activation, fault injection, cleanup,
restore drill, and no-public-listener proof.
