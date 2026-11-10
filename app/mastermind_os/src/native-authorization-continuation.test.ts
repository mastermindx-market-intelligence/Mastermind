import {expect, it} from "vitest";
import {decodeNativeAuthorizationContinuation as decode} from "./native-authorization-continuation";
const yes = {schema:"mastermind.native_authorization_continuation.v1",state:"ELIGIBLE",resource:"CONTENT",reason:"CONTENT_PENDING_TIMEOUT"};
const no = {...yes,state:"INELIGIBLE",resource:null,reason:"NOT_ELIGIBLE"};
it.each([yes,no])("copies only the exact closed native metadata variant", value => {
  const decoded = decode(value); expect(decoded).toEqual(value); expect(decoded).not.toBe(value);
});
it.each([null,[],{}, {...yes, schema:"old"}, {...yes, resource:"EXECUTIVE"}, {...yes, reason:"NOT_ELIGIBLE"},
  {...no,resource:"CONTENT"}, {...yes,account:"caller"}, {...yes,token:"forged"}, Object.create(yes),
  Object.assign(Object.create({foreign:true}),yes), {...yes,[Symbol("extra")]:true}])("refuses foreign/mixed/extra metadata %#", value => expect(decode(value)).toBeNull());
it("never evaluates accessors or accepts hidden fields", () => {
  const getter = {...yes};Object.defineProperty(getter,"reason",{enumerable:true,get:()=>{throw new Error("must not execute");}});
  expect(decode(getter)).toBeNull();const hidden={...yes};Object.defineProperty(hidden,"reason",{enumerable:false,value:"CONTENT_PENDING_TIMEOUT"});expect(decode(hidden)).toBeNull();
});
