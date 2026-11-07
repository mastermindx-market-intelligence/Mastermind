'use strict';
// Ordinary CI only: real pinned engines, synthetic HTTPS responses, fresh owned
// context. The HTTP route is a fixture seam; no account, CDP or TLS bypass.
const path = require('node:path');
const [source, runtimeRoot, outputDir, resourceId, expiry] = process.argv.slice(2);
const receiver = require(source);
const playwright = require(path.join(runtimeRoot, 'node_modules/playwright'));
async function main() {
  const owned = await receiver.createOwnedSession({ runtimeRoot,
    chromeExecutable: playwright.chromium.executablePath(), outputDir,
    resourceId, resourceExpiry: Number(expiry) });
  try {
    await owned.context.route('https://vault.test/**', async route => {
      const which = new URL(route.request().url()).pathname;
      const script = which === '/partial' ?
        `document.querySelector('[name=username]').addEventListener('input',()=>{document.querySelector('form').action='https://other.test';});` :
        which === '/override' ?
        `Object.defineProperty(HTMLInputElement.prototype,'value',{configurable:true,get(){return this._fake||'';},set(v){this._fake=v;}});` :
        `document.querySelector('[type=password]').addEventListener('input', e => {
          const s=e.target.value;
          for(const value of [s,JSON.stringify(s),encodeURIComponent(s),new URLSearchParams({v:s}).toString(),s.replaceAll("'","''"),s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;')]) {
            console.log(value); const node=document.createElement('p');node.textContent=value;document.body.appendChild(node);
          }
        });`;
      const second = which === '/ambiguous' ? '<input type=password autocomplete=current-password>' : '';
      const autocomplete = which === '/new-password' ? 'new-password' : 'current-password';
      await route.fulfill({ status: 200, contentType: 'text/html', body:
        '<!doctype html><title>Vault engine fixture</title><form action="/submit"><label>Account <input name=username autocomplete=username></label>' +
        '<label>Password <input type=password autocomplete=' + autocomplete + '></label>' + second + '<button>Log in</button></form><script>' + script + '</script>' });
    });
    process.on('SIGTERM', () => { void owned.close(); });
    process.on('SIGINT', () => { void owned.close(); });
    await owned.server.connect(owned.transport);
  } catch { await owned.close(); throw new Error('PINNED_FIXTURE_FAILED'); }
}
main().catch(() => { process.exitCode = 70; process.stderr.write('PINNED_FIXTURE_FAILED\n'); });
