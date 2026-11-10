// Mastermind Core — manifest V1. Pure data: the host loads this module with a
// plain dynamic import from the plugin directory, so it must not import the
// SDK (or anything else).
export const manifest = {
  id: 'mastermind.core',
  apiVersion: 1,
  version: '0.1.0',
  displayName: 'Mastermind Core',
  description:
    'First Mastermind OS module. One page, one sidebar entry, one roster-truth dashboard widget, one agent tool and one health check. Displays and joins; never admits, schedules, retries or accepts work.',
  author: 'Mastermind OS lane L9',
  categories: ['ui', 'workspace'],
  capabilities: [
    'agents.read',
    'ui.page.register',
    'ui.sidebar.register',
    'ui.dashboardWidget.register',
    'agent.tools.register',
    'plugin.state.read',
    'plugin.state.write',
  ],
  entrypoints: {
    worker: 'dist/worker.js',
    ui: 'dist/ui',
  },
  ui: {
    slots: [
      {
        type: 'page',
        id: 'mastermind-core-page',
        displayName: 'Mastermind',
        exportName: 'MastermindPage',
        routePath: 'mastermind',
      },
      {
        type: 'sidebar',
        id: 'mastermind-core-sidebar',
        displayName: 'Mastermind',
        exportName: 'MastermindSidebar',
      },
      {
        type: 'dashboardWidget',
        id: 'roster-truth',
        displayName: 'Roster truth',
        exportName: 'RosterTruthWidget',
      },
    ],
  },
  tools: [
    {
      name: 'roster-report',
      displayName: 'Roster report',
      description:
        'Reports the four roster-truth counts — configured roles, enrolled agents, reachable agents, agents with active work — together with the source each count came from and any source that could not be read.',
      parametersSchema: {
        type: 'object',
        properties: {
          companyId: {
            type: 'string',
            description: 'Company to report on. Defaults to the company of the invoking run.',
          },
        },
        additionalProperties: false,
      },
    },
  ],
}

export default manifest
