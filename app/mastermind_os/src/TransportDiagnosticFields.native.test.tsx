// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TransportDiagnosticFields } from "./TransportDiagnosticFields";
import { decodeNativeExecutiveObservation } from "./native-executive-observation";
(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
let container:HTMLDivElement,root:Root;
beforeEach(()=>{container=document.createElement("div");document.body.append(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const observation=()=>decodeNativeExecutiveObservation({schema:"mastermind.native_executive_status.v1",generation:7,available:false,configured:true,reason:"AUTHORIZATION_REFUSED",programs_read:{phase:"HTTP_FAILURE",http_status:503}})!;
const base={snapshot:null,programsPhase:"transport_failure" as const,locale:"en"};
async function click(){await act(async()=>{container.querySelector("button")!.click();});}
it("performs no mount read and exposes current local metadata only on the explicit action",async()=>{
 const read=vi.fn(async()=>observation());await act(async()=>root.render(<TransportDiagnosticFields {...base} refreshNativeDiagnostics={read}/>));
 expect(read).not.toHaveBeenCalled();await click();expect(read).toHaveBeenCalledTimes(1);
 expect(container.textContent).toContain("AUTHORIZATION_REFUSED");expect(container.textContent).toContain("503");
 expect(container.textContent).toContain("Executive availabilityUnknown");
 expect(container.textContent).toContain("Local Executive availabilityNo");
 expect(container.textContent).toContain("does not sign in or refresh projects");
});
it("masks old local metadata when the actual reader changes and refuses its delayed result",async()=>{
 let resolve!:(v:ReturnType<typeof observation>)=>void;
 const old=vi.fn(()=>new Promise<ReturnType<typeof observation>>(done=>{resolve=done;}));
 await act(async()=>root.render(<TransportDiagnosticFields {...base} refreshNativeDiagnostics={old}/>));await click();
 const next=vi.fn(async()=>observation());await act(async()=>root.render(<TransportDiagnosticFields {...base} refreshNativeDiagnostics={next}/>));
 await act(async()=>resolve(observation()));expect(container.textContent).not.toContain("AUTHORIZATION_REFUSED");expect(next).not.toHaveBeenCalled();
 await click();expect(next).toHaveBeenCalledTimes(1);expect(container.textContent).toContain("AUTHORIZATION_REFUSED");
});
it("never renders a private exception and preserves an explicit unavailable local observation",async()=>{
 const read=vi.fn(async()=>{throw new Error("private-token-at-secret-origin");});
 await act(async()=>root.render(<TransportDiagnosticFields {...base} locale="zh-CN" refreshNativeDiagnostics={read}/>));await click();
 expect(container.textContent).toContain("无法读取本地诊断");expect(container.textContent).not.toContain("private-token");
});
