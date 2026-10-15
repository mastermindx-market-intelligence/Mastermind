/** TSX corpus: exercises the .tsx path through the same consumer. */

import { consume } from "./consumer";

export function ProducerBadge(): JSX.Element {
  return <span className="producer-badge">{consume()}</span>;
}
