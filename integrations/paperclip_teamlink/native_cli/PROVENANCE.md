# Native T3 transport dependency

Upstream: `https://github.com/pingdotgg/t3code`, MIT license (included).
Pinned source: `0770446869d247a8b28c27d7ed93f47f8ff0c1e4`.

`t3-native.patch` is the completed `web-t3-cli-adapter-20261109-a1` native CLI
candidate, adopted without changing its bytes. SHA-256:
`6ce1853635819631d35353c5e6c2f4596931d3d57493d396d82e5b50901ccb0c`.
Original native coordinator: `mcp:5b3b360e-1842-4b27-b510-e38b9546941b`.
The coordinator completed its task before this adoption. Its worktree is not
modified or used as the installed runtime.

The patch adds an allowlisted `thread native` command and `thread native-catalog`.
It reuses the native CLI's `withThreadTools` / EnvironmentAuth session issuance
and revocation. It does not borrow an agent's authorization environment, install
an authentication service, change the running T3 server, or retry native calls.
Provider selection remains restricted to `capacity_fabric`.

The Paperclip port exposes only environment/project/thread observations and
`t3_thread_send` in queue mode; the wider operator CLI does not enlarge the
Paperclip tool surface. The port discovers actual live schemas and uses the
existing Mastermind `integrations/session_bridge/t3_native_client.py`.

Build in an isolated checkout at the pinned source, apply the exact patch, use
the frozen upstream dependency lock, run the three affected test files, and run
`vp pack --out-dir <fresh-build-dir>` in `apps/server`. Then use
`package_runtime.py --source <checkout> --built <fresh-build-dir> --output <fresh-runtime-dir>`.
The packager copies the installed lockfile-resolved external dependency graph
with relative internal symlinks. It records dependency provenance and includes
the upstream license. It does not require the build worktree at runtime.

Install only from the merged Mastermind source receipt. Keep the native bundle
under an immutable release directory and configure the plugin's exact absolute
path. Never overwrite `/Applications/T3 Code (Beta).app` or restart user sessions.
