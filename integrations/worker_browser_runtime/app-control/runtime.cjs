'use strict';
const fs = require('node:fs');
const path = require('node:path');

// The original Playwright/vault package lock remains byte-identical. Only this
// opt-in adapter has an additional SDK dependency, pinned in its own closure.
function assertRuntime() {
  for (const [base, name, version] of [
    ['..', '@playwright/mcp', '0.0.79'],
    ['..', 'playwright', '1.63.0-alpha-2026-08-05'],
    ['..', 'playwright-core', '1.63.0-alpha-2026-08-05'],
    ['.', '@modelcontextprotocol/sdk', '1.32.2'],
  ]) {
    const directory = path.resolve(__dirname, base, 'node_modules', name);
    const metadata = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
    if (metadata.name !== name || metadata.version !== version ||
        !fs.realpathSync(require.resolve(name === '@modelcontextprotocol/sdk' ? name + '/server/index.js' : name)).startsWith(fs.realpathSync(directory) + path.sep)) throw new Error('APP_PROFILE_DEPENDENCY_DRIFT');
  }
}
module.exports = { assertRuntime };
