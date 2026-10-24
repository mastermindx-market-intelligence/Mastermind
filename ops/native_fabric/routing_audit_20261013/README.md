# Native routing audit — source-only integration input

This is not an installer or a new router. Read `research/FABRIC_ROUTING_DEEP_AUDIT_2026_10_13.md` from the repository root for the findings, exact evidence, denied-action boundaries and release sequence.

`manifest.json` binds the captured original files and candidate outputs. The two unified patches target the incumbent kit's `ext/` directory. Changed preimages require current-owner reconciliation, not a forced application. Preserve the active #1365/#1441/#1391 source owners and all existing platform refusals.

The captured source reproduced 30 failing and 20 passing checks. The isolated candidate produced **49 passing and one failing** check; the remaining GLM test has the disclosed disabled-provider fixture. Broader regression has not been qualified. The exact reproducer remains an inert `.py.txt` artifact; it is not automatically collected by repository CI and no green CI status is inferred from its presence.

No live source, provider, quota, account, credential, lease or worker was modified. Independent review, full regression, integrated source acceptance, coordinated broker/client installation and original-parent proof remain required. **DRAFT / HOLD / NOT PRODUCTION COMPLETE.**
