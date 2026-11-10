'use strict';

// Release-time catalogue extraction only; no browser, listener or credentials.
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { InMemoryTransport } = require('@modelcontextprotocol/sdk/inMemory.js');
const { createAppControlConnection } = require('./connection.cjs');

async function main() {
  const server = await createAppControlConnection({
    getContext: async () => { throw new Error('CATALOGUE_ONLY'); },
    origin: 'https://mcp.mastermind-x.com',
  });
  const client = new Client({ name: 'mastermind-app-profile-catalogue', version: '1.0.0' });
  try {
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    process.stdout.write(JSON.stringify(await client.listTools(), null, 2) + '\n');
  } finally {
    await client.close();
    await server.close();
  }
}
main().catch(() => { process.stderr.write('APP_PROFILE_CATALOGUE_FAILED\n'); process.exitCode = 1; });
