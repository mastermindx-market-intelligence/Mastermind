# Native transport source fixtures

`provenance.json` identifies each complete, unmodified source file by repository,
commit, Git blob, SHA-256 and byte length. Hermes uses
`1c0cd667746d3395fe9e1b6c74f8f85952486f18`; HTTPX 0.28.1 uses
`26d48e0634e6ee9cdc0533996db289ce4b430177`. MIT notices are retained separately
in `HERMES_LICENSE` and `HTTPX_LICENSE`.

The native transport tests execute selected exact AST definitions and the real
caller import from these files under their original module globals and source
paths. SDK bypass and header helpers run as complete modules. Dependencies not
under examination are declared fixtures in the test. HTTPX executes from the
actual installed, full-source-qualified package; its archive provides a durable
comparison and license record. No donor code or test fixture is a provider,
host-service, identity, account, or installed acceptance receipt.
