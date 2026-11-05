#!/bin/bash
# gb2-nofocus (Nov 3 2026, Chris t58s491 "Make sends without focusing the message box"): NO focus()/execCommand/select/
#  scrollIntoView/keystrokes. Text goes in via a synthetic ClipboardEvent('paste') on the ProseMirror editor (handled by
#  ProseMirror without focus); model pill is forced to Extra High via dispatched events (never Pro); Send via dispatched click.
#  Previous versions: jsend.sh.bak-gb2-nofocus-*, jsend.sh.bak-gb2fix-1632
# jsend.sh WINID "Exact Title" promptfile   (TAB=<n> honored via cjs.sh/mjs.sh)
# A leftover draft is replaced (dispatched Mod-A keydown to ProseMirror selectAll, then paste). No OS keystrokes.
# exit: 0 SENT | 2 refused (TITLE_MISMATCH/RUNNING/NO_EDITOR/NO_SEND) | 3 PASTE_FAILED | 4 MODEL_NOT_EH
txt=$(python3 -c "import sys,json; print(json.dumps(open(sys.argv[1]).read().strip()))" "$3")
ttl=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$2")
W=$1; J=/tmp/jsend_nf.$$.js; trap 'rm -f $J' EXIT
PRE="if(document.title!==$ttl)return 'TITLE_MISMATCH '+document.title;var vis=GS.vis;
var B=[...document.querySelectorAll('button')].filter(vis);
var pill=[...document.querySelectorAll('button[aria-label=\"Select ChatGPT model\"]')].filter(vis).pop();
var pv=pill?pill.innerText.replace(/Thinking effort/g,'').replace(/\\s+/g,' ').trim():'';
var menu=[...document.querySelectorAll('[role=menu]')].filter(vis).pop();
var ed=[...document.querySelectorAll(GS.S.editor)].filter(vis).pop();"
run(){ printf '(function(){%s\n%s})()\n' "$PRE" "$1" > $J; ~/gwcap/cjs.sh $W $J; }
closemenu='if(menu&&pill){GS.click(pill);}'
# 1) preflight
r=$(run "if(B.some(b=>(b.getAttribute('aria-label')||'').startsWith('Stop')))return 'RUNNING';if(!ed)return 'NO_EDITOR';if(!pill)return 'NO_PILL';return 'OK pill='+pv+' draft='+ed.innerText.trim().length;")
echo "PRE $r"; case "$r" in OK*) ;; NO_PILL*) echo MODEL_NOT_EH; exit 4;; *) exit 2;; esac
p0=${r#OK pill=}; p0=${p0% draft=*}
# 2) force Extra High (bounded loop; never Pro)
ok=0
for i in 1 2 3 4 5 6 7; do
 r=$(run "if(!menu){if(pv==='Extra High')return 'EH_OK';GS.click(pill);return 'OPENED pill='+pv;}
var lab=(menu.querySelector('[class*=EffortLabel]')||{innerText:''}).innerText.trim();var s=menu.querySelector('[role=slider]');
if(s&&lab==='Extra High'){GS.click(pill);return 'EH_SET_CLOSE';}
if(s){var v=+s.getAttribute('aria-valuenow');var k=(lab==='Pro'||v>3)?'ArrowLeft':'ArrowRight';
 var o={key:k,code:k,keyCode:k==='ArrowLeft'?37:39,which:k==='ArrowLeft'?37:39,bubbles:true,cancelable:true};
 s.dispatchEvent(new KeyboardEvent('keydown',o));s.dispatchEvent(new KeyboardEvent('keyup',o));return 'STEP '+k+' from='+lab+'/'+v;}
var th=[...menu.querySelectorAll('[role^=menuitem]')].find(e=>/^Thinking/.test(e.innerText.trim()));if(th){GS.click(th);return 'PICK_THINKING';}
GS.click(pill);return 'NO_SLIDER_NO_THINKING menu='+menu.innerText.replace(/\\s+/g,' ').slice(0,120);")
 echo "MODEL $r"
 case "$r" in EH_OK|EH_SET_CLOSE) ok=1; break;; TITLE_MISMATCH*) exit 2;; NO_SLIDER_NO_THINKING*) break;; esac
 sleep 1.2
done
if [ $ok != 1 ]; then run "$closemenu return 'closed';" >/dev/null; echo "MODEL_NOT_EH (pill was '$p0')"; exit 4; fi
echo "PILL before='$p0' after='Extra High'"
# 3) no-focus insert: synthetic paste event (ProseMirror handlePaste works without focus)
r=$(run "if(!ed)return 'NO_EDITOR';if(pv!=='Extra High')return 'MODEL_NOT_EH';var d0=ed.innerText.trim().length;if(d0){var ko={key:'a',code:'KeyA',keyCode:65,which:65,metaKey:true,bubbles:true,cancelable:true};ed.dispatchEvent(new KeyboardEvent('keydown',ko));ed.dispatchEvent(new KeyboardEvent('keyup',ko));}
var dt=new DataTransfer();dt.setData('text/plain',$txt);ed.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
var n=s=>s.replace(/\\s+/g,'');return n(ed.innerText)===n($txt)?'INSERTED '+ed.innerText.length+(d0?' (replaced draft '+d0+')':''):'PASTE_MISMATCH len='+ed.innerText.length;")
echo "$r"; case "$r" in INSERTED*) ;; MODEL_NOT_EH*) echo MODEL_NOT_EH; exit 4;; PASTE_MISMATCH*) echo PASTE_FAILED; exit 3;; *) exit 2;; esac
sleep 1.2
# 4) send via dispatched click (no focus); re-check model right before
r=$(run "if(pv!=='Extra High')return 'MODEL_NOT_EH';var b=B.find(x=>/^Send/.test(x.getAttribute('aria-label')||''));if(!b)return 'NO_SEND';b.click();return 'SENT';")
echo "$r"; case "$r" in SENT) exit 0;; MODEL_NOT_EH) exit 4;; *) exit 2;; esac
