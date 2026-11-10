# Qualified T3 dynamic-tool binding source patch

This directory retains a reviewable source candidate for
`chriswong6031-creator/t3code@924ad5d194287441f825b8f2f6054e9539808534`.
It is evidence attached to the existing estate integration carrier. It has not
been published to that fork or installed in T3.

The exact three-file unified patch is stored in
`native-dynamic-tools-bindings.patch.json`. The JSON envelope preserves every
original byte, including ordinary unified-diff context markers, without treating
those data markers as source whitespace violations. The original child manifest
and qualification report are retained byte-for-byte.

To materialize the original patch in a disposable directory:

```python
import hashlib
import json
from pathlib import Path

envelope = json.loads(Path("native-dynamic-tools-bindings.patch.json").read_text())
raw = envelope["unified_diff"].encode("utf-8")
assert hashlib.sha256(raw).hexdigest() == envelope["sha256"]
Path(envelope["original_filename"]).write_bytes(raw)
```

Apply/check against the exact declared native base, using the existing source
owner. `source_manifest.json` records the original preimages and every final
postimage. `QUALIFICATION.md` records the failing-before/passing-after real typed
wire test, official protocol compatibility, generator scope, commands and limits.

The patch restores an input that the current typed encoder silently removes.
It does not advertise a production dispatch tool or confer native requester
authority. The existing original-call connection owner and Control host
enrollment must be joined and qualified before native-origin dispatch is usable.
