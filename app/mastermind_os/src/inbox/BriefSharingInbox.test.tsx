// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BriefSharingInbox, type BriefSharingRequestView } from "./BriefSharingInbox";

afterEach(cleanup);

function request(overrides: Partial<BriefSharingRequestView> = {}): BriefSharingRequestView {
  return {
    requestRef: "private:brief-share-1",
    requestRevision: "request:1",
    deliveryId: "delivery:1",
    contentSha256: "a".repeat(64),
    title: "Week 44 platform brief",
    version: "v3",
    audienceName: "Platform team",
    audienceMemberCount: 6,
    access: "VIEW_ONLY",
    ...overrides,
  };
}

function pendingReview() {
  let resolveReview!: () => void;
  let rejectReview!: (reason?: unknown) => void;
  const onReview = vi.fn(() => new Promise<void>((resolve, reject) => {
    resolveReview = resolve;
    rejectReview = reject;
  }));
  return { onReview, resolve: () => resolveReview(), reject: () => rejectReview(new Error("disk on fire")) };
}

async function flush() {
  await act(async () => {});
}

describe("brief-sharing request review", () => {
  it("renders the supplied request and never takes an action on render", () => {
    const onReview = vi.fn();
    const brief = request();
    const { container } = render(<BriefSharingInbox locale="en" state="ready" requests={[brief]} onReview={onReview} />);
    const section = screen.getByRole("region", { name: "Brief sharing requests" });
    expect(section.querySelector("h1")).toBeNull();
    expect(section.textContent).toContain("Terminal");
    expect(screen.getByText("Share this brief?")).toBeTruthy();
    expect(screen.getByText("Week 44 platform brief")).toBeTruthy();
    expect(screen.getByText("Version v3")).toBeTruthy();
    expect(screen.getByText("Platform team")).toBeTruthy();
    expect(screen.getByText("6 members")).toBeTruthy();
    expect(screen.getByText("View only")).toBeTruthy();
    expect(document.body.textContent).toContain("Some requests may be missing.");
    expect(document.body.textContent).toContain("Sources and access");
    // Text only: the existing global Inbox owns h1 and no opaque identifiers leak.
    expect(container.querySelector("h1")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("article")?.textContent).not.toContain("private:brief-share-1");
    expect(container.querySelector("article")?.textContent).not.toContain("delivery:1");
    expect(onReview).not.toHaveBeenCalled();
  });

  it("omits a null version and member count instead of inventing them", () => {
    render(<BriefSharingInbox locale="en" state="ready" requests={[request({ version: null, audienceMemberCount: null })]} />);
    expect(screen.queryByText(/version/i)).toBeNull();
    expect(screen.queryByText(/member/i)).toBeNull();
    expect(screen.queryByText("3 members")).toBeNull();
    expect(screen.queryByText("6 members")).toBeNull();
    expect(screen.getByText("Week 44 platform brief")).toBeTruthy();
    expect(screen.getByText("Platform team")).toBeTruthy();
    expect(screen.getByText("View only")).toBeTruthy();
  });

  it("renders the zh-CN copy", () => {
    render(<BriefSharingInbox locale="zh-CN" state="ready" requests={[request()]} />);
    const section = screen.getByRole("region", { name: "简报共享请求" });
    expect(section.querySelector("h1")).toBeNull();
    expect(section.textContent).toContain("Terminal");
    expect(screen.getByText("共享这份简报？")).toBeTruthy();
    expect(screen.getByText("在 Terminal 中继续")).toBeTruthy();
    expect(screen.getByText("仅查看")).toBeTruthy();
    expect(screen.getByText("6 名成员")).toBeTruthy();
    expect(screen.getByText("版本 v3")).toBeTruthy();
    expect(screen.queryByText("Share this brief?")).toBeNull();
  });

  it("keeps an unavailable source distinct from an empty ready list", () => {
    const { rerender } = render(<BriefSharingInbox locale="en" state="unavailable" requests={[]} />);
    expect(screen.getByText("Requests are unavailable.")).toBeTruthy();
    expect(screen.queryByText("No requests were returned from Terminal.")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<BriefSharingInbox locale="en" state="ready" requests={[]} />);
    expect(screen.getByText("No requests were returned from Terminal.")).toBeTruthy();
    expect(screen.queryByText("Requests are unavailable.")).toBeNull();
    expect(screen.queryByRole("button", { name: /continue|retry|share/i })).toBeNull();
    expect(screen.queryByText(/all clear|nothing needs/i)).toBeNull();
    rerender(<BriefSharingInbox locale="en" state="loading" requests={[]} />);
    expect(screen.getByText("Loading brief-sharing requests…")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("hands back exactly the selected request once and disables duplicates while pending", () => {
    const brief = request();
    const review = pendingReview();
    render(<BriefSharingInbox locale="en" state="ready" requests={[brief]} onReview={review.onReview} />);
    const button = screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(review.onReview).toHaveBeenCalledExactlyOnceWith(brief);
    expect(screen.getByText("Opening Terminal…")).toBeTruthy();
    fireEvent.click(button);
    expect(review.onReview).toHaveBeenCalledExactlyOnceWith(brief);
    expect(button.disabled).toBe(true);
  });

  it("keeps the row listed after a requested handoff without claiming a share", async () => {
    const review = pendingReview();
    render(<BriefSharingInbox locale="en" state="ready" requests={[request()]} onReview={review.onReview} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await act(async () => { review.resolve(); });
    expect(screen.getByText("Continue in Terminal to review this request.")).toBeTruthy();
    expect(screen.getByText("Week 44 platform brief")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/shared|all clear/i);
    expect((screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: /retry|resend/i })).toBeNull();
    await flush();
    expect(review.onReview).toHaveBeenCalledTimes(1);
  });

  it("reports an unavailable outcome without the raw error and without replay", async () => {
    const review = pendingReview();
    render(<BriefSharingInbox locale="en" state="ready" requests={[request()]} onReview={review.onReview} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await act(async () => { review.reject(); });
    expect(screen.getByText("Terminal could not be confirmed open.")).toBeTruthy();
    expect(document.body.textContent).toContain("Check the original Terminal page.");
    expect(document.body.textContent).not.toContain("disk on fire");
    expect(screen.getByText("Week 44 platform brief")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await flush();
    expect(review.onReview).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /retry|resend/i })).toBeNull();
  });

  it("keeps review disabled and says so when no handoff source is supplied", () => {
    render(<BriefSharingInbox locale="en" state="ready" requests={[request()]} />);
    const button = screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("Review in Terminal is unavailable.")).toBeTruthy();
    fireEvent.click(button);
    expect(document.body.textContent).not.toContain("Requesting review handoff");
  });

  it("ignores a late completion after the supplied identity changed", async () => {
    const first = request();
    const review = pendingReview();
    const { rerender } = render(<BriefSharingInbox locale="en" state="ready" requests={[first]} onReview={review.onReview} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    const second = request({ requestRef: "private:brief-share-2", requestRevision: "request:2", deliveryId: "delivery:2", contentSha256: "b".repeat(64), title: "Week 45 platform brief" });
    rerender(<BriefSharingInbox locale="en" state="ready" requests={[second]} onReview={review.onReview} />);
    await act(async () => { review.resolve(); });
    expect(screen.queryByText("Week 44 platform brief")).toBeNull();
    expect(screen.getByText("Week 45 platform brief")).toBeTruthy();
    expect(screen.queryByText("Continue in Terminal to review this request.")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("Share this brief?")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(review.onReview).toHaveBeenCalledTimes(2);
    expect(review.onReview).toHaveBeenLastCalledWith(second);
  });

  it("does not replay an already attempted request identity across rerenders", async () => {
    const brief = request();
    const review = pendingReview();
    const { rerender } = render(<BriefSharingInbox locale="en" state="ready" requests={[brief]} onReview={review.onReview} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    rerender(<BriefSharingInbox locale="en" state="ready" requests={[request()]} onReview={review.onReview} />);
    await act(async () => { review.resolve(); });
    expect(review.onReview).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Continue in Terminal to review this request.")).toBeTruthy();
    expect(screen.getByText("Week 44 platform brief")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

it("contains a synchronous handoff exception without exposing it or replaying", async () => {
  const onReview = vi.fn(() => { throw new Error("synthetic private native detail"); });
  render(<BriefSharingInbox locale="en" state="ready" requests={[request()]} onReview={onReview} />);
  fireEvent.click(screen.getByRole("button", {name:"Continue in Terminal"}));
  await flush();
  expect(screen.getByText("Terminal could not be confirmed open.")).toBeTruthy();
  expect(document.body.textContent).not.toContain("synthetic private native detail");
  fireEvent.click(screen.getByRole("button", {name:"Continue in Terminal"}));
  expect(onReview).toHaveBeenCalledTimes(1);
});

it("limits primary requests to eight and puts the exact remaining count in a closed disclosure", () => {
  const requests=Array.from({length:10},(_,i)=>request({requestRef:`request-${i}`,deliveryId:`delivery-${i}`,title:`Actual brief ${i}`}));
  const {container}=render(<BriefSharingInbox locale="en" state="ready" requests={requests}/>);
  expect(container.querySelectorAll(".brief-sharing-inbox > article")).toHaveLength(8);
  const more=container.querySelector("details.brief-sharing-more") as HTMLDetailsElement;
  expect(more.open).toBe(false);
  expect(more.querySelector("summary")?.textContent).toBe("Show 2 more requests");
  expect(more.querySelectorAll("article")).toHaveLength(2);
  expect(container.querySelectorAll("details.brief-sharing-sources")).toHaveLength(1);
  expect(container.querySelector("details.brief-sharing-sources")?.textContent).toContain("request-0");
});
