This is a test-only snapshot of the independently reviewed Macro `engine/provider_capacity_v2.py` (SHA256 `946537a8abf54715d5ba98d21ada007bb535f1c12a45ccb69915eb5db19ed9ab`). It makes the Mastermind test suite hermetic. Production never imports this file; it loads the sealed Macro release through the existing fixed-path custody checks.

Cross-repository qualification uses `MASTERMIND_TEST_MACRO_SOURCE` pointing to the actual Macro checkout; the test checks the same source digest. Changes to the producer require an explicitly reviewed source update, not an automatic fixture refresh.
