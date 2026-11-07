import { describe, expect, it } from "vitest";
import { fleetFixture } from "./fleet.test-fixture";

// Glob makes an absent implementation a normal failing feature assertion.
const module = import.meta.glob<{ decodeFleetHealth: (value: unknown, window?: string) => any }>("./fleet.ts", { eager: true })["./fleet.ts"];
const decode = (value: unknown, window = "24h") => {
  expect(module?.decodeFleetHealth, "Fleet decoder is not implemented").toBeTypeOf("function");
  return module.decodeFleetHealth(value, window);
};

describe("Fleet observation contract", () => {
  it("distinguishes measured zero from missing readings and detaches source objects", () => {
    const input = fleetFixture();
    const result = decode(input);
    expect(result).toEqual(input);
    expect(result.hosts[0].metrics.cpu_busy_pct).toBe(0);
    expect(result.hosts[0].metrics.fan_rpm).toBeNull();
    expect(result.hosts).not.toBe(input.hosts);
    input.hosts[0].metrics.cpu_busy_pct = 99;
    expect(result.hosts[0].metrics.cpu_busy_pct).toBe(0);
  });
  it.each([NaN, Infinity, -1, true, "50", 101])("refuses invalid utilization %s", value => {
    const input: any = fleetFixture();
    input.hosts[0].metrics.cpu_busy_pct = value;
    expect(decode(input)).toBeNull();
  });
  it("rejects extra fields, duplicate identities, and wrong request windows", () => {
    expect(decode({ ...fleetFixture(), private_path: "/secret" })).toBeNull();
    const extra: any = fleetFixture();
    extra.hosts[0].metrics.private = "secret";
    expect(decode(extra)).toBeNull();
    const duplicate = fleetFixture(); duplicate.hosts.push(duplicate.hosts[0]);
    expect(decode(duplicate)).toBeNull();
    expect(decode(fleetFixture(), "7d")).toBeNull();
  });
  it("keeps unavailable distinct from an empty available fleet", () => {
    const input = { ...fleetFixture(), hosts: [], availability: "UNAVAILABLE", reason_codes: ["SOURCE_UNAVAILABLE"] };
    expect(decode(input)).toEqual(input);
    expect(decode({ ...input, availability: "AVAILABLE", reason_codes: [] })).toBeNull();
  });
  it("enforces observation freshness without accepting future timestamps", () => {
    const input = fleetFixture(); input.hosts[0].observed_at -= 181;
    expect(decode(input)).toBeNull();
    input.hosts[0].state = "STALE"; input.availability = "PARTIAL";
    expect(decode(input)).not.toBeNull();
    input.hosts[0].observed_at = input.generated_at + 1;
    expect(decode(input)).toBeNull();
  });
  it("rejects offline readings advertised as current numbers", () => {
    const input = fleetFixture(); input.hosts[0].state = "OFFLINE"; input.availability = "PARTIAL";
    expect(decode(input)).toBeNull();
  });
  it("validates RAM arithmetic and integer lane counts", () => {
    const input = fleetFixture(); input.hosts[0].metrics.memory_used_pct = 2;
    expect(decode(input)).toBeNull();
    input.hosts[0].metrics.memory_used_pct = 50; input.hosts[0].metrics.fabric_active_lanes = 1.5;
    expect(decode(input)).toBeNull();
  });
  it("retains raw gap markers and rejects reordered or future history", () => {
    expect(decode(fleetFixture()).hosts[0].history[1].gaps).toEqual(["memory_used_pct"]);
    const input = fleetFixture(); input.hosts[0].history.reverse();
    expect(decode(input)).toBeNull();
    input.hosts[0].history.reverse(); input.hosts[0].history[1].timestamp++;
    expect(decode(input)).toBeNull();
  });
  it("rejects arbitrary gap keys and unbounded findings", () => {
    const input: any = fleetFixture(); input.hosts[0].history[1].gaps = ["private_path"];
    expect(decode(input)).toBeNull();
    input.hosts[0].history[1].gaps = [];
    input.hosts[0].findings = [{ code: "HEAT", category: "hardware", severity: "warning",
      summary: "x", detail: "x".repeat(801), duration_seconds: 600 }];
    expect(decode(input)).toBeNull();
  });
});
