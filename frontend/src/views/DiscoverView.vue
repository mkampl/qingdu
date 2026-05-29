<script setup lang="ts">
/**
 * Discover: two layers.
 *   1. "For You" — bundled library texts in the user's comprehension zone,
 *      sorted by adherence to 85-98% known-word ratio. Hidden when the user
 *      is unauthenticated or hasn't built any known-word state yet.
 *   2. Static external-source links — curation by hand.
 */

import { onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { LibraryForYouItem } from "@/api/client";
import type { AnalysisResponse } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";

const auth = useAuthStore();
const analysis = useAnalysisStore();
const toast = useToastStore();
const router = useRouter();

const forYou = ref<LibraryForYouItem[]>([]);
const forYouLoading = ref(false);
const forYouLoaded = ref(false);

onMounted(async () => {
  if (!auth.isAuthed) return;
  forYouLoading.value = true;
  try {
    const r = await api.libraryForYou({ limit: 9 });
    forYou.value = r.items;
  } catch {
    // silent — rail is optional
  } finally {
    forYouLoading.value = false;
    forYouLoaded.value = true;
  }
});

async function openLibraryText(slug: string) {
  try {
    const entry = await api.getLibraryEntry(slug);
    analysis.loadSaved(entry.text, entry.analyzed as AnalysisResponse, null);
    router.push("/");
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Couldn't open that text");
  }
}

interface Source {
  /** Chinese name where it exists, otherwise English. Rendered prominently. */
  name: string;
  /** Latinised name / translation, shown as a quieter subtitle. */
  subtitle?: string;
  /** Public-facing homepage. */
  url: string;
  /** One-sentence pitch — what this source is good for. */
  note: string;
  /** HSK range as a display string, e.g. "HSK 1–4" or "HSK 5+". */
  level: string;
  /** Optional badge — e.g. "open licence", "free trial", "RSS". */
  marker?: string;
}

interface Group {
  kicker: string;
  title: string;
  blurb: string;
  sources: Source[];
}

const groups: Group[] = [
  {
    kicker: "Graded",
    title: "Stories for learners",
    blurb:
      "HSK-labelled texts with audio, pinyin, and pop-up dictionaries. Best place to start if you're under HSK 5.",
    sources: [
      {
        name: "Mandarin Bean",
        url: "https://mandarinbean.com/all-lessons/",
        note: "100+ graded texts, recordings, toggleable pinyin, in-page dictionary.",
        level: "HSK 1–6+",
      },
      {
        name: "Chinese Graded Reader",
        url: "https://chinesegradedreader.com/",
        note: "Stories strictly limited to a single HSK level's vocabulary.",
        level: "HSK 1–5",
      },
      {
        name: "HSK Story",
        url: "https://hskstory.com/",
        note: "Multi-chapter narratives with audio and tap-to-define.",
        level: "HSK 1–4",
      },
      {
        name: "HSK Reading",
        url: "https://hskreading.com/",
        note: "Texts with voice-overs and comprehension questions.",
        level: "HSK 1–6",
      },
    ],
  },
  {
    kicker: "Slower",
    title: "Slower-paced & cultural",
    blurb:
      "A step up from graded readers, before tackling real news. Reads at conversational speed.",
    sources: [
      {
        name: "慢速中文",
        subtitle: "Slow Chinese (archive)",
        url: "https://archive.org/details/slowchinese_201909",
        note: "Cultural-narrative podcast with transcripts. Read at ~3 chars/sec.",
        level: "HSK 3–4",
        marker: "open access",
      },
    ],
  },
  {
    kicker: "News",
    title: "Current affairs",
    blurb:
      "Real-world Chinese. International broadcasters tend to be more approachable than mainland outlets — they explain context for an external audience.",
    sources: [
      {
        name: "美国之音中文网",
        subtitle: "VOA Chinese",
        url: "https://www.voachinese.com",
        note: "International news in approachable Mandarin. RSS available.",
        level: "HSK 4–5",
        marker: "RSS",
      },
      {
        name: "BBC 中文",
        subtitle: "BBC Chinese (simplified)",
        url: "https://www.bbc.com/zhongwen/simp",
        note: "International perspective in simplified Chinese.",
        level: "HSK 5–6",
        marker: "RSS",
      },
      {
        name: "德国之声中文",
        subtitle: "Deutsche Welle Chinese",
        url: "https://www.dw.com/zh",
        note: "German broadcaster — strong cultural and EU-affairs coverage.",
        level: "HSK 5–6",
      },
      {
        name: "自由亚洲电台",
        subtitle: "Radio Free Asia (Mandarin)",
        url: "https://www.rfa.org/mandarin",
        note: "Mandarin news service with an outsider perspective.",
        level: "HSK 5–6",
        marker: "RSS",
      },
    ],
  },
  {
    kicker: "Long-form",
    title: "Encyclopedia & classics",
    blurb:
      "When you want to read at length. Open-licence sources you can re-use freely. Difficulty varies — pick an approachable article first.",
    sources: [
      {
        name: "维基百科",
        subtitle: "Chinese Wikipedia",
        url: "https://zh.wikipedia.org",
        note: "Bottomless encyclopedia under CC BY-SA. Try a 月饼 / 茶 / 武术 article to start.",
        level: "varies",
        marker: "CC BY-SA",
      },
      {
        name: "维基文库",
        subtitle: "Chinese Wikisource",
        url: "https://zh.wikisource.org",
        note: "Public-domain classical Chinese texts — 论语, 红楼梦, 史记 and so on.",
        level: "HSK 8+",
        marker: "public domain",
      },
      {
        name: "Project Gutenberg",
        subtitle: "中文书库",
        url: "https://www.gutenberg.org/browse/languages/zh",
        note: "Public-domain literature in Chinese.",
        level: "HSK 7+",
        marker: "public domain",
      },
    ],
  },
  {
    kicker: "Meta",
    title: "Where to look next",
    blurb: "Two more meta-resources if you want to keep digging.",
    sources: [
      {
        name: "The Chairman's Bao — Reading list",
        url: "https://www.thechairmansbao.com/blog/chinese-reading-materials/",
        note: "Their own curated list. Useful for finding niche sources.",
        level: "meta",
      },
      {
        name: "Hacking Chinese",
        url: "https://www.hackingchinese.com/10-best-free-chinese-reading-resources-beginner-intermediate-advanced/",
        note: "Most actively maintained list of free resources.",
        level: "meta",
      },
    ],
  },
];
</script>

<template>
  <section
    class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10"
  >
    <header class="mb-10 flex items-baseline justify-between gap-4">
      <div class="flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Discover
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        <h1
          class="font-display text-2xl font-medium tracking-tight text-fg sm:text-3xl"
        >
          Where to find Chinese
        </h1>
      </div>
    </header>

    <!-- For You — bundled library texts in the user's comprehension zone. -->
    <section v-if="forYou.length" class="mb-14">
      <header class="mb-5">
        <div class="mb-2 flex items-baseline gap-3">
          <span
            class="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
          >
            For you
          </span>
          <span class="h-px w-8 bg-border-subtle" aria-hidden="true" />
        </div>
        <h2
          class="font-display text-xl font-medium tracking-tight text-fg sm:text-2xl"
        >
          On your level
        </h2>
        <p class="mt-2 max-w-prose text-sm leading-relaxed text-fg-muted">
          Short bundled texts where you already know 85-98% of the words.
          The sweet spot for reading without a dictionary on every line.
        </p>
      </header>

      <ul class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <li v-for="item in forYou" :key="item.slug">
          <button
            type="button"
            class="group flex h-full w-full flex-col gap-2 rounded-lg border border-border bg-bg-elevated p-4 text-left transition-shadow hover:shadow-md"
            @click="openLibraryText(item.slug)"
          >
            <div class="flex items-start justify-between gap-2">
              <p
                class="text-cn-serif text-base font-medium leading-snug text-fg group-hover:text-accent"
              >
                {{ item.title }}
              </p>
              <span
                class="shrink-0 rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent"
              >
                {{ Math.round(item.comprehension_score * 100) }}%
              </span>
            </div>
            <p class="text-cn-serif text-sm leading-relaxed text-fg-muted">
              {{ item.preview }}…
            </p>
            <div class="mt-auto flex items-center gap-2 pt-2">
              <span
                class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted"
              >
                HSK {{ item.hsk_level }}
              </span>
              <span
                class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] tracking-wider text-fg-muted"
              >
                {{ item.char_count }} 字
              </span>
              <span
                v-if="item.new_words > 0"
                class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] tracking-wider text-fg-muted"
              >
                {{ item.new_words }} new
              </span>
            </div>
          </button>
        </li>
      </ul>
    </section>

    <!-- Intro / how-to-use -->
    <div
      class="mb-12 max-w-prose rounded-lg border border-border-subtle bg-bg-elevated p-5"
    >
      <p class="font-display text-base italic leading-relaxed text-fg-muted">
        Open any source below to browse for something interesting. When you
        find an article you want to read, copy its URL and use
        <span class="font-medium text-fg">Import from URL</span>
        on the
        <RouterLink to="/" class="font-medium text-accent hover:underline">
          Reader
        </RouterLink>
        — the article body comes through clean of navigation and ads.
      </p>
    </div>

    <!-- Groups -->
    <div class="space-y-14">
      <section v-for="group in groups" :key="group.title">
        <header class="mb-5">
          <div class="mb-2 flex items-baseline gap-3">
            <span
              class="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
            >
              {{ group.kicker }}
            </span>
            <span class="h-px w-8 bg-border-subtle" aria-hidden="true" />
          </div>
          <h2
            class="font-display text-xl font-medium tracking-tight text-fg sm:text-2xl"
          >
            {{ group.title }}
          </h2>
          <p class="mt-2 max-w-prose text-sm leading-relaxed text-fg-muted">
            {{ group.blurb }}
          </p>
        </header>

        <ul class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <li v-for="src in group.sources" :key="src.url">
            <a
              :href="src.url"
              target="_blank"
              rel="noopener"
              class="group flex h-full flex-col gap-2 rounded-lg border border-border bg-bg-elevated p-4 transition-shadow hover:shadow-md"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <p
                    class="text-cn-serif text-base font-medium leading-snug text-fg group-hover:text-accent"
                  >
                    {{ src.name }}
                  </p>
                  <p
                    v-if="src.subtitle"
                    class="font-display text-[11px] italic text-fg-subtle"
                  >
                    {{ src.subtitle }}
                  </p>
                </div>
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 13 13"
                  fill="none"
                  class="mt-1 shrink-0 text-fg-subtle transition-colors group-hover:text-accent"
                  aria-hidden="true"
                >
                  <path
                    d="M4 3h6v6M9.5 3.5L3 10"
                    stroke="currentColor"
                    stroke-width="1.4"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </div>

              <p class="text-sm leading-relaxed text-fg-muted">
                {{ src.note }}
              </p>

              <div class="mt-auto flex items-center gap-2 pt-2">
                <span
                  class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted"
                >
                  {{ src.level }}
                </span>
                <span
                  v-if="src.marker"
                  class="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent"
                >
                  {{ src.marker }}
                </span>
              </div>
            </a>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>
