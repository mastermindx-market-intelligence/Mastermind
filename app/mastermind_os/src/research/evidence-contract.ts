import { ORIGIN } from "../public-config";

export const EVIDENCE_PATH = "/os/research/evidence/";
export const EVIDENCE_BODY_BYTES = 16000;
const ID = /^rvitem\.v1\.[0-9a-f]{64}$/;

/** A capability of the existing private token owner, never a token or grant. */
export interface ResearchEvidenceTransport {
  authGeneration(): number;
  available(): boolean;
  subscribe(listener: () => void): () => void;
  signIn(): Promise<unknown>;
  readEvidenceItem(itemId: string, signal: AbortSignal): Promise<unknown>;
}

export interface EvidenceItem {
  id: string;
  title: string;
  text: string;
  url: string;
}

export function validEvidenceId(value: unknown): value is string {
  return typeof value === "string" && value.length === 74 && ID.test(value);
}

export function evidenceUrl(itemId: string): string {
  if (!validEvidenceId(itemId)) throw new Error("EVIDENCE_ITEM_INVALID");
  return `${ORIGIN}${EVIDENCE_PATH}${itemId}`;
}

export function evidenceRoute(location: Pick<Location, "origin" | "pathname" | "search" | "hash">): string | null {
  if (location.origin !== ORIGIN || location.search || location.hash ||
      !location.pathname.startsWith(EVIDENCE_PATH)) return null;
  const id = location.pathname.slice(EVIDENCE_PATH.length);
  return validEvidenceId(id) ? id : null;
}

function scalarText(value: unknown): value is string {
  if (typeof value !== "string") return false;
  // TextEncoder replaces lone surrogates; reject rather than silently changing bytes.
  for (const scalar of value) {
    const point = scalar.codePointAt(0)!;
    if (point >= 0xd800 && point <= 0xdfff) return false;
  }
  return true;
}

/** Conditional protocol decoder. Canonical replay and current grants are server-owned. */
export function decodeEvidenceItem(value: unknown, expectedId: string): EvidenceItem {
  const refuse = (): never => { throw new Error("EVIDENCE_RESPONSE_INVALID"); };
  if (!validEvidenceId(expectedId) || !value || typeof value !== "object" || Array.isArray(value)) return refuse();
  const row = value as Record<string, unknown>;
  if (Object.keys(row).sort().join(",") !== "id,metadata,text,title,url" ||
      row.id !== expectedId || row.url !== evidenceUrl(expectedId) ||
      !scalarText(row.title) || !row.title.trim() || row.title.length > 1000 ||
      !scalarText(row.text) || !row.text || new TextEncoder().encode(row.text).byteLength > 1000 ||
      !row.metadata || typeof row.metadata !== "object" || Array.isArray(row.metadata) ||
      Object.keys(row.metadata).join(",") !== "coverage" ||
      (row.metadata as Record<string, unknown>).coverage !== "COMPLETE_BOUNDED_ITEM") return refuse();
  // Unknown provenance fields are not displayed, interpreted as authority, or retained.
  return { id: expectedId, title: row.title, text: row.text, url: row.url as string };
}
