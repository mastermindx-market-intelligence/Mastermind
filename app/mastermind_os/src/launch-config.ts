import type { LaunchBindingConfig } from "./orchestration/executive-launch-command-port";

declare global { interface ImportMetaEnv { readonly VITE_MM_LAUNCH_CONFIG?: string; } }
const rootKeys = new Set(["v", "workstream", "priority", "projects", "profiles", "attemptLimit", "allowedWritePaths", "validation"]);
const validationKeys = new Set(["pytest_targets", "compileall_paths", "git_diff_check"]);
const object = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const string = (x: unknown, max = 256): x is string => typeof x === "string" && x.length > 0 && x.length <= max && !/[\u0000-\u001f\u007f]/.test(x);
const list = (x: unknown): x is string[] => Array.isArray(x) && x.length <= 16 && x.every((v) => string(v));
function paths(x: unknown): x is string[] {
  return list(x) && x.every((p) => !p.startsWith("/") && !p.includes("\\") &&
    p.split("/").every((s) => s.length > 0 && s !== "." && s !== ".." && s !== ".git"));
}
function choices(x: unknown, profile: boolean): x is Array<{ ref: string; label: string }> {
  return Array.isArray(x) && x.length > 0 && x.length <= 16 &&
    x.every((c) => object(c) && Object.keys(c).length === 2 &&
      string(c.label, 120) && string(c.ref, 64) &&
      (profile ? ["research_only", "bounded_code_change"].includes(c.ref) : /^[a-z][a-z0-9._-]{1,63}$/.test(c.ref))) &&
    new Set(x.map((c) => c.ref)).size === x.length;
}
/** Public operator build manifest, never selected from URL, UI, or a tool reply. */
export function decodeLaunchBindingConfig(raw: unknown): LaunchBindingConfig | null {
  if (typeof raw !== "string" || raw.length > 16_384) return null;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return null; }
  if (!object(parsed) || Object.keys(parsed).some((k) => !rootKeys.has(k)) || parsed.v !== 1 ||
      !string(parsed.workstream, 72) || !/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(parsed.workstream) ||
      !Number.isInteger(parsed.priority) || Number(parsed.priority) < -100 || Number(parsed.priority) > 100 ||
      !choices(parsed.projects, false) || !choices(parsed.profiles, true)) return null;
  if (parsed.attemptLimit !== undefined && ![1, 2, 3].includes(Number(parsed.attemptLimit))) return null;
  if (parsed.attemptLimit !== undefined && typeof parsed.attemptLimit !== "number") return null;
  if (parsed.allowedWritePaths !== undefined && !paths(parsed.allowedWritePaths)) return null;
  if (parsed.validation !== undefined) {
    const v = parsed.validation;
    if (!object(v) || Object.keys(v).some((k) => !validationKeys.has(k)) ||
      (v.pytest_targets !== undefined && !list(v.pytest_targets)) ||
      (v.compileall_paths !== undefined && !paths(v.compileall_paths)) ||
      (v.git_diff_check !== undefined && typeof v.git_diff_check !== "boolean")) return null;
  }
  const writeCount = (parsed.allowedWritePaths as string[] | undefined)?.length ?? 0;
  const validation = parsed.validation as LaunchBindingConfig["validation"];
  const hasValidation = !!(validation?.pytest_targets?.length || validation?.compileall_paths?.length || validation?.git_diff_check);
  for (const profile of parsed.profiles) {
    if (profile.ref === "research_only" && (writeCount || hasValidation)) return null;
    if (profile.ref === "bounded_code_change" && (!writeCount || !hasValidation)) return null;
  }
  const { v: _version, ...config } = parsed;
  const freeze = (value: unknown): void => {
    if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  };
  freeze(config);
  return config as unknown as LaunchBindingConfig;
}
export function readLaunchBindingConfig(): LaunchBindingConfig | null {
  return decodeLaunchBindingConfig(import.meta.env?.VITE_MM_LAUNCH_CONFIG);
}
