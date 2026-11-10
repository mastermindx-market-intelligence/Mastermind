import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import "./team-shell.css";

type Section = "company" | "runtime" | "conversations";

/** Presentation and draft lifetime only. Each consumer retains its own source,
 * authentication, native selection and pending-operation owner. A roster
 * selection never supplies a conversation recipient or execution identity. */
export function TeamShell({ locale, company, runtime, nativeConversations }: {
  locale: "en" | "zh-CN";
  company: ReactNode;
  runtime?: ReactNode;
  nativeConversations?: ReactNode;
}) {
  const zh = locale === "zh-CN", id = useId();
  const [selected, setSelected] = useState<Section>("company");
  const [opened, setOpened] = useState<ReadonlySet<Section>>(() => new Set(["company"]));
  const buttons = useRef<Partial<Record<Section, HTMLButtonElement | null>>>({});
  const sections: { id: Section; label: string; content: ReactNode }[] = [
    { id: "company", label: zh ? "公司与工作" : "Company", content: company },
    ...(runtime == null ? [] : [{ id: "runtime" as const, label: zh ? "运行配置" : "Runtime profiles", content: runtime }]),
    ...(nativeConversations == null ? [] : [{ id: "conversations" as const, label: zh ? "原生对话" : "Native conversations", content: nativeConversations }]),
  ];
  const current = sections.some(section => section.id === selected) ? selected : "company";
  useEffect(() => { if (current !== selected) setSelected(current); }, [current, selected]);
  const select = (section: Section) => {
    setOpened(previous => previous.has(section) ? previous : new Set([...previous, section]));
    setSelected(section);
  };
  return <section className="mm-team-shell" aria-label={zh ? "团队工作区" : "Team workspace"}>
    {sections.length > 1 && <div className="mm-team-shell-tabs" role="tablist" aria-label={zh ? "团队视图" : "Team sections"}>
      {sections.map((section, index) => <button key={section.id} type="button" role="tab"
        id={`${id}-${section.id}-tab`} aria-controls={`${id}-${section.id}-panel`}
        aria-selected={current === section.id} tabIndex={current === section.id ? 0 : -1}
        ref={node => { buttons.current[section.id] = node; }}
        onClick={() => select(section.id)}
        onKeyDown={event => {
          const next = event.key === "ArrowRight" ? (index + 1) % sections.length
            : event.key === "ArrowLeft" ? (index + sections.length - 1) % sections.length
            : event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1 : null;
          if (next === null) return;
          event.preventDefault();
          const target = sections[next].id;
          select(target); buttons.current[target]?.focus();
        }}>{section.label}</button>)}
    </div>}
    {sections.map(section => <div key={section.id} id={`${id}-${section.id}-panel`}
      className="mm-team-shell-panel" role={sections.length > 1 ? "tabpanel" : undefined}
      aria-labelledby={sections.length > 1 ? `${id}-${section.id}-tab` : undefined}
      hidden={current !== section.id} inert={current !== section.id}>
      {opened.has(section.id) ? section.content : null}
    </div>)}
  </section>;
}
