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
  SavedText,
  SavedTextSummary,
  TranslateResponse,
  VocabStatsResponse,
  VocabularyListSummary,
  WordGloss,
  WordInfo,
  WordReading,
} from "./types";

const TOKEN_KEY = "qingdu.token.v2";
const API_BASE_KEY = "qingdu.api_base.v1";

/**
 * Base URL for every API call. Resolved on every request so a runtime
 * change in Settings → Server propagates without reload.
 *
 * Resolution order:
 *  1. `localStorage["qingdu.api_base.v1"]` — runtime override the user
 *     set in Settings or via the first-launch onboarding modal. Lets
 *     self-hosters point an F-Droid build at their own server without
 *     a rebuild.
 *  2. `VITE_API_BASE_URL` build-time env — what the Capacitor wrapper
 *     bakes in (defaults to https://qingdu.itvoodoo.at for the maintainer
 *     build; an F-Droid build leaves this empty so the first launch
 *     forces the user to choose).
 *  3. Empty string — web build at the same origin; relative URLs work.
 */
const BUILD_TIME_API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? ""
).replace(/\/$/, "");

export function getApiBase(): string {
  try {
    const stored = localStorage.getItem(API_BASE_KEY);
    if (stored !== null) return stored.replace(/\/$/, "");
  } catch {
    /* localStorage unavailable — fall through */
  }
  return BUILD_TIME_API_BASE;
}

/** Build-time default, exposed so the Settings modal can show 'currently
 *  using the default URL' without a separate flag. */
export function getDefaultApiBase(): string {
  return BUILD_TIME_API_BASE;
}

/** Set or clear the runtime override. Pass `null` to revert to the
 *  build-time default. */
export function setApiBase(url: string | null) {
  try {
    if (url === null || url === "") {
      localStorage.removeItem(API_BASE_KEY);
    } else {
      localStorage.setItem(API_BASE_KEY, url.replace(/\/$/, ""));
    }
  } catch {
    /* ignore — the override is best-effort */
  }
}

/** Prepend the configured base URL to an API path. Exported so direct
 *  `fetch()` calls outside `request()` (file uploads, audio blobs) can
 *  share the same logic. */
export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path; // already absolute
  return getApiBase() + path;
}

/**
 * Verify that `baseUrl` is actually a Qingdu backend, not just any web
 * server. Hits /health (NOT /api/health — the SPA catch-all answers that
 * with 200 + index.html, which made "Connect" false-positive against any
 * website) and requires the JSON shape. Shared by the first-launch
 * ServerPicker and the Settings server switcher so the two can't disagree.
 */
export async function testServer(
  baseUrl: string,
): Promise<{ ok: true; vocabCount: number } | { ok: false; message: string }> {
  const target = baseUrl.trim().replace(/\/$/, "");
  if (!target) return { ok: false, message: "Enter a URL like https://qingdu.example.com" };
  try {
    const r = await fetch(`${target}/health`, { method: "GET" });
    if (!r.ok) return { ok: false, message: `HTTP ${r.status}` };
    const body = (await r.json()) as { vocab_count?: number };
    if (typeof body.vocab_count !== "number") {
      return { ok: false, message: "That server doesn't look like a Qingdu backend." };
    }
    return { ok: true, vocabCount: body.vocab_count };
  } catch (e) {
    return {
      ok: false,
      message: e instanceof Error ? e.message : "Couldn't reach that URL",
    };
  }
}

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

// Fired when an authenticated request comes back 401 — the token expired
// or was revoked server-side. The auth store registers a handler that
// clears the session and reopens the login modal; without it, a mid-session
// expiry surfaced as a trickle of raw "Not authenticated" toasts while
// optimistic UI kept accepting edits that rolled back one by one.
let unauthorizedHandler: (() => void) | null = null;

// A 401 from these means "wrong credentials", never "session died": login /
// register take a password, and the re-check endpoints (change password,
// delete account) answer 403 for a wrong one — listed anyway so an older
// server that still sends 401 can't log the user out over a typo.
function isCredentialCheck(path: string, method: string): boolean {
  if (path.startsWith("/api/auth/login") || path.startsWith("/api/auth/register")) return true;
  if (path.startsWith("/api/auth/change-password")) return true;
  return path === "/api/auth/me" && method === "DELETE";
}

export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn;
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

  const method = opts.method ?? (opts.body !== undefined ? "POST" : "GET");
  const response = await fetch(apiUrl(path), {
    method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (!response.ok) {
    if (
      response.status === 401 &&
      !opts.anonymous &&
      getToken() &&
      !isCredentialCheck(path, method)
    ) {
      unauthorizedHandler?.();
    }
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

export interface ImpressumInfo {
  name: string;
  street: string;
  zip: string;
  city: string;
  country: string | null;
  email: string;
  phone: string | null;
  extra: string | null;
}

export interface LegalConfig {
  // null when the server operator hasn't filled in the required
  // IMPRESSUM_* env vars — the frontend must not show the page/link then.
  impressum: ImpressumInfo | null;
  privacy_enabled: boolean;
}

export const getLegalConfig = () =>
  request<LegalConfig>("/api/legal", { anonymous: true });

export interface HskBrowseItem {
  hanzi: string;
  pinyin: string | null;
  meaning: string | null;
  meanings: string[];
  meaning_tags?: string[];
  readings?: WordReading[] | null;
  level_new: string | null;
  level_old: string | null;
  frequency: number | null;
  user_state: "learning" | "known" | "ignored" | null;
}

export interface HskBrowseResponse {
  items: HskBrowseItem[];
  total: number;
  offset: number;
  limit: number;
  /** How the level/search result splits across the caller's word states. */
  state_counts?: { new: number; learning: number; known: number; ignored: number };
}

export const browseHsk = (params: {
  level?: string;
  q?: string;
  /** Comma list of new / learning / known / ignored. */
  state?: string;
  offset?: number;
  limit?: number;
}) => {
  const search = new URLSearchParams();
  if (params.level) search.set("level", params.level);
  if (params.q) search.set("q", params.q);
  if (params.state) search.set("state", params.state);
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return request<HskBrowseResponse>(`/api/vocab/hsk${suffix}`);
};

/** Word-level TTS (short text in the URL path). */
export const tts = (text: string) =>
  fetch(apiUrl(`/api/tts/${encodeURIComponent(text)}`));

/** Sentence TTS — body-based, so long sentences don't hit URL limits. */
export const ttsSentence = (text: string) =>
  fetch(apiUrl("/api/tts/sentence"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

// --- Auth --------------------------------------------------------------------

export const login = (username: string, password: string) =>
  request<LoginResponse>("/api/auth/login", {
    body: { username, password },
    anonymous: true,
  });

export const me = () => request<MeResponse | NotAuthedResponse>("/api/auth/me");

export const logout = () => request<{ message: string }>("/api/auth/logout");

export const changePassword = (old_password: string, new_password: string) =>
  // access_token: the change revokes every existing session token, so the
  // server returns a fresh one for the caller (absent on older servers).
  request<{ message: string; access_token?: string }>("/api/auth/change-password", {
    body: { old_password, new_password },
  });

export interface UserSettingsPayload {
  daily_new_words?: number;
  hsk_focus_version?: "new" | "old";
  display_script?: "auto" | "simp" | "trad";
  review_retention?: number;
  review_window?: "now" | "today" | "tomorrow";
  review_focus?: ReviewFocus;
  timezone?: string;
}

/** What the mixed review trains between intro and produce. */
export type ReviewFocus = "both" | "reading" | "writing";

export const updateMySettings = (payload: UserSettingsPayload) =>
  request<{
    daily_new_words: number;
    hsk_focus_version: string;
    display_script: string;
    review_retention: number;
    review_window: string;
    review_focus?: string;
    timezone?: string | null;
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

// --- Open registration (Phase 2.9) -------------------------------------------

export interface RegistrationStatus {
  open: boolean;
  captcha: boolean;
}

export const getRegistrationStatus = () =>
  request<RegistrationStatus>("/api/auth/registration-status", {
    anonymous: true,
  });

export interface Captcha {
  question: string;
  token: string;
}

export const getCaptcha = () =>
  request<Captcha>("/api/auth/captcha", { anonymous: true });

export const openRegister = (input: {
  username: string;
  password: string;
  captcha_token?: string;
  captcha_answer?: number | string;
}) =>
  request<{
    access_token: string;
    token_type: "bearer";
    user: { id: number; username: string; is_admin: boolean };
  }>("/api/auth/register", { body: input, anonymous: true });

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

// Phase 2.7 — open-registration + lifecycle settings (admin-only).
export interface RegistrationSettings {
  "registration.open": boolean;
  "registration.per_ip_24h": number;
  "registration.daily_cap": number;
  "registration.captcha": boolean;
  "lifecycle.soft_delete_days": number;
  "lifecycle.hard_delete_days": number;
}

export const adminGetRegistrationSettings = () =>
  request<RegistrationSettings>("/api/admin/registration-settings");

export const adminPatchRegistrationSettings = (
  patch: Partial<{
    registration_open: boolean;
    registration_per_ip_24h: number;
    registration_daily_cap: number;
    registration_captcha: boolean;
    lifecycle_soft_delete_days: number;
    lifecycle_hard_delete_days: number;
  }>,
) =>
  request<RegistrationSettings>("/api/admin/registration-settings", {
    method: "PATCH",
    body: patch,
  });

export const adminRunLifecycleNow = () =>
  request<{ soft_marked: number; hard_deleted: number; attempts_pruned: number }>(
    "/api/admin/lifecycle/run-now",
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

export const getText = (id: number) => request<SavedText>(`/api/texts/${id}`);

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

export const getVocabularyList = (id: number) =>
  request<VocabularyListSummary>(`/api/vocabulary-lists/${id}`);

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

/** Take a list's words (or one section's) into review. */
export const learnVocabularyList = (id: number, sectionName: string | null = null) =>
  request<{ added: string[]; already_tracked: number; skipped: string[] }>(
    `/api/vocabulary-lists/${id}/learn`,
    { method: "POST", body: { section_name: sectionName } },
  );

export const addWordToList = (
  id: number,
  input: { section_name: string; hanzi: string; meaning: string },
) =>
  // A word already in the list (any section) is a 409 whose detail names
  // the section.
  request<{ message: string; added: boolean; pinyin?: string }>(
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
  const response = await fetch(apiUrl(url), { headers });
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

// --- Watch & read prototype (spike, not a shipped feature yet) -------------

export interface YoutubeSegment {
  start: number;
  end: number;
  text: string;
  words: WordInfo[];
}

export interface YoutubeReadResponse {
  video_id: string;
  is_generated: boolean;
  segments: YoutubeSegment[];
}

export const readYoutube = (url: string) =>
  request<YoutubeReadResponse>("/api/media/youtube", { body: { url } });

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
  // apiUrl() is load-bearing: a relative URL resolves against the Capacitor
  // WebView origin (bundled assets) on native builds and ignores a custom
  // server override on web.
  const r = await fetch(
    apiUrl(`/api/import/package/file?strict=${strict ? "true" : "false"}`),
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

export const packageSchemaUrl = () => apiUrl("/api/import/package/schema.json");

// ----- Library --------------------------------------------------------------

export interface LibraryManifestItem {
  slug: string;
  title: string;
  hsk_level: number;
  topic: string;
  grammar_pattern: string | null;
  char_count: number;
  total_unique_words: number;
  has_quiz: boolean;
}

/** How readable a text is for the user (share of running words known). */
export interface TextReadability {
  known_pct: number;
  with_progress_pct: number;
  /** Missing words, most frequent first, still needed to reach 95 %. */
  to_unlock: number;
  unlocked: boolean;
}

export interface LibraryForYouItem extends LibraryManifestItem, TextReadability {
  known_unique: number;
  new_words: number;
  /** Share of running words known (same as known_pct). */
  comprehension_score: number;
  preview: string;
}

export const getLibraryReadability = () =>
  request<{ threshold: number; items: Record<string, TextReadability> }>(
    "/api/library/readability",
  );

export interface LibraryEntry extends LibraryManifestItem {
  text: string;
  analyzed: unknown;
}

export const listLibrary = () =>
  request<{ items: LibraryManifestItem[] }>("/api/library", { anonymous: true });

export const libraryForYou = (params: { min?: number; max?: number; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.min !== undefined) q.set("min_score", String(params.min));
  if (params.max !== undefined) q.set("max_score", String(params.max));
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  const suffix = q.toString() ? `?${q}` : "";
  return request<{ items: LibraryForYouItem[]; reason?: string }>(
    `/api/library/for-you${suffix}`,
  );
};

export const getLibraryEntry = (slug: string) =>
  request<LibraryEntry>(`/api/library/${encodeURIComponent(slug)}`, {
    anonymous: true,
  });

export interface LibraryProgressEntry {
  status: "read" | "quiz";
  score: number | null;
  completed_at: string | null;
}

export const getLibraryProgress = () =>
  request<{ items: Record<string, LibraryProgressEntry> }>("/api/library/progress");

export const markLibraryRead = (slug: string) =>
  request<LibraryProgressEntry>(`/api/library/${encodeURIComponent(slug)}/read`, {
    method: "POST",
  });

export const unmarkLibraryRead = (slug: string) =>
  request<{ status: null }>(`/api/library/${encodeURIComponent(slug)}/read`, {
    method: "DELETE",
  });

export interface LibraryQuizQuestion {
  prompt: string;
  options: string[];
}

export const getLibraryQuiz = (slug: string) =>
  request<{ questions: LibraryQuizQuestion[] }>(`/api/library/${encodeURIComponent(slug)}/quiz`);

export const submitLibraryQuiz = (slug: string, answers: number[]) =>
  request<{ results: boolean[]; all_correct: boolean; progress: LibraryProgressEntry | null }>(
    `/api/library/${encodeURIComponent(slug)}/quiz`,
    { method: "POST", body: { answers } },
  );

// ----- Readability ("make this text readable") ------------------------------

export interface ReadabilityMissingWord {
  word: string;
  /** Occurrences in the text. */
  count: number;
  pinyin: string;
  meaning: string;
  hsk_level: number | null;
}

export interface ReadabilityResponse {
  /** Share of running words that makes a text readable (0.95). */
  threshold: number;
  total: number;
  unique: number;
  known: number;
  in_progress: number;
  known_pct: number;
  /** Known plus words in review that are not learned yet. */
  with_progress_pct: number;
  /** Missing words (most frequent first) still to learn to reach the threshold. */
  to_unlock: number;
  unlocked: boolean;
  missing_count: number;
  missing: ReadabilityMissingWord[];
  in_progress_words: string[];
  /** Words pre-learned for this text, and how many of them are learned by now. */
  prelearned: { total: number; learned: number } | null;
}

export const getReadability = (
  tokens: string[],
  extra: string[] = [],
  textKey: string | null = null,
) =>
  request<ReadabilityResponse>("/api/readability", {
    method: "POST",
    body: { tokens, extra, text_key: textKey },
  });

/** The text's own meaning for a word (package or glossary). */
export interface TextGloss {
  meaning: string;
  pinyin?: string | null;
  source: "package" | "glossary";
  tag?: string | null;
}

export interface PrelearnRequest {
  tokens: string[];
  extra: string[];
  words: string[];
  text_key: string;
  title?: string | null;
  source_text_id?: number | null;
  library_slug?: string | null;
  glosses?: Record<string, TextGloss>;
}

export const prelearnWords = (body: PrelearnRequest) =>
  request<ReadabilityResponse & { added: string[]; skipped: string[] }>(
    "/api/readability/prelearn",
    { method: "POST", body },
  );

// ----- Words queue ----------------------------------------------------------

export interface WordsQueueItem {
  word: string;
  state: "learning" | "known" | "ignored";
  pinyin: string | null;
  meaning: string | null;
  hsk_level: number | null;
  seen_count: number | null;
  ease: number | null;
  stability: number | null;
  difficulty: number | null;
  due_at: string | null;
  seconds_until_due: number | null;
  last_reviewed_at: string | null;
  created_at: string | null;
}

/** FSRS fields of a word row as the server left them after a change. */
export interface WordSchedule {
  due_at: string | null;
  seconds_until_due: number | null;
  stability: number | null;
  difficulty: number | null;
  last_reviewed_at: string | null;
}

export interface WordsQueueParams {
  state?: string;
  /** Due before the end of the day N days from now (0 = Review's "due today"). */
  dueWithinDays?: number | null;
  hskLevels?: string;
  /** Which HSK list the level filter, sort and badge use. */
  hskVersion?: "new" | "old";
  search?: string;
  sort?: "due" | "recent" | "hsk";
  limit?: number;
  offset?: number;
}

export interface WordsQueuePage {
  items: WordsQueueItem[];
  /** Rows matching every filter (all pages). */
  total: number;
  /** True when rows exist past offset + items.length. */
  has_more: boolean;
}

export const listWordsQueue = (params: WordsQueueParams = {}) => {
  const q = new URLSearchParams();
  if (params.state) q.set("state", params.state);
  if (params.dueWithinDays !== undefined && params.dueWithinDays !== null)
    q.set("due_within_days", String(params.dueWithinDays));
  if (params.hskLevels) q.set("hsk_levels", params.hskLevels);
  if (params.hskVersion) q.set("hsk_version", params.hskVersion);
  if (params.search) q.set("search", params.search);
  if (params.sort) q.set("sort", params.sort);
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  if (params.offset !== undefined) q.set("offset", String(params.offset));
  const suffix = q.toString() ? `?${q}` : "";
  return request<WordsQueuePage>(
    `/api/words/queue${suffix}`,
  );
};

export const snoozeWord = (word: string, days = 3) =>
  request<{ word: string; days: number } & WordSchedule>("/api/words/snooze", {
    body: { word, days },
  });

export const reviewNow = (word: string) =>
  request<{ word: string; due_at: string }>("/api/words/review-now", {
    body: { word },
  });

export async function extractFile(file: File): Promise<ExtractedArticle> {
  const form = new FormData();
  form.append("file", file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(apiUrl("/api/extract/file"), {
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
  /** Phase F3 — banked streak freezes (earned every 7-day milestone, cap 2). */
  streak_freezes: number;
}

export const listUserWordStates = () =>
  request<WordStatesResponse>("/api/words/state");

/**
 * Snapshot of a curated package gloss to ship alongside a state change.
 * Only set when the reader is acting on a word whose meaning came from a
 * pre-analyzed JSON package — for HSK / CC-CEDICT / compound / pypinyin
 * sources we omit these fields so the backend falls through to its
 * normal dictionary-lookup chain.
 */
export interface WordSnapshot {
  meaning?: string | null;
  pinyin?: string | null;
  translation_source?: string | null;
  /** Phase #120 — package name that owns this gloss. Backend uses it as
   *  the source_tag on the resulting UserWordGloss row so the UI can
   *  show "[Dao De Jing]" next to the meaning. */
  package_source?: string | null;
}

/** Where a word was met: its sentence and, for a bundled text, the slug.
 *  The server keeps the sentence for review cards. */
export interface WordContext {
  sentence?: string | null;
  librarySlug?: string | null;
}

export const setUserWordState = (
  word: string,
  state: UserWordState,
  source_text_id?: number | null,
  snapshot?: WordSnapshot | null,
  context?: WordContext | null,
) =>
  request<{ word: string; state: UserWordState } & WordSchedule>("/api/words/state", {
    body: {
      word,
      state,
      source_text_id: source_text_id ?? null,
      ...(context?.sentence
        ? { sentence: context.sentence, library_slug: context.librarySlug ?? null }
        : {}),
      ...(snapshot
        ? {
            meaning: snapshot.meaning ?? null,
            pinyin: snapshot.pinyin ?? null,
            translation_source: snapshot.translation_source ?? null,
          }
        : {}),
    },
  });

export const clearUserWordState = (word: string) =>
  request<{ word: string; state: "new" }>(
    `/api/words/state?word=${encodeURIComponent(word)}`,
    { method: "DELETE" },
  );

export const bulkMarkKnown = (
  words: string[],
  source_text_id?: number | null,
  snapshots?: Record<string, WordSnapshot> | null,
) =>
  request<{ updated: number; total: number; skipped?: string[] }>("/api/words/bulk-mark-known", {
    body: {
      words,
      source_text_id: source_text_id ?? null,
      ...(snapshots ? { snapshots } : {}),
    },
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
 * Open a download as a plain link (`<path>?ticket=…`). The ticket is good
 * for this one path for two minutes, so the session token never lands in a
 * URL. A plain link is what works everywhere: the browser saves the file,
 * and the Android app hands the link to the system browser.
 */
export async function openDownload(path: string): Promise<void> {
  const { ticket } = await request<{ ticket: string }>("/api/auth/download-ticket", {
    method: "POST",
    body: { path },
  });
  const anchor = document.createElement("a");
  anchor.href = apiUrl(`${path}?ticket=${encodeURIComponent(ticket)}`);
  anchor.download = "";
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

export const WORDS_CSV_PATH = "/api/words/export.csv";
export const WORDS_ANKI_PATH = "/api/words/export.apkg";
// Full-account JSON export — texts, word states + FSRS scheduling, vocab
// lists, glosses, review log, settings. The escape hatch the demo server's
// inactivity-deletion policy owes its users.
export const FULL_EXPORT_PATH = "/api/auth/export";

export const deleteAccount = (password: string) =>
  request<{ message: string }>("/api/auth/me", {
    method: "DELETE",
    body: { password },
  });

export const getWordStats = () =>
  request<WordStatsResponse>("/api/words/stats");

// --- API tokens (Phase #121 — external integrations) ------------------------

export const API_TOKEN_SCOPES = ["read:words", "write:words"] as const;
export type ApiTokenScope = (typeof API_TOKEN_SCOPES)[number];

export interface ApiTokenSummary {
  id: number;
  name: string;
  token_prefix: string;
  scopes: ApiTokenScope[];
  created_at: string;
  last_used_at: string | null;
}

export interface CreatedApiToken extends Omit<ApiTokenSummary, "last_used_at"> {
  // Only present in the create response — shown once, never retrievable again.
  token: string;
}

export const listApiTokens = () =>
  request<{ tokens: ApiTokenSummary[] }>("/api/tokens");

export const createApiToken = (name: string, scopes: ApiTokenScope[]) =>
  request<CreatedApiToken>("/api/tokens", { body: { name, scopes } });

export const revokeApiToken = (id: number) =>
  request<{ revoked: boolean }>(`/api/tokens/${id}`, { method: "DELETE" });

// --- Review (Phase B) ------------------------------------------------------

export type ReviewMode = "recognition" | "dictation" | "writing" | "cloze";
/** Phase 1.3b — the queue can also be fetched in "mixed", which is the
 *  default and returns cards with their server-assigned prompt_stage so
 *  the SPA can render intro/trace/produce per card. Advanced single-mode
 *  passes one of the four ReviewModes instead. */
export type QueueMode = ReviewMode | "mixed";
/** Phase 1.3b — server-picked prompt stage based on FSRS stability.
 *  Drives which review surface the SPA renders for the card. */
export type PromptStage = "intro" | "trace" | "produce" | "read";
export type ReviewGrade = 1 | 2 | 3 | 4;

export interface ReviewCard {
  word: string;
  pinyin: string;
  meaning: string;
  /** Every dictionary sense, full text. The headline's own sense is not
   *  necessarily first — list the rest with otherMeanings(). */
  meanings: string[];
  /** Register tags stripped off the dictionary headline. */
  meaning_tags?: string[];
  /** All readings of a polyphone, the one this card is graded on first. */
  readings?: WordReading[] | null;
  hsk_level: string | null;
  stability: number | null;
  difficulty: number | null;
  due_at: string | null;
  /** Phase #120 — every gloss this user has on the word, with
   *  provenance. Review card renders them as chips so the same
   *  character can carry CEDICT + multiple package meanings. */
  glosses?: WordGloss[];
  /** In a session focused on one text or list: that text's or list's own
   *  meaning, which the card leads with. */
  focus_gloss?: WordGloss | null;
  /** Cloze mode only — sentence with the target word replaced by "___". */
  cloze_template?: string;
  /** The word's sample sentence: the context it was marked in, else one
   *  from a saved or library text. Cloze blanks it; the other surfaces
   *  show it once the answer is out. */
  cloze_sentence?: string;
  /** Title of the text cloze_sentence came from; null when unknown
   *  (unsaved reading, older rows). */
  sentence_source?: string | null;
  /** Phase 1.3b — server-picked progressive prompt stage. */
  prompt_stage?: PromptStage;
  /** Phase 1.3b — does this row have a sample sentence (for cloze
   *  Advanced single-mode + future use)? */
  has_sample_sentence?: boolean;
}

export interface ReviewQueueResponse {
  mode: QueueMode;
  cards: ReviewCard[];
  /** Title of the text or list a focused session is about. */
  scope_title?: string | null;
}

/** A review session focused on the words of one text or one vocab list. */
export interface ReviewScope {
  textKey?: string;
  listId?: number;
}

export interface ReviewGradeResponse {
  word: string;
  due_at: string | null;
  stability: number | null;
  difficulty: number | null;
  /** Phase 1.3b — the card's new prompt stage given the updated
   *  stability after this grade. Informational. */
  prompt_stage: PromptStage;
}

export interface ReviewStatsResponse {
  due_now: number;
  due_today: number;
  /** What /api/review/queue would serve now under user.review_window. */
  due_in_window: number;
  learning: number;
  /** learning + known — every card that can come due. */
  in_rotation: number;
  reviewed_today: number;
  /** Phase #96 — auto-enrolled HSK words since UTC midnight. */
  new_today: number;
  /** Phase #96 — user's daily target (mirror of User.daily_new_words). */
  daily_target: number;
  /** Only when asked for a scope: its title and counts. */
  scope?: ReviewScopeInfo | null;
}

/** Counts of a focused session's words (one text or one list). */
export interface ReviewScopeInfo {
  title: string | null;
  /** Due under the review window: what Start serves. */
  due: number;
  /** Words in rotation. */
  total: number;
  due_now: number;
  due_today: number;
  /** Words that already count as known when reading. */
  learned: number;
}

function scopeQuery(scope: ReviewScope | null | undefined): string {
  if (scope?.textKey) return `&text_key=${encodeURIComponent(scope.textKey)}`;
  if (scope?.listId !== undefined) return `&list_id=${scope.listId}`;
  return "";
}

export const getReviewQueue = (
  mode: QueueMode = "recognition",
  limit = 20,
  scope: ReviewScope | null = null,
) =>
  request<ReviewQueueResponse>(
    `/api/review/queue?mode=${mode}&limit=${limit}${scopeQuery(scope)}`,
  );

export const gradeReviewCard = (
  word: string,
  grade: ReviewGrade,
  mode: ReviewMode = "recognition",
) =>
  request<ReviewGradeResponse>("/api/review/grade", {
    body: { word, grade, mode },
  });

export const getReviewStats = (scope: ReviewScope | null = null) =>
  request<ReviewStatsResponse>(
    `/api/review/stats${scope ? `?${scopeQuery(scope).slice(1)}` : ""}`,
  );

// Practice mode — fetch a single card by word without any queue side
// effects. The client cycles modes locally; no /grade call happens
// during practice, so FSRS / stats / streak stay untouched.
export const getPracticeCard = (word: string) =>
  request<{ card: ReviewCard }>(
    `/api/review/practice/${encodeURIComponent(word)}`,
  );

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
