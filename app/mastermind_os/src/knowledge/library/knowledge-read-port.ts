/** Fixed project selectors and strict raw-body validation for real host reads. */
import { validate_catalogue, validate_memory, validate_source, sha256Hex } from './knowledge-library-contract';

export interface KnowledgeReadSelection { readonly work_ref: string }
export interface KnowledgeSourceSelection extends KnowledgeReadSelection {
  readonly source_ref: string;
  readonly expected_revision: string;
}
export type KnowledgeReadKind = 'catalogue'|'memory'|'source';

const full=(pattern:RegExp,value:string)=>pattern.exec(value)?.[0]===value;

export function knowledgeReadSelection(value: unknown, kind: KnowledgeReadKind): KnowledgeReadSelection|KnowledgeSourceSelection|null {
  if (typeof value!=='object' || value===null || Array.isArray(value)) return null;
  if (![Object.prototype,null].includes(Object.getPrototypeOf(value))) return null;
  const keys=Reflect.ownKeys(value), expected=kind==='source'?['work_ref','source_ref','expected_revision']:['work_ref'];
  if (keys.length!==expected.length || keys.some(key=>typeof key!=='string' || !expected.includes(key))) return null;
  const data:Record<string,unknown>={};
  for(const key of expected){const field=Object.getOwnPropertyDescriptor(value,key);if(!field || !('value' in field))return null;data[key]=field.value;}
  if(typeof data.work_ref!=='string' || !full(/^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/,data.work_ref) || data.work_ref.length<5 || data.work_ref.length>67) return null;
  if(kind==='source'){
    if(typeof data.source_ref!=='string' || !full(/^project-(?:file|record)\.v1\.[0-9a-f]{64}$/,data.source_ref)
      || typeof data.expected_revision!=='string' || !full(/^[0-9a-f]{40}$/,data.expected_revision)) return null;
    return Object.freeze({work_ref:data.work_ref,source_ref:data.source_ref,expected_revision:data.expected_revision});
  }
  return Object.freeze({work_ref:data.work_ref});
}

export async function validateKnowledgeRead(raw: unknown, selected: KnowledgeReadSelection|KnowledgeSourceSelection, kind: KnowledgeReadKind): Promise<unknown> {
  const decoded=kind==='catalogue' ? validate_catalogue(raw,selected.work_ref)
    :kind==='memory' ? validate_memory(raw,selected.work_ref)
    :validate_source(raw,selected.work_ref,(selected as KnowledgeSourceSelection).source_ref);
  // Snapshot only after descriptor-safe strict decode, and before any await.
  const encoded=JSON.stringify(raw);
  if(new TextEncoder().encode(encoded).length+1>131_072) throw new Error('PROJECT_KNOWLEDGE_RESPONSE_OVER_BUDGET');
  const detached=JSON.parse(encoded);
  if(kind==='source'){
    const source=decoded as ReturnType<typeof validate_source>;
    if(source.availability==='AVAILABLE'){
      if(source.source!.revision!==(selected as KnowledgeSourceSelection).expected_revision
        || await sha256Hex(source.document!.contentUtf8)!==source.document!.contentSha256)
        throw new Error('PROJECT_KNOWLEDGE_SOURCE_CHANGED');
    }
  }
  return detached;
}
