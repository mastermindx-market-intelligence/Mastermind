import { expect, it } from "vitest";
import fixture from "./fixtures/accepted-direction-owner.json";
import { decodeAcceptedDirection } from "./accepted-direction";

it("decodes the actual Python owner projection of Root's new current Direction without invented history", () => {
  const selected = { work_ref: "WS:EXECUTIVE-ECOSYSTEM-COMPLETION" };
  const value = decodeAcceptedDirection(fixture, selected);
  expect(value.availability).toBe("AVAILABLE");
  if (value.availability !== "AVAILABLE") throw new Error("fixture unavailable");
  expect(value.direction.current.decision_ref).toBe("DEC:EXECUTIVE-ECOSYSTEM-CURRENT-DIRECTION-20261104");
  expect(value.direction.current.answer).toContain("full canonical Paper feature and design parity");
  expect(value.direction.current.decided_by).toBe("astra-meta-ceo (root 01a15741-5e68-7803-8eb4-ccac74a6c04b)");
  expect(value.direction.current.decided_at).toBe("2026-11-04");
  expect(value.direction.current.date_precision).toBe("DAY");
  expect(value.direction.history).toEqual({ revisions: [], has_more: false, total_count: 1 });
});
