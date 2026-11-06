import { describe, expect, it } from 'vitest';

import {
  decodeProjectArchive,
  type AvailableArchiveRead,
  type ProjectArchiveRead,
} from './project-archive';

const BODY_SCHEMA = 'mastermind.workspace_project_archive.v1';
const SAMPLE_SCHEMA = 'agentos.project_archive_sample.v1';
const ARCHIVE_SCHEMA = 'agentos.workstream_archive.v1';
const DOCUMENT_DIGEST = 'f38a9c7d61e24b508ac37d92e1f04b6a5d8c92e71f43a0b96d5e8c71f20a43b9';
const OTHER_DIGEST = '0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0';
const MACRO_SHA = '9c41d7e2b8a05f36c19d4e8b72fa05c31d8e94b6';
const OTHER_MACRO_SHA = '5b2e8f41a7c30d96e15b84f72ac60d39e84b17a5';
const CONTENT_SHA = '3f9c1d7e5a28b40691cd73e52f80a46b19d7c3e58a20f46b93d71e502ac84b67';

type Body = Record<string, unknown>;

function part(value: unknown): Body {
  return value as Body;
}

function sampleItems(body: Body): Body[] { return part(body.sample).items as Body[]; }

function expectInvalid(body: unknown): void {
  expect(() => decodeProjectArchive(body)).toThrowError('PROJECT_ARCHIVE_INVALID');
}

function archiveItem(workName: string, overrides: Body = {}): Body {
  const workRef = `WS:${workName}`;
  return {
    work_ref: workRef,
    title: 'Quarterly reconciliation pass',
    objective: 'Archive the completed workstream for bounded later reads.',
    archive: {
      schema: ARCHIVE_SCHEMA,
      state: 'ARCHIVED',
      archived_on: '2026-03-14',
      archived_by: 'sol-operating-executive',
      reason: 'Delivery accepted; retained for bounded archival reads.',
    },
    source: {
      repository: 'macro',
      commit: MACRO_SHA,
      path: `agentos/workstreams/WS-${workName}.md`,
      content_sha256: CONTENT_SHA,
    },
    ...overrides,
  };
}

function availableBody(): Body {
  return {
    schema: BODY_SCHEMA,
    availability: 'AVAILABLE',
    catalogue: {
      document_digest: DOCUMENT_DIGEST,
      macro_sha: MACRO_SHA,
      work_refs: ['WS:ALPHA-1', 'WS:BETA-2'],
      qualified_catalogue_count: 2,
    },
    sample: {
      schema: SAMPLE_SCHEMA,
      source_commit: MACRO_SHA,
      coverage: {
        kind: 'QUALIFIED_CATALOGUE_SAMPLE',
        supplied_count: 2,
        observed_count: 2,
        company_total: null,
      },
      availability: 'AVAILABLE',
      reason: null,
      items: [archiveItem('ALPHA-1')],
      can_restore: false,
    },
    reason_codes: [],
  };
}

function unavailableBody(reason = 'SOURCE_UNAVAILABLE'): Body {
  return {
    schema: BODY_SCHEMA,
    availability: 'UNAVAILABLE',
    catalogue: null,
    sample: null,
    reason_codes: [reason],
  };
}

function linkSampleToRefs(body: Body, refs: string[]): void {
  part(body.catalogue).work_refs = refs;
  part(body.catalogue).qualified_catalogue_count = refs.length;
  const sample = part(body.sample);
  sample.source_commit = part(body.catalogue).macro_sha;
  part(sample.coverage).supplied_count = refs.length;
  part(sample.coverage).observed_count = refs.length;
}

describe('decodeProjectArchive', () => {
  it('decodes a real-shaped available read with two refs and one archived item', () => {
    const decoded: ProjectArchiveRead = decodeProjectArchive(availableBody());
    expect(decoded.availability).toBe('AVAILABLE');
    const available = decoded as AvailableArchiveRead;
    expect(available.schema).toBe(BODY_SCHEMA);
    expect(available.reason_codes).toEqual([]);
    expect(available.catalogue).toEqual({
      document_digest: DOCUMENT_DIGEST,
      macro_sha: MACRO_SHA,
      work_refs: ['WS:ALPHA-1', 'WS:BETA-2'],
      qualified_catalogue_count: 2,
    });
    expect(available.sample.schema).toBe(SAMPLE_SCHEMA);
    expect(available.sample.source_commit).toBe(MACRO_SHA);
    expect(available.sample.coverage).toEqual({
      kind: 'QUALIFIED_CATALOGUE_SAMPLE',
      supplied_count: 2,
      observed_count: 2,
      company_total: null,
    });
    expect(available.sample.availability).toBe('AVAILABLE');
    expect(available.sample.reason).toBeNull();
    expect(available.sample.can_restore).toBe(false);
    expect(available.sample.items).toHaveLength(1);
    expect(available.sample.items[0]).toEqual({
      work_ref: 'WS:ALPHA-1',
      title: 'Quarterly reconciliation pass',
      objective: 'Archive the completed workstream for bounded later reads.',
      archive: {
        schema: ARCHIVE_SCHEMA,
        state: 'ARCHIVED',
        archived_on: '2026-03-14',
        archived_by: 'sol-operating-executive',
        reason: 'Delivery accepted; retained for bounded archival reads.',
      },
      source: {
        repository: 'macro',
        commit: MACRO_SHA,
        path: 'agentos/workstreams/WS-ALPHA-1.md',
        content_sha256: CONTENT_SHA,
      },
    });
  });

  it('decodes an available read with an empty sample and preserves company_total null', () => {
    const body = availableBody();
    linkSampleToRefs(body, []);
    part(body.sample).items = [];
    const decoded = decodeProjectArchive(body) as AvailableArchiveRead;
    expect(decoded.sample.items).toEqual([]);
    expect(decoded.catalogue.work_refs).toEqual([]);
    expect(decoded.catalogue.qualified_catalogue_count).toBe(0);
    expect(decoded.sample.coverage.company_total).toBeNull();
    expect(decoded.sample.coverage.supplied_count).toBe(0);
    expect(decoded.sample.coverage.observed_count).toBe(0);
    expect(decoded.sample.can_restore).toBe(false);
    expect(decoded.reason_codes).toEqual([]);
  });

  it('decodes unavailable reads with a single known reason code and null data', () => {
    for (const reason of ['SOURCE_UNAVAILABLE', 'SOURCE_CHANGED', 'CONTENT_OVER_BUDGET']) {
      const decoded = decodeProjectArchive(unavailableBody(reason));
      expect(decoded.availability).toBe('UNAVAILABLE');
      expect(decoded.catalogue).toBeNull();
      expect(decoded.sample).toBeNull();
      expect(decoded.reason_codes).toEqual([reason]);
    }
    expectInvalid(unavailableBody('ARCHIVE_DONE'));
    expectInvalid(unavailableBody('source_unavailable'));
    expectInvalid(unavailableBody(''));
  });

  it('rejects reason_codes lists that are not exactly one known code', () => {
    const empty = unavailableBody();
    empty.reason_codes = [];
    expectInvalid(empty);
    const doubled = unavailableBody();
    doubled.reason_codes = ['SOURCE_UNAVAILABLE', 'SOURCE_CHANGED'];
    expectInvalid(doubled);
    const missing = unavailableBody();
    delete missing.reason_codes;
    expectInvalid(missing);
  });

  it('rejects non-object and wrongly shaped inputs', () => {
    for (const bad of [null, undefined, 7, 'body', true, [], [availableBody()]]) {
      expectInvalid(bad);
    }
    const wrongSchema = availableBody();
    wrongSchema.schema = 'mastermind.workspace_project_chat.v1';
    expectInvalid(wrongSchema);
  });

  it('never infers availability from done, parked or chat-archive shapes', () => {
    const done = availableBody();
    done.availability = 'DONE';
    expectInvalid(done);
    const parked = availableBody();
    parked.availability = 'PARKED';
    expectInvalid(parked);
    const chat = availableBody();
    chat.availability = 'ARCHIVED_IN_CHAT';
    expectInvalid(chat);
  });

  it('rejects unknown private fields at every level', () => {
    const top = availableBody();
    top.internal_note = 'done';
    expectInvalid(top);

    const catalogueExtra = availableBody();
    part(catalogueExtra.catalogue).selector = 'ws:*';
    expectInvalid(catalogueExtra);

    const sampleExtra = availableBody();
    part(sampleExtra.sample).restored_hint = true;
    expectInvalid(sampleExtra);

    const coverageExtra = availableBody();
    part(part(coverageExtra.sample).coverage).company_zero = 0;
    expectInvalid(coverageExtra);

    const itemExtra = availableBody();
    part(sampleItems(itemExtra)[0]).chat_archive = true;
    expectInvalid(itemExtra);

    const archiveExtra = availableBody();
    part(part(sampleItems(archiveExtra)[0]).archive).state_hint = 'DONE';
    expectInvalid(archiveExtra);

    const sourceExtra = availableBody();
    part(part(sampleItems(sourceExtra)[0]).source).branch = 'main';
    expectInvalid(sourceExtra);
  });

  it('rejects missing required keys at every level', () => {
    const noCatalogue = availableBody();
    delete noCatalogue.catalogue;
    expectInvalid(noCatalogue);

    const noDigest = availableBody();
    delete part(noDigest.catalogue).document_digest;
    expectInvalid(noDigest);

    const noCoverage = availableBody();
    delete part(noCoverage.sample).coverage;
    expectInvalid(noCoverage);

    const noCanRestore = availableBody();
    delete part(noCanRestore.sample).can_restore;
    expectInvalid(noCanRestore);

    const noArchive = availableBody();
    delete part(sampleItems(noArchive)[0]).archive;
    expectInvalid(noArchive);

    const noSource = availableBody();
    delete part(sampleItems(noSource)[0]).source;
    expectInvalid(noSource);
  });

  it('rejects foreign, duplicate and unlinked sample items', () => {
    const foreign = availableBody();
    part(foreign.sample).items = [archiveItem('GAMMA-9')];
    expectInvalid(foreign);

    const duplicate = availableBody();
    part(duplicate.sample).items = [archiveItem('ALPHA-1'), archiveItem('ALPHA-1')];
    expectInvalid(duplicate);

    const overflow = availableBody();
    linkSampleToRefs(overflow, ['WS:ALPHA-1']);
    part(overflow.sample).items = [archiveItem('ALPHA-1'), archiveItem('BETA-2')];
    expectInvalid(overflow);
  });

  it('rejects duplicate or unsorted catalogue refs', () => {
    const duplicated = availableBody();
    part(duplicated.catalogue).work_refs = ['WS:ALPHA-1', 'WS:ALPHA-1'];
    expectInvalid(duplicated);

    const unsorted = availableBody();
    part(unsorted.catalogue).work_refs = ['WS:BETA-2', 'WS:ALPHA-1'];
    expectInvalid(unsorted);

    const malformedRef = availableBody();
    part(malformedRef.catalogue).work_refs = ['WS:ALPHA-1', 'chat:ALPHA-1'];
    expectInvalid(malformedRef);
  });

  it('rejects coverage counts that do not link to the catalogue', () => {
    const suppliedMismatch = availableBody();
    part(part(suppliedMismatch.sample).coverage).supplied_count = 1;
    expectInvalid(suppliedMismatch);

    const observedMismatch = availableBody();
    part(part(observedMismatch.sample).coverage).observed_count = 3;
    expectInvalid(observedMismatch);

    const qualifiedTooLow = availableBody();
    part(qualifiedTooLow.catalogue).qualified_catalogue_count = 1;
    expectInvalid(qualifiedTooLow);

    const qualifiedTooHigh = availableBody();
    part(qualifiedTooHigh.catalogue).qualified_catalogue_count = 501;
    expectInvalid(qualifiedTooHigh);

    const fractional = availableBody();
    part(fractional.catalogue).qualified_catalogue_count = 2.5;
    expectInvalid(fractional);

    const numericBoolean = availableBody();
    part(part(numericBoolean.sample).coverage).supplied_count = true;
    expectInvalid(numericBoolean);

    const stringCount = availableBody();
    part(part(stringCount.sample).coverage).observed_count = '2';
    expectInvalid(stringCount);
  });

  it('rejects catalogue, source commit, path and hash mismatches', () => {
    const sampleCommit = availableBody();
    part(sampleCommit.sample).source_commit = OTHER_MACRO_SHA;
    expectInvalid(sampleCommit);

    const recatalogued = availableBody();
    part(recatalogued.catalogue).macro_sha = OTHER_MACRO_SHA;
    expectInvalid(recatalogued);

    const itemCommit = availableBody();
    part(part(sampleItems(itemCommit)[0]).source).commit = OTHER_MACRO_SHA;
    expectInvalid(itemCommit);

    const itemPath = availableBody();
    part(part(sampleItems(itemPath)[0]).source).path = 'agentos/workstreams/WS-OTHER.md';
    expectInvalid(itemPath);

    const itemRefPath = availableBody();
    part(part(sampleItems(itemRefPath)[0])).work_ref = 'WS:BETA-2';
    expectInvalid(itemRefPath);

    const repository = availableBody();
    part(part(sampleItems(repository)[0]).source).repository = 'minio';
    expectInvalid(repository);

    const shortDigest = availableBody();
    part(shortDigest.catalogue).document_digest = OTHER_DIGEST.slice(0, 63);
    expectInvalid(shortDigest);

    const malformedMacroSha = availableBody();
    part(malformedMacroSha.catalogue).macro_sha = 'ZZZ';
    expectInvalid(malformedMacroSha);

    const upperHex = availableBody();
    part(part(sampleItems(upperHex)[0]).source).content_sha256 = CONTENT_SHA.toUpperCase();
    expectInvalid(upperHex);
  });

  it('accepts real leap days and rejects impossible DAY dates and year zero', () => {
    const leap = availableBody();
    part(part(sampleItems(leap)[0]).archive).archived_on = '2024-02-29';
    const leapDecoded = decodeProjectArchive(leap) as AvailableArchiveRead;
    expect(leapDecoded.sample.items[0]?.archive.archived_on).toBe('2024-02-29');

    const century = availableBody();
    part(part(sampleItems(century)[0]).archive).archived_on = '2000-02-29';
    expect(decodeProjectArchive(century)).toBeDefined();

    for (const badDay of [
      '2026-13-01',
      '2026-00-10',
      '2026-04-31',
      '2026-02-30',
      '2023-02-29',
      '1900-02-29',
      '0000-01-01',
      '2026-3-14',
      '2026-03-14T00:00:00Z',
      'not-a-day',
    ]) {
      const body = availableBody();
      part(part(sampleItems(body)[0]).archive).archived_on = badDay;
      expectInvalid(body);
    }
  });

  it('enforces UTF-8 byte budgets and rejects blank text fields', () => {
    const atLimit = availableBody();
    part(part(sampleItems(atLimit)[0])).title = 'é'.repeat(2048);
    expect(decodeProjectArchive(atLimit)).toBeDefined();

    const overBytes = availableBody();
    part(part(sampleItems(overBytes)[0])).title = 'é'.repeat(2049);
    expectInvalid(overBytes);

    const blankActor = availableBody();
    part(part(sampleItems(blankActor)[0]).archive).archived_by = '   ';
    expectInvalid(blankActor);

    const blankReason = availableBody();
    part(part(sampleItems(blankReason)[0]).archive).reason = '';
    expectInvalid(blankReason);

    const blankTitle = availableBody();
    part(part(sampleItems(blankTitle)[0])).title = '\n\t ';
    expectInvalid(blankTitle);

    const longActor = availableBody();
    part(part(sampleItems(longActor)[0]).archive).archived_by = 's'.repeat(257);
    expectInvalid(longActor);

    const longObjective = availableBody();
    part(part(sampleItems(longObjective)[0])).objective = 'o'.repeat(16385);
    expectInvalid(longObjective);
  });

  it('rejects unpaired UTF-16 surrogates and accepts well-formed multibyte text', () => {
    const loneHigh = availableBody();
    part(part(sampleItems(loneHigh)[0])).objective = 'completed \ud800 pass';
    expectInvalid(loneHigh);

    const loneLow = availableBody();
    part(part(sampleItems(loneLow)[0])).title = 'tail\udc00';
    expectInvalid(loneLow);

    const trailingHigh = availableBody();
    part(part(sampleItems(trailingHigh)[0]).archive).archived_by = 'sol \udfff';
    expectInvalid(trailingHigh);

    const paired = availableBody();
    part(part(sampleItems(paired)[0])).title = 'archive 👁 lens';
    expect(decodeProjectArchive(paired)).toBeDefined();
  });

  it('rejects numerical or string stand-ins for literal booleans and nulls', () => {
    const numericFalse = availableBody();
    part(numericFalse.sample).can_restore = 0;
    expectInvalid(numericFalse);

    const trueRestore = availableBody();
    part(trueRestore.sample).can_restore = true;
    expectInvalid(trueRestore);

    const zeroCompany = availableBody();
    part(part(zeroCompany.sample).coverage).company_total = 0;
    expectInvalid(zeroCompany);

    const stringCompany = availableBody();
    part(part(stringCompany.sample).coverage).company_total = 'unknown';
    expectInvalid(stringCompany);

    const stringReason = availableBody();
    part(stringReason.sample).reason = 'none';
    expectInvalid(stringReason);

    const unavailableLike = availableBody();
    part(unavailableLike.sample).reason = null;
    part(unavailableLike.sample).coverage = null;
    expectInvalid(unavailableLike);
  });

  it('rejects bodies whose serialized envelope exceeds the response budget', () => {
    const body = availableBody();
    linkSampleToRefs(body, buildRefs(24));
    part(body.sample).items = buildRefs(24).map((ref) =>
      archiveItem(ref.slice(3), { objective: 'x'.repeat(16384) }),
    );
    expectInvalid(body);
  });

  it('still accepts large but in-budget bodies', () => {
    const refs = buildRefs(4);
    const body = availableBody();
    linkSampleToRefs(body, refs);
    part(body.sample).items = refs.map((ref) =>
      archiveItem(ref.slice(3), { objective: 'x'.repeat(16384) }),
    );
    const decoded = decodeProjectArchive(body) as AvailableArchiveRead;
    expect(decoded.sample.items).toHaveLength(4);
    expect(decoded.sample.coverage.observed_count).toBe(4);
  });

  it('returns defensive copies independent of the input and of each other', () => {
    const body = availableBody();
    const first = decodeProjectArchive(body) as AvailableArchiveRead;
    const second = decodeProjectArchive(body) as AvailableArchiveRead;
    expect(first).not.toBe(second);
    expect(first.sample.items[0]).not.toBe(second.sample.items[0]);
    expect(first).toEqual(second);

    sampleItems(body).push(archiveItem('BETA-2'));
    (part(body.catalogue).work_refs as string[]).push('WS:GAMMA-3');
    expect(first).toEqual(second);
    expect(first.sample.items).toHaveLength(1);
    expect(first.catalogue.work_refs).toEqual(['WS:ALPHA-1', 'WS:BETA-2']);

    const decoded = decodeProjectArchive(availableBody()) as AvailableArchiveRead;
    decoded.catalogue.work_refs.push('WS:ZED-9');
    decoded.sample.items.pop();
    decoded.sample.coverage.company_total = null;
    const fresh = decodeProjectArchive(availableBody()) as AvailableArchiveRead;
    expect(fresh.catalogue.work_refs).toEqual(['WS:ALPHA-1', 'WS:BETA-2']);
    expect(fresh.sample.items).toHaveLength(1);
  });

  it('decodes a deep-frozen input without mutating it', () => {
    const frozen: Body = JSON.parse(JSON.stringify(availableBody())) as Body;
    Object.freeze(frozen);
    Object.freeze(part(frozen.catalogue));
    Object.freeze(part(frozen.sample));
    Object.freeze(part(part(frozen.sample).coverage));
    Object.freeze(part(frozen.sample).items);
    Object.freeze(part(part(sampleItems(frozen)[0]).archive));
    Object.freeze(part(part(sampleItems(frozen)[0]).source));
    const decoded = decodeProjectArchive(frozen) as AvailableArchiveRead;
    expect(decoded.sample.items).toHaveLength(1);
    expect(part(frozen.sample).items).toHaveLength(1);
  });
});

function buildRefs(count: number): string[] {
  const refs: string[] = [];
  for (let index = 0; index < count; index += 1) {
    refs.push(`WS:R${String(index).padStart(3, '0')}`);
  }
  return refs;
}


it('matches canonical upper-kebab2..64 work refs and rejects newline digest/date aliases', () => {
  for (const key of ['AA', 'A'.repeat(64)]) {
    const body = availableBody(); part(body.catalogue).work_refs = ['WS:' + key];
    part(part(body.sample).coverage).supplied_count = 1; part(part(body.sample).coverage).observed_count = 1;
    part(body.sample).items = [archiveItem(key)];
    expect(decodeProjectArchive(body).availability).toBe('AVAILABLE');
  }
  for (const key of ['A', 'A'.repeat(65), 'lower', 'AA.BB', 'AA_BB', 'AA--BB', 'AA\n']) {
    const body = availableBody(); part(body.catalogue).work_refs = ['WS:' + key];
    part(part(body.sample).coverage).supplied_count = 1; part(part(body.sample).coverage).observed_count = 1;
    part(body.sample).items = [archiveItem(key)]; expectInvalid(body);
  }
  const digest = availableBody(); part(digest.catalogue).document_digest = DOCUMENT_DIGEST + '\n'; expectInvalid(digest);
  const day = availableBody(); part(sampleItems(day)[0]!.archive).archived_on = '2026-11-04\n'; expectInvalid(day);
});

it('never exposes thrown getters or prototype trap text from invalid input', () => {
  const hostile = new Proxy({}, { getPrototypeOf: () => { throw new Error('PRIVATE_SOURCE_VALUE'); } });
  expect(() => decodeProjectArchive(hostile)).toThrowError(/^PROJECT_ARCHIVE_INVALID$/);
});
