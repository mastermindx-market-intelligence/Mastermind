# Frozen Web Sol overlay compatibility fixtures

These are exact public source assets from this repository, retained so shallow CI checkouts can qualify installed-profile upgrades without fetching historical git objects.

- `0.2.0`: `320f586126b7c82c843ef17612f12d40d20a42e0`, `integrations/chairman_surfaces/web_sol_extension/`.
- `0.4.0`: `e6140689976a95e029d499633a3054418d99bd76`, the same source directory, including `continuation_core.js`.

The overlay owner freezes their source commits and SHA-256 digests. Tests synthesize an instance configuration for a fictional binding; no installed configuration, credential, native wrapper, browser state, or conversation data is included here. The fixtures are not a release of the historical native-host protocol and must not be used to replace current surface code wholesale.
