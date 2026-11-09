'use strict';

// Opt-in entry for the original one-resource Workbench relay. Stdio only.
const path = require('node:path');
const { chromium } = require('playwright');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { validateOrigin } = require('./adapter.cjs');
const { createAppControlConnection } = require('./connection.cjs');

function options(argv) {
  const values = Object.create(null);
  const valueFlags = new Set(['--app-origin', '--browser', '--executable-path', '--output-dir', '--user-data-dir']);
  const boolFlags = new Set(['--headless', '--isolated']);
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index];
    if (Object.hasOwn(values, flag)) throw new Error('DUPLICATE_OPTION');
    if (boolFlags.has(flag)) values[flag] = true;
    else if (valueFlags.has(flag) && argv[index + 1] && !argv[index + 1].startsWith('--')) values[flag] = argv[++index];
    else throw new Error('UNSUPPORTED_OPTION');
  }
  validateOrigin(values['--app-origin']);
  if (values['--browser'] !== 'chrome' || !values['--headless'] ||
      Boolean(values['--isolated']) === Boolean(values['--user-data-dir'])) throw new Error('OWNER_MODE_REQUIRED');
  for (const flag of ['--executable-path', '--output-dir', '--user-data-dir']) {
    const value = values[flag];
    if (value === undefined && flag === '--user-data-dir') continue;
    if (typeof value !== 'string' || !path.isAbsolute(value) || path.normalize(value) !== value || value.includes('\0')) throw new Error('OWNER_PATH_REQUIRED');
  }
  return values;
}
async function main(argv) {
  const config = options(argv);
  let context, browser, starting, retired = false;
  const getContext = async () => {
    if (retired) throw new Error('BROWSER_RESOURCE_RETIRED');
    if (context) return context;
    if (!starting) starting = (async () => {
      const launch = { executablePath: config['--executable-path'], headless: true };
      if (config['--isolated']) {
        browser = await chromium.launch(launch);
        context = await browser.newContext();
      } else context = await chromium.launchPersistentContext(config['--user-data-dir'], launch);
      context.once('close', () => { retired = true; });
      return context;
    })();
    return starting;
  };
  const server = await createAppControlConnection({ getContext, origin: config['--app-origin'], outputDir: config['--output-dir'] });
  let stopping = false;
  const stop = async () => {
    if (stopping) return;
    stopping = true; retired = true;
    await server.close();
    await context?.close().catch(() => {});
    await browser?.close().catch(() => {});
  };
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void stop(); });
  process.stdin.once('end', () => { void stop(); });
  await server.connect(new StdioServerTransport());
}
if (require.main === module) main(process.argv.slice(2)).catch(() => { process.stderr.write('APP_BROWSER_PROFILE_START_FAILED\n'); process.exitCode = 1; });
module.exports = { options, main };
