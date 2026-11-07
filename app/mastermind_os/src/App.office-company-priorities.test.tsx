// @vitest-environment jsdom
// Actual client/Host/App. Signed source body unchanged; native auth/invoke inert.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import {createNativeClient,bindMissionHost} from "./host";
import company from "./fixtures/office-company-priorities-source.json";
import office from "./fixtures/office-existing-reads-source.json";
import work from "./fixtures/work-service-available.json";
import {companyPriorityDisplayName} from "./meta-ceo/CompanyPrioritiesRead";
beforeEach(()=>{vi.spyOn(Date,"now").mockReturnValue(company.clock.verified_at*1000);history.replaceState(null,"","/os/");delete window.MastermindMissionHost});
afterEach(()=>{cleanup();delete window.MastermindMissionHost;vi.restoreAllMocks()});
async function setup(hold=false){let release!:(v:unknown)=>void;const pending=new Promise(r=>release=r),listeners=new Map<string,(e:{payload:unknown})=>void>();const invoke=vi.fn(async(command:string)=>{
 if(command==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:false};
 if(command==="executive_auth_status")return {generation:0,available:true};
 if(command==="read_programs")return structuredClone(office.responses.programs.body);
 if(command==="read_work")return structuredClone(work);
 if(command==="read_company_priorities")return hold?pending:structuredClone(company.response);
 throw Error("Explicitly unavailable other source/command");
});const client=await createNativeClient(invoke as never,async(n,fn)=>{listeners.set(n,fn);return()=>listeners.delete(n)}),host=bindMissionHost(client);window.MastermindMissionHost=host;render(<App/>);
 const nav=(name:string)=>{if(!screen.queryByRole("button",{name}))fireEvent.click(document.querySelector('.nav-advanced>summary')!);fireEvent.click(screen.getByRole("button",{name}))};nav("Meta-CEO");const section=await screen.findByRole("region",{name:"Company priorities"});
 return {host,client,invoke,nav,section,release,withdraw:()=>listeners.get("mastermind-executive-auth-state")?.({payload:{generation:1,available:false}})};
}
it("explicit actual App read shows authored priorities/criteria and source, then Work→Office preserves the draft without extra read or effect",async()=>{
 const f=await setup();expect(f.invoke.mock.calls.filter(([c])=>c==="read_company_priorities")).toHaveLength(0);
 const draft=screen.getByRole("textbox",{name:"Direction to Meta-CEO"});fireEvent.change(draft,{target:{value:"Keep exactly this unsent company question."}});
 fireEvent.click(within(f.section).getByRole("button",{name:"Read company priorities"}));
 const list=await within(f.section).findByRole("list",{name:"Active priorities"});
 const rows=[...list.querySelectorAll<HTMLDetailsElement>("details[data-priority-id]")];
 expect(rows.map(r=>r.dataset.priorityId)).toEqual(company.response.priorities.filter(p=>p.status==="active").map(p=>p.id));
 expect(rows.every(r=>!r.open)).toBe(true);
 expect(within(f.section).getAllByText("Authored company priorities")).toHaveLength(1);
 const first=within(list).getByText(companyPriorityDisplayName(company.response.priorities[0].id,"en"),{exact:true});
 fireEvent.click(first);expect(rows[0].open).toBe(true);
 expect(within(rows[0]).getByText(company.response.priorities[0].objective,{exact:true})).toBeTruthy();
 expect(within(rows[0]).getByText(new RegExp(company.response.priorities[0].id))).toBeTruthy();
 fireEvent.click(within(f.section).getByText("Declared phase-review criteria",{exact:true}));expect(within(f.section).getByText(company.response.phase_review_criteria.SELL_READY.criteria[0],{exact:true})).toBeTruthy();
 fireEvent.click(within(f.section).getByText("Company source details",{exact:true}));expect(within(f.section).getByText(new RegExp(company.response.source.revision))).toBeTruthy();
 expect(screen.getByText("The critical path is unavailable. The owner’s next action remains visible.")).toBeTruthy();
 f.nav("Work");f.nav("Meta-CEO");expect(screen.getByRole("textbox",{name:"Direction to Meta-CEO"}).getAttribute("value")??(screen.getByRole("textbox",{name:"Direction to Meta-CEO"}) as HTMLTextAreaElement).value).toBe("Keep exactly this unsent company question.");
 expect(f.invoke.mock.calls.filter(([c])=>c==="read_company_priorities")).toHaveLength(1);expect(f.invoke.mock.calls.some(([c])=>/submit|prepare|send|consume|pause/.test(c))).toBe(false);
});
it.each(["globalHost","executiveEpoch"])("no-render %s withdrawal withholds late company source",async kind=>{const f=await setup(true);fireEvent.click(within(f.section).getByRole("button",{name:"Read company priorities"}));await waitFor(()=>expect(f.invoke.mock.calls.filter(([c])=>c==="read_company_priorities")).toHaveLength(1));await act(async()=>{if(kind==="globalHost")window.MastermindMissionHost={...f.host};else f.withdraw();f.release(structuredClone(company.response));await Promise.resolve()});expect(screen.queryByText(company.response.priorities[0].objective,{exact:true})).toBeNull();expect(f.invoke.mock.calls.some(([c])=>/submit|send|prepare/.test(c))).toBe(false)});
it("current Executive withdrawal clears already-read company text",async()=>{const f=await setup();fireEvent.click(within(f.section).getByRole("button",{name:"Read company priorities"}));await within(f.section).findByText(company.response.priorities[0].objective,{exact:true});await act(async()=>f.withdraw());await waitFor(()=>expect(screen.queryByText(company.response.priorities[0].objective,{exact:true})).toBeNull());expect(screen.getByText("Company priorities are unavailable. No company conclusion can be drawn from this read.")).toBeTruthy()});

it("a replaced original Executive read method is not admitted by the bound Host",async()=>{const f=await setup();const replacement=vi.fn(async()=>structuredClone(company.response));Object.assign(f.client.executive!,{companyPriorities:replacement});fireEvent.click(within(f.section).getByRole("button",{name:"Read company priorities"}));await act(async()=>Promise.resolve());expect(replacement).not.toHaveBeenCalled();expect(f.invoke.mock.calls.filter(([c])=>c==="read_company_priorities")).toHaveLength(0);expect(screen.queryByText(company.response.priorities[0].objective,{exact:true})).toBeNull()});

it("unknown priority identifiers keep a readable fallback without an invented summary",()=>{expect(companyPriorityDisplayName("UNKNOWN_SOURCE_PRIORITY","en")).toBe("Unknown source priority");expect(companyPriorityDisplayName("UNKNOWN_SOURCE_PRIORITY","zh-CN")).toBe("Unknown source priority")});
