/**
 * A view's fetch: not started, running, loaded or failed. `Ok` is what the
 * loaded state carries (`{ users: AdminUserSummary[] }`); `Extra` adds a
 * view's own states (`{ status: "notfound" }`).
 */
export type LoadState<Ok extends object, Extra extends { status: string } = never> =
  | { status: "idle" }
  | { status: "loading" }
  | ({ status: "ok" } & Ok)
  | { status: "error"; message: string }
  | Extra;
