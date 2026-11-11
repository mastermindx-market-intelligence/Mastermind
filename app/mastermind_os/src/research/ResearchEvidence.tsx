import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import type { AppProps } from "../App";
import { decodeEvidenceItem, validEvidenceId, type EvidenceItem, type ResearchEvidenceTransport } from "./evidence-contract";

interface Props {
  itemId: string | null;
  transport?: ResearchEvidenceTransport;
  signOut: () => Promise<unknown>;
  locale?: AppProps["locale"];
  theme?: AppProps["theme"];
  onLocaleChange?: () => void;
  onThemeChange?: () => void;
}

/** Literal item view only. It never acquires workspace grants or receives a bearer. */
export function ResearchEvidence({ itemId, transport, signOut, locale = "en", theme = "dark", onLocaleChange, onThemeChange }: Props) {
  const [item, setItem] = useState<EvidenceItem | null>(null);
  const [state, setState] = useState<"signin" | "loading" | "unavailable" | "ready">("signin");
  const invalidate = useRef<() => void>(() => {});
  const retry = useRef<() => void>(() => {});
  const mounted = useRef(true);
  // Local presentation identity only; the transport still owns all auth state.
  const pendingSignIn = useRef<object | null>(null);
  const t = (en: string, zh: string) => locale === "zh-CN" ? zh : en;

  useEffect(() => {
    mounted.current = true;
    let alive = true, ticket = 0;
    let request: AbortController | null = null;
    let epoch = transport?.authGeneration(), available = transport?.available();
    const clear = () => { ticket++; request?.abort(); request = null; if (alive) setItem(null); };
    const read = () => {
      clear();
      if (!alive) return;
      if (!transport || !itemId || !validEvidenceId(itemId)) { setState("unavailable"); return; }
      if (document.visibilityState === "hidden") { setState("signin"); return; }
      if (!transport.available()) { setState(pendingSignIn.current ? "loading" : "signin"); return; }
      const token = ticket, generation = transport.authGeneration();
      request = new AbortController();
      const controller = request;
      setState("loading");
      void transport.readEvidenceItem(itemId, controller.signal).then(raw => {
        if (!alive || ticket !== token || controller.signal.aborted ||
            generation !== transport.authGeneration() || !transport.available() ||
            document.visibilityState === "hidden") return;
        try { setItem(decodeEvidenceItem(raw, itemId)); setState("ready"); }
        catch { clear(); setState("unavailable"); }
      }).catch(() => {
        if (alive && ticket === token) { clear(); setState("unavailable"); }
      });
    };
    const changed = () => {
      const nextEpoch = transport?.authGeneration(), nextAvailable = transport?.available();
      if (nextEpoch === epoch && nextAvailable === available) return;
      epoch = nextEpoch; available = nextAvailable; read();
    };
    const visibility = () => {
      if (document.visibilityState === "hidden") { flushSync(() => { clear(); setState("signin"); }); }
      else read();
    };
    const hide = () => { flushSync(() => { clear(); setState("signin"); }); };
    const show = () => read();
    const unsubscribe = transport?.subscribe(changed);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", hide);
    window.addEventListener("pageshow", show);
    invalidate.current = clear;
    retry.current = read;
    read();
    return () => {
      mounted.current = false; pendingSignIn.current = null; alive = false; clear(); unsubscribe?.(); invalidate.current = () => {}; retry.current = () => {};
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", hide);
      window.removeEventListener("pageshow", show);
    };
  }, [itemId, transport]);

  const login = async () => {
    if (pendingSignIn.current) return;
    const attempt = {};
    pendingSignIn.current = attempt;
    invalidate.current(); setState("loading");
    try {
      if (!transport) throw new Error();
      await transport.signIn();
      if (mounted.current && pendingSignIn.current === attempt && !transport.available()) setState("unavailable");
    } catch {
      if (mounted.current && pendingSignIn.current === attempt) setState("unavailable");
    } finally {
      if (pendingSignIn.current === attempt) pendingSignIn.current = null;
    }
  };
  const logout = async () => {
    pendingSignIn.current = null;
    invalidate.current(); setState("signin");
    await signOut().catch(() => {});
  };
  return <div className="shell" data-theme={theme} lang={locale}>
    <aside><div className="brand"><span className="brand-mark" aria-hidden="true">M</span><div className="brand-copy"><b>Mastermind</b><small>{t("Research Vault", "研究库")}</small></div></div><nav aria-label={t("Company navigation", "公司导航")}><button onClick={() => location.assign("/os/")} aria-label={t("Open company", "打开公司")}><span className="nav-glyph" aria-hidden="true">↗</span><span className="nav-label">{t("Company", "公司")}</span></button></nav></aside>
    <main>
      <header><div><p className="eyebrow">{t("Research Vault", "研究库")}</p><h1>{t("Source passage", "来源片段")}</h1></div><div className="form-actions">{onLocaleChange && <button onClick={onLocaleChange} aria-label={t("Change language", "切换语言")}>{locale === "en" ? "中文" : "English"}</button>}{onThemeChange && <button onClick={onThemeChange} aria-label={t("Change theme", "切换主题")}>{theme === "dark" ? t("Light", "浅色") : t("Dark", "深色")}</button>}<button onClick={logout}>{t("Sign out", "退出登录")}</button></div></header>
      <p role="status" className="notice">{state === "loading" ? t("Loading authorized evidence…", "正在读取已授权证据…") : state === "ready" ? t("This citation contains one complete item from the source.", "此引用包含来源中的一个完整片段。") : state === "unavailable" ? t("This evidence item is unavailable.", "此证据片段不可用。") : t("Sign in to read this evidence item.", "请登录以阅读此证据片段。")}</p>
      {!item && <button onClick={() => transport?.available() ? retry.current() : void login()} disabled={state === "loading" || !itemId || !transport}>{transport?.available() ? t("Retry evidence", "重试读取证据") : t("Sign in to Research", "登录研究库")}</button>}
      {item && <section aria-label={t("Literal source evidence", "来源原文证据")}><h2>{item.title}</h2><pre className="visible-text">{item.text}</pre></section>}
    </main>
  </div>;
}
