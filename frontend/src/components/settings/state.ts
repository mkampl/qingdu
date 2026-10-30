import { computed, reactive, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError, getApiBase, getDefaultApiBase, setApiBase, setToken } from "@/api/client";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { isNative } from "@/services/native";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

// Local state of the Settings sections. Modal renders its body only while
// open, so the sections unmount on close; SettingsModal creates this state
// once and passes it down, so it survives closing and reopening the modal.

// --- Onboarding shortcut: bulk-mark HSK levels as known ---
// Two-step button: the first click shows a confirm row with an estimated
// count (roughCount); the real count comes back from the import.
export function useHskImport() {
  const settings = useSettingsStore();
  const auth = useAuthStore();
  const toasts = useToastStore();
  const userWords = useUserWordsStore();

  const importLevel = ref<number>(4);
  const importing = ref(false);
  const pendingConfirm = ref(false);
  const lastResult = ref<{
    inserted: number;
    skipped: number;
    total_eligible: number;
  } | null>(null);

  const importMaxLevel = computed(() => (settings.hskVersion === "new" ? 9 : 6));

  // Approximate new words per level, only for the "about N words" hint.
  function roughCount(level: number, version: "new" | "old"): number {
    if (version === "new") {
      return [0, 500, 770, 1000, 1100, 1500, 1500, 1600, 1700, 1800][level] ?? 0;
    }
    return [0, 150, 300, 600, 1200, 2500, 5000][level] ?? 0;
  }

  const roughTotal = computed(() => {
    let n = 0;
    for (let i = 1; i <= importLevel.value; i++) {
      n += roughCount(i, settings.hskVersion);
    }
    return n;
  });

  async function runImport() {
    if (!auth.isAuthed) {
      toasts.info("Sign in to import HSK words.");
      return;
    }
    importing.value = true;
    try {
      const r = await api.importHskKnown(importLevel.value, settings.hskVersion);
      lastResult.value = r;
      pendingConfirm.value = false;
      toasts.success(
        `Marked ${r.inserted.toLocaleString()} new word${r.inserted === 1 ? "" : "s"} as known.`,
      );
      // Refresh the store so the header counter ticks immediately.
      userWords.hydrate(true);
    } catch (e) {
      toasts.error(
        e instanceof ApiError ? e.message : "Couldn't import HSK words.",
      );
    } finally {
      importing.value = false;
    }
  }

  return reactive({
    importLevel,
    importing,
    pendingConfirm,
    lastResult,
    importMaxLevel,
    roughTotal,
    runImport,
  });
}
export type HskImport = ReturnType<typeof useHskImport>;

// --- Account deletion ---
// Two-step inline confirm + password re-entry; irreversible.
export function useAccountDeletion() {
  const modals = useAppModalsStore();
  const toasts = useToastStore();

  const deleteArmed = ref(false);
  const deletePassword = ref("");
  const deleteBusy = ref(false);

  async function confirmDeleteAccount() {
    if (!deletePassword.value) return;
    deleteBusy.value = true;
    try {
      await api.deleteAccount(deletePassword.value);
      setToken(null);
      toasts.success("Your account and all its data are gone. 再见!");
      modals.closeAll();
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      toasts.error(
        e instanceof ApiError ? e.message : "Couldn't delete the account.",
      );
    } finally {
      deleteBusy.value = false;
    }
  }

  return reactive({ deleteArmed, deletePassword, deleteBusy, confirmDeleteAccount });
}
export type AccountDeletion = ReturnType<typeof useAccountDeletion>;

// --- API tokens for external integrations ---
// Read/write access to word state for outside apps (e.g. a speaking
// companion's own whisper/LLM/TTS stack), scoped and revocable. Loaded
// lazily on first modal open rather than at import time, since most
// sessions never open Settings.
export function useApiTokens() {
  const modals = useAppModalsStore();
  const auth = useAuthStore();
  const toasts = useToastStore();

  const apiTokens = ref<api.ApiTokenSummary[]>([]);
  const apiTokensLoaded = ref(false);
  const newTokenName = ref("");
  const newTokenScopes = ref<api.ApiTokenScope[]>(["read:words"]);
  const creatingToken = ref(false);
  const revealedToken = ref<api.CreatedApiToken | null>(null);
  const revokingTokenId = ref<number | null>(null);

  async function loadApiTokens() {
    try {
      const { tokens } = await api.listApiTokens();
      apiTokens.value = tokens;
      apiTokensLoaded.value = true;
    } catch (e) {
      toasts.error(e instanceof ApiError ? e.message : "Couldn't load API tokens.");
    }
  }

  watch(
    () => modals.settingsOpen,
    (open) => {
      if (open && auth.isAuthed && !apiTokensLoaded.value) void loadApiTokens();
    },
  );

  async function createToken() {
    const name = newTokenName.value.trim();
    if (!name || newTokenScopes.value.length === 0) return;
    creatingToken.value = true;
    try {
      const created = await api.createApiToken(name, [...newTokenScopes.value]);
      revealedToken.value = created;
      newTokenName.value = "";
      await loadApiTokens();
    } catch (e) {
      toasts.error(e instanceof ApiError ? e.message : "Couldn't create the token.");
    } finally {
      creatingToken.value = false;
    }
  }

  async function revokeToken(id: number) {
    revokingTokenId.value = id;
    try {
      await api.revokeApiToken(id);
      apiTokens.value = apiTokens.value.filter((t) => t.id !== id);
      toasts.success("Token revoked.");
    } catch (e) {
      toasts.error(e instanceof ApiError ? e.message : "Couldn't revoke the token.");
    } finally {
      revokingTokenId.value = null;
    }
  }

  async function copyRevealedToken() {
    if (!revealedToken.value) return;
    try {
      await navigator.clipboard.writeText(revealedToken.value.token);
      toasts.success("Copied.");
    } catch {
      // Clipboard API can be unavailable (no HTTPS, no permission) — the
      // token stays selectable in the field either way, so this is a
      // soft failure.
    }
  }

  return reactive({
    apiTokens,
    apiTokensLoaded,
    newTokenName,
    newTokenScopes,
    creatingToken,
    revealedToken,
    revokingTokenId,
    createToken,
    revokeToken,
    copyRevealedToken,
  });
}
export type ApiTokens = ReturnType<typeof useApiTokens>;

// --- Server switcher ---
// Runtime override for the API base URL. "Test" probes whatever URL is in
// the field so a typo'd server doesn't strand the user.
export function useServerSwitcher() {
  const modals = useAppModalsStore();
  const toasts = useToastStore();

  const apiBaseDefault = getDefaultApiBase();
  // The Server section shows on web builds with a baked-in default and on
  // every native build. F-Droid builds ship an empty default (first-launch
  // ServerPicker), and that picker promises "switch later in Settings".
  const serverSectionVisible = apiBaseDefault !== "" || isNative();
  // On native-with-no-default there is no "default server" to name in the
  // copy; show the server currently in use instead.
  const apiBaseCurrent = getApiBase() || "(not set)";
  const apiBaseInput = ref(getApiBase());
  const apiBaseTesting = ref(false);
  const apiBaseStatus = ref<
    | { kind: "idle" }
    | { kind: "ok"; vocabCount: number }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const apiBaseChanged = computed(
    () => apiBaseInput.value.replace(/\/$/, "") !== getApiBase(),
  );
  const apiBaseIsDefault = computed(
    () => apiBaseInput.value.replace(/\/$/, "") === apiBaseDefault,
  );

  async function testApiBase() {
    const target = apiBaseInput.value.replace(/\/$/, "");
    if (!target) {
      apiBaseStatus.value = {
        kind: "error",
        message: "Enter a URL like https://qingdu.example.com",
      };
      return;
    }
    apiBaseTesting.value = true;
    apiBaseStatus.value = { kind: "idle" };
    // Shared probe with the first-launch ServerPicker (client.ts testServer)
    // so the two testers can't disagree about what a valid server is.
    const result = await api.testServer(target);
    apiBaseTesting.value = false;
    apiBaseStatus.value = result.ok
      ? { kind: "ok", vocabCount: result.vocabCount }
      : { kind: "error", message: `Couldn't verify that URL — ${result.message}` };
  }

  function saveApiBase() {
    const target = apiBaseInput.value.replace(/\/$/, "");
    // Empty input is interpreted as "reset to default" so the user can
    // wipe the override by clearing the field.
    setApiBase(target === apiBaseDefault || target === "" ? null : target);
    // The JWT is signed by the old server's SECRET_KEY and would fail on
    // the new one; clearing it makes the "sign in again" toast true.
    setToken(null);
    toasts.success(
      "Server updated. Sign in again on the new server.",
    );
    modals.closeAll();
    // Force a clean reload so every store hydrates against the new URL.
    setTimeout(() => window.location.reload(), 400);
  }

  function resetApiBase() {
    apiBaseInput.value = apiBaseDefault;
    apiBaseStatus.value = { kind: "idle" };
  }

  return reactive({
    serverSectionVisible,
    apiBaseCurrent,
    apiBaseInput,
    apiBaseTesting,
    apiBaseStatus,
    apiBaseChanged,
    apiBaseIsDefault,
    testApiBase,
    saveApiBase,
    resetApiBase,
  });
}
export type ServerSwitcher = ReturnType<typeof useServerSwitcher>;
