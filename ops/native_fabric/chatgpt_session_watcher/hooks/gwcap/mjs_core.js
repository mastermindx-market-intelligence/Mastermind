// mjs_core.js — ScriptingBridge-by-PID driver for Chrome and every Mimic/Orbita instance.
// argv: mode(list|exec) pid profileFilter(""|Chris|Ryan) win(id|active|"") jsfile tab(""|1-based)
ObjC.import('ScriptingBridge');ObjC.import('Foundation');
function U(x){return ObjC.unwrap(x)}
function seNames(pid){try{var se=Application('System Events');var p=se.processes.whose({unixId:pid});return p.length?p[0].windows.name():[]}catch(e){return null}}
function run(a){
 var mode=a[0],pid=parseInt(a[1]),prof=a[2]||'',win=a[3]||'active',jsf=a[4]||'',tab=a[5]||'';
 var app=$.SBApplication.applicationWithProcessIdentifier(pid);
 var ws;try{ws=app.valueForKey('windows')}catch(e){return 'NOAPP '+pid}if(!ws)return 'NOAPP '+pid;
 var names=prof?seNames(pid):null;var W=[];
 for(var i=0;i<ws.count;i++){var w=ws.objectAtIndex(i);var id=String(U(w.valueForKey('id')));var nm=String(U(w.valueForKey('name'))||'');
  var p='';if(names){var se=names.find(n=>n.indexOf(nm)===0);if(se){var m=se.match(/ - (Google Chrome|Mimic) - (.+)$/);p=m?m[2]:''}}
  if(prof&&p!==prof)continue;W.push({w:w,id:id,name:nm,profile:p});}
 if(mode==='list'){var out=[];W.forEach(function(x){var tabs=x.w.valueForKey('tabs');var at=x.w.valueForKey('activeTab');var atid=String(U(at.valueForKey('id')));
   out.push('WIN '+x.id+(x.profile?' ['+x.profile+']':'')+' tabs='+tabs.count+' name="'+x.name+'"');
   for(var j=0;j<tabs.count;j++){var t=tabs.objectAtIndex(j);out.push('   '+(String(U(t.valueForKey('id')))===atid?'*':' ')+'['+(j+1)+'] '+String(U(t.valueForKey('title'))).slice(0,60)+' | '+String(U(t.valueForKey('URL'))).slice(0,140));}});
  return out.join('\n')||'NOWINDOWS';}
 var tw=win==='active'?W[0]:W.find(x=>x.id===win);if(!tw)return 'NOWIN '+win+' (have '+W.map(x=>x.id).join(',')+')';
 var t=tab?tw.w.valueForKey('tabs').objectAtIndex(parseInt(tab)-1):tw.w.valueForKey('activeTab');
 var sel=U($.NSString.stringWithContentsOfFileEncodingError($.NSHomeDirectory().js+'/gwcap/gpt_sel.js',4,null));
 var src=U($.NSString.stringWithContentsOfFileEncodingError(jsf,4,null));
 var r=t.performSelectorWithObject('executeJavascript:',$(sel+'\n;'+src));return String(U(r));
}
