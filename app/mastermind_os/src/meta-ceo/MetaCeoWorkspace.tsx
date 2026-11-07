import { useState } from "react";
import { MetaCeoOffice, type MetaCeoOfficeProps } from "./MetaCeoOffice";
import { HermesNativePanel } from "../hermes-native/HermesNativePanel";
import { nativeHermesPort } from "../hermes-native/native-port";
import { DeepSeekNativeEntry } from "../conversations/DeepSeekNativeEntry";
import "./workspace.css";

/** Presentation/navigation only. The native chat and existing company workflow
 * keep their own state and authority; switching tabs never re-creates either. */
export function MetaCeoWorkspace(props: MetaCeoOfficeProps) {
  const native = nativeHermesPort.available();
  const [surface, setSurface] = useState<"chat" | "deepseek" | "company">(native ? "chat" : "company");
  const zh = props.locale === "zh-CN";
  if (!native) return <MetaCeoOffice {...props} />;
  return <div className="office-chat-workspace" data-view={surface}>
    <div className="office-chat-tabs" role="tablist" aria-label={zh ? "Meta-CEO 视图" : "Meta-CEO views"}
      onKeyDown={event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const tabs = ["chat", "deepseek", "company"] as const;
        const next = event.key === "Home" ? "chat" : event.key === "End" ? "company" : tabs[(tabs.indexOf(surface) + (event.key === "ArrowRight" ? 1 : 2)) % 3];
        setSurface(next);
        event.currentTarget.querySelector<HTMLButtonElement>(`[data-surface="${next}"]`)?.focus();
      }}>
      <button type="button" role="tab" id="office-chat-tab" data-surface="chat" aria-controls="office-chat-panel" aria-selected={surface === "chat"} tabIndex={surface === "chat" ? 0 : -1} onClick={() => setSurface("chat")}>Hermes</button>
      <button type="button" role="tab" id="office-deepseek-tab" data-surface="deepseek" aria-controls="office-deepseek-panel" aria-selected={surface === "deepseek"} tabIndex={surface === "deepseek" ? 0 : -1} onClick={() => setSurface("deepseek")}>DeepSeek ↗</button>
      <button type="button" role="tab" id="office-company-tab" data-surface="company" aria-controls="office-company-panel" aria-selected={surface === "company"} tabIndex={surface === "company" ? 0 : -1} onClick={() => setSurface("company")}>{zh ? "公司工作区" : "Company workspace"}</button>
    </div>
    <div id="office-chat-panel" role="tabpanel" aria-labelledby="office-chat-tab" hidden={surface !== "chat"} className="office-chat-panel">
      <HermesNativePanel key={`hermes:${props.projection.context.authGeneration}`} locale={props.locale ?? "en"} visible={surface === "chat"} />
    </div>
    <div id="office-deepseek-panel" role="tabpanel" aria-labelledby="office-deepseek-tab" hidden={surface !== "deepseek"}>
      <DeepSeekNativeEntry key={`deepseek:${props.projection.context.authGeneration}`} locale={props.locale} />
    </div>
    <div id="office-company-panel" role="tabpanel" aria-labelledby="office-company-tab" hidden={surface !== "company"}>
      <MetaCeoOffice key={JSON.stringify([props.projection.context.authGeneration,
        props.projection.context.selection, props.projection.context.sessionRef,
        props.projection.context.bindingGeneration])} {...props} />
    </div>
  </div>;
}
