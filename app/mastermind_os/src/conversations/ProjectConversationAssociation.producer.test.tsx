// @vitest-environment jsdom
import { useLayoutEffect, useRef } from "react";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import producer from "../fixtures/project-session-association-producer.json";
import { ProjectConversationAssociation } from "./ProjectConversationAssociation";

afterEach(cleanup);
it("renders the actual pure producer observation and clears it on changed source", async () => {
  const selection = { workRef: producer.selection.work_ref, rootJobId: producer.selection.root_job_id };
  let returned: unknown = producer;
  const readAssociation = vi.fn(async () => returned);
  const view = render(<ProjectConversationAssociation selection={selection} authGeneration={1}
    hostGeneration="observed-host-1" readAssociation={readAssociation} />);
  await waitFor(() => expect(view.container.textContent).toContain(producer.materialization.recorded_at));
  expect(screen.getAllByRole("heading").map(h => h.tagName)).not.toContain("H1");
  expect(readAssociation).toHaveBeenCalledWith(expect.objectContaining(selection));
  expect(view.container.textContent).toContain(producer.selection.work_ref);
  expect(view.container.querySelector("details")).not.toBeNull();
  expect(screen.queryByRole("button", {name: /^(send|continue|create|start|resume)\b/i})).toBeNull();
  returned = { ...producer, availability: "UNAVAILABLE", state: "UNAVAILABLE", reason: "SOURCE_CHANGED",
    project_source: null, runtime_creation: null, materialization: null };
  view.rerender(<ProjectConversationAssociation selection={selection} authGeneration={2}
    hostGeneration="observed-host-1" readAssociation={readAssociation} />);
  await waitFor(() => expect(view.container.textContent).toContain("SOURCE_CHANGED"));
  expect(view.container.textContent).not.toContain(producer.materialization.recorded_at);
});

it("removes old evidence during commit before passive effects on an auth replacement", async () => {
  const selection = {workRef: producer.selection.work_ref, rootJobId: producer.selection.root_job_id};
  const layouts: string[] = [];
  const readAssociation = vi.fn(async () => producer);
  function Probe({authGeneration}: {authGeneration: number}) {
    const region = useRef<HTMLDivElement>(null);
    useLayoutEffect(() => { layouts.push(region.current?.textContent ?? ""); });
    return <div ref={region}><ProjectConversationAssociation selection={selection} authGeneration={authGeneration}
      hostGeneration="host-1" readAssociation={readAssociation} /></div>;
  }
  const view = render(<Probe authGeneration={1} />);
  await waitFor(() => expect(view.container.textContent).toContain(producer.materialization.recorded_at));
  view.rerender(<Probe authGeneration={2} />);
  expect(layouts.at(-1)).not.toContain(producer.materialization.recorded_at);
  expect(layouts.at(-1)).toContain("Loading session information");
});
