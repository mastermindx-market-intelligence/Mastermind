// Protocol-only composition. Execution, authentication and retained results stay
// with the existing gateway/Fabric owners supplied by acquireScope.
import { Server, createMcpHandler, ProtocolError } from '@modelcontextprotocol/server';

function compatibleError(error) {
  // The incumbent gateway uses SDK v1 McpError. Preserve its code/data rather
  // than falsely turning an uncertain backend effect into a successful result.
  if (error?.name === 'McpError' && Number.isInteger(error.code)) {
    return new ProtocolError(error.code, error.message, error.data);
  }
  return error;
}

export function createModernFabricHandler({ acquireScope, serverInfo }) {
  if (typeof acquireScope !== 'function') throw new TypeError('acquireScope is required');
  const handler = createMcpHandler(async ({ authInfo }) => {
    const scope = await acquireScope({ authInfo });
    let released;
    const release = () => (released ??= Promise.resolve().then(() => scope.close()));
    let server;
    try {
      server = new Server(serverInfo, { capabilities: { tools: {} } });
      const closeServer = server.close.bind(server);
      let closed;
      server.close = () => (closed ??= (async () => {
        try { await closeServer(); } finally { await release(); }
      })());
      // A completed transport can close the protocol before close() is called.
      server.onclose = () => { void release().catch(() => {}); };
      server.setRequestHandler('tools/list', async (request, context) => {
        const params = typeof request.params?.cursor === 'string' ? { cursor: request.params.cursor } : {};
        try { return await scope.listTools({ method: 'tools/list', params },
          { signal: context.mcpReq.signal, requestId: context.mcpReq.id }); }
        catch (error) { throw compatibleError(error); }
      });
      server.setRequestHandler('tools/call', async (request, context) => {
        try {
          const result = await scope.callTool({ method: 'tools/call', params: {
            name: request.params.name, arguments: request.params.arguments ?? {},
          } }, { signal: context.mcpReq.signal, requestId: context.mcpReq.id });
          return server.projectCallToolResult(result, undefined);
        } catch (error) { throw compatibleError(error); }
      });
      return server;
    } catch (error) { await release(); throw error; }
  }, { legacy: 'reject' });
  return {
    fetch(request, options) {
      // This is pass-through trusted middleware state, never client _meta or
      // headers. The SDK deliberately does not authenticate it for the caller.
      if (!options?.authInfo || typeof options.authInfo !== 'object') {
        return Promise.resolve(new Response(JSON.stringify({ error: 'Authenticated gateway principal required' }),
          { status: 401, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } }));
      }
      return handler.fetch(request, options);
    },
    close() { return handler.close(); },
  };
}
