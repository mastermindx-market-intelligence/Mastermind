"""Review-bound archive path limit; no runtime identity or permission change.

Exact source review binds only _safe_path's 500-character relative member-path
bound. Other literals/identities remain visible to D8; changed/duplicated AST
anchors receive no suppression. Pins are frozen review data, never learned by CI.
Independent root review receipt SHA256:
8515f05136efc1dda95d5cfa8f3077f1e52ec6d88d5096a1dda8dbd5ab3424cc.
"""

REVIEWED_ANCHORS = {
    "_safe_path": {
        "node_type": "FunctionDef",
        "ast_sha256": "e8761e26fb7070fd0b98e23a423fd9feb73c36ecdde2fbdbadd96cc5e66beaac",
        "sites": ((('body', 0, 'test', 'values', 2, 'comparators', 0), 'int', 500, '500'),),
    },
}
