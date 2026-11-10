# CI source review proof

This is the human review record for exact HTTP status sites, the Group purpose textarea's character limit, and the installed Control entrypoint. The numbers below are source coordinates, protocol statuses and a UI input limit. They are not host account identities. The production source and its exact static identity records remain under the unchanged canonical guards.

Original JSON SHA256: `bfa66541680a8abbd1a02936f192ddc7f40d15ee530e892db77638aa76191257` (4043 bytes). The original bytes are retained verbatim in the following fenced block; the Markdown report has its own Git identity.

```json
{
  "service": {
    "preimage_ref": "108e84da3f1c9d18ca756963d291454030d59b49",
    "before_source_sha256": "af0a97de9bfc503db756626d0eacf65876848473cfb2230d8fbe478c9bb5c1cc",
    "after_source_sha256": "3c98ce090d9d147385edd7300b56c0eb58e88610f8018947b264a08ceae85638",
    "after_method_ast_sha256": "1aadcefa715c43cef131a7bccc70ed6caa1951af73616480f782c094a7fd4db2",
    "protected_subtree_ast_sha256": "70820944367157cfa6d655c36fcf89c7e63242aca01b761f9176d75397418962",
    "protected_subtree_nodes": 136,
    "company_method_ast_unchanged": true,
    "sites": [
      [
        [
          "body",
          3,
          "body",
          60,
          "body",
          3,
          "orelse",
          0,
          "body",
          2,
          "body",
          0,
          "value",
          "args",
          1
        ],
        "int",
        403,
        "403"
      ],
      [
        [
          "body",
          3,
          "body",
          60,
          "body",
          3,
          "orelse",
          0,
          "body",
          2,
          "orelse",
          0,
          "body",
          4,
          "body",
          0,
          "value",
          "args",
          1
        ],
        "int",
        403,
        "403"
      ],
      [
        [
          "body",
          3,
          "body",
          60,
          "body",
          3,
          "orelse",
          0,
          "body",
          2,
          "orelse",
          0,
          "handlers",
          0,
          "body",
          0,
          "value",
          "args",
          1
        ],
        "int",
        503,
        "503"
      ]
    ],
    "status_positions": [
      [
        6059,
        66,
        69,
        "int"
      ],
      [
        6072,
        74,
        77,
        "int"
      ],
      [
        6074,
        75,
        78,
        "int"
      ]
    ]
  },
  "app/mastermind_os/src-tauri/src/auth.rs": {
    "sha256": "e47ac442aff8fec4ad9beb1c8b0f726c981936165e65b38c5bf430f5bb6226cc",
    "sites": [
      [
        3958,
        68,
        71,
        "int",
        "503"
      ],
      [
        3963,
        69,
        72,
        "int",
        "503"
      ],
      [
        3967,
        67,
        70,
        "int",
        "503"
      ]
    ]
  },
  "integrations/mastermind_workspace_app/app.py": {
    "sha256": "4ecb26e79fe43d48db25b0b61cfa0af4926b82df1a0e528ac6a56b701208cf30",
    "sites": [
      [
        934,
        71,
        74,
        "int",
        "400"
      ],
      [
        945,
        71,
        74,
        "int",
        "403"
      ],
      [
        953,
        71,
        74,
        "int",
        "400"
      ],
      [
        959,
        79,
        82,
        "int",
        "400"
      ],
      [
        968,
        71,
        74,
        "int",
        "400"
      ],
      [
        978,
        71,
        74,
        "int",
        "403"
      ],
      [
        983,
        76,
        79,
        "int",
        "503"
      ],
      [
        989,
        71,
        74,
        "int",
        "403"
      ]
    ]
  },
  "group_input_limit": {
    "path": "app/mastermind_os/src/team/NewGroupPanel.tsx",
    "sha256": "b84219e674c305e9d57571214e9c970c63508b774573b5d284d0bf8be869459d",
    "site": [
      187,
      25,
      28,
      "int",
      "600"
    ],
    "context": [
      "          <div className=\"mm-field\">",
      "            <label htmlFor={purposeId}>{t.purposeLabel}</label>",
      "            <textarea",
      "              id={purposeId}",
      "              value={purpose}",
      "              rows={2}",
      "              maxLength={600}",
      "              onChange={(event) => setPurpose(event.target.value)}",
      "              aria-describedby={`${purposeId}-hint`}"
    ]
  },
  "d7": {
    "source_sha256": "121bd6987e67d015a0aa2ffdcd8d95693188d7440f9f1a62f3ee3b2cde4e01ba",
    "same_anchor_ast_sha256": "060525ac61b01452e7a84397f0e68ab4be9c0a05f6dac560113bce8180adc819"
  }
}
```
