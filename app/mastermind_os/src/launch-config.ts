import type { LaunchBindingConfig, LaunchConfiguration } from "./orchestration/executive-launch-command-port";

declare global { interface ImportMetaEnv { readonly VITE_MM_LAUNCH_CONFIG?: string; } }
const rootKeys = new Set(["v", "workstream", "priority", "projects", "profiles", "attemptLimit", "allowedWritePaths", "validation", "frontierModels"]);
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
      (profile ? ["research_only", "bounded_code_change", "native_research_only"].includes(c.ref) : /^[a-z][a-z0-9._-]{1,63}$/.test(c.ref))) &&
    new Set(x.map((c) => c.ref)).size === x.length;
}
function frontierChoices(x: unknown): boolean {
  return Array.isArray(x) && x.length > 0 && x.length <= 16 &&
    x.every((c) => object(c) && Object.keys(c).every((key) => ["ref", "label", "unavailableReason"].includes(key)) &&
      string(c.label, 120) && string(c.ref, 64) && /^[a-z0-9][a-z0-9._-]{0,63}$/.test(c.ref) &&
      (c.unavailableReason === undefined || string(c.unavailableReason, 256))) &&
    new Set(x.map((c) => c.ref)).size === x.length;
}
function decodeBinding(parsed: unknown): LaunchBindingConfig | null {
  if (!object(parsed) || Object.keys(parsed).some((k) => !rootKeys.has(k)) || parsed.v !== 1 ||
      !string(parsed.workstream, 72) || !/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(parsed.workstream) ||
      !Number.isInteger(parsed.priority) || Number(parsed.priority) < -100 || Number(parsed.priority) > 100 ||
      !choices(parsed.projects, false) || !choices(parsed.profiles, true)) return null;
  if (parsed.frontierModels !== undefined && !frontierChoices(parsed.frontierModels)) return null;
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
  if (parsed.profiles.some(p => p.ref === "native_research_only") &&
      (parsed.projects.length !== 1 || parsed.profiles.length !== 2 ||
       parsed.profiles[0].ref !== "research_only" || parsed.profiles[1].ref !== "native_research_only")) return null;
  for (const profile of parsed.profiles) {
    if (["research_only", "native_research_only"].includes(profile.ref) && (writeCount || hasValidation)) return null;
    if (profile.ref === "native_research_only" && parsed.attemptLimit !== 1) return null;
    if (profile.ref === "bounded_code_change" && (!writeCount || !hasValidation)) return null;
  }
  const { v: _version, ...config } = parsed;
  const freeze = (value: unknown): void => {
    if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  };
  freeze(config);
  return config as unknown as LaunchBindingConfig;
}
function canonicalManifestSize(value: unknown): number {
  const ordered = (item: unknown): unknown => Array.isArray(item) ? item.map(ordered) :
    object(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key, ordered(item[key])])) : item;
  // The sealed Python receipt uses ensure_ascii=True and one final newline.
  return JSON.stringify(ordered(value)).replace(/[^\x00-\x7f]/g,
    character => "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0")).length + 1;
}
/** Public operator build manifest, never selected from URL, UI, or a tool reply. */
export function decodeLaunchBindingConfig(raw: unknown): LaunchConfiguration | null {
  if (typeof raw !== "string" || raw.length > 16_384) return null;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return null; }
  if (!object(parsed)) return null;
  if (parsed.v === 1) return decodeBinding(parsed);
  if (parsed.v !== 2 || Object.keys(parsed).length !== 3 ||
      Object.keys(parsed).some(key => !["v", "defaultWorkstream", "bindings"].includes(key)) ||
      !string(parsed.defaultWorkstream, 72) || !Array.isArray(parsed.bindings) ||
      parsed.bindings.length < 1 || parsed.bindings.length > 16) return null;
  const bindings: Array<LaunchBindingConfig & { readonly label: string }> = [];
  const seen = new Set<string>();
  let templates = 0;
  for (const entry of parsed.bindings) {
    if (!object(entry) || !string(entry.label, 120) ||
        Object.keys(entry).some(key => key !== "label" && (key === "v" || !rootKeys.has(key)))) return null;
    const { label, ...fields } = entry;
    const binding = decodeBinding({ v: 1, ...fields });
    if (!binding || binding.projects.length !== 1 || seen.has(binding.workstream) ||
        !(binding.profiles.length === 1 && binding.profiles[0].ref === "research_only" ||
          binding.profiles.length === 2 && binding.profiles[0].ref === "research_only" &&
          binding.profiles[1].ref === "native_research_only")) return null;
    // The incumbent publisher accepts only absent or exactly empty validation for a native pair.
    if (binding.profiles.length === 2 && binding.validation !== undefined &&
        Object.keys(binding.validation).length !== 0) return null;
    seen.add(binding.workstream);
    templates += binding.profiles.length;
    bindings.push(Object.freeze({ ...binding, label }));
  }
  if (templates > 16 || !seen.has(parsed.defaultWorkstream) || canonicalManifestSize(parsed) > 4096) return null;
  return Object.freeze({ v: 2, defaultWorkstream: parsed.defaultWorkstream,
    bindings: Object.freeze(bindings) });
}
export function readLaunchBindingConfig(): LaunchConfiguration | null {
  return decodeLaunchBindingConfig(import.meta.env?.VITE_MM_LAUNCH_CONFIG);
}
