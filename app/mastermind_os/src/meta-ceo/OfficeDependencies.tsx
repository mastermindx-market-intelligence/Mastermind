import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { OfficeProjection } from "./projection";

/** No acquisition or navigation authority; inspect only this supplied collection. */
export function OfficeDependencies({
  read,
  locale,
  children,
}: {
  read: OfficeProjection["programs"];
  locale: "en" | "zh-CN";
  children?: ReactNode;
}) {
  const zh = locale === "zh-CN",
    label = (en: string, cn: string) => (zh ? cn : en);
  const rows =
    read.source.state === "CURRENT" ? (read.value?.dependencies ?? []) : [];
  const [selection, setSelection] = useState<{
    ref: string;
    revision: string | null;
  } | null>(null);
  const [page, setPage] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null),
    detail = useRef<HTMLHeadingElement>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>()),
    origin = useRef<string | null>(null),
    focusDetail = useRef(false),
    focusList = useRef(false);
  const selected =
    selection?.revision === read.source.revision
      ? rows.find((r) => r.workRef === selection.ref)
      : null;
  const offset =
    Math.min(page, Math.max(0, Math.ceil(rows.length / 8) - 1)) * 8;
  useLayoutEffect(() => {
    if (focusDetail.current) {
      focusDetail.current = false;
      detail.current?.focus();
    }
    if (focusList.current) {
      focusList.current = false;
      (buttons.current.get(origin.current ?? "") ?? heading.current)?.focus();
    }
  });
  const back = () => {
    focusList.current = true;
    setSelection(null);
  };
  return (
    <section
      className="office-panel"
      aria-labelledby="office-dependencies-title"
      onKeyDown={(e) => {
        if (e.key === "Escape" && selected) {
          e.preventDefault();
          back();
        }
      }}
    >
      <h2 id="office-dependencies-title" ref={heading} tabIndex={-1}>
        {label("Declared dependencies", "已声明的依赖")}
      </h2>
      <p className="office-muted">
        {label(
          "Supplied collection only. This is not a ranked critical path or adopted company direction.",
          "仅覆盖已提供的集合；这不是排序后的关键路径或已采纳的公司方向。",
        )}
      </p>
      {selected ? (
        <>
          <h3 ref={detail} tabIndex={-1}>
            {selected.title ?? selected.workRef}
          </h3>
          <p className="office-ref">{selected.workRef}</p>
          {selected.state === "AVAILABLE" ? (
            <>
              <h4>{label("Unmet dependencies", "尚未满足的依赖")}</h4>
              <p>
                {selected.unmet!.length
                  ? selected.unmet!.join(" · ")
                  : label(
                      "No unmet dependencies were reported for this record.",
                      "此记录未报告尚未满足的依赖。",
                    )}
              </p>
              <h4>{label("Declared dependencies", "已声明的依赖")}</h4>
              {selected.declared!.length ? (
                <ul>
                  {selected.declared!.map((ref) => {
                    const target = rows.find((r) => r.workRef === ref);
                    return (
                      <li key={ref}>
                        <span>{target?.title ?? ref}</span> ·{" "}
                        <span className="office-ref">{ref}</span>
                        {!target && (
                          <p>
                            {label(
                              "Outside the supplied collection; project details are unavailable here.",
                              "此依赖位于已提供集合之外；此处无法查看项目详情。",
                            )}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p>
                  {label(
                    "No dependencies were declared for this record.",
                    "此记录未声明依赖。",
                  )}
                </p>
              )}
            </>
          ) : (
            <p>
              {label(
                "Dependency metadata was not supplied or could not be verified.",
                "依赖元数据尚未提供或无法验证。",
              )}
            </p>
          )}
          <details className="office-raw">
            <summary>{label("Source details", "来源详情")}</summary>
            <dl className="office-next">
              <dt>{label("Record", "记录")}</dt>
              <dd>{selected.source ?? label("Not supplied", "未提供")}</dd>
              <dt>{label("Projected readiness", "来源就绪状态")}</dt>
              <dd>{selected.readiness ?? label("Not supplied", "未提供")}</dd>
              <dt>{label("Collection identity", "集合标识")}</dt>
              <dd className="office-ref">{read.source.ref}</dd>
              <dt>{label("Local acquisition time", "本地读取时间")}</dt>
              <dd>{read.source.observed_at}</dd>
            </dl>
          </details>
          <button type="button" onClick={back}>
            {label("Back to dependencies", "返回依赖列表")}
          </button>
        </>
      ) : (
        <>
          {rows.length ? (
            <ul className="office-lanes">
              {rows.slice(offset, offset + 8).map((row) => (
                <li key={row.workRef}>
                  <div>
                    <strong>{row.title ?? row.workRef}</strong>
                    <p className="office-ref">{row.workRef}</p>
                    <p>
                      {row.state === "AVAILABLE"
                        ? label(
                            `${row.declared!.length} declared · ${row.unmet!.length} unmet`,
                            `已声明 ${row.declared!.length} 项 · 尚未满足 ${row.unmet!.length} 项`,
                          )
                        : label(
                            "Dependency metadata unavailable",
                            "依赖元数据不可用",
                          )}
                    </p>
                  </div>
                  <button
                    type="button"
                    ref={(button) => {
                      if (button) buttons.current.set(row.workRef, button);
                      else buttons.current.delete(row.workRef);
                    }}
                    aria-label={label(
                      `Inspect dependencies for ${row.title ?? row.workRef}`,
                      `查看 ${row.title ?? row.workRef} 的依赖`,
                    )}
                    onClick={(e) => {
                      origin.current = row.workRef;
                      focusDetail.current = true;
                      setSelection({
                        ref: row.workRef,
                        revision: read.source.revision,
                      });
                    }}
                  >
                    {label("Inspect dependencies", "查看依赖")}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>
              {label(
                "A current qualified Programs collection with dependency metadata is unavailable.",
                "当前没有合格的项目集合依赖元数据。",
              )}
            </p>
          )}
          {rows.length > 8 && (
            <div className="office-composer-actions">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setPage(Math.max(0, offset / 8 - 1))}
              >
                {label("Previous projects", "上一页项目")}
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 8, rows.length)} / {rows.length}
              </span>
              <button
                type="button"
                disabled={offset + 8 >= rows.length}
                onClick={() => setPage(offset / 8 + 1)}
              >
                {label("Next projects", "下一页项目")}
              </button>
            </div>
          )}
        </>
      )}
      {children}
    </section>
  );
}
