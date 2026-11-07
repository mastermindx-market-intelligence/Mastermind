/** v5 adds two DISTINCT owner facts. The original eight-row decoder is reused
 * without treating v4 membership as permission for either new operation. */
import {
  decodeProjectAccess,
  type ProjectAccessRead,
  type ProjectAccessSelection,
} from "./project-access";
export { validProjectAccessSelection } from "./project-access";
export type { ProjectAccessSelection } from "./project-access";
type Available = Extract<ProjectAccessRead, { availability: "AVAILABLE" }>;
type Row = NonNullable<Available["grants"]>[number];
export type ProjectAccessAction =
  Row["action"] | "publish_project_plan_proposal" | "read_latest_project_data" | "correct_project_discovery";
export type CurrentGrant = Omit<Row, "action" | "scope" | "instruction_ref"> & {
  action: ProjectAccessAction;
  scope: "WORKSPACE" | "PROJECT" | "INSTRUCTION";
  instruction_ref: string | null;
};
type V5 = Omit<Available, "schema" | "declaration" | "grants"> & {
  schema: "mastermind.workspace_project_access.v2";
  grant_schema: "mastermind.workspace_acquisition_bindings.v5";
  declaration: "SUPPLIED";
  grants: CurrentGrant[];
};
type V6 = Omit<V5,'schema'|'grant_schema'> & {
  schema:'mastermind.workspace_project_access.v3';
  grant_schema:'mastermind.workspace_acquisition_bindings.v6';
};
export type ProjectAccessCurrentRead = ProjectAccessRead | V5 | V6;
function exact(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> | null {
  if (
    typeof value !== "object" ||
    value === null ||
    Array.isArray(value) ||
    ![Object.prototype, null].includes(Object.getPrototypeOf(value))
  )
    return null;
  const fields = Object.getOwnPropertyDescriptors(value);
  if (
    Reflect.ownKeys(fields).length !== keys.length ||
    !keys.every(
      (key) =>
        Object.hasOwn(fields, key) &&
        fields[key].enumerable &&
        Object.hasOwn(fields[key], "value"),
    )
  )
    return null;
  return Object.fromEntries(keys.map((key) => [key, fields[key].value]));
}
export function decodeCurrentProjectAccess(
  value: unknown,
  expected: ProjectAccessSelection,
): ProjectAccessCurrentRead | null {
  try {
    const schema =
      typeof value === "object" && value !== null
        ? Object.getOwnPropertyDescriptor(value, "schema")
        : undefined;
    if (!schema || !Object.hasOwn(schema, "value")) return null;
    if (schema.value !== "mastermind.workspace_project_access.v2" && schema.value !== 'mastermind.workspace_project_access.v3')
      return decodeProjectAccess(value, expected);
    const v6=schema.value==='mastermind.workspace_project_access.v3', count=v6?11:10;
    const body = exact(value, [
      "schema",
      "selection",
      "availability",
      "source",
      "membership",
      "declaration",
      "grants",
      "reason_codes",
      "grant_schema",
    ]);
    if (
      !body ||
      body.grant_schema !== (v6?'mastermind.workspace_acquisition_bindings.v6':"mastermind.workspace_acquisition_bindings.v5") ||
      body.availability !== "AVAILABLE" ||
      body.declaration !== "SUPPLIED" ||
      !Array.isArray(body.grants) ||
      Object.getPrototypeOf(body.grants) !== Array.prototype
    )
      return null;
    const fields = Object.getOwnPropertyDescriptors(body.grants as object),
      keys = Reflect.ownKeys(fields);
    if (
      fields.length?.value !== count ||
      keys.length !== count+1 ||
      !Array.from({ length: count }, (_, i) => String(i)).every(
        (key) => fields[key]?.enumerable && Object.hasOwn(fields[key], "value"),
      )
    )
      return null;
    const rows = Array.from({ length: count }, (_, i) => fields[String(i)].value);
    const { grant_schema: _, ...base } = body;
    const decoded = decodeProjectAccess(
      {
        ...base,
        schema: "mastermind.workspace_project_access.v1",
        grants: rows.slice(0, 8),
      },
      expected,
    );
    if (
      !decoded ||
      decoded.availability !== "AVAILABLE" ||
      decoded.declaration !== "SUPPLIED" ||
      decoded.grants === null
    )
      return null;
    const added: CurrentGrant[] = [];
    const extensions:readonly (readonly [number,ProjectAccessAction,'PROJECT'|'WORKSPACE'])[]=[
      [8, "publish_project_plan_proposal", "PROJECT"],
      [9, "read_latest_project_data", "WORKSPACE"],
      ...(v6?[[10,'correct_project_discovery','PROJECT'] as const]:[]),
    ];
    for (const [i, action, scope] of extensions) {
      const row = exact(rows[i], [
        "action",
        "scope",
        "work_ref",
        "instruction_ref",
        "supply",
      ]);
      if (
        !row ||
        row.action !== action ||
        row.scope !== scope ||
        row.work_ref !==
          (scope === "WORKSPACE" ? null : decoded.selection.work_ref) ||
        row.instruction_ref !== null ||
        !["SUPPLIED", "NOT_SUPPLIED"].includes(row.supply as string)
      )
        return null;
      added.push({
        action,
        scope,
        work_ref: scope === "WORKSPACE" ? null : decoded.selection.work_ref,
        instruction_ref: null,
        supply: row.supply as "SUPPLIED" | "NOT_SUPPLIED",
      });
    }
    const qualified = {
      ...decoded,
      grants: [...decoded.grants, ...added],
    };
    return v6?{...qualified,schema:'mastermind.workspace_project_access.v3',grant_schema:'mastermind.workspace_acquisition_bindings.v6'}
      :{...qualified,schema:'mastermind.workspace_project_access.v2',grant_schema:'mastermind.workspace_acquisition_bindings.v5'};
  } catch {
    return null;
  }
}
