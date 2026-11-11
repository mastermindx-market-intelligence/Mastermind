// @vitest-environment jsdom
import sourceFixture from "../../../../tests/fixtures/paperclip_connections.json";
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyConnectionsView } from "./CompanyConnectionsView";
import { CompanyViews } from "./CompanyViews";
import { decodeCompanyRead, type CompanySnapshot } from "./contract";

const fixture = () => JSON.parse(JSON.stringify(sourceFixture));
const snapshot = () => decodeCompanyRead(fixture(), { view: "overview" }) as CompanySnapshot;
afterEach(cleanup);

describe("Company connections uses the existing visible records and navigation", () => {
  it("opens the actual directory and exact existing runtime inspector", () => {
    const onSelect = vi.fn();
    render(<CompanyConnectionsView snapshot={snapshot()} locale="en" onSelect={onSelect} />);
    expect(screen.getByRole("heading", { name: "Team connections" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Find a teammate" }));
    expect(onSelect).toHaveBeenLastCalledWith({ view: "people" });
    fireEvent.click(screen.getAllByRole("button", { name: "Engineer" })[0]);
    expect(onSelect).toHaveBeenLastCalledWith({ view: "runtime", itemId: "00000000-0000-4000-8000-000000000002" });
    expect(screen.queryByRole("button", { name: /^delegate|^resume|^consult/i })).toBeNull();
  });
  it("does not display ambiguous relationships as a valid hierarchy", () => {
    const source = fixture(); source.collections.people.items[0].reportsTo = source.collections.people.items[1].id;
    render(<CompanyConnectionsView snapshot={decodeCompanyRead(source, { view: "overview" }) as CompanySnapshot} locale="en" onSelect={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toContain("need checking");
    expect(screen.queryByRole("button", { name: "Engineer" })).toBeNull();
  });
  it("keeps useful navigation in Chinese", () => {
    const onSelect = vi.fn();
    render(<CompanyConnectionsView snapshot={snapshot()} locale="zh-CN" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "查找团队成员" }));
    expect(onSelect).toHaveBeenLastCalledWith({ view: "people" });
    expect(screen.getByRole("heading", { name: "团队关系" })).toBeTruthy();
  });
  it("explains a manager outside the loaded window without inventing leadership", () => {
    const source = fixture(); source.view = "people";
    source.collections.people.items[1].reportsTo = "00000000-0000-4000-8000-999999999999";
    render(<CompanyViews snapshot={decodeCompanyRead(source, { view: "people" }) as CompanySnapshot}
      selection={{ view: "people" }} locale="en" onSelect={vi.fn()} />);
    expect(screen.getByText("Manager outside this loaded view")).toBeTruthy();
    expect(screen.queryByText("00000000-0000-4000-8000-999999999999")).toBeNull();
    expect(screen.queryByText("Company leadership")).toBeNull();
  });
});
