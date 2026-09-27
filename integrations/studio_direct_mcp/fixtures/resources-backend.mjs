import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
const server = new McpServer({name:'resource-fixture',version:'1.0.0'});
const uri='ui://studio-test/preview';
server.registerResource('preview',uri,{mimeType:'text/html'},async () => ({contents:[{
  uri,mimeType:'text/html',text:`<p>Resource fixture process ${process.pid}</p>`,
  _meta:{fixturePid:process.pid}
}]}));
server.registerTool('preview',{description:'Read-only preview fixture',inputSchema:{},
  annotations:{readOnlyHint:true},_meta:{'openai/outputTemplate':uri}},async()=>({content:[{type:'text',text:'preview'}]}));
await server.connect(new StdioServerTransport());
