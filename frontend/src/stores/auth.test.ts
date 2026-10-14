import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
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
  describe("timezone", () => {
    function recordFetch(user: Record<string, unknown>) {
      const calls: { url: string; method: string; body: unknown }[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn((url: string, init?: RequestInit) => {
          const method = init?.method ?? "GET";
          const body = init?.body ? JSON.parse(String(init.body)) : undefined;
          calls.push({ url, method, body });
          let payload: unknown = {};
          if (url.endsWith("/api/auth/me")) payload = { authenticated: true, user };
          if (url.endsWith("/api/auth/me/settings")) payload = { ...user, ...(body as object) };
          return Promise.resolve(
            new Response(JSON.stringify(payload), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }),
      );
      return calls;
    }
    const patches = (calls: { url: string; method: string; body: unknown }[]) =>
      calls.filter((c) => c.url.endsWith("/api/auth/me/settings") && c.method === "PATCH");

    beforeEach(() => {
      vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
        timeZone: "Asia/Shanghai",
      } as Intl.ResolvedDateTimeFormatOptions);
    });
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("sends the device zone when the account has none yet", async () => {
      api.setToken("tok");
      const calls = recordFetch({ ...ME, timezone: null });
      const auth = useAuthStore();
      await auth.hydrate();
      await vi.waitFor(() => expect(patches(calls)).toHaveLength(1));
      expect(patches(calls)[0].body).toEqual({ timezone: "Asia/Shanghai" });
      await vi.waitFor(() => expect(auth.user?.timezone).toBe("Asia/Shanghai"));
    });

    it("leaves a stored zone alone", async () => {
      api.setToken("tok");
      const calls = recordFetch({ ...ME, timezone: "Europe/Vienna" });
      const auth = useAuthStore();
      await auth.hydrate();
      await new Promise((r) => setTimeout(r, 0));
      expect(patches(calls)).toHaveLength(0);
      expect(auth.user?.timezone).toBe("Europe/Vienna");
    });

    it("leaves an older server without the field alone", async () => {
      api.setToken("tok");
      const calls = recordFetch({ ...ME });
      await useAuthStore().hydrate();
      await new Promise((r) => setTimeout(r, 0));
      expect(patches(calls)).toHaveLength(0);
    });

    it("sends the HSK version picked on this device when the account differs", async () => {
      api.setToken("tok");
      useSettingsStore().hskVersion = "old";
      const calls = recordFetch({ ...ME, timezone: "Europe/Vienna", hsk_focus_version: "new" });
      const auth = useAuthStore();
      await auth.hydrate();
      await vi.waitFor(() => expect(patches(calls)).toHaveLength(1));
      expect(patches(calls)[0].body).toEqual({ hsk_focus_version: "old" });
      await vi.waitFor(() => expect(auth.user?.hsk_focus_version).toBe("old"));
    });

    it("leaves a matching HSK version alone", async () => {
      api.setToken("tok");
      useSettingsStore().hskVersion = "new";
      const calls = recordFetch({ ...ME, timezone: "Europe/Vienna", hsk_focus_version: "new" });
      await useAuthStore().hydrate();
      await new Promise((r) => setTimeout(r, 0));
      expect(patches(calls)).toHaveLength(0);
    });
  });
});
