import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useVocabListsStore } from "@/stores/vocab-lists";

function stubFetch(handler: (url: string) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(handler(url)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    ),
  );
}

const ME = {
  username: "alice",
  is_admin: false,
  must_change_password: false,
};

describe("auth store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });
  afterEach(() => {
    api.setToken(null);
    api.setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
  });

  it("is hydrated right away without a token", async () => {
    const auth = useAuthStore();
    expect(auth.hydrated).toBe(false);
    await auth.hydrate();
    expect(auth.hydrated).toBe(true);
    expect(auth.isAuthed).toBe(false);
  });

  it("marks hydrated only after /me resolves", async () => {
    api.setToken("tok");
    stubFetch((url) => (url.endsWith("/api/auth/me") ? { authenticated: true, user: ME } : {}));
    const auth = useAuthStore();
    const pending = auth.hydrate();
    expect(auth.hydrated).toBe(false);
    await pending;
    expect(auth.hydrated).toBe(true);
    expect(auth.isAuthed).toBe(true);
  });

  it("silently drops a token the server no longer accepts", async () => {
    api.setToken("stale");
    stubFetch(() => ({ authenticated: false }));
    const auth = useAuthStore();
    await auth.hydrate();
    expect(auth.isAuthed).toBe(false);
    expect(auth.hydrated).toBe(true);
    expect(api.getToken()).toBeNull();
  });

  it("resets per-user stores on logout", async () => {
    api.setToken("tok");
    stubFetch((url) => (url.endsWith("/api/auth/me") ? { authenticated: true, user: ME } : {}));
    const auth = useAuthStore();
    await auth.hydrate();

    const analysis = useAnalysisStore();
    analysis.adoptSavedId(42, "Alice's text", []);
    const lists = useVocabListsStore();
    lists.lists = [{ id: 1 } as never];
    lists.loadedAt = Date.now();

    await auth.logout();
    expect(analysis.savedTextId).toBeNull();
    expect(lists.lists).toEqual([]);
    expect(lists.loadedAt).toBeNull();
  });

  it("forgets the reminder caches of the previous account on logout", async () => {
    api.setToken("tok");
    stubFetch((url) => (url.endsWith("/api/auth/me") ? { authenticated: true, user: ME } : {}));
    const auth = useAuthStore();
    await auth.hydrate();
    localStorage.setItem("qingdu.notif.lastDueCount", "12");
    localStorage.setItem("qingdu.notif.lastStreak", "40");
    localStorage.setItem("qingdu.notif.lastActiveDate", "2026-10-10");

    await auth.logout();
    expect(localStorage.getItem("qingdu.notif.lastDueCount")).toBeNull();
    expect(localStorage.getItem("qingdu.notif.lastStreak")).toBeNull();
    expect(localStorage.getItem("qingdu.notif.lastActiveDate")).toBeNull();
  });
});
