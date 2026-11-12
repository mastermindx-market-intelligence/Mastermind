# Design memory convention

Design memory lives in places the programme already owns. This adds no new store.

1. **In Paper, the file's `00 · AGENT README` page.** This is the first thing every
   designer reads. It holds the scope, the page map, which pages are current, history
   or donor, and the rules for that file. It is updated only by that file's canvas
   writer. If a file has no README page, the lead asks the writer to create one
   before other work.
2. **In the programme's repository, the design manifest.** It is a JSON file that
   binds board codes to Paper root ids, with page, viewport, theme, language,
   `get_jsx` sha256 and review state. Existing examples are the Sector
   `R6_PAPER_MANIFEST_*.json` and the Prophet `TURN2_PAPER_MANIFEST.json` /
   `SECTOR_PAPER_MANIFEST.json`. Keep the same shape for new work.
3. **In the same repository, the design log.** One Markdown file per design
   programme, appended to, never rewritten. It is the continuity record between
   sessions. One entry per material event:

   ```
   ## <UTC timestamp> · <event> · <actor/session>
   - canvas writer: <session or role> for <file / page ids>
   - operation: <stable operation id> · state: APPLIED | EFFECT_UNKNOWN | REFUSED | RECONCILED
   - targets: <node ids>        - screenshots: <paths + sha256>
   - decision / finding: <one or two sentences>
   - next: <the next safe step and who takes it>
   ```

   Events are: writer named, writer handed over, brief issued, direction, canvas
   round, critique, decision, handoff, implementation PR, verification, held target,
   held target released.
4. **Held targets** are listed in both the design log and the manifest, with the
   original operation id and carrier. Nobody retries, recreates, finishes or exports
   a held target. Only the lead who owns its original carrier releases it.
5. **A screenshot of a root that contains a held target carries the hold for that
   region.** Mark such an image in the inventory as "contains held region `<id>`;
   reference for the surrounding board only". Never build, edit or copy from that
   region, and never use the image as a reference pull, skillpack example or critique
   sample. Do not crop, re-export or re-render it to work around the hold.

Account-local chat memory is not design memory. A fresh session must be able to
continue from the README page, the manifest and the log alone.
