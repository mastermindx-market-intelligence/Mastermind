import {
  decodeBacklogResult,
  decodeCompanyRead,
  validateBacklogRequest,
  validateCompanySelection,
  type BacklogRequest,
  type BacklogResult,
  type CompanyRead,
  type CompanySelection,
} from "./contract";

export interface CompanyRawMethods {
  readCompany?(
    request: CompanySelection & { signal: AbortSignal },
  ): Promise<unknown>;
  createCompanyBacklog?(request: {
    payload: BacklogRequest;
    signal: AbortSignal;
  }): Promise<unknown>;
}
export interface CompanyTransport {
  read(selection: CompanySelection, signal: AbortSignal): Promise<CompanyRead>;
  createBacklog?(
    request: BacklogRequest,
    context: { scopeKey: string; companyId: string },
    signal: AbortSignal,
  ): Promise<BacklogResult>;
}
type Client = CompanyRawMethods & {
  getState(): { status: string; acquisition: boolean };
  invalidationGeneration?: () => number;
};

/** Uses the incumbent host identity and invalidation owner, not another auth session. */
export function bindCompanyTransport(
  client: Client,
): CompanyTransport | undefined {
  if (!client.readCompany || !client.invalidationGeneration) return undefined;
  function guard(signal: AbortSignal) {
    const generation = client.invalidationGeneration!();
    const verify = () => {
      const state = client.getState();
      if (
        signal.aborted ||
        !Number.isSafeInteger(generation) ||
        generation !== client.invalidationGeneration?.()
      )
        throw new Error("READ_CANCELLED");
      if (state.status !== "signed_in" || !state.acquisition)
        throw new Error("COMPANY_ACCESS_REQUIRED");
    };
    verify();
    return verify;
  }
  return Object.freeze({
    async read(selection: CompanySelection, signal: AbortSignal) {
      validateCompanySelection(selection);
      const verify = guard(signal),
        method = client.readCompany!;
      const raw = await method.call(client, { ...selection, signal });
      verify();
      if (client.readCompany !== method) throw new Error("READ_CANCELLED");
      return decodeCompanyRead(raw, selection);
    },
    ...(client.createCompanyBacklog
      ? {
          async createBacklog(
            request: BacklogRequest,
            context: { scopeKey: string; companyId: string },
            signal: AbortSignal,
          ) {
            validateBacklogRequest(request);
            const verify = guard(signal),
              method = client.createCompanyBacklog!;
            // The existing durable pointer must be reserved by the UI before this
            // one call. Any rejection after invocation remains held, never replayed.
            const raw = await method.call(client, { payload: request, signal });
            verify();
            if (client.createCompanyBacklog !== method)
              throw new Error("READ_CANCELLED");
            return decodeBacklogResult(
              raw,
              request,
              context.scopeKey,
              context.companyId,
            );
          },
        }
      : {}),
  });
}
