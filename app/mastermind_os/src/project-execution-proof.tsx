/**
 * Test-only compiled browser entry. Never imported by production main.
 * Run only on dedicated localhost:18765, whose real IndexedDB contains fixture
 * pointers only. No new store, live authentication or provider transport.
 */
import {useSyncExternalStore} from "react";
import {createRoot} from "react-dom/client";
import {App} from "./App";
import {DisplayPreferences,DisplayPreferencesRoot} from "./preferences/DisplayPreferences";
import {createIndexedDbPendingPointerStore} from "./orchestration/indexeddb-pending-pointer-store";
import {createProjectExecutionProofFixture,type ProjectExecutionProofHistory,type ProjectExecutionProofMode} from "./project-execution-proof-fixture";
import "./styles.css";

async function main(){
  if(!["127.0.0.1","localhost"].includes(window.location.hostname)||window.location.port!=="18765")
    throw Error("This inert fixture requires its dedicated localhost:18765 origin.");
  const fixture=await createProjectExecutionProofFixture(createIndexedDbPendingPointerStore(window.indexedDB),{history:"empty"});
  window.MastermindMissionHost=fixture.host;
  function Controls(){
    const state=useSyncExternalStore(fixture.subscribe,fixture.getSnapshot);
    return <details open style={{padding:"8px 16px",background:"#fff7ed",color:"#431407",borderBottom:"1px solid #c2410c",font:"13px/1.5 system-ui"}}>
      <summary>Inert fixture controls — collapse for product layout checks</summary>
      <p>Open <b>Projects → Project team fixture → Start work</b>. For a follow-up, choose Completed history, then read and open that run.</p>
      <div style={{display:"flex",flexWrap:"wrap",gap:"12px",alignItems:"center"}}>
        <label htmlFor="fixture-history">Run history </label>
        <select id="fixture-history" value={state.historyMode} onChange={event=>fixture.setHistory(event.target.value as ProjectExecutionProofHistory)}>
          <option value="empty">No runs</option><option value="queued">Queued run</option><option value="completed">Completed run</option>
        </select>
        <label htmlFor="fixture-mode">Next submission </label>
        <select id="fixture-mode" value={state.mode} onChange={event=>fixture.setMode(event.target.value as ProjectExecutionProofMode)}>
          <option value="accepted">Accepted fixture</option><option value="refused">Refused before execution</option><option value="lost_reply">Lost reply; recover original</option>
        </select>
        <button type="button" onClick={fixture.invalidateHistory}>Invalidate history read</button>
        <label><input type="checkbox" onChange={event=>fixture.holdPreview(event.target.checked)}/> Hold preview response</label>
        <button type="button" disabled={state.heldPreviews===0} onClick={fixture.releasePreviews}>Release preview</button>
      </div>
      <p role="status">Previews: {state.previewCount} · Submissions: {state.submitCount} · Status reads: {state.statusCount} · Held previews: {state.heldPreviews}</p>
      <p>Latest fixture operation: <code style={{overflowWrap:"anywhere"}}>{state.lastOperationKey||"none"}</code></p>
      <p>For lost-reply recovery, reload this same page and use <b>Check status</b>. The product’s real IndexedDB owner retains only the original operation pointer.</p>
    </details>;
  }
  const controls=document.getElementById("fixture-controls"),root=document.getElementById("root");
  if(!controls||!root)throw Error("Fixture mount unavailable");
  createRoot(controls).render(<Controls/>);
  createRoot(root).render(<DisplayPreferencesRoot>{({theme,locale,control})=>
    <App theme={theme} locale={locale} preferencesControl={<DisplayPreferences control={control}/>}/>
  }</DisplayPreferencesRoot>);
}
void main().catch(error=>{
  const root=document.getElementById("root");
  if(root)root.textContent=error instanceof Error?error.message:"Inert fixture unavailable.";
});
