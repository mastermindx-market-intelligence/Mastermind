import { expect, it } from "vitest";
import ownerProjection from "../../../../research/evidence/native-capacity-owner-projection.json";
import { capacityBindingFields, decodeHostCapacityRead, qualifyHostCapacityRead, type HostCapacityBinding } from "./host-capacity";
const copy = () => structuredClone(ownerProjection);
const binding = () => Object.fromEntries(capacityBindingFields.map(field => [field, ownerProjection[field]])) as HostCapacityBinding;

it("consumes the actual Python owner projection fixture and preserves no-placement semantics", () => {
  const read = qualifyHostCapacityRead(copy(), binding(), 100100, 5000);
  expect(read.metrics.effective_cpu_capacity_millicores.value).toBe(1500);
  expect(read.metrics.effective_memory_headroom_estimate_bytes.unit).toBe("bytes_estimate");
  expect(read.metrics.darwin_vm_counters.value).toBeNull();
  expect(read.can_place_work).toBe(false);
  expect(read.admission_state).toBe("NOT_EVALUATED");
  expect(Object.isFrozen(read.metrics)).toBe(true);
});
it.each(capacityBindingFields)("rejects mismatched independent owner binding %s", field => {
  expect(() => qualifyHostCapacityRead(copy(), { ...binding(), [field]: "wrong" }, 100100, 5000)).toThrow("RESOURCE_CAPACITY_BINDING_MISMATCH");
});
it.each([[98999, 5000], [104001, 5000], [100100, 1000], [100100, 0]])("refuses future, oldest-window stale or invalid age policy", (now, age) => {
  expect(() => qualifyHostCapacityRead(copy(), binding(), now, age)).toThrow("RESOURCE_CAPACITY_STALE");
});
it("does not promote null readings to zero and checks their exact unknown list", () => {
  const d = copy();
  d.metrics.disk_usable_bytes = { value: null, null_reason: "PERMISSION_DENIED", unit: "bytes_unprivileged" } as unknown as typeof d.metrics.disk_usable_bytes;
  d.telemetry_status = "PARTIAL";
  d.unknown_fields = ["disk_usable_bytes"] as never;
  expect(decodeHostCapacityRead(d).metrics.disk_usable_bytes.value).toBeNull();
  d.unknown_fields = [];
  expect(() => decodeHostCapacityRead(d)).toThrow();
});
it("refuses forged readiness, extra fields, wrong units and unsafe integer rounding", () => {
  expect(() => decodeHostCapacityRead({ ...copy(), can_place_work: true })).toThrow();
  expect(() => decodeHostCapacityRead({ ...copy(), free_slots: 3 })).toThrow();
  const wrongUnit = copy(); wrongUnit.metrics.disk_usable_bytes.unit = "free_worker_slots";
  expect(() => decodeHostCapacityRead(wrongUnit)).toThrow();
  const unsafe = copy(); unsafe.metrics.disk_usable_bytes.value = Number.MAX_SAFE_INTEGER + 1;
  expect(() => decodeHostCapacityRead(unsafe)).toThrow();
});
it("checks physical bounds and retains inapplicable readings as null", () => {
  const bad = copy(); bad.metrics.host_swap_used_bytes.value = bad.metrics.host_swap_total_bytes.value + 1;
  expect(() => decodeHostCapacityRead(bad)).toThrow();
  const darwin = copy(); darwin.metrics.darwin_vm_counters = { value: 0, null_reason: null, unit: "not_applicable" } as never;
  expect(() => decodeHostCapacityRead(darwin)).toThrow();
});
