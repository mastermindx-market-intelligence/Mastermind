/**
 * Load boundary only. `packages/db/src/computers.ts` imports Prisma at module
 * scope. These stand-ins let that file evaluate. They create no Computer row
 * and are not Rakazo behavior. Callers must not treat them as a database.
 */
export const Prisma = {
  sql() {
    return { strings: [], values: [] };
  },
  TransactionIsolationLevel: { Serializable: "Serializable" },
};

export class PrismaClient {}
