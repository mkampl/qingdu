import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import { useTtsPlayer } from "@/composables/use-tts-player";

let player!: ReturnType<typeof useTtsPlayer>;
const Host = defineComponent({
  setup() {
    player = useTtsPlayer();
    return () => h("div");
  },
});

const pause = vi.fn();
const playSpy = vi.fn(async () => {});

describe("useTtsPlayer", () => {
  beforeEach(() => {
    pause.mockClear();
    playSpy.mockClear();
    let n = 0;
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:${++n}`);
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(pause);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playSpy);
  });
  afterEach(() => vi.restoreAllMocks());

  it("plays a clip and is loading until playback starts", async () => {
    const w = mount(Host);
    let resolve!: (r: Response) => void;
    const done = player.play(() => new Promise((r) => (resolve = r)));
    expect(player.loading.value).toBe(true);
    resolve(new Response("x"));
    await done;
    expect(playSpy).toHaveBeenCalledTimes(1);
    expect(player.loading.value).toBe(false);
    w.unmount();
  });

  it("stops the playing clip and revokes its URL on unmount", async () => {
    const w = mount(Host);
    await player.play(async () => new Response("x"));
    w.unmount();
    expect(pause).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
  });

  it("stops the previous clip when a new one plays", async () => {
    const w = mount(Host);
    await player.play(async () => new Response("a"));
    await player.play(async () => new Response("b"));
    expect(pause).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    expect(URL.revokeObjectURL).not.toHaveBeenCalledWith("blob:2");
    w.unmount();
  });

  it("revokes the URL when the clip ends", async () => {
    const w = mount(Host);
    let clip: HTMLMediaElement | null = null;
    playSpy.mockImplementationOnce(async function (this: HTMLMediaElement) {
      clip = this;
    } as never);
    await player.play(async () => new Response("x"));
    clip!.dispatchEvent(new Event("ended"));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    w.unmount();
    expect(pause).not.toHaveBeenCalled();
  });

  it("drops a fetch that resolves after cancel", async () => {
    const w = mount(Host);
    let resolve!: (r: Response) => void;
    const done = player.play(() => new Promise((r) => (resolve = r)));
    player.cancel();
    expect(player.loading.value).toBe(false);
    resolve(new Response("x"));
    await done;
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(playSpy).not.toHaveBeenCalled();
    w.unmount();
  });

  it("swallows a failed request", async () => {
    const w = mount(Host);
    await player.play(async () => new Response("", { status: 500 }));
    await flushPromises();
    expect(playSpy).not.toHaveBeenCalled();
    expect(player.loading.value).toBe(false);
    w.unmount();
  });
  it("drops an older fetch that resolves after a newer play", async () => {
    const w = mount(Host);
    let first!: (r: Response) => void;
    let second!: (r: Response) => void;
    const a = player.play(() => new Promise((r) => (first = r)));
    const b = player.play(() => new Promise((r) => (second = r)));
    first(new Response("a"));
    await a;
    expect(playSpy).not.toHaveBeenCalled();
    expect(player.loading.value).toBe(true);
    second(new Response("b"));
    await b;
    expect(playSpy).toHaveBeenCalledTimes(1);
    expect(player.loading.value).toBe(false);
    w.unmount();
  });

  it("resets loading when the fetch rejects or playback is blocked", async () => {
    const w = mount(Host);
    await expect(
      player.play(() => Promise.reject(new Error("offline"))),
    ).resolves.toBeUndefined();
    expect(player.loading.value).toBe(false);
    playSpy.mockImplementationOnce(() =>
      Promise.reject(new DOMException("blocked", "NotAllowedError")),
    );
    await expect(player.play(async () => new Response("x"))).resolves.toBeUndefined();
    expect(player.loading.value).toBe(false);
    // The blocked clip is still stopped and revoked by the next play.
    await player.play(async () => new Response("y"));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    w.unmount();
  });
});
