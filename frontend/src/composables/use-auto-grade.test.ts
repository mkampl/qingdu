import { ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAutoGrade } from "./use-auto-grade";

describe("useAutoGrade", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("fires the scheduled grade after the delay", () => {
    const fire = vi.fn();
    const a = useAutoGrade(1000, fire);
    a.schedule(3);
    expect(a.pending.value).toBe(3);
    vi.advanceTimersByTime(999);
    expect(fire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fire).toHaveBeenCalledExactlyOnceWith(3);
    expect(a.pending.value).toBeNull();
  });

  it("a new schedule replaces the old one; cancel stops it", () => {
    const fire = vi.fn();
    const a = useAutoGrade(1000, fire);
    a.schedule(4);
    a.schedule(2);
    vi.advanceTimersByTime(1000);
    expect(fire).toHaveBeenCalledExactlyOnceWith(2);
    a.schedule(1);
    a.cancel();
    expect(a.pending.value).toBeNull();
    vi.advanceTimersByTime(5000);
    expect(fire).toHaveBeenCalledTimes(1);
  });

  it("delay 0 never schedules, read at schedule time", () => {
    const fire = vi.fn();
    const delay = ref(0);
    const a = useAutoGrade(delay, fire);
    a.schedule(3);
    expect(a.pending.value).toBeNull();
    delay.value = 500;
    a.schedule(3);
    vi.advanceTimersByTime(500);
    expect(fire).toHaveBeenCalledOnce();
  });
});
