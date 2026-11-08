/**
 * Presentation-only bridge between the existing OS and full DeepSeek app.
 * These messages never authorize a provider, tool, Job, or native session.
 * Authentication and all effectful commands retain their existing owners.
 */
export const COMPANY_SCHEMA = "mastermind.dsh.company.v1" as const;
export const COMPANY_PLUGIN_ID = "@mastermind/dsh-company" as const;
export const DONOR_SHA = "687f282e8625c6b8d11ff58211a90524be2e4317" as const;
export const MAX_PROJECTS = 128;

export interface CompanyProject {
  readonly workRef: string;
  readonly title: string;
}
export interface CompanyView {
  readonly generation: number;
  readonly state: "CURRENT" | "UNAVAILABLE" | "SIGNED_OUT";
  readonly locale: "en" | "zh-CN";
  readonly theme: "dark" | "light";
  readonly selectedProject: string | null;
  readonly projects: readonly CompanyProject[];
}
export type ChildMessage =
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "hello" }
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "ready"; readonly nonce: string; readonly donor: typeof DONOR_SHA }
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "ack"; readonly nonce: string; readonly generation: number }
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "open_project"; readonly nonce: string; readonly generation: number; readonly workRef: string };
export type ParentMessage =
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "connect"; readonly nonce: string }
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "context"; readonly nonce: string; readonly view: CompanyView }
  | { readonly schema: typeof COMPANY_SCHEMA; readonly type: "navigation_result"; readonly nonce: string; readonly generation: number; readonly workRef: string; readonly ok: boolean };

const WORK_REF = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const NONCE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function record(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key => typeof key === "string") &&
    Object.values(descriptors).every(d => "value" in d);
}
function keys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).sort().join(",") === [...expected].sort().join(",");
}
function generation(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}
function nonce(value: unknown): value is string {
  return typeof value === "string" && NONCE.test(value);
}
export function validWorkRef(value: unknown): value is string {
  return typeof value === "string" && WORK_REF.test(value);
}
export function decodeCompanyView(value: unknown): CompanyView | null {
  try {
    if (!record(value) || !keys(value, ["generation", "state", "locale", "theme", "selectedProject", "projects"]) ||
      !generation(value.generation) || !["CURRENT", "UNAVAILABLE", "SIGNED_OUT"].includes(value.state as string) ||
      !["en", "zh-CN"].includes(value.locale as string) || !["dark", "light"].includes(value.theme as string) ||
      !Array.isArray(value.projects) || value.projects.length > MAX_PROJECTS) return null;
    const seen = new Set<string>();
    const projects: CompanyProject[] = [];
    for (const raw of value.projects) {
      if (!record(raw) || !keys(raw, ["workRef", "title"]) || !validWorkRef(raw.workRef) ||
        typeof raw.title !== "string" || !raw.title.trim() || raw.title.length > 256 ||
        /[\u0000-\u001f\u007f]/.test(raw.title) || seen.has(raw.workRef)) return null;
      seen.add(raw.workRef);
      projects.push(Object.freeze({workRef: raw.workRef, title: raw.title}));
    }
    if (value.state !== "CURRENT" && (projects.length !== 0 || value.selectedProject !== null)) return null;
    if (value.selectedProject !== null && (!validWorkRef(value.selectedProject) || !seen.has(value.selectedProject))) return null;
    return Object.freeze({
      generation: value.generation,
      state: value.state as CompanyView["state"],
      locale: value.locale as CompanyView["locale"],
      theme: value.theme as CompanyView["theme"],
      selectedProject: value.selectedProject as string | null,
      projects: Object.freeze(projects),
    });
  } catch { return null; }
}
export function decodeChildMessage(value: unknown): ChildMessage | null {
  try {
    if (!record(value) || value.schema !== COMPANY_SCHEMA) return null;
    if (value.type === "hello" && keys(value, ["schema", "type"])) return {schema: COMPANY_SCHEMA, type: "hello"};
    if (!nonce(value.nonce)) return null;
    if (value.type === "ready" && keys(value, ["schema", "type", "nonce", "donor"]) && value.donor === DONOR_SHA)
      return {schema: COMPANY_SCHEMA, type: "ready", nonce: value.nonce, donor: DONOR_SHA};
    if (!generation(value.generation)) return null;
    if (value.type === "ack" && keys(value, ["schema", "type", "nonce", "generation"]))
      return {schema: COMPANY_SCHEMA, type: "ack", nonce: value.nonce, generation: value.generation};
    if (value.type === "open_project" && keys(value, ["schema", "type", "nonce", "generation", "workRef"]) && validWorkRef(value.workRef))
      return {schema: COMPANY_SCHEMA, type: "open_project", nonce: value.nonce, generation: value.generation, workRef: value.workRef};
    return null;
  } catch { return null; }
}
export function decodeParentMessage(value: unknown): ParentMessage | null {
  try {
    if (!record(value) || value.schema !== COMPANY_SCHEMA) return null;
    if (!nonce(value.nonce)) return null;
    if (value.type === "connect" && keys(value, ["schema", "type", "nonce"])) return {schema: COMPANY_SCHEMA, type: "connect", nonce: value.nonce};
    if (value.type === "context" && keys(value, ["schema", "type", "nonce", "view"])) {
      const view = decodeCompanyView(value.view);
      return view ? {schema: COMPANY_SCHEMA, type: "context", nonce: value.nonce, view} : null;
    }
    if (value.type === "navigation_result" && keys(value, ["schema", "type", "nonce", "generation", "workRef", "ok"]) &&
      generation(value.generation) && validWorkRef(value.workRef) && typeof value.ok === "boolean")
      return {schema: COMPANY_SCHEMA, type: "navigation_result", nonce: value.nonce, generation: value.generation, workRef: value.workRef, ok: value.ok};
    return null;
  } catch { return null; }
}

/** Public fixed deployment input, never a URL supplied by a message or user draft. */
export interface DeepSeekAppConfig { readonly url: string; readonly origin: string; }
export function deepSeekAppConfig(value: unknown, osOrigin: string): DeepSeekAppConfig | null {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value), parent = new URL(osOrigin);
    // A separate origin preserves the OS private authentication boundary.
    if (url.protocol !== "https:" || url.origin === parent.origin || url.username || url.password ||
      url.search || url.hash || url.port || url.href !== value || url.pathname !== "/") return null;
    // The release owner installs the application on an owned company origin.
    if (!/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+mastermind-x\.com$/.test(url.hostname) ||
      url.hostname === "mcp.mastermind-x.com" || value !== url.origin + "/") return null;
    return Object.freeze({url: url.href, origin: url.origin});
  } catch { return null; }
}
