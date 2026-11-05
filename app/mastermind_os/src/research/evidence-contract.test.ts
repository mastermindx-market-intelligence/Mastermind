import { describe, expect, it } from "vitest";
import { decodeEvidenceItem, evidenceRoute, evidenceUrl, validEvidenceId } from "./evidence-contract";
import { validateResearchResource, ORIGIN, ACQUISITION_AUDIENCE, CONTENT_AUDIENCE } from "../public-config";
const id = `rvitem.v1.${"a".repeat(64)}`;
const row = (text = "literal\f尾🙂") => ({ id, title: "Complete bounded evidence item", text, url: evidenceUrl(id), metadata: { coverage: "COMPLETE_BOUNDED_ITEM" } });
describe("conditional bounded evidence browser protocol", () => {
  it("accepts exactly the fixed opaque item path", () => {
    expect(validEvidenceId(id)).toBe(true);
    expect(evidenceRoute({ origin: ORIGIN, pathname: `/os/research/evidence/${id}`, search: "", hash: "" })).toBe(id);
  });
  it.each(["report", `${id}/`, id.toUpperCase(), `%72${id.slice(1)}`, `https://example.test/${id}`, `${id}?token=private`])("rejects opaque ID aliases: %s", input => {
    expect(validEvidenceId(input)).toBe(false); expect(() => evidenceUrl(input)).toThrow("EVIDENCE_ITEM_INVALID");
  });
  it.each([{ origin: "https://www.mastermind-x.com" }, { search: "?report=x" }, { hash: "#token=x" }, { pathname: `/os/research/evidence//${id}` }])("rejects route selectors and different origin", change => {
    expect(evidenceRoute({ origin: ORIGIN, pathname: `/os/research/evidence/${id}`, search: "", hash: "", ...change })).toBeNull();
  });
  it("preserves literal whitespace and Unicode without normalization", () => {
    const text = "  A\f中🙂e\u0301\n";
    expect(decodeEvidenceItem(row(text), id).text).toBe(text);
  });
  it("uses UTF8 bytes rather than UTF16 or codepoint counts", () => {
    expect(decodeEvidenceItem(row("🙂".repeat(250)), id).text).toHaveLength(500);
    expect(() => decodeEvidenceItem(row("🙂".repeat(251)), id)).toThrow("EVIDENCE_RESPONSE_INVALID");
  });
  it.each(["", "\ud800", "\udfff", "x".repeat(1001)])("refuses empty, changed Unicode and oversized text", text => {
    expect(() => decodeEvidenceItem(row(text), id)).toThrow("EVIDENCE_RESPONSE_INVALID");
  });
  it.each([{ id: `rvitem.v1.${"b".repeat(64)}` }, { url: `${evidenceUrl(id)}?token=x` }, { metadata: { coverage: "FULL_DOCUMENT" } }, { token: "private" }])("refuses mismatched identities and false completeness", change => {
    expect(() => decodeEvidenceItem({ ...row(), ...change }, id)).toThrow("EVIDENCE_RESPONSE_INVALID");
  });
  it("does not expose or interpret source metadata as authority", () => {
    expect(() => decodeEvidenceItem({ ...row(), metadata: { coverage: "COMPLETE_BOUNDED_ITEM", principal: "not authority" } }, id)).toThrow("EVIDENCE_RESPONSE_INVALID");
  });
  it.each([null, "http://example.test/research", "https://user:pass@example.test/research", "https://example.test/research?x=1", "https://example.test/research#token", ACQUISITION_AUDIENCE, CONTENT_AUDIENCE, `${ORIGIN}/os/executive`])("Research config fails closed without borrowing another resource", resource => {
    expect(validateResearchResource(resource)).toBeNull();
  });
});

it("rejects unreviewed metadata fields", () => {
  const id = `rvitem.v1.${"a".repeat(64)}`;
  expect(() => decodeEvidenceItem({ id, title: "Source", text: "Literal", url: evidenceUrl(id),
    metadata: { coverage: "COMPLETE_BOUNDED_ITEM", source_url: "r2://private" } }, id)).toThrow();
});
