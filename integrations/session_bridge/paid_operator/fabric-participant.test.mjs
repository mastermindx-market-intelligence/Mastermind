import test from 'node:test';
import assert from 'node:assert/strict';
import { createOperatorHandler, FABRIC_OPERATOR_TOOLS } from './fabric-operator.mjs';
const TOKEN='a'.repeat(64);


test('participant metadata routes use only authenticated incumbent owner capability', async () => {
  const calls=[];
  const handler=createOperatorHandler(async(action,token,args)=>{calls.push({action,token,args});return {scientific_admission:false};});
  const args={run_id:'child-one',binding_sha256:'a'.repeat(64),object_id:'principal-one'};
  const denied=await handler('fabric_participant_metadata',args,{});
  assert.equal(denied.isError,true);assert.equal(calls.length,0);
  const auth={fabricOperator:{token:TOKEN}};
  const value=await handler('fabric_participant_metadata',args,auth);
  assert.equal(value.isError,false);assert.equal(calls[0].action,'participant_metadata');
  assert.equal(calls[0].token,TOKEN);assert.deepEqual(calls[0].args,args);
  const publicText=JSON.stringify(value);assert.equal(publicText.includes(TOKEN),false);
  for(const name of ['fabric_participant_metadata','fabric_participant_observation']){
    const tool=FABRIC_OPERATOR_TOOLS.find(t=>t.name===name);
    assert.equal(tool.annotations.readOnlyHint,true);
    assert.equal(tool.inputSchema.additionalProperties,false);
    assert.equal('role' in tool.inputSchema.properties,false);
    assert.equal('reader' in tool.inputSchema.properties,false);
    assert.equal('rating' in tool.inputSchema.properties,false);
  }
});
