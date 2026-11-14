/** Team-roster adapter over Director B's authoritative contract
 * (`src/hermes-native/team-roster-contract.ts`, `mastermind.team_roster/v1`).
 *
 * This module holds NO parser of its own: every roster value the Team view
 * renders comes from B's fail-closed `parseTeamRoster` through the existing
 * native port. It only re-exports B's types and defines the read-state union
 * the view renders — one contract, one producer, no duplicate parser. */
import type { TeamRoster } from "../hermes-native/team-roster-contract";

export type {
  TeamRoster,
  TeamBot,
  RosterGateway,
  RosterGatewaySource,
  RosterReadiness,
} from "../hermes-native/team-roster-contract";

/** Honest read states for the roster. `UNAVAILABLE.reason` is a code from the
 * native port's closed vocabulary (e.g. `NATIVE_PLATFORM_UNAVAILABLE`,
 * `NATIVE_RESPONSE_INVALID`); unknown is never rendered as ready. */
export type TeamRosterRead =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "AVAILABLE"; roster: TeamRoster };
