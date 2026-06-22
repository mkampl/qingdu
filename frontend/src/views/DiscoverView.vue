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
import type { LibraryForYouItem, LibraryManifestItem } from "@/api/client";
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

const browseBands = ref<{ label: string; band: string; items: LibraryManifestItem[] }[]>([]);

const BANDS: { label: string; band: string; levels: number[] }[] = [
  { label: "Beginner (HSK 1–3)", band: "beg", levels: [1, 2, 3] },
  { label: "Intermediate (HSK 4–6)", band: "int", levels: [4, 5, 6] },
  { label: "Advanced (HSK 7–9)", band: "adv", levels: [7, 8, 9] },
];

onMounted(async () => {
  // Browse-strip is anonymous — always fetch the manifest.
  try {
    const all = await api.listLibrary();
    browseBands.value = BANDS.map((b) => ({
      label: b.label,
      band: b.band,
      items: all.items.filter((it) => b.levels.includes(it.hsk_level)).slice(0, 4),
    }));
  } catch {
    // silent — strip is optional
  }

  // For-You is auth-gated.
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
    class="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-10 md:py-14 lg:px-10"
  >
    <header class="mb-6 sm:mb-10">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Discover
        </span>
        <span class="hidden h-px w-12 bg-border-subtle sm:block" aria-hidden="true" />
        <h1
          class="font-display text-xl font-medium tracking-tight text-fg sm:text-3xl"
        >
          Where to find Chinese
        </h1>
      </div>
    </header>

    <!-- Phase 1.5 — For You moves above Browse for authed users so the
         first thing they see is something tuned to their level, not a
         generic HSK rail. The block is auth-gated server-side (returns
         an empty items array when there's no known-word data), so it
         only renders for signed-in users with progress. -->
    <section v-if="forYou.length" class="mb-10 sm:mb-14">
      <header class="mb-4 sm:mb-5">
        <div class="mb-1.5 flex items-baseline gap-3 sm:mb-2">
          <span
            class="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
          >
            For you
          </span>
          <span class="hidden h-px w-8 bg-border-subtle sm:block" aria-hidden="true" />
        </div>
        <h2
          class="font-display text-lg font-medium tracking-tight text-fg sm:text-2xl"
        >
          On your level
        </h2>
        <p class="mt-1.5 max-w-prose text-sm leading-relaxed text-fg-muted sm:mt-2">
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

    <!-- Browse — anonymous-friendly entry into the library by HSK band. -->
    <section v-if="browseBands.length" class="mb-10 sm:mb-14">
      <header class="mb-4 sm:mb-5">
        <div class="mb-1.5 flex items-baseline gap-3 sm:mb-2">
          <span
            class="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
          >
            Browse
          </span>
          <span class="hidden h-px w-8 bg-border-subtle sm:block" aria-hidden="true" />
        </div>
        <h2
          class="font-display text-lg font-medium tracking-tight text-fg sm:text-2xl"
        >
          From the library
        </h2>
        <p class="mt-1.5 max-w-prose text-sm leading-relaxed text-fg-muted sm:mt-2">
          180 bundled HSK-aligned texts in the app. A taste below; the full
          collection lives on the
          <RouterLink
            to="/library"
            class="font-medium text-accent hover:underline"
          >
            Library
          </RouterLink>
          page with filters.
        </p>
      </header>

      <div class="space-y-5 sm:space-y-6">
        <div v-for="band in browseBands" :key="band.band">
          <p
            class="mb-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ band.label }}
          </p>
          <!-- Mobile: horizontal snap-scroll keeps each band a single visual
               row instead of a 4-tall stack. sm+: original grid. -->
          <ul
            class="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:snap-none sm:grid-cols-2 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-4"
          >
            <li
              v-for="item in band.items"
              :key="item.slug"
              class="w-[64%] shrink-0 snap-start sm:w-auto sm:shrink"
            >
              <button
                type="button"
                class="group flex h-full w-full flex-col gap-1 rounded-lg border border-border bg-bg-elevated p-3 text-left transition-shadow hover:shadow-md"
                @click="openLibraryText(item.slug)"
              >
                <p
                  class="text-cn-serif text-sm font-medium leading-snug text-fg group-hover:text-accent"
                >
                  {{ item.title }}
                </p>
                <p class="font-display text-[11px] italic text-fg-subtle">
                  {{ item.topic.replace(/-/g, " ") }}
                </p>
                <div class="mt-auto flex items-center gap-1 pt-1">
                  <span
                    class="rounded-full bg-bg-sunken px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-muted"
                  >
                    HSK {{ item.hsk_level }}
                  </span>
                  <span
                    class="rounded-full bg-bg-sunken px-1.5 py-0.5 font-mono text-[9px] tracking-wider text-fg-muted"
                  >
                    {{ item.char_count }} 字
                  </span>
                </div>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- Phase 1.5 — External-source groups collapsed into one disclosure.
         The 14 cards used to dominate the page (~2/3 of the scroll on
         mobile) even though they're static references most users hit
         rarely. Inside the details: each group's kicker becomes a
         subhead so the structure (Graded / News / Long-form / Meta)
         survives the collapse. -->
    <details
      class="group/disclosure rounded-lg border border-border-subtle bg-bg-elevated"
    >
      <summary
        class="flex cursor-pointer items-baseline justify-between gap-3 px-4 py-3 sm:px-5"
      >
        <span>
          <span
            class="block font-mono text-[10px] uppercase tracking-[0.22em] text-fg-subtle"
          >
            External sources
          </span>
          <span class="block font-display text-base font-medium text-fg sm:text-lg">
            Explore the wider Chinese web
          </span>
        </span>
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-transform group-open/disclosure:rotate-180"
          aria-hidden="true"
        >
          ▾
        </span>
      </summary>

      <div class="border-t border-border-subtle px-4 py-4 sm:px-5 sm:py-5">
        <p
          class="mb-6 max-w-prose font-display text-sm italic leading-relaxed text-fg-muted sm:text-base"
        >
          Pick a source, find an article, copy its URL and use
          <span class="font-medium text-fg">Import from URL</span>
          on the
          <RouterLink to="/" class="font-medium text-accent hover:underline">
            Reader
          </RouterLink>
          — the article body comes through clean of navigation and ads.
        </p>

        <div class="space-y-8">
          <section v-for="group in groups" :key="group.title">
            <header class="mb-3">
              <div class="mb-1 flex items-baseline gap-2">
                <span
                  class="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
                >
                  {{ group.kicker }}
                </span>
              </div>
              <h3
                class="font-display text-base font-medium tracking-tight text-fg sm:text-lg"
              >
                {{ group.title }}
              </h3>
              <p class="mt-1 max-w-prose text-xs leading-relaxed text-fg-muted">
                {{ group.blurb }}
              </p>
            </header>

            <ul class="grid grid-cols-1 gap-3 md:grid-cols-2">
              <li v-for="src in group.sources" :key="src.url">
                <a
                  :href="src.url"
                  target="_blank"
                  rel="noopener"
                  class="group flex h-full flex-col gap-2 rounded-lg border border-border bg-bg p-4 transition-shadow hover:shadow-md"
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
      </div>
    </details>
  </section>
</template>
