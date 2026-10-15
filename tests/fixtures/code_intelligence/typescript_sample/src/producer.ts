/**
 * Producer corpus: one interface, one live implementation, one dead sibling.
 *
 * The dead sibling is deliberately near-identical to the live one so that a
 * name-only text search cannot tell them apart. Only a semantic backend that
 * understands imports and types can say which one the consumer reaches.
 */

export interface Producer {
  produce(): string;
}

export class LiveProducer implements Producer {
  produce(): string {
    return "live";
  }
}

export class DeadProducer implements Producer {
  produce(): string {
    return "dead";
  }
}

export function makeProducer(): Producer {
  return new LiveProducer();
}

export function makeDeadProducer(): Producer {
  return new DeadProducer();
}
