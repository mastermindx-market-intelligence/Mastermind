# Projects presentation

`Projects` consumes `OfficeProjection["programs"]`; it performs no acquisition,
authentication, URL/history changes, commands, or persistence. The existing
Programs decoder and selection owner remain authoritative. The shared application
shell has not been wired to this component.

Design: Mastermind OS Paper file `01M3NRCX55B452A12819WNE1RH`, snapshot
`2ccdbcd528a0990e8be40376b658f19d8059b50407d4f1ddc24b666a5468114d`,
AT02 `M4J-0` and AT02M `N28-0`. Desktop and mobile JSX structure and screenshots
were inspected. The composition uses the supplied-project list, optional exact
selected-project feature, search, restrained surfaces and responsive typography.
The existing decorative Atelier asset is reused. No illustrative identities,
owners, statuses, counts, recent activity or project descriptions are copied.

## Integration

- Pass only the Programs value produced by `projectOffice`, with its own owner
  provenance. The current host drops the Programs observation envelope; it must
  remain UNKNOWN/UNAVAILABLE until that producer seam is qualified. A qualified
  Mission does not qualify the Programs collection.
- `selectedProject` is an optional exact `{workRef, rootJobId}` supplied by the
  existing selection owner. It features only the matching resolved row; the
  component never chooses the first, most recent or similarly titled project.
- `onNavigateMission(selection, mode)` is read navigation, not execution. Route
  `"current"` through the existing canonical selection/deep-link owner. Route
  `"history"` to an explicitly historical inspection surface. If historical
  inspection is unavailable, omit the callback for STALE inputs. Never ignore
  the mode and open historical facts with current semantics.
- Root navigation requires RESOLVED plus one candidate equal to the supplied
  root. Conflicts/unknown roots remain visible but have no navigation action.
- Supplied scope and coverage remain explicit. Search matches supplied titles
  and work references without changing source order or inventing completeness.
- CURRENT requires source reference, revision and observed time. STALE keeps
  retained facts with historical wording. Other states clear all project rows
  and search. WITHHELD also clears source provenance. Duplicate work references
  fail closed rather than being deduplicated.

## Outstanding product integration

New-project commands and Active/Archived filters need canonical owner semantics;
they are not guessed from free-text state. Project owners are not supplied by
`ProgramCard` and remain visibly unknown. Project detail, Work, sessions, journal,
Inbox, shell routing and authenticated producer qualification remain separate
integration work. This component does not claim route parity, native installation,
browser visual acceptance or production completeness.
