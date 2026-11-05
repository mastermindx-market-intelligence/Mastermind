(function(){var out=[];var acct=(document.querySelector('nav [data-testid="accounts-profile-button"]')||{}).innerText||'';
out.push('T='+document.title+' | acct='+acct.replace(/\n/g,' ').slice(0,60));
var vis=[...document.querySelectorAll('button')].filter(b=>b.offsetWidth>0);
out.push('stop='+vis.some(b=>/Stop/i.test(b.getAttribute('aria-label')||''))+' maxlen='+document.body.innerText.includes('maximum length for this conversation'));
var seen={};document.querySelectorAll('nav a[href*="/c/"]').forEach(a=>{var m=a.href.match(/\/c\/([0-9a-f-]{36})/);if(!m||seen[m[1]])return;seen[m[1]]=1;
var proj=(a.getAttribute('href').split('/c/')[0].split('-').pop())||'-';var t=a.innerText.replace(/\n/g,' ').trim();
var row=a.closest('li')||a.parentElement;var rt=(row?row.innerHTML:'');var unread=/Unread|unread/.test(rt)||/Unread/.test(a.getAttribute('aria-label')||'');
out.push(m[1].slice(0,8)+'|'+m[1]+'|'+proj+'|'+t+(unread?'|UNREAD':''));});
return out.join('\n');})()
