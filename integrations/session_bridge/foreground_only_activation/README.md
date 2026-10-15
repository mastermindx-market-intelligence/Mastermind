# Ordinary foreground-only activation correction

A global ordinary arm could select an older open root before the intended request and could continue its root after the foreground request returned. A timing-only arm/submit/disarm sequence could not cover restart or the post-Job-creation crash gap.

The existing arm transaction now persists `coo_foreground_only`. That mode disables autonomous root selection and background ticks, requires the current original request for the physical cycle and admission mutations, and carries its callback through the original Operator owner to the authenticated Unix/TLS write boundary. It introduces no new dispatcher, lifecycle, grant or serialized authority. Default operation stays compatible.

Recovery retains existing turn collection, sealed-result settlement and cancellation. In foreground-only mode it quarantines a recovery that would begin an unacknowledged first turn or resume a dead session into a new turn. It also refuses a missing foreground source before a new claim. A restart cannot silently fall back to the legacy ordinary launch path.

Mixed startup accepts a qualified primary canary and applies it only to that primary. Each Fabric Attempt still requires its own observational admission; a primary startup receipt cannot qualify the Fabric owner.

`SOURCE_QUALIFICATION.json` binds exact reviewed source and test evidence. The 387-check combined suite preceded the final restart correction; 52 affected restart/arm/operator checks and a factory propagation check qualify the final correction. Six Unix compatibility checks are separate. Counts overlap and are not added. All checks are inert; none is provider, credential, installation or native same-parent execution proof.

Release uses the existing PR1391 observer and installation owner. Actual admitted provider/realm/binary, source-owned production factory, enabled reviewed profile, physical host/process/collection/cancellation composition and authenticated original-parent consumption remain required. The fixed proof operation remains NOT_SUBMITTED. Original uncertain effects and refused operations remain unchanged.
