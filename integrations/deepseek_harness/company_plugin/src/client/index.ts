import {createElement, useState, useSyncExternalStore} from "react";
import {COMPANY_PLUGIN_ID} from "../protocol";
import {createCompanyConnection, type CompanySnapshot} from "./connection";
import {COMPANY_CSS} from "./styles";

interface CompanyContext {
  effect(factory: () => (() => void), label?: string): void;
  slots: {
    inject(name: string, factory: () => unknown): void;
    register(options: Record<string, unknown>, component: unknown): unknown;
  };
  theme: {overrideTokens(source: string, tokens: Record<string, {light: string; dark: string}>): () => void; setTheme(theme: string): void;};
  locale: {setLocale(locale: string): void;};
}
interface CompanyStore {
  getSnapshot(): CompanySnapshot;
  subscribe(listener: () => void): () => void;
}
interface PanelProps {store: CompanyStore; onOpenProject: (workRef: string) => boolean;}
export const inject = ["slots", "theme", "locale"];

function CompanyPanel({store, onOpenProject}: PanelProps) {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [query, setQuery] = useState("");
  const view = snapshot.view, zh = view?.locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const needle = query.trim().toLocaleLowerCase(zh ? "zh-CN" : "en");
  const projects = view?.state === "CURRENT" ? view.projects.filter(p => !needle ||
    [p.title,p.workRef].some(value => value.toLocaleLowerCase(zh ? "zh-CN" : "en").includes(needle))) : [];
  return createElement("section", {className: "mmx-company", lang: zh ? "zh-CN" : "en", "aria-labelledby": "mmx-company-title"},
    createElement("p", {className: "mmx-company__eyebrow"}, "MASTERMIND OS"),
    createElement("h1", {id: "mmx-company-title"}, t("Your projects", "您的项目")),
    createElement("p", null, t("Move from a conversation to the project behind it.", "从对话进入相关项目。")),
    !view || view.state !== "CURRENT" ? createElement("div", {className:"mmx-company__empty"},
      createElement("p", {role:"status"}, !view ? t("Open chat from Mastermind OS to connect your projects.", "从 Mastermind OS 打开聊天以连接您的项目。")
        : view.state === "SIGNED_OUT" ? t("Sign in to Mastermind OS to see your projects.", "登录 Mastermind OS 以查看您的项目。")
        : t("Projects are unavailable right now. Return to your workspace to refresh them.", "当前无法获取项目。请返回工作区刷新。")),
      createElement("a", {href:"https://mcp.mastermind-x.com/os/",target:"_blank",rel:"noopener noreferrer"},t("Open Mastermind OS","打开 Mastermind OS")),
    ) : createElement("div", null,
      createElement("label", {className:"mmx-company__search"},t("Find a project","查找项目"),
        createElement("input",{type:"search",value:query,maxLength:128,onChange:(event: {target:{value:string}})=>setQuery(event.target.value)})),
      snapshot.refused ? createElement("p",{role:"status"},t("This project view changed. Reopen it from Mastermind OS.","项目视图已更改。请从 Mastermind OS 重新打开。")) : null,
      createElement("ul",{className:"mmx-company__list"},projects.map(project => createElement("li",{className:"mmx-company__row",key:project.workRef},
        createElement("div",null,createElement("h2",null,project.title),
          project.workRef===view.selectedProject?createElement("p",null,t("Current project","当前项目")):null),
        createElement("button",{type:"button",onClick:()=>onOpenProject(project.workRef),"aria-label":t("Open project: ","打开项目：")+project.title},t("Open project","打开项目")),
      ))),
      projects.length===0?createElement("p",{role:"status"},needle?t("No matching projects.","没有匹配的项目。"):t("No projects are available in this view.","此视图中暂无项目。")):null,
    ),
  );
}
function BrandMark({size = 20}: {size?: number}) {
  return createElement("span", {style:{width:size,height:size,display:"inline-flex"},"aria-hidden":true},
    createElement("span",{className:"mmx-company__brand"},"M"));
}
function BrandName() { return createElement("span",null,"Mastermind"); }
function ProjectIcon({size = 20}: {size?: number}) {
  return createElement("svg",{width:size,height:size,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.5,"aria-hidden":true},
    createElement("rect",{x:3,y:4,width:18,height:16,rx:3}),createElement("path",{d:"M9 4v16M3 10h18"}));
}

/** Supported Cordis slots: native chat/session/workspace occupants stay intact. */
export function apply(ctx: CompanyContext): void {
  const company = createCompanyConnection(window);
  ctx.effect(() => () => company.dispose(), "mastermind: company connection");
  ctx.effect(() => {
    let lastLocale: string | null = null, lastTheme: string | null = null;
    return company.state.subscribe(() => {
      const view = company.state.getSnapshot().view;
      if (!view || view.state === "SIGNED_OUT") return;
      if (lastLocale !== view.locale) { lastLocale = view.locale; ctx.locale.setLocale(view.locale === "zh-CN" ? "zh" : "en"); }
      if (lastTheme !== view.theme) { lastTheme = view.theme; ctx.theme.setTheme(view.theme); }
    });
  }, "mastermind: shared appearance");
  ctx.effect(() => {
    const style = document.createElement("style");
    style.dataset.plugin = COMPANY_PLUGIN_ID;
    style.textContent = COMPANY_CSS;
    document.head.appendChild(style);
    return () => style.remove();
  }, "mastermind: company presentation");
  ctx.effect(() => ctx.theme.overrideTokens(COMPANY_PLUGIN_ID, {
    "--dsw-alias-bg-base":{light:"#f6f4ee",dark:"#0b0c0e"},
    "--dsw-alias-bg-layer-1":{light:"#fffefa",dark:"#121417"},
    "--dsw-alias-bg-layer-2":{light:"#eeece5",dark:"#1a1d21"},
    "--dsw-alias-bg-overlay":{light:"#fffefa",dark:"#181b1f"},
    "--dsw-alias-border-l1":{light:"#d8d5cb",dark:"#2a2e33"},
    "--dsw-alias-border-l2":{light:"#bdb9ae",dark:"#42474f"},
    "--dsw-alias-brand-primary":{light:"#766642",dark:"#c8b993"},
    "--dsw-alias-label-primary":{light:"#25241f",dark:"#eeeae1"},
    "--dsw-alias-label-secondary":{light:"#666359",dark:"#aaa89e"},
    "--dsw-specific-sidebar-fill":{light:"#eeece5",dark:"#101215"},
  }), "mastermind: Noir palette");
  ctx.slots.inject("sidebar.brand.mark", () => ctx.slots.register({name:"sidebar.brand.mark"},BrandMark));
  ctx.slots.inject("sidebar.brand.name", () => ctx.slots.register({name:"sidebar.brand.name"},BrandName));
  ctx.slots.inject("conversation.hero.brand.mark", () => ctx.slots.register({name:"conversation.hero.brand.mark"},BrandMark));
  ctx.slots.inject("main", () => ctx.slots.register({
    name:"main",key:"mastermind-projects",inject:()=>({store:company.state,onOpenProject:company.openProject}),
  },CompanyPanel));
  ctx.slots.inject("sidebar.panellist", () => ctx.slots.register({
    name:"sidebar.panellist",id:"mastermind-projects",order:-10,label:()=>{
      const view=company.state.getSnapshot().view;return view?.locale==="zh-CN"?"项目":"Projects";
    },
  },ProjectIcon));
}
