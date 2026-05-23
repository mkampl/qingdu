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

export interface AnalysisResponse {
  words: WordInfo[];
  statistics: AnalysisStatistics;
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
}

export interface VocabularyListSummary {
  id: number;
  name: string;
  type: string;
  sections: VocabularySection[];
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
