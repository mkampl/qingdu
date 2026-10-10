import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAudioPlayerStore } from "@/stores/audio-player";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Minimal HTMLAudioElement stand-in whose play() settles on demand. */
class FakeAudio {
  static plays: Array<ReturnType<typeof deferred<void>>> = [];
  src = "";
  paused = true;
  preload = "";
  playbackRate = 1;
  error = null;
  addEventListener() {}
  removeAttribute() {
    this.src = "";
  }
  load() {}
  pause() {
    this.paused = true;
  }
  play() {
    const d = deferred<void>();
    FakeAudio.plays.push(d);
    this.paused = false;
    return d.promise;
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("audio-player store", () => {
  let fetches: Array<ReturnType<typeof deferred<Response>>>;

  beforeEach(() => {
    setActivePinia(createPinia());
    FakeAudio.plays = [];
    fetches = [];
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        const d = deferred<Response>();
        fetches.push(d);
        return d.promise;
      }),
    );
    let n = 0;
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:fake/${++n}`);
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const ok = () => new Response(new Blob(["mp3"]), { status: 200 });

  it("pausing while the first sentence loads keeps it paused", async () => {
    const player = useAudioPlayerStore();
    player.setQueue([{ key: "a", text: "一" }]);
    const p = player.play();
    player.pause();
    fetches[0].resolve(ok());
    await p;
    expect(player.playing).toBe(false);
    expect(player.loading).toBe(false);
    expect(FakeAudio.plays).toHaveLength(0);
  });

  it("an interrupted play() does not surface a playback error", async () => {
    const player = useAudioPlayerStore();
    player.setQueue([
      { key: "a", text: "一" },
      { key: "b", text: "二" },
    ]);
    const first = player.play();
    fetches[0].resolve(ok());
    await tick();
    await tick();
    expect(FakeAudio.plays).toHaveLength(1);

    // Skip ahead before the first play() settles; the browser then rejects
    // the old play() with "interrupted by a new load request".
    const second = player.advance();
    await tick();
    fetches[1]?.resolve(ok());
    FakeAudio.plays[0].reject(
      new DOMException("interrupted by a new load request", "AbortError"),
    );
    await first;
    expect(player.error).toBeNull();
    await tick();
    FakeAudio.plays[1]?.resolve();
    await second;
    expect(player.error).toBeNull();
    expect(player.playing).toBe(true);
    expect(player.cursor).toBe(1);
  });
});
