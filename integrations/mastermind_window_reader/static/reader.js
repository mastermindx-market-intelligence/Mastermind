'use strict';
(() => {
  // Only the strict Python projection is embedded. No network or provider client.
  let data = JSON.parse(document.getElementById('capture-data').textContent);
  const emptyBootstrap = data.reader_bootstrap === 'no-source';
  if(emptyBootstrap)data={lane:{ref:null},items:[],relations:[],review:null};
  const el = id => document.getElementById(id);
  const state = { selected: data.items.length ? data.items[0].id : null, compare: false, query: '', size: 0, selectionRemoved: false, sourceAvailable: !emptyBootstrap };
  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
  const formatTime = value => value ? new Date(value).toLocaleString('en-GB', {
    day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit', timeZone:'UTC', hour12:false
  }) + ' UTC' : 'Time not established';
  const short = value => value ? value.slice(0,12) : 'Not established';
  const queryPattern = (query, global=false) => new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),global?'giu':'iu');
  const visible = () => data.items.filter(i => !state.query || queryPattern(state.query).test(i.title+'\n'+(i.text||'')));
  const isWindow = () => !!data.window;
  const evidenceLabel = i => isWindow() ? ('VISIBLE RESPONSE · '+i.sourceState.toUpperCase()+(i.representation==='FILTERED_VISIBLE_TEXT'?' · DISPLAY FILTER APPLIED':'')) : i.representation === 'FILTERED_RECORDED_TEXT' ? 'RECORDED OUTPUT · DISPLAY FILTER APPLIED' : 'RECORDED OUTPUT · NOT A LIVE THREAD';
  const verdictText = r => r ? `Reported ${r.reported_verdict} · ${r.major_count} major findings` : 'Review not recorded';
  function highlighted(text, query) {
    const frag = document.createDocumentFragment();
    if (!query) { frag.append(document.createTextNode(text)); return frag; }
    const pattern=queryPattern(query,true); let pos=0, count=0, match;
    while ((match=pattern.exec(text)) !== null && count < 1000) {
      const found=match.index;
      frag.append(document.createTextNode(text.slice(pos,found)));
      frag.append(make('mark','',match[0]));
      pos=found+match[0].length;count++;
    }
    frag.append(document.createTextNode(text.slice(pos)));return frag;
  }
  function renderNav(items) {
    el('output-nav').replaceChildren();
    items.forEach(i => {
      const button=make('button','output-select');button.dataset.itemIndex=String(data.items.indexOf(i));
      button.setAttribute('aria-pressed',String(state.selected===i.id));
      const top=make('span','nav-top');top.append(make('span','mini-avatar',isWindow()?'V':i.stage==='fix'?'B':'R'),document.createTextNode(i.title));
      button.append(top,make('span','nav-meta',isWindow()?`${i.sourceState} · ${i.state==='READABLE'?'Visible response':'Content withheld'}`:`Round ${i.round} · ${i.state==='READABLE'?'Available recorded text':i.state==='WITHHELD'?'Content withheld':'Output unavailable'}`));
      if(i.review)button.append(make('span','nav-tag',verdictText(i.review)));
      button.addEventListener('click',() => {state.selected=i.id;state.selectionRemoved=false;state.compare=false;render();});
      el('output-nav').append(button);
    });
  }
  function card(i) {
    const section=make('article','output-card');section.dataset.itemKey=i.id;section.setAttribute('aria-label',i.title);
    const header=make('header','output-header');header.append(make('span','avatar'+(i.stage==='review'?' review':''),isWindow()?'V':i.stage==='fix'?'B':'R'));
    const summary=make('div');summary.append(make('h3','',i.title),make('p','output-sub',isWindow()?`Observed ${formatTime(data.captured_at)}`:`Round ${i.round} · Output recorded ${formatTime(i.ended_at)}`));header.append(summary);
    section.append(header,make('div','body-caption',evidenceLabel(i)));
    if(i.state==='READABLE') {
      const text=make('pre','message-text');text.tabIndex=0;text.setAttribute('aria-label',i.title+' text');text.append(highlighted(i.text,state.query));section.append(text);
    } else {
      const why=i.state==='WITHHELD'?'This output was withheld by the capture reader. It is not embedded in this page.':'This output was unavailable in the capture. No replacement text has been generated.';
      section.append(make('p','message-text',why));
    }
    const foot=make('footer','output-footer');foot.append(make('span','',isWindow()?'Observed turn only · history not established':i.coverage.file==='COMPLETE_FILE'?'Captured file complete · provider history unknown':'File coverage not established'),make('code','',isWindow()?`Text ${short(i.display_sha256)}`:`Source ${short(i.source&&i.source.sha256)}`));
    section.append(foot);return section;
  }
  function render() {
    const items=visible();
    if(!state.selectionRemoved&&!items.some(i=>i.id===state.selected))state.selected=items.length?items[0].id:null;
    el('search-result').textContent=!state.sourceAvailable?'No source currently displayed':state.query?`${items.length} of ${data.items.length} outputs`:`${data.items.length} ${isWindow()?'visible items':'recorded outputs'}`;
    el('clear-search').hidden=!state.query;
    renderNav(items);
    el('single').setAttribute('aria-pressed',String(!state.compare));el('compare').setAttribute('aria-pressed',String(state.compare));
    el('reading-grid').className='reading-grid'+(state.compare?' compare':'')+' size-'+state.size;
    const displayed=state.selectionRemoved?[]:(state.compare?items:items.filter(i=>i.id===state.selected));
    el('reading-grid').replaceChildren(...displayed.map(card));
    el('empty-result').hidden=displayed.length>0;
    el('empty-result').textContent=!state.sourceAvailable?'Source content is not currently displayed. A qualified read is required; this is not an empty inventory.':state.selectionRemoved?'The selected output is no longer available in this source read. Select an available output to continue.':data.items.length?'No matching outputs. Clear the search to read the captured records.':isWindow()?'No visible items in this observed window; this is not a fleet count.':'No outputs in this capture. An empty recorded window is not evidence that no work exists.';
    el('smaller').disabled=state.size===0;el('larger').disabled=state.size===5;
  }
  function detailSection(title, rows) {
    const section=make('section','detail-section');section.append(make('h3','',title));const dl=make('dl');
    rows.forEach(([label,value,mono])=>{dl.append(make('dt','',label));const dd=make('dd');dd.append(mono?make('code','',value):document.createTextNode(String(value??'Not established')));dl.append(dd);});
    section.append(dl);return section;
  }
  let focusReturn=null;
  function showDetail(title,nodes,trigger) {
    focusReturn=trigger;el('dialog-title').textContent=title;el('dialog-body').replaceChildren(...nodes);el('details').showModal();el('close-dialog').focus();
  }
  function evidence() {
    if(isWindow()){windowEvidence();return;}
    const intro=make('p','detail-intro','This page reads a fixed capture of native output files. The recorded reports are historical source content—not a fresh assessment of the project. Hashes identify captured bytes; they do not prove provider identity, current permission or company acceptance.');
    const sections=[intro,detailSection('Capture boundary',[
      ['Captured at',formatTime(data.captured_at)],['Source timestamp',data.captured_at,true],['Capture SHA-256',data.capture_sha256,true],['Scope','One explicitly selected native lane'],
      ['Provider history','Provider history not established'],['Live connection',connection.port?'Recorded-source read port; not live chat':'Not connected'],['Control capability','None — no sending, starting, stopping or approval']
    ])];
    data.items.forEach(i=>sections.push(detailSection(i.title,[
      ['Source reference',i.source&&i.source.ref,true],['Source SHA-256',i.source&&i.source.sha256,true],
      ['Displayed-text SHA-256',i.display_sha256,true],['Source bytes',i.source&&i.source.bytes],
      ['Representation',i.representation||'No displayable content'],['File coverage',i.coverage.file],
      ['Capture truncation',i.coverage.capture_truncation],['Recorded exit code',i.reported_exit_code],
      ['Provider/model','Not established'],['Session identity','Not established'],['Limitations',(i.issues||[]).join(' · ')||'No additional item issue recorded']
    ])));
    if(data.review)sections.push(detailSection('Reported review — not acceptance',[
      ['Reported verdict',data.review.reported_verdict],['Blocking findings',data.review.blocker_count],['Major findings',data.review.major_count],
      ['Checked revision',data.review.checked_head,true],['Recorded current revision',data.review.recorded_head_now,true],
      ['Company acceptance','Not established'],['Final-record alias',data.review.final_alias||'Not recorded']
    ]));
    showDetail('Capture evidence',sections,el('evidence'));
  }
  function connections() {
    if(isWindow()){
      showDetail('Observation context',[make('p','detail-intro','This read is scoped by the existing owner to one managed turn. No organizational relationships are inferred from these messages.'),detailSection('Selected observation',[
        ['Source reference',data.lane.ref,true],['History','Not established'],['Acceptance','Not projected'],['Provider control','Not available in this reader']
      ])],el('connections'));return;
    }
    const nodes=[make('p','detail-intro','These relationships come from the selected native lane record. They are not an inferred organizational hierarchy. The reader does not attach a CEO, provider session or Executive Job when the source has not established that link.')];
    nodes.push(detailSection('Selected work reference',[
      ['Native lane',data.lane.label,true],['Repository',data.lane.repository],['Pull request',`#${data.lane.pr} — historical association`],
      ['Branch',data.lane.branch,true],['Prior source revision',data.lane.head_before,true],
      ['Executive association','Executive Job not linked'],['Accountable office','Not linked in this capture']
    ]));
    const labels={RECORDED_ROUND:'Recorded round',RECORDED_OUTPUT:'Recorded output',REVIEW_TARGET:'Review target'};
    const relSection=make('section','detail-section');relSection.append(make('h3','','Source-declared relationships'));
    data.relations.forEach(r=>{const e=make('div','relation');e.dataset.relation=r.kind;e.append(make('strong','',labels[r.kind]),make('p','',r.from+' → '+r.to));relSection.append(e);});
    if(!data.relations.length)relSection.append(make('p','detail-intro','No relationships were recorded in this capture.'));
    nodes.push(relSection);
    const links=make('p','detail-note');const validRepository=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(data.lane.repository);const validPr=Number.isInteger(data.lane.pr)&&data.lane.pr>0;if(validRepository&&validPr){const parts=data.lane.repository.split('/');const owner=parts[0],name=parts[1];const pr=make('a','',`Open repository PR #${data.lane.pr}`);pr.href='https://github.com/'+encodeURIComponent(owner)+'/'+encodeURIComponent(name)+'/pull/'+String(Number(data.lane.pr));pr.target='_blank';pr.rel='noopener noreferrer';links.append(pr,document.createTextNode(' · Opens an external source; this reader does not refresh its status.'));}else{links.append('PR reference unavailable',document.createTextNode(' · Opens an external source; this reader does not refresh its status.'));}nodes.push(links);
    showDetail('Recorded connections',nodes,el('connections'));
  }
  function updateHeader() {
  if(isWindow()){windowHeader();return;}
  el('lane-title').textContent=(data.lane.repo==='macro'?'Macro':'Terminal')+` · PR #${data.lane.pr}`;
  el('lane-subtitle').textContent=data.lane.label;
  el('captured-time').textContent=`Capture from ${formatTime(data.captured_at)} · source output, not a live session`;
  const warning=el('review-warning');warning.replaceChildren();
  if(data.review){warning.append(make('strong','',verdictText(data.review)),document.createTextNode(' — this is the recorded reviewer verdict, not company acceptance.'));}
  else warning.textContent='No review is recorded in this capture. No acceptance state has been inferred.';
  }
  if(!emptyBootstrap)updateHeader();
  el('single').addEventListener('click',()=>{state.compare=false;render();});
  el('compare').addEventListener('click',()=>{state.compare=true;render();});
  el('search').addEventListener('input',event=>{state.query=event.target.value.slice(0,256);render();});
  el('clear-search').addEventListener('click',()=>{el('search').value='';state.query='';render();el('search').focus();});
  el('larger').addEventListener('click',()=>{state.size=Math.min(5,state.size+1);render();});
  el('smaller').addEventListener('click',()=>{state.size=Math.max(0,state.size-1);render();});
  el('evidence').addEventListener('click',evidence);el('connections').addEventListener('click',connections);
  el('close-dialog').addEventListener('click',()=>el('details').close());
  el('details').addEventListener('close',()=>{if(focusReturn)focusReturn.focus();});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!el('details').open&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();el('search').focus();}});

  // The host application supplies this port after applying its authentication.
  // It is not a bearer-token UI, a message listener, an HTTP proxy or a provider.
  // This module never chooses an endpoint, mints a grant, retries or starts work.
  let fixedLane = data.lane.ref;
  let fixedKind = 'recorded';
  const connection = {port:null, epoch:0, controller:null, busy:false, lastView:null};
  const sourceStatus = (text) => {el('source-status').textContent=text;};
  function closeDetailsAndClear() {
    focusReturn=null;
    if(el('details').open)el('details').close();
    el('dialog-title').textContent='';el('dialog-body').replaceChildren();
  }
  function clearProtected() {
    closeDetailsAndClear();
    // This clears this component's DOM/model, not already downloaded files or
    // arbitrary memory held by another same-origin program or a former viewer.
    data={lane:{ref:fixedLane},items:[],relations:[],review:null};
    state.selected=null;state.selectionRemoved=false;state.query='';state.sourceAvailable=false;
    el('search').value='';el('capture-data').textContent='';
    el('lane-title').textContent='Recorded output';el('lane-subtitle').textContent='';
    el('captured-time').textContent='No qualified source read is currently displayed.';
    el('review-warning').textContent='No current recorded review is displayed.';
    el('evidence').disabled=true;el('connections').disabled=true;
    const ws=el('window-state');if(ws){ws.textContent='';ws.hidden=true;}
    connection.lastView=null;render();
  }
  const exactKeys=(o,keys)=>o&&Object.getPrototypeOf(o)===Object.prototype&&
      Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
  const asObject=o=>o&&typeof o==='object'&&!Array.isArray(o);
  const hash=(x,git=false)=>typeof x==='string'&&(git?/^[0-9a-f]{40}$/:/^[0-9a-f]{64}$/).test(x);
  const safeTime=x=>x===null||(typeof x==='string'&&x.length<=50&&
      /(?:Z|[+-]\d{2}:\d{2})$/.test(x)&&Number.isFinite(Date.parse(x)));
  function qualifyView(wire,laneRef) {
    if(fixedKind==='live-window')return qualifyWindow(wire,laneRef);
    // Representation validation only: source and access authenticity remain
    // with the existing server owner. Never infer grants from these fields.
    try {
      const encoded=JSON.stringify(wire);
      if(new TextEncoder().encode(encoded).length>2000000)return null;
      const w=JSON.parse(encoded);
      if(w.schema!=='mastermind.workspace.recorded_read_candidate.v1'||w.mode!=='recorded-source-read'||w.selection_ref!==laneRef)return null;
      const v=w.view;
      if(!asObject(v)||v.schema!=='mastermind.workspace_native_lane_capture_candidate.v1'||
         v.authority!=='OBSERVATION_ONLY'||v.scope!=='one-explicit-native-lane'||!hash(v.capture_sha256)||
         v.captured_at===null||!safeTime(v.captured_at))return null;
      if(!exactKeys(v.capabilities,['send','live_stream','provider_control'])||
         Object.values(v.capabilities).some(x=>x!==false))return null;
      const l=v.lane;const repos={macro:'mastermindx-market-intelligence/macro',terminal:'mastermindx-market-intelligence/mastermind-terminal'};
      if(!asObject(l)||l.ref!==laneRef||l.ref!==('native-lane:'+l.label)||
         typeof l.label!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(l.label)||l.label.includes('..')||
         !Object.hasOwn(repos,l.repo)||l.repository!==repos[l.repo]||!Number.isInteger(l.pr)||l.pr<1||l.pr>=10000000||
         typeof l.branch!=='string'||l.branch.length>200||!(/^[A-Za-z0-9_.\/-]+$/).test(l.branch)||l.branch.includes('..')||l.branch.startsWith('/')||
         !hash(l.head_before,true)||l.executive_job_id!==null||l.responsibility_ref!==null)return null;
      const checkReview=r=>r===null||(asObject(r)&&r.company_acceptance==='NOT_ESTABLISHED'&&
         ['PASS','FIX_REQUIRED','NO_REVIEW','UNKNOWN'].includes(r.reported_verdict)&&
         ['blocker_count','major_count','minor_count'].every(k=>Number.isInteger(r[k])&&r[k]>=0&&r[k]<=64)&&
         ['checked_head','recorded_head_now'].every(k=>r[k]===null||hash(r[k],true))&&
         (r.final_alias===null||['NOT_RECORDED','MATCHES_LAST_ROUND','DISAGREES_WITH_LAST_ROUND'].includes(r.final_alias)));
      if(!checkReview(v.review)||!Array.isArray(v.items)||v.items.length>16||!Array.isArray(v.relations)||v.relations.length>48)return null;
      const ids=new Set(),edges=new Set();let bytes=0;
      for(const i of v.items) {
        if(!asObject(i)||!Number.isInteger(i.round)||i.round<1||i.round>99||!['fix','review'].includes(i.stage))return null;
        const round=laneRef+':round:'+i.round,key=round+':'+i.stage;
        if(i.id!==key||ids.has(key)||i.provider_model!==null||i.provider_session_id!==null||!safeTime(i.ended_at))return null;
        ids.add(key);edges.add(JSON.stringify([laneRef,round,'RECORDED_ROUND']));edges.add(JSON.stringify([round,key,'RECORDED_OUTPUT']));
        if(i.title!==(i.stage==='fix'?'Builder output':'Reviewer output')||!['READABLE','WITHHELD','UNAVAILABLE'].includes(i.state))return null;
        const c=i.coverage;
        if(!asObject(c)||c.provider_history!=='NOT_ESTABLISHED'||!['COMPLETE_FILE','NOT_ESTABLISHED'].includes(c.file)||
           !['REPORTED_NOT_TRUNCATED','REPORTED_TRUNCATED','NOT_ESTABLISHED'].includes(c.capture_truncation))return null;
        if(i.state==='READABLE') {
          if(typeof i.text!=='string'||!hash(i.display_sha256)||!['RECORDED_TEXT','FILTERED_RECORDED_TEXT'].includes(i.representation))return null;
          const count=new TextEncoder().encode(i.text).length;bytes+=count;if(count>262144||bytes>1048576)return null;
          const p=i.source;
          if(!asObject(p)||p.ref!==laneRef+'/r'+i.round+'_'+i.stage+'.out.md'||!hash(p.sha256)||
             p.stable_during_read!==true||p.complete_file!==true||!Number.isInteger(p.bytes)||p.bytes<0||p.bytes>262144||p.mtime===null||!safeTime(p.mtime))return null;
        } else if(i.text!==null||i.display_sha256!==null)return null;
        if(i.review!==undefined) {
          if(!checkReview(i.review))return null;
          if(i.review&&i.review.checked_head)edges.add(JSON.stringify([i.id,'git:'+l.repo+':'+i.review.checked_head,'REVIEW_TARGET']));
        }
      }
      const seen=new Set();
      for(const e of v.relations) {
        if(!asObject(e)||e.basis!=='NATIVE_LANE_RECORD')return null;
        const key=JSON.stringify([e.from,e.to,e.kind]);
        if(!edges.has(key)||seen.has(key))return null;seen.add(key);
      }
      return v;
    }catch(_){return null;}
  }

  function qualifyWindow(wire,ref) {
    try {
      const raw=JSON.stringify(wire);if(new TextEncoder().encode(raw).length>2000000)return null;
      const w=JSON.parse(raw),v=w.view;
      const v1=w.schema==='mastermind.workspace.window_read_candidate.v1';
      const v2=w.schema==='mastermind.workspace.window_read_candidate.v2';
      if(v1){if(!exactKeys(w,['schema','selection_ref','mode','view']))return null;}
      else if(v2){
        if(!exactKeys(w,['schema','selection_ref','mode','view','observation_binding']))return null;
        const b=w.observation_binding;
        if(!exactKeys(b,['job_id','attempt_id'])||typeof b.job_id!=='string'||typeof b.attempt_id!=='string'||
           !/^JOB-[0-9]{1,9}$/.test(b.job_id)||!/^ATT-[0-9a-f]{32}$/.test(b.attempt_id))return null;
      }else return null;
      if(w.mode!=='observed-turn-window'||w.selection_ref!==ref)return null;
      if(!exactKeys(v,['schema','source_ref','scope','observed_at','epoch','terminal','coverage','history','acceptance','capabilities','items','gaps'])||
         v.schema!=='mastermind.workspace.visible_window_candidate.v1'||v.source_ref!==ref||v.scope!=='one-managed-turn-window'||
         v.observed_at===null||!safeTime(v.observed_at)||!hash(v.epoch)||typeof v.terminal!=='boolean'||
         !['OBSERVED_WINDOW','GAP_PRESENT','READ_LIMIT_REACHED'].includes(v.coverage)||v.history!=='NOT_PROVEN'||v.acceptance!=='NOT_PROJECTED'||
         !exactKeys(v.capabilities,['send','provider_control','history'])||Object.values(v.capabilities).some(x=>x!==false)||
         !Array.isArray(v.items)||v.items.length>256||!Array.isArray(v.gaps)||v.gaps.length>256)return null;
      const ids=new Set();let bytes=0;
      for(const i of v.items){
        if(!exactKeys(i,['id','source_sequence','publication_sequence','state','kind','text','representation','display_sha256'])||
           typeof i.id!=='string'||!/^visible:[0-9a-f]{64}$/.test(i.id)||ids.has(i.id)||
           !Number.isSafeInteger(i.source_sequence)||i.source_sequence<0||!Number.isSafeInteger(i.publication_sequence)||i.publication_sequence<1||
           !['partial','completed'].includes(i.state)||!['visible-response','withheld'].includes(i.kind))return null;
        ids.add(i.id);
        if(i.kind==='withheld'){if(i.text!==null||i.display_sha256!==null||i.representation!=='WITHHELD')return null;}
        else {
          if(typeof i.text!=='string'||!hash(i.display_sha256)||!['VISIBLE_TEXT','FILTERED_VISIBLE_TEXT'].includes(i.representation))return null;
          const n=new TextEncoder().encode(i.text).length;bytes+=n;if(n>16384||bytes>1048576)return null;
        }
      }
      for(const g of v.gaps)if(!exactKeys(g,['first','last','reason'])||!Number.isSafeInteger(g.first)||!Number.isSafeInteger(g.last)||g.first<0||g.last<g.first||g.reason!=='SOURCE_REPORTED_GAP')return null;
      if(v.gaps.length&&v.coverage!=='GAP_PRESENT')return null;
      const items=[...v.items].sort((a,b)=>a.source_sequence-b.source_sequence||a.publication_sequence-b.publication_sequence).map((i,n)=>({
        id:i.id,title:'Response '+(n+1),stage:'visible',round:null,sourceState:i.state,sourceOrder:i.source_sequence,
        publicationSequence:i.publication_sequence,state:i.kind==='withheld'?'WITHHELD':'READABLE',text:i.text,
        representation:i.representation,display_sha256:i.display_sha256,source:null,ended_at:null,
        coverage:{file:'NOT_ESTABLISHED',capture_truncation:'NOT_ESTABLISHED',provider_history:'NOT_ESTABLISHED'}
      }));
      return {window:v,lane:{ref,label:'Managed turn observation'},captured_at:v.observed_at,items,relations:[],review:null};
    }catch(_){return null;}
  }
  function windowHeader(){
    const w=data.window;
    el('evidence').textContent='Inspect window evidence';el('connections').textContent='Inspect observation context';
    document.querySelector('.breadcrumb').textContent='Workspace / Conversation window';
    document.querySelector('.search-label').textContent='Find in this window';
    el('search').setAttribute('aria-label','Find in visible responses');
    document.querySelector('.sidebar-section .eyebrow').textContent='TURN OBSERVATION';
    document.querySelector('.read-boundary div > span').textContent='Reading this view does not start, stop or send to the worker.';
    el('lane-title').textContent='Observed conversation';el('lane-subtitle').textContent='One permitted managed turn';
    el('captured-time').textContent='Observed at '+formatTime(w.observed_at)+' · not a complete history snapshot';
    el('capture-notice').textContent='Observed turn window';el('record-scope').textContent='SOURCE-QUALIFIED VISIBLE RESPONSES';
    el('review-warning').textContent='Acceptance is not projected. A completed response or ended turn is not company acceptance.';
    document.querySelector('.sidebar-footer p').textContent='Bounded turn observation. Full history is not established.';
    el('mode-note').textContent='Bounded turn observation · full history is not established. No commands can be sent.';
    let status=el('window-state');if(!status){status=make('p','window-state');status.id='window-state';el('source-connection').after(status);}
    status.hidden=false;status.textContent=(w.terminal?'Turn ended':'Turn is nonterminal')+' · '+
      (w.coverage==='GAP_PRESENT'?'Source reports a gap; some content is unavailable.':w.coverage==='READ_LIMIT_REACHED'?'Bounded read limit reached; additional content may exist.':'Available bounded window; complete history not established.');
  }
  function windowEvidence(){
    const w=data.window;const nodes=[make('p','detail-intro','This is a bounded observation of explicitly permitted responses. Read time is not generation time. Publication order and conversational order are distinct. No hidden reasoning, full-history coverage or work acceptance is inferred.'),detailSection('Window scope',[
      ['Observed at',formatTime(w.observed_at)],['Source reference',w.source_ref,true],['Publication epoch digest',w.epoch,true],
      ['History','Not established'],['Coverage',w.coverage],['Source-reported gaps',w.gaps.length],['Acceptance','Not projected']
    ])];
    data.items.forEach(i=>nodes.push(detailSection(i.title,[['Content state',i.sourceState],['Representation',i.representation],
      ['Display order',i.sourceOrder],['Publication update',i.publicationSequence],['Displayed-text SHA-256',i.display_sha256,true]])));
    showDetail('Window evidence',nodes,el('evidence'));
  }

  function applyView(next) {
    const stable=JSON.stringify(next);
    if(connection.lastView===stable)return;
    const positions=new Map();let focusedKey=null;
    document.querySelectorAll('.output-card').forEach(c=>{
      const text=c.querySelector('.message-text');
      if(text){positions.set(c.dataset.itemKey,{top:text.scrollTop,left:text.scrollLeft});
        if(document.activeElement===text)focusedKey=c.dataset.itemKey;}
    });
    const previousSelection=state.selected;
    data=next;state.sourceAvailable=true;
    if(previousSelection&&!next.items.some(i=>i.id===previousSelection)){state.selectionRemoved=true;}
    // The initial successful read selects its first output; subsequent removal
    // is explicit and never switches the human to somebody else's output.
    closeDetailsAndClear();updateHeader();render();
    document.querySelectorAll('.output-card').forEach(c=>{
      const text=c.querySelector('.message-text'),pos=positions.get(c.dataset.itemKey);
      if(text&&pos){text.scrollTop=pos.top;text.scrollLeft=pos.left;}
      if(text&&c.dataset.itemKey===focusedKey)text.focus({preventScroll:true});
    });
    el('evidence').disabled=false;el('connections').disabled=false;
    connection.lastView=stable;
  }
  function invalidatePort() {
    connection.epoch++;
    if(connection.controller)connection.controller.abort();
    connection.controller=null;connection.busy=false;connection.port=null;
  }
  function attach({expectedLane,read,sourceKind='recorded'}={}) {
    const prefix=sourceKind==='recorded'?'native-lane:':sourceKind==='live-window'?'managed-window:':null;
    if(prefix===null||typeof expectedLane!=='string'||!new RegExp('^'+prefix+'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$').test(expectedLane)||expectedLane.includes('..')||
        (fixedLane!==null&&expectedLane!==fixedLane)||typeof read!=='function')throw new TypeError('Qualified fixed-source read port required');
    fixedLane=expectedLane;fixedKind=sourceKind;
    invalidatePort();clearProtected();
    connection.port=read;el('source-connection').hidden=false;
    el('refresh-source').disabled=false;el('disconnect-source').disabled=false;
    sourceStatus('Ready to read · no source has been requested.');
    el('mode-note').textContent=sourceKind==='live-window'?'Bounded turn observation · full history is not established. No commands can be sent.':'Recorded-source connection; not live chat. No commands can be sent.';
  }
  function detach() {
    invalidatePort();clearProtected();
    sourceStatus('Reader disconnected · displayed source cleared.');
    el('refresh-source').disabled=true;el('disconnect-source').disabled=true;
    el('mode-note').textContent='Reader disconnected; not live chat. Workers are unaffected.';
  }
  async function refresh() {
    if(!connection.port||connection.busy)return false;
    const epoch=connection.epoch,read=connection.port,controller=new AbortController();
    connection.controller=controller;connection.busy=true;el('refresh-source').disabled=true;
    sourceStatus(fixedKind==='live-window'?'Reading the permitted observed window…':'Reading the selected recorded source…');
    let timer=null,timedOut=false,onAbort=null;
    const cancelled=new Promise((resolve,reject)=>{onAbort=()=>reject(new Error('reader_abort'));controller.signal.addEventListener('abort',onAbort,{once:true});});
    const timeout=new Promise((resolve,reject)=>{timer=setTimeout(()=>{timedOut=true;controller.abort();reject(new Error('reader_timeout'));},15000);});
    try {
      const result=await Promise.race([Promise.resolve().then(()=>read({signal:controller.signal})),cancelled,timeout]);
      if(connection.epoch!==epoch||controller.signal.aborted)return false;
      if(result&&['401','403'].includes(String(result.status))) {
        clearProtected();sourceStatus('Access unavailable · displayed source cleared.');return false;
      }
      if(!result||result.status!==200) {
        sourceStatus(connection.lastView?'Source unavailable · Last successful read retained.':'Source unavailable · no qualified content displayed.');return false;
      }
      const next=qualifyView(result.body,fixedLane);
      if(!next){sourceStatus(connection.lastView?'Read response refused · Last successful read retained.':'Read response refused · no content displayed.');return false;}
      applyView(next);sourceStatus(fixedKind==='live-window'?'Observed window read · not full conversation history.':'Read succeeded · source capture time retained.');return true;
    } catch(_) {
      if(connection.epoch!==epoch)return false;
      if(timedOut){sourceStatus(connection.lastView?'Read timed out · Last successful read retained.':'Read timed out · no qualified content displayed.');return false;}
      if(controller.signal.aborted)return false;
      sourceStatus(connection.lastView?'Source unavailable · Last successful read retained.':'Source unavailable · no qualified content displayed.');return false;
    } finally {
      clearTimeout(timer);controller.signal.removeEventListener('abort',onAbort);
      if(connection.epoch===epoch){connection.busy=false;connection.controller=null;el('refresh-source').disabled=!connection.port;}
    }
  }
  Object.defineProperty(window,'MastermindReadConnection',{value:Object.freeze({attach,refresh,detach}),writable:false,configurable:false});
  el('refresh-source').addEventListener('click',()=>{void refresh();});
  el('disconnect-source').addEventListener('click',detach);
  if(emptyBootstrap)clearProtected();else render();
})();
