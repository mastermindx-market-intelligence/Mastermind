// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ByokRolesPanel } from "./ByokRolesPanel";

afterEach(cleanup);

describe("BYOK role setup boundary", () => {
  it("shows candidates without connection claims or credential collection", () => {
    const { container } = render(<ByokRolesPanel />);
    expect(screen.getAllByText("Needs setup")).toHaveLength(2);
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
    expect(screen.getAllByText("Not proven")).toHaveLength(2);
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector("input, textarea, form")).toBeNull();
    expect(screen.queryByText(/connected|ready to run/i)).toBeNull();
    fireEvent.click(screen.getAllByText("Setup requirements")[0]);
    expect(screen.getAllByText("Connection controls are not available in this session.")).toHaveLength(2);
  });

  it("only hands an explicit role to the supplied connection owner on a click", () => {
    const review = vi.fn();
    render(<ByokRolesPanel onReviewConnection={review} locale="zh-CN" />);
    expect(review).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByText("设置要求")[1]);
    fireEvent.click(screen.getByRole("button", { name: "查看连接 · 秘书" }));
    expect(review).toHaveBeenCalledExactlyOnceWith("secretary");
    expect(screen.getAllByText("需要设置")).toHaveLength(2);
    expect(screen.getAllByText("尚未验证")).toHaveLength(2);
  });
});
