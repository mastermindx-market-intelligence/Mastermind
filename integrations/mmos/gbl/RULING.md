# Grok Bot link (lane GBL): the principal's ruling, 2026-11-11

The Chairman's order: bots in Grok Bot, starting with its Secretary, and Mastermind OS
teammates, team threads and T3 development threads exchange messages and jobs both ways.
Design: `ARCHITECTURE.md`, corrected by `ADDENDUM_1.md`. Facts: `FACTS.md`. Lanes:
`BUILD_PLAN.md`. Where the addendum and the architecture disagree, the addendum wins.

## Ruled

1. **Transport.** One authenticated MCP connector carries every message and result. A Grok
   Bot webhook routine is an attention nudge only and carries an ask id, never text. Slack
   is not used; it may return later as a visible copy of the same records.
2. **Its own edge.** The September consultation facet stores in the production Executive,
   which this programme does not write. The link is a separate edge whose only store is
   Paperclip issues and comments. It imports the existing sign-in check, id mint, frame
   codec and wake dispatcher; none of those is written twice or edited.
3. **Admission.** Grok Bot has no per-bot identity, so the boundary is the connected account
   plus a table the bridge owns: which targets, which kinds, what rate. Every request is
   admitted by its OAuth token, never by source address or header. Local sessions are
   admitted by Unix socket and peer uid.
4. **Kinds in the first version.** Delegate, result, question, answer, and message. No
   source writes, installs or spending through the link.
5. **Messages to a named thread** are built with an empty allowlist. A thread on the team
   server is switched on by the principal. An environment of the Chairman's own T3 app is
   switched on only after he names it. Text always arrives as quoted words of a named
   outside party.
6. **Development threads asking a bot** need no write into any T3 app: the session runs the
   ask command in the background and is woken by its exit.
7. **Account.** The existing Grok Bot account. No new seat.
8. **Ingress.** One dedicated named tunnel on this Mac to one loopback port that serves only
   this edge. The existing relay to the VPS is not used. Opening a public endpoint and
   creating the OAuth client are the Chairman's acts or need his word.

## Proofs without a person

Everything up to the real connector is proven on dev with a stand-in for Grok Bot: a test
MCP client holding a token from a test issuer, and a local stand-in for the routine URL.
The real connector, consent and routine are one sitting for the Chairman, asked once when
the reviewed build is ready.

## Open

- How Grok Bot's custom connector obtains its token (a client registered ahead, or
  registration by the connector itself) is not in `FACTS.md`. Lane GBL-3 reads the vendor
  documentation for it before writing the edge.
- Whether a slow tool call is waited for, and whether a second bot under the account sees
  the connector: checked in the Chairman's sitting. The design holds under either answer.
- The result of a delegation lands in the chat of the bot that owns the routine. The
  routine is pinned to the Secretary bot so the main path returns to the conversation
  that asked.
