import { getCurrentInstance, onBeforeUnmount, ref } from "vue";

/**
 * One TTS clip at a time for a component: `play(fetchAudio)` fetches the
 * audio, stops the clip before it and plays the new one from a blob URL.
 * The URL is revoked when the clip ends or is stopped. A fetch that
 * resolves after a newer `play()` or `cancel()` is dropped, so a stale
 * clip never plays over the current one. `loading` is true from the
 * request until playback starts (or fails). Called in a component's
 * setup, the clip stops when the component unmounts.
 *
 * Errors are swallowed: the text stays readable and the next click can
 * retry. Which endpoint to call (word or sentence) is up to the caller.
 */
export function useTtsPlayer() {
  const loading = ref(false);
  let audio: HTMLAudioElement | null = null;
  let url: string | null = null;
  let seq = 0;

  function stop() {
    if (audio) {
      try {
        audio.pause();
        audio.currentTime = 0;
      } catch {
        // the element may already be gone
      }
      audio = null;
    }
    if (url) {
      URL.revokeObjectURL(url);
      url = null;
    }
  }

  /** Stop the clip and drop a fetch still in flight. */
  function cancel() {
    seq += 1;
    stop();
    loading.value = false;
  }

  async function play(fetchAudio: () => Promise<Response>) {
    stop();
    const mine = ++seq;
    loading.value = true;
    try {
      const r = await fetchAudio();
      if (!r.ok) throw new Error("TTS failed");
      const blob = await r.blob();
      if (mine !== seq) return;
      const clipUrl = URL.createObjectURL(blob);
      const clip = new Audio(clipUrl);
      audio = clip;
      url = clipUrl;
      clip.addEventListener("ended", () => {
        if (audio !== clip) return;
        URL.revokeObjectURL(clipUrl);
        audio = null;
        url = null;
      });
      await clip.play();
    } catch {
      // no audio this time
    } finally {
      if (mine === seq) loading.value = false;
    }
  }

  if (getCurrentInstance()) onBeforeUnmount(cancel);

  return { loading, play, stop, cancel };
}
