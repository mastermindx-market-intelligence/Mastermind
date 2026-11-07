/** A literal correction form in the incumbent Knowledge editor shell.
 * Preparation and every publication/recovery phase remain parent-owned. */
import {useEffect,useRef,useState} from 'react';
import type {ProjectDiscoverySource} from './knowledge-library-contract';
import type {KnowledgeEditPhase,KnowledgeEditorLocale} from './ProjectKnowledgeEditor';
import {DISCOVERY_CORRECTION_SCHEMA,DISCOVERY_KINDS,validateDiscoveryCorrectionRequest,
  validateDiscoveryCorrectionLookup,type DiscoveryCorrectionLookup,type ProjectDiscoveryCorrectionRequest} from './project-discovery-correction';
import {canonicalPublicRequest} from './project-knowledge-requests';
import {sha256Hex} from '../../orchestration/operation-key';
import type {ProjectSourceStatus} from './project-source-operation';
import './knowledge-editor.css';

interface Props {
  source:ProjectDiscoverySource;
  requestId:string;
  locale?:KnowledgeEditorLocale;
  phase:KnowledgeEditPhase;
  current:(source:ProjectDiscoverySource)=>boolean;
  onPrepare:(request:ProjectDiscoveryCorrectionRequest,source:ProjectDiscoverySource)=>Promise<void>|void;
  onClose:()=>void;
  onCheckOriginal:()=>void;
  onInspectOriginal:(lookup:DiscoveryCorrectionLookup)=>Promise<ProjectSourceStatus>;
}
const FIELDS=[
  ['reason','Why this correction?','为什么更正？'],
  ['claim','Corrected finding','更正后的发现'],
  ['falsifier','What would disprove it?','什么证据会推翻它？'],
  ['so_what','What changes?','这会改变什么？'],
  ['verified_by','How was it checked?','如何核实？'],
  ['evidence','Supporting references','支持证据'],
  ['body_utf8','Evidence and limitations','证据与局限'],
] as const;
type Field=(typeof FIELDS)[number][0];
const empty=()=>({reason:'',claim:'',falsifier:'',so_what:'',verified_by:'',evidence:'',body_utf8:'',kind:'',confidence:'',verified_at:'',expires:''});

export function ProjectDiscoveryCorrectionEditor(props:Props){
  const [draft,setDraft]=useState(empty),[attempted,setAttempted]=useState(false),[error,setError]=useState(false);
  const [inspection,setInspection]=useState<'checking'|'recorded'|'unavailable'|null>(null);
  const alive=useRef(true),original=useRef<DiscoveryCorrectionLookup|null>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  // An opened editor never retargets its source or callback. The parent keys it
  // by the issued original ID and unmounts it at an auth/host/scope boundary.
  const opened=useRef({source:props.source,id:props.requestId,current:props.current,prepare:props.onPrepare,inspect:props.onInspectOriginal});
  const sent=useRef(false);
  const zh=props.locale==='zh-CN',bound=opened.current;
  let current=false;
  try {current=props.source===bound.source&&props.requestId===bound.id&&props.current===bound.current
    &&props.onPrepare===bound.prepare&&bound.current(bound.source);}catch{ /* No current source, no action. */ }
  const title=zh?'更正发现':'Correct discovery';
  const check=async()=>{
    if(!alive.current||!original.current)return;
    // A prepare can durably retain private input before its response is lost.
    // It has no submission pointer yet; inspect only the retained safe tuple.
    if(['prepare-unavailable','prepared','idle'].includes(props.phase)){
      if(inspection==='checking')return;setInspection('checking');
      try{await bound.inspect(original.current);if(alive.current)setInspection('recorded');}
      catch{if(alive.current)setInspection('unavailable');}
    }else props.onCheckOriginal();
  };
  const recovery=attempted?<><button type="button" className="knowledge-editor-button" disabled={inspection==='checking'} onClick={()=>void check()}>{zh?'检查原始操作':'Check original operation'}</button>
    {inspection?<p role="status">{inspection==='checking'?(zh?'正在检查原始操作。':'Checking the original operation.'):
      inspection==='recorded'?(zh?'已读取原始操作。未重新提交更改。':'The original operation was read. No change was resubmitted.'):
      (zh?'暂时无法读取原始操作。保留此窗口后再检查。':'The original operation could not be read. Keep this window and check again.')}</p>:null}</>:null;
  if(!current)return <section className="knowledge-editor" aria-label={title}>
    <h2 className="knowledge-editor-heading">{title}</h2>
    <p role="status">{zh?'原始发现已变化。重新打开当前来源后再更正。':'The original discovery has changed. Open the current source to correct it.'}</p>
    <button type="button" className="knowledge-editor-button" onClick={props.onClose}>{zh?'关闭':'Close'}</button>
    {recovery}
  </section>;
  const update=(field:keyof ReturnType<typeof empty>,value:string)=>{if(!sent.current){setError(false);setDraft(previous=>({...previous,[field]:value}));}};
  const prepare=async()=>{
    if(sent.current||!current)return;
    let request:ProjectDiscoveryCorrectionRequest;
    try{
      if(!alive.current||!bound.current(bound.source))throw Error();
      const s=bound.source;
      request=validateDiscoveryCorrectionRequest({schema:DISCOVERY_CORRECTION_SCHEMA,request_id:bound.id,
        work_ref:s.workRef,source_commit:s.sourceContext.sourceCommit,base_revision:s.sourceContext.baseRevision,
        discovery_ref:s.discoveryRef,expected_discovery_revision:s.contentSha256,correction_reason:draft.reason,
        replacement:{claim:draft.claim,falsifier:draft.falsifier,so_what:draft.so_what,kind:draft.kind,
          confidence:draft.confidence,verified_at:draft.verified_at,verified_by:draft.verified_by,expires:draft.expires||null,
          body_utf8:draft.body_utf8,evidence:draft.evidence.split(/\r?\n/).filter(line=>line!=='')}});
      original.current=validateDiscoveryCorrectionLookup({action:'correct_project_discovery',request_id:request.request_id,
        work_ref:request.work_ref,source_commit:request.source_commit,base_revision:request.base_revision,
        discovery_ref:request.discovery_ref,expected_discovery_revision:request.expected_discovery_revision,
        request_sha256:sha256Hex(canonicalPublicRequest(request))});
      if(!bound.current(bound.source))throw Error();
    }catch{setError(true);return;}
    // This original body is fixed once handed to prepare. A new edited version
    // needs a new explicit draft in the parent, never a changed-body retry.
    sent.current=true;setAttempted(true);
    try{await bound.prepare(request,bound.source);}catch{setError(true);}
  };
  return <section className="knowledge-editor" lang={zh?'zh-CN':'en'} data-knowledge-editor-mode="correction" data-knowledge-editor-phase={props.phase}>
    <h2 className="knowledge-editor-heading">{title}</h2>
    <p className="knowledge-editor-hint">{zh?'保留原始证据，记录有依据的更正。':'Record a supported correction and keep the original evidence.'}</p>
    <details className="knowledge-editor-details"><summary>{zh?'原始发现':'Original discovery'}</summary>
      <pre className="visible-text">{bound.source.contentUtf8}</pre></details>
    <fieldset disabled={attempted}>
      {FIELDS.map(([field,en,cn])=><div className="knowledge-editor-field" key={field}>
        <label className="knowledge-editor-label" htmlFor={bound.id+'-'+field}>{zh?cn:en}</label>
        <textarea id={bound.id+'-'+field} className="knowledge-editor-textarea" value={draft[field as Field]}
          rows={field==='body_utf8'?5:field==='evidence'?3:2} onChange={event=>update(field,event.target.value)}/>
        {field==='evidence'?<p className="knowledge-editor-hint">{zh?'每行一条引用，最多八条。':'One reference per line, up to eight.'}</p>:null}
      </div>)}
      <div className="knowledge-editor-field"><label className="knowledge-editor-label" htmlFor={bound.id+'-kind'}>{zh?'发现类别':'Discovery type'}</label>
        <select id={bound.id+'-kind'} className="knowledge-editor-textarea" value={draft.kind} onChange={event=>update('kind',event.target.value)}>
          <option value="">{zh?'请选择':'Choose a type'}</option>
          {DISCOVERY_KINDS.map((kind,i)=><option key={kind} value={kind}>{zh?['架构','数据','隐患','废弃代码','约束','运行行为'][i]:['Architecture','Data','Pitfall','Unused code','Constraint','Runtime behavior'][i]}</option>)}
        </select></div>
      <div className="knowledge-editor-field"><label className="knowledge-editor-label" htmlFor={bound.id+'-confidence'}>{zh?'可信程度':'Confidence'}</label>
        <select id={bound.id+'-confidence'} className="knowledge-editor-textarea" value={draft.confidence} onChange={event=>update('confidence',event.target.value)}>
          <option value="">{zh?'请选择':'Choose confidence'}</option>
          <option value="suspected">{zh?'待核实':'Suspected'}</option><option value="probable">{zh?'很可能':'Probable'}</option><option value="verified">{zh?'已核实':'Verified'}</option>
        </select></div>
      <div className="knowledge-editor-field"><label className="knowledge-editor-label" htmlFor={bound.id+'-verified-at'}>{zh?'证据日期':'Evidence date'}</label>
        <input id={bound.id+'-verified-at'} className="knowledge-editor-textarea" type="date" value={draft.verified_at} onChange={event=>update('verified_at',event.target.value)}/>
        <p className="knowledge-editor-hint">{zh?'填写实际核实日期。更正不会自动变成已核实。':'Use the date it was checked. A correction does not automatically become verified.'}</p></div>
      <div className="knowledge-editor-field"><label className="knowledge-editor-label" htmlFor={bound.id+'-expires'}>{zh?'有效截止日期（可选）':'Valid until (optional)'}</label>
        <input id={bound.id+'-expires'} className="knowledge-editor-textarea" type="date" value={draft.expires} onChange={event=>update('expires',event.target.value)}/></div>
    </fieldset>
    {error?<p className="knowledge-editor-status" role="status">{zh?'请检查更正内容、证据和日期。':'Check the correction, references and dates.'}</p>:null}
    {attempted&&props.phase==='prepared'?<p role="status">{zh?'请检查下方这版更正。若要修改，请关闭后重新开始。':'Review this version below. To change it, close and start another correction.'}</p>:null}
    {props.phase==='prepare-unavailable'?<p role="status">{zh?'暂时无法准备这次更正。请检查原始操作。':'This correction could not be prepared. Check the original operation.'}</p>:null}
    <div className="knowledge-editor-actions">
      <button type="button" className="knowledge-editor-button knowledge-editor-button--primary" disabled={attempted||!current} onClick={()=>void prepare()}>{zh?'检查更正':'Review correction'}</button>
      <button type="button" className="knowledge-editor-button" onClick={props.onClose}>{zh?'关闭':'Close'}</button>
      {recovery}
    </div>
  </section>;
}

export function DiscoveryCorrectionReview({request,source,locale}:{request:ProjectDiscoveryCorrectionRequest;source:ProjectDiscoverySource;locale:KnowledgeEditorLocale}){
  const zh=locale==='zh-CN',r=request.replacement;
  const kind=(zh?['架构','数据','隐患','废弃代码','约束','运行行为']:['Architecture','Data','Pitfall','Unused code','Constraint','Runtime behavior'])[DISCOVERY_KINDS.indexOf(r.kind)];
  const confidence=zh?{suspected:'待核实',probable:'很可能',verified:'已核实'}[r.confidence]:{suspected:'Suspected',probable:'Probable',verified:'Verified'}[r.confidence];
  return <div>
    <h3>{zh?'更正原因':'Reason for correction'}</h3><p className="visible-text">{request.correction_reason}</p>
    <h3>{zh?'更正内容':'Replacement'}</h3>
    <dl>{[['Finding','发现',r.claim],['Would be disproved by','推翻条件',r.falsifier],['What changes','实际影响',r.so_what],
      ['Type','类别',kind],['Confidence','可信程度',confidence],['Evidence date','证据日期',r.verified_at],
      ['Checked by','核实方式',r.verified_by],['Valid until','有效截止',r.expires??(zh?'未设定':'Not specified')]].map(([en,cn,value])=><div key={en}><dt>{zh?cn:en}</dt><dd className="visible-text">{value}</dd></div>)}</dl>
    <h3>{zh?'支持证据':'Supporting references'}</h3><ul>{r.evidence.map(item=><li key={item} className="visible-text">{item}</li>)}</ul>
    {r.body_utf8?<pre className="visible-text">{r.body_utf8}</pre>:null}
    <details><summary>{zh?'保留的原始发现':'Preserved original discovery'}</summary><pre className="visible-text">{source.contentUtf8}</pre></details>
  </div>;
}
