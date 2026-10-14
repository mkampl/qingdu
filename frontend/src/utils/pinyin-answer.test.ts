import { describe, expect, it } from "vitest";

import { checkPinyin } from "@/utils/pinyin-answer";

describe("checkPinyin", () => {
  it("accepts tone marks with or without spaces", () => {
    expect(checkPinyin("gǎn mào", "gǎn mào")).toBe("exact");
    expect(checkPinyin("gǎnmào", "gǎn mào")).toBe("exact");
  });

  it("accepts tone numbers, v and u: for ü", () => {
    expect(checkPinyin("gan3mao4", "gǎn mào")).toBe("exact");
    expect(checkPinyin("gan3 mao4", "gǎn mào")).toBe("exact");
    expect(checkPinyin("lv4", "lǜ")).toBe("exact");
    expect(checkPinyin("lu:4", "lǜ")).toBe("exact");
  });

  it("lets neutral tones be left out or typed as 5", () => {
    expect(checkPinyin("ma1ma", "mā ma")).toBe("exact");
    expect(checkPinyin("ma1ma5", "mā ma")).toBe("exact");
  });

  it("tells missing tones apart from wrong ones", () => {
    expect(checkPinyin("ganmao", "gǎn mào")).toBe("toneless");
    expect(checkPinyin("gan4mao4", "gǎn mào")).toBe("wrong-tone");
    expect(checkPinyin("gan3", "gǎn mào")).toBe("wrong");
    expect(checkPinyin("gan3mao4", "gǎn mào")).toBe("exact");
  });

  it("is case-insensitive", () => {
    expect(checkPinyin("Zhōng Guó", "zhōng guó")).toBe("exact");
  });

  it("allows the tone changes of 一 and 不", () => {
    expect(checkPinyin("yi1xia4", "yí xià")).toBe("exact");
    expect(checkPinyin("bu4yao4", "bú yào")).toBe("exact");
    expect(checkPinyin("bu3yao4", "bú yào")).toBe("wrong-tone");
  });

  it("rejects other syllables", () => {
    expect(checkPinyin("ganma", "gǎn mào")).toBe("wrong");
    expect(checkPinyin("", "gǎn mào")).toBe("wrong");
  });
});
