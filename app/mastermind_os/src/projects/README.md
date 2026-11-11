# Projects presentation

`Projects` consumes `OfficeProjection["programs"]`; it performs no acquisition,
authentication, URL/history changes, commands, or persistence. The existing
Programs decoder and selection owner remain authoritative. The shared application
shell now exposes this component as Projects, preserving the nine legacy destinations.

Design: Mastermind OS Paper file `01M3NRCX55B452A12819WNE1RH`, snapshot
`2ccdbcd528a0990e8be40376b658f19d8059b50407d4f1ddc24b666a5468114d`,
AT02 `M4J-0` and AT02M `N28-0`. Desktop and mobile JSX structure and screenshots
were inspected. The composition uses the supplied-project list, optional exact
selected-project feature, search, restrained surfaces and responsive typography.
The existing decorative Atelier asset is reused. No illustrative identities,
owners, statuses, counts, recent activity or project descriptions are copied.

## Integration

- Pass only the Programs value produced by `projectOffice`, with its own owner
  provenance. App uses the qualified Programs observation companion from one fixed
  acquisition. Legacy hosts with only a bare Programs value remain unqualified
  here while their existing Programs route stays reachable. A qualified Mission
  does not qualify the Programs collection.
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

New-project commands require their existing canonical command owner. Archive
browsing uses the explicit canonical declaration described below; free-text
project state never supplies it. Project owners are not supplied by
`ProgramCard` and remain visibly unknown. Project detail, Work, sessions, journal,
Inbox and authenticated producer qualification remain separate
integration work. This component does not claim route parity, native installation,
browser visual acceptance or production completeness.

App routes only CURRENT Project selections through its existing exact URL/root owner.
It omits historical navigation until an explicit retained-history destination is
available. Navigation back to Projects preserves the selected pair and causes no
extra acquisition; choosing a new pair requalifies its collection before Mission.

## Canonical archive browsing

`archive/ProjectArchiveBrowser` joins the existing CURRENT Programs projection
with the fixed `GET /workspace/projects/archive/current` read. The integrating
App supplies its actual workspace/auth scope key, stable host reader, source
generation and permission getter. The returned catalogue digest must equal the
Programs collection's qualified document reference. Each exact checked work-ref
vector must be the next bounded sorted window from that same collection; the
controller rejects overlapping/skipped pages and mixed Macro revisions. A
different publication (even with identical document bytes), source generation
or interrupted/revoked read clears or masks all accumulated archive pages.

Macro's optional `archive` declaration is the sole archive fact. The installed
reader executes the actual captured `agentos_project_archive.py` helper and
parser against fixed canonical WS records within its existing source seal.
A checked record omitted from the archive rows has no archive declaration; an
unobserved record stays unknown. Neither means Running. The two UI modes are
Projects and Archived projects. Counts describe returned archive rows, checked
records and supplied catalogue records; company total remains unknown.

Opening an archive inspects its returned title, objective, archive date (DAY
precision), actor, reason and exact source details in an explicit read-only
context. Back returns to the same loaded collection/search. It never invokes
a current Mission or guesses a root. Ordinary Projects may retain the App's
existing qualified rootless `onOpenProject` read callback; its optional Mission
callback requires the exact resolved work/root pair. Archive status supplies
no mutation, SEND, restore or continuation authority.

The App remains the sole composition owner and passes its existing guarded New
project action as `newProjectControl` to the browser/header; the view creates no
command or grant. It preserves catalogue navigation. A legacy host without the new reader
keeps its existing Projects view; it cannot fabricate archive evidence. This
source contract does not establish installed, authenticated or rendered parity.

The first read remains rootless with no query. Explicit continuation uses only
`after_work_ref` and `catalogue_digest` on that same fixed GET. These are selectors,
not authority: the existing owner requalifies the principal and complete current
catalogue, checks the exact digest and anchor membership, and reads at most128
next records through the same sealed helper. The unchanged v1 response decoder
validates each page. The browser traverses only on Check more supplied projects;
there is no auto traversal, second cursor store or pagination registry. Every
supplied record up to the existing500-record catalogue bound is reachable, while
company total remains unknown even after that supplied collection is exhausted.

Explicit archive Open focuses the inspector heading; Back restores that exact
record's Open button, or the archive heading if it is no longer shown. Explicit
Projects/Archived mode navigation focuses the destination heading. Passive reads
never create a focus request. List reasons have a two-line visual preview; the
inspector retains the full exact source reason.
