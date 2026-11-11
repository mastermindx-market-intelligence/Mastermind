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
