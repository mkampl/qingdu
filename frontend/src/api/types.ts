// Hand-written types for the FastAPI backend's response shapes.
// Keep in sync with app/schemas.py + the route return-types in app/routers/.

export type HskLevel =
  | "new-1"
  | "new-2"
  | "new-3"
  | "new-4"
  | "new-5"
  | "new-6"
  | "new-7"
  | "new-8"
  | "new-9"
  | "old-1"
  | "old-2"
  | "old-3"
  | "old-4"
  | "old-5"
  | "old-6"
  | "unknown"
  | "Custom"
  | string;

export type TranslationSource =
  | "deepl"
  | "google"
  | "mymemory"
  | "glossary"
  | "package"
  | "hsk"
  | "hsk-chars"
  | "cache"
  | "linebreak";

export interface WordInfo {
  text: string;
  hsk_level?: HskLevel;
  level_new?: HskLevel | null;
  level_old?: HskLevel | null;
  pinyin?: string;
  meaning?: string;
  meanings?: string[];
  frequency?: number;
  is_hsk: boolean;
  translation_source?: TranslationSource;
  radical?: string;
  radical_pinyin?: string;
  /** Per-user state from /api/analyze when authenticated. Undefined = new. */
  user_state?: "learning" | "known" | "ignored";
  /** Phase #99 — name of the user's glossary list this word came from
   *  (translation_source === "glossary"). The popover surfaces it. */
  glossary_source?: string | null;
}

export interface AnalysisStatistics {
  total_characters: number;
  total_words: number;
  hsk_words_new: number;
  hsk_distribution_new: Record<string, number>;
  estimated_level_new: string;
  hsk_words_old: number;
  hsk_distribution_old: Record<string, number>;
  estimated_level_old: string;
  // Legacy aliases — point at the new-HSK numbers.
  hsk_words: number;
  hsk_distribution: Record<string, number>;
  estimated_level: string;
}

export interface GrammarPatternMeta {
  id: string;
  title: string;
  pinyin: string;
  hsk_level: number;
  explanation: string;
  example: string;
  example_translation: string;
}

export interface GrammarMatch {
  pattern_id: string;
  sentence_idx: number;
  /** Absolute index into AnalysisResponse.words for the first token. */
  start_word_idx: number;
  /** Absolute index into AnalysisResponse.words for the last token (inclusive). */
  end_word_idx: number;
  span_text: string;
}

export interface GrammarPayload {
  matches: GrammarMatch[];
  patterns: GrammarPatternMeta[];
}

export interface AnalysisResponse {
  words: WordInfo[];
  statistics: AnalysisStatistics;
  /** Optional — older saved analyses pre-Phase D won't have this. */
  grammar?: GrammarPayload;
  /** Phase #100 — sentence-level translations baked in by the package
   *  author. Keyed by the exact sentence text. Reader checks here BEFORE
   *  hitting /api/translate so curated translations always win and don't
   *  expire with the server's TTL cache. */
  sentence_translations?: Record<string, string>;
}

export interface TranslateResponse {
  translation: string;
  source: TranslationSource;
  cached: boolean;
}

export interface User {
  username: string;
  is_admin: boolean;
  must_change_password: boolean;
  /** Phase #96 — daily auto-enrol target for HSK words into the learning pool. */
  daily_new_words?: number;
  /** Phase #96 — which HSK list the auto-enrol walks ('new' or 'old'). */
  hsk_focus_version?: "new" | "old";
  /** Phase #96 follow-up — Simplified vs Traditional display across the app. */
  display_script?: "auto" | "simp" | "trad";
  /** Phase #117 — FSRS desired retention. 0.85-0.97 valid range. */
  review_retention?: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface MeResponse {
  authenticated: true;
  user: User;
}

export interface NotAuthedResponse {
  authenticated: false;
}

export interface VocabStatsResponse {
  loaded: boolean;
  count: number;
  by_level?: Record<string, number>;
}

export interface HealthResponse {
  status: "healthy";
  vocab_loaded: boolean;
  vocab_count: number;
}

export interface SavedTextSummary {
  id: number;
  title: string;
  content: string;
  date: string;
  analysisData: AnalysisResponse;
  tags: string | null;
  reading_progress: number;
  /** Unique CJK words you've marked known/ignored (Phase F1). */
  known_unique: number;
  /** Unique CJK words in the text. */
  total_unique: number;
  /** known_unique / total_unique. Null when total_unique === 0. */
  comprehension_score: number | null;
  /** Public share token if this text has been shared (Phase G3). */
  share_token: string | null;
  /** Phase #99 — per-text glossary picker selection. null = use all
   *  glossary-flagged lists, [] = none, [3,5] = only those. */
  glossary_list_ids: number[] | null;
}

export interface VocabularyListSummary {
  id: number;
  name: string;
  type: string;
  sections: VocabularySection[];
  /** Phase #99 — when true, this list's entries override HSK lookup during
   *  analysis. Toggled from the list's edit page. */
  apply_as_glossary?: boolean;
}

export interface VocabularySection {
  name: string;
  words: VocabularyWord[];
}

export interface VocabularyWord {
  hanzi: string;
  pinyin: string;
  meaning: string;
  level: HskLevel;
}

export interface InvitationSummary {
  id: number;
  token: string;
  full_token: string;
  status: "pending" | "claimed" | "expired";
  claimed_by: string | null;
  claimed_at: string | null;
  expires_at: string;
  created_at: string;
}

export interface MyInvitationsResponse {
  invitations: InvitationSummary[];
  quota: { total: number; used: number; remaining: number };
}

export interface GenerateInvitationResponse {
  id: number;
  token: string;
  invite_url: string;
  expires_at: string;
  remaining_quota: number;
}

export interface AdminUserSummary {
  id: number;
  username: string;
  is_admin: boolean;
  invite_quota: number;
  last_active: string;
  created_at: string;
}
