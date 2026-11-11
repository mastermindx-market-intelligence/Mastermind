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
