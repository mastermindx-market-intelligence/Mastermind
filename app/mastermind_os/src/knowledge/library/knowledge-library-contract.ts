/**
 * Knowledge Library presentation contract.
 *
 * Typed DTOs, strict closed validators and safe unavailable builders for the
 * read-only Knowledge Files / Memory / records slice. Backend JSON shapes are
 * frozen upstream; this module never mutates a raw payload, only validates it
 * into detached, deeply frozen plain data or throws a typed contract error.
 *
 * This leaf owns no upload, publication, auth or storage authority. It is a
 * consumer of owner-supplied read ports only.
 */

import type { ReactNode } from 'react';
import {knowledgeReadKeys,validateKnowledgeReadMetadata,type ProjectKnowledgeReadMetadata,type ProjectKnowledgeCodeContext} from './project-data-observation';
import type {ProjectSourceDraftPort} from './project-source-draft';
import type {ProjectFileMatch,ProjectFileSearchOwner} from '../../discovery/project-file-search';

/* ------------------------------------------------------------------ */
/* Scalars and closed vocabularies                                     */
/* ------------------------------------------------------------------ */

export type KnowledgeLibraryLocale = 'en' | 'zh-CN';
export type KnowledgeLibraryTheme = 'dark' | 'light';

export type KnowledgeRepository = 'mastermindx-market-intelligence/macro';
export const KNOWLEDGE_REPOSITORY: KnowledgeRepository = 'mastermindx-market-intelligence/macro';

export type KnowledgeFileRepository = 'macro' | 'terminal' | 'mastermind';
export type KnowledgeMediaType = 'text/markdown' | 'text/plain';

export type KnowledgeFileState =
  | 'READABLE'
  | 'SOURCE_MISSING'
  | 'SOURCE_INVALID'
  | 'CONTENT_OVER_BUDGET'
  | 'UNSUPPORTED_SOURCE';

export type KnowledgeFileOriginKind = 'PRINCIPAL_UPLOAD' | 'DECLARED_ARTIFACT';
export type KnowledgeViewerRelation = 'UNKNOWN' | 'CURRENT_PRINCIPAL' | 'OTHER_PRINCIPAL';

export type KnowledgeRecordKind =
  | 'WORKSTREAM'
  | 'DECISION'
  | 'DISCOVERY'
  | 'HANDOFF'
  | 'PROJECT_PREFERENCE';

export type KnowledgePreferenceOriginKind = 'USER_EDIT' | 'CONVERSATION';

export const KNOWLEDGE_CATALOGUE_SCHEMA = 'mastermind.workspace_project_knowledge.v1' as const;
export const KNOWLEDGE_SOURCE_SCHEMA = 'mastermind.workspace_project_source.v1' as const;
export const KNOWLEDGE_MEMORY_SCHEMA = 'mastermind.workspace_project_preference.v1' as const;
export const KNOWLEDGE_ACTIONS_SCHEMA = 'mastermind.project_knowledge_actions.v1' as const;

/** Closed set of backend reason codes. Anything else fails closed. */
export const KNOWLEDGE_REASON_CODES = [
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'RECORD_NOT_FOUND',
  'SOURCE_MISMATCH',
  'SOURCE_INVALID',
  'CONTENT_OVER_BUDGET',
  'RESPONSE_OVER_BUDGET',
  'UNSUPPORTED_SOURCE',
  'CONFLICT',
] as const;
export type KnowledgeReasonCode = (typeof KNOWLEDGE_REASON_CODES)[number];

/** UTF-8 byte budgets enforced by the validators. */
export const KNOWLEDGE_BUDGETS = {
  title: 200,
  displayName: 128,
  path: 512,
  actorRef: 200,
  preferenceValue: 2000,
  sourceContent: 32768,
} as const;

/* ------------------------------------------------------------------ */
/* Validated, detached plain-data DTOs                                 */
/* ------------------------------------------------------------------ */

export interface KnowledgeCatalogueFileRow {
  readonly sourceRef: string;
  readonly repository: KnowledgeFileRepository | null;
  readonly path: string | null;
  readonly revision: string | null;
  readonly displayName: string;
  readonly mediaType: KnowledgeMediaType | null;
  readonly contentSha256: string | null;
  readonly state: KnowledgeFileState;
  readonly origin: {
    readonly kind: KnowledgeFileOriginKind;
    readonly actorRef: string | null;
    readonly requestSha256: string | null;
  };
  readonly viewerRelation: KnowledgeViewerRelation;
}

export interface KnowledgeCatalogueRecordRow {
  readonly sourceRef: string;
  readonly path: string;
  readonly revision: string;
  readonly kind: KnowledgeRecordKind;
  readonly title: string;
  readonly authoredAt: string | null;
  readonly committedAt: string | null;
}

export interface KnowledgeCatalogue {
  readonly workRef: string;
  readonly availability: 'AVAILABLE';
  readonly sourceCommit: string;
  readonly workstreamSha256: string;
  readonly title: string;
  readonly files: readonly KnowledgeCatalogueFileRow[];
  readonly records: readonly KnowledgeCatalogueRecordRow[];
  readonly memory: {
    readonly state: 'AVAILABLE' | 'EMPTY' | 'UNAVAILABLE';
    readonly sourceRef: string | null;
    readonly revision: string | null;
  };
  readonly fileCoverage: {
    readonly state: 'COMPLETE' | 'PARTIAL';
    readonly declared: number;
    readonly listed: number;
    readonly omitted: number;
  };
  readonly recordCoverage: {
    readonly state: 'BOUNDED_SAMPLE';
    readonly scanned: number;
    readonly matched: number;
    readonly omitted: number;
    readonly invalid: number;
  };
}

export interface KnowledgeCatalogueResult extends ProjectKnowledgeReadMetadata {
  readonly availability: 'AVAILABLE' | 'UNAVAILABLE';
  readonly catalogue: KnowledgeCatalogue | null;
  readonly reasonCodes: readonly string[];
}

/** Immutable git-sourced pointer shared by the source and memory DTOs. */
export interface KnowledgeSourcePointer {
  readonly repository: KnowledgeRepository;
  readonly commit: string;
  readonly path: string;
  readonly revision: string;
  readonly contentSha256: string;
  readonly committedAt: string | null;
}

export interface KnowledgeSourceDocumentBody {
  readonly title: string;
  readonly mediaType: KnowledgeMediaType;
  readonly contentUtf8: string;
  readonly contentSha256: string;
}

export interface KnowledgeSourceResult extends ProjectKnowledgeReadMetadata {
  readonly availability: 'AVAILABLE' | 'UNAVAILABLE';
  readonly source: KnowledgeSourcePointer | null;
  readonly document: KnowledgeSourceDocumentBody | null;
  readonly reasonCodes: readonly string[];
}

export interface KnowledgePreferenceOrigin {
  readonly kind: KnowledgePreferenceOriginKind;
  readonly actorRef: string;
  readonly sourceRef: string | null;
  readonly sourceRevision: string | null;
}

export interface KnowledgePreferenceLastEdit {
  readonly actorRef: string;
  readonly requestSha256: string;
}

export interface KnowledgeMemoryValue {
  readonly value: string;
  readonly origin: KnowledgePreferenceOrigin;
  readonly lastEdit: KnowledgePreferenceLastEdit;
}

export interface KnowledgeMemoryResult extends ProjectKnowledgeReadMetadata {
  readonly availability: 'AVAILABLE' | 'EMPTY' | 'UNAVAILABLE';
  readonly source: KnowledgeSourcePointer | null;
  readonly memory: KnowledgeMemoryValue | null;
  readonly reasonCodes: readonly string[];
}

export interface KnowledgeActionsResult {
  readonly addFiles: 'AVAILABLE' | 'UNAVAILABLE';
  readonly editPreference: 'AVAILABLE' | 'UNAVAILABLE';
}

/** Typed parent handoff payload for an explicit edit-preference callback. */
export interface ProjectMemoryDocument {
  readonly source: KnowledgeSourcePointer;
  readonly sourceRef: string;
  readonly revision: string | null;
  readonly value: string;
  readonly origin: KnowledgePreferenceOrigin;
  readonly lastEdit: KnowledgePreferenceLastEdit;
}

/** Full validated source document handed to the parent companion slot. */
export interface ProjectSourceDocument {
  readonly workRef: string;
  readonly sourceRef: string;
  readonly title: string;
  readonly mediaType: KnowledgeMediaType;
  readonly contentUtf8: string;
  readonly contentSha256: string;
  readonly source: KnowledgeSourcePointer;
}

/** Exact typed context forwarded on Add files / Edit preference handoffs. */
export interface KnowledgeLibrarySourceContext {
  readonly workRef: string;
  readonly sourceCommit: string;
  readonly baseRevision: string;
}

/* ------------------------------------------------------------------ */
/* Owner read ports (parent-supplied; this leaf only calls them)        */
/* ------------------------------------------------------------------ */

export interface KnowledgeLibraryReadCatalogueRequest {
  readonly workRef: string;
  readonly signal: AbortSignal;
}

export interface KnowledgeLibraryReadSourceRequest {
  readonly workRef: string;
  readonly sourceRef: string;
  readonly expectedRevision: string;
  readonly signal: AbortSignal;
}

export interface KnowledgeLibraryReadMemoryRequest {
  readonly workRef: string;
  readonly signal: AbortSignal;
}

export interface KnowledgeLibraryReadActionsRequest {
  readonly workRef: string;
  readonly sourceCommit: string;
  readonly baseRevision: string;
  readonly signal: AbortSignal;
}

/** One currently mounted fixed catalogue owner, not a new read/grant. */
export interface KnowledgeLibrarySourceOwner {
  readonly codeContext?:()=>ProjectKnowledgeCodeContext|null;
  current(snapshot:KnowledgeLibrarySourceContext):KnowledgeLibrarySourceContext;
}
export interface KnowledgeLibraryProps {
  readonly onCurrentSourceOwner?: (owner:KnowledgeLibrarySourceOwner|null)=>void;
  readonly draftPort?: ProjectSourceDraftPort;
  /** Original explicit Search selection; always re-read through its real owner. */
  readonly requestedFile?: Readonly<{match:ProjectFileMatch;workRef:string;authGeneration:number;hostGeneration:string|number}>;
  readonly fileSearchOwner?: ProjectFileSearchOwner;
  readonly onReturnToSearch?: () => void;
  readonly workRef: string | null;
  readonly authGeneration: number;
  readonly hostGeneration: string | number | null;
  readonly locale?: KnowledgeLibraryLocale;
  readonly theme?: KnowledgeLibraryTheme;
  readonly refreshKey?: number;
  readonly readCatalogue?: (request: KnowledgeLibraryReadCatalogueRequest) => Promise<unknown>;
  readonly readSource?: (request: KnowledgeLibraryReadSourceRequest) => Promise<unknown>;
  readonly readMemory?: (request: KnowledgeLibraryReadMemoryRequest) => Promise<unknown>;
  readonly readActions?: (request: KnowledgeLibraryReadActionsRequest) => Promise<unknown>;
  readonly onAddFiles?: (context: KnowledgeLibrarySourceContext) => void;
  readonly onEditPreference?: (context: KnowledgeLibrarySourceContext, memory: ProjectMemoryDocument | null) => void;
  readonly renderSourceCompanion?: (source: ProjectSourceDocument) => ReactNode;
}

/* ------------------------------------------------------------------ */
/* Strict plain-data helpers                                           */
/* ------------------------------------------------------------------ */

export class KnowledgeContractError extends Error {
  readonly code: string;
  constructor(code: string, message?: string) {
    super(message === undefined ? code : message);
    this.name = 'KnowledgeContractError';
    this.code = code;
  }
}

const FORBIDDEN_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return false;
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) return false;
  if (Object.getOwnPropertySymbols(value).length > 0) return false;
  const keys = Object.getOwnPropertyNames(value);
  for (const key of keys) {
    if (FORBIDDEN_KEYS.has(key)) return false;
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || 'get' in descriptor || 'set' in descriptor) return false;
    if (!('value' in descriptor)) return false;
    if (!Object.prototype.propertyIsEnumerable.call(value, key)) return false;
  }
  return true;
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length) fail('EXTRA_KEYS');
  for (let i = 0; i < actual.length; i += 1) {
    if (actual[i] !== wanted[i]) fail('EXTRA_KEYS');
  }
}

/** Cycle-safe structural walk over already-proven plain records. */
function assertAcyclic(value: unknown, seen: Set<object>, budget = {left:8192}, depth=0): void {
  if (--budget.left < 0 || depth > 48) fail('CONTENT_OVER_BUDGET');
  if (typeof value === 'object' && value !== null) {
    if (seen.has(value)) fail('CYCLE');
    if (!Array.isArray(value) && !isPlainRecord(value)) fail('MALFORMED_PAYLOAD');
    const descriptors=Object.getOwnPropertyDescriptors(value);
    if (Reflect.ownKeys(descriptors).some(key => typeof key !== 'string')) fail('MALFORMED_PAYLOAD');
    seen.add(value);
    for (const [key, descriptor] of Object.entries(descriptors)) {
      if (!Object.hasOwn(descriptor,'value')) fail('MALFORMED_PAYLOAD');
      if (Array.isArray(value) && key === 'length') continue;
      assertAcyclic(descriptor.value, seen, budget, depth+1);
    }
    seen.delete(value);
  } else if (typeof value !== 'string' && typeof value !== 'number' && typeof value !== 'boolean' && value !== null) {
    fail('MALFORMED_PAYLOAD');
  }
}

function assertWireBudget(value: unknown): void {
  if(new TextEncoder().encode(JSON.stringify(value)).length+1>131_072) fail('RESPONSE_OVER_BUDGET');
}

const HEX_40 = /^[0-9a-f]{40}$/;
const HEX_64 = /^[0-9a-f]{64}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/;

function fail(code: string): never {
  throw new KnowledgeContractError(code);
}

/** Rejects lone surrogates: every string must be made of Unicode scalars. */
export function hasLoneSurrogates(text: string): boolean {
  for (let i = 0; i < text.length; i += 1) {
    const unit = text.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      if (i + 1 >= text.length) return true;
      const next = text.charCodeAt(i + 1);
      if (next < 0xdc00 || next > 0xdfff) return true;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function expectScalarString(value: unknown, code: string): string {
  if (typeof value !== 'string') fail(code);
  if (hasLoneSurrogates(value)) fail('UNSAFE_UNICODE');
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(value)) fail('UNSAFE_CONTROL');
  return value;
}

export function utf8ByteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

function expectBoundedString(value: unknown, maxUtf8: number, code: string, allowEmpty = false): string {
  const text = expectScalarString(value, code);
  if (!allowEmpty && text.trim().length === 0) fail(code);
  if (utf8ByteLength(text) > maxUtf8) fail('UTF8_OVER_BUDGET');
  return text;
}

function expectHex40(value: unknown, code: string): string {
  const text = expectScalarString(value, code);
  if (text.length!==40 || !HEX_40.test(text)) fail(code);
  return text;
}

function expectHex64(value: unknown, code: string): string {
  const text = expectScalarString(value, code);
  if (text.length!==64 || !HEX_64.test(text)) fail(code);
  return text;
}

function expectIsoDateOrNull(value: unknown, code: string): string | null {
  if (value === null) return null;
  const text = expectScalarString(value, code);
  if (!ISO_DATE.test(text) || !Number.isFinite(Date.parse(text+'T00:00:00Z')) || new Date(text+'T00:00:00Z').toISOString().slice(0,10)!==text) fail(code);
  return text;
}

function expectIsoUtcOrNull(value: unknown, code: string): string | null {
  if (value === null) return null;
  const text = expectScalarString(value, code);
  if (!ISO_UTC.test(text) || !Number.isFinite(Date.parse(text))) fail(code);
  expectIsoDateOrNull(text.slice(0,10),code);
  return text;
}

function expectInt(value: unknown, code: string, max?: number): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) fail(code);
  if (max !== undefined && value > max) fail(code);
  return value;
}

function expectEnum<T extends string>(value: unknown, allowed: readonly T[], code: string): T {
  if (typeof value !== 'string') fail(code);
  if (!(allowed as readonly string[]).includes(value)) fail(code);
  return value as T;
}

function expectClosedReasons(value: unknown, allowEmpty: boolean): readonly string[] {
  if (!Array.isArray(value)) fail('MALFORMED_REASON_CODES');
  if ((value.length === 0 && !allowEmpty) || value.length>KNOWLEDGE_REASON_CODES.length || new Set(value).size!==value.length) fail('MALFORMED_REASON_CODES');
  const codes: string[] = [];
  for (const entry of value) {
    const code = expectScalarString(entry, 'MALFORMED_REASON_CODES');
    if (!(KNOWLEDGE_REASON_CODES as readonly string[]).includes(code)) fail('UNKNOWN_REASON_CODE');
    codes.push(code);
  }
  return Object.freeze(codes);
}

function expectExactSchema(value: unknown, schema: string): void {
  if (typeof value !== 'string' || value !== schema) fail('SCHEMA_MISMATCH');
}

/** Deep detached, deeply frozen copy of already-validated plain data. */
export function cloneFrozen<T>(value: T): T {
  if (Array.isArray(value)) return Object.freeze((value as unknown[]).map(cloneFrozen)) as unknown as T;
  if (typeof value === 'object' && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) out[key] = cloneFrozen(child);
    return Object.freeze(out) as unknown as T;
  }
  return value;
}

/* ------------------------------------------------------------------ */
/* Catalogue validator: mastermind.workspace_project_knowledge.v1       */
/* ------------------------------------------------------------------ */

const AVAILABILITY = ['AVAILABLE', 'UNAVAILABLE'] as const;

function safeSourcePath(value: string): boolean {
  return /^(?:agentos|research|docs)\/[A-Za-z0-9][A-Za-z0-9._/-]*\.(?:md|txt)$/.exec(value)?.[0]===value
    && !value.includes('..') && !value.includes('//') && value.split('/').length<=16
    && !value.split('/').slice(1).some(part=>part.startsWith('.'));
}
function actor(value: unknown): string {
  const text=expectBoundedString(value,KNOWLEDGE_BUDGETS.actorRef,'MALFORMED_ACTOR');
  if(!/^workspace:[0-9a-f]{64}$/.test(text) || text.length!=='workspace:'.length+64) fail('MALFORMED_ACTOR');
  return text;
}

function sourceRef(value: unknown, prefix: 'file'|'record'): string {
  const text=expectScalarString(value,'MALFORMED_SOURCE_REF');
  if (text.length!==('project-'+prefix+'.v1.').length+64 || !new RegExp('^project-'+prefix+'\\.v1\\.[0-9a-f]{64}$').test(text)) fail('MALFORMED_SOURCE_REF');
  return text;
}

function validateFileRow(value: unknown): KnowledgeCatalogueFileRow {
  if (!isPlainRecord(value)) fail('MALFORMED_FILE_ROW');
  assertAcyclic(value, new Set());
  exactKeys(
    value,
    ['source_ref', 'repository', 'path', 'revision', 'display_name', 'media_type', 'content_sha256', 'state', 'origin', 'viewer_relation'],
  );
  const origin = value['origin'];
  if (!isPlainRecord(origin)) fail('MALFORMED_FILE_ROW');
  exactKeys(origin, ['kind', 'actor_ref', 'request_sha256']);
  const repository = value['repository'];
  if (repository !== null) {
    expectEnum(repository, ['macro', 'terminal', 'mastermind'], 'MALFORMED_FILE_ROW');
  }
  const path = value['path'];
  if (path !== null) expectBoundedString(path, KNOWLEDGE_BUDGETS.path, 'MALFORMED_FILE_ROW');
  const revision = value['revision'];
  if (revision !== null) expectHex40(revision, 'MALFORMED_FILE_ROW');
  const contentSha256 = value['content_sha256'];
  if (contentSha256 !== null) expectHex64(contentSha256, 'MALFORMED_FILE_ROW');
  const mediaType = value['media_type'];
  if (mediaType !== null) expectEnum(mediaType, ['text/markdown', 'text/plain'], 'MALFORMED_FILE_ROW');
  const requestSha256 = origin['request_sha256'];
  if (requestSha256 !== null) expectHex64(requestSha256, 'MALFORMED_FILE_ROW');
  const actorRef = origin['actor_ref'];
  if (actorRef !== null) expectBoundedString(actorRef, KNOWLEDGE_BUDGETS.actorRef, 'MALFORMED_FILE_ROW');
  const state=expectEnum(value['state'],['READABLE','SOURCE_MISSING','SOURCE_INVALID','CONTENT_OVER_BUDGET','UNSUPPORTED_SOURCE'],'MALFORMED_FILE_ROW');
  if(state==='READABLE' && (repository!=='macro' || typeof path!=='string' || !safeSourcePath(path) || revision===null || mediaType===null)) fail('MALFORMED_FILE_ROW');
  if(origin['kind']==='PRINCIPAL_UPLOAD'){
    actor(actorRef);if(requestSha256===null || contentSha256===null || typeof path!=='string') fail('MALFORMED_FILE_ROW');
    if(/[\/]/.test(value['display_name'] as string)) fail('MALFORMED_FILE_ROW');
  } else if(origin['kind']==='DECLARED_ARTIFACT' && (actorRef!==null || requestSha256!==null)) fail('MALFORMED_FILE_ROW');
  return cloneFrozen({
    sourceRef: sourceRef(value['source_ref'],'file'),
    repository: repository as KnowledgeFileRepository | null,
    path: path as string | null,
    revision: revision as string | null,
    displayName: expectBoundedString(value['display_name'], KNOWLEDGE_BUDGETS.displayName, 'MALFORMED_FILE_ROW'),
    mediaType: mediaType as KnowledgeMediaType | null,
    contentSha256: contentSha256 as string | null,
    state: expectEnum(
      value['state'],
      ['READABLE', 'SOURCE_MISSING', 'SOURCE_INVALID', 'CONTENT_OVER_BUDGET', 'UNSUPPORTED_SOURCE'],
      'MALFORMED_FILE_ROW',
    ),
    origin: {
      kind: expectEnum(origin['kind'], ['PRINCIPAL_UPLOAD', 'DECLARED_ARTIFACT'], 'MALFORMED_FILE_ROW'),
      actorRef: actorRef as string | null,
      requestSha256: requestSha256 as string | null,
    },
    viewerRelation: expectEnum(value['viewer_relation'], ['UNKNOWN'], 'MALFORMED_FILE_ROW'),
  });
}

function validateRecordRow(value: unknown): KnowledgeCatalogueRecordRow {
  if (!isPlainRecord(value)) fail('MALFORMED_RECORD_ROW');
  assertAcyclic(value, new Set());
  exactKeys(value, ['source_ref', 'path', 'revision', 'kind', 'title', 'authored_at', 'committed_at']);
  return cloneFrozen({
    sourceRef: sourceRef(value['source_ref'],'record'),
    path: expectBoundedString(value['path'], KNOWLEDGE_BUDGETS.path, 'MALFORMED_RECORD_ROW'),
    revision: expectHex40(value['revision'], 'MALFORMED_RECORD_ROW'),
    kind: expectEnum(
      value['kind'],
      ['WORKSTREAM', 'DECISION', 'DISCOVERY', 'HANDOFF', 'PROJECT_PREFERENCE'],
      'MALFORMED_RECORD_ROW',
    ),
    title: expectBoundedString(value['title'], KNOWLEDGE_BUDGETS.title, 'MALFORMED_RECORD_ROW'),
    authoredAt: expectIsoDateOrNull(value['authored_at'], 'MALFORMED_RECORD_ROW'),
    committedAt: expectIsoUtcOrNull(value['committed_at'], 'MALFORMED_RECORD_ROW'),
  });
}

/** Validates a catalogue read result against the exact expected work ref. */
export function validate_catalogue(raw: unknown, expectedWorkRef: string): KnowledgeCatalogueResult {
  if (!isPlainRecord(raw)) fail('MALFORMED_PAYLOAD');
  assertAcyclic(raw, new Set());
  assertWireBudget(raw);
  exactKeys(raw, knowledgeReadKeys(raw, ['schema', 'selection', 'availability', 'reason_codes', 'source', 'project']));
  const metadata=validateKnowledgeReadMetadata(raw, expectedWorkRef);
  expectExactSchema(raw['schema'], KNOWLEDGE_CATALOGUE_SCHEMA);
  const selection = raw['selection'];
  if (!isPlainRecord(selection)) fail('MALFORMED_PAYLOAD');
  exactKeys(selection, ['work_ref']);
  const workRef = expectScalarString(selection['work_ref'], 'MALFORMED_PAYLOAD');
  if (workRef !== expectedWorkRef || /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(workRef)?.[0]!==workRef || workRef.length<5 || workRef.length>67) fail('WORK_REF_MISMATCH');
  const availability = expectEnum(raw['availability'], AVAILABILITY, 'MALFORMED_PAYLOAD');

  if (availability === 'UNAVAILABLE') {
    if (raw['source'] !== null) fail('REASON_PAYLOAD_MISMATCH');
    if (raw['project'] !== null) fail('REASON_PAYLOAD_MISMATCH');
    return cloneFrozen({
      ...metadata, availability,
      catalogue: null,
      reasonCodes: expectClosedReasons(raw['reason_codes'], false),
    });
  }

  expectClosedReasons(raw['reason_codes'], true);
  const source = raw['source'];
  if (!isPlainRecord(source)) fail('MALFORMED_PAYLOAD');
  exactKeys(source, ['repository', 'commit', 'workstream_sha256']);
  if (source['repository'] !== KNOWLEDGE_REPOSITORY) fail('SCHEMA_MISMATCH');
  const sourceCommit = expectHex40(source['commit'], 'MALFORMED_PAYLOAD');
  const workstreamSha256 = expectHex64(source['workstream_sha256'], 'MALFORMED_PAYLOAD');

  const project = raw['project'];
  if (!isPlainRecord(project)) fail('MALFORMED_PAYLOAD');
  exactKeys(project, ['title', 'files', 'records', 'memory', 'coverage']);
  const title = expectBoundedString(project['title'], KNOWLEDGE_BUDGETS.title, 'MALFORMED_PAYLOAD');
  if (!Array.isArray(project['files']) || !Array.isArray(project['records'])) fail('MALFORMED_PAYLOAD');
  if (project['files'].length>32 || project['records'].length>64) fail('CONTENT_OVER_BUDGET');
  const files = Object.freeze(project['files'].map(validateFileRow));
  const records = Object.freeze(project['records'].map(validateRecordRow));
  for(const file of files){
    if(file.origin.kind==='PRINCIPAL_UPLOAD' && (file.repository!=='macro' || !new RegExp('^agentos/project-files/WS-'+workRef.slice(3)+'/[0-9a-f]{64}\\.(md|txt)$').test(file.path??''))) fail('MALFORMED_FILE_ROW');
  }
  for(const record of records){
    if(!safeSourcePath(record.path) || !/^agentos\/(?:workstreams|decisions|discoveries|handoffs)\/[A-Za-z0-9][A-Za-z0-9._-]*\.md$/.test(record.path)) fail('MALFORMED_RECORD_ROW');
    if(record.kind==='WORKSTREAM' && record.path!=='agentos/workstreams/WS-'+workRef.slice(3)+'.md') fail('MALFORMED_RECORD_ROW');
    if(record.kind==='PROJECT_PREFERENCE' && record.path!=='agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-'+workRef.slice(3)+'.md') fail('MALFORMED_RECORD_ROW');
  }
  const refs=[...files,...records].map(row=>row.sourceRef);
  if (new Set(refs).size!==refs.length) fail('DUPLICATE_SOURCE_REF');

  const memoryMeta = project['memory'];
  if (!isPlainRecord(memoryMeta)) fail('MALFORMED_PAYLOAD');
  exactKeys(memoryMeta, ['state', 'source_ref', 'revision']);
  const memoryState = expectEnum(memoryMeta['state'], ['AVAILABLE', 'EMPTY', 'UNAVAILABLE'], 'MALFORMED_PAYLOAD');
  const memorySourceRef = memoryMeta['source_ref'];
  if (memorySourceRef !== null && (typeof memorySourceRef !== 'string' ||
    !/^project-record\.v1\.[0-9a-f]{64}$/.test(memorySourceRef))) fail('MALFORMED_PAYLOAD');
  const memoryRevision = memoryMeta['revision'];
  if (memoryRevision !== null) expectHex40(memoryRevision, 'MALFORMED_PAYLOAD');
  if(memoryState==='AVAILABLE'){
    if(memorySourceRef===null || memoryRevision===null || !records.some(row=>row.sourceRef===memorySourceRef && row.revision===memoryRevision && row.kind==='PROJECT_PREFERENCE')) fail('MEMORY_SOURCE_MISMATCH');
  } else if(memorySourceRef!==null || memoryRevision!==null) fail('MEMORY_SOURCE_MISMATCH');

  const coverage = project['coverage'];
  if (!isPlainRecord(coverage)) fail('MALFORMED_PAYLOAD');
  exactKeys(coverage, ['files', 'records']);
  const fileCoverageRaw = coverage['files'];
  if (!isPlainRecord(fileCoverageRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(fileCoverageRaw, ['state', 'declared', 'listed', 'omitted']);
  const declared = expectInt(fileCoverageRaw['declared'], 'MALFORMED_PAYLOAD');
  const listed = expectInt(fileCoverageRaw['listed'], 'MALFORMED_PAYLOAD');
  const omitted = expectInt(fileCoverageRaw['omitted'], 'MALFORMED_PAYLOAD');
  if (omitted !== declared - listed || listed < 0 || declared < listed) fail('COVERAGE_CONTRADICTION');
  if (files.length !== listed) fail('COVERAGE_CONTRADICTION');
  expectEnum(fileCoverageRaw['state'], ['COMPLETE', 'PARTIAL'], 'MALFORMED_PAYLOAD');
  if (fileCoverageRaw['state'] === 'COMPLETE' && omitted !== 0) fail('COVERAGE_CONTRADICTION');

  const recordCoverageRaw = coverage['records'];
  if (!isPlainRecord(recordCoverageRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(recordCoverageRaw, ['state', 'scanned', 'matched', 'omitted', 'invalid']);
  const scanned = expectInt(recordCoverageRaw['scanned'], 'MALFORMED_PAYLOAD', 128);
  const matched = expectInt(recordCoverageRaw['matched'], 'MALFORMED_PAYLOAD', 64);
  const recordOmitted = expectInt(recordCoverageRaw['omitted'], 'MALFORMED_PAYLOAD');
  const invalid = expectInt(recordCoverageRaw['invalid'], 'MALFORMED_PAYLOAD');
  if (scanned<matched || matched<records.length || invalid>scanned || recordOmitted<matched-records.length) fail('COVERAGE_CONTRADICTION');
  expectEnum(recordCoverageRaw['state'], ['BOUNDED_SAMPLE'], 'MALFORMED_PAYLOAD');

  return cloneFrozen({
    ...metadata, availability,
    catalogue: {
      workRef,
      availability,
      sourceCommit,
      workstreamSha256,
      title,
      files,
      records,
      memory: {
        state: memoryState,
        sourceRef: memorySourceRef as string | null,
        revision: memoryRevision as string | null,
      },
      fileCoverage: {
        state: fileCoverageRaw['state'] as 'COMPLETE' | 'PARTIAL',
        declared,
        listed,
        omitted,
      },
      recordCoverage: {
        state: 'BOUNDED_SAMPLE',
        scanned,
        matched,
        omitted: recordOmitted,
        invalid,
      },
    },
    reasonCodes: Object.freeze([]),
  });
}

/* ------------------------------------------------------------------ */
/* Source validator: mastermind.workspace_project_source.v1            */
/* ------------------------------------------------------------------ */

function validateSourcePointer(value: unknown): KnowledgeSourcePointer {
  if (!isPlainRecord(value)) fail('MALFORMED_PAYLOAD');
  exactKeys(value, ['repository', 'commit', 'path', 'revision', 'content_sha256', 'committed_at']);
  if (value['repository'] !== KNOWLEDGE_REPOSITORY) fail('SCHEMA_MISMATCH');
  return cloneFrozen({
    repository: KNOWLEDGE_REPOSITORY,
    commit: expectHex40(value['commit'], 'MALFORMED_PAYLOAD'),
    path: (()=>{const path=expectBoundedString(value['path'],KNOWLEDGE_BUDGETS.path,'MALFORMED_PAYLOAD');if(!safeSourcePath(path)) fail('MALFORMED_PAYLOAD');return path;})(),
    revision: expectHex40(value['revision'], 'MALFORMED_PAYLOAD'),
    contentSha256: expectHex64(value['content_sha256'], 'MALFORMED_PAYLOAD'),
    committedAt: expectIsoUtcOrNull(value['committed_at'], 'MALFORMED_PAYLOAD'),
  });
}

/** Validates a source read result; digest verification happens separately. */
export function validate_source(
  raw: unknown,
  expectedWorkRef: string,
  expectedSourceRef: string,
): KnowledgeSourceResult {
  if (!isPlainRecord(raw)) fail('MALFORMED_PAYLOAD');
  assertAcyclic(raw, new Set());
  assertWireBudget(raw);
  exactKeys(raw, knowledgeReadKeys(raw, ['schema', 'selection', 'availability', 'reason_codes', 'source', 'document']));
  const metadata=validateKnowledgeReadMetadata(raw, expectedWorkRef);
  expectExactSchema(raw['schema'], KNOWLEDGE_SOURCE_SCHEMA);
  const selection = raw['selection'];
  if (!isPlainRecord(selection)) fail('MALFORMED_PAYLOAD');
  exactKeys(selection, ['work_ref', 'source_ref']);
  const workRef = expectScalarString(selection['work_ref'], 'MALFORMED_PAYLOAD');
  const sourceRef = expectScalarString(selection['source_ref'], 'MALFORMED_PAYLOAD');
  if (workRef !== expectedWorkRef || /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(workRef)?.[0]!==workRef || workRef.length<5 || workRef.length>67) fail('WORK_REF_MISMATCH');
  if (sourceRef !== expectedSourceRef) fail('SOURCE_REF_MISMATCH');
  const availability = expectEnum(raw['availability'], ['AVAILABLE', 'UNAVAILABLE'], 'MALFORMED_PAYLOAD');

  if (availability === 'UNAVAILABLE') {
    if (raw['source'] !== null || raw['document'] !== null) fail('REASON_PAYLOAD_MISMATCH');
    return cloneFrozen({
      ...metadata, availability,
      source: null,
      document: null,
      reasonCodes: expectClosedReasons(raw['reason_codes'], false),
    });
  }

  expectClosedReasons(raw['reason_codes'], true);
  const source = validateSourcePointer(raw['source']);
  const documentRaw = raw['document'];
  if (!isPlainRecord(documentRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(documentRaw, ['title', 'media_type', 'content_utf8', 'content_sha256']);
  const contentUtf8 = expectScalarString(documentRaw['content_utf8'], 'MALFORMED_PAYLOAD');
  if (utf8ByteLength(contentUtf8) > KNOWLEDGE_BUDGETS.sourceContent) fail('CONTENT_OVER_BUDGET');
  const document: KnowledgeSourceDocumentBody = cloneFrozen({
    title: expectBoundedString(documentRaw['title'], KNOWLEDGE_BUDGETS.title, 'MALFORMED_PAYLOAD'),
    mediaType: expectEnum(documentRaw['media_type'], ['text/markdown', 'text/plain'], 'MALFORMED_PAYLOAD'),
    contentUtf8,
    contentSha256: expectHex64(documentRaw['content_sha256'], 'MALFORMED_PAYLOAD'),
  });
  if (document.contentSha256 !== source.contentSha256) fail('DIGEST_MISMATCH');
  return cloneFrozen({ ...metadata, availability, source, document, reasonCodes: Object.freeze([]) });
}

/* ------------------------------------------------------------------ */
/* Memory validator: mastermind.workspace_project_preference.v1        */
/* ------------------------------------------------------------------ */

/** Validates a memory (project communication preference) read result. */
export function validate_memory(raw: unknown, expectedWorkRef: string): KnowledgeMemoryResult {
  if (!isPlainRecord(raw)) fail('MALFORMED_PAYLOAD');
  assertAcyclic(raw, new Set());
  assertWireBudget(raw);
  exactKeys(raw, knowledgeReadKeys(raw, ['schema', 'selection', 'availability', 'reason_codes', 'source', 'memory']));
  const metadata=validateKnowledgeReadMetadata(raw, expectedWorkRef);
  expectExactSchema(raw['schema'], KNOWLEDGE_MEMORY_SCHEMA);
  const selection = raw['selection'];
  if (!isPlainRecord(selection)) fail('MALFORMED_PAYLOAD');
  exactKeys(selection, ['work_ref']);
  const workRef = expectScalarString(selection['work_ref'], 'MALFORMED_PAYLOAD');
  if (workRef !== expectedWorkRef || /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(workRef)?.[0]!==workRef || workRef.length<5 || workRef.length>67) fail('WORK_REF_MISMATCH');
  const availability = expectEnum(raw['availability'], ['AVAILABLE', 'EMPTY', 'UNAVAILABLE'], 'MALFORMED_PAYLOAD');

  if (availability === 'UNAVAILABLE') {
    if (raw['source'] !== null || raw['memory'] !== null) fail('REASON_PAYLOAD_MISMATCH');
    return cloneFrozen({
      ...metadata, availability,
      source: null,
      memory: null,
      reasonCodes: expectClosedReasons(raw['reason_codes'], false),
    });
  }

  expectClosedReasons(raw['reason_codes'], true);
  if (raw['memory'] === null) {
    if (availability !== 'EMPTY') fail('REASON_PAYLOAD_MISMATCH');
    if(raw['source']!==null) fail('REASON_PAYLOAD_MISMATCH');
    return cloneFrozen({ ...metadata, availability, source:null, memory: null, reasonCodes: Object.freeze([]) });
  }

  const memoryRaw = raw['memory'];
  if (!isPlainRecord(memoryRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(memoryRaw, ['value', 'origin', 'last_edit']);
  const source = validateSourcePointer(raw['source']);
  const value = expectBoundedString(memoryRaw['value'], KNOWLEDGE_BUDGETS.preferenceValue, 'MALFORMED_PAYLOAD');
  const originRaw = memoryRaw['origin'];
  if (!isPlainRecord(originRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(originRaw, ['kind', 'actor_ref', 'source_ref', 'source_revision']);
  const kind = expectEnum(originRaw['kind'], ['USER_EDIT', 'CONVERSATION'], 'MALFORMED_PAYLOAD');
  const originSourceRef = originRaw['source_ref'];
  const originSourceRevision = originRaw['source_revision'];
  if (kind === 'USER_EDIT') {
    if (originSourceRef !== null || originSourceRevision !== null) fail('ORIGIN_MISMATCH');
  } else {
    if (originSourceRef === null || originSourceRevision === null) fail('ORIGIN_MISMATCH');
    if (typeof originSourceRef !== 'string' || originSourceRef.length!=='session-reply-'.length+64 || !/^session-reply-[0-9a-f]{64}$/.test(originSourceRef)) fail('MALFORMED_PAYLOAD');
    expectHex64(originSourceRevision, 'MALFORMED_PAYLOAD');
  }
  const lastEditRaw = memoryRaw['last_edit'];
  if (!isPlainRecord(lastEditRaw)) fail('MALFORMED_PAYLOAD');
  exactKeys(lastEditRaw, ['actor_ref', 'request_sha256']);
  const memory: KnowledgeMemoryValue = cloneFrozen({
    value,
    origin: {
      kind,
      actorRef: actor(originRaw['actor_ref']),
      sourceRef: originSourceRef as string | null,
      sourceRevision: originSourceRevision as string | null,
    },
    lastEdit: {
      actorRef: actor(lastEditRaw['actor_ref']),
      requestSha256: expectHex64(lastEditRaw['request_sha256'], 'MALFORMED_PAYLOAD'),
    },
  });
  return cloneFrozen({ ...metadata, availability, source, memory, reasonCodes: Object.freeze([]) });
}

/* ------------------------------------------------------------------ */
/* Actions validator: mastermind.project_knowledge_actions.v1          */
/* ------------------------------------------------------------------ */

/** Validates an actions read result against the exact snapshot identity. */
export function validate_actions(
  raw: unknown,
  expectedWorkRef: string,
  expectedSourceCommit: string,
  expectedBaseRevision: string,
): KnowledgeActionsResult {
  if (!isPlainRecord(raw)) fail('MALFORMED_PAYLOAD');
  assertAcyclic(raw, new Set());
  assertWireBudget(raw);
  exactKeys(raw, ['schema', 'selection', 'source_commit', 'base_revision', 'actions']);
  expectExactSchema(raw['schema'], KNOWLEDGE_ACTIONS_SCHEMA);
  const selection = raw['selection'];
  if (!isPlainRecord(selection)) fail('MALFORMED_PAYLOAD');
  exactKeys(selection, ['work_ref']);
  if (expectScalarString(selection['work_ref'], 'MALFORMED_PAYLOAD') !== expectedWorkRef) fail('WORK_REF_MISMATCH');
  if (expectHex40(raw['source_commit'], 'MALFORMED_PAYLOAD') !== expectedSourceCommit) fail('SNAPSHOT_MISMATCH');
  if (expectHex64(raw['base_revision'], 'MALFORMED_PAYLOAD') !== expectedBaseRevision) fail('SNAPSHOT_MISMATCH');
  const actions = raw['actions'];
  if (!isPlainRecord(actions)) fail('MALFORMED_PAYLOAD');
  exactKeys(actions, ['add_files', 'edit_preference']);
  return cloneFrozen({
    addFiles: expectEnum(actions['add_files'], ['AVAILABLE', 'UNAVAILABLE'], 'MALFORMED_PAYLOAD'),
    editPreference: expectEnum(actions['edit_preference'], ['AVAILABLE', 'UNAVAILABLE'], 'MALFORMED_PAYLOAD'),
  });
}

/* ------------------------------------------------------------------ */
/* Safe unavailable builders (typed owner-side diagnostics)            */
/* ------------------------------------------------------------------ */

/** Builds a typed owner-side unavailable result from closed reason codes. */
export function unavailableCatalogue(reasonCodes: readonly KnowledgeReasonCode[]): KnowledgeCatalogueResult {
  return Object.freeze({
    availability: 'UNAVAILABLE' as const,
    catalogue: null,
    reasonCodes: Object.freeze([...reasonCodes]),
  });
}

export function unavailableSource(reasonCodes: readonly KnowledgeReasonCode[]): KnowledgeSourceResult {
  return Object.freeze({
    availability: 'UNAVAILABLE' as const,
    source: null,
    document: null,
    reasonCodes: Object.freeze([...reasonCodes]),
  });
}

export function unavailableMemory(reasonCodes: readonly KnowledgeReasonCode[]): KnowledgeMemoryResult {
  return Object.freeze({
    availability: 'UNAVAILABLE' as const,
    source: null,
    memory: null,
    reasonCodes: Object.freeze([...reasonCodes]),
  });
}

export function unavailableActions(): KnowledgeActionsResult {
  return Object.freeze({ addFiles: 'UNAVAILABLE' as const, editPreference: 'UNAVAILABLE' as const });
}

/* ------------------------------------------------------------------ */
/* Digest helpers (WebCrypto over exact UTF-8)                         */
/* ------------------------------------------------------------------ */

/** SHA-256 over the exact UTF-8 encoding, lowercase hex. */
export async function sha256Hex(text: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new KnowledgeContractError('DIGEST_UNAVAILABLE');
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  let hex = '';
  for (const byte of new Uint8Array(digest)) hex += byte.toString(16).padStart(2, '0');
  return hex;
}

/* ------------------------------------------------------------------ */
/* Public copy (plain, EN / ZH-CN) — no raw identifiers                */
/* ------------------------------------------------------------------ */

export const KNOWLEDGE_LIBRARY_COPY = {
  en: {
    productLabel: 'Mastermind OS',
    fallbackTitle: 'Knowledge',
    filesTab: 'Files',
    memoryTab: 'Memory',
    addFiles: 'Add files',
    addFilesUnavailable: 'Adding files is not available right now.',
    open: 'Open',
    openUnavailable: 'Unavailable',
    back: 'Back',
    backToFiles: 'Back to files',
    browseAllRecords: 'Browse all records',
    backToLibrary: 'Back to library',
    recordsTitle: 'All records',
    queryLabel: 'Filter',
    queryFilesPlaceholder: 'Filter files by name',
    queryRecordsPlaceholder: 'Filter records by title, kind or date',
    filterScopeNote: 'Filters names, kinds and dates in the permitted sample. Not a full-text search.',
    partialNotice: 'Some sources are unavailable.',
    partialFilesDetail: (declared: number, listed: number) =>
      `Showing ${listed} of ${declared} declared files in the permitted scope.`,
    boundedRecordsNote: (matched: number, scanned: number) =>
      `Listing ${matched} records from ${scanned} reviewed candidates in the permitted sample.`,
    emptyFiles: 'No files are listed for this project in the permitted scope.',
    emptyRecords: 'No records are listed for this project in the permitted sample.',
    memoryTitle: 'Communication preference',
    memoryEmpty: 'No communication preference is recorded for this project.',
    addPreference: 'Add preference',
    editPreference: 'Edit',
    originConversation: 'From a conversation · Only this project',
    originUserEdit: 'Only this project',
    addedByYou: 'Added by you',
    addedByOther: 'Added by another member',
    uploadedFile: 'Uploaded file',
    declaredArtifact: 'Declared artifact',
    markdownLabel: 'Markdown document',
    plainLabel: 'Plain text document',
    provenance: 'Provenance',
    sourceDetails: 'Source details',
    diagnostics: 'Read details',
    loading: 'Loading…',
    refreshPrompt: 'The project files have changed. Refresh to continue.',
    scopeUnavailable: 'Knowledge is not available for this view.',
    chooseProject:'Choose a project to see its files and saved work',
    invalidPayload: 'This project knowledge could not be read safely.',
    readFailed: 'The project knowledge could not be read.',
    catalogueUnavailable: 'Project knowledge is unavailable.',
    sourceUnavailable: 'This source is unavailable.',
    memoryUnavailable: 'The project preference is unavailable.',
    sourceChanged: 'This source changed. Refresh to continue.',
    emptyQuery: 'Nothing in the permitted sample matches this filter.',
    closeDiagnostics: 'Show technical details',
    reasonCopy: {
      SOURCE_UNAVAILABLE: 'The stored source is not reachable right now.',
      SOURCE_CHANGED: 'The stored source changed since it was listed.',
      RECORD_NOT_FOUND: 'This record is not in the permitted scope.',
      SOURCE_MISMATCH: 'This source does not match the listed project snapshot.',
      SOURCE_INVALID: 'The stored source failed its integrity check.',
      CONTENT_OVER_BUDGET: 'This source is too large to show here.',
      RESPONSE_OVER_BUDGET: 'The response was too large to show.',
      UNSUPPORTED_SOURCE: 'This source kind is not supported here.',
      CONFLICT: 'Conflicting project state prevents this view.',
    } as Record<string, string>,
  },
  'zh-CN': {
    productLabel: 'Mastermind OS',
    fallbackTitle: '知识',
    filesTab: '文件',
    memoryTab: '记忆',
    addFiles: '添加文件',
    addFilesUnavailable: '当前无法添加文件。',
    open: '打开',
    openUnavailable: '不可用',
    back: '返回',
    backToFiles: '返回文件',
    browseAllRecords: '浏览全部记录',
    backToLibrary: '返回知识库',
    recordsTitle: '全部记录',
    queryLabel: '筛选',
    queryFilesPlaceholder: '按名称筛选文件',
    queryRecordsPlaceholder: '按标题、类型或日期筛选记录',
    filterScopeNote: '仅筛选许可样本中的名称、类型和日期，不是全文搜索。',
    partialNotice: '部分来源不可用。',
    partialFilesDetail: (declared: number, listed: number) => `在许可范围内显示 ${declared} 个已声明文件中的 ${listed} 个。`,
    boundedRecordsNote: (matched: number, scanned: number) => `在许可样本中，从审阅的 ${scanned} 个候选里列出 ${matched} 条记录。`,
    emptyFiles: '许可范围内没有列出此项目的文件。',
    emptyRecords: '许可样本中没有列出此项目的记录。',
    memoryTitle: '沟通偏好',
    memoryEmpty: '此项目尚未记录沟通偏好。',
    addPreference: '添加偏好',
    editPreference: '编辑',
    originConversation: '来自对话 · 仅此项目',
    originUserEdit: '仅此项目',
    addedByYou: '由你添加',
    addedByOther: '由其他成员添加',
    uploadedFile: '已上传文件',
    declaredArtifact: '声明产物',
    markdownLabel: 'Markdown 文档',
    plainLabel: '纯文本文档',
    provenance: '来源信息',
    sourceDetails: '来源详情',
    diagnostics: '读取详情',
    loading: '正在加载…',
    refreshPrompt: '项目文件已变化，请刷新后继续。',
    scopeUnavailable: '此视图无法使用知识库。',
    chooseProject:'选择一个项目，查看其文件和已保存的工作',
    invalidPayload: '无法安全读取此项目知识。',
    readFailed: '无法读取项目知识。',
    catalogueUnavailable: '项目知识不可用。',
    sourceUnavailable: '此来源不可用。',
    memoryUnavailable: '项目偏好不可用。',
    sourceChanged: '此来源已变化，请刷新后继续。',
    emptyQuery: '许可样本中没有匹配该筛选的内容。',
    closeDiagnostics: '查看技术详情',
    reasonCopy: {
      SOURCE_UNAVAILABLE: '存储的来源当前无法访问。',
      SOURCE_CHANGED: '存储的来源在列出后已变化。',
      RECORD_NOT_FOUND: '该记录不在许可范围内。',
      SOURCE_MISMATCH: '此来源与列出的项目快照不一致。',
      SOURCE_INVALID: '存储的来源未通过完整性校验。',
      CONTENT_OVER_BUDGET: '此来源过大，无法在此显示。',
      RESPONSE_OVER_BUDGET: '响应过大，无法显示。',
      UNSUPPORTED_SOURCE: '此处不支持该来源类型。',
      CONFLICT: '项目状态冲突，无法显示此视图。',
    } as Record<string, string>,
  },
} as const;

export type KnowledgeLibraryCopy = (typeof KNOWLEDGE_LIBRARY_COPY)['en'];

export function knowledgeLibraryCopy(locale: KnowledgeLibraryLocale | undefined): KnowledgeLibraryCopy {
  return (locale === 'zh-CN' ? KNOWLEDGE_LIBRARY_COPY['zh-CN'] : KNOWLEDGE_LIBRARY_COPY.en) as KnowledgeLibraryCopy;
}

/** Plain public copy for a closed backend reason code; unknown stays generic. */
export function reasonPublicCopy(
  code: string,
  locale: KnowledgeLibraryLocale | undefined,
): string {
  const copy = knowledgeLibraryCopy(locale);
  return copy.reasonCopy[code] ?? copy.readFailed;
}
