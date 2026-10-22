# Grok 4.7 Fabric model compatibility candidate

Source basis: installed native generation `0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f` on M2, inspected October 21/22 2026. The generated overlay is a non-installed candidate; it is NOT evidence of a production runtime switch.

* Picker and new generic ledger default: `grok-4.7`.
* Keep both `grok-4.6` and `grok-4.7` valid for new and historical receipts, executor validation, usage normalization and operator grant binding. Exact prior-operation reconciliation files remain bound to the original 4.6 records.
* Preserve the existing separate Cursor `cursor-grok-4.6-high` route: it is not Grok Build 4.7, and any fallback to it is a changed model.
* Do not change live leases, service, authentication, active generations, workers, or host placement.
* The four online Ubuntu hosts advertise 4.7 in `grok models`, but this command also said `You are not authenticated`; a successful paid authenticated Grok 4.7 worker return has **not** been established.

`overlay/` is intentionally assembled from the installed exact generation, because `ops/native_fabric/quota_continuity/source` contains earlier baseline preimages, not the complete current installed release. Test script `test_model_selection.py` validates the model-selector and explicit CLI contract. The exact source closure, manifest hashes, actual controlled native publish/select via incumbent generation owner, host bootstrap and authenticated end-to-end return remain mandatory to finish rollout.
