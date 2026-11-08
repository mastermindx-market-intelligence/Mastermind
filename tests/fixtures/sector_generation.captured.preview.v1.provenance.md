# Native generation fixture provenance

This is the captured Macro preview API response used by Terminal's native consumer qualification. The original response is 179,788 bytes with SHA-256 `3e275fc69d22e990f81261c8a803576a832be9332484c7a99b2dddd165a5d425`; this JSON fixture has one trailing newline and SHA-256 `88afd1917b710a8db2cb14ffa0d0b3283f13ee57725154a17b6b38175c035dac`.

The capture accompanies Macro PR 10780 at `f769c2b879797e0237429dd011a5c6b7e7bc0bc7`, with canonical evidence at https://github.com/mastermindx-market-intelligence/macro/pull/10780#issuecomment-6710410239. It is controlled qualification evidence, not authenticated production acceptance or original historical availability evidence.

The Portfolio tests construct a **new synthetic five-member generation** from the captured core and history: they restore the raw measured-read horizon, omit optional dated/classification context, and add explicit synthetic legacy market and basket sentinels. The companion handoff and action board are synthetic. The resulting generation is published only into the test's temporary directory through the existing Macro publisher. It does not claim to reconstruct the original raw snapshot or its content identity.

All source clocks, numerical return measurements and their qualifications in the captured fixture remain unchanged. Synthetic pointer replacement and legacy-field controls are labelled in the tests. No live data store, selected generation, portfolio, credentials, model, or execution authority is used or changed.
