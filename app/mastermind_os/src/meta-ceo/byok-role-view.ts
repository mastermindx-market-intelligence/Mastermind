import type { ByokRoleMetadata, ByokRolesRead } from "./byok-roles-read";

type RoleView<R extends "mmmeta" | "mmsecretary"> = Readonly<{
  role: R;
  state: ByokRoleMetadata["state"];
  requestedProvider?: string;
  requestedModel?: string;
}>;

/** Presentation data only. The authenticated read owner retains all evidence. */
export type ByokRoleView = Readonly<{
  state: "LOADING" | "SOURCE_UNBOUND" | "UNAVAILABLE" | "OBSERVED";
  roles?: readonly [RoleView<"mmmeta">, RoleView<"mmsecretary">];
}>;

export function byokRoleView(input: Readonly<{
  state: ByokRoleView["state"];
  body: ByokRolesRead | null;
}>): ByokRoleView {
  if (input.state !== "OBSERVED") return { state: input.state };
  const body = input.body;
  if (body?.state !== "OBSERVED" || body.roles.length !== 2 ||
      body.roles[0].role !== "mmmeta" || body.roles[1].role !== "mmsecretary" ||
      body.roles.some(row => row.state === "CONFIGURATION_OBSERVED" &&
        (row.requested_provider === null || row.requested_model === null))) {
    return { state: "UNAVAILABLE" };
  }
  function role<R extends "mmmeta" | "mmsecretary">(row: ByokRoleMetadata, name: R): RoleView<R> {
    return row.state === "CONFIGURATION_OBSERVED"
      ? { role: name, state: row.state,
          requestedProvider: row.requested_provider!, requestedModel: row.requested_model! }
      : { role: name, state: row.state };
  }
  return { state: "OBSERVED", roles: [role(body.roles[0], "mmmeta"), role(body.roles[1], "mmsecretary")] };
}
