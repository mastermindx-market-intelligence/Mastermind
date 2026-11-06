import { expect, it, vi } from "vitest";
import { createNativeDraftRecoveryOwner } from "./native-draft-owner";
function setup() {
  let source = 1, signed = true, clock = 1000;
  let metadata: unknown = { schema: "mastermind.native_draft_continuity.v1", owner_instance: "1".repeat(32), privacy_epoch: 1,
    phase: "QUALIFIED", cause: "OWNER_QUALIFIED", principal_scope: "a".repeat(64), valid_until_ms: 5000 };
  const inspect = vi.fn(async () => metadata);
  const owner = createNativeDraftRecoveryOwner({ inspect, sourceGeneration: () => source, signedIn: () => signed, now: () => clock });
  return { owner, inspect, set: (value: unknown) => { metadata = value; }, rotate: () => source++, signOut: () => { signed = false; }, signIn: () => { signed = true; }, expire: () => { clock = 5000; } };
}
const frame = (phase: string, cause: string, overrides = {}) => ({ schema: "mastermind.native_draft_continuity.v1", owner_instance: "1".repeat(32), privacy_epoch: 1,
  phase, cause, principal_scope: null, valid_until_ms: null, ...overrides });
it("holds metadata only and restores only explicit same-principal/original-scope return", async () => {
  const s = setup(), origin = await s.owner.capture("project:WS:ONE:goal"); expect(origin).not.toBeNull();
  expect(s.owner.canReturn(origin!, "project:WS:ONE:goal")).toBe(false);
  s.set(frame("EXPIRED", "TOKEN_EXPIRED")); s.signOut(); s.owner.invalidate();
  expect(s.owner.quarantine(origin!)).toBe(true); expect(await s.owner.check(origin!)).toBe("QUARANTINED");
  s.set(frame("REAUTHENTICATING", "REAUTHENTICATION")); expect(await s.owner.check(origin!)).toBe("QUARANTINED");
  s.set(frame("QUALIFIED", "OWNER_QUALIFIED", { principal_scope: "a".repeat(64), valid_until_ms: 5000 })); s.signIn();
  expect(await s.owner.check(origin!)).toBe("RETURNABLE");
  expect(s.owner.canReturn(origin!, "project:WS:OTHER:goal")).toBe(false);
  expect(s.owner.canReturn(origin!, "project:WS:ONE:goal")).toBe(true);
  expect(Object.keys(origin!)).toEqual(["scopeKey", "principalScope", "ownerInstance", "privacyEpoch"]);
});
it.each(["logout", "other_principal", "epoch", "instance"])("retires original draft boundary on %s", async kind => {
  const s = setup(), origin = await s.owner.capture("original");
  if (kind === "logout") s.set(frame("WITHDRAWN", "EXPLICIT_LOGOUT", { privacy_epoch: 2 }));
  else s.set(frame("QUALIFIED", "OWNER_QUALIFIED", { principal_scope: kind === "other_principal" ? "b".repeat(64) : "a".repeat(64), valid_until_ms: 5000,
    privacy_epoch: kind === "epoch" ? 2 : 1, owner_instance: kind === "instance" ? "2".repeat(32) : "1".repeat(32) }));
  expect(await s.owner.check(origin!)).toBe("CLEARED");
  expect(s.owner.canReturn(origin!, "original")).toBe(false);
});
it("a public DTO cannot mint an issued draft origin", async () => {
  const s = setup();
  const forged = { scopeKey: "original", principalScope: "a".repeat(64), ownerInstance: "1".repeat(32), privacyEpoch: 1 };
  expect(s.owner.quarantine(forged)).toBe(false); expect(await s.owner.check(forged)).toBe("CLEARED");
  expect(s.owner.canReturn(forged, "original")).toBe(false); expect(s.inspect).not.toHaveBeenCalled();
});
it("unqualified identity remains quarantined and loses no pending-operation state", async () => {
  const s = setup(), origin = await s.owner.capture("original");
  s.set(frame("UNQUALIFIED", "OWNER_UNQUALIFIED"));
  expect(await s.owner.check(origin!)).toBe("QUARANTINED");
  expect(s.owner.canReturn(origin!, "original")).toBe(false);
});
it("expiry and owner invalidation retire prior explicit return witness", async () => {
  const s = setup(), origin = await s.owner.capture("original");
  expect(await s.owner.check(origin!)).toBe("RETURNABLE"); s.expire();
  expect(s.owner.canReturn(origin!, "original")).toBe(false); s.owner.invalidate();
  expect(s.owner.canReturn(origin!, "original")).toBe(false);
});
it("late native reply after generation departure is not a current continuity proof", async () => {
  const s = setup(); s.inspect.mockImplementationOnce(async () => { s.rotate(); return frame("QUALIFIED", "OWNER_QUALIFIED", { principal_scope: "a".repeat(64), valid_until_ms: 5000 }); });
  expect(await s.owner.capture("original")).toBeNull();
});
