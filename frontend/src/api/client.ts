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

export const health = () =>
  request<HealthResponse>("/health", { anonymous: true });

export const analyze = (
  text: string,
  options: { glossary_list_ids?: number[] | null; signal?: AbortSignal } = {},
) =>
  request<AnalysisResponse>("/api/analyze", {
    body: {
      text,
      // Only include the field when the caller has an explicit choice;
      // omitting it tells the backend "use all glossary-flagged lists".
      ...(options.glossary_list_ids !== undefined
        ? { glossary_list_ids: options.glossary_list_ids }
        : {}),
    },
    signal: options.signal,
  });

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

export const me = () => request<MeResponse | NotAuthedResponse>("/api/auth/me");

export const logout = () => request<{ message: string }>("/api/auth/logout");

export const changePassword = (old_password: string, new_password: string) =>
  request<{ message: string }>("/api/auth/change-password", {
    body: { old_password, new_password },
  });

export interface UserSettingsPayload {
  daily_new_words?: number;
  hsk_focus_version?: "new" | "old";
  display_script?: "auto" | "simp" | "trad";
}

export const updateMySettings = (payload: UserSettingsPayload) =>
  request<{
    daily_new_words: number;
    hsk_focus_version: string;
    display_script: string;
  }>("/api/auth/me/settings", { method: "PATCH", body: payload });

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

export const adminCreateUser = (input: {
  username: string;
  password: string;
}) => request<{ message: string }>("/api/admin/users", { body: input });

export const adminDeleteUser = (id: number) =>
  request<{ message: string }>(`/api/admin/users/${id}`, { method: "DELETE" });

export const adminResetPassword = (id: number, newPassword: string) =>
  request<{ message: string }>(`/api/admin/users/${id}/reset-password`, {
    body: { new_password: newPassword },
  });

export const adminToggleAdmin = (id: number) =>
  request<{ message: string }>(`/api/admin/users/${id}/toggle-admin`, {
    method: "POST",
  });

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
  glossary_list_ids?: number[] | null;
}) =>
  request<{ id: number; message: string }>("/api/texts/save", { body: input });

export const updateText = (
  id: number,
  patch: Partial<{
    title: string;
    tags: string[];
    reading_progress: number;
    content: string;
    analysis_data: AnalysisResponse;
    glossary_list_ids: number[] | null;
  }>,
) =>
  request<{ id: number; title: string; message: string }>(`/api/texts/${id}`, {
    method: "PATCH",
    body: patch,
  });

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
  patch: { name?: string; sections?: unknown[]; apply_as_glossary?: boolean },
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
  request<PrepareExportResult>(`/api/vocabulary-lists/${id}/prepare-export`, {
    method: "POST",
  });

/**
 * Download a Blob with the JWT attached. Used for the .apkg + CSV exports;
 * the backend honours both Bearer header and `?token=` query, but the
 * header approach keeps the token out of server logs.
 */
async function downloadBlob(url: string): Promise<{
  blob: Blob;
  filename: string;
  stats?: string;
  rateLimited?: boolean;
}> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(url, { headers });
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = null;
    }
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

// --- Pre-analyzed package import (Phase #100) ------------------------------

export interface PackageImportResponse {
  title: string | null;
  byline: string | null;
  source: string | null;
  content: string;
  analysisData: AnalysisResponse;
  sentence_translations: Record<string, string>;
}

export interface PackageSampleSummary {
  name: string;
  title: string | null;
  source: string | null;
  byline: string | null;
  language_hint: string | null;
  char_count: number;
}

/**
 * Import a JSON body. `strict=false` skips the token-concatenation check
 * (useful during LLM prompt iteration).
 */
export const importPackageBody = (payload: unknown, strict = true) =>
  request<PackageImportResponse>(
    `/api/import/package?strict=${strict ? "true" : "false"}`,
    { body: payload },
  );

export async function importPackageFile(
  file: File,
  strict = true,
): Promise<PackageImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(
    `/api/import/package/file?strict=${strict ? "true" : "false"}`,
    { method: "POST", headers, body: form },
  );
  if (!r.ok) {
    let detail: unknown = null;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text().catch(() => null);
    }
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `API ${r.status}`;
    throw new ApiError(r.status, detail, message);
  }
  return (await r.json()) as PackageImportResponse;
}

export const listPackageSamples = () =>
  request<{ samples: PackageSampleSummary[] }>("/api/import/package/samples", {
    anonymous: true,
  });

export const getPackageSample = (name: string) =>
  request<unknown>(`/api/import/package/samples/${encodeURIComponent(name)}`, {
    anonymous: true,
  });

export const packageSchemaUrl = () => "/api/import/package/schema.json";

export async function extractFile(file: File): Promise<ExtractedArticle> {
  const form = new FormData();
  form.append("file", file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch("/api/extract/file", {
    method: "POST",
    headers,
    body: form,
  });
  if (!r.ok) {
    let detail: unknown = null;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text().catch(() => null);
    }
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `API ${r.status}`;
    throw new ApiError(r.status, detail, message);
  }
  return (await r.json()) as ExtractedArticle;
}

// --- User word state (Phase A) ---------------------------------------------

export type UserWordState = "learning" | "known" | "ignored";

export interface WordStatesResponse {
  states: Record<string, UserWordState>;
}

export interface WordStatsResponse {
  learning: number;
  known: number;
  ignored: number;
  /** Phase F2 — current daily streak (consecutive days with activity). */
  streak: number;
}

export const listUserWordStates = () =>
  request<WordStatesResponse>("/api/words/state");

export const setUserWordState = (
  word: string,
  state: UserWordState,
  source_text_id?: number | null,
) =>
  request<{ word: string; state: UserWordState }>("/api/words/state", {
    body: { word, state, source_text_id: source_text_id ?? null },
  });

export const clearUserWordState = (word: string) =>
  request<{ word: string; state: "new" }>(
    `/api/words/state?word=${encodeURIComponent(word)}`,
    { method: "DELETE" },
  );

export const bulkMarkKnown = (
  words: string[],
  source_text_id?: number | null,
) =>
  request<{ updated: number; total: number }>("/api/words/bulk-mark-known", {
    body: { words, source_text_id: source_text_id ?? null },
  });

export const importHskKnown = (
  up_to_level: number,
  hsk_version: "new" | "old" = "new",
) =>
  request<{ inserted: number; skipped: number; total_eligible: number }>(
    "/api/words/import-hsk",
    { body: { up_to_level, hsk_version } },
  );

// --- Sharing + export (Phase G3 / G4) -------------------------------------

export interface PublicSharedText {
  title: string | null;
  content: string;
  analysisData: AnalysisResponse | null;
  created_at: string;
}

export const enableShare = (textId: number) =>
  request<{ token: string }>(`/api/texts/${textId}/share`, { method: "POST" });

export const disableShare = (textId: number) =>
  request<{ message: string }>(`/api/texts/${textId}/share`, {
    method: "DELETE",
  });

export const fetchSharedText = (token: string) =>
  request<PublicSharedText>(`/api/share/${encodeURIComponent(token)}`, {
    anonymous: true,
  });

/**
 * CSV / Anki downloads — surfaced via direct link with the token in a
 * query string (require_auth_flexible accepts ?token=…).
 */
export function wordsCsvUrl(): string {
  const token = getToken();
  return token
    ? `/api/words/export.csv?token=${encodeURIComponent(token)}`
    : "/api/words/export.csv";
}

export function wordsAnkiUrl(): string {
  const token = getToken();
  return token
    ? `/api/words/export.apkg?token=${encodeURIComponent(token)}`
    : "/api/words/export.apkg";
}

export const getWordStats = () =>
  request<WordStatsResponse>("/api/words/stats");

// --- Review (Phase B) ------------------------------------------------------

export type ReviewMode = "recognition" | "dictation" | "writing" | "cloze";
export type ReviewGrade = 1 | 2 | 3 | 4;

export interface ReviewCard {
  word: string;
  pinyin: string;
  meaning: string;
  meanings: string[];
  hsk_level: string | null;
  stability: number | null;
  difficulty: number | null;
  due_at: string | null;
}

export interface ReviewQueueResponse {
  mode: ReviewMode;
  cards: ReviewCard[];
}

export interface ReviewStatsResponse {
  due_now: number;
  due_today: number;
  learning: number;
  reviewed_today: number;
  /** Phase #96 — auto-enrolled HSK words since UTC midnight. */
  new_today: number;
  /** Phase #96 — user's daily target (mirror of User.daily_new_words). */
  daily_target: number;
}

export const getReviewQueue = (mode: ReviewMode = "recognition", limit = 20) =>
  request<ReviewQueueResponse>(`/api/review/queue?mode=${mode}&limit=${limit}`);

export const gradeReviewCard = (
  word: string,
  grade: ReviewGrade,
  mode: ReviewMode = "recognition",
) =>
  request<{
    word: string;
    due_at: string | null;
    stability: number | null;
    difficulty: number | null;
  }>("/api/review/grade", { body: { word, grade, mode } });

export const getReviewStats = () =>
  request<ReviewStatsResponse>("/api/review/stats");

// --- Activity stats (Phase F3) --------------------------------------------

export interface WeeklyActivityDay {
  date: string; // ISO YYYY-MM-DD
  reviews: number;
  marked_known: number;
}

export const getWeeklyActivity = () =>
  request<{ days: WeeklyActivityDay[] }>("/api/stats/weekly");

// --- Script conversion (Phase E1) ------------------------------------------

export type ConvertDirection = "s2t" | "t2s";

export const convertScript = (text: string, direction: ConvertDirection) =>
  request<{ converted: string; direction: ConvertDirection }>("/api/convert", {
    body: { text, direction },
    anonymous: true,
  });

export const detectScript = (text: string) =>
  request<{
    script: "simplified" | "traditional" | "unknown";
    confidence: number;
  }>("/api/convert/detect", { body: { text }, anonymous: true });
