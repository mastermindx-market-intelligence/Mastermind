// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, expect, it, vi } from "vitest";
import { createWebAuth } from "./web-auth";
import { ORIGIN } from "./public-config";

const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
const deferred = () => {
  let resolve!: (value: Response) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Response>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve();
};
const signal = () => new AbortController().signal;
const id = "mmos-project-adopt-" + "a".repeat(40);
const lookup = {
  schema: "mastermind.workspace_source_operation_lookup.v1" as const,
  action: "ADOPT_PLAN" as const,
  request_id: id,
  work_ref: "WS:ONE",
};
const fixedUrl = `${ORIGIN}/workspace/source-operation/operation?action=ADOPT_PLAN&request_id=${id}&work_ref=WS%3AONE`;
const referenceRoute = (url: string) =>
  url.startsWith(`${ORIGIN}/workspace/source-operation/`);

function setup() {
  vi.useFakeTimers();
  let count = 0;
  const popup = {
    location: "",
    closed: false,
    close: vi.fn(function () {
      popup.closed = true;
    }),
  };
  const messages = new Set<(e: MessageEvent) => void>();
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const url = String(input);
    if (referenceRoute(url))
      return jsonResponse({ unexpected: "read-without-handler" });
    return jsonResponse({
      token_type: "Bearer",
      access_token: "private-token",
      expires_in: 3600,
      scope: new URL(popup.location).searchParams.get("scope"),
    });
  });
  const client = createWebAuth({
    config: {
      executiveResource: null,
      webClientId: "fixture-public-client",
    },
    openPopup: () => popup,
    fetchFn: fetcher,
    crypto: {
      getRandomValues(array: Uint8Array) {
        array.fill(++count);
        return array;
      },
      subtle: { digest: () => Promise.resolve(new ArrayBuffer(32)) },
    } as unknown as Crypto,
    addEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.add(fn)) as unknown as typeof window.addEventListener,
    removeEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.delete(fn)) as unknown as typeof window.removeEventListener,
  });
  const callback = () => {
    const state = new URL(popup.location).searchParams.get("state");
    for (const listener of [...messages])
      listener({
        source: popup,
        origin: ORIGIN,
        data: {
          type: "mastermind-auth-callback",
          state,
          code: "code-opaque",
        },
      } as unknown as MessageEvent);
  };
  const login = async () => {
    const pending = client.signIn();
    await flush();
    callback();
    await flush();
    callback();
    await pending;
    fetcher.mockClear();
  };
  const reads = () =>
    fetcher.mock.calls.filter(([input]) => referenceRoute(String(input)));
  return { client, fetcher, login, reads };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  history.replaceState(null, "", "/os/");
});

it("uses fixed status GET and explicit reconciliation POST with the private acquisition bearer", async () => {
  const e = setup();
  await e.login();
  e.fetcher.mockImplementation(async () => jsonResponse({ owner: "body" }));
  await e.client.sourceOperations!.readSourceOperation(lookup, signal());
  await e.client.sourceOperations!.reconcileSourceOperation(lookup, signal());
  expect(e.reads()).toHaveLength(2);
  const [read, reconcile] = e.reads();
  expect(String(read[0])).toBe(fixedUrl);
  expect(read[1]?.method).toBe("GET");
  expect(read[1]?.body).toBeUndefined();
  expect(String(reconcile[0])).toBe(
    `${ORIGIN}/workspace/source-operation/reconcile`,
  );
  expect(reconcile[1]).toMatchObject({
    method: "POST",
    credentials: "omit",
    redirect: "error",
    cache: "no-store",
    headers: {
      Authorization: "Bearer private-token",
      "Content-Type": "application/json",
    },
  });
  expect(JSON.parse(String(reconcile[1]?.body))).toEqual(lookup);
});
it("does not dispatch without acquisition and never retries a refused response", async () => {
  const e = setup();
  await expect(
    e.client.sourceOperations!.reconcileSourceOperation(lookup, signal()),
  ).rejects.toThrow();
  expect(e.reads()).toHaveLength(0);
  await e.login();
  e.fetcher.mockImplementation(async () =>
    jsonResponse({ private: "canary" }, 403),
  );
  await expect(
    e.client.sourceOperations!.reconcileSourceOperation(lookup, signal()),
  ).rejects.toThrow("SOURCE_OPERATION_FAILED");
  expect(e.reads()).toHaveLength(1);
});
it("discards delayed POST after sign-out", async () => {
  const e = setup();
  await e.login();
  const pending = deferred();
  e.fetcher.mockImplementation(() => pending.promise);
  const post = e.client.sourceOperations!.reconcileSourceOperation(
    lookup,
    signal(),
  );
  const rejected = expect(post).rejects.toThrow();
  await e.client.signOut();
  pending.resolve(jsonResponse({ owner: "late" }));
  await rejected;
  expect(e.reads()).toHaveLength(1);
});
it("enforces the response cap on authenticated POST", async () => {
  const e = setup();
  await e.login();
  e.fetcher.mockImplementation(async () =>
    jsonResponse({ tooLarge: "x".repeat(32768) }),
  );
  await expect(
    e.client.sourceOperations!.reconcileSourceOperation(lookup, signal()),
  ).rejects.toThrow("RESPONSE_TOO_LARGE");
  expect(e.reads()).toHaveLength(1);
});

it('serializes allowed32KiB file text as UTF8 in the real web POST and keeps response/other operation caps',async()=>{
 const e=setup();await e.login();e.fetcher.mockImplementation(async()=>jsonResponse({prepared:true}));
 for(const unit of ['"','\\','\r','\n','\t','中文😀','"\\\r\n\t中文😀']){
  const width=new TextEncoder().encode(unit).length,content=unit.repeat(Math.floor(32768/width))+'x'.repeat(32768%width);
  const body={action:'add_project_file' as const,request:{schema:'mastermind.project_file_add_request.v1',
    request_id:'mmos-project-file-add-'+'a'.repeat(40),work_ref:'WS:TEST',source_commit:'b'.repeat(40),base_revision:'c'.repeat(64),
    file:{display_name:'计划.MD',media_type:'text/markdown',content_utf8:content}}};
  await e.client.sourceOperations!.prepareSourceOperation(body,signal());
  const actual=e.reads().at(-1)![1]!.body as string;
  expect(new TextEncoder().encode(actual).length).toBeLessThanOrEqual(98304);
  expect(JSON.parse(actual).request.file.content_utf8).toBe(content);
  const count=e.reads().length;
  await expect(e.client.sourceOperations!.prepareSourceOperation({...body,request:{...body.request,file:{...body.request.file,content_utf8:content+'x'}}},signal())).rejects.toThrow();
  expect(e.reads()).toHaveLength(count);
 }
 e.fetcher.mockImplementation(async()=>jsonResponse({data:'x'.repeat(32768)}));
 await expect(e.client.sourceOperations!.reconcileSourceOperation(lookup,signal())).rejects.toThrow();
});
