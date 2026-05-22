/**
 * Thin typed wrapper around the FastAPI backend.
 *
 * - Single auth-token store that the auth Pinia store reads/writes.
 * - Throws `ApiError` on non-2xx so view code can `try/catch` once.
 * - Network/parse errors bubble up as plain `Error`s.
 */

import type {
  AdminUserSummary,
  AnalysisResponse,
  GenerateInvitationResponse,
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
  request<GenerateInvitationResponse>("/api/invitations/generate", {
    method: "POST",
  });

export const myInvitations = () =>
  request<MyInvitationsResponse>("/api/invitations/my-invitations");

// --- Admin -------------------------------------------------------------------

export const adminListUsers = () =>
  request<AdminUserSummary[]>("/api/admin/users");

export const adminCreateUser = (input: { username: string; password: string }) =>
  request<{ message: string }>("/api/admin/users", { body: input });

export const adminDeleteUser = (id: number) =>
  request<{ message: string }>(`/api/admin/users/${id}`, { method: "DELETE" });

export const adminResetPassword = (id: number, newPassword: string) =>
  request<{ message: string }>(
    `/api/admin/users/${id}/reset-password`,
    { body: { new_password: newPassword } },
  );

export const adminToggleAdmin = (id: number) =>
  request<{ message: string }>(
    `/api/admin/users/${id}/toggle-admin`,
    { method: "POST" },
  );

export const adminUpdateInviteQuota = (id: number, quota: number) =>
  request<{
    message: string;
    user_id: number;
    username: string;
    invite_quota: number;
  }>(`/api/admin/users/${id}/invite-quota`, {
    method: "PATCH",
    body: { invite_quota: quota },
  });

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

export const updateVocabularyList = (
  id: number,
  patch: { name?: string; sections?: unknown[] },
) =>
  request<{ message: string }>(`/api/vocabulary-lists/${id}`, {
    method: "PUT",
    body: patch,
  });

export const deleteVocabularyList = (id: number) =>
  request<{ message: string }>(`/api/vocabulary-lists/${id}`, {
    method: "DELETE",
  });

export const addWordToList = (
  id: number,
  input: { section_name: string; hanzi: string; meaning: string },
) =>
  request<{ message: string; pinyin?: string }>(
    `/api/vocabulary-lists/${id}/words`,
    { body: input },
  );

export const updateWordInList = (
  id: number,
  input: {
    section_name: string;
    old_hanzi: string;
    word: { hanzi: string; meaning: string };
  },
) =>
  request<{ message: string; pinyin?: string }>(
    `/api/vocabulary-lists/${id}/words`,
    { method: "PUT", body: input },
  );

export const deleteWordFromList = (
  id: number,
  input: { section_name: string; hanzi: string },
) =>
  request<{ message: string }>(`/api/vocabulary-lists/${id}/words`, {
    method: "DELETE",
    body: input,
  });

export const addSectionToList = (id: number, name: string) =>
  request<{ message: string; name: string; total_sections: number }>(
    `/api/vocabulary-lists/${id}/sections`,
    { body: { name } },
  );

export const renameSection = (
  id: number,
  input: { old_name: string; new_name: string },
) =>
  request<{ message: string }>(`/api/vocabulary-lists/${id}/sections`, {
    method: "PUT",
    body: input,
  });

export const deleteSection = (id: number, name: string) =>
  request<{ message: string; word_count: number }>(
    `/api/vocabulary-lists/${id}/sections/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );

// --- Anki / audio export -----------------------------------------------------

export interface AudioStatus {
  total: number;
  cached: number;
  missing: number;
  estimated_time: string;
  ready: boolean;
}

export const checkAudioStatus = (id: number) =>
  request<AudioStatus>(`/api/vocabulary-lists/${id}/check-audio`);

export interface PrepareExportResult {
  total: number;
  cached: number;
  generated: number;
  failed: number;
  rate_limited: boolean;
  ready: boolean;
}

export const prepareExportAudio = (id: number) =>
  request<PrepareExportResult>(
    `/api/vocabulary-lists/${id}/prepare-export`,
    { method: "POST" },
  );

/**
 * Download a Blob with the JWT attached. Used for the .apkg + CSV exports;
 * the backend honours both Bearer header and `?token=` query, but the
 * header approach keeps the token out of server logs.
 */
async function downloadBlob(url: string): Promise<{ blob: Blob; filename: string; stats?: string; rateLimited?: boolean }> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    let detail: unknown = null;
    try { detail = await response.json(); } catch { detail = null; }
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `API ${response.status}`;
    throw new ApiError(response.status, detail, message);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename=(?:"([^"]+)"|([^;]+))/.exec(disposition);
  const filename = (match?.[1] ?? match?.[2] ?? "download").trim();
  return {
    blob: await response.blob(),
    filename,
    stats: response.headers.get("X-Export-Stats") ?? undefined,
    rateLimited: response.headers.get("X-Rate-Limited") === "true",
  };
}

export const exportVocabularyListAnki = (id: number) =>
  downloadBlob(`/api/vocabulary-lists/${id}/export-anki`);

export const exportVocabularyListCsv = (id: number) =>
  downloadBlob(`/api/vocabulary-lists/${id}/export`);

// --- Article extraction -----------------------------------------------------

export interface ExtractedArticle {
  url: string;
  title: string | null;
  byline: string | null;
  excerpt: string | null;
  content: string;
  char_count: number;
}

export const extractArticle = (url: string) =>
  request<ExtractedArticle>("/api/extract", { body: { url } });
