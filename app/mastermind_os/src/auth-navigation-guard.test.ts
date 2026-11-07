// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { canNavigateForAutomaticSignIn, explicitLogoutRecorded, registerUnsavedNavigationHold } from "./auth-navigation-guard";

describe("ephemeral auth navigation protection", () => {
  it("never treats an explicit sign-out marker as passive token expiry", () => {
    const key = "mastermind-os-auth-logout-v1:synthetic-app";
    localStorage.removeItem(key);
    expect(explicitLogoutRecorded()).toBe(false);
    try {
      localStorage.setItem(key, "1");
      expect(explicitLogoutRecorded()).toBe(true);
    } finally { localStorage.removeItem(key); }
  });
  it("allows unattended SSO only while all mounted UI owners are safe", () => {
    expect(canNavigateForAutomaticSignIn()).toBe(true);
    let dirty = false;
    const releaseA = registerUnsavedNavigationHold(() => dirty);
    const releaseB = registerUnsavedNavigationHold(() => true);
    try {
      expect(canNavigateForAutomaticSignIn()).toBe(false);
      releaseB();
      expect(canNavigateForAutomaticSignIn()).toBe(true);
      dirty = true;
      expect(canNavigateForAutomaticSignIn()).toBe(false);
      dirty = false;
      expect(canNavigateForAutomaticSignIn()).toBe(true);
    } finally { releaseA(); releaseB(); }
    expect(canNavigateForAutomaticSignIn()).toBe(true);
  });

  it("fails closed if a mounted UI owner cannot report its draft state", () => {
    const release = registerUnsavedNavigationHold(() => { throw new Error("probe unavailable"); });
    try { expect(canNavigateForAutomaticSignIn()).toBe(false); }
    finally { release(); }
    expect(canNavigateForAutomaticSignIn()).toBe(true);
  });
});
