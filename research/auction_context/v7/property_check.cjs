const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {computeAsOfAuctionContext:compute}=require('./compiled/auctionContext.js');
const {calculateFixedRangeVolumeProfile:profile}=require('./compiled/terminal_analytics_pinned.js');
const T=1788825600,source={provider:'property-fixture',instrument:'BTC-USD',venue:'test',priceUnit:'USD',volumeUnit:'BTC',vintage:'synthetic',timeBasis:'utc_epoch_seconds',calendar:'24x7_utc'};
let seed=1172026;const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
let assertions=0;const checks=[];
for(let scenario=0;scenario<250;scenario++){
 const count=21+Math.floor(rand()*80),cs=[],ps=[];let price=100+rand()*1000;
 for(let i=0;i<count*3+30;i++){const o=price,c=o+(rand()-.5)*2,h=Math.max(o,c)+rand(),l=Math.min(o,c)-rand(),v=.1+100*rand();
  cs.push({start:T+i*60,open:o,high:h,low:l,close:c,volume:v,observedAt:T+(i+1)*60});price=c;}
 for(let i=0;i<cs.length;i+=3){const q=cs.slice(i,i+3);ps.push({start:q[0].start,open:q[0].open,high:Math.max(...q.map(x=>x.high)),low:Math.min(...q.map(x=>x.low)),close:q[2].close,volume:q.reduce((s,x)=>s+x.volume,0),observedAt:q[2].start+60});}
 const req={source,decisionAt:T+count*180,analysisSeconds:180,lookback:count,bins:4+Math.floor(rand()*40),valueAreaFraction:.7,balancePeriods:20,evidenceMode:'selected_historical_vintage'};
 const p={source,seconds:180,rows:ps},c={source,seconds:60,rows:cs};
 const a=compute(req,p,c),b=compute(req,{...p,rows:ps.slice(0,count)},{...c,rows:cs.slice(0,count*3)});
 assert.deepEqual(a,b);assertions++;
 assert.equal(a.profile.state,'ready');assert.equal(a.flow.state,'ready');assertions+=2;
 const total=ps.slice(0,count).reduce((s,x)=>s+x.volume,0);assert.ok(Math.abs(a.profile.value.representedVolume-total)<1e-9*total);assertions++;
 const selected=cs.slice(count*3-60,count*3),v=selected.reduce((s,x)=>s+x.volume,0),d=selected.reduce((s,x)=>s+(x.close>x.open?x.volume:-x.volume),0);
 assert.ok(Math.abs(a.flow.value.balanceDeltaPct-100*(d/v))<1e-10);assertions++;
 assert.ok(a.flow.value.latestDeltaPct>=-100.0000000001&&a.flow.value.latestDeltaPct<=100.0000000001);assertions++;
 const stale=compute({...req,decisionAt:req.decisionAt+180},{...p,rows:ps.slice(0,count)},{...c,rows:cs.slice(0,count*3)});
 assert.equal(stale.profile.state,'incomplete_window');assertions++;
 checks.push({scenario,lookback:count,bins:req.bins,status:'PASS'});
}
const result={status:'PASS',scope:'250 fixed-seed synthetic scenarios, seven assertions each; not market validation',seed:1172026,scenarios:checks.length,assertions,checks,
 adapter_sha256:crypto.createHash('sha256').update(fs.readFileSync('source/auctionContext.ts')).digest('hex')};
fs.writeFileSync('results/property_report.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:result.status,scenarios:result.scenarios,assertions:result.assertions}));
