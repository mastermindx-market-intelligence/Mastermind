/** No draft body, source preview or action authority belongs in this notice. */
export function NativeDraftRecoveryNotice({ locale, checking, canRecover, onRecover, onDiscard }: {
  locale: "en" | "zh-CN"; checking: boolean; canRecover: boolean;
  onRecover: () => void; onDiscard: () => void;
}) {
  const zh = locale === "zh-CN";
  return <section className="notice" lang={locale} aria-label={zh ? "未发送的内容" : "Unsent work"}>
    <p>{zh ? "未发送的内容保留在此窗口中。登录后可恢复。" : "Your unsent work is kept in this window. Sign in to recover it."}</p>
    <button type="button" disabled={!canRecover || checking} onClick={onRecover}>
      {checking ? zh ? "正在验证身份…" : "Checking identity…" : zh ? "恢复未发送的内容" : "Recover unsent work"}
    </button>
    <button type="button" onClick={onDiscard}>{zh ? "丢弃未发送的内容" : "Discard unsent work"}</button>
  </section>;
}
