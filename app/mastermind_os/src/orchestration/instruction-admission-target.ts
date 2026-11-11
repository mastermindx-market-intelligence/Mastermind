/** Stable lookup only. Source revision, text and permission never enter storage. */
export interface InstructionAdmissionTarget { readonly work_ref: string; readonly instruction_ref: string }
const PREFIX = "instruction-admission.v1:";
const REF = /^(?:WS|INS):[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
function valid(ref: unknown, prefix: string): ref is string {
  return typeof ref === "string" && ref.startsWith(prefix) && ref.length - prefix.length >= 2
    && ref.length - prefix.length <= 64 && REF.exec(ref)?.[0] === ref;
}
export function serializeInstructionAdmissionTarget(value: InstructionAdmissionTarget): string | null {
  try {
    if (typeof value !== "object" || value === null || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
    const keys = Reflect.ownKeys(value);
    if (keys.length !== 2 || !keys.includes("work_ref") || !keys.includes("instruction_ref")) return null;
    const work = Object.getOwnPropertyDescriptor(value,"work_ref"), instruction = Object.getOwnPropertyDescriptor(value,"instruction_ref");
    if (!work?.enumerable || !("value" in work) || !instruction?.enumerable || !("value" in instruction)
      || !valid(work.value,"WS:") || !valid(instruction.value,"INS:")) return null;
    return PREFIX + JSON.stringify({instruction_ref:instruction.value,work_ref:work.value});
  } catch { return null; }
}
export function parseInstructionAdmissionTarget(value: unknown): InstructionAdmissionTarget | null {
  if (typeof value !== "string" || value.length > 256 || !value.startsWith(PREFIX)) return null;
  try {
    const selected = JSON.parse(value.slice(PREFIX.length));
    return serializeInstructionAdmissionTarget(selected) === value ? selected as InstructionAdmissionTarget : null;
  } catch { return null; }
}
