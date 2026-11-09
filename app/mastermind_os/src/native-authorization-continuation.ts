/** Metadata from the fixed native owner; eligibility never substitutes for its command guard. */
export type NativeAuthorizationContinuation =
  | {schema: "mastermind.native_authorization_continuation.v1"; state: "ELIGIBLE"; resource: "CONTENT"; reason: "CONTENT_PENDING_TIMEOUT"}
  | {schema: "mastermind.native_authorization_continuation.v1"; state: "INELIGIBLE"; resource: null; reason: "NOT_ELIGIBLE"};
export function decodeNativeAuthorizationContinuation(raw: unknown): NativeAuthorizationContinuation | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const prototype = Object.getPrototypeOf(raw);
  if (prototype !== Object.prototype && prototype !== null) return null;
  const keys = Reflect.ownKeys(raw);
  if (keys.length !== 4 || keys.some(key => typeof key !== "string") ||
      keys.sort().join(",") !== "reason,resource,schema,state") return null;
  const descriptors = Object.getOwnPropertyDescriptors(raw);
  if (keys.some(key => !descriptors[key as string].enumerable || !("value" in descriptors[key as string]))) return null;
  const value = raw as Record<string, unknown>;
  if (value.schema !== "mastermind.native_authorization_continuation.v1") return null;
  if (value.state === "ELIGIBLE" && value.resource === "CONTENT" && value.reason === "CONTENT_PENDING_TIMEOUT")
    return {schema: value.schema, state: "ELIGIBLE", resource: "CONTENT", reason: "CONTENT_PENDING_TIMEOUT"};
  if (value.state === "INELIGIBLE" && value.resource === null && value.reason === "NOT_ELIGIBLE")
    return {schema: value.schema, state: "INELIGIBLE", resource: null, reason: "NOT_ELIGIBLE"};
  return null;
}
