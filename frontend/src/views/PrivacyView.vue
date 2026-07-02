<script setup lang="ts">
// Audit trust item — a plain, honest privacy page. Linked from the footer,
// the F-Droid listing, and the fastlane metadata. Content is written for
// the demo server (qingdu.itvoodoo.at); a self-hosted instance is governed
// by whoever runs it, and the page says so.
import { getApiBase, getDefaultApiBase } from "@/api/client";

const serverShown =
  getApiBase() || getDefaultApiBase() || "the server you selected";
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <header class="mb-8">
      <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
        轻读 QingDu
      </p>
      <h1 class="mt-1 font-display text-2xl font-medium tracking-tight text-fg">
        Privacy
      </h1>
      <p class="mt-2 text-sm text-fg-muted">
        Last updated 2026-07-02. Applies to the app and the maintainer's demo
        server. If you point the app at a self-hosted server, that server's
        operator — possibly you — controls the data instead.
      </p>
    </header>

    <div class="space-y-8 text-sm leading-relaxed text-fg">
      <section>
        <h2 class="mb-2 font-display text-lg font-medium">What's stored</h2>
        <p class="text-fg-muted">
          Your account is a username and a hashed password — no email, no
          phone number, no real name. Alongside it the server keeps what you
          create by using the app: saved texts, word states with their
          review schedule, vocabulary lists, review history, and settings.
          You can download all of it as one JSON file and delete the whole
          account yourself, both under Settings → Data &amp; account.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">What's not collected</h2>
        <p class="text-fg-muted">
          No analytics, no telemetry, no ads, no crash reporting, no
          third-party SDKs. The Android app talks to exactly one host: the
          server you chose at first launch ({{ serverShown }}). The one
          exception is the optional photo/scan import, which downloads its
          OCR engine from a public CDN the first time you use it.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">
          Third-party services the server uses
        </h2>
        <p class="text-fg-muted">
          When you tap a sentence to translate it, the demo server forwards
          that sentence to a translation provider — DeepL, Google Translate,
          or MyMemory, in that order of availability — and caches the
          result. Word and sentence audio is fetched from Google's public
          text-to-speech endpoint. Pronunciation recordings are decoded and
          scored in memory on the server and are not stored. If any of this
          is a concern, self-host: the server is the same open-source code,
          and translation keys are optional.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">Demo-server housekeeping</h2>
        <ul class="list-disc space-y-1 pl-5 text-fg-muted">
          <li>
            Signup attempts keep the requesting IP address for up to 24
            hours, purely for rate limiting, then they're deleted.
          </li>
          <li>
            Ordinary web-server logs (IP address, requested path) exist
            briefly for operations and abuse handling.
          </li>
          <li>
            Accounts unused for 30 days are paused; paused accounts unused
            for 90 days are deleted along with all their data. Signing in
            again at any point before that reactivates the account. The app
            warns you in advance.
          </li>
        </ul>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">Questions</h2>
        <p class="text-fg-muted">
          The entire stack is open source (MIT). Ask anything via
          <a
            href="https://github.com/mkampl/qingdu/issues"
            target="_blank"
            rel="noopener"
            class="text-accent underline-offset-2 hover:underline"
          >GitHub issues</a
          >.
        </p>
      </section>
    </div>
  </div>
</template>
