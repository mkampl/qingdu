import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./client";

function respond(status: number, body: unknown) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

describe("request() 401 handling", () => {
  const onUnauthorized = vi.fn();

  beforeEach(() => {
    api.setToken("tok");
    api.setUnauthorizedHandler(onUnauthorized);
  });
  afterEach(() => {
    api.setUnauthorizedHandler(null);
    api.setToken(null);
    onUnauthorized.mockReset();
    vi.unstubAllGlobals();
  });

  it("does not end the session on a wrong old password", async () => {
    vi.stubGlobal("fetch", respond(403, { detail: "Invalid old password" }));
    await expect(api.changePassword("wrong", "new-password")).rejects.toMatchObject({
      status: 403,
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
    expect(api.getToken()).toBe("tok");
  });

  it("ignores a 401 from credential re-checks (older servers)", async () => {
    vi.stubGlobal("fetch", respond(401, { detail: "Invalid old password" }));
    await expect(api.changePassword("wrong", "new-password")).rejects.toThrow();
    vi.stubGlobal("fetch", respond(401, { detail: "Password is incorrect" }));
    await expect(api.deleteAccount("wrong")).rejects.toThrow();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("treats a 401 from a normal endpoint as session death", async () => {
    vi.stubGlobal("fetch", respond(401, { detail: "Not authenticated" }));
    await expect(api.me()).rejects.toThrow();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});
