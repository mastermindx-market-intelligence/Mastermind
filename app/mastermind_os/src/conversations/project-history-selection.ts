/** Fixed rootless history READ selector. DATA only, no session or send target. */
export function projectHistorySelection(value: unknown): Readonly<{workRef: string}> | null {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
    const fields = Object.getOwnPropertyDescriptors(value), keys = Reflect.ownKeys(fields);
    if (keys.length !== 1 || keys[0] !== "workRef" || !Object.hasOwn(fields.workRef, "value")) return null;
    const workRef = fields.workRef.value;
    return typeof workRef === "string" && /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(workRef) &&
      !workRef.includes("\n") ? Object.freeze({workRef}) : null;
  } catch { return null; }
}
