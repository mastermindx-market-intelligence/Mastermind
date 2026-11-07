/** LOCAL INERT App operand only; native auth/continuity are declared fixtures.
 * All project/planning DTOs come unchanged from whole same-run6cb8; no network. */
import {createRoot} from 'react-dom/client';
import {App} from './App';
import {createFileConsumerFixture,fixture} from './projects/project-draft-files-consumer-fixture';
import {DisplayPreferencesRoot,DisplayPreferences} from './preferences/DisplayPreferences';
import './styles.css';
Date.now=()=>fixture.recorded_at_ms;
const originalRandom=crypto.getRandomValues.bind(crypto),seeds=[0xcc,0xbb];
crypto.getRandomValues=(<T extends ArrayBufferView<ArrayBuffer>>(value:T):T=>{
 if(value instanceof Uint8Array&&value.byteLength===20){const byte=seeds.shift();if(byte!==undefined){value.fill(byte);return value;}}
 return originalRandom(value);
}) as typeof crypto.getRandomValues;
const q=new URLSearchParams(location.search),locale=q.get('locale')==='zh-CN'?'zh-CN':'en',theme=q.get('theme')==='light'?'light':'dark';
localStorage.setItem('mastermind-os.display-preferences.v1',JSON.stringify({version:1,locale,theme}));
Object.assign(window,{__TAURI_INTERNALS__:{}});
const owner=await createFileConsumerFixture(indexedDB);
(window as unknown as {__projectDraftFileProof:unknown}).__projectDraftFileProof={
 fixtureScope:fixture.scope,recordedAtMs:fixture.recorded_at_ms,consumerInputs:fixture.consumer_inputs,identities:fixture.identities,
 limitations:fixture.limitations,calls:owner.calls,callProvenance:()=>owner.calls.map(c=>({command:c.command,sequence:c.sequence})),
 expirePassively:owner.expire,loseNextFileSubmit:()=>owner.lose('source_operation_submit'),loseNextPlanningResponse:()=>owner.lose('planning'),
 clockLabel:'INERT_RECORDED_CLOCK_NOT_REAL_AUTHORIZATION',nativeAuthorityPremise:'Synthetic signed-in status + registered NativeDraftRecoveryOwner over fixed continuity fixture; no native enrollment/live auth proof',
};
createRoot(document.getElementById('root')!).render(<DisplayPreferencesRoot>{({theme,locale,control})=><App theme={theme} locale={locale} preferencesControl={<DisplayPreferences control={control}/>}/>}</DisplayPreferencesRoot>);
