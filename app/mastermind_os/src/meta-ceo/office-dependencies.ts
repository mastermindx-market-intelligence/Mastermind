/** Presentation only, over the SAME qualified configured-C Programs collection. */
export interface DependencyRow {
  workRef: string;
  title: string | null;
  state: "AVAILABLE" | "UNAVAILABLE";
  source: string | null;
  readiness: "ready" | "blocked" | "in_progress" | "done" | "unknown" | null;
  declared: readonly string[] | null;
  unmet: readonly string[] | null;
}
const states = ["ready", "blocked", "in_progress", "done", "unknown"] as const;
const workRef = (v: unknown): v is string =>
  typeof v === "string" && /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(v);
function record(v: unknown): Record<string, unknown> | null {
  if (
    !v ||
    typeof v !== "object" ||
    ![Object.prototype, null].includes(Object.getPrototypeOf(v))
  )
    return null;
  const descriptors = Object.getOwnPropertyDescriptors(v);
  if (
    Reflect.ownKeys(v).some(
      (k) => typeof k !== "string" || !("value" in descriptors[k]),
    )
  )
    return null;
  return v as Record<string, unknown>;
}
function array(v: unknown, max: number): unknown[] | null {
  if (
    !Array.isArray(v) ||
    Object.getPrototypeOf(v) !== Array.prototype ||
    v.length > max
  )
    return null;
  const d = Object.getOwnPropertyDescriptors(v);
  if (
    Reflect.ownKeys(v).length !== v.length + 1 ||
    !Array.from({ length: v.length }, (_, i) => d[String(i)]).every(
      (x) => x && "value" in x,
    )
  )
    return null;
  return v;
}
function refs(v: unknown, self: string): string[] | null {
  const rows = array(v, 128);
  return rows &&
    rows.every((x) => workRef(x) && x !== self) &&
    new Set(rows).size === rows.length
    ? (rows as string[])
    : null;
}
/** Unknown metadata is not a zero-dependency claim. No new rows or authority. */
export function projectDeclaredDependencies(
  raw: unknown,
  known: readonly { workRef: string; title: string | null }[],
): DependencyRow[] {
  const absent = (): DependencyRow[] =>
    known.map((p) => ({
      workRef: p.workRef,
      title: p.title,
      state: "UNAVAILABLE",
      source: null,
      readiness: null,
      declared: null,
      unmet: null,
    }));
  try {
    const cards = array(raw, 512),
      result = absent();
    if (
      !cards ||
      known.length > 512 ||
      cards.length !== known.length ||
      new Set(known.map((p) => p.workRef)).size !== known.length
    )
      return result;
    const byRef = new Map<string, Record<string, unknown>>();
    for (const card of cards) {
      const item = record(card);
      if (!item || !workRef(item.work_ref) || byRef.has(item.work_ref))
        return result;
      byRef.set(item.work_ref, item);
    }
    if (known.some((p) => !workRef(p.workRef) || !byRef.has(p.workRef)))
      return result;
    return result.map((row) => {
      const agent = record(byRef.get(row.workRef)!.agent_os);
      const source = `agentos/workstreams/WS-${row.workRef.slice(3)}.md`;
      if (
        !agent ||
        agent.workstream !== row.workRef.slice(3) ||
        agent.source !== source ||
        !states.includes(agent.state as (typeof states)[number])
      )
        return row;
      const declared = refs(agent.depends_on, row.workRef),
        unmet = refs(agent.unmet_dependencies, row.workRef);
      if (!declared || !unmet || unmet.some((ref) => !declared.includes(ref)))
        return row;
      return {
        ...row,
        state: "AVAILABLE",
        source,
        readiness: agent.state as DependencyRow["readiness"],
        declared: [...declared],
        unmet: [...unmet],
      };
    });
  } catch {
    return absent();
  }
}
