/**
 * Corpus module: imports the consumer, giving find_references a third hop.
 *
 * Deliberately NOT named `test_*.py` and not a Python module at all, so the
 * repository gate cannot discover it.
 */

import { consume } from "../src/consumer";

export function expectsLive(): boolean {
  return consume() === "live";
}
