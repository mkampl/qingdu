import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick } from "vue";

import { useAuthStore } from "@/stores/auth";

import { onAuthReady } from "./use-auth-ready";

const USER = { username: "alice", is_admin: false, must_change_password: false };

describe("onAuthReady", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("waits for hydration, then loads; clears on logout", async () => {
    const auth = useAuthStore();
    const load = vi.fn();
    const clear = vi.fn();
    effectScope().run(() => onAuthReady(load, clear));

    expect(load).not.toHaveBeenCalled();
    expect(clear).not.toHaveBeenCalled();

    auth.user = USER as never;
    auth.hydrated = true;
    await nextTick();
    expect(load).toHaveBeenCalledOnce();

    auth.user = null;
    await nextTick();
    expect(clear).toHaveBeenCalledOnce();
  });

  it("reports anonymous once hydration settles without a user", async () => {
    const auth = useAuthStore();
    const load = vi.fn();
    const clear = vi.fn();
    effectScope().run(() => onAuthReady(load, clear));
    auth.hydrated = true;
    await nextTick();
    expect(load).not.toHaveBeenCalled();
    expect(clear).toHaveBeenCalledOnce();
  });
});
