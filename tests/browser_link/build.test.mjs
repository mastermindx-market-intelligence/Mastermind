import test from 'node:test';
import assert from 'node:assert/strict';
import { Script, createContext, runInContext } from 'node:vm';
import { webcrypto } from 'node:crypto';
import { buildWebSolLink } from '../../integrations/mastermind_browser_link/build.mjs';

const event=()=>({listeners:[],addListener(fn){this.listeners.push(fn);}});

test('classic build is deterministic, self-contained, and coexists with Web Sol globals', async () => {
  const first=await buildWebSolLink(), second=await buildWebSolLink();
  assert.deepEqual(first.receipt,second.receipt);
  assert.deepEqual(Object.keys(first.assets).sort(),[
    'browser-link-bootstrap.js','browser-link/popup.css','browser-link/popup.html',
    'browser-link/popup.mjs','browser-link/worker.bundle.js',
  ]);
  const chrome={
    runtime:{id:'a'.repeat(32),getURL:p=>'chrome-extension://'+'a'.repeat(32)+'/'+p,
      onMessage:event(),onInstalled:event(),onStartup:event(),
      connectNative(){throw new Error('No native host in this source test');}},
    debugger:{sendCommand(){},onDetach:event(),onEvent:event()},
    tabs:{get(){},onRemoved:event(),onUpdated:event()},
    storage:{local:{async get(){return {};},async set(){}}},
    alarms:{onAlarm:event(),async get(){return {periodInMinutes:1};},async create(){}},
    action:{async setBadgeText(){assert.fail('Link must not take over the Web Sol badge');}},
  };
  const context=createContext({chrome,crypto:webcrypto,setTimeout,clearTimeout,TextEncoder,URL,
    MMX_WEB_SOL_INSTANCE:Object.freeze({instanceId:'c'.repeat(64)})});
  // Execute as a classic script in an already-populated Web Sol global scope.
  new Script("const nativePort='existing-web-sol'; const controller='existing-web-sol';").runInContext(context);
  new Script(first.assets['browser-link/worker.bundle.js'].toString('utf8')).runInContext(context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(runInContext('nativePort',context),'existing-web-sol');
  assert.equal(runInContext('controller',context),'existing-web-sol');
  let responded=false;
  const listener=chrome.runtime.onMessage.listeners[0];
  assert.equal(listener({kind:'MMX_WEB_SOL_CENSUS_REFRESH'},
    {id:chrome.runtime.id,url:chrome.runtime.getURL('census.html')},()=>{responded=true;}),false);
  assert.equal(responded,false);
  assert.equal(first.receipt.is_installation,false);
  assert.equal(first.receipt.compiler_version,'0.28.2');
});
