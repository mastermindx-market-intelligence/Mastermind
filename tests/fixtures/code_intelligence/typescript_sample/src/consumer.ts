/** Consumer corpus: imports only the live wrapper. */

import { makeProducer } from "./producer";

export function consume(): string {
  return makeProducer().produce();
}

export function brokenHelper(): string {
  // Planted, deterministic undefined-name diagnostic. Exactly one per corpus.
  return undefinedSymbolForDiagnostics;
}
