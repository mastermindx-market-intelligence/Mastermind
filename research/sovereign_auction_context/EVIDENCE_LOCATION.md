# Consumer verification evidence owner

Executable loopback/browser test harnesses and their fixtures now live under [tests/fixtures/sovereign_auction_context](../../tests/fixtures/sovereign_auction_context/). Research interpretation and architecture remain here. This uses the existing test/evidence boundary; the identity guard and its registry are unchanged, and the production reader remains guarded.

All45 moved files were verified against source55198ba62ff47d2a371397567418cb43fd98892c and moved byte-for-byte. Raw historical receipts, screenshots, preimages and patches retain their original content and embedded historical paths. Consult the [relocation receipt](../../tests/fixtures/sovereign_auction_context/verification/identity_scope/RELOCATION_RECEIPT.json) for exact old/new mappings. Earlier files also remain in reachable Git history.

The current [source manifest](../../tests/fixtures/sovereign_auction_context/VERIFIED_SOURCE_MANIFEST.json) and [browser evidence](../../tests/fixtures/sovereign_auction_context/verification/browser_final/) are owned by that test tree. The prior55198 source manifest is retained separately in identity_scope. Reverification after relocation and the standard HTTPS protocol-constant repair will update current acceptance, without rewriting the historical receipts.
