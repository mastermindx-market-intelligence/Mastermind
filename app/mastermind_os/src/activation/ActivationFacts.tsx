import type { ActivationFactsModel, ReceiptRoute } from "./activation-facts";
import { PHASES } from "./activation-facts";
import "./activation-facts.css";

export function ActivationFacts({
  model,
  locale = "en",
  onNavigate,
}: {
  model: ActivationFactsModel | null;
  locale?: "en" | "zh-CN";
  onNavigate?: (route: ReceiptRoute) => void;
}) {
  const zh = locale === "zh-CN",
    t = (en: string, cn: string) => (zh ? cn : en);
  const labels = zh
    ? ["请求", "接收", "开始", "效果", "返回", "接受"]
    : ["Request", "Pickup", "START", "Effect", "Return", "Acceptance"];
  const request = {
    submitting: t("Awaiting the original request result", "等待原始请求结果"),
    checking: t("Checking the original request", "正在查询原始请求"),
    accepted: t("Request accepted", "请求已接受"),
    refused: t("Request refused", "请求被拒绝"),
  };
  const reported = [
    t("Request reported", "已报告请求"),
    t("Pickup acknowledged", "已确认接收"),
    t("START reported for this Attempt", "此尝试已报告开始"),
    t("Effect applied", "效果已应用"),
    t("Return reported", "已报告返回"),
    t("Acceptance reported by its owner", "所属方已报告接受"),
  ];
  return (
    <section
      className="card activation-facts"
      lang={locale}
      aria-label={t("Activation receipts", "激活回执")}
    >
      <h2>{t("Activation receipts", "激活回执")}</h2>
      <p className="muted">
        {t(
          "Each fact belongs to its source. A request does not confirm START, return or acceptance.",
          "每项事实均来自其所属来源。请求不能确认工作已开始、结果已返回或已被接受。",
        )}
      </p>
      {!model && (
        <p>
          {t("Original request identity unavailable.", "原始请求身份不可用。")}
        </p>
      )}
      <dl className="activation-facts__rows">
        {PHASES.map((phase, i) => {
          const fact = model?.facts.find((row) => row.phase === phase);
          return (
            <div key={phase}>
              <dt>{labels[i]}</dt>
              <dd>
                {fact?.state === "reported"
                  ? phase === "request" && fact.value && fact.value in request
                    ? request[fact.value as keyof typeof request]
                    : reported[i]
                  : fact?.state === "held"
                    ? t(
                        "Outcome unknown — original operation held",
                        "结果未知，原始操作保持未决",
                      )
                    : t("Not reported by this source", "此来源未报告")}
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="muted">
        {t(
          "Provider identity and session usability are not established by this receipt.",
          "此回执不能确认提供方身份或会话可用性。",
        )}
      </p>
      {model && (
        <details className="reason-details">
          <summary>{t("Receipt evidence", "回执证据")}</summary>
          <dl>
            <dt>{t("Original operation", "原始操作")}</dt>
            <dd>
              <code>{model.operationKey}</code>
            </dd>
            <dt>{t("Kind", "类型")}</dt>
            <dd>
              <code>{model.kind}</code>
            </dd>
            <dt>{t("Target", "目标")}</dt>
            <dd>
              <code>{model.targetKey ?? t("Not reported", "未报告")}</code>
            </dd>
          </dl>
          {model.selection && (
            <p>
              <code>{model.selection.workRef}</code> ·{" "}
              <code>{model.selection.rootJobId}</code>
            </p>
          )}
          <dl>
            {(
              [
                [t("Job", "工作"), model.runtime?.jobId],
                [t("Worker", "工作者"), model.runtime?.workerId],
                [t("Attempt", "尝试"), model.runtime?.attemptId],
                [t("Runtime binding", "运行时绑定"), model.runtime?.bindingId],
                [
                  t("Binding generation", "绑定代次"),
                  model.runtime?.bindingGeneration,
                ],
                [t("Provider identity", "提供方身份"), null],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  <code>
                    {value === null || value === undefined
                      ? t("Not reported", "未报告")
                      : String(value)}
                  </code>
                </dd>
              </div>
            ))}
          </dl>
          <ul>
            {model.facts.map((f) => (
              <li key={f.phase}>
                <strong>{labels[PHASES.indexOf(f.phase)]}</strong>:{" "}
                <code>{f.value ?? t("Not reported", "未报告")}</code>
                {f.evidence.map((e, i) => (
                  <dl key={i}>
                    <dt>{t("Source / field", "来源／字段")}</dt>
                    <dd>
                      {e.owner} · <code>{e.field}</code>
                    </dd>
                    {e.revision && (
                      <>
                        <dt>{t("Revision", "修订")}</dt>
                        <dd>
                          <code>{e.revision}</code>
                        </dd>
                      </>
                    )}
                    {e.time && (
                      <>
                        <dt>{t("Source time", "来源时间")}</dt>
                        <dd>{e.time}</dd>
                      </>
                    )}
                  </dl>
                ))}
              </li>
            ))}
          </ul>
        </details>
      )}
      {model && onNavigate && (
        <div className="form-actions">
          {model.routes.map((route) => (
            <button type="button" key={route} onClick={() => onNavigate(route)}>
              {route === "work"
                ? t("Open Work", "打开工作")
                : route === "sessions"
                  ? t("Open Sessions", "打开会话")
                  : t("Read original status", "读取原始状态")}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
