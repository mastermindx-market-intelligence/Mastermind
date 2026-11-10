// Paperclip module manifest — PURE DATA. No imports, no code: the host loads
// this file with a plain dynamic import. Everything the host needs to mount
// your UI and fork your worker is described here.
//
// Replace REPLACE-ME with your plugin id (reverse-dns style, e.g.
// mastermind.core). The package.json "name" must differ (it is a package
// name, not the plugin id).
export default {
  id: 'REPLACE-ME.core',
  apiVersion: 1,
  displayName: 'REPLACE ME',
  description: 'One sentence: what this module shows. It displays and joins; it never admits, schedules, retries or accepts work.',
  author: 'Mastermind OS',
  version: '0.1.0',
  categories: ['ui', 'workspace'],
  capabilities: [
    'agents.read',
    'plugin.state.read',
    'plugin.state.write',
    'ui.page.register',
    'agent.tools.register',
  ],
  entrypoints: {
    worker: 'dist/worker.js',
    ui: 'dist/ui',
  },
  ui: {
    slots: [
      // routePath 'foo' mounts the page at /:companyPrefix/foo
      {
        id: 'REPLACE-ME-page',
        type: 'page',
        routePath: 'REPLACE-ME',
        exportName: 'ModulePage',
        displayName: 'REPLACE ME',
      },
    ],
  },
  tools: [
    {
      name: 'REPLACE-ME-report',
      displayName: 'REPLACE ME report',
      description: 'What the tool reports, and which source each fact came from.',
      parametersSchema: {
        type: 'object',
        properties: {
          companyId: { type: 'string', description: 'Company to report on; defaults to the run company.' },
        },
        additionalProperties: false,
      },
    },
  ],
}
