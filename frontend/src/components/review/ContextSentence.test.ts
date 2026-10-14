import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ContextSentence from "@/components/review/ContextSentence.vue";

describe("ContextSentence", () => {
  it("highlights the word and names the text it came from", () => {
    const w = mount(ContextSentence, {
      props: { sentence: "上个星期我感冒了。", word: "感冒", source: "去看医生" },
    });
    expect(w.find("mark").text()).toBe("感冒");
    expect(w.find('[data-testid="context-sentence"]').text()).toBe("上个星期我感冒了。");
    expect(w.text()).toContain("from “去看医生”");
  });

  it("falls back to 'your reading' without a source", () => {
    const w = mount(ContextSentence, { props: { sentence: "我在学中文。", word: "中文" } });
    expect(w.text()).toContain("from your reading");
  });
});
