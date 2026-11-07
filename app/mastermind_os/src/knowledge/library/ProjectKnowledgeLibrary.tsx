/** Mount the existing Library directly on the actual fixed MissionHost reads. */
import {useMemo} from 'react';
import type {MissionHost} from '../../host';
import {KnowledgeLibrary} from './KnowledgeLibrary';
import type {KnowledgeLibraryProps} from './knowledge-library-contract';

export interface ProjectKnowledgeLibraryProps extends Omit<KnowledgeLibraryProps,'readCatalogue'|'readMemory'|'readSource'> {
  readonly host: Pick<MissionHost,'readProjectKnowledgeCatalogue'|'readProjectKnowledgeMemory'|'readProjectKnowledgeSource'|'projectFilesSearch'>|undefined;
}

export function ProjectKnowledgeLibrary({host,...props}:ProjectKnowledgeLibraryProps) {
  const catalogue=host?.readProjectKnowledgeCatalogue, memory=host?.readProjectKnowledgeMemory,
    source=host?.readProjectKnowledgeSource;
  const reads=useMemo(()=>({
    ...(catalogue?{readCatalogue:({workRef,signal}:{workRef:string;signal:AbortSignal})=>catalogue({work_ref:workRef,signal})}:{}),
    ...(memory?{readMemory:({workRef,signal}:{workRef:string;signal:AbortSignal})=>memory({work_ref:workRef,signal})}:{}),
    ...(source?{readSource:({workRef,sourceRef,expectedRevision,signal}:{workRef:string;sourceRef:string;expectedRevision:string;signal:AbortSignal})=>
      source({work_ref:workRef,source_ref:sourceRef,expected_revision:expectedRevision,signal})}:{}),
  }),[catalogue,memory,source]);
  return <KnowledgeLibrary {...props} {...reads} fileSearchOwner={host?.projectFilesSearch}/>;
}
