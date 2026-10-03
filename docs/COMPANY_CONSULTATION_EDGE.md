# Company consultation edge

The Company SDK is a separate product runtime. The sealed Executive control service stays SDK-free and owns the optional Company Unix listener in its existing launchd service. The listener is absent unless its exact `company_consultation` configuration is armed.

The capability registry has one fixed Company stdio grant and a distinct `operator.appserver.interactive.company-mcp.v1` profile. **That profile is disabled.** Its installed native admission and answer-consumption qualification are still outstanding; the ordinary interactive profile remains MCP-free. Building this edge does not prove live consultation, delivery, or original-parent consumption.

## Provisioning owner

After the exact reviewed release is installed and Company intake is disabled, root runs the installed release's `ops/executive_os/company_mcp_edge.py provision` with the signed framework Python and `-I -S -B`. The entry accepts no path, package, interpreter, index, socket, or UID selectors. It derives the release from its installed location, verifies the complete release manifest, invokes the existing Python runtime owner's `--verify-only`, and validates the installed control configuration before any package mutation.

The runtime is built at its final release-specific path under `/Library/Application Support/MastermindExecutive/mcp-runtimes/`. A root-only provision lock excludes concurrent builders; `.incomplete` marks an unpublished build. The existing product lock `requirements/executive-mcp-macos-arm64-py312.lock` is the only dependency source. The signed framework's bundled pip wheel runs with host pip configuration disabled, binary wheels only, required hashes, no cache and no bytecode compilation. Pip is not installed into the final runtime.

The complete read-only inventory and base/source evidence are sealed in `.company-mcp-runtime.json`. Startup hooks and bytecode caches are refused before the SDK interpreter is executed. A root-owned public configuration is published last at `config/company-consultation-edge.json`; it contains only fixed identity/digest fields, no credentials. The fixed stdio bootstrap verifies it, verifies the installed entry, and enters a stdlib verifier. That verifier checks the source, interpreter and complete SDK tree before executing the immutable SDK Python with `-I -B`.

## Interrupted provisioning

`verify` is read-only. A completed runtime with a valid receipt but no public configuration can be reverified by `provision`, which publishes the missing configuration without rebuilding packages. Failed builds are not silently reused or deleted. The explicit `recover-incomplete` command requires the same installed release, disabled Company intake, absent public configuration and exclusive provision lock; it preserves the marked partial tree (or the exact empty directory left before marker creation) under the fixed `mcp-runtime-archive` root and returns its archive path. `provision` can then perform one fresh build. A published or mismatched binding refuses this recovery path and requires reconciliation through its actual installed owner.

No provider session, CEO intake, trade authority, scheduler, extra service, or remote credential is created by this provisioner.
