import { describe, expect, it, vi } from "vitest";
import { OperationController } from "./operation-controller";
import type { CommandIntent, EffectReceipt, FiniteCommandPort, OperationPointer, PendingPointerStore } from "./operation-controller";

const message: CommandIntent = { kind: "message", targetKey: "session-A", payload: { text: "Continue accepted slice" } };
function fixture() {
  const hints = new Map<string, OperationPointer>();
  const store: PendingPointerStore = {
    read: (scope) => hints.get(scope) ?? null,
    write: (scope, pointer) => { hints.set(scope, pointer); },
    clear: (scope, pointer) => {
      if (hints.get(scope)?.operationKey === pointer.operationKey) hints.delete(scope);
    },
  };
  const echo = (pointer: OperationPointer): EffectReceipt => ({ ...pointer, disposition: "accepted" });
  const port: FiniteCommandPort = {
    context: () => ({ principalScope: "scope-A", generation: "generation-1" }),
    prepare: vi.fn((intent) => ({ operationKey: "operation-A", kind: intent.kind, targetKey: intent.targetKey })),
    submit: vi.fn(async (pointer) => echo(pointer)),
    readOperation: vi.fn(async (pointer) => echo(pointer)),
  };
  const controller = new OperationController(port, store);
  return { controller, port, hints, echo };
}

describe("host failures before a Promise is returned", () => {
  it("reconciles a synchronously thrown submit without another submission", async () => {
    const f = fixture();
    f.port.submit = vi.fn(() => { throw new Error("synchronous transport failure"); });
    expect((await f.controller.begin(message)).reason).toBe("TRANSPORT_ERROR");
    expect(f.hints.get("scope-A")?.operationKey).toBe("operation-A");
    const recovered = await f.controller.recover();
    expect(recovered.status).toBe("accepted");
    expect(f.port.readOperation).toHaveBeenCalledTimes(1);
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.hints.size).toBe(0);
  });

  it("allows a second read after a synchronous readOperation failure", async () => {
    const f = fixture();
    f.hints.set("scope-A", { operationKey: "operation-A", kind: "message", targetKey: "session-A" });
    f.port.readOperation = vi.fn().mockImplementationOnce(() => { throw new Error("read failed synchronously"); }).mockImplementation(async (p: OperationPointer) => f.echo(p));
    expect((await f.controller.recover()).reason).toBe("RECOVER_FAILED");
    expect(f.hints.size).toBe(1);
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.port.readOperation).toHaveBeenCalledTimes(2);
    expect(f.port.submit).not.toHaveBeenCalled();
    expect(f.hints.size).toBe(0);
  });
  it("keeps recovery read-only after an asynchronously rejected submission", async () => {
    const f = fixture();
    f.port.submit = vi.fn(async () => { throw new Error("async transport failure"); });
    expect((await f.controller.begin(message)).reason).toBe("TRANSPORT_ERROR");
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.port.readOperation).toHaveBeenCalledTimes(1);
  });

  it("releases a rejected asynchronous recovery for the next read", async () => {
    const f = fixture();
    f.hints.set("scope-A", { operationKey: "operation-A", kind: "message", targetKey: "session-A" });
    f.port.readOperation = vi.fn().mockRejectedValueOnce(new Error("async read failure")).mockImplementation(async (p: OperationPointer) => f.echo(p));
    expect((await f.controller.recover()).reason).toBe("RECOVER_FAILED");
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.port.submit).not.toHaveBeenCalled();
  });

  it("registers in-flight state before synchronous host callbacks re-enter recovery", async () => {
    const f = fixture();
    let joined: ReturnType<OperationController["recover"]> | undefined;
    f.port.submit = vi.fn((pointer) => {
      joined = f.controller.recover();
      return Promise.resolve(f.echo(pointer));
    });
    expect((await f.controller.begin(message)).status).toBe("accepted");
    expect((await joined)?.status).toBe("accepted");
    expect(f.port.readOperation).not.toHaveBeenCalled();
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });

  it("does not require invalidate/reload to use a recovered controller", async () => {
    const f = fixture();
    f.port.submit = vi.fn().mockImplementationOnce(() => { throw new Error("sync failure"); }).mockImplementation(async (p: OperationPointer) => f.echo(p));
    await f.controller.begin(message);
    expect((await f.controller.recover()).status).toBe("accepted");
    f.port.prepare = vi.fn((intent) => ({ operationKey: "operation-B", kind: intent.kind, targetKey: intent.targetKey }));
    expect((await f.controller.begin(message)).status).toBe("accepted");
    expect(f.port.submit).toHaveBeenCalledTimes(2);
    expect(f.port.readOperation).toHaveBeenCalledTimes(1);
    expect(f.hints.size).toBe(0);
  });
});

describe("recovery identity remains fenced", () => {
  it("retains a mismatched readback after a synchronous submit error", async () => {
    const f = fixture();
    f.port.submit = vi.fn(() => { throw new Error("outcome unknown"); });
    await f.controller.begin(message);
    f.port.readOperation = vi.fn().mockImplementationOnce(async (p: OperationPointer) => ({ ...f.echo(p), operationKey: "wrong-operation" })).mockImplementation(async (p: OperationPointer) => f.echo(p));
    expect((await f.controller.recover()).reason).toBe("RECEIPT_MISMATCH");
    expect(f.hints.get("scope-A")?.operationKey).toBe("operation-A");
    expect((await f.controller.begin(message)).reason).toBe("PENDING_POINTER");
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });

  it("does not reinstall the old join after synchronous invalidation", async () => {
    const f = fixture();
    f.port.submit = vi.fn(() => {
      f.controller.invalidate();
      throw new Error("host changed while calling submit");
    });
    expect((await f.controller.begin(message)).status).toBe("idle");
    expect(f.hints.size).toBe(1);
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(f.port.readOperation).toHaveBeenCalledTimes(1);
  });

  it("joins a reentrant read without issuing a second read", async () => {
    const f = fixture();
    f.hints.set("scope-A", { operationKey: "operation-A", kind: "message", targetKey: "session-A" });
    let joined: ReturnType<OperationController["recover"]> | undefined;
    let calls = 0;
    f.port.readOperation = vi.fn((pointer) => {
      if (++calls === 1) joined = f.controller.recover();
      return Promise.resolve(f.echo(pointer));
    });
    expect((await f.controller.recover()).status).toBe("accepted");
    expect((await joined)?.status).toBe("accepted");
    expect(f.port.readOperation).toHaveBeenCalledTimes(1);
    expect(f.port.submit).not.toHaveBeenCalled();
  });
});
