(function(){var ms=[...document.querySelectorAll('main')].filter(m=>m.offsetWidth>0);var m=ms[ms.length-1];if(!m)return 'NOMAIN';
var u=[...m.querySelectorAll('[data-chatgpt-search-unit-key]')].filter(e=>e.offsetWidth>0);
var roles=u.map(e=>e.getAttribute('data-chatgpt-search-unit-key'));
var as=u.filter(e=>/assistant$/.test(e.getAttribute('data-chatgpt-search-unit-key')));if(!as.length)return 'NOASST '+roles.join(',');
var a=as[as.length-1].cloneNode(true);
a.querySelectorAll('.katex').forEach(k=>{var t=k.querySelector('annotation[encoding="application/x-tex"]');if(t){var d=k.closest('.katex-display');var s=d?'\n$$'+t.textContent+'$$\n':'\\('+t.textContent+'\\)';(d||k).replaceWith(document.createTextNode(s));}});
a.querySelectorAll('button,svg,[aria-hidden="true"]').forEach(x=>x.remove());
var h=document.createElement('div');h.style.cssText='position:fixed;left:-99999px;top:0;width:900px;white-space:normal';h.appendChild(a);document.body.appendChild(h);var t=a.innerText;h.remove();t=t.replace(/^ChatGPT said:\s*/,'');return 'ROLES '+roles.join(',')+'\n=====\n'+t;})()
