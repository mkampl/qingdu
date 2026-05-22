/**
 * Thin typed wrapper around the FastAPI backend.
 *
 * - Single auth-token store that the auth Pinia store reads/writes.
 * - Throws `ApiError` on non-2xx so view code can `try/catch` once.
 * - Network/parse errors bubble up as plain `Error`s.
 */

import type {
  AnalysisResponse,
  HealthResponse,
  LoginResponse,
  MeResponse,
  MyInvitationsResponse,
  NotAuthedResponse,
  SavedTextSummary,
  TranslateResponse,
  VocabStatsResponse,
  VocabularyListSummary,
} from "./types";

const TOKEN_KEY = "qingdu.token.v2";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore — auth still works for the current tab via memory
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  // If true, don't attach the bearer token even if present.
  anonymous?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (!opts.anonymous) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text().catch(() => null);
    }
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `API ${response.status}`;
    throw new ApiError(response.status, detail, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- Public endpoints --------------------------------------------------------

export const health = () => request<HealthResponse>("/health", { anonymous: true });

export const analyze = (text: string, signal?: AbortSignal) =>
  request<AnalysisResponse>("/api/analyze", { body: { text }, signal });

export const translate = (text: string, signal?: AbortSignal) =>
  request<TranslateResponse>("/api/translate", { body: { text }, signal });

export const vocabularyStats = () =>
  request<VocabStatsResponse>("/api/vocabulary-stats", { anonymous: true });

export const tts = (text: string) =>
  fetch(`/api/tts/${encodeURIComponent(text)}`);

// --- Auth --------------------------------------------------------------------

export const login = (username: string, password: string) =>
  request<LoginResponse>("/api/auth/login", {
    body: { username, password },
    anonymous: true,
  });

export const me = () =>
  request<MeResponse | NotAuthedResponse>("/api/auth/me");

export const logout = () => request<{ message: string }>("/api/auth/logout");

export const changePassword = (old_password: string, new_password: string) =>
  request<{ message: string }>("/api/auth/change-password", {
    body: { old_password, new_password },
  });

export const signupWithInvite = (
  token: string,
  username: string,
  password: string,
) =>
  request<LoginResponse>("/api/auth/signup-with-invite", {
    body: { token, username, password },
    anonymous: true,
  });

// --- Invitations -------------------------------------------------------------

export const generateInvitation = () =>
  request<{ invite_url: string; expires_at: string; remaining_quota: number }>(
    "/api/invitations/generate",
    { method: "POST" },
  );

export const myInvitations = () =>
  request<MyInvitationsResponse>("/api/invitations/my-invitations");

// --- Saved texts -------------------------------------------------------------

export const listTexts = () => request<SavedTextSummary[]>("/api/texts");

export const saveText = (input: {
  title: string;
  content: string;
  analysis_data: AnalysisResponse;
  tags?: string[];
}) => request<{ id: number; message: string }>("/api/texts/save", { body: input });

export const updateText = (
  id: number,
  patch: Partial<{
    title: string;
    tags: string[];
    reading_progress: number;
    content: string;
    analysis_data: AnalysisResponse;
  }>,
) =>
  request<{ id: number; title: string; message: string }>(
    `/api/texts/${id}`,
    { method: "PATCH", body: patch },
  );

export const deleteText = (id: number) =>
  request<{ message: string }>(`/api/texts/${id}`, { method: "DELETE" });

// --- Vocab lists -------------------------------------------------------------

export const listVocabularyLists = () =>
  request<VocabularyListSummary[]>("/api/vocabulary-lists");

export const createVocabularyList = (input: {
  name: string;
  type?: string;
  sections?: unknown[];
}) =>
  request<{ id: number; message: string }>("/api/vocabulary-lists", {
    body: input,
  });
