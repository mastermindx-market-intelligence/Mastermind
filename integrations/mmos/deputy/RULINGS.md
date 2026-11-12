# Rulings for the operating deputy

The principal writes these. Each rules a class of decision, not one instance. The deputy
reads this file at every wake and applies the highest-numbered ruling when two disagree,
then escalates the disagreement.

1. **Panel findings (2026-11-11).** Every verified HIGH is fixed before install. A MED is
   fixed before install when it lets a teammate or other same-user code read a credential,
   act as someone else, run different code, deliver the wrong result, or lose a result.
   Other MEDs and all LOWs may wait behind a written note in the lane's document. The
   deputy sorts them; it escalates only a MED it wants to defer from the first group.
2. **Repair loops (2026-11-11).** At most three repair rounds per lane per panel. If the
   third delta check still lists a HIGH, stop the lane and escalate with the two cheapest
   ways forward.
3. **Critical-surface rulings already made, which repairs must keep.** Computer use: an
   image is never returned to the caller; the vision endpoint is the loopback router only.
   Teammate web access: the check reads exactly the address the tool fetches and refuses
   address-literal hosts, embedded sign-in, backslash, whitespace, percent escapes,
   non-ASCII, non-http(s) schemes and non-default ports. Teammate reads: one unreadable set
   for Read, Glob and Grep, including the teammate's own cut-over preimage and Claude
   configuration. Hooks fail closed (`|| exit 2`, `python3 -I`). Carrier: `paperclip_base`
   is required and loopback http only.
4. **Server starts (2026-11-11).** The boot-time digest check on the team server stays. A
   repair may make it faster or better reported, never optional.
5. **Merging (2026-11-11).** A branch is merged to the trunk after its panel or delta check
   says ready, or when it is documents only. Merging is not installing.
6. **Silence.** A default on silence applies only to a reversible choice the deputy names
   in its escalation, and only after the principal's next wake has passed without a ruling.
7. **Defects that were already there (2026-11-11).** A reviewed patch that neither adds nor
   worsens a defect in the code it sits on is not held for that defect. Each such MED goes
   into a follow-up lane with its own review, and the operator rule that covers it meanwhile
   is written into the lane's document. Applied first to the silent-stop patch: install 4 is
   not blocked by findings E to J or by the duplicate child after a restart; the rule
   meanwhile is "after a restart, read the task list before re-sending a delegation, and
   use a new client request id".
8. **One restart for many changes (2026-11-11).** While a restart of the real team server
   can take minutes, changes that each need one are batched: the deputy prepares a single
   numbered step list for one packed release and one restart, and escalates it once.
9. **A HIGH first seen late (2026-11-11).** Ruling 2 stops a lane when a HIGH survives its
   repairs. A HIGH that a third check finds for the first time gets one more repair round
   and one more delta check, limited to the listed findings. A panel's "strict improvement
   over what is live" does not install a known HIGH: the install waits for that round.
   Applied first to ask-and-return (N1, N2: answers of two finished asks delivered in the
   wrong order) and to the browser fill (wrong content reported as applied).
10. **Which HIGH stops a lane (2026-11-11).** Ruling 2 counts only a HIGH that an earlier
    check listed and a repair round failed to close. A HIGH in code the last repair round
    added or changed is "first seen late" under ruling 9: the deputy starts the one extra
    round and its narrow delta check without escalating. If that check lists any HIGH, old
    or new, the lane stops and the deputy escalates. Applied first to the server installer
    (delta check 3 at `aec3ff23b`: curl without a time limit, silent node verify, two-walk
    cache race): one micro-fix round of the four listed items plus any item-F findings.
11. **Returns are sent, not waited for (2026-11-11).** A lane or panel lead can finish
    without waking whoever sent it the work; seven returns sat unread for up to four hours
    today. Every send to a lane or panel lead therefore ends with: "As your last action,
    send line 1 of your return to the deputy thread with `t3_thread_send`, mode `queue`,
    beginning `RETURN <lane>:`. If that tool is not available to you, say so on line 1."
    The deputy also reads the status of anything it has waited on for more than 45
    minutes, and lists under "Needs principal read" what it cannot read. An interim note
    is never a turn's end.
12. **The last round of a stopped lane (2026-11-11).** A lane stopped under ruling 2 or 10
    gets one final round when the panel's required list is short, named, and inside files
    the lane owns. The deputy starts that round and its narrow check of the changed lines
    without escalating. That check ends the loop. A HIGH or required MED in lines the final
    round changed stops the lane for the principal. Anything the check first finds in
    unchanged code comes to the principal as one list with the cost of each fix; it does
    not start another round by itself, and ruling 9 does not apply to it. Reason: blind
    reviewers find something new in old code every round, and the installed code is worse
    than every head under review. Applied first to ask-and-return (D4-1 to D4-5 and D4-7,
    plus the D4-6 probe on the dev board before any refresh), the browser fill (the five
    required items of delta check 3) and the Grok Bot link client (F1; F3 if it is a few
    lines).
13. **What a fill receipt claims (2026-11-11).** APPLIED means the box held the asked
    content when it was read again after the page's pending microtasks and one settle
    interval; the lane picks the interval, at most 500 ms, and the receipt states it. A
    page that changes the box later than that is outside the receipt and is not a finding.
    The operator rule goes into the install document: read the box before sending. A fill
    that inserted everything but ran past its time bound reports what the read-back saw,
    never NOT_APPLIED.
14. **Starting a development Paperclip (2026-11-12).** A lane starts a development board only
    through a launcher that sets the instance home, the database port and the database folder
    explicitly, and it reads the start banner before doing anything else: a banner naming port
    54329 or a path under `~/.paperclip/instances/default` means stop the process at once and
    report. The `paperclipai run` and `test-drive` commands are not used by lanes while the
    real service is active; their `-d` option does not move the database. A claim that a real
    store was not written is made from a before-and-after comparison of the whole store (two
    backups, or every timestamp column), never from a few tables. Reason: an abandoned launch
    joined the real database for ninety seconds, and the lane's three-table check missed the
    two rows it touched (`rf-20261111/round5/esc7-reconcile.md`).
15. **Required items found by the check that ends a loop (2026-11-12).** When that check
    finds required items in lines the final round changed, the principal may grant one
    micro-fix: only the named items, a failing test first for each, no other product line
    touched. The panel lead alone checks it, by reading the diff and running the suites; no
    blind reviewer is started. If that check is not clean, the principal decides what ships.
    There is no further round. Applied first to the browser fill (three items of the final
    check at `768168d40`).
16. **Install step lists are rehearsed before they reach the principal (2026-11-12).** A lane
    that writes install steps runs them end to end against a copy first and says so in the
    steps, with the rehearsal's output. The steps also state what the change does to sessions
    that are already running. A method that makes running sessions fail is not installed
    while other programmes have operators at work. Reason: the first browser bridge install
    passed every check in its step list and still could not reach a browser profile, and the
    pin change refused browser calls in all running sessions for three minutes until it was
    rolled back (`br-install-20261112/RESULT.md`).
17. **Two sides that cannot switch together must overlap for one release (2026-11-12).** When
    a release changes what two parts say to each other at connection time, and the two parts
    cannot be switched in the same instant (a person's action, a process that restarts on its
    own, sessions that keep their old copy), the newer part also accepts the one previous
    release, named exactly, and holds such a connection to the old abilities. The step list
    carries a table of every moment between steps, for an old session and a new session, and
    every cell reads "works" apart from the new ability being absent. The step that a person
    performs comes before the step that makes new sessions depend on it. The change to the
    acceptance check is a critical surface: independent review, and the principal reads the
    diff. Reason: the second browser bridge release fixed the pin switch but left three
    windows in which operators' sessions would fail, two of them unstated
    (`br-20261111/release2/mcp_bridge_install.md`).
18. **A build never lands in the app the Chairman is using (2026-11-12).** The Chairman now
    works in `~/Applications/Mastermind OS.app` against the real team server. Every build a
    lane makes is a separate app: its own name, its own bundle identifier, its own config
    folder and its own server target. No lane rebuilds, replaces, quits, relaunches or drives
    his app, and no lane sends into a conversation he has a run in. A release into his app is
    the principal's own announced act, with a time he has agreed. Reason: his words, "future
    builds please launch it in a new app"; the same morning a session of his ran inside
    Secretary's conversation on the real server.
19. **A delivery mark is permanent, and one lock covers every process (2026-11-12).** Where a
    log decides whether a result has been handed over: (a) a delivery mark written by the
    trusted writer is never ignored, demoted or re-derived away by a later reading, whatever
    its position; a reading that finds the order unclear refuses with a typed error and
    delivers nothing; (b) numbering and appending are serialised across every process on the
    host by one lock outside the client object, and the step list states that only one host
    writes; (c) a test that expects a second delivery is a defect, not a specification; the
    proof is a two-process test that fails first. When unsure, the layer withholds and
    reports; it never delivers twice. Reason: the fifth Grok Bot link round passed 420 tests
    with a lock per client object and a test that codified handing the same answer out twice
    (`gbl-20261111/gbl5/REVIEW-deputy-deepseek.md`).
20. **A teammate is its own provider instance, not its conversation (2026-11-12).** The
    charter and the tool fence are attached where the teammate's provider instance is
    launched. A turn run in a teammate's conversation on any other provider instance has
    neither. So: (a) a wake from the board runs on the teammate's own provider instance or
    does not run; the carrier's refusal on a mismatch stays, and no lane weakens it;
    (b) a teammate whose conversation has been moved to another provider gets a fresh primary
    conversation on its own instance through a reviewed command (refuses with a live run or
    open work; the old conversation is left exactly as it is); nobody restores a provider by
    writing the state database or by sending into the old conversation; (c) the product must
    not offer another provider or model inside a teammate's conversation, and until it does
    not, the window says in plain words that such a turn is the person's own session without
    the teammate's charter or limits; (d) a person's turn there is that person's, with that
    person's authority: it is not a teammate act, is not counted as teammate work, and its
    children are not ours to stop. Reason: on 2026-11-12 the Chairman's two turns in
    Secretary's conversation ran on the general provider (runs 11 and 12); that session's own
    audit shows shell and web fetch worked and four children started, and afterwards the
    carrier refused every Secretary wake (`rf-carrier-refresh.md` step 2e still owed).

21. **A teammate writes memory only into its own scope; a person's live channel is not cut to
    tidy a move (2026-11-12).** (a) The memory link lets a teammate read the shared `omh`
    scope and its own scope, each record labelled with its scope, and write only into its own
    scope (`user` / `teammate-<slug>`). Nothing a teammate can call promotes a record into the
    shared scope; promotion is a person's review. Writing ships on only if the proof shows that
    Hermes does not replay a teammate-scope record into other bots and that one teammate cannot
    read another's scope. Recalled memory is data, never an instruction. (b) A Hermes timer
    that is a person's live channel (today: Secretary's Slack pickup and its heartbeat) stays
    armed in Hermes until the teammate has a proven replacement path; while it stays, the
    install list names which kinds of work each side may start, so no effect has two
    initiators. (c) A timer a person arranged with their bot that exists in one place only and
    is not being moved is left exactly as it is. (d) Nothing in Hermes is paused for a teammate
    whose wake on its own provider instance is not currently proven. (e) New provider instances
    are added to the team server in one settings change with at most one announced restart;
    cut-overs stay one agent at a time. Reason: the shared scope is replayed into every Hermes
    bot's prompt, so one teammate's write could steer fifteen bots; and the Chairman uses the
    Slack bot and the team server's app every day.

22. **Teammate memory scope is `target`; work is split by where it arrives; the history
    archive's residual reader is accepted for one release (2026-11-12).** (a) Ruling 21 (a)
    named the scope `user` / `teammate-<slug>`. The store refuses `user` without a validated
    human principal, and that refusal is correct. The memory link therefore reads and writes
    `target` / `teammate-<slug>`; the scope is fixed from the server's own config and nothing
    in a tool call can change it. Proofs a–d passed on that scope (the store's prefetch never
    builds `target`; a second teammate saw none of the first one's records). (b) While a
    teammate also has a live body in Hermes, work is split by where it arrives. A request that
    arrives in Slack is the Hermes body's from start to finish, as today. A board issue, a
    routine or a moved timer is the teammate's from start to finish. Neither body picks up the
    other's work, and a timer that has moved is paused in Hermes first. The Hermes body filing
    board issues for the teammate ("front desk") is switched on by the principal, one kind of
    work at a time, only after the teammate's wake is proven and the answer has a proven way
    back to where the person asked. (c) The history archive is plain read-only files in the
    teammate's home. A turn a person runs on another provider in that conversation can read
    them; that reader is the same Mac user who already holds the originals. Accepted until the
    release that stops offering another provider in a teammate's conversation (ruling 20 c).
    No lane widens the archive's readers or copies it elsewhere. (d) A teammate that already
    moved gets the memory link only through a fresh primary conversation on its own provider
    instance (ruling 20 b), one at a time, with its board agent idle. A teammate's wake is
    never held back to save a second rebind. Reason: the Hermes body's behaviour is its Hermes
    prompt, which no lane edits, and the teammate has no Slack path, so a request filed to the
    board today would be answered where the person never looks.
