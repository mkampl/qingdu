import { flushPromises, mount, RouterLinkStub, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useUserWordsStore } from "@/stores/userWords";

import SettingsModal from "./SettingsModal.vue";

// Native builds always show the Server fieldset, so the switcher is
// reachable without a build-time API base.
vi.mock("@/services/native", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/services/native")>()),
  isNative: () => true,
}));

async function mountOpen() {
  const w = mount(SettingsModal, {
    global: { stubs: { teleport: true, RouterLink: RouterLinkStub } },
  });
  useAppModalsStore().settingsOpen = true;
  await flushPromises();
  return w;
}

function button(w: VueWrapper, text: string) {
  const b = w.findAll("button").find((x) => x.text() === text);
  if (!b) throw new Error(`no button "${text}"`);
  return b;
}

function group(w: VueWrapper, legend: string) {
  const f = w.findAll("fieldset").find((x) => x.find("legend").text() === legend);
  if (!f) throw new Error(`no fieldset "${legend}"`);
  return f;
}

function signIn(extra: Record<string, unknown> = {}) {
  useAuthStore().user = { username: "a", daily_new_words: 0, ...extra } as never;
}

const token = {
  id: 7,
  name: "companion",
  token_prefix: "qd_abc",
  scopes: ["read:words"],
  created_at: "2026-10-01T00:00:00Z",
  last_used_at: null,
};

describe("SettingsModal actions", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.spyOn(api, "listApiTokens").mockResolvedValue({ tokens: [] } as never);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("creates, copies, dismisses and revokes an API token", async () => {
    signIn();
    const create = vi
      .spyOn(api, "createApiToken")
      .mockResolvedValue({ ...token, token: "qd_abc_secret" } as never);
    const revoke = vi.spyOn(api, "revokeApiToken").mockResolvedValue({ revoked: true } as never);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const w = await mountOpen();
    const tokens = group(w, "API tokens");
    expect(tokens.text()).toContain("No tokens yet.");
    expect(button(w, "Create token").attributes("disabled")).toBeDefined();

    await tokens.find('input[type="text"]').setValue("  companion  ");
    await tokens.find('input[value="write:words"]').setValue(true);
    vi.mocked(api.listApiTokens).mockResolvedValue({ tokens: [token] } as never);
    await button(w, "Create token").trigger("click");
    await flushPromises();

    expect(create).toHaveBeenCalledWith("companion", ["read:words", "write:words"]);
    expect(api.listApiTokens).toHaveBeenCalledTimes(2);
    expect(w.text()).toContain("qd_abc_secret");
    expect((tokens.find('input[type="text"]').element as HTMLInputElement).value).toBe("");

    await button(w, "Copy").trigger("click");
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith("qd_abc_secret");

    await button(w, "Done").trigger("click");
    expect(w.text()).not.toContain("qd_abc_secret");

    expect(w.text()).toContain("companion");
    await button(w, "Revoke").trigger("click");
    await flushPromises();
    expect(revoke).toHaveBeenCalledWith(7);
    expect(w.text()).toContain("No tokens yet.");
  });

  it("export buttons open the matching downloads", async () => {
    signIn();
    const open = vi.spyOn(api, "openDownload").mockResolvedValue(undefined);
    const w = await mountOpen();
    for (const name of ["everything.json", "words.csv", "words.apkg"]) {
      await button(w, name).trigger("click");
    }
    expect(open.mock.calls.map((c) => c[0])).toEqual([
      api.FULL_EXPORT_PATH,
      api.WORDS_CSV_PATH,
      api.WORDS_ANKI_PATH,
    ]);
  });

  it("tests a server URL and reports the result", async () => {
    const probe = vi
      .spyOn(api, "testServer")
      .mockResolvedValueOnce({ ok: true, vocabCount: 1234 })
      .mockResolvedValueOnce({ ok: false, message: "HTTP 502" });
    const w = await mountOpen();
    const server = group(w, "Server");
    expect(button(w, "Save & reload").attributes("disabled")).toBeDefined();

    await server.find('input[type="url"]').setValue("https://qd.example.org/");
    expect(button(w, "Save & reload").attributes("disabled")).toBeUndefined();
    await button(w, "Test").trigger("click");
    await flushPromises();
    expect(probe).toHaveBeenLastCalledWith("https://qd.example.org");
    expect(server.text()).toContain("Connected");

    await button(w, "Test").trigger("click");
    await flushPromises();
    expect(server.text()).toContain("Couldn't verify that URL — HTTP 502");

    // Back to the (empty) default clears the status and the input.
    await button(w, "Use default").trigger("click");
    expect((server.find('input[type="url"]').element as HTMLInputElement).value).toBe("");
    expect(server.text()).not.toContain("Couldn't verify");
  });

  it("saving a server stores it, signs out and closes", async () => {
    const setBase = vi.spyOn(api, "setApiBase");
    const setTok = vi.spyOn(api, "setToken");
    const w = await mountOpen();
    await group(w, "Server").find('input[type="url"]').setValue("https://qd.example.org/");
    await button(w, "Save & reload").trigger("click");
    expect(setBase).toHaveBeenCalledWith("https://qd.example.org");
    expect(setTok).toHaveBeenCalledWith(null);
    expect(useAppModalsStore().settingsOpen).toBe(false);
  });

  it("deletes the account only after the password is entered", async () => {
    signIn();
    const del = vi.spyOn(api, "deleteAccount").mockResolvedValue({ message: "" });
    const w = await mountOpen();
    await button(w, "Delete my account…").trigger("click");
    expect(button(w, "Yes, delete everything").attributes("disabled")).toBeDefined();

    // Cancel disarms and forgets the password.
    await group(w, "Delete account").find('input[type="password"]').setValue("pw");
    await button(w, "Cancel").trigger("click");
    await button(w, "Delete my account…").trigger("click");
    const pw = group(w, "Delete account").find('input[type="password"]');
    expect((pw.element as HTMLInputElement).value).toBe("");

    await pw.setValue("hunter2");
    await button(w, "Yes, delete everything").trigger("click");
    await flushPromises();
    expect(del).toHaveBeenCalledWith("hunter2");
    expect(useAppModalsStore().settingsOpen).toBe(false);
  });

  it("bulk-marks HSK levels after the confirm step", async () => {
    signIn();
    const imp = vi
      .spyOn(api, "importHskKnown")
      .mockResolvedValue({ inserted: 3, skipped: 1, total_eligible: 4 } as never);
    const hydrate = vi.spyOn(useUserWordsStore(), "hydrate").mockResolvedValue(undefined as never);
    const w = await mountOpen();
    await group(w, "Onboarding shortcuts").find("select").setValue("2");
    await button(w, "Mark as known").trigger("click");
    await button(w, "Confirm").trigger("click");
    await flushPromises();
    expect(imp).toHaveBeenCalledWith(2, useSettingsStore().hskVersion);
    expect(hydrate).toHaveBeenCalledWith(true);
    expect(w.text()).toContain("3 added");
    expect(w.findAll("button").some((b) => b.text() === "Mark as known")).toBe(true);
  });

  it("daily learning toggle and count save clamped targets", async () => {
    signIn();
    const auth = useAuthStore();
    const save = vi.spyOn(auth, "updateSettings").mockImplementation(async (p) => {
      auth.user = { ...auth.user!, ...p } as never;
    });
    const w = await mountOpen();
    const daily = group(w, "Daily learning");
    await daily.find('input[type="checkbox"]').setValue(true);
    expect(save).toHaveBeenLastCalledWith({ daily_new_words: 5 });
    await flushPromises();
    await daily.find('input[type="number"]').setValue("99");
    expect(save).toHaveBeenLastCalledWith({ daily_new_words: 30 });
  });

  it("device-local controls write the settings store", async () => {
    signIn({ hsk_focus_version: "new" });
    const settings = useSettingsStore();
    const sync = vi.spyOn(useAuthStore(), "syncHskVersion").mockResolvedValue(undefined);
    const w = await mountOpen();

    await w.find('input[type="radio"][value="dark"]').setValue();
    expect(settings.theme).toBe("dark");

    await group(w, "Daily reminder").find('input[type="checkbox"]').setValue(true);
    expect(settings.reminderEnabled).toBe(true);
    await flushPromises();
    await group(w, "Daily reminder").find('input[type="time"]').setValue("07:45");
    expect(settings.reminderTime).toBe("07:45");

    const haptics = settings.hapticsEnabled;
    await group(w, "Feedback").find('input[type="checkbox"]').setValue(!haptics);
    expect(settings.hapticsEnabled).toBe(!haptics);

    const grade = w.find('[aria-label="Auto-grade delay"]');
    await grade.findAll('input[type="radio"]')[2].setValue();
    expect(settings.autoGradeDelayMs).toBe(2000);

    await group(w, "HSK version").find('input[value="old"]').setValue();
    expect(settings.hskVersion).toBe("old");
    expect(sync).toHaveBeenCalled();
  });

  it("account-backed radios and timezone save to the account", async () => {
    signIn({ timezone: "UTC", review_retention: 0.95 });
    const save = vi.spyOn(useAuthStore(), "updateSettings").mockResolvedValue(undefined);
    const w = await mountOpen();
    await group(w, "Review challenge").find('input[value="strict"]').setValue();
    expect(save).toHaveBeenLastCalledWith({ review_retention: 0.97 });
    await group(w, "Review focus").find('input[value="writing"]').setValue();
    expect(save).toHaveBeenLastCalledWith({ review_focus: "writing" });
    await group(w, "Script").find('input[value="trad"]').setValue();
    expect(save).toHaveBeenLastCalledWith({ display_script: "trad" });
    const tz = group(w, "Timezone").find("select");
    const other = tz.findAll("option").map((o) => o.attributes("value")!).find((v) => v !== "UTC")!;
    await tz.setValue(other);
    expect(save).toHaveBeenLastCalledWith({ timezone: other });
  });
});
