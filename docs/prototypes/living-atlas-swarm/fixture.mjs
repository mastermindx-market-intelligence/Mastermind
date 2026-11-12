/* Original, synthetic scenario. No real sessions, commands, or source observations. */
export const DURATION = 48;
export const PROJECTS = [
  { id:'team', label:'Always-on team', detail:'Paperclip · coordination', x:610, y:155, r:133, color:'#59dfcc' },
  { id:'os', label:'Mastermind OS', detail:'Portfolio reliability', x:980, y:370, r:170, color:'#9aa4ff' },
  { id:'terminal', label:'Terminal', detail:'Market intelligence', x:990, y:730, r:139, color:'#ff80b5' },
  { id:'macro', label:'Macro', detail:'Regime research', x:545, y:805, r:147, color:'#ebc475' },
  { id:'research', label:'Research', detail:'Source validation', x:235, y:555, r:143, color:'#78caff' },
  { id:'capacity', label:'Capacity Fabric', detail:'Placement observations', x:240, y:205, r:116, color:'#78dec0' }
];
export const RESOURCES = [
  { id:'assignment', project:'team', x:630,y:117,label:'Project brief',kind:'artifact' },
  { id:'teamlink', project:'team', x:677,y:203,label:'Teamlink',kind:'message' },
  { id:'source', project:'os',x:1095,y:250,label:'Portfolio view',kind:'file' },
  { id:'browser', project:'os',x:1135,y:435,label:'Browser check',kind:'browser' },
  { id:'shell', project:'os',x:860,y:450,label:'Targeted checks',kind:'process' },
  { id:'review', project:'os',x:855,y:275,label:'Change set',kind:'artifact' },
  { id:'pull-request',project:'os',x:1020,y:500,label:'Pull request',kind:'artifact'},
  { id:'news',project:'terminal',x:1055,y:713,label:'News flow',kind:'process'},
  { id:'chart',project:'terminal',x:937,y:776,label:'Chart output',kind:'artifact'},
  { id:'regime',project:'macro',x:598,y:760,label:'Regime model',kind:'file'},
  { id:'macro-result',project:'macro',x:496,y:860,label:'Research result',kind:'artifact'},
  { id:'sources',project:'research',x:187,y:512,label:'Primary sources',kind:'browser'},
  { id:'research-result',project:'research',x:304,y:588,label:'Source notes',kind:'artifact'},
  { id:'placement',project:'capacity',x:185,y:179,label:'Placement state',kind:'process'},
  { id:'pool',project:'capacity',x:290,y:248,label:'Pool observation',kind:'artifact'}
];
const s=(at,project,x,y,label,status='working',targets=[])=>({at,project,x,y,label,status,targets});
export const ACTORS = [
 {id:'meta',name:'Meta-CEO',role:'Always-on coordinator',owner:'Paperclip / native runtime',project:'team',born:0,color:'#59dfcc',parent:null,repo:null,steps:[
   s(0,'team',592,167,'Preparing the project brief','working',['assignment']),
   s(1.8,'team',641,188,'Sending the brief through Teamlink','working',['teamlink']),
   s(5,'capacity',261,221,'Inspecting the capacity observation','working',['pool']),
   s(10,'research',269,550,'Following source validation','working',['research-result']),
   s(16,'macro',559,811,'Inspecting the research handoff','working',['macro-result']),
   s(24,'team',599,180,'Waiting for the coding team','waiting'),
   s(33,'team',640,187,'Receiving the prepared change','working',['teamlink']),
   s(36,'team',601,166,'Awaiting the verification result','waiting'),
   s(45,'team',615,157,'Consuming the verified result','complete',['assignment'])]},
 {id:'lead',name:'T3 coding lead',role:'Project COO',owner:'T3 Code',project:'os',born:2.6,color:'#82f5e6',parent:'meta',repo:'Mastermind',steps:[
   s(2.6,'os',927,343,'Tracing the Portfolio return path','working',['review','source']),
   s(5.2,'os',973,347,'Delegating source and browser checks','working',['source','browser']),
   s(9,'os',924,408,'Starting targeted checks','working',['shell']),
   s(12,'os',1044,362,'Inspecting the route in a browser','working',['browser']),
   s(18,'os',929,407,'Investigating a failing check','attention',['shell']),
   s(21,'os',999,309,'Applying a focused correction','working',['source']),
   s(24,'os',1052,359,'Verifying the corrected route','working',['browser']),
   s(28,'os',966,350,'Collecting helper results','working',['review']),
   s(32,'os',982,425,'Preparing the pull request','working',['pull-request']),
   s(35,'os',976,375,'PR ready; awaiting merge observation','waiting'),
   s(40,'os',1053,365,'Merged; product check still running','working',['browser']),
   s(44,'os',977,362,'Product behavior verified','complete')]},
 {id:'ui',name:'Source helper',role:'Delegated implementation',owner:'T3 child session',project:'os',born:5.4,color:'#a9b1ff',parent:'lead',repo:'Mastermind',steps:[
   s(5.4,'os',1005,220,'Reading the affected view','working',['source']),
   s(11,'os',1055,219,'Saving the first correction','working',['source']),
   s(17,'os',1025,226,'Waiting for the check result','waiting'),
   s(21.2,'os',1065,238,'Saving the follow-up correction','working',['source']),
   s(27,'os',998,264,'Returning the source change','complete')]},
 {id:'browser-helper',name:'Browser helper',role:'Delegated verification',owner:'T3 child session',project:'os',born:6.2,color:'#d0b4ff',parent:'lead',repo:'Mastermind',steps:[
   s(6.2,'os',1146,471,'Reproducing the Portfolio failure','working',['browser']),
   s(14,'os',1130,487,'Waiting for the correction','waiting'),
   s(24.2,'os',1166,474,'Checking the updated interaction','working',['browser']),
   s(29,'os',1116,477,'Returning browser evidence','complete')]},
 {id:'researcher',name:'Research bot',role:'Always-on researcher',owner:'Paperclip / native runtime',project:'research',born:0,color:'#78caff',parent:'meta',repo:'Research',steps:[
   s(0,'research',238,530,'Comparing primary sources','working',['sources']),
   s(7,'research',274,567,'Writing the source notes','working',['research-result']),
   s(12,'research',245,548,'Waiting for the next source','waiting'),
   s(16,'research',205,529,'Checking a new observation','working',['sources']),
   s(22,'research',278,574,'Returning source notes to Macro','complete')]},
 {id:'macro-lead',name:'Macro lead',role:'Project lead',owner:'T3 Code',project:'macro',born:0,color:'#ebc475',parent:null,repo:'Macro',steps:[
   s(0,'macro',544,788,'Reviewing regime inputs','working',['regime']),
   s(9.8,'macro',507,825,'Running the research check','working',['macro-result']),
   s(18,'macro',546,800,'Awaiting source validation','waiting'),
   s(23,'macro',574,779,'Integrating the source notes','working',['regime']),
   s(31,'macro',514,835,'Returning the analysis','complete')]},
 {id:'terminal-lead',name:'Terminal lead',role:'Project lead',owner:'T3 Code',project:'terminal',born:0,color:'#ff80b5',parent:null,repo:'Terminal',steps:[
   s(0,'terminal',1018,728,'Inspecting the news update path','working',['news']),
   s(8,'terminal',967,749,'Checking a chart update','working',['chart']),
   s(19,'terminal',1029,714,'Inspecting the next update','working',['news']),
   s(32,'terminal',973,747,'Waiting for a new source observation','waiting')]},
 {id:'capacity-bot',name:'Capacity observer',role:'Always-on operations',owner:'Existing capacity owner',project:'capacity',born:0,color:'#78dec0',parent:'meta',repo:'Mastermind',steps:[
   s(0,'capacity',220,195,'Reading placement observations','working',['placement']),
   s(10,'capacity',259,229,'Inspecting the pool observation','working',['pool']),
   s(20,'capacity',218,190,'Refreshing the qualified observation','working',['placement']),
   s(30,'capacity',253,225,'Waiting for a new observation','waiting')]}
];
export const SIGNALS=[
 {at:1.9,duration:.85,from:[655,194],to:[928,343],label:'Assignment',color:'#59dfcc',kind:'teamlink',scope:'t3'},
 {at:5.4,duration:.4,from:[973,347],to:[1005,220],label:'Source helper',color:'#a9b1ff',kind:'delegation',scope:'t3'},
 {at:6.2,duration:.45,from:[973,347],to:[1146,471],label:'Browser helper',color:'#d0b4ff',kind:'delegation',scope:'t3'},
 {at:22.2,duration:.9,from:[278,574],to:[574,779],label:'Source notes',color:'#78caff',kind:'result',scope:'research'},
 {at:28,duration:.45,from:[998,264],to:[966,350],label:'Change returned',color:'#a9b1ff',kind:'result',scope:'t3'},
 {at:29,duration:.5,from:[1116,477],to:[966,350],label:'Evidence returned',color:'#d0b4ff',kind:'result',scope:'t3'},
 {at:33.5,duration:.95,from:[982,425],to:[640,187],label:'PR prepared',color:'#82f5e6',kind:'teamlink',scope:'t3'},
 {at:44.5,duration:.95,from:[977,362],to:[615,157],label:'Verification result',color:'#82f5e6',kind:'teamlink',scope:'t3'}
];
export const EVENTS=[
 {at:0,label:'A project brief is prepared',actor:'meta',kind:'Brief',detail:'The always-on team holds the objective and context.'},
 {at:1.9,label:'Teamlink carries the assignment',actor:'meta',kind:'Handoff',detail:'A message crosses to a distinct T3 execution.'},
 {at:2.6,label:'The T3 coding lead starts',actor:'lead',kind:'Started',detail:'A new observed session is separate from the persistent coordinator.'},
 {at:5.4,label:'The source helper starts',actor:'ui',kind:'Helper',detail:'An explicit parent–child relationship is visible.'},
 {at:6.2,label:'The browser helper starts',actor:'browser-helper',kind:'Helper',detail:'Two helpers now work alongside their lead.'},
 {at:9,label:'A check process starts',actor:'lead',kind:'Process',detail:'The process stays at its station when the lead moves away.'},
 {at:11,label:'A file change is confirmed',actor:'ui',kind:'Saved',detail:'A confirmed effect, separate from a requested edit.'},
 {at:12,label:'The lead moves to browser inspection',actor:'lead',kind:'Browser',detail:'The independent check process continues.'},
 {at:18,label:'The targeted check fails',actor:'lead',kind:'Attention',detail:'Attention interrupts the previous work pose.'},
 {at:21.2,label:'A correction is saved',actor:'ui',kind:'Saved',detail:'The follow-up edit has its own observation.'},
 {at:22.2,label:'Research returns notes to Macro',actor:'researcher',kind:'Result',detail:'An unrelated team continues concurrently.'},
 {at:23,label:'The targeted checks restart',actor:'lead',kind:'Process',detail:'The retry is a separate process attempt.'},
 {at:26,label:'The targeted checks pass',actor:'lead',kind:'Checks',detail:'Passing checks do not imply merge or deployment.'},
 {at:29,label:'Browser evidence returns',actor:'browser-helper',kind:'Evidence',detail:'The helper result is available to its parent.'},
 {at:33.5,label:'The pull request is prepared',actor:'lead',kind:'PR ready',detail:'Prepared delivery is distinct from merge.'},
 {at:35,label:'The coordinator reads the return',actor:'meta',kind:'Consumed',detail:'Delivery and consumption are separate observations.'},
 {at:40,label:'A merge is observed',actor:'lead',kind:'Merged',detail:'The product verification remains pending.'},
 {at:44,label:'The product check is verified',actor:'lead',kind:'Verified',detail:'This distinct observation completes the example journey.'},
 {at:45.5,label:'The verified result is consumed',actor:'meta',kind:'Consumed',detail:'The always-on team receives the final result.'}
];
export const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
export const smooth=v=>{v=clamp(v);return v*v*v*(v*(v*6-15)+10);};
export function actorAt(actor,time,motion='full'){
 if(time<actor.born)return null;
 let index=0;for(let i=1;i<actor.steps.length&&actor.steps[i].at<=time;i++)index=i;
 const step=actor.steps[index],prev=actor.steps[Math.max(0,index-1)];
 const dx=step.x-prev.x,dy=step.y-prev.y,distance=Math.hypot(dx,dy);
 const duration=motion==='off'?0:motion==='calm'?.55:distance>180?.72:.31;
 const u=duration===0?1:clamp((time-step.at)/duration),f=smooth(u);
 const arc=motion==='full'?Math.sin(Math.PI*u)*Math.min(26,distance*.18):0;
 return {...actor,...step,x:prev.x+dx*f,y:prev.y+dy*f-arc,stepIndex:index,
  heading:distance>1?Math.atan2(dy,dx):.1+actor.born*.3,moving:u<1&&distance>1,
  age:time-step.at,targets:step.targets,sourceTime:time,fromX:prev.x,fromY:prev.y,travelDuration:duration,travelProgress:u};
}
export function snapshotAt(time,{motion='full',lostAt=null}={}){
 const t=clamp(time,0,DURATION),isT3=id=>['lead','ui','browser-helper'].includes(id);
 const actors=ACTORS.map(a=>{
  const stale=lostAt!==null&&isT3(a.id);const aTime=stale?Math.min(t,lostAt):t;
  const pose=actorAt(a,aTime,motion),terminal=pose?.status==='complete';return pose?{...pose,stale,status:stale&&!terminal?'unobserved':pose.status,
   label:stale?(terminal?'Result previously returned; T3 feed now unobserved':'T3 observation lost; current work unknown'):pose.label,targets:stale?[]:pose.targets,moving:stale?false:pose.moving}:null;
 }).filter(Boolean);
 const ptime=lostAt===null?t:Math.min(t,lostAt);
 let process=null;
 if(ptime>=9){const observed=ptime<18?'running':ptime<23?'failed':ptime<26?'running':'passed',state=lostAt!==null&&observed==='running'?'unobserved':observed;
  process={id:'checks',x:860,y:450,label:'Targeted checks',state,stale:lostAt!==null,attempt:ptime>=23?2:1,startedAt:ptime>=23?23:9};}
 const events=EVENTS.filter(e=>e.at<=t&&!(lostAt!==null&&isT3(e.actor)&&e.at>lostAt));
 const signals=SIGNALS.filter(e=>t>=e.at&&t<e.at+e.duration&&!(lostAt!==null&&e.scope==='t3'));
 return {time:t,projects:PROJECTS,resources:RESOURCES,actors,process,events,signals,partial:lostAt!==null,finished:t>=DURATION};
}
