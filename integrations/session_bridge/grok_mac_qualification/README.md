# Explicit Mac Grok qualification

This reviewed helper adds a one-worker qualification route to the existing adapter for already-registered `mb` or `m1`. It temporarily removes only the automatic-selection qualification hold; it preserves provider, physical role, mode, resource, source, account and lease checks. It changes no registration or authority. M2 is excluded.

The bootstrap CLI addition can install only the requested Grok CLI, preserving other tools and all authentication. On-host qualification still requires compatible runtime and policy, provider authentication and an actual accepted worker result.

Paid review `fabric-grok-mac-qualification-review-01a11e90-v1` returned 1513 bytes, SHA256 `307cef955c366de88fe3f69b7d82816fb221709f2fbd83d893765838bab1cb9c`, consumed and accepted once by the original parent. Fourteen isolated contract checks passed. `test_qualification.py` is an installed-runtime qualification check requiring the existing M2 dependency closure; it is not a portable repository CI test.

Installed 2026-10-12T04:09:37Z: adapter `cbd46bd88a4e5d545c77010bfb9eb1997399fe4f5cc67596210e849858eddd99`; helper `d2a1c8f589a9758f94e36f947a91a0a4b731c5aa69694ac7258691a85873166a`; bootstrap `14a859e644268f6d92ff19c6899955b57fa67c1a68c085cb33bab3949de6909f`.

First MacBook operation `fabric-grok-mb-native-enrollment-review-01a11e90-v1` returned `native_remote_host_refused`, rc78 before provider start. Original 27-byte result SHA256 `7d3e46b6e2af92c7ace100a1419a3dbefb3ac9bcd9480a6cdcf405ee0ba162c4`; consumed once, not accepted or replayed. M1 Grok CLI installation returned rc0; authentication and worker qualification remain unproven. Neither Mac is advertised as accepted Grok capacity.
